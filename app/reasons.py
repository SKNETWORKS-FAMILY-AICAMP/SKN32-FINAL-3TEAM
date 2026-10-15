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

from app import premise as pm
from app.contracts import Category, Infeasibility, Risk, SubstBranch, Violation
from collect import statute
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


#: 🆕 2026-10-11 — **보류 문장의 유형 후보가 조건부일 때** 붙이는 말 (D-319 보충 10-11 · D-326).
#:    건강기능식품 제품의 `거짓_과장` 후보 중에는 시행령 [별표 1] 4.나(인정하지 않은 기능성)에서 온 것이 있다 — 그 후보는
#:    「그 기능성으로 인정받지 않았다면」의 것이다. **조문이 조건을 말한다** — 새 칸을 두지 않고 문장의 인용 근거에 4.나가
#:    있는지로 가른다(D-282 「정본은 조문 인용」 · 인코더 후보는 조문이 없어 `moved_from` 칸으로 말한다).
#: ✅ 2026-10-11 승인 — 오한빈 (모델 권고 승인 · 글자는 모델이 옮겨 적음). 정본 글자는 `docs/ohb/기준문안_초안_2026-10-02.md` §11 이고
#:    게이트(`tests/test_premise_branches.py`)가 글자를 대조한다. 고치려면 그 문서를 먼저 고치고 다시 승인받는다 (D-147 · D-263 ②)
UNRECOGNIZED_CANDIDATE_NOTE = "이 후보는 이 기능성으로 인정받지 않은 건강기능식품일 때 해당합니다. 인정받은 기능성이라면 해당하지 않습니다."
_UNRECOGNIZED = statute.article_item(pm.UNRECOGNIZED_FUNCTION_CITE)


def candidate_condition(sentence: object) -> str | None:
    """보류 문장의 유형 후보에 붙일 조건 문안. 붙일 것이 없으면 **None** — 지어내지 않는다 (D-220).

    ★ 확신 부족 보류 문장이고 **인용 근거**(`EvidenceArticle.basis`)에 [별표 1] 4.나가 있을 때만 낸다.
    ⛔ 확정 문장에는 내지 않는다 — 확정의 조건은 불가 사유(자격형)와 증명서 사유 문안이 말한다(`REASON_TEXT`).
    ⛔ 참고 조문(검색이 찾은 조문)에 4.나가 있는 것으로는 내지 않는다 — 판정이 기댄 조문이 아니다.
    🚨 근거는 문장 단위다 — 한 문장에 조건 없는 `거짓_과장` 낱말이 함께 걸려도 이 말이 붙는다. 그래서 「이 후보는」이
       가리키는 것은 4.나 근거이고, 화면은 이 말을 근거 옆에 그린다.
    """
    verdict = getattr(getattr(sentence, "verdict", None), "value", None)
    reason = getattr(getattr(sentence, "hold_reason", None), "value", None)
    if (verdict, reason) != ("hold", "low_conf"):
        return None
    for e in getattr(sentence, "evidence", None) or ():
        if getattr(e, "basis", False) is True and (e.law_id, e.article, e.item) == _UNRECOGNIZED:
            return UNRECOGNIZED_CANDIDATE_NOTE
    return None


# ── 인코더 추정 유형 (🆕 2026-10-14 · D-330 보충 2 · D-323 보충) ─────────────────────────────
#: 사전 유형이 없는 문장에 인코더 유형 후보가 있으면 **접힌 칸 밖에** 다는 한 줄. 유형 이름 · 확률은 싣지 않는다 (D-330 결정 3)
#: 🚨 문안은 화면 담당(ksr) 검토 대상이다(D-330 ⬜ 검토 A ~ H) — 고치면 여기 한 곳을 고친다 (D-99)
GUESSED_TYPE_MARK = "AI 추정 유형 있음 — 판정 아님"
#: 고쳐 쓰기에 생성 서버(sLLM)가 「고칠 수 없음」(`infeasible`)으로 답했을 때의 말 — **유형의 출처와 무관하게 이 말 하나다**.
#: ⛔ 「합법화 불가」라 그리지 않는다 — 불가는 코드의 불가 사유(D-59 · `INFEASIBILITY_OF`)만 말한다(D-10 · D-323 보충 개정 10-14).
#:    코드가 「실증하면 쓸 수 있다」(B)로 정한 문장 70 중 13 에 sLLM 이 불가로 답했다 — 같은 카드에서 말이 갈린다
#:    (`docs/lse/고쳐쓰기_dev평가_2026-10-11.md` §1 · 3B v12 · 정답 유형 입력). 사유 C 문장은 카드가 이미 「불가」를 말한다
REWRITE_INFEASIBLE_TEXT = "고쳐 쓴 문장을 만들지 못했어요"
#: 고친 문장을 다시 판정했을 때 사전은 지났는데 인코더가 유형 후보를 내면 다는 말 (D-323 결정 4 「위반 못 찾음 + 인코더 주의」)
ENC_REMAINS_MARK = "AI 추정 유형 남음 — 판정 아님"


def guessed_types(sentence: object) -> list[str]:
    """사전 유형(`violations`)이 없고 **인코더 유형 후보만** 있는 문장의 추정 유형 이름(정렬). 아니면 빈 목록.

    ★ 화면의 겉 표지 · 고쳐 쓰기 버튼 · 고쳐 쓰기 BFF 가 생성 서버에 넘길 유형이 모두 이 함수를 쓴다 (D-99).
    ⛔ 사전 유형이 있으면 빈 목록 — 그 문장은 사전 유형으로 고쳐 쓰고 유형 줄이 이미 있다. 판정 대상 아님(`not_claim`)도 빈 목록.
    🔴 후보가 없으면 빈 목록이다 — 「추정 유형 없음」은 「문제없음」이 아니다(D-220 · D-330 결정 1). 이 함수는 그 말을 하지 않는다.
    """
    if getattr(sentence, "violations", None) or getattr(sentence, "not_claim", False):
        return []
    return sorted({c.violation.value for c in getattr(sentence, "encoder_candidates", None) or ()})


def guessed_mark(sentence: object) -> str | None:
    """겉 표지 글자 — 추정 유형이 있으면 `GUESSED_TYPE_MARK` · 없으면 None (D-330 보충 2)."""
    return GUESSED_TYPE_MARK if guessed_types(sentence) else None


#: 🆕 2026-10-14 (D-330 보충 3) — 보류 문장에서 사전 유형 후보와 인코더 유형 후보가 **같은 유형**일 때 유형 줄에 붙이는 말.
#: ⛔ 확정이 아니다 — 합의로 확정할지는 사전 재작업 때 판정한다(D-313 ⬜). 문안은 화면 담당 검토 대상이다
#: 🔄 2026-10-14 (ksr) — 「확정 아님」을 뺐다. 이 말은 보류 문장의 유형 줄에만 붙고 그 줄이 「유형 후보 — 확정 아님」으로 시작한다
AGREED_MARK = "사전과 AI 추정이 같은 유형"

#: 🆕 2026-10-14 (D-341 결정 1) — 생성의 **인정 · 심사 문구**(이용자가 적은 고정 문구)를 따로 판정한 경고. 생성 후보를 떨구지 않는다.
#:    · 강한 — 그 전제의 문장 판정에 질병 표방 · 의약품 오인이 섰다(사전 적중) · `{types}` 에 유형 이름
#:    · 약한 — 사전은 조용하고 인코더만 질병 · 의약품 오인을 냈다. 「질병 발생 위험 감소」 인정 문구(고시형)는 적법이라 단정하지 않는다
#:    · 확인 못 함 — 판정 엔진에 닿지 못했다. 「경고 없음」으로 그리지 않는다 (D-220)
#: 문안은 화면 담당 검토 대상이다
FIXED_STRONG = "이 문구는 인정 · 심사받은 문구로 보기 어려워요 — {types} 표현이 있어요. 인정서(심사서)의 문구와 같은지 확인해 주세요."
FIXED_WEAK = "AI 가 질병 · 의약품 관련 표현으로 추정했어요 — 「질병 발생 위험 감소」로 인정받은 문구라면 정상이에요. 인정서의 문구와 같은지 확인해 주세요."
FIXED_UNCHECKED = "인정 · 심사 문구를 확인하지 못했어요(판정 엔진에 연결하지 못함) — 이 문구는 검수를 거치지 않았어요."


def agreed_types(sentence: object) -> list[str]:
    """보류 문장의 사전 유형 후보(`violations`) ∩ 인코더 유형 후보(옮긴 후보 제외) — 이름 · 정렬. 아니면 빈 목록 (D-330 보충 3).

    ⛔ 보류가 아니면 빈 목록 — 확정 문장의 유형은 이미 「걸린 유형」이다. ⛔ 품목 전제가 옮긴 후보(`moved_from`)는 세지 않는다 —
       평가 도구가 「인코더가 직접 낸 유형」만 세는 것과 같다(`scripts/eval_graph.py` `enc_candidates`).
    """
    if getattr(getattr(sentence, "verdict", None), "value", None) != "hold":
        return []
    mine = {v.value for v in getattr(sentence, "violations", None) or ()}
    enc = {
        c.violation.value
        for c in getattr(sentence, "encoder_candidates", None) or ()
        if getattr(c, "moved_from", None) is None
    }
    return sorted(mine & enc)


def agreed_mark(sentence: object) -> str | None:
    """유형 줄에 붙일 말 — 합의한 유형이 있으면 `AGREED_MARK` · 없으면 None (D-330 보충 3)."""
    return AGREED_MARK if agreed_types(sentence) else None


# ── 실증 분기 (🆕 2026-10-14 · D-337 · D-268 「지시」 · D-304 · D-289) ─────────────────────────────
class SubstText(NamedTuple):
    """실증 분기 한 줄 — 기준 문안과 인정되는 자료 종류."""

    criteria: str
    evidence: tuple[str, ...]


#: 법 축(`collect.law_map.LAW_OF_ID` 의 값) → 실증 분기 문안.
#: ✅ 2026-10-14 승인 — 오한빈 (모델 권고 승인 · 글자는 모델이 옮겨 적음). 정본 글자는 `docs/ohb/기준문안_초안_2026-10-02.md` §13 이고
#:    게이트(`tests/test_substantiation.py`)가 글자를 대조한다. 고치려면 그 문서를 먼저 고치고 다시 승인받는다 (D-147 · D-263 ②)
#: 자료 종류 `[문헌]` — 식품표시광고법 시행규칙 제9조① 1 ~ 3 호 · 화장품법 시행규칙 제23조② 1 · 2 호 · 표시광고 실증 운영고시(20246)
#:    「시험결과, 조사결과, 전문가의 견해, 학술문헌, 기타 …」. ⛔ 「기타」 · 「그 밖에 … 인정하는 자료」는 넣지 않는다 — 특허 · 인증을
#:    그 칸으로 읽게 된다(D-228)
#: 🔄 2026-10-14 개정 1 (§13) — 표시광고법 끝 문장. 「인증을 받았다」는 실증 대상이고(실증 고시 Ⅲ.2.②) 그 사실의 증빙이 필요하다 —
#:    「특허 · 수상 · 인증은 실증 자료가 아니다」로 쓰면 증서가 소용없다로 읽혔다. 성능 · 효능 차용 경고(지정고시 Ⅲ.5.마)는 뒤 절에 남긴다
SUBST_TEXT: dict[str, SubstText] = {
    "식품표시광고법": SubstText(
        "이 표현을 실증할 수 있는 자료(시험 또는 조사 결과 · 전문가 견해 · 학술문헌)가 있고, 순위 · 함량 · 연구 인용처럼 "
        "법이 함께 밝히라고 정한 사항은 같은 광고에 밝혔다면 등급이 내려갈 수 있습니다. 특허 · 수상 · 인증은 효능의 실증 자료가 아닙니다.",
        ("시험 또는 조사 결과", "전문가 견해", "학술문헌"),
    ),
    "화장품법": SubstText(
        "사실과 관련한 표현은 실증할 수 있어야 하고, 자료는 주장하는 내용과 직접 관계가 있어야 합니다. 그런 자료가 있고, "
        "법이 함께 밝히라고 정한 사항은 같은 광고에 밝혔다면 등급이 내려갈 수 있습니다.",
        ("시험결과(인체 적용시험 · 인체 외 시험 · 같은 수준 이상의 조사자료)", "조사결과"),
    ),
    "표시광고법": SubstText(
        "사실과 관련한 표현은 실증할 수 있어야 합니다. 실증할 수 있는 자료가 있고, 순위 · 기간처럼 함께 밝혀야 할 사항은 "
        "같은 광고에 밝혔다면 등급이 내려갈 수 있습니다. 특허 · 인증 · 수상을 받았다는 표현은 그 사실이 맞아야 하고, "
        "특허 · 인증 · 수상만으로 성능 · 효능이 실증되지는 않습니다.",
        ("시험결과", "조사결과", "전문가의 견해", "학술문헌"),
    ),
}

#: 실증 분기를 붙이는 유형 → 실증했을 때의 상한 (D-337 결정 1).
#: `[문헌]` 실증 책임 조문 — 식품표시광고법 제9조① · 화장품법 제14조① · 표시광고법 제5조① 「사실과 관련한 사항 … 실증할 수 있어야」.
#: ⛔ 비방광고는 상한이 R1 이상이고(D-304 · 「불리한 사실만 골라 비방」은 사실이어도 남는다) 문안이 따로 있어야 한다 · 소비자 기만 ·
#:    부당 비교는 자료로 풀리지 않는 갈래(은폐 · 누락 · 비교 방법)가 있다 — 1 단계 밖이다. 이 유형의 확정은 지시가 아니라 보류로 남는다 (D-192)
SUBST_MAX: dict[Violation, Risk] = {Violation.거짓_과장: Risk.R0}


def subst_branch(violations: list[Violation], basis_axes: set[str]) -> SubstBranch | None:
    """확정된 실증형 위반의 실증 분기 — 붙일 수 없으면 None (그 문장은 지시가 서지 않고 보류로 남는다 · D-220).

    ★ 문장의 위반이 **전부** `SUBST_MAX` 의 유형이어야 한다 — 하나라도 다른 유형이면 그 유형이 실증으로 풀리는지 모른다.
    ★ 문안의 열쇠는 **인용 근거가 속한 법 축 하나**다. 둘 이상이면(두 법이 섞인 문장) 어느 줄인지 정하지 않는다 — None.
    """
    vs = set(violations)
    if not vs or not vs <= set(SUBST_MAX) or len(basis_axes) != 1:
        return None
    text = SUBST_TEXT.get(next(iter(basis_axes)))
    if text is None:
        return None
    top = max((SUBST_MAX[v] for v in vs), key=lambda r: r.level)
    return SubstBranch(
        substantiated_max=top, accepted_evidence=list(text.evidence), criteria=text.criteria
    )


# ── 화장품 전제의 인코더 후보 옮김 (🆕 2026-10-14 · D-338) ─────────────────────────────────────
#: 화장품 전제에서 인코더가 낸 유형 → 우리 라벨 규약의 유형. 골든 화장품 행의 질병 · 건강 기능류 주장은 의약품_오인이다
#: (화장품 골든 라벨 의약품_오인 296 · 기능성화장품_오인 43 · 질병 표방 0 · 원장 10-14(B) ④). ⛔ 인코더 후보 전용 — 사전 경로(`pm.NO_HF_MISLEAD`)는
#: 건드리지 않는다. D-336 새 판(품목 입력)이 관문을 넘으면 걷는다
COSMETIC_MOVE: dict[Violation, Violation] = {
    Violation.질병_예방치료_표방: Violation.의약품_오인,
    Violation.건강기능식품_오인: Violation.의약품_오인,
}

#: 옮긴 후보 아래 붙는 한 줄 — (원래 유형, 옮긴 유형) → 말. 문안은 화면 담당 검토 대상이다
MOVED_NOTES: dict[tuple[Violation, Violation], str] = {
    (
        Violation.건강기능식품_오인,
        Violation.거짓_과장,
    ): "건강기능식품인데 이 기능성으로 인정받지 않았다면의 것이에요.",
    (
        Violation.질병_예방치료_표방,
        Violation.의약품_오인,
    ): "화장품이라면의 것이에요 — 화장품의 질병 관련 표현은 의약품 오인으로 봐요.",
    (
        Violation.건강기능식품_오인,
        Violation.의약품_오인,
    ): "화장품이라면의 것이에요 — 화장품의 건강 기능 표현은 의약품 오인으로 봐요.",
}


def moved_note(candidate: object) -> str | None:
    """옮긴 인코더 후보(`moved_from`)에 붙일 말. 옮기지 않았거나 표에 없으면 None."""
    src = getattr(candidate, "moved_from", None)
    if src is None:
        return None
    return MOVED_NOTES.get((src, getattr(candidate, "violation", None)))
