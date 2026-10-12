"""카드 17 — 채택 판 재학습의 판정 (박수진 · 2026-10-12)

카드 17 노트북(`copylane_encoder_finetune_v10_카드17_채택판재학습_검수정상문구_20261012.ipynb`)이 낸 시드별 행별 확률로
**D-324 문턱**을 고르고 **규약 2판 관문(D-324 결정 4)** 으로 판정한다. 학습 없음 — 확률만 읽는다.

  uv run python docs\\psj\\e2e_prototype\\card17_adopt.py --dir <행별 확률 폴더> --out-md docs\\psj\\reports\\v10_카드17_채택판재학습_dev_20261012.md

  · 목표 재현율 (D-324 결정 1) = 기준선 재현(`카드17-Baseline재현`) 시드 48 · 49 · 50 의 유형별 재현율 평균 (각 시드 F1 최대 문턱에서)
  · 문턱 = dev 양성 30 이상 유형마다 「dev 재현율이 목표 이상인 가장 높은 문턱」 (격자 0.1 ~ 0.9 · 0.025)
           dev 양성 30 미만(후기 · 부당 비교 · 비방)은 D-324 결정 2 로 측정 불가 · 문턱 ⬜ — 이 카드는 그 판의 F1 최대를 임시로 쓴다 `[임의]`
           두 실험 모두 같은 규칙 · 같은 목표로 고른다
  · 관문 (D-324 결정 4 · 규약 2판 · 시드 평균 · 기준선 재현 대비) — B 6종 PR-AUC −0.02 · G1 위반 탐지(유형 무관) −2.5%p · G3 음성(D · L) +4행
           G2(유형별 재현율)는 참고로만 적는다
  · 목표 (카드 17) — 검수 「적법」 정상 문구 측정용 171행에 후보가 서는 행이 기준선 재현의 절반 이하
  · 배포 시드 (D-324 결정 3) = 채택 판 후보의 6종 PR-AUC 가 가장 높은 시드 — 그 시드의 문턱을 표로 낸다(label_scheme 다시 쓰기의 입력)

목표 · 관문은 실험 기록 카드 17 에 먼저 적었다(`docs/psj/reports/v10_문턱규칙_거짓과장_실험기록_20261007.md`).
🔴 dev 전용 (D-175). 집계표에는 건수만 쓴다.
"""
import argparse
import csv
import json
import os
import statistics

import score_encoder_dev as sd

SEEDS = [48, 49, 50]
BASE = "copylane-encoder-kcbert-v10-카드17-Baseline재현"
CAND = "copylane-encoder-kcbert-v10-카드17-검수정상음성"
NAMES = {BASE: "기준선 재현", CAND: "채택 판 후보 (검수 정상 음성)"}
GRID = [round(0.1 + 0.025 * i, 3) for i in range(33)]
MEASURABLE_MIN = 30          # D-324 결정 2 — dev 양성 30 미만은 측정 불가
GOAL_SYN = 0.5               # 목표 — 검수 적법 정상 문구 후보가 기준선 재현의 이 배수 이하
G = sd.GATE_V2               # B · G1 · G3 (· G2 참고)


def recall(Y, P, i, t):
    y = [r[i] for r in Y]
    n = sum(y)
    return sum(1 for k in range(len(Y)) if y[k] and P[k][i] >= t) / n if n else None


def d324_thresholds(Y, P, target):
    """D-324 문턱 — 측정 가능한 유형은 목표 재현율 이상인 가장 높은 문턱 · 측정 불가 유형은 그 판의 F1 최대 (임시)."""
    f1 = sd.pick_thresholds(Y, P)
    th, src = {}, {}
    for i, x in enumerate(sd.CONF8):
        n = sum(r[i] for r in Y)
        if n < MEASURABLE_MIN:
            th[x], src[x] = f1[x], "F1 최대 (측정 불가 · ⬜ 임시)"
            continue
        best = None
        for t in GRID:
            if recall(Y, P, i, t) >= target[x] - 1e-12:
                best = t
        th[x], src[x] = (best if best is not None else GRID[0]), "목표 재현율"
    return th, src


def syn_counts(path, th):
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            p = [float(r[f"p_{x}"]) for x in sd.CONF8]
            flag = any(p[i] >= th[x] for i, x in enumerate(sd.CONF8))
            quiet = all(p[i] < th[x] * 0.5 for i, x in enumerate(sd.CONF8))
            o = out.setdefault(r["갈래"], {"n": 0, "flag": 0, "quiet": 0})
            o["n"] += 1
            o["flag"] += flag
            o["quiet"] += quiet
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--self-test", action="store_true", help="후보 자리에 기준선 재현을 넣는다 — 차이가 0 이어야 한다")
    a = ap.parse_args(argv)
    cand = BASE if a.self_test else CAND
    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    f = lambda tag, s, kind: os.path.join(a.dir, f"{tag}_seed{s}_{kind}.csv")
    P = {(tag, s): sd.read_probs(f(tag, s, "dev행별확률"), dev) for tag in (BASE, cand) for s in SEEDS}

    # 목표 재현율 — 기준선 재현 3 시드 · 각 시드 F1 최대 문턱
    rec = {s: {x: recall(Y, P[(BASE, s)], i, sd.pick_thresholds(Y, P[(BASE, s)])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in SEEDS) for x in rec[SEEDS[0]]}

    R = {}
    for tag in dict.fromkeys((BASE, cand)):
        R[tag] = {}
        for s in SEEDS:
            th, src = d324_thresholds(Y, P[(tag, s)], target)
            e = sd.evaluate(dev, P[(tag, s)], th)
            R[tag][s] = {"th": th, "src": src, "e": e, "syn": syn_counts(f(tag, s, "합성정상_행별확률"), th)}
    m = lambda tag, fn: statistics.mean(fn(R[tag][s]) for s in SEEDS)
    det, hit, neg, pr = (lambda v: v["e"]["det"]), (lambda v: v["e"]["hit"]), (lambda v: v["e"]["neg"][0]), (lambda v: v["e"]["prauc6"])
    syn = lambda key, k: (lambda v: v["syn"].get(key, {}).get(k, 0))
    per = lambda tag, fn: " · ".join(f"{fn(R[tag][s]):g}" if isinstance(fn(R[tag][s]), int) else f"{fn(R[tag][s]):.4f}" for s in SEEDS)
    sc, nn = R[BASE][SEEDS[0]]["e"]["scored"], R[BASE][SEEDS[0]]["e"]["neg"][1]
    n_ok = R[BASE][SEEDS[0]]["syn"].get("합성정상dev", {}).get("n", 0)
    tags = list(dict.fromkeys((BASE, cand)))

    md = [f"# 카드 17 — 채택 판 재학습 판정 (dev){' — 자기 검증' if a.self_test else ''}", "",
          f"> golden `{gsha[:12]}` · 공통 dev 지문 `{mark}` · 시드 {' · '.join(map(str, SEEDS))} 평균 (괄호 안은 시드별) · "
          "문턱 D-324 (목표 = 기준선 재현의 유형별 재현율 평균 · dev 양성 30 미만 유형은 F1 최대 임시) · 표적 encoder_target · 건수만 적는다", "",
          "### 목표 재현율 (D-324 결정 1 · 기준선 재현 3 시드 평균)", "",
          "| 유형 | dev 양성 | 목표 재현율 | 시드별 (F1 최대 문턱에서) |", "|---|---:|---:|---|"]
    for x in target:
        md.append(f"| {x}{'' if npos[x] >= MEASURABLE_MIN else ' (측정 불가)'} | {npos[x]} | {target[x] * 100:.1f}% | "
                  + " · ".join(f"{rec[s][x] * 100:.1f}%" for s in SEEDS) + " |")
    md += ["", "### 공통 dev · 정상 문구 (D-324 문턱 · 시드 평균)", "",
           "| 지표 | " + " | ".join(NAMES.get(t, t) for t in tags) + " |", "|---|" + "---:|" * len(tags),
           f"| 6종 PR-AUC | " + " | ".join(f"{m(t, pr):.4f} ({per(t, pr)})" for t in tags) + " |",
           f"| 위반 탐지 · 유형 무관 (/{sc}) | " + " | ".join(f"{m(t, det):.1f} ({per(t, det)})" for t in tags) + " |",
           f"| 정답 유형 적중 (/{sc}) | " + " | ".join(f"{m(t, hit):.1f}" for t in tags) + " |",
           f"| 음성(D · L) 오판정 (/{nn}) | " + " | ".join(f"{m(t, neg):.1f} ({per(t, neg)})" for t in tags) + " |",
           f"| **검수 적법 정상 문구 — 후보 (/{n_ok})** | " + " | ".join(f"**{m(t, syn('합성정상dev', 'flag')):.1f}** ({per(t, syn('합성정상dev', 'flag'))})" for t in tags) + " |",
           f"| 검수 적법 정상 문구 — 조용 (/{n_ok}) | " + " | ".join(f"{m(t, syn('합성정상dev', 'quiet')):.1f}" for t in tags) + " |"]
    for key in ("참고-적법(사실 전제)", "참고-조건부", "애매"):
        n = R[BASE][SEEDS[0]]["syn"].get(key, {}).get("n", 0)
        if n:
            md.append(f"| 참고 · {key} — 후보 (/{n}) | " + " | ".join(f"{m(t, syn(key, 'flag')):.1f}" for t in tags) + " |")
    md += ["", "### 유형별 재현율 (시드 평균) · 문턱 (시드 " + " · ".join(map(str, SEEDS)) + ")", "",
           "| 유형 | " + " | ".join(NAMES.get(t, t) for t in tags) + " |", "|---|" + "---|" * len(tags)]
    for x in sd.CONF8:
        cell = lambda t: (f"{statistics.mean(R[t][s]['e']['types'][x]['tp'] / npos[x] for s in SEEDS) * 100:.1f}% · τ "
                          + " · ".join(f"{R[t][s]['th'][x]:g}" for s in SEEDS)) if npos[x] else "—"
        md.append(f"| {x}{'' if npos[x] >= MEASURABLE_MIN else ' (F1 최대 · 임시)'} | " + " | ".join(cell(t) for t in tags) + " |")

    if not a.self_test:
        b, c = BASE, cand
        d_pr, d_det, d_neg = m(c, pr) - m(b, pr), (m(c, det) - m(b, det)) / sc, m(c, neg) - m(b, neg)
        okB, okG1, okG3 = d_pr >= -G["prauc_drop"], d_det >= -G["recall_drop"] - 1e-12, d_neg <= G["neg_flag_up"] + 1e-9
        bs, cs = m(b, syn("합성정상dev", "flag")), m(c, syn("합성정상dev", "flag"))
        goal = bs > 0 and cs <= GOAL_SYN * bs + 1e-9
        g2 = []
        for x, lim in G["type_recall_drop"].items():
            d = statistics.mean(R[c][s]["e"]["types"][x]["tp"] / npos[x] for s in SEEDS) - statistics.mean(R[b][s]["e"]["types"][x]["tp"] / npos[x] for s in SEEDS)
            g2.append(f"{x} {d * 100:+.1f}%p{'' if d >= -lim - 1e-12 else ' ⚠️'}")
        adopt = okB and okG1 and okG3 and goal
        md += ["", "### 관문 · 목표 (카드 17 에 먼저 적은 것 · 시드 평균 · 기준선 재현 대비)", "",
               "| B 6종 PR-AUC −0.02 이내 | G1 위반 탐지 −2.5%p 이내 | G3 음성 오판정 +4 이내 | 목표 — 검수 적법 정상 문구 후보 절반 이하 | 판정 |",
               "|---|---|---|---|---|",
               f"| {'지킴' if okB else '**넘음**'} ({d_pr:+.4f}) | {'지킴' if okG1 else '**넘음**'} ({d_det * 100:+.1f}%p) | "
               f"{'지킴' if okG3 else '**넘음**'} ({d_neg:+.1f}) | {'충족' if goal else '**미달**'} ({cs:.1f} 대 {bs:.1f}) | "
               f"{'**채택 판** — 배포 시드의 label_scheme 을 D-324 문턱으로 다시 쓴다' if adopt else '채택 판 아님'} |",
               "", "G2 유형별 재현율 (참고 · D-324 관문 아님) — " + " · ".join(g2)]
        best = max(SEEDS, key=lambda s: R[c][s]["e"]["prauc6"])
        md += ["", f"### 배포 시드 (D-324 결정 3 · 6종 PR-AUC 최고) — 시드 {best} ({R[c][best]['e']['prauc6']:.4f})", "",
               "| 유형 | 문턱 | 고른 방법 |", "|---|---:|---|"]
        md += [f"| {x} | {R[c][best]['th'][x]:g} | {R[c][best]['src'][x]} |" for x in sd.CONF8]
        md += ["| 기능성화장품_오인 | 1.01 | 편입 대기 · 꺼 둠 (D-321) |"]
    print("\n".join(md))
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write("\n".join(md) + "\n")
        print(f"[INFO] 집계표(건수만): {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
