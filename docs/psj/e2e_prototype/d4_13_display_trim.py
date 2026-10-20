"""D4-13 표시후보 — 탐지 문턱은 그대로 두고 화면에 띄우는 유형 후보만 줄인다 (박수진 · 2026-10-15 · 학습 없음)

후보 C = {t : p_t ≥ τ_t (D-324)} · 표시 D = {t ∈ C : p_t ≥ r × max_C p} (r = 1.0 이면 한 개). 가장 높은 유형은 늘 남는다.
기준은 D4 실험기록 「D4-13」 에 먼저 적었다 — 입력마다 시드 평균 「하나라도 맞음」 하락 2.0%p 이내에서 「전부 정답」 최대.

  uv run python docs\\psj\\e2e_prototype\\d4_13_display_trim.py --dir <D4-00 CSV> --d10-dir <D4-10 CSV> [--graph-json build/eval/psj_dev_d410.json] --out-md docs\\psj\\reports\\D4-13_표시후보_dev_YYYYMMDD.md
  `--self-test` — R0 의 후보가 선 위반 행 수가 D4-10 기록의 위반 탐지(464.7 · 479.3)와 같은지 본다
🔴 dev 전용 (D-175). 건수만 적는다 (D-249).
"""
import argparse
import json
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_10_fact_train import D410, MODES

SEEDS = ca.SEEDS
RS = [None, 0.9, 0.8, 0.7, 0.6, 0.5, 1.0]          # None = R0 (줄이지 않음)
LIM, GOAL = 0.020, 0.10
SELF_DET = {"품목": 464.7, "모름": 479.3}


def trim(cands, r, score):
    if r is None or not cands:
        return set(cands)
    top = max(score[t] for t in cands)
    if r == 1.0:
        return {max(cands, key=lambda t: score[t])}
    return {t for t in cands if score[t] >= r * top}


def measure(rows_c, r, norm):
    """rows_c = [(정답 집합, {유형: p}, {유형: τ})] — 후보가 선 위반 행만."""
    anyok = allok = n = 0
    for truth, P, th in rows_c:
        score = {t: (P[t] / th[t]) if norm else P[t] for t in P}
        d = trim(set(P), r, score)
        anyok += bool(d & truth)
        allok += d <= truth
        n += len(d)
    m = len(rows_c)
    return {"any": anyok / m, "all": allok / m, "k": n / m, "rows": m}


def lab(r):
    return "R0 줄이지 않음" if r is None else ("한 개(top-1)" if r == 1.0 else f"r {r:.1f}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--d10-dir", required=True)
    ap.add_argument("--graph-json", default=None)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    dev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(C)}
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]

    R = {}
    for m in MODES:
        for s in SEEDS:
            P = sd.read_probs(os.path.join(a.d10_dir, f"{D410}_{m}_seed{s}_dev행별확률.csv"), dev)
            th, _ = ca.d324_thresholds(Y, P, target)
            rows_c = []
            for k in sc:
                cand = {x: P[k][i] for i, x in enumerate(C) if P[k][i] >= th[x]}
                if cand:
                    rows_c.append(({x for x in dev[k]["target"] if x in C}, cand, th))
            for norm in (False, True):
                for r in RS:
                    R[(m, s, norm, r)] = measure(rows_c, r, norm)
    mn = lambda m, norm, r, key: statistics.mean(R[(m, s, norm, r)][key] for s in SEEDS)
    if a.self_test:
        ok = True
        for m in MODES:
            got = round(mn(m, False, None, "rows"), 1)
            print(f"  {m}: 후보가 선 위반 행 {got} · 기록 {SELF_DET[m]}")
            ok &= got == SELF_DET[m]
        if not ok:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    md = ["# D4-13 표시후보 — 탐지 문턱 그대로 · 표시 유형만 줄이기 (dev)", "",
          f"> golden `{gsha[:12]}` · dev `{mark}` · D4-10 · 시드 48 · 49 · 50 평균 · D-324 문턱 · 분모 = 후보가 선 유형 있는 위반 행 · 건수만", ""]
    pick = {}
    for m, title in MODES.items():
        base_any = mn(m, False, None, "any")
        md += [f"## 입력 {title} — 분모 {mn(m, False, None, 'rows'):.1f} 행", "",
               "| 규칙 | 하나라도 맞음 | 전부 정답 | 표시 유형 수 | 기준(하나라도 −2.0%p 이내) |", "|---|---:|---:|---:|---|"]
        best = None
        for r in RS:
            av, al, kk = mn(m, False, r, "any"), mn(m, False, r, "all"), mn(m, False, r, "k")
            okr = base_any - av <= LIM + 1e-12
            if r is not None and okr and (best is None or al > mn(m, False, best, "all") + 1e-12):
                best = r
            md.append(f"| {lab(r)} | {av * 100:.1f}% | {al * 100:.1f}% | {kk:.2f} | {'지킴' if okr else '넘음'} |")
        pick[m] = best
        gain = mn(m, False, best, "all") - mn(m, False, None, "all")
        md += ["", f"고른 규칙 — **{lab(best)}** · 전부 정답 {gain * 100:+.1f}%p (목표 +10%p {'충족' if gain >= GOAL - 1e-12 else '미달'}) · "
               f"하나라도 {(mn(m, False, best, 'any') - base_any) * 100:+.1f}%p", "",
               "참고 — 문턱으로 나눈 점수(p / τ)로 같은 규칙: " + " · ".join(
                   f"{lab(r)} {mn(m, True, r, 'any') * 100:.1f} / {mn(m, True, r, 'all') * 100:.1f}%" for r in RS if r is not None), ""]
    if a.graph_json:
        G = json.load(open(a.graph_json, encoding="utf-8"))["rows"]
        by_id = {r["id"]: r for r in dev}
        rows_c = []
        for g in G:
            r = by_id.get(g["id"])
            if r is None or r["bucket"] != "scored" or g.get("candidates") or not g.get("enc_conf"):
                continue                                          # 「인코더만」 — 사전 후보 없음 · 인코더 직접 후보 있음
            P = {t: v for t, v in g["enc_conf"].items() if t in C}
            if P:
                rows_c.append(({x for x in r["target"] if x in C}, P, {t: 1.0 for t in P}))
        md += ["## 참고 — 판정 그래프 「인코더만」 칸 위반 (박수진 PC · 배포 시드 48 · 무조건부 · enc_conf)", "",
               f"분모 {len(rows_c)} 행", "", "| 규칙 | 하나라도 맞음 | 전부 정답 | 표시 유형 수 |", "|---|---:|---:|---:|"]
        for r in RS:
            v = measure(rows_c, r, False)
            md.append(f"| {lab(r)} | {v['any'] * 100:.1f}% | {v['all'] * 100:.1f}% | {v['k']:.2f} |")
        md.append("")
    md += ["탐지 · 놓침 · 오판정(후보가 선 행)은 규칙과 무관하게 같다 — 가장 높은 유형은 늘 남는다.", "",
           "🚨 dev 다 — 같은 dev 로 D-324 문턱과 r 을 골랐다. 표시 규칙 채택은 팀장 판정이다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
