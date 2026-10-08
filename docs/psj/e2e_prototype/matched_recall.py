"""카드 13 — 유형별 재현율을 Baseline 과 맞춘 비교 (박수진 · 2026-10-08)

카드 9 · 11 은 통과 기준에 걸렸는데, 걸린 곳마다 F1 최대 문턱이 크게 옮겨 가 있었다. 이 비교는 **문턱이 옮겨 간 효과를 뺀다** —
유형마다 Baseline 과 **같은 재현율**이 되는 문턱을 골라, 같은 재현율에서 누가 음성(D · L)과 정상 합성 문구에 덜 울리는지만 본다.

  uv run python docs\\psj\\e2e_prototype\\matched_recall.py --dir <행별 확률 폴더> --out-md docs\\psj\\reports\\<집계표>.md

  · 시드마다 짝 — 같은 시드의 Baseline 재현(그 시드의 F1 최대 문턱)과 견준다. 시드 42 · 43 · 44 평균으로 판정한다(규약 2판)
  · 맞추는 법 — dev 양성 10 이상인 유형마다, 그 모델의 재현율이 Baseline 의 재현율 이상인 가장 높은 문턱(격자 0.1 ~ 0.9 · 0.025)
                 dev 양성 10 미만인 유형은 0.5 (규칙 그대로) · 편입 대기 칸은 끈다
  · 정상 합성 문구 — 학습에 넣지 않은 285행에 후보가 서는 행 (애매 표시 46행은 참고)

목표 · 한도는 실험 카드에 먼저 적었다(`docs/psj/reports/v10_문턱규칙_거짓과장_실험기록_20261007.md` 카드 13).
🔴 dev 전용 (D-175). 집계표에는 건수만 쓴다.
"""
import argparse
import csv
import os
import statistics

import score_encoder_dev as sd

SEEDS = [42, 43, 44]
BASE = "copylane-encoder-kcbert-v10-Baseline재현"
MODELS = {"카드 9 모델": "copylane-encoder-kcbert-v10-카드9-정상음성", "카드 11 모델": "copylane-encoder-kcbert-v10-카드11-정상음성절반"}
GRID = [round(0.1 + 0.025 * i, 3) for i in range(33)]
#: 카드 13 에 먼저 적은 값 — 결과를 본 뒤 고치지 않는다
GOAL_SYN = 0.5      # 목표 — 정상 합성 dev 후보(시드 평균)가 Baseline 재현의 이 배수 이하
LIM_NEG = 4         # 한도 ① — 음성(D · L) 오판정(시드 평균) 증가 (규약 2판 G3)
LIM_DET = 0.025     # 한도 ② — 위반 탐지(시드 평균) 하락 (규약 2판 G1)


def matched(Y, P, base_rec):
    """유형마다 Baseline 재현율 이상인 가장 높은 문턱."""
    th = {}
    for i, x in enumerate(sd.CONF8):
        y = [row[i] for row in Y]
        n = sum(y)
        if n < 10:
            th[x] = 0.5
            continue
        best = GRID[0]
        for t in GRID:
            tp = sum(1 for k in range(len(Y)) if y[k] and P[k][i] >= t)
            if tp / n >= base_rec[x] - 1e-12:
                best = t
        th[x] = best
    return th


def syn_flags(path, th):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {"dev": 0, "dev_n": 0, "amb": 0, "amb_n": 0}
    for r in rows:
        key = "dev" if r["갈래"] == "합성정상dev" else "amb"
        out[key + "_n"] += 1
        out[key] += any(float(r[f"p_{x}"]) >= th[x] for x in sd.CONF8)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="Baseline 재현을 자기 자신과 견준다 (차이가 0 이어야 한다)")
    a = ap.parse_args(argv)
    models = {"Baseline 재현 (자기 자신)": BASE} if a.self_test else MODELS
    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    f = lambda tag, s, kind: os.path.join(a.dir, f"{tag}_seed{s}_{kind}.csv")

    R = {"Baseline 재현": {}}
    for s in SEEDS:
        P = sd.read_probs(f(BASE, s, "dev행별확률"), dev)
        th = sd.pick_thresholds(Y, P)
        e = sd.evaluate(dev, P, th)
        rec = {x: e["types"][x]["tp"] / e["types"][x]["n"] for x in sd.CONF8 if e["types"][x]["n"]}
        R["Baseline 재현"][s] = {"th": th, "e": e, "rec": rec, "syn": syn_flags(f(BASE, s, "합성정상_행별확률"), th)}
    for name, tag in models.items():
        R[name] = {}
        for s in SEEDS:
            P = sd.read_probs(f(tag, s, "dev행별확률"), dev)
            b = R["Baseline 재현"][s]
            th = matched(Y, P, b["rec"])
            e = sd.evaluate(dev, P, th)
            R[name][s] = {"th": th, "e": e, "syn": syn_flags(f(tag, s, "합성정상_행별확률"), th),
                          "th_f1": sd.pick_thresholds(Y, P)}

    mean = lambda name, fn: statistics.mean(fn(R[name][s]) for s in SEEDS)
    det = lambda v: v["e"]["det"]
    hit = lambda v: v["e"]["hit"]
    neg = lambda v: v["e"]["neg"][0]
    syn = lambda v: v["syn"]["dev"]
    md = [f"# 카드 13 — 유형별 재현율을 Baseline 과 맞춘 비교 (dev)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 시드마다 같은 시드의 Baseline 재현(F1 최대 문턱)과 짝 · 판정은 시드 42 · 43 · 44 평균 · 건수만 적는다", "",
          "| 모델 | 위반 탐지 (/510 · 시드 평균) | 정답 유형 적중 | 음성(D · L) 오판정 (/86) | 정상 합성 dev 후보 (/285) | 애매 표시 후보 (/46) | 시드별 정상 합성 후보 |",
          "|---|---:|---:|---:|---:|---:|---|"]
    for name in R:
        md.append(f"| {name} | {mean(name, det):.1f} | {mean(name, hit):.1f} | {mean(name, neg):.1f} | {mean(name, syn):.1f} | "
                  f"{mean(name, lambda v: v['syn']['amb']):.1f} | {' · '.join(str(syn(R[name][s])) for s in SEEDS)} |")
    md += ["", "### 유형별 재현율 — 맞춘 값 (시드 평균) · 문턱 (시드 42 · 43 · 44)", "",
           "| 유형 | dev 양성 | Baseline 재현 | " + " | ".join(models) + " |", "|---|---:|---|" + "---|" * len(models)]
    for x in sd.CONF8:
        n = R["Baseline 재현"][SEEDS[0]]["e"]["types"][x]["n"]
        cell = lambda name: (f"{statistics.mean(R[name][s]['e']['types'][x]['tp'] / n for s in SEEDS) * 100:.1f}% · τ "
                             + " · ".join(f"{R[name][s]['th'][x]:g}" for s in SEEDS))
        md.append(f"| {x} | {n} | {cell('Baseline 재현')} | " + " | ".join(cell(m) for m in models) + " |")
    md += ["", "### 목표 · 한도 (카드 13 에 먼저 적은 것 · 시드 평균)", "",
           "| 모델 | 목표 — 정상 합성 dev 후보가 Baseline 재현의 절반 이하 | ① 음성 오판정 +4 이내 | ② 위반 탐지 −2.5%p 이내 | 읽기 |",
           "|---|---|---|---|---|"]
    verdict = {}
    for name in models:
        b_syn, b_neg, b_det = mean("Baseline 재현", syn), mean("Baseline 재현", neg), mean("Baseline 재현", det)
        goal = b_syn > 0 and mean(name, syn) <= GOAL_SYN * b_syn + 1e-9
        l1 = mean(name, neg) - b_neg <= LIM_NEG + 1e-9
        l2 = (mean(name, det) - b_det) / 510 >= -LIM_DET - 1e-12
        ok = goal and l1 and l2
        verdict[name] = ok
        md.append(f"| {name} | {'충족' if goal else '**미달**'} ({mean(name, syn):.1f} 대 {b_syn:.1f}) | "
                  f"{'지킴' if l1 else '**넘음**'} ({mean(name, neg) - b_neg:+.1f}) | {'지킴' if l2 else '**넘음**'} ({(mean(name, det) - b_det) / 510 * 100:+.1f}%p) | "
                  + ("같은 재현율에서 과탐이 적다 — 탈락은 문턱 자리 탓이 크다" if ok else "같은 재현율로 맞춰도 값이 남는다") + " |")
    print("\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
