"""chunk.exempt_of — 적용 제외 목이라는 사실과 그 부모 (2026-09-28 · 팀장 판정 (나) · D-238 개정).

Revision ID: 0021_chunk_exempt
Revises: 0020_flag_nd
Create Date: 2026-09-28

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0021_chunk_exempt.sql` 을 읽어 실행한다 (D-99).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0021_chunk_exempt"
down_revision = "0020_flag_nd"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0021_chunk_exempt.sql"


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
        "ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_exempt;\n"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS exempt_of;\n"
        "CREATE VIEW v_current_chunk AS\n"
        "SELECT c.* FROM chunk c\n"
        "JOIN fragment f USING (fragment_id)\n"
        "WHERE c.superseded_at IS NULL AND f.excluded = false;"
    )
