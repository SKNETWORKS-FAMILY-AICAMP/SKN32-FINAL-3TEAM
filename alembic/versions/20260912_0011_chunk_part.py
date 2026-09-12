"""쪼갠 조각(`part_no`·`part_total`)과 모델 입력 토큰 수 (2026-09-12 밤).

Revision ID: 0011_chunk_part
Revises: 0010_chunk_tsv
Create Date: 2026-09-12

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0011_chunk_part.sql` 을 읽어 실행한다 (D-99).
🔴 `chunk` 에 열을 더하므로 그 SQL 이 `v_current_chunk` 도 같이 다시 만든다 (0009 의 규칙 · D-197).

🔴 **이 마이그레이션만으로는 세 칸이 전부 NULL 이다** (D-187). 선언한 상태로 만들려면 —

    uv run python -m preprocess.chunk --dump
    uv run python -m scripts.embed          # 🚨 재임베딩 2,400건

   ⛔ 그 전까지 `part_no` 가 NULL 이고, **NULL 은 「안 쪼갰다」가 아니라 「아직 안 채웠다」**다.
      중간 상태가 성공처럼 보이지 않게 1/1 을 기본값으로 넣지 않았다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0011_chunk_part"
down_revision = "0010_chunk_tsv"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0011_chunk_part.sql"


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
    # 🚨 열을 떨어뜨리면 뷰도 **같이** 다시 만들어야 한다 — 되돌리기도 같은 규칙을 지킨다.
    #    ⛔ `ck_chunk_tokens` 주석은 되돌리지 않는다 — 종전 문장이 **틀린 문장**이었다.
    _run(
        "ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_part;"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS input_token_count;"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS part_total;"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS part_no;"
        "DROP VIEW IF EXISTS v_current_chunk;"
        "CREATE VIEW v_current_chunk AS"
        "  SELECT c.* FROM chunk c"
        "  JOIN fragment f USING (fragment_id)"
        "  WHERE c.superseded_at IS NULL AND f.excluded = false;"
    )
