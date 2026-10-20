#!/usr/bin/env python3
"""perf_report.py — 성능 시험을 한 번에 돌리고 보고서(Markdown)까지 쓴다 (2026-10-20 · 소성민).

`load_test.py` 의 측정 함수를 그대로 쓴다 — 같은 문구 · 같은 셈법이라 10-19 표와 비교된다.
표준 라이브러리만 쓴다 — 서버의 시스템 python3 로 돈다(앱 .venv 불필요).
합격선은 두지 않는다(D-322 결정 A). 「참고 목표」는 sLLM 담당이 말한 고쳐 쓰기 10~20초 하나만 적는다.

쓰는 법 (서버 · tmux 안 · 앱과 sLLM 이 떠 있을 때 · load_test.py 와 같은 폴더)
  python3 ~/perf_report.py                 # 전부 — 약 15~25분
  python3 ~/perf_report.py --quick         # 짧게 — 약 5분 (리허설 전 확인용)
  python3 ~/perf_report.py --skip-rewrite  # sLLM 을 끈 서버
  python3 ~/perf_report.py --note "9b59728 업데이트 직후"

무엇을 하나 — 순서대로
  1. 환경 — 배포 커밋 · 인스턴스 유형 · GPU · /health 행 수 · 인코더 지문(judged_by) · sLLM 잠금 지문
  2. 검수(judge)      동시 1 · 10 · 30
  3. 고쳐 쓰기(rewrite) 동시 1 · 3 · 6   (sLLM 직접)
  4. 섞인 부하        검수 동시 10 과 고쳐 쓰기 동시 3 을 함께 (시연 상황)
  5. 내내 GPU 메모리 · 사용률을 1초마다 재고 단계별 최대치를 남긴다
  6. 시험 시간 동안 앱 · sLLM 로그의 오류 줄 · 5xx 응답 수를 센다 (줄 내용은 옮기지 않는다)
  7. ~/perf_reports/성능시험_<MMDD_HHMM>.md (보고서) · .json (원자료) 을 쓴다

🚨 문구는 load_test.py 의 **지어낸 예시**다. 실제 광고 문구를 넣지 않는다.
🚨 사람이 쓰는 시간에 돌리지 않는다 — 시험 동안 판정이 느려진다. 팀 채팅에 먼저 알린다.
🚨 보고서에 IP · 키 · 로그 원문을 넣지 않는다 — 그대로 저장소에 올려도 되게 쓴다.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    import load_test as lt  # noqa: E402 — 같은 폴더의 load_test.py (측정 함수의 정본)
except ImportError:
    sys.exit("[중단] load_test.py 가 이 파일과 같은 폴더에 없다 — git show origin/ssm:docs/ssm/배포/load_test.py > ~/load_test.py")

APP_DIR = pathlib.Path(os.environ.get("APP_DIR", str(pathlib.Path.home() / "SKN32-FINAL-3TEAM")))
REWRITE_TARGET_S = (10, 20)  # sLLM 담당(lse) 기준 — 한 문장 10~20초 (참고용 · 합격선 아님)


# ── 작은 도구 ────────────────────────────────────────────────────────────────
def sh(*cmd: str, timeout: float = 10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:  # noqa: BLE001 — 없는 명령 · 시간 초과는 「모름」으로 적는다
        return ""


def get_json(url: str, timeout: float = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def post_json(url: str, body: dict, timeout: float = 120) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def instance_type() -> str:
    try:
        tok_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        tok = urllib.request.urlopen(tok_req, timeout=2).read().decode()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": tok},
        )
        return urllib.request.urlopen(req, timeout=2).read().decode()
    except Exception:  # noqa: BLE001
        return "?"


# ── GPU 감시 ────────────────────────────────────────────────────────────────
class GpuWatch:
    """nvidia-smi 를 1초마다 읽어 「지금 단계」의 최대 메모리 · 사용률을 모은다."""

    def __init__(self) -> None:
        self.ok = shutil.which("nvidia-smi") is not None
        self.phase = "대기"
        self.peak: dict[str, dict[str, float]] = {}
        self.total_mib = 0.0
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._t: threading.Thread | None = None

    def start(self) -> None:
        if not self.ok:
            return
        self._proc = subprocess.Popen(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits", "-l", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()

    def _read(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            try:
                used, total, util = (float(x) for x in line.split(",")[:3])
            except ValueError:
                continue
            self.total_mib = total
            p = self.peak.setdefault(self.phase, {"mem": 0.0, "util": 0.0})
            p["mem"] = max(p["mem"], used)
            p["util"] = max(p["util"], util)

    def stop(self) -> None:
        self._stop.set()
        if self._proc:
            self._proc.terminate()


# ── 로그 집계 (줄 내용은 옮기지 않는다) ─────────────────────────────────────
def log_counts(since_epoch: int) -> dict:
    if not shutil.which("journalctl"):
        return {"가능": False, "이유": "journalctl 없음"}
    out = subprocess.run(
        ["journalctl", "-u", "copylane-app", "-u", "copylane-sllm",
         "--since", f"@{since_epoch}", "--no-pager", "-o", "cat"],
        capture_output=True, text=True,
    )
    if out.returncode != 0 and not out.stdout:
        return {"가능": False, "이유": "로그를 읽을 권한이 없다 — sudo python3 로 돌리거나 adm 그룹 확인"}
    lines = out.stdout.splitlines()
    err = [ln for ln in lines if re.search(r"\b(ERROR|CRITICAL)\b|Traceback|Exception", ln)]
    kinds: dict[str, int] = {}
    for ln in err:
        m = re.search(r"([A-Za-z_]+(?:Error|Exception))|(Traceback)|\b(ERROR|CRITICAL)\b", ln)
        k = next((g for g in (m.groups() if m else ()) if g), "기타")
        kinds[k] = kinds.get(k, 0) + 1
    s5 = sum(1 for ln in lines if re.search(r'HTTP/1\.[01]" 5\d\d', ln))
    s4 = sum(1 for ln in lines if re.search(r'HTTP/1\.[01]" 4\d\d', ln))
    return {"가능": True, "오류줄": len(err), "종류": kinds, "5xx": s5, "4xx": s4}


# ── 측정 ────────────────────────────────────────────────────────────────────
def measure(mode: str, url: str, levels: list[int], per: int, timeout: float, gpu: GpuWatch) -> list[dict]:
    rows = []
    for lv in levels:
        name = {"judge": "검수", "rewrite": "고쳐 쓰기"}[mode]
        gpu.phase = f"{name} 동시 {lv}"
        print(f"  · {name} 동시 {lv} × {per} …", flush=True)
        r = lt.run_level(url, mode, lv, per, timeout)
        print(f"    p50 {r['p50']:.2f}s · p95 {r['p95']:.2f}s · 실패 {r['실패']}", flush=True)
        rows.append(r)
    return rows


def warm(mode: str, url: str, timeout: float) -> tuple[bool, float, str]:
    body = {"text": lt.TEXTS[0]} if mode == "judge" else {"text": lt.TEXTS[0], "violation_types": lt.REWRITE_TYPES}
    return lt.one(url, body, timeout)


def mixed(judge_url: str, rewrite_url: str, jl: int, rl: int, per_j: int, per_r: int, gpu: GpuWatch) -> dict:
    gpu.phase = f"섞인 부하 (검수 {jl} + 고쳐 쓰기 {rl})"
    print(f"  · 섞인 부하 — 검수 동시 {jl} 과 고쳐 쓰기 동시 {rl} 를 함께 …", flush=True)
    out: dict[str, dict] = {}
    tj = threading.Thread(target=lambda: out.__setitem__("judge", lt.run_level(judge_url, "judge", jl, per_j, 60)))
    tr = threading.Thread(target=lambda: out.__setitem__("rewrite", lt.run_level(rewrite_url, "rewrite", rl, per_r, 90)))
    tj.start(); tr.start(); tj.join(); tr.join()
    return out


# ── 보고서 ──────────────────────────────────────────────────────────────────
def f2(x: float) -> str:
    return "—" if x != x else f"{x:.2f}"  # NaN → —


def table(rows: list[dict]) -> str:
    h = "| 동시 | 요청 | 성공 | 실패 | p50(초) | p95(초) | 최대(초) | 평균(초) | 처리량/초 | 실패 내역 |\n|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|\n"
    return h + "".join(
        f"| {r['동시']} | {r['요청']} | {r['성공']} | {r['실패']} | {f2(r['p50'])} | {f2(r['p95'])} | "
        f"{f2(r['최대'])} | {f2(r['평균'])} | {r['처리량']:.2f} | {r['실패내역'] or '-'} |\n"
        for r in rows
    )


def findings(res: dict) -> list[str]:
    out = []
    j = res.get("judge") or []
    if j:
        one = next((r for r in j if r["동시"] == 1), j[0])
        top = max(j, key=lambda r: r["처리량"])
        out.append(f"검수 — 혼자 쓸 때 p50 **{f2(one['p50'])}초**, 처리량은 초당 최대 **{top['처리량']:.2f}건**(동시 {top['동시']}).")
        last = j[-1]
        if len(j) >= 2 and last["처리량"] < top["처리량"] * 1.1 and last["동시"] > top["동시"]:
            out.append(f"검수 — 동시 {top['동시']} 이후 처리량이 늘지 않는다 → 그 뒤로는 대기 시간만 늘어난다(동시 {last['동시']} p50 {f2(last['p50'])}초).")
    r = res.get("rewrite") or []
    if r:
        one = next((x for x in r if x["동시"] == 1), r[0])
        lo, hi = REWRITE_TARGET_S
        verdict = "참고 목표 안" if one["p50"] == one["p50"] and one["p50"] <= hi else "참고 목표 밖 — sLLM 담당과 정밀도(bf16→fp16) · 길이 상한 논의"
        out.append(f"고쳐 쓰기 — 혼자 쓸 때 p50 **{f2(one['p50'])}초** (참고 목표 {lo}~{hi}초 · {verdict}).")
        worst = max(r, key=lambda x: x["p95"] if x["p95"] == x["p95"] else 0)
        out.append(f"고쳐 쓰기 — 동시 {worst['동시']} 에서 p95 {f2(worst['p95'])}초(앱의 sLLM 대기 상한 90초).")
    m = res.get("mixed") or {}
    if m.get("judge") and j:
        base = next((x for x in j if x["동시"] == m["judge"]["동시"]), None)
        if base and base["p50"] == base["p50"] and base["p50"] > 0:
            ratio = m["judge"]["p50"] / base["p50"]
            out.append(f"섞인 부하 — 고쳐 쓰기와 함께 돌면 검수 p50 이 {f2(base['p50'])}초 → {f2(m['judge']['p50'])}초 (×{ratio:.1f}).")
    fails = sum(x["실패"] for x in (j + r)) + sum(v["실패"] for v in m.values())
    out.append("실패 요청 **0건**." if fails == 0 else f"실패 요청 **{fails}건** — 실패 내역 칸과 로그 집계를 본다.")
    return out


def write_report(path: pathlib.Path, env: dict, res: dict, gpu: GpuWatch, logs: dict, args: argparse.Namespace, took: float) -> None:
    L: list[str] = []
    L.append(f"# 성능 시험 보고 — {env['시각']}\n")
    L.append("> 자동 생성 — `docs/ssm/배포/perf_report.py` · 측정 함수는 `load_test.py` 와 같다 · 합격선 없는 보고(D-322 결정 A)")
    if args.note:
        L.append(f"> 메모 — {args.note}")
    L.append(f"> 소요 {took/60:.1f}분 · 모드 {'짧게(--quick)' if args.quick else '전체'}\n")

    L.append("## 요약\n")
    L += [f"- {x}" for x in findings(res)]
    if gpu.peak:
        mx = max(v["mem"] for v in gpu.peak.values())
        L.append(f"- GPU 메모리 최대 **{mx:,.0f} / {gpu.total_mib:,.0f} MiB** ({mx / gpu.total_mib * 100:.0f}%).")
    if logs.get("가능"):
        L.append(f"- 시험 시간 로그 — 오류 줄 **{logs['오류줄']}** · 5xx 응답 **{logs['5xx']}**.")
    L.append("")

    L.append("## 1. 환경\n")
    L.append("| 항목 | 값 |\n|---|---|")
    for k in ("배포 커밋", "인스턴스", "GPU", "인코더(judged_by)", "sLLM", "DB 행 수", "uvicorn 워커"):
        L.append(f"| {k} | {env.get(k, '?')} |")
    L.append("")

    if res.get("judge"):
        L.append("## 2. 검수 (`POST /judge` · 앱 전체 경로 — DB · 인코더 · 임베딩)\n")
        L.append(table(res["judge"]))
    if res.get("rewrite"):
        lo, hi = REWRITE_TARGET_S
        L.append(f"## 3. 고쳐 쓰기 (`POST :8765/rewrite` · sLLM 직접 · 참고 목표 한 문장 {lo}~{hi}초)\n")
        L.append(table(res["rewrite"]))
    if res.get("mixed"):
        m = res["mixed"]
        L.append("## 4. 섞인 부하 (검수와 고쳐 쓰기를 함께 — 시연 상황)\n")
        L.append("| 구분 | " + table([m["judge"]]).split("\n", 1)[0].split("| ", 1)[1])
        L.append("|---|" + "---:|" * 9 + "---|")
        for name in ("judge", "rewrite"):
            row = table([m[name]]).splitlines()[2]
            L.append(f"| {'검수' if name == 'judge' else '고쳐 쓰기'} {row}")
        L.append("")

    if gpu.peak:
        L.append("## 5. GPU 메모리 · 사용률 (단계별 최대)\n")
        L.append("| 단계 | 메모리(MiB) | 사용률(%) |\n|---|---:|---:|")
        for ph, v in gpu.peak.items():
            L.append(f"| {ph} | {v['mem']:,.0f} | {v['util']:.0f} |")
        L.append("")
    else:
        L.append("## 5. GPU\n\nnvidia-smi 가 없어 재지 못했다.\n")

    L.append("## 6. 시험 시간 동안의 로그\n")
    if logs.get("가능"):
        L.append(f"- 앱 · sLLM 로그의 오류 줄 {logs['오류줄']} · 응답 5xx {logs['5xx']} · 4xx {logs['4xx']}")
        if logs["종류"]:
            L.append("- 종류별 — " + " · ".join(f"{k} {v}" for k, v in sorted(logs["종류"].items(), key=lambda x: -x[1])))
        L.append("- 🚨 줄 내용은 옮기지 않았다(입력 문구가 섞일 수 있다 · 보안점검 P1-4). 원인은 서버에서 `journalctl -u copylane-app` 로 본다.")
    else:
        L.append(f"- 집계하지 못했다 — {logs.get('이유', '?')}")
    L.append("")

    L.append("## 7. 조건 · 읽는 법\n")
    L.append("- 측정 위치 — 서버 안(127.0.0.1). 인터넷 · Caddy 를 거친 시간은 PC 에서 `load_test.py judge --base http://<주소>` 로 따로 잰다.")
    L.append("- p50 = 절반이 이 시간 안에 끝남(보통 체감) · p95 = 95% 가 이 시간 안 · 처리량 = 초당 끝난 요청 수.")
    L.append(f"- 요청 문구 — `load_test.py` 의 지어낸 예시 {len(lt.TEXTS)}개를 돌려 쓴다.")
    L.append("- 원자료 — 같은 이름의 `.json`.")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ── 실행 ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--sllm", default="http://127.0.0.1:8765")
    ap.add_argument("--quick", action="store_true", help="짧게 — 검수 1·10 · 고쳐 쓰기 1·3 · 요청 수 줄임")
    ap.add_argument("--skip-rewrite", action="store_true", help="sLLM 을 끈 서버")
    ap.add_argument("--skip-mixed", action="store_true")
    ap.add_argument("--out", default=str(pathlib.Path.home() / "perf_reports"))
    ap.add_argument("--note", default="", help="보고서 머리에 남길 메모 (커밋 · 상황)")
    a = ap.parse_args()

    t_start = time.time()
    stamp = time.strftime("%m%d_%H%M")
    outdir = pathlib.Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    judge_url, rewrite_url = a.base.rstrip("/") + "/judge", a.sllm.rstrip("/") + "/rewrite"

    print("== 1. 환경")
    env: dict = {"시각": time.strftime("%Y-%m-%d %H:%M")}
    env["배포 커밋"] = sh("git", "-C", str(APP_DIR), "log", "-1", "--format=%h %s")[:90] or "?"
    env["인스턴스"] = instance_type()
    gq = sh("nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader")
    env["GPU"] = gq or "없음"
    h = get_json(a.base.rstrip("/") + "/health")
    if not h:
        print("[중단] 앱 /health 가 응답하지 않는다 — bash ~/deploy_server.sh check")
        return 1
    env["DB 행 수"] = f"db {h.get('db')} · " + " · ".join(f"{k} {v}" for k, v in (h.get("counts") or {}).items())
    jb = post_json(judge_url, {"text": lt.TEXTS[0]}, 60).get("judged_by", "?")
    env["인코더(judged_by)"] = f"`{jb}`"
    if not a.skip_rewrite:
        s = get_json(a.sllm.rstrip("/") + "/health")
        if not s.get("ok"):
            print("[중단] sLLM /health 가 ok 가 아니다 — --skip-rewrite 로 돌리거나 copylane-sllm 을 확인")
            return 1
        env["sLLM"] = f"{s.get('base', '?')} · {s.get('model', '?')} · {s.get('lock_stage1', '?')} · {s.get('lock_stage2', '?')}"
    else:
        env["sLLM"] = "건너뜀(--skip-rewrite)"
    unit = sh("systemctl", "cat", "copylane-app")
    m = re.search(r"--workers[ =](\d+)", unit)
    env["uvicorn 워커"] = m.group(1) if m else "1 (기본)"
    for k, v in env.items():
        print(f"  {k}: {v}")

    gpu = GpuWatch()
    gpu.start()
    res: dict = {}
    try:
        print("\n== 2. 검수 — 예열")
        ok, t, c = warm("judge", judge_url, 60)
        print(f"  예열 {'성공' if ok else '실패'} {t:.1f}초 ({c})")
        if not ok:
            print("[중단] 검수 예열 실패")
            return 1
        jl, jp = ([1, 10], 3) if a.quick else ([1, 10, 30], 5)
        res["judge"] = measure("judge", judge_url, jl, jp, 60, gpu)

        if not a.skip_rewrite:
            print("\n== 3. 고쳐 쓰기 — 예열 (처음은 모델을 올리느라 느리다)")
            gpu.phase = "고쳐 쓰기 예열"
            ok, t, c = warm("rewrite", rewrite_url, 120)
            print(f"  예열 {'성공' if ok else '실패'} {t:.1f}초 ({c})")
            if ok:
                rl, rp = ([1, 3], 1) if a.quick else ([1, 3, 6], 2)
                res["rewrite"] = measure("rewrite", rewrite_url, rl, rp, 90, gpu)
                if not a.skip_mixed:
                    print("\n== 4. 섞인 부하")
                    res["mixed"] = mixed(judge_url, rewrite_url, 10, 3, 3 if a.quick else 5, 1 if a.quick else 2, gpu)
            else:
                print("  [확인] 고쳐 쓰기 예열 실패 — 3 · 4 를 건너뛴다 (보고서에 남는다)")
                env["sLLM"] += " · ⚠️ 예열 실패로 측정 못 함"
    finally:
        gpu.phase = "끝"
        time.sleep(1.5)
        gpu.stop()

    print("\n== 5. 로그 집계")
    logs = log_counts(int(t_start))
    print(f"  {logs}")

    took = time.time() - t_start
    md = outdir / f"성능시험_{stamp}.md"
    js = outdir / f"성능시험_{stamp}.json"
    write_report(md, env, res, gpu, logs, a, took)
    js.write_text(json.dumps({"env": env, "results": res, "gpu_peak": gpu.peak, "gpu_total_mib": gpu.total_mib,
                              "logs": logs, "took_s": round(took, 1), "args": vars(a)},
                             ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n✅ 보고서 — {md}\n   원자료 — {js}")
    print("   MobaXterm SFTP 로 내려받아 docs/ssm/배포/성능시험/ 에 넣는다 (IP · 키 · 로그 원문은 들어 있지 않다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
