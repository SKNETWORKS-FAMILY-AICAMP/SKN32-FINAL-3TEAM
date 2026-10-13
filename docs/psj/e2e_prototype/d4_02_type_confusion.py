"""D4-02 유형오인 — D4-00(카드 17 채택 판)의 유형 오인 · 놓침 진단 (박수진 · 2026-10-12)

학습 없음 — 카드 17 노트북이 저장한 dev 행별 확률만 읽는다. 판정(채택 · 탈락)은 없다. 결과로 다음 실험을 고른다.

  uv run python docs\\psj\\e2e_prototype\\d4_02_type_confusion.py --dir <행별 확률 폴더> --out-md docs\\psj\\reports\\D4-02_유형오인_dev_20261012.md

  · 모델 — D4-00 = `카드17-검수정상음성` · 비교로 `카드17-Baseline재현` (같은 시드 48 · 49 · 50)
  · 문턱 — D-324 (card17_adopt.py 와 같은 규칙 · 같은 목표) — 카드 17 판정의 수와 같아야 한다 (위반 탐지 · 정답 유형 적중을 화면에 대조)
  · 채점 행 = 공통 dev 의 scored 행 (encoder_target · 확정 8종)
  · 묻는 것 (D4 실험기록 D4-02 에 먼저 적었다)
      Q1 정답 유형을 못 잡은 행은 「다른 유형이 대신 섰나(오인)」 「아무것도 안 섰나(놓침)」
      Q2 어떤 유형이 어떤 유형 자리를 빼앗나 — 정답 유형 × 대신 선 유형
      Q3 못 잡은 정답 유형의 확률이 문턱 가까이 있나 — p ÷ τ 구간 (가까우면 문턱 쪽 · 멀면 모델 쪽)
      Q4 어디에 몰리나 — 출처(provenance) · 전제 · 라벨 개수(단일 · 여럿)

🔴 dev 전용 (D-175). 집계표(`--out-md`)에는 건수만 쓴다. 행 id 가 든 요약(JSON)은 저장소 밖(`--out-dir`)에 쓴다 (D-249 ⑥).
"""
import argparse
import datetime as dt
import json
import os
import statistics
from collections import Counter, defaultdict

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
BASE, CAND = ca.BASE, ca.CAND
NAMES = {BASE: "기준선 재현", CAND: "D4-00"}
DEPLOY = 49
FOCUS = ["의약품_오인", "소비자_기만", "건강기능식품_오인"]   # 측정 가능한 유형 중 재현율이 낮은 셋
BANDS = [(0.8, "τ × 0.8 ~ 1"), (0.5, "τ × 0.5 ~ 0.8"), (0.0, "τ × 0.5 미만")]
OUT_DIR = os.path.join(os.path.expanduser("~"), "copylane_local", "eval")


def band(r):
    for lo, name in BANDS:
        if r >= lo:
            return name
    return BANDS[-1][1]


def diagnose(dev, P, th):
    """한 모델 · 한 시드의 진단 수 (행 id 는 rows 에만)."""
    e = sd.evaluate(dev, P, th)
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    d = {"det": e["det"], "hit": e["hit"], "cat": Counter(e["cats"][k] for k in sc),
         "per": {}, "swap": Counter(), "pattern": Counter(), "rows": []}
    for x in sd.CONF8:
        d["per"][x] = {"n": 0, "tp": 0, "other": 0, "none": 0, "band": Counter(),
                       "prov": Counter(), "prov_miss": Counter(), "prem": Counter(), "prem_miss": Counter(),
                       "single": [0, 0], "multi": [0, 0]}
    for k in sc:
        r, c = dev[k], set(e["cand"][k])
        gold = [x for x in r["target"] if x in sd.CONF8]
        prov, prem = r.get("provenance") or "—", r.get("전제") or "없음"
        for x in gold:
            i = sd.CONF8.index(x)
            o = d["per"][x]
            o["n"] += 1
            o["prov"][prov] += 1
            o["prem"][prem] += 1
            key = "single" if len(gold) == 1 else "multi"
            o[key][1] += 1
            if x in c:
                o["tp"] += 1
                o[key][0] += 1
                continue
            o["prov_miss"][prov] += 1
            o["prem_miss"][prem] += 1
            o["band"][band(P[k][i] / th[x])] += 1
            if c:
                o["other"] += 1
                for y in c - set(gold):
                    d["swap"][(x, y)] += 1
            else:
                o["none"] += 1
        if e["cats"][k] == "F1 유형 오인":
            d["pattern"][(" + ".join(sorted(gold)), " + ".join(sorted(c)))] += 1
            d["rows"].append({"id": r["id"], "gold": gold, "cand": sorted(c), "전제": r.get("전제"), "provenance": prov})
    return d


def mean(v):
    return statistics.mean(v) if v else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="카드 17 행별 확률 폴더 (…_seed{48,49,50}_dev행별확률.csv)")
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-dir", default=OUT_DIR)
    a = ap.parse_args(argv)
    if a.out_dir and sd.inside_repo(a.out_dir):
        raise SystemExit("🔴 --out-dir 는 저장소 밖이어야 한다 (행 id 가 들어간다 · D-249)")

    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    f = lambda tag, s: os.path.join(a.dir, f"{tag}_seed{s}_dev행별확률.csv")
    P = {(t, s): sd.read_probs(f(t, s), dev) for t in (BASE, CAND) for s in SEEDS}
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    rec = {s: {x: ca.recall(Y, P[(BASE, s)], i, sd.pick_thresholds(Y, P[(BASE, s)])[x])
               for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    D = {}
    for t in (BASE, CAND):
        for s in SEEDS:
            th, _ = ca.d324_thresholds(Y, P[(t, s)], target)
            D[(t, s)] = diagnose(dev, P[(t, s)], th)
    for t in (BASE, CAND):
        print(f"[대조] {NAMES[t]} — 위반 탐지 {mean([D[(t, s)]['det'] for s in SEEDS]):.1f} · "
              f"정답 유형 적중 {mean([D[(t, s)]['hit'] for s in SEEDS]):.1f} (카드 17 집계표와 같아야 한다)")

    M = lambda t, fn: mean([fn(D[(t, s)]) for s in SEEDS])
    one = lambda t, fn: fn(D[(t, DEPLOY)])
    n_sc = sum(D[(CAND, SEEDS[0])]["cat"].values())
    md = ["# D4-02 유형오인 — D4-00 의 유형 오인 · 놓침 진단 (dev)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 채점 행 {n_sc} · D-324 문턱 (card17_adopt.py 와 같다) · "
          f"시드 {' · '.join(map(str, SEEDS))} 평균 (배포 시드 {DEPLOY} 는 따로) · 학습 없음 · 판정 없음 · 건수만 적는다", ""]

    md += ["### 채점 행의 갈래 (/%d)" % n_sc, "",
           f"| 갈래 | 기준선 재현 | D4-00 | D4-00 · 시드 {DEPLOY} |", "|---|---:|---:|---:|"]
    for c in sd.CATS:
        md.append(f"| {c} | {M(BASE, lambda d: d['cat'][c]):.1f} | {M(CAND, lambda d: d['cat'][c]):.1f} | {one(CAND, lambda d: d['cat'][c])} |")

    md += ["", "### Q1 — 정답 유형을 못 잡은 행: 다른 유형이 섰나 · 아무것도 안 섰나 (D4-00 · 시드 평균)", "",
           "| 정답 유형 | dev 양성(채점) | 잡음 | 못 잡음 — 다른 유형이 섬 | 못 잡음 — 아무것도 안 섬 | 기준선 재현 — 잡음 |",
           "|---|---:|---:|---:|---:|---:|"]
    for x in sd.CONF8:
        g = lambda k: (lambda d: d["per"][x][k])
        md.append(f"| {x}{' ◀' if x in FOCUS else ''} | {M(CAND, g('n')):.0f} | {M(CAND, g('tp')):.1f} | "
                  f"{M(CAND, g('other')):.1f} | {M(CAND, g('none')):.1f} | {M(BASE, g('tp')):.1f} |")

    md += ["", "### Q2 — 정답 유형 자리에 대신 선 유형 (D4-00 · 시드 평균 · 0.5 이상만)", "",
           "| 정답 유형 (못 잡음) | 대신 선 유형 | 행 (시드 평균) | 기준선 재현 |", "|---|---|---:|---:|"]
    keys = set().union(*[D[(t, s)]["swap"] for t in (BASE, CAND) for s in SEEDS])
    rows = sorted(keys, key=lambda k: -M(CAND, lambda d: d["swap"][k]))
    for k in rows:
        v = M(CAND, lambda d: d["swap"][k])
        if v >= 0.5:
            md.append(f"| {k[0]} | {k[1]} | {v:.1f} | {M(BASE, lambda d: d['swap'][k]):.1f} |")

    md += ["", "### Q2 보충 — 유형 오인(F1) 행의 꼴 (정답 → 선 유형 · D4-00 · 시드 평균 상위 10)", "",
           "| 정답 | 선 유형 | 행 |", "|---|---|---:|"]
    pk = set().union(*[D[(CAND, s)]["pattern"] for s in SEEDS])
    for k in sorted(pk, key=lambda k: -M(CAND, lambda d: d["pattern"][k]))[:10]:
        md.append(f"| {k[0]} | {k[1]} | {M(CAND, lambda d: d['pattern'][k]):.1f} |")

    md += ["", "### Q3 — 못 잡은 정답 유형의 확률 ÷ 문턱 (D4-00 · 시드 평균)", "",
           "| 정답 유형 | 못 잡음 | " + " | ".join(n for _, n in BANDS) + " |", "|---|---:|" + "---:|" * len(BANDS)]
    for x in sd.CONF8:
        miss = M(CAND, lambda d: d["per"][x]["n"] - d["per"][x]["tp"])
        if miss:
            md.append(f"| {x}{' ◀' if x in FOCUS else ''} | {miss:.1f} | " +
                      " | ".join(f"{M(CAND, lambda d: d['per'][x]['band'][n]):.1f}" for _, n in BANDS) + " |")

    md += ["", "### Q4 — 어디에 몰리나 (D4-00 · 시드 평균 · 재현율이 낮은 셋)", ""]
    for x in FOCUS:
        o0 = D[(CAND, SEEDS[0])]["per"][x]
        md += [f"**{x}** — 단일 라벨 {M(CAND, lambda d: d['per'][x]['single'][0]):.1f}/{o0['single'][1]} · "
               f"여러 라벨 {M(CAND, lambda d: d['per'][x]['multi'][0]):.1f}/{o0['multi'][1]}", "",
               "| 갈래 | 값 | 양성 | 못 잡음 |", "|---|---|---:|---:|"]
        for kind, a_, b_ in (("출처", "prov", "prov_miss"), ("전제", "prem", "prem_miss")):
            for v, n in o0[a_].most_common():
                md.append(f"| {kind} | {v} | {n} | {M(CAND, lambda d: d['per'][x][b_][v]):.1f} |")
        md.append("")

    md += ["읽는 법 — Q1 에서 「다른 유형이 섬」이 크면 유형 경계(오인) 문제 · 「아무것도 안 섬」이 크면 재현율(놓침) 문제다. "
           "Q3 에서 τ × 0.8 이상이 많으면 문턱 쪽, 0.5 미만이 많으면 모델(데이터) 쪽이다. 진단이라 판정은 없다."]

    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8") as fo:
            fo.write(out)
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    os.makedirs(a.out_dir, exist_ok=True)
    js = os.path.join(a.out_dir, f"d4_02_type_confusion_{dt.datetime.now():%Y%m%d_%H%M%S}.json")
    with open(js, "w", encoding="utf-8") as fo:
        json.dump({"golden": gsha, "dev_mark": mark, "seeds": SEEDS,
                   "f1_rows": {f"{NAMES[t]}_seed{s}": D[(t, s)]["rows"] for t in (BASE, CAND) for s in SEEDS}},
                  fo, ensure_ascii=False, indent=1)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {js}")


if __name__ == "__main__":
    main()
