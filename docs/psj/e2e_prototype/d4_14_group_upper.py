"""D4-14 호 묶음 표시 · 1 · 2호 경계 상한 — 유형을 묶어서 채점하면 얼마나 맞나 (박수진 · 2026-10-15 · 학습 없음)

D4-13 과 같은 후보 C(D-324 문턱) · 표시 D(R0 · r 0.7 · 한 개)를 묶음 g 로 바꿔 g(D) · g(정답) 을 비교한다.
기준 · 묶음 정의는 D4 실험기록 「D4-14」 에 먼저 적었다 (L0 유형 · L1 호 · L2 T3 상한 · L3 넓은 묶음).

  uv run python docs\\psj\\e2e_prototype\\d4_14_group_upper.py --dir <D4-00 CSV> --d10-dir <D4-10 CSV> [--graph-json build/eval/psj_dev_d410.json] --out-md docs\\psj\\reports\\D4-14_호묶음상한_dev_YYYYMMDD.md
  `--self-test` — L0 · R0 이 D4-13 R0(분모 464.7 · 479.3 · 하나라도 89.5 · 86.4 · 전부 69.5 · 63.5%)과 같은지 본다
🔴 dev 전용 (D-175). 건수만 적는다 (D-249).
"""
import argparse
import collections
import json
import os
import statistics

import card17_adopt as ca
import score_encoder_dev as sd
from d4_10_fact_train import D410, MODES
from d4_13_display_trim import trim

SEEDS = ca.SEEDS
RULES = [None, 0.7, 1.0]
CLAIM = ("거짓_과장", "소비자_기만", "후기_체험기_기만")
LEVELS = {
    "L0 유형": {},
    "L1 호(5호 묶음)": {"후기_체험기_기만": "8조①5호"},
    "L2 T3 상한(+ 거짓≡기만)": {t: "주장·기만" for t in CLAIM},
    "L3 넓은 묶음(참고)": {**{t: "1~3호 효능·품목" for t in ("질병_예방치료_표방", "의약품_오인", "건강기능식품_오인")},
                       **{t: "4~5호 주장·기만" for t in CLAIM},
                       **{t: "6~7호 다른 업체" for t in ("비방광고", "부당_비교광고")}},
}
LEVELS["L1 호(5호 묶음)"]["소비자_기만"] = "8조①5호"
SELF = {"품목": (464.7, 89.5, 69.5), "모름": (479.3, 86.4, 63.5)}


def g(m, ts):
    return {m.get(t, t) for t in ts}


def measure(rows_c, r, m):
    anyok = allok = n = 0
    for truth, P in rows_c:
        d = g(m, trim(set(P), r, P))
        tg = g(m, truth)
        anyok += bool(d & tg)
        allok += d <= tg
        n += len(d)
    k = len(rows_c)
    return {"any": anyok / k, "all": allok / k, "k": n / k, "rows": k}


def lab(r):
    return "R0" if r is None else ("한 개" if r == 1.0 else f"r {r:.1f}")


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

    R, miss = {}, {m: collections.Counter() for m in MODES}
    for m in MODES:
        for s in SEEDS:
            P = sd.read_probs(os.path.join(a.d10_dir, f"{D410}_{m}_seed{s}_dev행별확률.csv"), dev)
            th, _ = ca.d324_thresholds(Y, P, target)
            rows_c = []
            for k in sc:
                cand = {x: P[k][i] for i, x in enumerate(C) if P[k][i] >= th[x]}
                if cand:
                    truth = {x for x in dev[k]["target"] if x in C}
                    rows_c.append((truth, cand))
                    if not (set(cand) & truth):                     # L0 R0 에서 하나도 못 맞힌 행 — 정답 → 대표 후보
                        top = max(cand, key=cand.get)
                        for t in truth:
                            miss[m][(t, top)] += 1 / len(SEEDS)
            for lv, mp in LEVELS.items():
                for r in RULES:
                    R[(m, s, lv, r)] = measure(rows_c, r, mp)
    mn = lambda m, lv, r, key: statistics.mean(R[(m, s, lv, r)][key] for s in SEEDS)
    if a.self_test:
        ok = True
        for m in MODES:
            got = (round(mn(m, "L0 유형", None, "rows"), 1), round(mn(m, "L0 유형", None, "any") * 100, 1),
                   round(mn(m, "L0 유형", None, "all") * 100, 1))
            print(f"  {m}: {got} · D4-13 {SELF[m]}")
            ok &= got == SELF[m]
        if not ok:
            raise SystemExit("🔴 자기 검증 실패")
        print("[OK] 자기 검증 통과")
        return 0

    md = ["# D4-14 호 묶음 표시 · 1 · 2호 경계 상한 (dev)", "",
          f"> golden `{gsha[:12]}` · dev `{mark}` · D4-10 · 시드 48 · 49 · 50 평균 · D-324 문턱 · 분모 = 후보가 선 유형 있는 위반 행 · 건수만 · 학습 없음", "",
          "묶음 — L1 {소비자_기만 · 후기} · L2 L1 + 거짓_과장 · L3 {질병 · 의약품 · 건기식} / {거짓 · 기만 · 후기} / {비방 · 부당 비교}", ""]
    for m, title in MODES.items():
        md += [f"## 입력 {title} — 분모 {mn(m, 'L0 유형', None, 'rows'):.1f} 행", "",
               "| 묶음 | R0 하나라도 · 전부 · 수 | r 0.7 하나라도 · 전부 | 한 개 하나라도 · 전부 |", "|---|---|---|---|"]
        for lv in LEVELS:
            c = [f"{mn(m, lv, r, 'any') * 100:.1f} · {mn(m, lv, r, 'all') * 100:.1f}%" for r in RULES]
            c[0] += f" · {mn(m, lv, None, 'k'):.2f}"
            md.append(f"| {lv} | " + " | ".join(c) + " |")
        d3 = mn(m, "L2 T3 상한(+ 거짓≡기만)", None, "all") - mn(m, "L1 호(5호 묶음)", None, "all")
        d2 = mn(m, "L3 넓은 묶음(참고)", None, "all") - mn(m, "L0 유형", None, "all")
        v3 = "들일 값 없음(+5%p 미만)" if d3 < 0.05 - 1e-12 else ("제안 근거(+10%p 이상)" if d3 >= 0.10 - 1e-12 else "보류")
        v2 = "제안 근거(+10%p 이상)" if d2 >= 0.10 - 1e-12 else "근거 부족"
        md += ["", f"읽는 규칙(R0) — **T3** L2 − L1 전부 정답 {d3 * 100:+.1f}%p → {v3} · **T2** L3 − L0 전부 정답 {d2 * 100:+.1f}%p → {v2}", "",
               "L0 · R0 에서 하나도 못 맞힌 위반 — 정답 → 대표 후보 상위 (시드 평균 행)", ""]
        tot = sum(miss[m].values())
        for (t, p), n in miss[m].most_common(8):
            md.append(f"- {t} → {p} · {n:.1f} ({n / tot:.0%})")
        md.append("")
    if a.graph_json:
        G = json.load(open(a.graph_json, encoding="utf-8"))["rows"]
        by_id = {r["id"]: r for r in dev}
        rows_c = []
        for gg in G:
            r = by_id.get(gg["id"])
            if r is None or r["bucket"] != "scored" or gg.get("candidates") or not gg.get("enc_conf"):
                continue
            P = {t: v for t, v in gg["enc_conf"].items() if t in C}
            if P:
                rows_c.append(({x for x in r["target"] if x in C}, P))
        md += ["## 참고 — 판정 그래프 「인코더만」 칸 위반 (박수진 PC · 배포 시드 48 · 무조건부 · enc_conf)", "",
               f"분모 {len(rows_c)} 행", "", "| 묶음 | R0 | r 0.7 | 한 개 |", "|---|---|---|---|"]
        for lv, mp in LEVELS.items():
            md.append(f"| {lv} | " + " | ".join(f"{measure(rows_c, r, mp)['any'] * 100:.1f} · {measure(rows_c, r, mp)['all'] * 100:.1f}%" for r in RULES) + " |")
        md.append("")
    md += ["칸 = 하나라도 맞음 · 전부 정답(· 표시 묶음 수). 탐지 · 놓침 · 오판정은 묶음과 무관하게 같다.", "",
           "🚨 L2 는 상한이다 — 경계를 정리해 다시 라벨 · 학습해도 모델이 그만큼 맞힌다는 뜻이 아니다. dev 다 — 라벨 · 표시 규칙은 팀장 판정이다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
