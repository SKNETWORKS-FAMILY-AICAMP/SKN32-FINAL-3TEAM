"""D4-19 화장품사용감 — 검수 정상 문구 가중 ×2 · 「모름」 사본의 판정 (박수진 · 2026-10-16 · 확률만 읽는다)

D4-19 노트북의 두 실험을 D4-18 ×2 · D4-15 · D4-10재현과 같은 채점으로 견준다. 기준은 D4 실험기록 「D4-19」 에 먼저 적었다.
합격(V1 = 목표 재현율 + 0.03) — ① D4-18 기준 그대로(두 입력) ② 화장품 정상 문구(측정용 59 + 사실 전제 34) · (나) 모름 · 비조용 ≤ 13.0 · 후보 ≤ 6.4

  uv run python docs\\psj\\e2e_prototype\\d4_19_cosmetic.py --base-dir <D4-15a CSV> --d15-dir <D4-15 CSV> --d18-dir <D4-18 CSV> --dir <D4-19 CSV> --review-csv <검수판> --out-md docs\\psj\\reports\\D4-19_화장품사용감_dev_YYYYMMDD.md
  `--self-test` — D4-19 자리에 D4-18 ×2 CSV → 화장품 (나) 비조용 26.0 · 후보 6.4 · (가) 탐지 708.0 이 나와야 한다
🔴 dev 전용 (D-175) · 봉인 · GPT 213 은 읽지 않는다 · 건수만 (D-249).
"""
import argparse
import csv
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure
from d4_10_fact_train import fact_dev_ids
from d4_15_resplit import D410R, D415, MODES, SEEDS, base_probs, ext_dev, targets
from d4_17_ensemble_grid import thresholds

X2 = "copylane-encoder-kcbert-D4-18-적법가중2"
S2, SU = "copylane-encoder-kcbert-D4-19-정상가중2", "copylane-encoder-kcbert-D4-19-정상모름"
RULES = {"V0 지금 D-324": 0.0, "V1 δ 0.03": 0.03}
COS_GRP = ("합성정상dev", "참고-적법(사실 전제)")
GOAL_QUIET, GOAL_FLAG = 13.0, 6.4


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--base-dir", "--d15-dir", "--d18-dir", "--review-csv"):
        ap.add_argument(k, required=True)
    ap.add_argument("--dir", default=None)
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
    runs = {D410R: ("D4-10재현", a.d15_dir, D410R), D415: ("D4-15", a.d15_dir, D415), X2: ("D4-18 ×2", a.d18_dir, X2)}
    if a.self_test:
        runs[S2] = ("(자기 검증) D4-18 ×2", a.d18_dir, X2)
    else:
        if not a.dir:
            ap.error("--dir 가 필요하다")
        runs.update({S2: ("D4-19 정상가중2", a.dir, S2), SU: ("D4-19 정상모름", a.dir, SU)})

    def one(run, m, s, delta):
        _, d, tag = runs[run]
        P = sd.read_probs(os.path.join(d, f"{tag}_{m}_seed{s}_dev행별확률.csv"), D)
        sp = os.path.join(d, f"{tag}_{m}_seed{s}_합성정상_행별확률.csv")
        th = thresholds(Y, P, T0, ca.GRID, delta, False, npos)
        r = measure(D, P, th, sp)
        with open(sp, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        ratio = lambda row: max(float(row[f"p_{x}"]) / th[x] for x in C)
        r["fact"] = sum(1 for row in rows if row["id"] in fids and ratio(row) >= 1)
        cos = [ratio(row) for row in rows if row["품목"] == "화장품" and row["갈래"] in COS_GRP]
        r["cos_n"], r["cos_flag"], r["cos_quiet"] = len(cos), sum(x >= 1 for x in cos), sum(x >= 0.5 for x in cos)
        for c in ("식품", "건기식", "화장품"):
            r[f"syn_{c}"] = sum(1 for row in rows if row["품목"] == c and row["갈래"] == "합성정상dev" and ratio(row) >= 1)
        fl = [any(P[k][i] >= th[x] for i, x in enumerate(C)) for k in range(len(D))]
        r["neg_g"] = sum(1 for k, row in enumerate(D) if row["guide"] and row["bucket"] in ("D", "L") and fl[k])
        return r

    K = ("prauc6", "det", "hit", "F1", "F2", "neg", "neg_g", "syn_flag", "fact", "cos_n", "cos_flag", "cos_quiet", "syn_식품", "syn_건기식", "syn_화장품")
    R = {}
    for run in runs:
        for rule, dl in RULES.items():
            for m in MODES:
                rr = [one(run, m, s, dl) for s in SEEDS]
                R[(run, rule, m)] = {k: statistics.mean(x[k] for x in rr) for k in K}
    V1 = "V1 δ 0.03"
    if a.self_test:
        got = (round(R[(S2, V1, "모름")]["cos_quiet"], 1), round(R[(S2, V1, "모름")]["cos_flag"], 1), round(R[(S2, V1, "품목")]["det"], 1))
        print("  자기 검증", got, "기대 (26.0, 6.3~6.4, 708.0)")
        if got[0] != 26.0 or abs(got[1] - 6.35) > 0.06 or got[2] != 708.0:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0
    base = {m: R[(D410R, "V0 지금 D-324", m)] for m in MODES}
    v0 = {m: R[(D415, "V0 지금 D-324", m)] for m in MODES}

    def ok(run, rule):
        c = {}
        for m in MODES:
            r = R[(run, rule, m)]
            c[f"{m} 탐지"] = (r["det"] - base[m]["det"]) / sc >= -0.025 - 1e-12
            c[f"{m} 적법"] = r["neg"] <= v0[m]["neg"] + 1e-9
            c[f"{m} PR-AUC"] = r["prauc6"] >= base[m]["prauc6"] - 0.02 - 1e-12
            c[f"{m} 정상 문구"] = r["syn_flag"] <= base[m]["syn_flag"] + 5 + 1e-9
        rn = R[(run, rule, "모름")]
        c["화장품 비조용"] = rn["cos_quiet"] <= GOAL_QUIET + 1e-9
        c["화장품 후보"] = rn["cos_flag"] <= GOAL_FLAG + 1e-9
        return c

    md = ["# D4-19 화장품사용감 — 검수 정상 문구 가중 · 「모름」 사본 (dev · 재학습)", "",
          f"> golden `{gsha[:12]}` · 확장 dev {len(D)}행 · 목표 재현율 = D4-15a 기준선 · 시드 48 · 49 · 50 평균 · GPT 213 · 봉인은 읽지 않음 · 건수만", ""]
    for m, title in MODES.items():
        md += [f"## 입력 {title}", "", f"| 판 · 규칙 | PR-AUC | 탐지 (/{sc}) | 적중 | 오인 | 놓침 | 적법 오판정 (해설서) | 정상 문구 (식 · 건 · 화) | 사실 전제 | 화장품 정상 문구 후보 · 비조용 (/93) |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for run, (nm, _, _) in runs.items():
            for rule in RULES:
                r = R[(run, rule, m)]
                md.append(f"| {nm} · {rule} | {r['prauc6']:.4f} | {r['det']:.1f} | {r['hit']:.1f} | {r['F1']:.1f} | {r['F2']:.1f} | {r['neg']:.1f} ({r['neg_g']:.1f}) | "
                          f"{r['syn_flag']:.1f} ({r['syn_식품']:.1f} · {r['syn_건기식']:.1f} · {r['syn_화장품']:.1f}) | {r['fact']:.1f} | {r['cos_flag']:.1f} · {r['cos_quiet']:.1f} |")
        md.append("")
    md += ["## 합격 (V1 · 등록 기준)", "", "| 판 | 결과 | 넘은 기준 |", "|---|---|---|"]
    cand = []
    for run in (S2, SU):
        c = ok(run, V1)
        if all(c.values()):
            cand.append(run)
        md.append(f"| {runs[run][0]} | {'✅' if all(c.values()) else '❌'} | {' · '.join(k for k, v in c.items() if not v) or '—'} |")
    pick = min(cand, key=lambda run: (R[(run, V1, "모름")]["cos_quiet"], -statistics.mean(R[(run, V1, m)]["hit"] for m in MODES))) if cand else None
    md += ["", "**판정 — " + (f"{runs[pick][0]} · V1**" if pick else "못 줄였다**") + f" (기준: D4-18 합격 기준 + 화장품 정상 문구 (나) 비조용 ≤ {GOAL_QUIET} · 후보 ≤ {GOAL_FLAG})", "",
           "🚨 dev 다. 합격 판은 팀장이 GPT 적법 213 으로 한 번 잰다 — 213 은 판 선택에 쓰지 않았다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
