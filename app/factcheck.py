"""app/factcheck.py — 사실 확인 분기의 **알아보기 · 문안 표** (🆕 2026-10-16 · D-348 보충 3). **규칙 · 표는 여기 한 곳**이다 (D-99).

★ 보충 3 결정 1 ~ 3 · 6
   · 사실에 달린 문장(수상 · 인증 · 특허 · 등급 · 자격 · 원재료)은 사실을 모르면 위반을 확정할 수 없다 — 보류(`premise_unknown`) + 사실 확인 분기
   · 알아보기 = **호 관문**(사실에 달린 목을 품은 호 · 사전 인용이든 인코더 근거 호든 같다) + **낱말 규칙**(사실 주장 꼴 · 종류)
   · 사실이 참이면 그 사실에 달린 위반은 R0 · 남는 위험(사실을 빌린 성능 주장)은 실증 분기가 낸다
   · **표가 비면 아무것도 하지 않는다** — 낱말 목록 · 받는 증빙 · 기준 문안은 승인(D-263 ②) 전 비워 둔다(D-147 · D-220)
🚨 낱말 출처는 법령 · 고시 문언 `[문헌]` · 사전의 사실형 단독 항목 `[사례]` 만 — dev 를 보며 고르지 않는다(D-175 · 보충 3 결정 2)
🚨 이 모듈은 DB · 모델을 모른다 — 문장 글자와 근거 좌표만 본다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple

from app.contracts import FactKind, Risk
from collect.law_map import STATUTE_ID

#: 호 관문 — **사실에 달린 목을 품은 호** (보충 3 결정 2). (법 ID, 조, 항, 호)
#:    · 식품표시광고법 8조①4호 — [별표 1] 4.마(수상 · 인증) · 4.다(사용하지 않은 원재료명) `[문헌]` 제재표 원천 `fact` 칸(`scripts/sanction_review.yaml`)
#:    · 같은 법 7호 — 7.나(원재료 비교) `[문헌]` 같은 원천
#:    · 표시광고법 3조①1호 — 목이 없다 · 특허 · 인증 · 등급 · 자격 주장이 이 호로 의결됐다 `[사례]` 원장 10-14(B) ⑤
#: ⛔ 질병 표방(1호) · 의약품 오인(2호) · 건강기능식품 오인(3호)은 넣지 않는다 — 「인증」 낱말이 있어도 사실에 달린 목이 없다
FACT_HO: frozenset[tuple[str, int, int, int]] = frozenset(
    {
        (STATUTE_ID["식품표시광고법"], 8, 1, 4),
        (STATUTE_ID["식품표시광고법"], 8, 1, 7),
        (STATUTE_ID["표시광고법"], 3, 1, 1),
    }
)

#: 낱말 규칙 — 종류 → 사실 주장 꼴. 🔴 **승인 전 비어 있다**(보충 3 결정 6) — 비면 어느 문장에도 분기를 걸지 않는다.
#:    ⬜ 채우는 절차: 법령 · 고시 문언과 사전의 사실형 단독 항목(원장 10-14(B) ⑤ 의 16)에서 꼴을 뽑고 → 학습 분할에서 다듬고 →
#:       dev 는 확인만 → 「불충분」 기준(측정 전 고정 · 보충 3 ⬜ ①)을 넘으면 연다
FACT_RULES: dict[FactKind, re.Pattern[str]] = {}

#: 사실 주장 꼴**만** 있는 문장(성능 · 효능 표현이 없다)을 가르는 꼴 — 맞으면 실증 분기를 싣지 않는다(보충 3 결정 3). 🔴 승인 전 None
PERFORMANCE: re.Pattern[str] | None = None


class FactText(NamedTuple):
    """종류 하나의 문안 — 받는 증빙 · 기준 문안 · 참이면 상한 (D-263 ② · 보충 3 결정 3)."""

    accepted_evidence: list[str]
    criteria: str
    confirmed_max: Risk = Risk.R0


#: 종류 → 문안. 🔴 **승인 전 비어 있다** — 비면 그 종류의 분기를 내지 않는다(계약 `FactBranch` 의 필수 칸을 초안으로 채우지 않는다 · D-147)
FACT_TEXTS: dict[FactKind, FactText] = {}


def in_gate(coords: Iterable[tuple[str, int, int, int]]) -> bool:
    """근거 호 중 하나라도 사실에 달린 목을 품은 호인가 (보충 3 결정 2 · 호 관문)."""
    return any(c in FACT_HO for c in coords)


def fact_kind(text: str) -> FactKind | None:
    """문장의 사실 주장 종류 — 낱말 규칙의 첫 일치(표 순서) · 없으면 None. 🔴 표가 비면 늘 None (D-220)."""
    for kind, pat in FACT_RULES.items():
        if pat.search(text or ""):
            return kind
    return None


def fact_only(text: str) -> bool:
    """사실 주장 꼴만 있고 성능 · 효능 표현이 없는가 — 참이면 실증 분기도 필요 없다. 🔴 꼴이 승인 전(None)이면 거짓(실증 분기를 그대로 둔다)."""
    return PERFORMANCE is not None and not PERFORMANCE.search(text or "")
