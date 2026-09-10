"""violation_t 에 기능성화장품_오인 후보 등재 (2026-09-10 · D-65).

Revision ID: 0005_violation_t_candidate
Revises: 0004_product_fact_unique
Create Date: 2026-09-10

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0005_violation_t_candidate.sql` 을 읽어 실행한다 (D-99).
⛔ 화장품법 [별표 5] 제2호 나목을 `violation_article` 에 적을 자리가 없었다.
🔴 등재이지 편입이 아니다 — `VIOLATION_TYPES` 승격 판정일은 2026-09-17 이다 (D-65).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0005_violation_t_candidate"
down_revision = "0004_product_fact_unique"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "0005_violation_t_candidate.sql"
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
    # 🚨 `ALTER TYPE ... DROP VALUE` 가 없다. 되돌리려면 타입을 다시 만들어야 하고,
    #    그 값을 쓰는 행이 하나라도 있으면 그때는 되돌릴 수 없다 (0003 이 그 경로다).
    raise NotImplementedError("ENUM 값은 뗄 수 없다 — 되돌리려면 0003 처럼 타입을 재생성해야 한다")
