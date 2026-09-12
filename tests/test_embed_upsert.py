"""`chunk` upsert 가 **넣는 칸을 전부 갱신하는가** (2026-09-12).

⛔ 같은 자리를 두 번 밟았다.
   09-10 `token_count` 를 넣도록 고쳤는데 `DO UPDATE SET` 에 안 넣어, 기존 2,585행이
   **널로 남았다.** 마이그레이션 0006 은 「먼저 embed 를 돌려라」고 안내했고 —
   **돌려도 안 채워졌다.** 안내가 거짓이 되는 자리다.
   09-12 `paragraph`·`item` 을 고치면서 **같은 자리를 또 밟을 뻔했다.**

★ 그래서 처방을 「사람이 지키는 규칙」에서 **구조**로 옮겼다 — `CHUNK_COLS` 한 줄에서
  INSERT·VALUES·DO UPDATE SET·값 튜플이 전부 파생된다. 이 파일은 **그 구조가 서 있는지**를
  본다. 누군가 다시 손으로 풀어 쓰면 여기서 걸린다.

🔴 이것은 정적 검사다 — DB 에 실제로 갱신되는지는 보지 않는다.
"""

from __future__ import annotations

import pytest

from scripts import embed


@pytest.mark.gate
def test_기본키를_뺀_모든_칸이_갱신된다() -> None:
    assert set(embed.CHUNK_UPDATABLE) == set(embed.CHUNK_COLS) - {"chunk_id"}
    for col in embed.CHUNK_UPDATABLE:
        assert f"{col}=EXCLUDED.{col}" in embed.SQL_CHUNK_UPSERT, (
            f"🔴 {col} 이 DO UPDATE SET 에 없다 — 고친 값이 기존 행에 안 닿는다"
        )


@pytest.mark.gate
def test_자리표시자_수가_칸_수와_같다() -> None:
    """⛔ 손으로 `%s` 를 세던 자리다. 하나 어긋나면 실행 시점에야 터진다."""
    head = embed.SQL_CHUNK_UPSERT[: embed.SQL_CHUNK_UPSERT.index("ON CONFLICT")]
    assert head.count("%s") == len(embed.CHUNK_COLS)


def test_기본키는_갱신하지_않는다() -> None:
    assert "chunk_id=EXCLUDED.chunk_id" not in embed.SQL_CHUNK_UPSERT


def test_칸이_빠진_청크는_멈춘다() -> None:
    """🚨 `chunk_values` 가 조용히 `None` 을 넣지 않는다 — fail-closed (D-72)."""
    with pytest.raises(SystemExit):
        embed.chunk_values({"text": "…"}, _NoTokenizer())


class _NoTokenizer:
    """`_tokens()` 가 토크나이저를 못 찾으면 `None` 을 낸다 — 그 경로를 그대로 쓴다."""
