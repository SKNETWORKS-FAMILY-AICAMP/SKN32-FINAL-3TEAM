"""product_fact 적재를 멱등으로 — UNIQUE 자연키 (2026-09-10).

Revision ID: 0004_product_fact_unique
Revises: 0003_golden_labels
Create Date: 2026-09-10

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0004_product_fact_unique.sql` 을 읽어 실행한다 (D-99).
⛔ 적재기가 `ON CONFLICT` 없는 순수 INSERT 인데 UNIQUE 가 없어 **두 번 돌리면 두 배**였다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0004_product_fact_unique"
down_revision = "0003_golden_labels"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "0004_product_fact_unique.sql"
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
    _run("ALTER TABLE product_fact DROP CONSTRAINT IF EXISTS uq_product_fact;")
