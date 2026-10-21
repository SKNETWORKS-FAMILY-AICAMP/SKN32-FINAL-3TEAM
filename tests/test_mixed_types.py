"""섞인 유형 1 단계 — 유형마다 묻고 답을 모두 받은 뒤 합친다 (🆕 2026-10-21 · D-348 보충 39 결정 5 · 보충 37 결정 1).

지키는 것
  ① 섞인 문장은 유형마다 그 유형의 질문을 이어 묻는다 — 한 유형의 답만으로 R0 이 되지 않는다(종전 새던 꼴: 조건 고지 「예」 하나로 거짓 · 과장까지 R0)
  ② 모두 「예」로 풀렸을 때만 R0
  ③ 「아니오」인 유형 모두 확정 · 위험도는 그 유형 하한 중 높은 쪽 · 근거는 유형마다 모두 · 「예」인 유형은 싣지 않는다
  ④ 물을 질문이 없는 유형(식품 축 기만 · 보충 13)이 남으면 「확인 못 함」 보류 — 통과가 아니다(D-340 결정 6)
  ⑤ 실증 답은 문장에 하나라 실증형 유형 중 첫 유형에만 든다(2 단계 전) — 둘째 실증형 유형은 남는다
  ⑥ 유형 하나는 종전 경로 그대로 — `_enc_confirmed` 에 유형 하나를 주면 근거 유형이 그 하나일 때만 확정
"""

from __future__ import annotations

import pytest

from app import graph as g
from app.contracts import (
    Answer,
    EncoderBasis,
    EvidenceArticle,
    FactKind,
    HoldKind,
    HoldReason,
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
)

pytestmark = pytest.mark.gate

FAIR1 = EvidenceArticle(law_id="002011", article="제3조제1항제1호")
FAIR2 = EvidenceArticle(law_id="002011", article="제3조제1항제2호")
FOOD4 = EvidenceArticle(law_id="013094", article="제8조제1항제4호")
FOOD5 = EvidenceArticle(law_id="013094", article="제8조제1항제5호")

GEN = "전 품목 50% 할인, 업계 최고의 품질"
FOOD = "피로가 싹 풀리는 최고의 음료"


def _b(p: Premise, v: Violation, floor: Risk, art: EvidenceArticle) -> EncoderBasis:
    return EncoderBasis(premise=p, violation=v, floor=floor, articles=[art])


def _general() -> SentenceJudgment:
    basis = [
        _b(Premise.일반상품, Violation.거짓_과장, Risk.R1, FAIR1),
        _b(Premise.일반상품, Violation.소비자_기만, Risk.R2, FAIR2),
    ]
    return _held(GEN, basis)


def _food() -> SentenceJudgment:
    basis = [
        _b(Premise.식품, Violation.거짓_과장, Risk.R1, FOOD4),
        _b(Premise.식품, Violation.소비자_기만, Risk.R1, FOOD5),
    ]
    return _held(FOOD, basis)


def _held(text: str, basis: list[EncoderBasis]) -> SentenceJudgment:
    # 답 없는 인코더 쪽 기록 위험도는 R1 층(D-348 결정 5) — 근거 하한(제재표)은 확정 때 쓴다
    top = Risk.R1
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=top, encoder_basis=basis, final=top),
    )


def _run(
    s: SentenceJudgment,
    facts: list[UserFact] | None = None,
    substs: list[UserSubst] | None = None,
) -> SentenceJudgment:
    # 문장 구간(`_sentence_spans`)은 원문 · 문장 목록에서 선다 — 없으면 확정하지 않는다(D-220)
    out = g.doc_rules(
        {
            "sentences": [s],
            "text": s.text,
            "sents": [s.text],
            "product": ProductContext(facts=facts or [], substs=substs or []),
        }
    )
    got = out.get("sentences") or []
    assert got, "판정이 바뀌지 않았다"
    return got[0]


def _cond(a: Answer) -> list[UserFact]:
    return [UserFact(text=GEN, kind=FactKind.조건_고지, answer=a)]


def _subst(text: str, a: Answer) -> list[UserSubst]:
    return [UserSubst(text=text, answer=a)]


def test_답하기_전에는_첫_유형의_질문과_실증을_묻는다() -> None:
    got = _run(_general())
    assert got.verdict is Verdict.hold and got.hold_kind is HoldKind.awaiting_answer
    assert got.fact_check is not None and got.fact_check.kind is FactKind.조건_고지
    assert got.substantiation is not None, "거짓 · 과장의 실증도 함께 묻는다"


def test_한_유형의_예만으로는_R0_이_아니다() -> None:
    """종전 결함 — 조건 고지 「예」 하나로 거짓 · 과장까지 R0 으로 닫혔다."""
    got = _run(_general(), _cond(Answer.예))
    assert got.verdict is Verdict.hold, "거짓 · 과장의 실증을 아직 받지 않았다"
    assert got.substantiation is not None and got.user_subst is None
    assert got.hold_kind is HoldKind.awaiting_answer


def test_모두_예면_R0() -> None:
    got = _run(_general(), _cond(Answer.예), _subst(GEN, Answer.예))
    assert got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0
    assert got.user_subst is not None and got.user_facts


def test_모두_아니오면_모두_확정_위험도는_높은_쪽_근거는_모두() -> None:
    got = _run(_general(), _cond(Answer.아니오), _subst(GEN, Answer.아니오))
    assert got.verdict is Verdict.confirmed
    assert got.violations == [Violation.거짓_과장, Violation.소비자_기만]
    assert got.risk.final is Risk.R2, "하한 R1 · R2 중 높은 쪽"
    assert {(a.law_id, a.article) for a in got.evidence} == {
        ("002011", "제3조제1항제1호"),
        ("002011", "제3조제1항제2호"),
    }
    assert got.spans and got.spans[0].label == "거짓_과장,소비자_기만"
    assert got.substantiation is not None, "실증 「아니오」로 선 유형이 있으면 지시 문안"


def test_아니오인_유형만_확정한다() -> None:
    got = _run(_general(), _cond(Answer.아니오), _subst(GEN, Answer.예))
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.소비자_기만]
    assert got.risk.final is Risk.R2
    assert got.substantiation is None, "사실 거짓으로 선 확정에는 실증 지시가 없다"


def test_아니오가_먼저_와도_남은_질문을_계속_묻는다() -> None:
    got = _run(_general(), _cond(Answer.아니오))
    assert got.verdict is Verdict.hold and got.hold_kind is HoldKind.awaiting_answer
    assert got.substantiation is not None


def test_해당없음으로_걷힌_유형은_풀리지_않는다() -> None:
    got = _run(_general(), _cond(Answer.해당없음), _subst(GEN, Answer.예))
    assert got.verdict is Verdict.hold, "기만이 풀리지 않았다 — 통과가 아니다"


def test_물을_질문이_없는_유형이_남으면_확인_못_함() -> None:
    """식품 축 기만에는 조건 고지를 묻지 않는다(보충 13) — 거짓 · 과장의 실증 「예」로 R0 이 되지 않는다."""
    got = _run(_food(), substs=_subst(FOOD, Answer.예))
    assert got.verdict is Verdict.hold
    assert got.hold_kind is HoldKind.unconfirmed
    assert got.user_subst is not None, "답은 출처로 남는다"


def test_물을_질문이_없는_유형이_있어도_아니오인_유형은_확정한다() -> None:
    got = _run(_food(), substs=_subst(FOOD, Answer.아니오))
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.거짓_과장]


def test_실증형_유형이_둘이면_답은_첫_유형에만_든다() -> None:
    """2 단계(답 칸 유형별 · 보충 39 결정 6) 전 — 한 유형의 문안에 답한 실증이 다른 주장까지 풀지도 · 넓히지도 않는다."""
    basis = [
        _b(Premise.식품, Violation.거짓_과장, Risk.R1, FOOD4),
        _b(
            Premise.식품,
            Violation.부당_비교광고,
            Risk.R1,
            EvidenceArticle(law_id="013094", article="제8조제1항제7호"),
        ),
    ]
    text = "어느 제품보다 피로가 싹 풀리는 최고의 음료"
    s = _held(text, basis)
    first = g._enc_mixed(
        s,
        [],
        [],
        Span(start=0, end=len(text)),
        [Violation.거짓_과장, Violation.부당_비교광고],
        lambda v: [],
    )
    assert first is not None and first.substantiation is not None
    yes = g._enc_mixed(
        s,
        [],
        _subst(text, Answer.예),
        Span(start=0, end=len(text)),
        [Violation.거짓_과장, Violation.부당_비교광고],
        lambda v: [],
    )
    assert yes is not None and yes.verdict is Verdict.hold, "부당 비교는 실증을 묻지 못해 남는다"
    no = g._enc_mixed(
        s,
        [],
        _subst(text, Answer.아니오),
        Span(start=0, end=len(text)),
        [Violation.거짓_과장, Violation.부당_비교광고],
        lambda v: [],
    )
    assert no is not None and no.violations == [Violation.거짓_과장], (
        "아니오를 다른 유형까지 넓히지 않는다"
    )


def test_유형_하나를_주면_종전대로_근거_유형이_그_하나일_때만() -> None:
    s = _general()
    span = Span(start=0, end=len(GEN))
    assert g._enc_confirmed(s, Violation.거짓_과장, span).verdict is Verdict.hold
    both = g._enc_confirmed(s, frozenset({Violation.거짓_과장}), span)
    assert both.verdict is Verdict.confirmed and both.violations == [Violation.거짓_과장]
