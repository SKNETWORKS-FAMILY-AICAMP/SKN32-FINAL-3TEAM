"""NULL 로 우회되던 제약 둘을 막는다 (2026-09-10 · D-170 계열).

Revision ID: 0006_null_holes
Revises: 0005_violation_t_candidate
Create Date: 2026-09-10

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0006_null_holes.sql` 을 읽어 실행한다 (D-99).
⛔ ck_chunk_tokens · ck_judgment_raise_needs_evidence 둘이
   `X IS NULL OR …` 로 시작해, 칸을 비우면 통과했다. postgres 16 에 실측으로 확인했다.
★ 널이면 안 되는 것은 CHECK 가 아니라 NOT NULL 로 막는다 — ck_source_four_eyes 의 모양이다.
🔴 `ck_sanction_four_eyes` 는 건드리지 않는다 — 거기 NOT NULL 을 걸면 없던 차단이 생긴다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0006_null_holes"
down_revision = "0005_violation_t_candidate"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0006_null_holes.sql"


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
        "ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_tokens;"
        "ALTER TABLE chunk ALTER COLUMN token_count DROP NOT NULL;"
        "ALTER TABLE chunk ADD CONSTRAINT ck_chunk_tokens"
        "  CHECK (token_count IS NULL OR token_count <= 512);"
        "ALTER TABLE judgment DROP CONSTRAINT IF EXISTS ck_judgment_raise_needs_evidence;"
        "ALTER TABLE judgment ADD CONSTRAINT ck_judgment_raise_needs_evidence"
        "  CHECK (risk_final IS NULL OR risk_floor IS NULL"
        "         OR risk_final <= risk_floor OR evidence_span IS NOT NULL);"
    )
