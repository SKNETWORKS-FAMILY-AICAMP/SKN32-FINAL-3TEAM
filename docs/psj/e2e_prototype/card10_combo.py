"""카드 10 — 카드 9 모델 + 카드 8 후보 문턱 (판정 로직까지 · 박수진 · 2026-10-08)

카드 8 의 채택 후보(v10 · 후보 문턱 × 0.6 · 합의 문턱 그대로)에서 모델만 카드 9(정상 합성 문구를 음성으로 학습)로 바꿨을 때,
정상 광고 문구는 통과시키면서 위반 탐지는 지키는지 **시드마다 짝지어** 잰다. 재학습 없음 — 카드 9 노트북이 저장한 행별 확률만 읽는다.

  uv run python docs\\psj\\e2e_prototype\\card10_combo.py --dir <행별 확률 폴더> --syn-csv <정상 합성 문구 CSV> --out-md docs\\psj\\reports\\<집계표>.md

  · 견주는 쌍 — 같은 시드의 「Baseline 재현 + 카드 8」 대 「카드 9 모델 + 카드 8」 (시드 42 · 43 · 44)
  · 문턱 — 시드마다 그 시드의 공통 dev 확률로 규칙(F1 최대)대로 다시 고른다(노트북과 같은 값). 후보 문턱 = 0.6 × τ · 여유 구간 0.5 ÷ 0.6 · 합의 문턱 = τ
  · 공통 dev(무조건부 · 조건부)는 `sweep_cand_threshold.py` 와 같은 자로 잰다
  · 정상 합성 문구(학습에 넣지 않은 285행 · 애매 46행 참고)는 판정 로직(사전 + 인코더 층)에 넣는다 — 조건부는 그 문구의 품목을 제품 정보로 준다

고르는 규칙 · 목표 · 한도는 실험 카드에 먼저 적었다(`docs/psj/reports/v10_문턱규칙_거짓과장_실험기록_20261007.md` 카드 10) — 여기서는 그대로 계산할 뿐이다.

🔴 dev 전용 (D-175). 집계표에는 건수만 쓴다. 행 id 가 든 요약(JSON)은 저장소 밖(`--out-dir`)에 쓴다 (D-249 ⑥).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from collections import Counter

import run_judge_dist as rj
import score_encoder_dev as sd
import sweep_cand_threshold as sw
from judge_stage1 import BANNED_TERMS_PATH, QUIET_MARGIN, REPO, load_banned_terms, stage1_signals
from judge_stage2 import stage2_judge
from app import graph as g
from app.contracts import Category
from scripts.eval_graph import conditional_rows

MODELS = {"기준": "copylane-encoder-kcbert-v10-Baseline재현", "카드10": "copylane-encoder-kcbert-v10-카드9-정상음성"}
NAMES = {"기준": "Baseline 재현 + 카드 8", "카드10": "카드 9 모델 + 카드 8"}
SEEDS = [42, 43, 44]
K = 0.6                       # 카드 8 의 채택 후보
SYN_SHA = "aae3b4a5ab5471d31583ca704e0e4fc9bfc24b56693b65e13569a759ecd9cd22"
#: 카드 10 에 먼저 적은 값 — 결과를 본 뒤 고치지 않는다
GOAL_PASS = 0.5               # 목표 — 정상 합성 dev 중 조건부 통과 비율
LIM_DETECT = 0.02             # 한도 ① — 무조건부 탐지 재현율 하락 허용폭 (기준 대비 · 같은 시드)
LIM_QUIET_POS = 1             # 한도 ② — 조용해진 위반 행이 늘어도 되는 수 (두 조건 · 같은 시드)
LIM_AVG, LIM_GE4 = 2.0, 0.05  # 한도 ③ — 유형이 붙은 채점 행의 문장당 유형 · 4개 이상 비율 (두 조건)


def thresholds_of(dev_csv, sdev, Y):
    """시드의 공통 dev 확률로 문턱을 다시 고른다 — 노트북 · 채점 스크립트와 같은 규칙. 편입 대기 칸은 1.01."""
    P = sd.read_probs(dev_csv, sdev)
    th = dict(sd.pick_thresholds(Y, P))
    for l in sd.LABELS:
        th.setdefault(l, 1.01)
    return th


def judge_syn(rows, prob_of, book, th, conditional):
    """정상 합성 문구 → 판정 로직의 칸별 수 (카드 8 문턱)."""
    thk, mg = sw.scaled(th, K, QUIET_MARGIN)
    st = Counter()
    typed = 0
    for r in rows:
        cat = Category(r["품목"]) if conditional else None
        v = stage2_judge(stage1_signals(r["text"], prob_of[r["id"]], book, thk, margin=mg, agree_thresholds=th), category=cat)
        st[rj.state_of(v)] += 1
        typed += bool(v["violations"] or v["hold_types"] or v["no_basis_types"])
    n = len(rows)
    return {"n": n, "pass": sum(st[s] for s in rj.PASS_STATES), "quiet": sum(st[s] for s in rj.QUIET_STATES),
            "confirmed": st["confirmed:위반"], "typed": typed, "states": dict(st)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="카드 9 노트북의 행별 확률 CSV 가 있는 폴더 (두 실험 × 시드 3 × dev · 합성 정상)")
    ap.add_argument("--syn-csv", required=True, help="정상 합성 문구 원본 CSV (문장 · 품목) — 권소라 10-06 판")
    ap.add_argument("--golden", default=rj.GOLDEN)
    ap.add_argument("--banned", default=BANNED_TERMS_PATH)
    ap.add_argument("--out-dir", default=rj.OUT_DIR)
    ap.add_argument("--out-md", default=None)
    a = ap.parse_args(argv)
    out_dir = os.path.abspath(a.out_dir)
    if os.path.commonpath([out_dir, REPO]) == REPO:
        raise SystemExit(f"🔴 요약(JSON · 행 id 포함)을 저장소 안에 쓰지 않는다 (D-249 ⑥): {out_dir}")
    with open(a.syn_csv, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != SYN_SHA:
            raise SystemExit("🔴 정상 합성 문구 CSV 가 카드 9 · 10 에 적은 판과 다르다")
    with open(a.syn_csv, encoding="utf-8-sig", newline="") as f:
        src = {"syn:" + r["id"]: r for r in csv.DictReader(f)}

    sdev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in sdev]
    labels = list(sd.LABELS)
    book = sw.CachedBook(load_banned_terms(a.banned))
    with open(a.banned, "rb") as f:
        dict_sha = hashlib.sha256(f.read()).hexdigest()
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark} · 사전 {dict_sha[:12]} · 규칙 {g.JUDGED_BY} + 인코더 층 · k {K}")

    R = {}
    for key, tag in MODELS.items():
        for s in SEEDS:
            dev_csv = os.path.join(a.dir, f"{tag}_seed{s}_dev행별확률.csv")
            syn_csv = os.path.join(a.dir, f"{tag}_seed{s}_합성정상_행별확률.csv")
            for p in (dev_csv, syn_csv):
                if not os.path.exists(p):
                    raise SystemExit(f"🔴 파일이 없다: {p}")
            th = thresholds_of(dev_csv, sdev, Y)
            _, _, rows, prob_of = sw.load_rows(a.golden, dev_csv, labels)
            sets = {"무조건부": [dict(r) for r in rows], "조건부": conditional_rows([dict(r) for r in rows])}
            m = {}
            for name, rs in sets.items():
                for r in rs:
                    r.setdefault("labels", [])
                    r["bucket"] = rj.bucket(r)
                thk, mg = sw.scaled(th, K, QUIET_MARGIN)
                m[name] = sw.measure(rs, sw.judge_all(rs, [prob_of[r["id"]] for r in rs], book, thk, mg, name == "조건부", th))
            with open(syn_csv, encoding="utf-8-sig", newline="") as f:
                sp = list(csv.DictReader(f))
            assert all(r["id"] in src for r in sp), "합성 정상 확률의 id 가 원본 CSV 에 없다"
            sprob = {r["id"]: {l: float(r[f"p_{l}"]) for l in labels} for r in sp}
            part = {"dev": [], "amb": []}
            for r in sp:
                part["dev" if r["갈래"] == "합성정상dev" else "amb"].append({"id": r["id"], "text": src[r["id"]]["text"], "품목": src[r["id"]]["품목"]})
            assert len(part["dev"]) == 285 and len(part["amb"]) == 46, {k: len(v) for k, v in part.items()}
            syn = {f"{p}_{c}": judge_syn(part[p], sprob, book, th, c == "cond") for p in part for c in ("uncond", "cond")}
            R[(key, s)] = {"th": th, "dev": m, "syn": syn}
            print(f"  {NAMES[key]} · 시드 {s} — 무조건부 탐지 {m['무조건부']['detected']}/{m['무조건부']['positive']} · "
                  f"정상 합성 dev 조건부 통과 {syn['dev_cond']['pass']}/{syn['dev_cond']['n']}")

    # ── 목표 · 한도 (시드마다 · 같은 시드의 기준과 짝)
    V = {}
    for s in SEEDS:
        b, c = R[("기준", s)], R[("카드10", s)]
        det = lambda x: x["dev"]["무조건부"]["detected"] / x["dev"]["무조건부"]["positive"]
        ok = {
            "목표": c["syn"]["dev_cond"]["pass"] >= GOAL_PASS * c["syn"]["dev_cond"]["n"],
            "①": det(c) >= det(b) - LIM_DETECT - 1e-12,
            "②": all(c["dev"][n]["pos_quiet"] <= b["dev"][n]["pos_quiet"] + LIM_QUIET_POS for n in ("무조건부", "조건부")),
            "③": all(c["dev"][n]["avg"] <= LIM_AVG + 1e-9 and c["dev"][n]["ge4"] <= LIM_GE4 + 1e-9 for n in ("무조건부", "조건부")),
            "④": all(c["dev"][n]["errors"] <= b["dev"][n]["errors"] and c["dev"][n]["law_confirmed"] <= b["dev"][n]["law_confirmed"]
                     for n in ("무조건부", "조건부")),
        }
        V[s] = ok
    adopt = all(all(v.values()) for v in V.values())

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    pct = lambda k, n: f"{k}/{n} ({k / n:.1%})" if n else "—"
    md = [f"# 카드 10 — 카드 9 모델 + 카드 8 후보 문턱 (dev · {stamp[:8]})", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 사전 `{dict_sha[:12]}` · 규칙 {g.JUDGED_BY} + 인코더 층(`judge_stage2.py`)",
          f"> 후보 문턱 = {K} × τ · 여유 구간 {QUIET_MARGIN / K:.3f} · 합의 문턱 = τ · τ 는 시드마다 그 시드의 공통 dev 로 고른 F1 최대 문턱 · 건수만 적는다", ""]
    for n in ("무조건부", "조건부"):
        md += [f"### 공통 dev — {n}", "",
               "| 시드 | 모델 | 탐지 재현율 | 확정 재현율 | 조용한 위반 행 | D · L — 조용 | D · L — 유형 후보 | 틀린 확정 (채점 행) | D · L 위반 확정 | 문장당 유형 | 4개 이상 |",
               "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for s in SEEDS:
            for key in MODELS:
                m = R[(key, s)]["dev"][n]
                md.append(f"| {s} | {NAMES[key]} | {pct(m['detected'], m['positive'])} | {pct(m['confirmed'], m['positive'])} | {m['pos_quiet']}/{m['pos_n']} | "
                          f"{m['law_quiet']}/{m['law_n']} | {m['law_typed']}/{m['law_n']} | {m['errors']}/{m['committed']} | {m['law_confirmed']} | {m['avg']:.2f} | {m['ge4']:.1%} |")
        md.append("")
    md += ["### 정상 합성 문구 — 판정 로직 (학습에 넣지 않은 285행 · 애매 표시 46행은 참고)", "",
           "| 시드 | 모델 | 조건부 — 통과 | 조건부 — 유형이 붙은 보류 | 무조건부 — 조용(품목만 알면 통과) | 무조건부 — 유형이 붙은 보류 | 위반 확정 | 애매 — 조건부 통과 |",
           "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for s in SEEDS:
        for key in MODELS:
            y = R[(key, s)]["syn"]
            md.append(f"| {s} | {NAMES[key]} | {pct(y['dev_cond']['pass'], y['dev_cond']['n'])} | {y['dev_cond']['typed']} | "
                      f"{pct(y['dev_uncond']['quiet'], y['dev_uncond']['n'])} | {y['dev_uncond']['typed']} | {y['dev_cond']['confirmed']} · {y['dev_uncond']['confirmed']} | "
                      f"{y['amb_cond']['pass']}/{y['amb_cond']['n']} |")
    yn = lambda x: "지킴" if x else "**넘음**"
    md += ["", "### 목표 · 한도 (카드 10 에 먼저 적은 것 · 같은 시드의 「Baseline 재현 + 카드 8」 대비)", "",
           "| 시드 | 목표 — 정상 합성 dev 조건부 통과 50% 이상 | ① 무조건부 탐지 재현율 −2%p 이내 | ② 조용한 위반 행 +1 이내 | ③ 문장당 유형 2.0 · 4개 이상 5% | ④ 틀린 확정이 늘지 않는다 |",
           "|---:|---|---|---|---|---|"]
    for s in SEEDS:
        v = V[s]
        md.append(f"| {s} | {'충족' if v['목표'] else '**미달**'} | {yn(v['①'])} | {yn(v['②'])} | {yn(v['③'])} | {yn(v['④'])} |")
    md += ["", f"판정 — **{'채택 후보' if adopt else '채택 후보 아님'}** (세 시드 모두 목표와 한도를 지켜야 한다)"]
    print("\n" + "\n".join(md))

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"card10_combo_dev_{stamp}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"at": stamp, "golden_sha256": gsha, "dev_mark": mark, "banned_terms_sha256": dict_sha, "k": K, "judged_by": g.JUDGED_BY,
                   "goal_pass": GOAL_PASS, "lim_detect": LIM_DETECT, "lim_quiet_pos": LIM_QUIET_POS, "lim_avg": LIM_AVG, "lim_ge4": LIM_GE4,
                   "verdict": {str(s): V[s] for s in SEEDS}, "adopt": adopt,
                   "result": {f"{k}_seed{s}": v for (k, s), v in R.items()}}, f, ensure_ascii=False, indent=1, default=str)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {path}")
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
