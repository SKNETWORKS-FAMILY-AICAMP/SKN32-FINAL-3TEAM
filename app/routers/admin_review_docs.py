"""app/routers/admin_review_docs.py — 문서관리(심사 서류) 화면 · **비활성 + 사유** · 소유자 **psj** (병렬작업 계약 §5)

🔄 2026-10-20 — **닫은 화면이다** (D-260 ⑤ · D-107 조건 1). 신원 서류는 **파일도 상태 칸도 두지 않는다** —
   파일이 한 번 저장되면 보관 · 파기 책임을 지고, 받지 않은 서류에 「제출함」 칸을 두면 그 값이 지어낸 데이터다.
   종전 더미(목업 review-docs 배열)를 지우고 사유 라벨 `외부 감사 전` 화면만 그린다.
   🔴 **이 화면만은 되살릴 때도 가장 무겁다** — 파일 선택 요소(`<input type="file">`)를 만드는 순간 신원 서류를 받는
      제품이 된다 (D-107 트레이드오프). D-107 조건 1 을 개정하는 판정이 먼저다.

⬜ **되살릴 때** — `docs/psj/notes/닫힌_관리자화면_되살리기.md`. 화면 구조는
   `admin/docs/review_docs_list.html` · `review_doc_detail.html` 에 남겨 두었고, 더미 · 라우터는 git 기록(`653974b`)에 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/review-docs` 다 — `/admin/review-docs`, `/admin/review-docs/{id}` 가 된다.
router = APIRouter(prefix="/review-docs")

LABEL = "외부 감사 전"

CLOSED = {
    "page_title": "심사 서류",
    "label": LABEL,
    "decision": "D-260 ⑤ · D-107 조건 1",
    "why": [
        "신원 서류 파일을 받지 않아요 — 받는 순간 보관 · 파기 · 유출 책임이 생겨요 (D-107 조건 1).",
        "받지 않은 서류에 「제출함 · 승인」 상태를 두면 그 값이 지어낸 데이터가 돼요 (D-260 ⑤).",
        "서류를 요구하는 가입 심사 흐름 자체를 열지 않았어요 (D-260 ④).",
    ],
    "needs": [
        "D-107 조건 1(입력 · 파일 선택 없음) 개정 판정 — 이게 먼저예요",
        "파일 보관 위치 · 암호화 · 보관 기한 · 파기 절차 (D-129 · 개인정보 처리방침)",
        "가입 심사(`signup_review`)를 함께 여는 결정 (D-260 ④)",
        "서류 표 스키마 · 업로드 경로 · 관리자 쓰기 허용 목록 (팀장)",
    ],
}


@router.get("", response_class=HTMLResponse)
def review_docs_list(request: Request) -> HTMLResponse:
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})


@router.get("/{doc_id}", response_class=HTMLResponse)
def review_doc_detail(request: Request, doc_id: str) -> HTMLResponse:  # noqa: ARG001
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})
