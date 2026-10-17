"""유형에 딸린 분기 뼈대 — 부당 비교 · 비방 ② · 기만(조건 고지 · 가짜 후기) · 무첨가 (🆕 2026-10-17 · D-348 보충 6 결정 3 · 4 · 보충 7 결정 5 ~ 7).

지키는 것
  ① 문안은 승인본(`docs/ohb/기준문안_초안_2026-10-02.md` §14)과 글자가 같다 — 🔄 2026-10-17 승인(종전 「승인 전에는 서지 않는다」)
  ② 인코더만 잡은 문장 · 그 전제 축의 칸이 B 인 유형만 묻는다 — 「아니오」 → 그 유형으로 확정 위반 · 「해당 없음」 → 걷는다
  ③ 갈래 ① (객관적 근거)이 따로 있는 유형(비방 · 부당 비교)은 사실 갈래가 「예」여도 실증 갈래가 서지 않으면 R0 으로 닫지 않는다
  ④ 갈래 ① 이 없는 유형(기만)은 사실이 전부 「예」면 R0 · 출처
  ⑤ 조합 칸 — 인코더 판정 확정은 「사전 확정」과 가른다
"""

from __future__ import annotations

import pathlib

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


def _uf(kind: FactKind, a: Answer, text: str = TEXT) -> UserFact:
    return UserFact(text=text, kind=kind, answer=a)


DOC = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md")


def _sec14() -> str:
    text = DOC.read_text(encoding="utf-8")
    return text[text.index("## 14. ") :]


def test_문안은_승인본과_글자가_같다() -> None:
    """🔄 2026-10-17 — 질문 · 기준 문안 · 증빙 · 화면 안내는 정본 §14 와 글자가 같다 (D-99 · D-147 · D-263 ②)."""
    sec = _sec14()
    assert set(fc.FACT_QUESTIONS) == set(fc.FACT_TEXTS)
    for k, q in fc.FACT_QUESTIONS.items():
        assert f"질문: {q}" in sec, k
        t = fc.FACT_TEXTS[k]
        assert f"기준: {t.criteria}" in sec, k
        assert f"증빙: {' · '.join(t.accepted_evidence)}" in sec, k
    for line in (
        reasons.GENERAL_GOODS_RISK_NOTE,
        reasons.GENERAL_GOODS_UNJUDGEABLE,
        reasons.SLANDER_HOLD_NOTE,
        reasons.FACT_FALSE_TODO,
        reasons.ENCODER_QUESTION_TEXT,
    ):
        assert f": {line}" in sec, line


def test_유형_종류는_모두_문안이_있다() -> None:
    for kinds in fc.TYPE_KINDS.values():
        assert all(k in fc.FACT_TEXTS for k in kinds)
    assert FactKind.후기_실재 in fc.FACT_TEXTS and FactKind.무첨가_조건 in fc.FACT_TEXTS
    assert all(len(c) >= 3 for c in fc.NOFREE_CONDITIONS.values()), (
        "고시 원문 조건(36814 별지 1.아.3)"
    )


def test_일반상품_비방은_선별을_묻는다() -> None:
    got = _run(_enc(Premise.일반상품, Violation.비방광고, FAIR4), "일반상품")
    assert (
        got is not None and got.fact_check is not None and got.fact_check.kind is FactKind.비방_선별
    )
    assert got.verdict is Verdict.hold and got.hold_reason is HoldReason.low_conf, (
        "답 없이 확정하지 않는다"
    )


def test_비방_선별_아니오는_비방_확정_위반() -> None:
    got = _run(
        _enc(Premise.일반상품, Violation.비방광고, FAIR4),
        "일반상품",
        [_uf(FactKind.비방_선별, Answer.아니오)],
    )
    assert got is not None and got.verdict is Verdict.confirmed
    assert got.violations == [Violation.비방광고] and got.infeasibility is Infeasibility.B


def test_비방_선별_예여도_근거_갈래가_없으면_R0_으로_닫지_않는다() -> None:
    got = _run(
        _enc(Premise.일반상품, Violation.비방광고, FAIR4),
        "일반상품",
        [_uf(FactKind.비방_선별, Answer.예)],
    )
    assert got is not None and got.verdict is Verdict.hold and got.user_facts
    assert got.risk.final is not Risk.R0


def test_기만_조건_고지_예는_R0() -> None:
    got = _run(
        _enc(Premise.일반상품, Violation.소비자_기만, FAIR2),
        "일반상품",
        [_uf(FactKind.조건_고지, Answer.예)],
    )
    assert got is not None and got.verdict is Verdict.confirmed and not got.violations
    assert got.risk.final is Risk.R0 and got.user_facts


def test_해당_없음은_그_갈래를_걷는다() -> None:
    na = _uf(FactKind.조건_고지, Answer.해당없음)
    got = _run(_enc(Premise.일반상품, Violation.소비자_기만, FAIR2), "일반상품", [na])
    assert got is None or (got.fact_check is None and got.verdict is Verdict.hold)


def test_식품_비방은_절대형이라_묻지_않는다() -> None:
    food6 = EvidenceArticle(law_id="013094", article="제8조제1항제6호")
    got = _run(_enc(Premise.식품, Violation.비방광고, food6, FAIR4), "식품")
    assert got is not None and got.verdict is Verdict.confirmed and got.fact_check is None
    assert got.infeasibility is Infeasibility.C


def test_조합_칸은_인코더_판정_확정을_가른다() -> None:
    assert reasons.combo_cell(True, (), ("비방광고",), encoder_judged=True) == "인코더 판정 확정"
    assert reasons.combo_cell(True, (), ()) == reasons.COMBO_CELLS[0]


# ── 일반상품 안내 (🆕 2026-10-17 · D-348 보충 6 결정 8 · 문안 초안) ─────────────────────────────


def test_일반상품_안내_두_줄() -> None:
    from app.contracts import EncoderTypeCandidate  # noqa: PLC0415

    s = _enc(Premise.일반상품, Violation.비방광고, FAIR4)
    assert reasons.general_goods_notes(s, "일반상품") == [reasons.GENERAL_GOODS_RISK_NOTE]
    assert reasons.general_goods_notes(s, "식품") == [], "일반상품이 아니면 안내 없음"
    q = SentenceJudgment(
        sent_id="s0",
        text="관절염이 낫습니다",
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=[
            EncoderTypeCandidate(violation=Violation.질병_예방치료_표방, confidence=0.9)
        ],
    )
    assert reasons.general_goods_notes(q, "일반상품") == [reasons.GENERAL_GOODS_UNJUDGEABLE], (
        "표시광고법에 질병 호가 없다 — 판정하지 않고 전용법 확인 안내(위험도가 없으면 ① 은 없다)"
    )


def test_검수_화면_틀이_안내_줄과_함께_읽힌다() -> None:
    from app.templating import templates  # noqa: PLC0415

    templates.env.get_template("user/review.html")


def test_질문은_사실_하나_표에_없으면_공통_질문() -> None:
    """질문은 종류마다 한 줄 · 설명은 기준 문안 칸 · 표에 없는 종류는 종전 공통 질문."""
    assert fc.fact_question(FactKind.비방_선별) == (
        "같은 광고에 경쟁 제품의 장점이나 비교 조건도 함께 밝혔나요?"
    )
    assert fc.fact_question(FactKind.인증) == fc.FALLBACK_QUESTION
    for q in fc.FACT_QUESTIONS.values():
        assert q.count("?") == 1 and "요" in q, "질문 하나"


# ── 묻지 않는 비방 후보 (🆕 2026-10-17 · D-348 보충 11) ─────────────────────────────────────────

FOOD6 = EvidenceArticle(law_id="013094", article="제8조제1항제6호")


@pytest.mark.parametrize(
    ("text", "claim"),
    [
        ("국내 판매 NO.1", True),
        ("타사 제품보다 2배", True),
        ("대한민국 처음으로 ooo런칭", True),
        ("The Only 오직 oo에만", True),
        ("시장 점유율 1위를 지켰다", True),
        ("아기전문회사", False),
        ("지금까지 ○○ 음료는 오히려 우리 몸의 수분을 빼앗아 갔다", False),
        ("한우 1등급", False),
        ("비교적 순한 맛", False),
    ],
)
def test_비교_우월_표지(text: str, claim: bool) -> None:
    assert fc.comparison_claim(text) is claim


def test_식품_비방_비교_표지가_있으면_비교_기준을_묻는다() -> None:
    got = _run(_enc(Premise.식품, Violation.비방광고, FOOD6, text="국내 판매 NO.1"), "식품")
    assert got is not None and got.fact_check is not None
    assert got.fact_check.kind is FactKind.비교_기준
    assert got.verdict is Verdict.hold, "답 없이 확정하지 않는다"
    assert reasons.slander_note(got) == "", "질문이 선 문장에는 기준 줄을 달지 않는다"


def test_식품_비방_표지가_없으면_묻지_않고_기준_한_줄() -> None:
    text = "지금까지 ○○ 음료는 오히려 우리 몸의 수분을 빼앗아 갔다"
    s = _enc(Premise.식품, Violation.비방광고, FOOD6, text=text)
    got = _run(s, "식품")
    assert got is None or (got.fact_check is None and got.verdict is Verdict.hold), (
        "맞지 않는 질문을 띄우지 않는다 — 보류 그대로"
    )
    assert reasons.slander_note(got or s) == reasons.SLANDER_HOLD_NOTE


def test_기준_한_줄은_식품_화장품_축의_보류_비방만() -> None:
    text = "아기전문회사"
    assert (
        reasons.slander_note(_enc(Premise.일반상품, Violation.비방광고, FAIR4, text=text)) == ""
    ), "표시광고법 축의 비방은 C 가 아니다 — 「비방이에요」라고 말하지 않는다"
    assert reasons.slander_note(_enc(Premise.식품, Violation.거짓_과장, FOOD6, text=text)) == ""
    s = _enc(Premise.식품, Violation.비방광고, FOOD6, text="타사 제품은 해롭습니다")
    assert reasons.slander_note(s) == "", "타사 ∧ 부정은 C 확정 길이다"


# ── 조건 고지는 표시광고법 축의 기만에만 (🆕 2026-10-17 · D-348 보충 13) ─────────────────────────


def test_식품_기만에는_조건_고지를_묻지_않는다() -> None:
    """식품 [별표 1] 5(가 ~ 카)에 은폐 · 축소 목이 없다 — 식품 축 근거가 있으면 묻지 않고, 「예」로 R0 이 되지도 않는다."""
    s = _enc(Premise.식품, Violation.소비자_기만, FOOD5, FAIR2, text="설탕 0%")
    got = _run(s, "식품")
    assert got is None or (got.fact_check is None and got.verdict is Verdict.hold)
    got = _run(s, "식품", [_uf(FactKind.조건_고지, Answer.예, text="설탕 0%")])
    assert got is None or (got.verdict is Verdict.hold and got.risk.final is not Risk.R0), (
        "묻지 않은 질문의 답으로 닫지 않는다"
    )


def test_일반상품_기만에는_조건_고지를_묻는다() -> None:
    got = _run(_enc(Premise.일반상품, Violation.소비자_기만, FAIR2), "일반상품")
    assert got is not None and got.fact_check is not None
    assert got.fact_check.kind is FactKind.조건_고지


# ── 무첨가 조건 (🆕 2026-10-17 · D-348 보충 14) ──────────────────────────────────────────────────

FOOD7 = EvidenceArticle(law_id="013094", article="제8조제1항제7호")


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("설탕 무첨가 오렌지주스", ["설탕 무첨가"]),
        ("무가당이라 좋아요", ["설탕 무첨가"]),
        ("나트륨무첨가", ["나트륨 무첨가"]),
        ("무가염 버터", ["나트륨 무첨가"]),
        ("무설탕 캔디", []),
        ("인공색소를 사용하지 않았습니다", []),
    ],
)
def test_무첨가_표현은_조건표에_있는_것만(text: str, names: list[str]) -> None:
    assert [n for n, _ in fc.nofree_conditions(text)] == names


def test_식품_비교의_무첨가_표현은_무첨가_조건을_묻는다() -> None:
    s = _enc(Premise.식품, Violation.부당_비교광고, FOOD7, text="설탕 무첨가 오렌지주스")
    got = _run(s, "식품")
    assert got is not None and got.fact_check is not None
    assert got.fact_check.kind is FactKind.무첨가_조건
    no = _run(s, "식품", [_uf(FactKind.무첨가_조건, Answer.아니오, text="설탕 무첨가 오렌지주스")])
    assert no is not None and no.verdict is Verdict.confirmed
    assert no.violations == [Violation.부당_비교광고], "조건을 지키지 않은 무첨가는 7.나 부당 비교"


def test_조건표에_없는_무첨가는_비교_기준_그대로() -> None:
    s = _enc(Premise.식품, Violation.부당_비교광고, FOOD7, text="인공색소를 사용하지 않았습니다")
    got = _run(s, "식품")
    assert got is not None and got.fact_check is not None
    assert got.fact_check.kind is FactKind.비교_기준


def test_무첨가_조건_목록이_화면에_펼쳐진다() -> None:
    """화면은 질문의 「아래 조건」을 필터(`nofree_conditions`)로 펼친다 — 필터 등록 · 틀의 사용 자리 · 펼친 글자."""
    import pathlib as _p  # noqa: PLC0415

    from app.templating import templates  # noqa: PLC0415

    assert templates.env.filters["nofree_conditions"] is fc.nofree_conditions
    src = _p.Path("app/templates/user/review.html").read_text(encoding="utf-8")
    assert "s.text|nofree_conditions" in src and '"무첨가_조건"' in src
    html = templates.env.from_string(
        "{% for name, conds in t|nofree_conditions %}「{{ name }}」 조건"
        "{% for c in conds %}<li>{{ c }}</li>{% endfor %}{% endfor %}"
    ).render(t="설탕 무첨가 오렌지주스")
    assert "「설탕 무첨가」 조건" in html
    assert fc.NOFREE_CONDITIONS[("설탕 무첨가", "무가당")][0] in html
