"""후보 문턱 배율 훑기 — 판정 로직(1 · 2단계)까지 (카드 7 · 박수진 · 2026-10-08)

인코더의 **후보 문턱**을 F1 최대 문턱(τ)의 k 배로 낮췄을 때, 판정 로직을 지난 뒤의 수가 어떻게 달라지는지 dev 에서 잰다.
모델 · 확률은 그대로다(재학습 없음) — 저장해 둔 dev 행별 확률만 읽는다.

  uv run python docs\\psj\\e2e_prototype\\sweep_cand_threshold.py --model <모델 zip 또는 폴더> --probs-csv <…_dev행별확률.csv> --out-md docs\\psj\\reports\\<집계표>.md

  · 후보 문턱 = k × τ (편입 대기 칸 · τ 1.01 은 그대로 둔다)
  · 여유 구간 = min(1, base ÷ k) — 「보류로 붙드는 경계」(base × τ · 지금 0.5 τ)를 그 자리에 둔다
      k ≥ base — 통과하던 문장은 그대로 통과한다(기대 · 표의 「통과 변화」로 확인한다). 달라지는 것은 보류 문장에 유형 후보가 붙는가다
      k < base — 경계가 k × τ 로 내려간다. 통과하던 문장이 보류로 온다(치르는 값)
  · 무조건부(품목 모름) · 조건부(골든 품목) 둘 다 잰다
  · 판정은 `judge_stage2.stage2_judge` 그대로다 — 이 파일은 문턱과 여유 구간만 바꿔 넣는다 (D-99)
  · k = 1.0 줄은 `run_judge_dist.py` 의 지금 결과와 같아야 한다

고르는 규칙은 실험 카드에 먼저 적었다(`docs/psj/reports/v10_문턱규칙_거짓과장_실험기록_20261007.md` 카드 7) — 여기서는 그 규칙을 그대로 계산해 보일 뿐이다.

🔴 dev 전용 — test 행이 든 확률 파일이면 멈춘다 (D-175).
🔴 집계표(`--out-md`)에는 건수만 쓴다. 행 id 가 든 요약(JSON)은 저장소 밖(`--out-dir`)에 쓴다 (D-249 ⑥).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import time
from collections import Counter

import run_judge_dist as rj
import score_encoder_dev as sd
from judge_stage1 import BANNED_TERMS_PATH, QUIET_MARGIN, REPO, load_banned_terms, load_scheme, stage1_signals
from judge_stage2 import stage2_judge
from app import graph as g
from app.contracts import Category

SCALES = "1.0,0.9,0.8,0.7,0.6,0.5,0.4,0.3"
#: 카드 7 에 먼저 적은 값 — 결과를 본 뒤 고치지 않는다
TARGET_DETECT = 0.90      # 목표 — 무조건부 탐지 재현율
LIMIT_AVG = 2.0           # 한도 ② — 유형이 붙은 채점 행의 문장당 유형 수 (카드 5 와 같은 값)
LIMIT_GE4 = 0.05          # 한도 ② — 그중 유형이 4개 이상인 비율 (카드 5 와 같은 값)
LAWFUL = ("D", "D_기타", "D_거래", "neg")   # 조건 D · L


class CachedBook:
    """사전 훑기는 문턱과 무관하다 — 문장마다 한 번만 훑는다. 결과는 `DictBook.scan` 그대로다."""

    def __init__(self, book):
        self.book, self.memo = book, {}

    def scan(self, text, sid="s0"):
        if text not in self.memo:
            self.memo[text] = self.book.scan(text, sid)
        return self.memo[text]


def load_rows(golden_path, probs_csv, labels):
    """dev 행 · 확률 — `run_judge_dist.py` 의 `--probs-csv` 길과 같은 거름."""
    with open(golden_path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    golden = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    ids, prob_of = rj.read_probs_csv(probs_csv, labels)
    by_id = {r["id"]: r for r in golden}
    lost = [i for i in ids if i not in by_id]
    if lost:
        raise SystemExit(f"🔴 행별 확률의 id {len(lost)}개가 골든에 없다 (예: {lost[:3]}) — 골든 판이 다르다 (D-220)")
    n_gold, n_csv = Counter(r["id"] for r in golden), Counter(ids)
    vague = {i for i in n_csv if n_csv[i] > 1 or n_gold[i] > 1}
    mark = hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:16]     # 공통 dev 지문 (`score_encoder_dev.load_dev` 와 같은 식)
    want = sd.DEV_EXPECT.get(sha)
    note = "공통 dev 와 같은 행이다" if want == (len(ids), mark) else f"🟡 공통 dev(기대 {want})와 다르다 — 파일의 행을 쓴다"
    print(f"[INFO] 행별 확률 {len(ids)}행 · 지문 {mark} · {note}")
    if vague:
        print(f"[INFO] 같은 id 가 둘 이상인 행 {sum(n_csv[i] for i in vague)}개는 확률을 문장에 붙일 수 없어 뺐다")
        ids = [i for i in ids if i not in vague]
    rows = [dict(by_id[i]) for i in ids]
    if any(r["split"] != "train" for r in rows):
        raise SystemExit("🔴 dev(train 에서 뗀 행)가 아닌 행이 있다 — 이 스크립트는 dev 전용이다 (D-175)")
    return sha, mark, rows, prob_of


def scaled(th, k, base):
    """(후보 문턱, 여유 구간) — 후보를 낼 수 있는 칸(0 < τ ≤ 1)만 k 배 한다."""
    return {x: (t * k if 0 < t <= 1 else t) for x, t in th.items()}, min(1.0, base / k)


def judge_all(rows, probs, book, th, margin, conditional):
    out = []
    for r, lp in zip(rows, probs):
        cat = Category(r["품목"]) if conditional else None
        out.append(stage2_judge(stage1_signals(r["text"], lp, book, th, margin=margin), category=cat))
    return out


def measure(rows, res):
    """판정 결과 → 수. 탐지 · 확정 재현율은 팀장 평가 도구(`scripts/eval_graph.py`)의 것이다."""
    from scripts import eval_graph as eg
    st = [rj.state_of(v) for v in res]
    s = eg.summarize(rows, [eg.predict(v["state"]) for v in res])
    d, sr = s["detect"], s["selective_risk"]
    ntypes = [len(v["violations"]) + len(v["hold_types"]) + len(v["no_basis_types"]) for v in res]
    shown = [ntypes[i] for i, r in enumerate(rows) if r["bucket"] == "scored" and ntypes[i]]
    law = [i for i, r in enumerate(rows) if r["bucket"] in LAWFUL]
    pos = [i for i, r in enumerate(rows) if r["bucket"] in ("scored", "pending")]
    conf = Counter(rows[i]["bucket"] for i in range(len(rows)) if st[i] == "confirmed:위반")
    return {
        "rows": len(rows), "positive": d["positive"], "detected": d["detected"], "confirmed": d["confirmed"],
        "committed": s["committed"], "errors": round(sr * s["committed"]) if sr is not None else 0,
        "quiet": sorted(rows[i]["id"] for i in range(len(rows)) if st[i] in rj.QUIET_STATES),
        "passed": sum(1 for x in st if x in rj.PASS_STATES),
        "pos_n": len(pos), "pos_quiet": sum(1 for i in pos if st[i] in rj.QUIET_STATES),
        "law_n": len(law), "law_quiet": sum(1 for i in law if st[i] in rj.QUIET_STATES),
        "law_typed": sum(1 for i in law if ntypes[i] and st[i] != "confirmed:위반"),
        "law_confirmed": sum(conf[b] for b in LAWFUL), "confirmed_by_bucket": dict(conf),
        "typed_scored": len(shown), "avg": sum(shown) / len(shown) if shown else 0.0,
        "ge4": sum(1 for x in shown if x >= 4) / len(shown) if shown else 0.0,
        "why": dict(Counter(v["why"] for v in res)),
    }


def compare(m, base):
    """Baseline(k = 1.0) 과의 차이 — 통과(조용)하던 행이 그대로인가 · 틀린 확정이 늘었는가."""
    q, q0 = set(m["quiet"]), set(base["quiet"])
    m["quiet_lost"], m["quiet_gained"] = sorted(q0 - q), sorted(q - q0)
    m["errors_up"] = m["errors"] - base["errors"]
    m["law_confirmed_up"] = m["law_confirmed"] - base["law_confirmed"]


def limits(k, un, co):
    """카드 7 의 한도 — ① 통과 변화 없음(두 조건) ② 후보 부담(무조건부) ③ 틀린 확정이 늘지 않는다(두 조건)."""
    a = all(not m["quiet_lost"] and not m["quiet_gained"] for m in (un, co))
    b = un["avg"] <= LIMIT_AVG + 1e-9 and un["ge4"] <= LIMIT_GE4 + 1e-9
    c = all(m["errors_up"] <= 0 and m["law_confirmed_up"] <= 0 for m in (un, co))
    return {"①": a, "②": b, "③": c}


def table(title, ms, mark):
    """조건 하나의 표 — 문자열 줄들(마크다운)."""
    head = ("| k | 여유 구간 | 탐지 재현율 | 확정 재현율 | 통과 변화 (잃음 · 얻음) | 조용한 위반 행 | D · L — 조용 | D · L — 유형 후보 | "
            "D · L — 위반 확정 | 틀린 확정 (채점 행) | 유형 붙은 채점 행 | 문장당 유형 | 4개 이상 |")
    lines = [f"### {title}", "", head, "|" + "---:|" * 13]
    for k, mg, m in ms:
        p = m["positive"]
        lines.append(
            f"| {k:g}{mark.get(k, '')} | {mg:.3f} | {m['detected']}/{p} ({m['detected'] / p:.1%}) | {m['confirmed']}/{p} ({m['confirmed'] / p:.1%}) | "
            f"{len(m['quiet_lost'])} · {len(m['quiet_gained'])} | {m['pos_quiet']}/{m['pos_n']} | {m['law_quiet']}/{m['law_n']} | "
            f"{m['law_typed']}/{m['law_n']} | {m['law_confirmed']}/{m['law_n']} | {m['errors']}/{m['committed']} | "
            f"{m['typed_scored']} | {m['avg']:.2f} | {m['ge4']:.1%} |")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="모델 폴더 또는 zip — label_scheme.json(문턱)만 읽는다")
    ap.add_argument("--probs-csv", required=True, help="노트북이 저장한 dev 행별 확률 CSV (id · p_<유형>)")
    ap.add_argument("--scales", default=SCALES, help=f"후보 문턱 배율 k 들 (기본 {SCALES}) — 1.0 은 늘 함께 잰다")
    ap.add_argument("--base-margin", type=float, default=QUIET_MARGIN, help="지금의 여유 구간 (τ 배수 · 보류 경계)")
    ap.add_argument("--golden", default=rj.GOLDEN)
    ap.add_argument("--banned", default=BANNED_TERMS_PATH)
    ap.add_argument("--out-dir", default=rj.OUT_DIR, help="요약 JSON 을 둘 곳 — 저장소 밖")
    ap.add_argument("--out-md", default=None, help="집계표(건수만) — 저장소 안에 둬도 된다")
    a = ap.parse_args(argv)

    out_dir = os.path.abspath(a.out_dir)
    if os.path.commonpath([out_dir, REPO]) == REPO:
        raise SystemExit(f"🔴 요약(JSON · 행 id 포함)을 저장소 안에 쓰지 않는다 (D-249 ⑥): {out_dir}")
    ks = sorted({float(x) for x in a.scales.split(",") if x.strip()} | {1.0}, reverse=True)
    if any(not 0 < k <= 1 for k in ks):
        raise SystemExit("🔴 배율 k 는 0 초과 1 이하다 — 문턱을 올리는 실험이 아니다")

    labels, th, scheme = load_scheme(rj.scheme_dir(a.model))
    sha, dev_mark, rows, prob_of = load_rows(a.golden, a.probs_csv, labels)
    if scheme.get("golden_sha256") and scheme["golden_sha256"] != sha:
        raise SystemExit(f"🔴 이 모델은 다른 골든으로 학습했다 — 모델 {scheme['golden_sha256'][:12]} · 지금 {sha[:12]} (D-220)")
    book = CachedBook(load_banned_terms(a.banned))
    with open(a.banned, "rb") as f:
        dict_sha = hashlib.sha256(f.read()).hexdigest()
    print(f"[INFO] golden {sha[:12]} · 사전 {dict_sha[:12]} · 모델 {scheme.get('experiment', '?')} · 규칙 {g.JUDGED_BY} + 인코더 층")
    print("[INFO] τ(F1 최대): " + " · ".join(f"{k} {v:g}" for k, v in th.items()))

    from scripts.eval_graph import conditional_rows
    sets = {"무조건부": [dict(r) for r in rows], "조건부": conditional_rows([dict(r) for r in rows])}
    for rs in sets.values():
        for r in rs:
            r.setdefault("labels", [])
            r["bucket"] = rj.bucket(r)
    print(f"[INFO] 무조건부 {len(sets['무조건부'])}행 · 조건부(품목을 아는 행) {len(sets['조건부'])}행 · 배율 {' · '.join(f'{k:g}' for k in ks)}")

    result = {name: {} for name in sets}
    for name, rs in sets.items():
        probs = [prob_of[r["id"]] for r in rs]
        for k in ks:
            t0 = time.perf_counter()
            thk, mg = scaled(th, k, a.base_margin)
            m = measure(rs, judge_all(rs, probs, book, thk, mg, name == "조건부"))
            m["margin"] = mg
            result[name][k] = m
            print(f"  {name} · k {k:g} · 여유 구간 {mg:.3f} — 탐지 {m['detected']}/{m['positive']} · 확정 {m['confirmed']}/{m['positive']} "
                  f"({time.perf_counter() - t0:.0f}초)")
        for k in ks:
            compare(result[name][k], result[name][1.0])

    lim = {k: limits(k, result["무조건부"][k], result["조건부"][k]) for k in ks}
    rate = lambda k: result["무조건부"][k]["detected"] / result["무조건부"][k]["positive"]
    okay = [k for k in ks if k < 1.0 and all(lim[k].values())]
    pick = max(okay, key=lambda k: (rate(k), k)) if okay else None
    mark = {k: " ◀" for k in ([pick] if pick is not None else [])}

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    md = [f"# 후보 문턱 배율 훑기 — 판정 로직까지 (dev · {stamp[:8]})", "",
          f"> 모델 {scheme.get('experiment', '?')} · 확률 `{os.path.basename(a.probs_csv)}` · dev 지문 `{dev_mark}` · golden `{sha[:12]}` · 사전 `{dict_sha[:12]}` · "
          f"규칙 {g.JUDGED_BY} + 인코더 층(`judge_stage2.py`) · 사전 확정에 인코더 합의 요구",
          f"> 후보 문턱 = k × τ(F1 최대) · 여유 구간 = min(1, {a.base_margin:g} ÷ k) · 건수만 적는다(행 id · 문장 없음)",
          "> τ: " + " · ".join(f"{k} {v:g}" for k, v in th.items()), ""]
    for name in sets:
        n = len(sets[name])
        md += table(f"{name} — {n}행", [(k, result[name][k]["margin"], result[name][k]) for k in ks], mark) + [""]
    md += ["### 한도 · 목표 (카드 7 에 먼저 적은 것)", "",
           "| k | ① 통과 변화 없음 (두 조건) | ② 문장당 유형 ≤ 2.0 · 4개 이상 ≤ 5% (무조건부) | ③ 틀린 확정이 늘지 않는다 (두 조건) | 무조건부 탐지 재현율 | 목표 90% |",
           "|---:|---|---|---|---:|---|"]
    yn = lambda x: "지킴" if x else "**넘음**"
    for k in ks:
        md.append(f"| {k:g}{mark.get(k, '')} | {yn(lim[k]['①'])} | {yn(lim[k]['②'])} | {yn(lim[k]['③'])} | {rate(k):.1%} | "
                  f"{'충족' if rate(k) >= TARGET_DETECT else '미달'} |")
    md += ["", ("고른 값 — 한도를 모두 지킨 k 중 무조건부 탐지 재현율이 가장 높은 것: "
                + (f"**k = {pick:g}** ({rate(pick):.1%} · 목표 {'충족' if rate(pick) >= TARGET_DETECT else '미달'})" if pick is not None
                   else "**없음** — 한도를 모두 지킨 k 가 없다")), ""]
    whys = sorted({w for name in sets for k in ks for w in result[name][k]["why"]},
                  key=lambda w: -result["무조건부"][1.0]["why"].get(w, 0))
    for name in sets:
        md += [f"### 인코더 층의 까닭별 — {name}", "", "| 까닭 | " + " | ".join(f"k {k:g}" for k in ks) + " |", "|---|" + "---:|" * len(ks)]
        md += [f"| {w} | " + " | ".join(str(result[name][k]["why"].get(w, 0)) for k in ks) + " |"
               for w in whys if any(result[name][k]["why"].get(w) for k in ks)]
        md += ["", f"위반 확정이 선 행 (버킷별) — " + " / ".join(
            f"k {k:g}: " + (" · ".join(f"{b} {v}" for b, v in sorted(result[name][k]["confirmed_by_bucket"].items())) or "없음") for k in ks), ""]
    print("\n" + "\n".join(md))

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"cand_threshold_sweep_dev_{stamp}.json")
    meta = {"at": stamp, "golden_sha256": sha, "banned_terms_sha256": dict_sha, "model_experiment": scheme.get("experiment"),
            "probs_csv": os.path.basename(a.probs_csv), "dev_mark": dev_mark, "thresholds_f1": th, "base_margin": a.base_margin, "scales": ks,
            "judged_by": g.JUDGED_BY, "target_detect": TARGET_DETECT, "limit_avg": LIMIT_AVG, "limit_ge4": LIMIT_GE4,
            "limits": {f"{k:g}": lim[k] for k in ks}, "pick": pick,
            "result": {name: {f"{k:g}": result[name][k] for k in ks} for name in sets}}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {path}")
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
