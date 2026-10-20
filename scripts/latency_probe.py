"""scripts/latency_probe.py — 판정 한 번의 시간이 **어디서** 쓰이는가 (🆕 2026-10-19 · D-77 응답 시간 예산).

    uv run python scripts/latency_probe.py
    uv run python scripts/latency_probe.py "피로 회복에 도움을 줍니다" --n 5 --profile

★ 왜 — E2E 에서 `POST /judge` 한 번이 약 3.7 초였는데 노드 계측(`timings`) 합은 약 0.6 초였다(원장 10-19(B) ⑬ 앞 실행).
  나머지가 어디서 쓰이는지를 단계로 나눠 잰다:
    connect   DB 연결(`app.db.pg_connect`)
    invoke    검수 그래프 한 바퀴(`review.invoke`) — 그 안의 노드 계측 합과 **노드 밖**(그래프 틀 · 노드 사이 상태 복사 · 계측 없는 코드)
    response  응답 조립(`graph.to_response`)
  `--profile` 이면 마지막 한 번을 cProfile 로 돌려 누적 시간 상위 함수를 보인다 — 「노드 밖」이 무엇인지 이것으로 본다.
🔴 첫 번은 모델 로드가 들어가 따로 보인다(예열) · 그 뒤 `--n` 번의 중앙값을 낸다.
🚨 게이트가 아니다 — 기기 · DB · 모델 판에 딸린 수다. 판정은 바꾸지 않는다(읽기만 한다).
⛔ 문구는 지은 문장만 넣는다(재배포 제한 원천 문구를 넣지 않는다).
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_TEXT = "면역력 강화에 도움을 줍니다."


def _one(review, text: str):  # noqa: ANN001, ANN202
    from app import graph as g  # noqa: PLC0415
    from app.contracts import ProductContext  # noqa: PLC0415
    from app.db import pg_connect  # noqa: PLC0415

    t0 = time.perf_counter()
    with pg_connect() as conn, conn.cursor() as cur:
        t1 = time.perf_counter()
        state = review.invoke(
            {"text": text, "product": ProductContext()}, config={"configurable": {"conn": cur}}
        )
        t2 = time.perf_counter()
    t3 = time.perf_counter()
    res = g.to_response(state)
    t4 = time.perf_counter()
    nodes = {}
    for t in state.get("timings", []):
        nodes[t.node] = nodes.get(t.node, 0.0) + t.ms
    return {
        "connect": (t1 - t0) * 1000,
        "invoke": (t2 - t1) * 1000,
        "close": (t3 - t2) * 1000,
        "response": (t4 - t3) * 1000,
        "total": (t4 - t0) * 1000,
        "nodes": nodes,
        "outcome": res.outcome.value,
        "branches": len(res.branches),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    ap.add_argument("--n", type=int, default=3, help="예열 뒤 잴 횟수")
    ap.add_argument("--profile", action="store_true", help="마지막 한 번을 cProfile 로 돌린다")
    ap.add_argument("--top", type=int, default=30, help="cProfile 상위 몇 줄")
    args = ap.parse_args(argv)

    from app import graph as g  # noqa: PLC0415

    t0 = time.perf_counter()
    review = g.build_review()
    print(f"그래프 짓기 {(time.perf_counter() - t0) * 1000:.0f} ms")
    warm = _one(review, args.text)
    print(f"예열(첫 번 · 모델 로드 포함) {warm['total']:.0f} ms")

    runs = [_one(review, args.text) for _ in range(args.n)]
    med = {
        k: statistics.median(r[k] for r in runs)
        for k in ("connect", "invoke", "close", "response", "total")
    }
    node_names = sorted({n for r in runs for n in r["nodes"]})
    node_med = {n: statistics.median(r["nodes"].get(n, 0.0) for r in runs) for n in node_names}
    node_sum = sum(node_med.values())
    print(
        f"\n문구 「{args.text}」 · 종착 {runs[-1]['outcome']} · 분기 {runs[-1]['branches']} · {args.n} 번 중앙값"
    )
    for k in ("connect", "invoke", "close", "response", "total"):
        print(f"  {k:9s} {med[k]:8.0f} ms")
    print(
        f"  └ invoke 안 노드 계측 합 {node_sum:8.0f} ms · 노드 밖 {med['invoke'] - node_sum:8.0f} ms"
    )
    for n, ms in sorted(node_med.items(), key=lambda x: -x[1]):
        if ms >= 1:
            print(f"      {n:18s} {ms:8.1f} ms")

    if args.profile:
        pr = cProfile.Profile()
        pr.enable()
        _one(review, args.text)
        pr.disable()
        buf = io.StringIO()
        st = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
        st.print_stats(args.top)
        print("\n── cProfile (누적 시간 상위) ──")
        print(buf.getvalue())
        buf = io.StringIO()
        pstats.Stats(pr, stream=buf).sort_stats("tottime").print_stats(15)
        print("── cProfile (자기 시간 상위) ──")
        print(buf.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
