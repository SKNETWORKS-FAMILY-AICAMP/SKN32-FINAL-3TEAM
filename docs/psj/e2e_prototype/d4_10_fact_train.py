"""D4-10 품목입력 + 사실전제 — 다음 배포 판 후보의 판정 (박수진 · 2026-10-14 · 학습 결과 판정 · 확률만 읽는다)

D4-10 노트북(`copylane_encoder_D4-10_사실전제학습_20261013.ipynb` · 10-14 다시 등록)이 낸 시드 · 입력별 행별 확률을
D4-00(카드 17 채택 판 · 배포 중) · D4-04(품목 입력 · 사실 전제 없음)의 행별 확률과 같은 D-324 문턱 · 같은 채점으로 견준다.
근거 — D-336(인코더 입력에 품목 · 기록은 「모름」 · 분기는 그 품목 · 관문은 둘로 나눠 적는다) · D-331 결정 7(사실 전제를 다음 판에서 음성으로).

  uv run python docs\\psj\\e2e_prototype\\d4_10_fact_train.py --dir <D4-00 CSV 폴더> --d4-dir <D4-04 CSV 폴더> --d10-dir <D4-10 CSV 폴더> --review-csv <권소라 10-11 검수판> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_10_fact_train.py --dir <D4-00 CSV 폴더> --d4-dir <D4-04 CSV 폴더> --d10-dir <D4-10 CSV 폴더> --review-csv <검수판> --out-md docs\\psj\\reports\\D4-10_품목입력사실전제_dev_YYYYMMDD.md

  · 문턱 — D-324 (card17_adopt.d324_thresholds · 목표 = 카드 17 기준선 재현 3 시드 평균) · 모델 · 입력 · 시드마다 고른다 → 입력별 문턱 두 벌
  · 기준 (D4 실험기록 「D4-10」 에 먼저 적었다 · 시드 평균 · 입력 (가) 품목 · (나) 모름 각각)
      관문 (D4-00 대비) — B 6종 PR-AUC −0.02 이내 · G1 위반 탐지(유형 무관) −2.5%p 이내 · G3 음성(D · L) 오판정 +4행 이내
      한도 ① (D4-00 대비) 검수 적법 정상 문구 측정용 171행 후보 +5행 이내
      한도 ② (D4-00 대비 · (가) 만) 품목을 아는 위반(216)의 유형 오인 ≤ D4-00 × 0.75 (D4-04 의 목표 — 품목 입력의 득을 지킨다)
      한도 ③ (D4-04 대비 · 같은 입력) 건강기능식품_오인 · 의약품_오인 · 질병_예방치료_표방 — 같은 시드 D4-04 의 D-324 문턱을 두 판에 걸어
             「후보가 선 정답 행」이 3행 넘게 줄지 않는다 (사실 전제 음성이 원료를 말하는 위반을 지우는지)
      목표 (D4-00 대비 · D-331 결정 7) 사실 전제 dev 110행(측정 제품)의 후보 ≤ D4-00 × 0.5 — 두 입력 모두
      판정 — 통과 = 두 입력 모두 관문 · 한도 ① ② ③ 을 지키고 목표를 채운다 → 배포 판 후보 (팀장 보고 · 정본 재현 · D-331 결정 2 사후 확인은 팀장)
  · 참고 — 사실 전제 효과(D4-04 → D4-10) · 유형별 재현율 · 품목별 유형 오인 · 화장품 「유형 없는 위반」 후보 · 사실 전제 dev 각도별
  · `--self-test` — D4-10 자리에 D4-04 를 넣는다. D4-00 · D4-04 기준 수가 D4 실험기록과 같고, D4-04 대비 차이가 모두 0 이어야 한다
🔴 dev 전용 (D-175). 집계표에는 건수만 적는다 (D-249).
"""
import argparse
import csv
import os
import random
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure, CATS

SEEDS = ca.SEEDS
D400 = ca.CAND
D404 = "copylane-encoder-kcbert-D4-04-품목입력"
D410 = "copylane-encoder-kcbert-D4-10-품목입력사실전제"
MODES = {"품목": "(가) 품목", "모름": "(나) 모름"}
FACT, FACT_OK = "참고-적법(사실 전제)", "적법(사실 전제)"
LIM3 = ["건강기능식품_오인", "의약품_오인", "질병_예방치료_표방"]
GATE = {"prauc": 0.02, "det": 0.025, "neg": 4}
LIM_SYN, LIM_KNOWN, LIM_POS, GOAL = 5, 0.75, 3, 0.5
SYN_HOLD_PER_CAT, SYN_SEED = 5, 42
# 자기 검증 — D4 실험기록의 수 (D4-00 기준 수 · D4-04 결과 · D4-10 등록 때 잰 D4-00 의 사실 전제 dev 후보)
SELF = {("D4-00", "det"): 473.3, ("D4-00", "syn_flag"): 5.0, ("D4-00", "known_F1"): 33.0, ("D4-00", "fact"): 21.7,
        ("품목", "det"): 467.3, ("품목", "known_F1"): 20.0, ("품목", "syn_flag"): 2.7,
        ("모름", "det"): 480.3, ("모름", "known_F1"): 35.3, ("모름", "syn_flag"): 7.7}


def fact_dev_ids(review_csv):
    """카드 17 과 같은 측정 제품(품목마다 5 · SYN_SEED 42)의 「적법(사실 전제)」 · 애매 표시 없음 행 — 노트북 cell 9 와 같은 규칙."""
    with open(review_csv, encoding="utf-8-sig", newline="") as fh:
        raw = list(csv.DictReader(fh))
    hold = set()
    for c in ("식품", "건기식", "화장품"):
        prods = sorted({r["제품종류"] for r in raw if r["품목"] == c})
        hold |= {(c, p) for p in random.Random(SYN_SEED).sample(prods, SYN_HOLD_PER_CAT)}
    ids = {"syn:" + r["id"] for r in raw if r["판독(사람)"].strip() == FACT_OK and not r["애매표시"].strip() and (r["품목"], r["제품종류"]) in hold}
    angle = {"syn:" + r["id"]: r["각도"] for r in raw}
    return ids, angle


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 카드 17 행별 확률 폴더 (D-324 목표 재현율도 여기서)")
    ap.add_argument("--d4-dir", required=True, help="D4-04 행별 확률 폴더")
    ap.add_argument("--d10-dir", default=None, help="D4-10 행별 확률 폴더 (D4-10_csv.zip 을 푼 곳 · --self-test 에서는 안 읽는다)")
    ap.add_argument("--review-csv", required=True, help="권소라 10-11 검수판 — 사실 전제 dev 110행 · 각도")
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if not a.self_test and not a.d10_dir:
        ap.error("--d10-dir 이 필요하다")

    dev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(C)}
    fids, angle = fact_dev_ids(a.review_csv)
    print(f"[INFO] golden {gsha[:12]} · dev {len(dev)}행 · 지문 {mark} · 사실 전제 dev {len(fids)}행")
    if len(fids) != 110:
        raise SystemExit(f"🔴 사실 전제 dev 가 {len(fids)}행이다 (등록 110)")

    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    def files(model, mode, s):
        if model == D400:
            b, d = f"{D400}_seed{s}", a.dir
        elif model == D404 or a.self_test:
            b, d = f"{D404}_{mode}_seed{s}", a.d4_dir
        else:
            b, d = f"{D410}_{mode}_seed{s}", a.d10_dir
        return os.path.join(d, f"{b}_dev행별확률.csv"), os.path.join(d, f"{b}_합성정상_행별확률.csv")

    def flagged(p, th):
        return any(p[i] >= th[x] for i, x in enumerate(C))

    R, P_, TH = {}, {}, {}
    for model, modes in ((D400, ["—"]), (D404, list(MODES)), (D410, list(MODES))):
        for mode in modes:
            for s in SEEDS:
                dp, spth = files(model, mode, s)
                P = sd.read_probs(dp, dev)
                th, _ = ca.d324_thresholds(Y, P, target)
                r = measure(dev, P, th, spth)
                with open(spth, encoding="utf-8-sig", newline="") as fh:
                    syn = [(row["id"], row["갈래"], [float(row[f"p_{x}"]) for x in C]) for row in csv.DictReader(fh)]
                fact_rows = [(i, p) for i, br, p in syn if i in fids]
                got = {i for i, br, p in syn if br == FACT}
                if model == D410 and not a.self_test and got != fids:
                    raise SystemExit(f"🔴 D4-10 CSV 의 사실 전제 dev 갈래가 등록한 110행과 다르다 ({len(got)}행)")
                if len(fact_rows) != len(fids):
                    raise SystemExit(f"🔴 {os.path.basename(spth)} 에 사실 전제 dev {len(fact_rows)}행뿐이다")
                r["fact"] = sum(1 for i, p in fact_rows if flagged(p, th))
                r["fact_ids"] = {i for i, p in fact_rows if flagged(p, th)}
                R[(model, mode, s)], P_[(model, mode, s)], TH[(model, mode, s)] = r, P, th

    def pos_at(model, mode, s, th):
        P = P_[(model, mode, s)]
        return {x: sum(1 for k in range(len(dev)) if Y[k][C.index(x)] and P[k][C.index(x)] >= th[x]) for x in LIM3}

    mn = lambda model, mode, k: statistics.mean(R[(model, mode, s)][k] for s in SEEDS)
    per = lambda model, mode, k: " · ".join(f"{R[(model, mode, s)][k]:g}" if not isinstance(R[(model, mode, s)][k], float)
                                            else f"{R[(model, mode, s)][k]:.4f}" for s in SEEDS)
    b0 = {k: mn(D400, "—", k) for k in ("prauc6", "det", "hit", "neg", "F1", "F2", "known_F1", "syn_flag", "fact")}
    sc, nn, kn = R[(D400, "—", SEEDS[0])]["scored"], R[(D400, "—", SEEDS[0])]["neg_n"], R[(D400, "—", SEEDS[0])]["known_n"]

    if a.self_test:
        got = {("D4-00", k): round(b0[k], 1) for k in ("det", "syn_flag", "known_F1", "fact")}
        got.update({(m, k): round(mn(D404, m, k), 1) for m in MODES for k in ("det", "known_F1", "syn_flag")})
        diff = {f"{m}·{k}": mn(D410, m, k) - mn(D404, m, k) for m in MODES for k in ("prauc6", "det", "neg", "syn_flag", "fact", "known_F1")}
        diff.update({f"{m}·pos_{x}": statistics.mean(pos_at(D410, m, s, TH[(D404, m, s)])[x] - pos_at(D404, m, s, TH[(D404, m, s)])[x] for s in SEEDS)
                     for m in MODES for x in LIM3})
        bad = [k for k in SELF if SELF[k] != got[k]] + [k for k, v in diff.items() if abs(v) > 1e-12]
        for k in SELF:
            print(f"  {'❌ ' if k in bad else 'OK '} {k}: 기록 {SELF[k]} · 지금 {got[k]}")
        print("  D4-04 대비 차이 (0 이어야 한다): " + " · ".join(f"{k} {v:+g}" for k, v in diff.items()))
        if bad:
            raise SystemExit(f"🔴 자기 검증 실패 — {bad}")
        print("[OK] 자기 검증 통과 — D4-00 · D4-04 기준 수가 기록과 같고 D4-10 자리 차이가 0 이다")
        return 0

    # ── 판정
    cells, ok_all = {}, True
    for m in MODES:
        d_pr, d_det, d_neg = mn(D410, m, "prauc6") - b0["prauc6"], (mn(D410, m, "det") - b0["det"]) / sc, mn(D410, m, "neg") - b0["neg"]
        d_syn = mn(D410, m, "syn_flag") - b0["syn_flag"]
        d_pos = {x: statistics.mean(pos_at(D410, m, s, TH[(D404, m, s)])[x] - pos_at(D404, m, s, TH[(D404, m, s)])[x] for s in SEEDS) for x in LIM3}
        f10 = mn(D410, m, "fact")
        c = [("B 6종 PR-AUC −0.02 이내 (D4-00 대비)", f"{d_pr:+.4f}", d_pr >= -GATE["prauc"] - 1e-12),
             ("G1 위반 탐지 −2.5%p 이내 (D4-00 대비)", f"{d_det * 100:+.1f}%p", d_det >= -GATE["det"] - 1e-12),
             ("G3 음성(D · L) 오판정 +4행 이내 (D4-00 대비)", f"{d_neg:+.1f}행", d_neg <= GATE["neg"] + 1e-9),
             ("한도 ① 검수 적법 정상 문구 후보 +5행 이내 (D4-00 대비)", f"{d_syn:+.1f}행", d_syn <= LIM_SYN + 1e-9)]
        if m == "품목":
            k10 = mn(D410, m, "known_F1")
            c.append((f"한도 ② 품목을 아는 위반의 유형 오인 ≤ {LIM_KNOWN * b0['known_F1']:.1f} (D4-00 {b0['known_F1']:.1f} × {LIM_KNOWN})",
                      f"{k10:.1f}", k10 <= LIM_KNOWN * b0["known_F1"] + 1e-9))
        else:
            c.append(("한도 ② (가) 만", "—", True))
        for x in LIM3:
            c.append((f"한도 ③ {x} 후보가 선 정답 행 (D4-04 문턱 · /{npos[x]}) 3행 넘게 줄지 않음",
                      f"{d_pos[x]:+.1f}", d_pos[x] >= -LIM_POS - 1e-9))
        c.append((f"목표 사실 전제 dev 후보 ≤ {GOAL * b0['fact']:.1f} (D4-00 {b0['fact']:.1f} × {GOAL})", f"{f10:.1f}", f10 <= GOAL * b0["fact"] + 1e-9))
        cells[m] = c
        ok_all &= all(v for _, _, v in c)

    md = ["# D4-10 품목입력 + 사실전제 — 다음 배포 판 후보 (dev · 판정)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · D-324 문턱 (모델 · 입력 · 시드마다 — 입력별 두 벌) · 시드 {' · '.join(map(str, SEEDS))} 평균 "
          "(괄호 안은 시드별) · D4-00 = 카드 17 채택 판(배포 중) · D4-04 = 품목 입력(사실 전제 없음) · 인코더 단독 · 건수만 적는다", "",
          "## 지표", "",
          "| 지표 | D4-00 | D4-04 (가) 품목 | D4-04 (나) 모름 | **D4-10 (가) 품목** | **D4-10 (나) 모름** |", "|---|---:|---:|---:|---:|---:|"]
    rowdef = [("6종 PR-AUC", "prauc6", ".4f"), (f"위반 탐지 · 유형 무관 (/{sc})", "det", ".1f"), (f"정답 유형 적중 (/{sc})", "hit", ".1f"),
              (f"유형 오인 (/{sc})", "F1", ".1f"), (f"품목을 아는 위반의 유형 오인 (/{kn})", "known_F1", ".1f"), ("놓침", "F2", ".1f"),
              (f"음성(D · L) 오판정 (/{nn})", "neg", ".1f"), ("검수 적법 정상 문구 — 후보 (/171)", "syn_flag", ".1f"),
              (f"**사실 전제 dev — 후보 (/{len(fids)})**", "fact", ".1f")]
    for name, k, f in rowdef:
        md.append(f"| {name} | {format(b0[k], f)} | " + " | ".join(f"{format(mn(D404, m, k), f)}" for m in MODES) + " | "
                  + " | ".join(f"**{format(mn(D410, m, k), f)}** ({per(D410, m, k)})" for m in MODES) + " |")

    md += ["", "## 관문 · 한도 · 목표 (D4 실험기록 「D4-10」 에 먼저 적은 것 · 시드 평균)", "", "| 항목 | (가) 품목 | (나) 모름 |", "|---|---|---|"]
    for i in range(len(cells["품목"])):
        md.append(f"| {cells['품목'][i][0]} | " + " | ".join(f"{cells[m][i][1]} · {'지킴' if cells[m][i][2] else '**넘음**'}" for m in MODES) + " |")
    md += ["", "**판정 — " + ("통과 → 배포 판 후보 (팀장 보고 · 정본 재현 · D-331 결정 2 사후 확인은 팀장 · 채택은 팀장 판정)" if ok_all
                              else "통과 아님") + "**", ""]

    md += ["## 사실 전제 효과 — D4-04 → D4-10 (같은 입력 · 시드 평균 · 참고)", "", "| 지표 | (가) D4-04 → D4-10 | (나) D4-04 → D4-10 |", "|---|---|---|"]
    for name, k, f in rowdef:
        md.append(f"| {name} | {format(mn(D404, '품목', k), f)} → {format(mn(D410, '품목', k), f)} | {format(mn(D404, '모름', k), f)} → {format(mn(D410, '모름', k), f)} |")
    for x in LIM3:
        md.append(f"| {x} 후보가 선 정답 행 (D4-04 문턱 · /{npos[x]}) | " + " | ".join(
            f"{statistics.mean(pos_at(D404, m, s, TH[(D404, m, s)])[x] for s in SEEDS):.1f} → {statistics.mean(pos_at(D410, m, s, TH[(D404, m, s)])[x] for s in SEEDS):.1f}"
            for m in MODES) + " |")

    md += ["", "## 유형별 재현율 (시드 평균 · D-324 문턱 · 참고)", "", "| 유형 | dev 양성 | D4-00 | D4-10 (가) 품목 | D4-10 (나) 모름 |", "|---|---:|---:|---:|---:|"]
    rr = lambda model, mode, x: statistics.mean(R[(model, mode, s)]["rec"][x] for s in SEEDS) * 100
    for x in C:
        if npos[x]:
            md.append(f"| {x}{' (측정 불가)' if npos[x] < ca.MEASURABLE_MIN else ''} | {npos[x]} | {rr(D400, '—', x):.1f}% | "
                      + " | ".join(f"{rr(D410, m, x):.1f}%" for m in MODES) + " |")

    md += ["", "## 품목별 유형 오인 · 화장품 「유형 없는 위반」 후보 (시드 평균 · 참고)", "", "| 갈래 | D4-00 | D4-10 (가) 품목 | D4-10 (나) 모름 |", "|---|---:|---:|---:|"]
    for c in CATS + [None]:
        md.append(f"| 유형 오인 — {c or '품목 없음'} | {statistics.mean(R[(D400, '—', s)]['cat_F1'][c] for s in SEEDS):.1f} | "
                  + " | ".join(f"{statistics.mean(R[(D410, m, s)]['cat_F1'][c] for s in SEEDS):.1f}" for m in MODES) + " |")
    cp = lambda model, mode: statistics.mean(R[(model, mode, s)]["cos_pending"][0] for s in SEEDS)
    md.append(f"| 화장품 「유형 없는 위반」에 후보 (/{R[(D400, '—', SEEDS[0])]['cos_pending'][1]}) | {cp(D400, '—'):.1f} | "
              + " | ".join(f"{cp(D410, m):.1f}" for m in MODES) + " |")

    angles = sorted({angle[i] for i in fids})
    md += ["", "## 사실 전제 dev — 각도별 후보 (시드 평균 · 참고)", "", "| 각도 | 행 | D4-00 | D4-04 (가) | D4-10 (가) 품목 | D4-10 (나) 모름 |", "|---|---:|---:|---:|---:|---:|"]
    fa = lambda model, mode, g: statistics.mean(sum(1 for i in R[(model, mode, s)]["fact_ids"] if angle[i] == g) for s in SEEDS)
    for g in angles:
        md.append(f"| {g} | {sum(1 for i in fids if angle[i] == g)} | {fa(D400, '—', g):.1f} | {fa(D404, '품목', g):.1f} | "
                  + " | ".join(f"{fa(D410, m, g):.1f}" for m in MODES) + " |")

    best = max(SEEDS, key=lambda s: R[(D410, "품목", s)]["prauc6"])
    md += ["", f"## 배포 시드 후보 (D-324 결정 3 · (가) 6종 PR-AUC 최고) — 시드 {best}", "", "| 유형 | 문턱 (가) 품목 | 문턱 (나) 모름 |", "|---|---:|---:|"]
    md += [f"| {x} | {TH[(D410, '품목', best)][x]:g} | {TH[(D410, '모름', best)][x]:g} |" for x in C]
    md += ["| 기능성화장품_오인 | 1.01 | 1.01 |", "",
           "측정 불가 세 유형(후기 · 부당 비교 · 비방)은 D-324 결정 2 로 그 판의 F1 최대 임시값이다(D-331 결정 6 은 카드 17 의 값 — 새 판에 무엇을 쓸지는 팀장).",
           "", "🚨 dev 다 — 같은 dev 로 문턱을 고르고 잰다. 학습 문구와 측정 문구가 같은 생성기다(D-325 맥락 4) · 사실 전제 dev 는 제품 15개다."]
    out = "\n".join(md) + "\n"
    print("\n" + out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(out)
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
