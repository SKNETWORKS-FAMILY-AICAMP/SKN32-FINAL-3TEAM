"""sanction_rule — 행 열쇠 · 별표1 목 · 덮음 · 원문 인용 · 사실 칸 · 판 sha (2026-10-02 · W5 · D-305 · D-309 · D-310).

Revision ID: 0023_sanction_rule_w5
Revises: 0022_judgment_ratchet
Create Date: 2026-10-02

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0023_sanction_rule_w5.sql` 을 읽어 실행한다 (D-99). 사유도 거기 있다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0023_sanction_rule_w5"
down_revision = "0022_judgment_ratchet"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0023_sanction_rule_w5.sql"
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
    # ⛔ 되돌리면 목 단위 하한(D-310)의 재료가 표에서 사라져 판정 그래프가 서명한 표와 다른 규칙으로 돈다 — 사람이 판정한다
    raise NotImplementedError(
        "0023 을 되돌리면 제재표의 별표1 목 · 덮음 칸이 사라진다 — "
        "되돌리려면 db/migrations/0023_sanction_rule_w5.sql 을 읽고 사람이 판정한다 (D-310)."
    )
