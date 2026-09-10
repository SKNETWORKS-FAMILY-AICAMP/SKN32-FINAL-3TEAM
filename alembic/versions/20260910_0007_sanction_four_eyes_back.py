"""sanction_rule 2인 확인 강제를 되돌린다 (2026-09-10).

Revision ID: 0007_sanction_four_eyes_back
Revises: 0006_null_holes
Create Date: 2026-09-10

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0007_sanction_four_eyes_back.sql` 을 읽어 실행한다 (D-99).
🔴 0006 이 이 기기에서 이미 돌았다. 돈 마이그레이션의 본문을 고치면 새 DB 와 옮긴 DB 가
   갈리므로, 되돌리기도 **앞으로 나아가는 방향**으로 적는다.
★ 2인 확인의 강제 지점은 `collect/registry.py` 하나다 (D-66).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0007_sanction_four_eyes_back"
down_revision = "0006_null_holes"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "0007_sanction_four_eyes_back.sql"
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
        "ALTER TABLE sanction_rule DROP CONSTRAINT IF EXISTS ck_sanction_four_eyes;"
        "ALTER TABLE sanction_rule ALTER COLUMN verified_by SET NOT NULL;"
        "ALTER TABLE sanction_rule ALTER COLUMN reviewed_by SET NOT NULL;"
        "ALTER TABLE sanction_rule ADD CONSTRAINT ck_sanction_four_eyes"
        "  CHECK (verified_by <> reviewed_by);"
    )
