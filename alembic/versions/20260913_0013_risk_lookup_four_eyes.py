"""서명 없는 제재 행이 위험도 하한으로 쓰이지 않게 한다 (2026-09-13 · D-66 · D-170).

Revision ID: 0013_risk_lookup_four_eyes
Revises: 0012_app_account
Create Date: 2026-09-13

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0013_risk_lookup_four_eyes.sql` 을 읽어
   실행한다 (D-99). 사유도 거기 있다.

🔴 한 줄 요약 — `ck_sanction_four_eyes` 는 **둘 다 NULL 이면 통과한다.** 이름은 four_eyes 인데
   zero_eyes 를 막지 않는다 (D-170). 막는 자리를 **읽는 쪽**(뷰)으로 옮긴다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0013_risk_lookup_four_eyes"
down_revision = "0012_app_account"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "0013_risk_lookup_four_eyes.sql"
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
    # ⛔ 되돌리면 **서명 없는 행이 다시 위험도 하한으로 보인다.** 그것이 이 마이그레이션이
    #    막으려던 것이고, 되돌리는 것 자체가 판정이다 (D-66). 자동으로 조용히 열지 않는다.
    raise NotImplementedError(
        "0013 을 되돌리면 2인 확인 없는 sanction_rule 행이 위험도 하한으로 다시 보인다 — "
        "되돌리려면 db/migrations/0013_risk_lookup_four_eyes.sql 을 읽고 사람이 판정한다 (D-66)."
    )
