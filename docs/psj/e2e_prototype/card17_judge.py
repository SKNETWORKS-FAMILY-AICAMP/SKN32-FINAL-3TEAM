"""카드 17 보충 — 채택 판을 판정 로직에 넣어 잰다 (박수진 · 2026-10-12)

카드 17 의 판정(`card17_adopt.py`)은 인코더만 본 수다. 팀장 보고에는 **판정 로직(사전 + 인코더 층)** 의 수가 든다.
같은 시드의 기준선 재현과 채택 판 후보를 **판 그대로(D-324 문턱 · k = 1.0)** 판정 로직에 넣어 잰다. 판정(채택 여부)은 바꾸지 않는다 — 수만 낸다.

  uv run python docs\\psj\\e2e_prototype\\card17_judge.py --dir <행별 확률 폴더> --syn-csv <권소라 10-11 검수판 CSV> --out-md docs\\psj\\reports\\v10_카드17_판정로직_정상문구_dev_20261012.md

  · 공통 dev — 무조건부 749행 · 조건부(제품 정보를 아는 행) — 탐지 · 확정 · 조용해진 위반 · 틀린 확정 · D · L
  · 정상 문구 — 검수 「적법」 측정용 171행 · 참고 묶음(적법(사실 전제) · 조건부 · 애매) — 조건부(그 문구의 품목을 준다) 통과 · 무조건부 조용
  · 진단 — 조건부 · 무조건부의 **틀린 확정 행**(확정 유형이 골든 라벨과 겹치지 않는 채점 행)을 화면에만 적는다(id · 정답 · 확정 유형 · 까닭) — 집계표에는 수만
🔴 dev 전용 (D-175). 행 id 가 든 요약(JSON)은 저장소 밖(`--out-dir`)에 쓴다 (D-249 ⑥).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import statistics

import card17_adopt as ca
import run_judge_dist as rj
import score_encoder_dev as sd
import sweep_cand_threshold as sw
from judge_stage1 import BANNED_TERMS_PATH, QUIET_MARGIN, REPO, load_banned_terms, stage1_signals
from judge_stage2 import stage2_judge
from app import graph as g
from scripts.eval_graph import conditional_rows
from scripts import eval_graph as _eg

SYN_SHA = "f3bfec9079e05c367b2d27495c385659118fd56abd963e89ac5d760abfdd00ea"   # 권소라 10-11 검수판
NAMES = {ca.BASE: "기준선 재현", ca.CAND: "채택 판 후보"}
GROUPS = ["합성정상dev", "참고-적법(사실 전제)", "참고-조건부", "애매"]


def wrong_confirms(rows, res):
    """확정했는데 확정 유형이 골든 라벨과 하나도 겹치지 않는 채점 행 (진단 — 평가 도구의 selective risk 와 같은 방향의 근사)."""
    out = []
    for r, v in zip(rows, res):
        if rj.state_of(v) == "confirmed:위반" and r.get("bucket") == "scored" and not (set(v["violations"]) & set(r.get("labels") or [])):
            out.append({"id": r["id"], "gold": list(r.get("labels") or []), "premise": r.get("전제"), "confirmed": list(v["violations"]), "why": v.get("why")})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--syn-csv", required=True)
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
            raise SystemExit("🔴 정상 문구 CSV 가 카드 17 의 검수판(10-11 · f3bfec90…)이 아니다")
    with open(a.syn_csv, encoding="utf-8-sig", newline="") as f:
        src = {"syn:" + r["id"]: r for r in csv.DictReader(f)}

    sdev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in sdev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    labels = list(sd.LABELS)
    book = sw.CachedBook(load_banned_terms(a.banned))
    with open(a.banned, "rb") as f:
        dict_sha = hashlib.sha256(f.read()).hexdigest()
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark} · 사전 {dict_sha[:12]} · 규칙 {g.JUDGED_BY} + 인코더 층 · 판 그대로 (k 1.0 · D-324 문턱)")

    f = lambda tag, s, kind: os.path.join(a.dir, f"{tag}_seed{s}_{kind}.csv")
    # D-324 목표 — card17_adopt 와 같은 계산
    PB = {s: sd.read_probs(f(ca.BASE, s, "dev행별확률"), sdev) for s in ca.SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in ca.SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in ca.SEEDS) for x in rec[ca.SEEDS[0]]}

    R, W = {}, {}
    for tag in (ca.BASE, ca.CAND):
        for s in ca.SEEDS:
            th, _ = ca.d324_thresholds(Y, sd.read_probs(f(tag, s, "dev행별확률"), sdev), target)
            for l in sd.LABELS:
                th.setdefault(l, 1.01)
            _, _, rows, prob_of = sw.load_rows(a.golden, f(tag, s, "dev행별확률"), labels)
            m, w = {}, {}
            for name, rs in (("무조건부", [dict(r) for r in rows]), ("조건부", conditional_rows([dict(r) for r in rows]))):
                for r in rs:
                    r.setdefault("labels", [])
                    r["bucket"] = rj.bucket(r)
                res = sw.judge_all(rs, [prob_of[r["id"]] for r in rs], book, th, QUIET_MARGIN, name == "조건부", th)
                m[name] = sw.measure(rs, res)
                w[name] = wrong_confirms(rs, res)
            with open(f(tag, s, "합성정상_행별확률"), encoding="utf-8-sig", newline="") as fh:
                sp = list(csv.DictReader(fh))
            syn = {}
            for grp in GROUPS:
                part = [r for r in sp if r["갈래"] == grp]
                for c in ("uncond", "cond"):
                    st, typed = {}, 0
                    for r in part:
                        cat = _eg.product_of({"품목": src[r["id"]]["품목"]}, True).category if c == "cond" else None
                        lp = {l: float(r[f"p_{l}"]) for l in labels}
                        v = stage2_judge(stage1_signals(src[r["id"]]["text"], lp, book, th, margin=QUIET_MARGIN, agree_thresholds=th), category=cat)
                        k = rj.state_of(v)
                        st[k] = st.get(k, 0) + 1
                        typed += bool(v["violations"] or v["hold_types"] or v["no_basis_types"])
                    syn[f"{grp}_{c}"] = {"n": len(part), "pass": sum(st.get(x, 0) for x in rj.PASS_STATES),
                                         "quiet": sum(st.get(x, 0) for x in rj.QUIET_STATES), "confirmed": st.get("confirmed:위반", 0), "typed": typed}
            R[(tag, s)] = {"dev": m, "syn": syn}
            W[(tag, s)] = w
            print(f"  {NAMES[tag]} · 시드 {s} — 무조건부 탐지 {m['무조건부']['detected']}/{m['무조건부']['positive']} · 확정 {m['무조건부']['confirmed']} · "
                  f"조건부 틀린 확정 {m['조건부']['errors']}/{m['조건부']['committed']} · 검수 적법 정상 문구 조건부 통과 "
                  f"{syn['합성정상dev_cond']['pass']}/{syn['합성정상dev_cond']['n']}")

    mean = lambda tag, fn: statistics.mean(fn(R[(tag, s)]) for s in ca.SEEDS)
    per = lambda tag, fn: " · ".join(str(fn(R[(tag, s)])) for s in ca.SEEDS)
    tags = (ca.BASE, ca.CAND)
    md = [f"# 카드 17 보충 — 채택 판을 판정 로직에 넣어 잰 수 (dev · {dt.date.today():%Y%m%d})", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 사전 `{dict_sha[:12]}` · 규칙 {g.JUDGED_BY} + 인코더 층(`judge_stage2.py`) · "
          f"판 그대로(D-324 문턱 · 후보 = 합의 = τ · 여유 구간 {QUIET_MARGIN}) · 시드 {' · '.join(map(str, ca.SEEDS))} 평균 (괄호 안은 시드별) · 건수만 적는다", "",
          "| 지표 | " + " | ".join(NAMES[t] for t in tags) + " |", "|---|" + "---:|" * len(tags)]
    for n in ("무조건부", "조건부"):
        P = R[(ca.BASE, ca.SEEDS[0])]["dev"][n]["positive"]
        md += [f"| **{n}** — 탐지 재현율 (/{P}) | " + " | ".join(f"{mean(t, lambda x: x['dev'][n]['detected']):.1f} ({per(t, lambda x: x['dev'][n]['detected'])})" for t in tags) + " |",
               f"| {n} — 확정 (/{P}) | " + " | ".join(f"{mean(t, lambda x: x['dev'][n]['confirmed']):.1f} ({per(t, lambda x: x['dev'][n]['confirmed'])})" for t in tags) + " |",
               f"| {n} — 틀린 확정 | " + " | ".join(f"{mean(t, lambda x: x['dev'][n]['errors']):.1f} ({per(t, lambda x: x['dev'][n]['errors'])})" for t in tags) + " |",
               f"| {n} — 조용해진 위반 행 | " + " | ".join(f"{mean(t, lambda x: x['dev'][n]['pos_quiet']):.1f}" for t in tags) + " |",
               f"| {n} — D · L 유형 후보 · 위반 확정 | " + " | ".join(f"{mean(t, lambda x: x['dev'][n]['law_typed']):.1f} · {mean(t, lambda x: x['dev'][n]['law_confirmed']):.1f}" for t in tags) + " |"]
    for grp in GROUPS:
        n = R[(ca.BASE, ca.SEEDS[0])]["syn"][f"{grp}_cond"]["n"]
        lab = "**검수 적법 정상 문구**" if grp == "합성정상dev" else f"참고 · {grp}"
        md += [f"| {lab} — 조건부 통과 (/{n}) | " + " | ".join(f"{mean(t, lambda x: x['syn'][f'{grp}_cond']['pass']):.1f} ({per(t, lambda x: x['syn'][f'{grp}_cond']['pass'])})" for t in tags) + " |"]
        if grp == "합성정상dev":
            md += [f"| 검수 적법 정상 문구 — 무조건부 조용(품목만 알면 통과) (/{n}) | " + " | ".join(f"{mean(t, lambda x: x['syn'][f'{grp}_uncond']['quiet']):.1f}" for t in tags) + " |",
                   f"| 검수 적법 정상 문구 — 위반 확정 (조건부 · 무조건부) | " + " | ".join(f"{mean(t, lambda x: x['syn'][f'{grp}_cond']['confirmed']):.1f} · {mean(t, lambda x: x['syn'][f'{grp}_uncond']['confirmed']):.1f}" for t in tags) + " |"]
    nw = {t: {n: statistics.mean(len(W[(t, s)][n]) for s in ca.SEEDS) for n in ("무조건부", "조건부")} for t in tags}
    md += ["", "진단 — 확정 유형이 골든 라벨과 겹치지 않는 채점 행(시드 평균): " + " · ".join(f"{NAMES[t]} 무조건부 {nw[t]['무조건부']:.1f} · 조건부 {nw[t]['조건부']:.1f}" for t in tags)
           + " — 행 목록은 저장소 밖 요약(JSON)에만 있다"]
    print("\n" + "\n".join(md))

    print("\n[진단 · 화면에만] 채택 판 후보의 틀린 확정 행 (id · 정답 · 전제 · 확정 유형 · 까닭)")
    for s in ca.SEEDS:
        for n in ("무조건부", "조건부"):
            for x in W[(ca.CAND, s)][n]:
                print(f"  시드 {s} · {n} · {x['id']} · 정답 {x['gold']} · 전제 {x['premise']} · 확정 {x['confirmed']} · {x['why']}")
    print("[진단 · 화면에만] 기준선 재현의 틀린 확정 행")
    for s in ca.SEEDS:
        for n in ("무조건부", "조건부"):
            for x in W[(ca.BASE, s)][n]:
                print(f"  시드 {s} · {n} · {x['id']} · 정답 {x['gold']} · 전제 {x['premise']} · 확정 {x['confirmed']} · {x['why']}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"card17_judge_dev_{stamp}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fo:
        json.dump({"at": stamp, "golden_sha256": gsha, "dev_mark": mark, "banned_terms_sha256": dict_sha, "judged_by": g.JUDGED_BY,
                   "result": {f"{NAMES[t]}_seed{s}": R[(t, s)] for t in tags for s in ca.SEEDS},
                   "wrong_confirms": {f"{NAMES[t]}_seed{s}": W[(t, s)] for t in tags for s in ca.SEEDS}},
                  fo, ensure_ascii=False, indent=1, default=str)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {path}")
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
