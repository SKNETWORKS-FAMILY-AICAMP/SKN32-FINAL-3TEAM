"""`scripts/decision_map.py` 의 폐기·대체 판정 (2026-09-23).

⛔ 상태 칸 **어디에든** 「폐기」가 있으면 폐기로 셌다 — D-229 에 개정 메모(「일반」 폐기)를 붙이자 살아 있는 결정이
   폐기로 세어졌다(`dmap` 폐기·대체 8 → 9). 오류는 안 났고 수만 틀렸다. 상태는 **첫 낱말**이다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from scripts.decision_map import PENDING_DAYS, _clean, is_dead, pending_age

pytestmark = pytest.mark.gate


@pytest.mark.parametrize(
    "status",
    [
        "대체됨 (→ D-119)",
        "대체됨(→ D-36)",
        "폐기",
        "🔴 **폐기** (09-17 · → D-233)",
        "🔄 **부분 대체됨 (→ D-205)** — 오기 정정과 태그 집계처는 유효",
    ],
)
def test_폐기_대체는_폐기로_센다(status: str) -> None:
    assert is_dead(_clean(status))


@pytest.mark.parametrize(
    "status",
    [
        # 🔴 실제로 틀리게 셌던 줄 (D-229 · 2026-09-23)
        "확정 (09-16) · 팀장 · **D-127 개정** · 🔄 **② 는 D-271 로 개정**(「일반」 폐기)",
        "확정 (09-12)",
        "확정 · 🔄 **D-265 · D-268 로 개정**(검수 종착 = 증명서·보류·지시·통과)",
        "조건부",
        "확정 · 기존 결정을 대체됨으로 적은 메모",
    ],
)
def test_이력에_낱말이_있어도_살아_있는_결정이다(status: str) -> None:
    assert not is_dead(_clean(status))


# ── 판정 대기 (2026-09-28) — 초안 · 제안 · 조건부가 판정 없이 쌓이던 것을 센다 ─────────────
_TODAY = dt.date(2026, 9, 28)


@pytest.mark.parametrize(
    ("status", "want"),
    [
        ("⬜ 초안 (09-17) · D-153·D-156 확장", ("초안", 11)),
        ("제안 (09-07) · 팀장 확정 대기", ("제안", 21)),
        ("조건부 (2026-08-30 · W2 실측 후 확정)", ("조건부", 29)),
        (
            "조건부 (W1 결단)",
            ("조건부", None),
        ),  # 🚨 날짜를 못 읽으면 「모른다」 — 0 일로 바꾸지 않는다
    ],
)
def test_판정_대기를_상태_첫_낱말로_가르고_날을_센다(status: str, want: tuple) -> None:
    assert pending_age(_clean(status), _TODAY) == want


@pytest.mark.parametrize(
    "status",
    [
        "확정 (09-28 · 집행으로 채택 · 초안 09-17) · 팀장 판정 (a)",  # 🔴 이력의 「초안」 은 상태가 아니다
        "폐기 (→ D-283 · 09-24) · 초안 09-18",
        "확정 · 🔄 조건부였던 것을 닫았다",
    ],
)
def test_이력에_초안이_있어도_판정_대기가_아니다(status: str) -> None:
    assert pending_age(_clean(status), _TODAY) is None


def test_대기_기준일은_임의값이고_양수다() -> None:
    assert PENDING_DAYS > 0
