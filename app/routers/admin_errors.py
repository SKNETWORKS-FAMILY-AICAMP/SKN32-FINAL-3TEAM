"""app/routers/admin_errors.py — 오류 로그 확인 화면 (뼈대) · 소유자 **ssm** (병렬작업 계약 §5).

★ **`admin.py` 와 파일을 가른다** — `admin.py` 는 ssm·psj 가 같이 쓴다. §5 「같은 파일을 두 사람이
   동시에 열지 않는다 · 쪼개는 것이 규칙을 만드는 것보다 싸다」를 따른다.
   붙이는 자리는 `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.
   그래서 **관리자 에디션에서만 붙는다** (D-213 — 클라우드에서는 404).

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 화면의 「처리 상태」 폼은 전부 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **`app_error_log` 테이블은 아직 승인 전이다** (`docs/ssm/요청_2026-09-16_app_error_log.md`).
   테이블이 없거나 DB 에 못 붙으면 **더미 5건**으로 화면을 그리고, 화면 맨 위에 그 사실을 크게 적는다.
   ⬜ 테이블이 승인·적재되면 `_DUMMY` 와 더미 분기를 지운다.

🚨 **필터 이름에 `q` · `text` 를 쓰지 않는다** — `RedactFilter` 가 그 이름의 값을 가린다.
   여기 필터는 레벨·로거·쪽번호뿐이고, 문구가 실릴 자리가 없다 (보안점검 P1-4).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/errors` 다 — `admin_router`(prefix `/admin`) 아래에 매달려 `/admin/errors` 가 된다.
router = APIRouter(prefix="/errors")
_log = logging.getLogger("copylane.admin.errors")

#: 화면이 받는 레벨. 🚨 요청 메모 §2 의 `CHECK` 와 같은 목록이라야 한다.
LEVELS = ("WARNING", "ERROR", "CRITICAL")

#: 한 쪽에 보여 줄 행 수. 화면 모양의 값이지 판정 파라미터가 아니다 (settings.py 대상 아님).
PAGE_SIZE = 50

_MAX_LOGGER_LEN = 80

_COLUMNS = (
    "id::text AS id, occurred_at, level, logger_name, message, exc_type, module, func_name, lineno"
)

# ─────────────────────────────────────────────────────────────
# 더미 — 테이블 승인 전 화면 확인용. ⬜ 승인·적재 뒤 지운다.
# 🚨 message 는 **마스킹을 지난 모양**으로 적는다 — 실제로 들어올 모양과 같아야 확인이 뜻이 있다.
# ─────────────────────────────────────────────────────────────
_KST = timezone(timedelta(hours=9))
_T0 = datetime(2026, 9, 16, 11, 5, 12, tzinfo=_KST)
_DUMMY: list[dict] = [
    {
        "id": "DUMMY-ERR-001",
        "occurred_at": _T0,
        "level": "ERROR",
        "logger_name": "copylane.api",
        "message": "judge: 판정 실패 — text=<가림 18자·sha256:9a1c3e7f>",
        "exc_type": "TimeoutError",
        "module": "api",
        "func_name": "judge",
        "lineno": 214,
    },
    {
        "id": "DUMMY-ERR-002",
        "occurred_at": _T0 - timedelta(minutes=7),
        "level": "WARNING",
        "logger_name": "copylane.admin",
        "message": "admin: source 조회 실패 — OperationalError",
        "exc_type": None,
        "module": "admin",
        "func_name": "_list_sources",
        "lineno": 128,
    },
    {
        "id": "DUMMY-ERR-003",
        "occurred_at": _T0 - timedelta(minutes=31),
        "level": "CRITICAL",
        "logger_name": "uvicorn.error",
        "message": "Exception in ASGI application",
        "exc_type": "RuntimeError",
        "module": "h11_impl",
        "func_name": "run_asgi",
        "lineno": 403,
    },
    {
        "id": "DUMMY-ERR-004",
        "occurred_at": _T0 - timedelta(hours=2),
        "level": "ERROR",
        "logger_name": "copylane.api",
        "message": "judge: 판정 실패 — text=<가림 31자·sha256:44be0c19>",
        "exc_type": "TimeoutError",
        "module": "api",
        "func_name": "judge",
        "lineno": 214,
    },
    {
        "id": "DUMMY-ERR-005",
        "occurred_at": _T0 - timedelta(hours=9),
        "level": "WARNING",
        "logger_name": "copylane.auth",
        "message": "auth: 로그인 시도 제한 도달",
        "exc_type": None,
        "module": "auth",
        "func_name": "login",
        "lineno": 141,
    },
]


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
        return max(1, int(value or 1))
    except ValueError:
        return 1


def _dummy_query(level: str | None, logger_name: str | None) -> list[dict]:
    return [
        r
        for r in _DUMMY
        if (not level or r["level"] == level)
        and (not logger_name or r["logger_name"].startswith(logger_name))
    ]


def _connect():
    """DB 연결. 🚨 import 를 함수 안에 둔다 — DB 가 없어도 화면 모듈은 서야 한다 (D-51)."""
    import psycopg  # noqa: PLC0415
    from psycopg.rows import dict_row  # noqa: PLC0415

    from app.settings import dsn  # noqa: PLC0415

    return psycopg.connect(dsn(), row_factory=dict_row)


def _is_undefined_table(e: Exception) -> bool:
    try:
        from psycopg import errors as pg_errors  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    return isinstance(e, pg_errors.UndefinedTable)


def _load_list(level: str | None, logger_name: str | None, page: int) -> dict:
    """목록 + 조건에 맞는 건수. `source` 는 ``db`` · ``dummy_no_table`` · ``dummy_no_db``.

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
            cur.execute(
                f"SELECT {_COLUMNS} FROM app_error_log {where_sql} "  # noqa: S608
                "ORDER BY occurred_at DESC LIMIT %s OFFSET %s",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            )
            return {"source": "db", "rows": cur.fetchall(), "total": total}
    except Exception as e:  # noqa: BLE001
        if _is_undefined_table(e):
            source = "dummy_no_table"
        else:
            source = "dummy_no_db"
            _log.warning("admin.errors: 조회 실패 — %s", type(e).__name__)

    rows = _dummy_query(level, logger_name)
    return {"source": source, "rows": rows, "total": len(rows)}


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
            source = "dummy_no_table"
        else:
            source = "dummy_no_db"
            _log.warning("admin.errors: 단건 조회 실패 — %s", type(e).__name__)

    row = next((r for r in _DUMMY if r["id"] == error_id), None)
    same = [
        r
        for r in _DUMMY
        if row
        and r["id"] != row["id"]
        and (r["module"], r["func_name"], r["lineno"])
        == (row["module"], row["func_name"], row["lineno"])
    ]
    return {"source": source, "row": row, "same": same}


@router.get("", response_class=HTMLResponse)
def error_list(request: Request) -> HTMLResponse:
    """오류 로그 목록 — 읽기 전용 · 최신순."""
    actor = require_governor(request)
    qp = request.query_params
    level = _clean_level(qp.get("level"))
    logger_name = _clean_logger(qp.get("logger"))
    page = _clean_page(qp.get("page"))

    data = _load_list(level, logger_name, page)
    pages = max(1, -(-data["total"] // PAGE_SIZE))
    return templates.TemplateResponse(
        request,
        "admin/errors/list.html",
        {
            "actor": actor,
            "levels": LEVELS,
            "level": level,
            "logger": logger_name or "",
            "page": page,
            "pages": pages,
            **data,
        },
    )


@router.get("/{error_id}", response_class=HTMLResponse)
def error_detail(request: Request, error_id: str) -> HTMLResponse:
    """오류 로그 한 건 — 읽기 전용. 처리 상태·메모는 **뼈대만** 있다."""
    actor = require_governor(request)
    data = _load_one(error_id[:64])
    if data["row"] is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "admin/errors/detail.html", {"actor": actor, **data})
