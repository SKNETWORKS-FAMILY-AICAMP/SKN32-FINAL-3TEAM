"""자립 텍스트·항 서수·임베딩 입력 지문 (2026-09-12).

Revision ID: 0008_chunk_context
Revises: 0007_sanction_four_eyes_back
Create Date: 2026-09-12

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0008_chunk_context.sql` 을 읽어 실행한다 (D-99).
🔴 이 마이그레이션만으로는 아무것도 채워지지 않는다. **선언한 상태로 만들려면**
   다시 돌려야 한다 (D-187) —

       uv run python -m preprocess.law_article --dump
       uv run python -m preprocess.chunk --dump
       uv run python -m scripts.embed          # 🚨 재임베딩 2,585건

   ⛔ 그 전까지 `chunk.context` 는 NULL 이고 `chunk_embedding.input_sha256` 도 NULL 이다.
      **NULL 은 「문맥이 없다」가 아니라 「아직 안 채웠다」**이므로, 중간 상태가
      성공처럼 보이지 않는다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0008_chunk_context"
down_revision = "0007_sanction_four_eyes_back"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0008_chunk_context.sql"


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
    # 🚨 열을 지우면 그 안의 값도 같이 사라진다 — 되돌린 뒤에는 재적재가 필요하다.
    _run(
        "ALTER TABLE chunk_embedding DROP COLUMN IF EXISTS input_sha256;"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS context;"
        "ALTER TABLE chunk DROP COLUMN IF EXISTS paragraph_no;"
    )
