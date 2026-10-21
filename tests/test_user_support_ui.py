"""Support layout: authenticated form, history and rejected submissions."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import app
from app.models import TICKET_CATEGORIES
from app.routers import user


@pytest.fixture
def support_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(user, "current_user", lambda *_: SimpleNamespace())
    monkeypatch.setattr(user, "_nav_user", lambda *_: None)
    monkeypatch.setattr(
        user,
        "_cs_list_ctx",
        lambda *_: {
            "tickets": [],
            "stat_total": 0,
            "stat_open": 0,
            "stat_done": 0,
            "categories": TICKET_CATEGORIES,
            "body_max": 2000,
            "title_max": 100,
        },
    )
    return TestClient(app)


def test_form_keeps_csrf_and_history_link(support_client: TestClient) -> None:
    response = support_client.get("/u/cs")
    assert response.status_code == 200
    assert f'name="{auth.CSRF_FIELD}"' in response.text
    assert 'href="/u/cs?tab=history"' in response.text
    assert 'name="priority"' not in response.text
    assert 'value="other" checked' in response.text


def test_history_has_return_path(support_client: TestClient) -> None:
    response = support_client.get("/u/cs?tab=history")
    assert response.status_code == 200
    assert "아직 접수한 문의가 없어요" in response.text
    assert "새 문의 작성" in response.text
    assert "data-support-form" not in response.text


def test_expired_csrf_keeps_input_escaped(support_client: TestClient) -> None:
    response = support_client.post(
        "/u/cs", data={"category": "judge", "title": "<script>제목</script>", "body": "오류 내용"}
    )
    assert response.status_code == 403
    assert "화면이 오래돼서" in response.text
    assert "&lt;script&gt;제목&lt;/script&gt;" in response.text
    assert "오류 내용</textarea>" in response.text
    assert 'value="judge" checked' in response.text
