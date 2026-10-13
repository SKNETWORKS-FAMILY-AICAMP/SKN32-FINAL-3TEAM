"""D4-04 품목입력 — 옛 카드 6 재시도의 판정 (박수진 · 2026-10-12 · 탐색)

학습 없음 — D4-04 노트북(`copylane_encoder_D4-04_품목입력_20261012.ipynb`)이 낸 시드 · 입력별 행별 확률과
D4-00(카드 17 채택 판)의 행별 확률을 같은 D-324 문턱 · 같은 채점으로 견준다.

  uv run python docs\\psj\\e2e_prototype\\d4_04_product_input.py --dir <카드 17 행별 확률 폴더> --d4-dir <D4-04 행별 확률 폴더> --out-md docs\\psj\\reports\\D4-04_품목입력_dev_YYYYMMDD.md

  · `--dir` = D4-00 · 기준선 재현(카드 17)의 CSV 가 있는 곳 (`Downloads\\copylane_v10`) · `--d4-dir` = D4-04 의 CSV 가 있는 곳 (안 주면 `--dir` 과 같다)

  · 모델 — D4-00 = `카드17-검수정상음성` · D4-04 = `D4-04-품목입력` 의 두 입력 (가) 품목 · (나) 모름 · 시드 48 · 49 · 50 짝
  · 문턱 — D-324 (card17_adopt.py 와 같은 규칙 · 같은 목표 = 카드17-Baseline재현 3 시드의 유형별 재현율 평균) · 모델 · 입력 · 시드마다 고른다
  · 기준 (D4 실험기록 D4-04 에 먼저 적었다 · 시드 평균 · D4-00 대비 · (가) (나) 둘 다)
      관문 B 6종 PR-AUC −0.02 이내 · G1 위반 탐지 −2.5%p 이내 · G3 음성(D · L) 오판정 +4행 이내
      한도 검수 적법 정상 문구 측정용 171행의 후보 +5행 이내
      목표 (가) 품목을 아는 dev 위반(채점 216행)의 유형 오인이 D4-00 의 0.75배 이하
      판정 — 탐색 통과 = 두 입력 모두 관문 · 한도를 지키고 목표를 채운다 (채택이 아니다 — D-326 보충 12 를 열지는 팀장 판정)
  · 참고 — 유형별 재현율 · 정답 유형 적중 · 품목별 유형 오인 · 화장품 「유형 없는 위반」에 후보가 선 행(옛 카드 6 의 숨은 값)
  · `--self-test` — D4-04 자리에 D4-00 을 넣는다. 차이가 모두 0 이어야 한다

🔴 dev 전용 (D-175). 집계표에는 건수만 쓴다.
"""
import argparse
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
D400 = ca.CAND
D404 = "copylane-encoder-kcbert-D4-04-품목입력"
MODES = {"품목": "(가) 품목", "모름": "(나) 모름"}
CATS = ["식품", "건기식", "화장품"]
GATE = {"prauc": 0.02, "det": 0.025, "neg": 4}
SYN_UP = 5
GOAL = 0.75


def paths(a, model, mode, s):
    if model == D400 or a.self_test:
        b = f"{D400}_seed{s}"
    else:
        b = f"{D404}_{mode}_seed{s}"
        d = a.d4_dir or a.dir
        return os.path.join(d, f"{b}_dev행별확률.csv"), os.path.join(d, f"{b}_합성정상_행별확률.csv")
    return os.path.join(a.dir, f"{b}_dev행별확률.csv"), os.path.join(a.dir, f"{b}_합성정상_행별확률.csv")


def measure(dev, P, th, syn_path):
    e = sd.evaluate(dev, P, th)
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    known = [k for k in sc if dev[k].get("품목") in CATS]
    out = {"prauc6": e["prauc6"], "det": e["det"], "hit": e["hit"], "scored": e["scored"], "neg": e["neg"][0], "neg_n": e["neg"][1],
           "F1": e["cat_n"]["F1 유형 오인"], "F2": e["cat_n"]["F2 놓침"], "known_n": len(known),
           "known_F1": sum(1 for k in known if e["cats"][k] == "F1 유형 오인"),
           "cat_F1": {c: sum(1 for k in sc if dev[k].get("품목") == c and e["cats"][k] == "F1 유형 오인") for c in CATS + [None]},
           "cos_pending": (sum(1 for k, r in enumerate(dev) if r["bucket"] == "pending" and r.get("품목") == "화장품" and e["cand"][k]),
                           sum(1 for r in dev if r["bucket"] == "pending" and r.get("품목") == "화장품")),
           "rec": {x: (e["types"][x]["tp"] / e["types"][x]["n"]) if e["types"][x]["n"] else None for x in sd.CONF8}}
    syn = ca.syn_counts(syn_path, th)
    out["syn_flag"] = syn.get("합성정상dev", {}).get("flag", 0)
    out["syn_quiet"] = syn.get("합성정상dev", {}).get("quiet", 0)
    out["syn_n"] = syn.get("합성정상dev", {}).get("n", 0)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 기준선 재현(카드 17) 행별 확률 폴더")
    ap.add_argument("--d4-dir", default=None, help="D4-04 행별 확률 폴더 (안 주면 --dir)")
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="D4-04 자리에 D4-00 을 넣는다 — 차이가 0 이어야 한다")
    a = ap.parse_args(argv)

    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    R = {}
    for model, modes in ((D400, ["—"]), (D404, list(MODES))):
        for mode in modes:
            for s in SEEDS:
                dp, spth = paths(a, model, mode, s)
                P = sd.read_probs(dp, dev)
                th, _ = ca.d324_thresholds(Y, P, target)
                R[(model, mode, s)] = measure(dev, P, th, spth)
    base = {k: statistics.mean(R[(D400, "—", s)][k] for s in SEEDS) for k in ("prauc6", "det", "hit", "neg", "F1", "F2", "known_F1", "syn_flag", "syn_quiet")}
    sc, nn, kn = R[(D400, "—", SEEDS[0])]["scored"], R[(D400, "—", SEEDS[0])]["neg_n"], R[(D400, "—", SEEDS[0])]["known_n"]
    print(f"[대조] D4-00 — 위반 탐지 {base['det']:.1f} · 정답 유형 적중 {base['hit']:.1f} · F1 유형 오인 {base['F1']:.1f} (카드 17 · D4-02 와 같아야 한다)")

    m = lambda mode, k: statistics.mean(R[(D404, mode, s)][k] for s in SEEDS)
    per = lambda model, mode, k: " · ".join(f"{R[(model, mode, s)][k]:g}" if not isinstance(R[(model, mode, s)][k], float) else f"{R[(model, mode, s)][k]:.4f}" for s in SEEDS)
    title = "D4-04 품목입력 — 옛 카드 6 재시도 (dev · 탐색)" + (" — 자기 검증" if a.self_test else "")
    md = [f"# {title}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · D-324 문턱 (모델 · 입력 · 시드마다) · 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · "
          f"D4-00 = 카드17-검수정상음성 · 건수만 적는다", "",
          "| 지표 | D4-00 | D4-04 (가) 품목 | D4-04 (나) 모름 |", "|---|---:|---:|---:|"]
    rowdef = [("6종 PR-AUC", "prauc6", ".4f"), (f"위반 탐지 (/{sc})", "det", ".1f"), (f"정답 유형 적중 (/{sc})", "hit", ".1f"),
              (f"F1 유형 오인 (/{sc})", "F1", ".1f"), (f"**품목을 아는 위반의 유형 오인 (/{kn})**", "known_F1", ".1f"), ("F2 놓침", "F2", ".1f"),
              (f"음성(D · L) 오판정 (/{nn})", "neg", ".1f"), ("검수 적법 정상 문구 — 후보 (/171)", "syn_flag", ".1f"), ("검수 적법 정상 문구 — 조용 (/171)", "syn_quiet", ".1f")]
    for name, k, f in rowdef:
        md.append(f"| {name} | {format(base[k], f)} ({per(D400, '—', k)}) | " +
                  " | ".join(f"{format(m(md_, k), f)} ({per(D404, md_, k)})" for md_ in MODES) + " |")

    md += ["", "### 품목별 유형 오인 · 숨은 값 (시드 평균)", "", "| 갈래 | D4-00 | (가) 품목 | (나) 모름 |", "|---|---:|---:|---:|"]
    for c in CATS + [None]:
        md.append(f"| 유형 오인 — {c or '품목 없음'} | {statistics.mean(R[(D400, '—', s)]['cat_F1'][c] for s in SEEDS):.1f} | " +
                  " | ".join(f"{statistics.mean(R[(D404, md_, s)]['cat_F1'][c] for s in SEEDS):.1f}" for md_ in MODES) + " |")
    cp = lambda model, mode: statistics.mean(R[(model, mode, s)]["cos_pending"][0] for s in SEEDS)
    cpn = R[(D400, "—", SEEDS[0])]["cos_pending"][1]
    md.append(f"| 화장품 「유형 없는 위반」에 후보 (/{cpn}) | {cp(D400, '—'):.1f} | " + " | ".join(f"{cp(D404, md_):.1f}" for md_ in MODES) + " |")

    md += ["", "### 유형별 재현율 (시드 평균 · D-324 문턱이라 측정 가능한 유형은 목표 근처로 맞춰진다)", "",
           "| 유형 | dev 양성 | D4-00 | (가) 품목 | (나) 모름 |", "|---|---:|---:|---:|---:|"]
    rr = lambda model, mode, x: statistics.mean(R[(model, mode, s)]["rec"][x] for s in SEEDS) * 100
    for x in sd.CONF8:
        md.append(f"| {x}{' (측정 불가)' if npos[x] < ca.MEASURABLE_MIN else ''} | {npos[x]} | {rr(D400, '—', x):.1f}% | " +
                  " | ".join(f"{rr(D404, md_, x):.1f}%" for md_ in MODES) + " |")

    md += ["", "### 기준 (D4 실험기록 D4-04 에 먼저 적은 것 · D4-00 대비 · 시드 평균)", "",
           "| 기준 | (가) 품목 | (나) 모름 |", "|---|---|---|"]
    ok_all = True
    cells = {}
    for md_ in MODES:
        d_pr, d_det, d_neg, d_syn = m(md_, "prauc6") - base["prauc6"], (m(md_, "det") - base["det"]) / sc, m(md_, "neg") - base["neg"], m(md_, "syn_flag") - base["syn_flag"]
        cells[md_] = [(f"{d_pr:+.4f}", d_pr >= -GATE["prauc"] - 1e-12), (f"{d_det * 100:+.1f}%p", d_det >= -GATE["det"] - 1e-12),
                      (f"{d_neg:+.1f}행", d_neg <= GATE["neg"] + 1e-9), (f"{d_syn:+.1f}행", d_syn <= SYN_UP + 1e-9)]
        ok_all &= all(v for _, v in cells[md_])
    for i, name in enumerate(["관문 B — 6종 PR-AUC −0.02 이내", "관문 G1 — 위반 탐지 −2.5%p 이내", "관문 G3 — 음성 오판정 +4행 이내", "한도 — 검수 적법 정상 문구 후보 +5행 이내"]):
        md.append(f"| {name} | " + " | ".join(f"{cells[md_][i][0]} · {'지킴' if cells[md_][i][1] else '**넘음**'}" for md_ in MODES) + " |")
    lim = GOAL * base["known_F1"]
    g = m("품목", "known_F1")
    goal_ok = g <= lim + 1e-9
    md.append(f"| 목표 — (가) 품목을 아는 위반의 유형 오인 {lim:.1f}행 이하 (D4-00 {base['known_F1']:.1f} × {GOAL}) | {g:.1f} · {'충족' if goal_ok else '**미달**'} | — |")
    verdict = "**탐색 통과** — 두 입력 모두 관문 · 한도를 지키고 목표를 채웠다. 채택이 아니다 — D-326 보충 12(인코더는 기준 전제 하나로 배운다)를 열지는 팀장 판정" \
        if ok_all and goal_ok else "**탐색 탈락** — " + " · ".join(
            ([] if ok_all else ["관문 · 한도를 넘은 칸이 있다"]) + ([] if goal_ok else ["목표 미달"]))
    md += ["", verdict]

    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8") as fo:
            fo.write(out)
        print(f"[INFO] 집계표(건수만): {a.out_md}")


if __name__ == "__main__":
    main()
