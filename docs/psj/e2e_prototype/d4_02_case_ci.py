"""D4-02 보충 ② — 유형별 재현율의 95% 구간을 사건(같은 원문 묶음) 단위로 낸다 (박수진 · 2026-10-13 · 진단 · 학습 없음 · 판정 없음)

D4 의 유형별 재현율은 행을 서로 독립으로 보고 낸 수다. 같은 의결서 · 같은 사례의 문장은 같이 맞거나 같이 틀린다
(D4-02 보충 — 소비자_기만 놓침 27행이 의결서 8건에서 나왔고 한 건이 12행). 그래서 행 단위 구간은 실제보다 좁다.
같은 원문 묶음(`score_encoder_dev.group_key` — dev 를 뗄 때 쓴 묶음)을 통째로 다시 뽑아 구간을 낸다.

  uv run python docs\\psj\\e2e_prototype\\d4_02_case_ci.py --dir <D4-00 행별 확률 폴더> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_02_case_ci.py --dir <D4-00 행별 확률 폴더> --out-md docs\\psj\\reports\\D4-02_사건단위구간_dev_YYYYMMDD.md

  · 묻는 것 (결과 전에 적었다 · 판정 없음)
      Q1 유형별 재현율의 95% 구간이 행 단위와 사건 단위에서 얼마나 다른가 (폭의 배율)
      Q2 유형마다 정답이 몇 사건에서 오나 · 가장 큰 사건이 정답 행의 몇 %인가
      Q3 행 단위 「유형 적중」 · 「위반 탐지(유형 무관)」의 구간은 어떤가
  · 재현율 — D4-00 시드 48 · 49 · 50 · D-324 문턱(card17_adopt.py 와 같은 규칙 · 시드마다) · 시드 평균. 부트스트랩의 매 회차에서
    같은 묶음 표본으로 시드 셋의 재현율을 내고 평균한다. 백분위 2.5 · 97.5 를 구간으로 쓴다
  · `--self-test` — 점추정이 D4 실험기록 「D4-00 기준 수」의 유형별 재현율과 같은지 본다 (부트스트랩은 돌리지 않는다)
🔴 dev 전용 (D-175). 집계표에는 건수만 적는다 — 행 · 사건 id 는 쓰지 않는다 (D-249).
"""
import argparse
import os
import random
import statistics
from collections import defaultdict

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
GOLDEN = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "derived", "golden", "golden.jsonl"))
D400 = ca.CAND
B_DEFAULT = 2000
RNG_SEED = 20261013
#: `--self-test` 대조 값 — D4 실험기록 「D4-00 · 기준 수 — 인코더」 유형별 재현율(%, 소수 한 자리)
SELF = {"질병_예방치료_표방": 86.7, "건강기능식품_오인": 69.4, "의약품_오인": 56.8, "거짓_과장": 88.3, "소비자_기만": 58.8,
        "후기_체험기_기만": 83.3, "부당_비교광고": 26.7, "비방광고": 44.0}


def pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 기준선 재현(카드 17) 행별 확률 폴더")
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--b", type=int, default=B_DEFAULT, help="부트스트랩 회차")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    sdev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in sdev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark}")

    # D-324 문턱 — d4_04_judge.py 와 같다 (재현율 목표 = 기준선 재현의 시드 평균)
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), sdev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}
    P, TH = {}, {}
    for s in SEEDS:
        P[s] = sd.read_probs(os.path.join(a.dir, f"{D400}_seed{s}_dev행별확률.csv"), sdev)
        TH[s], _ = ca.d324_thresholds(Y, P[s], target)

    types = [x for x in sd.CONF8 if npos[x]]
    point = {x: statistics.mean(ca.recall(Y, P[s], sd.CONF8.index(x), TH[s][x]) for s in SEEDS) for x in types}
    if a.self_test:
        bad = [x for x in types if round(point[x] * 100, 1) != SELF.get(x)]
        for x in types:
            print(f"  {'❌ ' if x in bad else 'OK '} {x}: 기록 {SELF.get(x)} · 지금 {point[x] * 100:.1f}")
        if bad:
            raise SystemExit("🔴 자기 검증 실패 — 점추정이 D4-00 기준 수와 다르다")
        print("[OK] 자기 검증 통과 — 점추정 = D4-00 기준 수")
        return 0

    # 행마다 · 시드마다: 유형별 (정답, 맞음) · 위반 행이면 (유형 적중, 유형 무관 탐지)
    def row_stat(k, s):
        y, p, th = Y[k], P[s][k], TH[s]
        flag = {x for i, x in enumerate(sd.CONF8) if p[i] >= th[x]}
        gold = {x for i, x in enumerate(sd.CONF8) if y[i]}
        return {"type": {x: (1, int(x in flag)) for x in gold}, "pos": int(bool(gold)),
                "hit": int(bool(gold & flag)), "any": int(bool(gold) and bool(flag))}

    stats = [[row_stat(k, s) for s in SEEDS] for k in range(len(sdev))]
    groups = defaultdict(list)
    for k, r in enumerate(sdev):
        groups[sd.group_key(r["id"])].append(k)
    gkeys = sorted(groups)

    def unit_sum(idx):
        """행 묶음 → 시드마다 합계."""
        out = []
        for j in range(len(SEEDS)):
            t = defaultdict(lambda: [0, 0])
            pos = hit = anyf = 0
            for k in idx:
                st = stats[k][j]
                for x, (n, h) in st["type"].items():
                    t[x][0] += n
                    t[x][1] += h
                pos += st["pos"]
                hit += st["hit"]
                anyf += st["any"]
            out.append({"type": dict(t), "pos": pos, "hit": hit, "any": anyf})
        return out

    G = {g: unit_sum(groups[g]) for g in gkeys}
    R = [unit_sum([k]) for k in range(len(sdev))]

    def boot(units, b):
        rng = random.Random(RNG_SEED)
        res = defaultdict(list)
        for _ in range(b):
            pick = [units[rng.randrange(len(units))] for _ in units]
            vals = defaultdict(list)
            for j in range(len(SEEDS)):
                tn = defaultdict(int)
                th_ = defaultdict(int)
                pos = hit = anyf = 0
                for u in pick:
                    uj = u[j]
                    for x, (n, h) in uj["type"].items():
                        tn[x] += n
                        th_[x] += h
                    pos += uj["pos"]
                    hit += uj["hit"]
                    anyf += uj["any"]
                for x in types:
                    if tn[x]:
                        vals[x].append(th_[x] / tn[x])
                if pos:
                    vals["__hit"].append(hit / pos)
                    vals["__any"].append(anyf / pos)
            for x, v in vals.items():
                if len(v) == len(SEEDS):
                    res[x].append(statistics.mean(v))
        return {x: (pct(v, 0.025), pct(v, 0.975), len(v)) for x, v in res.items()}

    print(f"[INFO] 부트스트랩 {a.b}회 — 사건 단위({len(gkeys)} 묶음) · 행 단위({len(sdev)}행)")
    ci_g = boot([G[g] for g in gkeys], a.b)
    ci_r = boot(R, a.b)

    def gstat(x):
        i = sd.CONF8.index(x)
        per = defaultdict(int)
        for k, r in enumerate(sdev):
            if Y[k][i]:
                per[sd.group_key(r["id"])] += 1
        return len(per), max(per.values()) / npos[x]

    hit_pt = statistics.mean(sum(st[j]["hit"] for st in stats) / sum(st[j]["pos"] for st in stats) for j in range(len(SEEDS)))
    any_pt = statistics.mean(sum(st[j]["any"] for st in stats) / sum(st[j]["pos"] for st in stats) for j in range(len(SEEDS)))
    npos_row = sum(stats[k][0]["pos"] for k in range(len(sdev)))

    def row(lab, n, ncase, big, pt, key):
        lr, hr, _ = ci_r[key]
        lg, hg, used = ci_g[key]
        w = (hg - lg) / (hr - lr) if hr > lr else float("nan")
        return (f"| {lab} | {n} | {ncase} | {big} | {pt * 100:.1f}% | {lr * 100:.1f} ~ {hr * 100:.1f} | "
                f"{lg * 100:.1f} ~ {hg * 100:.1f} | ×{w:.1f} |" + ("" if used == a.b else f" (정답이 빠진 회차 {a.b - used} 제외)"))

    md = ["# D4-02 보충 ② — 유형별 재현율의 사건 단위 95% 구간 (dev · 진단)", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · D4-00(카드 17 채택 판) 시드 {' · '.join(map(str, SEEDS))} · D-324 문턱 · "
          f"인코더 단독(판정 로직 아님) · 부트스트랩 {a.b}회 · 난수 {RNG_SEED} · 묶음 = `group_key`(같은 원문) {len(gkeys)}개 · 건수만 적는다", "",
          "| 유형 | 정답 행 | 사건(묶음) 수 | 가장 큰 사건 비중 | 재현율 (시드 평균) | 행 단위 95% | 사건 단위 95% | 폭 배율 |",
          "|---|---:|---:|---:|---:|---|---|---:|"]
    for x in types:
        nc, big = gstat(x)
        lab = x + (" (측정 불가)" if npos[x] < ca.MEASURABLE_MIN else "")
        md.append(row(lab, npos[x], nc, f"{big * 100:.0f}%", point[x], x))
    md += [row("**유형 적중** (위반 행 · 정답 유형 하나라도)", npos_row, "—", "—", hit_pt, "__hit"),
           row("**위반 탐지** (위반 행 · 유형 무관)", npos_row, "—", "—", any_pt, "__any"), "",
           "읽는 법 — 「폭 배율」은 사건 단위 구간 폭 ÷ 행 단위 구간 폭이다. 1 보다 크면 같은 원문의 문장이 같이 맞고 같이 틀려 "
           "행 단위 구간이 불확실성을 작게 보인다는 뜻이다. 실험 사이의 차(예: D4-04 의 유형 오인 감소)가 사건 단위 구간보다 작으면 우연 범위로 읽는다.",
           "", "🚨 dev 다 — 같은 dev 로 문턱을 골랐다(D-324). 구간은 이 dev 표본의 흔들림이지 봉인 평가셋에서의 수가 아니다."]
    print("\n" + "\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
