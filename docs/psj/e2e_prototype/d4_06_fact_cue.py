"""D4-06 사실전제 — 사실 주장 표지 규칙으로 사실 확인 분기 (박수진 · 2026-10-12 · 판정 로직 · 학습 없음)

판정이 조용(통과 · 판정대상아님 · 품목만 보류)인 문장에 **사실 주장 표지**가 있으면 「사실확인 보류」로 바꾼다.
조용하지 않은 문장(보류 · 확정)은 건드리지 않는다 — 위반이 통과로 가는 일은 생기지 않는다.
D4-00 확률 그대로 · D-324 문턱 · k 1.0 · 여유 구간 0.5(D4-05) · 판 그대로.

  uv run python docs\\psj\\e2e_prototype\\d4_06_fact_cue.py --dir <D4-00 행별 확률 폴더> --syn-csv <권소라 10-11 검수판 CSV> --self-test
  uv run python docs\\psj\\e2e_prototype\\d4_06_fact_cue.py --dir <D4-00 행별 확률 폴더> --syn-csv <검수판 CSV> --out-md docs\\psj\\reports\\D4-06_사실전제_dev_YYYYMMDD.md

  · 기준 (D4 실험기록 「D4-06 사실전제」 에 먼저 적었다 · 시드 평균 · D4-00 대비 · 재판정 = 조건부)
      목표   적법(사실 전제) 재판정 「통과」 중 「사실확인 보류」로 옮겨 간 행 71.0 이상 (D4-00 통과 142.0 의 절반)
      한도 ① 검수 적법 정상 문구 재판정 통과 감소 5행 이내
           ② D · L 음성 재판정 조용 감소 4행 이내
           ③ 적법(사실 전제) · 정상 문구 위반 확정 0 (재판정 · 첫 판정)
      판정   모두 지키면 통과 → 팀장 보고 · 못 지키면 탈락 → 인코더 칸(사실_전제) 검토를 팀장에게 묻는다
  · 「사실확인 보류」 — 계약의 보류 사유(HoldReason · DB 와 같은 여섯)에 사실 확인이 없다. 프로토타입에서는 보류(low_conf) + `fact_hold` 표시로 센다.
    `FactBranch` 를 채우는 노드 · 사전 반영은 팀장 판정이다 (D-308 ④′ · D-313 결정 4).
  · `--self-test` — 규칙을 끄면 카드 17 판정 로직 수(v10_카드17_판정로직_정상문구_dev_20261012.md)와 같은지 본다
🔴 dev 전용 (D-175). 행 id 가 든 요약(JSON)은 저장소 밖(`--out-dir`)에 쓴다 (D-249 ⑥). 문장은 집계표에 쓰지 않는다.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import statistics
from collections import Counter

import card17_adopt as ca
import card17_judge as cj
import judge_stage2 as s2
import run_judge_dist as rj
import score_encoder_dev as sd
import sweep_cand_threshold as sw
from judge_stage1 import BANNED_TERMS_PATH, QUIET_MARGIN, REPO, load_banned_terms, stage1_signals
from judge_stage2 import stage2_judge
from app import graph as g
from app.contracts import HoldReason, Outcome, Verdict
from scripts.eval_graph import conditional_rows
from scripts import eval_graph as _eg

SEEDS = ca.SEEDS
D400 = ca.CAND
COND = {"무조건부": "uncond", "조건부": "cond"}
GROUPS = cj.GROUPS            # 합성정상dev · 참고-적법(사실 전제) · 참고-조건부 · 애매
FACT = "참고-적법(사실 전제)"
GOAL_MOVED = 71.0
LIM_SYN_PASS = 5
LIM_LAW_QUIET = 4

#: 🔒 사실 주장 표지 — D4 실험기록 「D4-06」 등록(10-12 · 결과 전)에 고정한 목록. 결과를 보고 고치지 않는다.
#:    법 · 계약에서만 가져왔다 — D-308 FactKind(수상_상장 · 인증 · 원재료) · D-313 결정 4(인증 · 승인류) · 지시서 §3 ⑨
#:    ⛔ 생성기의 CERT_WORDS(docs/ksr/llm_copy/filters.py)는 쓰지 않는다 — 측정 문장을 만든 목록이다
CUES = {
    "수상_상장": r"수상|상장|브랜드\s*대상|대상\s*(?:수상|선정)|금상|은상|동상|어워드|선정",
    "인증_승인": r"인증|승인|허가|특허|HACCP|해썹|GMP|ISO|FDA|식약처|유기농|친환경|무농약|할랄|비건",
    "원재료": r"국내산|(?<!한)국산(?!업)|무첨가|천연",
}
CUE_RE = {k: re.compile(p) for k, p in CUES.items()}
#: `--self-test` 대조 값 — v10_카드17_판정로직_정상문구_dev_20261012.md 의 「채택 판 후보」(= D4-00) 열
SELF = {"syn_cond_pass": (134, 131, 117), "fact_cond_pass": (150, 154, 122), "uncond_det": (414, 421, 423), "cond_det": (163, 168, 168)}


def cue_kinds(text):
    return [k for k, rx in CUE_RE.items() if rx.search(text)]


def fact_hold(v, use_rule=True):
    """조용한 판정 + 사실 주장 표지 → 사실확인 보류. 그 밖에는 그대로 돌려준다. (새 판정, 바뀐 표지 종류 또는 None)"""
    if not use_rule or rj.state_of(v) not in rj.QUIET_STATES:
        return v, None
    kinds = cue_kinds(v["text"])
    if not kinds:
        return v, None
    j = v["state"]["sentences"][0]
    nj = s2._remake(j, verdict=Verdict.hold, hold_reason=HoldReason.low_conf, not_claim=False, violations=[], risk=s2.R0)
    nv = dict(v)
    nv["pass"] = False
    nv.update(verdict="hold", hold_reason=HoldReason.low_conf.value, not_claim=False, violations=[],
              pass_blocked=False, fact_hold=True, why="사실 주장 표지 → 사실확인 보류 (D4-06 · D-308 ④′)",
              outcome=Outcome.hold.value, state={**v["state"], "sentences": [nj], "outcome": Outcome.hold})
    return nv, kinds


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00(카드 17) 행별 확률 폴더")
    ap.add_argument("--syn-csv", required=True)
    ap.add_argument("--golden", default=rj.GOLDEN)
    ap.add_argument("--banned", default=BANNED_TERMS_PATH)
    ap.add_argument("--out-dir", default=rj.OUT_DIR)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="규칙을 끈 수를 카드 17 판정 로직 수와 대조하고 끝낸다")
    a = ap.parse_args(argv)
    if QUIET_MARGIN != 0.5:
        raise SystemExit(f"🔴 judge_stage1.QUIET_MARGIN 이 {QUIET_MARGIN} 이다 — D4-05 에서 유지한 0.5 와 다르다")
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
    print(f"[INFO] golden {gsha[:12]} · dev {len(sdev)}행 · 지문 {mark} · 사전 {dict_sha[:12]} · 규칙 {g.JUDGED_BY} + 인코더 층 · k 1.0 · D-324 문턱 · 여유 구간 {QUIET_MARGIN}")

    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), sdev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    arms = ("끔",) if a.self_test else ("끔", "켬")
    R, FLIP = {}, {}
    for s in SEEDS:
        base = os.path.join(a.dir, f"{D400}_seed{s}")
        dp, spth = f"{base}_dev행별확률.csv", f"{base}_합성정상_행별확률.csv"
        th, _ = ca.d324_thresholds(Y, sd.read_probs(dp, sdev), target)
        for l in sd.LABELS:
            th.setdefault(l, 1.01)
        _, _, rows, prob_of = sw.load_rows(a.golden, dp, labels)
        with open(spth, encoding="utf-8-sig", newline="") as fh:
            sp = list(csv.DictReader(fh))
        judged = {}
        for name, ckey in COND.items():
            rs = [dict(r) for r in rows] if name == "무조건부" else conditional_rows([dict(r) for r in rows])
            for r in rs:
                r.setdefault("labels", [])
                r["bucket"] = rj.bucket(r)
            res = sw.judge_all(rs, [prob_of[r["id"]] for r in rs], book, th, QUIET_MARGIN, name == "조건부", th)
            syn = {}
            for grp in GROUPS:
                part = [r for r in sp if r["갈래"] == grp]
                syn[grp] = [(r["id"], stage2_judge(stage1_signals(src[r["id"]]["text"], {l: float(r[f"p_{l}"]) for l in labels}, book, th,
                                                                  margin=QUIET_MARGIN, agree_thresholds=th),
                                                   category=_eg.product_of({"품목": src[r["id"]]["품목"]}, True).category if ckey == "cond" else None))
                             for r in part]
            judged[name] = (rs, res, syn)
        for arm in arms:
            on = arm == "켬"
            dev, synm = {}, {}
            for name, ckey in COND.items():
                rs, res, syn = judged[name]
                res2, flips = [], []
                for r, v in zip(rs, res):
                    nv, kinds = fact_hold(v, on)
                    res2.append(nv)
                    if kinds:
                        flips.append({"id": r["id"], "bucket": r["bucket"], "from": rj.state_of(v), "kinds": kinds,
                                      "gold": list(r.get("labels") or []), "provenance": r.get("provenance") or "—"})
                m = sw.measure(rs, res2)
                m["flips"] = flips
                dev[name] = m
                for grp, items in syn.items():
                    st, kc, frm = Counter(), Counter(), Counter()
                    for _, v in items:
                        nv, kinds = fact_hold(v, on)
                        st[rj.state_of(nv)] += 1
                        if kinds:
                            kc.update(kinds)
                            frm[rj.state_of(v)] += 1
                    synm[f"{grp}_{ckey}"] = {"n": len(items), "pass": sum(st[x] for x in rj.PASS_STATES),
                                             "quiet": sum(st[x] for x in rj.QUIET_STATES), "confirmed": st["confirmed:위반"],
                                             "fact": sum(frm.values()), "fact_from": dict(frm), "fact_kinds": dict(kc)}
            R[(arm, s)] = {"dev": dev, "syn": synm}
            if on:
                FLIP[s] = {n: dev[n]["flips"] for n in COND}
        print(f"  시드 {s} — " + " · ".join(
            f"규칙 {arm}: 사실 전제 재판정 통과 {R[(arm, s)]['syn'][f'{FACT}_cond']['pass']} · 정상 문구 재판정 통과 "
            f"{R[(arm, s)]['syn']['합성정상dev_cond']['pass']} · D · L 재판정 조용 {R[(arm, s)]['dev']['조건부']['law_quiet']}" for arm in arms))

    mn = lambda arm, fn: statistics.mean(fn(R[(arm, s)]) for s in SEEDS)
    per = lambda arm, fn: " · ".join(str(fn(R[(arm, s)])) for s in SEEDS)

    if a.self_test:
        got = {"syn_cond_pass": tuple(R[("끔", s)]["syn"]["합성정상dev_cond"]["pass"] for s in SEEDS),
               "fact_cond_pass": tuple(R[("끔", s)]["syn"][f"{FACT}_cond"]["pass"] for s in SEEDS),
               "uncond_det": tuple(R[("끔", s)]["dev"]["무조건부"]["detected"] for s in SEEDS),
               "cond_det": tuple(R[("끔", s)]["dev"]["조건부"]["detected"] for s in SEEDS)}
        bad = {k for k in SELF if SELF[k] != got[k]}
        for k in SELF:
            print(f"  {'❌ ' if k in bad else 'OK '} {k}: 카드 17 {SELF[k]} · 지금 {got[k]}")
        if bad:
            raise SystemExit("🔴 자기 검증 실패 — 규칙을 끈 수가 카드 17 판정 로직 수와 다르다")
        print("[OK] 자기 검증 통과 — 규칙을 끄면 카드 17 판정 로직 수와 같다")
        return 0

    sv = lambda arm, key, k: mn(arm, lambda x: x["syn"][key][k])
    moved = sv("끔", f"{FACT}_cond", "pass") - sv("켬", f"{FACT}_cond", "pass")   # 통과 → 사실확인 보류 (규칙은 통과를 다른 데로 보내지 않는다)
    checks = [
        ("목표 — 사실 전제 재판정 통과 → 사실확인 보류 71.0행 이상",
         f"{moved:.1f} (통과 {sv('끔', f'{FACT}_cond', 'pass'):.1f} → {sv('켬', f'{FACT}_cond', 'pass'):.1f})", moved >= GOAL_MOVED - 1e-9),
        ("① 검수 적법 정상 문구 재판정 통과 감소 5행 이내",
         f"{sv('끔', '합성정상dev_cond', 'pass'):.1f} → {sv('켬', '합성정상dev_cond', 'pass'):.1f}",
         sv("끔", "합성정상dev_cond", "pass") - sv("켬", "합성정상dev_cond", "pass") <= LIM_SYN_PASS + 1e-9),
        ("② D · L 음성 재판정 조용 감소 4행 이내",
         f"{mn('끔', lambda x: x['dev']['조건부']['law_quiet']):.1f} → {mn('켬', lambda x: x['dev']['조건부']['law_quiet']):.1f}",
         mn("끔", lambda x: x["dev"]["조건부"]["law_quiet"]) - mn("켬", lambda x: x["dev"]["조건부"]["law_quiet"]) <= LIM_LAW_QUIET + 1e-9),
        ("③ 사실 전제 · 정상 문구 위반 확정 0 (재판정 · 첫 판정)",
         " · ".join(f"{sv('켬', f'{grp}_{ck}', 'confirmed'):.1f}" for grp in ("합성정상dev", FACT) for ck in COND.values()),
         all(sv("켬", f"{grp}_{ck}", "confirmed") == 0 for grp in ("합성정상dev", FACT) for ck in COND.values())),
    ]
    ok_all = all(ok for _, _, ok in checks)

    title = "D4-06 사실전제 — 사실 주장 표지 규칙으로 사실 확인 분기 (dev · 판정 로직 · 학습 없음)"
    md = [f"# {title}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 사전 `{dict_sha[:12]}` · 규칙 {g.JUDGED_BY} + 인코더 층(`judge_stage2.py`) · "
          f"D4-00 확률 · D-324 문턱 · 후보 = 합의 = τ (k 1.0) · 여유 구간 {QUIET_MARGIN} · 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · "
          "「규칙 끔」 = D4-00 · 건수만 적는다", "",
          "사실 주장 표지 (등록에 고정) — " + " · ".join(f"{k} `{p}`" for k, p in CUES.items()), "",
          "## 정상 문구 쪽 (검수판)", "",
          "| 묶음 | 판정 | 규칙 끔 — 통과 | 규칙 켬 — 통과 | 사실확인 보류로 옮김 | 위반 확정 |", "|---|---|---:|---:|---:|---:|"]
    for grp in GROUPS:
        nn = R[("끔", SEEDS[0])]["syn"][f"{grp}_cond"]["n"]
        lab = {"합성정상dev": "**검수 적법 정상 문구**", FACT: "**적법(사실 전제)**"}.get(grp, f"참고 · {grp}")
        for name, ck in COND.items():
            key = f"{grp}_{ck}"
            md.append(f"| {lab} (/{nn}) | {'재판정' if ck == 'cond' else '첫 판정'} | "
                      f"{sv('끔', key, 'pass'):.1f} ({per('끔', lambda x: x['syn'][key]['pass'])}) | "
                      f"{sv('켬', key, 'pass'):.1f} ({per('켬', lambda x: x['syn'][key]['pass'])}) | "
                      f"{sv('켬', key, 'fact'):.1f} | {sv('켬', key, 'confirmed'):.1f} |")
    md += ["", "첫 판정의 「통과」 칸은 확정 통과만이다 — 첫 판정은 품목을 몰라 조용한 문장도 대부분 「품목만 보류」라 통과가 적다. 사실확인 보류로 옮긴 수는 조용한 문장(통과 · 품목만 보류) 전체에서 센다.", ""]

    md += ["## 위반 쪽 (공통 dev)", "",
           "| 판정 | 규칙 | 탐지 | 확정 | 틀린 확정 | 조용해진 위반 | D · L 조용 | D · L 위반 확정 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for name in COND:
        P = R[("끔", SEEDS[0])]["dev"][name]["positive"]
        PN = R[("끔", SEEDS[0])]["dev"][name]["pos_n"]
        LN = R[("끔", SEEDS[0])]["dev"][name]["law_n"]
        for arm in ("끔", "켬"):
            v = lambda k: f"{mn(arm, lambda x: x['dev'][name][k]):.1f}"
            md.append(f"| {name} | {arm} | {v('detected')} /{P} | {v('confirmed')} | {v('errors')} | {v('pos_quiet')} /{PN} | "
                      f"{v('law_quiet')} /{LN} ({per(arm, lambda x: x['dev'][name]['law_quiet'])}) | {v('law_confirmed')} |")
    md.append("")

    md += ["## 기준 (D4 실험기록 「D4-06 사실전제」 에 먼저 적은 것 · 시드 평균 · D4-00 대비)", "", "| 기준 | 값 | |", "|---|---|---|"]
    md += [f"| {k} | {v} | {'지킴' if ok else '**못 지킴**'} |" for k, v, ok in checks]
    md += ["", "**통과** — 근거(수 · 낱말 목록)를 들고 팀장 보고 · 채택이 아니다 (사전 · 그래프 반영은 팀장 판정 · D-313)" if ok_all else
           "**탈락** — " + " · ".join(k.split(" — ")[0] for k, _, ok in checks if not ok) + " → 인코더 칸(사실_전제) 검토를 팀장에게 묻는다", ""]

    md += ["## 참고 — 규칙이 바꾼 문장 (세 시드 합 · 건수만)", ""]
    for grp in GROUPS:
        key = f"{grp}_cond"
        kc = sum((Counter(R[("켬", s)]["syn"][key]["fact_kinds"]) for s in SEEDS), Counter())
        fr = sum((Counter(R[("켬", s)]["syn"][key]["fact_from"]) for s in SEEDS), Counter())
        if kc:
            md.append(f"- {grp} · 재판정 — 표지 " + " · ".join(f"{k} {v}" for k, v in kc.most_common()) +
                      " · 바뀌기 전 " + " · ".join(f"{k} {v}" for k, v in fr.most_common()))
    for name in COND:
        xs = [x for s in SEEDS for x in FLIP[s][name]]
        if not xs:
            continue
        bk = Counter(x["bucket"] for x in xs)
        kc = Counter(k for x in xs for k in x["kinds"])
        gold = Counter(t for x in xs if x["bucket"] in ("scored", "pending") for t in (x["gold"] or ["(유형 없음)"]))
        md.append(f"- dev · {name} — {len(xs)}행 · 갈래 " + " · ".join(f"{k} {v}" for k, v in bk.most_common()) +
                  " · 표지 " + " · ".join(f"{k} {v}" for k, v in kc.most_common()) +
                  (" · 위반 행의 정답 유형 " + " · ".join(f"{k} {v}" for k, v in gold.most_common()) if gold else ""))
    md.append("")
    print("\n" + "\n".join(md))

    print("\n[진단 · 화면에만] dev 에서 규칙이 바꾼 행 (id · 갈래 · 바뀌기 전 · 표지 · 정답 · 출처)")
    for s in SEEDS:
        for name in COND:
            for x in FLIP[s][name]:
                print(f"  시드 {s} · {name} · {x['id']} · {x['bucket']} · {x['from']} · {x['kinds']} · 정답 {x['gold']} · {x['provenance']}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"d4_06_fact_cue_dev_{stamp}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fo:
        json.dump({"at": stamp, "golden_sha256": gsha, "dev_mark": mark, "banned_terms_sha256": dict_sha, "judged_by": g.JUDGED_BY,
                   "cues": CUES, "goal_moved": GOAL_MOVED, "lim_syn_pass": LIM_SYN_PASS, "lim_law_quiet": LIM_LAW_QUIET, "pass": ok_all,
                   "result": {f"{arm}_seed{s}": R[(arm, s)] for arm in ("끔", "켬") for s in SEEDS}},
                  fo, ensure_ascii=False, indent=1, default=str)
    print(f"[INFO] 요약(저장소 밖 · 행 id 포함): {path}")
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
