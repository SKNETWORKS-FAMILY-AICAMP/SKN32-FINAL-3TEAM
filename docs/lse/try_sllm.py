"""직접 문구를 넣어 보는 시험 도구 — 1단계(v8 · 10-02 채택) → 관문 → [선택] 2단계(페르소나) (2026-10-01).

모델을 한 번 올리고(약 30초) 문구를 계속 넣어 볼 수 있다. 결과는 화면에만 찍고 파일로 남기지 않는다.

실행 (repo 루트, GPU venv):
    .venv-sllm/Scripts/python.exe docs/lse/try_sllm.py
    .venv-sllm/Scripts/python.exe docs/lse/try_sllm.py "국내 1위 다이어트 차" --types 거짓_과장 --persona q1

대화형에서 한 줄 형식:  문구 | 위반유형(쉼표) | 고객층코드
    예) 먹기만 해도 살 빠지는 차 | 거짓_과장 | p1
    위반유형 · 고객층은 생략 가능 · 빈 줄이면 끝.
🚨 결과는 적법 확정이 아니다 — 재판정(판정 코어)이 연결되지 않았고 사람 검수가 필요하다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from persona_experiment import BASE  # noqa: E402
from persona_pipeline_e2e import PERSONAS, STAGE1, STAGE2, run_one  # noqa: E402

OUTCOME = {"infeasible": "⛔ 합법화 불가", "hold": "🟡 보류(사람 검토)", "candidate": "✅ 후보"}


def show(r: dict) -> None:
    print(f"  결과   : {OUTCOME[r['outcome']]}")
    if r["infeasible"]:
        print(f"  사유   : {r['infeasible']}")
    if r["stage1"]:
        print(f"  1단계  : {r['stage1']}")
    if r["gate1"]:
        print(f"  관문   : {', '.join(r['gate1'])}")
    if r["persona"]:
        print(f"  고객층 : {r['persona']}")
        if r.get("persona_failed"):
            print(f"  2단계  : (실패 — {', '.join(r['stage2_problems'] or []) or '관문'}) → 1단계 문장을 냄")
    if r["final"]:
        print(f"  최종   : {r['final']}")
    if r.get("rejudge"):
        msg = {"rejected": "⛔ 위반 확정 → 탈락", "no_violation": "위반 미검출 (통과 보증 아님)", "passed": "✅ 통과",
               "unavailable": "재판정 못 함 (DB 없음)"}[r["rejudge"]]
        extra = f" · {', '.join(r.get('rejudge_violations') or [])}" if r.get("rejudge_violations") else ""
        print(f"  재판정 : {msg}{extra}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", help="시험할 광고 문구 — 없으면 대화형")
    ap.add_argument("--types", default="", help="위반 유형(쉼표) — 실제로는 판정 인코더가 준다")
    ap.add_argument("--persona", choices=sorted(PERSONAS), default=None)
    ap.add_argument("--rejudge", action="store_true", help="후보를 팀 판정 코어로 재판정(DB 필요)")
    args = ap.parse_args()

    print("모델 올리는 중 (약 30초)…", flush=True)
    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(STAGE1), adapter_name="stage1")
    model.load_adapter(str(STAGE2), adapter_name="stage2")
    model.eval()
    print("고객층 코드: " + " · ".join(f"{k}={v.split(' — ')[0]}" for k, v in PERSONAS.items()) + "\n")

    def once(text: str, types: str, pcode: str | None) -> None:
        labels = [t.strip() for t in types.split(",") if t.strip()]
        persona = PERSONAS.get(pcode) if pcode else None
        print(f"■ {text}" + (f"  [{', '.join(labels)}]" if labels else ""))
        show(run_one(model, tok, text, labels, persona, do_rejudge=args.rejudge))

    if args.text:
        once(args.text, args.types, args.persona)
        return
    print("문구 | 위반유형 | 고객층코드  (빈 줄이면 끝)")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            break
        parts = [p.strip() for p in line.split("|")] + ["", ""]
        once(parts[0], parts[1], parts[2] or None)


if __name__ == "__main__":
    main()
