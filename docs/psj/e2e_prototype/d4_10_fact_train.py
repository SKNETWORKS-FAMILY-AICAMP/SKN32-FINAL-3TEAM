"""D4-10 사실전제학습 — 검수 「적법(사실 전제)」 문구를 학습 음성에 더한 판의 판정 (박수진 · 2026-10-13 · 학습 결과 판정 · 확률만 읽는다)

D4-10 노트북(`copylane_encoder_D4-10_사실전제학습_20261013.ipynb`)이 낸 두 판(D4-00 재현 · 사실전제음성) · 시드 48 · 49 · 50 의
행별 확률로 D-324 문턱을 고르고 D4 실험기록 「D4-10」 에 먼저 적은 관문 · 한도 · 목표로 판정한다.

  uv run python docs\\psj\\e2e_prototype\\d4_10_fact_train.py --dir <D4-00 행별 확률 폴더> --d10-dir <D4-10 행별 확률 폴더> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_10_fact_train.py --dir <D4-00 행별 확률 폴더> --d10-dir <D4-10 행별 확률 폴더> --out-md docs\\psj\\reports\\D4-10_사실전제학습_dev_YYYYMMDD.md
      (--review-csv <권소라 10-11 검수판> 을 주면 사실 전제 dev 의 각도별 후보도 적는다 · 문구는 읽지 않는다)

  · 문턱 — 판 · 시드마다 D-324 (card17_adopt.d324_thresholds · 목표 = 카드 17 기준선 재현 3 시드 평균 · --dir 에서 읽는다)
  · 관문 (시드 평균 · D4-00 재현 대비) — B 6종 PR-AUC −0.02 이내 · G1 위반 탐지(유형 무관) −2.5%p 이내 · G3 음성(D · L) 오판정 +4행 이내
  · 한도 ① 검수 적법 정상 문구 측정용 171행의 후보 +5행 이내
         ② 건강기능식품_오인 · 의약품_오인 · 질병_예방치료_표방 — 같은 시드 D4-00 재현의 D-324 문턱을 두 판에 걸어 「후보가 선 정답 행」이 3행 넘게 줄지 않는다
  · 목표 — 사실 전제 dev(갈래 「참고-적법(사실 전제)」 110행)의 후보가 D4-00 재현의 0.5배 이하
  · 판정 — 탐색 통과 = 관문 · 한도를 지키고 목표를 채운다 (채택 아님 · 팀장 보고)
  · `--self-test` — 두 판 자리에 카드 17 채택 판(D4-00) 확률을 넣는다. 기준 수(위반 탐지 473.3 · D · L 17.0 · 정상 문구 후보 5.0 ·
    사실 전제 후보 56.3/321)와 같고 차이가 모두 0 이어야 한다
🔴 dev 전용 (D-175). 집계표에는 건수만 적는다 (D-249).
"""
import argparse
import csv
import os
import statistics
from collections import defaultdict

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
GOLDEN = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "derived", "golden", "golden.jsonl"))
BASE10 = "copylane-encoder-kcbert-D4-10-D4-00재현"
CAND10 = "copylane-encoder-kcbert-D4-10-사실전제음성"
NAMES = {BASE10: "D4-00 재현", CAND10: "사실전제음성"}
FACT = "참고-적법(사실 전제)"
OK = "합성정상dev"
LIM2 = ["건강기능식품_오인", "의약품_오인", "질병_예방치료_표방"]
GATE = {"B": 0.02, "G1": 0.025, "G3": 4}
LIM_SYN, LIM_POS, GOAL = 5, 3, 0.5
SELF = {"det": 473.3, "neg": 17.0, "syn": 5.0, "fact": 56.3}


def read_syn(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({"id": r["id"], "cat": r["품목"], "br": r["갈래"], "p": [float(r[f"p_{x}"]) for x in sd.CONF8]})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 카드 17 행별 확률 폴더 (D-324 목표 재현율 · 자기 검증)")
    ap.add_argument("--d10-dir", required=True, help="D4-10 노트북의 행별 확률 폴더 (D4-10_csv.zip 을 푼 곳)")
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--review-csv", default=None, help="(선택) 권소라 10-11 검수판 — 사실 전제 dev 의 각도별 후보")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    dev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(C)}
    cond = [r.get("조건") for r in dev]
    typed = [k for k in range(len(dev)) if any(Y[k][i] for i in range(len(C)))]
    untyped = [k for k, c in enumerate(cond) if c in ("A", "B", "C") and k not in set(typed)]
    viol = sorted(set(typed) | set(untyped))
    neg = [k for k, c in enumerate(cond) if c in ("D", "L")]
    print(f"[INFO] golden {gsha[:12]} · dev {len(dev)}행 · 지문 {mark}")

    # 목표 재현율 — 카드 17 기준선 재현 3 시드 평균 (D4 의 다른 실험과 같다)
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    def path(tag, s, kind):
        if a.self_test:
            return os.path.join(a.dir, f"{ca.CAND}_seed{s}_{kind}.csv")
        return os.path.join(a.d10_dir, f"{tag}_seed{s}_{kind}.csv")

    R = {}
    for tag in (BASE10, CAND10):
        for s in SEEDS:
            P = sd.read_probs(path(tag, s, "dev행별확률"), dev)
            th, src = ca.d324_thresholds(Y, P, target)
            R[(tag, s)] = {"P": P, "th": th, "e": sd.evaluate(dev, P, th), "syn": read_syn(path(tag, s, "합성정상_행별확률"))}

    def flagged(p, th):
        return any(p[i] >= th[x] for i, x in enumerate(C))

    def summ(tag, s, th=None):
        r = R[(tag, s)]
        th = th or r["th"]
        fl = [flagged(p, th) for p in r["P"]]
        by = defaultdict(lambda: [0, 0])
        for row in r["syn"]:
            by[row["br"]][0] += 1
            by[row["br"]][1] += flagged(row["p"], th)
        tp = sum(1 for k in viol if fl[k])
        fp = sum(1 for k in neg if fl[k])
        return {"prauc6": r["e"]["prauc6"], "det": r["e"]["det"], "hit": r["e"]["hit"], "neg": r["e"]["neg"][0],
                "syn": by[OK][1], "syn_n": by[OK][0], "fact": by[FACT][1], "fact_n": by[FACT][0],
                "prec": tp / (tp + fp) if tp + fp else float("nan"),
                "rec": {x: r["e"]["types"][x]["tp"] / npos[x] for x in C if npos[x]},
                "pos": {x: sum(1 for k in range(len(dev)) if Y[k][C.index(x)] and r["P"][k][C.index(x)] >= th[x]) for x in LIM2},
                "fact_cat": {c: sum(1 for row in r["syn"] if row["br"] == FACT and row["cat"] == c and flagged(row["p"], th)) for c in ("식품", "건기식", "화장품")},
                "fact_ids": {row["id"] for row in r["syn"] if row["br"] == FACT and flagged(row["p"], th)}}

    S = {(t, s): summ(t, s) for t in (BASE10, CAND10) for s in SEEDS}
    S2 = {s: summ(CAND10, s, R[(BASE10, s)]["th"]) for s in SEEDS}       # 한도 ② — D4-00 재현의 문턱을 후보에 건다
    mn = lambda t, k: statistics.mean(S[(t, s)][k] for s in SEEDS)
    per = lambda t, k, f="%.4f": " · ".join(f % S[(t, s)][k] for s in SEEDS)
    sc, nn = R[(BASE10, SEEDS[0])]["e"]["scored"], len(neg)
    b, c = BASE10, CAND10

    if a.self_test:
        got = {"det": round(mn(b, "det"), 1), "neg": round(mn(b, "neg"), 1), "syn": round(mn(b, "syn"), 1), "fact": round(mn(b, "fact"), 1)}
        diff = {k: mn(c, k) - mn(b, k) for k in ("prauc6", "det", "neg", "syn", "fact")}
        diff.update({f"pos_{x}": statistics.mean(S2[s]["pos"][x] - S[(b, s)]["pos"][x] for s in SEEDS) for x in LIM2})
        bad = [k for k in SELF if SELF[k] != got[k]] + [k for k, v in diff.items() if abs(v) > 1e-12]
        for k in SELF:
            print(f"  {'❌ ' if k in bad else 'OK '} {k}: 기록 {SELF[k]} · 지금 {got[k]}")
        print("  차이 (0 이어야 한다): " + " · ".join(f"{k} {v:+g}" for k, v in diff.items()))
        if bad:
            raise SystemExit(f"🔴 자기 검증 실패 — {bad}")
        print("[OK] 자기 검증 통과 — D4-00 기준 수와 같고 두 판 차이가 0 이다")
        return 0

    fn_ = S[(b, SEEDS[0])]["fact_n"]
    if fn_ != 110 or S[(b, SEEDS[0])]["syn_n"] != 171:
        raise SystemExit(f"🔴 갈래 행 수가 등록과 다르다 — 사실 전제 dev {fn_} (기대 110) · 정상 문구 {S[(b, SEEDS[0])]['syn_n']} (기대 171)")

    d_pr, d_det, d_neg = mn(c, "prauc6") - mn(b, "prauc6"), (mn(c, "det") - mn(b, "det")) / sc, mn(c, "neg") - mn(b, "neg")
    d_syn = mn(c, "syn") - mn(b, "syn")
    d_pos = {x: statistics.mean(S2[s]["pos"][x] - S[(b, s)]["pos"][x] for s in SEEDS) for x in LIM2}
    okB, okG1, okG3 = d_pr >= -GATE["B"], d_det >= -GATE["G1"] - 1e-12, d_neg <= GATE["G3"] + 1e-9
    ok1 = d_syn <= LIM_SYN + 1e-9
    ok2 = all(v >= -LIM_POS - 1e-9 for v in d_pos.values())
    bf, cf = mn(b, "fact"), mn(c, "fact")
    goal = bf > 0 and cf <= GOAL * bf + 1e-9
    passed = okB and okG1 and okG3 and ok1 and ok2 and goal
    yn = lambda ok: "지킴" if ok else "**넘음**"

    md = ["# D4-10 사실전제학습 — 검수 「적법(사실 전제)」 문구를 학습 음성에 더하기 (dev · 판정)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · 판 · 시드마다 D-324 문턱 "
          "(목표 = 카드 17 기준선 재현 평균) · 기준선 = 같은 노트북 · 같은 시드의 D4-00 재현 · 인코더 단독 · 건수만 적는다", "",
          "## 공통 dev · 정상 문구 · 사실 전제 dev", "",
          f"| 지표 | {NAMES[b]} | {NAMES[c]} |", "|---|---:|---:|",
          f"| 6종 PR-AUC | {mn(b, 'prauc6'):.4f} ({per(b, 'prauc6')}) | {mn(c, 'prauc6'):.4f} ({per(c, 'prauc6')}) |",
          f"| 위반 탐지 · 유형 무관 (/{sc}) | {mn(b, 'det'):.1f} ({per(b, 'det', '%g')}) | {mn(c, 'det'):.1f} ({per(c, 'det', '%g')}) |",
          f"| 정답 유형 적중 (/{sc}) | {mn(b, 'hit'):.1f} | {mn(c, 'hit'):.1f} |",
          f"| 음성(D · L) 오판정 (/{nn}) | {mn(b, 'neg'):.1f} ({per(b, 'neg', '%g')}) | {mn(c, 'neg'):.1f} ({per(c, 'neg', '%g')}) |",
          f"| 검수 적법 정상 문구 — 후보 (/171) | {mn(b, 'syn'):.1f} ({per(b, 'syn', '%g')}) | {mn(c, 'syn'):.1f} ({per(c, 'syn', '%g')}) |",
          f"| **사실 전제 dev — 후보 (/{fn_})** | **{bf:.1f}** ({per(b, 'fact', '%g')}) | **{cf:.1f}** ({per(c, 'fact', '%g')}) |",
          f"| 위반 정밀도 (D · L 기준 · 참고) | {mn(b, 'prec') * 100:.1f}% | {mn(c, 'prec') * 100:.1f}% |"]
    for br in ("참고-조건부", "애매"):
        n = sum(1 for row in R[(b, SEEDS[0])]["syn"] if row["br"] == br)
        if n:
            f = lambda t: statistics.mean(sum(1 for row in R[(t, s)]["syn"] if row["br"] == br and flagged(row["p"], R[(t, s)]["th"])) for s in SEEDS)
            md.append(f"| 참고 · {br} — 후보 (/{n}) | {f(b):.1f} | {f(c):.1f} |")
    md += ["", "## 관문 · 한도 · 목표 (D4 실험기록 「D4-10」 에 먼저 적은 것 · 시드 평균 · D4-00 재현 대비)", "",
           "| 항목 | 기준 | 차이 | 결과 |", "|---|---|---:|---|",
           f"| B 6종 PR-AUC | −0.02 이내 | {d_pr:+.4f} | {yn(okB)} |",
           f"| G1 위반 탐지 (유형 무관) | −2.5%p 이내 | {d_det * 100:+.1f}%p | {yn(okG1)} |",
           f"| G3 음성(D · L) 오판정 | +4행 이내 | {d_neg:+.1f} | {yn(okG3)} |",
           f"| 한도 ① 검수 적법 정상 문구 후보 | +5행 이내 | {d_syn:+.1f} | {yn(ok1)} |"]
    for x in LIM2:
        md.append(f"| 한도 ② {x} — 후보가 선 정답 행 (D4-00 재현 문턱 · /{npos[x]}) | 3행 넘게 줄지 않음 | "
                  f"{statistics.mean(S[(b, s)]['pos'][x] for s in SEEDS):.1f} → {statistics.mean(S2[s]['pos'][x] for s in SEEDS):.1f} ({d_pos[x]:+.1f}) | "
                  f"{yn(d_pos[x] >= -LIM_POS - 1e-9)} |")
    md += [f"| 목표 — 사실 전제 dev 후보 | D4-00 재현의 0.5배 이하 | {cf:.1f} 대 {bf:.1f} ({cf / bf:.2f}배) | {'충족' if goal else '**미달**'} |" if bf else
           "| 목표 — 사실 전제 dev 후보 | D4-00 재현의 0.5배 이하 | D4-00 재현 0 | 잴 수 없음 |",
           "", f"**판정 — {'탐색 통과 (관문 · 한도를 지키고 목표를 채움) → 근거를 들고 팀장 보고 · 채택 아님' if passed else '탐색 통과 아님'}**", "",
           "## 유형별 재현율 (시드 평균 · D-324 문턱 · 참고)", "", f"| 유형 | dev 양성 | {NAMES[b]} | {NAMES[c]} |", "|---|---:|---:|---:|"]
    for x in C:
        if npos[x]:
            md.append(f"| {x}{'' if npos[x] >= ca.MEASURABLE_MIN else ' (측정 불가)'} | {npos[x]} | "
                      f"{statistics.mean(S[(b, s)]['rec'][x] for s in SEEDS) * 100:.1f}% | {statistics.mean(S[(c, s)]['rec'][x] for s in SEEDS) * 100:.1f}% |")
    md += ["", "## 사실 전제 dev — 품목별 후보 (시드 평균 · 참고)", "", f"| 품목 | 행 | {NAMES[b]} | {NAMES[c]} |", "|---|---:|---:|---:|"]
    for cat in ("식품", "건기식", "화장품"):
        n = sum(1 for row in R[(b, SEEDS[0])]["syn"] if row["br"] == FACT and row["cat"] == cat)
        md.append(f"| {cat} | {n} | {statistics.mean(S[(b, s)]['fact_cat'][cat] for s in SEEDS):.1f} | {statistics.mean(S[(c, s)]['fact_cat'][cat] for s in SEEDS):.1f} |")
    if a.review_csv:
        with open(a.review_csv, encoding="utf-8-sig", newline="") as fh:
            angle = {"syn:" + r["id"]: r["각도"] for r in csv.DictReader(fh)}
        fids = {row["id"] for row in R[(b, SEEDS[0])]["syn"] if row["br"] == FACT}
        angles = sorted({angle[i] for i in fids})
        md += ["", "## 사실 전제 dev — 각도별 후보 (시드 평균 · 참고)", "", f"| 각도 | 행 | {NAMES[b]} | {NAMES[c]} |", "|---|---:|---:|---:|"]
        for g in angles:
            n = sum(1 for i in fids if angle[i] == g)
            md.append(f"| {g} | {n} | " + " | ".join(f"{statistics.mean(sum(1 for i in S[(t, s)]['fact_ids'] if angle[i] == g) for s in SEEDS):.1f}" for t in (b, c)) + " |")
    md += ["", "판정 로직(사전 + 인코더 층)의 정상 문구 · 사실 전제 통과는 `card17_judge.py` 로 따로 잰다(참고).",
           "", "🚨 dev 다 — 같은 dev 로 문턱을 고르고 잰다. 학습 문구와 측정 문구가 같은 생성기다(D-325 맥락 4) · 사실 전제 dev 는 제품 15개다."]
    print("\n" + "\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
