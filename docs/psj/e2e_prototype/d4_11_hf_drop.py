"""D4-11 건기식감소 — 건강기능식품_오인 탐지 감소의 원인 가르기 (박수진 · 2026-10-14 · 진단 · 학습 없음 · 판정 없음)

D-331 ⬜ — eval_graph(인코더 후보까지)에서 건강기능식품_오인이 v10 85.7% → 카드 17 76.2%. 표적 변경(D-326 보충 12)인지 문턱(0.525 → 0.65)인지.
dev 유형 있는 위반 중 골든 라벨에 건강기능식품_오인이 있는 42행(eval_graph 와 같은 정의)에 인코더 단독으로 건기식 후보가 서는지를 단계별로 잰다.

  uv run python docs\\psj\\e2e_prototype\\d4_11_hf_drop.py --v10-dir <v10 CSV 폴더> --dir <D4-00 CSV> --d10-dir <D4-10 CSV> --out-md docs\\psj\\reports\\D4-11_건기식감소_dev_YYYYMMDD.md

  · 단계 — S0 v10 기준선 재현(옛 골든 · 옛 표적 · 시드 42 ~ 47 · F1 최대 문턱 — 옛 표적으로 고른다)
           S1 카드 17 기준선 재현(새 골든 · 새 표적 · 시드 48 ~ 50 · F1 최대) · S2 D4-00(+ 정상 문구 334 · F1 최대) · S3 D4-00 · D-324
           참고 S2′ D4-00 · 문턱 0.525 고정 · S4 D4-10 (가) 품목 · (나) 모름 · D-324
  · 참고 S0* 배포 v10(합성O-이유O · 가중치 b1205ce5484d · 시드 42 · 0.525) — eval_graph 의 v10 이 이 판이다
  · 「선다」(행 단위 이동) = 그 단계의 시드 중 과반
  · `--self-test` — S3 의 건기식 재현율(49행 기준)이 D4 기준 수 69.4% 와 같은지 본다
🔴 dev 전용 (D-175). 건수만 적는다 (D-249).
"""
import argparse
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd

X = "건강기능식품_오인"
V10 = "copylane-encoder-kcbert-v10-Baseline재현"
V10_SEEDS = [42, 43, 44, 45, 46, 47]
V10_DEPLOY = "copylane-encoder-kcbert-v10-합성O-이유O"   # 배포 v10 (가중치 b1205ce5484d · 시드 42 · 건기식 문턱 0.525)
D410 = "copylane-encoder-kcbert-D4-10-품목입력사실전제"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--v10-dir", required=True)
    ap.add_argument("--dir", required=True, help="카드 17 · D4-00 CSV 폴더")
    ap.add_argument("--d10-dir", default=None)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    dev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    xi = C.index(X)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    # 옛 표적 — 표적 변경(D-326 보충 12)으로 건기식이 된 행을 골든 라벨로 되돌린다
    moved = [k for k, r in enumerate(dev) if X in r["target"] and X not in r["labels"]]
    Y_old = [list(y) for y in Y]
    for k in moved:
        Y_old[k][xi] = 0
        if "거짓_과장" in dev[k]["labels"]:
            Y_old[k][C.index("거짓_과장")] = 1
    rows42 = [k for k, r in enumerate(dev) if r["bucket"] == "scored" and X in r["labels"]]
    rows7 = [k for k in moved if dev[k]["bucket"] == "scored"]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(C)}
    print(f"[INFO] golden {gsha[:12]} · dev {mark} · 대상 42행 {len(rows42)} · 표적 변경 행 {len(rows7)} · 새 표적 건기식 정답 {npos[X]}")

    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in ca.SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in ca.SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in ca.SEEDS) for x in rec[ca.SEEDS[0]]}

    steps = []   # (이름, [(P, 문턱)])

    def f1(Yy, P):
        return sd.pick_thresholds(Yy, P)[X]

    S0 = [sd.read_probs(os.path.join(a.v10_dir, f"{V10}_seed{s}_dev행별확률.csv"), dev) for s in V10_SEEDS]
    steps.append(("S0 v10 기준선 재현 · F1 최대 (옛 골든 · 옛 표적)", [(P, f1(Y_old, P)) for P in S0]))
    dep = os.path.join(a.v10_dir, f"{V10_DEPLOY}_dev행별확률.csv")
    if os.path.exists(dep):
        steps.append(("S0* 배포 v10 (합성O-이유O · 시드 42 · 그 판 문턱 0.525 · 참고)", [(sd.read_probs(dep, dev), 0.525)]))
    steps.append(("S1 카드 17 기준선 재현 · F1 최대 (새 골든 · 새 표적)", [(PB[s], f1(Y, PB[s])) for s in ca.SEEDS]))
    P2 = {s: sd.read_probs(os.path.join(a.dir, f"{ca.CAND}_seed{s}_dev행별확률.csv"), dev) for s in ca.SEEDS}
    steps.append(("S2 D4-00 · F1 최대 (+ 정상 문구 334)", [(P2[s], f1(Y, P2[s])) for s in ca.SEEDS]))
    steps.append(("S2′ D4-00 · 0.525 고정 (참고)", [(P2[s], 0.525) for s in ca.SEEDS]))
    steps.append(("S3 D4-00 · D-324 (배포)", [(P2[s], ca.d324_thresholds(Y, P2[s], target)[0][X]) for s in ca.SEEDS]))
    if a.d10_dir:
        for m, lab in (("품목", "(가) 품목"), ("모름", "(나) 모름")):
            P4 = [sd.read_probs(os.path.join(a.d10_dir, f"{D410}_{m}_seed{s}_dev행별확률.csv"), dev) for s in ca.SEEDS]
            steps.append((f"S4 D4-10 {lab} · D-324 (참고)", [(P, ca.d324_thresholds(Y, P, target)[0][X]) for P in P4]))

    def rec_on(rows, P, t):
        return sum(1 for k in rows if P[k][xi] >= t) / len(rows)

    if a.self_test:
        got = round(statistics.mean(ca.recall(Y, P, xi, t) for P, t in steps[[n for n, _ in steps].index("S3 D4-00 · D-324 (배포)")][1]) * 100, 1)
        print(f"  S3 건기식 재현율(49행) {got}% · 기록 69.4%")
        if got != 69.4:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    def stands(runs, k):
        return sum(1 for P, t in runs if P[k][xi] >= t) * 2 > len(runs)

    md = ["# D4-11 건기식감소 — 건강기능식품_오인 탐지 감소의 원인 (dev · 진단)", "",
          f"> golden `{gsha[:12]}` · dev `{mark}` · 인코더 단독(사전 안 봄 — eval_graph 의 85.7 · 76.2 와 숫자가 다르다) · "
          f"대상 = 골든 라벨에 건강기능식품_오인이 있는 유형 있는 위반 {len(rows42)}행 · 건수만 적는다", "",
          f"| 단계 | 시드 | 건기식 문턱 (시드별) | 42행 재현율 (시드별) | 42행 확률 중앙값 | 표적 변경 {len(rows7)}행 재현율 | 42행 중 선 행 (과반) |",
          "|---|---|---|---:|---:|---:|---:|"]
    prev = None
    trans = []
    for name, runs in steps:
        r42 = [rec_on(rows42, P, t) for P, t in runs]
        r7 = [rec_on(rows7, P, t) for P, t in runs] if rows7 else [0]
        med = statistics.median(statistics.mean(P[k][xi] for P, _ in runs) for k in rows42)
        st = {k for k in rows42 if stands(runs, k)}
        md.append(f"| {name} | {len(runs)} | {' · '.join(f'{t:g}' for _, t in runs)} | {statistics.mean(r42) * 100:.1f}% "
                  f"({' · '.join(f'{v * 100:.0f}' for v in r42)}) | {med:.2f} | {statistics.mean(r7) * 100:.1f}% | {len(st)} |")
        if prev is not None and not name.startswith(("S0*", "S2′", "S4")):
            trans.append((prev[0].split(" ")[0] + " → " + name.split(" ")[0], len(prev[1] - st), len(st - prev[1])))
        if not name.startswith(("S0*", "S2′", "S4")):
            prev = (name, st)
    md += ["", "## 단계별 행 이동 (42행 · 과반 시드 기준)", "", "| 단계 | 잃은 행 | 얻은 행 |", "|---|---:|---:|"]
    md += [f"| {n} | {lo} | {ga} |" for n, lo, ga in trans]
    md += ["", "읽는 법 — S0 → S1 은 표적 변경 · 골든 재동결 · 시드가 함께 바뀐 몫 · S1 → S2 는 정상 문구 음성 · S2 → S3 는 문턱 규칙(F1 최대 → D-324).",
           "", "🚨 dev 다 — 같은 dev 로 문턱을 골랐다. 시드 수가 단계마다 다르다(S0 6 · 나머지 3)."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
