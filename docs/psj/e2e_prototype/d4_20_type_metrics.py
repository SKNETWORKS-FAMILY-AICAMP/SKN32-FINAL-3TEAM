"""D4-20 판정 인코더 — 확장 dev 유형별 Precision · Recall · F1 · accuracy · macro F1 (2026-10-22 · 박수진).

  uv run python docs\\psj\\e2e_prototype\\d4_20_type_metrics.py
  uv run python docs\\psj\\e2e_prototype\\d4_20_type_metrics.py --limit 50   # 빠른 확인

★ 왜 — 최종 산출물 05 · 06 확인 요청 #1: D4-20 의 유형별 지표가 기록에 없다.
★ 무엇을 — 확장 dev(= devsplit dev + 해설서 dev · `scripts/eval_graph.py --dev --guide-dev` 와 같은 행 · D-347)를
   **앱과 같은 로더 · 문턱**(`app.encoder.JudgeEncoder` · `label_scheme.json`)으로 돌린다. 인코더 단독 성적이다 — 판정 그래프(사전 · 전제 · 보류) 성적이 아니다.
   두 입력으로 잰다:
     모름  — 품목 입력 「모름」(문턱 `label_thresholds`)
     품목  — 골든 `품목` 칸이 있으면 그 품목(문턱 `label_thresholds_by_cat`) · 없으면 「모름」
🚨 양성 30 미만 유형은 「측정 불가」로 표시하고 macro 에서 뺀 값도 같이 낸다 (D-324 결정 2).
🔴 문장 원문은 결과 파일에 싣지 않는다 — 수와 id 만.
결과 — `docs/psj/reports/D4-20_유형별지표_확장dev_<날짜>.md` · `.json`
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app import encoder as enc  # noqa: E402
from app import premise as pm  # noqa: E402
from app.contracts import Category  # noqa: E402
from app.settings import PARAMS  # noqa: E402
from preprocess import devsplit  # noqa: E402
from preprocess import encoder_resplit as resplit  # noqa: E402

GOLDEN = ROOT / "data" / "derived" / "golden" / "golden.jsonl"
MODEL = ROOT / "models" / "copylane-encoder-kcbert-D4-20-기능성편입"
MIN_MEASURABLE = PARAMS.min_measurable  # D-324 결정 2 · 값은 settings 한 곳 (D-99)


def _rows(limit: int | None) -> list[dict]:
    every = [json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()]
    by = {r["id"]: r for r in every}
    rows = [by[i] for i in devsplit.dev_ids(every)] + resplit.guide_dev_rows(every)
    return rows[:limit] if limit else rows


def _category_input(row: dict) -> str:
    try:
        return pm.encoder_input(Category(row["품목"])) if row.get("품목") else pm.ENCODER_UNKNOWN
    except ValueError:
        return pm.ENCODER_UNKNOWN


def _metrics(rows: list[dict], preds: list[set[str]], labels: list[str]) -> dict:
    n = len(rows)
    per = {}
    for lab in labels:
        tp = fp = fn = tn = 0
        for r, p in zip(rows, preds, strict=True):
            gold, hit = lab in (r.get("labels") or []), lab in p
            tp += gold and hit
            fp += (not gold) and hit
            fn += gold and not hit
            tn += (not gold) and not hit
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if (tp + fp) and (tp + fn) else None)
        per[lab] = {
            "pos": tp + fn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec, "recall": rec, "f1": f1, "accuracy": (tp + tn) / n if n else None,
            "measurable": tp + fn >= MIN_MEASURABLE,
        }
    f1s = [v["f1"] for v in per.values() if v["f1"] is not None]
    f1m = [v["f1"] for v in per.values() if v["f1"] is not None and v["measurable"]]
    exact = sum(set(r.get("labels") or []) == p for r, p in zip(rows, preds, strict=True))
    micro_tp = sum(v["tp"] for v in per.values())
    micro_fp = sum(v["fp"] for v in per.values())
    micro_fn = sum(v["fn"] for v in per.values())
    mp = micro_tp / (micro_tp + micro_fp) if micro_tp + micro_fp else None
    mr = micro_tp / (micro_tp + micro_fn) if micro_tp + micro_fn else None
    return {
        "per_label": per,
        "macro_f1_all": sum(f1s) / len(f1s) if f1s else None,
        "macro_f1_measurable": sum(f1m) / len(f1m) if f1m else None,
        "micro_precision": mp,
        "micro_recall": mr,
        "micro_f1": 2 * mp * mr / (mp + mr) if mp and mr else None,
        "exact_match_accuracy": exact / n if n else None,
        "rows": n,
    }


def _fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    golden_sha = hashlib.sha256(GOLDEN.read_bytes()).hexdigest()[:12]
    e = enc.JudgeEncoder(MODEL)
    labels = [v.value for v in e.scheme.labels]
    rows = _rows(args.limit)
    print(f"골든 {golden_sha} · 확장 dev {len(rows)}행 · 모델 {MODEL.name} · 판 {enc.bundle_mark(MODEL)}")

    out = {}
    for mode in ("모름", "품목"):
        preds = []
        for i, r in enumerate(rows, 1):
            ci = pm.ENCODER_UNKNOWN if mode == "모름" else _category_input(r)
            p = e.predict(r["text"], ci)
            preds.append({c.violation.value for c in p.candidates})
            if i % 200 == 0:
                print(f"  {mode} {i}/{len(rows)}")
        out[mode] = _metrics(rows, preds, labels)

    today = dt.date.today().strftime("%Y%m%d")
    rep = ROOT / "docs" / "psj" / "reports"
    meta = {
        "golden_sha": golden_sha, "model": MODEL.name, "bundle": enc.bundle_mark(MODEL),
        "rows": len(rows), "min_measurable": MIN_MEASURABLE, "date": today,
    }
    (rep / f"D4-20_유형별지표_확장dev_{today}.json").write_text(
        json.dumps({"meta": meta, **out}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# D4-20 판정 인코더 — 확장 dev 유형별 지표 ({today})",
        "",
        f"> 골든 `{golden_sha}` · 확장 dev {len(rows)}행(dev + 해설서 dev · D-347) · 모델 `{MODEL.name}` · 판 `{meta['bundle']}`",
        "> 인코더 단독(앱 로더 · `label_scheme.json` 문턱) — 판정 그래프 성적이 아니다. 양성 30 미만은 측정 불가(D-324 결정 2).",
        "",
    ]
    for mode, m in out.items():
        title = "품목 입력 「모름」" if mode == "모름" else "골든 품목 입력(없으면 「모름」)"
        lines += [
            f"## {title}",
            "",
            "| 유형 | 양성 | TP | FP | FN | Precision | Recall | F1 | Accuracy | 비고 |",
            "|---|--:|--:|--:|--:|--:|--:|--:|--:|---|",
        ]
        for lab, v in sorted(m["per_label"].items(), key=lambda kv: -kv[1]["pos"]):
            note = "" if v["measurable"] else "측정 불가(양성 < 30)"
            lines.append(
                f"| {lab} | {v['pos']} | {v['tp']} | {v['fp']} | {v['fn']} | {_fmt(v['precision'])} | "
                f"{_fmt(v['recall'])} | {_fmt(v['f1'])} | {_fmt(v['accuracy'])} | {note} |"
            )
        lines += [
            "",
            f"- macro F1 (전체 {len(labels)}종): **{_fmt(m['macro_f1_all'])}** · 측정 가능 유형만: **{_fmt(m['macro_f1_measurable'])}**",
            f"- micro P / R / F1: {_fmt(m['micro_precision'])} / {_fmt(m['micro_recall'])} / {_fmt(m['micro_f1'])}",
            f"- 완전 일치 accuracy(라벨 집합이 정확히 같음): {_fmt(m['exact_match_accuracy'])}",
            "",
        ]
    md = rep / f"D4-20_유형별지표_확장dev_{today}.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ {md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
