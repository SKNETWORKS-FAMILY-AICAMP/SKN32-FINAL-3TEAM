"""dev 문구 검색 탐침 — 좌표 풀기 · 화면 순위 · 집계 (🆕 2026-10-12).

🔴 막는 것
   ① 좌표 없는 줄이 화면 순위의 자리를 먹는 것 — 판정 그래프는 그 줄을 버린다(`app/graph.py` `_pick` · D-224)
   ② 못 찾은 줄이 집계의 분모에서 빠지는 것 — 없음이 성공으로 세어진다 (D-220)
   ③ 결과에 문구가 실리는 것 — 실제 광고 문구다 (D-249)
"""

from __future__ import annotations

import types

import pytest

from scripts import search_probe_dev as spd

pytestmark = pytest.mark.gate


def _hit(law_id: str, basis: str | None) -> types.SimpleNamespace:
    return types.SimpleNamespace(law_id=law_id, basis_citation=basis)


def test_근거_좌표를_법과_호와_세부_기준으로_푼다() -> None:
    row = {"id": "r1", "근거": ["013094:제8조제1항제4호|다목", "002011:제3조제1항제1호"]}
    got = spd.targets(row)
    assert [(t["law"], t["ho"], t["mok"]) for t in got] == [
        ("식품표시광고법", "013094:제8조제1항제4호", "013453:[별표 1]제4호다목"),
        ("표시광고법", "002011:제3조제1항제1호", ""),
    ]


def test_꼴이_틀린_좌표는_건너뛰지_않고_멈춘다() -> None:
    with pytest.raises(ValueError, match="인용 꼴이 아니다"):
        spd.targets({"id": "r1", "근거": ["제8조"]})


def test_화면_순위는_좌표_없는_줄을_건너뛰고_같은_좌표를_한_번만_센다() -> None:
    view = [
        _hit("36814", None),  # 좌표 없음 — 화면에 못 나간다
        _hit("013094", "제1조"),
        _hit("013094", "제1조"),  # 같은 좌표 — 한 줄
        _hit("013094", "제8조제1항제4호"),
    ]
    assert spd.screen_rank(view, "013094:제8조제1항제4호") == 2
    assert spd.sp.rank_of(view, "013094:제8조제1항제4호") == 4  # 탐침 순위는 자리 그대로
    assert spd.screen_rank(view, "013094:제8조제1항제5호") is None


def test_못_찾은_줄도_분모에_남는다() -> None:
    recs = [
        {"law": "가", "rank": 1, "screen": 1},
        {"law": "가", "rank": 9, "screen": 4},
        {"law": "가", "rank": None, "screen": None},
    ]
    got = spd.tally(recs, "law")["가"]
    assert (got["n"], got["in_pool"], got["top"], got["screen_top"], got["screen_first"]) == (
        3,
        2,
        1,
        2,
        1,
    )
    assert got["mrr"] == pytest.approx((1 + 1 / 4 + 0) / 3)


def test_결과_줄에_문구가_실리지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    view = [_hit("002011", "제3조제1항제1호")]
    monkeypatch.setattr(spd.rt, "wide", lambda cur, q, pool: ([], [], None))
    monkeypatch.setattr(spd.rt, "law_view", lambda vec, lex, law: view)
    row = {"id": "r1", "text": "문구", "근거": ["002011:제3조제1항제1호"]}
    (rec,) = spd.probe_row(None, row, 50)
    assert rec == {
        "id": "r1",
        "law": "표시광고법",
        "cite": "002011:제3조제1항제1호",
        "pool": 1,
        "rank": 1,
        "screen": 1,
        "uncited_top": 0,
    }
    assert "문구" not in str(rec)
