"""`encode` 노드 — 인코더 **그림자 배선** (🆕 2026-10-07).

지키는 것
  ① 모델 폴더가 설정되지 않으면 인코더를 올리지 않는다 — 신호가 없고 판정은 그대로다 (CI · 모델 없는 기기)
  ② 인코더가 돌아도 **판정은 한 글자도 바뀌지 않는다** — `judge` 는 `encodings` 를 읽지 않는다. 스텁 · 컴파일본 둘 다
  ③ 설정했는데 올리지 못하면 **경고를 남기고** 규칙 판정으로 간다 — 조용히 꺼지지 않는다 (D-162 · D-220)
  ④ 평가 도구는 인코더 신호를 **따로** 센다 — 문장 판정의 보류 후보(D-311)와 섞지 않고, 인코더가 안 돈 행을 「조용했다」로 세지 않는다
  ⑤ 평가 도구는 켰는데 못 올리면 **멈춘다** — 인코더 없는 수가 인코더 수처럼 찍히지 않게

⛔ 실제 가중치는 여기서 올리지 않는다 — 가짜 인코더를 끼운다. 로더 자체(라벨 계약 · 문턱)는 `tests/test_encoder.py` 가 본다.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app import encoder as enc
from app import graph as g
from app.contracts import Violation

TEXT = "이 차를 마시면 당뇨가 낫습니다.\n피부가 10년 젊어집니다. 지금 50% 할인!"


class _Fake:
    """문장마다 거짓·과장 후보 하나를 내는 인코더."""

    def predict(self, text: str) -> enc.EncoderPrediction:
        scores = {Violation.거짓_과장: 0.9, Violation.질병_예방치료_표방: 0.1}
        cand = enc.EncoderCandidate(violation=Violation.거짓_과장, confidence=0.9, threshold=0.375)
        return enc.EncoderPrediction(scores=scores, candidates=(cand,), truncated=len(text) > 20)


def _judgments(state: dict) -> list[dict]:
    return [s.model_dump() for s in state.get("sentences", [])]


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(enc.ENV_MODEL_DIR, raising=False)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: _Fake())


@pytest.mark.gate
def test_설정이_없으면_인코더를_올리지_않는다(off: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(model_dir: Path) -> None:
        raise AssertionError("설정이 없는데 모델을 올렸다")

    monkeypatch.setattr(enc, "encoder_at", boom)
    assert enc.configured_dir() is None
    state, visited = g.run_review_stub(TEXT)
    assert "encode" in visited
    assert not state.get("encodings")


@pytest.mark.gate
def test_인코더가_돌아도_판정은_바뀌지_않는다(
    off: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """🚨 그림자 배선의 정의다 — 이 테스트가 깨지면 인코더가 판정에 새고 있다."""
    base, base_visited = g.run_review_stub(TEXT)
    base_out = g.build_review().invoke({"text": TEXT})

    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: _Fake())
    state, visited = g.run_review_stub(TEXT)
    out = g.build_review().invoke({"text": TEXT})

    assert visited == base_visited
    for got, want in ((state, base), (out, base_out)):
        assert _judgments(got) == _judgments(want)
        assert got["outcome"] == want["outcome"]
        assert got.get("branches") == want.get("branches")
        assert [e.sent_id for e in got["encodings"]] == [s.sent_id for s in got["sentences"]]
    # 응답(계약)도 같다 — 실행 시간만 다르다. 인코더 신호는 응답에 나가지 않는다
    drop = {"timings"}
    assert g.to_response(state).model_dump(exclude=drop) == g.to_response(base).model_dump(
        exclude=drop
    )


@pytest.mark.gate
def test_신호는_문장마다_한_벌이고_문장_판정에_섞이지_않는다(fake: None) -> None:
    state, _ = g.run_review_stub(TEXT)
    e = state["encodings"]
    assert len(e) == len(state["sents"]) == 3
    assert all(x.candidates == ("거짓_과장",) for x in e)
    assert dict(e[0].scores)["거짓_과장"] == 0.9
    assert [x.truncated for x in e] == [
        len(t) > 20 for t in state["sents"]
    ]  # 잘림 표시가 문장마다 실린다
    # ⛔ 문장 판정의 유형 칸은 고쳐 쓰기가 읽는다 — 인코더 후보가 거기 들어가면 안 된다
    assert all(not s.violations for s in state["sentences"])


@pytest.mark.gate
def test_못_올리면_경고를_남기고_규칙_판정으로_간다(
    off: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base, _ = g.run_review_stub(TEXT)
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path / "없는_폴더"))
    g._warn_encoder_off.cache_clear()
    with caplog.at_level(logging.WARNING, logger="copylane.graph"):
        state, _ = g.run_review_stub(TEXT)
    assert not state.get("encodings")
    assert _judgments(state) == _judgments(base)
    assert any("판정 인코더를 올리지 못했다" in r.getMessage() for r in caplog.records)


@pytest.mark.gate
def test_평가_도구는_인코더_신호를_따로_센다(fake: None) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    state, _ = g.run_review_stub(TEXT)
    p = eg.predict(state)
    assert p["encoded"] is True
    assert p["enc_candidates"] == ["거짓_과장"]
    assert p["candidates"] == []  # 문장 판정의 보류 후보와 다른 칸이다 (D-311)

    hit = {"text": "가", "labels": ["거짓_과장"], "split": "test_sentence"}
    miss = {"text": "나", "labels": ["의약품_오인"], "split": "test_sentence"}
    rows = [hit, miss]
    rep = eg.encoder_report(rows, [p, p], [(hit, p), (miss, p)])
    assert rep["rows"] == 2
    assert (rep["positive"], rep["detected"], rep["detected_with_encoder"]) == (2, 0, 1)


@pytest.mark.gate
def test_인코더가_안_돈_행은_세지_않는다(off: None) -> None:
    """🔴 없음은 조용함이 아니다 — 인코더 없이 잰 행이 「후보 없음」으로 집계되면 안 된다 (D-220)."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    state, _ = g.run_review_stub(TEXT)
    p = eg.predict(state)
    assert p["encoded"] is False and p["enc_candidates"] == []
    row = {"text": "가", "labels": ["거짓_과장"], "split": "test_sentence"}
    assert eg.encoder_report([row], [p], [(row, p)]) == {"rows": 0}


@pytest.mark.gate
def test_평가_도구는_켰는데_못_올리면_멈춘다(off: None, tmp_path: Path) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    assert eg.use_encoder(None) == {}
    with pytest.raises(SystemExit, match="인코더를 올리지 못했다"):
        eg.use_encoder(tmp_path / "없는_폴더")
