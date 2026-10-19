"""app/routers/admin_enterprise.py — 회원관리(기업 회원) 화면 · **비활성 + 사유** · 소유자 **psj** (병렬작업 계약 §5)

🔄 2026-10-20 — **닫은 화면이다** (D-260 ④ · D-107). 기업 표(`enterprise`)는 만들지 않기로 했다 — 기업 단위
   계정 · 사업자 인증은 검증 수단이 없고, 회원은 `user_account.org`(소속 자유 기재 · FK 아님)까지만 둔다(D-260 ②).
   종전 더미(목업 `ENTERPRISES_V22` — 사업자번호 형식 값)를 지우고 사유 라벨 `외부 감사 전` 화면만 그린다.
   🚨 입력 요소 · POST 를 두지 않는다 (D-107 조건 1).

⬜ **되살릴 때** — `docs/psj/notes/닫힌_관리자화면_되살리기.md`. 화면 구조는
   `admin/members/enterprise_list.html` · `enterprise_detail.html` 에 남겨 두었고, 더미 · 라우터는 git 기록(`653974b`)에 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/enterprise` 다 — `/admin/enterprise`, `/admin/enterprise/{id}` 가 된다.
router = APIRouter(prefix="/enterprise")

LABEL = "외부 감사 전"

CLOSED = {
    "page_title": "기업 회원",
    "label": LABEL,
    "decision": "D-260 ④ · D-107",
    "why": [
        "사업자 · 법인 정보를 검증할 수단이 없어요 — 사업자번호 · 대표자명을 받아도 진위를 확인할 수 없어요 (D-104).",
        "요금제 · 결제가 없어 기업 단위로 묶을 이유가 아직 없어요 (D-69).",
        "회원의 소속은 자유 기재(`user_account.org`)까지만 받아요 — 회원 목록에서 볼 수 있어요 (D-260 ②).",
    ],
    "needs": [
        "사업자 진위 확인 수단 — 외부 감사 또는 확인 API (외부 의존 판정)",
        "기업 단위로 무엇이 달라지는지 — 요금제 · 구성원 권한 (D-69 · D-66 개정)",
        "기업 표(`enterprise`) 스키마와 `user_account.org` 정규화 여부 (팀장)",
    ],
}


@router.get("", response_class=HTMLResponse)
def enterprise_list(request: Request) -> HTMLResponse:
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})


@router.get("/{enterprise_id}", response_class=HTMLResponse)
def enterprise_detail(request: Request, enterprise_id: str) -> HTMLResponse:  # noqa: ARG001
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})
