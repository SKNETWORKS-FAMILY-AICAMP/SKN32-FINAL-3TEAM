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
  ⑨ 🆕 2026-10-14 (D-336 · D-339) 품목 입력 판은 문장마다 **한 배치**로 부르고, 기록 판정은 요청 품목의 입력(모르면 「모름」) ·
     분기는 그 전제의 입력을 읽는다(일반상품 → 「모름」) · 판정은 그대로다 · 로더는 학습과 다른 입력 계약이면 멈춘다(D-220)

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
    # 🚨 지우지 않고 빈 값으로 둔다 — 지우면 프로세스에서 처음 `collect.env.load()` 가 불릴 때 `.env` 의 값이 들어와
    #    (override=False 는 「없는 키」를 채운다) 켜 둔 기기에서 이 파일만 돌리면 「설정 없음」이 아니게 된다 (2026-10-14)
    monkeypatch.setenv(enc.ENV_MODEL_DIR, "")


#: 🆕 2026-10-13 (D-333) — 가짜 폴더는 잠금의 판이 아니다. 여기서 보는 것은 그래프 배선이므로 잠금 대조는 연다 —
#:    앱이 잠금 밖 판을 거절하는지는 `tests/test_model_lock.py` 가 잰다
def _unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enc, "checked_dir", lambda model_dir: None)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: _Fake())
    _unlock(monkeypatch)


@pytest.fixture
def fake_hf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: _FakeHF())
    _unlock(monkeypatch)


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
    _unlock(monkeypatch)
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
    # 판 표지 — 앞머리는 규칙 판정 그대로이고 인코더 판이 뒤에 붙는다.
    # 🔄 2026-10-13 (D-333) — 표지는 판 지문(`+encb:` · 폴더의 파일 전부)이다. 가짜 폴더는 빈 폴더의 판 지문이 적힌다
    assert g.to_response(base).judged_by == g.JUDGED_BY
    assert (
        g.to_response(state).judged_by
        == f"{g.JUDGED_BY}{enc.JUDGED_BY_MARK}{enc.bundle_mark(tmp_path)}"
    )
    assert enc.ran(g.to_response(state).judged_by) and not enc.ran(g.to_response(base).judged_by)


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
    # 🔄 2026-10-12 (D-327) — 후보마다 참조 조항이 붙는다. 유형 · 확신은 종전 그대로이고 조항은 따로 본다
    assert all(
        [c.model_copy(update={"references": []}) for c in s.encoder_candidates]
        == [EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.9)]
        for s in state["sentences"]
    )
    # 품목을 모르면 세 법으로 보낸다 — 거짓 · 과장의 조항이 세 법 모두에서 실린다. 🚨 근거(`evidence`)에는 섞이지 않는다
    refs = state["sentences"][0].encoder_candidates[0].references
    assert {r.law_id for r in refs} == {"002011", "005361", "013094", "013453", "002015", "008741"}
    assert all(r.basis is False for r in refs)
    assert all(not s.evidence for s in state["sentences"])


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
        if p is Premise.화장품:
            continue  # 🔄 2026-10-14 (D-338) — 화장품 전제는 옮김 표를 탄다(`tests/test_substantiation.py`)
        assert kinds((p,)) == (rest if p in g.pm.NO_HF_MISLEAD else both), p
    assert kinds((Premise.화장품,)) == [
        "거짓_과장",
        "의약품_오인",
    ]  # 건기식 오인 → 의약품 오인(조건부)
    # 품목의 전제 전부 — 한 전제에서라도 서면 남는다
    assert kinds(g.pm.PREMISES_OF[None]) == both  # 품목 미상
    assert kinds(g.pm.PREMISES_OF[Category.식품]) == both  # 식품 전제에서 선다
    assert kinds(g.pm.PREMISES_OF[Category.건기식]) == rest  # 두 전제 다 서지 않는다
    assert kinds(g.pm.PREMISES_OF[Category.화장품]) == ["거짓_과장", "의약품_오인"]  # D-338
    # 🔴 전제가 없는 품목은 거르지 않는다 — 빈 합집합으로 후보를 지우지 않는다 (D-220)
    assert g.pm.PREMISES_OF[Category.전용법_미수록] == ()
    assert kinds(()) == both
    # 신호가 없으면 빈 목록 · 확신은 모델의 확률 그대로
    assert g._encoder_candidates(None, (Premise.식품,)) == []
    assert [c.confidence for c in g._encoder_candidates(e, (Premise.식품,))] == [0.9, 0.8]


@pytest.mark.gate
def test_인정_없는_건강기능식품_전제에서는_건기식_오인_후보를_거짓과장으로_옮긴다() -> None:
    """🆕 2026-10-10 (팀장 판정 (나)) — 같은 문구가 제품에 따라 다른 조항에 걸린다. 3호가 서지 않는 자리에 4.나가 선다."""
    hf_only = g.SentEncoding(
        sent_id="s0", scores=(("건강기능식품_오인", 0.8),), candidates=("건강기능식품_오인",)
    )

    def got(premises: tuple[Premise, ...]) -> list[tuple[str, float, str | None]]:
        return [
            (c.violation.value, c.confidence, c.moved_from.value if c.moved_from else None)
            for c in g._encoder_candidates(hf_only, premises)
        ]

    native, moved = ("건강기능식품_오인", 0.8, None), ("거짓_과장", 0.8, "건강기능식품_오인")
    assert got((Premise.식품,)) == [native]
    assert got((Premise.건기식_인정,)) == []  # 인정받은 제품이면 서는 것이 없다
    assert got((Premise.일반식품_기능성,)) == []
    assert got((Premise.건기식_비인정,)) == [moved], (
        "확률은 옮기기 전 유형의 것이고 원래 유형을 적는다"
    )
    # 합집합 — 품목이 건강기능식품이면 옮긴 후보만 · 품목 미상이면 둘 다 (한 전제에서라도 서면 남는다)
    assert got(g.pm.PREMISES_OF[Category.건기식]) == [moved]
    assert got(g.pm.PREMISES_OF[Category.식품]) == [native]
    assert got(g.pm.PREMISES_OF[None]) == [native, moved]
    assert got(()) == [native]  # 전제 없는 품목 — 거르지도 옮기지도 않는다
    # ⛔ 인코더가 거짓_과장을 직접 냈으면 더하지 않는다 — 직접 낸 쪽의 확률이 남는다
    both = g.SentEncoding(
        sent_id="s0",
        scores=(("거짓_과장", 0.6), ("건강기능식품_오인", 0.8)),
        candidates=("거짓_과장", "건강기능식품_오인"),
    )
    assert [
        (c.violation.value, c.confidence, c.moved_from)
        for c in g._encoder_candidates(both, (Premise.건기식_비인정,))
    ] == [("거짓_과장", 0.6, None)]


@pytest.mark.gate
def test_평가_도구는_옮긴_후보를_직접_낸_후보와_섞지_않는다() -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    s = SentenceJudgment(
        sent_id="s0",
        text="가",
        verdict=g.Verdict.hold,
        hold_reason=g.HoldReason.low_conf,
        encoder_candidates=[
            g.EncoderTypeCandidate(violation=Violation.질병_예방치료_표방, confidence=0.7),
            g.EncoderTypeCandidate(
                violation=Violation.거짓_과장,
                confidence=0.8,
                moved_from=Violation.건강기능식품_오인,
            ),
        ],
    )
    p = eg.predict({"sentences": [s]})
    assert p["enc_candidates"] == ["질병_예방치료_표방"]
    assert p["enc_moved"] == ["거짓_과장"]


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
        if p is Premise.화장품:  # 화장품이라면 건기식 오인 → 의약품 오인 (D-338)
            want = ["거짓_과장", "의약품_오인"]
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


@pytest.mark.gate
def test_옮긴_후보는_전제가_인정_없는_건강기능식품인_행에서만_적중이다() -> None:
    """🔴 2026-10-11 (D-326 보충 12) — 인코더가 기준 전제로 배우면 4.나 행에 `건강기능식품_오인` 을 내고 그래프가 옮긴다.

    그 행의 정답은 옮긴 쪽이다. ⛔ 전제가 없는 행까지 세면 정답이 마침 거짓_과장인 행이 건강기능식품 오인 신호로 맞는다.
    """
    from scripts import eval_graph as eg  # noqa: PLC0415

    p = {
        "encoded": True,
        "types": [],
        "candidates": [],
        "enc_candidates": [],
        "enc_moved": ["거짓_과장"],
    }
    mine = {"text": "가", "labels": ["거짓_과장"], "split": "train", "전제": "건기식_비인정"}
    none = {"text": "나", "labels": ["거짓_과장"], "split": "train", "전제": None}
    food = {"text": "다", "labels": ["거짓_과장"], "split": "train", "전제": "식품"}
    old = {"text": "라", "labels": ["거짓_과장"], "split": "train"}  # 전제 칸이 없는 옛 골든
    for row, want in ((mine, 1), (none, 0), (food, 0), (old, 0)):
        rep = eg.encoder_report([row], [p], [(row, p)])
        assert (rep["positive"], rep["detected_with_encoder"], rep["flagged_any"]) == (
            1,
            want,
            want,
        )
    # 인코더가 직접 낸 후보는 전제와 무관하게 센다 — 종전 그대로
    direct = {**p, "enc_candidates": ["거짓_과장"], "enc_moved": []}
    assert eg.encoder_report([none], [direct], [(none, direct)])["detected_with_encoder"] == 1


@pytest.mark.gate
def test_유형별_탐지는_세_칸을_따로_세고_인코더가_안_돈_행은_분모에서_뺀다() -> None:
    """🆕 2026-10-11 (D-321 결정 6 · D-311 보충) — 확정 ⊆ 사전 후보까지 ⊆ 인코더 후보까지 · (행 · 유형) 단위."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    def pred(types=(), cand=(), enc=(), moved=(), encoded=True) -> dict:
        return {
            "encoded": encoded,
            "types": list(types),
            "candidates": list(cand),
            "enc_candidates": list(enc),
            "enc_moved": list(moved),
        }

    two = {"text": "가", "labels": ["거짓_과장", "의약품_오인"], "split": "train"}
    one = {"text": "나", "labels": ["거짓_과장"], "split": "train"}
    off = {"text": "다", "labels": ["의약품_오인"], "split": "train"}
    na = {"text": "라", "labels": ["거짓_과장"], "split": "train", "전제": "건기식_비인정"}
    sc = [
        (two, pred(types=["거짓_과장"], enc=["의약품_오인"])),
        (one, pred(cand=["거짓_과장"])),
        (off, pred(enc=["의약품_오인"], encoded=False)),  # 안 돈 행 — 후보 칸이 있어도 세지 않는다
        (na, pred(moved=["거짓_과장"])),  # 옮긴 후보는 그 전제인 행에서 적중이다 (D-326 보충 12)
    ]
    got = eg.detect_by_type(sc)
    assert got == {"거짓_과장": (3, 1, 2, 3, 3), "의약품_오인": (2, 0, 0, 1, 1)}
    # 정답의 합(5)은 행 수(4)보다 크다 — 행 단위 수(`detect`)와 맞대지 않는다
    assert sum(v[0] for v in got.values()) == 5
    # 옮긴 후보 규칙은 `encoder_report` 와 한 함수다 — 전제가 없으면 적중이 아니다
    assert eg.detect_by_type([({**na, "전제": None}, sc[3][1])]) == {"거짓_과장": (1, 0, 0, 1, 0)}


# ── 🆕 2026-10-14 (D-336 · D-339) — 품목 입력 판 ─────────────────────────────

#: 품목 입력마다 다른 유형을 내는 가짜 — 전제 거름 · 옮김을 타지 않는 유형만 쓴다(어느 입력의 신호가 어디 실렸는지만 본다)
_BY_INPUT = {
    "모름": Violation.소비자_기만,
    "식품": Violation.거짓_과장,
    "건기식": Violation.후기_체험기_기만,
    "화장품": Violation.비방광고,
}


class _FakePair:
    takes_category = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def predict_many(self, text: str, inputs: tuple[str, ...]) -> list[enc.EncoderPrediction]:
        self.calls.append(tuple(inputs))
        out = []
        for x in inputs:
            v = _BY_INPUT[x]
            out.append(
                enc.EncoderPrediction(
                    scores={v: 0.9},
                    candidates=(enc.EncoderCandidate(violation=v, confidence=0.9, threshold=0.5),),
                )
            )
        return out

    def predict(self, text: str, category_input: str | None = None) -> enc.EncoderPrediction:
        raise AssertionError("품목 입력 판은 그래프에서 한 배치(predict_many)로 부른다")


@pytest.fixture
def fake_pair(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakePair:
    model = _FakePair()
    monkeypatch.setenv(enc.ENV_MODEL_DIR, str(tmp_path))
    monkeypatch.setattr(enc, "encoder_at", lambda model_dir: model)
    _unlock(monkeypatch)
    return model


@pytest.mark.gate
def test_품목_입력_판은_한_배치로_부르고_기록은_모름_분기는_그_전제의_품목이다(
    fake_pair: _FakePair, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, _ = g.run_review_stub(TEXT)
    n = len(state["sents"])
    # 품목 미상 — 기록(모름)이 맨 앞 · 분기 여섯의 입력은 넷으로 모인다 · 문장마다 한 번
    assert fake_pair.calls == [("모름", "식품", "건기식", "화장품")] * n
    assert len(state["encodings"]) == 4 * n
    assert all(_cands(s) == ["소비자_기만"] for s in state["sentences"])
    want = {
        Premise.식품: "거짓_과장",
        Premise.일반식품_기능성: "거짓_과장",
        Premise.건기식_인정: "후기_체험기_기만",
        Premise.건기식_비인정: "후기_체험기_기만",
        Premise.화장품: "비방광고",
        Premise.일반상품: "소비자_기만",  # 일반상품 → 모름 (D-339 결정 3)
    }
    for p, kind in want.items():
        assert all(_cands(x) == [kind] for x in g._premise_sentences(p, state, [])), p
    # 판정은 그대로다 — 인코더를 끈 판정과 후보 칸을 뺀 나머지가 같다 (D-323)
    monkeypatch.setenv(enc.ENV_MODEL_DIR, "")
    base, _ = g.run_review_stub(TEXT)
    assert _judgments(state) == _judgments(base)
    assert state["outcome"] == base["outcome"]


@pytest.mark.gate
@pytest.mark.parametrize(
    ("category", "inputs", "kind"),
    [
        (Category.화장품, ("화장품",), "비방광고"),
        (Category.건기식, ("건기식",), "후기_체험기_기만"),
        (Category.식품, ("식품",), "거짓_과장"),
        (Category.일반상품, ("모름",), "소비자_기만"),
        (Category.전용법_미수록, ("모름",), "소비자_기만"),
    ],
)
def test_품목을_알면_그_품목의_입력_하나다(
    fake_pair: _FakePair, category: Category, inputs: tuple[str, ...], kind: str
) -> None:
    """재검수 · 카피 생성(품목을 넘긴다)이 그 품목 분기와 같은 계산을 탄다 (D-336 결정 3)."""
    state, _ = g.run_review_stub(TEXT, ProductContext(category=category))
    assert set(fake_pair.calls) == {inputs}
    assert all(_cands(s) == [kind] for s in state["sentences"])


@pytest.mark.gate
def test_평가_도구는_품목_입력_판의_신호를_문장_수로_센다(fake_pair: _FakePair) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    state, _ = g.run_review_stub(TEXT)
    p = eg.predict(state)
    assert p["encoded"] is True  # 신호는 문장 × 입력 넷이지만 문장은 다 돌았다
    assert p["enc_inputs"] == ["건기식", "모름", "식품", "화장품"]
    assert p["enc_candidates"] == ["소비자_기만"] and p["enc_conf"] == {"소비자_기만": 0.9}


def _pair_scheme(tmp_path: Path, **over: object) -> Path:
    import json  # noqa: PLC0415

    raw: dict[str, object] = {
        "label_list": ["거짓_과장", "의약품_오인"],
        "label_thresholds": {"거짓_과장": 0.5, "의약품_오인": 0.6},
        "label_thresholds_by_cat": {"거짓_과장": 0.7, "의약품_오인": 0.4},
        "input_format": {
            "pair": True,
            "first": "품목",
            "values": ["식품", "건기식", "화장품"],
            "unknown": "모름",
            "truncation": "only_second",
            "max_len": 136,
            # 박수진 스킴의 표 그대로 — 일반식품_기능성 줄이 없다(앱의 대응을 쓴다 · D-339 결정 3)
            "premise_to_input": {
                "식품": "식품",
                "건기식_인정": "건기식",
                "건기식_비인정": "건기식",
                "화장품": "화장품",
                "일반상품": "모름",
            },
        },
        "max_len": 136,
    }
    for k, v in over.items():
        if v is None:
            raw.pop(k, None)
        else:
            raw[k] = v
    (tmp_path / "label_scheme.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


@pytest.mark.gate
def test_품목_입력_스킴은_문턱_두_벌을_입력에_맞춰_쓴다(tmp_path: Path) -> None:
    scheme = enc.load_label_scheme(_pair_scheme(tmp_path))
    assert scheme.pair and scheme.max_tokens == 136
    assert scheme.thresholds_for("모름") == scheme.thresholds_for(None) == scheme.thresholds
    assert scheme.thresholds_for("화장품")[Violation.의약품_오인] == 0.4
    # 같은 확률이 입력에 따라 다른 후보가 된다 — 모름(0.6)에서는 서지 않고 품목 앎(0.4)에서는 선다
    probs = [0.6, 0.5]
    assert [c.violation for c in enc.select_candidates(scheme, probs, "모름")] == [
        Violation.거짓_과장
    ]
    assert [c.violation for c in enc.select_candidates(scheme, probs, "식품")] == [
        Violation.의약품_오인
    ]


@pytest.mark.gate
@pytest.mark.parametrize(
    ("over", "match"),
    [
        # 종전 결정의 칸 이름은 받지 않는다 — 두 이름이 섞이지 않게 (D-339 결정 2 개정)
        (
            {
                "label_thresholds_by_cat": None,
                "label_thresholds_known": {"거짓_과장": 0.7, "의약품_오인": 0.4},
            },
            "label_thresholds_by_cat",
        ),
        ({"label_thresholds_by_cat": {"거짓_과장": 0.7}}, "label_thresholds_by_cat"),
        ({"max_len": None}, "max_len"),
        ({"max_len": 128}, "max_len"),
    ],
)
def test_품목_입력_스킴이_어긋나면_멈춘다(tmp_path: Path, over: dict, match: str) -> None:
    with pytest.raises(enc.EncoderUnavailable, match=match):
        enc.load_label_scheme(_pair_scheme(tmp_path, **over))


@pytest.mark.gate
@pytest.mark.parametrize(
    "fmt_over",
    [
        {"premise_to_input": {"일반상품": "식품"}},  # 앱의 대응과 다르다
        {"premise_to_input": {"없는_전제": "식품"}},
        {"values": ["식품", "건기식", "화장품", "일반상품"]},  # 학습한 품목 입력이 앱의 표와 다르다
        {"unknown": "미상"},
        {"truncation": "longest_first"},
        {"pair": False},
    ],
)
def test_입력_계약이_앱의_표와_다르면_멈춘다(tmp_path: Path, fmt_over: dict) -> None:
    base = _pair_scheme(tmp_path)
    import json  # noqa: PLC0415

    raw = json.loads((base / "label_scheme.json").read_text(encoding="utf-8"))
    raw["input_format"] = {**raw["input_format"], **fmt_over}
    (base / "label_scheme.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(enc.EncoderUnavailable):
        enc.load_label_scheme(base)


@pytest.mark.gate
def test_문장만_받는_판에_품목_앎_문턱이_있으면_멈춘다(tmp_path: Path) -> None:
    """어느 입력으로 배웠는지 모르는 판을 올리지 않는다 (D-220). 문장만 받는 판은 종전과 같다."""
    with pytest.raises(enc.EncoderUnavailable, match="input_format"):
        enc.load_label_scheme(_pair_scheme(tmp_path, input_format=None))
    plain = enc.load_label_scheme(
        _pair_scheme(tmp_path, input_format=None, label_thresholds_by_cat=None, max_len=None)
    )
    assert not plain.pair and plain.thresholds_for("화장품") == plain.thresholds


@pytest.mark.gate
def test_인코더_입력의_대응은_전제_품목_표에서_낸다() -> None:
    """정본은 `app/premise.py` 하나다 (D-339 결정 3) — 일반식품_기능성은 식품 · 일반상품은 모름."""
    pm = g.pm
    assert {p: pm.premise_input(p) for p in Premise} == {
        Premise.식품: "식품",
        Premise.일반식품_기능성: "식품",
        Premise.건기식_인정: "건기식",
        Premise.건기식_비인정: "건기식",
        Premise.화장품: "화장품",
        Premise.일반상품: "모름",
    }
    assert pm.encoder_input(None) == pm.ENCODER_UNKNOWN
    assert g._encoder_inputs(None) == ("모름", "식품", "건기식", "화장품")


@pytest.mark.gate
def test_거름을_끈_평가는_전제로_거르지도_옮기지도_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """앱은 늘 켠다 — 끄는 것은 평가 도구의 dev 비교뿐이다 (D-336 결정 5)."""
    e = g.SentEncoding(
        sent_id="s0", scores=(("건강기능식품_오인", 0.8),), candidates=("건강기능식품_오인",)
    )
    assert g._encoder_candidates(e, (Premise.건기식_비인정,))[0].moved_from is not None
    monkeypatch.setattr(g, "_ENCODER_FILTER", True)
    g.disable_encoder_filter()
    for p in Premise:
        got = g._encoder_candidates(e, (p,))
        assert [(c.violation.value, c.moved_from) for c in got] == [("건강기능식품_오인", None)], p


@pytest.mark.gate
def test_조합_칸_표는_인코더가_돈_행만_센다() -> None:
    """D-340 결정 1 · 8 — 칸은 기록 판정의 것이고, 인코더가 안 돈 행을 「조용」 칸에 넣지 않는다 (D-220)."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    def pred(**kw: object) -> dict:
        return {"committed": False, "candidates": [], "enc_candidates": [], "encoded": True, **kw}

    rows = [{"조건": c} for c in ("C", "D", "A", "M", "L", "B")]
    preds = [
        pred(candidates=["질병_예방치료_표방"], enc_candidates=["질병_예방치료_표방"]),
        pred(candidates=["질병_예방치료_표방"], enc_candidates=["거짓_과장"]),
        pred(enc_candidates=["거짓_과장"]),
        pred(),
        pred(committed=True),
        pred(encoded=False),
    ]
    assert eg.combo_report(rows, preds) == {
        eg.COMBO_CELLS[0]: (1, 0, 1, 0),
        eg.COMBO_CELLS[1]: (1, 1, 0, 0),
        eg.COMBO_CELLS[2]: (1, 0, 1, 0),
        eg.COMBO_CELLS[4]: (1, 1, 0, 0),
        eg.COMBO_CELLS[5]: (1, 0, 0, 1),
    }
