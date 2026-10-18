"""D4-20 기능성편입 — 기능성화장품_오인 편입 · 재판독 반영 골든의 dev 판정 (박수진 · 2026-10-18 · 확률만 읽는다)

D4-20 노트북 확률을 D4-18 ×2 확률과 **같은 골든(재판독 반영판)으로** 견준다. 기준은 D4 실험기록 「D4-20」 에 먼저 적었다.
  · 8종 문턱 — D-324 + δ 0.03 (V1) · 기능성화장품_오인 — 확장 dev 양성 30 미만이면 「측정 불가」 · 문턱은 그 판의 dev F1 최대(격자 0.1 ~ 0.9 · 0.025)
  · 이 스크립트가 내는 관문 — B 6종 PR-AUC −0.02 이내 · G3 음성(D · L) 오판정 +4행 이내 · 한도 ① 정상 문구 171 후보 +5행 이내 (8종 · 기능성 칸 뺌)
  · G1(무엇이든 걸린 행)은 정본 도구 `scripts/eval_graph.py` 로 따로 잰다 — 여기 「탐지」는 참고
  · 보고 — 화장품 dev 의약품_오인 ↔ 기능성화장품_오인 혼동표 · dev 8행(팀장 지정)의 유형과 확신 · 기능성 재현율 · 정밀도

  uv run python docs\\psj\\e2e_prototype\\d4_20_functional.py --base-dir <D4-15a CSV> --d18-dir <D4-18 CSV> --dir <D4-20 CSV> --out-md docs\\psj\\reports\\D4-20_기능성편입_dev_YYYYMMDD.md
  `--self-test` — D4-20 자리에 D4-18 ×2 CSV 를 넣는다 → 모든 차이가 0 이어야 한다
🔴 dev 전용 (D-175) · 봉인은 읽지 않는다 · 건수 · id · 확률만 (D-249 — 행 문장은 쓰지 않는다).
"""
import argparse
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure
from d4_15_resplit import MODES, SEEDS, base_probs, ext_dev, targets
from d4_17_ensemble_grid import thresholds

W18, W20 = "copylane-encoder-kcbert-D4-18-적법가중2", "copylane-encoder-kcbert-D4-20-기능성편입"
FN, RX = "기능성화장품_오인", "의약품_오인"
DELTA = 0.03
WATCH = ["ic:deg7vkkzxpce#0", "ic:pwvpxddz72w6#0", "ic:vcyd4f6a6c6d#0", "gs:oogucfw7bi4t#0",
         "dg:67lry65bfil2#0", "gs:awkpn3pusuvp#0", "gs:sdsmox7hotg5#0", "gs:hc45s3i6h7mz#0"]


def f1_max(y, p, grid=ca.GRID):
    """dev F1 최대 문턱 — 같은 F1 이면 낮은 문턱 (sd.pick_thresholds 와 같은 규칙 · 단 양성 10 미만도 0.5 로 두지 않는다)."""
    best, bt = -1.0, grid[0]
    for t in grid:
        tp = sum(1 for a, b in zip(y, p, strict=True) if a and b >= t)
        pp = sum(1 for b in p if b >= t)
        f = 2 * tp / (pp + sum(y)) if pp + sum(y) else 0.0
        if f > best + 1e-12:
            best, bt = f, t
    return bt, best


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", required=True)
    ap.add_argument("--d18-dir", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    dev, guide, gsha, mark = ext_dev(a.golden)
    D, C = dev + guide, sd.CONF8
    ifn, irx = sd.LABELS.index(FN), sd.LABELS.index(RX)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in D]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(sd.LABELS)}
    T0 = targets(Y, base_probs(a.base_dir, dev, guide), npos)
    sc = sum(1 for r in D if r["bucket"] == "scored")
    idx = {r["id"]: k for k, r in enumerate(D)}
    miss = [i for i in WATCH if i not in idx]
    if miss:
        raise SystemExit(f"🔴 8행이 확장 dev 에 없다 — {miss}")
    runs = {W18: ("D4-18 ×2", a.d18_dir, W18), W20: ("D4-20 기능성편입", a.d18_dir if a.self_test else a.dir, W18 if a.self_test else W20)}
    cos = [k for k, r in enumerate(D) if r.get("품목") == "화장품" and r["bucket"] not in ("M",)]

    def one(run, m, s):
        _, d, tag = runs[run]
        P = sd.read_probs(os.path.join(d, f"{tag}_{m}_seed{s}_dev행별확률.csv"), D)
        sp = os.path.join(d, f"{tag}_{m}_seed{s}_합성정상_행별확률.csv")
        th = thresholds(Y, P, T0, ca.GRID, DELTA, False, npos)
        r = measure(D, P, th, sp)
        tfn, ffn = f1_max([y[ifn] for y in Y], [p[ifn] for p in P])
        cf = [P[k][ifn] >= tfn for k in range(len(D))]
        tp = sum(1 for k in range(len(D)) if cf[k] and Y[k][ifn])
        r.update(th_fn=tfn, f1_fn=ffn, fn_tp=tp, fn_pp=sum(cf), fn_neg=sum(1 for k, row in enumerate(D) if cf[k] and row["bucket"] in ("D", "L")))
        with open(sp, encoding="utf-8-sig", newline="") as fh:
            import csv
            r["fn_syn"] = sum(1 for row in csv.DictReader(fh) if row["갈래"] == "합성정상dev" and float(row[f"p_{FN}"]) >= tfn)
        conf = {}
        for k in cos:
            truth = "기능성" if Y[k][ifn] else ("의약품" if Y[k][irx] else "그 밖")
            rx, fn = P[k][irx] >= th[RX], cf[k]
            pred = "둘 다" if rx and fn else ("의약품" if rx else ("기능성" if fn else "없음"))
            conf[(truth, pred)] = conf.get((truth, pred), 0) + 1
        r["conf"] = conf
        w = {}
        for i in WATCH:
            k = idx[i]
            fired = [(x, P[k][j]) for j, x in enumerate(C) if P[k][j] >= th[x]] + ([(FN, P[k][ifn])] if cf[k] else [])
            top = max(range(len(sd.LABELS)), key=lambda j: P[k][j])
            w[i] = {"fired": sorted(fired, key=lambda z: -z[1]), "top": (sd.LABELS[top], P[k][top]), "pfn": P[k][ifn], "prx": P[k][irx]}
        r["watch"], r["th"] = w, th
        return r

    K = ("prauc6", "det", "hit", "F1", "F2", "neg", "syn_flag", "fn_tp", "fn_pp", "fn_neg", "fn_syn", "th_fn")
    R, RS = {}, {}
    for run in runs:
        for m in MODES:
            rr = {s: one(run, m, s) for s in SEEDS}
            RS[(run, m)] = rr
            R[(run, m)] = {k: statistics.mean(rr[s][k] for s in SEEDS) for k in K}
    best = {run: max(SEEDS, key=lambda s: RS[(run, "품목")][s]["prauc6"]) for run in runs}

    if a.self_test:
        bad = [(m, k) for m in MODES for k in K if abs(R[(W18, m)][k] - R[(W20, m)][k]) > 1e-9]
        print("  자기 검증 — 차이 난 칸:", bad or "없음", "· D4-18 ×2 V1 (가) 탐지", round(R[(W18, "품목")]["det"], 1))
        if bad:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    def gates(m):
        b, c = R[(W18, m)], R[(W20, m)]
        return {"B PR-AUC": c["prauc6"] >= b["prauc6"] - 0.02 - 1e-12, "G3 음성": c["neg"] <= b["neg"] + 4 + 1e-9,
                "한도 ① 정상 문구": c["syn_flag"] <= b["syn_flag"] + 5 + 1e-9}

    md = ["# D4-20 기능성편입 — 기능성화장품_오인 편입 · 재판독 반영 골든 (dev · 재학습)", "",
          f"> golden `{gsha[:12]}` · 확장 dev {len(D)}행 · 8종 문턱 V1(D-324 + δ {DELTA}) · 목표 재현율 = D4-15a 기준선 · 시드 48 · 49 · 50 평균 · "
          f"비교 D4-18 ×2 = 같은 골든으로 다시 채점 · 건수 · id 만", "",
          f"기능성화장품_오인 확장 dev 양성 **{npos[FN]}** — {'**측정 불가**(30 미만 · D-324 결정 2) · 문턱 = 판마다 dev F1 최대' if npos[FN] < ca.MEASURABLE_MIN else '측정 가능'}", ""]
    for m, title in MODES.items():
        g = gates(m)
        md += [f"## 입력 {title}", "",
               f"| 판 | PR-AUC 6종 | 탐지 (/{sc} · 참고) | 정답 유형 적중 | 유형 오인 | 놓침 | 음성(D · L) 오판정 | 정상 문구 171 후보 | 기능성 문턱 · 후보 · 적중 (/{npos[FN]}) · D · L · 정상 문구 |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for run, (nm, _, _) in runs.items():
            r = R[(run, m)]
            md.append(f"| {nm} | {r['prauc6']:.4f} | {r['det']:.1f} | {r['hit']:.1f} | {r['F1']:.1f} | {r['F2']:.1f} | {r['neg']:.1f} | {r['syn_flag']:.1f} | "
                      f"{r['th_fn']:.3f} · {r['fn_pp']:.1f} · {r['fn_tp']:.1f} · {r['fn_neg']:.1f} · {r['fn_syn']:.1f} |")
        b = R[(W18, m)]
        md += ["", "관문 (D4-20 대 D4-18 ×2 · 8종 · 기능성 칸 뺌) — " + " · ".join(
            f"{k} {'✅' if v else '❌'}" for k, v in g.items()) + f" · G1 은 eval_graph (참고 — 탐지 {R[(W20, m)]['det'] - b['det']:+.1f}행 · {(R[(W20, m)]['det'] - b['det']) / sc * 100:+.1f}%p)", ""]
        md += [f"### 화장품 dev 혼동표 (정답 × 후보 · 시드 합 / 3 · {len(cos)}행 · 조건 M 뺌)", "",
               "| 판 · 정답 | 후보 의약품 | 후보 기능성 | 둘 다 | 없음 |", "|---|---:|---:|---:|---:|"]
        for run, (nm, _, _) in runs.items():
            for t in ("기능성", "의약품", "그 밖"):
                v = [sum(RS[(run, m)][s]["conf"].get((t, p), 0) for s in SEEDS) / 3 for p in ("의약품", "기능성", "둘 다", "없음")]
                md.append(f"| {nm} · {t} | " + " | ".join(f"{x:.1f}" for x in v) + " |")
        md.append("")
    md += ["## dev 8행 — 배포 시드의 확정 유형과 확신 (팀장 지정 · 그래프 신뢰 문턱 고르기용)", "",
           f"배포 시드 = (가) 6종 PR-AUC 최고 — D4-18 ×2 시드 {best[W18]} · D4-20 시드 {best[W20]}. 🚨 8행은 dev 안이다", "",
           "| id | 정답 | 입력 | D4-18 ×2 후보 (확률) | D4-20 후보 (확률) | D4-20 기능성 · 의약품 확률 |", "|---|---|---|---|---|---|"]
    for i in WATCH:
        k = idx[i]
        truth = "·".join(D[k]["target"]) or f"없음({D[k]['조건']})"
        for m, title in MODES.items():
            c = [RS[(run, m)][best[run]]["watch"][i] for run in (W18, W20)]
            cell = lambda w: " · ".join(f"{x} {p:.3f}" for x, p in w["fired"]) or f"없음 (최고 {w['top'][0]} {w['top'][1]:.3f})"
            md.append(f"| {i} | {truth} | {title[:6]} | {cell(c[0])} | {cell(c[1])} | {c[1]['pfn']:.3f} · {c[1]['prx']:.3f} |")
    md += ["", "🚨 dev 다 — 213 · eval_graph 관문은 따로 잰다. 채택은 팀장 판정 (D-349)."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
