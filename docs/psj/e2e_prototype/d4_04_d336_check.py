"""D4-04 보충 ② — D-336 확인 요청 Q1 · Q2 (박수진 · 2026-10-14 · 진단 · 학습 없음 · 판정 없음)

  Q1 놓친 30행 — 팀장이 준 id 목록(저장소 밖 파일)의 행마다 (가) 품목 · (나) 모름 · D4-00 에서 D-324 문턱을 넘는 유형
  Q2 새로 놓친 행 — 유형 있는 위반 중 D4-00 은 후보가 섰는데 (가) 품목에서 후보가 하나도 안 선 행 (+ 반대 방향)
  「선다」 = 시드 48 · 49 · 50 중 둘 이상. 문턱 = D-324 (card17_adopt.d324_thresholds · 모델 · 입력 · 시드마다)

  uv run python docs\\psj\\e2e_prototype\\d4_04_d336_check.py --dir <D4-00 CSV> --d4-dir <D4-04 CSV> --ids <id 목록 txt> --out <저장소 밖 .md>
      --model D4-10 --d4-dir <D4-10 CSV> 로 D4-10 판도 같은 방식으로 잰다
  · `--self-test` — D4-00 의 놓침(F2) 시드 평균이 D4 기준 수(36.7)와 같고 (가) 가 D4-04 기록(42.7)과 같은지 본다

🔴 dev 전용 (D-175). 결과에는 행 id 가 들어간다 — 저장소에 두지 않는다 (--out 은 저장소 밖 · 문장은 쓰지 않는다).
"""
import argparse
import os
import statistics
from collections import Counter

import card17_adopt as ca
import score_encoder_dev as sd

SEEDS = ca.SEEDS
D400 = ca.CAND
TAGS = {"D4-04": "copylane-encoder-kcbert-D4-04-품목입력", "D4-10": "copylane-encoder-kcbert-D4-10-품목입력사실전제"}
MODES = ["품목", "모름"]
SELF = {"D4-00": 36.7, "품목": 42.7, "모름": 29.7}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="D4-00 · 카드 17 행별 확률 폴더")
    ap.add_argument("--d4-dir", required=True, help="품목 입력 판의 행별 확률 폴더")
    ap.add_argument("--model", default="D4-04", choices=list(TAGS))
    ap.add_argument("--ids", required=True, help="놓친 30행 id 목록 (한 줄에 하나 · 저장소 밖)")
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out", default=None, help="결과 md (저장소 밖 경로)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.out and "SKN32-FINAL-3TEAM" in os.path.abspath(a.out):
        raise SystemExit("🔴 --out 은 저장소 밖이어야 한다 (행 id 가 들어간다)")

    dev, gsha, mark = sd.load_dev(a.golden)
    C = sd.CONF8
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(C)}
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(C) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    E = {}
    for key in ["D4-00"] + MODES:
        for s in SEEDS:
            f = (os.path.join(a.dir, f"{D400}_seed{s}_dev행별확률.csv") if key == "D4-00"
                 else os.path.join(a.d4_dir, f"{TAGS[a.model]}_{key}_seed{s}_dev행별확률.csv"))
            P = sd.read_probs(f, dev)
            th, _ = ca.d324_thresholds(Y, P, target)
            E[(key, s)] = sd.evaluate(dev, P, th)
    f2 = {key: statistics.mean(E[(key, s)]["cat_n"]["F2 놓침"] for s in SEEDS) for key in ["D4-00"] + MODES}
    print(f"[INFO] golden {gsha[:12]} · dev {len(dev)}행 · 지문 {mark} · {a.model} · 놓침(F2) 시드 평균 " + " · ".join(f"{k} {v:.1f}" for k, v in f2.items()))
    if a.self_test:
        bad = [k for k in SELF if round(f2[k], 1) != SELF[k]] if a.model == "D4-04" else [k for k in ["D4-00"] if round(f2[k], 1) != SELF[k]]
        if bad:
            raise SystemExit(f"🔴 자기 검증 실패 — {bad}")
        print("[OK] 자기 검증 통과 — 놓침 수가 D4 기록과 같다")
        return 0

    def stands(key, k):
        """시드 둘 이상에서 문턱을 넘은 유형 (시드 수 포함)."""
        c = Counter(x for s in SEEDS for x in E[(key, s)]["cand"][k])
        return {x: n for x, n in c.items() if n >= 2}

    idx = {r["id"]: k for k, r in enumerate(dev)}
    ids = [l.strip() for l in open(a.ids, encoding="utf-8") if l.strip()]
    missing = [i for i in ids if i not in idx]
    if missing:
        raise SystemExit(f"🔴 dev 에 없는 id {missing}")
    fmt = lambda d: " · ".join(f"{x}({n})" for x, n in sorted(d.items(), key=lambda t: -t[1])) or "—"
    hit = lambda d, y: ("맞음" if set(d) & y else "다른 유형") if d else "안 섬"
    md = [f"# D-336 확인 — 놓친 30행 · 새로 놓친 행 ({a.model} · dev · 진단)", "",
          f"> golden `{gsha[:12]}` · dev `{mark}` · D-324 문턱 (모델 · 입력 · 시드마다) · 「선다」 = 시드 48 · 49 · 50 중 둘 이상 (괄호 = 선 시드 수) · 🔴 행 id 포함 — 저장소 밖", "",
          "## Q1 놓친 30행", "", "| id | 품목 | 정답 유형 | D4-00 | (가) 품목 | (나) 모름 |", "|---|---|---|---|---|---|"]
    tally = Counter()
    for i in ids:
        k = idx[i]
        r = dev[k]
        y = {x for x in r["target"] if x in C}
        cat = r.get("품목") or "없음"
        d0, dA, dB = stands("D4-00", k), stands("품목", k), stands("모름", k)
        a_cell = f"{fmt(dA)} · {hit(dA, y)}" if r.get("품목") else "— (품목 없음 · (나) 와 같은 입력)"
        md.append(f"| {i} | {cat} | {', '.join(sorted(y)) or '(없음)'} | {fmt(d0)} · {hit(d0, y)} | {a_cell} | {fmt(dB)} · {hit(dB, y)} |")
        tally[("D4-00", hit(d0, y))] += 1
        tally[("모름", hit(dB, y))] += 1
        if r.get("품목"):
            tally[("품목", hit(dA, y))] += 1
    n_cat = sum(1 for i in ids if dev[idx[i]].get("품목"))
    md += ["", "| 입력 | 맞음 | 다른 유형 | 안 섬 | 행 |", "|---|---:|---:|---:|---:|"]
    for key, n in (("D4-00", len(ids)), ("품목", n_cat), ("모름", len(ids))):
        md.append(f"| {key if key == 'D4-00' else '(가) 품목' if key == '품목' else '(나) 모름'} | {tally[(key, '맞음')]} | {tally[(key, '다른 유형')]} | {tally[(key, '안 섬')]} | {n} |")

    sc = [k for k, r in enumerate(dev) if r["bucket"] == "scored"]
    lost = [k for k in sc if stands("D4-00", k) and not stands("품목", k)]
    gain = [k for k in sc if not stands("D4-00", k) and stands("품목", k)]
    md += ["", f"## Q2 새로 놓친 행 — D4-00 은 섰는데 (가) 품목에서 안 선 행 ({len(lost)}행 · 반대로 (가) 가 새로 잡은 행 {len(gain)})", "",
           "| id | 품목 | 정답 유형 | D4-00 에서 선 유형 | (나) 모름 |", "|---|---|---|---|---|"]
    for k in lost:
        r = dev[k]
        md.append(f"| {r['id']} | {r.get('품목') or '없음'} | {', '.join(sorted(x for x in r['target'] if x in C))} | {fmt(stands('D4-00', k))} | {fmt(stands('모름', k))} |")
    md += ["", "품목별 — 잃은 행 " + " · ".join(f"{c} {n}" for c, n in Counter(dev[k].get('품목') or '없음' for k in lost).items())
           + " / 얻은 행 " + " · ".join(f"{c} {n}" for c, n in Counter(dev[k].get('품목') or '없음' for k in gain).items()),
           "", "🚨 dev 다 — 같은 dev 로 문턱을 골랐다(D-324). 판정 그래프의 30행은 D4-00 시드 49 · 사전까지 본 수다 — 여기 D4-00 칸은 인코더 단독 · 세 시드다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(out)
        print(f"[INFO] 저장(저장소 밖): {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
