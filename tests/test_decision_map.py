"""`scripts/decision_map.py` 의 폐기·대체 판정 (2026-09-23).

⛔ 상태 칸 **어디에든** 「폐기」가 있으면 폐기로 셌다 — D-229 에 개정 메모(「일반」 폐기)를 붙이자 살아 있는 결정이
   폐기로 세어졌다(`dmap` 폐기·대체 8 → 9). 오류는 안 났고 수만 틀렸다. 상태는 **첫 낱말**이다.
"""

from __future__ import annotations

import pytest

from scripts.decision_map import _clean, is_dead

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
