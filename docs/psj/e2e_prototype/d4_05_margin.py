"""D4-05 여유구간 — 보류 경계(QUIET_MARGIN)를 다시 훑는다 (박수진 · 2026-10-12 · 판정 로직 · 학습 없음)

판정 로직은 후보가 없어도 어느 유형의 확률이 τ × m 이상이면 보류로 둔다(`judge_stage1.QUIET_MARGIN` = 0.5).
D4-00 의 확률을 그대로 두고 m 만 0.5 · 0.6 · 0.7 · 0.8 · 0.9 · 1.0(끔)으로 바꿔 판정 로직(사전 + 인코더 층)에 넣는다.
후보 = 합의 = τ (k = 1.0) · D-324 문턱(card17_adopt.py 와 같은 규칙 · 시드마다) · 판 그대로.

  uv run python docs\\psj\\e2e_prototype\\d4_05_margin.py --dir <D4-00 행별 확률 폴더> --syn-csv <권소라 10-11 검수판 CSV> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_05_margin.py --dir <D4-00 행별 확률 폴더> --d4-dir <D4-04 행별 확률 폴더> --syn-csv <검수판 CSV> --out-md docs\\psj\\reports\\D4-05_여유구간_dev_YYYYMMDD.md

  · 기준 (D4 실험기록 「D4-05 여유구간」 에 먼저 적었다 · D4-00 m 0.5 대비 · 무조건부 · 조건부 두 조건)
      목표   검수 적법 정상 문구 조건부 통과 146.2행 이상 (/171 · 시드 평균)
      한도 ① 조용해진 위반 행(통과 · 품목만 보류로 간 위반 행)이 1행 넘게 늘지 않는다 — 시드 평균과 세 시드 각각 모두
               (시드 s 는 D4-00 m 0.5 의 같은 시드 s 와 비교)
           ② 틀린 확정이 늘지 않는다 ③ D · L 위반 확정 0 ④ 검수 적법 정상 문구 위반 확정 0 (② ~ ④ 는 시드 평균)
      판정   한도를 모두 지키고 목표를 채운 m 중 정상 문구 조건부 통과(시드 평균)가 가장 많은 것 (같으면 작은 m) → 통과
             없으면 탈락 → 0.5 를 그대로 두고 D4-05 를 닫는다
  · 참고 — D4-04(첫 판정 (나) 모름 · 재판정 (가) 품목)에도 같은 m 을 걸어 본 수 (`--d4-dir` · 판정에 쓰지 않는다)
  · `--self-test` — D4-00 m 0.5 가 card17_judge.py 의 수(v10_카드17_판정로직_정상문구_dev_20261012.md)와 같은지 본다
🔴 dev 전용 (D-175). 행 id 가 든 요약(JSON)은 저장소 밖(`--out-dir`)에 쓴다 (D-249 ⑥).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import statistics
from collections import Counter

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
COND = {"무조건부": ("uncond", "모름"), "조건부": ("cond", "품목")}
GROUPS = cj.GROUPS
MARGINS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
BASE_M = 0.5
GOAL = 146.2          # 검수 적법 정상 문구 조건부 통과 (/171 · 시드 평균) = 127.3 + 37.7 / 2
LIM_QUIET = 1         # 한도 ① — 조용해진 위반 행 증가 (시드 평균 · 세 시드 각각)
#: `--self-test` 대조 값 — v10_카드17_판정로직_정상문구_dev_20261012.md 의 「채택 판 후보」(= D4-00) 열
SELF = {"syn_cond_pass": (134, 131, 117), "uncond_det": (414, 421, 423), "cond_det": (163, 168, 168),
        "uncond_pos_quiet": "1.0", "cond_pos_quiet": "0.7"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00(카드 17) 행별 확률 폴더")
    ap.add_argument("--d4-dir", default=None, help="D4-04 행별 확률 폴더 (주면 참고로 같은 m 을 걸어 본다)")
    ap.add_argument("--syn-csv", required=True)
    ap.add_argument("--golden", default=rj.GOLDEN)
    ap.add_argument("--banned", default=BANNED_TERMS_PATH)
    ap.add_argument("--out-dir", default=rj.OUT_DIR)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="D4-00 m 0.5 를 카드 17 판정 로직 수와 대조하고 끝낸다")
    a = ap.parse_args(argv)
    if QUIET_MARGIN != BASE_M:
        raise SystemExit(f"🔴 judge_stage1.QUIET_MARGIN 이 {QUIET_MARGIN} 이다 — 등록한 기준점(0.5)과 다르다")
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
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark} · 사전 {dict_sha[:12]} · 규칙 {g.JUDGED_BY} + 인코더 층 · k 1.0 · D-324 문턱")

    # D-324 문턱의 재현율 목표 — 기준선 재현(카드 17)의 시드 평균 (d4_04_judge.py 와 같다)
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), sdev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    def files(model, mode, s):
        b = os.path.join(a.dir, f"{D400}_seed{s}") if model == "D4-00" else os.path.join(a.d4_dir, f"{D404}_{mode}_seed{s}")
        return f"{b}_dev행별확률.csv", f"{b}_합성정상_행별확률.csv"

    models = ["D4-00"] + (["D4-04"] if a.d4_dir and not a.self_test else [])
    margins = [BASE_M] if a.self_test else MARGINS
    R, NEWQ = {}, {}
    for model in models:
        for s in SEEDS:
            prep = {}
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
                with open(spth, encoding="utf-8-sig", newline="") as fh:
                    sp = list(csv.DictReader(fh))
                syn = {grp: [(src[r["id"]]["text"], {l: float(r[f"p_{l}"]) for l in labels},
                              _eg.product_of({"품목": src[r["id"]]["품목"]}, True).category if ckey == "cond" else None)
                             for r in sp if r["갈래"] == grp] for grp in GROUPS}
                prep[name] = (th, rs, [prob_of[r["id"]] for r in rs], syn)
            for m in margins:
                dev, synm = {}, {}
                for name, (ckey, _) in COND.items():
                    th, rs, probs, syn = prep[name]
                    res = sw.judge_all(rs, probs, book, th, m, name == "조건부", th)
                    dev[name] = sw.measure(rs, res)
                    dev[name]["pos_quiet_ids"] = sorted(r["id"] for r, v in zip(rs, res)
                                                        if r["bucket"] in ("scored", "pending") and rj.state_of(v) in rj.QUIET_STATES)
                    for grp, part in syn.items():
                        st = Counter(rj.state_of(stage2_judge(stage1_signals(t, lp, book, th, margin=m, agree_thresholds=th), category=cat))
                                     for t, lp, cat in part)
                        synm[f"{grp}_{ckey}"] = {"n": len(part), "pass": sum(st[x] for x in rj.PASS_STATES),
                                                 "quiet": sum(st[x] for x in rj.QUIET_STATES), "confirmed": st["confirmed:위반"]}
                R[(model, m, s)] = {"dev": dev, "syn": synm}
            if model == "D4-00":
                byid = {r["id"]: r for r in prep["무조건부"][1]}
                for m in margins:
                    for name in COND:
                        new = set(R[(model, m, s)]["dev"][name]["pos_quiet_ids"]) - set(R[(model, BASE_M, s)]["dev"][name]["pos_quiet_ids"])
                        NEWQ[(m, s, name)] = [{"id": i, "provenance": byid[i].get("provenance") or "—", "전제": byid[i].get("전제") or "없음",
                                               "gold": [x for x in (byid[i].get("labels") or [])]} for i in sorted(new)]
            print(f"  {model} · 시드 {s} — " + " · ".join(
                f"m {m}: 정상 문구 재판정 통과 {R[(model, m, s)]['syn']['합성정상dev_cond']['pass']} · 조용해진 위반 "
                f"{R[(model, m, s)]['dev']['무조건부']['pos_quiet']}/{R[(model, m, s)]['dev']['조건부']['pos_quiet']}" for m in margins))

    mn = lambda model, m, fn: statistics.mean(fn(R[(model, m, s)]) for s in SEEDS)
    per = lambda model, m, fn: " · ".join(str(fn(R[(model, m, s)])) for s in SEEDS)

    if a.self_test:
        got = {"syn_cond_pass": tuple(R[("D4-00", BASE_M, s)]["syn"]["합성정상dev_cond"]["pass"] for s in SEEDS),
               "uncond_det": tuple(R[("D4-00", BASE_M, s)]["dev"]["무조건부"]["detected"] for s in SEEDS),
               "cond_det": tuple(R[("D4-00", BASE_M, s)]["dev"]["조건부"]["detected"] for s in SEEDS),
               "uncond_pos_quiet": f"{mn('D4-00', BASE_M, lambda x: x['dev']['무조건부']['pos_quiet']):.1f}",
               "cond_pos_quiet": f"{mn('D4-00', BASE_M, lambda x: x['dev']['조건부']['pos_quiet']):.1f}"}
        bad = {k: (SELF[k], got[k]) for k in SELF if SELF[k] != got[k]}
        for k in SELF:
            print(f"  {'OK ' if k not in bad else '❌ '} {k}: 카드 17 {SELF[k]} · 지금 {got[k]}")
        if bad:
            raise SystemExit("🔴 자기 검증 실패 — D4-00 m 0.5 가 카드 17 판정 로직 수와 다르다")
        print("[OK] 자기 검증 통과 — D4-00 m 0.5 = 카드 17 판정 로직 수")
        return 0

    # ── 기준 판정 (D4-00 만) ──
    b0 = lambda n, k: mn("D4-00", BASE_M, lambda x: x["dev"][n][k])
    verdict = {}
    for m in MARGINS:
        q = {n: [R[("D4-00", m, s)]["dev"][n]["pos_quiet"] - R[("D4-00", BASE_M, s)]["dev"][n]["pos_quiet"] for s in SEEDS] for n in COND}
        goal_v = mn("D4-00", m, lambda x: x["syn"]["합성정상dev_cond"]["pass"])
        c = {
            "목표": (goal_v >= GOAL - 1e-9, f"{goal_v:.1f}"),
            "①": (all(statistics.mean(q[n]) <= LIM_QUIET + 1e-9 and max(q[n]) <= LIM_QUIET for n in COND),
                  " / ".join(f"{statistics.mean(q[n]):+.1f} ({' · '.join(f'{d:+d}' for d in q[n])})" for n in COND)),
            "②": (all(mn("D4-00", m, lambda x: x["dev"][n]["errors"]) <= b0(n, "errors") + 1e-9 for n in COND),
                  " / ".join(f"{mn('D4-00', m, lambda x: x['dev'][n]['errors']):.1f}" for n in COND)),
            "③": (all(mn("D4-00", m, lambda x: x["dev"][n]["law_confirmed"]) == 0 for n in COND),
                  " / ".join(f"{mn('D4-00', m, lambda x: x['dev'][n]['law_confirmed']):.1f}" for n in COND)),
            "④": (all(mn("D4-00", m, lambda x: x["syn"][f"합성정상dev_{ck}"]["confirmed"]) == 0 for ck, _ in COND.values()),
                  " / ".join(f"{mn('D4-00', m, lambda x: x['syn'][f'합성정상dev_{ck}']['confirmed']):.1f}" for ck, _ in COND.values())),
        }
        verdict[m] = (c, goal_v)
    ok = [m for m in MARGINS if all(v[0] for v in verdict[m][0].values())]
    pick = max(ok, key=lambda m: (verdict[m][1], -m)) if ok else None

    title = "D4-05 여유구간 — 보류 경계 QUIET_MARGIN 다시 훑기 (dev · 판정 로직 · 학습 없음)"
    md = [f"# {title}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 사전 `{dict_sha[:12]}` · 규칙 {g.JUDGED_BY} + 인코더 층(`judge_stage2.py`) · "
          f"D-324 문턱 · 후보 = 합의 = τ (k 1.0) · 여유 구간 m 만 바꾼다 · 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · 건수만 적는다", ""]
    for model in models:
        P = {n: R[(model, BASE_M, SEEDS[0])]["dev"][n]["positive"] for n in COND}
        PN = {n: R[(model, BASE_M, SEEDS[0])]["dev"][n]["pos_n"] for n in COND}
        LN = {n: R[(model, BASE_M, SEEDS[0])]["dev"][n]["law_n"] for n in COND}
        head = "D4-00 (판정)" if model == "D4-00" else "D4-04 (참고 · 첫 판정 (나) 모름 · 재판정 (가) 품목 · 판정에 쓰지 않는다)"
        md += [f"## {head}", "", "### 위반 쪽", "",
               f"| m | 첫 판정 탐지 (/{P['무조건부']}) | 재판정 탐지 (/{P['조건부']}) | 조용해진 위반 — 첫 판정 (/{PN['무조건부']}) | "
               f"조용해진 위반 — 재판정 (/{PN['조건부']}) | 확정 (첫 · 재) | 틀린 확정 (첫 · 재) | D · L 조용 (첫 /{LN['무조건부']} · 재 /{LN['조건부']}) | D · L 위반 확정 |",
               "|---:|---:|---:|---:|---:|---|---|---|---|"]
        for m in MARGINS:
            v = lambda n, k: f"{mn(model, m, lambda x: x['dev'][n][k]):.1f}"
            md.append(f"| {m}{' (지금)' if m == BASE_M else ''}{' (끔)' if m == 1.0 else ''} | "
                      f"{v('무조건부', 'detected')} | {v('조건부', 'detected')} | "
                      f"{v('무조건부', 'pos_quiet')} ({per(model, m, lambda x: x['dev']['무조건부']['pos_quiet'])}) | "
                      f"{v('조건부', 'pos_quiet')} ({per(model, m, lambda x: x['dev']['조건부']['pos_quiet'])}) | "
                      f"{v('무조건부', 'confirmed')} · {v('조건부', 'confirmed')} | {v('무조건부', 'errors')} · {v('조건부', 'errors')} | "
                      f"{v('무조건부', 'law_quiet')} · {v('조건부', 'law_quiet')} | {v('무조건부', 'law_confirmed')} · {v('조건부', 'law_confirmed')} |")
        nn = {grp: R[(model, BASE_M, SEEDS[0])]["syn"][f"{grp}_cond"]["n"] for grp in GROUPS}
        md += ["", "### 정상 문구 쪽", "",
               f"| m | **검수 적법 정상 문구** — 재판정 통과 (/{nn['합성정상dev']}) | 첫 판정 조용 | 위반 확정 (재 · 첫) | "
               + " | ".join(f"참고 · {grp} — 재판정 통과 (/{nn[grp]})" for grp in GROUPS[1:]) + " |",
               "|---:|---:|---:|---|" + "---:|" * (len(GROUPS) - 1)]
        for m in MARGINS:
            sf = lambda key, k: f"{mn(model, m, lambda x: x['syn'][key][k]):.1f}"
            md.append(f"| {m} | {sf('합성정상dev_cond', 'pass')} ({per(model, m, lambda x: x['syn']['합성정상dev_cond']['pass'])}) | "
                      f"{sf('합성정상dev_uncond', 'quiet')} | {sf('합성정상dev_cond', 'confirmed')} · {sf('합성정상dev_uncond', 'confirmed')} | "
                      + " | ".join(sf(f"{grp}_cond", "pass") for grp in GROUPS[1:]) + " |")
        md.append("")

    md += ["## 기준 (D4 실험기록 「D4-05 여유구간」 에 먼저 적은 것 · D4-00 m 0.5 대비)", "",
           f"목표 — 정상 문구 재판정 통과 {GOAL} 이상 · ① 조용해진 위반 +{LIM_QUIET} 이내 (첫 판정 / 재판정 · 평균 (시드별 증가) · 평균과 세 시드 각각) · "
           "② 틀린 확정이 늘지 않는다 (첫 / 재) · ③ D · L 위반 확정 0 (첫 / 재) · ④ 정상 문구 위반 확정 0 (재 / 첫)", "",
           "| m | 목표 | ① | ② | ③ | ④ | 결과 |", "|---:|---|---|---|---|---|---|"]
    for m in MARGINS:
        c = verdict[m][0]
        cell = lambda k: f"{c[k][1]} {'✓' if c[k][0] else '**✗**'}"
        res = "**고름**" if m == pick else ("모두 지킴" if m in ok else "—")
        md.append(f"| {m} | {cell('목표')} | {cell('①')} | {cell('②')} | {cell('③')} | {cell('④')} | {res} |")
    md += ["", f"**통과 — m {pick}** (정상 문구 재판정 통과 {verdict[pick][1]:.1f}/171) · 채택이 아니다 — 팀장 판정 · `QUIET_MARGIN` 변경은 판정 파라미터 변경" if pick is not None
           else "**탈락** — 목표와 한도를 모두 지킨 m 이 없다 → 0.5 를 그대로 두고 D4-05 를 닫는다", ""]

    md += ["### 새로 조용해진 위반 행 — 정답 유형 · 출처 (D4-00 · m 0.5 대비 · 세 시드 합 · 건수만)", ""]
    for m in MARGINS[1:]:
        for name in COND:
            xs = [x for s in SEEDS for x in NEWQ[(m, s, name)]]
            if not xs:
                continue
            gold = Counter(t for x in xs for t in (x["gold"] or ["(유형 없음)"]))
            prov = Counter(x["provenance"] for x in xs)
            md.append(f"- m {m} · {name} — {len(xs)}행 · 정답 유형 " + " · ".join(f"{k} {v}" for k, v in gold.most_common())
                      + " · 출처 " + " · ".join(f"{k} {v}" for k, v in prov.most_common()))
    print("\n" + "\n".join(md))

    print("\n[진단 · 화면에만] 새로 조용해진 위반 행 (D4-00 · m 0.5 대비 · id · 정답 · 전제 · 출처)")
    for m in MARGINS[1:]:
        for s in SEEDS:
            for name in COND:
                for x in NEWQ[(m, s, name)]:
                    print(f"  m {m} · 시드 {s} · {name} · {x['id']} · 정답 {x['gold']} · 전제 {x['전제']} · {x['provenance']}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"d4_05_margin_dev_{stamp}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fo:
        json.dump({"at": stamp, "golden_sha256": gsha, "dev_mark": mark, "banned_terms_sha256": dict_sha, "judged_by": g.JUDGED_BY,
                   "margins": MARGINS, "goal": GOAL, "lim_quiet": LIM_QUIET, "pick": pick,
                   "result": {f"{mo}_m{m}_seed{s}": R[(mo, m, s)] for mo in models for m in MARGINS for s in SEEDS},
                   "new_quiet_violations": {f"m{m}_seed{s}_{n}": NEWQ[(m, s, n)] for m in MARGINS for s in SEEDS for n in COND}},
                  fo, ensure_ascii=False, indent=1, default=str)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {path}")
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
