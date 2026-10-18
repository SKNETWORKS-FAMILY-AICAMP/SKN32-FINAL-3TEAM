"""식품 두 전제의 인코더 쪽 판정 (🆕 2026-10-19 · D-348 보충 28 결정 3).

지키는 것
  ① `식품` — 인코더가 건강기능식품 오인 후보를 내고 그 근거만 선 문장은 3호 확정 위반(사유 A · 답 없이)
  ② `일반식품_기능성` — 전제가 지운 자리에서 `기능성_표시` 를 묻는다 · 예 R0 · 아니오 3호 확정(A) · 해당 없음 보류 + 출처
  ③ 손대지 않는다 — 후보 없음 · 다른 근거가 섞임 · 질병 · 의약품 후보 · 치료 꼴 · 건기식 · 화장품 전제
  ④ 문안은 정본 §19 와 글자가 같다
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from app import factcheck as fc
from app import graph as g
from app.contracts import (
    Answer,
    EncoderBasis,
    EvidenceArticle,
    FactKind,
    HoldReason,
    Infeasibility,
    Premise,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Span,
    UserFact,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

TEXT = "피로 회복에 도움을 줍니다"
SPAN = Span(start=0, end=len(TEXT), label=Violation.건강기능식품_오인.value)
HF = g.SentEncoding(
    sent_id="s0", scores=(("건강기능식품_오인", 0.8),), candidates=("건강기능식품_오인",)
)
NONE = g.SentEncoding(sent_id="s0", scores=(("건강기능식품_오인", 0.2),), candidates=())
FOOD3 = EvidenceArticle(law_id="013094", article="제8조제1항제3호")
FOOD5 = EvidenceArticle(law_id="013094", article="제8조제1항제5호")


@pytest.fixture(autouse=True)
def _floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(g, "estimate_of", lambda rows, premise, v: SimpleNamespace(floor=Risk.R1))


def _held(basis: list[EncoderBasis] | None = None, text: str = TEXT) -> SentenceJudgment:
    b = basis or []
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=Risk.R1, final=Risk.R1, encoder_basis=b)
        if b
        else RiskAssessment(),
    )


def _hf(premise: Premise = Premise.식품) -> list[EncoderBasis]:
    return [
        EncoderBasis(
            premise=premise, violation=Violation.건강기능식품_오인, floor=Risk.R1, articles=[FOOD3]
        )
    ]


def test_식품은_3호_확정_위반_사유_A() -> None:
    got = g._food_premise(Premise.식품, _held(_hf()), HF, [], SPAN, [])
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.건강기능식품_오인]
    assert got.infeasibility is Infeasibility.A and got.evidence


def test_식품에_다른_근거가_섞이면_그대로() -> None:
    mixed = _hf() + [
        EncoderBasis(
            premise=Premise.식품, violation=Violation.소비자_기만, floor=Risk.R1, articles=[FOOD5]
        )
    ]
    j = _held(mixed)
    assert g._food_premise(Premise.식품, j, HF, [], SPAN, []) is j


def test_일반식품_기능성은_묻는다() -> None:
    got = g._food_premise(Premise.일반식품_기능성, _held(), HF, [], SPAN, [])
    assert got.verdict is Verdict.hold and got.fact_check is not None
    assert got.fact_check.kind is FactKind.기능성_표시 and got.fact_check.confirmed_max is Risk.R0
    assert got.fact_check.criteria == fc.FOOD_FUNC_TEXT.criteria
    (b,) = got.risk.encoder_basis
    assert b.violation is Violation.건강기능식품_오인 and b.premise is Premise.일반식품_기능성


@pytest.mark.parametrize(
    ("answer", "verdict", "violations"),
    [
        (Answer.예, Verdict.confirmed, []),
        (Answer.아니오, Verdict.confirmed, [Violation.건강기능식품_오인]),
        (Answer.해당없음, Verdict.hold, []),
    ],
)
def test_답(answer: Answer, verdict: Verdict, violations: list[Violation]) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.기능성_표시, answer=answer)
    got = g._food_premise(Premise.일반식품_기능성, _held(), HF, [uf], SPAN, [])
    assert got.verdict is verdict
    if verdict is Verdict.confirmed:
        assert list(got.violations) == violations
    assert got.user_facts == [uf] and got.fact_check is None
    if answer is Answer.예:
        assert got.risk.final is Risk.R0
    if answer is Answer.아니오:
        assert got.infeasibility is Infeasibility.A


def test_손대지_않는_문장() -> None:
    j = _held()
    assert g._food_premise(Premise.일반식품_기능성, j, NONE, [], SPAN, []) is j, "후보 없음"
    assert g._food_premise(Premise.일반식품_기능성, j, HF, [], None, []) is j, "구간 모름"
    t = _held(text="관절염을 치료해 줍니다")
    assert g._food_premise(Premise.일반식품_기능성, t, HF, [], SPAN, []) is t, "치료 꼴"
    d = _held().model_copy(update={"violations": [Violation.질병_예방치료_표방]})
    assert g._food_premise(Premise.일반식품_기능성, d, HF, [], SPAN, []) is d, "질병 후보"
    for p in (Premise.건기식_인정, Premise.화장품):
        assert g._food_premise(p, j, HF, [], SPAN, []) is j, p


def test_문안은_정본_19절과_같다() -> None:
    doc = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md").read_text(encoding="utf-8")
    sec = doc[doc.index("## 19.") : doc.index("## 20.")]
    assert f"질문: {fc.FOOD_FUNC_QUESTION}" in sec
    assert f"기준: {fc.FOOD_FUNC_TEXT.criteria}" in sec
    assert f"증빙: {fc.FOOD_FUNC_TEXT.accepted_evidence[0]}" in sec
    assert fc.fact_question(FactKind.기능성_표시) == fc.FOOD_FUNC_QUESTION
    assert FactKind.기능성_표시 not in fc.FACT_TEXTS
