"""불가 사유는 (유형 × 법 축) 칸 · 인코더 쪽 절대형은 답 없이 위반 (🆕 2026-10-17 · D-348 보충 6 결정 1 · 2 · 5 · 6 · 보충 7 결정 10).

지키는 것
  ① 칸 표와 대응표(`collect/statute.references`)가 같은 자리를 덮는다 — 조항 없는 칸에 사유가 없고 조항 있는 칸에 사유가 빠지지 않는다
  ② 조회 — 빈 칸은 사유 모름(None · 보류) · 전용법 칸이 먼저 · 유형들 사이는 더 막힌 쪽 · 비방은 축마다 다르다
  ③ 인코더 근거의 칸은 **그 근거가 선 전제의 법만** 센다 — 식품 전제 근거에 실린 화장품 조항은 세지 않는다
  ④ 인코더만 잡은 문장 — 칸이 C 인 유형은 답 없이 확정 위반(문장 전체 구간 · 대응표 근거 · 제재표 하한 · 사유 C) · 분기 없음 ·
     구간을 못 세우면 보류 그대로 · 섞인 B 유형은 싣지 않는다 · 건기식 인정 전제의 질병은 종전 분기
  ⑤ 사전 확정도 칸으로 사유를 낸다 — 화장품 축 비방 적중은 C(실증 분기 없음)
"""

from __future__ import annotations

import pytest

from app import graph as g
from app.contracts import (
    EncoderBasis,
    EvidenceArticle,
    HoldReason,
    Infeasibility,
    JudgeResponse,
    Outcome,
    Premise,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Verdict,
    Violation,
    encoder_judged,
)
from collect import statute

pytestmark = pytest.mark.gate

F, P, C = "식품표시광고법", "표시광고법", "화장품법"
TEXT = "타사 크림은 피부를 망칩니다"
COSM_SLANDER = EvidenceArticle(law_id="008741", article="[별표 5]제2호카목")
FAIR_SLANDER = EvidenceArticle(law_id="002011", article="제3조제1항제4호")
COSM_DRUG = EvidenceArticle(law_id="002015", article="제13조제1항제1호")
FOOD_FALSE = EvidenceArticle(law_id="013094", article="제8조제1항제4호")


def _enc(*basis: EncoderBasis, text: str = TEXT) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=g.sent_id(1),
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=Risk.R1, encoder_basis=list(basis), final=Risk.R1),
    )


def _b(premise: Premise, v: Violation, floor: Risk, *arts: EvidenceArticle) -> EncoderBasis:
    return EncoderBasis(premise=premise, violation=v, floor=floor, articles=list(arts))


_CAT = {
    Premise.화장품: "화장품",
    Premise.식품: "식품",
    Premise.일반상품: "일반상품",
}


def _run(
    s: SentenceJudgment, *, with_text: bool = True, known: bool = True
) -> SentenceJudgment | None:
    from app.contracts import Category  # noqa: PLC0415

    prem = {b.premise for b in s.risk.encoder_basis}
    cat = Category(_CAT[next(iter(prem))]) if known and len(prem) == 1 else None
    state = {"sentences": [s], "product": ProductContext(category=cat)}
    if with_text:
        state |= {"text": "앞 문장. " + s.text, "sents": ["앞 문장.", s.text]}
    got = g.doc_rules(state).get("sentences") or []
    return got[0] if got else None


def test_칸_표와_대응표가_같은_자리를_덮는다() -> None:
    for v in Violation:
        for law in (F, P, C):
            has_ref = bool(statute.references(v.value, law))
            has_cell = (v, law) in g.INFEASIBILITY_CELL
            assert has_ref == has_cell, f"{v.value} × {law}: 조항 {has_ref} · 칸 {has_cell}"


def test_칸_조회_빈칸_전용법_먼저_더_막힌_쪽() -> None:
    io = g.infeasibility_of
    assert io([]) is None
    assert io([(Violation.질병_예방치료_표방, P)]) is None, (
        "표시광고법 × 질병은 빈 칸 — 판정하지 않는다(보충 6 결정 8)"
    )
    assert io([(Violation.비방광고, P)]) is Infeasibility.B
    assert io([(Violation.비방광고, F)]) is Infeasibility.C
    assert io([(Violation.비방광고, C), (Violation.비방광고, P)]) is Infeasibility.C, (
        "전용법 칸이 먼저"
    )
    assert io([(Violation.거짓_과장, F), (Violation.의약품_오인, F)]) is Infeasibility.C
    assert io([(Violation.거짓_과장, F), (Violation.질병_예방치료_표방, P)]) is None, (
        "칸 없는 유형이 섞이면 모름"
    )
    assert (
        io([(Violation.실증책임_위반, F)]) is None and io([(Violation.추천_보증_뒷광고, F)]) is None
    )


def test_인코더_근거의_칸은_그_전제의_법만_센다() -> None:
    # 품목을 모르면 세 법을 보내 참조 조항이 법마다 실린다 — 식품 전제 근거의 화장품 조항은 세지 않는다
    b = _b(Premise.식품, Violation.비방광고, Risk.R1, COSM_SLANDER, FAIR_SLANDER)
    assert g._basis_cells([b]) == [(Violation.비방광고, P)]
    assert g.infeasibility_of(g._basis_cells([b])) is Infeasibility.B
    c = _b(Premise.화장품, Violation.비방광고, Risk.R2, COSM_SLANDER, FAIR_SLANDER)
    assert g.infeasibility_of(g._basis_cells([c])) is Infeasibility.C


def test_인코더만_화장품_비방은_답_없이_확정_위반() -> None:
    s = _enc(_b(Premise.화장품, Violation.비방광고, Risk.R2, COSM_SLANDER, FAIR_SLANDER))
    got = _run(s)
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.비방광고] and got.infeasibility is Infeasibility.C
    assert got.risk.final is Risk.R2 and got.risk.floor is Risk.R2 and got.risk.encoder is None
    assert [(x.start, x.end) for x in got.spans] == [(6, 6 + len(TEXT))], "문장 전체 · 원문 좌표"
    assert got.substantiation is None and got.fact_check is None, "절대형 — 분기 없음"
    assert not any(e.basis for e in got.evidence) and encoder_judged(got)
    # 종착 — 승인된 증명서 문안(`rs.lookup`)이 있으면 증명서 · 없으면 보류로 내린다(D-320) · 어느 쪽이든 응답 계약을 지난다
    from app.contracts import Category  # noqa: PLC0415

    cert = g._certificate_of([got], Category.화장품)
    if cert is None:
        JudgeResponse(outcome=Outcome.hold, sentences=[got])
    else:
        JudgeResponse(outcome=Outcome.certificate, certificate=cert, sentences=[got])


def test_품목을_모르면_절대형도_확정하지_않는다() -> None:
    """🔄 2026-10-17 (보충 8 결정 1) — 품목을 모르면 전제 자체가 가정이다 · 품목을 고르면 그 품목으로 다시 판정한다."""
    s = _enc(_b(Premise.화장품, Violation.비방광고, Risk.R2, COSM_SLANDER, FAIR_SLANDER))
    assert _run(s, known=False) is None


def test_구간을_못_세우면_보류_그대로_분기도_없다() -> None:
    s = _enc(_b(Premise.화장품, Violation.비방광고, Risk.R2, COSM_SLANDER, FAIR_SLANDER))
    assert _run(s, with_text=False) is None


def test_C_와_B_가_섞이면_C_유형만_위반() -> None:
    s = _enc(
        _b(Premise.화장품, Violation.의약품_오인, Risk.R2, COSM_DRUG),
        _b(
            Premise.화장품,
            Violation.거짓_과장,
            Risk.R1,
            EvidenceArticle(law_id="002015", article="제13조제1항제4호"),
        ),
    )
    got = _run(s)
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.의약품_오인] and got.infeasibility is Infeasibility.C
    assert got.risk.final is Risk.R2


def test_식품_전제_비방은_식품_칸_C_로_위반() -> None:
    food6 = EvidenceArticle(law_id="013094", article="제8조제1항제6호")
    got = _run(_enc(_b(Premise.식품, Violation.비방광고, Risk.R1, food6, FAIR_SLANDER)))
    assert (
        got is not None
        and got.verdict is Verdict.confirmed
        and got.infeasibility is Infeasibility.C
    )


def test_일반상품_전제_비방은_B_라_답_없이_확정하지_않는다() -> None:
    got = _run(_enc(_b(Premise.일반상품, Violation.비방광고, Risk.R1, FAIR_SLANDER)))
    assert got is None or got.verdict is Verdict.hold


def test_B_유형만이면_종전대로_확정하지_않는다() -> None:
    got = _run(_enc(_b(Premise.식품, Violation.거짓_과장, Risk.R1, FOOD_FALSE)))
    assert got is None or got.verdict is Verdict.hold


def test_사유_모음은_더_막힌_쪽() -> None:
    s = _enc(
        _b(Premise.화장품, Violation.비방광고, Risk.R2, COSM_SLANDER, FAIR_SLANDER),
        _b(
            Premise.화장품,
            Violation.거짓_과장,
            Risk.R1,
            EvidenceArticle(law_id="002015", article="제13조제1항제4호"),
        ),
    )
    assert g._encoder_reason(s) is Infeasibility.C


# ── 기록 = 분기의 가장 나쁜 경우 이상 (🆕 2026-10-17 · D-263 ① · D-319 ① · 원장 10-17(B) ④) ──────────────


def _branch(premise: Premise, sents: list[SentenceJudgment]):  # noqa: ANN202
    from app.contracts import Branch  # noqa: PLC0415

    return Branch(
        premise=premise,
        outcome=g._branch_outcome(premise, sents),
        sentences=sents,
        criteria="(시험) 기준",
    )


def _doc(
    rec: SentenceJudgment, per: dict[Premise, SentenceJudgment], category: str | None = None
) -> tuple[SentenceJudgment, list]:
    from app.contracts import Category  # noqa: PLC0415

    state = {
        "text": "앞 문장. " + rec.text,
        "sents": ["앞 문장.", rec.text],
        "sentences": [rec],
        "branches": [_branch(p, [s]) for p, s in per.items()],
        "product": ProductContext(category=Category(category) if category else None),
    }
    out = g.doc_rules(state)
    got = (out.get("sentences") or [rec])[0]
    return got, out.get("branches") or state["branches"]


def test_품목을_모르면_분기는_보류_기록은_품목_선택_필요() -> None:
    """🔄 2026-10-17 (보충 8 결정 1) — 화장품 가정에서만 절대형이 서는 문장: 분기 확정 없음 · 기록 `cat_unknown`(등급이 전제마다 갈린다 · D-229)."""
    drug = _b(Premise.화장품, Violation.의약품_오인, Risk.R2, COSM_DRUG)
    false_ = _b(Premise.식품, Violation.거짓_과장, Risk.R1, FOOD_FALSE)
    got, bs = _doc(_enc(drug, false_), {Premise.화장품: _enc(drug), Premise.식품: _enc(false_)})
    cosm = next(b for b in bs if b.premise is Premise.화장품).sentences[0]
    assert cosm.verdict is Verdict.hold, "품목을 모르면 확정하지 않는다"
    assert got.verdict is Verdict.hold and got.hold_reason is HoldReason.cat_unknown
    assert got.risk.final is Risk.R1, "인코더 R1 층 그대로 — 화장품 가정이 기록을 올리지 않는다"
    JudgeResponse(outcome=Outcome.hold, sentences=[got], branches=bs)


def test_품목을_알고_전제가_둘이면_분기가_모두_같은_절대형일_때_기록도_확정() -> None:
    """건기식 품목(인정 · 비인정 두 전제) — 두 분기가 같은 절대형으로 확정되면 기록도 확정(D-319 ① · `_record_at_least`)."""
    food2 = EvidenceArticle(law_id="013094", article="제8조제1항제2호")
    a = _b(Premise.건기식_인정, Violation.의약품_오인, Risk.R2, food2)
    b = _b(Premise.건기식_비인정, Violation.의약품_오인, Risk.R2, food2)
    got, bs = _doc(
        _enc(a, b), {Premise.건기식_인정: _enc(a), Premise.건기식_비인정: _enc(b)}, "건기식"
    )
    assert all(x.sentences[0].verdict is Verdict.confirmed for x in bs)
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.의약품_오인]
    assert got.risk.final is Risk.R2
    JudgeResponse(outcome=Outcome.hold, sentences=[got], branches=bs)


# ── 식품 · 화장품 비방은 낱말로 가른다 (🆕 2026-10-17 · D-348 보충 10) ─────────────────────────────


@pytest.mark.parametrize(
    ("text", "absolute"),
    [
        (
            "다른 우유와 달리 이 우유는 첨가물을 넣지 않습니다",
            True,
        ),  # 고시 69549 제2조 4.가 예시 꼴
        ("타사제품은 불쾌감과 악취가 나는 반면에 저희 제품은 산뜻합니다", True),
        ("타사 크림은 피부를 망칩니다", True),
        ("타사 제품보다 2배 빠른 흡수", False),  # 자사 우월 비교 — 부당 비교
        ("국내 최초 무항생제 인증 목장원유", False),  # 우월 주장 — 고시 4.나
        ("동종 제품 중 면역기능 증진 1위", False),
    ],
)
def test_비방_낱말_규칙(text: str, absolute: bool) -> None:
    from app import factcheck  # noqa: PLC0415

    assert factcheck.slander_absolute(text) is absolute


def test_식품_비방_칸은_문장으로_가른다() -> None:
    io = g.infeasibility_of
    assert io([(Violation.비방광고, F)], "타사 제품은 효과가 없습니다") is Infeasibility.C
    assert io([(Violation.비방광고, F)], "국내 최초로 개발한 제품") is Infeasibility.B
    assert io([(Violation.비방광고, C)], "타사 제품보다 보습력이 2배") is Infeasibility.B
    assert io([(Violation.비방광고, F)]) is Infeasibility.C, "문장을 모르면 칸 그대로"
    assert io([(Violation.비방광고, P)], "국내 최초") is Infeasibility.B, "표시광고법 축은 원래 B"


def test_타사를_깎아내리지_않는_식품_비방은_답_없이_확정하지_않는다() -> None:
    food6 = EvidenceArticle(law_id="013094", article="제8조제1항제6호")
    s = _enc(
        _b(Premise.식품, Violation.비방광고, Risk.R1, food6, FAIR_SLANDER),
        text="시중에서 판매되는 타제품보다 높은 함유율",
    )
    got = _run(s)
    assert got is None or got.verdict is Verdict.hold, "원장 10-17(B) ⑤ 의 꼴 — 부당 비교(B)로 본다"


# ── 측정 전용 사전 판 (🆕 2026-10-18 · D-348 보충 15 결정 3) ─────────────────────────────────────


def test_사전_판_c_only_는_C_항목만_남기고_자격_없는_항목을_뺀다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import dictmatch as dm  # noqa: PLC0415

    disease = dm.Entry(
        term="암 치료", violation_type="질병_예방치료_표방", basis=("013094:제8조제1항제1호",)
    )
    exag = dm.Entry(term="최고급", violation_type="거짓_과장", basis=("013094:제8조제1항제4호",))
    assert g.entry_cell(disease) is Infeasibility.C and g.entry_cell(exag) is Infeasibility.B
    # 🔄 2026-10-18 (D-348 보충 16) — 기본은 칸 C 만 단독판정 · 나머지 단독판정 항목은 내린 후보
    assert g._viewed([disease, exag], [exag]) == ([disease], [exag], [exag])
    monkeypatch.setattr(g, "_DICT_VIEW", None)
    try:
        g.set_dict_view("c_only")
        assert g._viewed([disease, exag], [exag]) == ([disease], [], [])
        g.set_dict_view("legacy")
        assert g._viewed([disease, exag], [exag]) == ([disease, exag], [exag], []), "종전 사전"
    finally:
        monkeypatch.setattr(g, "_DICT_VIEW", None)
    with pytest.raises(ValueError):
        g.set_dict_view("모르는 판")
