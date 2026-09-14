"""document.annex_no — 별표 번호를 원문 머리글에서 읽어 담는다 (2026-09-14 · D-224).

Revision ID: 0015_document_annex_no
Revises: 0014_judgment_check_reassert
Create Date: 2026-09-14

🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0015_document_annex_no.sql` 을 읽어 실행한다.
   `document` 는 **거버넌스 층**이고 그쪽 정본은 `db/schema.sql` 이다 (D-99 · 0008~0011 과 같다).

🧊 **동결 후 첫 새 마이그레이션이다.** `0001` 이 `db/schema_0001.sql` 만 읽게 된 뒤로,
   스키마 변경은 **`db/schema.sql`(현재 선언) + 이 파일** 둘로만 들어온다.
   ⛔ 하나만 고치면 「새로 세운 DB」와 「옮긴 DB」가 갈린다 — `launcher.py db-drift` 가 대조한다.

🔴 **왜 이 칸인가** — 별표 경로가 유일하지 않다. 실측(2026-09-14):

    013475 / 2.가.1 → 「수입식품안전관리 특별법 제2조제1호에 따른 …」  (annex:013475_0003)
    013475 / 2.가.1 → 「과자류, 빵류 또는 떡류: 추잉껌」              (annex:013475_0004)

   같은 법령·같은 경로인데 **다른 별표**다. 번호 없이 인용하면 두 근거가 같은 좌표로 찍힌다.

⬜ **값을 여기서 채우지 않는다** (D-188) — 칸만 만든다. 채우는 것은 `scripts/load_db.py` 이고
   그것은 `data/derived/law_norm/*.jsonl` 을 읽는다. 즉 **재추출이 먼저**다:
   `uv run python launcher.py db-reset --yes --data` 가 그 순서를 갖고 있다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0015_document_annex_no"
down_revision = "0014_judgment_check_reassert"
branch_labels = None
depends_on = None

SQL = (
    pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0015_document_annex_no.sql"
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
    """🚨 칸을 뗀다 — 값은 파생물에서 다시 채울 수 있으므로 잃을 것이 없다.

    ⛔ 다만 되돌리면 별표 인용이 전부 `None` 으로 돌아간다 (`citation()` 의 별표 갈래가
       이 칸을 본다). **기능이 조용히 꺼지는 것이지 오류가 나는 것이 아니다** — D-72 가
       fail-closed 라 부른 바로 그 설계다.
    """
    _run("ALTER TABLE document DROP COLUMN IF EXISTS annex_no")
