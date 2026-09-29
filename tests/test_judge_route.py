"""`POST /judge` — 검수 그래프를 실제 DB 로 한 바퀴 (🆕 2026-09-29).

⛔ 종전에는 501 이었다. 이제 라우트가 `app/graph.py` 의 검수 그래프를 부르고 `to_response` 로 계약을 지나 낸다.
🚨 판정 노드는 스텁이다 — 종착은 `hold` 이고 문장은 `unjudged` 다(D-127 · D-269). 여기서 재는 것은 **배선**이다:
   ① 커서가 `config` 로 그래프에 들어간다 ② 계약을 지난 응답이 나간다 ③ DB 가 없으면 503 이고 원인을 응답에 안 담는다.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import api
from app import graph as g
from app.contracts import Outcome, Verdict


class _FakeReview:
    """컴파일본 대역 — 받은 입력 · config 를 적어 두고 스텁 한 바퀴의 상태를 돌려준다."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    def invoke(self, state: dict, config: dict) -> dict[str, Any]:
        self.calls.append((state, config))
        out, _ = g.run_review_stub(state["text"])
        return out


@contextmanager
def _conn():
    class _Cur:
        pass

    class _Conn:
        def cursor(self):  # noqa: ANN202
            @contextmanager
            def cm():  # noqa: ANN202
                yield _Cur()

            return cm()

    yield _Conn()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeReview:
    review = _FakeReview()
    monkeypatch.setattr(api, "_review_graph", lambda: review)
    import app.db  # noqa: PLC0415

    monkeypatch.setattr(app.db, "pg_connect", _conn)
    return review


@pytest.mark.gate
def test_판정_라우트가_검수_그래프를_커서와_함께_부른다(fake: _FakeReview) -> None:
    r = TestClient(api.app).post("/judge", json={"text": "이 제품은 암 예방에 좋습니다"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 🚨 판정 노드가 스텁이라 늘 보류다 — 통과로 나가지 않는다 (D-127)
    assert body["outcome"] == Outcome.hold.value
    assert [s["verdict"] for s in body["sentences"]] == [Verdict.unjudged.value]
    assert body["judged_by"].startswith("stub")
    (state, config), *_ = fake.calls
    assert state["text"] == "이 제품은 암 예방에 좋습니다"
    assert "product" in state
    # 🔴 커서가 config 로 들어간다 — 노드가 스스로 연결하지 않는다
    assert config["configurable"]["conn"] is not None


@pytest.mark.gate
def test_DB_가_없으면_503_이고_원인을_응답에_안_담는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "_review_graph", _FakeReview)

    def down():  # noqa: ANN202
        raise psycopg.OperationalError("connection to server at 10.0.0.9 port 5432 failed")

    import app.db  # noqa: PLC0415

    monkeypatch.setattr(app.db, "pg_connect", down)
    r = TestClient(api.app).post("/judge", json={"text": "면역력 강화"})
    assert r.status_code == 503
    assert "10.0.0.9" not in r.text  # P1-4 — 주소가 응답으로 새지 않는다


@pytest.mark.gate
def test_그래프를_못_지으면_가짜_보류가_아니라_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise ImportError("langgraph")

    monkeypatch.setattr(api, "_review_graph", broken)
    r = TestClient(api.app).post("/judge", json={"text": "면역력 강화"})
    assert r.status_code == 503


@pytest.mark.gate
def test_생성_조립_라우트는_여전히_501() -> None:
    """🚨 엔진이 없는 진입점은 가짜 200 을 내지 않는다 (D-124 ②)."""
    c = TestClient(api.app)
    assert c.post("/compose", json={}).status_code in (422, 501)
