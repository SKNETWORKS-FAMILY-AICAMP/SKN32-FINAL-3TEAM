"""판별 매뉴얼(2015) 조문·조건 판 — 단위의 원천 대조 (2026-10-04 · 지시서 2026-10-03 판별매뉴얼 · 원장 10-03 ㊿-10).

🔴 무엇을 막나
   ① 추출 · 가림이 달라져 조각의 글이 바뀌었는데 옛 단위(옛 판독)가 그대로 붙는 것 — 조각과 한 칸이라도 다르면 멈춘다 (D-220)
   ② 파생물에 없는 조각이 단위로 드는 것
   ★ 단위 표는 조각의 부분집합이어도 된다 — 식약처 서술만 든 조각은 판독하지 않았다
"""

from __future__ import annotations

import pytest

from scripts import guide_statute_round as g

K1, K2 = "mn:aaaaaaaaaaaa", "mn:bbbbbbbbbbbb"


def _piece(k: str, n: int, text: str) -> dict:
    return {"지문": k, "구역": "식품", "쪽": 22, "면": "L", "조각": n, "조각수": 2, "문구": text}


@pytest.fixture
def mn(monkeypatch):
    have = {K1: _piece(K1, 1, "혈액순환에 좋은 차"), K2: _piece(K2, 2, "식약처 서술")}
    monkeypatch.setattr(g, "mn_pieces", lambda: have)
    monkeypatch.setattr(g.registry, "assert_derivable", lambda rows, who: None)
    return have


@pytest.mark.gate
def test_단위는_조각의_부분집합이어도_된다(mn) -> None:
    src = g.mn_units([dict(mn[K1])])
    assert list(src) == [K1]
    assert src[K1]["원천"] == g.MN_SOURCE and src[K1]["문구"] == "혈액순환에 좋은 차"


@pytest.mark.gate
@pytest.mark.parametrize(
    "change",
    [
        {"문구": "혈액순환에 좋은 차!"},
        {"조각": 2},
        {"쪽": 23},
        {"지문": "mn:cccccccccccc"},
        {"지문": "cb:aaaaaaaaaaaa"},
    ],
)
def test_조각과_다른_단위는_멈춘다(mn, change) -> None:
    with pytest.raises(SystemExit, match="판별 매뉴얼"):
        g.mn_units([{**mn[K1], **change}])


@pytest.mark.gate
def test_같은_지문이_두_번이면_멈춘다(mn) -> None:
    with pytest.raises(SystemExit, match="두 번"):
        g.mn_units([dict(mn[K1]), dict(mn[K1])])


@pytest.mark.gate
def test_판별_매뉴얼_판이_판_틀에_올라_있다() -> None:
    R, _ = g.ROUNDS["mn"]
    assert R.cite_of is g.cite_of  # 식품 근거 코드
    assert R.path("ADOPTED") == g.MN_ADOPTED
