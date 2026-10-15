"""사실 확인 분기 뼈대 — 사실에 달린 문장은 보류 + 분기 · 사용자 확인은 출처를 남기고 반영 (🆕 2026-10-16 · D-348 보충 3).

지키는 것
  ① 표(`app/factcheck.py`)가 비면 아무것도 하지 않는다 — 문안 승인 전 판정이 한 글자도 안 바뀐다 (결정 6)
  ② 호 관문 — 사실에 달린 목을 품은 호에 걸린 문장만 · 사전 인용이든 인코더 근거 호든 같다 (결정 2)
  ③ 사용자 확인 없음 → 보류(premise_unknown) + 분기 · 위험도는 가장 나쁜 경우 그대로 · 응답 계약을 지난다 (결정 1)
  ④ 사용자 「참」 ∧ 사실 주장 꼴만 → 확정 · R0 · 출처(`user_fact`) · 「거짓」 ∧ 확정 → 그대로 + 출처 (결정 3 · 4)
  ⑤ 저장은 출처를 남긴다 (결정 4)
"""

from __future__ import annotations

import re
import uuid

import pytest

from app import factcheck as fc
from app import graph as g
from app.contracts import (
    EvidenceArticle,
    FactKind,
    HoldReason,
    Infeasibility,
    JudgeResponse,
    Outcome,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    UserFact,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

TEXT = "HACCP 인증을 받은 공장에서 만든 그래놀라"
FOOD4 = EvidenceArticle(law_id="013094", article="제8조", item="제1항제4호", basis=True)
FOOD1 = EvidenceArticle(law_id="013094", article="제8조", item="제1항제1호", basis=True)


def _confirmed(
    text: str = TEXT, ev: EvidenceArticle = FOOD4, v: Violation = Violation.거짓_과장
) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.confirmed,
        violations=[v],
        infeasibility=Infeasibility.B,
        evidence=[ev],
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
    )


@pytest.fixture
def tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 시험용 꼴 · 문안이다 — 실제 표는 승인된 줄만 든다(결정 6)."""
    monkeypatch.setattr(fc, "FACT_RULES", {FactKind.인증: re.compile("인증")})
    monkeypatch.setattr(
        fc, "FACT_TEXTS", {FactKind.인증: fc.FactText(["(시험) 인증서"], "(시험) 기준")}
    )
    monkeypatch.setattr(fc, "PERFORMANCE", re.compile("효과|개선|완화"))


def _run(s: SentenceJudgment, facts: list[UserFact] | None = None) -> SentenceJudgment | None:
    out = g.doc_rules({"sentences": [s], "product": ProductContext(facts=facts or [])})
    got = out.get("sentences") or []
    return got[0] if got else None


def test_표가_비면_아무것도_하지_않는다() -> None:
    assert fc.FACT_RULES == {} and fc.FACT_TEXTS == {} and fc.PERFORMANCE is None, (
        "🔴 승인 전 표가 채워졌다 — 문안 승인(D-263 ②) 뒤 이 게이트를 고친다"
    )
    assert _run(_confirmed()) is None


def test_사실에_달린_문장은_보류와_분기다(tables: None) -> None:
    got = _run(_confirmed())
    assert got is not None and (got.verdict, got.hold_reason) == (
        Verdict.hold,
        HoldReason.premise_unknown,
    )
    assert got.risk.final is Risk.R2, "기록 위험도는 가장 나쁜 경우(사실 거짓) 그대로 (D-263 ①)"
    assert got.fact_check.kind is FactKind.인증 and got.fact_check.confirmed_max is Risk.R0
    assert got.violations == [Violation.거짓_과장], "보류에도 유형 · 근거는 실린다"
    JudgeResponse(outcome=Outcome.hold, sentences=[got])  # 품목 분기 없이도 계약을 지난다


def test_호_관문_밖이면_낱말이_있어도_분기를_달지_않는다(tables: None) -> None:
    disease = _confirmed("인증받은 원료로 당뇨를 치료", FOOD1, Violation.질병_예방치료_표방)
    assert _run(disease) is None, "질병 표방(1호)에는 사실에 달린 목이 없다"


def test_인코더만_잡은_보류도_근거_호로_관문을_지난다(tables: None) -> None:
    from app.contracts import EncoderBasis, Premise  # noqa: PLC0415

    ref = EvidenceArticle(
        law_id="013094", article="제8조제1항제4호"
    )  # 참조 조항 꼴(`_ref_article`)
    basis = [
        EncoderBasis(
            premise=Premise.식품, violation=Violation.거짓_과장, floor=Risk.R1, articles=[ref]
        )
    ]
    s = SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=Risk.R1, encoder_basis=basis, final=Risk.R1),
    )
    got = _run(s)
    assert got is not None and got.hold_reason is HoldReason.premise_unknown and got.fact_check


def test_사용자가_참으로_고르면_확정_R0_과_출처(tables: None) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인증, true=True)
    got = _run(_confirmed(), [uf])
    assert got is not None and got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0 and got.user_fact == uf


def test_성능_주장이_섞이면_참이어도_풀지_않는다(tables: None) -> None:
    text = "HACCP 인증으로 피로 개선 효과"
    uf = UserFact(text=text, kind=FactKind.인증, true=True)
    got = _run(_confirmed(text), [uf])
    assert got is not None and got.violations and got.user_fact == uf, (
        "남는 위험은 실증 분기의 몫(결정 3)"
    )


def test_사용자가_거짓으로_고르면_확정_그대로_출처(tables: None) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인증, true=False)
    got = _run(_confirmed(), [uf])
    assert (
        got is not None
        and got.verdict is Verdict.confirmed
        and got.violations
        and got.user_fact == uf
    )


def test_계약_사용자_확인은_확정에만() -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인증, true=True)
    with pytest.raises(ValueError, match="사용자 확인"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.low_conf,
            user_fact=uf,
        )


def test_저장은_사용자_확인_출처를_남긴다(tables: None) -> None:
    from app import judgment_store as js  # noqa: PLC0415

    uf = UserFact(text=TEXT, kind=FactKind.인증, true=True)
    got = _run(_confirmed(), [uf])
    row = js._judgment_row(
        uuid.uuid4(), uuid.uuid4(), got, JudgeResponse(outcome=Outcome.passed, sentences=[got])
    )
    assert row.evidence["user_fact"]["kind"] == "인증" and row.evidence["user_fact"]["true"] is True


def test_제재표의_사실_칸_유형은_호_관문_안이다() -> None:
    """제재표 원천(`scripts/sanction_review.yaml`)의 사실 칸 행은 식품 4호 · 7호 유형이다 — 관문이 그 호를 품는다 (D-99)."""
    from collect import statute  # noqa: PLC0415
    from scripts import sanction_rule as sr  # noqa: PLC0415

    spec = sr.load_rules()
    rows = [r for r in sr.rule_rows(spec) if r.get("fact")]
    assert rows, "제재표에 사실 칸 행이 없다 — 관문의 근거가 사라졌다"
    gate_types = {
        t
        for law, jo, hang, ho in fc.FACT_HO
        for t in statute.types_of([statute.cite(law, jo, hang, ho)])
    }
    assert {r["type"] for r in rows} <= gate_types
