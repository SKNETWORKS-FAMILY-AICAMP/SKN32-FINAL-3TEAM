"""서비스 시험 공통 — 설정 · 요청 기록 · 결과 수집 (2026-10-22 · 소성민).

★ 이 폴더는 저장소의 `tests/` 와 **따로 돈다** — 자기 `pytest.ini` 가 있어서 저장소 쪽 `tests/conftest.py` 를 읽지 않는다.
   `tests/` 는 코드를 서버 없이 재는 단위 시험이고, 여기는 **떠 있는 서비스를 밖에서 부르는** 시험이다.
★ 실행은 `run.py` 하나로 한다 — 설정을 환경변수로 넘기고 pytest 를 부른 뒤, 끝나면 이 파일이 로그 · CSV · 보고서를 쓴다.

🚨 로그 · 보고서에 비밀번호 · 쿠키 값 · 이메일 원문을 남기지 않는다(이메일은 가린다).
🚨 시험 문구는 전부 **지어낸 예시**다 — 실제 광고 문구(재배포 불가)를 넣지 않는다.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import pathlib
import socket
import sys
import time
import urllib.parse

import pytest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import report  # noqa: E402 — 같은 폴더의 보고서 작성기

try:
    import requests
except ImportError:  # pragma: no cover
    print("requests 가 없다 — 저장소 루트에서 `uv sync` 를 하거나 `pip install requests` 로 설치한다.")
    raise


# ══════════════════════════════════════════════════════════════════════
#  설정 — run.py 가 환경변수로 넘긴다 (pytest 를 바로 불러도 기본값으로 돈다)
# ══════════════════════════════════════════════════════════════════════
def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


BASE = os.environ.get("SVC_BASE", "https://copylane.site").rstrip("/")
TIMEOUT = float(os.environ.get("SVC_TIMEOUT", "180"))
WITH_LLM = _flag("SVC_WITH_LLM")
ADMIN_OPEN = _flag("SVC_ADMIN_OPEN")
USER_EMAIL = os.environ.get("CL_TEST_EMAIL", "").strip()
USER_PASSWORD = os.environ.get("CL_TEST_PASSWORD", "")
ADMIN_EMAIL = os.environ.get("CL_ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.environ.get("CL_ADMIN_PASSWORD", "")
STARTED = dt.datetime.now()
OUT_DIR = pathlib.Path(
    os.environ.get("SVC_OUT") or HERE / "결과" / STARTED.strftime("%m%d_%H%M")
)

URL = urllib.parse.urlsplit(BASE)
HOST = URL.hostname or ""
IS_HTTPS = URL.scheme == "https"

log = logging.getLogger("svc")


def mask_email(v: str) -> str:
    """`tester@example.com` → `t***@example.com` — 로그 · 보고서에 원문을 남기지 않는다."""
    if "@" not in v:
        return "***"
    local, _, dom = v.partition("@")
    return f"{local[:1]}***@{dom}"


# ══════════════════════════════════════════════════════════════════════
#  결과 기록 — 시험 하나 = 레코드 하나
# ══════════════════════════════════════════════════════════════════════
RESULTS: list[dict] = []
CURRENT: dict | None = None
#: 판정 결과 관찰 — 합격 여부와 별개로 「무엇이 나왔는지」를 보고서에 표로 남긴다
JUDGE_OBS: list[dict] = []


def _case_meta(item: pytest.Item) -> dict:
    m = item.get_closest_marker("case")
    if m is None:
        return {"id": item.name, "area": "기타", "title": item.name, "expect": ""}
    kw = dict(m.kwargs)
    if m.args:
        for key, val in zip(("id", "area", "title", "expect"), m.args, strict=False):
            kw.setdefault(key, val)
    return {
        "id": kw.get("id", item.name),
        "area": kw.get("area", "기타"),
        "title": kw.get("title", item.name),
        "expect": kw.get("expect", ""),
    }


def note(text: str) -> None:
    """지금 시험의 「비고」 칸에 한 줄 더한다 (통과여도 남길 관찰)."""
    if CURRENT is not None:
        CURRENT["notes"].append(text)
    log.info("     · 비고 | %s", text)


# ══════════════════════════════════════════════════════════════════════
#  HTTP 클라이언트 — 요청마다 한 줄씩 로그에 적는다
# ══════════════════════════════════════════════════════════════════════
class Client:
    """`requests.Session` 을 감싼다. 경로만 넘기면 `BASE` 를 붙이고, 걸린 시간을 적는다.

    ★ 리다이렉트는 기본으로 **따라가지 않는다** — 303 · 404 를 그대로 보는 시험이 많다(`follow=True` 로 켠다).
    """

    def __init__(self, name: str = "익명") -> None:
        self.name = name
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "CopyLane-ServiceTest/1.0"
        # zstd · br 은 PC 의 urllib3 판에 따라 못 풀 수 있다 — 늘 풀리는 것만 받는다
        self.s.headers["Accept-Encoding"] = "gzip, deflate"

    def url(self, path: str) -> str:
        return path if path.startswith(("http://", "https://")) else f"{BASE}{path}"

    def request(
        self, method: str, path: str, *, follow: bool = False, timeout: float | None = None, **kw
    ) -> requests.Response:
        url = self.url(path)
        shown = urllib.parse.urlsplit(url)
        label = shown.path + (f"?{shown.query}" if shown.query else "")
        if not url.startswith(BASE):
            label = f"{shown.scheme}://{shown.netloc}{label}"
        t0 = time.perf_counter()
        try:
            r = self.s.request(
                method, url, allow_redirects=follow, timeout=timeout or TIMEOUT, **kw
            )
        except requests.RequestException as e:
            ms = (time.perf_counter() - t0) * 1000
            self._record(method, label, None, ms, 0, type(e).__name__)
            raise AssertionError(f"요청 실패 — {method} {label}: {type(e).__name__}") from e
        ms = (time.perf_counter() - t0) * 1000
        extra = ""
        if r.is_redirect:
            extra = f"→ {r.headers.get('Location', '')}"
        self._record(method, label, r.status_code, ms, len(r.content), extra)
        return r

    def _record(self, method, label, status, ms, size, extra) -> None:
        row = {
            "method": method,
            "path": label,
            "status": status,
            "ms": round(ms, 1),
            "bytes": size,
            "client": self.name,
        }
        if CURRENT is not None:
            CURRENT["requests"].append(row)
        st = status if status is not None else "ERR"
        log.info(
            "     %-6s %-38s %4s  %8.0fms  %6.1fKB %s",
            method,
            label[:38],
            st,
            ms,
            size / 1024,
            extra,
        )

    def get(self, path: str, **kw) -> requests.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> requests.Response:
        return self.request("POST", path, **kw)


# ══════════════════════════════════════════════════════════════════════
#  공용 도우미
# ══════════════════════════════════════════════════════════════════════
SERVER_ERROR_SIGNS = ("Traceback (most recent call last)", "Internal Server Error", "psycopg", "sqlalchemy.exc")


def assert_no_server_error(r: requests.Response) -> None:
    """응답 본문에 서버 내부 오류의 흔적(스택 · DB 오류 원문)이 없는지."""
    body = r.text[:200_000]
    for sign in SERVER_ERROR_SIGNS:
        assert sign not in body, f"응답 본문에 내부 오류 흔적이 있다: {sign!r}"


def set_cookie_headers(r: requests.Response) -> list[str]:
    """응답의 `Set-Cookie` 머리글 전부 (여러 줄)."""
    raw = getattr(r.raw, "headers", None)
    if raw is not None and hasattr(raw, "getlist"):
        return list(raw.getlist("Set-Cookie"))
    v = r.headers.get("Set-Cookie")
    return [v] if v else []


def cookie_attrs(r: requests.Response, name: str) -> str | None:
    """이름이 `name` 인 `Set-Cookie` 줄 — 값은 지우고 속성만 낸다(로그에 값을 남기지 않는다)."""
    for line in set_cookie_headers(r):
        if line.split("=", 1)[0].strip() == name:
            parts = [p.strip() for p in line.split(";")]
            return "; ".join(parts[1:])
    return None


def port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════════════
#  fixture
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture
def http() -> Client:
    """로그인하지 않은 새 세션 — 시험마다 따로."""
    return Client("익명")


def login_user(client: Client, email: str, password: str, nxt: str = "") -> requests.Response:
    """`/u/login` 화면에서 CSRF 토큰을 받아 로그인한다. 응답(303)을 그대로 돌려준다."""
    page = client.get("/u/login")
    assert page.status_code == 200, f"로그인 화면이 {page.status_code}"
    token = report.find_input(page.text, "csrf_token")
    assert token, "로그인 화면에 CSRF 토큰 칸이 없다"
    data = {"email": email, "password": password, "csrf_token": token}
    if nxt:
        data["next"] = nxt
    return client.post("/u/login", data=data)


@pytest.fixture(scope="module")
def member() -> Client:
    """시험 계정으로 로그인한 세션 — 모듈 안에서 같이 쓴다. 계정이 없으면 이 fixture 를 쓰는 시험은 건너뛴다."""
    if not (USER_EMAIL and USER_PASSWORD):
        pytest.skip("시험 계정이 없다 — run.py 실행 때 입력하거나 CL_TEST_EMAIL · CL_TEST_PASSWORD 를 넣는다")
    c = Client("회원")
    r = login_user(c, USER_EMAIL, USER_PASSWORD)
    if r.status_code != 303 or "copylane_user" not in c.s.cookies:
        pytest.fail(f"시험 계정 로그인 실패 — {r.status_code} (계정 · 비밀번호를 확인한다)")
    return c


# ══════════════════════════════════════════════════════════════════════
#  pytest 훅 — 시험마다 레코드를 열고 닫는다
# ══════════════════════════════════════════════════════════════════════
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "case(id, area, title, expect): 시험 항목 메타")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    log.propagate = False
    for h in list(log.handlers):
        log.removeHandler(h)
    fh = logging.FileHandler(OUT_DIR / "서비스시험_로그.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)
    log.info("=" * 78)
    log.info("CopyLane 서비스 시험 시작")
    log.info("대상 주소   : %s", BASE)
    log.info("요청 대기   : %.0f초", TIMEOUT)
    log.info("고쳐 쓰기   : %s", "포함 (--with-llm)" if WITH_LLM else "제외")
    log.info("관리자 화면 : %s", "허용 IP 에서 실행 (--admin-open)" if ADMIN_OPEN else "닫혀 있어야 함")
    log.info("회원 계정   : %s", mask_email(USER_EMAIL) if USER_EMAIL else "없음 — 로그인 시험 건너뜀")
    log.info("관리자 계정 : %s", mask_email(ADMIN_EMAIL) if ADMIN_EMAIL else "없음")
    log.info("=" * 78)


def pytest_report_header(config: pytest.Config) -> list[str]:
    return [f"대상 주소: {BASE}", f"결과 폴더: {OUT_DIR}"]


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    global CURRENT
    meta = _case_meta(item)
    CURRENT = {
        **meta,
        "nodeid": item.nodeid,
        "outcome": "passed",
        "duration": 0.0,
        "message": "",
        "requests": [],
        "notes": [],
        "started": dt.datetime.now().strftime("%H:%M:%S"),
    }
    RESULTS.append(CURRENT)
    log.info("[%s] %s — %s", meta["id"], meta["area"], meta["title"])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    rep = outcome.get_result()
    rec = CURRENT
    if rec is None or rec.get("nodeid") != item.nodeid:
        return
    rec["duration"] += rep.duration
    if rep.skipped:
        reason = ""
        if isinstance(rep.longrepr, tuple) and len(rep.longrepr) == 3:
            reason = str(rep.longrepr[2])
        rec["outcome"] = "skipped"
        rec["message"] = reason.removeprefix("Skipped: ")
    elif rep.failed:
        rec["outcome"] = "failed"
        msg = call.excinfo.exconly() if call.excinfo else str(rep.longrepr)
        msg = msg.replace("AssertionError: ", "").strip()
        # pytest 의 assert 재작성이 붙이는 긴 비교 줄은 첫 줄만 쓴다
        rec["message"] = msg.splitlines()[0][:400] if msg else "실패"
        if rep.when != "call":
            rec["message"] = f"[{rep.when}] {rec['message']}"


@pytest.hookimpl(trylast=True)
def pytest_runtest_logfinish(nodeid: str, location) -> None:
    rec = CURRENT
    if rec is None or rec.get("nodeid") != nodeid:
        return
    label = report.OUTCOME_LABEL[rec["outcome"]]
    tail = f" — {rec['message']}" if rec["message"] else ""
    log.info("  => %s (%.2fs)%s", label, rec["duration"], tail)
    print(f"\n  [{label}] {rec['id']:<8} {rec['title']}{tail}", end="")


def pytest_report_teststatus(report, config):  # noqa: ARG001 — 훅 인자 이름은 pytest 가 정한다
    """pytest 기본 점(`.` `F` `s`) 표시를 끈다 — 진행 표시는 위의 한 줄 요약이 맡는다."""
    if report.when == "call" or (report.when == "setup" and not report.passed):
        return report.outcome, "", ""
    return None


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    finished = dt.datetime.now()
    meta = {
        "base": BASE,
        "started": STARTED.strftime("%Y-%m-%d %H:%M:%S"),
        "finished": finished.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round((finished - STARTED).total_seconds(), 1),
        "with_llm": WITH_LLM,
        "admin_open": ADMIN_OPEN,
        "member": mask_email(USER_EMAIL) if USER_EMAIL else "",
        "admin": mask_email(ADMIN_EMAIL) if ADMIN_EMAIL else "",
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    paths = report.write_all(RESULTS, JUDGE_OBS, meta, OUT_DIR)
    s = report.summarize(RESULTS)
    log.info("=" * 78)
    log.info(
        "끝 — 전체 %d · 통과 %d · 실패 %d · 건너뜀 %d · 걸린 시간 %.1f초",
        s["total"],
        s["passed"],
        s["failed"],
        s["skipped"],
        meta["elapsed_s"],
    )
    for p in paths:
        log.info("저장 — %s", p.name)
    print("\n")
    print("=" * 70)
    print(
        f" 서비스 시험 끝 — 전체 {s['total']} · 통과 {s['passed']} · 실패 {s['failed']} · 건너뜀 {s['skipped']}"
    )
    print(f" 결과 폴더: {OUT_DIR}")
    for p in paths:
        print(f"   - {p.name}")
    print("=" * 70)
