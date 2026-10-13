"""D4-09 의약품목표 — 의약품_오인의 목표 재현율만 올리면 재현율 · 과탐이 어떻게 되나 (박수진 · 2026-10-13 · 인코더 단독 · 학습 없음)

D-324 는 유형마다 「dev 재현율이 목표 이상인 가장 높은 문턱」을 고르고 목표를 기준선 재현의 재현율에 묶는다.
의약품_오인 하나만 목표 T 를 올려 문턱을 다시 고르고, 다른 유형은 D-324 그대로 둔다. D4-00 · D4-04 (가) 품목 · (나) 모름.

  uv run python docs\\psj\\e2e_prototype\\d4_09_drug_target.py --dir <D4-00 행별 확률 폴더> --d4-dir <D4-04 행별 확률 폴더> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_09_drug_target.py --dir <D4-00 행별 확률 폴더> --d4-dir <D4-04 행별 확률 폴더> --out-md docs\\psj\\reports\\D4-09_의약품목표_dev_YYYYMMDD.md

  · 기준 (D4 실험기록 「D4-09 의약품목표」 에 먼저 적었다 · 시드 평균 · 기준점 D4-00 · T = D-324)
      한도 ① D · L 음성 오판정 +4행 이내 ② 검수 적법 정상 문구 후보 +5행 이내 ③ 의약품 정밀도 하락 5%p 이내
      고르는 규칙 — 모델마다 한도를 모두 지킨 T 중 가장 높은 것 (판정 아님 · D-324 개정 제안의 근거)
  · 의약품 정밀도 — 조건 M 을 뺀 dev 행에서 의약품 후보가 선 행 중 의약품이 정답인 비율
  · `--self-test` — D4-00 · T = D-324 가 D4 실험기록 「D4-00 기준 수」(의약품 재현율 56.8 · D · L 오판정 17.0 · 정상 문구 후보 5.0)와 같은지 본다
🔴 dev 전용 (D-175). 집계표에는 건수만 적는다 (D-249).
"""
import argparse
import csv
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
GOLDEN = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "derived", "golden", "golden.jsonl"))
D404 = "copylane-encoder-kcbert-D4-04-품목입력"
DRUG = "의약품_오인"
TARGETS = ["D-324", 0.60, 0.65, 0.70, 0.75, 0.80]
LIM_DL, LIM_SYN, LIM_PREC = 4, 5, 0.05
SELF = {"drug_recall": 56.8, "dl_flag": 17.0, "syn_flag": 5.0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 기준선 재현(카드 17) 행별 확률 폴더")
    ap.add_argument("--d4-dir", required=True, help="D4-04 행별 확률 폴더")
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    sdev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in sdev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    di = sd.CONF8.index(DRUG)
    cond = [r.get("조건") for r in sdev]
    dl = [k for k, c in enumerate(cond) if c in ("D", "L")]
    viol = [k for k in range(len(sdev)) if any(Y[k][i] for i in range(len(sd.CONF8)))]
    nonM = [k for k, c in enumerate(cond) if c != "M"]
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark} · 의약품 정답 {npos[DRUG]} · D · L {len(dl)} · 위반 {len(viol)}")

    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), sdev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    def files(model, s):
        if model == "D4-00":
            b = os.path.join(a.dir, f"{ca.CAND}_seed{s}")
        else:
            b = os.path.join(a.d4_dir, f"{D404}_{'품목' if '(가)' in model else '모름'}_seed{s}")
        return f"{b}_dev행별확률.csv", f"{b}_합성정상_행별확률.csv"

    models = ["D4-00"] if a.self_test else ["D4-00", "D4-04 (가) 품목", "D4-04 (나) 모름"]
    targets = ["D-324"] if a.self_test else TARGETS
    R = {}
    for model in models:
        for s in SEEDS:
            dp, spth = files(model, s)
            P = sd.read_probs(dp, sdev)
            with open(spth, encoding="utf-8-sig", newline="") as fh:
                syn = [[float(r[f"p_{x}"]) for x in sd.LABELS] for r in csv.DictReader(fh) if r["갈래"] == "합성정상dev"]
            th0, _ = ca.d324_thresholds(Y, P, target)
            for T in targets:
                th = dict(th0)
                goal = target[DRUG] if T == "D-324" else T
                best = None
                for t in ca.GRID:
                    if ca.recall(Y, P, di, t) >= goal - 1e-12:
                        best = t
                th[DRUG] = best if best is not None else ca.GRID[0]
                flag = lambda p: any(p[i] >= th[x] for i, x in enumerate(sd.CONF8))
                dflag = [P[k][di] >= th[DRUG] for k in range(len(sdev))]
                tp = sum(1 for k in nonM if dflag[k] and Y[k][di])
                fp = sum(1 for k in nonM if dflag[k] and not Y[k][di])
                R[(model, T, s)] = {
                    "tau": th[DRUG], "recall": tp / npos[DRUG],
                    "fp_viol": sum(1 for k in viol if dflag[k] and not Y[k][di]), "fp_dl": sum(1 for k in dl if dflag[k]),
                    "dl_flag": sum(1 for k in dl if flag(P[k])), "syn_flag": sum(1 for p in syn if flag(p)),
                    "syn_drug": sum(1 for p in syn if p[di] >= th[DRUG]), "syn_n": len(syn),
                    "prec": tp / (tp + fp) if tp + fp else float("nan"),
                }
        print(f"  {model} — " + " · ".join(f"T {T}: τ {'/'.join(str(R[(model, T, s)]['tau']) for s in SEEDS)}" for T in targets))

    mn = lambda m, T, k: statistics.mean(R[(m, T, s)][k] for s in SEEDS)
    if a.self_test:
        got = {"drug_recall": round(mn("D4-00", "D-324", "recall") * 100, 1), "dl_flag": round(mn("D4-00", "D-324", "dl_flag"), 1),
               "syn_flag": round(mn("D4-00", "D-324", "syn_flag"), 1)}
        bad = [k for k in SELF if SELF[k] != got[k]]
        for k in SELF:
            print(f"  {'❌ ' if k in bad else 'OK '} {k}: 기록 {SELF[k]} · 지금 {got[k]}")
        if bad:
            raise SystemExit("🔴 자기 검증 실패 — D4-00 · T = D-324 가 기준 수와 다르다")
        print("[OK] 자기 검증 통과 — D4-00 · T = D-324 = 기준 수")
        return 0

    base = {k: mn("D4-00", "D-324", k) for k in ("dl_flag", "syn_flag", "prec")}
    syn_n = R[("D4-00", "D-324", SEEDS[0])]["syn_n"]
    md = ["# D4-09 의약품목표 — 의약품_오인의 목표 재현율 올리기 (dev · 인코더 단독 · 학습 없음)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 시드 {' · '.join(map(str, SEEDS))} 평균 (τ 는 시드별) · 의약품만 목표 T · 다른 유형은 D-324 · "
          f"기준점 D4-00 · T = D-324 · 건수만 적는다", "",
          f"| 모델 | T | τ (시드별) | 의약품 재현율 (/{npos[DRUG]}) | 의약품 오탐 — 다른 위반 · D · L | 의약품 정밀도 | D · L 오판정 (/{len(dl)}) | "
          f"정상 문구 후보 (/{syn_n}) · 그중 의약품 | 한도 ① ② ③ |", "|---|---|---|---:|---|---:|---:|---|---|"]
    pick = {}
    for m in models:
        for T in TARGETS:
            ok = [mn(m, T, "dl_flag") - base["dl_flag"] <= LIM_DL + 1e-9,
                  mn(m, T, "syn_flag") - base["syn_flag"] <= LIM_SYN + 1e-9,
                  base["prec"] - mn(m, T, "prec") <= LIM_PREC + 1e-12]
            if all(ok):
                pick[m] = T
            lab = f"{T:.0%}" if T != "D-324" else f"D-324 ({target[DRUG]:.1%})"
            md.append(f"| {m} | {lab} | {' · '.join(str(R[(m, T, s)]['tau']) for s in SEEDS)} | {mn(m, T, 'recall') * 100:.1f}% | "
                      f"{mn(m, T, 'fp_viol'):.1f} · {mn(m, T, 'fp_dl'):.1f} | {mn(m, T, 'prec') * 100:.1f}% | {mn(m, T, 'dl_flag'):.1f} | "
                      f"{mn(m, T, 'syn_flag'):.1f} · {mn(m, T, 'syn_drug'):.1f} | {' '.join('✓' if x else '✗' for x in ok)} |")
    md += ["", f"기준점(D4-00 · D-324) — D · L 오판정 {base['dl_flag']:.1f} · 정상 문구 후보 {base['syn_flag']:.1f} · 의약품 정밀도 {base['prec'] * 100:.1f}% · "
           f"한도 ① +{LIM_DL} ② +{LIM_SYN} ③ −{LIM_PREC * 100:.0f}%p", "",
           "## 한도 안에서 올릴 수 있는 목표 (모델별 · 고르는 규칙)", ""]
    for m in models:
        T = pick.get(m)
        md.append(f"- {m} — " + (f"T = {T if T == 'D-324' else f'{T:.0%}'} · 의약품 재현율 {mn(m, T, 'recall') * 100:.1f}%" if T is not None
                                 else "한도를 지키는 T 가 없다"))
    md += ["", "🚨 dev 다 — 같은 dev 로 문턱을 고르고 잰다. D4-04 (가) 는 품목이 있는 행에만 품목이 들어간다(재판정 자리의 수)."]
    print("\n" + "\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
