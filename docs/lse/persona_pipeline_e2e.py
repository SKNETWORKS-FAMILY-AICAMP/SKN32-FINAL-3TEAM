"""1단계(위반 제거 LoRA) → 관문 → 2단계(페르소나 LoRA) 를 실제 광고 문구로 끝까지 돌려 본다 (2026-10-01).

🔄 최종 구조(10-01 정리): 1단계는 **v6**(`copylane_sllm_lora_adapter_v6` · 합법화 불가를 낼 수 있다).
   종착은 셋 — `infeasible`(1단계가 합법화 불가) · `hold`(관문 · 규칙에 걸림) · `candidate`(2단계 후보).
   🚨 `candidate` 도 적법 확정이 아니다 — 재판정(판정 코어 · D-119)은 미연결이고 사람 검수가 남는다.

입력: `persona_experiment.load_inputs()` 와 같은 실제 위반 문구(식약처 사례집 train · 재배포 불가 →
결과는 `_private/` 에만 쓴다) + 결과서의 고정 신규 문구.
2단계 페르소나는 평가 전용(q1 · q2) 1개 + 학습 페르소나 2개.

🚨 2단계는 「1단계가 적법하게 고쳤다」를 전제로 한다. 1단계가 위반을 못 지운 문장은 2단계가 고칠 수 없다 —
   그래서 1단계 결과에 kadlint 금지 패턴(외부 규칙 · 채점용만)이 남았는지 따로 센다.

실행 (repo 루트):
    .venv-sllm/Scripts/python.exe docs/lse/persona_pipeline_e2e.py [--kadlint <kadlint 저장소 경로>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from persona_experiment import BASE, load_inputs  # noqa: E402
from persona_two_stage import load_kadlint  # noqa: E402
from stage_gate import check as gate  # noqa: E402
from train_persona_stage2 import SYSTEM as STAGE2_SYSTEM  # noqa: E402
from train_persona_stage2 import rule_check  # noqa: E402
from train_stage1_v5 import SYSTEM_V6 as STAGE1_SYSTEM  # noqa: E402
from train_stage1_v5 import parse as parse_stage1  # noqa: E402
from train_stage1_v5 import user_msg as stage1_user  # noqa: E402

ROOT = HERE.parents[1]
STAGE1 = ROOT / "models" / "copylane_sllm_lora_adapter_v6"
STAGE2 = ROOT / "models" / "copylane_sllm_persona_adapter"
OUT = HERE / "_private" / "persona_pipeline_e2e.jsonl"
PERSONAS = {
    "q1": "30대 프리랜서 — 재택근무하며 자기 페이스대로 사는 사람",
    "p2": "50대 — 가족과 함께하는 꾸준한 건강 습관",
    "p3": "20대 — 운동·자기관리 루틴을 즐기는 사람",
}


def chat(model, tok, system: str, user: str, n: int) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=n, do_sample=False)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kadlint", type=Path, default=None)
    args = ap.parse_args()
    kad = load_kadlint(args.kadlint) if args.kadlint else []

    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(STAGE1), adapter_name="stage1")
    model.load_adapter(str(STAGE2), adapter_name="stage2")
    model.eval()
    t0 = time.time()
    rows = []
    for k, row in enumerate(load_inputs()):
        model.set_adapter("stage1")
        out1 = parse_stage1(chat(model, tok, STAGE1_SYSTEM,
                                 stage1_user({"input": row["input"], "violation_types": row["labels"]}), 220))
        infeasible = out1.get("infeasible") if out1 else None
        s1 = out1.get("body") if out1 and not infeasible else None
        kad1 = [p.pattern[:20] for p, _ in kad if s1 and p.search(s1)]
        # 🚨 관문 — 1단계가 위반을 못 지운 문장은 2단계에 넘기지 않는다(말투로 포장하지 않는다) · 보류로 끝난다
        g1 = gate(row["input"], s1)
        model.set_adapter("stage2")
        for pid, label in PERSONAS.items():
            s2 = None
            if g1.passed:
                raw = chat(model, tok, STAGE2_SYSTEM, f"검수 통과 문장: {s1}\n대상 고객: {label}", 160)
                i, j = raw.find("{"), raw.rfind("}")
                try:
                    s2 = json.loads(raw[i:j + 1])["body"]
                except Exception:  # noqa: BLE001
                    s2 = None
            r2 = {"input": s1 or "", "persona_label": label}
            # 2단계 결과도 같은 관문을 다시 지난다 — 말투를 입히다 위반을 들여오지 않았는지 (D-119 의 축소판)
            g2 = gate(s1 or "", s2) if s2 else None
            if infeasible:
                outcome = "infeasible"  # 1단계가 합법화 불가 — 증명서 경로(D-32 · D-125) · 2단계를 부르지 않는다
            else:
                outcome = "hold" if not g1.passed or not g2 or not g2.passed or rule_check(r2, s2) else "candidate"
            rows.append({**row, "persona": pid, "stage1": s1, "infeasible": infeasible, "gate1": list(g1.reasons),
                         "stage1_kadlint": kad1,
                         "stage2": s2, "gate2": list(g2.reasons) if g2 else None, "outcome": outcome,
                         "stage2_problems": rule_check(r2, s2) if s2 else ["관문 보류"],
                         "stage2_kadlint": [p.pattern[:20] for p, _ in kad if s2 and p.search(s2)]})
        print(f"{k + 1}  {time.time() - t0:.0f}s", flush=True)

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(rows)
    print("\n=== 요약 ===")
    print(f"합법화 불가 {sum(r['outcome'] == 'infeasible' for r in rows) // len(PERSONAS)}/{n // len(PERSONAS)} 문장 · "
          f"관문 통과 문장 {sum(not r['gate1'] for r in rows) // len(PERSONAS)}/{n // len(PERSONAS)} · "
          f"후보로 나간 것 {sum(r['outcome'] == 'candidate' for r in rows)}/{n} · "
          f"2단계 규칙 통과 {sum(not r['stage2_problems'] for r in rows)}/{n} · "
          f"1단계에 kadlint 금지 패턴 남음 {sum(bool(r['stage1_kadlint']) for r in rows) // len(PERSONAS)}/{n // len(PERSONAS)} 문장 · "
          f"2단계에 남음 {sum(bool(r['stage2_kadlint']) for r in rows)}/{n}")
    print(f"결과: {OUT}")


if __name__ == "__main__":
    main()
