"""app/premise.py — **품목 전제의 표** (D-319 · D-267 · D-276). 판정 그래프의 분기 노드(`app/graph.py` `premise_branches`)가 읽는다.

★ 표가 넷이다 — 품목 → 전제 · 전제 → 법 묶음 · 전제 → 품목(미검수 판단) · 전제 → 기준 문안.
🔴 **기준 문안은 확정된 줄만 적는다** (D-319 ③ · D-263 ② · D-147). 초안 문안을 여기 옮기지 않는다 — 한 줄이라도 비면
   분기 노드는 분기를 내지 않고 종전대로 돈다(`criteria_ready` · D-220). 승인본은 `docs/ohb/기준문안_초안_2026-10-02.md` §10 이다.
🚨 전제가 유형을 바꾸는 자리(D-319 ④′)는 조문 글자만 대조한 법 해석이다 — 근거는 줄마다 적는다.
"""

from __future__ import annotations

from app.contracts import Category, Premise, ProductContext, Violation

#: 품목 → 그 품목에서 갈리는 전제 (D-276 ① · D-295). 🔴 **품목을 모르면 전부다** (D-229 ⑥ 「분기는 언제나」).
#:    `전용법_미수록` 은 전제가 아니다 — 판정할 법이 없다 (D-277).
PREMISES_OF: dict[Category | None, tuple[Premise, ...]] = {
    None: (
        Premise.식품,
        Premise.일반식품_기능성,
        Premise.건기식_인정,
        Premise.건기식_비인정,
        Premise.화장품,
        Premise.일반상품,
    ),
    Category.식품: (Premise.식품, Premise.일반식품_기능성),
    Category.건기식: (Premise.건기식_인정, Premise.건기식_비인정),
    Category.화장품: (Premise.화장품,),
    Category.일반상품: (Premise.일반상품,),
    Category.전용법_미수록: (),
}

#: 전제 → 법별 노드 이름 (D-319 ④ · D-267 표 · D-271 ④). 표시광고법은 모든 전제에 든다.
PREMISE_LAWS: dict[Premise, tuple[str, ...]] = {
    Premise.식품: ("law_ftc", "law_food"),
    Premise.일반식품_기능성: ("law_ftc", "law_food"),
    Premise.건기식_인정: ("law_ftc", "law_food"),
    Premise.건기식_비인정: ("law_ftc", "law_food"),
    Premise.화장품: ("law_ftc", "law_cosmetic"),
    Premise.일반상품: ("law_ftc",),
}

#: 전제 → 그 전제의 품목. 주된 광고법을 안 본 품목(`UNCOVERED_CATEGORIES`)인지 · 종착 규칙이 이것으로 읽는다 (D-314).
PREMISE_CATEGORY: dict[Premise, Category] = {
    Premise.식품: Category.식품,
    Premise.일반식품_기능성: Category.식품,
    Premise.건기식_인정: Category.건기식,
    Premise.건기식_비인정: Category.건기식,
    Premise.화장품: Category.화장품,
    Premise.일반상품: Category.일반상품,
}

#: D-319 ④′ ① ④ — **건강기능식품 오인(식품표시광고법 제8조① 3호)이 서지 않는 전제.** 3호 본문 「건강기능식품이 **아닌 것을**」 ·
#:    시행령 [별표 1] 3.나(고시한 내용의 표시 · 광고는 제외) · 지시서 ⑫-3 개정(판정기록 10-04).
NO_HF_MISLEAD = frozenset({Premise.건기식_인정, Premise.건기식_비인정, Premise.일반식품_기능성})
HF_MISLEAD = Violation.건강기능식품_오인.value

#: D-319 ④′ ② — `건기식_비인정` 에서 기능성 표방이 서는 자리. 시행령 [별표 1] 4.나 「건강기능식품의 경우 식품의약품안전처장이
#:    인정하지 않은 기능성을 나타내는 내용의 표시ㆍ광고」. 불가 사유는 **자격형**이다(인정을 받으면 풀린다 · D-59 · 지시서 ⑫-3 「A · 4.나」).
UNRECOGNIZED_FUNCTION_CITE = "013094:제8조제1항제4호|나목"

#: D-319 ④′ ③ — `건기식_인정` 에서 질병 표방의 건기식 단서는 [별표 1] 1호 **가목 · 라목**에만 있다. 인용의 목이 나 · 다이면 이 전제에서도
#:    위반이고, 가 · 라이거나 **목을 모르면 판정하지 못한다**(통과로도 위반으로도 내리지 않는다 · D-220).
DISEASE = Violation.질병_예방치료_표방.value
DISEASE_NO_PROVISO_MOK = frozenset({"나", "다"})

#: 전제 → **확정된** 기준 문안 한 줄 (계약 `Branch.criteria` · D-263 ②). 🔴 승인된 줄만 적는다.
#: 🆕 2026-10-10 — 인정 · 요건 충족을 전제로 삼는 전제. 계약의 제품 정보(`ProductContext`)는 품목과 자격 두 칸이고
#:    전제는 그 둘의 짝이다 — 이 표와 `PREMISE_CATEGORY` 가 그 짝을 적는다. ⬜ 화장품에는 자격 있는 전제가 없다(기능성화장품)
RECOGNIZED_PREMISES = frozenset({Premise.건기식_인정, Premise.일반식품_기능성})


def product_of(premise: Premise) -> ProductContext:
    """전제 → 계약의 제품 정보. **전제를 아는 쪽이 제품 정보를 만드는 한 곳이다** — 골든의 `전제` 칸(평가) · 고른 분기(화면).

    🚨 그래프는 지금 `has_recognized_function` 을 읽지 않는다 — 품목의 전제를 전부 계산하고 화면 · 평가가 그 전제의 분기를
       골라 읽는다(D-263 ⑦ · D-276). 자격 칸은 생성 쪽(고쳐 쓰기 서버)이 전제를 알아야 할 때를 위해 같이 채운다.
    """
    return ProductContext(
        category=PREMISE_CATEGORY[premise], has_recognized_function=premise in RECOGNIZED_PREMISES
    )


#: ✅ 2026-10-06 승인 — 오한빈 (모델 권고 승인 · 글자는 모델이 옮겨 적음) · 🔄 같은 날 `일반식품_기능성` 한 줄 재승인(광고의 조건은
#:    「정해진 문구」가 아니라 자율심의다 — 식품표시광고법 제10조 · 시행규칙 제10조 4호 · 원장 10-03 ㊿-40). 정본 글자는 `docs/ohb/기준문안_초안_2026-10-02.md` §10 이고
#:    근거 조문은 그 문서의 §1 · §6 · §8-1 표다. 글자를 고치면 그 문서를 먼저 고치고 다시 승인받는다(D-147 · D-263 ②).
#: 🚨 `건기식_인정` · `일반식품_기능성` 의 「위반으로 보지 않습니다 / 말할 수 있습니다」는 **기준**이지 그 분기의 결과가 아니다 —
#:    문구 대조가 붙기 전에는 두 분기가 통과를 내지 않는다(`app/graph.py` `_premise_sentences` · 원장 10-03 ㊿-34).
CRITERIA: dict[Premise, str] = {
    Premise.식품: (
        "일반식품(건강기능식품이 아닌 식품)이라면 식품표시광고법과 표시광고법 기준으로 봅니다."
    ),
    Premise.일반식품_기능성: (
        "일반식품이지만 기능성 표시 고시의 요건을 모두 채워 정해진 기능성 표시를 한 제품(기능성표시식품)이라면 이 전제입니다. 이런 제품의 광고는 자율심의 대상이고 「본 제품은 건강기능식품이 아닙니다.」가 들어가야 합니다. 이 문구를 적는 것만으로는 이 전제가 아닙니다."
    ),
    Premise.건기식_인정: (
        "이 기능성으로 제품이 인정받은 건강기능식품이라면 인정받은 내용 그대로의 문구는 위반으로 보지 않습니다. 인정 원료가 들어 있다는 것만으로는 이 전제가 아닙니다. 인정받은 내용을 일부 빼거나 바꾼 표현, 질병을 치료한다는 표현, 질병의 증상을 예방 · 치료한다는 표현은 이 전제에서도 위반으로 봅니다."
    ),
    Premise.건기식_비인정: (
        "건강기능식품이지만 이 기능성으로는 인정받지 않았다면 그 기능성을 내세우는 표현은 위반으로 봅니다. 특허 · 수상 · 논문은 인정을 대신하지 않습니다."
    ),
    Premise.화장품: (
        "화장품이라면 화장품법과 표시광고법 기준으로 봅니다. 질병을 예방 · 치료한다는 표현은 의약품으로 잘못 인식할 우려가 있는 광고로 봅니다."
    ),
    Premise.일반상품: (
        "식품 · 화장품이 아닌 상품이라면 표시광고법 기준만 보았습니다. 이 품목에 따로 적용되는 법은 검수하지 않았습니다."
    ),
}


def criteria_ready(premises: tuple[Premise, ...]) -> bool:
    """이 전제들의 기준 문안이 **전부** 확정됐는가. 하나라도 비면 분기를 내지 않는다 — 빈 문안 · 초안 문안으로 응답을 내지 않는다."""
    return all(CRITERIA.get(p) for p in premises)


# 🔴 표가 어긋나면 import 에서 멈춘다 (D-220) — 전제가 늘었는데 한 표만 고치면 그 전제는 법 없이 판정된다.
if set(PREMISE_LAWS) != set(Premise) or set(PREMISE_CATEGORY) != set(Premise):
    raise RuntimeError("🔴 전제 표가 계약 `Premise` 와 어긋났다 (D-276 · D-319)")
if {p for ps in PREMISES_OF.values() for p in ps} != set(Premise) or set(PREMISES_OF) != {
    None,
    *Category,
}:
    raise RuntimeError(
        "🔴 품목 → 전제 표가 계약 `Category` · `Premise` 와 어긋났다 (D-276 · D-319)"
    )
