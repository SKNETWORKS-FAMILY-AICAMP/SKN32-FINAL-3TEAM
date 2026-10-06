"""app/reasons.py — **증명서 사유 문안의 표** (D-320 · D-319 ③′ · D-59). 증명서 조립(`app/graph.py` `_certificate_of`)이 읽는다.

★ 열쇠는 (법, 유형, 사유)다 — **법은 품목이 정한다**(D-319 ④). 같은 유형이라도 식품과 화장품의 글이 다르다.
🔴 **승인된 줄만 적는다** (D-147 · D-263 ②). 정본 글자는 `docs/ohb/기준문안_초안_2026-10-02.md` §9(승인 §10-2)이고 게이트가 글자를 대조한다
   (`tests/test_certificate.py`). 글자를 고치려면 그 문서를 먼저 고치고 다시 승인받는다.
🔴 **열쇠에 없는 조합은 글이 없다 — 증명서를 내지 않는다**(D-320 ② · D-220). 표시광고법 유형은 전부 실증형(B)이라 줄이 없다.
🚨 글은 소수 경우에도 참이 되게 썼다(D-320 ③) — 사유가 문장마다 맞는다는 보장이 없고(원장 10-03 ㊿-36), 표시로 풀리는 금지(D-289)를
   막는 가드가 판정 응답 계약에 없다. 「법이 정한 예외가 아니면」 같은 한정을 지우지 않는다.
⬜ §9 의 4(식품 · 건강기능식품 오인 · 절대형)는 승인하지 않았다 — 범위 대조기 뒤에 다시 쓴다.
"""

from __future__ import annotations

from typing import NamedTuple

from app.contracts import Category, Infeasibility, Violation
from collect.law_map import STATUTE_ID

FOOD = STATUTE_ID["식품표시광고법"]
COSM = STATUTE_ID["화장품법"]

#: 품목 → 그 품목의 전용 광고법. 🔴 미확정 · 일반상품 · 전용법 미수록은 **없다** — 사유 문안을 꺼낼 법이 없다(D-320 ⑤).
LAW_OF_CATEGORY: dict[Category, str] = {
    Category.식품: FOOD,
    Category.건기식: FOOD,
    Category.화장품: COSM,
}


class ReasonText(NamedTuple):
    """사유 문안 한 줄 — 설명과 자격 안내(자격형만)."""

    explanation: str
    guidance: str | None


#: (법, 유형, 사유) → 문안. ✅ 2026-10-06 승인 — 오한빈 (모델 권고 승인 · 글자는 모델이 옮겨 적음) · 일곱 줄
REASON_TEXT: dict[tuple[str, Violation, Infeasibility], ReasonText] = {
    # §9 의 1
    (FOOD, Violation.질병_예방치료_표방, Infeasibility.C): ReasonText(
        "질병을 예방하거나 치료한다는 표현은 법이 정한 예외가 아니면 근거 자료가 있어도 쓸 수 없습니다. 표현을 바꿔도 같은 뜻이면 같은 위반으로 봅니다.",
        None,
    ),
    # §9 의 2
    (FOOD, Violation.의약품_오인, Infeasibility.C): ReasonText(
        "식품을 의약품으로 인식할 우려가 있는 표현은 근거 자료나 자격과 무관하게 쓸 수 없습니다.",
        None,
    ),
    # §9 의 3
    (FOOD, Violation.건강기능식품_오인, Infeasibility.A): ReasonText(
        "건강기능식품이 아닌 제품은 법이 정한 경우가 아니면 기능성이 있는 것으로 표현할 수 없습니다. 표현을 바꿔도 같은 위반이 반복됩니다.",
        "이 기능성에 길이 열려 있을 때의 길은 둘입니다 — 건강기능식품으로 그 기능성을 인정받거나, 일반식품 기능성 표시 고시의 요건을 모두 채워 정해진 표시를 하는 것입니다. 특허 · 수상 · 논문은 어느 쪽도 대신하지 않습니다.",
    ),
    # §9 의 5
    (FOOD, Violation.거짓_과장, Infeasibility.A): ReasonText(
        "건강기능식품이라도 인정받지 않은 기능성은 내세울 수 없습니다.",
        "그 기능성으로 인정을 받으면 인정받은 범위에서 표시할 수 있습니다.",
    ),
    # §9 의 6
    (FOOD, Violation.후기_체험기_기만, Infeasibility.C): ReasonText(
        "체험기 · 감사장을 내세우거나 '주문쇄도' · '단체추천' 같은 표현으로 소비자를 현혹하는 광고는 쓸 수 없습니다. 체험기는 내용이 사실이어도 같습니다.",
        None,
    ),
    # §9 의 7
    (COSM, Violation.의약품_오인, Infeasibility.C): ReasonText(
        "화장품을 의약품으로 잘못 인식할 우려가 있는 표현은 쓸 수 없습니다. 기능성화장품으로 심사받거나 보고한 효능, 지침이 실증 자료로 입증하도록 정한 표현은 여기에 들지 않습니다.",
        None,
    ),
    # §9 의 8
    (COSM, Violation.기능성화장품_오인, Infeasibility.A): ReasonText(
        "기능성화장품이 아닌 제품은 기능성화장품의 효능이 있는 것으로 표현할 수 없고, 기능성화장품이라도 심사받거나 보고한 내용과 다르게 표현할 수 없습니다.",
        "기능성화장품 심사를 받거나 보고를 마치면 그 범위에서 표시할 수 있습니다.",
    ),
}


#: 품목이 맞을 때만 서는 줄. 🔴 「거짓 · 과장 ∧ 자격형」은 건강기능식품의 인정받지 않은 기능성([별표 1] 4.나 · D-319 ④′ ②)뿐이다 —
#:    식품 품목에서 건강기능식품 오인(자격형)과 거짓 · 과장이 한 문장에 함께 서도 이 줄을 꺼내지 않는다.
ONLY_FOR: dict[tuple[str, Violation, Infeasibility], Category] = {
    (FOOD, Violation.거짓_과장, Infeasibility.A): Category.건기식,
}


def lookup(
    category: Category | None, violation: Violation, infeasibility: Infeasibility | None
) -> ReasonText | None:
    """품목 · 유형 · 사유 → 문안. 없으면 **None** — 지어내지 않는다 (D-220)."""
    law = LAW_OF_CATEGORY.get(category) if category is not None else None
    if law is None or infeasibility is None:
        return None
    key = (law, violation, infeasibility)
    if key in ONLY_FOR and ONLY_FOR[key] is not category:
        return None
    return REASON_TEXT.get(key)
