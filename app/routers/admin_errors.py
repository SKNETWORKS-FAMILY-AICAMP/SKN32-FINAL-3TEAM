"""app/routers/admin_errors.py — 오류 로그 확인 화면 (뼈대) · 소유자 **ssm** (병렬작업 계약 §5).

★ **`admin.py` 와 파일을 가른다** — `admin.py` 는 ssm·psj 가 같이 쓴다. §5 「같은 파일을 두 사람이
   동시에 열지 않는다 · 쪼개는 것이 규칙을 만드는 것보다 싸다」를 따른다.
   붙이는 자리는 `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.
   그래서 **관리자 에디션에서만 붙는다** (D-213 — 클라우드에서는 404).

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 화면의 「처리 상태」 폼은 전부 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-09-22 — **`app_error_log` 가 섰다** (마이그레이션 `0016_app_error_log` · 쓰는 쪽 `app/error_log.py`).
   ⛔ 종전에는 표가 없거나 DB 에 못 붙으면 **더미 5건**을 그렸다 — 지웠다. 가짜 오류를 그리면 「오류가 있다」가 거짓이 된다 (D-147).
   ★ 이제 상태는 셋이다 — `db`(읽었다) · `no_table`(표가 아직 없다 — 마이그레이션 전) · `no_db`(DB 에 못 붙었다).
     뒤의 둘은 **0건이 아니라 「못 읽었다」**로 그린다 (D-72 — `/u/` 의 `reachable()` 과 같은 원칙).

🚨 **필터 이름에 `q` · `text` 를 쓰지 않는다** — `RedactFilter` 가 그 이름의 값을 가린다.
   여기 필터는 레벨·로거·쪽번호뿐이고, 문구가 실릴 자리가 없다 (보안점검 P1-4).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.error_log import PURGE_EVERY_S
from app.models import ERROR_LOG_LEVELS
from app.routers.admin import require_governor
from app.settings import ERROR_LOG_RETENTION_DAYS
from app.templating import templates

#: 🚨 prefix 는 `/errors` 다 — `admin_router`(prefix `/admin`) 아래에 매달려 `/admin/errors` 가 된다.
router = APIRouter(prefix="/errors")
_log = logging.getLogger("copylane.admin.errors")

#: 화면이 받는 레벨. 🔄 2026-09-22 — 정본은 `app.models.ERROR_LOG_LEVELS`(표의 CHECK 와 같은 목록 · D-99).
LEVELS = ERROR_LOG_LEVELS

#: 한 쪽에 보여 줄 행 수. 화면 모양의 값이지 판정 파라미터가 아니다 (settings.py 대상 아님).
PAGE_SIZE = 50

_MAX_LOGGER_LEN = 80

#: 쪽 번호 상한 — `OFFSET` 이 bigint 를 넘어 「DB 가 죽었다」로 읽히는 것을 막는 안전장치다.
#: 실제 쪽 수는 건수를 센 뒤 다시 자른다 (`_load_list`).
_MAX_PAGE = 100_000

#: 화면에 적는 보관 정책 — 🚨 값은 설정·기록기에서 읽는다(화면에 수를 따로 적지 않는다 · D-99).
_POLICY = {
    "retention_days": ERROR_LOG_RETENTION_DAYS,
    "purge_every_h": PURGE_EVERY_S // 3600,
}

_COLUMNS = (
    "id::text AS id, occurred_at, level, logger_name, message, exc_type, module, func_name, lineno"
)


def _clean_level(value: str | None) -> str | None:
    """허용 목록에 있는 레벨만 통과시킨다. 모르는 값은 **필터 없음**으로 본다."""
    if value and value.upper() in LEVELS:
        return value.upper()
    return None


def _clean_logger(value: str | None) -> str | None:
    value = (value or "").strip()[:_MAX_LOGGER_LEN]
    return value or None


def _clean_page(value: str | None) -> int:
    try:
        return min(max(1, int(value or 1)), _MAX_PAGE)
    except ValueError:
        return 1


def _page_count(total: int) -> int:
    return max(1, -(-total // PAGE_SIZE))


def _connect():
    """DB 연결. 🚨 import 를 함수 안에 둔다 — DB 가 없어도 화면 모듈은 서야 한다 (D-51).

    🔄 2026-09-22 — `app.db.pg_connect` 를 쓴다(연결 대기 상한 한 곳 · D-99). ⛔ 종전 `psycopg.connect(dsn())` 은
       `connect_timeout` 이 없어 응답 없는 DB 에 **화면이 매달렸다.**
    """
    from psycopg.rows import dict_row  # noqa: PLC0415

    from app.db import pg_connect  # noqa: PLC0415

    return pg_connect(row_factory=dict_row)


def _is_undefined_table(e: Exception) -> bool:
    try:
        from psycopg import errors as pg_errors  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    return isinstance(e, pg_errors.UndefinedTable)


def _load_list(level: str | None, logger_name: str | None, page: int) -> dict:
    """목록 + 조건에 맞는 건수. `source` 는 ``db`` · ``no_table`` · ``no_db``.

    `page` 는 **실제 쪽 수로 자른 값**을 돌려준다 — 넘치는 쪽 번호는 마지막 쪽으로 본다.

    🔴 원인 문자열을 화면·로그에 담지 않는다 — 호스트·포트·사용자명이 그 안에 있다.
    ⛔ 여기서 난 오류를 ERROR 로 남기지 않는다 — DB 저장 핸들러가 붙으면
       「저장 실패 → 로그 → 저장 실패」가 돈다. WARNING 한 줄, 이름만 남긴다.
    """
    where: list[str] = []
    params: list[object] = []
    if level:
        where.append("level = %s")
        params.append(level)
    if logger_name:
        # 앞부분 일치 — `copylane` 을 넣으면 `copylane.admin` 도 잡힌다
        where.append(r"logger_name LIKE %s ESCAPE '\'")
        params.append(
            logger_name.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        )
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    try:
        with _connect() as conn, conn.cursor() as cur:
            # where_sql 은 위의 고정 조각만 이어 붙인다 — 값은 전부 파라미터로 간다
            cur.execute(f"SELECT count(*) AS n FROM app_error_log {where_sql}", params)  # noqa: S608
            total = cur.fetchone()["n"]
            page = min(page, _page_count(total))
            cur.execute(
                f"SELECT {_COLUMNS} FROM app_error_log {where_sql} "  # noqa: S608
                "ORDER BY occurred_at DESC LIMIT %s OFFSET %s",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            )
            return {"source": "db", "rows": cur.fetchall(), "total": total, "page": page}
    except Exception as e:  # noqa: BLE001
        if _is_undefined_table(e):
            source = "no_table"
        else:
            source = "no_db"
            _log.warning("admin.errors: 조회 실패 — %s", type(e).__name__)

    # 🚨 못 읽었으면 **빈 목록 + 상태** — 0건이라고 말하지 않는다(화면이 상태로 가른다 · D-72)
    return {"source": source, "rows": [], "total": None, "page": 1}


def _load_one(error_id: str) -> dict:
    """한 건 + 같은 위치(module·func·lineno)에서 난 최근 기록."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM app_error_log WHERE id::text = %s", [error_id])  # noqa: S608
            row = cur.fetchone()
            same: list[dict] = []
            if row and row["module"]:
                cur.execute(
                    f"SELECT {_COLUMNS} FROM app_error_log "  # noqa: S608
                    "WHERE module = %s AND func_name IS NOT DISTINCT FROM %s "
                    "AND lineno IS NOT DISTINCT FROM %s AND id::text <> %s "
                    "ORDER BY occurred_at DESC LIMIT 10",
                    [row["module"], row["func_name"], row["lineno"], error_id],
                )
                same = cur.fetchall()
            return {"source": "db", "row": row, "same": same}
    except Exception as e:  # noqa: BLE001
        if _is_undefined_table(e):
            source = "no_table"
        else:
            source = "no_db"
            _log.warning("admin.errors: 단건 조회 실패 — %s", type(e).__name__)

    # 🚨 못 읽었으면 **행 없음 + 상태** — 404(「그런 기록은 없다」)로 그리지 않는다 (D-72)
    return {"source": source, "row": None, "same": []}


@router.get("", response_class=HTMLResponse)
def error_list(request: Request) -> HTMLResponse:
    """오류 로그 목록 — 읽기 전용 · 최신순."""
    actor = require_governor(request)
    qp = request.query_params
    level = _clean_level(qp.get("level"))
    logger_name = _clean_logger(qp.get("logger"))
    page = _clean_page(qp.get("page"))

    data = _load_list(level, logger_name, page)  # `data["page"]` 가 자른 값이다
    pages = _page_count(data["total"]) if data["total"] is not None else 1
    return templates.TemplateResponse(
        request,
        "admin/errors/list.html",
        {
            "actor": actor,
            "levels": LEVELS,
            "level": level,
            "logger": logger_name or "",
            "pages": pages,
            **_POLICY,
            **data,
        },
    )


@router.get("/{error_id}", response_class=HTMLResponse)
def error_detail(request: Request, error_id: str) -> HTMLResponse:
    """오류 로그 한 건 — 읽기 전용. 처리 상태·메모는 **뼈대만** 있다."""
    actor = require_governor(request)
    data = _load_one(error_id[:64])
    # ★ 404 는 **읽었는데 없을 때만**. 못 읽었으면 상태 안내를 그린다 — 「없다」와 「모른다」를 가른다 (D-188)
    if data["source"] == "db" and data["row"] is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "admin/errors/detail.html", {"actor": actor, **_POLICY, **data}
    )
