"""평가용 짝 50쌍으로 인코더 판을 견준다 (2026-10-08 · ksr) — 학습에 넣지 않은 문구다.

    .venv\\Scripts\\python.exe docs/ksr/llm_copy/eval_pairs.py --model models/<판> [--model <다른 판> ...]

짝마다 사실만 말한 문장(적법 기대)과 같은 사실 낱말에 위반 요소를 더한 문장(위반 기대)이 있다.
보는 것 — ① 위반 쪽을 잡는가 ② 사실 쪽을 걸지 않는가 ③ 한 짝을 둘 다 맞히는가(낱말이 아니라 구조를 보는가).
🚨 「걸림」은 문턱을 넘은 유형이 하나라도 있다는 뜻이다. 사실 쪽 문장은 골든셋 관례로는 조건 B(근거를 내면 가능)라
   「걸려야 맞다」고 볼 수도 있다 — 라벨 규칙 판정 전이다. 🚨 정답은 모델 판독이다(사람 확인 전).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import sys
from collections import Counter

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = pathlib.Path(__file__).resolve().parents[3]
PAIRS = ROOT / "docs/ksr/LLM_카피생성_사실진술_짝_평가용_50쌍_ksr_2026-10-08.csv"


def score(
    model_dir: pathlib.Path, texts: list[str]
) -> tuple[np.ndarray, list[str], dict[str, float]]:
    scheme = json.loads((model_dir / "label_scheme.json").read_text("utf-8"))
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
    out = []
    for s in range(0, len(texts), 32):
        enc = tok(
            texts[s : s + 32], truncation=True, max_length=128, padding=True, return_tensors="pt"
        )
        with torch.inference_mode():
            out.append(torch.sigmoid(model(**enc).logits.float()).numpy())
    return np.concatenate(out), scheme["label_list"], scheme["label_thresholds"]


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--show", action="store_true", help="틀린 줄을 적는다")
    ap.add_argument("--out", help="줄별 결과를 적을 json")
    args = ap.parse_args()
    rows = list(csv.DictReader(PAIRS.open(encoding="utf-8-sig", newline="")))
    by = {r["id"]: i for i, r in enumerate(rows)}
    pos = [i for i, r in enumerate(rows) if r["판독(보조)"] == "위반"]
    neg = [i for i, r in enumerate(rows) if r["판독(보조)"] != "위반"]
    dump = {}
    print(f"평가용 짝 {len(pos)}쌍 · 위반 {len(pos)} · 사실 {len(neg)}\n")
    print(
        "| 판 | 위반 잡음 | 유형까지 맞음 | 사실 걸림 | 짝 둘 다 맞음 | 품목별 위반 잡음 (식품·건기식·화장품) | 품목별 사실 걸림 |"
    )
    print("|---|--:|--:|--:|--:|---|---|")
    for m in args.model:
        d = ROOT / m
        p, labels, th = score(d, [r["text"] for r in rows])
        t = np.array([th[n] for n in labels])
        hit = p >= t
        flagged = hit.any(1)
        names = [[labels[j] for j in np.where(hit[i])[0]] for i in range(len(rows))]
        typ = [
            bool(set(rows[i]["위반유형(보조)"].split()) & set(names[i])) for i in range(len(rows))
        ]
        both = sum(1 for i in pos if flagged[i] and not flagged[by[rows[i]["짝"]]])
        cat = lambda idx, c, flagged=flagged: sum(  # noqa: E731
            1 for i in idx if rows[i]["품목"] == c and flagged[i]
        )
        n = lambda idx, c: sum(1 for i in idx if rows[i]["품목"] == c)  # noqa: E731
        cats = ("식품", "건기식", "화장품")
        print(
            f"| {d.name} | {int(flagged[pos].sum())}/{len(pos)} | {sum(typ[i] for i in pos)}/{len(pos)} | {int(flagged[neg].sum())}/{len(neg)} | {both}/{len(pos)} | "
            + " · ".join(f"{cat(pos, c)}/{n(pos, c)}" for c in cats)
            + " | "
            + " · ".join(f"{cat(neg, c)}/{n(neg, c)}" for c in cats)
            + " |"
        )
        dump[d.name] = {
            rows[i]["id"]: {
                "걸림": bool(flagged[i]),
                "유형": names[i],
                "최고확률": round(float(p[i].max()), 3),
            }
            for i in range(len(rows))
        }
        if args.show:
            print(f"\n  [{d.name}] 놓친 위반")
            for i in pos:
                if not flagged[i]:
                    print(
                        f"   - {rows[i]['id']} ({rows[i]['위반유형(보조)']}) {rows[i]['text']} · 최고 {p[i].max():.2f}"
                    )
            print(
                f"  [{d.name}] 걸린 사실 문장 — 붙은 유형 {dict(Counter(n_ for i in neg for n_ in names[i]))}"
            )
            for i in neg:
                if flagged[i]:
                    print(
                        f"   - {rows[i]['id']} {rows[i]['text']} → {' '.join(names[i])} ({p[i].max():.2f})"
                    )
            print()
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(dump, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
