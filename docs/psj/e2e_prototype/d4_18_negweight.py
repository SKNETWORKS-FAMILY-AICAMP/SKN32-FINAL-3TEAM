"""D4-18 적법가중 — 적법 원천 학습 행 손실 가중 ×2 · ×4 의 판정 (박수진 · 2026-10-16 · 확률만 읽는다)

D4-18 노트북의 두 실험을 V0(지금 D-324) · V1(목표 재현율 + 0.03) 두 규칙으로 재고, D4-15 CSV(D4-15 · D4-10재현)와 견준다.
기준은 D4 실험기록 「D4-18」 에 먼저 적었다 (D4-17 과 같은 합격 · 두 입력 모두).

  uv run python docs\\psj\\e2e_prototype\\d4_18_negweight.py --base-dir <D4-15a CSV> --d15-dir <D4-15 CSV> --dir <D4-18 CSV> --review-csv <검수판> --out-md docs\\psj\\reports\\D4-18_적법가중_dev_YYYYMMDD.md
  `--self-test` — D4-18 자리에 D4-15 CSV 를 넣는다 → D4-15 V0 · V1 이 D4-17 집계((가) 687.3 · 709.0)와 같아야 한다
🔴 dev 전용 (D-175) · 봉인은 읽지 않는다 · 건수만 (D-249).
"""
import argparse
import csv
import os
import re
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure
from d4_10_fact_train import fact_dev_ids
from d4_15_resplit import D410R, D415, MODES, SEEDS, base_probs, ext_dev, targets
from d4_17_ensemble_grid import thresholds

W2, W4 = "copylane-encoder-kcbert-D4-18-적법가중2", "copylane-encoder-kcbert-D4-18-적법가중4"
RULES = {"V0 지금 D-324": 0.0, "V1 δ 0.03": 0.03}
NUM = re.compile(r"\d")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", required=True)
    ap.add_argument("--d15-dir", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--review-csv", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    dev, guide, gsha, mark = ext_dev(a.golden)
    D, C = dev + guide, sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in D]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(C)}
    fids, _ = fact_dev_ids(a.review_csv)
    T0 = targets(Y, base_probs(a.base_dir, dev, guide), npos)
    sc = sum(1 for r in D if r["bucket"] == "scored")
    runs = {D415: ("D4-15", a.d15_dir), D410R: ("D4-10재현", a.d15_dir)}
    if a.self_test:
        runs.update({W2: ("(자기 검증) D4-15", a.d15_dir)})
        alias = {W2: D415}
    else:
        runs.update({W2: ("D4-18 ×2", a.dir), W4: ("D4-18 ×4", a.dir)})
        alias = {}

    def one(run, m, s, delta):
        d = runs[run][1]
        tag = alias.get(run, run)
        P = sd.read_probs(os.path.join(d, f"{tag}_{m}_seed{s}_dev행별확률.csv"), D)
        sp = os.path.join(d, f"{tag}_{m}_seed{s}_합성정상_행별확률.csv")
        th = thresholds(Y, P, T0, ca.GRID, delta, False, npos)
        r = measure(D, P, th, sp)
        with open(sp, encoding="utf-8-sig", newline="") as fh:
            fact = [[float(row[f"p_{x}"]) for x in C] for row in csv.DictReader(fh) if row["id"] in fids]
        r["fact"] = sum(1 for p in fact if any(p[i] >= th[x] for i, x in enumerate(C)))
        fl = [any(P[k][i] >= th[x] for i, x in enumerate(C)) for k in range(len(D))]
        r["neg_g"] = sum(1 for k, row in enumerate(D) if row["guide"] and row["bucket"] in ("D", "L") and fl[k])
        r["neg_num"] = sum(1 for k, row in enumerate(D) if row["bucket"] in ("D", "L") and fl[k] and NUM.search(row["text"]))
        r["th"] = th
        return r

    K = ("prauc6", "det", "hit", "F1", "F2", "neg", "neg_g", "neg_num", "syn_flag", "fact")
    R = {}
    for run in runs:
        for rule, dl in RULES.items():
            for m in MODES:
                rr = {s: one(run, m, s, dl) for s in SEEDS}
                R[(run, rule, m)] = {k: statistics.mean(rr[s][k] for s in SEEDS) for k in K}
                R[(run, rule, m)]["th49"] = rr[49]["th"]
    if a.self_test:
        got = {m: (round(R[(W2, "V0 지금 D-324", m)]["det"], 1), round(R[(W2, "V1 δ 0.03", m)]["det"], 1)) for m in MODES}
        want = {"품목": (687.3, 709.0), "모름": (704.0, 720.0)}
        print("  자기 검증", got, "기대", want)
        if got != want:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    base = {m: R[(D410R, "V0 지금 D-324", m)] for m in MODES}
    v0 = {m: R[(D415, "V0 지금 D-324", m)] for m in MODES}

    def ok(run, rule, m):
        r = R[(run, rule, m)]
        return {"탐지": (r["det"] - base[m]["det"]) / sc >= -0.025 - 1e-12, "적법": r["neg"] <= v0[m]["neg"] + 1e-9,
                "PR-AUC": r["prauc6"] >= base[m]["prauc6"] - 0.02 - 1e-12, "정상 문구": r["syn_flag"] <= base[m]["syn_flag"] + 5 + 1e-9}

    md = ["# D4-18 적법가중 — 적법 원천 학습 행 손실 ×2 · ×4 (dev · 재학습)", "",
          f"> golden `{gsha[:12]}` · 확장 dev {len(D)}행 · 목표 재현율 = D4-15a 기준선 · 시드 48 · 49 · 50 평균 · 비교 D4-15 · D4-10재현 = D4-15 CSV · 건수만", ""]
    for m, title in MODES.items():
        md += [f"## 입력 {title}", "",
               f"합격선 — 탐지 ≥ {base[m]['det'] - 0.025 * sc:.1f} (D4-10재현 V0 {base[m]['det']:.1f} − 2.5%p) · 적법 오판정 ≤ {v0[m]['neg']:.1f} (D4-15 V0) · "
               f"PR-AUC ≥ {base[m]['prauc6'] - 0.02:.4f} · 정상 문구 ≤ {base[m]['syn_flag'] + 5:.1f}", "",
               f"| 판 · 규칙 | PR-AUC | 탐지 (/{sc}) | 정답 유형 적중 | 유형 오인 | 놓침 | 적법 오판정 (해설서 · 숫자) | 정상 문구 | 사실 전제 | 합격 |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for run, (nm, _) in runs.items():
            for rule in RULES:
                r, c = R[(run, rule, m)], ok(run, rule, m)
                md.append(f"| {nm} · {rule} | {r['prauc6']:.4f} | {r['det']:.1f} | {r['hit']:.1f} | {r['F1']:.1f} | {r['F2']:.1f} | "
                          f"{r['neg']:.1f} ({r['neg_g']:.1f} · {r['neg_num']:.1f}) | {r['syn_flag']:.1f} | {r['fact']:.1f} | "
                          f"{'✅' if all(c.values()) else '❌ ' + ' · '.join(k for k, v in c.items() if not v)} |")
        md.append("")
    cand = [(run, rule) for run in (W2, W4) for rule in RULES if all(all(ok(run, rule, m).values()) for m in MODES)]
    order = {W2: 0, W4: 1}
    pick = max(cand, key=lambda x: (statistics.mean(R[(x[0], x[1], m)]["hit"] for m in MODES), x[1] == "V0 지금 D-324", -order[x[0]])) if cand else None
    md += ["**판정 — " + (f"{runs[pick[0]][0]} · {pick[1]}** (두 입력 모두 합격 · 정답 유형 적중 최고)" if pick else "가중으로 못 잡는다**"), ""]
    if pick:
        md += [f"### {runs[pick[0]][0]} · {pick[1]} 의 문턱 (시드 49)", "", "| 유형 | (나) 모름 | (가) 품목 |", "|---|---:|---:|"]
        for x in C:
            md.append(f"| {x} | {R[(pick[0], pick[1], '모름')]['th49'][x]} | {R[(pick[0], pick[1], '품목')]['th49'][x]} |")
        md.append("")
    md += ["🚨 dev 다 — 같은 확장 dev 로 회차 · 문턱 · 판을 고른다. 배포 시드는 판정 뒤 (가) 6종 PR-AUC 최고로(D-324 결정 3). 채택은 팀장 측정."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
