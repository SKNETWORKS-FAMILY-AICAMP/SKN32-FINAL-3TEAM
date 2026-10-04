"""실제 광고 정답표로 채점 — 정답표 파일을 골라 1단계 → 후처리 → 관문을 돌린다 (2026-10-05).

정답표 v2(사례집 · 화장품 광고 Q&A 74개 · `_private/answer_key_v2_draft.jsonl`)처럼 e2e 의 고정 31개 밖의 정답표를 잰다.
채점은 e2e 와 같다 — 불가를 불가로 · 살릴 것을 살림 · 위반 포장 · 지나친 거절 · 보류. 조건부는 조건이 붙었는지도 센다.

🚨 정답표 · 결과에 재배포 불가 원문이 들어간다 — 읽고 쓰는 곳은 `_private/` 뿐이다. 화면에는 개수만 낸다.

실행 (repo 루트 · GPU venv):
    .venv-sllm/Scripts/python.exe docs/lse/eval_answer_key.py _private/answer_key_v2_draft.jsonl [--stage1 v10]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from persona_experiment import BASE  # noqa: E402
from persona_pipeline_e2e import STAGE1_VER, STAGE2, run_one  # noqa: E402


def grade(outcome: str, label: str) -> str:
    can = label != "불가"
    return {
        ("infeasible", False): "✅ 불가를 불가로",
        ("candidate", True): "✅ 살림",
        ("candidate", False): "🔴 위반 포장",
        ("infeasible", True): "🟠 지나친 거절",
    }.get((outcome, can), "🟡 보류")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="정답표 jsonl (docs/lse 기준 · _private 안)")
    ap.add_argument("--stage1", default=STAGE1_VER)
    args = ap.parse_args()
    key_path = HERE / args.key
    assert "_private" in key_path.parts, "정답표는 _private 안에 있어야 한다(재배포 불가 원문)"
    rows = [json.loads(line) for line in key_path.open(encoding="utf-8") if line.strip()]
    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(
        base, str(ROOT / "models" / f"copylane_sllm_lora_adapter_{args.stage1}"), adapter_name="stage1"
    )
    model.load_adapter(str(STAGE2), adapter_name="stage2")
    model.eval()
    res = []
    for i, k in enumerate(rows, 1):
        r = run_one(model, tok, k["input"], k.get("labels_all") or [k["reason"]])
        res.append({**k, "got": r, "grade": grade(r["outcome"], k["label"])})
        print(f"{i}/{len(rows)}", flush=True)
    out = key_path.with_name(f"{key_path.stem}_result_{args.stage1}.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for x in res:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"\n[{args.stage1}] {len(res)}개 → {dict(sorted(collections.Counter(x['grade'] for x in res).items()))}")
    by = collections.Counter((x.get("source"), x["label"], x["grade"]) for x in res)
    for (src, lab, g), n in sorted(by.items(), key=lambda t: (str(t[0][0]), t[0][1], t[0][2])):
        print(f"   {src} · 정답 {lab} · {g}: {n}")
    # 🆕 10-05 — 학습 데이터 안에 들어 있는 문구(`seen_in_training`)는 따로 센다 — 학습 때 본 문구라 점수가 부푼다
    clean = [x for x in res if not x.get("seen_in_training")]
    print(f"   학습에 없던 것만 {len(clean)}개 → {dict(sorted(collections.Counter(x['grade'] for x in clean).items()))}")
    sal = [x for x in res if x["grade"] == "✅ 살림" and x["label"] == "조건부"]
    print(f"   조건부를 살린 것 {len(sal)} 중 조건이 붙은 것 {sum(bool(x['got'].get('note')) for x in sal)}")
    print(f"결과: {out}  (재배포 불가 원문 포함 — _private)")


if __name__ == "__main__":
    main()
