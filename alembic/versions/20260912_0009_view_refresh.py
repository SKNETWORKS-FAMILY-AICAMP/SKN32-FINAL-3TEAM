"""0008 이 더한 열을 `v_current_chunk` 가 못 보고 있었다 (2026-09-12).

Revision ID: 0009_view_refresh
Revises: 0008_chunk_context
Create Date: 2026-09-12

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0009_view_refresh.sql` 을 읽어 실행한다 (D-99).
🔴 `SELECT c.*` 는 뷰를 만들 때 **열 목록으로 전개돼 고정**된다. 0008 이 `chunk` 에
   `context`·`paragraph_no` 를 더했는데 뷰가 그대로라 검색이 503 이 났다.
⛔ 0008 을 고치지 않는다 — 이미 돌았다. 되돌리기도 **앞으로 나아가는 방향**으로 적는다 (0007 과 같다).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0009_view_refresh"
down_revision = "0008_chunk_context"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0009_view_refresh.sql"


def _run(sql: str) -> None:
    raw = op.get_bind().connection
    raw = getattr(raw, "driver_connection", raw)
    with raw.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    if not SQL.exists():
        raise FileNotFoundError(f"{SQL} 가 없다 — 이 마이그레이션의 본문이다")
    _run(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    # 🚨 되돌려도 뷰는 **현재 열 목록으로** 다시 만든다 — 옛 열 목록을 복원할 방법이 없고,
    #    복원하면 그게 다시 이 사고다.
    _run(
        "DROP VIEW IF EXISTS v_current_chunk;"
        "CREATE VIEW v_current_chunk AS"
        "  SELECT c.* FROM chunk c"
        "  JOIN fragment f USING (fragment_id)"
        "  WHERE c.superseded_at IS NULL AND f.excluded = false;"
    )
