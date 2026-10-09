"""`encode` 노드와 인코더 후보 칸 (🆕 2026-10-07 그림자 배선 · 🔄 2026-10-09 응답에 싣는다 · D-323).

지키는 것
  ① 모델 폴더가 설정되지 않으면 인코더를 올리지 않는다 — 신호가 없고 판정은 그대로다 (CI · 모델 없는 기기)
  ② 인코더가 돌아도 **판정은 한 글자도 바뀌지 않는다** — 달라지는 것은 문장의 `encoder_candidates` 와 판 표지뿐이다. 스텁 · 컴파일본 둘 다
  ⑥ 후보는 `encoder_candidates` 한 칸에만 실린다 — `violations` · 분기 열쇠에 들지 않는다 (D-323 결정 1 · 3)
  ⑦ 거름은 유형 단위다 — 건강기능식품 전제 둘 · 일반식품 기능성 전제의 분기에서 건강기능식품 오인 후보가 빠진다 (D-323 결정 6)
  ⑧ 기록 판정의 후보는 전제별로 거른 후보의 합집합이다 — 어느 전제에서도 설 수 없는 후보만 빠진다 (2026-10-09 (다))
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
from app.contracts import (
    Category,
    EncoderTypeCandidate,
    HoldReason,
    Premise,
    ProductContext,
    SentenceJudgment,
    Verdict,
    Violation,
)

TEXT = "이 차를 마시면 당뇨가 낫습니다.\n피부가 10년 젊어집니다. 지금 50% 할인!"


class _Fake:
    """문장마다 거짓·과장 후보 하나를 내는 인코더."""

    def predict(self, text: str) -> enc.EncoderPrediction:
        scores = {Violation.거짓_과장: 0.9, Violation.질병_예방치료_표방: 0.1}
        cand = enc.EncoderCandidate(violation=Violation.거짓_과장, confidence=0.9, threshold=0.375)
        return enc.EncoderPrediction(scores=scores, candidates=(cand,), truncated=len(text) > 20)


class _FakeHF:
    """문장마다 거짓·과장과 건강기능식품 오인 후보 둘을 내는 인코더 — 전제별 거름을 보려고 둔다."""

    def predict(self, text: str) -> enc.EncoderPrediction:
        scores = {Violation.거짓_과장: 0.9, Violation.건강기능식품_오인: 0.8}
        cands = tuple(
            enc.EncoderCandidate(violation=v, confidence=c, threshold=0.5)
            for v, c in scores.items()
        )
        return enc.EncoderPrediction(scores=scores, candidates=cands)


#: 판정이 같은지 볼 때 빼는 칸 — 인코더가 채우는 것은 이 칸 하나다 (D-323)
ENC_ONLY = {"encoder_candidates"}


def _judgments(state: dict) -> list[dict]:
    return [s.model_dump(exclude=ENC_ONLY) for s in state.get("sentences", [])]


def _cands(s: SentenceJudgment) -> list[str]:
    return [c.violation.value for c in s.encoder_candidates]


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(enc.ENV_MODEL_DIR, raising=False)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: _Fake())


@pytest.fixture
def fake_hf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: _FakeHF())


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
    """🚨 이 테스트가 깨지면 인코더가 판정에 새고 있다 — 달라져도 되는 것은 후보 칸과 판 표지뿐이다 (D-323)."""
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
        # 후보는 실렸다 — 그 칸을 뺀 나머지가 위에서 같았다
        assert all(_cands(s) == ["거짓_과장"] for s in got["sentences"])
    assert all(not s.encoder_candidates for s in base["sentences"])
    # 응답(계약)도 같다 — 다른 것은 실행 시간 · 문장의 후보 칸 · 판 표지뿐이다
    drop = {"timings": True, "judged_by": True, "sentences": {"__all__": ENC_ONLY}}
    assert g.to_response(state).model_dump(exclude=drop) == g.to_response(base).model_dump(
        exclude=drop
    )
    # 판 표지 — 앞머리는 규칙 판정 그대로이고 인코더 판이 뒤에 붙는다. 가짜 폴더라 지문은 못 읽는다고 적힌다 (D-220)
    assert g.to_response(base).judged_by == g.JUDGED_BY
    assert g.to_response(state).judged_by == f"{g.JUDGED_BY}+enc:지문없음"


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
    # 후보는 제 칸에 — 유형과 확신(모델의 확률)이 그대로 실린다 (D-323 결정 1)
    assert all(
        s.encoder_candidates
        == [EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.9)]
        for s in state["sentences"]
    )


@pytest.mark.gate
def test_후보_거름은_유형_단위이고_전제가_여럿이면_합집합이다() -> None:
    e = g.SentEncoding(
        sent_id="s0",
        scores=(("거짓_과장", 0.9), ("건강기능식품_오인", 0.8)),
        candidates=("거짓_과장", "건강기능식품_오인"),
    )
    both, rest = ["거짓_과장", "건강기능식품_오인"], ["거짓_과장"]

    def kinds(premises: tuple[Premise, ...]) -> list[str]:
        return [c.violation.value for c in g._encoder_candidates(e, premises)]

    # 전제 하나 — 건강기능식품 오인이 서지 않는 전제 셋에서만 빠진다 (D-323 결정 6 · `pm.NO_HF_MISLEAD`)
    for p in Premise:
        assert kinds((p,)) == (rest if p in g.pm.NO_HF_MISLEAD else both), p
    # 품목의 전제 전부 — 한 전제에서라도 서면 남는다
    assert kinds(g.pm.PREMISES_OF[None]) == both  # 품목 미상
    assert kinds(g.pm.PREMISES_OF[Category.식품]) == both  # 식품 전제에서 선다
    assert kinds(g.pm.PREMISES_OF[Category.건기식]) == rest  # 두 전제 다 서지 않는다
    assert kinds(g.pm.PREMISES_OF[Category.화장품]) == both
    # 🔴 전제가 없는 품목은 거르지 않는다 — 빈 합집합으로 후보를 지우지 않는다 (D-220)
    assert g.pm.PREMISES_OF[Category.전용법_미수록] == ()
    assert kinds(()) == both
    # 신호가 없으면 빈 목록 · 확신은 모델의 확률 그대로
    assert g._encoder_candidates(None, (Premise.식품,)) == []
    assert [c.confidence for c in g._encoder_candidates(e, (Premise.식품,))] == [0.9, 0.8]


@pytest.mark.gate
def test_기록_판정은_품목의_전제로_거르고_분기_문장은_그_전제로_거른다(fake_hf: None) -> None:
    both, rest = ["거짓_과장", "건강기능식품_오인"], ["거짓_과장"]
    # 기록 판정 — 품목 미상 · 식품은 남고, 건강기능식품은 빠진다 (2026-10-09 (다))
    for category, want in ((None, both), (Category.식품, both), (Category.건기식, rest)):
        state, _ = g.run_review_stub(TEXT, ProductContext(category=category))
        assert all(_cands(s) == want for s in state["sentences"]), category
        assert all(not s.violations for s in state["sentences"])
    # 분기 문장 — 전제 하나로 거른다. 재료는 품목 미상 판정의 상태 그대로다(DB 없이도 전제별 문장은 선다)
    state, _ = g.run_review_stub(TEXT)
    for p in Premise:
        sents = g._premise_sentences(p, state, [])
        assert len(sents) == len(state["sentences"])
        want = rest if p in g.pm.NO_HF_MISLEAD else both
        assert all(_cands(s) == want for s in sents), p


@pytest.mark.gate
def test_기록_판정을_다시_짤_때_후보는_기록_판정의_것이_남는다() -> None:
    """가장 무거운 전제의 문장을 옮겨 와도 그 전제 하나로 거른 후보가 따라오지 않는다 (D-323 · (다))."""

    def cand(*vs: Violation) -> list[EncoderTypeCandidate]:
        return [EncoderTypeCandidate(violation=v, confidence=0.9) for v in vs]

    base = SentenceJudgment(
        sent_id="s0",
        text="가",
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=cand(Violation.거짓_과장, Violation.건강기능식품_오인),
    )
    hit = SentenceJudgment(
        sent_id="s0",
        text="가",
        verdict=Verdict.confirmed,
        violations=[Violation.거짓_과장],
        infeasibility=g.Infeasibility.B,
        evidence=[
            g.EvidenceArticle(law_id="002011", article="제3조제1항", item="제1호", basis=True)
        ],
        risk=g.RiskAssessment(floor=g.Risk.R2, final=g.Risk.R2),
        encoder_candidates=cand(Violation.거짓_과장),
    )
    quiet = base.model_copy(update={"encoder_candidates": cand(Violation.거짓_과장)})
    # 전제마다 판정이 갈린다 → 보류로 다시 짠다 · 모든 전제에서 같다 → 가장 무거운 문장을 옮긴다. 두 길 다 후보는 `base` 의 것
    for per in ([hit, quiet], [hit, hit]):
        r = g._recorded(base, per, HoldReason.cat_unknown)
        assert r is not None
        assert r.encoder_candidates == base.encoder_candidates
    # 분기 열쇠에는 후보가 들지 않는다 — 후보만 다르면 같은 판정이다 (D-323 결정 1)
    assert g._judgment_key(base) == g._judgment_key(quiet)


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
    # 유형 무관(규약 G1) — 틀린 유형으로 걸린 행(`miss`)도 센다. 유형 적중과 다른 수다
    assert rep["flagged_any"] == 2


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
