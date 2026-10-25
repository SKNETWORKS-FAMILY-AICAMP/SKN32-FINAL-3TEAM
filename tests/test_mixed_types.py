"""섞인 유형 1 단계 — 유형마다 묻고 답을 모두 받은 뒤 합친다 (🆕 2026-10-21 · D-348 보충 39 결정 5 · 보충 37 결정 1).

지키는 것
  ① 섞인 문장은 유형마다 그 유형의 질문을 이어 묻는다 — 한 유형의 답만으로 R0 이 되지 않는다(종전 새던 꼴: 조건 고지 「예」 하나로 거짓 · 과장까지 R0)
  ② 모두 「예」로 풀렸을 때만 R0
  ③ 「아니오」인 유형 모두 확정 · 위험도는 그 유형 하한 중 높은 쪽 · 근거는 유형마다 모두 · 「예」인 유형은 싣지 않는다
  ④ 물을 질문이 없는 유형(식품 축 기만 · 보충 13)이 남으면 「확인 못 함」 보류 — 통과가 아니다(D-340 결정 6)
  ⑤ 실증형 유형마다 이어 묻고 답은 그 유형에만(🔄 보충 39 결정 6 · 2 단계) · 유형이 빈 답은 첫 실증형 유형의 답 · 화면의 유형 없는 답은 보인 질문의 유형으로 묶는다
  ⑦ 판정 결과의 실증 답은 목록(`user_substs`) · 종전 칸 `user_subst` 는 첫 답(계산 칸) · 종전 칸으로 온 입력은 목록으로 옮긴다
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


def test_실증을_먼저_답해도_남은_사실을_묻고_실증_답은_싣지_않는다() -> None:
    """계약은 「실증 답 ∧ 사실 확인 분기」를 거부한다(보충 4 결정 3) — 사실이 남았으면 실증 답은 입력에만 두고 다음 판정에 든다.

    dev 답 경로(이어 묻기)에서 처음 드러났다 — 실증에 먼저 답한 섞인 문장이 계약 오류로 멈췄다.
    """
    got = _run(_general(), substs=_subst(GEN, Answer.예))
    assert got.verdict is Verdict.hold and got.hold_kind is HoldKind.awaiting_answer
    assert got.fact_check is not None and got.fact_check.kind is FactKind.조건_고지
    assert got.user_subst is None and got.substantiation is None, "실증은 이미 답했다"
    done = _run(_general(), _cond(Answer.예), _subst(GEN, Answer.예))
    assert done.verdict is Verdict.confirmed and done.risk.final is Risk.R0


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


V2 = [Violation.거짓_과장, Violation.부당_비교광고]
T2 = "어느 제품보다 피로가 싹 풀리는 최고의 음료"


def _two(substs: list[UserSubst]) -> SentenceJudgment:
    basis = [
        _b(Premise.식품, Violation.거짓_과장, Risk.R1, FOOD4),
        _b(
            Premise.식품,
            Violation.부당_비교광고,
            Risk.R1,
            EvidenceArticle(law_id="013094", article="제8조제1항제7호"),
        ),
    ]
    got = g._enc_mixed(_held(T2, basis), [], substs, Span(start=0, end=len(T2)), V2, lambda v: [])
    assert got is not None
    return got


def _typed(v: Violation, a: Answer) -> UserSubst:
    return UserSubst(text=T2, answer=a, violation=v)


def test_실증형_유형이_둘이면_유형마다_이어_묻는다() -> None:
    """2 단계(보충 39 결정 6) — 질문에 유형이 실리고, 첫 유형에 답하면 둘째 유형을 묻는다."""
    first = _two([])
    assert (
        first.substantiation is not None and first.substantiation.violation is Violation.거짓_과장
    )
    second = _two([_typed(Violation.거짓_과장, Answer.예)])
    assert second.verdict is Verdict.hold and second.hold_kind is HoldKind.awaiting_answer
    assert second.substantiation is not None
    assert second.substantiation.violation is Violation.부당_비교광고
    assert [u.violation for u in second.user_substs] == [Violation.거짓_과장], (
        "앞선 답은 출처로 실린다"
    )


def test_실증형_유형이_둘이면_모두_예일_때만_R0() -> None:
    got = _two([_typed(Violation.거짓_과장, Answer.예), _typed(Violation.부당_비교광고, Answer.예)])
    assert got.verdict is Verdict.confirmed and got.risk.final is Risk.R0
    assert [u.violation for u in got.user_substs] == V2, "답 둘 모두 출처로 남는다"
    assert got.user_subst is not None and got.user_subst.violation is Violation.거짓_과장, (
        "종전 칸은 첫 답(계산 칸 · 보충 39 결정 6 (나))"
    )


def test_실증형_유형이_둘이면_아니오인_유형만_확정한다() -> None:
    got = _two(
        [_typed(Violation.거짓_과장, Answer.예), _typed(Violation.부당_비교광고, Answer.아니오)]
    )
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.부당_비교광고]
    assert got.substantiation is not None
    assert got.substantiation.violation is Violation.부당_비교광고, "그 유형의 지시 문안"
    both = _two(
        [_typed(Violation.거짓_과장, Answer.아니오), _typed(Violation.부당_비교광고, Answer.아니오)]
    )
    assert both.violations == V2


def test_유형이_빈_답은_첫_실증형_유형의_답이다() -> None:
    """유형을 담지 않는 종전 화면 · 요청 — 첫 유형의 답으로 읽고 둘째 유형을 묻는다(1 단계와 같은 결과 · 넓히지 않는다)."""
    no = _two(_subst(T2, Answer.아니오))
    assert no.verdict is Verdict.hold, "둘째 유형을 아직 묻는다"
    assert no.substantiation is not None
    assert no.substantiation.violation is Violation.부당_비교광고
    done = _two(_subst(T2, Answer.아니오) + [_typed(Violation.부당_비교광고, Answer.예)])
    assert done.verdict is Verdict.confirmed and done.violations == [Violation.거짓_과장], (
        "아니오를 다른 유형까지 넓히지 않는다"
    )


def test_같은_문장의_둘째_실증_답이_유형_없이_오면_거부한다() -> None:
    """`app/routers/user.py` `_untyped_again` · `_answers_of` (🔄 2026-10-24 · D-348 보충 42 결정 1 · 종전 `_tag_subst`) —
    둘째 질문에 한 유형 없는 답이 앞선 답을 지우고 첫 유형으로 읽히면 안 된다 → 받지 않는다(422)."""
    from app.routers import user as u

    assert u._untyped_again([("s0", "subst:yes:거짓_과장"), ("s0", "subst:no")]), (
        "앞선 실증 답이 있는 문장 · 유형 없음"
    )
    assert u._untyped_again([("s0", "subst:yes"), ("s0", "subst:no")])
    assert not u._untyped_again([("s0", "subst:no")]), "유형 없는 첫 답은 받는다(첫 유형 = 첫 질문)"
    assert not u._untyped_again(
        [("s0", "subst:yes:거짓_과장"), ("s0", "subst:no:부당_비교광고")]
    ), "유형이 있으면 받는다"
    assert not u._untyped_again([("s1", "subst:yes:거짓_과장"), ("s0", "subst:no")]), (
        "다른 문장의 답은 보지 않는다"
    )
    assert not u._untyped_again([("s0", "fact:인증:true"), ("s0", "subst:no")]), (
        "앞선 사실 답은 실증 답이 아니다"
    )
    assert not u._untyped_again([("s0", "subst:yes"), ("s0", "fact:인증:true")])
    facts, substs = u._answers_of(
        [("s0", "subst:yes:거짓_과장"), ("s0", "subst:no:부당_비교광고")], {"s0": T2}
    )
    assert [(x.violation, x.answer) for x in substs] == [
        (Violation.거짓_과장, Answer.예),
        (Violation.부당_비교광고, Answer.아니오),
    ], "유형이 다르면 둘 다 남는다 · 같은 유형만 바뀐다"


def test_종전_칸으로_들어온_실증_답은_목록으로_옮긴다() -> None:
    """계약 `_user_subst_in` — 계산 칸은 입력에서 무시되므로 옮기지 않으면 답이 조용히 사라진다(D-220)."""
    one = UserSubst(text=GEN, answer=Answer.예)
    s = SentenceJudgment(
        sent_id="s0",
        text=GEN,
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
        user_subst=one,
    )
    assert s.user_substs == [one] and s.user_subst == one
    again = SentenceJudgment.model_validate_json(s.model_dump_json())
    assert again.user_substs == [one], "응답 JSON 을 되읽어도 같다"
    with pytest.raises(ValueError, match="정본은 목록"):
        SentenceJudgment(
            sent_id="s0",
            text=GEN,
            verdict=Verdict.confirmed,
            risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
            user_subst=one,
            user_substs=[UserSubst(text=GEN, answer=Answer.아니오)],
        )


def test_계산_칸을_model_copy_로_바꾸려_하면_거부한다() -> None:
    """🆕 2026-10-21 (인계 10-21 클론A §2) — pydantic 은 `update` 의 계산 칸 이름을 조용히 버린다 · 막지 않으면 답이 그대로 남는다(D-220)."""
    one = UserSubst(text=GEN, answer=Answer.예)
    s = SentenceJudgment(
        sent_id="s0",
        text=GEN,
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
        user_substs=[one],
    )
    other = UserSubst(text=GEN, answer=Answer.아니오)
    with pytest.raises(ValueError, match="계산 칸"):
        s.model_copy(update={"user_subst": other})
    moved = s.model_copy(update={"user_substs": [other]})
    assert moved.user_substs == [other] and moved.user_subst == other, "정본 칸으로는 바뀐다"
    assert s.model_copy(update={"text": GEN}).user_substs == [one], "다른 칸의 복사는 그대로"


def test_유형_하나를_주면_종전대로_근거_유형이_그_하나일_때만() -> None:
    s = _general()
    span = Span(start=0, end=len(GEN))
    assert g._enc_confirmed(s, Violation.거짓_과장, span).verdict is Verdict.hold
    both = g._enc_confirmed(s, frozenset({Violation.거짓_과장}), span)
    assert both.verdict is Verdict.confirmed and both.violations == [Violation.거짓_과장]
