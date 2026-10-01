"""이력·홈은 **내 판정만** 보인다 — 🆕 2026-09-29 (보안점검 P1-5).

★ 판정 엔진이 붙기 전이라 `judgment` 표가 비어 있다 — 새는 행이 없어 눈으로는 못 잡는다.
  그래서 **나가는 SQL 을 잰다** — 화면이 던진 쿼리가 전부 `work_doc.owner_id = 내 id` 를 달고 있는가.
🚨 DB 없이 돈다(CI `gate.yml` 에 Postgres 없음) — 쿼리를 받아 적기만 하는 가짜 세션을 끼운다.
   로그인은 `current_user` 를 바꿔 끼워 흉내 낸다 — 쿠키를 안 넣으니 상단바(`_nav_user`)는 DB 를 안 연다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api import app
from app.db import get_session
from app.routers import user as user_router

_ME = uuid.uuid4()


class _Recorder:
    """연결은 되고 쿼리는 **받아 적기만** 하는 세션 — 결과는 늘 0건."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    def connection(self) -> None:
        return None

    def _keep(self, stmt: object) -> None:
        compiled = stmt.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        self.sql.append(str(compiled))

    def scalar(self, stmt: object, *_a: object, **_k: object) -> int:
        self._keep(stmt)
        return 0

    def execute(self, stmt: object, *_a: object, **_k: object) -> SimpleNamespace:
        self._keep(stmt)
        return SimpleNamespace(all=list, scalars=lambda: SimpleNamespace(all=list))

    def close(self) -> None:
        return None


@pytest.fixture
def rec() -> Iterator[_Recorder]:
    r = _Recorder()

    def _dep() -> Iterator[_Recorder]:
        yield r

    app.dependency_overrides[get_session] = _dep
    try:
        yield r
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        user_router, "current_user", lambda *_a: SimpleNamespace(id=_ME, name="테스트")
    )


@pytest.mark.gate
@pytest.mark.parametrize("path", ["/u/history", "/u/history?verdict=hold&page=2", "/u/"])
def test_판정을_읽는_쿼리는_모두_내_문서로_걸러진다(
    rec: _Recorder, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    _login(monkeypatch)
    r = TestClient(app).get(path)
    assert r.status_code == 200, f"🔴 {path} — {r.status_code}"
    judg = [q for q in rec.sql if "FROM judgment" in q]
    assert judg, f"🔴 {path} 가 판정을 읽지 않았다 — 재는 대상이 없다"
    for q in judg:
        assert "work_doc.owner_id = " in q and str(_ME) in q, (
            f"🔴 소유자 조건 없이 판정을 읽었다 — {q}"
        )


@pytest.mark.gate
@pytest.mark.parametrize("path", ["/u/history", "/u/"])
def test_로그아웃이면_판정을_읽지_않고_로그인을_안내한다(rec: _Recorder, path: str) -> None:
    r = TestClient(app).get(path)
    assert r.status_code == 200, f"🔴 로그인 벽을 세웠다(D-66) — {r.status_code}"
    assert not rec.sql, f"🔴 로그아웃인데 판정을 읽었다 — {rec.sql}"
    assert 'href="/u/login"' in r.text, "🔴 로그인 안내가 없다"
    assert "아직 판정 기록이 없다" not in r.text, "🔴 못 본 것을 「기록 없음」으로 그렸다"
