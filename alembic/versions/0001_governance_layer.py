"""거버넌스·데이터 층 — `db/schema.sql` 을 그대로 적용한다.

Revision ID: 0001_governance
Revises:
Create Date: 2026-09-09

──────────────────────────────────────────────────────────────
🚨 **이 마이그레이션은 DDL 을 여기 적지 않는다.** `db/schema.sql` 을 읽어 실행한다.

    거버넌스·데이터 층 (18테이블·14타입·3뷰)   db/schema.sql   ← **원본**
    런타임 층 (6테이블)                        app/models.py   ← ORM · autogenerate

⛔ DDL 을 이 파일에 복사하면 같은 판정이 **세 곳**(설계 문서 · schema.sql · 마이그레이션)에
   생긴다. 그러면 한 곳만 고쳐지고, 고쳐지지 않은 쪽이 실제로 도는 쪽일 수 있다 (D-99).
   `docs/02_설계/거버넌스데이터층_DDL.md` 가 스스로 「저장소의 그 파일이 원본」이라 적었다.

🚨 **스키마를 바꿀 때** — `db/schema.sql` 을 고치고 **새 마이그레이션**을 쓴다.
   이 파일을 고치지 않는다. 이미 적용된 마이그레이션을 고치면 기기마다 스키마가 갈린다.

🔴 **`%` 때문에 파라미터 경로로 보내지 않는다** (2026-09-09 실측).

    psycopg.ProgrammingError: incomplete placeholder: '%'

   `exec_driver_sql()` 은 파라미터가 비어 있어도 **DBAPI 의 자리표시자 처리**를 탄다.
   psycopg3 은 그때 `%` 를 자리표시자 시작으로 읽는다. 스키마에 `%` 가 둘 있다 —

       -- 반복위반 100% 등 (2026.7.1 개정)
       -- 인정 기능성 문구 (100% 지향 프레임)

   ⛔ **둘 다 SQL 주석 안이다.** 주석 한 글자가 스키마 전체를 못 만들게 한다.
   ★ 고칠 곳은 주석이 아니라 **보내는 방식**이다 — 주석을 고치면 `db/schema.sql` 이
     설계 문서와 갈리고(게이트가 잡는다), 다음에 누가 `%` 를 또 쓰면 같은 자리에서 터진다.
   → **드라이버 커서에 파라미터 없이** 보낸다. 그러면 자리표시자 처리 자체가 안 일어난다.
"""

from __future__ import annotations

import pathlib
import re

from alembic import op

revision = "0001_governance"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def _sql() -> str:
    if not SCHEMA.exists():
        raise FileNotFoundError(
            f"{SCHEMA} 가 없다 — 거버넌스 층의 원본이다.\n"
            "  docs/02_설계/거버넌스데이터층_DDL.md 의 부록에서 뽑아 둔 파일이다."
        )
    return SCHEMA.read_text(encoding="utf-8")


def _run(sql: str) -> None:
    """🔴 **파라미터 없이** 보낸다 — 위 docstring 의 `%` 문제.

    🚨 여러 문장을 한 번에 보낸다 — psycopg 가 세미콜론으로 가른다.
    🚨 같은 트랜잭션 안이다 — alembic 이 연 커넥션의 드라이버 커서를 그대로 쓴다.
    """
    raw = op.get_bind().connection
    raw = getattr(raw, "driver_connection", raw)
    with raw.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _run(_sql())


def downgrade() -> None:
    """🔴 만든 것만 지운다 — `DROP SCHEMA public CASCADE` 를 쓰지 않는다.

    ⛔ 그 한 줄은 런타임 층(`app/models.py`)까지 같이 지운다. 층이 둘인데
       한 층의 downgrade 가 다른 층을 지우면, 되돌리기가 사고가 된다.
    ★ 목록은 `db/schema.sql` 에서 읽는다 — 손으로 유지하지 않는다 (D-99).
    """
    sql = _sql()
    for view in reversed(re.findall(r"^CREATE VIEW\s+(\w+)", sql, re.M)):
        _run(f"DROP VIEW IF EXISTS {view} CASCADE")
    for table in reversed(re.findall(r"^CREATE TABLE\s+(\w+)", sql, re.M)):
        _run(f"DROP TABLE IF EXISTS {table} CASCADE")
    for typ in reversed(re.findall(r"^CREATE TYPE\s+(\w+)", sql, re.M)):
        _run(f"DROP TYPE IF EXISTS {typ} CASCADE")
    # 🚨 `vector` 확장은 지우지 않는다 — 다른 층이 쓸 수 있고, 지우는 쪽이 위험하다.
