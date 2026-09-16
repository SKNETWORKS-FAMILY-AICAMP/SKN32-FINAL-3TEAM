"""app/routers/admin_cs.py — CS문의(티켓 목록) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 상태 변경·담당자 배정 폼은 전부 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **`ticket` 테이블은 아직 없다** — DB 승인 요청조차 안 한 상태다. 그래서 DB 조회를
   시도하지 않고 **더미로만** 그린다 (admin_board.py 와 같은 이유).
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `TICKETS` 구조를 그대로 따른다 — 사용자 쪽 「CS 문의」
   화면이 접수한 티켓이 그대로 여기 뜨는 구조였다(목업 08 CS문의 화면 참고). 사용자 쪽
   티켓 접수 기능(ksr·lse 담당)이 먼저 생겨야 실데이터가 흐른다 — 이 화면은 그 전까지
   관리자 쪽 뼈대만 먼저 만든다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/cs` 다 — `admin_router`(prefix `/admin`) 아래에 매달려 `/admin/cs/tickets` 가 된다.
router = APIRouter(prefix="/cs")

PAGE_SIZE = 20

TICKET_TYPES = ("결제", "검수·카피생성", "매칭", "계정", "기타")
TICKET_PRIORITIES = ("긴급", "보통", "낮음")
TICKET_STATUSES = ("미처리", "처리중", "완료")

# ─────────────────────────────────────────────────────────────
# 더미 — ticket 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 TICKETS 배열 구조를 옮겨온 것 — 실제 문의 내용이 아니라
# 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────
_DUMMY_TICKETS: list[dict] = [
    {
        "id": "TK-2026091601",
        "at": "09.16 09:12",
        "who": "이서은",
        "type": "결제",
        "title": "Pro 플랜 결제가 중복으로 청구됐어요",
        "priority": "긴급",
        "status": "미처리",
        "owner": "미배정",
        "content": "9월 결제가 두 번 청구된 것 같습니다. 확인 부탁드려요.",
    },
    {
        "id": "TK-2026091502",
        "at": "09.15 16:40",
        "who": "김민준",
        "type": "검수·카피생성",
        "title": "판정 결과가 이전과 다르게 나와요",
        "priority": "보통",
        "status": "처리중",
        "owner": "박수진",
        "content": "동일한 문구인데 어제는 주의, 오늘은 위험으로 판정됐습니다.",
    },
    {
        "id": "TK-2026091403",
        "at": "09.14 11:05",
        "who": "정하윤",
        "type": "계정",
        "title": "비밀번호 재설정 메일이 안 와요",
        "priority": "낮음",
        "status": "완료",
        "owner": "김민수",
        "content": "재설정 메일을 요청했는데 30분째 안 옵니다.",
    },
    {
        "id": "TK-2026091304",
        "at": "09.13 14:22",
        "who": "최지호",
        "type": "매칭",
        "title": "인플루언서 매칭이 하루째 안 돼요",
        "priority": "보통",
        "status": "미처리",
        "owner": "미배정",
        "content": "매칭 요청 후 하루가 지났는데 응답이 없습니다.",
    },
    {
        "id": "TK-2026091205",
        "at": "09.12 10:00",
        "who": "이서은",
        "type": "기타",
        "title": "기능 개선 제안드려요",
        "priority": "낮음",
        "status": "완료",
        "owner": "박수진",
        "content": "카피 생성 시 이전 결과와 비교하는 기능이 있으면 좋겠습니다.",
    },
]


def _clean_page(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1


def _clean_choice(value: str | None, allowed: tuple[str, ...]) -> str | None:
    return value if value in allowed else None


@router.get("/tickets", response_class=HTMLResponse)
def ticket_list(request: Request) -> HTMLResponse:
    """CS 티켓 목록 — 읽기 전용. `ticket` 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    ticket_type = _clean_choice(qp.get("type"), TICKET_TYPES)
    priority = _clean_choice(qp.get("priority"), TICKET_PRIORITIES)
    status = _clean_choice(qp.get("status"), TICKET_STATUSES)
    page = _clean_page(qp.get("page"))

    rows = _DUMMY_TICKETS
    if ticket_type:
        rows = [r for r in rows if r["type"] == ticket_type]
    if priority:
        rows = [r for r in rows if r["priority"] == priority]
    if status:
        rows = [r for r in rows if r["status"] == status]

    total = len(rows)
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start : start + PAGE_SIZE]
    pages = max(1, -(-total // PAGE_SIZE))

    counts = {
        "전체": len(_DUMMY_TICKETS),
        "미처리": sum(1 for r in _DUMMY_TICKETS if r["status"] == "미처리"),
        "처리중": sum(1 for r in _DUMMY_TICKETS if r["status"] == "처리중"),
        "긴급": sum(
            1 for r in _DUMMY_TICKETS if r["priority"] == "긴급" and r["status"] != "완료"
        ),
    }

    return templates.TemplateResponse(
        request,
        "admin/cs/tickets.html",
        {
            "actor": actor,
            "rows": page_rows,
            "total": total,
            "page": page,
            "pages": pages,
            "ticket_type": ticket_type or "",
            "priority": priority or "",
            "status": status or "",
            "types": TICKET_TYPES,
            "priorities": TICKET_PRIORITIES,
            "statuses": TICKET_STATUSES,
            "counts": counts,
        },
    )


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(request: Request, ticket_id: str) -> HTMLResponse:
    """CS 티켓 상세 — 읽기 전용. 상태 변경·답변 작성 폼은 뼈대만."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_TICKETS if r["id"] == ticket_id), None)
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/cs/ticket_detail.html",
        {"actor": actor, "row": row, "statuses": TICKET_STATUSES},
    )
