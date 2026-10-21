"""평가 도구 — 답 경로 · 불변식 표시 · 품목만 넘기기 (🆕 2026-10-21 · D-348 보충 35 결정 1 · 2 · 인계 10-21 클론B §1 #1 · #2).

지키는 것 — `scripts/eval_graph.py`
  ① 답 경로 — 질문이 선 행만 두 벌(모두 예 · 모두 아니오)로 다시 판정 · 새 질문이 서면 이어 묻는다 · 상한 뒤 남은 질문은 따로
  ② 채점표 — A · B 「아니오」에 골든 유형 = 도달 · D 「아니오」에 위반 = 답에 달린 오탐 · 상한 뒤 남은 행은 도달로 세지 않는다
  ③ 불변식 로그가 행에 실린다(`invariant`) · 요약에 행 수
  ④ `--category-only` 는 골든 전제의 품목만 넘긴다 · 행에 넘긴 제품 정보(`product`)가 실린다
그래프는 대역이다(실제 판정 규칙을 재지 않는다 — 도구의 배선만).
"""

from __future__ import annotations

import logging

import pytest

from app import graph as g
from app.contracts import (
    Answer,
    Category,
    EvidenceArticle,
    HoldReason,
    Infeasibility,
    Premise,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    SubstBranch,
    Verdict,
    Violation,
)
from scripts import eval_graph as eg

pytestmark = pytest.mark.gate

_EV = EvidenceArticle(
    law_id="013094", article="제8조", item="제1항제4호"
)  # `tests/test_contracts.py` `_EV` 와 같은 좌표
_SUBST = SubstBranch(
    substantiated_max=Risk.R0, accepted_evidence=["시험 또는 조사 결과"], criteria="초안"
)
TEXT = "지은 문장"


def _held() -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        infeasibility=Infeasibility.B,
        risk=RiskAssessment(floor=Risk.R1, final=Risk.R1),
        substantiation=_SUBST,
    )


def _viol() -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.confirmed,
        violations=[Violation.거짓_과장],
        infeasibility=Infeasibility.B,
        evidence=[_EV],
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
    )


def _clean() -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
    )


def _runner(calls: list[ProductContext], *, sticky: bool = False):  # noqa: ANN202
    """실증 질문 하나 · 「아니오」 → 위반 확정 · 「예」 → R0. `sticky` 면 답해도 새 질문이 계속 선다(문장 글자가 바뀐 것처럼)."""

    def run(text: str, p: ProductContext) -> dict:
        calls.append(p)
        if not p.substs:
            return {"sentences": [_held()], "outcome": None}
        if sticky:
            j = _held().model_copy(update={"text": f"{TEXT}{len(p.substs)}"})
            return {"sentences": [j], "outcome": None}
        return {
            "sentences": [_viol() if p.substs[-1].answer is Answer.아니오 else _clean()],
            "outcome": None,
        }

    return run


def test_답_경로는_질문이_선_행만_두_벌로_다시_판정한다() -> None:
    calls: list[ProductContext] = []
    rows = [{"id": "a", "text": TEXT, "조건": "B", "labels": ["거짓_과장"]}]
    (p,) = eg.run(rows, _runner(calls), 0, answers=True)
    ap_ = p["answer_path"]
    assert ap_["아니오"]["class"] == "확정위반" and ap_["아니오"]["types"] == ["거짓_과장"]
    assert ap_["예"]["class"] == "확정무위반"
    assert ap_["예"]["rounds"] == 1 and ap_["예"]["left"] == 0
    assert len(calls) == 3  # 첫 판정 + 두 벌


def test_질문이_없으면_답_경로를_돌지_않는다() -> None:
    calls: list[ProductContext] = []
    rows = [{"id": "a", "text": TEXT, "조건": "D", "labels": []}]
    (p,) = eg.run(
        rows,
        lambda t, x: calls.append(x) or {"sentences": [_clean()], "outcome": None},
        0,
        answers=True,
    )
    assert "answer_path" not in p and len(calls) == 1


def test_이어_묻기는_상한까지_남은_질문은_따로() -> None:
    calls: list[ProductContext] = []
    rows = [{"id": "a", "text": TEXT, "조건": "B", "labels": ["거짓_과장"]}]
    (p,) = eg.run(rows, _runner(calls, sticky=True), 0, answers=True)
    assert p["answer_path"]["아니오"]["rounds"] == eg.ANSWER_ROUNDS
    assert p["answer_path"]["아니오"]["left"] == 1
    rep = eg.answer_report(rows, [p])
    assert (
        rep["left"] == 1 and rep["by_condition"]["B"].get("도달", 0) == 0
    )  # 남은 행은 도달로 세지 않는다


def test_답한_질문이_다시_서면_따로_세고_도달로_세지_않는다() -> None:
    """🆕 2026-10-21 (인계 10-21 클론A §2) — 종전에는 `asked` 로 걸러 다시 답하지도 · `left` 에 세지도 않아 조용히 묻혔다(D-220)."""
    calls: list[ProductContext] = []

    def run(text: str, p: ProductContext) -> dict:
        calls.append(p)  # 답해도 같은 질문(같은 문장 · 같은 종류)이 다시 선다 — 그래프 결함 대역
        if p.substs and p.substs[-1].answer is Answer.아니오:
            return {
                "sentences": [_viol(), _held().model_copy(update={"sent_id": "s1"})],
                "outcome": None,
            }
        return {"sentences": [_held()], "outcome": None}

    rows = [{"id": "a", "text": TEXT, "조건": "B", "labels": ["거짓_과장"]}]
    (p,) = eg.run(rows, run, 0, answers=True)
    no = p["answer_path"]["아니오"]
    assert no["reasked"] == 1 and no["left"] == 0, "다시 선 질문은 `left` 가 아니라 따로"
    assert p["answer_path"]["예"]["reasked"] == 1
    rep = eg.answer_report(rows, [p])
    assert rep["reasked"] == 1
    assert rep["by_condition"]["B"].get("도달", 0) == 0, "골든 유형이 확정돼도 도달로 세지 않는다"
    assert rep["by_condition"]["B"]["재질문"] == 1


def test_종전_결과_파일은_재질문_칸이_없어도_읽는다() -> None:
    rows = [{"id": "b", "text": TEXT, "조건": "B", "labels": ["거짓_과장"]}]
    path = {"class": "확정위반", "types": ["거짓_과장"], "left": 0}
    rep = eg.answer_report(rows, [{"answer_path": {"예": dict(path), "아니오": dict(path)}}])
    assert rep["reasked"] == 0 and rep["by_condition"]["B"]["도달"] == 1


def test_실증_질문의_열쇠에_유형이_실린다() -> None:
    typed = _held().model_copy(
        update={"substantiation": _SUBST.model_copy(update={"violation": Violation.비방광고})}
    )
    assert eg._questions([typed]) == ["s0:subst:비방광고"]
    assert eg._questions([_held()]) == ["s0:subst"], "유형이 빈 질문은 종전 꼴"


def test_채점표_도달과_답에_달린_오탐() -> None:
    rows = [
        {"id": "b", "text": TEXT, "조건": "B", "labels": ["거짓_과장"]},
        {"id": "d", "text": TEXT, "조건": "D", "labels": []},
    ]
    preds = eg.run(rows, _runner([]), 0, answers=True)
    rep = eg.answer_report(rows, preds)
    assert rep["rows"] == 2
    assert (
        rep["by_condition"]["B"]["도달"] == 1 and rep["by_condition"]["B"].get("답미반영", 0) == 0
    )
    assert (
        rep["by_condition"]["D"]["아니오에위반"] == 1 and rep["by_condition"]["D"]["예에위반"] == 0
    )
    s = eg.summarize(rows, preds)
    assert s["answers"]["rows"] == 2


def test_불변식_로그가_행에_실린다() -> None:
    def run(text: str, p: ProductContext) -> dict:
        logging.getLogger(g.INVARIANT_LOG).warning("불변식 ① — 대역")
        return {"sentences": [_clean()], "outcome": None}

    rows = [{"id": "a", "text": TEXT, "조건": "D", "labels": []}]
    (p,) = eg.run(rows, run, 0)
    assert p["invariant"] == ["불변식 ① — 대역"]
    assert eg.summarize(rows, [p])["invariant_rows"] == 1
    (q,) = eg.run(rows, lambda t, x: {"sentences": [_clean()], "outcome": None}, 0)
    assert q["invariant"] == []  # 앞 행의 로그가 다음 행에 남지 않는다


def test_품목만_넘기기와_행의_제품_정보() -> None:
    r = {"id": "a", "text": TEXT, "품목": "건기식", "전제": "건기식_인정"}
    assert eg.product_of(r, True).premise is Premise.건기식_인정
    only = eg.product_of(r, True, category_only=True)
    assert only.category is Category.건기식 and only.premise is None
    (p,) = eg.run(
        [r],
        lambda t, x: {"sentences": [_clean()], "outcome": None},
        0,
        conditional=True,
        category_only=True,
    )
    assert p["product"] == {"category": "건기식", "premise": None}


def test_category_only_는_조건부_dev_전용() -> None:
    with pytest.raises(SystemExit, match="category-only"):
        eg.main(["--dev", "--category-only", "--stub"])


def test_보류_종류가_행과_요약에_실린다() -> None:
    """🆕 2026-10-21 (D-348 보충 36 결정 4) — 행의 `hold_kinds` · 요약의 종류 × 조건 표."""
    rows = [
        {"id": "a", "text": TEXT, "조건": "B", "labels": ["거짓_과장"]},
        {"id": "b", "text": TEXT, "조건": "D", "labels": []},
    ]
    nothing = SentenceJudgment(
        sent_id="s0", text=TEXT, verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    out = iter([_held(), nothing])
    preds = eg.run(rows, lambda t, x: {"sentences": [next(out)], "outcome": None}, 0)
    assert preds[0]["hold_kinds"] == ["awaiting_answer"] and preds[1]["hold_kinds"] == [
        "nothing_found"
    ]
    s = eg.summarize(rows, preds)
    assert s["hold_kinds"] == {"awaiting_answer": {"B": 1}, "nothing_found": {"D": 1}}


def test_대표_지표는_고른_뒤_답_뒤를_잰다() -> None:
    """🆕 2026-10-21 (D-348 보충 37 결정 8 · (다)) — 보수 기록은 진단 칸 · 대표는 조건부 · 답 경로 · 경로 동치 · 불변식."""
    text = " ".join(eg.REPRESENTATIVE)
    for word in ("조건부", "답 경로", "경로 동치", "불변식"):
        assert word in text
    assert "보수 기록" not in text
