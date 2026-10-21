"""app/routers/admin_board.py — 게시판관리(공지사항) 화면 · 소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **`notice` 표를 읽는다** (alembic `0017_ops_tables` · `app/models.py` `Notice` · D-260 ①).
   사용자 화면의 알림(`app/routers/user.py`)이 읽는 것과 같은 표다. 종전 더미(목업 `_notices`)는 지웠다.
   ★ 못 읽으면 빈 화면 + 안내다 — 0건이라 말하지 않는다 (`admin_dbread` · D-72).
   🚨 분류 값은 `app/models.py` `NOTICE_CATEGORIES` 한 벌이다(표의 CHECK 와 같다 · D-99).
   🚨 상태는 저장하지 않는다(`Notice` docstring) — `hidden_at` · `starts_on` · `ends_on` 에서 계산한다:
      숨김 > 예정(시작 전) > 종료(끝난 뒤) > 게시중.

🆕 2026-10-20 — **공지 작성 · 수정을 열었다** (D-260 ⑦ — 허용 목록 `POST /notices` · `POST /notices/{id}`).
   ★ 핸들러는 `require_governor` · `auth.csrf_ok` · `auth.audit` 를 본문에서 부른다 (`tests/test_auth_boundary.py`).
   ★ 작성자는 로그인한 계정(`app_account.initials` → `author_id`)이다 — 폼으로 받지 않는다.
   ⛔ **지우지 않는다** — 「숨김」(`hidden_at`)으로 내린다. 사용자 알림이 가리키던 공지가 사라지지 않게.
   ⛔ 길이는 자르지 않고 거부한다 (D-220).

🔴 **FAQ 관리는 뺐다** — 목업 최종본(11648번 줄 대 NAV)엔 게시판관리에 FAQ 가 없다 (2026-09-16 사용자 확인).
"""

from __future__ import annotations

import uuid
from datetime import date
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth
from app.formbody import read_capped
from app.models import NOTICE_CATEGORIES
from app.routers import admin_dbread as db
from app.routers import admin_dbwrite as dbw
from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/board` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/board/notices` 가 된다.
router = APIRouter(prefix="/board")

PAGE_SIZE = 20

#: `notice.title` String(200)
NOTICE_TITLE_MAX = 200
#: 본문은 `Text` 라 표에는 상한이 없다 — 화면 상한만 둔다 (자르지 않고 거부 · D-220)
NOTICE_BODY_MAX = 5000
#: 한글은 퍼센트 인코딩으로 글자당 9바이트 — 사용자 문의 폼(`_CS_BODY`)과 같은 여유
_FORM_BODY = NOTICE_BODY_MAX * 16

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
    start = (
        db.fmt_dt(r["starts_on"], "%m.%d")
        if r["starts_on"]
        else db.fmt_dt(r["created_at"], "%m.%d")
    )
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
        # 수정 폼이 채우는 원래 값
        "category_code": r["category"],
        "starts_on": r["starts_on"].isoformat() if r["starts_on"] else "",
        "ends_on": r["ends_on"].isoformat() if r["ends_on"] else "",
        "hidden": r["hidden_at"] is not None,
    }


def _form_of(row: dict | None) -> dict:
    """폼 기본값 — 새 공지면 빈 칸, 수정이면 지금 값."""
    if row is None:
        return {
            "title": "",
            "category": "",
            "body": "",
            "pinned": False,
            "starts_on": "",
            "ends_on": "",
            "hidden": False,
        }
    return {
        "title": row["title"],
        "category": row["category_code"],
        "body": row["content"],
        "pinned": row["pinned"],
        "starts_on": row["starts_on"],
        "ends_on": row["ends_on"],
        "hidden": row["hidden"],
    }


def _clean(form: dict[str, list[str]]) -> tuple[dict, dict | None, str | None]:
    """폼 → (다시 그릴 값, 저장할 값, 오류). 오류가 있으면 저장할 값은 `None`."""

    def one(key: str) -> str:
        return (form.get(key) or [""])[0]

    kept = {
        "title": one("title").strip(),
        "category": one("category"),
        "body": one("body").strip(),
        "pinned": one("pinned") == "1",
        "starts_on": one("starts_on").strip(),
        "ends_on": one("ends_on").strip(),
        "hidden": one("hidden") == "1",
    }
    if not kept["title"] or len(kept["title"]) > NOTICE_TITLE_MAX:
        return kept, None, f"제목을 1~{NOTICE_TITLE_MAX}자로 적어 주세요."
    if kept["category"] not in NOTICE_CATEGORIES:
        return kept, None, "분류를 골라 주세요."
    if not kept["body"] or len(kept["body"]) > NOTICE_BODY_MAX:
        return kept, None, f"내용을 1~{NOTICE_BODY_MAX:,}자로 적어 주세요."
    days: dict[str, date | None] = {}
    for key in ("starts_on", "ends_on"):
        try:
            days[key] = date.fromisoformat(kept[key]) if kept[key] else None
        except ValueError:
            return kept, None, "게시 기간 날짜를 다시 골라 주세요."
    if days["starts_on"] and days["ends_on"] and days["starts_on"] > days["ends_on"]:
        return kept, None, "게시 시작일이 종료일보다 늦어요."
    return kept, {**kept, **days}, None


async def _read_form(request: Request) -> dict[str, list[str]]:
    raw = await read_capped(request, _FORM_BODY, "공지가 너무 길어요")
    return parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)


def _save_error(source: str) -> tuple[str, int]:
    if source == "db":
        return (
            "저장하지 못했어요 — 로그인한 관리자 계정을 찾지 못했어요. 다시 로그인해 주세요.",
            403,
        )
    return (
        "저장하지 못했어요. DB 연결 상태를 확인한 뒤 다시 저장해 주세요. 쓴 내용은 그대로 두었어요.",
        503,
    )


@router.get("/notices", response_class=HTMLResponse)
def notice_list(request: Request) -> HTMLResponse:
    """공지사항 목록 — 고정 공지 먼저, 그다음 최신순."""
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


def _new_page(
    request: Request, actor: str, form: dict, error: str | None, code: int = 200
) -> HTMLResponse:
    return dbw.render_form(
        request,
        "admin/board/notice_form.html",
        {
            "actor": actor,
            "form": form,
            "error": error,
            "categories": NOTICE_CATEGORIES,
            "title_max": NOTICE_TITLE_MAX,
            "body_max": NOTICE_BODY_MAX,
        },
        code,
    )


# 🚨 `/notices/new` 는 `/notices/{notice_id}` 보다 **먼저** 매단다 — 뒤에 두면 「new」라는 id 의 상세로 간다
@router.get("/notices/new", response_class=HTMLResponse)
def notice_new(request: Request) -> HTMLResponse:
    """새 공지 작성 폼."""
    actor = require_governor(request)
    return _new_page(request, actor, _form_of(None), None)


@router.post("/notices")
async def notice_create(request: Request):  # noqa: ANN201 — 화면(오류) 또는 이동(PRG)
    """공지 등록 → 그 공지 상세로 (PRG). 작성자는 로그인한 계정이다."""
    actor = require_governor(request)
    form = await _read_form(request)
    if not auth.csrf_ok(*dbw.form_csrf_ok(request, form)):
        auth.audit("admin_notice_create", actor, ok=False)
        kept, _, _ = _clean(form)
        return _new_page(
            request, actor, kept, "화면이 오래돼서 다시 불러왔어요. 한 번 더 저장해 주세요.", 403
        )
    kept, v, error = _clean(form)
    if v is None:
        return _new_page(request, actor, kept, error, 422)
    source, rows = dbw.run(
        """INSERT INTO notice (id, title, category, body, author_id, pinned, starts_on, ends_on)
           SELECT %s, %s, %s, %s, a.id, %s, %s, %s FROM app_account a
           WHERE a.initials = %s AND a.disabled_at IS NULL
           RETURNING id::text AS id""",
        [
            uuid.uuid4(),
            v["title"],
            v["category"],
            v["body"],
            v["pinned"],
            v["starts_on"],
            v["ends_on"],
            actor,
        ],
        what="board.create",
    )
    if source != "db" or not rows:
        auth.audit("admin_notice_create", actor, ok=False)
        msg, code = _save_error(source)
        return _new_page(request, actor, kept, msg, code)
    auth.audit("admin_notice_create", actor, ok=True)
    return RedirectResponse(f"/admin/board/notices/{rows[0]['id']}?saved=1", status_code=303)


def _load_one(notice_id: str) -> tuple[str, dict | None]:
    source, out = db.run(
        [(f"{_SELECT} WHERE n.id::text = %s", [notice_id[:64]])],  # noqa: S608
        what="board.detail",
    )
    return source, (view(out[0][0]) if source == "db" and out[0] else None)


def _detail_page(
    request: Request,
    actor: str,
    source: str,
    row: dict | None,
    *,
    form: dict | None = None,
    error: str | None = None,
    saved: bool = False,
    code: int = 200,
) -> HTMLResponse:
    return dbw.render_form(
        request,
        "admin/board/notice_detail.html",
        {
            "actor": actor,
            "source": source,
            "row": row,
            "form": form or _form_of(row),
            "error": error,
            "saved": saved,
            "categories": NOTICE_CATEGORIES,
            "title_max": NOTICE_TITLE_MAX,
            "body_max": NOTICE_BODY_MAX,
        },
        code,
    )


@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: str) -> HTMLResponse:
    """공지사항 상세 + 수정 폼."""
    actor = require_governor(request)
    source, row = _load_one(notice_id)
    if source == "db" and row is None:
        raise HTTPException(status_code=404)
    saved = request.query_params.get("saved") == "1"
    return _detail_page(request, actor, source, row, saved=saved)


@router.post("/notices/{notice_id}")
async def notice_update(request: Request, notice_id: str):  # noqa: ANN201
    """공지 수정 · 숨김 · 고정. ⛔ 지우지 않는다 — 숨김으로 내린다."""
    actor = require_governor(request)
    form = await _read_form(request)
    kept, v, error = _clean(form)
    if not auth.csrf_ok(*dbw.form_csrf_ok(request, form)):
        auth.audit("admin_notice_update", actor, ok=False)
        v, error, code = None, "화면이 오래돼서 다시 불러왔어요. 한 번 더 저장해 주세요.", 403
    else:
        code = 422
    if v is not None:
        source, rows = dbw.run(
            """UPDATE notice SET title = %s, category = %s, body = %s, pinned = %s,
                      starts_on = %s, ends_on = %s,
                      hidden_at = CASE WHEN %s THEN COALESCE(hidden_at, now()) ELSE NULL END,
                      updated_at = now()
               WHERE id::text = %s
               RETURNING id::text AS id""",
            [
                v["title"],
                v["category"],
                v["body"],
                v["pinned"],
                v["starts_on"],
                v["ends_on"],
                v["hidden"],
                notice_id[:64],
            ],
            what="board.update",
        )
        if source == "db" and rows:
            auth.audit("admin_notice_update", actor, ok=True)
            return RedirectResponse(
                f"/admin/board/notices/{rows[0]['id']}?saved=1", status_code=303
            )
        auth.audit("admin_notice_update", actor, ok=False)
        if source == "db":
            raise HTTPException(status_code=404)
        error, code = _save_error(source)
    source, row = _load_one(notice_id)
    if source == "db" and row is None:
        raise HTTPException(status_code=404)
    return _detail_page(request, actor, source, row, form=kept, error=error, code=code)
