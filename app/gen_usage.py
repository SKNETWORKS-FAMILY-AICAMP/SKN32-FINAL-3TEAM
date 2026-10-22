"""app/gen_usage.py — 카피 생성 이용을 **서버 메모리에서만** 센다 · 소유자 **psj** (2026-10-21).

★ 왜 메모리인가 — 생성 요청 · 결과를 저장하는 표가 없다(스키마 판정 대기). 관리자 생성 통계에 성공률 · 소요 시간을
   보이려고, 생성 처리부(`app/routers/user.py` `generate`)가 **건수와 시간만** 여기에 올린다.
🔴 원문 · 사용자 · 후보 글자는 받지 않는다 — 결과 종류 · 분기 키 · 걸린 초 · 「더 탐색하기」 여부 ·
   성공한 요청의 후보 수 · 통과 수 · 탈락 사유 코드(`copygen.filters.REASONS` 키) · 탐색 라운드 수뿐 (D-76).
🚨 **서버를 다시 켜면 0 부터** — 화면은 반드시 `started_at`(이 프로세스가 센 때부터)을 함께 적는다. 누적 통계가 아니다.
🚨 프로세스마다 따로 센다 — 워커를 여럿 띄우면 숫자가 나뉜다(지금은 한 프로세스).
"""

from __future__ import annotations

import threading
from collections import Counter
from datetime import UTC, datetime

#: 결과 종류 — 생성 처리부의 세 갈래
OUTCOMES = ("ok", "failed", "off")

_lock = threading.Lock()
_started_at = datetime.now(UTC)
_count: Counter[str] = Counter()
_by_branch: Counter[str] = Counter()
_more = 0
_secs_sum = 0.0
_secs_max = 0.0
#: 🆕 10-21 — 성공한 요청의 후보 · 통과 · 탈락 사유 · 라운드
_candidates = 0
_passed = 0
_reasons: Counter[str] = Counter()
_rounds_sum = 0
_rounds_n = 0
#: 🆕 10-21 — AI 광고 생성(`/u/compose`) 요청 수 · 고른 광고 종류. 이 화면은 생성 엔진을 부르지 않는다(판정 + 편집기)
_compose: Counter[str] = Counter()


def record(
    outcome: str,
    branch: str,
    seconds: float | None = None,
    *,
    more: bool = False,
    candidates: int | None = None,
    passed: int | None = None,
    reasons: dict[str, int] | None = None,
    rounds: int | None = None,
) -> None:
    """한 번 센다. 🚨 예외를 올리지 않는다 — 세는 일이 생성 화면을 멈추면 안 된다."""
    global _more, _secs_sum, _secs_max, _candidates, _passed, _rounds_sum, _rounds_n  # noqa: PLW0603
    if outcome not in OUTCOMES:
        return
    with _lock:
        _count[outcome] += 1
        _by_branch[branch] += 1
        if more:
            _more += 1
        if outcome != "ok":
            return
        if seconds is not None:
            _secs_sum += seconds
            _secs_max = max(_secs_max, seconds)
        if candidates is not None and passed is not None:
            _candidates += candidates
            _passed += passed
        if reasons:
            _reasons.update(reasons)
        if rounds is not None:
            _rounds_sum += rounds
            _rounds_n += 1


def record_compose(ad_format: str) -> None:
    """AI 광고 생성 요청 한 번 — 고른 광고 종류(`user._AD_FORMATS` 키)만. 문구는 받지 않는다."""
    with _lock:
        _compose[ad_format] += 1


def snapshot() -> dict:
    """지금까지의 수 — 복사본이다."""
    with _lock:
        total = sum(_count.values())
        ok = _count["ok"]
        tried = ok + _count["failed"]  # 엔진이 꺼져 막힌 것은 성공률 분모에서 뺀다
        return {
            "started_at": _started_at,
            "total": total,
            "ok": ok,
            "failed": _count["failed"],
            "off": _count["off"],
            "success_pct": round(ok * 100 / tried, 1) if tried else None,
            "avg_secs": round(_secs_sum / ok, 1) if ok else None,
            "max_secs": round(_secs_max, 1) if ok else None,
            "more": _more,
            "more_pct": round(_more * 100 / total, 1) if total else None,
            "by_branch": dict(_by_branch),
            "candidates": _candidates,
            "passed": _passed,
            "pass_pct": round(_passed * 100 / _candidates, 1) if _candidates else None,
            "reasons": dict(_reasons),
            "avg_rounds": round(_rounds_sum / _rounds_n, 1) if _rounds_n else None,
            "compose_total": sum(_compose.values()),
            "compose_by_format": dict(_compose),
        }


def reset() -> None:
    """시험용 — 0 으로 되돌리고 시작 시각을 지금으로."""
    global _started_at, _more, _secs_sum, _secs_max, _candidates, _passed, _rounds_sum, _rounds_n  # noqa: PLW0603
    with _lock:
        _started_at = datetime.now(UTC)
        _count.clear()
        _by_branch.clear()
        _reasons.clear()
        _compose.clear()
        _more = 0
        _secs_sum = _secs_max = 0.0
        _candidates = _passed = _rounds_sum = _rounds_n = 0
