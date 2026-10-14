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
