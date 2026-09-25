"""조문 추출은 시행 전 판을 싣지 않는다 (2026-09-25 · D-290 ③).

🔴 막는 것 — 법제처 본문이 시행 전 판(36814 · 20280101)을 줄 때 그 기준이 지금 기준으로 코퍼스에 들어가는 것.
"""

from __future__ import annotations

import pathlib

import pytest

from preprocess import law_article as la

pytestmark = pytest.mark.gate


def test_시행_전_판은_따로_갈린다() -> None:
    files = [
        pathlib.Path("admrul_69549_20251204.xml"),
        pathlib.Path("admrul_36814_20280101.xml"),
        pathlib.Path("law_002015_20260925.xml"),  # 오늘 시행은 시행 중이다
    ]
    now, later = la.split_in_force(files, "20260925")
    assert [p.name for p in later] == ["admrul_36814_20280101.xml"]
    assert [p.name for p in now] == ["admrul_69549_20251204.xml", "law_002015_20260925.xml"]


def test_시행일을_못_읽으면_멈춘다() -> None:
    with pytest.raises(SystemExit, match="시행일"):
        la.split_in_force([pathlib.Path("admrul_36814.xml")], "20260925")
