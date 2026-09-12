"""어휘 검색(BM25 자리)의 색인 — `chunk.tsv` 생성열 + GIN (2026-09-12 오후).

Revision ID: 0010_chunk_tsv
Revises: 0009_view_refresh
Create Date: 2026-09-12

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0010_chunk_tsv.sql` 을 읽어 실행한다 (D-99).
🔴 `chunk` 에 열을 더하므로 그 SQL 이 `v_current_chunk` 도 같이 다시 만든다 (0009 의 규칙).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0010_chunk_tsv"
down_revision = "0009_view_refresh"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0010_chunk_tsv.sql"


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
    # 🚨 열을 떨어뜨리면 뷰도 **같이** 다시 만들어야 한다 — 되돌리기도 같은 규칙을 지킨다.
    _run(
        "DROP INDEX IF EXISTS ix_chunk_tsv;"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS tsv;"
        "DROP VIEW IF EXISTS v_current_chunk;"
        "CREATE VIEW v_current_chunk AS"
        "  SELECT c.* FROM chunk c"
        "  JOIN fragment f USING (fragment_id)"
        "  WHERE c.superseded_at IS NULL AND f.excluded = false;"
    )
