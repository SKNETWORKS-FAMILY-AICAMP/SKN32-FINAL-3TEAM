"""4. 회원 · 인증 — 로그인 · 로그아웃 · 로그인이 필요한 화면 · 쿠키 보안 속성.

🚨 틀린 비밀번호 시험은 **지어낸 이메일**로 한 번만 한다 — 시험 계정에 시도 제한(5분 잠금)이 걸리지 않게.
🚨 회원으로 로그인한 상태에서는 검수를 돌리지 않는다 — 이력 보관에 동의한 계정이면 시험 문구가 이력에 쌓인다.
"""

from __future__ import annotations

import secrets

import pytest
from conftest import (
    ADMIN_EMAIL,
    ADMIN_OPEN,
    ADMIN_PASSWORD,
    IS_HTTPS,
    USER_EMAIL,
    USER_PASSWORD,
    Client,
    assert_no_server_error,
    cookie_attrs,
    login_user,
    note,
)

import report

case = pytest.mark.case
AREA = "회원·인증"


def need_user() -> None:
    if not (USER_EMAIL and USER_PASSWORD):
        pytest.skip("시험 계정이 없다 — run.py 실행 때 입력하거나 CL_TEST_EMAIL · CL_TEST_PASSWORD 를 넣는다")


def check_cookie(attrs: str | None, name: str) -> None:
    assert attrs is not None, f"{name} 쿠키를 내주지 않았다"
    low = attrs.lower()
    assert "httponly" in low, f"{name} 에 HttpOnly 가 없다 ({attrs})"
    assert "samesite=lax" in low or "samesite=strict" in low, f"{name} 에 SameSite 가 없다 ({attrs})"
    if IS_HTTPS:
        assert "secure" in low, f"{name} 에 Secure 가 없다 — https 인데 앱이 http 로 알고 있다 ({attrs})"
    note(f"{name}: {attrs}")


# ── 로그아웃 상태 ──────────────────────────────────────
@case(id="AUTH-01", area=AREA, title="로그인 화면 — CSRF 토큰 발급", expect="200 · 폼과 쿠키에 같은 토큰 · 쿠키 보안 속성")
def test_login_page(http: Client) -> None:
    r = http.get("/u/login")
    assert r.status_code == 200, f"상태 {r.status_code}"
    token = report.find_input(r.text, "csrf_token")
    assert token, "폼에 csrf_token 칸이 없다"
    assert http.s.cookies.get("copylane_csrf") == token, "쿠키와 폼의 토큰이 다르다"
    check_cookie(cookie_attrs(r, "copylane_csrf"), "copylane_csrf")


@case(id="AUTH-02", area=AREA, title="CSRF 토큰 없이 로그인", expect="403 (위조 요청 거부)")
def test_login_without_csrf(http: Client) -> None:
    r = http.post("/u/login", data={"email": f"svc-{secrets.token_hex(4)}@example.invalid", "password": "x"})
    assert r.status_code == 403, f"상태 {r.status_code}"
    assert "copylane_user" not in http.s.cookies, "로그인 쿠키가 생겼다"


@case(id="AUTH-03", area=AREA, title="없는 계정 · 틀린 비밀번호", expect="401 · 「이메일이나 비밀번호가 맞지 않아요」 · 로그인 안 됨")
def test_login_wrong(http: Client) -> None:
    r = login_user(http, f"svc-{secrets.token_hex(4)}@example.invalid", "wrong-password-123")
    assert r.status_code == 401, f"상태 {r.status_code}"
    assert "이메일이나 비밀번호가 맞지 않아요" in r.text, "안내 문구가 다르다(계정 존재 여부를 흘리지 않는 같은 문구여야 한다)"
    assert "copylane_user" not in http.s.cookies, "로그인 쿠키가 생겼다"


@case(id="AUTH-04", area=AREA, title="로그아웃 상태로 마이페이지", expect="303 → /u/login")
def test_mypage_needs_login(http: Client) -> None:
    r = http.get("/u/mypage")
    assert r.status_code == 303, f"상태 {r.status_code}"
    assert r.headers.get("Location", "").startswith("/u/login"), f"Location={r.headers.get('Location')}"


@case(id="AUTH-05", area=AREA, title="로그아웃 상태로 고객센터", expect="200 · 로그인 안내(로그인 벽 없이)")
def test_cs_logged_out(http: Client) -> None:
    r = http.get("/u/cs")
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert "로그인하고 문의를 남겨주세요" in r.text, "로그인 안내가 없다"


@case(id="AUTH-06", area=AREA, title="로그아웃 상태로 문의 접수(POST)", expect="303 → /u/login (접수 안 됨)")
def test_cs_post_logged_out(http: Client) -> None:
    r = http.post("/u/cs", data={"title": "시험", "body": "시험"})
    assert r.status_code == 303, f"상태 {r.status_code}"
    assert r.headers.get("Location", "").startswith("/u/login"), f"Location={r.headers.get('Location')}"


# ── 시험 계정 ──────────────────────────────────────────
@case(id="AUTH-07", area=AREA, title="시험 계정 로그인 — 세션 쿠키 보안 속성", expect="303 · copylane_user 쿠키 HttpOnly · SameSite · Secure")
def test_login_success() -> None:
    need_user()
    c = Client("회원(로그인 시험)")
    r = login_user(c, USER_EMAIL, USER_PASSWORD)
    assert r.status_code == 303, f"상태 {r.status_code} — 계정 · 비밀번호를 확인한다"
    check_cookie(cookie_attrs(r, "copylane_user"), "copylane_user")


@case(id="AUTH-08", area=AREA, title="로그인 후 마이페이지", expect="200 · 프로필 화면")
def test_member_mypage(member: Client) -> None:
    r = member.get("/u/mypage")
    assert r.status_code == 200, f"상태 {r.status_code} (로그인이 유지되지 않음)"
    assert_no_server_error(r)


@case(id="AUTH-09", area=AREA, title="로그인 후 검수 이력", expect="200 · 내 이력만")
def test_member_history(member: Client) -> None:
    r = member.get("/u/history")
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert_no_server_error(r)
    r2 = member.get("/u/history?page=999&verdict=nonsense")
    assert r2.status_code == 200, f"이상한 page·verdict 값에 {r2.status_code} (기본값으로 돌아가야 한다)"


@case(id="AUTH-10", area=AREA, title="로그인 후 고객센터", expect="200 · 문의 작성 폼")
def test_member_cs(member: Client) -> None:
    r = member.get("/u/cs")
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert 'action="/u/cs"' in r.text, "문의 작성 폼이 없다"
    r2 = member.get("/u/cs?tab=history")
    assert r2.status_code == 200, f"내 문의 내역 {r2.status_code}"


@case(id="AUTH-11", area=AREA, title="로그인 뒤 외부 주소로 보내기(next) 시도", expect="303 → /u/ (외부로 안 넘어간다)")
def test_open_redirect() -> None:
    need_user()
    c = Client("회원(next 시험)")
    r = login_user(c, USER_EMAIL, USER_PASSWORD, nxt="https://evil.example/")
    assert r.status_code == 303, f"상태 {r.status_code}"
    loc = r.headers.get("Location", "")
    assert loc.startswith("/u"), f"외부 주소로 보낸다: Location={loc}"


@case(id="AUTH-12", area=AREA, title="로그아웃", expect="303 → /u/landing · 이후 마이페이지는 로그인으로")
def test_logout() -> None:
    need_user()
    c = Client("회원(로그아웃 시험)")
    r = login_user(c, USER_EMAIL, USER_PASSWORD)
    assert r.status_code == 303, f"로그인 {r.status_code}"
    out = c.post("/u/logout")
    assert out.status_code == 303, f"로그아웃 {out.status_code}"
    assert out.headers.get("Location", "").endswith("/u/landing"), f"Location={out.headers.get('Location')}"
    after = c.get("/u/mypage")
    assert after.status_code == 303 and after.headers.get("Location", "").startswith("/u/login"), (
        f"로그아웃 뒤에도 마이페이지가 열린다 ({after.status_code})"
    )


# ── 관리자 (허용 IP 에서 --admin-open 일 때만) ──────────
@case(id="ADM-01", area="관리자", title="로그인 없이 관리자 화면", expect="303 → /login (내용을 보여 주지 않는다)")
def test_admin_needs_login(http: Client) -> None:
    if not ADMIN_OPEN:
        pytest.skip("관리자 화면이 외부에서 닫힌 구성 — 차단 여부는 보안 SEC-02 에서 본다")
    r = http.get("/admin/")
    assert r.status_code == 303, f"상태 {r.status_code}"
    assert "/login" in r.headers.get("Location", ""), f"Location={r.headers.get('Location')}"


@case(id="ADM-02", area="관리자", title="관리자 로그인 → 대시보드 · 오류 로그 화면", expect="303 → /admin/ · /admin/ · /admin/errors 200")
def test_admin_login() -> None:
    if not ADMIN_OPEN:
        pytest.skip("관리자 화면이 외부에서 닫힌 구성 (--admin-open 이 아님)")
    if not (ADMIN_EMAIL and ADMIN_PASSWORD):
        pytest.skip("관리자 계정이 없다 — CL_ADMIN_EMAIL · CL_ADMIN_PASSWORD")
    c = Client("관리자")
    r = login_user(c, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 303, f"로그인 {r.status_code}"
    assert r.headers.get("Location", "").startswith("/admin"), f"Location={r.headers.get('Location')}"
    for path in ("/admin/", "/admin/errors"):
        p = c.get(path)
        assert p.status_code == 200, f"{path} → {p.status_code}"
        assert_no_server_error(p)
