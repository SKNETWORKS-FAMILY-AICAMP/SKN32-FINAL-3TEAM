"""test셋(해설서 · 공정위 eval 행) 전체를 판정 로직 1·2단계에 통과시켜 **버킷별 판정 분포**를 낸다 (2026-09-29 · 박수진).

  uv run python docs\\psj\\e2e_prototype\\run_test_dist.py            # 요약 표 + CSV
  uv run python docs\\psj\\e2e_prototype\\run_test_dist.py --limit 200  # 빠른 확인

버킷(인코더 노트북 v7 섹션 2와 같은 규칙):
  scored  위반 라벨이 있는 행 (확정 6종)      → 기대: violation 또는 needs_review
  pending 조건 C·B·A인데 라벨 없는 행         → 기대: violation 또는 needs_review
  M       맥락 필요                           → 기대: needs_review
  D       판정 대상 아님                      → 기대: ok
  neg     승인 기능성 문구                    → 🔄 v2 ①-b 이후: needs_review(품목 분기) · 건기식_인정이면 ok

🔄 09-29 — 1단계가 위반을 확정하지 않는다(사전은 후보 · D-127). 품목별 분기 결과를 따로 표로 낸다.
  aux     비방 · 부당비교 (인코더 대상 아님)  → 참고
"""
import argparse
import csv
import json
import os
from collections import Counter, defaultdict

from judge_stage1 import (load_banned_terms, load_encoder, predict_label_probs_batch, resolve_model_dir,
                          stage1_judge)
from judge_stage2 import PREMISE_RULES, PREMISES, stage2_judge

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.normpath(os.path.join(HERE, "..", "..", "..", "data", "derived", "golden", "golden.jsonl"))
AUX = {"부당_비교광고", "비방광고"}
BUCKET_ORDER = ["scored", "pending", "M", "D", "neg", "aux"]
EXPECT = {"scored": "위반/보류", "pending": "위반/보류", "M": "보류", "D": "ok", "neg": "보류(①-b)", "aux": "참고"}


def bucket(r: dict) -> str:
    cond, labels = r.get("조건"), r.get("labels") or []
    if cond == "M":
        return "M"
    if any(l in AUX for l in labels):
        return "aux"
    if labels:
        return "scored"
    if cond == "D":
        return "D"
    if cond in ("C", "B", "A"):
        return "pending"
    return "neg"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--category", default=None, choices=PREMISES, help="품목을 안다고 가정 (기본: 모름 = 첫 검수)")
    ap.add_argument("--limit", type=int, default=0, help="버킷마다 앞에서 N행만 (빠른 확인)")
    ap.add_argument("--out", default=os.path.join(HERE, "test_dist_result.csv"))
    a = ap.parse_args()

    rows = []
    with open(a.golden, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r["split"] != "train":
                    r["bucket"] = bucket(r)
                    rows.append(r)
    if a.limit:
        per = defaultdict(int)
        rows = [r for r in rows if (per.__setitem__(r["bucket"], per[r["bucket"]] + 1) or per[r["bucket"]] <= a.limit)]
    print(f"[INFO] golden: {a.golden} · eval {len(rows)}행")

    tokenizer, model, label_list, thresholds = load_encoder(resolve_model_dir(a.model))
    banned_terms = load_banned_terms()
    print(f"[INFO] banned_terms {len(banned_terms)}건 · 추론 중…")
    probs = predict_label_probs_batch([r["text"] for r in rows], tokenizer, model, label_list)

    dist = defaultdict(Counter)          # 첫 검수(품목 모름)
    bdist = {p: defaultdict(Counter) for p in PREMISE_RULES}   # 품목을 알 때
    why = defaultdict(Counter)
    extra = defaultdict(Counter)         # dict_backed · premise_unknown
    gold_hit = Counter()
    out = []
    for r, lp in zip(rows, probs):
        s2 = stage2_judge(stage1_judge(r["text"], lp, banned_terms, high_threshold=thresholds), category=a.category)
        b = r["bucket"]
        dist[b][s2["verdict"]] += 1
        for p in PREMISE_RULES:
            bdist[p][b][s2["branches"][p]["verdict"]] += 1
        extra[b]["dict_backed"] += s2["dict_backed"]
        extra[b]["premise_unknown"] += s2.get("hold_reason") == "premise_unknown"
        types = [x["type"] for x in s2["signals"]]
        for x in s2["signals"]:
            why[b][f"{x['kind']}:{x['type']}"] += 1
        if b == "scored":
            gold = set(r.get("labels") or [])
            gold_hit["any"] += bool(gold & set(types))
            gold_hit["n"] += 1
        out.append({
            "bucket": b, "id": r["id"], "조건": r.get("조건"), "labels": "|".join(r.get("labels") or []),
            "verdict": s2["verdict"], "hold_reason": s2.get("hold_reason") or "", "dict_backed": int(s2["dict_backed"]),
            "signals": "|".join(f"{x['kind']}:{x['type']}" for x in s2["signals"]),
            **{f"br_{p}": s2["branches"][p]["verdict"] for p in PREMISE_RULES},
            "matched_terms": "|".join(s2["matched_terms_all"]),
            **{f"p_{l}": round(lp[l], 3) for l in label_list},
            "text": r["text"],
        })

    def table(title, d):
        print(f"\n{title}")
        print(f"{'버킷':8s} {'n':>5s}  {'violation':>12s} {'needs_review':>13s} {'ok':>12s}   기대")
        for b in BUCKET_ORDER:
            n = sum(d[b].values())
            if not n:
                continue
            pct = lambda v: f"{d[b][v]:4d}({d[b][v] / n:5.1%})"
            print(f"{b:8s} {n:5d}  {pct('violation'):>12s} {pct('needs_review'):>13s} {pct('ok'):>12s}   {EXPECT[b]}")

    table(f"[첫 검수 · 품목 {a.category or '모름'}]", dist)
    print("\n  보류 중 사전근거(dict_backed) · 품목 확인 필요(premise_unknown)")
    for b in BUCKET_ORDER:
        n = sum(dist[b].values())
        if n:
            print(f"  {b:8s} 사전근거 {extra[b]['dict_backed']:4d} · 품목 확인 필요 {extra[b]['premise_unknown']:4d}")
    for p in PREMISE_RULES:
        table(f"[품목 = {p} 일 때]", bdist[p])
    if gold_hit["n"]:
        print(f"\nscored — 정답 유형이 신호에 포함: {gold_hit['any']}/{gold_hit['n']} ({gold_hit['any'] / gold_hit['n']:.1%})")
    print("\n버킷별 신호 상위 (종류:유형)")
    for b in BUCKET_ORDER:
        if why[b]:
            print(f"  {b:8s} " + " · ".join(f"{k} {v}" for k, v in why[b].most_common(6)))

    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"\n[INFO] 행별 결과: {a.out}")


if __name__ == "__main__":
    main()
