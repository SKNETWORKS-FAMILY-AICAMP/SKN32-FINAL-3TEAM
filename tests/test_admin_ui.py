"""Admin shell migration, dashboard query state and existing read-only boundaries."""

from __future__ import annotations

import importlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin, admin_dbread, admin_errors, admin_router
from app.templating import templates


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in (
        "admin",
        "admin_stats",
        "admin_cs",
        "admin_board",
        "admin_terms",
        "admin_members",
        "admin_signup_review",
        "admin_errors",
    ):
        module = importlib.import_module(f"app.routers.{name}")
        monkeypatch.setattr(module, "require_governor", lambda request: "UI-TEST")
    monkeypatch.setattr(admin, "_table_counts", lambda: {})
    # 운영 표는 「못 붙었다」로 둔다 — 실제 DB 를 부르지 않는다 (DB 를 읽는 경우는 test_admin_dbread_screens.py)
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_db", []))
    monkeypatch.setattr(
        admin_errors,
        "_load_list",
        lambda *args: {"source": "no_db", "rows": [], "total": None, "page": 1},
    )
    monkeypatch.setattr(
        admin_errors,
        "_load_one",
        lambda *args: {"source": "no_db", "row": None, "same": []},
    )
    return _client()


def test_admin_dashboard_still_requires_login() -> None:
    response = _client().get("/admin/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize(
    ("path", "parent"),
    [
        ("/admin/stats/revenue", "통계"),
        ("/admin/terms/any-id", "문서관리"),
        ("/admin/members/any-id", "회원관리"),
        ("/admin/cs/tickets/any-id", "소식·문의"),
    ],
)
def test_top_navigation_marks_current_parent_without_opening_it(
    client: TestClient, path: str, parent: str
) -> None:
    html = client.get(path).text
    nav = html.split('<nav id="admin-navigation"', 1)[1].split("</nav>", 1)[0]
    current = re.findall(
        r'<details class="admin-nav-cat is-current">\s*<summary><span>(.*?)</span>', nav
    )
    assert current == [parent]
    assert not re.search(r"<details[^>]*\sopen(?:\s|>)", nav)
    assert 'class="admin-sidebar"' not in html
    assert 'src="/static/admin-nav.js?v=1" defer' in html
    assert 'aria-controls="admin-navigation"' in html


@pytest.mark.parametrize(
    "path",
    [
        "/admin/",
        "/admin/stats/dashboard",
        "/admin/stats/member",
        "/admin/stats/quality",
        "/admin/stats/quality/judge",
        "/admin/stats/quality/generation",
        "/admin/stats/revenue",
        "/admin/cs/tickets",
        "/admin/cs/tickets/any-id",
        "/admin/board/notices",
        "/admin/board/notices/any-id",
        "/admin/terms",
        "/admin/terms/any-id",
        "/admin/members",
        "/admin/members/any-id",
        "/admin/signup-review",
        "/admin/signup-review/r1",
        "/admin/errors",
        "/admin/errors/preview",
    ],
)
def test_admin_pages_share_one_accessible_shell(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.text.count('id="admin-content"') == 1
    assert response.text.count('class="admin-shell"') == 1
    assert "/static/admin-ui.css?v=2" in response.text
    assert "/static/brand/symbol-180.png" in response.text
    assert 'href="/u/landing"' in response.text


def test_dashboard_filters_preserve_period_and_sample_provenance(client: TestClient) -> None:
    response = client.get("/admin/", params={"period": "weekly", "status": "open"})
    assert response.context["period"] == "weekly"
    assert response.context["ticket_status"] == "open"
    assert response.context["tickets"] == []  # DB 를 못 읽으면 예시로 채우지 않는다
    assert 'name="period" value="weekly"' in response.text
    assert "일부는 예시 데이터입니다" in response.text
    assert "문의를 읽지 못했습니다" in response.text
    assert "테이블 건수를 확인할 수 없습니다" in response.text
    assert 'href="/admin/errors"' in response.text
    fallback = client.get("/admin/?period=invalid&status=invalid")
    assert fallback.context["period"] == "daily"
    assert fallback.context["ticket_status"] == ""


def test_dashboard_escapes_reused_ticket_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_admin_dbread_screens import (
        fake_run,  # noqa: PLC0415 — pytest 가 tests/ 를 sys.path 에 둔다
    )

    monkeypatch.setattr(
        admin_dbread, "run", fake_run(ticket_title='<img src=x onerror="alert(1)">')
    )
    response = client.get("/admin/")
    assert "&lt;img" in response.text
    assert "<img src=x" not in response.text


def test_all_admin_templates_compile_after_inheritance_migration() -> None:
    for name in templates.env.list_templates():
        if name.startswith("admin/"):
            templates.env.get_template(name)


@pytest.mark.parametrize(("raw", "days"), [("7", 7), ("all", 0), ("invalid", 30)])
def test_stats_menu_uses_existing_live_judgment_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, raw: str, days: int
) -> None:
    from test_admin_dbread_screens import fake_run  # noqa: PLC0415

    calls: list = []
    monkeypatch.setattr(admin_dbread, "run", fake_run(calls=calls))
    response = client.get("/admin/stats/quality", params={"days": raw})
    assert response.status_code == 200
    assert response.context["source"] == "db"
    assert response.context["days"] == days
    assert response.context["kpi"]["sentences"] == 12
    assert calls[0][0] == "stats.judge"
    assert "94.2%" not in response.text
    assert "더미 데이터" not in response.text
