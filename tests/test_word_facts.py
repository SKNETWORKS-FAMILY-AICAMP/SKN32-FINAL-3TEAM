"""낱말 사실 확인 — 특허 · 인증 (🆕 2026-10-19 · D-348 보충 28 결정 4).

지키는 것
  ① 표는 「불충분」 기준을 넘은 두 종류만 연다 · 문안은 정본 §20 과 글자가 같다
  ② 인코더 쪽 거짓 · 과장 문장에 그 사실을 묻는다 · 사실만 주장한 문장은 「예」로 닫히고(R0) · 성능 꼴이 있으면 실증이 이어진다
  ③ 열지 않은 종류(수상 등)에는 묻지 않는다 · 🔄 2026-10-21 (D-348 보충 39 결정 5) 다른 유형이 함께 선 문장에는 **거짓 · 과장의 질문으로** 묻고
     「예」여도 남은 유형이 풀리지 않으면 R0 이 아니다(종전 「묻지 않는다」 — 「예」가 다른 유형까지 풀지 않게 막던 자리를 합치기 규칙이 맡는다)
"""

from __future__ import annotations

import pathlib

import pytest

from app import factcheck as fc
from app import graph as g
from app.contracts import (
    Answer,
    EncoderBasis,
    EvidenceArticle,
    FactKind,
    HoldReason,
    Premise,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    UserFact,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

FOOD4 = EvidenceArticle(law_id="013094", article="제8조제1항제4호")
FOOD5 = EvidenceArticle(law_id="013094", article="제8조제1항제5호")


def _enc(text: str, extra: list[EncoderBasis] | None = None) -> SentenceJudgment:
    basis = [
        EncoderBasis(
            premise=Premise.식품, violation=Violation.거짓_과장, floor=Risk.R1, articles=[FOOD4]
        )
    ] + (extra or [])
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=Risk.R1, encoder_basis=basis, final=Risk.R1),
    )


def _run(s: SentenceJudgment, facts: list[UserFact] | None = None) -> SentenceJudgment | None:
    out = g.doc_rules({"sentences": [s], "product": ProductContext(facts=facts or [])})
    got = out.get("sentences") or []
    return got[0] if got else None


def test_두_종류만_열고_문안은_정본_20절과_같다() -> None:
    assert set(fc.FACT_RULES) == {FactKind.특허, FactKind.인증}
    doc = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md").read_text(encoding="utf-8")
    sec = doc[doc.index("## 20.") :]
    for k in (FactKind.특허, FactKind.인증):
        t = fc.FACT_TEXTS[k]
        assert t.criteria in sec and " · ".join(t.accepted_evidence) in sec, k
    assert fc.PERFORMANCE is not None and fc.PERFORMANCE.pattern in sec
    for k in (FactKind.특허, FactKind.인증):
        q = fc.fact_question(k)
        assert q != fc.FALLBACK_QUESTION and f"질문: {q}" in sec, k
        assert q.count("?") == 1, "질문 하나 · 설명은 기준 칸(보충 9 결정 1)"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("HACCP 인증을 받은 공장에서 만든 그래놀라", FactKind.인증),
        ("특허받은 제조 공법", FactKind.특허),
    ],
)
def test_거짓_과장_문장에_그_사실을_묻는다(text: str, kind: FactKind) -> None:
    got = _run(_enc(text))
    assert got is not None and got.fact_check is not None and got.fact_check.kind is kind
    assert got.verdict is Verdict.hold, "답 없이 확정하지 않는다"


def test_사실만_주장한_문장은_예로_닫힌다() -> None:
    t = "HACCP 인증을 받은 공장에서 만든 그래놀라"
    got = _run(_enc(t), [UserFact(text=t, kind=FactKind.인증, answer=Answer.예)])
    assert got is not None and got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0


def test_성능_꼴이_있으면_실증이_이어진다() -> None:
    t = "특허받은 원료로 피로 회복 효과가 탁월합니다"
    got = _run(_enc(t), [UserFact(text=t, kind=FactKind.특허, answer=Answer.예)])
    assert got is not None and got.verdict is Verdict.hold and got.substantiation is not None


def test_섞인_문장과_열지_않은_종류() -> None:
    mixed = _enc(
        "HACCP 인증 제품",
        [
            EncoderBasis(
                premise=Premise.식품,
                violation=Violation.소비자_기만,
                floor=Risk.R1,
                articles=[FOOD5],
            )
        ],
    )
    got = _run(mixed)
    assert (
        got is not None and got.fact_check is not None and got.fact_check.kind is FactKind.인증
    ), "섞인 문장도 거짓 · 과장의 사실을 묻는다(보충 39 결정 5)"
    yes = _run(mixed, [UserFact(text="HACCP 인증 제품", kind=FactKind.인증, answer=Answer.예)])
    assert yes is not None and yes.verdict is Verdict.hold, (
        "식품 축 기만은 물을 질문이 없어 남는다 — R0 이 아니다(D-340 결정 6)"
    )
    award = _run(_enc("대한민국 브랜드 대상 수상"))
    assert award is None or award.fact_check is None, "열지 않은 종류(수상)"
