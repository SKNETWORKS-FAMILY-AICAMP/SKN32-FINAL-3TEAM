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
    Branch,
    EvidenceArticle,
    FactKind,
    HoldReason,
    Infeasibility,
    JudgeResponse,
    Outcome,
    Premise,
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


def test_신뢰_규칙_전에는_인코더만_잡은_보류는_조건부가_아니다() -> None:
    """D-348 결정 5 — 조건부 위반은 「답하지 않으면 확정 B」다 · 확정에는 신뢰 규칙이 필요하다(보충 1 결정 2 · 문턱 None = 닫힘)."""
    assert g.ENCODER_CONFIRM_TAU is None, (
        "🔴 문턱이 열렸다 — 관문(데이터 밖 ≤ 2%) 기록 뒤 이 게이트를 고친다"
    )
    assert _run(_enc_only()) is None
    weak = SentenceJudgment(
        **{
            **_enc_only().model_dump(),
            "violations": [Violation.거짓_과장],
            "evidence": [FOOD4.model_dump()],
        }
    )
    assert _run(weak) is None, (
        "자격 없는 사전 적중 + 인코더 하한도 확정 재료가 아니다(D-311 결정 4)"
    )


def test_신뢰_규칙이_열리면_주장_가드와_확신을_지난_것만(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.contracts import EncoderTypeCandidate  # noqa: PLC0415

    monkeypatch.setattr(g, "ENCODER_CONFIRM_TAU", 0.8)
    hi = EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.9)
    lo = EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.5)
    base = _enc_only().model_dump()
    ok = SentenceJudgment(
        **{**base, "text": "국내 판매 1위를 지켰어요", "encoder_candidates": [hi.model_dump()]}
    )
    got = _run(ok)
    assert got is not None and is_conditional(got) and got.substantiation is not None
    JudgeResponse(outcome=Outcome.hold, sentences=[got])
    low = SentenceJudgment(
        **{**base, "text": "국내 판매 1위를 지켰어요", "encoder_candidates": [lo.model_dump()]}
    )
    assert _run(low) is None, "확신이 문턱 아래"
    veto = SentenceJudgment(
        **{**base, "text": "국내 판매 1위 정가 19,900원", "encoder_candidates": [hi.model_dump()]}
    )
    assert _run(veto) is None, "거부 가드(가격)"


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


def test_종착_조건부는_답하지_않은_확정_B로_센다() -> None:
    """D-263 ① — 조건부 위반의 가장 나쁜 경우는 「자료 없음 = 확정 B」다. 섞인 문서의 종착은 그 기준이다."""
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
    assert g.route_review({"sentences": [c, cond]}) == "certificate", (
        "C 확정 + B 확정이면 증명서였다 — 조건부(답 없는 B)도 같다"
    )
    assert not is_conditional(low)


def test_자격_문제는_조건부가_아니다() -> None:
    """10-16 결함 — 식품 8조①4호 나목(인정받지 않은 기능성 · A)은 호가 같아도 실증으로 풀리지 않는다 (D-59)."""
    from app import premise as pm  # noqa: PLC0415

    na = g._basis_article(pm.UNRECOGNIZED_FUNCTION_CITE)
    a = SentenceJudgment(
        **{
            **_confirmed("관절 건강에 도움").model_dump(),
            "infeasibility": Infeasibility.A,
            "evidence": [na.model_dump()],
        }
    )
    assert _run(a) is None
    b = SentenceJudgment(
        **{**_confirmed("관절 건강에 도움").model_dump(), "evidence": [na.model_dump()]}
    )
    assert _run(b) is None, "사유가 B 로 적혀 있어도 4.나 인용이면 자격 문제다"
    moved = _enc_only()
    eb = moved.risk.encoder_basis[0].model_copy(update={"moved_from": Violation.건강기능식품_오인})
    moved = SentenceJudgment(
        **{
            **moved.model_dump(),
            "risk": moved.risk.model_copy(update={"encoder_basis": [eb]}).model_dump(),
        }
    )
    assert _run(moved) is None, "전제가 옮긴 인코더 근거(인정받지 않았다면)는 자격 문제다"


def _branch(premise: str, sents: list[SentenceJudgment]) -> Branch:
    return Branch(
        premise=Premise(premise),
        outcome=g._branch_outcome(Premise(premise), sents),
        sentences=sents,
        criteria="(시험) 기준",
    )


def _doc(rec: SentenceJudgment, per: dict[str, SentenceJudgment], **product: object) -> dict:
    out = g.doc_rules(
        {
            "sentences": [rec],
            "branches": [_branch(p, [s]) for p, s in per.items()],
            "product": ProductContext(**product),
        }
    )
    return {
        "rec": (out.get("sentences") or [rec])[0],
        "branches": out.get("branches", []),
    }


def test_분기마다_정하고_기록은_분기에서_모은다() -> None:
    got = _doc(_confirmed(), {"식품": _confirmed(), "일반상품": _confirmed()})
    assert all(is_conditional(b.sentences[0]) for b in got["branches"])
    assert is_conditional(got["rec"]) and got["rec"].risk.final is Risk.R2
    resp = JudgeResponse(outcome=Outcome.hold, sentences=[got["rec"]], branches=got["branches"])
    assert resp.branches[0].sentences[0].substantiation is not None


def test_분기마다_조건부가_갈리면_기록은_품목을_몰라_보류() -> None:
    disease = SentenceJudgment(
        **{
            **_confirmed().model_dump(),
            "violations": [Violation.거짓_과장],
            "infeasibility": Infeasibility.A,
        }
    )
    got = _doc(_confirmed(), {"식품": _confirmed(), "건기식_비인정": disease})
    rec = got["rec"]
    assert (rec.verdict, rec.hold_reason) == (Verdict.hold, HoldReason.cat_unknown)
    assert rec.substantiation is None and not is_conditional(rec)
    kinds = {b.premise.value: is_conditional(b.sentences[0]) for b in got["branches"]}
    assert kinds == {"식품": True, "건기식_비인정": False}


def test_답은_모든_분기와_기록에_같이() -> None:
    us = UserSubst(text=TEXT, has_evidence=True)
    got = _doc(_confirmed(), {"식품": _confirmed(), "일반상품": _confirmed()}, substs=[us])
    assert all(b.sentences[0].user_subst == us for b in got["branches"])
    rec = got["rec"]
    assert rec.verdict is Verdict.confirmed and rec.risk.final is Risk.R0 and rec.user_subst == us
    assert all(b.outcome is Outcome.passed or b.outcome is Outcome.hold for b in got["branches"])


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
    assert got.risk.final is Risk.R0 and got.user_facts == [uf]


def test_성능이_섞이면_사실_참_뒤_실증_조건부로_다시_선다(tables: None) -> None:
    """보충 4 「이어 묻기」 — 답 하나는 그 사실 하나만 푼다 · 남은 성능 주장은 실증 조건부(보충 3 결정 3)."""
    text = "HACCP 인증으로 피로 개선 효과"
    uf = UserFact(text=text, kind=FactKind.인증, true=True)
    got = _run(_confirmed(text), [uf])
    assert got is not None and is_conditional(got) and got.fact_check is None
    assert got.substantiation is not None and got.user_facts == [uf]
    JudgeResponse(outcome=Outcome.hold, sentences=[got])
    us = UserSubst(text=text, has_evidence=True)
    done = _run(_confirmed(text), [uf], [us])
    assert done is not None and done.risk.final is Risk.R0 and not done.violations
    assert done.user_facts == [uf] and done.user_subst == us


def test_사실_종류가_둘이면_하나씩_차례로_묻는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fc, "FACT_RULES", {FactKind.특허: re.compile("특허"), FactKind.인증: re.compile("인증")}
    )
    monkeypatch.setattr(
        fc,
        "FACT_TEXTS",
        {k: fc.FactText(["(시험) 증빙"], "(시험) 기준") for k in (FactKind.특허, FactKind.인증)},
    )
    monkeypatch.setattr(fc, "PERFORMANCE", re.compile("효과|개선"))
    text = "특허 원료로 만든 HACCP 인증 그래놀라"
    first = _run(_confirmed(text))
    assert first is not None and first.fact_check.kind is FactKind.특허
    p1 = UserFact(text=text, kind=FactKind.특허, true=True)
    second = _run(_confirmed(text), [p1])
    assert second is not None and second.fact_check.kind is FactKind.인증
    assert second.user_facts == [p1]
    JudgeResponse(outcome=Outcome.hold, sentences=[second])
    p2 = UserFact(text=text, kind=FactKind.인증, true=True)
    done = _run(_confirmed(text), [p2, p1])
    assert done is not None and done.risk.final is Risk.R0 and done.user_facts == [p1, p2]
    lie = UserFact(text=text, kind=FactKind.인증, true=False)
    bad = _run(_confirmed(text), [p1, lie])
    assert bad is not None and bad.verdict is Verdict.confirmed and bad.violations
    assert bad.user_facts == [p1, lie], "하나라도 거짓이면 확정 위반 그대로 + 출처"


def test_사용자가_거짓으로_고르면_확정_그대로_출처(tables: None) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인증, true=False)
    got = _run(_confirmed(), [uf])
    assert (
        got is not None
        and got.verdict is Verdict.confirmed
        and got.violations
        and got.user_facts == [uf]
    )


def test_계약_사용자_확인은_확정이나_남은_조건이_있는_조건부에만() -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인증, true=True)
    with pytest.raises(ValueError, match="사용자 확인"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.low_conf,
            user_facts=[uf],
        )
    with pytest.raises(ValueError, match="답이 둘"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.confirmed,
            risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
            user_facts=[uf, uf],
        )
    with pytest.raises(ValueError, match="다시 묻는다"):
        SentenceJudgment(
            **{
                **_confirmed().model_dump(),
                "verdict": Verdict.hold,
                "hold_reason": HoldReason.premise_unknown,
                "fact_check": {
                    "kind": "인증",
                    "confirmed_max": "R0",
                    "accepted_evidence": ["x"],
                    "criteria": "x",
                },
                "user_facts": [uf.model_dump()],
            }
        )


def test_저장은_사용자_확인_출처를_남긴다(tables: None) -> None:
    from app import judgment_store as js  # noqa: PLC0415

    uf = UserFact(text=TEXT, kind=FactKind.인증, true=True)
    got = _run(_confirmed(), [uf])
    row = js._judgment_row(
        uuid.uuid4(), uuid.uuid4(), got, JudgeResponse(outcome=Outcome.passed, sentences=[got])
    )
    assert row.evidence["user_facts"] == [{"text": TEXT, "kind": "인증", "true": True}]


def test_건기식_인정_질병_분기(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-348 결정 6 · 보충 3 결정 2 — 건기식_인정 전제의 「판정하지 못함」 질병 표방은 사실 확인 분기(`인정_기능성`)."""
    from app.graph import DictHit  # noqa: PLC0415

    hit = DictHit("위험 감소", "질병_예방치료_표방", ("013094:제8조제1항제1호|가목",), None)
    assert g._disease_answer(Premise.건기식_인정, [hit], "x", []) is None, "문안 승인 전 — 종전대로"
    monkeypatch.setattr(
        fc,
        "FACT_TEXTS",
        {FactKind.인정_기능성: fc.FactText(["(시험) 인정서"], "(시험) 인정 문구 그대로인가")},
    )
    assert g._disease_answer(Premise.건기식_비인정, [hit], "x", []) is None, "인정 전제에서만"
    assert g._disease_answer(Premise.건기식_인정, [hit], "x", []) == ("ask", None)
    worst = _confirmed("골다공증 발생 위험 감소에 도움", FOOD1, Violation.질병_예방치료_표방)
    worst = SentenceJudgment(**{**worst.model_dump(), "infeasibility": Infeasibility.C})
    asked = g._disease_branch(worst, "ask", None)
    assert is_conditional(asked) and asked.hold_reason is HoldReason.premise_unknown
    assert asked.fact_check.kind is FactKind.인정_기능성 and asked.risk.final is Risk.R2
    JudgeResponse(outcome=Outcome.hold, sentences=[asked])
    uf = UserFact(text=worst.text, kind=FactKind.인정_기능성, true=False)
    assert g._disease_answer(Premise.건기식_인정, [hit], worst.text, [uf]) == ("false", uf)
    lie = g._disease_branch(worst, "false", uf)
    assert lie.verdict is Verdict.confirmed and lie.violations and lie.user_facts == [uf]
    ok = UserFact(text=worst.text, kind=FactKind.인정_기능성, true=True)
    silent = SentenceJudgment(
        sent_id="s0", text=worst.text, verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    done = g._disease_branch(silent, "true", ok)
    assert (
        done.verdict is Verdict.confirmed and done.risk.final is Risk.R0 and done.user_facts == [ok]
    )


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
    assert eg.predict({"sentences": [cond, low]})["class"] == "조건부위반", (
        "확정위반과 같은 「하나라도」 — 확신 부족 보류가 섞여도 조건부위반"
    )
    row = {"text": TEXT, "labels": ["거짓_과장"], "조건": "B", "근거": []}
    rep = eg.conditional_report([row], [p])
    assert (rep["rows"], rep["positive"], rep["confirmed"], rep["conditional"], rep["either"]) == (
        1,
        1,
        0,
        1,
        1,
    )


def test_저장과_이력은_조건부_위반을_분류로_남긴다() -> None:
    from types import SimpleNamespace  # noqa: PLC0415

    from app import judgment_store as js  # noqa: PLC0415
    from app import reasons  # noqa: PLC0415
    from app.routers import user  # noqa: PLC0415

    cond = _run(_confirmed())
    row = js._judgment_row(
        uuid.uuid4(), uuid.uuid4(), cond, JudgeResponse(outcome=Outcome.hold, sentences=[cond])
    )
    assert (
        row.evidence["conditional"]["kind"] == "subst"
        and row.evidence["conditional"]["max"] == "R0"
    )
    import datetime as dt  # noqa: PLC0415

    j = SimpleNamespace(
        **{c.name: getattr(row, c.name, None) for c in row.__table__.columns},
    )
    j.judged_at = dt.datetime.now(dt.UTC)
    v = user._hist_view(j)
    assert v.label == reasons.CONDITIONAL_SUBST_TEXT and v.hold_reason is None


def test_평가의_보수_기록은_조건부_위반을_품목_보류로_세지_않는다() -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    p = eg.predict({"sentences": [_run(_confirmed())]})
    assert p["premise_held"] == [] and p["cond_types"] == ["거짓_과장"]
