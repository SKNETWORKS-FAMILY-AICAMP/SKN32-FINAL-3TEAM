"""D4-04 보충 — 품목입력 모델을 판정 로직에 넣어 잰다 (박수진 · 2026-10-12 · 탐색)

`d4_04_product_input.py` 는 인코더만 본 수다. 판정 흐름에 맞춰 **판정 로직(사전 + 인코더 층)** 으로 잰다.
  · 무조건부(품목 모름) = 첫 판정 → D4-04 는 (나) 모름 입력의 확률
  · 조건부(품목 앎)     = 재판정   → D4-04 는 (가) 품목 입력의 확률
D4-00 은 두 조건 모두 같은 확률(문구만)이다. 문턱은 D-324(card17_adopt.py 와 같은 규칙 · 모델 · 입력 · 시드마다) · k = 1.0 · 판 그대로.

  uv run python docs\\psj\\e2e_prototype\\d4_04_judge.py --dir <D4-00 행별 확률 폴더> --d4-dir <D4-04 행별 확률 폴더> --syn-csv <권소라 10-11 검수판 CSV> --out-md docs\\psj\\reports\\D4-04_판정로직_dev_YYYYMMDD.md

  · 기준 (D4 실험기록 「D4-04 보충 — 판정 로직」 에 먼저 적었다 · 시드 평균 · D4-00 대비)
      조건부(재판정)   ① 조용해진 위반 행(유형 있는 · 없는 위반이 통과 · 품목만 보류로 간 행)이 늘지 않는다
                       ② 틀린 확정이 늘지 않는다 ③ D · L 위반 확정 0
      무조건부(첫 판정) ④ 탐지 재현율 −2.5%p 이내 ⑤ 틀린 확정이 늘지 않는다 ⑥ D · L 위반 확정 0
      판정 — 여섯을 모두 지키면 「판정 로직 확인 통과」 (채택이 아니다 — 팀장 판정)
  · 참고 — 확정 · 화장품 「유형 없는 위반」 의 통과 · 검수 적법 정상 문구 · 참고 묶음의 통과
  · 🟡 조건부에서 인코더에 넣은 품목은 골든 `품목` 칸이고, 판정 로직의 제품 정보는 `product_of`(전제 먼저)다 — 둘이 다른 행 수를 화면에 적는다
  · `--self-test` — D4-04 자리에 D4-00 을 넣는다. 차이가 0 이어야 한다
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
import card17_judge as cj
import run_judge_dist as rj
import score_encoder_dev as sd
import sweep_cand_threshold as sw
from judge_stage1 import BANNED_TERMS_PATH, QUIET_MARGIN, REPO, load_banned_terms, stage1_signals
from judge_stage2 import stage2_judge
from app import graph as g
from scripts.eval_graph import conditional_rows
from scripts import eval_graph as _eg

SEEDS = ca.SEEDS
D400, D404 = ca.CAND, "copylane-encoder-kcbert-D4-04-품목입력"
NAMES = {"D4-00": "D4-00", "D4-04": "D4-04"}
COND = {"무조건부": ("uncond", "모름"), "조건부": ("cond", "품목")}
GROUPS = cj.GROUPS
DET_DROP = 0.025


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 기준선 재현(카드 17) 행별 확률 폴더")
    ap.add_argument("--d4-dir", default=None, help="D4-04 행별 확률 폴더 (안 주면 --dir)")
    ap.add_argument("--syn-csv", required=True)
    ap.add_argument("--golden", default=rj.GOLDEN)
    ap.add_argument("--banned", default=BANNED_TERMS_PATH)
    ap.add_argument("--out-dir", default=rj.OUT_DIR)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="D4-04 자리에 D4-00 을 넣는다 — 차이가 0 이어야 한다")
    a = ap.parse_args(argv)
    out_dir = os.path.abspath(a.out_dir)
    if os.path.commonpath([out_dir, REPO]) == REPO:
        raise SystemExit(f"🔴 요약(JSON · 행 id 포함)을 저장소 안에 쓰지 않는다 (D-249 ⑥): {out_dir}")
    with open(a.syn_csv, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != cj.SYN_SHA:
            raise SystemExit("🔴 정상 문구 CSV 가 권소라 10-11 검수판(f3bfec90…)이 아니다")
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

    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), sdev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    def files(model, mode, s):
        if model == "D4-00" or a.self_test:
            b = os.path.join(a.dir, f"{D400}_seed{s}")
        else:
            b = os.path.join(a.d4_dir or a.dir, f"{D404}_{mode}_seed{s}")
        return f"{b}_dev행별확률.csv", f"{b}_합성정상_행별확률.csv"

    R, W, mismatch = {}, {}, None
    for model in ("D4-00", "D4-04"):
        for s in SEEDS:
            m, w, syn = {}, {}, {}
            for name, (ckey, mode) in COND.items():
                dp, spth = files(model, mode, s)
                th, _ = ca.d324_thresholds(Y, sd.read_probs(dp, sdev), target)
                for l in sd.LABELS:
                    th.setdefault(l, 1.01)
                _, _, rows, prob_of = sw.load_rows(a.golden, dp, labels)
                rs = [dict(r) for r in rows] if name == "무조건부" else conditional_rows([dict(r) for r in rows])
                for r in rs:
                    r.setdefault("labels", [])
                    r["bucket"] = rj.bucket(r)
                res = sw.judge_all(rs, [prob_of[r["id"]] for r in rs], book, th, QUIET_MARGIN, name == "조건부", th)
                m[name] = sw.measure(rs, res)
                w[name] = cj.wrong_confirms(rs, res)
                cos = [i for i, r in enumerate(rs) if r["bucket"] == "pending" and r.get("품목") == "화장품"]
                st = [rj.state_of(v) for v in res]
                m[name]["cos_pending"] = (sum(1 for i in cos if st[i] in rj.PASS_STATES), sum(1 for i in cos if st[i] in rj.QUIET_STATES), len(cos))
                if name == "조건부" and mismatch is None:
                    mismatch = sum(1 for r in rs if r.get("품목") and _eg.product_of(r, True).category != _eg.Category(r["품목"]))
                with open(spth, encoding="utf-8-sig", newline="") as fh:
                    sp = list(csv.DictReader(fh))
                for grp in GROUPS:
                    part = [r for r in sp if r["갈래"] == grp]
                    stc = {}
                    for r in part:
                        cat = _eg.product_of({"품목": src[r["id"]]["품목"]}, True).category if ckey == "cond" else None
                        lp = {l: float(r[f"p_{l}"]) for l in labels}
                        v = stage2_judge(stage1_signals(src[r["id"]]["text"], lp, book, th, margin=QUIET_MARGIN, agree_thresholds=th), category=cat)
                        k = rj.state_of(v)
                        stc[k] = stc.get(k, 0) + 1
                    syn[f"{grp}_{ckey}"] = {"n": len(part), "pass": sum(stc.get(x, 0) for x in rj.PASS_STATES),
                                            "quiet": sum(stc.get(x, 0) for x in rj.QUIET_STATES), "confirmed": stc.get("confirmed:위반", 0)}
            R[(model, s)] = {"dev": m, "syn": syn}
            W[(model, s)] = w
            print(f"  {model} · 시드 {s} — 무조건부 탐지 {m['무조건부']['detected']}/{m['무조건부']['positive']} · 조건부 탐지 {m['조건부']['detected']}/{m['조건부']['positive']} · "
                  f"조건부 조용해진 위반 {m['조건부']['pos_quiet']} · 조건부 틀린 확정 {m['조건부']['errors']}/{m['조건부']['committed']}")
    print(f"[INFO] 조건부 행 중 인코더에 넣은 품목(골든 `품목`)과 판정 로직의 제품 정보(`product_of` · 전제 먼저)가 다른 행: {mismatch}")

    mn = lambda model, fn: statistics.mean(fn(R[(model, s)]) for s in SEEDS)
    per = lambda model, fn: " · ".join(str(fn(R[(model, s)])) for s in SEEDS)
    models = ("D4-00", "D4-04")
    title = "D4-04 보충 — 품목입력 모델을 판정 로직에 넣어 잰 수 (dev · 탐색)" + (" — 자기 검증" if a.self_test else "")
    md = [f"# {title}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 사전 `{dict_sha[:12]}` · 규칙 {g.JUDGED_BY} + 인코더 층(`judge_stage2.py`) · "
          f"판 그대로(D-324 문턱 · 후보 = 합의 = τ · 여유 구간 {QUIET_MARGIN}) · D4-04 는 무조건부 = (나) 모름 · 조건부 = (가) 품목 · "
          f"시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · 건수만 적는다", "",
          "| 지표 | D4-00 | D4-04 |", "|---|---:|---:|"]
    for n, lab in (("무조건부", "첫 판정"), ("조건부", "재판정")):
        P = R[("D4-00", SEEDS[0])]["dev"][n]["positive"]
        pn = R[("D4-00", SEEDS[0])]["dev"][n]["pos_n"]
        row = lambda key, f=".1f": " | ".join(f"{format(mn(mo, lambda x: x['dev'][n][key]), f)} ({per(mo, lambda x: x['dev'][n][key])})" for mo in models)
        md += [f"| **{n} ({lab})** — 탐지 재현율 (/{P}) | {row('detected')} |",
               f"| {n} — 확정 (/{P}) | {row('confirmed')} |",
               f"| {n} — 틀린 확정 | {row('errors')} |",
               f"| {n} — 조용해진 위반 행 (/{pn}) | {row('pos_quiet')} |",
               f"| {n} — D · L 유형 후보 · 위반 확정 | " + " | ".join(f"{mn(mo, lambda x: x['dev'][n]['law_typed']):.1f} · {mn(mo, lambda x: x['dev'][n]['law_confirmed']):.1f}" for mo in models) + " |",
               f"| {n} — 화장품 「유형 없는 위반」 통과 · 조용 (/{R[('D4-00', SEEDS[0])]['dev'][n]['cos_pending'][2]}) | " +
               " | ".join(f"{mn(mo, lambda x: x['dev'][n]['cos_pending'][0]):.1f} · {mn(mo, lambda x: x['dev'][n]['cos_pending'][1]):.1f}" for mo in models) + " |"]
    for grp in GROUPS:
        nn = R[("D4-00", SEEDS[0])]["syn"][f"{grp}_cond"]["n"]
        lab = "**검수 적법 정상 문구**" if grp == "합성정상dev" else f"참고 · {grp}"
        md.append(f"| {lab} — 재판정 통과 · 첫 판정 조용 (/{nn}) | " +
                  " | ".join(f"{mn(mo, lambda x: x['syn'][f'{grp}_cond']['pass']):.1f} · {mn(mo, lambda x: x['syn'][f'{grp}_uncond']['quiet']):.1f}" for mo in models) + " |")
    md.append("| 검수 적법 정상 문구 — 위반 확정 (재판정 · 첫 판정) | " +
              " | ".join(f"{mn(mo, lambda x: x['syn']['합성정상dev_cond']['confirmed']):.1f} · {mn(mo, lambda x: x['syn']['합성정상dev_uncond']['confirmed']):.1f}" for mo in models) + " |")

    b = lambda n, k: mn("D4-00", lambda x: x["dev"][n][k])
    c = lambda n, k: mn("D4-04", lambda x: x["dev"][n][k])
    Pu = R[("D4-00", SEEDS[0])]["dev"]["무조건부"]["positive"]
    checks = [
        ("① 재판정 — 조용해진 위반 행이 늘지 않는다", f"{b('조건부', 'pos_quiet'):.1f} → {c('조건부', 'pos_quiet'):.1f}", c("조건부", "pos_quiet") <= b("조건부", "pos_quiet") + 1e-9),
        ("② 재판정 — 틀린 확정이 늘지 않는다", f"{b('조건부', 'errors'):.1f} → {c('조건부', 'errors'):.1f}", c("조건부", "errors") <= b("조건부", "errors") + 1e-9),
        ("③ 재판정 — D · L 위반 확정 0", f"{c('조건부', 'law_confirmed'):.1f}", c("조건부", "law_confirmed") == 0),
        ("④ 첫 판정 — 탐지 재현율 −2.5%p 이내", f"{(c('무조건부', 'detected') - b('무조건부', 'detected')) / Pu * 100:+.1f}%p",
         (c("무조건부", "detected") - b("무조건부", "detected")) / Pu >= -DET_DROP - 1e-12),
        ("⑤ 첫 판정 — 틀린 확정이 늘지 않는다", f"{b('무조건부', 'errors'):.1f} → {c('무조건부', 'errors'):.1f}", c("무조건부", "errors") <= b("무조건부", "errors") + 1e-9),
        ("⑥ 첫 판정 — D · L 위반 확정 0", f"{c('무조건부', 'law_confirmed'):.1f}", c("무조건부", "law_confirmed") == 0),
    ]
    md += ["", "### 기준 (D4 실험기록 「D4-04 보충 — 판정 로직」 에 먼저 적은 것 · 시드 평균 · D4-00 대비)", "", "| 기준 | 값 | |", "|---|---|---|"]
    md += [f"| {k} | {v} | {'지킴' if ok else '**넘음**'} |" for k, v, ok in checks]
    ok_all = all(ok for _, _, ok in checks)
    md += ["", "**판정 로직 확인 통과** — 채택이 아니다 (팀장 판정)" if ok_all else
           "**판정 로직 확인 탈락** — " + " · ".join(k.split(" — ")[0] for k, _, ok in checks if not ok) + " 을 넘었다",
           "", f"🟡 조건부 행 중 인코더에 넣은 품목(골든 `품목`)과 판정 로직의 제품 정보(`product_of` · 전제 먼저)가 다른 행: {mismatch} — 실제 앱에서는 사용자가 고른 품목 하나가 둘 다에 들어간다"]
    nw = {mo: {n: statistics.mean(len(W[(mo, s)][n]) for s in SEEDS) for n in COND} for mo in models}
    md += ["", "진단 — 확정 유형이 골든 라벨과 겹치지 않는 채점 행(시드 평균): " + " · ".join(f"{mo} 첫 판정 {nw[mo]['무조건부']:.1f} · 재판정 {nw[mo]['조건부']:.1f}" for mo in models)
           + " — 행 목록은 저장소 밖 요약(JSON)에만 있다"]
    print("\n" + "\n".join(md))

    print("\n[진단 · 화면에만] D4-04 의 틀린 확정 행 (id · 정답 · 전제 · 확정 유형 · 까닭)")
    for s in SEEDS:
        for n in COND:
            for x in W[("D4-04", s)][n]:
                print(f"  시드 {s} · {n} · {x['id']} · 정답 {x['gold']} · 전제 {x['premise']} · 확정 {x['confirmed']} · {x['why']}")
    print("[진단 · 화면에만] 재판정에서 조용한 행(위반 · 음성 전부)의 바뀜 — D4-00 대비 (시드별 수 · 위반만은 표의 「조용해진 위반 행」)")
    for s in SEEDS:
        q0, q1 = set(R[("D4-00", s)]["dev"]["조건부"]["quiet"]), set(R[("D4-04", s)]["dev"]["조건부"]["quiet"])
        print(f"  시드 {s} — 새로 조용(통과 · 품목만 보류) {len(q1 - q0)} · 더는 조용하지 않음 {len(q0 - q1)}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"d4_04_judge_dev_{stamp}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fo:
        json.dump({"at": stamp, "golden_sha256": gsha, "dev_mark": mark, "banned_terms_sha256": dict_sha, "judged_by": g.JUDGED_BY,
                   "result": {f"{mo}_seed{s}": R[(mo, s)] for mo in models for s in SEEDS},
                   "wrong_confirms": {f"{mo}_seed{s}": W[(mo, s)] for mo in models for s in SEEDS}},
                  fo, ensure_ascii=False, indent=1, default=str)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {path}")
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
