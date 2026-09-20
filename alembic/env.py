"""alembic/env.py — 마이그레이션 실행 환경.

🚨 **pgvector 훅이 이 파일의 존재 이유다** (D-84 ⑪ · 기획서 8-4 체크리스트 11).
   `ischema_names['vector']` 를 등록하지 않으면 autogenerate 가 `Vector` 컬럼을
   **인식하지 못하고**, 매 마이그레이션마다 「알 수 없는 타입」으로 깨진다.
   알면 30분, 모르면 계속 깨진다 — 그래서 첫 파일부터 넣는다.

🚨 접속 문자열은 `.env` 에서 온다. `collect.env` 가 `.env` 를 읽는 유일한 곳이고,
   모양(검증·드라이버 접미사)은 `app.settings.sqlalchemy_url()` 이 정한다 — 여기서 다시 만들지 않는다.
   ⛔ `alembic.ini` 에 `sqlalchemy.url` 을 적으면 접속 문자열이 커밋된다 — gitleaks 가
      막으려는 것이 그것이다.

🔴 **`alembic.ini` 는 ASCII 만 담는다** (2026-09-09 실측).
   alembic 은 그 파일을 `configparser` 로 **`encoding="locale"`** 로 읽는다. 한국어
   Windows 에서 그건 cp949 다 — UTF-8 바이트가 하나라도 있으면 `alembic upgrade` 가
   **DB 를 보기도 전에 `UnicodeDecodeError` 로 죽는다.**
   ⛔ 9월 5일부터 잠복해 있었다. `alembic/versions/` 가 비어 있어 아무도 돌린 적이
      없었기 때문에 안 터졌을 뿐이다. 설명은 전부 이 파일에 둔다 —
      **파이썬 소스는 언제나 UTF-8 로 읽힌다.**

🔴 **층이 둘이고, 관리 방식이 다르다** (2026-09-09).

    거버넌스·데이터 층 (18테이블)   `db/schema.sql`   ← 원본. 손으로 쓴 DDL
    런타임 층 (6테이블)             `app/models.py`   ← ORM. autogenerate 대상

⛔ `target_metadata` 는 런타임 층뿐이다. 그대로 두면 `--autogenerate` 가 DB 에 있는
   거버넌스 18테이블을 **「메타데이터에 없다」고 보고 DROP 을 생성한다.**
   초안을 눈으로 보면 잡히지만, **안 보면 스키마가 통째로 날아간다.**
★ 그래서 `include_object` 로 거버넌스 객체를 autogenerate 시야에서 뺀다.
  🚨 목록은 `db/schema.sql` 에서 읽는다 — 두 곳에 같은 목록을 두지 않는다 (D-99).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from pgvector.sqlalchemy import Vector
from sqlalchemy import engine_from_config, pool
from sqlalchemy.dialects import postgresql

from alembic import context

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 🚨 이 한 줄이 D-84 ⑪ 이다. import 순서상 모델보다 먼저 와야 한다.
postgresql.base.ischema_names["vector"] = Vector

from app.models import Base  # noqa: E402  — ischema_names 등록 뒤에 온다
from app.settings import sqlalchemy_url  # noqa: E402  — 접속 문자열의 한 길

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _governance_objects() -> set[str]:
    """`db/schema.sql` 이 만드는 테이블·뷰 이름. 🚨 **파일이 목록의 단일 출처다.**"""
    import re  # noqa: PLC0415

    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    return set(re.findall(r"^CREATE (?:TABLE|VIEW)\s+(\w+)", sql, re.M))


GOVERNANCE = _governance_objects()


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001, ARG001
    """🔴 거버넌스 객체는 autogenerate 가 보지 않는다 — 안 그러면 DROP 을 생성한다."""
    return not (type_ in {"table", "view"} and name in GOVERNANCE)


def _url() -> str:
    """🆕 2026-09-20 (D-254 · 감사 §2 migrate) — 접속 문자열의 길은 **하나**다 (D-99 · D-209).

    ⛔ 종전에는 `DATABASE_URL` 을 **원문 그대로** 넘겼다. `db-fresh`·`db-drift` 는
       `app.settings.sqlalchemy_url()` 을 써서 — 검증(postgres 인가) · 드라이버 접미사(`+psycopg`) ·
       빈 값의 기본값이 거기서만 붙었다. 그래서 `postgresql://…` 를 적으면 `db-fresh` 는 초록인데
       `migrate` 는 psycopg2 를 찾다 죽었다.
    """
    return sqlalchemy_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
