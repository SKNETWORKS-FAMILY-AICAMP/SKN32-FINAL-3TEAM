"""2단계 다듬기 규칙판(`docs/lse/polish_rule.py`) — 소유자 lse (🆕 2026-10-14).

⛔ GPU · torch 없이 돈다. 🔴 지키는 것
   - 품목이 허락한 모양으로만 읽는다 — 식품 이름 속 「크림」을 화장품 크림으로 읽어 「얼굴에 펴 발라」를 붙이지 않는다
   - 모양을 못 읽거나 품목을 모르면 붙이지 않는다(None → 담백한 안만)
   - 붙인 문장은 관문(말투 모드)을 지난다
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LSE = Path(__file__).resolve().parents[1] / "docs" / "lse"
sys.path.insert(0, str(_LSE))

from polish_rule import polish_by_rule  # noqa: E402
from stage_gate import check  # noqa: E402


@pytest.mark.parametrize(
    ("s1", "category", "want"),
    [
        ("오메가3 미니 캡슐 90캡슐", "건기식", "물과 함께"),
        ("볼륨 마스카라", "화장품", "속눈썹"),
        ("시어버터 핸드크림 50ml", "화장품", "손등"),
        ("보성 녹차 티백 50개", "식품", "우려"),
        ("단호박 수프 파우치", "식품", "데워"),
    ],
)
def test_모양에_맞는_쓰는_법을_붙이고_관문을_지난다(s1: str, category: str, want: str) -> None:
    out = polish_by_rule(s1, category)
    assert out is not None and out.startswith(s1) and want in out
    assert check(s1, out, persona=True).passed, out


def test_식품_이름_속_크림을_화장품_크림으로_읽지_않는다() -> None:
    out = polish_by_rule("휘핑크림 케이크", "식품")
    assert out is None or "발라" not in out


@pytest.mark.parametrize(
    ("s1", "category"),
    [("편백나무 원목 도마", "식품"), ("볼륨 마스카라", None), ("볼륨 마스카라", "일반상품")],
)
def test_모양을_못_읽거나_품목을_모르면_붙이지_않는다(s1: str, category: str | None) -> None:
    assert polish_by_rule(s1, category) is None


def test_표의_어떤_문구도_용량_횟수_때를_정하지_않는다() -> None:
    """🆕 10-15 — 섭취 · 사용 방법(「식사 후 한 알」 · 「한 숟갈」 · 「세안 후」)은 제품 표시가 정한다(팀장 지적)."""
    from polish_rule import SAY
    from stage_gate import DOSE_TIME

    bad = [say for rows in SAY.values() for _, say in rows if DOSE_TIME.search(say)]
    assert bad == []


@pytest.mark.parametrize(
    ("s1", "s2"),
    [
        ("오메가3 미니 캡슐 90캡슐", "오메가3 미니 캡슐 90캡슐, 식사 후 물과 함께 한 알 드세요"),
        ("문경 오미자청", "문경 오미자청, 따뜻한 물에 한 숟갈 타서 드세요"),
        ("수분 토너", "수분 토너, 세안 후 손바닥에 덜어 두드려 보세요"),
        ("홍삼 스틱", "홍삼 스틱, 하루 한 번 하나씩 드세요"),
    ],
)
def test_관문이_새로_정한_용량_때를_막는다(s1: str, s2: str) -> None:
    r = check(s1, s2, persona=True)
    assert not r.passed and any("용량" in w for w in r.reasons), r.reasons


def test_원문에_있던_용량은_막지_않는다() -> None:
    """1단계 문장에 이미 있던 「90캡슐」은 사실이다 — 다듬기가 새로 정한 것만 막는다. 말투의 「한 번」도 횟수가 아니다."""
    s1 = "오메가3 미니 캡슐 90캡슐"
    assert check(s1, f"{s1}, 물과 함께 삼켜 드세요", persona=True).passed
    assert check(s1, f"{s1}, 한 번 드셔 보세요", persona=True).passed
