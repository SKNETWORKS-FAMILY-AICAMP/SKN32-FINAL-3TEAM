"""app/routers/admin_signup_review.py — 회원관리(승인 심사) 화면 · **비활성 + 사유** · 소유자 **psj** (병렬작업 계약 §5)

🔄 2026-10-20 — **닫은 화면이다** (D-260 ④ · D-107). 가입 심사 표(`signup_review`)는 만들지 않기로 했다 —
   D-66 은 역할을 두지 않는다(「행동이 역할을 정한다」). **승인해도 켜 주는 권한이 없는** 심사 흐름은 실제 데이터가
   흘러도 가짜 절차다. 그래서 종전 더미(목업 `REVIEWS_V22` — 실재 도메인 이메일 · 사업자번호 형식 값)를 지우고
   사유 라벨 `외부 감사 전` 화면(`admin/_closed.html`)만 그린다.
   🚨 입력 요소 · POST 를 두지 않는다 (D-107 조건 1).

⬜ **되살릴 때** — `docs/psj/notes/닫힌_관리자화면_되살리기.md`. 화면 구조(목록 · 상세 템플릿)는
   `admin/members/signup_review.html` · `review_detail.html` 에 그대로 남겨 두었고, 더미 데이터 · 라우터는
   git 기록(커밋 `653974b` 의 이 파일)에 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/signup-review` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/signup-review`, `/admin/signup-review/{id}` 가 된다.
router = APIRouter(prefix="/signup-review")

#: 사유 라벨 — 🚨 D-107 조건 5 의 다섯 중 하나만 쓴다. 대시보드도 이 글자를 읽는다 (D-99)
LABEL = "외부 감사 전"

CLOSED = {
    "page_title": "승인 심사",
    "label": LABEL,
    "decision": "D-260 ④ · D-107",
    "why": [
        "가입 시 역할을 고르지 않아요 — 승인해도 켜 줄 권한이 없어 심사가 바꾸는 것이 없어요.",
        "인플루언서 · 기업 여부를 검증할 수단이 없어요 — 사업자번호 · 팔로워 수를 확인하려면 외부 감사가 먼저예요.",
        "신원 서류는 받지 않아요 — 파일을 받는 순간 보관 · 파기 책임이 생겨요.",
    ],
    "needs": [
        "승인이 무엇을 켜 주는지 — 역할 · 프로필 공개 권한 같은 결정",
        "검증 수단 — 외부 감사 또는 사업자 진위 확인 API (외부 의존 판정)",
        "가입 신청 표 스키마 · 마이그레이션 (팀장)",
        "승인 · 반려 쓰기 경로 — 관리자 쓰기 허용 목록 · CSRF · 쓰기 기록",
    ],
    "alt": [
        {
            "name": "회원 목록",
            "href": "/admin/members",
            "description": "현재 가입한 회원 정보와 계정 상태를 확인할 수 있어요",
        },
    ],
}


@router.get("", response_class=HTMLResponse)
def review_list(request: Request) -> HTMLResponse:
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})


@router.get("/{review_id}", response_class=HTMLResponse)
def review_detail(request: Request, review_id: str) -> HTMLResponse:  # noqa: ARG001 — 옛 링크가 깨지지 않게 같은 안내
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})
