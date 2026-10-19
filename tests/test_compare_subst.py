"""부당 비교 · 비방의 실증 갈래 ① · 후기 실재 자리 (🆕 2026-10-19 · D-348 보충 28 결정 1 · 2).

지키는 것
  ① 문안은 정본 §18 과 글자가 같다 · 자료 종류는 §13 법 축 줄과 같다 · 식품 · 화장품 축 비방 줄은 없다
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
    }
    for (v, ax), t in rs.TYPE_SUBST_TEXT.items():
        assert t.criteria in sec, (v, ax)
        assert t.evidence == rs.SUBST_TEXT[ax].evidence, "자료 종류는 §13 법 축 줄과 같다"
    assert rs.subst_branch([Violation.비방광고], {"화장품법"}) is None, "화장품 비방은 칸 C"


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
