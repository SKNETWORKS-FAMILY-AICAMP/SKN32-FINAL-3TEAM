"""판정 로직(1·2단계) 분포 — 🔄 2026-09-29 D-175 준수판 (종전 run_test_dist.py 대체 · 박수진)

  uv run python docs\\psj\\e2e_prototype\\run_judge_dist.py --model <모델 폴더>            # dev (기본)
  uv run python docs\\psj\\e2e_prototype\\run_judge_dist.py --model <모델 폴더> --split test --final   # 최종 1회만

🔴 D-175 — 평가로 봉인된 것(test_sentence)은 **판정 규칙의 설계 재료로 쓰지 않는다.**
   · 규칙을 고치며 보는 것은 **dev** 다 — train 에서 묶음 단위로 뗀 15%(인코더 노트북 섹션 4 와 같은 규칙 · DEV_SEED 42).
     dev 에는 해설서(D · M) 문장이 없다 → D · M 규칙은 결정 문언(D-286 · D-268)으로 세우고, 수로는 최종 측정 때만 본다.
   · `--split test` 는 `--final` 없이는 멈춘다. 최종 후보가 정해진 뒤 **한 번** 잰다 — 그 결과로 규칙을 다시 고치지 않는다.
🔴 D-249 ⑥ — 결과 파일은 **저장소 밖**에 쓰고(기본 ~/copylane_local/eval/) 문장 원문은 넣지 않는다. `--with-text` 는 저장소 밖일 때만.
🔴 D-269 — 보류율을 **사유별로** 함께 보고한다.
🔴 D-272 개정 — 거래 조건(가격 · 할인 · 환불 · 배송) D 행은 `판정 대상 아님`을 기대하지 않는다 → 버킷 `D_거래` 로 따로 센다.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

from judge_stage1 import (QUIET_MARGIN, REPO, load_banned_terms, load_encoder, predict_label_probs_batch, resolve_model_dir,
                          stage1_signals)
from judge_stage2 import stage2_judge
from app.contracts import Category

GOLDEN = os.path.join(REPO, "data", "derived", "golden", "golden.jsonl")
OUT_DIR = os.path.join(os.path.expanduser("~"), "copylane_local", "eval")
CONFIRMED = ["질병_예방치료_표방", "건강기능식품_오인", "의약품_오인", "거짓_과장", "소비자_기만", "후기_체험기_기만"]
AUX = {"부당_비교광고", "비방광고"}
DEV_FRAC, DEV_SEED = 0.15, 42  # 인코더 노트북 섹션 4 와 같은 값 — 바꾸면 둘 다 바꾼다
#: 거래 조건 문장 표지 (D-272 개정) — 버킷을 가르는 데만 쓴다
TRADE = re.compile(r"가격|할인|적립|쿠폰|무료\s*배송|배송|환불|반품|교환|\d+\s*원|만원|1\+1|2\+1|특가|최저가")
EXPECT = {"scored": "위반·보류", "pending": "위반·보류", "M": "보류(채점 안 함)", "D": "판정 대상 아님(별도 지표)", "D_거래": "보류(표시광고법 대상)",
          "neg": "음성 L · 전제별로 갈림(①-b)", "aux": "참고"}
ORDER = ["scored", "pending", "M", "D", "D_거래", "neg", "aux"]


def bucket(r):
    """🔄 10-01 팀장 채점 기준 — C·A·B = 양성 · L = 음성 · D = 별도 지표 · M = 채점 안 함.

    조건이 M · D 면 라벨보다 먼저 가른다(채점 밖). L 은 음성인데 라벨이 붙어 있으면 데이터가 어긋난 것이라 멈춘다.
    조건 칸이 없는 판(8,432판)에서는 라벨 없음 ∧ 조건 없음이 음성(neg)이다 — L 이 생긴 판에서도 같은 버킷으로 떨어진다.
    """
    cond, labels = r.get("조건"), r.get("labels") or []
    if cond == "M":
        return "M"
    if cond == "D":
        return "D_거래" if TRADE.search(r["text"]) else "D"
    if cond == "L":
        if labels:
            raise SystemExit(f"🔴 조건 L(적법)인데 라벨이 있다 — {r['id']} · {labels}")
        return "neg"
    if any(l in AUX for l in labels):
        return "aux"
    if labels:
        return "scored"
    if cond in ("C", "B", "A"):
        return "pending"
    return "neg"


def wilson(k, n, z=1.96):
    """D-40 — 비율의 95% 구간. n=0 이면 (nan, nan)."""
    if not n:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


#: 팀장 채점 묶음 — 버킷 → (묶음, 기대)
TEAM = {"scored": "양성", "pending": "양성", "neg": "음성", "D": "D", "D_거래": "D_거래", "M": "채점 안 함", "aux": "참고"}
PASS_STATES = ("confirmed:신호없음", "판정대상아님")


def team_summary(dist):
    """팀장 기준 요약. 판정 로직은 위반을 「확정 · 근거없음 · 보류」로 내고 통과는 「신호없음 · 판정대상아님」이다."""
    agg = defaultdict(Counter)
    for b, c in dist.items():
        if b in TEAM:
            agg[TEAM[b]].update(c)
    pct = lambda k, n: f"{k:5d}/{n:<5d} {k / n:6.1%} [{wilson(k, n)[0]:.1%}~{wilson(k, n)[1]:.1%}]" if n else "    —"
    print("\n[팀장 채점 기준 · C·A·B 양성 · L 음성 · D 별도 · M 채점 안 함]")
    c = agg["양성"]; n = sum(c.values())
    if n:
        print(f"  양성 (C·A·B + 유형 라벨)  위반 확정    {pct(c['confirmed:위반'], n)}")
        print(f"                            놓침(통과)   {pct(sum(c[s] for s in PASS_STATES), n)}   ← 낮을수록 좋다")
    c = agg["음성"]; n = sum(c.values())
    if n:
        print(f"  음성 (L)                  오판정(확정) {pct(c['confirmed:위반'], n)}   ← 낮을수록 좋다")
        print(f"                            통과         {pct(sum(c[s] for s in PASS_STATES), n)}")
    c = agg["D"]; n = sum(c.values())
    if n:
        print(f"  D (주장 없는 문구)        판정대상아님 {pct(c['판정대상아님'], n)}   ← 높을수록 좋다")
        print(f"                            위반 확정    {pct(c['confirmed:위반'], n)}")
    c = agg["D_거래"]; n = sum(c.values())
    if n:
        print(f"  D_거래 (참고 · D-272 개정) 판정대상아님 {pct(c['판정대상아님'], n)}   ← 0 이어야 한다(not_claim 금지)")


def group_key(r):
    rid = r["id"]
    return rid.split(":", 2)[2] if rid.startswith("inj:") else rid.split("#")[0]


def dev_rows(golden):
    """인코더 노트북 섹션 4 와 같은 묶음 단위 층화 dev (이유 구역 제외 · D-234)."""
    train = [r for r in golden if r["split"] == "train"]
    devable = lambda r: not (r.get("provenance") == "ftc_decisions_body" and r.get("구역") == "이유")
    groups = defaultdict(list)
    for r in train:
        groups[group_key(r)].append(r)
    gkeys = sorted(groups)
    random.Random(DEV_SEED).shuffle(gkeys)
    lab = lambda r: [l for l in (r.get("labels") or []) if l in CONFIRMED]
    pos_total = Counter(l for r in train if devable(r) for l in lab(r))
    target = {l: max(1, math.ceil(DEV_FRAC * pos_total[l])) for l in CONFIRMED}
    neg_groups = {g for g in gkeys if any(devable(r) and not r.get("labels") for r in groups[g])}
    neg_target = math.ceil(DEV_FRAC * len(neg_groups))
    got, neg_got, dev = Counter(), 0, set()
    for g in gkeys:
        labs = Counter(l for r in groups[g] if devable(r) for l in lab(r))
        is_neg = g in neg_groups and not labs
        if any(got[l] < target[l] for l in labs) or (is_neg and neg_got < neg_target):
            dev.add(g); got.update(labs); neg_got += is_neg
    return [r for g in dev for r in groups[g] if devable(r)]


def extra_holdout(path, frac=0.2):
    """인코더 노트북 v7.4 섹션 4 와 **같은 규칙**으로 뗀 추가 파일 홀드아웃 — family 별 · id 순 · DEV_SEED 셔플 · 앞 frac.
    어느 실행에서도 학습하지 않은 행이라 test 를 보지 않고 D형 비용 · 4호 탐지를 잴 수 있다 (D-175)."""
    if not os.path.exists(path):
        raise SystemExit(f"🔴 홀드아웃 파일이 없다: {path}")
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    fam = defaultdict(list)
    for r in rows:
        fam[r.get("family", "-")].append(r)
    rng, hold = random.Random(DEV_SEED), []
    for f, rs in sorted(fam.items()):
        rs = sorted(rs, key=lambda r: r["id"])
        rng.shuffle(rs)
        hold += rs[:int(round(frac * len(rs)))]
    stem = os.path.splitext(os.path.basename(path))[0].replace("proto_", "")
    for r in hold:
        r["bucket"] = f"hold:{stem}"
    return hold, stem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--final", action="store_true", help="test 최종 측정 1회 — 결과로 규칙을 다시 고치지 않는다 (D-175)")
    ap.add_argument("--category", default=None, choices=[c.value for c in Category])
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--margin", type=float, default=QUIET_MARGIN, help="여유 구간 (τ 배수 · 1.0 이면 끔)")
    ap.add_argument("--margin-sweep", default=None, help="예: 1.0,0.8,0.6,0.5,0.4 — 여유 구간별 버킷 분포만 출력하고 끝낸다")
    ap.add_argument("--holdout", action="append", default=[], help="추가 파일 홀드아웃 버킷 (예: C:\\Users\\...\\proto_negd4.jsonl) — 여러 번 줄 수 있다")
    ap.add_argument("--with-text", action="store_true", help="문장 원문 포함 — 저장소 밖 경로일 때만 (D-249 ⑥)")
    a = ap.parse_args()

    if a.split == "test" and not a.final:
        raise SystemExit("🔴 test_sentence 는 규칙 설계에 쓰지 않는다 (D-175). 최종 측정 1회면 --final 을 붙인다.")
    out_dir = os.path.abspath(a.out_dir)
    if os.path.commonpath([out_dir, REPO]) == REPO:
        raise SystemExit(f"🔴 결과를 저장소 안에 쓰지 않는다 (D-249 ⑥): {out_dir}")

    raw = open(a.golden, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    golden = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    rows = dev_rows(golden) if a.split == "dev" else [r for r in golden if r["split"] == "test_sentence"]
    for r in rows:
        r["bucket"] = bucket(r)
    for hp in a.holdout:
        hold, stem = extra_holdout(hp)
        rows += hold
        ORDER.append(f"hold:{stem}")
        EXPECT[f"hold:{stem}"] = "위반·보류(정답 유형)" if any(r.get("labels") for r in hold) else "신호 없음 (D형)"
        print(f"[INFO] 홀드아웃 {stem}: {len(hold)}행 (학습 안 함 · 노트북 v7.4 와 같은 행)")
    print(f"[INFO] golden {sha[:8]} · {a.split} {len(rows)}행" + ("  🔴 최종 측정 — 이 결과로 규칙을 고치지 않는다" if a.final else ""))

    tok, mdl, labels, th = load_encoder(resolve_model_dir(a.model))
    book = load_banned_terms()
    probs = predict_label_probs_batch([r["text"] for r in rows], tok, mdl, labels)
    cat = Category(a.category) if a.category else None

    if a.margin_sweep:
        ms = [float(x) for x in a.margin_sweep.split(",")]
        print(f"\n[여유 구간 sweep · {a.split}] 기록되는 판정 중 「confirmed:신호없음」 비율 (나머지는 보류 · 위반)")
        print(f"{'margin':>7s}  " + "  ".join(f"{b:>14s}" for b in ORDER if any(r['bucket'] == b for r in rows)))
        for m in ms:
            c = defaultdict(Counter)
            for r, lp in zip(rows, probs):
                s2 = stage2_judge(stage1_signals(r["text"], lp, book, th, margin=m), category=cat)
                quiet = s2["verdict"] == "confirmed" and not s2["violations"]
                c[r["bucket"]]["quiet" if quiet else "other"] += 1
            print(f"{m:7.2f}  " + "  ".join(f"{c[b]['quiet']:4d}/{sum(c[b].values()):4d} ({c[b]['quiet'] / max(sum(c[b].values()), 1):5.1%})"
                                           for b in ORDER if c[b]))
        return

    subj = defaultdict(Counter)
    dist, reasons, prem = defaultdict(Counter), defaultdict(Counter), defaultdict(lambda: defaultdict(Counter))
    out = []
    for r, lp in zip(rows, probs):
        s2 = stage2_judge(stage1_signals(r["text"], lp, book, th, margin=a.margin), category=cat)
        b = r["bucket"]
        state = s2["verdict"] if s2["verdict"] != "confirmed" else (
            "confirmed:위반" if s2["violations"] else ("판정대상아님" if s2.get("not_claim") else "confirmed:신호없음"))
        subj[b][s2.get("subject")] += 1
        dist[b][state] += 1
        if s2.get("hold_reason"):
            reasons[b][s2["hold_reason"]] += 1
        for p, br in s2.get("branches", {}).items():
            prem[p][b]["위반예상" if (br["violations"] or br["no_basis_types"]) else ("보류" if br["verdict"] == "hold" else "신호없음/해소")] += 1
        row = {"bucket": b, "id": r["id"], "조건": r.get("조건"), "labels": "|".join(r.get("labels") or []),
               "verdict": s2["verdict"], "hold_reason": s2.get("hold_reason") or "", "violations": "|".join(s2["violations"]),
               "no_basis": "|".join(s2["no_basis_types"]), "hold_types": "|".join(s2["hold_types"]),
               "dict_backed": int(s2["dict_backed"]), "signals": "|".join(f"{x['kind']}:{x['type']}" for x in s2["signals"]),
               **{f"p_{l}": round(lp[l], 3) for l in labels}}
        if a.with_text:
            row["text"] = r["text"]
        out.append(row)

    states = ["confirmed:위반", "no_basis", "hold", "confirmed:신호없음", "판정대상아님"]
    print(f"\n[기록되는 판정 · 품목 {a.category or '모름'}]")
    print(f"{'버킷':8s} {'n':>5s}  " + "  ".join(f"{s:>16s}" for s in states) + "   기대")
    for b in ORDER:
        n = sum(dist[b].values())
        if n:
            print(f"{b:8s} {n:5d}  " + "  ".join(f"{dist[b][s]:6d}({dist[b][s] / n:6.1%})".rjust(16) for s in states) + f"   {EXPECT[b]}")
    team_summary(dist)
    print("\n사항 판별 (주장 · 거래조건 · 혼합 · 판정대상아님)")
    for b in ORDER:
        if subj[b]:
            print(f"  {b:12s} " + " · ".join(f"{k} {v}" for k, v in subj[b].most_common()))
    print("\n보류 사유별 (D-269)")
    for b in ORDER:
        if reasons[b]:
            print(f"  {b:8s} " + " · ".join(f"{k} {v}" for k, v in reasons[b].most_common()))
    if prem:
        print("\n전제별 결과 (branches · 시뮬레이터 — 기록되는 판정이 아니다 · D-263)")
        for p, d in prem.items():
            print(f"  [{p}] " + " | ".join(f"{b}: " + ", ".join(f"{k} {v}" for k, v in d[b].items()) for b in ORDER if d[b]))

    os.makedirs(out_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"judge_dist_{a.split}_{stamp}.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print(f"\n[INFO] 행별 결과(저장소 밖): {path}" + ("" if a.with_text else " · 문장 원문 없음(id로 대조)"))


if __name__ == "__main__":
    main()
