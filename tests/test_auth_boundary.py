"""거버넌스 콘솔의 **경계가 실제로 막는가** (2026-09-12 밤 · D-66 · D-212 · D-213).

🔄 **파일 이름은 그대로 두되 보는 것이 바뀌었다** — 아침에는 「인증이 0줄이니 쓰기를 못 만들게」
   였고, 지금은 **「인증이 섰으니 그것이 실제로 막는가」**다.

★ 여기서 재는 것 일곱 —
  ① 관리자 쓰기는 **허용 목록에 있는 운영 표(공지·약관·문의)만** — 🔄 D-260 ⑦. 거버넌스 쓰기는 여전히 없다
  ② 🚨 **막는 이유가 낡지 않았다** — 게이트의 수명을 게이트가 지킨다 (D-170)
  ③ 로그인 없이 관리자 화면이 안 뜬다 — **읽기도 막는다**
  ④ CSRF 없는 로그인이 거부된다 (주 방어는 `SameSite=Lax`, 토큰은 이중 방어)
  ⑤ 해시가 Argon2id 이고 파라미터가 OWASP preferred 값이다 (P1-7)
  ⑥ 🔴 **클라우드 에디션에서는 관리자·로그인이 아예 안 붙는다** — 라우트가 없으면 404 다
  ⑦ 시도 제한이 실제로 잠근다 (P2-11 — 19 MiB 함수를 여는 것은 지렛대를 만드는 일이다)
  그리고 기본 바인딩(`127.0.0.1`)과 **모든 응답의 보안 헤더**.

🚨 **문자열이 아니라 응답을 받아 본다** — 패턴을 보는 검사는 실패할 수 없다 (D-170).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: 상태를 바꾸는 HTTP 메서드. 🚨 `GET` 은 바꾸면 안 되고, 나머지는 이름부터 바꾸는 쪽이다.
_WRITE_METHODS = {"post", "put", "patch", "delete"}

#: 🔄 **D-260 ⑦ — 관리자 쓰기 허용 목록.** 파일 → 허용하는 (메서드, 라우터 안 경로).
#:    ★ 운영 표(공지 · 약관 · 문의)만 연다. 🚨 **여기 없는 파일·경로의 쓰기는 🔴** — `admin.py`(거버넌스)는 목록에 없다.
#:    ⛔ 종전 게이트는 `admin.py` **한 파일**만 읽었다. 09-22 병합으로 관리자 라우터가 열 개가 되어 나머지 아홉에 POST 가
#:       생겨도 못 봤다(D-260 맥락). 이제 `app/routers/admin*.py` 전부를 구문 트리로 읽는다.
ADMIN_WRITES: dict[str, set[tuple[str, str]]] = {
    "admin_board.py": {("POST", "/notices"), ("POST", "/notices/{notice_id}")},
    "admin_terms.py": {("POST", "")},
    "admin_cs.py": {("POST", "/tickets/{ticket_id}")},
}

#: 허용된 쓰기 핸들러가 **본문에서 반드시 부르는 것** — 로그인 · CSRF 대조 · 쓰기 기록 (D-260 ⑦).
REQUIRED_CALLS = frozenset({"require_governor", "csrf_ok", "audit"})

#: 🔴 **거버넌스 쓰기를 아직 막는 이유.** 🔄 D-260 ⑦ — 운영 표 쓰기는 열었고, 남은 것은 판정 근거를 바꾸는 쓰기다.
#:    ⛔ `reviewed_by` 를 채우는 것과 **등급을 바꾸는 것**은 다른 권한이다. 누가 무엇을 언제 되돌릴 수 있는지가 안 정해졌다.
WRITE_CLOSED_REASON = (
    "거버넌스 쓰기(등급 변경 · 2인 확인 서명)의 절차가 미판정이다 (D-66 · D-260 ⑦)"
)


def _called(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return names


def admin_writes(src: str) -> list[tuple[str, str, str, int, set[str]]]:
    """라우터 소스의 쓰기 핸들러 — (메서드, 경로, 함수 이름, 줄, 본문이 부르는 이름들).

    🚨 문자열이 아니라 **데코레이터를 구문 트리로** 읽는다 — 주석·문서 안의 `@router.post` 에 속지 않는다.
    """
    out = []
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in fn.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            method = dec.func.attr.lower()
            if method not in _WRITE_METHODS:
                continue
            path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "?"
            out.append((method.upper(), path, fn.name, fn.lineno, _called(fn)))
    return out


def write_violations(files: dict[str, str]) -> list[str]:
    """파일 이름 → 소스. 허용 목록 밖의 쓰기 · 필수 호출을 빠뜨린 쓰기를 적는다."""
    bad = []
    for name, src in sorted(files.items()):
        allowed = ADMIN_WRITES.get(name, set())
        for method, path, fn, line, calls in admin_writes(src):
            if (method, path) not in allowed:
                bad.append(f"{name}:{line} {method} {path!r} ({fn}) — 허용 목록 밖")
            elif missing := sorted(REQUIRED_CALLS - calls):
                bad.append(f"{name}:{line} {method} {path!r} ({fn}) — 부르지 않는다: {missing}")
    return bad


@pytest.mark.gate
def test_관리자_쓰기는_허용_목록과_필수_호출_안에서만_생긴다() -> None:
    """🔴 관리자 라우터 **전부**에서 쓰기를 찾는다 (D-260 ⑦).

    ★ 허용 목록(공지·약관·문의) 밖의 쓰기는 🔴 — 거버넌스 쓰기가 조용히 생기는 길을 막는다.
    ★ 허용된 쓰기도 `require_governor` · `csrf_ok` · `audit` 셋을 **본문에서** 불러야 한다.
    ⛔ 사용자 라우터는 다르다 — 사용자 쓰기(가입·마이페이지·문의 접수)는 `app/routers/user.py` 에 있고 이 게이트 밖이다.
    """
    files = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((ROOT / "app" / "routers").glob("admin*.py"))
    }
    assert "admin.py" in files and len(files) > 1, f"🔴 관리자 라우터를 못 찾았다 — {sorted(files)}"
    bad = write_violations(files)
    assert not bad, (
        "🔴 관리자 쓰기 경로가 규칙 밖이다 —\n   "
        + "\n   ".join(bad)
        + f"\n   {WRITE_CLOSED_REASON}\n"
        "   고치는 법 — 운영 표 쓰기면 ADMIN_WRITES 에 한 줄을 더하고 필수 호출 셋을 부른다. 거버넌스 쓰기면 판정이 먼저다"
    )


@pytest.mark.gate
def test_허용_목록의_파일은_실제로_있다() -> None:
    """🚨 목록이 낡으면 이름이 바뀐 파일의 쓰기가 「목록 밖」이 아니라 「목록에 없는 파일」로 빠져나간다 — 둘 다 🔴 지만 원인을 가른다."""
    missing = [n for n in ADMIN_WRITES if not (ROOT / "app" / "routers" / n).exists()]
    assert not missing, f"🔴 허용 목록의 파일이 없다 — {missing}"


@pytest.mark.gate
def test_막는_이유가_낡지_않았다() -> None:
    """🚨 **게이트의 수명을 게이트가 지킨다** (D-170).

    ⛔ 인증이 선 뒤에도 「인증이 없어서 막는다」가 남아 있으면 **거짓말이 게이트 안에 산다.**
    """
    assert "인증" not in WRITE_CLOSED_REASON, (
        "🔴 인증은 이미 섰다 (D-66 구현 · D-213) — 막는 이유를 다시 쓰거나 게이트를 지운다"
    )
    assert len(WRITE_CLOSED_REASON) >= 20, "🔴 사유가 너무 짧다 — 다음 사람이 못 읽는다"


@pytest.mark.gate
def test_로그인_없이는_관리자_화면이_안_뜬다() -> None:
    """🔴 **읽기도 막는다** — 이 화면이 내는 것은 등급 판정 근거와 2인 확인 서명(사람 이름)이다.

    ⛔ 401 이 아니라 **303 → `/login`** 이다. 사람이 보는 화면이라 폼으로 보낸다.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/admin/", follow_redirects=False)
    assert r.status_code == 303, f"🔴 로그인 없이 관리자 화면이 떴다 — {r.status_code}"
    assert r.headers.get("location") == "/login", f"🔴 어디로 보내는지 모른다 — {r.headers}"


@pytest.mark.gate
def test_CSRF_토큰_없는_로그인은_거부된다() -> None:
    """🚨 주 방어는 `SameSite=Lax` 이고 이 토큰은 **이중 방어**다 — 둘 다 둔다 (P1-7)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post("/login", data={"initials": "ohb", "password": "x"})
    assert r.status_code == 403, f"🔴 CSRF 없이 로그인 시도가 통과했다 — {r.status_code}"


@pytest.mark.gate
def test_해시는_Argon2id_이고_파라미터가_OWASP_값이다() -> None:
    """🔴 **PHC 문자열에 알고리즘과 파라미터가 들어 있다** — DB `CHECK` 가 접두어를 강제한다.

    ⛔ 보안점검 P1-7 이 *"단순 SHA-256 1회 해시는 부적절"* 이라 적었고,
       **적어 두는 것과 막는 것은 다른 일이다** (D-117).
    🚨 값은 OWASP Password Storage Cheat Sheet 의 preferred 조합이다 (2026-09 확인).
    """
    from app import auth  # noqa: PLC0415

    h = auth.hash_password("correct horse battery staple")
    assert h.startswith(auth.PHC_PREFIX), f"🔴 Argon2id 가 아니다 — {h[:20]}"
    assert f"m={auth.ARGON2_MEMORY_KIB}" in h, "🔴 메모리 파라미터가 안 실렸다"
    assert f"t={auth.ARGON2_TIME_COST}" in h and f"p={auth.ARGON2_PARALLELISM}" in h
    assert auth.verify_password(h, "correct horse battery staple")
    assert not auth.verify_password(h, "wrong")
    assert not auth.needs_rehash(h), "🔴 방금 만든 해시가 낡았다고 나온다"


@pytest.mark.gate
def test_클라우드_에디션에서는_관리자와_로그인이_안_붙는다() -> None:
    """🔴 **닫는다 = 안 붙인다** (D-213). 라우트가 없으면 404 다.

    ⛔ 「비로컬이면 503」은 폐기했다 — Caddy 뒤에서는 `request.client.host` 가 프록시다.
       `X-Forwarded-For` 를 믿으면 위조 가능하고 안 믿으면 항상 503 이다.
       **판단을 네트워크 위상에 걸면 안 된다** — 에디션은 우리가 아는 사실이다.
    """
    import importlib  # noqa: PLC0415
    import os  # noqa: PLC0415

    import app.api  # noqa: PLC0415
    import app.settings as st  # noqa: PLC0415

    before = os.environ.get("COPYLANE_EDITION")
    try:
        os.environ["COPYLANE_EDITION"] = "cloud"
        st.settings.cache_clear()
        mod = importlib.reload(app.api)
        paths = {r.path for r in mod.app.routes if getattr(r, "path", None)}
        assert not any(p.startswith("/admin") for p in paths), "🔴 클라우드에 /admin 이 붙었다"
        assert "/login" not in paths, "🔴 클라우드에 /login 이 붙었다"
        assert "/health" in paths, "🔴 판정 API 까지 사라졌다 — 닫는 범위가 틀렸다"
    finally:
        if before is None:
            os.environ.pop("COPYLANE_EDITION", None)
        else:
            os.environ["COPYLANE_EDITION"] = before
        st.settings.cache_clear()
        importlib.reload(app.api)


@pytest.mark.gate
def test_시도_제한이_실제로_잠근다() -> None:
    """🚨 Argon2id 19 MiB 를 여는 것은 **DoS 지렛대를 만드는 일**이다 (P2-11).

    ⛔ 세는 것보다 해시가 비싸므로 **막는 판단이 해시 앞에** 와야 한다.
    """
    from app.auth import MAX_ATTEMPTS, throttle  # noqa: PLC0415

    key = "테스트계정"
    throttle.clear(key)
    assert not throttle.blocked(key)
    for _ in range(MAX_ATTEMPTS):
        throttle.fail(key)
    assert throttle.blocked(key), "🔴 시도 제한이 안 걸린다"
    throttle.clear(key)
    assert not throttle.blocked(key), "🔴 해제가 안 된다"


@pytest.mark.gate
def test_기본_바인딩이_로컬이다() -> None:
    """🚨 `--host 0.0.0.0` 하나면 `/admin` 과 `/docs` 가 사내망에 열린다 (P2-10).

    ⛔ 종전에는 `--host` 옵션 자체가 없어 **uvicorn 기본값에 기대고 있었고**,
       그것이 판정이라고 적힌 데가 없었다. 지금은 런처가 기본값으로 박고 경고한다.
    """
    src = (ROOT / "launcher.py").read_text(encoding="utf-8")
    m = re.search(r'host:\s*str\s*=\s*typer\.Option\(\s*"([^"]+)"', src)
    assert m, "🔴 launcher.serve 에 --host 옵션이 없다 — uvicorn 기본값에 기대게 된다"
    assert m.group(1) == "127.0.0.1", f"🔴 기본 바인딩이 로컬이 아니다 — {m.group(1)}"


@pytest.mark.gate
def test_모든_응답에_보안_헤더가_붙는다() -> None:
    """🔴 **헤더는 한 곳에서 전부에 붙어야 뜻이 있다** (D-99).

    ⛔ 종전에는 CSP 가 `base.html` 의 `<meta>` 에만 있었다. 그러면 **템플릿을 쓰는 페이지에만**
       붙는다 — 손으로 쓴 HTML(`/`)과 JSON·오류 응답은 그 밖이었다.
    🚨 **문자열이 아니라 실제 응답 헤더를 받아 본다** (D-170 — 패턴을 보면 실패할 수 없다).
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    client = TestClient(app)
    for path, kind in (("/", "html"), ("/u/", "html"), ("/fixtures", "json")):
        r = client.get(path)
        assert r.status_code == 200, f"🔴 {path} 가 안 뜬다 — {r.status_code}"
        assert r.headers.get("X-Content-Type-Options") == "nosniff", f"🔴 {path}: nosniff 없음"
        assert r.headers.get("X-Frame-Options") == "DENY", f"🔴 {path}: X-Frame-Options 없음"
        assert r.headers.get("Referrer-Policy") == "no-referrer", f"🔴 {path}: Referrer 정책 없음"
        csp = r.headers.get("Content-Security-Policy", "")
        assert csp, f"🔴 {path}: CSP 헤더가 없다"
        assert "frame-ancestors 'none'" in csp, f"🔴 {path}: frame-ancestors 가 없다"
        if kind == "html":
            assert "script-src 'self'" in csp, f"🔴 {path}: script-src 가 안 잠겼다"
            assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0], (
                f"🔴 {path}: script-src 에 'unsafe-inline' 이 열려 있다"
            )
        else:
            assert csp.startswith("default-src 'none'"), f"🔴 {path}: 데이터 응답 CSP 가 느슨하다"


def test_음성_픽스처_쓰기_검사가_실제로_잡는다() -> None:
    """🚨 게이트가 아니다 — **게이트가 잡는다는 것을 잰다** (D-203)."""
    ok = (
        '@router.post("/notices")\n'
        "def create(request):\n"
        "    require_governor(request)\n"
        "    csrf_ok(a, b)\n"
        "    audit('notice_create', 'x', ok=True)\n"
    )
    assert write_violations({"admin_board.py": ok}) == [], "🔴 규칙대로 쓴 핸들러를 잡았다"
    # 허용 목록 밖 경로
    assert write_violations({"admin_board.py": ok.replace("/notices", "/approve")}), (
        "🔴 목록 밖 경로를 못 잡는다"
    )
    # 거버넌스 파일의 쓰기
    assert write_violations({"admin.py": ok}), "🔴 admin.py 의 쓰기를 못 잡는다"
    # 필수 호출 하나 빠짐
    assert write_violations({"admin_board.py": ok.replace("    csrf_ok(a, b)\n", "")}), (
        "🔴 CSRF 누락을 못 잡는다"
    )
    # DELETE 도 쓰기다 · 주석 안의 데코레이터는 쓰기가 아니다
    assert write_violations({"admin_cs.py": '@router.delete("/x")\ndef d():\n    pass\n'})
    assert write_violations({"admin_cs.py": '# @router.post("/x")\n'}) == []
