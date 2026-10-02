"""1단계(위반 제거) v5 — 「고칠 수 없음」을 배운다 (2026-10-01).

v4(`models/copylane_sllm_lora_adapter`)의 실패: 학습 정답 784개가 전부 「○○에 도움을 줄 수 있음」이라,
실제 광고의 질병명 · 의약품 · 체험기에도 「도움」을 붙였다(「관절통에 도움을 줄 수 있음」). 실제 광고 31개 중
관문(`stage_gate.py`)을 넘은 건 6개뿐이었다.

v5 가 바꾸는 것:
  ① 출력에 **합법화 불가**를 더한다 — `{"infeasible": "<위반 유형>"}`. 살릴 기능성 주장이 없는 문구
     (질병 치료 · 예방, 의약품 표방, 체험기, 실증 불가 신체 변화)는 고치지 않고 손을 든다 (D-32 · D-125).
  ② 사실만 남기는 교정 · 병기 문구(`mandatory_note`) 예시를 넣는다 (`stage1_v5_extra.jsonl` · Claude 초안 · 법률 미검토).
  ③ 주입 데이터(T1~T7b)를 규칙별 45개로 줄인다 — 틀 암기를 줄인다.

🚨 누수 방지 (팀장 조건 2026-10-01):
  - 입력이나 정답이 판정 인코더 **평가용(test_sentence)** 문장과 같은 행은 학습 · 평가 모두에서 뺀다.
  - 새 데이터는 golden 과 겹침 0 (작성 후 확인).
  - 채점에 판정 인코더를 쓰지 않는다 — 형식 · 합법화 불가 정답률 · 관문(규칙) 통과율.

실행 (repo 루트, GPU venv):
    .venv-sllm/Scripts/python.exe docs/lse/train_stage1_v5.py              # v5 (v4 비교 포함)
    .venv-sllm/Scripts/python.exe docs/lse/train_stage1_v5.py --version v6 # v6

🆕 v6 (2026-10-01) — v5 가 실제 광고에서 **지나치게 거절**했다(살릴 수 있는 8개 중 0개 · 정답표 `_private/real_answer_key.jsonl`).
  · `stage1_v6_extra.jsonl` 50개 — 원료명 사실 표시 · 인증/순위만 빼기 · 대상 표시 · **건기식 오인이면 기능성 주장 불가** · 화장품 기능성 문구
  · 거절 사유를 위반 유형 목록(`app.contracts.Violation`)으로 제한 — v5 는 「질병」 · 「영양성분 표시」를 지어냈다
  · 실제 광고 채점을 정답표 기준으로 한다(정답표 문구는 평가 전용 — 비슷한 원료 · 표현을 학습 데이터에 쓰지 않았다)
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, get_cosine_schedule_with_warmup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from persona_experiment import load_inputs  # noqa: E402
from stage_gate import check as gate  # noqa: E402

from app.contracts import RewriteSet, Violation  # noqa: E402

BASE = "Qwen/Qwen2.5-3B-Instruct"
V4 = ROOT / "models" / "copylane_sllm_lora_adapter"
ADAPTERS = {v: ROOT / "models" / f"copylane_sllm_lora_adapter_{v}" for v in ("v5", "v6", "v7", "v8", "v9", "v10", "v11")}
EXTRAS = {"v5": ["stage1_v5_extra.jsonl"], "v6": ["stage1_v5_extra.jsonl", "stage1_v6_extra.jsonl"],
          "v7": ["stage1_v5_extra.jsonl", "stage1_v6_extra.jsonl"], "v8": ["stage1_v5_extra.jsonl", "stage1_v6_extra.jsonl"],
          "v9": ["stage1_v5_extra.jsonl", "stage1_v6_extra.jsonl"], "v10": ["stage1_v5_extra.jsonl", "stage1_v6_extra.jsonl"],
          "v11": ["stage1_v5_extra.jsonl", "stage1_v6_extra.jsonl"]}
#: 🆕 v7 — 합성 데이터(합성 활용 허용 10-01 · `gen_synthetic_stage1.py`). 🚨 **학습에만** 쓰고 평가에는 넣지 않는다
SYNTH = {"v7": ["synth_stage1.jsonl"], "v8": ["synth_stage1.jsonl"],  # v7 은 거르기 전 435행 · v8 은 원료명 불일치를 뺀 410행
         # 🆕 v9 (10-02) — 「사실 + 고칠 수 없는 위반」 짝 255행을 2배로. 질병 유형 학습행이 74:7 로 불가에 쏠려 있었다
         "v9": ["synth_stage1.jsonl", "synth_stage1_v9.jsonl", "synth_stage1_v9.jsonl"],
         # 🆕 v10 (10-02) — v9 와 같은 구성 · 정답이 원문에 없는 낱말(제품명 · 공정)을 지어낸 13행을 고치고 제품명 없이 끝나는 짝 8개를 더했다
         #    (v9 가 「…로스팅한 곶감」처럼 제품명을 지어냈다 · 결과서 12차)
         "v10": ["synth_stage1.jsonl", "synth_stage1_v9.jsonl", "synth_stage1_v9.jsonl"],
         # 🆕 v11 (10-02) — 같은 구성 · v9 데이터에 원료명 보존 짝 40개(띄어 쓴 · 조사처럼 보이는 앞말을 지키고 과장 수식어만 뗀다)를 더했다(304행)
         "v11": ["synth_stage1.jsonl", "synth_stage1_v9.jsonl", "synth_stage1_v9.jsonl"]}
KEY = HERE / "_private" / "real_answer_key.jsonl"
REASONS = [v.value for v in Violation]
SEED = 20261001
PER_RULE = 45
#: 🔄 10-01 — 512 였다. v6 첫 프롬프트가 길어 **모든 행의 정답이 잘려** loss 가 nan 이 됐다(v5 도 최장 544). 1024 는 VRAM 초과로 느려 640.
EPOCHS, LR, MAX_LEN = 3, 2e-4, 640

SYSTEM = (
    "당신은 광고 문구 준법 검수 보조 도구입니다. 위반 소지가 있는 광고 문구를 받아 다음 순서를 따릅니다.\n"
    "1) 문구에서 살릴 수 있는 핵심 주장(인정된 기능성 · 사실)을 찾는다.\n"
    "2) 살릴 주장이 있으면 위반 요소(질병 · 의약품 표현, 최상급 · 단정, 근거 없는 수치 · 비교, 후기)만 빼고 다시 쓴다.\n"
    "3) 살릴 주장이 없으면(질병 치료 · 예방, 의약품처럼 표방, 체험기, 실증할 수 없는 신체 변화가 주장의 전부) "
    "고치지 않고 합법화 불가로 답한다. 질병명이나 의약품 표현에 '도움을 줄 수 있음'을 붙여 고친 척하지 않는다.\n"
    "출력은 먼저 \"핵심 주장: ...\" 한 줄, 그다음 줄에 JSON 하나만 씁니다.\n"
    '고칠 수 있으면: {"body": "본문", "mandatory_note": "필수 병기 문구 또는 null", "placement": "배치 지시 또는 null"}\n'
    '고칠 수 없으면: {"infeasible": "위반 유형"}'
)
#: 🔄 10-01 — 첫 판(추가 256 토큰 · 위반 유형 11개 나열)은 너무 길어 VRAM 이 넘쳐 학습이 5배 느려졌다 → 줄였다
SYSTEM_V6 = SYSTEM + (
    "\n추가: 위반 유형에 건강기능식품_오인이 있으면 기능성 주장으로 고치지 말고 남는 사실만 쓰며, 없으면 불가. "
    "원료명·원산지 같은 사실은 과장만 빼고 살린다. 불가 사유는 위반 유형 이름 그대로 쓴다."
)


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s or "")


def load_rows(version: str = "v5") -> tuple[list[dict], list[dict]]:
    golden = [json.loads(line) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    test_set = {norm(r["text"]) for r in golden if r["split"] == "test_sentence"}

    def leaks(r: dict) -> bool:
        return norm(r["input"]) in test_set or norm((r["output"] or {}).get("body", "")) in test_set

    core = {}
    for line in (ROOT / "data/derived/injected_golden.jsonl").open(encoding="utf-8"):
        d = json.loads(line)
        if d.get("핵심주장"):
            core[d["문구"]] = d["핵심주장"]

    base = [json.loads(line) for line in (HERE / "train_pairs.jsonl").open(encoding="utf-8") if line.strip()]
    priv_path = HERE / "_private" / "ftc_pairs.jsonl"
    priv = [json.loads(line) for line in priv_path.open(encoding="utf-8")] if priv_path.exists() else []
    extra = [json.loads(line) for name in EXTRAS[version] for line in (HERE / name).open(encoding="utf-8")]

    dropped = sum(leaks(r) for r in base + priv)
    base = [r for r in base if not leaks(r)]
    priv = [r for r in priv if not leaks(r)]
    print(f"인코더 평가용 문장과 겹쳐 뺀 행 {dropped}", flush=True)

    rng = random.Random(SEED)
    train, ev = [], []
    by_rule: dict[str, list[dict]] = collections.defaultdict(list)
    for r in base:
        (ev if r["split"] == "held_out" else by_rule[r["rule_id"]]).append(r)
    for rows in by_rule.values():
        rng.shuffle(rows)
        train += rows[:PER_RULE]
    for r in base + priv:
        r["core"] = r.get("core_claim") or core.get(r["input"]) or r["output"]["body"]
        r["kind"] = "기존"
    train += [r for r in priv if r["split"] == "train"] * 2  # 실사례 비중 — v4 와 같은 뜻의 오버샘플
    ev += [r for r in priv if r["split"] == "held_out"]
    for x in extra:
        x["core"] = x["output"].get("body") or "없음 — 살릴 주장이 없다"
        x["kind"] = x["group"]
        # 그룹마다 4개 중 1개를 평가로 — 같은 그룹의 다른 문구로 학습하고, 본 적 없는 문구로 잰다
        (ev if int(x["id"][1:]) % 4 == 0 else train).append(x)
    train += [x for x in extra if int(x["id"][1:]) % 4 != 0]  # x · y 접두 모두 번호로 4개 중 1개를 평가로
    synth = [json.loads(line) for name in SYNTH.get(version, []) for line in (HERE / name).open(encoding="utf-8")]
    for x in synth:
        assert x.get("synthetic"), "합성 파일에 합성 표시가 없는 행이 있다"
        x["core"] = x["output"].get("body") or "없음 — 살릴 주장이 없다"
        x["kind"] = "합성:" + x["group"].split(":")[0]
    train += synth  # 🚨 평가(ev)에는 넣지 않는다
    if synth:
        print(f"합성 {len(synth)}행 — 학습에만", flush=True)  # 새 유형 2배 — 784개 틀에 묻히지 않게
    rng.shuffle(train)
    print(f"학습 {len(train)} · 평가 {len(ev)} · 학습 중 합법화 불가 {sum('infeasible' in r['output'] for r in train)}", flush=True)
    return train, ev


SYS = {"v5": SYSTEM, "v6": SYSTEM_V6, "v7": SYSTEM_V6, "v8": SYSTEM_V6, "v9": SYSTEM_V6, "v10": SYSTEM_V6, "v11": SYSTEM_V6}
CUR = {"system": SYSTEM}


def user_msg(r: dict) -> str:
    types = ", ".join(r.get("violation_types") or []) or "(미상)"
    return f"위반 문구: {r['input']}\n위반 유형: {types}\n근거: {r.get('legal_basis') or '(미상)'}"


def target_text(r: dict) -> str:
    return f"핵심 주장: {r['core']}\n{json.dumps(r['output'], ensure_ascii=False)}"


def parse(raw: str) -> dict | None:
    i, j = raw.find("{"), raw.rfind("}")
    try:
        d = json.loads(raw[i:j + 1])
    except Exception:  # noqa: BLE001
        return None
    if "infeasible" in d:
        # 목록 밖 사유(「질병」 · 「영양성분 표시」)는 사유 오류로 표시한다 — 거절 자체는 거절로 센다
        return {"infeasible": d["infeasible"], "reason_ok": str(d["infeasible"]).strip() in REASONS}
    try:
        return RewriteSet.model_validate(d).model_dump()
    except Exception:  # noqa: BLE001
        return None


def generate(model, tok, r: dict) -> dict | None:
    msgs = [{"role": "system", "content": CUR["system"]}, {"role": "user", "content": user_msg(r)}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=220, do_sample=False)
    return parse(tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True))


def train(model, tok, rows: list[dict]) -> None:
    data = []
    for r in rows:
        msgs = [{"role": "system", "content": CUR["system"]}, {"role": "user", "content": user_msg(r)}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        ids = tok(prompt + target_text(r) + tok.eos_token, add_special_tokens=False, truncation=True,
                  max_length=MAX_LEN)["input_ids"]
        if len(ids) <= len(p_ids):
            continue  # 정답 토큰이 하나도 안 남은 행 — 넣으면 loss 가 nan 이 된다
        data.append((ids, [-100] * len(p_ids) + ids[len(p_ids):]))
    print(f"정답이 잘려 뺀 행 {len(rows) - len(data)} / {len(rows)}", flush=True)
    assert data, "학습할 행이 없다 — MAX_LEN 을 확인한다"
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR)
    steps = EPOCHS * len(data)
    sched = get_cosine_schedule_with_warmup(opt, int(0.05 * steps), steps)
    model.train()
    rng = random.Random(SEED)
    for ep in range(EPOCHS):
        rng.shuffle(data)
        tot = 0.0
        nan_steps = 0
        for ids, labels in data:
            out = model(input_ids=torch.tensor([ids], device=model.device),
                        labels=torch.tensor([labels], device=model.device))
            if not torch.isfinite(out.loss):
                nan_steps += 1
                assert nan_steps < 10, "loss 가 계속 nan — 학습을 멈춘다"
                opt.zero_grad()
                continue
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            tot += out.loss.item()
        print(f"epoch {ep + 1}/{EPOCHS} loss {tot / len(data):.4f}", flush=True)
    model.eval()


def evaluate(model, tok, ev: list[dict], real: list[dict], name: str) -> list[dict]:
    res = []
    for r in ev:
        out = generate(model, tok, r)
        want_inf = "infeasible" in r["output"]
        got_inf = bool(out and "infeasible" in out)
        g = gate(r["input"], out.get("body")) if out and not got_inf else None
        res.append({"set": "eval", "model": name, "kind": r["kind"], "input": r["input"], "want": r["output"],
                    "got": out, "inf_ok": want_inf == got_inf, "gate": list(g.reasons) if g else None})
    key = {k["input"]: k for k in map(json.loads, KEY.open(encoding="utf-8"))} if KEY.exists() else {}
    seen: set[str] = set()
    for r in real:
        if r["input"] in seen:
            continue
        seen.add(r["input"])
        out = generate(model, tok, {"input": r["input"], "violation_types": r["labels"]})
        got_inf = bool(out and "infeasible" in out)
        g = gate(r["input"], out.get("body")) if out and not got_inf else None
        outcome = "형식실패" if out is None else ("합법화불가" if got_inf else ("후보" if g.passed else "관문보류"))
        k = key.get(r["input"])
        verdict = None
        if k:
            can = k["label"] != "불가"
            verdict = {("합법화불가", False): "✅ 불가를 불가로", ("후보", True): "✅ 살릴 것을 살림",
                       ("후보", False): "🔴 위반 포장", ("합법화불가", True): "🟠 지나친 거절"}.get(
                (outcome, can), "🟡 관문 보류" if outcome == "관문보류" else "형식실패")
        res.append({"set": "real", "model": name, "input": r["input"], "got": out, "outcome": outcome,
                    "verdict": verdict, "gate": list(g.reasons) if g else None})
    e = [x for x in res if x["set"] == "eval"]
    by = collections.defaultdict(list)
    for x in e:
        by[x["kind"]].append(x["inf_ok"])
    rw = [x for x in e if x["got"] and "infeasible" not in x["got"] and "body" in x["want"]]
    real_c = collections.Counter(x["outcome"] for x in res if x["set"] == "real")
    print(f"[{name}] 평가 {len(e)} · 고칠/못고칠 판단 정답 {sum(x['inf_ok'] for x in e)}/{len(e)} "
          f"({', '.join(f'{k} {sum(v)}/{len(v)}' for k, v in sorted(by.items()))}) · "
          f"고친 문장 관문 통과 {sum(not x['gate'] for x in rw)}/{len(rw)}", flush=True)
    print(f"[{name}] 실제 광고 {sum(real_c.values())}개 → {dict(real_c)}", flush=True)
    vc = collections.Counter(x["verdict"] for x in res if x["set"] == "real" and x["verdict"])
    bad_reason = sum(1 for x in res if x["got"] and "infeasible" in x["got"] and not x["got"].get("reason_ok", True))
    print(f"[{name}] 정답표 기준 → {dict(sorted(vc.items()))} · 목록 밖 거절 사유 {bad_reason}", flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", choices=["v5", "v6", "v7", "v8", "v9", "v10", "v11"], default="v5")
    args = ap.parse_args()
    CUR["system"] = SYS[args.version]
    out_path = HERE / "_private" / f"stage1_{args.version}_eval.jsonl"
    torch.manual_seed(SEED)
    train_rows, ev = load_rows(args.version)
    real = load_inputs()
    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    t0 = time.time()
    res: list[dict] = []
    if args.version == "v5":
        # v4 를 먼저 같은 평가로 잰다 — 비교 기준
        m4 = PeftModel.from_pretrained(base, str(V4))
        m4.eval()
        res = evaluate(m4, tok, ev, real, "v4")
        base = m4.unload()

    base.gradient_checkpointing_enable()
    base.enable_input_require_grads()
    model = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, task_type="CAUSAL_LM",
                                            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]))
    train(model, tok, train_rows)
    model.save_pretrained(ADAPTERS[args.version])
    print(f"{args.version} 어댑터 저장 {ADAPTERS[args.version]} · {time.time() - t0:.0f}s", flush=True)
    model.config.use_cache = True
    res += evaluate(model, tok, ev, real, args.version)

    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for x in res:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"결과: {out_path} · {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
