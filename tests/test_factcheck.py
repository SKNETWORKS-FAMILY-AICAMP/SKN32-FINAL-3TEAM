"""조건부 위반 — 근거 호가 전부 조건부 호인 문장은 보류 + 선택지(사실 · 실증) · 사용자의 답은 그 문장에 출처를 남기고 반영
(🆕 2026-10-16 · D-348 보충 3 · 🔄 보충 4).

지키는 것
  ① 호 관문 — 근거 호가 **전부** 조건부 호일 때만 · 무조건 호(질병 표방 등)가 섞이면 확정 그대로 · 사전 인용이든 인코더 근거 호든 같다 (보충 4 결정 1)
  ② 사실 표지가 없으면(또는 그 종류의 문안이 승인 전이면) 실증 분기 — 보류(premise_unknown) + 실증 분기 · 위험도는 가장 나쁜 경우 그대로 (결정 1)
  ③ 사실 확인 문안 표가 비면 사실 확인 분기는 서지 않는다 — 승인 전 사실 문안을 지어내지 않는다 (보충 3 결정 6)
  ④ 답 — 사실 「참」 ∧ 꼴만 / 실증 「있음」 → 확정 · R0 · 출처 · 「거짓」 / 「없음」 ∧ 확정 → 그대로 + 출처 · 답은 그 문장에만 (결정 3 · 4)
  ⑤ 조건부 위반은 보류와 다른 분류다 — 지시 종착을 막지 않는다 · 증명서 · 통과로는 가지 않는다 (결정 2)
  ⑥ 저장은 출처를 남긴다
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
    Span,
    UserFact,
    UserSubst,
    Verdict,
    Violation,
    is_conditional,
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


def _enc_only() -> SentenceJudgment:
    from app.contracts import EncoderBasis, Premise  # noqa: PLC0415

    ref = EvidenceArticle(
        law_id="013094", article="제8조제1항제4호"
    )  # 참조 조항 꼴(`_ref_article`)
    basis = [
        EncoderBasis(
            premise=Premise.식품, violation=Violation.거짓_과장, floor=Risk.R1, articles=[ref]
        )
    ]
    return SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=Risk.R1, encoder_basis=basis, final=Risk.R1),
    )


@pytest.fixture
def tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 시험용 꼴 · 문안이다 — 실제 표는 승인된 줄만 든다(결정 6)."""
    monkeypatch.setattr(fc, "FACT_RULES", {FactKind.인증: re.compile("인증")})
    monkeypatch.setattr(
        fc, "FACT_TEXTS", {FactKind.인증: fc.FactText(["(시험) 인증서"], "(시험) 기준")}
    )
    monkeypatch.setattr(fc, "PERFORMANCE", re.compile("효과|개선|완화"))


def _run(
    s: SentenceJudgment,
    facts: list[UserFact] | None = None,
    substs: list[UserSubst] | None = None,
) -> SentenceJudgment | None:
    out = g.doc_rules(
        {"sentences": [s], "product": ProductContext(facts=facts or [], substs=substs or [])}
    )
    got = out.get("sentences") or []
    return got[0] if got else None


def test_사실_확인_표가_비면_사실_분기는_서지_않고_실증_분기다() -> None:
    assert fc.FACT_RULES == {} and fc.FACT_TEXTS == {} and fc.PERFORMANCE is None, (
        "🔴 승인 전 표가 채워졌다 — 문안 승인(D-263 ②) 뒤 이 게이트를 고친다"
    )
    got = _run(_confirmed())
    assert got is not None and got.fact_check is None
    assert (got.verdict, got.hold_reason, got.infeasibility) == (
        Verdict.hold,
        HoldReason.premise_unknown,
        Infeasibility.B,
    )
    assert got.substantiation is not None and got.substantiation.substantiated_max is Risk.R0
    assert got.risk.final is Risk.R2, "기록 위험도는 가장 나쁜 경우(실증 못 함) 그대로 (D-263 ①)"
    assert got.violations == [Violation.거짓_과장] and got.evidence, "보류에도 유형 · 근거는 실린다"
    assert is_conditional(got)
    JudgeResponse(outcome=Outcome.hold, sentences=[got])  # 품목 분기 없이도 계약을 지난다


def test_무조건_호가_섞이면_확정_그대로() -> None:
    mixed = SentenceJudgment(
        **{
            **_confirmed().model_dump(),
            "violations": [Violation.거짓_과장, Violation.질병_예방치료_표방],
            "infeasibility": Infeasibility.C,
            "evidence": [FOOD4, FOOD1],
        }
    )
    assert _run(mixed) is None, "답해도 질병 표방은 남는다 — 조건부가 아니다 (보충 4 결정 1)"
    assert _run(_confirmed("당뇨 치료", FOOD1, Violation.질병_예방치료_표방)) is None


def test_실증_문안이_없는_유형은_조건부로_내리지_않는다() -> None:
    food7 = EvidenceArticle(law_id="013094", article="제8조", item="제1항제7호", basis=True)
    assert _run(_confirmed("다른 회사 원료보다 낫다", food7, Violation.부당_비교광고)) is None


def test_인코더만_잡은_보류도_근거_호로_조건부가_된다() -> None:
    got = _run(_enc_only())
    assert got is not None and is_conditional(got) and got.substantiation is not None
    assert got.infeasibility is Infeasibility.B and got.risk.final is Risk.R1
    JudgeResponse(outcome=Outcome.hold, sentences=[got])


def test_실증_있음이면_확정_R0_과_출처() -> None:
    us = UserSubst(text=TEXT, has_evidence=True)
    got = _run(_confirmed(), substs=[us])
    assert got is not None and got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0 and got.user_subst == us
    JudgeResponse(outcome=Outcome.passed, sentences=[got], product=ProductContext(category=None))


def test_실증_없음이면_확정_위반_그대로_출처() -> None:
    us = UserSubst(text=TEXT, has_evidence=False)
    got = _run(_confirmed(), substs=[us])
    assert got is not None and got.verdict is Verdict.confirmed and got.violations
    assert got.user_subst == us and got.substantiation is not None and got.risk.final is Risk.R2


def test_인코더만_잡은_문장의_없음은_반영하지_않는다() -> None:
    us = UserSubst(text=TEXT, has_evidence=False)
    assert _run(_enc_only(), substs=[us]) is None, (
        "확정은 신뢰 층의 몫(보충 2 결정 5) — 보류 그대로"
    )


def test_답은_그_문장에만() -> None:
    us = UserSubst(text="다른 문장", has_evidence=True)
    got = _run(_confirmed(), substs=[us])
    assert got is not None and is_conditional(got) and got.user_subst is None


def test_종착_조건부는_지시를_막지_않고_증명서_통과로_가지_않는다() -> None:
    cond = _run(_confirmed())
    assert cond is not None
    sub = g._cond_subst(_confirmed())
    ready = SentenceJudgment(
        **{
            **_confirmed().model_dump(),
            "sent_id": "s1",
            "substantiation": sub.model_dump(),
            "spans": [Span(start=0, end=2, label="거짓_과장").model_dump()],
        }
    )
    assert g.route_review({"sentences": [ready, cond]}) == "guidance"
    low = SentenceJudgment(
        sent_id="s2", text="x", verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    assert g.route_review({"sentences": [ready, cond, low]}) == "hold"
    c = _confirmed("당뇨 치료", FOOD1, Violation.질병_예방치료_표방)
    c = SentenceJudgment(**{**c.model_dump(), "sent_id": "s3", "infeasibility": Infeasibility.C})
    assert g.route_review({"sentences": [c, cond]}) == "hold", "증명서는 전 문장 확정을 요구한다"
    assert not is_conditional(low)


def test_계약_실증_분기는_확신_부족_보류에_못_붙는다() -> None:
    sub = g._cond_subst(_confirmed())
    with pytest.raises(ValueError, match="조건부 위반"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.low_conf,
            infeasibility=Infeasibility.B,
            risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
            substantiation=sub,
        )
    with pytest.raises(ValueError, match="실증 여부"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.low_conf,
            user_subst=UserSubst(text=TEXT, has_evidence=True),
        )


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
    assert _run(disease) is None, "질병 표방(1호)은 조건부 호가 아니다"


def test_인코더만_잡은_보류도_사실_표지면_사실_분기(tables: None) -> None:
    got = _run(_enc_only())
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


def test_저장은_실증_답_출처를_남긴다() -> None:
    from app import judgment_store as js  # noqa: PLC0415

    us = UserSubst(text=TEXT, has_evidence=True)
    got = _run(_confirmed(), substs=[us])
    row = js._judgment_row(
        uuid.uuid4(), uuid.uuid4(), got, JudgeResponse(outcome=Outcome.passed, sentences=[got])
    )
    assert row.evidence["user_subst"] == {"text": TEXT, "has_evidence": True}


def test_제재표의_사실_칸_유형은_호_관문_안이다() -> None:
    """제재표 원천(`scripts/sanction_review.yaml`)의 사실 칸 행은 식품 4호 · 7호 유형이다 — 관문이 그 호를 품는다 (D-99)."""
    from collect import statute  # noqa: PLC0415
    from scripts import sanction_rule as sr  # noqa: PLC0415

    spec = sr.load_rules()
    rows = [r for r in sr.rule_rows(spec) if r.get("fact")]
    assert rows, "제재표에 사실 칸 행이 없다 — 관문의 근거가 사라졌다"
    gate_types = {
        t
        for law, jo, hang, ho in fc.COND_HO
        for t in statute.types_of([statute.cite(law, jo, hang, ho)])
    }
    assert {r["type"] for r in rows} <= gate_types


def test_화면_결론_줄은_보류가_아니라_조건부_위반이다() -> None:
    from app import reasons  # noqa: PLC0415
    from app.templating import templates  # noqa: PLC0415

    m = templates.env.get_template("user/_sent_words.html").module
    got = _run(_confirmed())
    assert str(m.sent_concl(got)).strip() == reasons.CONDITIONAL_SUBST_TEXT
    low = SentenceJudgment(
        sent_id="s2", text="x", verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    assert reasons.conditional_text(low) == "", "확신 부족 보류는 조건부 위반이 아니다"


def test_평가는_조건부_위반을_보류와_따로_센다() -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    cond = _run(_confirmed())
    p = eg.predict({"sentences": [cond]})
    assert p["class"] == "조건부위반" and p["cond_types"] == ["거짓_과장"] and p["types"] == []
    low = SentenceJudgment(
        sent_id="s2", text="x", verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    assert eg.predict({"sentences": [cond, low]})["class"] == "보류"
    row = {"text": TEXT, "labels": ["거짓_과장"], "조건": "B", "근거": []}
    rep = eg.conditional_report([row], [p])
    assert (rep["rows"], rep["positive"], rep["confirmed"], rep["conditional"], rep["either"]) == (
        1,
        1,
        0,
        1,
        1,
    )
