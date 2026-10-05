"""golden_sample — 조건 칸 · 후보 근거 칸 · 읽는 뷰 둘 (2026-10-05 · D-317 · D-285 개정 4 ⑥ 개정).

Revision ID: 0024_golden_cond
Revises: 0023_sanction_rule_w5
Create Date: 2026-10-05

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0024_golden_cond.sql` 을 읽어 실행한다 (D-99). 사유도 거기 있다.
🚨 옮긴 뒤 `launcher.py load` 를 돌린다 — 기존 행의 조건은 적재가 채운다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0024_golden_cond"
down_revision = "0023_sanction_rule_w5"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0024_golden_cond.sql"


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
    # ⛔ 되돌리면 조건 M · D 행이 조건 없이 남아 빈 `violations` 가 적법으로 읽힌다 — 행을 먼저 거둬야 한다
    raise NotImplementedError(
        "0024 를 되돌리면 조건 칸이 사라져 M · D 행이 적법으로 읽힌다 — "
        "되돌리려면 그 행들을 먼저 거두고 사람이 판정한다 (D-317 · D-285 개정 4)."
    )
