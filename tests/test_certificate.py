"""증명서 조립 — 승인된 사유 문안으로만 낸다 (🆕 2026-10-06 · D-320 · D-59 · D-125 · D-319 ③′).

지키는 것
  ① 문안 표(`app/reasons.py`)는 승인본(`docs/ohb/기준문안_초안_2026-10-02.md` §9 · §10-2)과 글자가 같다 — 일곱 줄 (D-99 · D-147)
  ② 열쇠는 (품목의 법, 유형, 사유)다 — 같은 유형이라도 식품과 화장품의 글이 다르다 (D-320 ①)
  ③ 문안이 없는 조합 · 품목 미확정은 **증명서를 내지 않는다** — 보류다 (D-320 ② ⑤ · D-220)
  ④ 증명서의 사유는 가장 막힌 사유이고, 자격 안내는 자격형 증명서에만 싣는다 (D-61 🚨)
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app import reasons as rs
from app.contracts import (
    Category,
    EvidenceArticle,
    Infeasibility,
    Outcome,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Verdict,
    Violation,
)
from app.graph import _certificate_of, certificate, to_response

pytestmark = pytest.mark.gate

DOC = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md")
법 = EvidenceArticle(law_id="013094", article="제8조", item="제1항제1호", quote="조문")


def _s(sid: str, infeas: Infeasibility, *violations: Violation) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=sid,
        text="문구",
        verdict=Verdict.confirmed,
        violations=list(violations),
        evidence=[법],
        infeasibility=infeas,
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
    )


def _doc_rows() -> dict[str, tuple[str, str | None]]:
    text = DOC.read_text(encoding="utf-8")
    sec = text[text.index("## 9. ") : text.index("### 9-1.")]
    rows = {}
    for line in sec.splitlines():
        if re.match(r"\| \d \|", line):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            rows[c[0]] = (c[4], None if c[5] == "—" else c[5])
    return rows


def test_문안_표는_승인본과_글자가_같다() -> None:
    rows = _doc_rows()
    approved = [rows[n] for n in ("1", "2", "3", "5", "6", "7", "8")]
    got = [(t.explanation, t.guidance) for t in rs.REASON_TEXT.values()]
    assert got == approved, (
        "🚨 사유 문안이 승인본(§9 의 1 · 2 · 3 · 5 · 6 · 7 · 8)과 다르다 — 문서를 먼저 고치고 다시 승인받는다 (D-147 · D-263 ②)"
    )
    assert rows["4"][0] not in {t.explanation for t in rs.REASON_TEXT.values()}, (
        "§9 의 4 는 승인하지 않았다 — 범위 대조기 뒤에 다시 쓴다 (D-320 ④′)"
    )
    for t in rs.REASON_TEXT.values():
        for s in (t.explanation, t.guidance or ""):
            assert "적법" not in s and "안전" not in s and "초안" not in s, s
    assert all(i is not Infeasibility.B for _, _, i in rs.REASON_TEXT), (
        "실증형에는 증명서 문안이 없다 — 검수에서는 지시다 (D-59 · D-268)"
    )


def test_같은_유형도_품목의_법에_따라_글이_다르다() -> None:
    food = rs.lookup(Category.식품, Violation.의약품_오인, Infeasibility.C)
    cos = rs.lookup(Category.화장품, Violation.의약품_오인, Infeasibility.C)
    assert food and cos and food.explanation != cos.explanation, (
        "식품과 화장품의 의약품 오인이 같은 글이다 (D-320 ①)"
    )
    assert rs.lookup(Category.화장품, Violation.후기_체험기_기만, Infeasibility.C) is None, (
        "🚨 체험기 금지는 식품표시광고법 [별표 1] 5.다 다 — 화장품 품목에 그 글을 내면 안 된다"
    )
    for cat in (None, Category.일반상품, Category.전용법_미수록):
        assert rs.lookup(cat, Violation.질병_예방치료_표방, Infeasibility.C) is None, (
            f"{cat} — 꺼낼 법이 없는데 글이 나왔다 (D-320 ⑤)"
        )


def test_인정받지_않은_기능성_줄은_건강기능식품_품목에서만_선다() -> None:
    assert rs.lookup(Category.건기식, Violation.거짓_과장, Infeasibility.A) is not None
    assert rs.lookup(Category.식품, Violation.거짓_과장, Infeasibility.A) is None, (
        "🚨 식품 품목의 문장에 「건강기능식품이라도 …」가 나간다 — 4.나 는 건강기능식품의 줄이다 (D-319 ④′ ②)"
    )


def test_절대형_증명서가_조립되고_응답이_계약을_지난다() -> None:
    sents = [_s("s0", Infeasibility.C, Violation.질병_예방치료_표방)]
    out = certificate({"sentences": sents, "product": ProductContext(category=Category.식품)})  # type: ignore[typeddict-item]
    assert out["outcome"] is Outcome.certificate
    cert = out["certificate"]
    want = rs.REASON_TEXT[(rs.FOOD, Violation.질병_예방치료_표방, Infeasibility.C)]
    assert cert.reason is Infeasibility.C and cert.explanation == want.explanation
    assert cert.guidance is None, "절대형 증명서에 자격 안내가 붙었다 (D-61 🚨)"
    r = to_response(
        {
            "sentences": sents,
            "product": ProductContext(category=Category.식품),
            "outcome": out["outcome"],
            "certificate": cert,
        }  # type: ignore[typeddict-item]
    )
    assert r.outcome is Outcome.certificate and r.certificate == cert


def test_자격형_증명서에는_자격_안내가_실린다() -> None:
    cert = _certificate_of([_s("s0", Infeasibility.A, Violation.건강기능식품_오인)], Category.식품)
    assert cert is not None and cert.reason is Infeasibility.A and cert.guidance, (
        "자격형인데 자격을 얻는 길이 없다 (D-59)"
    )


def test_사유가_섞이면_가장_막힌_사유로_내고_자격_안내는_싣지_않는다() -> None:
    cert = _certificate_of(
        [
            _s("s0", Infeasibility.A, Violation.건강기능식품_오인),
            _s("s1", Infeasibility.C, Violation.질병_예방치료_표방),
            _s("s2", Infeasibility.C, Violation.질병_예방치료_표방),
        ],
        Category.식품,
    )
    assert cert is not None and cert.reason is Infeasibility.C
    want = rs.REASON_TEXT[(rs.FOOD, Violation.질병_예방치료_표방, Infeasibility.C)]
    assert cert.explanation == want.explanation, "같은 글이 문장 수만큼 겹쳐 실렸다"
    assert cert.guidance is None


def test_문안이_없으면_증명서를_내지_않고_보류다() -> None:
    cases = [
        ([_s("s0", Infeasibility.C, Violation.질병_예방치료_표방)], None),
        ([_s("s0", Infeasibility.A, Violation.기능성화장품_오인)], Category.식품),
        ([_s("s0", Infeasibility.C, Violation.거짓_과장)], Category.식품),
        (
            [
                _s("s0", Infeasibility.C, Violation.질병_예방치료_표방),
                _s("s1", Infeasibility.A, Violation.기능성화장품_오인),
            ],
            Category.식품,
        ),
    ]
    for sents, cat in cases:
        out = certificate({"sentences": sents, "product": ProductContext(category=cat)})  # type: ignore[typeddict-item]
        assert out["outcome"] is Outcome.hold and "certificate" not in out, (
            f"🚨 {cat} — 문안이 없는 조합인데 증명서를 냈다. 일부만 설명하는 증명서 · 지어낸 글을 내지 않는다 (D-220)"
        )
    assert _certificate_of([_s("s0", Infeasibility.B, Violation.거짓_과장)], Category.식품) is None
