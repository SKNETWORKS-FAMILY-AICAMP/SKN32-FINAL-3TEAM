"""카드 15 — 대체 문구 재판정에 새 인코더를 붙이면 (C안 · 박수진 · 2026-10-08)

앱은 인코더를 두 번 부른다 — 사용자 문구 판정(첫째)과 sLLM 대체 문구 재판정(둘째). 지금은 둘 다 같은 판정 코어다(D-119).
첫째에는 카드 14 의 채택 후보(카드 9 설정 KcBERT)를 붙인다. 이 스크립트는 둘째에 백본이 다른 새 인코더를 붙인 C안을
첫째를 두 번 쓰는 A안과 견준다. **학습 결과(행별 확률)만 읽는다.**

  uv run python docs\\psj\\e2e_prototype\\second_pass.py --dir <행별 확률 폴더> --out-md docs\\psj\\reports\\v10_카드15_둘째인코더_dev_20261008.md

  · 문턱 — 첫째 · 둘째 모두 유형마다 v10(선택 시드 42 · F1 최대)의 dev 재현율 이상인 가장 높은 문턱 (넘긴 후보와 같은 규칙)
  · 시드 45 · 46 · 47 평균 (규약 2판) · 같은 시드끼리 짝
  · 「통과」 = 조용(모든 유형이 문턱의 절반 미만 — 판정 로직이 통과시킬 수 있는 문장)
  · 재료 — 정상 합성 문구 측정용 285행(적법한 대체 문구의 대리) · 공통 dev 유형 있는 위반 510행(위반이 남은 대체 문구의 대리) · D · L 86행
  · 불일치 = C안에서 같은 문장에 둘째는 통과 · 첫째는 통과 못 함 — D-119 가 막으려는 것. **판정 없이 반드시 적는다**
  · --self-test — 둘째 자리에 첫째를 넣는다 (불일치 0 · A안과 C안의 수가 같아야 한다)

목표 · 한도는 실험 기록 카드 15 에 먼저 적었다(`docs/psj/reports/v10_문턱규칙_거짓과장_실험기록_20261007.md`).
🔴 dev 전용 (D-175). 집계표에는 건수만 쓴다.
"""
import argparse
import csv
import os
import statistics

import matched_recall as mr
import score_encoder_dev as sd

SEEDS = [45, 46, 47]
V10 = "copylane-encoder-kcbert-v10-합성O-이유O"
FIRST = "copylane-encoder-kcbert-v10-카드9-정상음성"          # 카드 14 의 채택 후보 설정
SECONDS = {"15a KcELECTRA": "copylane-encoder-kcelectra-v10-카드15-KcELECTRA",
           "15b KLUE-RoBERTa": "copylane-encoder-klue-roberta-v10-카드15-KLUE"}
#: 카드 15 에 먼저 적은 값 — 결과를 본 뒤 고치지 않는다
GOAL_SYN_UP = 0.10       # 목표 — 둘째 판정의 정상 합성 문구 통과(시드 평균)가 A안보다 10%p 이상 높다
LIM_VIOL_PASS = 2        # 한도 ① — 위반 행이 둘째에서 통과하는 수가 A안보다 2행 넘게 늘지 않는다
LIM_DET = 0.025          # 한도 ② — 둘째의 위반 탐지가 A안보다 2.5%p 넘게 내려가지 않는다 (규약 2판 G1)
LIM_DL = 4               # 한도 ③ — D · L 에 후보가 서는 수가 A안보다 4행 넘게 늘지 않는다 (규약 2판 G3)


def quiet(row, th):
    return all(row[i] < th[x] * 0.5 for i, x in enumerate(sd.CONF8))


def flag(row, th):
    return any(row[i] >= th[x] for i, x in enumerate(sd.CONF8))


def read_syn(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["갈래"] == "합성정상dev"]
    return {r["id"]: [float(r[f"p_{x}"]) for x in sd.CONF8] for r in rows}


def second_stats(dev, d, s, th):
    """둘째 판정 자리에 이 모델을 둘 때의 수."""
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    dl = [k for k, r in enumerate(dev) if r["bucket"] in ("D", "L")]
    return {"syn_pass": sum(quiet(v, th) for v in s.values()), "viol_pass": sum(quiet(d[k], th) for k in sc),
            "det": sum(flag(d[k], th) for k in sc), "dl_flag": sum(flag(d[k], th) for k in dl),
            "n_syn": len(s), "n_sc": len(sc), "n_dl": len(dl)}


def mismatch(dev, d1, s1, th1, d2, s2, th2):
    """C안의 불일치 — 둘째 통과 · 첫째 통과 못 함 (그중 첫째에 후보가 선 행) · 반대 방향."""
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    if set(s1) != set(s2):
        raise SystemExit("🔴 두 모델의 정상 합성 문구 행이 다르다")
    return {"mis_syn": sum(quiet(s2[i], th2) and not quiet(s1[i], th1) for i in s1),
            "mis_syn_flag": sum(quiet(s2[i], th2) and flag(s1[i], th1) for i in s1),
            "mis_viol": sum(quiet(d2[k], th2) and not quiet(d1[k], th1) for k in sc),
            "mis_viol_flag": sum(quiet(d2[k], th2) and flag(d1[k], th1) for k in sc),
            "rev_syn": sum(quiet(s1[i], th1) and not quiet(s2[i], th2) for i in s1),
            "rev_viol": sum(quiet(d1[k], th1) and not quiet(d2[k], th2) for k in sc)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--v10-scheme", default=None, help="v10 의 문턱 (기본: <dir>/" + V10 + "_scheme.zip)")
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    seconds = {"자기 검증 (둘째 = 첫째)": FIRST} if a.self_test else SECONDS
    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    f = lambda tag, s, kind: os.path.join(a.dir, f"{tag}_seed{s}_{kind}.csv")

    th10, _ = sd.read_scheme(a.v10_scheme or os.path.join(a.dir, f"{V10}_scheme.zip"))
    e10 = sd.evaluate(dev, sd.read_probs(os.path.join(a.dir, f"{V10}_dev행별확률.csv"), dev), th10)
    target = {x: e10["types"][x]["tp"] / e10["types"][x]["n"] for x in sd.CONF8 if e10["types"][x]["n"]}

    A, C, MIS, PR = {}, {n: {} for n in seconds}, {n: {} for n in seconds}, {"첫째 (카드 9 설정 KcBERT)": {}}
    PR.update({n: {} for n in seconds})
    for s in SEEDS:
        d1, s1 = sd.read_probs(f(FIRST, s, "dev행별확률"), dev), read_syn(f(FIRST, s, "합성정상_행별확률"))
        th1 = mr.matched(Y, d1, target)
        A[s] = second_stats(dev, d1, s1, th1)
        PR["첫째 (카드 9 설정 KcBERT)"][s] = sd.macro_prauc(Y, d1, 6)
        for n, tag in seconds.items():
            d2, s2 = sd.read_probs(f(tag, s, "dev행별확률"), dev), read_syn(f(tag, s, "합성정상_행별확률"))
            th2 = mr.matched(Y, d2, target)
            C[n][s], MIS[n][s] = second_stats(dev, d2, s2, th2), mismatch(dev, d1, s1, th1, d2, s2, th2)
            PR[n][s] = sd.macro_prauc(Y, d2, 6)

    m = lambda D, k: statistics.mean(D[s][k] for s in SEEDS)
    per = lambda D, k: " · ".join(str(D[s][k]) for s in SEEDS)
    n_syn, n_sc, n_dl = A[SEEDS[0]]["n_syn"], A[SEEDS[0]]["n_sc"], A[SEEDS[0]]["n_dl"]
    names = list(seconds)
    md = [f"# 카드 15 — 대체 문구 재판정에 새 인코더 (C안 · dev){' — 자기 검증' if a.self_test else ''}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · "
          "첫째 = 카드 9 설정 KcBERT(카드 14 의 채택 후보) · 문턱은 첫째 · 둘째 모두 v10 재현율 맞춤 · 건수만 적는다", "",
          "「통과」 = 조용 — 모든 유형의 확률이 문턱의 절반 미만 (판정 로직이 통과시킬 수 있는 문장 · 사전이 조용할 때)", "",
          "### 둘째 판정 (대체 문구 재판정) 자리의 수", "",
          "| 지표 | A안 — 첫째를 두 번 (D-119) | " + " | ".join(f"C안 — {n}" for n in names) + " |",
          "|---|---:|" + "---:|" * len(names),
          f"| 정상 합성 문구 — 통과 (/{n_syn}) | {m(A, 'syn_pass'):.1f} ({per(A, 'syn_pass')}) | " + " | ".join(f"{m(C[n], 'syn_pass'):.1f} ({per(C[n], 'syn_pass')})" for n in names) + " |",
          f"| 위반 행 — 통과해 버림 (/{n_sc}) | {m(A, 'viol_pass'):.1f} ({per(A, 'viol_pass')}) | " + " | ".join(f"{m(C[n], 'viol_pass'):.1f} ({per(C[n], 'viol_pass')})" for n in names) + " |",
          f"| 위반 탐지 — 후보가 섬 (/{n_sc}) | {m(A, 'det'):.1f} | " + " | ".join(f"{m(C[n], 'det'):.1f}" for n in names) + " |",
          f"| D · L — 후보가 섬 (/{n_dl}) | {m(A, 'dl_flag'):.1f} | " + " | ".join(f"{m(C[n], 'dl_flag'):.1f}" for n in names) + " |", "",
          "6종 PR-AUC 시드 평균 (참고 · 문턱과 무관) — " + " · ".join(f"{k} {statistics.mean(v.values()):.4f}" for k, v in PR.items()), "",
          "### 불일치 — C안에서 같은 문장에 두 판정이 다른 답 (판정 없이 적는다 · A안은 0)", "",
          "| 불일치 | " + " | ".join(names) + " | 뜻 |", "|---|" + "---:|" * len(names) + "---|",
          f"| 정상 합성 문구 — 둘째 통과 · 첫째 통과 못 함 (/{n_syn}) | " + " | ".join(f"{m(MIS[n], 'mis_syn'):.1f} (그중 첫째 후보 {m(MIS[n], 'mis_syn_flag'):.1f})" for n in names)
          + " | 승인된 대체 문구를 사용자가 검수에 다시 넣으면 보류된다 |",
          f"| 위반 행 — 둘째 통과 · 첫째 통과 못 함 (/{n_sc}) | " + " | ".join(f"{m(MIS[n], 'mis_viol'):.1f} (그중 첫째 후보 {m(MIS[n], 'mis_viol_flag'):.1f})" for n in names)
          + " | 🔴 첫째라면 잡았을 위반이 대체 문구 자리에서 빠진다 |",
          f"| 정상 합성 문구 — 첫째 통과 · 둘째 통과 못 함 (/{n_syn}) | " + " | ".join(f"{m(MIS[n], 'rev_syn'):.1f}" for n in names) + " | 반대 방향 — 대체 문구가 더 거부된다 |",
          f"| 위반 행 — 첫째 통과 · 둘째 통과 못 함 (/{n_sc}) | " + " | ".join(f"{m(MIS[n], 'rev_viol'):.1f}" for n in names) + " | 반대 방향 — 둘째가 더 잡는다 |"]
    if not a.self_test:
        md += ["", "### 목표 · 한도 (카드 15 에 먼저 적은 것 · 시드 평균 · A안 대비)", "",
               "| 백본 | 목표 — 정상 문구 통과 +10%p 이상 | ① 위반 행 통과 +2 이내 | ② 위반 탐지 −2.5%p 이내 | ③ D · L 후보 +4 이내 | 판정 |",
               "|---|---|---|---|---|---|"]
        for n in names:
            up = (m(C[n], "syn_pass") - m(A, "syn_pass")) / n_syn
            dv, dd, dl = m(C[n], "viol_pass") - m(A, "viol_pass"), (m(C[n], "det") - m(A, "det")) / n_sc, m(C[n], "dl_flag") - m(A, "dl_flag")
            ok = [up >= GOAL_SYN_UP - 1e-12, dv <= LIM_VIOL_PASS + 1e-9, dd >= -LIM_DET - 1e-12, dl <= LIM_DL + 1e-9]
            md.append(f"| {n} | {'충족' if ok[0] else '**미달**'} ({up * 100:+.1f}%p) | {'지킴' if ok[1] else '**넘음**'} ({dv:+.1f}) | "
                      f"{'지킴' if ok[2] else '**넘음**'} ({dd * 100:+.1f}%p) | {'지킴' if ok[3] else '**넘음**'} ({dl:+.1f}) | "
                      f"{'**C안 근거 있음** — 불일치 표와 함께 D-119 개정을 요청할 수 있다' if all(ok) else '근거 없음'} |")
    print("\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
