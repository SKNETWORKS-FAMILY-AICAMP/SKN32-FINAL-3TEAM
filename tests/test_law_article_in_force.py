"""조문 추출은 부칙을 읽지 않은 시행 전 판을 싣지 않는다 (2026-09-25 · 팀장 판정 (나) · D 초안).

🔄 같은 날 정정 — 종전 머리말은 「D-290 ③」이었다. ③ 은 옛 판이다.

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
        pathlib.Path("admrul_99999_20280101.xml"),  # 부칙을 읽지 않은 시행 전 판(허용 표에 없다)
        pathlib.Path("law_002015_20260925.xml"),  # 오늘 시행은 시행 중이다
    ]
    now, later = la.split_in_force(files, "20260925")
    assert [p.name for p in later] == ["admrul_99999_20280101.xml"]
    assert [p.name for p in now] == ["admrul_69549_20251204.xml", "law_002015_20260925.xml"]


def test_시행일을_못_읽으면_멈춘다() -> None:
    with pytest.raises(SystemExit, match="시행일"):
        la.split_in_force([pathlib.Path("admrul_36814.xml")], "20260925")


def test_허용된_시행_전_판은_싣고_시행_전_조항에만_표시한다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "admrul_36814_20280101.xml"
    now, later = la.split_in_force(
        [pathlib.Path(name), pathlib.Path("admrul_1_20280101.xml")], "20260925"
    )
    assert [p.name for p in now] == [name] and [p.name for p in later] == ["admrul_1_20280101.xml"]
    rows = [
        {"본문": "(나) 카페인을 제거한 커피원두를 원료로 사용하고 …"},
        {"본문": "(16) 주류를 주류가 아닌 식품의 상호ㆍ로고 …"},
        {"본문": "파. 영양강조표시라 함은 …"},
    ]
    assert la.mark_pending(rows, name) == 2
    assert rows[0]["시행예정"].startswith("2028-01-01 시행 예정")
    assert "시행예정" not in rows[2]


def test_시행_전_조항_글귀가_없으면_멈춘다() -> None:
    """🔴 판이 바뀌어 글귀가 사라지면 표시가 조용히 빠진다 — 멈춘다 (D-220)."""
    with pytest.raises(SystemExit, match="판이 바뀌었다"):
        la.mark_pending([{"본문": "커피원두의 함량"}], "admrul_36814_20280101.xml")


def test_시행_전_표시는_청크_문맥_맨_앞에_간다() -> None:
    from preprocess import chunk

    r = {"키": "prose-1", "제목": "커피", "시행예정": "2028-01-01 시행 예정"}
    assert chunk._context(r).splitlines()[0] == "[2028-01-01 시행 예정]"
    assert chunk._context({"키": "prose-1", "제목": "커피"}) == "커피"
