"""app/routers/admin_members.py — 회원관리(회원 목록·상세) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_board.py·admin_cs.py 와 같은 패턴). 붙이는
   자리는 `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 상태 변경 등은 화면에 없다(목업에도 없음).
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **회원(개인·인플루언서·기업) 을 담는 테이블 자체가 없다** — `app_account` 는 `governor`
   (관리자) 로그인 전용 테이블이라 다른 개념이다 (alembic 0012_app_account.py 참고).
   서비스 쪽 회원가입·인증 기능(ksr·lse 담당)이 스키마와 함께 먼저 생겨야 한다. 그래서
   admin_board.py·admin_cs.py 와 같은 이유로 DB 조회를 시도하지 않고 **더미로만** 그린다.
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `MEMBERS_V22` 배열·`member-detail` 뷰 구조를 그대로
   따른다 — 나중에 실데이터 붙을 때 필드명이 어긋나지 않게. 결제 이력은 목업에서도
   `member-detail` 안에 하드코딩된 예시 1~2행뿐이라 여기서도 상세 화면에 예시로만 둔다
   (결제 이력을 담는 테이블도 아직 없다).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/members` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/members`, `/admin/members/{id}` 가 된다.
router = APIRouter(prefix="/members")

PAGE_SIZE = 20

MEMBER_TYPES = ("일반 회원", "인플루언서", "기업 대표자", "기업 구성원")
MEMBER_PLANS = ("Basic", "Pro", "Enterprise")
MEMBER_STATUSES = ("active", "dormant")
_STATUS_LABEL = {"active": "활성", "dormant": "휴면"}

# ─────────────────────────────────────────────────────────────
# 더미 — 회원 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 MEMBERS_V22 배열을 그대로 옮겨온 것 — 실제 회원
# 정보가 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────
_DUMMY_MEMBERS: list[dict] = [
    {
        "id": "m1", "name": "김민아", "email": "mina@future-ad.co",
        "type": "기업 대표자", "company": "(주)미래광고", "role": "대표자",
        "channel": None, "followers": None,
        "plan": "Enterprise", "joined": "2026.03.12", "last_seen": "오늘 10:32",
        "status": "active",
    },
    {
        "id": "m2", "name": "이재현", "email": "jh.lee@gmail.com",
        "type": "인플루언서", "company": None, "role": None,
        "channel": "@jh_daily", "followers": "128,400",
        "plan": "Pro", "joined": "2026.05.08", "last_seen": "오늘 10:21",
        "status": "active",
    },
    {
        "id": "m3", "name": "박서윤", "email": "sy.park@brand1.kr",
        "type": "기업 구성원", "company": "브랜드원", "role": "구성원",
        "channel": None, "followers": None,
        "plan": "Enterprise", "joined": "2026.01.20", "last_seen": "오늘 10:08",
        "status": "active",
    },
    {
        "id": "m4", "name": "최하늘", "email": "sky.choi@naver.com",
        "type": "일반 회원", "company": None, "role": None,
        "channel": None, "followers": None,
        "plan": "Basic", "joined": "2026.07.15", "last_seen": "어제 18:45",
        "status": "active",
    },
    {
        "id": "m5", "name": "정은서", "email": "es.jung@kakao.com",
        "type": "인플루언서", "company": None, "role": None,
        "channel": "@eunseo_beauty", "followers": "72,900",
        "plan": "Pro", "joined": "2026.08.01", "last_seen": "어제 14:22",
        "status": "active",
    },
    {
        "id": "m6", "name": "한도윤", "email": "dy.han@test.com",
        "type": "일반 회원", "company": None, "role": None,
        "channel": None, "followers": None,
        "plan": "Pro", "joined": "2026.04.22", "last_seen": "3일 전",
        "status": "active",
    },
    {
        "id": "m7", "name": "송유진", "email": "yj.song@outlook.com",
        "type": "일반 회원", "company": None, "role": None,
        "channel": None, "followers": None,
        "plan": "Basic", "joined": "2026.06.30", "last_seen": "7일 전",
        "status": "dormant",
    },
    {
        "id": "m8", "name": "장우진", "email": "wj.jang@foodmkt.co",
        "type": "기업 대표자", "company": "푸드마켓", "role": "대표자",
        "channel": None, "followers": None,
        "plan": "Enterprise", "joined": "2025.11.05", "last_seen": "오늘 09:15",
        "status": "active",
    },
]

# 결제 이력도 담는 테이블이 없다 — 목업처럼 플랜 기준 금액만 계산해서 예시로 보여준다.
_PLAN_PRICE = {"Enterprise": "990,000원", "Pro": "49,000원", "Basic": "19,000원"}


def _clean_page(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1


def _clean_choice(value: str | None, allowed: tuple[str, ...]) -> str | None:
    return value if value in allowed else None


@router.get("", response_class=HTMLResponse)
def member_list(request: Request) -> HTMLResponse:
    """회원 목록 — 읽기 전용. 회원 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    q = (qp.get("q") or "").strip()
    member_type = _clean_choice(qp.get("type"), MEMBER_TYPES)
    plan = _clean_choice(qp.get("plan"), MEMBER_PLANS)
    status = _clean_choice(qp.get("status"), MEMBER_STATUSES)
    page = _clean_page(qp.get("page"))

    rows = _DUMMY_MEMBERS
    if q:
        needle = q.lower()
        rows = [
            r for r in rows
            if needle in r["name"].lower()
            or needle in r["email"].lower()
            or (r["company"] and needle in r["company"].lower())
        ]
    if member_type:
        rows = [r for r in rows if r["type"] == member_type]
    if plan:
        rows = [r for r in rows if r["plan"] == plan]
    if status:
        rows = [r for r in rows if r["status"] == status]

    total = len(rows)
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start : start + PAGE_SIZE]
    pages = max(1, -(-total // PAGE_SIZE))

    return templates.TemplateResponse(
        request,
        "admin/members/list.html",
        {
            "actor": actor,
            "rows": page_rows,
            "total": total,
            "page": page,
            "pages": pages,
            "q": q,
            "member_type": member_type or "",
            "plan": plan or "",
            "status": status or "",
            "types": MEMBER_TYPES,
            "plans": MEMBER_PLANS,
            "statuses": MEMBER_STATUSES,
            "status_label": _STATUS_LABEL,
        },
    )


@router.get("/{member_id}", response_class=HTMLResponse)
def member_detail(request: Request, member_id: str) -> HTMLResponse:
    """회원 상세 — 읽기 전용. 기본 정보·이용 내역(더미 수치)·결제 이력(예시)을 한 화면에."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_MEMBERS if r["id"] == member_id), None)
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/members/detail.html",
        {
            "actor": actor,
            "row": row,
            "status_label": _STATUS_LABEL,
            "price": _PLAN_PRICE.get(row["plan"], "-"),
        },
    )
