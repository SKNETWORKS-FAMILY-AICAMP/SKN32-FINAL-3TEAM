"""app/db.py — 런타임 층 DB 세션 · 소유자 lse (병렬작업 계약 §5).

★ **여기서 하는 일** — `app/models.py` 런타임 층(judgment 등 6+1 테이블)을 읽고 쓰는
  세션 하나를 FastAPI 의존성으로 낸다. 거버넌스 층(`db/schema.sql`)은 건드리지 않는다.

⬜ **아직 어떤 라우터도 이걸 쓰지 않는다.** `app/routers/user.py`·`admin.py` 는
   지금 의도적으로 DB에 안 붙어 있다 (D-124 — 엔진 없이도 화면이 뜬다). 화면 하나를
   실제로 이 세션에 연결하는 건 팀 논의 후에 한다 — 이 파일은 그 전에 필요한 배선(연결
   자체가 되는지)만 미리 만들어 둔 것이다.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import sqlalchemy_url

_engine = create_engine(sqlalchemy_url(), pool_pre_ping=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI `Depends(get_session)` 로 쓴다. 요청이 끝나면 세션을 닫는다."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
