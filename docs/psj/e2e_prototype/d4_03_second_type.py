"""D4-03 2등유형 — 옛 카드 2 재확인: 거짓_과장 단독일 때 2등 유형 올리기 (박수진 · 2026-10-12)

학습 없음 — D4-00(카드 17 채택 판) 시드 48 · 49 · 50 의 dev 행별 확률에 카드 2 의 후보 규칙을 건다.

  uv run python docs\\psj\\e2e_prototype\\d4_03_second_type.py --dir <행별 확률 폴더> --out-md docs\\psj\\reports\\D4-03_2등유형_dev_20261012.md

  · 문턱 — D-324 (card17_adopt.py 와 같은 규칙 · 같은 목표)
  · 규칙 (카드 2 그대로) — 후보가 거짓_과장 하나뿐일 때, 거짓_과장을 뺀 확정 8종 중 확률이 가장 높은 유형이
    자기 문턱의 k 배 이상이면 그 유형도 후보로 올린다 · k = 0.7 · 0.5
  · 이미 후보가 선 행에만 유형을 더하므로 위반 탐지 · 음성 오판정은 바뀌지 않는다 (화면에서 대조)
  · 목표 · 한도 (D4 실험기록 D4-03 에 먼저 적었다 · 카드 2 와 같은 값 · 시드 평균)
      목표 — F1 유형 오인율 9% 이하 (채점 510행 중 45.9행 이하)
      한도 — dev 양성 30 이상 유형의 정밀도 하락 5%p 이내 (D4-00 같은 시드 대비 · 시드 평균)
      판정 — 목표와 한도를 모두 지킨 k 가 있으면 통과 (그런 k 가 여럿이면 유형 오인이 가장 적은 것)
  · `--self-test` — k 를 무한대로 두면(아무것도 안 올림) D4-00 의 수와 같아야 한다

🔴 dev 전용 (D-175). 집계표에는 건수만 쓴다.
"""
import argparse
import statistics
from collections import Counter

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
CAND = ca.CAND
KS = [0.7, 0.5]
GOAL_RATE = 0.09
PREC_DROP = 0.05
FX = "거짓_과장"
FI = sd.CONF8.index(FX)


def lift(P, th, cand, k):
    """카드 2 규칙 — 거짓_과장 단독 행에 2등 유형을 올린다. (새 후보 · 올린 행 수)"""
    out, n = [], 0
    for p, c in zip(P, cand, strict=True):
        c = list(c)
        if c == [FX] and k != float("inf"):
            j = max((i for i in range(len(sd.CONF8)) if i != FI), key=lambda i: p[i])
            y = sd.CONF8[j]
            if p[j] >= k * th[y]:
                c.append(y)
                n += 1
        out.append(c)
    return out, n


def score(dev, cand):
    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    cats = Counter()
    added_ok = 0
    for k in sc:
        c, y = set(cand[k]), {x for x in dev[k]["target"] if x in sd.CONF8}
        if not c:
            cats["F2"] += 1
        elif not (c & y):
            cats["F1"] += 1
        else:
            cats["hit"] += 1
    prec = {}
    for i, x in enumerate(sd.CONF8):
        pp = sum(1 for k in range(len(dev)) if x in cand[k])
        tp = sum(1 for k in range(len(dev)) if x in cand[k] and x in dev[k]["target"])
        prec[x] = (tp / pp) if pp else None
    det = sum(1 for k in sc if cand[k])
    neg = sum(1 for k, r in enumerate(dev) if r["bucket"] in ("D", "L", "neg") and cand[k])
    return {"F1": cats["F1"], "hit": cats["hit"], "det": det, "neg": neg, "prec": prec, "scored": len(sc)}


def added(dev, before, after):
    ok = bad = 0
    for k, (b, a) in enumerate(zip(before, after, strict=True)):
        for x in set(a) - set(b):
            if x in dev[k]["target"]:
                ok += 1
            else:
                bad += 1
    return ok, bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="k = ∞ — 아무것도 안 올린다. D4-00 과 같아야 한다")
    a = ap.parse_args(argv)
    ks = [float("inf")] if a.self_test else KS

    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    f = lambda t, s: f"{a.dir}/{t}_seed{s}_dev행별확률.csv"
    P = {(t, s): sd.read_probs(f(t, s), dev) for t in (ca.BASE, CAND) for s in SEEDS}
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    rec = {s: {x: ca.recall(Y, P[(ca.BASE, s)], i, sd.pick_thresholds(Y, P[(ca.BASE, s)])[x])
               for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}
    big = [x for x in sd.CONF8 if npos[x] >= ca.MEASURABLE_MIN]

    R = {}
    for s in SEEDS:
        th, _ = ca.d324_thresholds(Y, P[(CAND, s)], target)
        e = sd.evaluate(dev, P[(CAND, s)], th)
        base = score(dev, e["cand"])
        assert base["det"] == e["det"] and base["hit"] == e["hit"], "채점이 score_encoder_dev 와 다르다"
        R[(s, "D4-00")] = dict(base, n_lift=0, ok=0, bad=0, solo=sum(1 for c in e["cand"] if c == [FX]))
        for k in ks:
            c2, n = lift(P[(CAND, s)], th, e["cand"], k)
            ok, bad = added(dev, e["cand"], c2)
            R[(s, k)] = dict(score(dev, c2), n_lift=n, ok=ok, bad=bad)

    m = lambda key, fn: statistics.mean(fn(R[(s, key)]) for s in SEEDS)
    sc = R[(SEEDS[0], "D4-00")]["scored"]
    goal = GOAL_RATE * sc
    print(f"[대조] D4-00 — 위반 탐지 {m('D4-00', lambda r: r['det']):.1f} · 정답 유형 적중 {m('D4-00', lambda r: r['hit']):.1f} "
          f"· F1 유형 오인 {m('D4-00', lambda r: r['F1']):.1f} (카드 17 · D4-02 와 같아야 한다)")

    md = [f"# D4-03 2등유형 — 옛 카드 2 재확인 (dev){' — 자기 검증' if a.self_test else ''}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 모델 D4-00 (카드17-검수정상음성) · D-324 문턱 · "
          f"시드 {' · '.join(map(str, SEEDS))} 평균 · 학습 없음 · 건수만 적는다", "",
          f"| 설정 | F1 유형 오인 (/{sc}) | 정답 유형 적중 | 위반 탐지 | 음성 오판정 | 2등을 올린 행 | 더한 유형 (맞음 · 틀림) |",
          "|---|---:|---:|---:|---:|---:|---|"]
    for key in ["D4-00"] + ks:
        name = "D4-00" if key == "D4-00" else f"2등 올림 k={key:g}"
        md.append(f"| {name} | {m(key, lambda r: r['F1']):.1f} ({m(key, lambda r: r['F1']) / sc * 100:.1f}%) | "
                  f"{m(key, lambda r: r['hit']):.1f} | {m(key, lambda r: r['det']):.1f} | {m(key, lambda r: r['neg']):.1f} | "
                  f"{m(key, lambda r: r['n_lift']):.1f} | {m(key, lambda r: r['ok']):.1f} · {m(key, lambda r: r['bad']):.1f} |")
    md += ["", f"거짓_과장 단독 후보 행 (D4-00 · 시드 평균) {m('D4-00', lambda r: r['solo']):.1f}", "",
           "| 유형별 정밀도 (%) · 시드 평균 | D4-00 | " + " | ".join(f"k={k:g}" for k in ks) + " |",
           "|---|---:|" + "---:|" * len(ks)]
    pm = lambda key, x: statistics.mean(R[(s, key)]["prec"][x] or 0 for s in SEEDS) * 100
    for x in big:
        md.append(f"| {x} | {pm('D4-00', x):.1f} | " + " | ".join(f"{pm(k, x):.1f}" for k in ks) + " |")

    md += ["", f"| 판정 (먼저 적은 기준) | 목표 — F1 유형 오인 {goal:.1f}행 이하 | 한도 — 정밀도 하락 5%p 이내 (최대 하락 유형) | 판정 |",
           "|---|---|---|---|"]
    passed = []
    for k in ks:
        f1 = m(k, lambda r: r["F1"])
        drops = {x: pm("D4-00", x) - pm(k, x) for x in big}
        wx = max(drops, key=drops.get)
        g_ok, l_ok = f1 <= goal + 1e-9, drops[wx] <= PREC_DROP * 100 + 1e-9
        if g_ok and l_ok:
            passed.append((f1, k))
        md.append(f"| k={k:g} | {f1:.1f} · {'충족' if g_ok else '미달'} | {wx} −{drops[wx]:.1f}%p · {'지킴' if l_ok else '넘음'} | "
                  f"{'통과' if g_ok and l_ok else '탈락'} |")
    md += ["", ("**통과** — k = %g" % min(passed)[1]) if passed else "**탈락** — 목표와 한도를 모두 지킨 k 가 없다 (옛 카드 2 와 같은 결론이면 D4-03 을 닫는다)"]

    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8") as fo:
            fo.write(out)
        print(f"[INFO] 집계표(건수만): {a.out_md}")


if __name__ == "__main__":
    main()
