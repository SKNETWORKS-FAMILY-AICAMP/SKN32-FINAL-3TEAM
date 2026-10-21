"""app/routers/admin_members.py — 회원관리(회원 목록 · 상세) 화면 · 소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_board.py · admin_cs.py 와 같은 패턴). 붙이는
   자리는 `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 비활성화 등 상태 변경은 화면에 없다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **`user_account` 표를 읽는다** (alembic `0017_ops_tables` · `app/models.py` `UserAccount` · D-260 ②).
   서비스 가입 · 로그인(`app/routers/user.py`)이 쓰는 표다. `app_account`(관리자 로그인)와 다른 표다.
   ★ 못 읽으면 빈 화면 + 안내다 — 0건이라 말하지 않는다 (`admin_dbread` · D-72).
   🚨 표에 **회원 유형 · 요금제 · 결제 칸이 없다**(D-66 · D-69 · `UserAccount` docstring) — 종전 더미의 유형 ·
      플랜 필터와 결제 이력 예시는 지웠다. 대응하는 칸 없이 그리면 없는 사실을 만든다.
   🚨 상태는 저장하지 않고 **계산한다**(`UserAccount` docstring) — 비활성(`disabled_at`) > 휴면(마지막 로그인 ·
      없으면 가입이 `DORMANT_DAYS` 보다 오래됨) > 활성.
   🔴 이용 내역은 **건수만** 센다 — 검수 원문은 읽지 않는다(D-76 열람 경계). 검수 이력은 사용자가 보관에
      동의한 것만 저장되므로(D-96) 「보관 동의한 검수」 건수다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.models import TICKET_STATUSES
from app.routers import admin_dbread as db
from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/members` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/members`, `/admin/members/{id}` 가 된다.
router = APIRouter(prefix="/members")

PAGE_SIZE = 20
_MAX_Q = 80

#: 휴면으로 보는 기준(일) — `[임의]` 화면 표시 기준이다. 계정을 막지 않는다
DORMANT_DAYS = 365

MEMBER_STATUSES = ("active", "dormant", "disabled")
_STATUS_LABEL = {"active": "활성", "dormant": "휴면", "disabled": "비활성"}

#: 상태 계산식 — 목록 · 필터 · 상세가 같은 식을 쓴다 (D-99). 값은 파라미터로 넘긴다
_STATUS_SQL = (
    "CASE WHEN u.disabled_at IS NOT NULL THEN 'disabled' "
    "WHEN coalesce(u.last_login_at, u.created_at) < now() - make_interval(days => %s) "
    "THEN 'dormant' ELSE 'active' END"
)

_SELECT = f"""
SELECT u.id::text AS id, u.email, u.name, u.org, u.created_at, u.last_login_at, u.disabled_at,
       u.terms_version, u.terms_agreed_at, u.consent_history_at, u.consent_improve_at,
       u.email_verified_at, {_STATUS_SQL} AS status
FROM user_account u
"""


def view(r: dict) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "email": r["email"],
        "company": r["org"],
        "joined": db.fmt_dt(r["created_at"], "%Y.%m.%d"),
        "last_seen": db.fmt_dt(r["last_login_at"]) if r["last_login_at"] else "로그인 기록 없음",
        "status": r["status"],
        "disabled_at": db.fmt_dt(r["disabled_at"]),
        "terms_version": r["terms_version"],
        "terms_agreed_at": db.fmt_dt(r["terms_agreed_at"]),
        "consent_history": db.fmt_dt(r["consent_history_at"]) if r["consent_history_at"] else None,
        "consent_improve": db.fmt_dt(r["consent_improve_at"]) if r["consent_improve_at"] else None,
        "email_verified": r["email_verified_at"] is not None,
    }


@router.get("", response_class=HTMLResponse)
def member_list(request: Request) -> HTMLResponse:
    """회원 목록 — 읽기 전용 · 최근 가입 먼저."""
    actor = require_governor(request)
    qp = request.query_params
    q = (qp.get("q") or "").strip()[:_MAX_Q]
    status = qp.get("status") if qp.get("status") in MEMBER_STATUSES else None
    page = db.clean_page(qp.get("page"))

    where: list[str] = []
    params: list[object] = []
    if q:
        where.append(
            r"(u.name ILIKE %s ESCAPE '\' OR u.email ILIKE %s ESCAPE '\' OR u.org ILIKE %s ESCAPE '\')"
        )
        params += [db.like_param(q)] * 3
    if status:
        where.append(f"{_STATUS_SQL} = %s")
        params += [DORMANT_DAYS, status]
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    source, out = db.run(
        [(f"SELECT count(*) AS n FROM user_account u {where_sql}", params)],  # noqa: S608 — 고정 조각만
        what="members.count",
    )
    rows: list[dict] = []
    total: int | None = None
    if source == "db":
        total = out[0][0]["n"]
        page = min(page, db.page_count(total, PAGE_SIZE))
        source, out = db.run(
            [
                (
                    f"{_SELECT} {where_sql} ORDER BY u.created_at DESC LIMIT %s OFFSET %s",  # noqa: S608
                    [DORMANT_DAYS, *params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
                )
            ],
            what="members.list",
        )
        rows = [view(r) for r in out[0]] if source == "db" else []

    return templates.TemplateResponse(
        request,
        "admin/members/list.html",
        {
            "actor": actor,
            "source": source,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": db.page_count(total or 0, PAGE_SIZE),
            "q": q,
            "status": status or "",
            "statuses": MEMBER_STATUSES,
            "status_label": _STATUS_LABEL,
            "dormant_days": DORMANT_DAYS,
        },
    )


@router.get("/{member_id}", response_class=HTMLResponse)
def member_detail(request: Request, member_id: str) -> HTMLResponse:
    """회원 상세 — 계정 · 동의 · 이용 건수 · 문의. 읽기 전용."""
    actor = require_governor(request)
    mid = member_id[:64]
    source, out = db.run(
        [
            (f"{_SELECT} WHERE u.id::text = %s", [DORMANT_DAYS, mid]),  # noqa: S608
            (
                "SELECT count(*) AS sentences, count(DISTINCT j.doc_id) AS requests, "
                "count(*) FILTER (WHERE j.judged_at >= date_trunc('month', now())) AS month, "
                "max(j.judged_at) AS last_at "
                "FROM judgment j JOIN work_doc w ON w.id = j.doc_id WHERE w.owner_id::text = %s",
                [mid],
            ),
            (
                "SELECT id::text AS id, created_at, title, status FROM ticket "
                "WHERE requester_id::text = %s ORDER BY created_at DESC LIMIT 10",
                [mid],
            ),
        ],
        what="members.detail",
    )
    row = view(out[0][0]) if source == "db" and out[0] else None
    if source == "db" and row is None:
        raise HTTPException(status_code=404)
    usage = None
    tickets: list[dict] = []
    if row is not None:
        u = out[1][0]
        usage = {
            "requests": u["requests"],
            "sentences": u["sentences"],
            "month": u["month"],
            "last_at": db.fmt_dt(u["last_at"]),
        }
        tickets = [
            {
                "id": t["id"],
                "at": db.fmt_dt(t["created_at"], "%Y.%m.%d"),
                "title": t["title"],
                "status": TICKET_STATUSES.get(t["status"], t["status"]),
            }
            for t in out[2]
        ]
    return templates.TemplateResponse(
        request,
        "admin/members/detail.html",
        {
            "actor": actor,
            "source": source,
            "row": row,
            "usage": usage,
            "tickets": tickets,
            "status_label": _STATUS_LABEL,
            "dormant_days": DORMANT_DAYS,
        },
    )
