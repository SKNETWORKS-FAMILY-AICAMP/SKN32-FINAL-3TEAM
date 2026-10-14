"""E1-00 KcELECTRA — D4-10 학습에서 백본만 바꾼 판과 견준다 (박수진 · 2026-10-14 · 발표용 비교 · 확률만 읽는다)

E1-00 노트북(`copylane_encoder_E1-00_KcELECTRA_백본비교_20261014.ipynb`)이 낸 시드 · 입력별 행별 확률을
D4-10(KcBERT · 같은 데이터 · 같은 설정 · 같은 시드)의 행별 확률과 같은 D-324 문턱 규칙 · 같은 채점으로 견준다.

  uv run python docs\\psj\\e2e_prototype\\e1_00_electra.py --dir <D4-00 CSV> --d10-dir <D4-10 CSV> --e1-dir <E1-00 CSV> --review-csv <검수판> --out-md docs\\psj\\reports\\E1-00_KcELECTRA비교_dev_YYYYMMDD.md
  `--self-test` — E1-00 자리에 D4-10 CSV 를 넣는다 · 차이가 0 이고 D4-10 수가 기록(위반 탐지 464.7 · 479.3)과 같아야 한다

  · 문턱 — D-324 (card17_adopt.d324_thresholds · 목표 = 카드 17 기준선 재현 3 시드 평균) · 백본 · 입력 · 시드마다 고른다
  · 판단 규칙 (D4 실험기록 「E1-00」 에 먼저 적었다) — 입력마다 6종 PR-AUC 시드 평균 차이가 0.02 이내면 「동등」, 넘으면 높은 쪽 「우세」.
    나머지 수(탐지 · 적중 · 오인 · 오판정 · 정상 문구)는 같이 적기만 한다 — 채택 판정이 아니다
🔴 dev 전용 (D-175 · 봉인 평가셋은 D4-T 한 번으로 끝). 건수만 적는다 (D-249).
"""
import argparse
import csv
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure
from d4_10_fact_train import D410, FACT, MODES, fact_dev_ids

SEEDS = ca.SEEDS
E100 = "copylane-encoder-kcelectra-E1-00-KcELECTRA"
EQ = 0.02
SELF_DET = {"품목": 464.7, "모름": 479.3}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 카드 17 행별 확률 폴더 (D-324 목표 재현율)")
    ap.add_argument("--d10-dir", required=True, help="D4-10 행별 확률 폴더 (KcBERT)")
    ap.add_argument("--e1-dir", default=None, help="E1-00 행별 확률 폴더 (KcELECTRA · E1-00_csv.zip 을 푼 곳)")
    ap.add_argument("--review-csv", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if not a.self_test and not a.e1_dir:
        ap.error("--e1-dir 이 필요하다")

    dev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(C)}
    fids, _ = fact_dev_ids(a.review_csv)
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}
    print(f"[INFO] golden {gsha[:12]} · dev {len(dev)}행 · 지문 {mark} · 사실 전제 dev {len(fids)}행")

    models = {"KcBERT (D4-10)": (a.d10_dir, D410),
              "KcELECTRA (E1-00)": (a.d10_dir, D410) if a.self_test else (a.e1_dir, E100)}
    R = {}
    for name, (d, base) in models.items():
        for m in MODES:
            for s in SEEDS:
                b = os.path.join(d, f"{base}_{m}_seed{s}")
                P = sd.read_probs(b + "_dev행별확률.csv", dev)
                th, _ = ca.d324_thresholds(Y, P, target)
                r = measure(dev, P, th, b + "_합성정상_행별확률.csv")
                with open(b + "_합성정상_행별확률.csv", encoding="utf-8-sig", newline="") as fh:
                    syn = [(row["id"], row["갈래"], [float(row[f"p_{x}"]) for x in C]) for row in csv.DictReader(fh)]
                fr = [p for i, br, p in syn if i in fids and br == FACT]
                if len(fr) != len(fids):
                    raise SystemExit(f"🔴 {os.path.basename(b)} 에 사실 전제 dev {len(fr)}행뿐이다 (등록 {len(fids)})")
                r["fact"] = sum(1 for p in fr if any(p[i] >= th[x] for i, x in enumerate(C)))
                R[(name, m, s)] = r
    names = list(models)
    mn = lambda n, m, k: statistics.mean(R[(n, m, s)][k] for s in SEEDS)
    sdv = lambda n, m, k: statistics.pstdev(R[(n, m, s)][k] for s in SEEDS)

    if a.self_test:
        ok = True
        for m in MODES:
            d = {k: mn(names[1], m, k) - mn(names[0], m, k) for k in ("prauc6", "det", "hit", "F1", "F2", "neg", "syn_flag", "fact")}
            got = round(mn(names[0], m, "det"), 1)
            print(f"  {m}: D4-10 위반 탐지 {got} · 기록 {SELF_DET[m]} · 차이 {d}")
            ok &= got == SELF_DET[m] and all(abs(v) < 1e-12 for v in d.values())
        if not ok:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    sc, nn = R[(names[0], "품목", SEEDS[0])]["scored"], R[(names[0], "품목", SEEDS[0])]["neg_n"]
    nsyn = R[(names[0], "품목", SEEDS[0])]["syn_n"]
    md = ["# E1-00 KcELECTRA — D4-10 학습에서 백본만 바꾼 비교 (dev)", "",
          f"> golden `{gsha[:12]}` · dev `{mark}` · 시드 48 · 49 · 50 평균 · 백본 · 입력 · 시드마다 D-324 문턱 · 인코더 단독 · 발표용 비교(채택 판정 아님) · 건수만 적는다", ""]
    verdict = {}
    for m, lab in MODES.items():
        diff = mn(names[1], m, "prauc6") - mn(names[0], m, "prauc6")
        verdict[m] = "동등" if abs(diff) <= EQ else (f"{names[1]} 우세" if diff > 0 else f"{names[0]} 우세")
        md += [f"## 입력 {lab}", "", "| 지표 | " + " | ".join(names) + " | 차이 (ELECTRA − BERT) |", "|---|---:|---:|---:|"]
        rows = [("6종 PR-AUC (시드 평균 ± 표준편차)", "prauc6", ".4f"), (f"위반 탐지 (/{sc})", "det", ".1f"), (f"정답 유형 적중 (/{sc})", "hit", ".1f"),
                (f"유형 오인 (/{sc})", "F1", ".1f"), (f"놓침 (/{sc})", "F2", ".1f"), (f"적법 원천(D · L) 오판정 (/{nn})", "neg", ".1f"),
                (f"검수 적법 정상 문구 후보 (/{nsyn})", "syn_flag", ".1f"), (f"사실 전제 dev 후보 (/{len(fids)})", "fact", ".1f")]
        for title, k, f in rows:
            cells = [f"{mn(n, m, k):{f}}" + (f" ± {sdv(n, m, k):.4f}" if k == "prauc6" else "") for n in names]
            md.append(f"| {title} | " + " | ".join(cells) + f" | {mn(names[1], m, k) - mn(names[0], m, k):+{f}} |")
        md += ["", f"판단 (6종 PR-AUC 차이 {diff:+.4f} · 기준 ±{EQ}) — **{verdict[m]}**", "",
               "| 유형별 재현율 | 정답 행 | " + " | ".join(names) + " |", "|---|---:|---:|---:|"]
        for x in C:
            if npos[x]:
                md.append(f"| {x}{' *' if npos[x] < 30 else ''} | {npos[x]} | " +
                          " | ".join(f"{statistics.mean(R[(n, m, s)]['rec'][x] for s in SEEDS) * 100:.1f}%" for n in names) + " |")
        md.append("")
    md += ["\\* dev 양성 30 미만 — 측정 불가(D-324 결정 2) · 문턱은 그 판의 F1 최대 임시값.", "",
           "학습 설정(lr 2e-5 · 6 epoch · 배치 32 · Focal γ 1.5)은 KcBERT 에 맞춘 값 그대로다 — ELECTRA 에 맞춰 고르지 않았다.", "",
           "🚨 dev 다 — 같은 dev 로 문턱을 골랐다(D-324). 봉인 평가셋은 열지 않았다(D-175)."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
