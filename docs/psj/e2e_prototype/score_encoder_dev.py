"""판정 인코더 공통 채점 — dev 행별 확률 CSV 를 넣으면 같은 표와 통과 판정을 낸다 (박수진 · 2026-10-07)

학습 코드가 달라도 **결과물의 형식만 같으면** 같은 자로 잰다. 규약은 `docs/psj/notes/인코더_개선실험_규약_20261007.md`.

  # ① 한 모델을 잰다 (문턱은 label_scheme.json — 폴더 · zip · json 아무거나)
  python docs/psj/e2e_prototype/score_encoder_dev.py --probs <dev행별확률.csv> --scheme <scheme.zip>
  # ② Baseline 과 견줘 통과 판정까지 (시드별 CSV 를 여러 개 주면 시드 평균 · 가장 좋은 시드를 쓴다)
  python docs/psj/e2e_prototype/score_encoder_dev.py --probs <s42.csv> <s43.csv> <s44.csv> \
      --baseline-probs <v10_dev행별확률.csv> --baseline-scheme <v10_scheme.zip> --baseline-seed-prauc 0.7167 0.7081 0.7165
  # ③ 집계표(md · id 없음)와 행 단위 목록(csv · 저장소 밖에만)을 남긴다
  python ... --out-md docs/psj/reports/<이름>.md --out-rows C:/Users/<나>/copylane_local/eval/<이름>.csv

입력
  · 확률 CSV — `id` 칸 + `p_<유형>` 9칸. dev 749행이 전부 있어야 한다(순서는 무관 · 다른 칸은 무시).
  · 문턱 — `label_scheme.json` 의 `label_thresholds`. 안 주면 이 스크립트가 규칙대로 고른다(유형별 dev F1 최대).

고정한 것 (바꾸면 규약도 같이 바꾼다)
  · dev = 원천별 묶음 15% + 6종 보충 · 시드 42 · 문장 단위 · 합성 아님 (v11 규칙) → 재동결 10-05 판에서 749행
  · 정답 = 조건 M · D · L 은 유형이 적혀 있어도 음성 · 채점 행 = 749행 전부 (광고 문구 줄만 본 값을 함께 낸다)
  · 모델 고르기 = 6종 macro PR-AUC · 통과 기준 = 아래 GATE

🔴 test 행은 읽지 않는다. 확률 CSV 에 dev 가 아닌 id 가 있으면 멈춘다 (D-175).
🔴 행 단위 목록(`--out-rows`)은 저장소 안에 쓰지 않는다 — 행별 정답이 드러난다 (D-249). 문장 원문은 어디에도 쓰지 않는다.
표준 라이브러리만 쓴다(numpy · sklearn 불필요).
"""

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import zipfile
from collections import Counter, defaultdict

SEL = [
    "질병_예방치료_표방",
    "건강기능식품_오인",
    "의약품_오인",
    "거짓_과장",
    "소비자_기만",
    "후기_체험기_기만",
]
CONF8 = SEL + ["부당_비교광고", "비방광고"]  # 확정 8종 (D-321)
LABELS = CONF8 + ["기능성화장품_오인"]  # 저장 9칸 — 마지막은 편입 대기
DEV_FRAC, DEV_SEED = 0.15, 42
#: 골든 sha → (dev 행 수 · 지문). 같은 골든이면 이 값이 나와야 한다
DEV_EXPECT = {
    "529c970556d77bd2c231526e20531294bf469f794e74a4796835a36f456eb7fe": (749, "4ebfcb231da703b5")
}
#: 🔒 통과 기준 — Baseline 대비. 실험을 돌리기 전에만 고친다
GATE = {
    "prauc_drop": 0.02,  # B  6종 PR-AUC(시드 평균) 하락 허용폭
    "recall_drop": 0.02,  # G1 위반 탐지율 하락 허용폭
    "type_recall_drop": 0.05,  # G2 유형별 재현율 하락 허용폭 (dev 양성 30 이상인 유형만)
    "neg_flag_up": 1,  # G3 음성(D · L) 오판정이 늘어도 되는 행 수
    "adopt_prauc": 0.008,  # 채택 — PR-AUC 시드 평균이 이만큼 이상 오른다 (시드 표준편차 0.004 의 두 배)
}
CATS = ["정확히 일치", "맞음 + 추가 유형", "맞음 · 일부만", "F1 유형 오인", "F2 놓침"]
TH_GRID = [round(0.1 + 0.025 * k, 3) for k in range(33)]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
GOLDEN = os.path.join(REPO, "data", "derived", "golden", "golden.jsonl")


# ── 데이터
def group_key(rid):
    return rid.split(":", 2)[2] if rid.startswith("inj:") else rid.split("#")[0]


def load_dev(path):
    """골든에서 dev 행만 돌려준다 — v11 노트북 섹션 3 과 같은 규칙. test 행은 버린다."""
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    train = []
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["split"] == "train":
                r["target"] = (
                    [] if r.get("조건") in ("M", "D", "L") else list(r.get("labels") or [])
                )
                train.append(r)
    del raw

    def eligible(r):
        return r.get("unit") == "문장" and r.get("origin") != "injected"

    groups = defaultdict(list)
    for r in train:
        groups[group_key(r["id"])].append(r)
    by_prov = defaultdict(list)
    for g in sorted(groups):
        el = [r for r in groups[g] if eligible(r)]
        if el:
            by_prov[Counter(r.get("provenance") for r in el).most_common(1)[0][0]].append(g)
    rng, dev_groups = random.Random(DEV_SEED), set()
    for prov in sorted(by_prov):
        gs = by_prov[prov][:]
        rng.shuffle(gs)
        dev_groups.update(gs[: max(1, math.ceil(DEV_FRAC * len(gs)))])

    def pos(rows, label):
        return sum(1 for r in rows if eligible(r) and label in r["target"])

    rest = [g for g in sorted(groups) if g not in dev_groups]
    rng.shuffle(rest)
    for label in SEL:
        want = min(10, math.ceil(DEV_FRAC * pos(train, label)))
        have = sum(pos(groups[g], label) for g in dev_groups)
        for g in rest:
            if have >= want:
                break
            k = pos(groups[g], label)
            if k and g not in dev_groups:
                dev_groups.add(g)
                have += k
    dev = [r for g in sorted(dev_groups) for r in groups[g] if eligible(r)]
    mark = hashlib.sha256("|".join(sorted(r["id"] for r in dev)).encode()).hexdigest()[:16]
    if sha in DEV_EXPECT and (len(dev), mark) != DEV_EXPECT[sha]:
        raise SystemExit(
            f"🔴 dev 가 규약과 다르다 — {len(dev)}행 · 지문 {mark} · 기대 {DEV_EXPECT[sha]}"
        )
    for r in dev:
        r["bucket"] = bucket(r)
        r["reason"] = r.get("provenance") == "ftc_decisions_body" and r.get("구역") == "이유"
    return dev, sha, mark


def bucket(r):
    c = r.get("조건")
    if c in ("M", "D", "L"):
        return c
    labels = r.get("labels") or []
    if any(x in CONF8 for x in labels):
        return "scored"
    if labels:
        return "대기"
    return "pending" if c in ("C", "A", "B") else "neg"


def read_probs(path, dev):
    """`id` · `p_<유형>` 9칸. 🔴 dev 와 행이 다르면 멈춘다 — 다른 dev 로 잰 수치는 견줄 수 없다."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    need = ["id"] + [f"p_{x}" for x in LABELS]
    miss = [x for x in need if not rows or x not in rows[0]]
    if miss:
        raise SystemExit(f"🔴 {os.path.basename(path)}: 칸이 없다 {miss}")
    got = {r["id"]: [float(r[f"p_{x}"]) for x in LABELS] for r in rows}
    ids = {r["id"] for r in dev}
    if len(got) != len(rows) or set(got) != ids:
        raise SystemExit(
            f"🔴 {os.path.basename(path)}: dev 와 행이 다르다 — 파일 {len(rows)}행 · dev {len(ids)}행 · "
            f"파일에만 {len(set(got) - ids)} · dev 에만 {len(ids - set(got))}. 같은 dev 로 잰 확률만 받는다"
        )
    return [got[r["id"]] for r in dev]


def read_scheme(path):
    """label_scheme.json 의 문턱 — 폴더 · zip · json 을 받는다."""
    if os.path.isdir(path):
        path = os.path.join(path, "label_scheme.json")
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = next(
                (n for n in z.namelist() if os.path.basename(n) == "label_scheme.json"), None
            )
            if name is None:
                raise SystemExit(f"🔴 zip 안에 label_scheme.json 이 없다: {path}")
            raw = json.loads(z.read(name))
    else:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    if raw.get("label_list") and list(raw["label_list"]) != LABELS:
        raise SystemExit(f"🔴 칸 순서가 규약과 다르다: {raw['label_list']}")
    th = {x: float(raw["label_thresholds"][x]) for x in CONF8}
    return th, raw.get("experiment") or raw.get("run_id") or "?"


# ── 지표 (표준 라이브러리)
def average_precision(y, p):
    order = sorted(range(len(y)), key=lambda i: -p[i])
    n, tp, out, i = sum(y), 0, 0.0, 0
    if n == 0 or n == len(y):
        return None
    while i < len(order):
        j, t = i, 0
        while j < len(order) and p[order[j]] == p[order[i]]:
            t += y[order[j]]
            j += 1
        tp += t
        if t:
            out += (t / n) * (tp / j)
        i = j
    return out


def auc(pos, neg):
    if not pos or not neg:
        return None
    vals = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(vals):
        j = i
        while j < len(vals) and vals[j][0] == vals[i][0]:
            j += 1
        rank_sum += (i + j + 1) / 2 * sum(t for _, t in vals[i:j])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def pick_thresholds(Y, P):
    """유형별 dev F1 최대 · 격자 0.1 ~ 0.9(0.025) · dev 양성 10 미만이면 0.5."""
    th = {}
    for i, label in enumerate(CONF8):
        y, p = [r[i] for r in Y], [r[i] for r in P]
        if sum(y) < 10:
            th[label] = 0.5
            continue
        best, best_t = -1.0, 0.5
        for t in TH_GRID:
            tp = sum(1 for a, b in zip(y, p, strict=True) if a and b >= t)
            pp = sum(1 for b in p if b >= t)
            f = 2 * tp / (pp + sum(y)) if pp + sum(y) else 0.0
            if f > best + 1e-12:
                best, best_t = f, t
        th[label] = best_t
    return th


def macro_prauc(Y, P, n, mask=None):
    idx = [k for k in range(len(Y)) if mask is None or mask[k]]
    vals = [average_precision([Y[k][i] for k in idx], [P[k][i] for k in idx]) for i in range(n)]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def evaluate(dev, P, th):
    n = len(dev)
    Y = [[1 if x in r["target"] else 0 for x in LABELS] for r in dev]
    cand = [[x for i, x in enumerate(CONF8) if P[k][i] >= th[x]] for k in range(n)]
    score = [
        max(P[k][i] / th[x] for i, x in enumerate(CONF8)) for k in range(n)
    ]  # 1 이상이면 후보가 선다
    ad = [not r["reason"] and r["bucket"] not in ("M", "pending") for r in dev]  # 광고 문구 줄
    out = {"n": n, "th": th, "cand": cand, "score": score, "Y": Y}
    out["prauc6"], out["prauc8"] = macro_prauc(Y, P, 6), macro_prauc(Y, P, 8)
    out["prauc6_ad"] = macro_prauc(Y, P, 6, ad)
    cats = []
    for k, r in enumerate(dev):
        c, y = set(cand[k]), {x for x in r["target"] if x in CONF8}
        if r["bucket"] != "scored":
            cats.append("")
        elif not c:
            cats.append("F2 놓침")
        elif not (c & y):
            cats.append("F1 유형 오인")
        elif c - y:
            cats.append("맞음 + 추가 유형")
        else:
            cats.append("맞음 · 일부만" if y - c else "정확히 일치")
    out["cats"] = cats
    sc = [k for k in range(n) if dev[k]["bucket"] == "scored"]
    out["scored"] = len(sc)
    out["cat_n"] = Counter(cats[k] for k in sc)
    out["det"] = sum(1 for k in sc if cand[k])
    out["hit"] = out["scored"] - out["cat_n"]["F1 유형 오인"] - out["cat_n"]["F2 놓침"]
    out["f1_only_false"] = sum(
        1 for k in sc if cats[k] == "F1 유형 오인" and cand[k] == ["거짓_과장"]
    )
    for b in ("D", "L", "neg", "M", "pending", "대기"):
        rows = [k for k in range(n) if dev[k]["bucket"] == b]
        out[f"flag_{b}"] = (sum(1 for k in rows if cand[k]), len(rows))
    out["neg"] = tuple(sum(out[f"flag_{b}"][i] for b in ("D", "L", "neg")) for i in (0, 1))
    types = {}
    for i, x in enumerate(CONF8):
        y = [Y[k][i] for k in range(n)]
        f = [x in cand[k] for k in range(n)]
        tp, pp = sum(1 for a, b in zip(y, f, strict=True) if a and b), sum(f)
        types[x] = {
            "n": sum(y),
            "tp": tp,
            "pp": pp,
            "ap": average_precision(y, [P[k][i] for k in range(n)]),
        }
    out["types"] = types
    nr_sc = [score[k] for k in sc if not dev[k]["reason"]]
    nr_neg = [
        score[k] for k in range(n) if dev[k]["bucket"] in ("D", "L", "neg") and not dev[k]["reason"]
    ]
    out["auc_neg"] = auc(nr_sc, nr_neg)
    return out


def at_same_detection(dev, P, res, det_target):
    """문턱 전체를 같은 비율로 옮겨 Baseline 과 같은 위반 탐지 수가 되는 자리에서 다시 센다."""
    sc = [k for k in range(len(dev)) if dev[k]["bucket"] == "scored"]
    if not 0 < det_target <= len(sc):
        return None
    s = sorted((res["score"][k] for k in sc), reverse=True)[det_target - 1]
    th = {x: res["th"][x] * s for x in CONF8}
    again = evaluate(dev, P, th)
    return {
        "scale": s,
        "det": again["det"],
        "hit": again["hit"],
        "neg": again["neg"],
        "types": again["types"],
    }


# ── 출력
def pct(k, n):
    return "—" if not n else f"{k / n * 100:.1f}%"


def frac(k, n):
    return "—" if not n else f"{k}/{n} ({k / n * 100:.1f}%)"


def f3(v):
    return "N/A" if v is None else f"{v:.3f}"


def table(head, rows):
    out = [
        "| " + " | ".join(head) + " |",
        "|" + "|".join("---" if i == 0 else "---:" for i in range(len(head))) + "|",
    ]
    return out + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]


def summary_rows(res, seeds):
    mean = (
        f"{statistics.mean(seeds):.4f} ± {statistics.pstdev(seeds):.4f} (시드 {len(seeds)}개)"
        if len(seeds) > 1
        else "— (시드 1개)"
    )
    return [
        ["6종 PR-AUC — 시드 평균", mean],
        [
            "6종 PR-AUC — 이 모델 (dev 전체 · 광고 문구 줄만)",
            f"{f3(res['prauc6'])} · {f3(res['prauc6_ad'])}",
        ],
        ["8종 PR-AUC", f3(res["prauc8"])],
        ["위반 탐지율 (하나라도)", frac(res["det"], res["scored"])],
        ["정답 유형 적중률", frac(res["hit"], res["scored"])],
        [
            "F1 유형 오인 (그중 거짓_과장 하나만)",
            f"{frac(res['cat_n']['F1 유형 오인'], res['scored'])} ({res['f1_only_false']})",
        ],
        ["F2 놓침", frac(res["cat_n"]["F2 놓침"], res["scored"])],
        [
            "음성(D · L) 오판정",
            f"{res['neg'][0]}/{res['neg'][1]} (D {res['flag_D'][0]}/{res['flag_D'][1]} · L {res['flag_L'][0]}/{res['flag_L'][1]})",
        ],
        [
            "조건 M · 유형 없는 위반에 후보 (참고)",
            f"{frac(*res['flag_M'])} · {frac(*res['flag_pending'])}",
        ],
        [
            "거짓_과장 — 후보 → 맞음 (정밀도)",
            f"{res['types']['거짓_과장']['pp']} → {res['types']['거짓_과장']['tp']} ({f3(res['types']['거짓_과장']['tp'] / max(res['types']['거짓_과장']['pp'], 1))})",
        ],
        ["위반 대 D · L AUC (광고 문구 줄)", f3(res["auc_neg"])],
    ]


def type_rows(res, base=None):
    rows = []
    for x in CONF8:
        t = res["types"][x]
        row = [
            x + (" (측정 불가)" if t["n"] < 30 else ""),
            t["n"],
            pct(t["tp"], t["n"]),
            pct(t["tp"], t["pp"]),
            f3(t["ap"]),
            res["th"][x],
        ]
        if base:
            b = base["types"][x]
            row.append(pct(b["tp"], b["n"]))
        rows.append(row)
    return rows


def breakdown(dev, res, key, name=lambda v: v):
    groups = defaultdict(list)
    for k, r in enumerate(dev):
        if r["bucket"] == "scored":
            groups[r.get(key) or "없음"].append(k)
    rows = []
    for g, ks in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        c = Counter(res["cats"][k] for k in ks)
        hit = len(ks) - c["F1 유형 오인"] - c["F2 놓침"]
        rows.append(
            [name(g), len(ks)]
            + [c.get(x, 0) for x in CATS]
            + [pct(hit, len(ks)) + (" (측정 불가)" if len(ks) < 30 else "")]
        )
    return rows


def gate(base, base_seeds, res, seeds):
    """통과 판정 — 규약의 네 기준. PR-AUC 는 시드 평균끼리, 없으면 한 시드 값으로 견준다(그때는 알린다)."""
    b_pr = statistics.mean(base_seeds) if base_seeds else base["prauc6"]
    c_pr = statistics.mean(seeds) if seeds else res["prauc6"]
    d_pr = c_pr - b_pr
    d_rec = res["det"] / res["scored"] - base["det"] / base["scored"]
    d_type = {
        x: res["types"][x]["tp"] / res["types"][x]["n"]
        - base["types"][x]["tp"] / base["types"][x]["n"]
        for x in CONF8
        if base["types"][x]["n"] >= 30
    }
    worst = min(d_type, key=d_type.get) if d_type else None
    d_neg = res["neg"][0] - base["neg"][0]
    ok = {
        "B": d_pr >= -GATE["prauc_drop"],
        "G1": d_rec >= -GATE["recall_drop"],
        "G2": worst is None or d_type[worst] >= -GATE["type_recall_drop"],
        "G3": d_neg <= GATE["neg_flag_up"],
    }
    fails = [k for k, v in ok.items() if not v]
    if fails:
        verdict = "탈락 (" + " · ".join(fails) + ")"
    elif d_pr >= GATE["adopt_prauc"]:
        verdict = "채택 후보 (PR-AUC)"
    else:
        verdict = "통과 · Baseline 과 차이 없음 — 겨냥한 지표가 미리 적은 만큼 나아졌는지 본다"
    rows = [
        [
            "B 6종 PR-AUC" + (" (시드 평균)" if base_seeds and seeds else " (한 시드 값 — 참고)"),
            f"{b_pr:.4f}",
            f"{c_pr:.4f}",
            f"{d_pr:+.4f}",
            f"−{GATE['prauc_drop']} 까지",
            "통과" if ok["B"] else "**탈락**",
        ],
        [
            "G1 위반 탐지율",
            frac(base["det"], base["scored"]),
            frac(res["det"], res["scored"]),
            f"{d_rec * 100:+.1f}%p",
            f"−{GATE['recall_drop'] * 100:.0f}%p 까지",
            "통과" if ok["G1"] else "**탈락**",
        ],
        [
            "G2 유형별 재현율 — 가장 내린 유형",
            "—",
            worst or "—",
            "—" if worst is None else f"{d_type[worst] * 100:+.1f}%p",
            f"−{GATE['type_recall_drop'] * 100:.0f}%p 까지",
            "통과" if ok["G2"] else "**탈락**",
        ],
        [
            "G3 음성(D · L) 오판정",
            f"{base['neg'][0]}/{base['neg'][1]}",
            f"{res['neg'][0]}/{res['neg'][1]}",
            f"{d_neg:+d}행",
            f"+{GATE['neg_flag_up']}행 까지",
            "통과" if ok["G3"] else "**탈락**",
        ],
    ]
    return verdict, rows, fails


def inside_repo(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent


def load_model(dev, Y, paths, scheme_path, name):
    """시드별 확률 → (가장 좋은 시드의 확률 · 문턱 · 시드별 PR-AUC · 이름)."""
    probs = [read_probs(p, dev) for p in paths]
    seeds = [macro_prauc(Y, P, 6) for P in probs]
    best = max(range(len(probs)), key=lambda i: seeds[i])
    P = probs[best]
    picked = pick_thresholds(Y, P)
    if scheme_path:
        th, exp = read_scheme(scheme_path)
        note = "문턱 = label_scheme.json" + (
            " (규칙으로 다시 고른 값과 같다)"
            if th == picked
            else " (규칙으로 다시 고르면 다르다 — 저장값으로 잰다)"
        )
    else:
        th, exp, note = picked, "?", "문턱 = 이 스크립트가 규칙대로 골랐다 (유형별 dev F1 최대)"
    label = name or (exp if exp != "?" else os.path.basename(paths[best]))
    if len(paths) > 1:
        note += (
            f" · 시드별 CSV {len(paths)}개 중 PR-AUC 가 가장 높은 {os.path.basename(paths[best])}"
        )
    return P, th, seeds, label, note


def main():
    ap = argparse.ArgumentParser(description="판정 인코더 공통 채점 (dev)")
    ap.add_argument(
        "--probs",
        nargs="+",
        required=True,
        help="dev 행별 확률 CSV — 시드별로 여러 개를 줄 수 있다",
    )
    ap.add_argument(
        "--scheme", help="label_scheme.json (폴더 · zip · json). 없으면 문턱을 규칙대로 고른다"
    )
    ap.add_argument(
        "--seed-prauc",
        nargs="+",
        type=float,
        help="시드별 CSV 가 없을 때 — 시드별 6종 PR-AUC 를 직접 준다",
    )
    ap.add_argument("--name", help="표에 쓸 이름")
    ap.add_argument("--baseline-probs", nargs="+", help="Baseline 의 dev 행별 확률 CSV")
    ap.add_argument("--baseline-scheme")
    ap.add_argument("--baseline-seed-prauc", nargs="+", type=float)
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument(
        "--target", help="이 실험이 겨냥한 지표와 목표 — 돌리기 전에 적은 문장을 그대로 넣는다"
    )
    ap.add_argument("--out-md", help="집계표(md · id 없음)를 쓸 경로 — 저장소 안에 둬도 된다")
    ap.add_argument(
        "--out-rows", help="행 단위 목록(csv · 문장 원문 없음)을 쓸 경로 — 저장소 밖에만"
    )
    a = ap.parse_args()
    if a.out_rows and inside_repo(os.path.dirname(os.path.abspath(a.out_rows))):
        raise SystemExit("🔴 --out-rows 는 저장소 밖에 쓴다 — 행별 정답이 드러난다 (D-249)")

    dev, sha, mark = load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in LABELS] for r in dev]
    P, th, seeds, name, note = load_model(dev, Y, a.probs, a.scheme, a.name)
    if a.seed_prauc:
        seeds = a.seed_prauc
    res = evaluate(dev, P, th)
    base = None
    if a.baseline_probs:
        bP, bth, bseeds, bname, bnote = load_model(
            dev, Y, a.baseline_probs, a.baseline_scheme, None
        )
        if a.baseline_seed_prauc:
            bseeds = a.baseline_seed_prauc
        base = evaluate(dev, bP, bth)

    md = [f"# 판정 인코더 dev 채점 — {name}", ""]
    md += [f"> 골든 `{sha[:12]}` · dev {len(dev)}행 (지문 `{mark}`) · {note}"]
    md += [
        "> 건수만 적은 집계표다. 행 단위 목록과 문장 원문은 저장소에 두지 않는다 (D-175 · D-249)."
    ]
    if a.target:
        md += [f"> **겨냥한 지표 (실험 전에 적음)** — {a.target}"]
    md += ["", "## 1. 요약", ""]
    if base:
        b_rows = summary_rows(base, bseeds if len(bseeds) > 1 else [])
        md += table(
            ["지표", f"Baseline ({bname})", name],
            [
                [r[0], b[1], r[1]]
                for r, b in zip(
                    summary_rows(res, seeds if len(seeds) > 1 else []), b_rows, strict=True
                )
            ],
        )
    else:
        md += table(["지표", name], summary_rows(res, seeds if len(seeds) > 1 else []))
    if base:
        verdict, rows, fails = gate(
            base, bseeds if len(bseeds) > 1 else None, res, seeds if len(seeds) > 1 else None
        )
        md += ["", "## 2. 통과 판정 (Baseline 대비)", "", f"**{verdict}**", ""]
        md += table(["기준", "Baseline", "이 모델", "차이", "허용", "판정"], rows)
        same = at_same_detection(dev, P, res, base["det"])
        md += ["", "### 문턱을 맞춘 비교 (참고 — 판정은 위 표로 한다)", ""]
        if same is None:
            md += ["Baseline 과 같은 위반 탐지 수를 만들 수 없다."]
        else:
            md += [
                f"이 모델의 문턱 전체에 {same['scale']:.3f} 을 곱해 **Baseline 과 같은 위반 탐지 수({base['det']})** 로 맞춘 자리다. 탈락이 문턱이 옮겨 간 탓인지 본다.",
                "",
            ]
            md += table(
                ["지표", "Baseline", "이 모델 (맞춘 자리)"],
                [
                    [
                        "위반 탐지",
                        frac(base["det"], base["scored"]),
                        frac(same["det"], res["scored"]),
                    ],
                    [
                        "정답 유형 적중",
                        frac(base["hit"], base["scored"]),
                        frac(same["hit"], res["scored"]),
                    ],
                    [
                        "음성(D · L) 오판정",
                        f"{base['neg'][0]}/{base['neg'][1]}",
                        f"{same['neg'][0]}/{same['neg'][1]}",
                    ],
                ]
                + [
                    [
                        f"재현율 — {x}",
                        pct(base["types"][x]["tp"], base["types"][x]["n"]),
                        pct(same["types"][x]["tp"], same["types"][x]["n"]),
                    ]
                    for x in CONF8
                    if base["types"][x]["n"] >= 30
                ],
            )
    md += ["", f"## {3 if base else 2}. 유형별", ""]
    md += table(
        ["유형", "dev 양성", "재현율", "정밀도", "PR-AUC", "문턱"]
        + (["Baseline 재현율"] if base else []),
        type_rows(res, base),
    )
    sec = 4 if base else 3
    md += ["", f"## {sec}. 유형 있는 위반 — 갈래별", ""]
    md += table(
        ["갈래", "행", "비율"] + (["Baseline"] if base else []),
        [
            [c, res["cat_n"][c], pct(res["cat_n"][c], res["scored"])]
            + ([base["cat_n"][c]] if base else [])
            for c in CATS
        ],
    )
    for i, (key, title) in enumerate(
        (("provenance", "원천별"), ("조건", "조건별"), ("품목", "품목별")), 1
    ):
        md += ["", f"## {sec + i}. {title} (유형 있는 위반)", ""]
        md += table([title[:-1], "행"] + CATS + ["정답 유형 적중률"], breakdown(dev, res, key))
    text = "\n".join(line.rstrip() for line in md) + "\n"
    print(text)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"[INFO] 집계표: {a.out_md}")
    if a.out_rows:
        with open(a.out_rows, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "id",
                    "갈래(버킷)",
                    "조건",
                    "원천",
                    "품목",
                    "이유구역",
                    "정답 유형",
                    "인코더 후보",
                    "인코더 갈래",
                    "최고 확률/문턱",
                ]
                + [f"p_{x}" for x in LABELS]
            )
            for k, r in enumerate(dev):
                w.writerow(
                    [
                        r["id"],
                        r["bucket"],
                        r.get("조건") or "",
                        r.get("provenance") or "",
                        r.get("품목") or "",
                        int(r["reason"]),
                        "|".join(r.get("labels") or []),
                        "|".join(res["cand"][k]),
                        res["cats"][k],
                        f"{res['score'][k]:.3f}",
                    ]
                    + [f"{v:.6f}" for v in P[k]]
                )
        print(f"[INFO] 행 단위 목록(저장소 밖 · 문장 원문 없음): {a.out_rows}")


if __name__ == "__main__":
    main()
