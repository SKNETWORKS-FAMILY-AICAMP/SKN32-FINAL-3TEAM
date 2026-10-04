#!/usr/bin/env python3
"""scripts/time_graph.py — 판정 그래프의 **응답시간**을 잰다: 노드별 · 문장 수별 p50 / p95 / p99 (🆕 2026-10-02 · D-77 L3).

  uv run python scripts/time_graph.py                          # 문장 1 · 5 · 10 · 20 · 품목 미확정(세 법)
  uv run python scripts/time_graph.py --sizes 1 5 --docs 10    # 빨리 한 번
  uv run python scripts/time_graph.py --category 식품 --out build/eval/time_식품.json
  uv run python scripts/time_graph.py --sizes 1 --docs 5 --search 100   # 검색 안쪽 분해만 크게

★ **무엇을 답하나** — 「분기를 미리 다 계산하면 응답이 너무 길지 않나」(2026-10-02 팀장 질문).
   ① 시간이 **어느 노드**에 드는가(분할 · 검색 · 사전 · 법별 노드 · 판정) ② **문장 수**에 따라 전체 시간이 어떻게 느는가.
🔴 **평균을 쓰지 않는다** — p50 / p95 / p99 (D-77 L3 「시연에서 터지는 것은 꼬리다」). 표본이 30 미만이면 p95 · p99 옆에 표시한다(D-40).
🔴 **모델 로드를 빼고 잰다** — 첫 호출(임베딩 모델 로드)은 예열로 돌리고 버린다. ⛔ 넣으면 p99 가 로드 시간이 된다.
🔴 **DB 가 없으면 멈춘다** — 검색 없는 시간은 이 도구가 답하려는 수가 아니다. 0 에 가까운 수가 「빠르다」로 읽힌다 (D-220).
🚨 **게이트가 아니다** — 답이 기기마다 다르다(D-19 · D-89). 원장에 적을 때 기기 · 조건(인코더 없음 · 리랭커 없음)을 같이 적는다 (D-178).
🚨 문구는 **골든 학습 쪽**(`split == "train"`)에서만 뽑는다 — 시간만 재므로 정답이 필요 없고, 봉인 평가 행을 읽을 이유가 없다 (D-175).
🚨 출력에 **문구를 싣지 않는다** — 문장 수 · 시간뿐이다(`tests/test_nd_gate.py` `EXEMPT`).
🆕 2026-10-02 **검색 안쪽 분해**(`--search N`) — 첫 측정(원장 10-02 ⑧)에서 시간의 91 ~ 98% 가 `retrieve` 였다. 그 안을
   모델 판 조회 · 입력판 검사 · 임베딩 · 벡터 질의 · 어휘 갈래로 나눠 잰다. 🔴 검색 코드를 베끼지 않는다 — `app.retrieve` 의
   함수를 **그대로 부르고 감싸서** 잰다(D-99 · `search_parts`). 임베딩은 한 문장씩과 묶음을 같이 잰다(묶으면 얼마나 주나).
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
from app import retrieve as rt  # noqa: E402 — 검색 안쪽 분해는 이 모듈의 함수를 그대로 부른다
from app.contracts import Category, ProductContext  # noqa: E402
from app.settings import PARAMS  # noqa: E402

GOLDEN = pathlib.Path("data/derived/golden/golden.jsonl")
#: D-77 L3 「단계별 응답시간 예산」 `[문헌]` — 🔴 정본은 원장이다 · 여기는 읽는 자리다(D-54). `scripts/graph_probe.py` `BUDGET_MS` 와 같은 표에서 왔다(D-99)
#:    ⛔ 「판정 전체」 예산 칸을 만들지 않는다 — D-77 에 있는 것은 단계별 예산과 **판정 목표 p95 < 3초**다
BUDGET_MS: dict[str, int] = {"split": 50, "match_dict": 20, "retrieve": 300}
TARGET_P95_MS = 3_000
#: 표본이 이보다 적으면 꼬리 분위수를 믿지 않는다 — D-40 의 값을 그대로 쓴다(`PARAMS` 한 곳 · D-99)
MIN_N = PARAMS.min_measurable
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


#: 검색 한 번 안에서 따로 재는 함수 — `app.retrieve` 의 이름 그대로. 🚨 저쪽이 이름을 바꾸면 여기서 **멈춘다**(조용히 0 이 되지 않게 · D-220)
SEARCH_PARTS = ("stored_model_id", "check_inputs", "encode", "by_vector", "by_lexical")
#: 묶음 임베딩을 잴 때 한 묶음의 문장 수 `[임의]` — 측정용(판정 경로 아님)
GROUP_SIZE = 20


def search_parts(rtmod: Any, cur: Any, text: str) -> dict[str, float]:
    """`rtmod.wide(cur, text)` 한 번을 돌리며 안쪽 함수별 ms 를 잰다. 함수를 감쌌다가 **반드시 되돌린다**.

    ★ 벡터 질의 시간 = `by_vector` − (모델 판 조회 + 입력판 검사 + 임베딩). 검색 코드를 다시 적지 않는다 (D-99).
    """
    missing = [n for n in SEARCH_PARTS if not hasattr(rtmod, n)]
    if missing:
        raise SystemExit(
            f"🔴 `app.retrieve` 에 {missing} 가 없다 — 이름이 바뀌었다. 분해를 다시 맞춘다 (D-220)"
        )
    ms: dict[str, float] = dict.fromkeys(SEARCH_PARTS, 0.0)
    orig = {n: getattr(rtmod, n) for n in SEARCH_PARTS}

    def wrap(name: str) -> Any:
        fn = orig[name]

        def inner(*a: Any, **kw: Any) -> Any:
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                ms[name] += (time.perf_counter() - t0) * 1000

        return inner

    t0 = time.perf_counter()
    try:
        for n in SEARCH_PARTS:
            setattr(rtmod, n, wrap(n))
        rtmod.wide(cur, text)
    finally:
        for n, fn in orig.items():
            setattr(rtmod, n, fn)
    total = (time.perf_counter() - t0) * 1000
    inside = ms["stored_model_id"] + ms["check_inputs"] + ms["encode"]
    return {
        "모델 판 조회": ms["stored_model_id"],
        "입력판 검사": ms["check_inputs"],
        "임베딩(한 문장)": ms["encode"],
        "벡터 질의": max(ms["by_vector"] - inside, 0.0),
        "어휘 갈래": ms["by_lexical"],
        "검색 한 번": total,
    }


def batch_encode_ms(
    rtmod: Any, cur: Any, sents: list[str], size: int = GROUP_SIZE, rounds: int = 5
) -> list[float]:
    """문장 `size` 개를 **한 번에** 임베딩한 시간(ms)을 `rounds` 번. 모델은 `retrieve` 가 올려 둔 것을 쓴다.

    🚨 `_model_cache` 는 `app/retrieve.py` 의 사유물이다 — 비어 있으면 멈춘다(`scripts/graph_probe.py` 와 같은 자리 · D-220).
    """
    model = rtmod._model_cache.get(rtmod.stored_model_id(cur))  # noqa: SLF001
    if model is None:
        raise SystemExit("🔴 임베딩 모델이 올라와 있지 않다 — 예열이 벡터 검색을 못 돌렸다 (D-220)")
    out = []
    for k in range(rounds):
        chunk = sents[k * size : (k + 1) * size]
        t0 = time.perf_counter()
        model.encode(chunk)
        out.append((time.perf_counter() - t0) * 1000)
    return out


def report_search(parts: list[dict[str, float]], batch: list[float]) -> dict[str, Any]:
    few = "  🔴 표본 30 미만 — 꼬리는 참고만 (D-40)" if len(parts) < MIN_N else ""
    print(f"\n[검색 안쪽 분해 · 문장 {len(parts)}개 · 한 문장씩]{few}")
    out: dict[str, Any] = {"n": len(parts), "parts": {}}
    whole = pct([p["검색 한 번"] for p in parts], 50)
    for k in parts[0]:
        v = [p[k] for p in parts]
        out["parts"][k] = {50: pct(v, 50), 95: pct(v, 95)}
        share = f" · 검색의 {pct(v, 50) / whole:5.1%}" if k != "검색 한 번" and whole else ""
        print(f"    {k:<10} p50 {pct(v, 50):8.1f} ms · p95 {pct(v, 95):8.1f} ms{share}")
    b = pct(batch, 50)
    out["batch"] = {"size": GROUP_SIZE, "rounds": len(batch), "p50": b}
    one = out["parts"]["임베딩(한 문장)"][50]
    print(
        f"    묶음 임베딩  문장 {GROUP_SIZE}개 한 번에 p50 {b:8.1f} ms → 문장당 {b / GROUP_SIZE:6.1f} ms "
        f"(한 문장씩은 {one:.1f} ms · {len(batch)}회)"
    )
    return out


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
    ap.add_argument(
        "--search", type=int, default=60, help="검색 안쪽 분해를 잴 문장 수 (0 이면 안 잰다)"
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
            search: dict[str, Any] | None = None
            if a.search:
                pick = random.Random(SEED).sample(sents, min(a.search, len(sents)))
                parts = [search_parts(rt, cur, t) for t in pick]
                picked = set(pick)
                rest = [t for t in sents if t not in picked]
                search = report_search(parts, batch_encode_ms(rt, cur, rest))
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
                    "search": search,
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
