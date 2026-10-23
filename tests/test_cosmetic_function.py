"""화장품 전제의 기능성화장품 오인 질문 (🆕 2026-10-19 · D-348 보충 6 결정 9 · 보충 27).

지키는 것
  ① C 가 서지 않았고 기능성화장품 오인 근거가 남은 문장에 묻는다(`기능성_심사`) · 문안은 정본 §17 과 글자가 같다
  ② 답 — 예 R0 · 아니오 13①2 확정(사유 A) · 해당 없음 보류 + 출처
  ③ 묻지 않는다 — 다른 유형의 근거가 남음(기능성 정형 낱말 · 인증 꼴로 내려온 의약품 오인은 예외) · 치료 꼴 · 화장품 전제가 아님 · 옮긴 근거
  ④ 인코더 쪽 판정에서 — 기능성 정형 문장은 의약품 오인 C 대신 이 질문으로 간다(보충 26 결정 1 의 A 몫)
"""

from __future__ import annotations

import pathlib

import pytest

from app import factcheck as fc
from app import graph as g
from app.contracts import (
    Answer,
    EncoderBasis,
    EncoderTypeCandidate,
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

COS1 = EvidenceArticle(law_id="002015", article="제13조제1항제1호")
COS2 = EvidenceArticle(law_id="002015", article="제13조제1항제2호")
COS4 = EvidenceArticle(law_id="002015", article="제13조제1항제4호")
F = Violation.기능성화장품_오인
D = Violation.의약품_오인


def _b(v: Violation, art: EvidenceArticle, premise: Premise = Premise.화장품) -> EncoderBasis:
    return EncoderBasis(premise=premise, violation=v, floor=Risk.R2, articles=[art])


def _held(text: str, basis: list[EncoderBasis]) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=[
            EncoderTypeCandidate(violation=b.violation, confidence=0.9) for b in basis
        ],
        risk=RiskAssessment(encoder=Risk.R1, final=Risk.R1, encoder_basis=basis),
    )


def _span(t: str) -> Span:
    return Span(start=0, end=len(t), label="")


TEXT = "피부 미백에 도움을 주는 세럼"


def test_기능성_근거만_남으면_묻는다() -> None:
    got = g._cosmetic_function(_held(TEXT, [_b(F, COS2)]), [], _span(TEXT))
    assert got is not None and got.verdict is Verdict.hold and got.fact_check is not None
    assert got.fact_check.kind is FactKind.기능성_심사 and got.fact_check.confirmed_max is Risk.R0
    assert got.fact_check.criteria == fc.COSMETIC_FUNC_TEXT.criteria
    assert {b.violation for b in got.risk.encoder_basis} == {F}


@pytest.mark.parametrize(
    ("answer", "verdict", "violations"),
    [
        (Answer.예, Verdict.confirmed, []),
        (Answer.아니오, Verdict.confirmed, [F]),
        (Answer.해당없음, Verdict.hold, []),
    ],
)
def test_답(answer: Answer, verdict: Verdict, violations: list[Violation]) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.기능성_심사, answer=answer)
    got = g._cosmetic_function(_held(TEXT, [_b(F, COS2)]), [uf], _span(TEXT))
    assert got is not None and got.verdict is verdict
    if verdict is Verdict.confirmed:
        assert list(got.violations) == violations
    assert got.user_facts == [uf] and got.fact_check is None
    if answer is Answer.예:
        assert got.risk.final is Risk.R0
    if answer is Answer.아니오:
        assert got.infeasibility is Infeasibility.A and got.evidence


def test_정형_낱말로_내려온_의약품_오인은_같은_문장의_A_몫이다() -> None:
    got = g._cosmetic_function(_held(TEXT, [_b(F, COS2), _b(D, COS1)]), [], _span(TEXT))
    assert got is not None and got.fact_check is not None
    uf = UserFact(text=TEXT, kind=FactKind.기능성_심사, answer=Answer.아니오)
    no = g._cosmetic_function(_held(TEXT, [_b(F, COS2), _b(D, COS1)]), [uf], _span(TEXT))
    assert no is not None and no.verdict is Verdict.confirmed and no.violations == [F]


@pytest.mark.parametrize(
    ("text", "basis", "why"),
    [
        ("피부 진정 효과", [_b(F, COS2), _b(D, COS1)], "정형 낱말 없이 의약품 오인이 남았다"),
        (TEXT, [_b(F, COS2), _b(Violation.거짓_과장, COS4)], "다른 유형이 남았다"),
        ("미백 치료 세럼", [_b(F, COS2)], "치료 꼴"),
        (TEXT, [_b(F, COS2, Premise.식품)], "화장품 전제가 아니다"),
        (TEXT, [_b(D, COS1)], "기능성 근거가 없다"),
    ],
)
def test_묻지_않는다(text: str, basis: list[EncoderBasis], why: str) -> None:
    assert g._cosmetic_function(_held(text, basis), [], _span(text)) is None, why


def test_인코더_쪽_판정에서_기능성_정형_문장은_C_대신_질문으로() -> None:
    got = g._encoder_side(_held(TEXT, [_b(F, COS2), _b(D, COS1)]), [], [], _span(TEXT))
    assert got is not None and got.verdict is Verdict.hold
    assert got.fact_check is not None and got.fact_check.kind is FactKind.기능성_심사
    #: 🔄 2026-10-24 (D-348 보충 41 결정 2 ②) — 답 없는 확정은 지금 주장 가드를 지나는 문장만 · 명사구(「… 치료 크림」)는 관문에서 막힌다
    drug = "아토피 피부염을 치료하는 크림입니다"
    c = g._encoder_side(_held(drug, [_b(D, COS1)]), [], [], _span(drug))
    assert c is not None and c.verdict is Verdict.confirmed, "기준 — 의약품 오인 문장은 C 확정"


def test_문안은_정본과_같다() -> None:
    doc = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md").read_text(encoding="utf-8")
    sec = doc[doc.index("## 17.") :]
    assert f"질문: {fc.COSMETIC_FUNC_QUESTION}" in sec
    assert f"기준: {fc.COSMETIC_FUNC_TEXT.criteria}" in sec
    assert f"증빙: {fc.COSMETIC_FUNC_TEXT.accepted_evidence[0]}" in sec
    assert fc.fact_question(FactKind.기능성_심사) == fc.COSMETIC_FUNC_QUESTION
    assert FactKind.기능성_심사 not in fc.FACT_TEXTS, (
        "유형에 딸린 사실 표가 이 종류를 집어 가지 않는다"
    )
