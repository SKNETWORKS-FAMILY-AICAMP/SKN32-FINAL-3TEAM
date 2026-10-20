"""D4-16 재현율여유 — D-324 목표 재현율에 δ 를 더해 D4-15 의 위반 탐지를 되찾는가 (박수진 · 2026-10-16 · 학습 없음)

D4-15 확률(D4-15 · D4-10재현-확장dev)을 그대로 두고 D-324 의 목표만 「목표 재현율 + δ」로 바꾼다(측정 가능 유형만 · 1.0 상한).
기준은 D4 실험기록 「D4-16」 에 먼저 적었다 — ① 같은 δ 를 두 판에 건 비교로 참고 기준 4개(B · G1 · G3 · 정상 문구)를 두 입력 모두
지키는 가장 작은 δ · ② 참고: D4-15 에만 δ (D4-10재현은 δ 0).

  uv run python docs\\psj\\e2e_prototype\\d4_16_recall_margin.py --base-dir <D4-15a CSV> --dir <D4-15 CSV> --review-csv <검수판> --out-md docs\\psj\\reports\\D4-16_재현율여유_dev_YYYYMMDD.md
  `--self-test` — δ 0 이 D4-15 집계(위반 탐지 (가) 687.3 · 709.3 · (나) 704.0 · 720.3)와 같은지
🔴 dev 전용 (D-175) · 봉인 1,141행은 읽지 않는다. 건수만 적는다 (D-249).
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

DELTAS = [0.0, 0.01, 0.02, 0.03, 0.05]
GATE = {"prauc": 0.02, "det": 0.025, "neg": 4, "syn": 5}
SELF = {("품목", D415): 687.3, ("품목", D410R): 709.3, ("모름", D415): 704.0, ("모름", D410R): 720.3}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", required=True)
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
    gi = [k for k, r in enumerate(D) if r["guide"]]
    deltas = [0.0] if a.self_test else DELTAS

    P, SY = {}, {}
    for run in (D415, D410R):
        for m in MODES:
            for s in SEEDS:
                P[(run, m, s)] = sd.read_probs(os.path.join(a.dir, f"{run}_{m}_seed{s}_dev행별확률.csv"), D)
                sp = os.path.join(a.dir, f"{run}_{m}_seed{s}_합성정상_행별확률.csv")
                with open(sp, encoding="utf-8-sig", newline="") as fh:
                    SY[(run, m, s)] = (sp, [[float(row[f"p_{x}"]) for x in C] for row in csv.DictReader(fh) if row["id"] in fids])
    R = {}
    for d in deltas:
        T = {x: min(1.0, v + d) if npos[x] >= ca.MEASURABLE_MIN else v for x, v in T0.items()}
        for key, PP in P.items():
            th, _ = ca.d324_thresholds(Y, PP, T)
            r = measure(D, PP, th, SY[key][0])
            r["fact"] = sum(1 for p in SY[key][1] if any(p[i] >= th[x] for i, x in enumerate(C)))
            r["neg_g"] = sum(1 for k in gi if D[k]["bucket"] in ("D", "L") and any(PP[k][i] >= th[x] for i, x in enumerate(C)))
            r["th"] = th
            R[(d,) + key] = r
    mn = lambda d, run, m, k: statistics.mean(R[(d, run, m, s)][k] for s in SEEDS)
    sc = R[(0.0, D415, "품목", SEEDS[0])]["scored"]
    if a.self_test:
        bad = []
        for (m, run), v in SELF.items():
            got = round(mn(0.0, run, m, "det"), 1)
            print(f"  {m} · {run[-12:]}: 위반 탐지 {got} · D4-15 집계 {v}")
            bad += [] if got == v else [(m, run)]
        if bad:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    def gates(dc, db, m):
        v = {"B": mn(dc, D415, m, "prauc6") - mn(db, D410R, m, "prauc6"),
             "G1": (mn(dc, D415, m, "det") - mn(db, D410R, m, "det")) / sc,
             "G3": mn(dc, D415, m, "neg") - mn(db, D410R, m, "neg"),
             "syn": mn(dc, D415, m, "syn_flag") - mn(db, D410R, m, "syn_flag")}
        ok = {"B": v["B"] >= -GATE["prauc"] - 1e-12, "G1": v["G1"] >= -GATE["det"] - 1e-12,
              "G3": v["G3"] <= GATE["neg"] + 1e-9, "syn": v["syn"] <= GATE["syn"] + 1e-9}
        return v, ok

    md = ["# D4-16 재현율여유 — D-324 목표 재현율 + δ (dev · D4-15 확률 · 학습 없음)", "",
          f"> golden `{gsha[:12]}` · 확장 dev {len(D)}행 · 목표 = D4-15a 기준선 재현 + δ (측정 가능 유형만) · 시드 48 · 49 · 50 평균 · 건수만", ""]
    for m, title in MODES.items():
        md += [f"## 입력 {title}", "", "| δ | 판 | 6종 PR-AUC | 위반 탐지 (/{0}) | 정답 유형 적중 | 유형 오인 | 놓침 | 적법 원천 오판정 (해설서) | 정상 문구 (/171) | 사실 전제 (/110) |".format(sc),
               "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for d in deltas:
            for run, nm in ((D415, "D4-15"), (D410R, "D4-10재현")):
                md.append(f"| {d:.2f} | {nm} | {mn(d, run, m, 'prauc6'):.4f} | {mn(d, run, m, 'det'):.1f} | {mn(d, run, m, 'hit'):.1f} | {mn(d, run, m, 'F1'):.1f} | "
                          f"{mn(d, run, m, 'F2'):.1f} | {mn(d, run, m, 'neg'):.1f} ({mn(d, run, m, 'neg_g'):.1f}) | {mn(d, run, m, 'syn_flag'):.1f} | {mn(d, run, m, 'fact'):.1f} |")
        md.append("")
    pick = None
    md += ["## ① 같은 규칙 비교 (판정) — 같은 δ 를 두 판에", "", "| δ | (가) B · G1 · G3 · 정상 문구 | (나) B · G1 · G3 · 정상 문구 | 넷 다 · 두 입력 |", "|---|---|---|---|"]
    for d in deltas:
        cells, allok = [], True
        for m in MODES:
            v, ok = gates(d, d, m)
            cells.append(f"{v['B']:+.4f} · {v['G1'] * 100:+.1f}%p{'' if ok['G1'] else '❌'} · {v['G3']:+.1f} · {v['syn']:+.1f}" + ("" if all(ok.values()) else " ❌"))
            allok &= all(ok.values())
        if allok and pick is None:
            pick = d
        md.append(f"| {d:.2f} | " + " | ".join(cells) + f" | {'지킴' if allok else '넘음'} |")
    md += ["", "## ② 참고 — D4-15 에만 δ (D4-10재현은 δ 0 · 지금 D-324)", "", "| δ | (가) B · G1 · G3 · 정상 문구 | (나) B · G1 · G3 · 정상 문구 |", "|---|---|---|"]
    for d in deltas:
        cells = []
        for m in MODES:
            v, ok = gates(d, 0.0, m)
            cells.append(f"{v['B']:+.4f} · {v['G1'] * 100:+.1f}%p{'' if ok['G1'] else '❌'} · {v['G3']:+.1f}{'' if ok['G3'] else '❌'} · {v['syn']:+.1f}{'' if ok['syn'] else '❌'}")
        md.append(f"| {d:.2f} | " + " | ".join(cells) + " |")
    md += ["", f"**판정 — " + (f"δ {pick:.2f} (같은 규칙 비교에서 두 입력 모두 참고 기준 4개를 지키는 가장 작은 δ)" if pick is not None else "여유로 못 메운다 (δ 0.05 까지 같은 규칙 비교에서 넘음)") + "**", ""]
    if pick is not None:
        md += [f"### δ {pick:.2f} 의 문턱 (시드 49)", "", "| 유형 | (나) 모름 | (가) 품목 |", "|---|---:|---:|"]
        for x in C:
            md.append(f"| {x} | {R[(pick, D415, '모름', 49)]['th'][x]} | {R[(pick, D415, '품목', 49)]['th'][x]} |")
        md.append("")
    md += ["🚨 dev 다 — 같은 확장 dev 로 δ 를 골라 낙관적이다. 문턱 규칙 변경(D-324 개정)은 팀장 판정이다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
