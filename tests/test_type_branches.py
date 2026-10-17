"""유형에 딸린 분기 뼈대 — 부당 비교 · 비방 ② · 기만(조건 고지 · 가짜 후기) · 무첨가 (🆕 2026-10-17 · D-348 보충 6 결정 3 · 4 · 보충 7 결정 5 ~ 7).

지키는 것
  ① 문안이 승인되기 전에는 서지 않는다 — `FACT_TEXTS` 가 비면 유형 분기도 없다 · 초안(`FACT_TEXT_DRAFTS` · `NOFREE_CONDITIONS`)은 판정에 쓰지 않는다
  ② 인코더만 잡은 문장 · 그 전제 축의 칸이 B 인 유형만 묻는다 — 「아니오」 → 그 유형으로 확정 위반 · 「해당 없음」 → 걷는다
  ③ 갈래 ① (객관적 근거)이 따로 있는 유형(비방 · 부당 비교)은 사실 갈래가 「예」여도 실증 갈래가 서지 않으면 R0 으로 닫지 않는다
  ④ 갈래 ① 이 없는 유형(기만)은 사실이 전부 「예」면 R0 · 출처
  ⑤ 조합 칸 — 인코더 판정 확정은 「사전 확정」과 가른다
"""

from __future__ import annotations

import pytest

from app import factcheck as fc
from app import graph as g
from app import reasons
from app.contracts import (
    Answer,
    Category,
    EncoderBasis,
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
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

TEXT = "다른 회사 제품은 효과가 없습니다"
FAIR4 = EvidenceArticle(law_id="002011", article="제3조제1항제4호")
FAIR2 = EvidenceArticle(law_id="002011", article="제3조제1항제2호")
FOOD5 = EvidenceArticle(law_id="013094", article="제8조제1항제5호")


def _enc(
    premise: Premise, v: Violation, *arts: EvidenceArticle, text: str = TEXT
) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=g.sent_id(1),
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(
            encoder=Risk.R1,
            final=Risk.R1,
            encoder_basis=[
                EncoderBasis(premise=premise, violation=v, floor=Risk.R1, articles=list(arts))
            ],
        ),
    )


def _run(
    s: SentenceJudgment, cat: str, facts: list[UserFact] | None = None
) -> SentenceJudgment | None:
    state = {
        "text": "앞 문장. " + s.text,
        "sents": ["앞 문장.", s.text],
        "sentences": [s],
        "product": ProductContext(category=Category(cat), facts=facts or []),
    }
    got = g.doc_rules(state).get("sentences") or []
    return got[0] if got else None


@pytest.fixture
def drafts(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 시험에서만 초안을 문안 표에 올린다 — 실제 표는 승인된 줄만 든다(D-263 ②)."""
    monkeypatch.setattr(fc, "FACT_TEXTS", dict(fc.FACT_TEXT_DRAFTS))


def _uf(kind: FactKind, a: Answer, text: str = TEXT) -> UserFact:
    return UserFact(text=text, kind=kind, answer=a)


def test_승인_전에는_유형_분기가_서지_않는다() -> None:
    assert fc.FACT_TEXTS == {}, (
        "🔴 승인 전 문안 표가 채워졌다 — 승인(D-263 ②) 뒤 이 게이트를 고친다"
    )
    assert fc.type_kinds(["비방광고", "부당_비교광고", "소비자_기만"]) == []
    got = _run(_enc(Premise.일반상품, Violation.비방광고, FAIR4), "일반상품")
    assert got is None or got.fact_check is None


def test_초안은_모든_유형_종류를_덮는다() -> None:
    for kinds in fc.TYPE_KINDS.values():
        assert all(k in fc.FACT_TEXT_DRAFTS for k in kinds)
    assert FactKind.후기_실재 in fc.FACT_TEXT_DRAFTS and FactKind.무첨가_조건 in fc.FACT_TEXT_DRAFTS
    assert all(len(c) >= 3 for c in fc.NOFREE_CONDITIONS.values()), (
        "고시 원문 조건(36814 별지 1.아.3)"
    )


def test_일반상품_비방은_선별을_묻는다(drafts: None) -> None:
    got = _run(_enc(Premise.일반상품, Violation.비방광고, FAIR4), "일반상품")
    assert (
        got is not None and got.fact_check is not None and got.fact_check.kind is FactKind.비방_선별
    )
    assert got.verdict is Verdict.hold and got.hold_reason is HoldReason.low_conf, (
        "답 없이 확정하지 않는다"
    )


def test_비방_선별_아니오는_비방_확정_위반(drafts: None) -> None:
    got = _run(
        _enc(Premise.일반상품, Violation.비방광고, FAIR4),
        "일반상품",
        [_uf(FactKind.비방_선별, Answer.아니오)],
    )
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.비방광고] and got.infeasibility is Infeasibility.B


def test_비방_선별_예여도_근거_갈래가_없으면_R0_으로_닫지_않는다(drafts: None) -> None:
    got = _run(
        _enc(Premise.일반상품, Violation.비방광고, FAIR4),
        "일반상품",
        [_uf(FactKind.비방_선별, Answer.예)],
    )
    assert got is not None and got.verdict is Verdict.hold and got.user_facts
    assert got.risk.final is not Risk.R0


def test_기만_조건_고지_예는_R0(drafts: None) -> None:
    got = _run(
        _enc(Premise.식품, Violation.소비자_기만, FOOD5, FAIR2),
        "식품",
        [_uf(FactKind.조건_고지, Answer.예)],
    )
    assert got is not None and got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0 and got.user_facts


def test_해당_없음은_그_갈래를_걷는다(drafts: None) -> None:
    na = _uf(FactKind.조건_고지, Answer.해당없음)
    got = _run(_enc(Premise.식품, Violation.소비자_기만, FOOD5, FAIR2), "식품", [na])
    assert got is None or (got.fact_check is None and got.verdict is Verdict.hold)


def test_식품_비방은_절대형이라_묻지_않는다(drafts: None) -> None:
    food6 = EvidenceArticle(law_id="013094", article="제8조제1항제6호")
    got = _run(_enc(Premise.식품, Violation.비방광고, food6, FAIR4), "식품")
    assert got is not None and got.verdict is Verdict.confirmed and got.fact_check is None
    assert got.infeasibility is Infeasibility.C


def test_조합_칸은_인코더_판정_확정을_가른다() -> None:
    assert reasons.combo_cell(True, (), ("비방광고",), encoder_judged=True) == "인코더 판정 확정"
    assert reasons.combo_cell(True, (), ()) == reasons.COMBO_CELLS[0]
