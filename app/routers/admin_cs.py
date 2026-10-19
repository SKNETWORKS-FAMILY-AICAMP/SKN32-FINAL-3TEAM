"""app/routers/admin_cs.py — CS문의(티켓 목록 · 상세) 화면 · 소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 상태 변경 · 담당자 배정 · 답변 폼은 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **`ticket` 표를 읽는다** (alembic `0017_ops_tables` · `app/models.py` `Ticket` · D-260 ③).
   사용자 고객센터(`/u/cs`)가 접수한 문의가 그대로 뜬다. 종전 더미(목업 `TICKETS` — 「결제」·「매칭」 분류)는 지웠다.
   ★ 못 읽으면 빈 화면 + 안내다 — 0건이라 말하지 않는다 (`admin_dbread` · D-72).
   🚨 분류 · 우선순위 · 상태의 값은 `app/models.py` `TICKET_*` 한 벌이다(표의 CHECK 와 같다 · D-99). 쿼리 값은 저장 코드다.
   🔴 문의에는 판정 원문 · 판정 id 칸이 없다(D-76 열람 경계) — 이 화면도 문의 본문만 보인다.
   표시 번호(`TK-…`)는 저장하지 않는다 — `created_at` 과 id 앞자리로 만든다(`Ticket` docstring).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.models import TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_STATUSES
from app.routers import admin_dbread as db
from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/cs` 다 — `admin_router`(prefix `/admin`) 아래에 매달려 `/admin/cs/tickets` 가 된다.
router = APIRouter(prefix="/cs")

PAGE_SIZE = 20

_SELECT = """
SELECT t.id::text AS id, t.created_at, t.category, t.title, t.body, t.priority, t.status,
       t.reply, t.closed_at, t.expires_at,
       u.name AS who, u.email AS who_email, a.display_name AS owner
FROM ticket t
JOIN user_account u ON u.id = t.requester_id
LEFT JOIN app_account a ON a.id = t.assignee_id
"""

_COUNTS = """
SELECT count(*) AS total,
       count(*) FILTER (WHERE status = 'open') AS open,
       count(*) FILTER (WHERE status = 'in_progress') AS in_progress,
       count(*) FILTER (WHERE priority = 'urgent' AND status <> 'closed') AS urgent
FROM ticket
"""


def _clean_choice(value: str | None, allowed: dict[str, str]) -> str | None:
    return value if value in allowed else None


def view(r: dict) -> dict:
    """표의 한 행 → 화면 글자. 라벨은 `TICKET_*` 에서 찾는다."""
    return {
        "id": r["id"],
        "no": "TK-" + db.fmt_dt(r["created_at"], "%Y%m%d") + "-" + r["id"][:4].upper(),
        "at": db.fmt_dt(r["created_at"], "%m.%d %H:%M"),
        "at_full": db.fmt_dt(r["created_at"]),
        "who": r["who"],
        "who_email": r["who_email"],
        "type": TICKET_CATEGORIES.get(r["category"], r["category"]),
        "title": r["title"],
        "content": r["body"],
        "reply": r["reply"],
        "priority_code": r["priority"],
        "priority": TICKET_PRIORITIES.get(r["priority"], r["priority"]),
        "status_code": r["status"],
        "status": TICKET_STATUSES.get(r["status"], r["status"]),
        "owner": r["owner"] or "미배정",
        "closed_at": db.fmt_dt(r["closed_at"]),
        "expires_at": db.fmt_dt(r["expires_at"], "%Y.%m.%d"),
    }


def _counts(row: dict | None) -> dict[str, int | None]:
    if row is None:
        return {"total": None, "open": None, "in_progress": None, "urgent": None}
    return {k: row[k] for k in ("total", "open", "in_progress", "urgent")}


def recent(status: str | None, limit: int = 5) -> dict:
    """최근 문의 몇 건 + 건수 — 운영 대시보드(`/admin/`)가 쓴다. 같은 SQL · 같은 라벨 (D-99)."""
    where, params = ("WHERE t.status = %s", [status]) if status else ("", [])
    source, out = db.run(
        [
            (f"{_SELECT} {where} ORDER BY t.created_at DESC LIMIT %s", [*params, limit]),  # noqa: S608
            (_COUNTS, []),
        ],
        what="cs.recent",
    )
    if source != "db":
        return {"source": source, "rows": [], "counts": _counts(None)}
    return {"source": source, "rows": [view(r) for r in out[0]], "counts": _counts(out[1][0])}


@router.get("/tickets", response_class=HTMLResponse)
def ticket_list(request: Request) -> HTMLResponse:
    """CS 티켓 목록 — 읽기 전용 · 최신순."""
    actor = require_governor(request)
    qp = request.query_params
    ticket_type = _clean_choice(qp.get("type"), TICKET_CATEGORIES)
    priority = _clean_choice(qp.get("priority"), TICKET_PRIORITIES)
    status = _clean_choice(qp.get("status"), TICKET_STATUSES)
    page = db.clean_page(qp.get("page"))

    where: list[str] = []
    params: list[object] = []
    for col, val in (("t.category", ticket_type), ("t.priority", priority), ("t.status", status)):
        if val:
            where.append(f"{col} = %s")
            params.append(val)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    source, out = db.run(
        [
            (f"SELECT count(*) AS n FROM ticket t {where_sql}", params),  # noqa: S608 — 고정 조각만
            (_COUNTS, []),
        ],
        what="cs.count",
    )
    rows: list[dict] = []
    total: int | None = None
    counts = _counts(None)
    if source == "db":
        total = out[0][0]["n"]
        counts = _counts(out[1][0])
        page = min(page, db.page_count(total, PAGE_SIZE))
        source, out = db.run(
            [
                (
                    f"{_SELECT} {where_sql} ORDER BY t.created_at DESC LIMIT %s OFFSET %s",  # noqa: S608
                    [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
                )
            ],
            what="cs.list",
        )
        rows = [view(r) for r in out[0]] if source == "db" else []

    return templates.TemplateResponse(
        request,
        "admin/cs/tickets.html",
        {
            "actor": actor,
            "source": source,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": db.page_count(total or 0, PAGE_SIZE),
            "ticket_type": ticket_type or "",
            "priority": priority or "",
            "status": status or "",
            "types": TICKET_CATEGORIES,
            "priorities": TICKET_PRIORITIES,
            "statuses": TICKET_STATUSES,
            "counts": counts,
        },
    )


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(request: Request, ticket_id: str) -> HTMLResponse:
    """CS 티켓 상세 — 읽기 전용. 상태 변경 · 답변 작성 폼은 뼈대만."""
    actor = require_governor(request)
    source, out = db.run(
        [(f"{_SELECT} WHERE t.id::text = %s", [ticket_id[:64]])],  # noqa: S608
        what="cs.detail",
    )
    row = view(out[0][0]) if source == "db" and out[0] else None
    # ★ 404 는 읽었는데 없을 때만 — 못 읽었으면 안내를 그린다 (D-188)
    if source == "db" and row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/cs/ticket_detail.html",
        {"actor": actor, "source": source, "row": row, "statuses": TICKET_STATUSES},
    )
