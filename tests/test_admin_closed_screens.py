"""닫은 관리자 화면 — 가입 심사 · 기업 회원 · 심사 서류 (2026-10-20 · psj · D-260 ④⑤ · D-107).

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
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in ("admin", "admin_signup_review", "admin_enterprise", "admin_review_docs"):
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
    assert label in body and "비활성" in body and "D-260" in body
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
