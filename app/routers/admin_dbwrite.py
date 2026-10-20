"""app/routers/admin_dbwrite.py — 관리자 화면이 운영 표에 **쓰는** 한 곳 · 소유자 **psj** (병렬작업 계약 §5).

🆕 2026-10-20 — 공지 작성 · 수정(`notice`)과 문의 답변 · 상태 변경(`ticket`)이 여기를 지나 쓴다 (D-260 ⑦).
   `admin_dbread.py` 와 같은 연결 · 같은 상태 구분(db · no_table · no_db)이다 — 읽기 모듈에 쓰기를 섞지 않으려고 파일을 갈랐다.

🔴 **이 모듈에는 라우트가 없다.** 쓰기 핸들러는 허용 목록(`tests/test_auth_boundary.py` `ADMIN_WRITES`)의 파일에만 있고,
   핸들러 본문이 `require_governor` · `auth.csrf_ok` · `auth.audit` 를 직접 부른다 (`REQUIRED_CALLS`).
🔴 원인 문자열을 화면 · 로그에 담지 않는다 — 예외 이름만 (admin_dbread 와 같다).
🚨 SQL 은 부르는 쪽의 고정 조각이고 값은 전부 파라미터다.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app import auth
from app.routers import admin_dbread as db
from app.routers.auth import _cookie_kwargs
from app.templating import templates

_log = logging.getLogger("copylane.admin.dbwrite")


def run(sql: str, params: list[Any], *, what: str) -> tuple[str, list[dict]]:
    """쓰기 한 번(+ `RETURNING`) — 한 트랜잭션. `(source, 돌려받은 행)`. 실패하면 되돌리고 `(no_table | no_db, [])`."""
    try:
        with db._connect() as conn, conn.cursor() as cur:  # noqa: SLF001 — 연결은 한 벌 (D-99)
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            conn.commit()
            return "db", rows
    except Exception as e:  # noqa: BLE001
        if db._is_undefined_table(e):  # noqa: SLF001
            return "no_table", []
        _log.warning("admin.%s: 쓰기 실패 — %s", what, type(e).__name__)
        return "no_db", []


def render_form(
    request: Request, template: str, ctx: dict, status_code: int = 200
) -> HTMLResponse:
    """폼이 있는 관리자 화면 — CSRF 토큰을 **쿠키와 폼 양쪽에** 심는다 (로그인 · 사용자 쓰기 화면과 같은 이중 제출 · P1-7)."""
    token = auth.new_csrf()
    resp = templates.TemplateResponse(
        request, template, {**ctx, "csrf_token": token, "csrf_field": auth.CSRF_FIELD}
    )
    resp.status_code = status_code
    resp.set_cookie(auth.CSRF_COOKIE, token, **_cookie_kwargs(request))  # type: ignore[arg-type]
    return resp


def form_csrf_ok(request: Request, form: dict[str, list[str]]) -> tuple[str | None, str | None]:
    """(쿠키 값, 폼 값) — 핸들러가 `auth.csrf_ok(*…)` 로 직접 대조한다(게이트가 본문의 호출을 본다)."""
    return request.cookies.get(auth.CSRF_COOKIE), (form.get(auth.CSRF_FIELD) or [""])[0]
