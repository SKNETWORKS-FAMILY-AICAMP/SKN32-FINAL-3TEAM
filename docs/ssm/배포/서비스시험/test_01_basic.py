"""1. 접속 · 화면 — 서비스가 떠 있고, 사용자 화면이 오류 없이 열리는가."""

from __future__ import annotations

import pytest
from conftest import BASE, IS_HTTPS, HOST, URL, Client, assert_no_server_error, note

case = pytest.mark.case
AREA = "접속·화면"


@case(id="SVC-01", area=AREA, title="헬스 체크 — 앱과 DB 연결", expect="200 · ok=true · db=up · 주요 표 행 수 > 0")
def test_health(http: Client) -> None:
    r = http.get("/health")
    assert r.status_code == 200, f"상태 {r.status_code}"
    body = r.json()
    assert body.get("ok") is True, f"ok={body.get('ok')} · db={body.get('db')}"
    assert body.get("db") == "up", f"db={body.get('db')}"
    counts = body.get("counts", {})
    empty = [k for k in ("source", "document", "chunk", "chunk_embedding", "dict_entry") if not counts.get(k)]
    assert not empty, f"비어 있는 표: {empty}"
    note("행 수 " + ", ".join(f"{k}={v}" for k, v in counts.items()))


@case(id="SVC-02", area=AREA, title="사이트 주소 → 사용자 첫 화면", expect="/ 가 /u/ 로 넘어간다")
def test_root_redirect(http: Client) -> None:
    r = http.get("/")
    assert r.status_code in (301, 302, 303, 307, 308), f"상태 {r.status_code}"
    assert r.headers.get("Location", "").rstrip("/").endswith("/u"), f"Location={r.headers.get('Location')}"


@case(id="SVC-03", area=AREA, title="http 접속 → https 로 전환", expect="http:// 요청이 https:// 로 넘어간다")
def test_http_to_https(http: Client) -> None:
    if not IS_HTTPS:
        pytest.skip("대상 주소가 https 가 아니다")
    port = f":{URL.port}" if URL.port else ""
    r = http.get(f"http://{HOST}{port}/u/landing")
    assert r.status_code in (301, 302, 307, 308), f"상태 {r.status_code}"
    assert r.headers.get("Location", "").startswith("https://"), f"Location={r.headers.get('Location')}"


SCREENS = [
    ("SCR-01", "/u/", "홈(로그아웃이면 랜딩)"),
    ("SCR-02", "/u/landing", "랜딩"),
    ("SCR-03", "/u/review", "문구 검수 입력"),
    ("SCR-04", "/u/generate", "카피 생성 입력"),
    ("SCR-05", "/u/segments", "소비자 세그먼트"),
    ("SCR-06", "/u/compose", "광고 만들기"),
    ("SCR-07", "/u/history", "검수 이력"),
    ("SCR-08", "/u/matching", "매칭"),
    ("SCR-09", "/u/help", "도움말"),
    ("SCR-10", "/u/help?tab=faq", "자주 묻는 질문"),
    ("SCR-11", "/u/login", "로그인"),
    ("SCR-12", "/u/signup", "회원가입"),
    ("SCR-13", "/u/reset", "비밀번호 재설정"),
    ("SCR-14", "/u/cs", "고객센터"),
]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            p,
            id=cid,
            marks=case(id=cid, area=AREA, title=f"화면 열기 — {name} ({p})", expect="최종 200 · 내부 오류 흔적 없음"),
        )
        for cid, p, name in SCREENS
    ],
)
def test_screen(http: Client, path: str) -> None:
    r = http.get(path, follow=True)
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert "text/html" in r.headers.get("Content-Type", ""), f"Content-Type={r.headers.get('Content-Type')}"
    assert "<html" in r.text.lower(), "HTML 문서가 아니다"
    assert_no_server_error(r)
    if r.history:
        note("넘어감 " + " → ".join(h.headers.get("Location", "") for h in r.history))


@case(id="SVC-04", area=AREA, title="정적 파일 제공", expect="/static/*.js 200 · 자바스크립트 형식")
def test_static(http: Client) -> None:
    r = http.get("/static/rewrite_copy.js")
    assert r.status_code == 200, f"상태 {r.status_code}"
    ctype = r.headers.get("Content-Type", "")
    assert "javascript" in ctype, f"Content-Type={ctype}"


@case(id="SVC-05", area=AREA, title="없는 주소", expect="404 · 내부 오류 흔적 없음")
def test_not_found(http: Client) -> None:
    r = http.get("/u/no-such-page-svc-test")
    assert r.status_code == 404, f"상태 {r.status_code}"
    assert_no_server_error(r)


@case(id="SVC-06", area=AREA, title="응답 압축", expect="gzip 을 받는 브라우저에 압축해 보낸다")
def test_compression(http: Client) -> None:
    r = http.get("/u/landing", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200, f"상태 {r.status_code}"
    enc = r.headers.get("Content-Encoding", "")
    assert enc == "gzip", f"Content-Encoding={enc or '없음'}"
    note(f"Content-Encoding={enc} · 대상 {BASE}")
