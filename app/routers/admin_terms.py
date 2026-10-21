"""관리자 약관 관리는 닫힘 안내만 제공한다. 사용자 약관·동의 흐름은 유지한다.

🔄 2026-10-21 (psj) — 관리자 약관 쓰기 범위 · 운영 절차가 승인 대기라 닫는다. `terms` 표(0017)와 가입 화면의 동의 버전 읽기는 그대로.
⚠️ D-260 ① 은 이 화면을 연다고 했다 — 닫음은 그 결정의 되돌림이라 팀장 확인 대상이다.
⚠️ 라벨 「관리 기능 비활성」은 D-107 조건 5 의 다섯 라벨 밖이다(예외) — 「승인 대기」 라벨을 더할지 팀장 확인.
⬜ 다시 열 때 — 목록 · 상세 템플릿(`admin/docs/terms_list.html` · `terms_detail.html`)과 종전 조회 코드(git `fd3623a` 이전)가 남아 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

router = APIRouter(prefix="/terms")

LABEL = "관리 기능 비활성"
CLOSED = {
    "page_title": "약관 관리",
    "label": LABEL,
    "decision": "관리자 약관 관리 화면 닫힘",
    "why": [
        "약관 등록 · 수정 기능과 운영 절차가 승인 대기 중이에요.",
        "이 화면에서는 약관 버전 조회 · 등록 · 수정 기능을 제공하지 않아요.",
        "가입 화면의 약관 동의는 그대로 동작해요.",
    ],
    "needs": ["관리자 약관 쓰기 범위와 운영 절차 승인 (팀장)"],
    "alt": [],
}


@router.get("", response_class=HTMLResponse)
def terms_list(request: Request) -> HTMLResponse:
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})


@router.get("/{term_id}", response_class=HTMLResponse)
def terms_detail(request: Request, term_id: str) -> HTMLResponse:  # noqa: ARG001
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})
