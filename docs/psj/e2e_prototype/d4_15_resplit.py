"""D4-15 재분할 재학습 — 확장 dev 판정 (박수진 · 2026-10-15 · D-347 · 확률만 읽는다)

D4-15 노트북(`copylane_encoder_D4-15_재분할학습_20261015.ipynb`)의 두 실험(D4-15-재분할학습 · D4-10재현-확장dev)과
D4-15a 노트북(`…_D4-15a_카드17기준선_확장dev_…`)이 다시 잰 카드 17 기준선 재현으로 **확장 dev 1,147행**(공통 749 + 재분할 398)에서
D-324 문턱(목표 재현율 = 확장 dev 의 기준선 재현 3 시드 평균)을 고르고 같은 채점으로 견준다.

  uv run python docs\\psj\\e2e_prototype\\d4_15_resplit.py --self-test --base-dir <D4-00 CSV> --dir <D4-10 CSV> --review-csv <검수판>
  uv run python docs\\psj\\e2e_prototype\\d4_15_resplit.py --base-dir <D4-15a CSV> --dir <D4-15 CSV> --review-csv <검수판> [--d400-dir <D4-00 CSV>] --out-md docs\\psj\\reports\\D4-15_재분할학습_dev_YYYYMMDD.md

  · 기준은 D4 실험기록 「D4-15」 에 먼저 적었다 (시드 평균 · 입력 (가) 품목 · (나) 모름 각각 · D4-10재현-확장dev 대비 · 참고 관문 — 채택은 팀장 측정)
  · `--self-test` — 공통 dev 749행만 · 기준선 = D4-00 폴더의 카드 17 기준선 재현 · 후보 = D4-10 CSV → D4-10 기록(위반 탐지 464.7 · 479.3 ·
    사실 전제 dev 0.7 · 4.7)이 나와야 한다 (채점 코드 확인)
  · `--d400-dir` — D4-15a 가 다시 학습한 기준선의 공통 dev 749행 확률을 카드 17 때 CSV 와 대조한다(시드별 6종 PR-AUC · 목표 재현율 차이)
🔴 dev 전용 (D-175) · 새 봉인 평가셋 1,141행은 읽지 않는다 (D-347). 집계표에는 건수만 적는다 (D-249).
"""
import argparse
import json
import os
import statistics
import sys

import card17_adopt as ca
import score_encoder_dev as sd
from d4_04_product_input import measure
from d4_10_fact_train import FACT, fact_dev_ids

sys.path.insert(0, sd.REPO)
from preprocess import encoder_resplit as rs  # noqa: E402 — 재분할 정본 (D-99)

SEEDS = ca.SEEDS
BASE = ca.BASE                                   # copylane-encoder-kcbert-v10-카드17-Baseline재현
D410 = "copylane-encoder-kcbert-D4-10-품목입력사실전제"
D415 = "copylane-encoder-kcbert-D4-15-재분할학습"
D410R = "copylane-encoder-kcbert-D4-10재현-확장dev"
MODES = {"품목": "(가) 품목", "모름": "(나) 모름"}
RESPLIT = {"train": (950, "e8f5d6d27e7a5cea"), "dev": (398, "cc2d8b7e42d57266")}
GATE = {"prauc": 0.02, "det": 0.025, "neg": 4, "syn": 5}
SELF = {"품목": (464.7, 0.7), "모름": (479.3, 4.7)}


def ext_dev(golden_path):
    """공통 dev 749(devsplit) + 재분할 dev 398 — 노트북과 같은 행 · 같은 표적 · 같은 갈래."""
    dev, gsha, mark = sd.load_dev(golden_path)
    rows = [json.loads(x) for x in open(golden_path, encoding="utf-8") if x.strip()]
    st = rs.stamp(rows)
    for k, (n, m) in RESPLIT.items():
        if (st[f"{k}_rows"], st[f"{k}_sha"]) != (n, m):
            raise SystemExit(f"🔴 재분할 {k} 가 D-347 과 다르다 — {st[f'{k}_rows']}행 · {st[f'{k}_sha']}")
    guide = rs.guide_dev_rows(rows)
    del rows
    for r in guide:
        r["target"] = sd.encoder_target(r)
        r["bucket"] = sd.bucket(r)
        r["reason"] = r.get("provenance") == "ftc_decisions_body" and r.get("구역") == "이유"
        r["guide"] = True
    for r in dev:
        r["guide"] = False
    assert not ({r["id"] for r in guide} & {r["id"] for r in dev})
    return dev, guide, gsha, mark


def base_probs(d, dev, guide):
    """기준선 재현 — 공통 dev CSV + 재분할 dev CSV 를 이어 붙인다."""
    out = {}
    for s in SEEDS:
        P = sd.read_probs(os.path.join(d, f"{BASE}_seed{s}_dev행별확률.csv"), dev)
        if guide:
            P = P + sd.read_probs(os.path.join(d, f"{BASE}_seed{s}_재분할dev행별확률.csv"), guide)
        out[s] = P
    return out


def targets(Y, PB, npos):
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    return {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}


def score(D, Y, target, run, mode, s, d, fids):
    P = sd.read_probs(os.path.join(d, f"{run}_{mode}_seed{s}_dev행별확률.csv"), D)
    th, src = ca.d324_thresholds(Y, P, target)
    spth = os.path.join(d, f"{run}_{mode}_seed{s}_합성정상_행별확률.csv")
    r = measure(D, P, th, spth)
    syn = ca.syn_counts(spth, th)
    import csv
    with open(spth, encoding="utf-8-sig", newline="") as fh:
        fact = [[float(row[f"p_{x}"]) for x in sd.CONF8] for row in csv.DictReader(fh) if row["id"] in fids]
    if len(fact) != len(fids):
        raise SystemExit(f"🔴 {os.path.basename(spth)} 에 사실 전제 dev {len(fact)}행뿐이다")
    r["fact"] = sum(1 for p in fact if any(p[i] >= th[x] for i, x in enumerate(sd.CONF8)))
    cand = [any(P[k][i] >= th[x] for i, x in enumerate(sd.CONF8)) for k in range(len(D))]
    for part, want in (("c", False), ("g", True)):
        idx = [k for k, row in enumerate(D) if row.get("guide", False) == want]
        r[f"det_{part}"] = sum(1 for k in idx if D[k]["bucket"] == "scored" and cand[k])
        r[f"sc_{part}"] = sum(1 for k in idx if D[k]["bucket"] == "scored")
        r[f"neg_{part}"] = sum(1 for k in idx if D[k]["bucket"] in ("D", "L") and cand[k])
        r[f"negn_{part}"] = sum(1 for k in idx if D[k]["bucket"] in ("D", "L"))
    r["th"], r["src"] = th, src
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", required=True, help="D4-15a CSV (기준선 재현 · 공통 + 재분할 dev) · --self-test 면 D4-00 CSV")
    ap.add_argument("--dir", required=True, help="D4-15 CSV · --self-test 면 D4-10 CSV")
    ap.add_argument("--review-csv", required=True)
    ap.add_argument("--d400-dir", default=None, help="카드 17 때 기준선 재현 CSV (D4-00 폴더) — 다시 학습한 기준선 대조")
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    dev, guide, gsha, mark = ext_dev(a.golden)
    if a.self_test:
        guide = []
    D = dev + guide
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in D]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(C)}
    fids, _ = fact_dev_ids(a.review_csv)
    PB = base_probs(a.base_dir, dev, guide)
    target = targets(Y, PB, npos)
    print(f"[INFO] golden {gsha[:12]} · dev {len(D)}행 (공통 {len(dev)} · 재분할 {len(guide)}) · 양성 {npos}")

    if a.self_test:
        ok = True
        for m in MODES:
            rr = [score(D, Y, target, D410, m, s, a.dir, fids) for s in SEEDS]
            got = (round(statistics.mean(r["det"] for r in rr), 1), round(statistics.mean(r["fact"] for r in rr), 1))
            print(f"  {m}: 위반 탐지 · 사실 전제 후보 {got} · 기록 {SELF[m]}")
            ok &= got == SELF[m]
        if not ok:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과 — 공통 dev 에서 D4-10 기록과 같다")
        return 0

    runs = {D415: "D4-15 재분할학습", D410R: "D4-10 재현 (같은 확장 dev)"}
    R = {(run, m, s): score(D, Y, target, run, m, s, a.dir, fids) for run in runs for m in MODES for s in SEEDS}
    mn = lambda run, m, k: statistics.mean(R[(run, m, s)][k] for s in SEEDS)
    sc, nn = R[(D415, "품목", SEEDS[0])]["scored"], R[(D415, "품목", SEEDS[0])]["neg_n"]
    scc, scg = R[(D415, "품목", SEEDS[0])]["sc_c"], R[(D415, "품목", SEEDS[0])]["sc_g"]
    ngc, ngg = R[(D415, "품목", SEEDS[0])]["negn_c"], R[(D415, "품목", SEEDS[0])]["negn_g"]

    md = ["# D4-15 재분할 재학습 — 확장 dev (D-347)", "",
          f"> golden `{gsha[:12]}` · 공통 dev `{mark}` 749 + 재분할 dev `{RESPLIT['dev'][1]}` 398 = 확장 dev {len(D)}행 · "
          f"D-324 문턱(목표 = 확장 dev 의 카드 17 기준선 재현 3 시드 평균 · 실험 · 입력 · 시드마다) · 시드 48 · 49 · 50 평균 · 인코더 단독 · 건수만", "",
          "## 목표 재현율 (확장 dev · 카드 17 기준선 재현 · D4-15a)", "",
          "| 유형 | 확장 dev 양성 | 목표 재현율 | 문턱 규칙 |", "|---|---:|---:|---|"]
    for x in C:
        md.append(f"| {x} | {npos[x]} | {target.get(x, float('nan')):.3f} | {'목표 재현율' if npos[x] >= ca.MEASURABLE_MIN else 'F1 최대 (양성 30 미만)'} |")
    if a.d400_dir:
        old = base_probs(a.d400_dir, dev, [])
        Y7 = Y[:len(dev)]
        n7 = {x: sum(y[i] for y in Y7) for i, x in enumerate(C)}
        t_old, t_new = targets(Y7, old, n7), targets(Y7, {s: PB[s][:len(dev)] for s in SEEDS}, n7)
        md += ["", "**다시 학습한 기준선 대조 (공통 dev 749)** — 6종 PR-AUC 시드별 카드 17 때 → 지금: " + " · ".join(
            f"{s} {sd.macro_prauc(Y7, old[s], 6):.4f} → {sd.macro_prauc(Y7, PB[s][:len(dev)], 6):.4f}" for s in SEEDS),
            "· 목표 재현율 차이(지금 − 그때): " + " · ".join(f"{x} {t_new[x] - t_old[x]:+.3f}" for x in t_old)]
    rows = [("6종 PR-AUC", "prauc6", ".4f"), (f"위반 탐지 (/{sc})", "det", ".1f"), (f"└ 공통 dev (/{scc})", "det_c", ".1f"),
            (f"└ 재분할 dev (/{scg})", "det_g", ".1f"), (f"정답 유형 적중 (/{sc})", "hit", ".1f"), (f"유형 오인 (/{sc})", "F1", ".1f"),
            ("놓침", "F2", ".1f"), (f"적법 원천(D · L) 오판정 (/{nn})", "neg", ".1f"), (f"└ 공통 dev (/{ngc})", "neg_c", ".1f"),
            (f"└ 재분할 dev (/{ngg})", "neg_g", ".1f"), ("검수 적법 정상 문구 후보 (/171)", "syn_flag", ".1f"), ("사실 전제 dev 후보 (/110)", "fact", ".1f")]
    md += ["", "## 지표 (시드 평균)", "", "| 지표 | " + " | ".join(f"{runs[r]} {MODES[m]}" for r in runs for m in MODES) + " |",
           "|---|" + "---:|" * (len(runs) * len(MODES))]
    for lab, k, f in rows:
        md.append(f"| {lab} | " + " | ".join(format(mn(r, m, k), f) for r in runs for m in MODES) + " |")
    md += ["", "## 유형별 재현율 (시드 평균)", "", "| 유형 | " + " | ".join(f"{runs[r]} {MODES[m]}" for r in runs for m in MODES) + " |",
           "|---|" + "---:|" * (len(runs) * len(MODES))]
    for x in C:
        vals = []
        for r in runs:
            for m in MODES:
                v = [R[(r, m, s)]["rec"][x] for s in SEEDS if R[(r, m, s)]["rec"][x] is not None]
                vals.append(f"{statistics.mean(v) * 100:.1f}%" if v else "—")
        md.append(f"| {x} (/{npos[x]}) | " + " | ".join(vals) + " |")

    md += ["", "## 등록 기준 — D4-10 재현(같은 확장 dev) 대비 · 참고 (채택은 팀장 측정)", "", "| 기준 | (가) 품목 | (나) 모름 |", "|---|---|---|"]
    allok = True
    for lab, fn in (("B 6종 PR-AUC −0.02 이내", lambda m: (mn(D415, m, "prauc6") - mn(D410R, m, "prauc6"), "{:+.4f}", lambda v: v >= -GATE["prauc"] - 1e-12)),
                    ("G1 위반 탐지 −2.5%p 이내", lambda m: ((mn(D415, m, "det") - mn(D410R, m, "det")) / sc * 100, "{:+.1f}%p", lambda v: v >= -GATE["det"] * 100 - 1e-9)),
                    ("G3 적법 원천(D · L) 오판정 +4행 이내", lambda m: (mn(D415, m, "neg") - mn(D410R, m, "neg"), "{:+.1f}행", lambda v: v <= GATE["neg"] + 1e-9)),
                    ("한도 검수 적법 정상 문구 후보 +5행 이내", lambda m: (mn(D415, m, "syn_flag") - mn(D410R, m, "syn_flag"), "{:+.1f}행", lambda v: v <= GATE["syn"] + 1e-9))):
        cells = []
        for m in MODES:
            v, f, ok = fn(m)
            cells.append(f"{f.format(v)} {'지킴' if ok(v) else '❌ 넘음'}")
            allok &= ok(v)
        md.append(f"| {lab} | " + " | ".join(cells) + " |")
    md += ["", f"**판정 — {'등록 기준 모두 지킴' if allok else '등록 기준 하나 이상 넘음'}** (참고 관문 · 채택 측정은 팀장)", ""]

    best = max(SEEDS, key=lambda s: R[(D415, "품목", s)]["prauc6"])
    md += [f"## 배포 시드 · 문턱 (D-324 결정 3 — (가) 6종 PR-AUC 최고 = 시드 {best})", "",
           "| 유형 | label_thresholds (모름) | label_thresholds_by_cat (품목) | 규칙 |", "|---|---:|---:|---|"]
    for x in C:
        md.append(f"| {x} | {R[(D415, '모름', best)]['th'][x]} | {R[(D415, '품목', best)]['th'][x]} | {'F1 최대 (확장 dev 양성 30 미만 · D-347)' if R[(D415, '품목', best)]['src'][x].startswith('F1') else R[(D415, '품목', best)]['src'][x]} |")
    md += ["", "🚨 dev 다 — 문턱 · 회차 · 시드를 같은 확장 dev 로 골랐다. 새 봉인 평가셋(1,141행)은 열지 않았다 (D-347 · D-175)."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
