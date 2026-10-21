"""부당 비교 · 비방의 실증 갈래 ① · 후기 실재 자리 (🆕 2026-10-19 · D-348 보충 28 결정 1 · 2).

지키는 것
  ① 문안은 정본 §18 과 글자가 같다 · 자료 종류는 §13 법 축 줄과 같다 · 화장품 축 비방 줄은 없다 · 🔄 식품 축 비방 줄은 최상급 · 순위 꼴만(보충 40)
  ② 사실 갈래가 「예」면 실증 갈래가 선다 — 실증 「예」면 R0 · 「아니오」면 그 유형으로 확정 위반(B) · 두 갈래를 모두 지나야 닫는다
  ③ 표시광고법 축 소비자 기만에 인코더 후기 후보가 함께 서면 조건 고지 대신 후기 실재를 묻는다
"""

from __future__ import annotations

import pathlib

import pytest

from app import graph as g
from app import reasons as rs
from app.contracts import (
    Answer,
    Category,
    EncoderBasis,
    EncoderTypeCandidate,
    EvidenceArticle,
    FactKind,
    HoldReason,
    Infeasibility,
    Premise,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    UserFact,
    UserSubst,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

DOC = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md")
FAIR2 = EvidenceArticle(law_id="002011", article="제3조제1항제2호")
FAIR3 = EvidenceArticle(law_id="002011", article="제3조제1항제3호")
FAIR4 = EvidenceArticle(law_id="002011", article="제3조제1항제4호")
CMP = "다른 회사 제품보다 2배 더 오래갑니다"
SLD = "다른 회사 제품은 효과가 없습니다"


def _enc(
    premise: Premise,
    v: Violation,
    art: EvidenceArticle,
    text: str,
    cands: list[EncoderTypeCandidate] | None = None,
) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=g.sent_id(1),
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=cands or [],
        risk=RiskAssessment(
            encoder=Risk.R1,
            final=Risk.R1,
            encoder_basis=[
                EncoderBasis(premise=premise, violation=v, floor=Risk.R1, articles=[art])
            ],
        ),
    )


def _run(
    s: SentenceJudgment,
    cat: str,
    facts: list[UserFact] | None = None,
    substs: list[UserSubst] | None = None,
) -> SentenceJudgment | None:
    state = {
        "text": "앞 문장. " + s.text,
        "sents": ["앞 문장.", s.text],
        "sentences": [s],
        "product": ProductContext(category=Category(cat), facts=facts or [], substs=substs or []),
    }
    got = g.doc_rules(state).get("sentences") or []
    return got[0] if got else None


def test_문안은_정본_18절과_같다() -> None:
    doc = DOC.read_text(encoding="utf-8")
    sec = doc[doc.index("## 18.") : doc.index("## 19.")]
    assert set(rs.TYPE_SUBST_TEXT) == {
        (Violation.부당_비교광고, "표시광고법"),
        (Violation.부당_비교광고, "식품표시광고법"),
        (Violation.부당_비교광고, "화장품법"),
        (Violation.비방광고, "표시광고법"),
        (Violation.비방광고, "식품표시광고법"),  # 🆕 보충 40 — 최상급 · 순위 꼴만
    }
    for (v, ax), t in rs.TYPE_SUBST_TEXT.items():
        assert t.criteria in sec, (v, ax)
        assert t.evidence == rs.SUBST_TEXT[ax].evidence, "자료 종류는 §13 법 축 줄과 같다"
    assert rs.subst_branch([Violation.비방광고], {"화장품법"}) is None, "화장품 비방은 칸 C"


FOOD6 = EvidenceArticle(law_id="013094", article="제8조제1항제6호")
RANK = "업계 시장 점유율 1위 제품"


def test_식품_비방_줄은_최상급_순위_꼴에만_선다() -> None:
    """🆕 2026-10-21 (D-348 보충 40 결정 1 · 3) — 고시 69549 제2조 4.나 꼴만 · 글자가 없으면 서지 않는다(D-220)."""
    food = {"식품표시광고법"}
    sb = rs.subst_branch([Violation.비방광고], food, RANK)
    want = rs.TYPE_SUBST_TEXT[(Violation.비방광고, "식품표시광고법")]
    assert sb is not None and sb.criteria == want.criteria and sb.substantiated_max is Risk.R0
    for t in (
        "국내 최초로 담았습니다",
        "The Only 오직 여기에만",
        "아기과학 No.1",
        "최고의 완전식품",
    ):
        assert rs.subst_branch([Violation.비방광고], food, t) is not None, t
    for t in (
        None,
        "",
        "종이실링보다 더 튼튼한 가이드",  # 자사 우월 비교 꼴 — 7.가 쪽 · 줄 없음
        "시중 타제품보다 높은 함유율",  # 타사 언급 ∧ 비교
        "시중 제품 중 1위",  # 타사 언급
        "불필요한 것을 일체 넣지 않습니다",  # 표지 없음
    ):
        assert rs.subst_branch([Violation.비방광고], food, t) is None, t
    assert rs.subst_branch([Violation.비방광고], {"화장품법"}, RANK) is None, "화장품 축은 기록만"
    assert rs.subst_branch([Violation.비방광고, Violation.거짓_과장], food, RANK) is None, (
        "섞이면 줄을 고르지 않는다"
    )


def test_비교_표지의_합은_종전과_같다() -> None:
    """보충 40 결정 2 — 두 갈래로 갈라도 `comparison_claim` 이 서는 자리는 같다(비교 기준을 묻는 자리 불변)."""
    import re

    from app import factcheck as fc

    # 보충 11 의 종전 정규식 글자 그대로 — 두 갈래의 합이 이것과 같은 자리에 서야 한다
    OLD_CUE = re.compile(  # noqa: N806
        r"보다|대비|비해|비교(?!적)|\d\s?배|최고|최상|최초|최대|최다|최적|제일|유일|독보|가장|처음으로|넘버\s?원|no\.?\s?1|\d\s?위|1등(?!급)|일등|\bonly\b",
        re.IGNORECASE,
    )
    for t in (
        "보다 낫다",
        "2배",
        "최초",
        "No.1",
        "only",
        "3위",
        "비교적 무난",
        "처음 드시는 분",
        "일반 문장",
        "1등급 원료",
    ):
        assert fc.comparison_claim(t) is bool(OLD_CUE.search(t)), t
    assert fc.comparison_claim("최초") and fc.superlative_only("최초")
    assert fc.comparison_claim("보다 낫다") and not fc.superlative_only("보다 낫다")


def test_식품_비방_순위_꼴은_비교_기준_예_뒤_실증_예면_R0() -> None:
    s = _enc(Premise.식품, Violation.비방광고, FOOD6, RANK)
    yes = UserFact(text=RANK, kind=FactKind.비교_기준, answer=Answer.예)
    got = _run(s, "식품", [yes])
    assert got is not None and got.verdict is Verdict.hold and got.substantiation is not None
    want = rs.TYPE_SUBST_TEXT[(Violation.비방광고, "식품표시광고법")].criteria
    assert got.substantiation.criteria == want
    done = _run(s, "식품", [yes], [UserSubst(text=RANK, answer=Answer.예)])
    assert done is not None and done.verdict is Verdict.confirmed and not done.violations
    assert done.risk.final is Risk.R0
    no = _run(s, "식품", [yes], [UserSubst(text=RANK, answer=Answer.아니오)])
    assert no is not None and no.verdict is Verdict.confirmed
    assert no.violations == [Violation.비방광고]


def test_식품_비방_비교_꼴은_예여도_줄이_없어_남는다() -> None:
    t = "종이실링보다 더 튼튼한 가이드로 보호합니다"
    s = _enc(Premise.식품, Violation.비방광고, FOOD6, t)
    yes = UserFact(text=t, kind=FactKind.비교_기준, answer=Answer.예)
    got = _run(s, "식품", [yes])
    assert got is not None and got.substantiation is None
    assert got.risk.final is not Risk.R0, "줄이 없으면 「예」로 닫지 않는다(보충 40 결정 1)"


def test_비교_기준_예면_실증_갈래가_서고_실증_예면_R0() -> None:
    s = _enc(Premise.일반상품, Violation.부당_비교광고, FAIR3, CMP)
    yes = UserFact(text=CMP, kind=FactKind.비교_기준, answer=Answer.예)
    got = _run(s, "일반상품", [yes])
    assert got is not None and got.verdict is Verdict.hold and got.substantiation is not None
    want = rs.TYPE_SUBST_TEXT[(Violation.부당_비교광고, "표시광고법")].criteria
    assert got.substantiation.criteria == want
    done = _run(s, "일반상품", [yes], [UserSubst(text=CMP, answer=Answer.예)])
    assert done is not None and done.verdict is Verdict.confirmed and not done.violations
    assert done.risk.final is Risk.R0


def test_실증_아니오는_그_유형으로_확정_위반() -> None:
    s = _enc(Premise.일반상품, Violation.부당_비교광고, FAIR3, CMP)
    yes = UserFact(text=CMP, kind=FactKind.비교_기준, answer=Answer.예)
    got = _run(s, "일반상품", [yes], [UserSubst(text=CMP, answer=Answer.아니오)])
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.부당_비교광고] and got.infeasibility is Infeasibility.B


def test_비방_선별_예면_근거_갈래가_선다() -> None:
    s = _enc(Premise.일반상품, Violation.비방광고, FAIR4, SLD)
    yes = UserFact(text=SLD, kind=FactKind.비방_선별, answer=Answer.예)
    got = _run(s, "일반상품", [yes])
    assert got is not None and got.verdict is Verdict.hold and got.substantiation is not None
    assert got.risk.final is not Risk.R0, "두 갈래를 모두 지나야 닫는다"
    done = _run(s, "일반상품", [yes], [UserSubst(text=SLD, answer=Answer.예)])
    assert done is not None and done.risk.final is Risk.R0


def test_기만에_후기_후보가_함께_서면_후기_실재를_묻는다() -> None:
    t = "이 제품 써 보고 정말 만족했어요"
    hu = [EncoderTypeCandidate(violation=Violation.후기_체험기_기만, confidence=0.8)]
    got = _run(_enc(Premise.일반상품, Violation.소비자_기만, FAIR2, t, hu), "일반상품")
    assert got is not None and got.fact_check is not None
    assert got.fact_check.kind is FactKind.후기_실재
    plain = _run(_enc(Premise.일반상품, Violation.소비자_기만, FAIR2, t), "일반상품")
    assert plain is not None and plain.fact_check is not None
    assert plain.fact_check.kind is FactKind.조건_고지, "후기 후보가 없으면 종전대로"
