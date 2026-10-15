"""D4-17 앙상블 · 문턱격자 — 위반 탐지와 적법 오판정을 함께 잡기 (박수진 · 2026-10-16 · 학습 없음)

D4-15 확률로 변형 아홉을 잰다 — V0 지금 D-324 · V1 δ 0.03 · B1 ~ B4 격자 0.01 / 거짓_과장 δ 제외 · A0 ~ A2 시드 앙상블(확률 평균).
기준은 D4 실험기록 「D4-17」 에 먼저 적었다 (두 입력 모두: 탐지 ≥ D4-10재현 −2.5%p ∧ 적법 오판정 ≤ D4-15 V0 ∧ PR-AUC ≥ D4-10재현 −0.02 ∧ 정상 문구 ≤ D4-10재현 +5).

  uv run python docs\\psj\\e2e_prototype\\d4_17_ensemble_grid.py --base-dir <D4-15a CSV> --dir <D4-15 CSV> --review-csv <검수판> --out-md docs\\psj\\reports\\D4-17_앙상블문턱격자_dev_YYYYMMDD.md
  자기 검증은 늘 돈다 — V0 · V1 의 위반 탐지가 D4-15 · D4-16 집계((가) 687.3 · 709.0 · (나) 704.0 · 720.0)와 같아야 한다
🔴 dev 전용 (D-175) · 봉인은 읽지 않는다 · 건수만 (D-249). 앙상블 CSV 는 임시 폴더에만 쓴다.
"""
import argparse
import csv
import os
import statistics
import tempfile

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure
from d4_10_fact_train import fact_dev_ids
from d4_15_resplit import D410R, D415, MODES, SEEDS, base_probs, ext_dev, targets

FINE = [round(0.10 + 0.01 * i, 2) for i in range(81)]
FP = "거짓_과장"
VARS = {  # 이름: (앙상블, 격자, δ, 거짓_과장 δ 제외)
    "V0 지금 D-324": (False, ca.GRID, 0.0, False),
    "V1 δ 0.03": (False, ca.GRID, 0.03, False),
    "B1 격자 0.01": (False, FINE, 0.0, False),
    "B2 격자 0.01 · δ 0.03": (False, FINE, 0.03, False),
    "B3 격자 0.01 · δ 0.03 · 거짓_과장 δ 0": (False, FINE, 0.03, True),
    "B4 δ 0.03 · 거짓_과장 δ 0": (False, ca.GRID, 0.03, True),
    "A0 앙상블": (True, ca.GRID, 0.0, False),
    "A1 앙상블 · δ 0.03": (True, ca.GRID, 0.03, False),
    "A2 앙상블 · 격자 0.01 · δ 0.03 · 거짓_과장 δ 0": (True, FINE, 0.03, True),
}
SELF = {("V0 지금 D-324", "품목"): 687.3, ("V1 δ 0.03", "품목"): 709.0, ("V0 지금 D-324", "모름"): 704.0, ("V1 δ 0.03", "모름"): 720.0}


def thresholds(Y, P, target, grid, delta, skip_fp, npos):
    f1 = sd.pick_thresholds(Y, P)
    th = {}
    for i, x in enumerate(sd.CONF8):
        if npos[x] < ca.MEASURABLE_MIN:
            th[x] = f1[x]
            continue
        want = min(1.0, target[x] + (0.0 if skip_fp and x == FP else delta))
        best = None
        for t in grid:
            if ca.recall(Y, P, i, t) >= want - 1e-12:
                best = t
        th[x] = best if best is not None else grid[0]
    return th


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--review-csv", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    a = ap.parse_args(argv)
    dev, guide, gsha, mark = ext_dev(a.golden)
    D, C = dev + guide, sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in D]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(C)}
    fids, _ = fact_dev_ids(a.review_csv)
    T0 = targets(Y, base_probs(a.base_dir, dev, guide), npos)
    gi = [k for k, r in enumerate(D) if r["guide"]]
    tmp = tempfile.mkdtemp(prefix="d4_17_")

    P, SYP = {}, {}
    for run in (D415, D410R):
        for m in MODES:
            for s in SEEDS:
                P[(run, m, s)] = sd.read_probs(os.path.join(a.dir, f"{run}_{m}_seed{s}_dev행별확률.csv"), D)
                SYP[(run, m, s)] = os.path.join(a.dir, f"{run}_{m}_seed{s}_합성정상_행별확률.csv")
            # 앙상블 — 확률 평균 (dev · 정상 문구)
            P[(run, m, "ens")] = [[statistics.mean(P[(run, m, s)][k][j] for s in SEEDS) for j in range(len(sd.LABELS))] for k in range(len(D))]
            rows = {}
            for s in SEEDS:
                with open(SYP[(run, m, s)], encoding="utf-8-sig", newline="") as fh:
                    for row in csv.DictReader(fh):
                        rows.setdefault(row["id"], {"id": row["id"], "갈래": row["갈래"], "p": []})["p"].append([float(row[f"p_{x}"]) for x in sd.LABELS])
            path = os.path.join(tmp, f"{run}_{m}_ens.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["id", "갈래"] + [f"p_{x}" for x in sd.LABELS])
                for r in rows.values():
                    w.writerow([r["id"], r["갈래"]] + [f"{statistics.mean(v):.6f}" for v in zip(*r["p"])])
            SYP[(run, m, "ens")] = path

    def run_one(run, m, key, grid, delta, skip):
        PP = P[(run, m, key)]
        th = thresholds(Y, PP, T0, grid, delta, skip, npos)
        r = measure(D, PP, th, SYP[(run, m, key)])
        with open(SYP[(run, m, key)], encoding="utf-8-sig", newline="") as fh:
            fact = [[float(row[f"p_{x}"]) for x in C] for row in csv.DictReader(fh) if row["id"] in fids]
        r["fact"] = sum(1 for p in fact if any(p[i] >= th[x] for i, x in enumerate(C)))
        r["neg_g"] = sum(1 for k in gi if D[k]["bucket"] in ("D", "L") and any(PP[k][i] >= th[x] for i, x in enumerate(C)))
        r["th"] = th
        return r

    K = ("prauc6", "det", "hit", "F1", "F2", "neg", "neg_g", "syn_flag", "fact")
    R = {}
    for name, (ens, grid, delta, skip) in VARS.items():
        for m in MODES:
            keys = ["ens"] if ens else SEEDS
            rr = [run_one(D415, m, k, grid, delta, skip) for k in keys]
            R[(name, m)] = {k: statistics.mean(r[k] for r in rr) for k in K}
            R[(name, m)]["th49"] = rr[-1]["th"] if ens else rr[SEEDS.index(49)]["th"]
    base = {m: {k: statistics.mean(run_one(D410R, m, s, ca.GRID, 0.0, False)[k] for s in SEEDS) for k in K} for m in MODES}
    sc = sum(1 for r in D if r["bucket"] == "scored")

    bad = [k for k, v in SELF.items() if round(R[k]["det"], 1) != v]
    if bad:
        raise SystemExit(f"🔴 자기 검증 실패 — {bad}: " + str({k: round(R[k]['det'], 1) for k in SELF}))
    print("[OK] 자기 검증 — V0 · V1 의 위반 탐지가 D4-15 · D4-16 집계와 같다")

    def ok(name, m):
        r, b, v0 = R[(name, m)], base[m], R[("V0 지금 D-324", m)]
        c = {"탐지": (r["det"] - b["det"]) / sc >= -0.025 - 1e-12, "적법": r["neg"] <= v0["neg"] + 1e-9,
             "PR-AUC": r["prauc6"] >= b["prauc6"] - 0.02 - 1e-12, "정상 문구": r["syn_flag"] <= b["syn_flag"] + 5 + 1e-9}
        return c

    md = ["# D4-17 앙상블 · 문턱격자 (dev · D4-15 확률 · 학습 없음)", "",
          f"> golden `{gsha[:12]}` · 확장 dev {len(D)}행 · 목표 재현율 = D4-15a 기준선 · 단일 모델 = 시드 48 · 49 · 50 평균 · 앙상블 = 세 시드 확률 평균 한 벌 · 건수만", ""]
    for m, title in MODES.items():
        b = base[m]
        md += [f"## 입력 {title}", "",
               f"기준 — D4-10재현(지금 D-324): 탐지 {b['det']:.1f} · 적중 {b['hit']:.1f} · 적법 오판정 {b['neg']:.1f} · PR-AUC {b['prauc6']:.4f} · 정상 문구 {b['syn_flag']:.1f} / "
               f"합격선: 탐지 ≥ {b['det'] - 0.025 * sc:.1f} · 적법 오판정 ≤ {R[('V0 지금 D-324', m)]['neg']:.1f}", "",
               f"| 변형 | PR-AUC | 탐지 (/{sc}) | 정답 유형 적중 | 유형 오인 | 놓침 | 적법 오판정 (해설서) | 정상 문구 | 사실 전제 | 합격 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for name in VARS:
            r, c = R[(name, m)], ok(name, m)
            md.append(f"| {name} | {r['prauc6']:.4f} | {r['det']:.1f} | {r['hit']:.1f} | {r['F1']:.1f} | {r['F2']:.1f} | {r['neg']:.1f} ({r['neg_g']:.1f}) | "
                      f"{r['syn_flag']:.1f} | {r['fact']:.1f} | {'✅' if all(c.values()) else '❌ ' + ' · '.join(k for k, v in c.items() if not v)} |")
        md.append("")
    passed = [n for n in VARS if all(all(ok(n, m).values()) for m in MODES)]
    pick = max(passed, key=lambda n: (statistics.mean(R[(n, m)]["hit"] for m in MODES), not VARS[n][0])) if passed else None
    md += [f"**판정 — " + (f"{pick}** (두 입력 모두 합격 · 정답 유형 적중 최고)" if pick else "학습 없이 못 잡는다** — D4-18(수정 문구 대조쌍 재학습)로 간다"), ""]
    if pick:
        md += [f"### {pick} 의 문턱 ({'앙상블' if VARS[pick][0] else '시드 49'})", "", "| 유형 | (나) 모름 | (가) 품목 |", "|---|---:|---:|"]
        for x in C:
            md.append(f"| {x} | {R[(pick, '모름')]['th49'][x]} | {R[(pick, '품목')]['th49'][x]} |")
        md.append("")
    md += ["🚨 dev 다 — 같은 확장 dev 로 고른다. 앙상블 PR-AUC 는 한 벌 값이라 시드 평균과 바로 견주지 않는다. 규칙 변경 · 앙상블 배포는 팀장 판정이다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
