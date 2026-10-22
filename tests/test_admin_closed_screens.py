"""닫은 관리자 화면 — 가입 심사 · 기업 회원 · 심사 서류 · 매출 (D-260 ④⑤⑥ · D-107).

지키는 것
  ① 화면은 남는다 — 목록 · 상세 경로가 200 으로 「비활성 + 사유」를 그린다 (D-107 (c) · 옛 링크가 깨지지 않게)
  ② 사유 라벨은 D-107 조건 5 의 다섯 중 하나다
  ③ 🚨 입력 요소 · 파일 선택 · POST 가 없다 (D-107 조건 1) — 페이지 전체가 아니라 본문 안에서 본다(머리글의 로그아웃 폼은 공용)
  ④ 예시 행이 없다 — 이메일 · 사업자번호 꼴 값이 본문에 없다 (D-260 「더미 값」)
  ⑤ 운영 대시보드는 승인 대기 건수 대신 라벨을 그린다
"""

from __future__ import annotations

import importlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin, admin_dbread, admin_router

LABELS = {"외부 감사 전", "Phase 3 이후", "Phase 4 이후", "열람 경계 (D-76)"}

CLOSED_PATHS = [
    "/admin/signup-review",
    "/admin/signup-review/r1",
    "/admin/enterprise",
    "/admin/enterprise/e1",
    "/admin/review-docs",
    "/admin/review-docs/1",
    "/admin/stats/revenue",
    "/admin/stats/revenue/any-id",
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in (
        "admin",
        "admin_signup_review",
        "admin_enterprise",
        "admin_review_docs",
        "admin_stats",
    ):
        module = importlib.import_module(f"app.routers.{name}")
        monkeypatch.setattr(module, "require_governor", lambda request: "UI-TEST")
    monkeypatch.setattr(admin, "_table_counts", lambda: {})
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_db", []))
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


def _main(html: str) -> str:
    """머리글 · 메뉴를 뺀 본문(`admin-content`)만."""
    start = html.index('id="admin-content"')
    end = html.index('class="admin-page-footer"', start)
    return html[start:end]


@pytest.mark.parametrize("path", CLOSED_PATHS)
def test_닫은_화면은_사유와_함께_남고_입력이_없다(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200
    body = _main(r.text)
    label = r.context["label"]
    assert label in LABELS or label.startswith("범위 밖 (D-")
    assert label in body and "비활성" in body
    # 🔄 10-22 — 근거 결정 번호는 화면에 싣지 않는다(코드 · 커밋에만) — 사유 · 열 조건 글에도 없다
    assert not re.search(r"D-\d", body), re.findall(r".{15}D-\d+.{5}", body)
    assert "`" not in body, "마크다운 백틱(코드 표기)이 화면에 그대로 보인다"
    assert "<form" not in body and "<input" not in body and "<textarea" not in body
    assert not re.search(r"[\w.-]+@[\w-]+\.[\w.]+", body), "예시 이메일이 남았다"
    assert not re.search(r"\d{3}-\d{2}-\d{5}", body), "사업자번호 꼴 값이 남았다"


def test_닫은_화면_라우터에_쓰기_경로가_없다() -> None:
    for name in ("admin_signup_review", "admin_enterprise", "admin_review_docs"):
        module = importlib.import_module(f"app.routers.{name}")
        methods = {m for route in module.router.routes for m in getattr(route, "methods", set())}
        assert methods <= {"GET", "HEAD"}, (name, methods)


def test_대시보드는_승인_대기_건수_대신_라벨을_그린다(client: TestClient) -> None:
    r = client.get("/admin/")
    assert r.context["signup_label"] == "외부 감사 전"
    assert "pending_reviews" not in r.context
    assert "가입 승인 심사" in r.text and "외부 감사 전" in r.text


@pytest.mark.parametrize(
    ("path", "module_name"),
    [
        ("/admin/signup-review", "admin_signup_review"),
        ("/admin/enterprise", "admin_enterprise"),
        ("/admin/review-docs", "admin_review_docs"),
        ("/admin/stats/revenue", "admin_stats"),
    ],
)
def test_메뉴는_닫힘만_표시하고_사유와_링크는_본문에_남긴다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str, module_name: str
) -> None:
    module = importlib.import_module(f"app.routers.{module_name}")
    html = client.get("/admin/").text
    nav = html[
        html.index('<nav id="admin-navigation"') : html.index(
            "</nav>", html.index('<nav id="admin-navigation"')
        )
    ]
    link = re.search(r'<a\b[^>]*href="' + re.escape(path) + r'".*?</a>', nav, re.S)
    assert link is not None
    assert "닫힘" in link.group() and module.LABEL not in link.group()
    assert module.LABEL in _main(client.get(path).text)
    monkeypatch.setattr(module, "LABEL", "라벨 변경 확인")
    html = client.get("/admin/").text
    nav = html[
        html.index('<nav id="admin-navigation"') : html.index(
            "</nav>", html.index('<nav id="admin-navigation"')
        )
    ]
    assert "라벨 변경 확인" not in nav


@pytest.mark.parametrize("period", ["daily", "weekly", "monthly", "invalid"])
def test_매출과_통계_대시보드에_예시_금액이_없다(client: TestClient, period: str) -> None:
    from app.routers import admin_stats  # noqa: PLC0415

    for path in ("/admin/stats/revenue", "/admin/stats/dashboard"):
        response = client.get(path, params={"period": period})
        assert response.status_code == 200
        body = _main(response.text)
        assert "₩" not in body
        assert admin_stats.LABEL in body
        assert "월별 매출 통계" not in body
    assert "sales" not in response.context["dash"]["kpi"]
    assert "sales" not in response.context["dash"]["delta"]


@pytest.mark.parametrize(
    ("path", "has_alt"),
    [
        ("/admin/enterprise", True),
        ("/admin/enterprise/e1", True),
        ("/admin/signup-review", True),
        ("/admin/signup-review/r1", True),
        ("/admin/review-docs", False),
        ("/admin/stats/revenue", False),
    ],
)
def test_대체_안내는_라우터의_alt가_있을_때만_그린다(
    client: TestClient, path: str, has_alt: bool
) -> None:
    response = client.get(path)
    body = _main(response.text)
    if has_alt:
        assert "대신 볼 수 있는 곳" in body
        for item in response.context["alt"]:
            assert f'href="{item["href"]}"' in body
            assert item["name"] in body and item["description"] in body
    else:
        assert "대신 볼 수 있는 곳" not in body


def test_관리자_화면은_공용_바닥글의_결정_번호를_싣지_않는다(client: TestClient) -> None:
    """🆕 10-22 — 관리자 화면은 자체 바닥글만(`admin/_base.html` 의 `site_footer` 비움)."""
    for path in ("/admin/", *CLOSED_PATHS):
        html = client.get(path).text
        assert "(D-124)" not in html and "admin-page-footer" in html, path
