"""app/routers/auth.py — `governor` 로그인 화면 · 소유자 **팀장** (D-66 · D-213).

🚨 **가입 화면은 없다.** 로그인과 로그아웃 둘뿐이다 (D-66 — 온프레미스는 계정 주입).
⛔ 이 라우터는 **관리자 화면이 붙는 에디션에서만** 붙는다. 클라우드에서는 관리자도 로그인도
   존재하지 않는다 — **라우트가 없으면 404 다** (D-213).

🔴 **논리는 `app/auth.py` 가 든다** — 여기는 껍데기다 (D-51 · D-99).
"""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth
from app.formbody import read_capped
from app.templating import templates

router = APIRouter(tags=["auth"])

#: 🚨 로그인 폼 본문 상한. 이니셜 + 비밀번호 둘뿐이라 넉넉해도 작다 (P2-11).
_MAX_BODY = 4096


def _cookie_kwargs(request: Request) -> dict[str, object]:
    """쿠키 옵션 (보안점검 P1-7).

    🚨 `Secure` 는 **HTTPS 일 때만** 붙인다. 로컬 `http://127.0.0.1` 에서 무조건 붙이면
       브라우저 판에 따라 쿠키가 아예 안 실려 **로그인이 조용히 안 된다.**
       ⛔ 그것이 「안전한 실패」가 아니다 — 원인을 못 찾는 실패다.
    ★ 배포는 Caddy 뒤 HTTPS 라 `url.scheme` 이 https 가 되고 자동으로 켜진다.
    """
    return {
        "httponly": True,
        "samesite": "lax",  # 🔴 **주 방어** — 교차 사이트 POST 에 쿠키가 안 붙는다
        "secure": request.url.scheme == "https",
        "path": "/",
    }


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    """로그인 화면. 🚨 CSRF 토큰을 여기서 발급하고 **쿠키와 폼 양쪽에** 심는다."""
    token = auth.new_csrf()
    resp = templates.TemplateResponse(request, "auth/login.html", {"csrf_token": token})
    resp.set_cookie(auth.CSRF_COOKIE, token, **_cookie_kwargs(request))  # type: ignore[arg-type]
    return resp


@router.post("/login")
async def login(request: Request) -> RedirectResponse:
    """로그인. ⛔ **없는 계정과 틀린 비밀번호를 같은 답으로 낸다** — 존재 여부가 정보다 (P1-5).

    🚨 **시도 제한이 먼저다** (P2-11) — Argon2id 는 19 MiB 를 잡는다. 세는 것보다 **해시를
       돌리는 것이 비싸므로** 막는 판단이 해시 앞에 와야 한다.
    """
    body = await read_capped(request, _MAX_BODY)  # 🔄 09-21 — 다 읽고 재지 않는다 (app/formbody.py)
    form = parse_qs(body.decode("utf-8", "replace"))
    initials = (form.get("initials", [""])[0] or "").strip()[:16]
    password = form.get("password", [""])[0] or ""

    if not auth.csrf_ok(request.cookies.get(auth.CSRF_COOKIE), form.get(auth.CSRF_FIELD, [""])[0]):
        auth.audit("login", initials or None, ok=False)
        raise HTTPException(403, "요청이 만료됐다 — 로그인 화면을 다시 연다")

    # 🚨 IP 가 아니라 **이니셜**로 센다 — 한 계정을 여러 곳에서 두드리는 것을 막는다.
    #    ⬜ IP 축은 따로다. 지금은 로컬뿐이라 안 넣었다 (D-188 — 안 넣은 것이지 없는 게 아니다).
    if auth.throttle.blocked(initials):
        auth.audit("login_blocked", initials or None, ok=False)
        raise HTTPException(429, f"시도가 많다 — {auth.LOCKOUT_SEC // 60}분 뒤에 다시")

    stored = _lookup(initials)
    # 🔄 2026-09-21 (전수 재검토) — 없는 계정도 해시를 한 번 돈다 — 걸린 시간이 존재를 알리지 않게 (P1-5)
    if not auth.verify_account(stored, password):
        auth.throttle.fail(initials)
        auth.audit("login", initials or None, ok=False)
        raise HTTPException(401, "이니셜이나 비밀번호가 맞지 않는다")

    auth.throttle.clear(initials)
    if auth.needs_rehash(stored):
        # 🚨 파라미터가 올라가면 **로그인 성공 시점에 조용히 재해시**한다 — 사용자는 모른다
        _store_hash(initials, auth.hash_password(password))
    auth.audit("login", initials, ok=True)

    resp = RedirectResponse("/admin/", status_code=303)
    resp.set_cookie(auth.SESSION_COOKIE, auth.issue_session(initials), **_cookie_kwargs(request))  # type: ignore[arg-type]
    return resp


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    """로그아웃. 🚨 쿠키를 지우는 것으로 끝난다 — 세션은 서버에 없다."""
    auth.audit("logout", auth.read_session(request.cookies.get(auth.SESSION_COOKIE)), ok=True)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp


def _lookup(initials: str) -> str | None:
    """계정의 PHC 해시. 없으면 `None`. ⛔ DB 가 없으면 **로그인이 안 된다** — 통과가 아니다."""
    if not initials:
        return None
    try:
        from app.db import pg_connect  # noqa: PLC0415 — 대기 상한 한 곳 (D-99)

        with pg_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pw_hash FROM app_account WHERE initials = %s AND disabled_at IS NULL",
                (initials,),
            )
            row = cur.fetchone()
    except Exception:  # noqa: BLE001 — DB 없음·표 없음 모두 「로그인 불가」다 (D-220)
        return None
    return row[0] if row else None


def account_active(initials: str) -> bool:
    """세션의 이니셜이 **지금도** 살아 있는 계정인가. 🆕 2026-09-21 (전수 재검토).

    ⛔ 세션은 서버에 없는 서명 쿠키라, 계정을 비활성(`disabled_at`)해도 **만료까지 그대로 들어왔다.**
    ★ 로그인과 **같은 조회**를 쓴다(`_lookup` · D-99) — DB 가 없으면 False 다 (D-220).
    """
    return _lookup(initials) is not None


def _store_hash(initials: str, pw_hash: str) -> None:
    """재해시 결과를 쓴다. 🚨 실패해도 로그인은 성공시킨다 — 다음 로그인에 다시 시도한다."""
    try:
        from app.db import pg_connect  # noqa: PLC0415 — 대기 상한 한 곳 (D-99)

        with pg_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE app_account SET pw_hash = %s, last_login_at = now() WHERE initials = %s",
                (pw_hash, initials),
            )
    except Exception:  # noqa: BLE001, S110 — 재해시 실패가 로그인을 막지 않는다
        pass
