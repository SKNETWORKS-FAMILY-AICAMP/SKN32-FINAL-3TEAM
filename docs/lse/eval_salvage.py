"""살리기 평가 — 「살릴 수 있는데 버린다」를 따로 잰다 (2026-10-02 · v9).

실제 광고 31개 중 살릴 수 있는 것은 8개뿐이라 차이가 1~2개면 우연과 가르기 어렵다. 그래서 학습에 쓰지 않은 원료 · 제품으로
직접 만든 40개(`stage1_salvage_eval.jsonl` · 살림 28 · 불가 12 · 학습 문구와 유사도 0.6 미만)를 따로 둔다.

채점 (1단계 → 관문 · 페르소나 없음):
  살림 기대  ✅ 살림        후보 + 남아야 할 사실 낱말(keep)이 모두 남음
             🟡 사실 잃음   후보지만 keep 중 일부가 사라짐
             🟡 관문 보류   관문이 막음(이유를 같이 적는다)
             🟠 지나친 거절 합법화 불가
  불가 기대  ✅ 막음        합법화 불가 또는 보류
             🔴 위반 포장   후보로 나옴

실행 (repo 루트 · GPU venv):
    .venv-sllm/Scripts/python.exe docs/lse/eval_salvage.py --stage1 v8
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

EVAL = HERE / "stage1_salvage_eval.jsonl"


def grade(row: dict, r: dict) -> str:
    if row["expect"] == "infeasible":
        return "🔴 위반 포장" if r["outcome"] == "candidate" else "✅ 막음"
    if r["outcome"] == "infeasible":
        return "🟠 지나친 거절"
    if r["outcome"] == "hold":
        return "🟡 관문 보류"
    return "✅ 살림" if all(k in (r["final"] or "") for k in row["keep"]) else "🟡 사실 잃음"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", default=STAGE1_VER)
    args = ap.parse_args()
    rows = [json.loads(line) for line in EVAL.open(encoding="utf-8") if line.strip()]
    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(ROOT / "models" / f"copylane_sllm_lora_adapter_{args.stage1}"),
                                      adapter_name="stage1")
    model.load_adapter(str(STAGE2), adapter_name="stage2")
    model.eval()
    res = []
    for row in rows:
        r = run_one(model, tok, row["input"], row["violation_types"])
        g = grade(row, r)
        res.append({**row, "outcome": r["outcome"], "final": r["final"], "stage1": r["stage1"], "gate1": r["gate1"],
                    "infeasible": r["infeasible"], "grade": g})
        detail = r["final"] or r["infeasible"] or "; ".join(r["gate1"] or []) or "-"
        print(f"{row['no']:>2} {g:<9} {row['input'][:28]:<30} → {detail}", flush=True)
    out = HERE / "_private" / f"salvage_eval_{args.stage1}.jsonl"  # 직접 만든 문구지만 다른 실험 결과와 같은 자리에 둔다
    with out.open("w", encoding="utf-8") as f:
        for x in res:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    sal = [x for x in res if x["expect"] == "salvage"]
    inf = [x for x in res if x["expect"] == "infeasible"]
    print(f"\n[{args.stage1}] 살림 기대 {len(sal)}: {dict(collections.Counter(x['grade'] for x in sal))}")
    print(f"[{args.stage1}] 불가 기대 {len(inf)}: {dict(collections.Counter(x['grade'] for x in inf))}")


if __name__ == "__main__":
    main()
