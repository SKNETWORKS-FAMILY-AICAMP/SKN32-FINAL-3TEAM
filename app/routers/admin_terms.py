"""app/routers/admin_terms.py — 문서관리(약관 관리) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_review_docs.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** "새 버전 등록" 버튼은 자리만 잡은 뼈대다 — action 없음. "이력" 도
   같은 상세 페이지 안에 읽기 전용으로 둔다(목업은 모달, 여기는 별도 페이지).
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **약관 버전을 담는 테이블 자체가 없다** — 심사 서류·회원 목록과 같은 이유
   (admin_review_docs.py 참고). 법무·정책 쪽 약관 관리 기능이 스키마와 함께 먼저
   생겨야 한다. 그래서 DB 조회를 시도하지 않고 **더미로만** 그린다.
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `terms` 뷰(10650번 줄대) 하드코딩 배열 구조를
   그대로 따른다. 이전 버전 이력은 목업에서도 `showTermsHistory()` 모달에 하드코딩된
   예시 1건뿐이라 여기서도 상세 화면에 그 정도로만 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/terms` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/terms`, `/admin/terms/{term_id}` 가 된다.
router = APIRouter(prefix="/terms")

# ─────────────────────────────────────────────────────────────
# 더미 — 약관 버전 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 terms 뷰 하드코딩 배열을 그대로 옮겨온 것 — 실제
# 약관 내용이 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────
_DUMMY_TERMS: list[dict] = [
    {
        "id": 1, "name": "서비스 이용약관", "version": "v3.2", "effective_date": "2026.08.01",
        "prev_version": "v3.1", "reason": "AI 판정 면책 조항 추가", "status": "시행 중",
    },
    {
        "id": 2, "name": "개인정보처리방침", "version": "v4.0", "effective_date": "2026.08.10",
        "prev_version": "v3.5", "reason": "개정 개인정보보호법 반영", "status": "시행 중",
    },
    {
        "id": 3, "name": "광고 검수 서비스 SLA", "version": "v2.1", "effective_date": "2026.07.15",
        "prev_version": "v2.0", "reason": "응답시간 보증 기준 변경", "status": "시행 중",
    },
    {
        "id": 4, "name": "기업 이용 계약서", "version": "v2.3", "effective_date": "2026.09.01",
        "prev_version": "v2.2", "reason": "기업 데이터 보호 조항 강화", "status": "예정",
    },
]


@router.get("", response_class=HTMLResponse)
def terms_list(request: Request) -> HTMLResponse:
    """약관 버전 목록 — 읽기 전용. 약관 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    return templates.TemplateResponse(
        request,
        "admin/docs/terms_list.html",
        {"actor": actor, "rows": _DUMMY_TERMS},
    )


@router.get("/{term_id}", response_class=HTMLResponse)
def terms_detail(request: Request, term_id: int) -> HTMLResponse:
    """약관 버전 상세(이력) — 읽기 전용."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_TERMS if r["id"] == term_id), None)
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/docs/terms_detail.html",
        {"actor": actor, "row": row},
    )
