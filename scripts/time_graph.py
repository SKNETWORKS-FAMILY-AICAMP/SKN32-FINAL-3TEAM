#!/usr/bin/env python3
"""scripts/time_graph.py — 판정 그래프의 **응답시간**을 잰다: 노드별 · 문장 수별 p50 / p95 / p99 (🆕 2026-10-02 · D-77 L3).

  uv run python scripts/time_graph.py                          # 문장 1 · 5 · 10 · 20 · 품목 미확정(세 법)
  uv run python scripts/time_graph.py --sizes 1 5 --docs 10    # 빨리 한 번
  uv run python scripts/time_graph.py --category 식품 --out build/eval/time_식품.json

★ **무엇을 답하나** — 「분기를 미리 다 계산하면 응답이 너무 길지 않나」(2026-10-02 팀장 질문).
   ① 시간이 **어느 노드**에 드는가(분할 · 검색 · 사전 · 법별 노드 · 판정) ② **문장 수**에 따라 전체 시간이 어떻게 느는가.
🔴 **평균을 쓰지 않는다** — p50 / p95 / p99 (D-77 L3 「시연에서 터지는 것은 꼬리다」). 표본이 30 미만이면 p95 · p99 옆에 표시한다(D-40).
🔴 **모델 로드를 빼고 잰다** — 첫 호출(임베딩 모델 로드)은 예열로 돌리고 버린다. ⛔ 넣으면 p99 가 로드 시간이 된다.
🔴 **DB 가 없으면 멈춘다** — 검색 없는 시간은 이 도구가 답하려는 수가 아니다. 0 에 가까운 수가 「빠르다」로 읽힌다 (D-220).
🚨 **게이트가 아니다** — 답이 기기마다 다르다(D-19 · D-89). 원장에 적을 때 기기 · 조건(인코더 없음 · 리랭커 없음)을 같이 적는다 (D-178).
🚨 문구는 **골든 학습 쪽**(`split == "train"`)에서만 뽑는다 — 시간만 재므로 정답이 필요 없고, 봉인 평가 행을 읽을 이유가 없다 (D-175).
🚨 출력에 **문구를 싣지 않는다** — 문장 수 · 시간뿐이다(`tests/test_nd_gate.py` `EXEMPT`).
⬜ 인코더(W7) · 리랭커가 붙으면 이 수는 달라진다 — 그때 다시 잰다. 동시 요청(D-77 L3 처리량)은 이 도구가 재지 않는다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import graph as g  # noqa: E402
from app.contracts import Category, ProductContext  # noqa: E402

GOLDEN = pathlib.Path("data/derived/golden/golden.jsonl")
#: D-77 L3 「단계별 응답시간 예산」 `[문헌]` — 🔴 정본은 원장이다 · 여기는 읽는 자리다(D-54). `scripts/graph_probe.py` `BUDGET_MS` 와 같은 표에서 왔다(D-99)
#:    ⛔ 「판정 전체」 예산 칸을 만들지 않는다 — D-77 에 있는 것은 단계별 예산과 **판정 목표 p95 < 3초**다
BUDGET_MS: dict[str, int] = {"split": 50, "match_dict": 20, "retrieve": 300}
TARGET_P95_MS = 3_000
#: 표본이 이보다 적으면 꼬리 분위수를 믿지 않는다 `[관행]` (D-40 의 30)
MIN_N = 30
SEED = 20261002


def pct(xs: list[float], q: float) -> float:
    """분위수 — 가장 가까운 순위(nearest-rank). 🔴 빈 목록이면 멈춘다 — 0 을 내지 않는다 (D-220)."""
    if not xs:
        raise ValueError("분위수를 낼 표본이 없다")
    s = sorted(xs)
    k = max(1, -(-len(s) * q // 100))  # ceil(n·q/100)
    return s[int(k) - 1]


def train_sentences(path: pathlib.Path = GOLDEN) -> list[str]:
    """골든 **학습 쪽** 문장 단위 문구. 🔴 파일이 없으면 멈춘다."""
    if not path.exists():
        raise SystemExit(f"🔴 {path} 가 없다 — 사본은 `launcher.py data-sync` 로 받는다 (D-220)")
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        if not x.strip():
            continue
        r = json.loads(x)
        if r.get("split") == "train" and r.get("unit") == "문장" and "\n" not in r["text"]:
            out.append(r["text"])
    if not out:
        raise SystemExit(f"🔴 {path} 에 학습 쪽 문장이 없다 — 판이 다르다 (D-220)")
    return out


def make_docs(sents: list[str], size: int, n: int, seed: int = SEED) -> list[str]:
    """문장 `size` 개를 줄바꿈으로 이은 원고 `n` 개. 같은 씨앗이면 같은 원고다(재현 · D-149)."""
    rng = random.Random(f"{seed}:{size}")
    return ["\n".join(rng.sample(sents, size)) for _ in range(n)]


def node_ms(timings: Any) -> dict[str, float]:
    """노드 이름 → ms. 법별 노드 셋은 `law_*` 하나로 합친다(병렬이라 벽시계 시간은 이보다 짧을 수 있다)."""
    by: dict[str, float] = collections.defaultdict(float)
    for t in timings:
        by["law_*" if t.node.startswith("law_") else t.node] += t.ms
    return dict(by)


def measure(review: Any, cfg: dict, docs: list[str], product: ProductContext) -> list[dict]:
    rows = []
    for text in docs:
        t0 = time.perf_counter()
        out = review.invoke({"text": text, "product": product}, config=cfg)
        total = (time.perf_counter() - t0) * 1000
        rows.append(
            {"sents": len(out["sents"]), "total": total, "nodes": node_ms(out.get("timings", []))}
        )
    return rows


def summarize(rows: list[dict]) -> dict[str, Any]:
    names = sorted({k for r in rows for k in r["nodes"]})
    tot = [r["total"] for r in rows]
    return {
        "n": len(rows),
        "sents": sorted({r["sents"] for r in rows}),
        "total": {q: pct(tot, q) for q in (50, 95, 99)},
        "nodes": {
            k: {q: pct([r["nodes"].get(k, 0.0) for r in rows], q) for q in (50, 95)} for k in names
        },
    }


def report(size: int, s: dict[str, Any]) -> None:
    few = "  🔴 표본 30 미만 — 꼬리는 참고만 (D-40)" if s["n"] < MIN_N else ""
    t = s["total"]
    over = "  🔴 목표 초과" if t[95] > TARGET_P95_MS else ""
    print(f"\n[문장 {size}개 원고 · {s['n']}건 · 실제 분할 문장 수 {s['sents']}]{few}")
    print(
        f"  전체   p50 {t[50]:8.0f} ms · p95 {t[95]:8.0f} ms · p99 {t[99]:8.0f} ms   (목표 p95 < {TARGET_P95_MS:,} ms · D-77 L3){over}"
    )
    order = [
        n
        for n in ("split", "classify", "retrieve", "match_dict", "encode", "law_*")
        if n in s["nodes"]
    ]
    order += [n for n in s["nodes"] if n not in order]
    for k in order:
        v = s["nodes"][k]
        b = BUDGET_MS.get(k)
        per = f" · 문장당 p50 {v[50] / size:6.0f} ms" if k in ("retrieve", "match_dict") else ""
        tail = f"   (예산 {b} ms)" if b else ""
        print(f"    {k:<12} p50 {v[50]:8.1f} ms · p95 {v[95]:8.1f} ms{per}{tail}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", type=int, nargs="+", default=[1, 5, 10, 20], help="원고의 문장 수")
    ap.add_argument("--docs", type=int, default=MIN_N, help="문장 수마다 원고 몇 건")
    ap.add_argument(
        "--category", choices=[c.value for c in Category], help="품목(안 주면 미확정 — 세 법)"
    )
    ap.add_argument("--out", type=pathlib.Path, help="수를 JSON 으로 (문구는 싣지 않는다)")
    a = ap.parse_args(argv)

    import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 선다

    from app.db import pg_connect  # noqa: PLC0415

    sents = train_sentences()
    product = ProductContext(category=Category(a.category) if a.category else None)
    review = g.build_review()
    result: dict[str, Any] = {}
    try:
        with pg_connect() as conn, conn.cursor() as cur:
            cfg = {"configurable": {"conn": cur}}
            # 🔴 예열 — 임베딩 모델 로드를 측정에서 뺀다. 결과는 버린다
            warm = review.invoke({"text": sents[0], "product": product}, config=cfg)
            ev = warm.get("evidence") or []
            if not ev or not ev[0].vector:
                print(
                    "🟡 벡터 검색이 돌지 않았다 — 아래 `retrieve` 시간은 어휘 갈래만의 시간이다 (D-220)"
                )
            for size in a.sizes:
                rows = measure(review, cfg, make_docs(sents, size, a.docs), product)
                result[str(size)] = summarize(rows)
                report(size, result[str(size)])
    except psycopg.Error as e:
        print(f"🔴 DB 에 못 붙었다 — {type(e).__name__}: {e}\n   uv run python launcher.py db-up")
        return 1
    laws = ", ".join(g.laws_for(product.category))
    print(
        f"\n  조건 — 품목 {a.category or '미확정'} · 법 {laws} · judged_by {g.JUDGED_BY} · 인코더 없음 · 리랭커 없음 · "
        f"학습 쪽 문장 {len(sents):,} · 씨앗 {SEED} · 예열 1회 제외"
    )
    print("  🚨 기기 축이다 — 원장에 적을 때 기기와 이 조건을 같이 적는다 (D-178 · D-19)")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(
            json.dumps(
                {
                    "sizes": result,
                    "category": a.category,
                    "laws": laws,
                    "judged_by": g.JUDGED_BY,
                    "docs": a.docs,
                    "seed": SEED,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
