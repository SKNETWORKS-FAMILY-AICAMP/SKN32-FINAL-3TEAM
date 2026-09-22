"""app/db.py — 런타임 층 DB 세션 · 소유자 lse (병렬작업 계약 §5).

★ **여기서 하는 일** — `app/models.py` 런타임 층(judgment 등 6+1 테이블)을 읽고 쓰는
  세션 하나를 FastAPI 의존성으로 낸다. 거버넌스 층(`db/schema.sql`)은 건드리지 않는다.

🔄 2026-09-22 (ohb 흡수) — ⛔ 종전 docstring 은 「아직 어떤 라우터도 이걸 쓰지 않는다」였다.
   09-16 부터 `app/routers/user.py` 의 `/u/`(홈)·`/u/history` 가 이 세션에 붙는다.
   🚨 **그 두 화면도 DB 없이 떠야 한다** — 게이트 `test_모든_응답에_보안_헤더가_붙는다` 가 `/u/` 200 을
      요구하고, CI(`gate.yml`)에는 Postgres 가 없다. 병합 직후 DB 없는 기기에서 이 게이트가 🔴 였다(재현).
   ★ 그래서 쿼리 전에 `reachable()` 로 **연결만** 물어본다. 못 붙으면 화면은 「DB 없음」을 그리고
     **0건으로 그리지 않는다** — 셀 수 없는 것을 0 으로 적으면 없음이 사실로 둔갑한다 (D-72 · D-147).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.settings import DB_CONNECT_TIMEOUT_S, sqlalchemy_url

_log = logging.getLogger("copylane.db")

#: 🚨 엔진을 만드는 것은 **붙는 것이 아니다** — 첫 쿼리 때 붙는다. 그래서 import 는 DB 없이도 선다.
#: 🆕 `connect_timeout` — 없으면 응답 없는 주소를 끝없이 기다린다 (`app.settings.DB_CONNECT_TIMEOUT_S`).
_engine = create_engine(
    sqlalchemy_url(),
    pool_pre_ping=True,
    connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_S},
)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI `Depends(get_session)` 로 쓴다. 요청이 끝나면 세션을 닫는다."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def reachable(session: Session) -> bool:
    """이 세션이 DB 에 **붙을 수 있으면** True.

    🚨 **연결 단계의 실패만** 받아 준다 — `session.connection()` 이 여는 그 한 번이다.
       쿼리가 틀린 것(없는 테이블·문법)은 여기서 안 걸리고 **그대로 올라간다** — 증상을 삼키지 않는다 (D-162).
    🔴 원인 문자열은 화면·로그에 담지 않는다 — 호스트·포트·사용자명이 그 안에 있다
       (`admin._table_counts` 와 같은 이유). 예외의 **종류 이름**만 남긴다.
    """
    try:
        session.connection()
    except OperationalError as e:
        _log.warning("db: 접속 실패 — %s", type(e.orig).__name__ if e.orig else type(e).__name__)
        return False
    return True


def pg_connect(**kwargs: object):  # noqa: ANN201 — psycopg 는 지연 import 라 반환 타입을 여기서 못 적는다
    """**psycopg 직결** 연결 — 관리자 화면·오류 로그 핸들러가 쓴다. 🆕 2026-09-22.

    ⛔ 종전에는 `admin.py` 여섯 곳과 `admin_errors.py` 가 `psycopg.connect(dsn())` 을 **각자** 불렀고
       어느 곳도 `connect_timeout` 을 안 줬다 — 응답 없는 주소면 **끝없이 기다린다**(`/u/` 에서 09-22 에 고친 것과 같은 자리).
    ★ 대기 상한은 `settings.DB_CONNECT_TIMEOUT_S` 한 곳이다 (D-99). 🚨 import 를 안에 둔다 — DB 가 없어도 모듈은 서야 한다 (D-51).
    """
    import psycopg  # noqa: PLC0415

    from app.settings import dsn  # noqa: PLC0415

    kwargs.setdefault("connect_timeout", DB_CONNECT_TIMEOUT_S)
    return psycopg.connect(dsn(), **kwargs)
