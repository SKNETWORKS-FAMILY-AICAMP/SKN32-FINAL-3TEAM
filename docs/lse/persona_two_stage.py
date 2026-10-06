"""페르소나 2단계 — 1단계 LoRA가 위반을 지우고, 2단계 원본 3B가 말투만 입힌다 (2026-10-01).

`persona_experiment.py`(1단 · 프롬프트에 페르소나)의 결과: 원본 3B 는 다양하지만 위반을 남기고,
LoRA 는 위반을 지우지만 페르소나를 무시했다. 그래서 일을 나눈다.

- 1단계(LoRA): 학습 때와 **같은** 프롬프트(노트북 셀 9)로 교정만 한다 — 페르소나 없음.
- 2단계(원본 3B, 어댑터 끔): 1단계 본문만 보고 페르소나 말투를 입힌다.
  🚨 **원문을 보여 주지 않는다** — 지운 위반을 다시 끌어오지 못하게.

채점(1단 실험과 같은 것 + 재유입):
  재유입 = 원문에는 있었고 1단계가 지운 낱말이 2단계에서 다시 나온 것.
  🚨 판정 인코더는 생성 문장에 과다 예측한다(1단 실험 · v7 결과서) — 절대값이 아니라
     **1단계 대비 늘었나/줄었나**만 본다.

`--kadlint <kadlint 저장소 경로>` 를 주면 2단계에 **대체 표현 힌트**를 넣는다
(https://github.com/feelyday/kadlint · MIT). 원문에 걸린 규칙의 `alternatives` 를 「이런 결로」 참고로만 준다.
🚨 외부 데이터라 팀 원천 등록 전에는 저장소에 복사하지 않고 경로로만 읽는다.
   특정 브랜드(키스아머) 내부 방침 규칙과 `_needs_review.json` 은 쓰지 않는다.

실행 (repo 루트):
    .venv-sllm/Scripts/python.exe docs/lse/persona_two_stage.py
    .venv-sllm/Scripts/python.exe docs/lse/persona_two_stage.py --kadlint <경로>
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import re
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.contracts import RewriteSet  # noqa: E402
from app.encoder import JudgeEncoder  # noqa: E402
from persona_experiment import ADAPTER, BASE, PAIN_WORDS, PERSONAS, load_inputs, parse  # noqa: E402

# 🔒 결과에 재배포 불가 원천 문구가 들어간다 — git 이 무시하는 _private 에 둔다
OUT = ROOT / "docs" / "lse" / "_private" / "persona_two_stage_results.jsonl"

# 노트북 셀 9 그대로 — LoRA 가 학습한 형식
STAGE1_SYSTEM = (
    "당신은 광고 문구 준법 검수 보조 도구입니다. 위반 소지가 있는 광고 문구를 교정할 때 "
    "반드시 다음 순서를 따릅니다.\n"
    "1) 문구에서 핵심 주장(무엇에 대한 효능·성분·비교인지)을 찾는다 — 이 핵심 주장은 "
    "절대 삭제하지 않는다.\n"
    "2) 위반 요소(수치·최상급·단정 표현·부당 비교·허위 인증 등)만 정확히 찾아 제거하거나 "
    "완화한다.\n"
    "3) 핵심 주장은 그대로 남기고, 위반 요소만 뺀 자연스러운 문장으로 다시 쓴다.\n"
    "출력은 먼저 \"핵심 주장: ...\" 한 줄, 그다음 줄에 JSON만 씁니다. "
    '형식: {"body": "본문(핵심 주장 유지)", "mandatory_note": "필수 병기 문구 또는 null", '
    '"placement": "배치 지시 또는 null"}'
)

STAGE2_SYSTEM = (
    "당신은 광고 카피라이터입니다. 이미 법률 검수를 통과한 문장을 받아, 대상 고객에게 더 "
    "자연스럽고 매력적으로 읽히도록 **말투와 어순만** 다듬습니다.\n"
    "반드시 지킬 것:\n"
    "- 문장이 말하는 효과·성분·주장의 **범위를 넓히거나 세게 만들지 않는다.** "
    "'도움을 줄 수 있음' 같은 완화 표현의 뜻은 유지한다(말투는 바꿔도 된다).\n"
    "- 새 효과·숫자·인증·비교·후기를 더하지 않는다.\n"
    "- 질병명, 치료·예방·완치, 고민·증상·불편을 건드리는 표현을 쓰지 않는다.\n"
    "- 대상 고객 단어는 자연스러울 때만 쓴다. 억지로 끼워 넣지 않는다.\n"
    "- 한 문장, 40자 안팎.\n"
    '출력은 JSON 한 줄만: {"body": "다듬은 문장"}'
)


def chat(model, tok, system: str, user: str, max_new: int) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", s or "")}


def reintroduced(original: str, stage1: str, stage2: str) -> list[str]:
    """원문에 있었고 1단계가 지운 낱말이 2단계에 다시 나온 것 — 앞 2글자 어근으로 본다."""
    s1 = (stage1 or "").replace(" ", "")
    removed = {w for w in words(original) if w[:2] not in s1}
    s2 = (stage2 or "").replace(" ", "")
    return sorted(w for w in removed if w[:2] in s2)


def load_kadlint(path: Path) -> list[tuple[re.Pattern[str], list[str]]]:
    rules = []
    for domain in ("common", "cosmetics", "health_food"):
        for r in json.loads((path / "data" / f"{domain}.json").read_text(encoding="utf-8"))["rules"]:
            if "키스아머" in json.dumps(r, ensure_ascii=False):
                continue
            src = r["pattern"] if r["pattern_type"] == "regex" else re.escape(r["pattern"])
            rules.append((re.compile(src), r["alternatives"]))
    return rules


def hints_for(text: str, rules: list[tuple[re.Pattern[str], list[str]]], limit: int = 4) -> list[str]:
    out: list[str] = []
    for pat, alts in rules:
        if pat.search(text):
            out.extend(a for a in alts if a not in out)
    return out[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kadlint", type=Path, default=None)
    args = ap.parse_args()
    kad = load_kadlint(args.kadlint) if args.kadlint else None
    out_path = OUT.with_name("persona_two_stage_kadlint_results.jsonl") if kad else OUT

    inputs = load_inputs()
    enc = JudgeEncoder()
    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(ADAPTER))
    model.eval()
    t0 = time.time()

    results = []
    for k, row in enumerate(inputs):
        types = ", ".join(row["labels"]) or "(미상)"
        raw1 = chat(model, tok, STAGE1_SYSTEM, f"위반 문구: {row['input']}\n위반 유형: {types}\n근거: (미상)", 220)
        _, rs1 = parse(raw1)
        s1 = rs1.body if rs1 else None
        f1 = [c.violation.value for c in enc.predict(s1).candidates] if s1 else None
        # 힌트는 원문으로 찾되 원문 자체는 2단계에 넘기지 않는다
        hints = hints_for(row["input"], kad) if kad else []
        for p in PERSONAS:
            s2 = None
            raw2 = ""
            if s1:
                user = (f"검수 통과 문장: {s1}\n대상 고객: {p.label}\n"
                        f"대상 고객이 자주 쓰는 말(참고만): {', '.join(p.top_terms)}")
                if hints:
                    user += ("\n참고할 만한 안전한 표현 결(그대로 베끼지 말고, 괄호 속 조건이 필요한 표현은 "
                             f"쓰지 않는다): {' / '.join(hints)}")
                with model.disable_adapter():
                    raw2 = chat(model, tok, STAGE2_SYSTEM, user, 120)
                i, j = raw2.find("{"), raw2.rfind("}")
                try:
                    s2 = RewriteSet.model_validate_json(raw2[i:j + 1]).body
                except Exception:  # noqa: BLE001 — 실패를 센다
                    s2 = None
            f2 = [c.violation.value for c in enc.predict(s2).candidates] if s2 else None
            results.append({
                **row, "persona": p.segment_id, "hints": hints, "stage1": s1, "stage1_flags": f1, "stage2": s2,
                "stage2_raw": raw2, "stage2_flags": f2,
                "reintroduced": reintroduced(row["input"], s1, s2) if s2 else None,
                "pain_hits": [w for w in PAIN_WORDS if s2 and w in s2 and w not in row["input"]],
                "new_numbers": sorted(set(re.findall(r"\d+", s2 or "")) - set(re.findall(r"\d+", s1 or ""))),
            })
        print(f"{k + 1}/{len(inputs)}  {time.time() - t0:.0f}s", flush=True)

    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = [r for r in results if r["stage2"]]
    div = []
    for row in inputs:
        b = [r["stage2"] for r in ok if r["input"] == row["input"]]
        if len(b) == 3:
            div.append(1 - sum(difflib.SequenceMatcher(None, x, y).ratio() for x, y in itertools.combinations(b, 2)) / 3)
    more = sum(len(r["stage2_flags"]) > len(r["stage1_flags"] or []) for r in ok)
    less = sum(len(r["stage2_flags"]) < len(r["stage1_flags"] or []) for r in ok)
    print("\n=== 요약 ===")
    print(f"2단계 형식 {len(ok)}/{len(results)} · 페르소나 간 차이 평균 {sum(div) / max(len(div), 1):.2f} · "
          f"인코더 후보 늘어남 {more} / 줄어듦 {less} · 재유입 {sum(bool(r['reintroduced']) for r in ok)} · "
          f"D-27 {sum(bool(r['pain_hits']) for r in ok)} · 새 숫자 {sum(bool(r['new_numbers']) for r in ok)}")
    if kad:
        h = [r for r in ok if r["hints"]]
        print(f"힌트 받은 행 {len(h)} · 그중 재유입 {sum(bool(r['reintroduced']) for r in h)}")
    print(f"결과: {out_path}")


if __name__ == "__main__":
    main()
