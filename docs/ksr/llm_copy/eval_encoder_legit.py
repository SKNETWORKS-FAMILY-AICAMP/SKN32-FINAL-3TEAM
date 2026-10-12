"""실험 — 다시 학습한 인코더를 v10 과 같은 문구로 견준다 (2026-10-08 · ksr).

    uv run python docs/ksr/llm_copy/eval_encoder_legit.py --signals build/llm_copy/compare_signals_<...>.json \
        --model models/copylane-encoder-kcbert-v10-ksr실험-적법900 [--model <다른 판> ...]

`compare_judges.py` 가 남긴 신호 파일의 문구(위반 30 · 대조 5 · 10-08 생성분 · 합성 정상 900)에 새 판의 확률을 다시 내고,
신호 파일에 든 v10 확률과 나란히 표로 낸다. 문턱은 ① 그 판이 dev 에서 고른 값 ② v10 의 값 두 가지로 본다.

🚨 합성 정상 900개는 새 판이 **학습에서 본 문구**다 — 그 칸은 참고용이다. 처음 보는 문구는 10-08 생성분이다.
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import sys

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MAX_LEN = 128


def probs(model_dir: pathlib.Path, texts: list[str]) -> tuple[np.ndarray, list[str], dict]:
    scheme = json.loads((model_dir / "label_scheme.json").read_text("utf-8"))
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(dev).eval()
    out = []
    for s in range(0, len(texts), 64):
        enc = tok(
            texts[s : s + 64],
            truncation=True,
            max_length=MAX_LEN,
            padding=True,
            return_tensors="pt",
        ).to(dev)
        with torch.inference_mode():
            out.append(torch.sigmoid(model(**enc).logits.float()).cpu().numpy())
    return np.concatenate(out), scheme["label_list"], scheme


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--signals", required=True)
    ap.add_argument(
        "--model", action="append", required=True, help="다시 학습한 판의 폴더 (여러 번 줄 수 있다)"
    )
    ap.add_argument("--out", default="", help="문구별 확률을 남길 JSON")
    args = ap.parse_args()

    sig = json.loads(pathlib.Path(args.signals).read_text("utf-8"))
    items, v10_thr = sig["items"], sig["thresholds"]
    texts = [it["judged"] for it in items]
    labels = list(v10_thr)

    def group(it: dict) -> str:
        if it["group"] == "V":
            return "위반 30" if it["violation"] else "대조 5"
        return (
            "10-08 생성분 371 (처음 보는 문구)"
            if it["group"] == "N"
            else "합성 정상 900 (학습에서 본 문구)"
        )

    groups = [
        "위반 30",
        "대조 5",
        "10-08 생성분 371 (처음 보는 문구)",
        "합성 정상 900 (학습에서 본 문구)",
    ]
    idx = {g: [i for i, it in enumerate(items) if group(it) == g] for g in groups}

    def flagged(p: np.ndarray, thr: dict) -> np.ndarray:
        t = np.array([thr[name] for name in labels])
        return (p >= t).any(axis=1)

    p_v10 = np.array([[it["enc"][name] for name in labels] for it in items])
    table = [("v10 (지금 판)", p_v10, v10_thr, v10_thr)]
    saved = {"labels": labels, "v10_thresholds": v10_thr, "models": {}}
    for m in args.model:
        d = pathlib.Path(m)
        p, lab, scheme = probs(d, texts)
        assert lab == labels, f"라벨 순서가 v10 과 다르다: {lab}"
        table.append((d.name, p, scheme["label_thresholds"], v10_thr))
        saved["models"][d.name] = {
            "thresholds": scheme["label_thresholds"],
            "best_epoch": scheme.get("best_epoch"),
            "dev_macro_prauc6": scheme.get("dev_macro_prauc6"),
            "train_rows": scheme.get("train_rows"),
            "probs": np.round(p, 4).tolist(),
        }

    print(
        "걸린 수 — 「자기 문턱」은 그 판이 dev 에서 고른 값 · 「v10 문턱」은 v10 의 값을 그대로 건 것"
    )
    head = f"{'판':<46} {'문턱':<8}" + "".join(f"{g.split(' (')[0]:>16}" for g in groups)
    print(head)
    for name, p, own, v10t in table:
        for tag, thr in (("자기", own), ("v10", v10t)):
            if name.startswith("v10") and tag == "v10":
                continue
            f = flagged(p, thr)
            print(
                f"{name:<46} {tag:<8}"
                + "".join(f"{int(f[idx[g]].sum()):>10} / {len(idx[g]):<4}" for g in groups)
            )
    print()
    for name, _p, own, _ in table:
        print(f"문턱 {name}: " + " · ".join(f"{k} {v}" for k, v in own.items()))
    print()
    print("가장 높은 확률의 중앙값")
    for name, p, _, _ in table:
        print(
            f"{name:<46}"
            + "".join(f"{float(np.median(p[idx[g]].max(axis=1))):>16.2f}" for g in groups)
        )
    for name, p, own, _ in table[1:]:
        f = flagged(p, own)
        miss = [items[i]["full"] for i in idx["위반 30"] if not f[i]]
        print(f"\n{name} — 자기 문턱에서 놓친 위반 {len(miss)}개: " + " / ".join(miss))
    if args.out:
        saved["items"] = [
            {
                "id": it["id"],
                "group": it["group"],
                "full": it["full"],
                "judged": it["judged"],
                "violation": it.get("violation"),
                "case": it.get("case"),
            }
            for it in items
        ]
        pathlib.Path(args.out).write_text(json.dumps(saved, ensure_ascii=False), "utf-8")
        print(f"\n문구별 확률 — {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
