"""6. 보안 재확인 — 보안 점검(10-22)에서 정한 것이 배포 서버에서 실제로 지켜지는가.

밖(인터넷)에서 볼 수 있는 것만 본다: 닫은 경로 · 보안 머리글 · 열린 포트 · 오류 응답에 새는 정보 · 요청 크기 상한.
"""

from __future__ import annotations

import pytest
from conftest import ADMIN_OPEN, HOST, IS_HTTPS, Client, assert_no_server_error, note, port_open

case = pytest.mark.case
AREA = "보안"

CLOSED = ["/docs", "/redoc", "/openapi.json", "/fixtures", "/fixtures/judge/x", "/dev"]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            p,
            id=f"SEC-01-{i}",
            marks=case(id=f"SEC-01-{i}", area=AREA, title=f"닫은 경로 — {p}", expect="404 (외부에 안 보인다)"),
        )
        for i, p in enumerate(CLOSED, 1)
    ],
)
def test_closed_paths(http: Client, path: str) -> None:
    r = http.get(path)
    assert r.status_code == 404, f"상태 {r.status_code} — 외부에서 열린다"


@case(id="SEC-02", area=AREA, title="관리자 화면 외부 차단 (/admin/ · /login)", expect="404 (허용 IP 밖)")
def test_admin_closed(http: Client) -> None:
    if ADMIN_OPEN:
        pytest.skip("허용 IP 에서 실행 중 (--admin-open) — 관리자 시험은 ADM-* 에서 본다")
    for p in ("/admin/", "/admin/errors", "/login"):
        r = http.get(p)
        assert r.status_code == 404, f"{p} → {r.status_code} (외부에서 관리자 화면이 보인다)"


@case(id="SEC-03", area=AREA, title="보안 머리글 — 화면(HTML)", expect="CSP · nosniff · X-Frame-Options · Referrer-Policy · HSTS · Server 숨김")
def test_security_headers_html(http: Client) -> None:
    r = http.get("/u/landing")
    h = r.headers
    csp = h.get("Content-Security-Policy", "")
    assert "script-src 'self'" in csp, f"CSP 에 script-src 'self' 가 없다: {csp or '없음'}"
    assert "frame-ancestors 'none'" in csp, "CSP 에 frame-ancestors 'none' 이 없다"
    assert h.get("X-Content-Type-Options") == "nosniff", "nosniff 가 없다"
    assert h.get("X-Frame-Options") == "DENY", f"X-Frame-Options={h.get('X-Frame-Options')}"
    assert h.get("Referrer-Policy"), "Referrer-Policy 가 없다"
    if IS_HTTPS:
        assert "max-age=" in h.get("Strict-Transport-Security", ""), "HSTS 가 없다"
    server = h.get("Server", "")
    assert not any(x in server.lower() for x in ("uvicorn", "caddy")), f"서버 프로그램 이름이 드러난다: Server={server}"
    note(f"Referrer-Policy={h.get('Referrer-Policy')} · HSTS={h.get('Strict-Transport-Security', '-')}")


@case(id="SEC-04", area=AREA, title="보안 머리글 — API(JSON)", expect="CSP default-src 'none' · nosniff")
def test_security_headers_json(http: Client) -> None:
    r = http.get("/health")
    assert "default-src 'none'" in r.headers.get("Content-Security-Policy", ""), "JSON 응답의 CSP 가 다르다"
    assert r.headers.get("X-Content-Type-Options") == "nosniff", "nosniff 가 없다"


@case(id="SEC-05", area=AREA, title="서버 포트 — 밖에서 안 열려야 할 포트", expect="8000(앱) · 8765(sLLM) · 5432(DB) 연결 안 됨")
def test_ports_closed() -> None:
    opened = [p for p in (8000, 8765, 5432) if port_open(HOST, p)]
    assert not opened, f"밖에서 열린 포트: {opened}"


@case(id="SEC-06", area=AREA, title="서버 포트 — 열려야 할 포트", expect="443(https) · 80(인증서 갱신·https 전환) 열림")
def test_ports_open() -> None:
    if not IS_HTTPS:
        pytest.skip("대상이 https 가 아니다")
    closed = [p for p in (443, 80) if not port_open(HOST, p)]
    assert not closed, f"닫힌 포트: {closed}"


@case(id="SEC-07", area=AREA, title="요청 본문 1MB 초과", expect="413 (Caddy 가 앱 앞에서 끊는다)")
def test_body_limit(http: Client) -> None:
    big = "가" * 600_000  # UTF-8 로 약 1.8MB
    try:
        r = http.post("/judge", json={"text": big}, timeout=60)
    except AssertionError as e:
        # 서버가 본문을 다 받기 전에 연결을 끊으면 요청 실패로 온다 — 끊은 것이므로 통과로 본다
        note(f"연결을 끊음: {e}")
        return
    assert r.status_code == 413, f"상태 {r.status_code} (1MB 넘는 본문을 받았다)"


@case(id="SEC-08", area=AREA, title="오류 응답에 내부 정보가 새지 않는다", expect="404 · 422 · 405 응답에 스택 · DB 원문 · 경로 없음")
def test_error_leak(http: Client) -> None:
    for r in (
        http.get("/u/no-such-page"),
        http.post("/judge", data="{broken", headers={"Content-Type": "application/json"}),
        http.get("/search"),
    ):
        assert_no_server_error(r)
        for sign in ("/home/ubuntu", "SKN32-FINAL-3TEAM", "DATABASE_URL", "rds.amazonaws.com"):
            assert sign not in r.text, f"{r.request.method} {r.request.path_url} 응답에 {sign!r} 가 보인다"


@case(id="SEC-09", area=AREA, title="경로 순회 시도", expect="404 (파일이 안 나온다)")
def test_path_traversal(http: Client) -> None:
    for p in ("/static/../.env", "/static/%2e%2e/%2e%2e/.env", "/u/preview/..%5C..%5C.env"):
        r = http.get(p)
        assert r.status_code in (400, 404), f"{p} → {r.status_code}"
        assert "DATABASE_URL" not in r.text and "OPENAI" not in r.text, f"{p} 에서 설정 파일 내용이 보인다"
