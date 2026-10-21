"""사용자 로그인 화면에서 관리자 도메인으로 관리자 진입 (2026-10-21 · psj).

지키는 것
  ① `psj@admin.copylane` → 이니셜 `psj` 로 **관리자 인증** → 관리자 쿠키 · `/admin/` (사용자 쿠키는 안 준다)
  ② 실패 문구는 사용자 실패와 같다 — 관리자 계정이 있는지 흘리지 않는다 (P1-5)
  ③ 꼴이 틀린 관리자 도메인 · 관리자 화면이 없는 판(cloud)도 같은 답 (D-213)
  ④ 관리자 도메인으로는 가입할 수 없다
  ⑤ 관리자 로그인(`/login`)도 같은 꼴을 받는다 — 같은 함수(`admin_sign_in`)를 지난다
  ⑥ 스키마 · 세션은 그대로 — 쿠키 주체는 이니셜이다
  ⑦ 🆕 2026-10-22 (D-350) 시도 제한이 관리자 분기 **앞**이다 — 꼴이 틀린 입력 · 관리자 화면이 없는 판도 같은 횟수에서 429 ·
     막힌 뒤에는 해시를 돌리지 않는다 · 성공하면 그 키를 지운다 (P2-11 · D-213). 게이트로 올렸다 — 로그인 경로다
DB 없이 돈다 — 관리자 계정 조회(`routers.auth._lookup`)를 가짜로 바꾼다.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.routers import auth as auth_router_mod
from app.routers import auth_router, user_router

pytestmark = pytest.mark.gate

PW = "correct horse battery"


@pytest.fixture(scope="module")
def stored() -> str:
    return auth.hash_password(PW)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, stored: str) -> TestClient:
    monkeypatch.setattr(auth, "throttle", auth._Throttle())  # noqa: SLF001 — 시험마다 새 시도 제한
    monkeypatch.setattr(auth_router_mod, "_lookup", lambda ini: stored if ini == "psj" else None)
    monkeypatch.setattr(auth_router_mod, "_store_hash", lambda *a: None)
    monkeypatch.setattr("app.settings.admin_is_mounted", lambda: True)
    app = FastAPI()
    app.include_router(user_router)
    app.include_router(auth_router)
    return TestClient(app)


def _token(client: TestClient, path: str) -> str:
    html = client.get(path).text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _login(client: TestClient, email: str, pw: str = PW):  # noqa: ANN202
    token = _token(client, "/u/login")
    return client.post(
        "/u/login",
        data={"email": email, "password": pw, "csrf_token": token},
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    ("given", "want"),
    [
        ("psj@admin.copylane", "psj"),
        ("  PSJ@Admin.Copylane ", "psj"),
        ("kim@naver.com", None),
        ("@admin.copylane", ""),
        ("p.sj@admin.copylane", ""),
        ("a" * 17 + "@admin.copylane", ""),
        ("psj@admin.copylane.evil.com", None),
    ],
)
def test_관리자_도메인에서_이니셜을_뗀다(given: str, want: str | None) -> None:
    assert auth.admin_initials_of(given) == want


def test_관리자_도메인이면_관리자로_들어간다(client: TestClient) -> None:
    r = _login(client, "psj@admin.copylane")
    assert r.status_code == 303 and r.headers["location"] == "/admin/"
    assert (
        auth.read_session(r.cookies.get(auth.SESSION_COOKIE)) == "psj"
    )  # 쿠키 주체는 이니셜 그대로
    assert auth.USER_SESSION_COOKIE not in r.cookies


@pytest.mark.parametrize(
    ("email", "pw"),
    [
        ("psj@admin.copylane", "wrong password!!"),  # 틀린 비밀번호
        ("nobody@admin.copylane", PW),  # 없는 관리자
        ("p.sj@admin.copylane", PW),  # 꼴이 틀림
    ],
)
def test_관리자_실패는_사용자_실패와_같은_답이다(client: TestClient, email: str, pw: str) -> None:
    r = _login(client, email, pw)
    assert r.status_code == 401
    assert "이메일이나 비밀번호가 맞지 않아요." in r.text
    assert auth.SESSION_COOKIE not in r.cookies


def test_관리자_화면이_없는_판에서는_같은_실패다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.settings.admin_is_mounted", lambda: False)
    r = _login(client, "psj@admin.copylane")
    assert r.status_code == 401 and "이메일이나 비밀번호가 맞지 않아요." in r.text
    assert auth.SESSION_COOKIE not in r.cookies


def test_관리자_도메인은_시도_제한을_관리자와_같이_쓴다(client: TestClient) -> None:
    for _ in range(auth.MAX_ATTEMPTS):
        _login(client, "psj@admin.copylane", "wrong password!!")
    r = _login(client, "psj@admin.copylane")
    assert r.status_code == 429


def test_관리자_도메인으로는_가입할_수_없다(client: TestClient) -> None:
    token = _token(client, "/u/signup")
    r = client.post(
        "/u/signup",
        data={
            "name": "가짜",
            "email": "psj@admin.copylane",
            "password": PW,
            "password2": PW,
            "agree_terms": "on",
            "agree_disclaimer": "on",
            "csrf_token": token,
        },
    )
    assert r.status_code == 422 and "이 이메일 주소로는 가입할 수 없어요." in r.text


def test_관리자_로그인_화면도_같은_꼴을_받는다(client: TestClient) -> None:
    token = _token(client, "/login")
    r = client.post(
        "/login",
        data={"initials": "psj@admin.copylane", "password": PW, "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/admin/"
    assert auth.read_session(r.cookies.get(auth.SESSION_COOKIE)) == "psj"


# ── 🆕 2026-10-22 (D-350) 시도 제한은 관리자 분기 앞 · 어느 갈래든 센다 ──────────────────────────────


@pytest.mark.parametrize(
    ("email", "mounted"),
    [
        ("p.sj@admin.copylane", True),  # 꼴이 틀림 — 종전에는 해시만 돌고 세지 않았다
        ("psj@admin.copylane", False),  # 관리자 화면이 없는 판(배포판) — 종전에는 늘 401
        ("nobody@admin.copylane", True),  # 없는 관리자
    ],
)
def test_관리자_도메인의_어느_실패든_같은_횟수에서_막힌다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str, mounted: bool
) -> None:
    monkeypatch.setattr("app.settings.admin_is_mounted", lambda: mounted)
    for _ in range(auth.MAX_ATTEMPTS):
        assert _login(client, email, "wrong password!!").status_code == 401
    r = _login(client, email, "wrong password!!")
    assert r.status_code == 429 and "시도가 너무 많아요" in r.text


def test_막힌_뒤에는_해시를_돌리지_않는다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.settings.admin_is_mounted", lambda: False)
    for _ in range(auth.MAX_ATTEMPTS):
        _login(client, "psj@admin.copylane", "wrong password!!")
    calls: list[object] = []
    real = auth.verify_account
    monkeypatch.setattr(auth, "verify_account", lambda *a: calls.append(a) or real(*a))
    assert _login(client, "psj@admin.copylane", "wrong password!!").status_code == 429
    assert not calls, "🔴 막혔는데 해시를 돌렸다(P2-11)"


def test_실패마다_해시는_한_번이다(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    real = auth.verify_account
    monkeypatch.setattr(auth, "verify_account", lambda *a: calls.append(a) or real(*a))
    for email, mounted in (("p.sj@admin.copylane", True), ("psj@admin.copylane", False)):
        monkeypatch.setattr("app.settings.admin_is_mounted", lambda m=mounted: m)
        calls.clear()
        assert _login(client, email, "wrong password!!").status_code == 401
        assert len(calls) == 1, f"🔴 해시 횟수가 {len(calls)} — 걸린 시간이 갈래를 알린다(P1-5)"


def test_성공하면_그_입력의_실패_횟수를_지운다(client: TestClient) -> None:
    for _ in range(auth.MAX_ATTEMPTS - 1):
        _login(client, "psj@admin.copylane", "wrong password!!")
    assert _login(client, "psj@admin.copylane").status_code == 303
    for _ in range(auth.MAX_ATTEMPTS - 1):
        assert _login(client, "psj@admin.copylane", "wrong password!!").status_code == 401
