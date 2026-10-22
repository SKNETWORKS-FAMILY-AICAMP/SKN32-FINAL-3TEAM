#!/usr/bin/env python3
"""test_evidence.py — 서비스 테스트 시간대의 서버 기록을 모아 **증빙 보고서(Markdown)** 를 쓴다 (2026-10-22 · 소성민).

서비스 테스트는 사람이 화면에서 기능을 쓴다. 그때 서버에 남는 기록을 시험이 끝난 뒤 시간대로 잘라 집계하고,
서비스테스트 계획서의 항목 ID(B-·C-·D-·F-)마다 「로그에 무엇이 남았는지」를 붙인다.

쓰는 법 (서버 · 시험이 끝난 뒤 · 시각은 KST)
  python3 ~/SKN32-FINAL-3TEAM/docs/ssm/배포/test_evidence.py --since "2026-10-22 14:00" --until "2026-10-22 16:10"
  python3 … --since … --until … --marker 시험마커1022     # F-4 — 입력 문구가 로그에 남는지 (0 이어야 한다)
  python3 … --since … --until … --no-db                   # 오류 로그 표(app_error_log)를 건너뛴다

읽는 기록 — 모두 서버 안
  ① Caddy 접속 기록  /var/log/caddy/copylane-access.log* (JSON · 도메인판에만 있다 · sudo 로 읽는다)
     → 경로별 요청 수 · 응답 코드 · 응답 시간. 앱까지 안 가는 응답(닫는 경로 · 관리자 IP 제한 404)도 여기에만 있다
  ② 앱 · sLLM 로그    journalctl -u copylane-app -u copylane-sllm
     → 오류 · 경고 줄 수(종류만) · 접속 사실(audit — 가입 · 로그인 · 문의 등) · 서비스 재시작
  ③ 오류 로그 표      app_error_log (demo 에디션) — 앱 .venv 로 건수만 센다

🚨 보고서에 넣지 않는 것 — IP · 쿼리 문자열 값 · 요청 본문 · 로그 줄 원문 · audit 의 actor(이니셜 · 계정 id).
   경로의 id(UUID · 숫자)는 {id} 로 바꾼다. 그대로 저장소에 올려도 되게 쓴다 (보안점검 P1-4 · README 규칙).
🚨 판정(통과 · 실패)은 사람이 한다 — 이 보고서는 「그 시간에 그 기능이 불렸고 서버가 이렇게 답했다」는 근거다.

출력  ~/test_evidence/서비스테스트증빙_<MMDD_HHMM>.md · .json
표준 라이브러리만 쓴다 — 시스템 python3 로 돈다 (오류 로그 표만 앱 .venv 를 `uv run` 으로 빌린다).
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import ipaddress
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import unquote

KST = timezone(timedelta(hours=9))
APP_DIR = pathlib.Path(os.environ.get("APP_DIR", pathlib.Path.home() / "SKN32-FINAL-3TEAM"))
DEPLOY_CONF = pathlib.Path(os.environ.get("DEPLOY_CONF", pathlib.Path.home() / ".copylane-deploy"))
CADDY_LOG_DIR = pathlib.Path(os.environ.get("CADDY_LOG_DIR", "/var/log/caddy"))
CADDY_LOG_GLOB = "copylane-access*.log*"

# 경로 안의 id 를 {id} 로 — UUID · 16진 12자 이상 · 숫자
_ID = re.compile(
    r"/(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{12,}|\d+)(?=/|$)"
)
_UVICORN = re.compile(r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS) (\S+) HTTP/[0-9.]+" (\d{3})')
_AUDIT = re.compile(r"audit event=(\w+) actor=\S+ ok=(True|False)")
_ERRLINE = re.compile(r"\b(ERROR|CRITICAL)\b|Traceback")
_WARNLINE = re.compile(r"\bWARNING\b")
_KIND = re.compile(r"([A-Za-z_]+(?:Error|Exception))")

# ── 시험 항목 ↔ 기록 ────────────────────────────────────────────────────────
# (ID, 설명, 확인할 것) — 확인할 것: ("req", 메서드, 경로 정규식, 기대 코드 집합) · ("audit", 이벤트, ok) · 특수 키
OK2 = {"2xx", "3xx"}
CHECKS: list[tuple[str, str, list[tuple]]] = [
    ("B-1", "첫 화면", [("req", "GET", r"^/$", {"3xx"}), ("req", "GET", r"^/u/?$", {"2xx"})]),
    ("B-2", "회원가입", [("req", "POST", r"^/u/signup$", OK2), ("audit", "user_signup", True)]),
    ("B-3", "가입 입력 오류", [("req", "POST", r"^/u/signup$", {"4xx"})]),
    (
        "B-4",
        "로그인 · 로그아웃",
        [
            ("audit", "user_login", True),
            ("audit", "user_login", False),
            ("audit", "user_logout", True),
        ],
    ),
    ("B-5~7", "검수", [("req", "POST", r"^/u/(review|judge)$", {"2xx"})]),
    ("B-8", "검수 입력 경계", [("req", "POST", r"^/u/(review|judge)$", {"4xx"})]),
    ("B-9", "고쳐 쓰기", [("req", "POST", r"^/u/review/rewrite$", {"2xx"})]),
    ("B-11", "카피 생성", [("req", "POST", r"^/u/generate$", {"2xx"})]),
    ("B-12", "검수 결과에서 생성", [("req", "POST", r"^/u/generate/from-review$", OK2)]),
    ("B-13", "작성 + 검수", [("req", "POST", r"^/u/compose(/judge)?$", {"2xx"})]),
    ("B-14", "이력", [("req", "GET", r"^/u/history$", {"2xx"})]),
    (
        "B-15",
        "마이페이지",
        [("req", "POST", r"^/u/mypage$", OK2), ("audit", "user_profile_save", True)],
    ),
    ("B-16", "고객센터 문의", [("req", "POST", r"^/u/cs$", OK2), ("audit", "user_ticket", True)]),
    (
        "B-17",
        "공지 · 도움말",
        [("req", "GET", r"^/u/notices", {"2xx"}), ("req", "GET", r"^/u/help$", {"2xx"})],
    ),
    (
        "B-18",
        "계정 끄기",
        [("req", "POST", r"^/u/mypage/disable$", OK2), ("audit", "user_account_disable", True)],
    ),
    ("C-1", "관리자 로그인", [("audit", "login", True)]),
    ("C-2", "대시보드", [("req", "GET", r"^/admin/(dashboard)?$", {"2xx"})]),
    ("C-3", "회원 목록", [("req", "GET", r"^/admin/members", {"2xx"})]),
    (
        "C-4",
        "문의 처리",
        [
            ("req", "POST", r"^/admin/cs/tickets/\{id\}$", OK2),
            ("audit", "admin_ticket_update", True),
        ],
    ),
    (
        "C-5",
        "공지 작성",
        [("req", "POST", r"^/admin/board/notices", OK2), ("audit", "admin_notice_create", True)],
    ),
    ("C-6", "오류 로그", [("req", "GET", r"^/admin/errors", {"2xx"})]),
    ("C-7", "통계 · 품질", [("req", "GET", r"^/admin/(stats|quality)", {"2xx"})]),
    ("C-8", "관리자 접근 제한", [("admin_gate",)]),
    ("D-1", "없는 주소", [("unknown_404",)]),
    ("D-3", "로그인 필요 화면", [("req", "GET", r"^/u/(history|mypage)$", {"3xx"})]),
    ("D-4", "오래된 화면 제출", [("req", "POST", r"^/u/", {"403"})]),
    ("D-9", "오류 집계", [("errors",)]),
    ("F-2", "닫는 경로", [("req", "GET", r"^/(docs|redoc|openapi\.json|fixtures)", {"404"})]),
    ("F-4", "입력 원문 로그", [("marker",)]),
    ("F-5", "서비스 재시작 · 복구", [("restarts",)]),
]
# 앱이 아는 경로의 첫 마디 — D-1 「없는 주소」를 가르는 데만 쓴다
KNOWN_TOP = {
    "",
    "u",
    "admin",
    "login",
    "logout",
    "health",
    "static",
    "judge",
    "search",
    "favicon.ico",
    "dev",
}


def cls(code: int) -> str:
    return f"{code // 100}xx"


def norm(uri: str) -> tuple[str, list[str]]:
    """경로만 남기고 id 를 {id} 로. 쿼리는 **키 이름만** 돌려준다 (값은 버린다)."""
    path, _, q = uri.partition("?")
    path = unquote(path)
    keys = sorted({kv.split("=", 1)[0] for kv in q.split("&") if kv}) if q else []
    return _ID.sub("/{id}", path) or "/", keys


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def parse_kst(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=KST)


def read_conf() -> dict:
    out = {}
    if DEPLOY_CONF.exists():
        for ln in DEPLOY_CONF.read_text(encoding="utf-8").splitlines():
            m = re.match(r'^([A-Z_]+)="?([^"]*)"?\s*$', ln.strip())
            if m:
                out[m.group(1)] = m.group(2)
    return out


def allowed_nets(conf: dict) -> list:
    nets = []
    for tok in conf.get("ADMIN_ALLOW_IPS", "").split():
        with contextlib.suppress(ValueError):
            nets.append(ipaddress.ip_network(tok, strict=False))
    return nets


# ── ① Caddy ─────────────────────────────────────────────────────────────────
def caddy_lines() -> tuple[list[str], str]:
    files = sorted(CADDY_LOG_DIR.glob(CADDY_LOG_GLOB)) if CADDY_LOG_DIR.exists() else []
    if not files:
        r = subprocess.run(
            ["sudo", "-n", "sh", "-c", f"ls {CADDY_LOG_DIR}/{CADDY_LOG_GLOB} 2>/dev/null"],
            capture_output=True,
            text=True,
        )
        files = [pathlib.Path(x) for x in r.stdout.split()]
    if not files:
        return [], "Caddy 접속 기록 파일이 없다 — 도메인판(Caddyfile)에만 log 가 있다"
    lines: list[str] = []
    for f in files:
        try:
            data = f.read_bytes()
        except PermissionError:
            r = subprocess.run(["sudo", "-n", "cat", str(f)], capture_output=True)
            if r.returncode != 0:
                return (
                    [],
                    "Caddy 기록을 읽을 권한이 없다 — sudo 가 비밀번호를 묻지 않는 계정에서 돌린다",
                )
            data = r.stdout
        if f.suffix == ".gz":
            data = gzip.decompress(data)
        lines += data.decode("utf-8", "replace").splitlines()
    return lines, ""


def caddy_reqs(lines: list[str], t0: float, t1: float) -> list[dict]:
    out = []
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        ts, rq = e.get("ts"), e.get("request") or {}
        if not isinstance(ts, (int, float)) or not (t0 <= ts <= t1) or "status" not in e:
            continue
        path, keys = norm(rq.get("uri", ""))
        out.append(
            {
                "m": rq.get("method", "?"),
                "p": path,
                "k": keys,
                "s": int(e["status"]),
                "d": float(e.get("duration") or 0),
                "ip": rq.get("client_ip") or rq.get("remote_ip") or "",
            }
        )
    return out


# ── ② journal ───────────────────────────────────────────────────────────────
def journal(t0: datetime, t1: datetime) -> tuple[list[str], list[str], str]:
    if not shutil.which("journalctl"):
        return [], [], "journalctl 없음"
    since, until = (
        t0.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        t1.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )
    base = ["journalctl", "--since", since, "--until", until, "--no-pager"]
    a = subprocess.run(
        base + ["-u", "copylane-app", "-u", "copylane-sllm", "-o", "cat"],
        capture_output=True,
        text=True,
    )
    if a.returncode != 0 and not a.stdout:
        return [], [], "로그를 읽을 권한이 없다 — adm 그룹 확인 또는 sudo python3"
    s = subprocess.run(
        base + ["-u", "copylane-app", "-u", "copylane-sllm", "-u", "caddy", "-o", "short-iso"],
        capture_output=True,
        text=True,
    )
    sysl = [
        ln
        for ln in s.stdout.splitlines()
        if re.search(r"systemd\[1\]: (Started|Stopped|Stopping) ", ln)
    ]
    return a.stdout.splitlines(), sysl, ""


# ── ③ app_error_log ─────────────────────────────────────────────────────────
def error_table(t0: datetime, t1: datetime) -> dict:
    code = (
        "import json,sys,psycopg\nfrom app.settings import dsn\n"
        "with psycopg.connect(dsn()) as c:\n"
        '  r=c.execute("select level,count(*) from app_error_log where occurred_at between %s and %s group by 1",(sys.argv[1],sys.argv[2])).fetchall()\n'
        "  k=c.execute(\"select coalesce(exc_type,'-'),count(*) from app_error_log where occurred_at between %s and %s group by 1 order by 2 desc limit 10\",(sys.argv[1],sys.argv[2])).fetchall()\n"
        "print(json.dumps({'level':dict(r),'kind':dict(k)}))\n"
    )
    uv = shutil.which("uv") or str(pathlib.Path.home() / ".local/bin/uv")
    try:
        r = subprocess.run(
            [uv, "run", "--no-sync", "python", "-c", code, t0.isoformat(), t1.isoformat()],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"가능": False, "이유": type(e).__name__}
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["?"])[-1]
        return {"가능": False, "이유": re.sub(r"\S+@\S+", "…", last)[:120]}
    d = json.loads(r.stdout.strip().splitlines()[-1])
    return {"가능": True, **d}


def sys_event(line: str) -> str:
    """`2026-10-22T14:03:10+0000 host systemd[1]: Started copylane-app.service - …` → `23:03:10 Started copylane-app` (KST)."""
    m = re.match(r"^(\S+)\s.*?systemd\[1\]: (Started|Stopped|Stopping) ([\w.@-]+)", line)
    if not m:
        return "?"
    ts = m.group(1)
    ts = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", ts)
    try:
        hhmm = datetime.fromisoformat(ts).astimezone(KST).strftime("%H:%M:%S")
    except ValueError:
        hhmm = "?"
    return f"{hhmm} {m.group(2)} {m.group(3).removesuffix('.service')}"


# ── 집계 ────────────────────────────────────────────────────────────────────
def summarize(reqs: list[dict]) -> list[dict]:
    g: dict[tuple, dict] = {}
    for r in reqs:
        k = (r["m"], r["p"])
        x = g.setdefault(k, {"m": r["m"], "p": r["p"], "n": 0, "codes": {}, "d": [], "keys": set()})
        x["n"] += 1
        x["codes"][r["s"]] = x["codes"].get(r["s"], 0) + 1
        x["d"].append(r["d"])
        x["keys"].update(r["k"])
    out = []
    for x in sorted(g.values(), key=lambda v: (v["p"], v["m"])):
        out.append(
            {
                **x,
                "p50": pct(x["d"], 50),
                "p95": pct(x["d"], 95),
                "keys": sorted(x["keys"]),
                "d": None,
            }
        )
    return out


def match(reqs, method, rx, want):
    hit = [r for r in reqs if r["m"] == method and re.search(rx, r["p"])]
    good = [r for r in hit if cls(r["s"]) in want or str(r["s"]) in want]
    codes: dict[int, int] = {}
    for r in hit:
        codes[r["s"]] = codes.get(r["s"], 0) + 1
    return len(hit), len(good), codes


def codes_txt(codes: dict) -> str:
    return " · ".join(f"{k}×{v}" for k, v in sorted(codes.items())) or "—"


def evaluate(reqs, audits, ctx) -> list[dict]:
    rows = []
    for cid, name, checks in CHECKS:
        parts, found = [], True
        for c in checks:
            if c[0] == "req":
                _, m, rx, want = c
                n, good, codes = match(reqs, m, rx, want)
                pretty = rx.strip("^$").replace("\\", "").replace("|", "/")
                parts.append(
                    f"{m} {pretty} — {n}건 ({codes_txt(codes)}) · 기대 {'/'.join(sorted(want))} {good}건"
                )
                found &= good > 0
            elif c[0] == "audit":
                _, ev, ok = c
                n = audits.get((ev, ok), 0)
                parts.append(f"audit {ev} ok={ok} — {n}건")
                found &= n > 0
            elif c[0] == "admin_gate":
                a, b = ctx["admin_allowed"], ctx["admin_other"]
                parts.append(
                    f"/admin* 허용 IP 요청 {a['n']}건({codes_txt(a['codes'])}) · 그 밖 {b['n']}건({codes_txt(b['codes'])})"
                )
                found &= b["n"] > 0 and set(b["codes"]) <= {404}
            elif c[0] == "unknown_404":
                n, kinds = ctx["unknown_404"]
                parts.append(f"앱이 모르는 경로 404 — {n}건 · 경로 {kinds}종")
                found &= n > 0
            elif c[0] == "errors":
                e = ctx["errors"]
                parts.append(
                    f"5xx — Caddy {e['caddy_5xx']} · 앱 {e['app_5xx']} / 오류 줄 {e['err_lines']} / 오류 로그 표 {e['table']}"
                )
                found = None if e["caddy_5xx"] or e["app_5xx"] or e["err_lines"] else True
            elif c[0] == "marker":
                mk = ctx["marker"]
                if mk is None:
                    parts.append("--marker 를 주지 않아 세지 않았다")
                    found = None
                else:
                    parts.append(f"앱 · sLLM 로그 {mk[0]}건 · Caddy 기록 {mk[1]}건 (0 이어야 한다)")
                    found = None if mk[0] or mk[1] else True
            elif c[0] == "restarts":
                parts.append(f"systemd 시작 기록 — {ctx['restarts']}")
                found &= bool(ctx["restart_n"])
        rows.append(
            {
                "id": cid,
                "name": name,
                "evidence": parts,
                "flag": "기록 있음"
                if found is True
                else ("확인 필요" if found is None else "기록 없음"),
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="서비스 테스트 증빙 — 시험 시간대 서버 기록 집계")
    ap.add_argument("--since", required=True, help='시작 (KST) "YYYY-MM-DD HH:MM"')
    ap.add_argument("--until", required=True, help='끝 (KST) "YYYY-MM-DD HH:MM"')
    ap.add_argument(
        "--marker", default=None, help="F-4 — 시험에 넣은 표시 문자열(로그에 0건이어야 한다)"
    )
    ap.add_argument("--no-db", action="store_true", help="오류 로그 표(app_error_log)를 건너뛴다")
    ap.add_argument("--note", default="", help="보고서 머리 메모 (기준판 · 테스터 등)")
    ap.add_argument("--out", default=str(pathlib.Path.home() / "test_evidence"))
    a = ap.parse_args()
    t0, t1 = parse_kst(a.since), parse_kst(a.until)
    if t1 <= t0:
        sys.exit("[중단] --until 이 --since 보다 늦어야 한다")

    conf = read_conf()
    nets = allowed_nets(conf)
    commit = (
        subprocess.run(
            ["git", "-C", str(APP_DIR), "log", "-1", "--format=%h %s"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        or "?"
    )

    clines, cwhy = caddy_lines()
    reqs = caddy_reqs(clines, t0.timestamp(), t1.timestamp())
    jlines, syslines, jwhy = journal(t0, t1)

    # audit (actor 는 버린다)
    audits: dict[tuple, int] = {}
    for ln in jlines:
        m = _AUDIT.search(ln)
        if m:
            k = (m.group(1), m.group(2) == "True")
            audits[k] = audits.get(k, 0) + 1
    err = [ln for ln in jlines if _ERRLINE.search(ln)]
    warn = [ln for ln in jlines if _WARNLINE.search(ln)]
    kinds: dict[str, int] = {}
    for ln in err:
        m = _KIND.search(ln)
        k = m.group(1) if m else ("Traceback" if "Traceback" in ln else "ERROR")
        kinds[k] = kinds.get(k, 0) + 1
    app_5xx = sum(1 for ln in jlines if (m := _UVICORN.search(ln)) and m.group(3).startswith("5"))
    table = {"가능": False, "이유": "--no-db"} if a.no_db else error_table(t0, t1)

    # 관리자 경로 — 허용 IP 인지 아닌지로만 가른다 (IP 는 쓰지 않는다)
    def in_allow(ip: str) -> bool:
        try:
            return any(ipaddress.ip_address(ip) in n for n in nets)
        except ValueError:
            return False

    adm = [r for r in reqs if r["p"].startswith("/admin")]

    def bucket(rs):
        c: dict[int, int] = {}
        for r in rs:
            c[r["s"]] = c.get(r["s"], 0) + 1
        return {"n": len(rs), "codes": c}

    admin_allowed = bucket([r for r in adm if in_allow(r["ip"])])
    admin_other = bucket([r for r in adm if not in_allow(r["ip"])])

    unknown = [
        r for r in reqs if r["s"] == 404 and r["p"].strip("/").split("/")[0] not in KNOWN_TOP
    ]
    unknown_u = [r for r in reqs if r["s"] == 404 and r["p"].startswith("/u/")]
    unk = unknown + unknown_u

    marker = None
    if a.marker:
        marker = (sum(a.marker in ln for ln in jlines), sum(a.marker in ln for ln in clines))

    restart_n = len([s for s in syslines if "Started" in s])
    restarts = " · ".join(sys_event(s) for s in syslines[:12]) or "없음"

    ctx = {
        "admin_allowed": admin_allowed,
        "admin_other": admin_other,
        "unknown_404": (len(unk), len({r["p"] for r in unk})),
        "errors": {
            "caddy_5xx": sum(1 for r in reqs if r["s"] >= 500),
            "app_5xx": app_5xx,
            "err_lines": len(err),
            "table": (
                sum(table.get("level", {}).values())
                if table.get("가능")
                else f"못 셈({table.get('이유')})"
            ),
        },
        "marker": marker,
        "restarts": restarts,
        "restart_n": restart_n,
    }
    rows = evaluate(reqs, audits, ctx)
    routes = summarize(reqs)

    # ── 보고서 ──
    now = datetime.now(KST)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"서비스테스트증빙_{now:%m%d_%H%M}"
    L = [
        f"# 서비스 테스트 증빙 — {t0:%Y-%m-%d %H:%M} ~ {t1:%H:%M} KST",
        "",
        "> 자동 생성 — `docs/ssm/배포/test_evidence.py` · 시험 시간대 서버 기록 집계 · 판정은 사람이 한다",
        f"> 메모 — {a.note or '-'}",
        f"> 만든 시각 {now:%Y-%m-%d %H:%M} KST",
        "",
        "## 1. 환경",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 서버 판 | {commit} |",
        f"| Caddy 판 | {conf.get('CADDY_MODE', '?')} |",
        f"| 관리자 허용 IP 수 | {len(nets)} |",
        f"| 기록 출처 | Caddy {len(reqs)}건{' — ' + cwhy if cwhy else ''} · 앱/sLLM 로그 {len(jlines)}줄{' — ' + jwhy if jwhy else ''} · 오류 로그 표 {'읽음' if table.get('가능') else '못 읽음'} |",
        "",
        "## 2. 항목별 증빙 (서비스테스트 계획서 ID)",
        "",
        "「기록 있음」= 기대한 요청 · 응답이 시간대 안에 남아 있다. 「기록 없음」= 시험을 안 했거나 다른 응답이 났다 — 결과 칸과 맞춰 본다. 「확인 필요」= 0 이어야 할 것이 나왔다.",
        "",
        "| ID | 항목 | 로그 근거 | 자동 표시 |",
        "|---|---|---|---|",
    ]
    for r in rows:
        L.append(f"| {r['id']} | {r['name']} | {'<br>'.join(r['evidence'])} | {r['flag']} |")
    L += [
        "",
        "화면에서만 확인하는 항목(로그로 증빙 안 됨) — B-10 · D-2 · D-5 ~ D-8 · F-1 · F-3 · E-3 → 캡처 · 결과 칸으로 증빙.",
        "",
        "## 3. 경로별 요청 (Caddy · 시험 시간대)",
        "",
        "| 메서드 | 경로 | 요청 | 응답 코드 | p50(초) | p95(초) | 쿼리 키 |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    for x in routes:
        L.append(
            f"| {x['m']} | `{x['p']}` | {x['n']} | {codes_txt(x['codes'])} | {x['p50']:.2f} | {x['p95']:.2f} | {', '.join(x['keys']) or '-'} |"
        )
    tot = len(reqs)
    by_cls: dict[str, int] = {}
    for r in reqs:
        by_cls[cls(r["s"])] = by_cls.get(cls(r["s"]), 0) + 1
    L += [
        "",
        f"합계 {tot}건 — " + " · ".join(f"{k} {v}" for k, v in sorted(by_cls.items())),
        "",
        "## 4. 접속 사실 (audit · actor 제외)",
        "",
        "| 이벤트 | 성공 | 실패 |",
        "|---|---:|---:|",
    ]
    for ev in sorted({k[0] for k in audits}):
        L.append(f"| {ev} | {audits.get((ev, True), 0)} | {audits.get((ev, False), 0)} |")
    if not audits:
        L.append("| (없음) | 0 | 0 |")
    L += [
        "",
        "## 5. 오류 · 경고",
        "",
        f"- 응답 5xx — Caddy {ctx['errors']['caddy_5xx']}건 · 앱 {app_5xx}건",
        f"- 앱 · sLLM 로그 — 오류 줄 {len(err)} · 경고 줄 {len(warn)} · 종류 {json.dumps(kinds, ensure_ascii=False) if kinds else '없음'}",
        "- 오류 로그 표(app_error_log) — "
        + (
            f"수준별 {json.dumps(table['level'], ensure_ascii=False)} · 종류 {json.dumps(table['kind'], ensure_ascii=False)}"
            if table.get("가능")
            else f"못 읽음 ({table.get('이유')})"
        ),
        f"- 서비스 시작 · 중지 기록 — {restarts}",
        "- 🚨 줄 원문은 옮기지 않았다(입력 문구가 섞일 수 있다 · 보안점검 P1-4). 원인은 서버에서 `journalctl -u copylane-app --since …` 로 본다.",
        "",
        "## 6. 읽는 법",
        "",
        "- 시각은 모두 KST. 시간대 밖 요청(성능 시험 · 다른 사람 접속)은 들어가지 않는다 — 시험 중 사이트 사용을 팀에 막아 두면 깨끗하다.",
        "- Caddy 기록은 도메인으로 들어온 요청만 있다. IP 로 들어온 요청 · http→https 넘김은 남지 않는다.",
        "- 경로의 id 는 {id} 로 바꿨고, 쿼리는 키 이름만 남겼다. IP · 계정 · 입력 문구는 어디에도 없다.",
        "",
    ]
    stem.with_suffix(".md").write_text("\n".join(L), encoding="utf-8")
    stem.with_suffix(".json").write_text(
        json.dumps(
            {
                "since": a.since,
                "until": a.until,
                "commit": commit,
                "checks": rows,
                "routes": routes,
                "audit": {f"{k[0]}:{k[1]}": v for k, v in audits.items()},
                "errors": ctx["errors"],
                "error_kinds": kinds,
                "error_table": table,
            },
            ensure_ascii=False,
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"[OK] {stem.with_suffix('.md')}")
    flags = {}
    for r in rows:
        flags[r["flag"]] = flags.get(r["flag"], 0) + 1
    print(
        "     "
        + " · ".join(f"{k} {v}" for k, v in flags.items())
        + f" · Caddy {tot}건 · 5xx {ctx['errors']['caddy_5xx']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
