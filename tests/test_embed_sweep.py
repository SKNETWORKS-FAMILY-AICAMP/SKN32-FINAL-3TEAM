"""`scripts/embed.py` `sweep_orphans` 의 가드 (2026-09-20 · D-254 · 감사 §1-8).

⛔ 종전에는 0행 `chunks.jsonl` 이면 DB 청크 **전부**를 고아로 보고 지운 뒤 「✅ 선언과 같다」였다.
   크게 줄어든 선언도 그대로 DB 삭제까지 초록으로 갔다.
🔴 DB 없이 돈다 — 가짜 커서로 SELECT 결과와 DELETE 호출만 본다.
"""

from __future__ import annotations

import pytest

from scripts import embed


class _Cur:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.sql: list[str] = []

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.sql.append(sql)

    def fetchall(self) -> list[tuple[str]]:
        return [(i,) for i in self.ids]

    @property
    def deleted(self) -> bool:
        return any(s.startswith("DELETE") for s in self.sql)


def _ids(n: int) -> list[str]:
    return [f"c{i}" for i in range(n)]


@pytest.mark.gate
def test_빈_선언이면_거두지_않고_멈춘다() -> None:
    cur = _Cur(_ids(100))
    with pytest.raises(SystemExit) as e:
        embed.sweep_orphans(cur, set(), partial=False)
    assert e.value.code == 1
    assert not cur.deleted


def test_빈_선언은_limit_이어도_멈춘다() -> None:
    cur = _Cur(_ids(100))
    with pytest.raises(SystemExit):
        embed.sweep_orphans(cur, set(), partial=True)
    assert not cur.deleted


@pytest.mark.gate
def test_문턱을_넘게_거두게_되면_멈춘다() -> None:
    cur = _Cur(_ids(100))
    with pytest.raises(SystemExit) as e:
        embed.sweep_orphans(cur, set(_ids(85)), partial=False)
    assert e.value.code == 1
    assert not cur.deleted, "🔴 멈춘다고 했는데 DELETE 가 나갔다"


def test_allow_shrink_면_거둔다() -> None:
    cur = _Cur(_ids(100))
    assert embed.sweep_orphans(cur, set(_ids(85)), partial=False, allow_shrink=True) == 15
    assert cur.deleted


def test_문턱_안이면_거둔다() -> None:
    cur = _Cur(_ids(100))
    assert embed.sweep_orphans(cur, set(_ids(96)), partial=False) == 4
    assert cur.deleted


def test_limit_부분실행은_여전히_거두지_않는다() -> None:
    """종전 `--limit` 동작은 그대로다 — 큰 차이여도 멈추지 않고 거두지도 않는다."""
    cur = _Cur(_ids(100))
    assert embed.sweep_orphans(cur, set(_ids(3)), partial=True) == 0
    assert not cur.deleted


@pytest.mark.gate
def test_문턱은_chunk_와_한_곳이다() -> None:
    """D-209 · D-99 — embed 가 자기 사본을 두지 않는다."""
    from preprocess import chunk

    assert embed.SHRINK_LIMIT is chunk.SHRINK_LIMIT
    assert embed.shrinkage is chunk.shrinkage
