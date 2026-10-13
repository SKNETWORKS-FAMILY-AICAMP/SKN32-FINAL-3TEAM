"""D4-00 보충 — 인코더 정밀도 (박수진 · 2026-10-13 · 진단 · 학습 없음 · 판정 없음)

D4 의 기준 수는 재현율(위반 탐지 · 유형별 재현율)과 음성 오판정 건수뿐이었다. 「위반이라고 한 것 중 진짜 위반」을 같은 확률로 낸다.

  uv run python docs\\psj\\e2e_prototype\\d4_00_precision.py --dir <D4-00 행별 확률 폴더> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_00_precision.py --dir <D4-00 행별 확률 폴더> --out-md docs\\psj\\reports\\D4-00_정밀도_dev_YYYYMMDD.md

  · 묻는 것 (결과 전에 적었다 · 판정 없음)
      Q1 위반 정밀도(유형 무관) — 후보가 하나라도 선 행 중 위반(조건 A · B · C)인 비율. dev 는 위반 542 · 음성(D · L) 86 이라 높게 나오기 쉽다
      Q2 같은 수에 검수 적법 정상 문구 측정용 171행을 음성으로 더하면
      Q3 유형별 정밀도 — 유형 x 후보가 선 행 중 정답에 x 가 있는 비율. 「유형 없는 위반」(조건 A · B · C · 정답 유형 칸이 빔)은
         정답을 모르므로 분모에서 빼고, 그 행에 선 후보 수를 따로 적는다
  · 조건 M 행은 모두 뺀다(학습 · 채점 밖). D4-00 시드 48 · 49 · 50 · D-324 문턱(card17_adopt.d324_thresholds) · 시드 평균
  · `--self-test` — 위반 탐지(유형 무관 · /510) 473.3 · D · L 오판정 17.0 · 정상 문구 후보 5.0 이 D4 실험기록 「D4-00 기준 수」와 같은지 본다
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
SELF = {"det": 473.3, "dl_flag": 17.0, "syn_flag": 5.0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 기준선 재현(카드 17) 행별 확률 폴더")
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    sdev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in sdev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(C)}
    cond = [r.get("조건") for r in sdev]
    typed = [k for k in range(len(sdev)) if any(Y[k][i] for i in range(len(C)))]
    untyped = [k for k, c in enumerate(cond) if c in ("A", "B", "C") and k not in set(typed)]
    viol = sorted(set(typed) | set(untyped))
    neg = [k for k, c in enumerate(cond) if c in ("D", "L")]
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark} · 위반 {len(viol)} (유형 있음 {len(typed)} · 유형 없음 {len(untyped)}) · 음성 D · L {len(neg)} · 조건 M 뺌")

    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), sdev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    R = {}
    for s in SEEDS:
        P = sd.read_probs(os.path.join(a.dir, f"{ca.CAND}_seed{s}_dev행별확률.csv"), sdev)
        th, _ = ca.d324_thresholds(Y, P, target)
        fl = [{x for i, x in enumerate(C) if P[k][i] >= th[x]} for k in range(len(sdev))]
        with open(os.path.join(a.dir, f"{ca.CAND}_seed{s}_합성정상_행별확률.csv"), encoding="utf-8-sig", newline="") as fh:
            syn = [[float(r[f"p_{x}"]) for x in C] for r in csv.DictReader(fh) if r["갈래"] == "합성정상dev"]
        syn_fl = sum(1 for p in syn if any(p[i] >= th[x] for i, x in enumerate(C)))
        tp = sum(1 for k in viol if fl[k])
        fp = sum(1 for k in neg if fl[k])
        per = {}
        for i, x in enumerate(C):
            t_ = sum(1 for k in typed + neg if x in fl[k] and Y[k][i])
            f_ = sum(1 for k in typed + neg if x in fl[k] and not Y[k][i])
            per[x] = (t_, f_, sum(1 for k in untyped if x in fl[k]))
        R[s] = {"det": sum(1 for k in typed if fl[k]), "tp": tp, "fp": fp, "syn_fl": syn_fl, "syn_n": len(syn), "per": per,
                "prec": tp / (tp + fp), "prec_syn": tp / (tp + fp + syn_fl)}

    mn = lambda f: statistics.mean(f(R[s]) for s in SEEDS)
    per_seed = lambda key: " · ".join("%.1f" % (R[s][key] * 100) for s in SEEDS)
    if a.self_test:
        got = {"det": round(mn(lambda r: r["det"]), 1), "dl_flag": round(mn(lambda r: r["fp"]), 1), "syn_flag": round(mn(lambda r: r["syn_fl"]), 1)}
        bad = [k for k in SELF if SELF[k] != got[k]]
        for k in SELF:
            print(f"  {'❌ ' if k in bad else 'OK '} {k}: 기록 {SELF[k]} · 지금 {got[k]}")
        if bad:
            raise SystemExit("🔴 자기 검증 실패 — D4-00 기준 수와 다르다")
        print("[OK] 자기 검증 통과 — D4-00 기준 수와 같다")
        return 0

    syn_n = R[SEEDS[0]]["syn_n"]
    md = ["# D4-00 보충 — 인코더 정밀도 (dev · 진단)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · D4-00(카드 17 채택 판) 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · D-324 문턱 · "
          f"인코더 단독(판정 로직 아님) · 조건 M 뺌 · 건수만 적는다", "",
          "## Q1 · Q2 — 위반 정밀도 (유형 무관)", "",
          f"| 음성 묶음 | 후보가 선 위반 (/{len(viol)}) | 후보가 선 음성 | 위반 정밀도 |", "|---|---:|---:|---:|",
          f"| dev 음성 D · L ({len(neg)}) | {mn(lambda r: r['tp']):.1f} | {mn(lambda r: r['fp']):.1f} | {mn(lambda r: r['prec']) * 100:.1f}% "
          f"({per_seed('prec')}) |",
          f"| D · L + 검수 적법 정상 문구 ({len(neg)} + {syn_n}) | {mn(lambda r: r['tp']):.1f} | {mn(lambda r: r['fp'] + r['syn_fl']):.1f} | "
          f"{mn(lambda r: r['prec_syn']) * 100:.1f}% ({per_seed('prec_syn')}) |", "",
          f"위반 {len(viol)}행에는 「유형 없는 위반」 {len(untyped)}행이 들어 있다(위반이라는 것은 정답이다).", "",
          "## Q3 — 유형별 정밀도", "",
          "| 유형 | 정답 행 | 후보가 선 행 (유형 있는 위반 + D · L) | 그중 정답 | 정밀도 | 재현율 | 「유형 없는 위반」에 선 후보 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for i, x in enumerate(C):
        tp_ = mn(lambda r: r["per"][x][0])
        fp_ = mn(lambda r: r["per"][x][1])
        un_ = mn(lambda r: r["per"][x][2])
        prec = statistics.mean(r["per"][x][0] / (r["per"][x][0] + r["per"][x][1]) for r in R.values() if r["per"][x][0] + r["per"][x][1])
        lab = x + (" (측정 불가)" if npos[x] < ca.MEASURABLE_MIN else "")
        md.append(f"| {lab} | {npos[x]} | {tp_ + fp_:.1f} | {tp_:.1f} | {prec * 100:.1f}% | {tp_ / npos[x] * 100:.1f}% | {un_:.1f} |")
    md += ["", "읽는 법 — Q1 의 정밀도는 음성 비율에 크게 달린다(dev 는 위반이 음성의 6배). Q2 는 실제 광고에 가까운 적법 문구를 더한 수다. "
           "Q3 의 정밀도는 「다른 유형의 위반 · 음성에 잘못 선 후보」를 뺀 몫이다. 확정의 정밀도(판정 로직)는 팀장 평가 도구의 selective risk 로 따로 본다.",
           "", "🚨 dev 다 — 같은 dev 로 문턱을 골랐다(D-324)."]
    print("\n" + "\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
