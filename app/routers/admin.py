"""app/routers/admin.py — 관리자 화면 + BFF · 소유자 **ssm · psj** (D-208 · 병렬작업 계약 §5).

✅ **로그인이 섰다** (D-66 구현 · D-213). `require_governor` 를 지나지 않으면 화면이 안 뜬다 —
   **읽기도 막는다.** 이 화면이 내는 것은 등급 판정 근거와 **2인 확인 서명(사람 이름)** 이다.
🔴 **클라우드 에디션에서는 이 라우터가 아예 안 붙는다** (D-213) — 라우트가 없으면 404 다.
   배포 그림에 제품 관리자 화면의 자리가 없었고, 그것을 에디션(compose 프로파일)으로 갈랐다.
⬜ **쓰기 경로는 아직 없다.** 게이트가 막고 있고, 여는 것은 별도 판정이다 (§8 ⑬ 의 남은 절반).

★ **거버넌스 운영 화면이 여기 붙는다** — 소스 레지스트리 2인 확인 · 판정매트릭스 열람.
  🚨 **생성물은 화면이 만들지 않는다** — 보여 주기만 한다 (D-90 · 집행계약 §6).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import auth
from app.routers.auth import account_active
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])
_log = logging.getLogger("copylane.admin")

#: 🚨 `app/api.py` 의 `/health` 와 **같은 목록**이라야 한다. ⬜ 두 벌이다 (D-99) —
#:    합치는 것은 `/health` 를 함수로 빼는 일이고, 그건 팀장 파일이라 PR 로 올린다.
_TABLES = (
    "source",
    "fragment",
    "document",
    "chunk",
    "chunk_embedding",
    "dict_entry",
    "product_fact",
    "golden_sample",
)


def require_governor(request: Request) -> str:
    """로그인한 이니셜. 없으면 로그인 화면으로 보낸다 (D-66 · D-213).

    🔴 **읽기도 막는다.** 이 화면이 내는 것은 등급 판정 근거와 **2인 확인 서명(사람 이름)** 이다 —
       읽기 전용이어도 공개 표면에 놓일 것이 아니다 (D-76 · P2-10).
    """
    initials = auth.read_session(request.cookies.get(auth.SESSION_COOKIE))
    # 🔴 2026-09-21 (전수 재검토) — 서명이 맞아도 **비활성 계정이면 막는다.** ⛔ 종전에는 `disabled_at` 을
    #    로그인에서만 봐서, 막은 계정의 쿠키가 만료까지 관리자 화면을 열었다.
    if initials and not account_active(initials):
        auth.audit("session_disabled", initials, ok=False)
        initials = None
    if not initials:
        # 🚨 401 이 아니라 **303 리다이렉트**다 — 사람이 보는 화면이라 로그인 폼으로 보낸다.
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return initials


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """관리자 첫 화면. 🚨 **DB 가 없어도 뜬다** — 빈 표를 그리고 고치는 법을 낸다 (D-51)."""
    actor = require_governor(request)
    counts: dict[str, int] = {}
    try:
        import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            for table in _TABLES:
                cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — 고정 목록이다
                counts[table] = cur.fetchone()[0]
    except Exception as e:  # noqa: BLE001
        # 🔴 원인 문자열을 화면에 담지 않는다 — 호스트·포트·사용자명이 그 안에 있다.
        _log.warning("admin: DB 접속 실패 — %s", type(e).__name__)
    return templates.TemplateResponse(
        request, "admin/index.html", {"counts": counts, "actor": actor}
    )
