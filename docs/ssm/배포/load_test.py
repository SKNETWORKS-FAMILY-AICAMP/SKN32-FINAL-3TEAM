#!/usr/bin/env python3
"""load_test.py — 배포 서버 부하 시험 (2026-10-15 · 소성민 · 배포점검 10-14 #3).

표준 라이브러리만 쓴다 — 서버의 시스템 python3 로 바로 돈다(앱 .venv 불필요).
합격선은 두지 않는다 — 잰 수를 작업기록에 그대로 적는다(D-322 결정 A 와 같은 태도).

쓰는 법 (서버 · tmux 창 3 · 앱과 sLLM 이 떠 있을 때)
  python3 load_test.py judge                      # 검수 — 동시 1 · 10 · 30
  python3 load_test.py rewrite                    # 고쳐 쓰기(sLLM 직접) — 동시 1 · 3 · 6
  python3 load_test.py judge --levels 1,5 --per 10
  python3 load_test.py judge --base https://<도메인>   # Caddy 를 거쳐서 (서버 밖 · 내 PC 에서)

무엇을 부르나
  judge    POST <base>/judge     {"text": ...}            — 검수 그래프 한 바퀴(DB · 인코더)
  rewrite  POST <sllm>/rewrite   {"text", "violation_types"} — sLLM 서버만 (앱의 재판정은 빠진다)
           🚨 sLLM 은 127.0.0.1 에만 열려 있다 — 서버 안에서만 돈다

🚨 문구는 이 파일에 적은 **지어낸 예시**다. 실제 광고 문구(재배포 불가)를 넣지 않는다.
🚨 배포 직후 사람이 쓰는 시간에 돌리지 않는다 — 판정이 느려진다. 리허설 전에 한 번.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import statistics
import time
import urllib.error
import urllib.request

TEXTS = [
    "이 크림 하나면 2주 만에 주름이 완전히 사라집니다.",
    "매일 한 포로 혈당 걱정 끝, 당뇨에 좋은 차.",
    "피로 회복에 도움을 줄 수 있는 비타민 C 1000mg.",
    "부작용 없는 100% 천연 다이어트 보조제, 한 달에 10kg 감량.",
    "아토피 피부도 안심하고 쓰는 순한 보습 로션.",
    "면역력을 높여 감기를 예방하는 홍삼 진액.",
    "탈모 치료에 효과가 입증된 샴푸.",
    "국내산 원료로 정성껏 만든 수제 그래놀라.",
]
REWRITE_TYPES = ["질병_예방치료_표방"]


def one(url: str, body: dict, timeout: float) -> tuple[bool, float, str]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return 200 <= r.status < 300, time.perf_counter() - t0, str(r.status)
    except urllib.error.HTTPError as e:
        return False, time.perf_counter() - t0, str(e.code)
    except Exception as e:  # noqa: BLE001 — 시간 초과 · 연결 거부를 그대로 센다
        return False, time.perf_counter() - t0, type(e).__name__


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def run_level(url: str, mode: str, conc: int, per: int, timeout: float) -> dict:
    n = conc * per
    bodies = []
    for i in range(n):
        t = TEXTS[i % len(TEXTS)]
        bodies.append(
            {"text": t} if mode == "judge" else {"text": t, "violation_types": REWRITE_TYPES}
        )
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=conc) as ex:
        res = list(ex.map(lambda b: one(url, b, timeout), bodies))
    wall = time.perf_counter() - t0
    ok_t = [t for ok, t, _ in res if ok]
    codes: dict[str, int] = {}
    for ok, _, c in res:
        if not ok:
            codes[c] = codes.get(c, 0) + 1
    return {
        "동시": conc,
        "요청": n,
        "성공": len(ok_t),
        "실패": n - len(ok_t),
        "실패내역": codes,
        "p50": pct(ok_t, 50),
        "p95": pct(ok_t, 95),
        "최대": max(ok_t) if ok_t else float("nan"),
        "평균": statistics.mean(ok_t) if ok_t else float("nan"),
        "처리량": len(ok_t) / wall if wall else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("mode", choices=["judge", "rewrite"])
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="앱 주소 (judge)")
    ap.add_argument("--sllm", default="http://127.0.0.1:8765", help="sLLM 주소 (rewrite)")
    ap.add_argument(
        "--levels", default=None, help="동시 요청 수 목록 — 기본 judge 1,10,30 · rewrite 1,3,6"
    )
    ap.add_argument(
        "--per", type=int, default=None, help="동시 1명당 요청 수 — 기본 judge 5 · rewrite 2"
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="요청 하나의 대기 상한(초) — 기본 judge 60 · rewrite 90(앱과 같다)",
    )
    a = ap.parse_args()

    if a.mode == "judge":
        url, levels, per, timeout = (
            a.base.rstrip("/") + "/judge",
            a.levels or "1,10,30",
            a.per or 5,
            a.timeout or 60,
        )
    else:
        url, levels, per, timeout = (
            a.sllm.rstrip("/") + "/rewrite",
            a.levels or "1,3,6",
            a.per or 2,
            a.timeout or 90,
        )

    print(
        f"부하 시험 — {a.mode} · {url} · 대기 상한 {timeout:.0f}초 · {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print("먼저 한 번 데운다(첫 요청은 모델을 올리느라 느리다) …")
    ok, t, c = one(
        url,
        {"text": TEXTS[0]}
        if a.mode == "judge"
        else {"text": TEXTS[0], "violation_types": REWRITE_TYPES},
        timeout,
    )
    print(f"  예열 {'성공' if ok else '실패'} {t:.1f}초 ({c})")
    if not ok:
        print("[중단] 예열이 실패했다 — 서버가 떠 있는지 bash deploy_server.sh check 로 본다")
        return 1

    print(
        f"\n{'동시':>4} {'요청':>4} {'성공':>4} {'실패':>4} {'p50(s)':>7} {'p95(s)':>7} {'최대(s)':>7} {'처리량/s':>8}  실패내역"
    )
    for lv in [int(x) for x in levels.split(",") if x.strip()]:
        r = run_level(url, a.mode, lv, per, timeout)
        print(
            f"{r['동시']:>4} {r['요청']:>4} {r['성공']:>4} {r['실패']:>4} {r['p50']:>7.2f} {r['p95']:>7.2f} "
            f"{r['최대']:>7.2f} {r['처리량']:>8.2f}  {r['실패내역'] or '-'}"
        )
    print("\n이 표를 작업기록(docs/ssm/배포/작업기록_<MMDD>.md)에 그대로 붙인다 — 합격선 없는 보고")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
