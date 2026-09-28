"""flag_t 에 ND(변경금지) — 파생 데이터셋 금지 플래그 (2026-09-25 · 팀장 판정 (가) · D-110).

Revision ID: 0020_flag_nd
Revises: 0019_chunk_law
Create Date: 2026-09-25

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0020_flag_nd.sql` 을 읽어 실행한다 (D-99).
⛔ 첫 판(41a345e)은 SQL 만 넣고 이 파일이 없어 `migrate` 가 0019 에서 멈췄다 — `db-drift` 가
   `flag_t` 의 `ND` 를 「선언에만」으로 잡았다(클론 B · 2026-09-25). 게이트
   `test_마이그레이션_SQL_은_alembic_이_부른다` 가 같은 빠짐을 막는다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0020_flag_nd"
down_revision = "0019_chunk_law"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0020_flag_nd.sql"


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
    # 🚨 `ALTER TYPE ... DROP VALUE` 가 없다 (0005 와 같다).
    raise NotImplementedError("ENUM 값은 뗄 수 없다 — 되돌리려면 0003 처럼 타입을 재생성해야 한다")
