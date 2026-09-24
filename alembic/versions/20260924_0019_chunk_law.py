"""청크 `category` → 법 축 `law` (2026-09-24 · W6 · D-271 ① ②).

Revision ID: 0019_chunk_law
Revises: 0018_judgment_w3
Create Date: 2026-09-24

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0019_chunk_law.sql` 을 읽어 실행한다 (D-99). `chunk` 는 거버넌스 층이고
   정본은 `db/schema.sql` 이다 (0011 과 같은 자리).
🔴 값은 이 마이그레이션이 **`law_id` 로 채운다** — 재임베딩이 없다(임베딩 입력에 법이 안 들어간다 · D-271 맥락 6).
   그래서 사본(A)은 `migrate` 만으로 정본과 같은 값이 된다. `chunks.jsonl` 은 정본이 `chunk --dump` 로 다시 쓴다.
🚨 대응표에 없는 법 ID 가 있으면 **멈춘다**(GUARD) — 지우지도 고치지도 않는다 (D-220 · D-162).
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0019_chunk_law"
down_revision = "0018_judgment_w3"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0019_chunk_law.sql"


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
    # 🚨 되돌리면 **옛 오분류는 돌아오지 않는다** — 법 → 옛 범주 한 값으로 접는다(식품표시광고법 → 식품 …).
    #    옛 `category_of()` 가 「일반」에 떨어뜨리던 265청크는 제 법의 범주로 간다. 되돌림은 칸 모양만 되돌린다.
    _run(
        "DROP VIEW IF EXISTS v_current_chunk;"
        "ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_law;"
        "ALTER TABLE chunk ALTER COLUMN law DROP NOT NULL;"
        "ALTER TABLE chunk ALTER COLUMN law TYPE TEXT[] USING ARRAY[CASE law"
        "  WHEN '표시광고법' THEN '일반' WHEN '식품표시광고법' THEN '식품'"
        "  WHEN '화장품법' THEN '화장품' WHEN '건강기능식품법' THEN '건기식' END];"
        "ALTER TABLE chunk ALTER COLUMN law SET DEFAULT '{}';"
        "ALTER TABLE chunk ALTER COLUMN law SET NOT NULL;"
        "ALTER TABLE chunk RENAME COLUMN law TO category;"
        "CREATE VIEW v_current_chunk AS"
        "  SELECT c.* FROM chunk c"
        "  JOIN fragment f USING (fragment_id)"
        "  WHERE c.superseded_at IS NULL AND f.excluded = false;"
    )
