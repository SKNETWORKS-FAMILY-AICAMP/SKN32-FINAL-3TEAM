"""페르소나 입힌 재작성 — 실제 광고 문구로 1차 실험 (2026-10-01).

배경: 보수/균형/공격 3안 학습 데이터가 실제로는 없다(식약처 수정쌍 245는 판정 J1 (b)로
인코더 평가 전용). 조장 제안 — 페르소나를 입혀 실제 광고 문구만으로 간다.
이 스크립트는 **학습 없이** 프롬프트에 페르소나(`app.contracts.Segment` 모양)를 넣어
Qwen2.5-3B-Instruct(원본) vs 3B+LoRA(4차 어댑터)를 비교한다.

입력: `golden.jsonl` 의 `mfds_casebook` **train** 실제 위반 문구(인코더 평가셋은 안 쓴다)
      + 1~4차 결과서의 고정 신규 문구 3개(비교 연속성 · 공정위 인용 문구는 뺐다).
채점: RewriteSet 스키마 · 판정 인코더 후보 수 · 금지어 사전 적중 · D-27(고민·증상 소구) ·
      원문에 없던 숫자 · 페르소나 간 문장 차이.

실행 (repo 루트, GPU 전용 venv):
    .venv-sllm/Scripts/python.exe docs/lse/persona_experiment.py
"""

from __future__ import annotations

import difflib
import itertools
import json
import random
import re
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.contracts import RewriteSet, Segment  # noqa: E402
from app.encoder import JudgeEncoder  # noqa: E402

BASE = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER = ROOT / "models" / "copylane_sllm_lora_adapter"
# 🔒 결과에 재배포 불가 원천(식약처 사례집) 문구가 들어간다 — git 이 무시하는 _private 에 둔다
OUT = ROOT / "docs" / "lse" / "_private" / "persona_experiment_results.jsonl"
N_REAL = 30
SEED = 20261001

# 🚨 D-27 — pain point 축은 넣지 않는다. 인구통계 · 라이프스타일 · 목표만.
PERSONAS = [
    Segment(segment_id="p1", label="30대 직장인 — 바쁜 일상 속 간편한 관리", member_count=20,
            top_terms=["간편", "출근 전", "하루 한 번", "휴대"]),
    Segment(segment_id="p2", label="50대 — 가족과 함께하는 꾸준한 건강 습관", member_count=20,
            top_terms=["꾸준히", "원료", "가족", "믿음"]),
    Segment(segment_id="p3", label="20대 — 운동·자기관리 루틴을 즐기는 사람", member_count=20,
            top_terms=["루틴", "운동", "데일리", "트렌디"]),
]

FIXED = [
    "당뇨병 환자도 안심하고 드실 수 있는 치료 효과",
    "이 크림 바르면 주름이 완전히 사라집니다",
    "국내 1위 다이어트 보조제, 3일만에 5kg 감량",
]

SYSTEM = (
    "당신은 광고 문구 준법 검수 보조 도구입니다. 위반 소지가 있는 광고 문구를 교정할 때 "
    "반드시 다음 순서를 따릅니다.\n"
    "1) 문구에서 핵심 주장을 찾는다 — 핵심 주장은 삭제하지 않는다.\n"
    "2) 위반 요소(질병 치료·예방 표현, 의약품 오인, 최상급·단정, 근거 없는 수치·비교)만 제거하거나 완화한다.\n"
    "3) 주어진 대상 고객에게 자연스럽게 읽히는 말투와 강조점으로 다시 쓴다.\n"
    "지켜야 할 것: 원문에 없는 사실·숫자·인증을 새로 만들지 않는다. "
    "고민·증상·불편을 건드리는 표현(예: '~로 고민이세요?')을 쓰지 않는다.\n"
    "출력은 먼저 \"핵심 주장: ...\" 한 줄, 그다음 줄에 JSON만 씁니다. "
    '형식: {"body": "본문", "mandatory_note": "필수 병기 문구 또는 null", '
    '"placement": "배치 지시 또는 null"}'
)

PAIN_WORDS = ("고민", "걱정", "증상", "불편", "괴로", "스트레스", "아프", "통증")  # redistribution: ok — 일반어(D-27 검사용)


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s or "")


def load_inputs() -> list[dict]:
    rows = [json.loads(line) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    pool = [r for r in rows if r["provenance"] == "mfds_casebook" and r["split"] == "train"
            and len(norm(r["text"])) >= 6 and r["labels"]]
    random.Random(SEED).shuffle(pool)
    # 유형이 한쪽에 몰리지 않게 라벨별로 돌아가며 뽑는다
    by_label: dict[str, list[dict]] = {}
    for r in pool:
        by_label.setdefault(r["labels"][0], []).append(r)
    picked: list[dict] = []
    for group in itertools.cycle(list(by_label.values())):
        if len(picked) >= N_REAL or not any(by_label.values()):
            break
        if group:
            picked.append(group.pop())
    real = [{"input": r["text"], "labels": r["labels"], "source": r["id"]} for r in picked]
    return real + [{"input": t, "labels": [], "source": "fixed"} for t in FIXED]


def user_prompt(row: dict, persona: Segment) -> str:
    types = ", ".join(row["labels"]) or "(미상)"
    return (f"위반 문구: {row['input']}\n위반 유형: {types}\n"
            f"대상 고객: {persona.label}\n대상 고객이 자주 쓰는 말: {', '.join(persona.top_terms)}")


def load_banned() -> list[str]:
    terms = []
    for line in (ROOT / "data/derived/banned_terms.jsonl").open(encoding="utf-8"):
        t = norm(json.loads(line)["term"].replace("*", ""))
        if len(t) >= 2:
            terms.append(t)
    return terms


def generate(model, tok, row: dict, persona: Segment) -> str:
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt(row, persona)}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=220, do_sample=False)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)


def parse(raw: str) -> tuple[str, RewriteSet | None]:
    i = raw.find("{")
    if i == -1:
        return raw.strip(), None
    j = raw.rfind("}")
    try:
        return raw[:i].strip(), RewriteSet.model_validate_json(raw[i:j + 1])
    except Exception:  # noqa: BLE001 — 실패 사례를 그대로 센다
        return raw[:i].strip(), None


def score(row: dict, rs: RewriteSet | None, enc: JudgeEncoder, banned: list[str]) -> dict:
    if rs is None:
        return {"schema_ok": False}
    body = rs.body
    pred = enc.predict(body)
    nb = norm(body)
    return {
        "schema_ok": True,
        "encoder_flags": [c.violation.value for c in pred.candidates],
        "banned_hits": [t for t in banned if t in nb][:5],
        "pain_hits": [w for w in PAIN_WORDS if w in body and w not in row["input"]],
        "new_numbers": sorted(set(re.findall(r"\d+", body)) - set(re.findall(r"\d+", row["input"]))),
        "input_similarity": round(difflib.SequenceMatcher(None, row["input"], body).ratio(), 3),
    }


def main() -> None:
    inputs = load_inputs()
    banned = load_banned()
    enc = JudgeEncoder()
    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(ADAPTER))
    model.eval()
    print(f"입력 {len(inputs)} × 페르소나 {len(PERSONAS)} × 모델 2", flush=True)

    results = []
    t0 = time.time()
    for variant in ("base", "lora"):
        for k, row in enumerate(inputs):
            for p in PERSONAS:
                if variant == "base":
                    with model.disable_adapter():
                        raw = generate(model, tok, row, p)
                else:
                    raw = generate(model, tok, row, p)
                core, rs = parse(raw)
                rec = {"variant": variant, "persona": p.segment_id, **row, "core": core, "raw": raw,
                       "body": rs.body if rs else None,
                       "mandatory_note": rs.mandatory_note if rs else None, **score(row, rs, enc, banned)}
                results.append(rec)
            print(f"[{variant}] {k + 1}/{len(inputs)}  {time.time() - t0:.0f}s", flush=True)

    with OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n=== 요약 ===")
    for variant in ("base", "lora"):
        rs = [r for r in results if r["variant"] == variant]
        ok = [r for r in rs if r["schema_ok"]]
        n = len(rs)
        div = []
        for row in inputs:
            bodies = [r["body"] for r in ok if r["input"] == row["input"]]
            if len(bodies) == 3:
                sims = [difflib.SequenceMatcher(None, a, b).ratio() for a, b in itertools.combinations(bodies, 2)]
                div.append(1 - sum(sims) / 3)
        print(f"[{variant}] 스키마 {len(ok)}/{n} · 인코더 위반후보 남음 {sum(bool(r['encoder_flags']) for r in ok)} · "
              f"금지어 {sum(bool(r['banned_hits']) for r in ok)} · D-27 고민소구 {sum(bool(r['pain_hits']) for r in ok)} · "
              f"새 숫자 {sum(bool(r['new_numbers']) for r in ok)} · 원문 유사도 평균 "
              f"{sum(r['input_similarity'] for r in ok) / max(len(ok), 1):.2f} · 페르소나 간 차이 평균 "
              f"{sum(div) / max(len(div), 1):.2f}")
    print(f"\n결과: {OUT}")


if __name__ == "__main__":
    main()
