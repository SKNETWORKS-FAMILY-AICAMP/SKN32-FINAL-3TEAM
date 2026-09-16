"""app/routers/admin_signup_review.py — 회원관리(승인 심사) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_members.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 승인·반려 버튼, 처리 사유 선택은 전부 `disabled` 뼈대다 — 실제
   처리(상태를 바꾸는 POST)는 아직 없다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **승인 심사(신청) 를 담는 테이블 자체가 없다** — 회원 테이블과 같은 이유다
   (admin_members.py 참고). 인플루언서·기업 가입 신청 기능(ksr·lse 담당)이 스키마와
   함께 먼저 생겨야 한다. 그래서 DB 조회를 시도하지 않고 **더미로만** 그린다.
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `REVIEWS_V22` 배열·`signup-review`/`review-detail`
   뷰(마지막에 덮어써진 v23·v24 최종본 — 제출 서류 체크리스트, 승인/반려 선택 UI) 구조를
   그대로 따른다. 제출 서류 확인 체크박스도 목업처럼 있지만 여기서는 읽기 전용이라
   전부 `disabled` 로 그린다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/signup-review` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/signup-review`, `/admin/signup-review/{id}` 가 된다.
router = APIRouter(prefix="/signup-review")

REVIEW_TYPES = ("인플루언서", "기업")
REVIEW_STATUSES = ("pending", "approved", "rejected")
_STATUS_LABEL = {"pending": "검토 대기", "approved": "승인", "rejected": "반려"}

# ─────────────────────────────────────────────────────────────
# 더미 — 승인 심사(가입 신청) 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로
# 바꾼다. 목업 app/static/mockup.html 의 REVIEWS_V22 배열을 그대로 옮겨온 것 — 실제
# 신청 정보가 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────
_DUMMY_REVIEWS: list[dict] = [
    {
        "id": "r1", "type": "인플루언서", "name": "윤채린", "email": "chaerin@naver.com",
        "date": "2026.08.28 09:42", "channel": "@chaerin_daily", "followers": "86,200",
        "category": "뷰티·라이프", "biz": None, "rep": None, "employees": None,
        "status": "pending",
        "docs": [
            {"name": "본인인증서.pdf", "kind": "본인 확인", "submitted": "2026.08.28"},
            {"name": "채널소유인증.png", "kind": "채널 소유 확인", "submitted": "2026.08.28"},
            {"name": "활동포트폴리오.pdf", "kind": "활동·광고 이력", "submitted": "2026.08.28"},
        ],
    },
    {
        "id": "r2", "type": "기업", "name": "(주)헬스푸드", "email": "biz@healthfood.co.kr",
        "date": "2026.08.28 08:15", "channel": None, "followers": None, "category": None,
        "biz": "120-81-88776", "rep": "정도현", "employees": "32명",
        "status": "pending",
        "docs": [
            {"name": "사업자등록증.pdf", "kind": "사업자 정보", "submitted": "2026.08.28"},
            {"name": "대표자재직증명서.pdf", "kind": "대표자 확인", "submitted": "2026.08.28"},
            {"name": "법인등기부등본.pdf", "kind": "법인 정보", "submitted": "2026.08.28"},
        ],
    },
    {
        "id": "r3", "type": "인플루언서", "name": "김도윤", "email": "doyoon@kakao.com",
        "date": "2026.08.27 17:30", "channel": "@doyoon_fit", "followers": "154,000",
        "category": "헬스·운동", "biz": None, "rep": None, "employees": None,
        "status": "pending",
        "docs": [
            {"name": "본인인증서.pdf", "kind": "본인 확인", "submitted": "2026.08.27"},
            {"name": "채널소유인증.png", "kind": "채널 소유 확인", "submitted": "2026.08.27"},
            {"name": "활동포트폴리오.pdf", "kind": "활동·광고 이력", "submitted": "2026.08.27"},
        ],
    },
    {
        "id": "r4", "type": "기업", "name": "브랜드팩토리", "email": "admin@brandfactory.kr",
        "date": "2026.08.27 15:20", "channel": None, "followers": None, "category": None,
        "biz": "211-88-12390", "rep": "한지수", "employees": "18명",
        "status": "pending",
        "docs": [
            {"name": "사업자등록증.pdf", "kind": "사업자 정보", "submitted": "2026.08.27"},
            {"name": "대표자재직증명서.pdf", "kind": "대표자 확인", "submitted": "2026.08.27"},
            {"name": "법인등기부등본.pdf", "kind": "법인 정보", "submitted": "2026.08.27"},
        ],
    },
]

_REJECT_REASONS_COMMON = ("서류 미비", "신청 정보 불일치", "중복 신청", "기타")
_REJECT_REASON_INFLUENCER = "활동 기준 미충족"
_REJECT_REASON_CORP = "업종 부적합"


def _clean_choice(value: str | None, allowed: tuple[str, ...]) -> str | None:
    return value if value in allowed else None


@router.get("", response_class=HTMLResponse)
def review_list(request: Request) -> HTMLResponse:
    """승인 심사 목록 — 읽기 전용. 가입 신청 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    review_type = _clean_choice(qp.get("type"), REVIEW_TYPES)

    rows = _DUMMY_REVIEWS
    if review_type:
        rows = [r for r in rows if r["type"] == review_type]

    pending = sum(1 for r in _DUMMY_REVIEWS if r["status"] == "pending")
    approved = sum(1 for r in _DUMMY_REVIEWS if r["status"] == "approved")
    rejected = sum(1 for r in _DUMMY_REVIEWS if r["status"] == "rejected")

    return templates.TemplateResponse(
        request,
        "admin/members/signup_review.html",
        {
            "actor": actor,
            "rows": rows,
            "review_type": review_type or "",
            "types": REVIEW_TYPES,
            "status_label": _STATUS_LABEL,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "total": len(_DUMMY_REVIEWS),
        },
    )


@router.get("/{review_id}", response_class=HTMLResponse)
def review_detail(request: Request, review_id: str) -> HTMLResponse:
    """승인 심사 상세 — 읽기 전용. 제출 서류 확인·승인/반려는 전부 disabled 뼈대."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_REVIEWS if r["id"] == review_id), None)
    if row is None:
        raise HTTPException(status_code=404)

    reject_reasons = list(_REJECT_REASONS_COMMON)
    reject_reasons.insert(
        -1,
        _REJECT_REASON_INFLUENCER if row["type"] == "인플루언서" else _REJECT_REASON_CORP,
    )

    return templates.TemplateResponse(
        request,
        "admin/members/review_detail.html",
        {
            "actor": actor,
            "row": row,
            "status_label": _STATUS_LABEL,
            "reject_reasons": reject_reasons,
        },
    )
