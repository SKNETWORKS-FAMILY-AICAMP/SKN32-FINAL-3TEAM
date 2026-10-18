"""조건부 위반 — 근거 호가 전부 조건부 호인 문장은 보류 + 선택지(사실 · 실증) · 사용자의 답은 그 문장에 출처를 남기고 반영
(🆕 2026-10-16 · D-348 보충 3 · 🔄 보충 4).

지키는 것
  ① 호 관문 — 근거 호가 **전부** 조건부 호일 때만 · 무조건 호(질병 표방 등)가 섞이면 확정 그대로 · 사전 인용이든 인코더 근거 호든 같다 (보충 4 결정 1)
  ② 사실 표지가 없으면(또는 그 종류의 문안이 승인 전이면) 실증 분기 — 보류(premise_unknown) + 실증 분기 · 위험도는 가장 나쁜 경우 그대로 (결정 1)
  ③ 사실 확인 문안 표가 비면 사실 확인 분기는 서지 않는다 — 승인 전 사실 문안을 지어내지 않는다 (보충 3 결정 6)
  ④ 답 — 사실 「참」 ∧ 꼴만 / 실증 「있음」 → 확정 · R0 · 출처 · 「거짓」 / 「없음」 ∧ 확정 → 그대로 + 출처 · 답은 그 문장에만 (결정 3 · 4)
  ⑤ 조건부 위반은 보류와 다른 분류다 — 지시 종착을 막지 않는다 · 증명서 · 통과로는 가지 않는다 (결정 2)
  ⑥ 저장은 출처를 남긴다
🔄 2026-10-18 (D-348 보충 20 · 보충 16 결정 5 집행) — **사전 확정 문장에는 분기를 달지 않는다**(사전 쪽 조건부 경로를 걷었다 · 사전은 칸 C 만 확정).
   ①~④ 의 사실 · 실증 분기와 답은 이제 **인코더 쪽 판정**이 단다(아래 「인코더만 …」 시험) · 조건부 위반 분류(⑤)와 뒷단(종착 · 기록 모음 · 저장 ·
   화면 · 평가)은 남는다 — 지금은 생성처가 없어(인코더 쪽 신뢰 규칙의 자리는 판정 대기 · 보충 17 결정 2) 시험은 조건부 문장을 직접 만든다(`_cond`)
"""

from __future__ import annotations

import re
import uuid

import pytest

from app import factcheck as fc
from app import graph as g
from app import reasons as rs
from app.contracts import (
    Answer,
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


def _cond(text: str = TEXT, sent_id: str = "s0") -> SentenceJudgment:
    """조건부 위반 문장(보류 · `premise_unknown` · 실증 분기 · 가장 나쁜 경우의 위험도) — 🔄 2026-10-18 (보충 20) 그래프에 지금 생성처가 없다 ·
    뒷단 계약을 지키려고 직접 만든다(종전 사전 쪽 경로가 내던 꼴과 같다)."""
    sub = rs.subst_branch([Violation.거짓_과장], {"식품표시광고법"})
    assert sub is not None
    return SentenceJudgment(
        **{
            **_confirmed(text).model_dump(),
            "sent_id": sent_id,
            "verdict": Verdict.hold,
            "hold_reason": HoldReason.premise_unknown,
            "substantiation": sub.model_dump(),
        }
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


def test_사실_확인_표가_비면_사실_분기는_서지_않고_사전_확정에는_분기가_없다() -> None:
    # 🔄 2026-10-17 — 유형에 딸린 다섯 종류는 승인됐다(정본 §14) · 낱말 사실 확인 종류는 여전히 승인 전이다
    word_kinds = (
        set(FactKind)
        - {k for ks in fc.TYPE_KINDS.values() for k in ks}
        - {
            FactKind.후기_실재,
            FactKind.무첨가_조건,
        }
    )
    assert fc.FACT_RULES == {} and fc.PERFORMANCE is None, (
        "🔴 승인 전 표가 채워졌다 — 문안 승인(D-263 ②) 뒤 이 게이트를 고친다"
    )
    assert not (word_kinds & set(fc.FACT_TEXTS)), (
        "🔴 낱말 사실 확인 종류의 문안이 승인 없이 들어왔다"
    )
    # 🔄 2026-10-18 (보충 20) — 종전 기대는 「보류 + 실증 분기(조건부 위반)」였다. 사전 확정 문장에는 분기를 달지 않는다
    assert _run(_confirmed()) is None, (
        "사전 확정 문장은 그대로 — 분기 · 조건부가 붙지 않는다(보충 15 결정 3)"
    )


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
    # 🔄 2026-10-16 (D-348 보충 5 · 1 단계) — 종전 기대는 None(분기 없음)이었다. 인코더 쪽 판정은 이제 **분기를 달되 보류 그대로**다 —
    #    답 없이 확정하지 않는다는 결정 5 의 뜻은 그대로(조건부 위반이 아니다)
    enc = _run(_enc_only())
    assert enc is not None and (enc.verdict, enc.hold_reason) == (Verdict.hold, HoldReason.low_conf)
    assert enc.substantiation is not None and not is_conditional(enc)
    weak = SentenceJudgment(
        **{
            **_enc_only().model_dump(),
            "violations": [Violation.거짓_과장],
            "evidence": [FOOD4.model_dump()],
        }
    )
    # 🔄 2026-10-18 (D-348 보충 16 · 2 단계 = 사전 좁히기) — 사전 후보는 판정을 막지 않는다 · 인코더 쪽 판정(보류 + 분기)으로 간다 ·
    #    후보는 여전히 확정 재료가 아니다(D-311 결정 4) — 확정도 조건부도 아니다
    got = _run(weak)
    assert got is not None and (got.verdict, got.hold_reason) == (Verdict.hold, HoldReason.low_conf)
    assert not is_conditional(got) and got.violations == [Violation.거짓_과장], (
        "유형 후보는 실려 간다"
    )


def test_인코더_쪽_판정은_신뢰_문턱과_무관하게_조건부가_아니다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔄 2026-10-16 (D-348 보충 5 · 1 단계) — 종전 「신뢰 규칙이 열리면 조건부」를 바꿨다. 인코더 쪽 판정에는 신뢰 게이트를 걸지 않는다 —
    어디에 어떻게 걸지는 사전과 합치는 단계(2 단계)에서 판정 뒤 정한다(D-192). 문턱을 열어도 인코더만 잡은 문장은 보류 + 분기다."""
    from app.contracts import EncoderTypeCandidate  # noqa: PLC0415

    monkeypatch.setattr(g, "ENCODER_CONFIRM_TAU", 0.8)
    hi = EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.9)
    base = _enc_only().model_dump()
    ok = SentenceJudgment(
        **{**base, "text": "국내 판매 1위를 지켰어요", "encoder_candidates": [hi.model_dump()]}
    )
    got = _run(ok)
    assert got is not None and not is_conditional(got) and got.substantiation is not None
    assert got.hold_reason is HoldReason.low_conf
    JudgeResponse(outcome=Outcome.hold, sentences=[got])


def test_인코더만_잡은_문장의_없음은_구간을_모르면_확정하지_않고_출처만_남긴다() -> None:
    # 🔄 2026-10-16 (D-348 보충 5) — 종전 기대는 None 이었다. 답은 출처로 남는다.
    # 🔄 2026-10-17 (1-b) — 「없음 → 확정 위반」은 **구간(문장 전체)이 설 때만**이다 — 원문이 없는 상태(이 시험)에서는 보류 + 출처(D-220)
    us = UserSubst(text=TEXT, answer=Answer.아니오)
    got = _run(_enc_only(), substs=[us])
    assert got is not None and (got.verdict, got.hold_reason) == (Verdict.hold, HoldReason.low_conf)
    assert got.user_subst == us and got.substantiation is None and not is_conditional(got)


def test_답은_그_문장에만() -> None:
    # 🔄 2026-10-18 (보충 20) — 종전 재료는 사전 확정 문장이었다 · 같은 규칙을 인코더 쪽 판정으로 본다
    us = UserSubst(text="다른 문장", answer=Answer.예)
    got = _run(_enc_only(), substs=[us])
    assert got is not None and got.substantiation is not None and got.user_subst is None


def test_종착_조건부는_답하지_않은_확정_B로_센다() -> None:
    """D-263 ① — 조건부 위반의 가장 나쁜 경우는 「자료 없음 = 확정 B」다. 섞인 문서의 종착은 그 기준이다."""
    cond = _cond(sent_id="s9")
    ready = SentenceJudgment(
        **{
            **_confirmed().model_dump(),
            "sent_id": "s1",
            "substantiation": cond.substantiation.model_dump(),
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
    # 🔄 2026-10-18 (보충 20) — 분기 문장이 조건부 위반이면(지금은 생성처 없음 · 직접 만든다) 기록 문장도 조건부로 모은다
    got = _doc(_confirmed(), {"식품": _cond(), "일반상품": _cond()})
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
    got = _doc(_confirmed(), {"식품": _cond(), "건기식_비인정": disease})
    rec = got["rec"]
    assert (rec.verdict, rec.hold_reason) == (Verdict.hold, HoldReason.cat_unknown)
    assert rec.substantiation is None and not is_conditional(rec)
    kinds = {b.premise.value: is_conditional(b.sentences[0]) for b in got["branches"]}
    assert kinds == {"식품": True, "건기식_비인정": False}


def test_계약_실증_분기는_인코더_쪽_보류에도_붙되_조건부가_아니다() -> None:
    # 🔄 2026-10-16 (D-348 보충 5) — 종전 「확신 부족 보류에 못 붙는다」를 바꿨다. 인코더 쪽 판정은 답 없이 확정하지 않으므로
    #    확신 부족 보류(`low_conf`)에 분기만 붙고 조건부 위반으로 세지 않는다. 그 밖의 보류 사유에는 여전히 못 붙는다
    sub = rs.subst_branch([Violation.거짓_과장], {"식품표시광고법"})
    enc = SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        infeasibility=Infeasibility.B,
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
        substantiation=sub,
    )
    assert not is_conditional(enc), "인코더 쪽 보류 + 분기는 조건부 위반이 아니다(보충 5)"
    with pytest.raises(ValueError, match="조건부 위반"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.cat_unknown,
            infeasibility=Infeasibility.B,
            risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
            substantiation=sub,
        )
    SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        user_subst=UserSubst(text=TEXT, answer=Answer.해당없음),
    )
    with pytest.raises(ValueError, match="실증 여부"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.cat_unknown,
            user_subst=UserSubst(text=TEXT, answer=Answer.예),
        )


def test_호_관문_밖이면_낱말이_있어도_분기를_달지_않는다(tables: None) -> None:
    disease = _confirmed("인증받은 원료로 당뇨를 치료", FOOD1, Violation.질병_예방치료_표방)
    assert _run(disease) is None, "질병 표방(1호)은 조건부 호가 아니다"


def test_인코더만_잡은_보류도_사실_표지면_사실_분기(tables: None) -> None:
    # 🔄 2026-10-16 (D-348 보충 5) — 종전 기대(`premise_unknown` = 조건부 위반)는 **결함**이었다 — 인코더만 잡은 문장이 질문 하나로
    #    「답 없으면 확정」이 됐다(신뢰 규칙 우회). 이제 확신 부족 보류 그대로 + 사실 확인 분기다
    got = _run(_enc_only())
    assert got is not None and got.hold_reason is HoldReason.low_conf and got.fact_check
    assert not is_conditional(got)
    JudgeResponse(outcome=Outcome.hold, sentences=[got])


def test_사실_종류가_둘이면_하나씩_차례로_묻는다(monkeypatch: pytest.MonkeyPatch) -> None:
    # 🔄 2026-10-18 (보충 20) — 종전 재료는 사전 확정 문장이었다 · 같은 「이어 묻기」를 인코더 쪽 판정으로 본다
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
    enc = SentenceJudgment(**{**_enc_only().model_dump(), "text": text})
    first = _run(enc)
    assert first is not None and first.fact_check.kind is FactKind.특허
    p1 = UserFact(text=text, kind=FactKind.특허, answer=Answer.예)
    second = _run(enc, [p1])
    assert second is not None and second.fact_check.kind is FactKind.인증
    assert second.user_facts == [p1]
    JudgeResponse(outcome=Outcome.hold, sentences=[second])
    p2 = UserFact(text=text, kind=FactKind.인증, answer=Answer.예)
    done = _run(enc, [p2, p1])
    assert done is not None and done.risk.final is Risk.R0 and done.user_facts == [p1, p2]


def test_계약_사용자_확인은_확정이나_남은_조건이_있는_조건부에만() -> None:
    # 🔄 2026-10-16 (D-348 보충 5) — 인코더 쪽 보류(`low_conf`)에도 답이 실린다(답 없이 확정하지 않는 쪽의 출처). 그 밖의 보류에는 못 실린다
    uf = UserFact(text=TEXT, kind=FactKind.인증, answer=Answer.예)
    SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        user_facts=[uf],
    )
    with pytest.raises(ValueError, match="사용자 확인"):
        SentenceJudgment(
            sent_id="s0",
            text=TEXT,
            verdict=Verdict.hold,
            hold_reason=HoldReason.cat_unknown,
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

    # 🔄 2026-10-18 (보충 20) — 출처를 내는 쪽은 인코더 쪽 판정이다(사실 참 ∧ 사실만 주장 → 확정 · R0)
    uf = UserFact(text=TEXT, kind=FactKind.인증, answer=Answer.예)
    got = _run(_enc_only(), [uf])
    row = js._judgment_row(
        uuid.uuid4(), uuid.uuid4(), got, JudgeResponse(outcome=Outcome.passed, sentences=[got])
    )
    assert row.evidence["user_facts"] == [{"text": TEXT, "kind": "인증", "answer": "예"}]


def test_저장은_실증_답_출처를_남긴다() -> None:
    from app import judgment_store as js  # noqa: PLC0415

    us = UserSubst(text=TEXT, answer=Answer.예)
    got = _run(_enc_only(), substs=[us])  # 🔄 2026-10-18 (보충 20) — 인코더 쪽 실증 답
    row = js._judgment_row(
        uuid.uuid4(), uuid.uuid4(), got, JudgeResponse(outcome=Outcome.passed, sentences=[got])
    )
    assert row.evidence["user_subst"] == {"text": TEXT, "answer": "예"}


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
    got = _cond()
    assert str(m.sent_concl(got)).strip() == reasons.CONDITIONAL_SUBST_TEXT
    low = SentenceJudgment(
        sent_id="s2", text="x", verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    assert reasons.conditional_text(low) == "", "확신 부족 보류는 조건부 위반이 아니다"


def test_평가는_조건부_위반을_보류와_따로_센다() -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    cond = _cond()
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

    cond = _cond()
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

    p = eg.predict({"sentences": [_cond()]})
    assert p["premise_held"] == [] and p["cond_types"] == ["거짓_과장"]


# ── 🆕 2026-10-16 (D-348 보충 5) — 답 셋 · 「해당없음」(보충 3 결정 2 의 집행) ─────────────────────────────


def test_사실_해당없음이면_그_종류는_묻지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    # 🔄 2026-10-18 (보충 20) — 같은 규칙을 인코더 쪽 판정으로 본다(종전 재료는 사전 확정 문장)
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
    enc = SentenceJudgment(**{**_enc_only().model_dump(), "text": text})
    na = UserFact(text=text, kind=FactKind.특허, answer=Answer.해당없음)
    got = _run(enc, [na])
    assert got is not None and got.fact_check.kind is FactKind.인증, "해당없음인 종류를 건너뛴다"
    assert got.user_facts == [na], "해당없음 답은 출처로 따라간다"
    both = [na, UserFact(text=text, kind=FactKind.인증, answer=Answer.해당없음)]
    rest = _run(enc, both)
    assert rest is not None and rest.fact_check is None and rest.substantiation is not None, (
        "사실 종류를 전부 걷으면 실증 질문으로 남는다 — R0 으로 가지 않는다"
    )
    assert rest.risk.final is not Risk.R0 and not is_conditional(rest)


# ── 🆕 2026-10-16 (D-348 보충 5 · 1 단계) — 인코더 쪽 판정 ─────────────────────────────────────


def test_인코더만_실증_있음이면_확정_R0_과_출처() -> None:
    us = UserSubst(text=TEXT, answer=Answer.예)
    got = _run(_enc_only(), substs=[us])
    assert got is not None and got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0 and got.user_subst == us
    JudgeResponse(outcome=Outcome.passed, sentences=[got], product=ProductContext(category=None))


def test_인코더만_실증_해당없음이면_분기를_걷고_보류() -> None:
    us = UserSubst(text=TEXT, answer=Answer.해당없음)
    got = _run(_enc_only(), substs=[us])
    assert got is not None and got.hold_reason is HoldReason.low_conf
    assert got.substantiation is None and got.user_subst == us


def test_인코더만_사실_참이고_사실만_주장하면_R0(tables: None) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인증, answer=Answer.예)
    got = _run(_enc_only(), [uf])
    assert got is not None and got.verdict is Verdict.confirmed and got.risk.final is Risk.R0
    assert got.user_facts == [uf]


def test_인코더만_사실_참이어도_성능이_섞이면_실증으로_이어_묻는다(tables: None) -> None:
    text = "HACCP 인증으로 피로 개선 효과"
    uf = UserFact(text=text, kind=FactKind.인증, answer=Answer.예)
    got = _run(SentenceJudgment(**{**_enc_only().model_dump(), "text": text}), [uf])
    assert got is not None and got.hold_reason is HoldReason.low_conf
    assert got.fact_check is None and got.substantiation is not None and got.user_facts == [uf]
    assert not is_conditional(got)


def test_인코더만_사실_거짓은_확정하지_않고_출처만(tables: None) -> None:
    # ⬜ 「거짓 → 확정 위반」은 계약 개정 뒤(D-323 결정 3 · 보충 2 결정 3) — 그 전까지 보류 + 출처
    uf = UserFact(text=TEXT, kind=FactKind.인증, answer=Answer.아니오)
    got = _run(_enc_only(), [uf])
    assert got is not None and got.hold_reason is HoldReason.low_conf and got.fact_check is None
    assert got.user_facts == [uf]


def test_인코더만_화장품_전제는_실증_문안의_축을_고르지_않는다() -> None:
    """D-272 개정 (나) ⑥ — 화장품의 주 근거는 ⬜ → 분기 없음(D-220)."""
    from app.contracts import EncoderBasis  # noqa: PLC0415

    ref = EvidenceArticle(law_id="002015", article="제13조제1항제4호")
    s = SentenceJudgment(
        **{
            **_enc_only().model_dump(),
            "risk": RiskAssessment(
                encoder=Risk.R1,
                final=Risk.R1,
                encoder_basis=[
                    EncoderBasis(
                        premise=Premise.화장품,
                        violation=Violation.거짓_과장,
                        floor=Risk.R1,
                        articles=[ref],
                    )
                ],
            ),
        }
    )
    assert _run(s) is None


def test_인코더만_기록은_분기의_선택지를_싣고_보류_그대로() -> None:
    got = _doc(_enc_only(), {"식품": _enc_only()})
    b = got["branches"][0].sentences[0]
    assert b.hold_reason is HoldReason.low_conf and b.substantiation is not None
    rec = got["rec"]
    assert (rec.verdict, rec.hold_reason) == (Verdict.hold, HoldReason.low_conf)
    assert rec.substantiation is not None and not is_conditional(rec)


def test_인코더_근거에_DB_청크_항목이_붙어도_호_관문을_지난다() -> None:
    """🆕 2026-10-17 (원장 10-16(B) ⑧) — 실제 그래프는 참조 조항에 원문과 청크 항목(「4.」 · 「본문」)을 붙인다(`reference_texts`).
    종전엔 항목이 있으면 좌표를 버려 인코더 근거 좌표가 비었다 → 호 관문이 늘 닫혀 dev 의 인코더 쪽 분기가 0 행이었다."""
    from app.contracts import EncoderBasis  # noqa: PLC0415

    arts = [
        EvidenceArticle(law_id="002011", article="제3조제1항제1호", item="1."),
        EvidenceArticle(law_id="005361", article="제3조제1항"),
        EvidenceArticle(law_id="013094", article="제8조제1항제4호", item="4."),
        EvidenceArticle(law_id="013453", article="[별표 1]제4호", item="본문"),
    ]
    assert g._coords(arts) == {("002011", 3, 1, 1), ("013094", 8, 1, 4)}, (
        "시행령 · 별표 좌표는 인용 꼴이 아니라 버린다 — 법률 호 둘만 남는다"
    )
    s = SentenceJudgment(
        **{
            **_enc_only().model_dump(),
            "risk": RiskAssessment(
                encoder=Risk.R1,
                final=Risk.R1,
                encoder_basis=[
                    EncoderBasis(
                        premise=Premise.식품,
                        violation=Violation.거짓_과장,
                        floor=Risk.R1,
                        articles=arts,
                    )
                ],
            ),
        }
    )
    got = _run(s)
    assert got is not None and got.substantiation is not None and not is_conditional(got)


# ── 🆕 2026-10-17 (D-348 보충 5 결정 4 · 1-b) — 인코더 쪽 「아니오」 → 확정 위반 ─────────────────────────────


def _run_t(
    s: SentenceJudgment,
    facts: list[UserFact] | None = None,
    substs: list[UserSubst] | None = None,
) -> SentenceJudgment | None:
    """원문 · 문장이 있는 상태 — 문장 전체 구간이 선다(`_sentence_spans`)."""
    out = g.doc_rules(
        {
            "text": "앞 문장. " + s.text,
            "sents": ["앞 문장.", s.text],
            "sentences": [SentenceJudgment(**{**s.model_dump(), "sent_id": g.sent_id(1)})],
            "product": ProductContext(facts=facts or [], substs=substs or []),
        }
    )
    got = out.get("sentences") or []
    return got[0] if got else None


def test_인코더만_실증_없음이면_확정_위반_문장_전체_구간_지시() -> None:
    us = UserSubst(text=TEXT, answer=Answer.아니오)
    got = _run_t(_enc_only(), substs=[us])
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.거짓_과장] and got.infeasibility is Infeasibility.B
    assert [(x.start, x.end) for x in got.spans] == [(6, 6 + len(TEXT))], "문장 전체 · 원문 좌표"
    assert got.substantiation is not None and got.user_subst == us
    assert got.risk.encoder is None and got.risk.final is Risk.R1, "제재표 하한(시험 근거 R1)"
    assert got.evidence and not any(e.basis for e in got.evidence), (
        "대응표 조항 — 문장에서 찾은 조문이 아니다"
    )
    JudgeResponse(outcome=Outcome.guidance, sentences=[got])


def test_인코더만_사실_거짓이면_확정_위반_실증_분기_없이_지시(tables: None) -> None:
    from app.contracts import fact_false  # noqa: PLC0415

    uf = UserFact(text=TEXT, kind=FactKind.인증, answer=Answer.아니오)
    got = _run_t(_enc_only(), [uf])
    assert got is not None and got.verdict is Verdict.confirmed and got.violations
    assert got.substantiation is None and fact_false(got), "실증으로 풀리지 않는다 — 고치거나 빼기"
    JudgeResponse(outcome=Outcome.guidance, sentences=[got])


def test_인코더_근거_유형이_분기_유형과_다르면_사실_질문을_내지_않는다(tables: None) -> None:
    """화장품법 13조①4호는 거짓 · 과장과 기만이 같은 호다 — 관문은 지나도 기만 문장에 사실 질문을 붙이지 않는다(1-b)."""
    from app.contracts import EncoderBasis  # noqa: PLC0415

    ref = EvidenceArticle(law_id="002015", article="제13조제1항제4호")
    s = SentenceJudgment(
        **{
            **_enc_only().model_dump(),
            "risk": RiskAssessment(
                encoder=Risk.R1,
                final=Risk.R1,
                encoder_basis=[
                    EncoderBasis(
                        premise=Premise.화장품,
                        violation=Violation.소비자_기만,
                        floor=Risk.R1,
                        articles=[ref],
                    )
                ],
            ),
        }
    )
    assert _run(s) is None


def test_인코더만_건기식_인정_질병은_인정_기능성_분기(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.contracts import EncoderBasis  # noqa: PLC0415

    monkeypatch.setattr(
        fc,
        "FACT_TEXTS",
        {FactKind.인정_기능성: fc.FactText(["(시험) 인정서"], "(시험) 인정 문구 그대로인가")},
    )
    ref = EvidenceArticle(law_id="013094", article="제8조제1항제1호", item="1.")
    base = SentenceJudgment(
        **{
            **_enc_only().model_dump(),
            "risk": RiskAssessment(
                encoder=Risk.R1,
                final=Risk.R1,
                encoder_basis=[
                    EncoderBasis(
                        premise=Premise.건기식_인정,
                        violation=Violation.질병_예방치료_표방,
                        floor=Risk.R2,
                        articles=[ref],
                    )
                ],
            ),
        }
    )
    ask = _run(base)
    assert ask is not None and ask.fact_check.kind is FactKind.인정_기능성
    assert ask.hold_reason is HoldReason.low_conf and not is_conditional(ask)
    yes = UserFact(text=TEXT, kind=FactKind.인정_기능성, answer=Answer.예)
    assert _run(base, [yes]).risk.final is Risk.R0
    no = UserFact(text=TEXT, kind=FactKind.인정_기능성, answer=Answer.아니오)
    got = _run_t(base, [no])
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.질병_예방치료_표방] and got.infeasibility is Infeasibility.C
    assert got.risk.final is Risk.R2, "그 유형 · 그 전제의 제재표 하한"


def test_인코더만_기록은_분기가_아니오로_확정되면_확정_위반() -> None:
    us = UserSubst(text=TEXT, answer=Answer.아니오)
    rec = SentenceJudgment(**{**_enc_only().model_dump(), "sent_id": g.sent_id(1)})
    out = g.doc_rules(
        {
            "text": "앞 문장. " + TEXT,
            "sents": ["앞 문장.", TEXT],
            "sentences": [rec],
            "branches": [_branch("식품", [rec])],
            "product": ProductContext(substs=[us]),
        }
    )
    got = (out.get("sentences") or [rec])[0]
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.거짓_과장]
    assert got.user_subst == us
