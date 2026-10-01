"""2단계(페르소나 말투) LoRA 학습 · 평가 (2026-10-01).

1단계(`models/copylane_sllm_lora_adapter`)가 위반을 지운 **적법 문장**을 받아, 대상 고객에게 말을 거는
형태로만 다듬는다. 기능성 주장 · 단서(「인체시험을 통한 확인이 필요」)는 그대로 둔다.

데이터: `persona_inputs.jsonl`(입력 · 분할 — `build_persona_inputs.py`) + `persona_targets.jsonl`(정답 ·
Claude 초안 · 법률 미검토). 원천은 식약처 기능성 원료 고시 문구(재배포 가능)뿐이다.

🚨 누수 방지 — 학습 전에 다시 확인하고 어기면 멈춘다 (팀장 조건 2026-10-01):
  ① 입력이 판정 인코더 데이터(golden)와 겹치지 않는다
  ② 학습 · 평가 주제가 겹치지 않는다
  ③ 평가 전용 페르소나(q*)가 학습에 없다
  ④ 채점에 판정 인코더를 쓰지 않는다 — 규칙 검사 + 사람 확인

실행 (repo 루트, GPU venv):
    .venv-sllm/Scripts/python.exe docs/lse/train_persona_stage2.py            # 학습 + 평가
    .venv-sllm/Scripts/python.exe docs/lse/train_persona_stage2.py --eval-only
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, get_cosine_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[2]
LSE = ROOT / "docs" / "lse"
BASE = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER = ROOT / "models" / "copylane_sllm_persona_adapter"
# 평가 출력은 공개 원천 문장뿐이지만, 실험 산출물은 한곳(_private)에 모은다
OUT = LSE / "_private" / "persona_stage2_eval.jsonl"
SEED = 20261001
EPOCHS, LR, MAX_LEN = 3, 2e-4, 384

SYSTEM = (
    "당신은 광고 카피라이터입니다. 이미 법률 검수를 통과한 건강기능식품 문장을 받아, 대상 고객에게 "
    "말을 거는 형태로 다듬습니다.\n"
    "반드시 지킬 것:\n"
    "- 기능성 주장 문구와 범위는 그대로 둔다. '도움을 줄 수 있음' 같은 완화 표현을 세게 바꾸지 않는다.\n"
    "- '인체시험을 통한 확인이 필요', '관련 인체적용시험이 미흡', '과학적 근거가 부족' 같은 단서는 반드시 남긴다.\n"
    "- 대상 고객은 말을 거는 대상으로만 쓴다. 효과를 암시하는 묘사, 제품 형태·섭취 횟수·가격·인기 같은 새 사실을 더하지 않는다.\n"
    "- 새 숫자·인증·후기·비교를 더하지 않는다. 고민·증상·불편을 건드리는 표현을 쓰지 않는다.\n"
    '출력은 JSON 한 줄만: {"body": "다듬은 문장"}'
)

CAVEAT = re.compile(r"확인이 필요|미흡|근거가 부족")
STRONG = re.compile(r"개선합니다|개선해요|감소시킵니다|완화합니다|확실|효과적|최고|보장|100%|완벽")
PAIN = ("고민", "걱정", "증상", "불편", "괴로", "통증", "아프")  # redistribution: ok — 일반어
#: 1차 평가(10-01)에서 원본 3B 가 원문에 없는 적합성 주장(「추천드립니다」 · 「특히 적합」)을 붙였다
SUIT = re.compile(r"추천|적합|딱 맞|안성맞춤|필수")
#: 1차 LoRA 가 정답 6개의 「50대 중 혈압이 높은 분」 문형을 다른 주제에 퍼뜨렸다(「프리랜서 중 기억력 개선에」)
ODD = re.compile(r"(프리랜서|직장인|대학생|\d0대|시니어|부부|분들?) 중 ")


def load() -> list[dict]:
    targets = {r["id"]: r["target"] for r in map(json.loads, (LSE / "persona_targets.jsonl").open(encoding="utf-8"))}
    rows = [json.loads(line) for line in (LSE / "persona_inputs.jsonl").open(encoding="utf-8")]
    for r in rows:
        r["target"] = targets[r["id"]]
    return rows


def leak_guard(rows: list[dict]) -> None:
    norm = lambda s: re.sub(r"[\s\W_]+", "", s or "")  # noqa: E731
    golden = [norm(json.loads(line)["text"]) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    gset, gblob = set(golden), "\n".join(golden)
    hit = [r["id"] for r in rows if norm(r["input"]) in gset or norm(r["input"]) in gblob]
    assert not hit, f"① golden 과 겹치는 입력: {hit[:5]}"
    tr = {r["group"] for r in rows if r["split"] == "train"}
    ev = {r["group"] for r in rows if r["split"] == "eval"}
    assert not tr & ev, f"② 학습 · 평가 주제 겹침: {tr & ev}"
    assert not {r["persona"] for r in rows if r["split"] == "train" and r["persona"].startswith("q")}, "③ 평가 페르소나가 학습에 있다"
    print(f"누수 검사 통과 — 학습 주제 {len(tr)} · 평가 주제 {len(ev)} · golden 겹침 0")


def user_msg(r: dict) -> str:
    return f"검수 통과 문장: {r['input']}\n대상 고객: {r['persona_label']}"


def rule_check(r: dict, body: str | None) -> list[str]:
    if not body:
        return ["형식 실패"]
    s, p = r["input"], []
    if CAVEAT.search(s) and not CAVEAT.search(body):
        p.append("단서 빠짐")
    if CAVEAT.search(body) and not CAVEAT.search(s):
        p.append("없던 단서 추가")  # 원문에 없는 「근거 부족」을 지어 붙이면 사실 왜곡이다
    if SUIT.search(body):
        p.append("적합·추천 주장")
    if ODD.search(body):
        p.append("어색한 '~중' 문형")
    allowed = set(re.findall(r"\d+", s + r["persona_label"]))
    if set(re.findall(r"\d+", body)) - allowed:
        p.append("새 숫자")
    if [w for w in PAIN if w in body and w not in s]:
        p.append("고민·증상")
    if STRONG.search(body):
        p.append("강한 표현")
    if "도움" in s and "도움" not in body:
        # 원문에 완화 표현이 있을 때만 — 「버섯추출물 함유」 같은 사실 표시에는 처음부터 없다
        p.append("완화 표현 빠짐")
    return p


def claim_kept(r: dict, body: str | None) -> float:
    """원문 주장이 본문에 얼마나 남았나 — 원문 각 글자 묶음이 본문에 이어서 나오는 비율."""
    if not body:
        return 0.0
    m = SequenceMatcher(None, r["input"].replace(" ", ""), body.replace(" ", ""))
    return sum(b.size for b in m.get_matching_blocks()) / max(len(r["input"].replace(" ", "")), 1)


def train(model, tok, rows: list[dict]) -> None:
    data = []
    for r in rows:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg(r)}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        full = prompt + json.dumps({"body": r["target"]}, ensure_ascii=False) + tok.eos_token
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        ids = tok(full, add_special_tokens=False, truncation=True, max_length=MAX_LEN)["input_ids"]
        labels = [-100] * min(len(p_ids), len(ids)) + ids[len(p_ids):]
        data.append((ids, labels))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR)
    steps = EPOCHS * len(data)
    sched = get_cosine_schedule_with_warmup(opt, int(0.05 * steps), steps)
    model.train()
    rng = random.Random(SEED)
    for ep in range(EPOCHS):
        rng.shuffle(data)
        tot = 0.0
        for ids, labels in data:
            out = model(input_ids=torch.tensor([ids], device=model.device),
                        labels=torch.tensor([labels], device=model.device))
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            tot += out.loss.item()
        print(f"epoch {ep + 1}/{EPOCHS} loss {tot / len(data):.4f}", flush=True)
    model.eval()


def generate(model, tok, r: dict) -> str | None:
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg(r)}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=160, do_sample=False)
    raw = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    i, j = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[i:j + 1])["body"]
    except Exception:  # noqa: BLE001 — 형식 실패로 센다
        return None


def evaluate(model, tok, rows: list[dict], variant: str) -> list[dict]:
    res = []
    for r in rows:
        body = generate(model, tok, r)
        res.append({"variant": variant, **{k: r[k] for k in ("id", "group", "persona", "input", "target")},
                    "body": body, "problems": rule_check(r, body), "claim_kept": round(claim_kept(r, body), 3)})
    ok = [x for x in res if not x["problems"]]
    div = []
    for _, grp in itertools.groupby(sorted(res, key=lambda x: x["input"]), key=lambda x: x["input"]):
        b = [x["body"] for x in grp if x["body"]]
        if len(b) == 3:
            div.append(1 - sum(SequenceMatcher(None, a, c).ratio() for a, c in itertools.combinations(b, 2)) / 3)
    probs: dict[str, int] = {}
    for x in res:
        for p in x["problems"]:
            probs[p] = probs.get(p, 0) + 1
    unseen = [x for x in res if x["persona"].startswith("q")]
    print(f"[{variant}] 규칙 통과 {len(ok)}/{len(res)} (처음 보는 페르소나 {sum(not x['problems'] for x in unseen)}/{len(unseen)}) · "
          f"주장 보존 평균 {sum(x['claim_kept'] for x in res) / len(res):.2f} · 페르소나 간 차이 {sum(div) / max(len(div), 1):.2f} · 문제 {probs}",
          flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()
    torch.manual_seed(SEED)
    rows = load()
    leak_guard(rows)
    train_rows = [r for r in rows if r["split"] == "train"]
    eval_rows = [r for r in rows if r["split"] == "eval"]
    # 정답 자체도 규칙을 지켜야 한다 — 어기면 학습 재료가 틀린 것이다
    bad = [(r["id"], rule_check(r, r["target"])) for r in rows if rule_check(r, r["target"])]
    assert not bad, f"정답이 규칙을 어긴다: {bad[:5]}"

    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    t0 = time.time()
    if args.eval_only:
        model = PeftModel.from_pretrained(base, str(ADAPTER))
    else:
        base.gradient_checkpointing_enable()
        base.enable_input_require_grads()
        model = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, task_type="CAUSAL_LM",
                                                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]))
        model.print_trainable_parameters()
        print(f"학습 {len(train_rows)}쌍 · 평가 {len(eval_rows)}쌍", flush=True)
        train(model, tok, train_rows)
        model.save_pretrained(ADAPTER)
        print(f"어댑터 저장 {ADAPTER} · {time.time() - t0:.0f}s", flush=True)
    model.config.use_cache = True

    with model.disable_adapter():
        res_base = evaluate(model, tok, eval_rows, "base(프롬프트만)")
    res_lora = evaluate(model, tok, eval_rows, "persona-LoRA")
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for x in res_base + res_lora:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"결과: {OUT} · {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
