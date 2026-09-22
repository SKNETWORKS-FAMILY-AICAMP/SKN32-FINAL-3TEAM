"""app/routers/admin_review_docs.py — 문서관리(심사 서류) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_members.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 목업은 "보기" 버튼이 모달을 띄워 승인·반려를 그 자리에서 처리하지만
   (`showDocReview`), 여기는 스크립트 없이(CSP `script-src 'self'`) 별도 상세 페이지로
   만들고 승인·반려는 disabled 뼈대만 둔다 — 다른 화면들과 같은 패턴이다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **심사 서류(제출 파일) 를 담는 테이블 자체가 없다** — 승인 심사(admin_signup_review.py)
   상세 화면에 이미 서류 더미가 있지만, 이 화면은 그것과 별개로 **전체 제출 서류를
   한곳에서 훑어보는 목록**이다(목업에도 "심사 서류"·"승인 심사"가 별도 메뉴로 있다).
   서비스 쪽 가입·서류 제출 기능(ksr·lse 담당)이 스키마와 함께 먼저 생겨야 한다.
   그래서 DB 조회를 시도하지 않고 **더미로만** 그린다.
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `review-docs` 뷰(10594번 줄대) 하드코딩 배열 구조를
   그대로 따른다. "파일 보기"는 실제로 파일을 열지 못하므로 여기서는 파일명만 표시한다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/review-docs` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/review-docs`, `/admin/review-docs/{doc_id}` 가 된다.
router = APIRouter(prefix="/review-docs")

PAGE_SIZE = 20
DOC_TYPES = ("인플루언서", "기업")
DOC_STATUSES = ("pending", "approved", "rejected")
_STATUS_LABEL = {"pending": "심사 대기", "approved": "승인", "rejected": "반려"}

# ─────────────────────────────────────────────────────────────
# 더미 — 심사 서류 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 review-docs 뷰 하드코딩 배열을 그대로 옮겨온 것 —
# 실제 제출 서류가 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────
_DUMMY_DOCS: list[dict] = [
    {
        "id": 1,
        "date": "08.28",
        "who": "(주)헬스푸드",
        "type": "기업",
        "name": "사업자등록증",
        "file": "사업자등록증.pdf",
        "size": "1.2MB",
        "status": "pending",
    },
    {
        "id": 2,
        "date": "08.28",
        "who": "(주)헬스푸드",
        "type": "기업",
        "name": "광고심의확인서",
        "file": "광고심의확인서.pdf",
        "size": "840KB",
        "status": "pending",
    },
    {
        "id": 3,
        "date": "08.27",
        "who": "이서은",
        "type": "인플루언서",
        "name": "인스타그램 인증",
        "file": "ig_verify_seoeun.pdf",
        "size": "320KB",
        "status": "pending",
    },
    {
        "id": 4,
        "date": "08.27",
        "who": "(주)코스메틱허브",
        "type": "기업",
        "name": "사업자등록증",
        "file": "사업자등록증_코스메틱.pdf",
        "size": "1.1MB",
        "status": "pending",
    },
    {
        "id": 5,
        "date": "08.27",
        "who": "김도현",
        "type": "인플루언서",
        "name": "유튜브 채널 인증",
        "file": "yt_channel_cert.pdf",
        "size": "450KB",
        "status": "approved",
    },
    {
        "id": 6,
        "date": "08.26",
        "who": "뷰티스타 주식회사",
        "type": "기업",
        "name": "사업자등록증",
        "file": "사업자등록증_뷰티.pdf",
        "size": "980KB",
        "status": "approved",
    },
    {
        "id": 7,
        "date": "08.26",
        "who": "박지민",
        "type": "인플루언서",
        "name": "블로그 인증",
        "file": "blog_verify_jimin.pdf",
        "size": "210KB",
        "status": "approved",
    },
    {
        "id": 8,
        "date": "08.26",
        "who": "(주)스마트팜",
        "type": "기업",
        "name": "제조허가증",
        "file": "제조허가증.pdf",
        "size": "2.1MB",
        "status": "approved",
    },
    {
        "id": 9,
        "date": "08.25",
        "who": "이재현",
        "type": "인플루언서",
        "name": "인스타그램 인증",
        "file": "ig_verify_jaehyun.pdf",
        "size": "280KB",
        "status": "rejected",
    },
    {
        "id": 10,
        "date": "08.25",
        "who": "일반식품(주)",
        "type": "기업",
        "name": "사업자등록증",
        "file": "사업자등록증_일반.pdf",
        "size": "1.3MB",
        "status": "rejected",
    },
]


def _clean_page(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1


def _clean_choice(value: str | None, allowed: tuple[str, ...]) -> str | None:
    return value if value in allowed else None


@router.get("", response_class=HTMLResponse)
def review_docs_list(request: Request) -> HTMLResponse:
    """심사 서류 목록 — 읽기 전용. 서류 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    doc_type = _clean_choice(qp.get("type"), DOC_TYPES)
    status = _clean_choice(qp.get("status"), DOC_STATUSES)
    page = _clean_page(qp.get("page"))

    rows = _DUMMY_DOCS
    if doc_type:
        rows = [r for r in rows if r["type"] == doc_type]
    if status:
        rows = [r for r in rows if r["status"] == status]

    total = len(rows)
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start : start + PAGE_SIZE]
    pages = max(1, -(-total // PAGE_SIZE))

    counts = {
        "전체": len(_DUMMY_DOCS),
        "인플루언서": sum(1 for r in _DUMMY_DOCS if r["type"] == "인플루언서"),
        "기업": sum(1 for r in _DUMMY_DOCS if r["type"] == "기업"),
    }

    return templates.TemplateResponse(
        request,
        "admin/docs/review_docs_list.html",
        {
            "actor": actor,
            "rows": page_rows,
            "total": total,
            "page": page,
            "pages": pages,
            "doc_type": doc_type or "",
            "status": status or "",
            "types": DOC_TYPES,
            "statuses": DOC_STATUSES,
            "status_label": _STATUS_LABEL,
            "counts": counts,
        },
    )


@router.get("/{doc_id}", response_class=HTMLResponse)
def review_doc_detail(request: Request, doc_id: int) -> HTMLResponse:
    """심사 서류 상세 — 읽기 전용. 승인·반려는 disabled 뼈대."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_DOCS if r["id"] == doc_id), None)
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/docs/review_doc_detail.html",
        {"actor": actor, "row": row, "status_label": _STATUS_LABEL},
    )
