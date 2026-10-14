"""D4-12 짧은문턱 — 짧은 문장에만 문턱을 올리기 (박수진 · 2026-10-14 · 학습 없음)

공백 뺀 글자 수 12 미만인 문장은 모든 유형의 문턱을 max(그 판의 D-324 문턱, τ_s) 로 올린다.
기준은 D4 실험기록 「D4-12 짧은문턱」 에 먼저 적었다 — 한도: 위반 탐지 −2.5%p 이내 · 목표: 짧은 사실 문장 10 중 후보 2 이하.

  dev (로컬 · CSV):
    uv run python docs\\psj\\e2e_prototype\\d4_12_short_th.py --dir <D4-00 CSV> --d10-dir <D4-10 CSV> --review-csv <검수판> --out-md docs\\psj\\reports\\D4-12_짧은문턱_dev_YYYYMMDD.md
  효과 묶음 (가중치가 있는 곳 · 배포 시드만):
    python d4_12_short_th.py --probe --d400-model <D4-00 폴더> --d410-model <D4-10 폴더>
  `--self-test` — τ_s 를 0 으로 두면(짧은 문장도 D-324 그대로) D4-00 위반 탐지가 D4 기준 수 473.3 과 같은지 본다

🔴 dev 전용 (D-175). 건수만 적는다 (D-249). 효과 묶음 10 문장은 dev 가 아니다 — Claude 가 제보 꼴로 만든 문장(제보 원문 셋 포함).
"""
import argparse
import csv
import os
import statistics

SHORT = 12
TAUS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
LIM_DET, GOAL_PROBE = 0.025, 2
D410 = "copylane-encoder-kcbert-D4-10-품목입력사실전제"
# 효과 묶음 — 순수 사실 문장 10 (소성민 제보 원문 셋 + 같은 꼴로 만든 일곱 · 품목은 식품)
PROBE = ["국산 우엉을 볶아 우린 차", "씨를 제거한 국산 대추칩", "저온 살균한 목장 우유", "국산 우엉을 볶아 우린 차입니다",
         "국산 우엉을 볶아 우린 차예요. 따뜻한 물에 티백 하나를 3분 우려 드세요", "우엉을 볶아 우린 차", "볶은 우엉차",
         "배도라지즙", "국산 배와 도라지를 달인 즙", "100% 국산 대추만 담았어요"]
# 배포 시드의 D-324 문턱 (D4-00 시드 49 = 채택 판 label_scheme · D4-10 시드 48 = 집계표 D4-10_품목입력사실전제_dev_20261014.md)
TH_DEPLOY = {
    "D4-00": {"질병_예방치료_표방": 0.45, "건강기능식품_오인": 0.65, "의약품_오인": 0.65, "거짓_과장": 0.475, "소비자_기만": 0.5,
              "후기_체험기_기만": 0.6, "부당_비교광고": 0.6, "비방광고": 0.3, "기능성화장품_오인": 1.01},
    "D4-10 (가) 품목": {"질병_예방치료_표방": 0.75, "건강기능식품_오인": 0.675, "의약품_오인": 0.825, "거짓_과장": 0.475, "소비자_기만": 0.4,
                     "후기_체험기_기만": 0.3, "부당_비교광고": 0.525, "비방광고": 0.5, "기능성화장품_오인": 1.01},
    "D4-10 (나) 모름": {"질병_예방치료_표방": 0.55, "건강기능식품_오인": 0.475, "의약품_오인": 0.6, "거짓_과장": 0.525, "소비자_기만": 0.4,
                     "후기_체험기_기만": 0.65, "부당_비교광고": 0.625, "비방광고": 0.275, "기능성화장품_오인": 1.01},
}


def nchar(t):
    return len(t.replace(" ", ""))


def flagged(p, th, short, tau):
    return any(p[i] >= (max(th[x], tau) if short else th[x]) for i, x in enumerate(th))


def probe(a):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    out = {}
    for name, mdir, cat in (("D4-00", a.d400_model, None), ("D4-10 (가) 품목", a.d410_model, "식품"), ("D4-10 (나) 모름", a.d410_model, "모름")):
        tok = AutoTokenizer.from_pretrained(mdir)
        m = AutoModelForSequenceClassification.from_pretrained(mdir).eval()
        labs = [m.config.id2label[i] for i in range(m.config.num_labels)]
        th = TH_DEPLOY[name]
        probs = []
        for s in PROBE:
            e = tok(s, truncation=True, max_length=128, return_tensors="pt") if cat is None else \
                tok(cat, s, truncation="only_second", max_length=136, return_tensors="pt")
            with torch.no_grad():
                p = torch.sigmoid(m(**e).logits)[0].tolist()
            probs.append({lab: v for lab, v in zip(labs, p)})
        out[name] = {tau: sum(1 for s, d in zip(PROBE, probs) if any(d[x] >= (max(th[x], tau) if nchar(s) < SHORT else th[x]) for x in th))
                     for tau in [0.0] + TAUS}
    print("| 판 | D-324 그대로 | " + " | ".join(f"τ_s {t:.2f}" for t in TAUS) + " |")
    print("|---|---:|" + "---:|" * len(TAUS))
    for name, d in out.items():
        print(f"| {name} | {d[0.0]} | " + " | ".join(str(d[t]) for t in TAUS) + " |")
    print(f"\n(짧은 사실 문장 {len(PROBE)} 중 후보가 서는 문장 · 12자 미만 {sum(nchar(s) < SHORT for s in PROBE)}개 · 배포 시드)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--d400-model")
    ap.add_argument("--d410-model")
    ap.add_argument("--dir")
    ap.add_argument("--d10-dir")
    ap.add_argument("--review-csv")
    ap.add_argument("--golden", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.probe:
        return probe(a)

    import card17_adopt as ca
    import score_encoder_dev as sd

    dev, gsha, mark = sd.load_dev(a.golden or sd.GOLDEN)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(C)}
    short = [nchar(r["text"]) < SHORT for r in dev]
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    dl = [k for k, r in enumerate(dev) if r.get("조건") in ("D", "L")]
    with open(a.review_csv, encoding="utf-8-sig", newline="") as fh:
        stext = {"syn:" + r["id"]: r["text"] for r in csv.DictReader(fh)}
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in ca.SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in ca.SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in ca.SEEDS) for x in rec[ca.SEEDS[0]]}

    models = [("D4-00", lambda s: os.path.join(a.dir, f"{ca.CAND}_seed{s}"))]
    if a.d10_dir:
        models += [(f"D4-10 {lab}", (lambda m: lambda s: os.path.join(a.d10_dir, f"{D410}_{m}_seed{s}"))(m)) for m, lab in (("품목", "(가) 품목"), ("모름", "(나) 모름"))]
    taus = [0.0] + TAUS
    R = {}
    for name, base in models:
        for s in ca.SEEDS:
            P = sd.read_probs(base(s) + "_dev행별확률.csv", dev)
            th, _ = ca.d324_thresholds(Y, P, target)
            with open(base(s) + "_합성정상_행별확률.csv", encoding="utf-8-sig", newline="") as fh:
                syn = [(r["갈래"], nchar(stext[r["id"]]) < SHORT, [float(r[f"p_{x}"]) for x in C]) for r in csv.DictReader(fh)]
            for tau in taus:
                fl = [flagged(P[k], th, short[k], tau) for k in range(len(dev))]
                hit = sum(1 for k in sc if any(Y[k][i] and P[k][i] >= (max(th[x], tau) if short[k] else th[x]) for i, x in enumerate(C)))
                R[(name, tau, s)] = {"det": sum(1 for k in sc if fl[k]), "det_s": sum(1 for k in sc if short[k] and fl[k]), "hit": hit,
                                     "neg": sum(1 for k in dl if fl[k]), "neg_s": sum(1 for k in dl if short[k] and fl[k]),
                                     "syn": sum(1 for br, sh, p in syn if br == "합성정상dev" and flagged(p, th, sh, tau)),
                                     "fact": sum(1 for br, sh, p in syn if br == "참고-적법(사실 전제)" and flagged(p, th, sh, tau))}
    mn = lambda name, tau, k: statistics.mean(R[(name, tau, s)][k] for s in ca.SEEDS)
    if a.self_test:
        got = round(mn("D4-00", 0.0, "det"), 1)
        print(f"  D4-00 · τ_s 0 위반 탐지 {got} · 기록 473.3")
        if got != 473.3:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0
    n_s = sum(1 for k in sc if short[k])
    n_dls = sum(1 for k in dl if short[k])
    md = ["# D4-12 짧은문턱 — 12자 미만 문장에만 문턱을 올리기 (dev)", "",
          f"> golden `{gsha[:12]}` · dev `{mark}` · 시드 48 · 49 · 50 평균 · 문턱 = max(그 판의 D-324, τ_s) — 12자 미만(공백 뺀 글자 수) 문장만 · "
          f"유형 있는 위반 510 중 짧은 행 {n_s} · D · L 86 중 짧은 행 {n_dls} · 건수만 적는다", ""]
    for name, _ in models:
        b = R[(name, 0.0, ca.SEEDS[0])]
        md += [f"## {name}", "", f"| τ_s | 위반 탐지 (/510) | 차이 | 짧은 위반 탐지 (/{n_s}) | 정답 유형 적중 | 음성 오판정 (/86 · 짧은 /{n_dls}) | 정상 문구 171 후보 | 사실 전제 110 후보 | 한도 |",
               "|---|---:|---:|---:|---:|---|---:|---:|---|"]
        d0 = mn(name, 0.0, "det")
        for tau in taus:
            d = mn(name, tau, "det")
            ok = (d - d0) / 510 >= -LIM_DET - 1e-12
            md.append(f"| {'D-324 그대로' if tau == 0 else f'{tau:.2f}'} | {d:.1f} | {(d - d0) / 510 * 100:+.1f}%p | {mn(name, tau, 'det_s'):.1f} | "
                      f"{mn(name, tau, 'hit'):.1f} | {mn(name, tau, 'neg'):.1f} · {mn(name, tau, 'neg_s'):.1f} | {mn(name, tau, 'syn'):.1f} | "
                      f"{mn(name, tau, 'fact'):.1f} | {'지킴' if ok else '**넘음**'} |")
        md.append("")
    md += ["효과(짧은 사실 문장 10)는 `--probe` 로 따로 잰다 — 기록 「D4-12」 결과.", "",
           "🚨 dev 다 — dev 의 짧은 행은 대부분 위반이라(위반 510 중 짧은 행이 D · L 의 짧은 행보다 훨씬 많다) 손실은 크게 · 효과는 작게 보인다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
