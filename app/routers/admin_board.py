"""app/routers/admin_board.py — 게시판관리(공지사항) 화면 · 소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 화면의 "새 공지 작성" · 수정 · 삭제 버튼은 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **`notice` 표를 읽는다** (alembic `0017_ops_tables` · `app/models.py` `Notice` · D-260 ①).
   사용자 화면의 알림(`app/routers/user.py`)이 읽는 것과 같은 표다. 종전 더미(목업 `_notices`)는 지웠다.
   ★ 못 읽으면 빈 화면 + 안내다 — 0건이라 말하지 않는다 (`admin_dbread` · D-72).
   🚨 분류 값은 `app/models.py` `NOTICE_CATEGORIES` 한 벌이다(표의 CHECK 와 같다 · D-99).
   🚨 상태는 저장하지 않는다(`Notice` docstring) — `hidden_at` · `starts_on` · `ends_on` 에서 계산한다:
      숨김 > 예정(시작 전) > 종료(끝난 뒤) > 게시중.
   ⬜ 공지를 쓰는 길(관리자 작성 폼)은 아직 없다 — 표에는 DB 에 직접 넣은 공지만 있다.

🔴 **FAQ 관리는 뺐다** — 목업 최종본(11648번 줄 대 NAV)엔 게시판관리에 FAQ 가 없다 (2026-09-16 사용자 확인).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.models import NOTICE_CATEGORIES
from app.routers import admin_dbread as db
from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/board` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/board/notices` 가 된다.
router = APIRouter(prefix="/board")

PAGE_SIZE = 20

_SELECT = """
SELECT n.id::text AS id, n.title, n.category, n.body, n.pinned, n.starts_on, n.ends_on,
       n.hidden_at, n.created_at, n.updated_at, a.display_name AS author
FROM notice n
LEFT JOIN app_account a ON a.id = n.author_id
"""


def _status(r: dict) -> str:
    today = db.today_kst()
    if r["hidden_at"] is not None:
        return "숨김"
    if r["starts_on"] is not None and r["starts_on"] > today:
        return "예정"
    if r["ends_on"] is not None and r["ends_on"] < today:
        return "종료"
    return "게시중"


def view(r: dict) -> dict:
    start = db.fmt_dt(r["starts_on"], "%m.%d") if r["starts_on"] else db.fmt_dt(r["created_at"], "%m.%d")
    end = db.fmt_dt(r["ends_on"], "%m.%d") if r["ends_on"] else "상시"
    return {
        "id": r["id"],
        "title": r["title"],
        "category": NOTICE_CATEGORIES.get(r["category"], r["category"]),
        "author": r["author"] or "-",
        "date": db.fmt_dt(r["created_at"], "%m.%d"),
        "updated": db.fmt_dt(r["updated_at"]),
        "period": f"{start} ~ {end}",
        "status": _status(r),
        "pinned": bool(r["pinned"]),
        "content": r["body"],
    }


@router.get("/notices", response_class=HTMLResponse)
def notice_list(request: Request) -> HTMLResponse:
    """공지사항 목록 — 읽기 전용 · 고정 공지 먼저, 그다음 최신순."""
    actor = require_governor(request)
    qp = request.query_params
    category = qp.get("category") if qp.get("category") in NOTICE_CATEGORIES else None
    page = db.clean_page(qp.get("page"))

    where_sql, params = ("WHERE n.category = %s", [category]) if category else ("", [])
    source, out = db.run(
        [(f"SELECT count(*) AS n FROM notice n {where_sql}", params)],  # noqa: S608 — 고정 조각만
        what="board.count",
    )
    rows: list[dict] = []
    total: int | None = None
    if source == "db":
        total = out[0][0]["n"]
        page = min(page, db.page_count(total, PAGE_SIZE))
        source, out = db.run(
            [
                (
                    f"{_SELECT} {where_sql} ORDER BY n.pinned DESC, n.created_at DESC "  # noqa: S608
                    "LIMIT %s OFFSET %s",
                    [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
                )
            ],
            what="board.list",
        )
        rows = [view(r) for r in out[0]] if source == "db" else []

    return templates.TemplateResponse(
        request,
        "admin/board/notices.html",
        {
            "actor": actor,
            "source": source,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": db.page_count(total or 0, PAGE_SIZE),
            "category": category or "",
            "categories": NOTICE_CATEGORIES,
        },
    )


@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: str) -> HTMLResponse:
    """공지사항 상세 — 읽기 전용. 수정 · 삭제 버튼은 뼈대만."""
    actor = require_governor(request)
    source, out = db.run(
        [(f"{_SELECT} WHERE n.id::text = %s", [notice_id[:64]])],  # noqa: S608
        what="board.detail",
    )
    row = view(out[0][0]) if source == "db" and out[0] else None
    if source == "db" and row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/board/notice_detail.html",
        {"actor": actor, "source": source, "row": row},
    )
