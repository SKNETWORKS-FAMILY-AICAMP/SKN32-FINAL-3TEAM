"""app/dictmatch.py — 금지 표현 사전 매칭. **정규화와 매칭 규칙이 사는 한 곳**이다 (D-99 · 🆕 2026-09-28 · W4).

★ 판정 그래프의 `match_dict`(`app/graph.py`)와 판정기 B(`scripts/eval_rule.py`)와 사전 빌더(`preprocess/dictionary.py`)가
   **같은 함수**를 쓴다. ⛔ 종전에는 `norm()` 이 `preprocess/dictionary.py` · `scripts/eval_rule.py` 두 곳에 같은 글자로 있었고,
   매칭(`term in norm(text)`)은 `eval_rule` 에만 있었다 — 그래프가 따로 적으면 세 번째 사본이 된다.

🔴 **매칭은 정규화문의 부분문자열이다** — 공백을 지우고 NFKC 로 접은 뒤 `term in text`.
   🚨 부분문자열이라 짧은 낱말이 위험하다(「면역력」 · 「두통」 — 인계 09-23 E6). 그래서 **단독판정 자격**이 있는 항목만
      받는다 — 자격 심사(적법중첩 · 모호 제외)가 이 매칭의 안전장치다 (D-156). 자격은 부르는 쪽이 고른다.
🔴 **보관은 원문으로 한다** (D-117) — 적중 자리(`span`)는 **원문 좌표**로 돌려준다. 뺄 구간(D-278)이 원문 위에 그려진다.
🚨 이 모듈은 DB 도 파일도 모른다 — 항목을 받아 맞출 뿐이다. 항목을 어디서 읽는지는 부르는 쪽이 정한다.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    """매칭용 정규화 — NFKC 로 접고 공백을 지운다. 🚨 **보관은 원문으로 한다** (D-117)."""
    return _WS.sub("", unicodedata.normalize("NFKC", str(s)))


def norm_with_map(s: str) -> tuple[str, list[int]]:
    """정규화문과 **정규화문 글자마다 원문 위치**. `norm()` 과 같은 결과를 낸다 — 게이트가 대조한다.

    🚨 글자 하나씩 NFKC 를 건다. 조합형 자모처럼 **앞뒤 글자와 합쳐지는** 경우는 통째 정규화와 다를 수 있다 —
       그때는 좌표를 내지 않는다(`None` · `spans_of`). 결과 글자가 다르면 맞춘 것이 아니다 (D-224 의 좌표 판).
    """
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(str(s)):
        for c in _WS.sub("", unicodedata.normalize("NFKC", ch)):
            out.append(c)
            where.append(i)
    return "".join(out), where


@dataclass(frozen=True, slots=True)
class Entry:
    """사전 항목 하나 — 부르는 쪽이 **단독판정 자격이 있는 것만** 넘긴다 (D-156)."""

    term: str
    #: 유형이 하나일 때만 값이 있다 — 여럿이면 낱말이 라벨을 감당하지 못한다(D-155 · `load_db.load_dict`)
    violation_type: str | None = None
    #: 근거 조문 인용(`collect.statute.cite` 꼴 · D-282). 🚨 법은 이 인용의 법 ID 가 정한다
    basis: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Match:
    """문장 하나에서 울린 항목. `span` 은 **원문** 좌표 `[start, end)` · 못 세우면 `None`."""

    entry: Entry
    span: tuple[int, int] | None


def find(text: str, entries: Iterable[Entry]) -> list[Match]:
    """정규화문에 항목이 부분문자열로 들어 있으면 적중이다. 항목마다 **첫 자리** 하나를 낸다(입력 순서 그대로).

    ★ `eval_rule.judge` 가 쓰던 규칙(`term in norm(text)`)과 **같은 적중 집합**을 낸다 — 좌표만 더한다.
    """
    n, where = norm_with_map(text)
    whole = norm(text)
    same = n == whole  # 🚨 글자 단위 정규화가 통째와 다르면 좌표를 믿지 않는다
    out: list[Match] = []
    for e in entries:
        t = norm(e.term)
        if not t or t not in whole:
            continue
        span = None
        if same:
            k = n.find(t)
            span = (where[k], where[k + len(t) - 1] + 1)
        out.append(Match(entry=e, span=span))
    return out


def terms_in(text: str, terms: Iterable[str]) -> set[str]:
    """울린 **낱말** 집합 — 판정기 B(`eval_rule`)용. `find` 와 같은 규칙이다."""
    return {m.entry.term for m in find(text, (Entry(term=t) for t in terms))}
