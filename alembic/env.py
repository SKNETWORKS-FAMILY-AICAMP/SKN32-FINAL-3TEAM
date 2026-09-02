"""alembic/env.py — 마이그레이션 실행 환경.

🚨 **pgvector 훅이 이 파일의 존재 이유다** (D-84 ⑪ · 기획서 8-4 체크리스트 11).
   `ischema_names['vector']` 를 등록하지 않으면 autogenerate 가 `Vector` 컬럼을
   **인식하지 못하고**, 매 마이그레이션마다 「알 수 없는 타입」으로 깨진다.
   알면 30분, 모르면 계속 깨진다 — 그래서 첫 파일부터 넣는다.

🚨 접속 문자열은 `.env` 에서 온다. `collect.env` 가 `.env` 를 읽는 유일한 곳이다.
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
from collect import env as dotenv  # noqa: E402  — .env 를 읽는 유일한 곳

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return dotenv.get("DATABASE_URL")


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
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
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
