"""1단계(위반 제거) → 관문 → [선택] 2단계(페르소나 말투) — 실제 광고 문구로 끝까지 돌려 본다 (2026-10-01).

🔄 최종 구조(10-01 정리): 1단계는 **v12**(`copylane_sllm_lora_adapter_v12` · 합법화 불가를 낼 수 있다).
   🔄 10-02 — v6 → v8. 같은 관문·재판정 · 고정 31개에서 위반 포장 0 은 같고 지나친 거절 5→4 · 살림 1→2 (결과서 11차).
   🔄 10-02 — v8 → v9. 살리기 평가 40 에서 살림 8 → 27 · 지나친 거절 20 → 0 · 포장 0 (결과서 12차).
   🔄 10-02 — v9 → v10. 정답이 지어낸 낱말을 고쳐 다시 학습 — 제품명 지어내기(「…로스팅한 곶감」)가 사라짐 (결과서 13차).
   🔄 10-05 — v10 → v12. 화장품 65행 — 실제 광고(학습에 없던 87) 지나친 거절 8 → 4 · 위반 포장 0(label_check 포함) (결과서 16차).
   종착은 셋 — `infeasible`(1단계가 합법화 불가) · `hold`(관문 · 규칙에 걸림) · `candidate`(후보).
   🚨 `candidate` 도 적법 확정이 아니다 — `--rejudge` 의 `no_violation` 은 통과 보증이 아니고 사람 검수가 남는다.

🔴 **페르소나는 사용자가 고객층을 고를 때만 입힌다** (10-01 · lse 판단).
   - 검수(진입점 A · `/judge`)의 기본 결과는 **1단계 문장 그대로**다 — 계약의 `JudgeRequest` 에 고객층이 없다.
   - 고객층을 고르면(생성 · 진입점 B 의 `GenerateRequest.segment` · 또는 화면에서 「이 고객층용으로」) **그 하나만** 2단계를 돌린다.
   - ⛔ 통과한 문장마다 페르소나를 자동으로 여럿 입히지 않는다 — 첫 실험(고정 3개 자동 적용)에서 「○○추출물 함유」 같은
     사실 표시에도 「가족의 건강을 생각하는 분들께,」가 붙어 어색했고, 고객층 선택은 마케터의 판단이지 모델의 일이 아니다.

입력: `persona_experiment.load_inputs()` 와 같은 실제 위반 문구(식약처 사례집 train · 재배포 불가 →
결과는 `_private/` 에만 쓴다) + 결과서의 고정 신규 문구.

실행 (repo 루트):
    .venv-sllm/Scripts/python.exe docs/lse/persona_pipeline_e2e.py                 # 페르소나 없이 (검수 기본)
    .venv-sllm/Scripts/python.exe docs/lse/persona_pipeline_e2e.py --persona q1    # 고른 고객층 하나만
    .venv-sllm/Scripts/python.exe docs/lse/persona_pipeline_e2e.py --rejudge       # 후보를 팀 판정 코어로 재판정(DB 필요)
    (--kadlint <kadlint 저장소 경로> 를 더하면 외부 금지 패턴으로도 센다 · 채점용)
"""

from __future__ import annotations

import argparse
import json
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
from postfix import (  # noqa: E402
    _CLAIM_HOLD,
    condition,
    label_check,
    repair_ingredients,
    to_approved_claim,
)
from rejudge import RejudgeUnavailable, rejudge  # noqa: E402
from stage_gate import check as gate  # noqa: E402
from train_persona_stage2 import SYSTEM as STAGE2_SYSTEM  # noqa: E402
from train_persona_stage2 import rule_check  # noqa: E402
from train_stage1_v5 import SYSTEM_V6 as STAGE1_SYSTEM  # noqa: E402
from train_stage1_v5 import parse as parse_stage1  # noqa: E402
from train_stage1_v5 import user_msg as stage1_user  # noqa: E402

ROOT = HERE.parents[1]
STAGE1_VER = "v12"  # 채택본 (10-05 · v6 → v8 → v9 → v10 → v12)
STAGE1 = ROOT / "models" / f"copylane_sllm_lora_adapter_{STAGE1_VER}"
STAGE2 = ROOT / "models" / "copylane_sllm_persona_adapter"
OUT = HERE / "_private" / "persona_pipeline_e2e.jsonl"
#: 고를 수 있는 고객층 — 🚨 D-27 고민 · 증상 축 없음. 실제 서비스에서는 세그먼트(`app.contracts.Segment.label`)가 들어온다
PERSONAS = {
    "p1": "30대 직장인 — 바쁜 일상 속 간편한 관리",
    "p2": "50대 — 가족과 함께하는 꾸준한 건강 습관",
    "p3": "20대 — 운동·자기관리 루틴을 즐기는 사람",
    "p4": "40대 맞벌이 부부 — 효율적으로 챙기는 생활",
    "p5": "60대 액티브 시니어 — 여행과 취미를 즐기는 일상",
    "p6": "20대 대학생 — 가성비와 트렌드에 민감",
    "q1": "30대 프리랜서 — 재택근무하며 자기 페이스대로 사는 사람",
    "q2": "40대 등산·캠핑 동호인 — 주말마다 야외 활동",
}


def chat(model, tok, system: str, user: str, n: int) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=n, do_sample=False)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)


def with_rejudge(res: dict, do_rejudge: bool) -> dict:
    """🆕 10-01 — 후보를 팀 판정 코어에 다시 넣는다(D-119 · `rejudge.py`). 위반이 확정되면 탈락(보류)시킨다.
    DB 가 없으면 `rejudge: unavailable` 로 적고 후보를 그대로 둔다 — 돌지 않은 재판정을 통과로 적지 않는다(D-146)."""
    if not do_rejudge or res["outcome"] != "candidate" or not res.get("final"):
        return res
    try:
        r = rejudge(res["final"])
    except RejudgeUnavailable as e:
        return {**res, "rejudge": "unavailable", "rejudge_note": str(e)}
    res = {**res, "rejudge": r.status, "rejudge_outcome": r.outcome, "rejudge_violations": list(r.violations),
           "rejudge_basis": list(r.basis), "rejudge_hold_reasons": list(r.hold_reasons)}
    if r.status == "rejected":
        # 탈락한 후보 문장은 남긴다 — 왜 떨어졌는지 사람이 보게(🆕 10-05)
        return {**res, "outcome": "hold", "final": None, "rejudge_body": res["final"]}
    return res


def run_one(model, tok, text: str, labels: list[str], persona: str | None = None, do_rejudge: bool = False) -> dict:
    """문구 하나 — 서비스가 부를 단위. `persona`(고객층 설명)를 주지 않으면 1단계 결과로 끝난다.
    `do_rejudge` 면 후보를 팀 판정 코어로 다시 판정한다(DB 필요)."""
    return with_rejudge(_run_one(model, tok, text, labels, persona), do_rejudge)


def _run_one(model, tok, text: str, labels: list[str], persona: str | None = None) -> dict:
    model.set_adapter("stage1")
    out1 = parse_stage1(chat(model, tok, STAGE1_SYSTEM, stage1_user({"input": text, "violation_types": labels}), 220))
    infeasible = out1.get("infeasible") if out1 else None
    s1 = out1.get("body") if out1 and not infeasible else None
    res = {"input": text, "stage1": s1, "infeasible": infeasible, "gate1": None, "persona": persona,
           "stage2": None, "gate2": None, "stage2_problems": None,
           "stage1_note": out1.get("mandatory_note") if out1 else None, "repairs": [], "note": None, "note_problem": None}
    if infeasible:
        return {**res, "outcome": "infeasible", "final": None}  # 증명서 경로(D-32 · D-125) — 고치지 않는다
    # 🆕 10-05 후처리(`postfix.py`) — 관문 전에 기계로 고칠 수 있는 실수를 고친다: 원료명 베끼기 · 지어낸 기능성 문구
    fixed, repairs = repair_ingredients(text, s1) if s1 else (s1, [])
    note_in = res["stage1_note"]
    g1 = gate(text, fixed)
    if (not g1.passed and any(r.startswith(_CLAIM_HOLD) for r in g1.reasons)
            and (ap := to_approved_claim(text, fixed, labels)) is not None):
        repairs.append(f"공식 기능성 문구로: {fixed} → {ap[0]}")
        fixed, note_in = ap
        g1 = gate(text, fixed)  # 🚨 고친 문장도 관문을 다시 지난다
    if fixed and g1.passed and (extra := label_check(text, fixed, labels)):
        g1 = type(g1)(False, tuple(g1.reasons) + tuple(extra))  # 🆕 10-05 — 위반 유형 · 주어 원료명(관문이 못 보는 것)
    note, note_problem = condition(fixed, note_in, text) if fixed else (None, None)
    res.update(stage1_fixed=fixed, repairs=repairs, note=note, note_problem=note_problem)
    # 🚨 관문 — 1단계가 위반을 못 지운 문장은 내보내지도, 말투로 포장하지도 않는다
    res["gate1"] = list(g1.reasons)
    if not g1.passed:
        return {**res, "outcome": "hold", "final": None}
    s1 = fixed
    if not persona:
        return {**res, "outcome": "candidate", "final": s1}  # 검수 기본 — 위반을 뺀 문장 그대로 + 조건(`note`)
    model.set_adapter("stage2")
    raw = chat(model, tok, STAGE2_SYSTEM, f"검수 통과 문장: {s1}\n대상 고객: {persona}", 160)
    i, j = raw.find("{"), raw.rfind("}")
    try:
        s2 = json.loads(raw[i:j + 1])["body"]
    except Exception:  # noqa: BLE001 — 형식 실패는 보류로
        s2 = None
    probs = rule_check({"input": s1, "persona_label": persona}, s2)
    g2 = gate(s1, s2) if s2 else None  # 말투를 입히다 위반을 들여오지 않았는지 — 같은 관문을 다시 지난다
    res.update(stage2=s2, gate2=list(g2.reasons) if g2 else None, stage2_problems=probs)
    if not s2 or probs or not g2.passed:
        # 2단계가 실패해도 1단계 문장은 이미 관문을 넘었다 — 말투만 포기하고 1단계 문장을 낸다
        return {**res, "outcome": "candidate", "final": s1, "persona_failed": True}
    return {**res, "outcome": "candidate", "final": s2}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", choices=sorted(PERSONAS), default=None,
                    help="고른 고객층 하나 — 없으면 페르소나 없이(검수 기본)")
    ap.add_argument("--kadlint", type=Path, default=None)
    ap.add_argument("--rejudge", action="store_true", help="후보를 팀 판정 코어로 재판정(DB 필요)")
    ap.add_argument("--stage1", default=STAGE1_VER, help=f"1단계 어댑터 버전(비교용) — 기본 {STAGE1_VER}(채택본)")
    args = ap.parse_args()
    stage1 = ROOT / "models" / f"copylane_sllm_lora_adapter_{args.stage1}"
    kad = load_kadlint(args.kadlint) if args.kadlint else []
    persona = PERSONAS[args.persona] if args.persona else None

    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(stage1), adapter_name="stage1")
    model.load_adapter(str(STAGE2), adapter_name="stage2")
    model.eval()
    t0 = time.time()
    rows, seen = [], set()
    for row in load_inputs():
        if row["input"] in seen:
            continue
        seen.add(row["input"])
        r = run_one(model, tok, row["input"], row["labels"], persona, do_rejudge=args.rejudge)
        r["kadlint_final"] = [p.pattern[:20] for p, _ in kad if r["final"] and p.search(r["final"])]
        rows.append({**row, **r})
        print(f"{len(rows)}  {r['outcome']}  {time.time() - t0:.0f}s", flush=True)

    tag = "" if args.stage1 == STAGE1_VER else f"_{args.stage1}"
    out = OUT.with_name(f"persona_pipeline_e2e_{args.persona or 'none'}{tag}.jsonl")
    out.parent.mkdir(exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(rows)
    c = {k: sum(r["outcome"] == k for r in rows) for k in ("infeasible", "hold", "candidate")}
    print("\n=== 요약 ===")
    print(f"문구 {n} · 합법화 불가 {c['infeasible']} · 보류 {c['hold']} · 후보 {c['candidate']}"
          + (f" (말투 실패로 1단계 문장을 낸 것 {sum(bool(r.get('persona_failed')) for r in rows)})" if persona else "")
          + (f" · 최종 문장에 kadlint 금지 패턴 {sum(bool(r['kadlint_final']) for r in rows)}" if kad else ""))
    if args.rejudge:
        rj: dict[str, int] = {}
        for r in rows:
            if r.get("rejudge"):
                rj[r["rejudge"]] = rj.get(r["rejudge"], 0) + 1
        print(f"재판정: {rj} (rejected 는 보류로 내렸다 · no_violation 은 통과 보증이 아니다)")
    print(f"결과: {out}")


if __name__ == "__main__":
    main()
