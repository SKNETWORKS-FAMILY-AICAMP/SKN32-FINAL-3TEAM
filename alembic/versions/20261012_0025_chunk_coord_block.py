"""chunk.coord_block — 좌표를 막는 이유 (2026-10-12 · 팀장 판정 · D-293 개정 안건 1 (나)).

Revision ID: 0025_chunk_coord_block
Revises: 0024_golden_cond
Create Date: 2026-10-12

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0025_chunk_coord_block.sql` 을 읽어 실행한다 (D-99).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0025_chunk_coord_block"
down_revision = "0024_golden_cond"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0025_chunk_coord_block.sql"
)


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
    _run(
        "DROP VIEW IF EXISTS v_current_chunk;\n"
        "ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_coord_block;\n"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS coord_block;\n"
        "CREATE VIEW v_current_chunk AS\n"
        "SELECT c.* FROM chunk c\n"
        "JOIN fragment f USING (fragment_id)\n"
        "WHERE c.superseded_at IS NULL AND f.excluded = false;"
    )
