"""1단계(위반 제거) 합성 데이터 — GPT 로 위반 문구를 만든다 (2026-10-01 · 합성 데이터 활용 허용).

v6 의 약점은 「살리기」다(실제 광고 정답표 기준 살릴 수 있는 8개 중 사실상 0). 원인은 데이터 양 · 다양성이다.

★ **정답을 먼저 정하고, GPT 는 위반 문구만 만든다** — GPT 가 고친 문장을 정답으로 쓰면 그 정답을 또 검증해야 한다.
   - 정답(적법 문구)은 공개 원천에서 **규칙으로** 정한다: 고시 기능성 문구(`hf_display_claims` · 재배포 가능) ·
     원료명 · 기능성화장품 문구(화장품법 시행규칙 [별표 3] 의 기능 범주) · 일반 제품 유형.
   - GPT 는 그 정답을 「과장 · 위반으로 망가뜨린」 광고 문구를 여러 형태로 쓴다. 고칠 수 없는 유형(질병 · 의약품 ·
     체험기 · 신체 변화 · 건기식 오인)은 문구만 만들고 정답 「합법화 불가」는 우리가 붙인다.

🚨 누수 · 재배포 (팀장 조건 · 2026-10-01):
   - golden(인코더 데이터)과 겹치는 정답 · 문구는 버린다(정확히 같거나 부분 포함).
   - 실제 광고 정답표(`_private/real_answer_key.jsonl` · 평가 전용)의 원료 · 표현이 들어간 문구는 버린다.
   - 재배포 불가 원천(공정위 · 사례집 · 해설서) 문구를 씨앗으로 쓰지 않는다 · GPT 에게도 실제 광고 인용을 금한다.
   - 모든 행에 `synthetic: true` · 생성 모델 · 프롬프트 판을 남긴다. 합성 행은 **평가에 쓰지 않는다**.

실행 (repo 루트, GPU venv — openai 는 이 venv 에만 설치):
    .venv-sllm/Scripts/python.exe docs/lse/gen_synthetic_stage1.py --dry-run          # 씨앗 · 프롬프트만 본다(API 안 씀)
    .venv-sllm/Scripts/python.exe docs/lse/gen_synthetic_stage1.py --pilot 50         # 시범
    .venv-sllm/Scripts/python.exe docs/lse/gen_synthetic_stage1.py --target 2000      # 본 생성
🔄 10-01 — API 결제 전이라 **직접 작성 경로**를 쓴다(GPT 대신 Claude 가 이 대화에서 위반 문구를 쓴다):
    ... --export-seeds 150      # 종류별로 고르게 씨앗을 골라 synth_seeds.jsonl 로
    ... --ingest synth_written.jsonl   # 직접 쓴 문구 {"seed": id, "inputs": [...]} 에 같은 거르기를 걸어 synth_stage1.jsonl 로
API 키는 `.env` 의 OPENAI_API_KEY(화면 · 로그에 찍지 않는다) · 모델은 OPENAI_MODEL(기본 gpt-4o-mini).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from build_persona_inputs import clean, split_claims  # noqa: E402
from stage_gate import check as gate  # noqa: E402
from stage_gate import ingredient_changed  # noqa: E402

OUT = HERE / "synth_stage1.jsonl"
PROMPT_VERSION = "synth-v1-2026-10-01"
SEED = 20261001
PER_SEED = 6  # 씨앗 하나당 위반 문구 수
#: 정답표(평가 전용)의 고유 원료 · 표현 — 🔄 첫 판은 정답표 낱말 전부를 썼다가 「건강기능식품」 · 「기능성」 같은 일반어까지 막아
#:    건기식 씨앗 179개가 전부 빠졌다. 고유한 것만 적는다
ANSWER_WORDS_PATH = HERE / "_private" / "answer_words.json"
#:    🚨 목록 자체가 실제 광고(재배포 불가) 표현이라 공개 파일에 적지 않는다 — `_private/` 에서 읽는다
#: 생성 문구가 정답표 문구와 이만큼 비슷하면 버린다(평가 누수)
SIM_MAX = 0.6

FORMS = ["짧은 키워드형(10자 안팎)", "한 문장 광고 카피", "SNS 게시글 말투", "상세페이지 소제목 + 한 줄 설명", "라이브커머스 멘트 말투"]

#: 화장품법 시행규칙 [별표 3] 기능성화장품 범주의 표시 문구 — 🚨 해당 기능성화장품으로 심사 · 보고된 제품에만 쓸 수 있다
COSMETIC = [
    ("미백", "피부의 미백에 도움을 줍니다"),
    ("주름", "피부의 주름 개선에 도움을 줍니다"),
    ("자외선", "자외선으로부터 피부를 보호하는 데 도움을 줍니다"),
    ("탈모", "탈모 증상의 완화에 도움을 줍니다"),
    ("여드름", "여드름성 피부를 완화하는 데 도움을 줍니다"),
    ("피부장벽", "피부장벽의 기능을 회복하여 가려움 등의 개선에 도움을 줍니다"),
    ("튼살", "튼살로 인한 붉은 선을 엷게 하는 데 도움을 줍니다"),
]
COSMETIC_PRODUCTS = ["크림", "세럼", "앰플", "토너", "로션", "선크림", "샴푸", "패드", "에센스", "마스크팩"]
#: 일반식품 유형 — 사실 표시 · 인증 · 순위 씨앗 (특정 브랜드 없음)
FOODS = ["김치", "육포", "들기름", "참기름", "된장", "고추장", "꿀", "누룽지", "곰탕", "그래놀라", "두유", "식초", "녹차",
         "현미밥", "떡볶이", "견과바", "과일칩", "쌀과자", "어묵", "만두", "청국장", "미역", "김", "잡곡", "사과즙", "배즙"]
INFEASIBLE = {
    "질병_예방치료_표방": "질병명(예: 당뇨 · 고혈압 · 관절염 · 위염 · 아토피 등)을 치료 · 예방 · 완화한다고 주장",
    "의약품_오인": "의약품처럼 표방(약 · 처방 · ○○제 대신 · 주사 맞은 듯 · 의사 추천 등)",
    "후기_체험기_기만": "구매자 · 가족의 사용 후기 · 체험담으로 효과를 주장",
    "거짓_과장": "실증할 수 없는 신체 변화(키 성장 · 시력 회복 · 세포 나이 되돌림 · 영구 효과 등)를 주장",
    "건강기능식품_오인": "건강기능식품이 아닌 일반식품이 기능성을 인정받은 것처럼 표방",
}

SYSTEM = (
    "당신은 광고 준법 검수 모델의 학습 데이터를 만드는 도우미입니다. 실제로 존재하는 광고를 인용하거나 흉내 내지 말고, "
    "실존 브랜드 · 회사 · 인물 이름을 쓰지 말고, 새로 지어낸 가상의 광고 문구만 씁니다. 출력은 JSON 하나만 씁니다."
)


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s or "")


def rewrite_prompt(target: str, kind: str, k: int) -> str:
    return (
        f"아래 '적법한 문구'를 쓸 수 있는 제품의 광고주가, 욕심을 내어 위반 요소를 덧붙인 **위반 광고 문구** {k}개를 만드세요.\n"
        f"적법한 문구: {target}\n"
        f"덧붙일 위반 요소 예: 최상급 · 1위 · 유일 · 100% · 근거 없는 수치 · 기간 보장 · 인증/수상/특허 과장 · 타사 비교 · '기적' 같은 과장.\n"
        f"조건: 각 문구는 위반 요소만 빼면 위 적법한 문구의 뜻으로 돌아갈 수 있어야 합니다. 질병 치료 · 의약품 표현은 넣지 마세요. "
        f"형식을 서로 다르게: {', '.join(random.sample(FORMS, min(k, len(FORMS))))}.\n"
        f'출력: {{"items": [{{"input": "위반 문구", "violation_types": ["거짓_과장" 등 다음 중에서: 거짓_과장, 소비자_기만, 부당_비교광고]}}]}}'
        f"\n(유형: {kind})"
    )


def infeasible_prompt(product: str, vtype: str, k: int) -> str:
    return (
        f"'{product}' 제품에 대해 다음 위반을 저지른 가상의 광고 문구 {k}개를 만드세요.\n"
        f"위반: {INFEASIBLE[vtype]}\n"
        f"이 위반이 주장의 전부여서 위반을 빼면 살릴 주장이 남지 않는 문구여야 합니다. "
        f"형식을 서로 다르게: {', '.join(random.sample(FORMS, min(k, len(FORMS))))}.\n"
        f'출력: {{"items": [{{"input": "위반 문구"}}]}}'
    )


def build_seeds(rng: random.Random, answer_words: list[str], golden_set: set[str], golden_blob: str) -> list[dict]:
    seeds = []
    hf = [json.loads(line) for line in (ROOT / "data/derived/hf_display_claims.jsonl").open(encoding="utf-8")]
    seen = set()
    for r in hf:
        if r.get("redistributable") is False:
            continue
        ing = clean(r.get("APLC_RAWMTRL_NM") or "")
        for raw in split_claims(r.get("정본_문구") or r.get("FNCLTY_CN")):
            c = clean(raw)
            k = norm(c)
            # 정답이 golden(인코더 데이터)과 같거나 부분이면 버린다 — 정답이 인코더가 외운 문장이 되면 누수다
            if len(c) < 10 or k in golden_set or k in golden_blob or k in seen or c.endswith("있으나"):
                continue
            seen.add(k)
            seeds.append({"kind": "건기식기능", "target": {"body": c, "mandatory_note": "기능성 인정 건강기능식품에 한해 표시",
                                                        "placement": None}})
            if ing and 2 <= len(ing) <= 20 and norm(ing) not in seen:
                seen.add(norm(ing))
                seeds.append({"kind": "원료사실", "target": {"body": f"{ing} 함유", "mandatory_note": "원재료 함량을 함께 표시",
                                                         "placement": "원료명 표시 근처"}})
    for name, claim in COSMETIC:
        for p in COSMETIC_PRODUCTS:
            seeds.append({"kind": "화장품기능", "target": {"body": claim, "mandatory_note": f"{name} 기능성화장품으로 심사·보고된 {p}에 한함",
                                                       "placement": None}, "product": p})
    for f in FOODS:
        seeds.append({"kind": "사실·인증순위", "target": {"body": f"{f} 제품", "mandatory_note": "순위 · 인증 · 수상은 근거(기관 · 기간 · 번호)와 함께만",
                                                       "placement": "해당 표시 바로 아래"}, "product": f})
        for vtype in INFEASIBLE:
            seeds.append({"kind": f"불가:{vtype}", "target": {"infeasible": vtype}, "product": f})
    # 정답표(평가 전용) 원료 · 표현이 든 씨앗은 처음부터 뺀다 — 정답 본문 · 제품명만 본다(병기 문구의 일반어는 보지 않는다)
    seeds = [s for s in seeds
             if not any(w in (s["target"].get("body") or "") + s.get("product", "") for w in answer_words)]
    rng.shuffle(seeds)
    return seeds


def call(client, model: str, prompt: str) -> list[dict]:
    resp = client.chat.completions.create(
        model=model, temperature=0.9, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content).get("items", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pilot", type=int, default=0, help="이 수만큼만 만든다(시범)")
    ap.add_argument("--target", type=int, default=2000)
    ap.add_argument("--export-seeds", type=int, default=0, help="고른 씨앗 수 — synth_seeds.jsonl 로 내보낸다")
    ap.add_argument("--ingest", type=Path, default=None, help="직접 쓴 문구 파일(docs/lse 기준)")
    ap.add_argument("--ingest-pairs", type=Path, default=None,
                    help="🆕 v9 — 문구와 정답을 짝으로 직접 쓴 파일(docs/lse 기준) → synth_stage1_v9.jsonl")
    args = ap.parse_args()
    rng = random.Random(SEED)
    random.seed(SEED)

    golden = [norm(json.loads(line)["text"]) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    gset, gblob = set(golden), "\n".join(golden)
    key_path = HERE / "_private" / "real_answer_key.jsonl"
    answer_words = json.loads(ANSWER_WORDS_PATH.read_text(encoding="utf-8")) if ANSWER_WORDS_PATH.exists() else []
    if not answer_words:
        print("⚠️ 정답표 금지어 파일이 없다 — 평가 누수 거르기가 약해진다", flush=True)
    answer_inputs = [norm(k["input"]) for k in map(json.loads, key_path.open(encoding="utf-8"))] if key_path.exists() else []
    seeds = build_seeds(rng, answer_words, gset, gblob)
    by_kind: dict[str, int] = {}
    for s in seeds:
        by_kind[s["kind"].split(":")[0]] = by_kind.get(s["kind"].split(":")[0], 0) + 1
    print(f"씨앗 {len(seeds)} · {by_kind} · 정답표 금지어 {len(answer_words)}개", flush=True)

    if args.export_seeds:
        # 종류별로 고르게 — 살리기 유형을 많이, 합법화 불가는 적게(손으로 쓴 100개가 이미 있다)
        quota = {"건기식기능": 0.27, "원료사실": 0.23, "화장품기능": 0.14, "사실·인증순위": 0.17, "불가": 0.19}
        picked: list[dict] = []
        for kind, q in quota.items():
            pool = [x for x in seeds if x["kind"].split(":")[0] == kind]
            picked += pool[: max(1, round(args.export_seeds * q))]
        with (HERE / "synth_seeds.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for i, x in enumerate(picked):
                f.write(json.dumps({"seed": f"g{i:03d}", **x}, ensure_ascii=False) + "\n")
        print(f"씨앗 {len(picked)}개 → synth_seeds.jsonl")
        return
    if args.ingest_pairs:
        # 🆕 10-02 (v9) — 「살릴 수 있는데 버린다」를 줄이려고 **사실 + 고칠 수 없는 위반**이 섞인 문구를 짝으로 쓴다.
        #    v8 까지의 합성은 질병 · 의약품 · 체험기를 「위반이 주장의 전부」로만 만들어 정답이 늘 불가였다(질병 81행 중 74행 불가).
        #    한 줄 = {"kind", "vt": [위반 유형], "note": 병기 문구|null, "pairs": [[문구, 정답 본문|null(=합법화 불가)]]}.
        #    정답이 문구마다 달라 사실(원산지 · 원료 · 제조 · 용량)이 문구 그대로 살아남는다. 거르기는 --ingest 와 같다.
        out = HERE / "synth_stage1_v9.jsonl"
        rows, seen_inputs = [], set()
        dropped = {"golden": 0, "정답표": 0, "중복": 0, "형식": 0, "원료명 불일치": 0, "정답 관문": 0}
        for line in (HERE / args.ingest_pairs).open(encoding="utf-8"):
            if not line.strip():
                continue
            g = json.loads(line)
            for text, body in g["pairs"]:
                text = text.strip()
                k = norm(text)
                target = ({"infeasible": g["vt"][0]} if body is None
                          else {"body": body, "mandatory_note": g.get("note"), "placement": None})
                if not text or len(text) > 120:
                    dropped["형식"] += 1
                elif k in gset or k in gblob:
                    dropped["golden"] += 1
                elif any(x in text.replace(" ", "") for x in answer_words) or any(
                        difflib.SequenceMatcher(None, k, a).ratio() >= SIM_MAX for a in answer_inputs):
                    dropped["정답표"] += 1
                elif k in seen_inputs:
                    dropped["중복"] += 1
                elif body and ingredient_changed(text, body):
                    dropped["원료명 불일치"] += 1
                elif body and not gate(text, body).passed and g["kind"] != "고시+질병":
                    dropped["정답 관문"] += 1  # 정답이 관문에 걸리면 정답이 틀린 것이다(고시 문구는 팀 사전 오탐 예외)
                else:
                    seen_inputs.add(k)
                    rows.append({"id": f"w{len(rows):05d}", "group": g["kind"], "input": text, "violation_types": g["vt"],
                                 "output": target, "synthetic": True, "generator": "claude-in-session",
                                 "prompt_version": "synth-v2-pairs-2026-10-02"})
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        n_inf = sum("infeasible" in r["output"] for r in rows)
        print(f"받아들임 {len(rows)} (살림 {len(rows) - n_inf} · 불가 {n_inf}) · 버림 {dropped} · {out.name}")
        return
    if args.ingest:
        seeds_by_id = {x["seed"]: x for x in map(json.loads, (HERE / "synth_seeds.jsonl").open(encoding="utf-8"))}
        written = [json.loads(line) for line in (HERE / args.ingest).open(encoding="utf-8") if line.strip()]
        rows, seen_inputs = [], set()
        dropped = {"golden": 0, "정답표": 0, "중복": 0, "형식": 0, "원료명 불일치": 0}
        answer_inputs_ = answer_inputs
        for w in written:
            sd = seeds_by_id[w["seed"]]
            for text in w["inputs"]:
                text = text.strip()
                k = norm(text)
                if not text or len(text) > 120:
                    dropped["형식"] += 1
                elif k in gset or k in gblob:
                    dropped["golden"] += 1
                elif any(x in text.replace(" ", "") for x in answer_words) or any(
                        difflib.SequenceMatcher(None, k, a).ratio() >= SIM_MAX for a in answer_inputs_):
                    dropped["정답표"] += 1
                elif k in seen_inputs:
                    dropped["중복"] += 1
                elif "body" in sd["target"] and ingredient_changed(text, sd["target"]["body"]):
                    # 🆕 10-01 — 정답의 원료명이 문구와 다르면(「히알루론산」 → 정답 「히알우론산 HA-LF-P」) 버린다.
                    #    「원료명을 바꿔 써도 된다」고 가르치게 된다 — v7 이 실제 광고의 원료명에 오타를 낸 원인 후보
                    dropped["원료명 불일치"] += 1
                else:
                    seen_inputs.add(k)
                    vt = [sd["target"]["infeasible"]] if "infeasible" in sd["target"] else (w.get("violation_types") or ["거짓_과장"])
                    rows.append({"id": f"s{len(rows):05d}", "group": sd["kind"], "input": text, "violation_types": vt,
                                 "output": sd["target"], "synthetic": True, "generator": "claude-in-session",
                                 "prompt_version": PROMPT_VERSION})
        with OUT.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"받아들임 {len(rows)} · 버림 {dropped} · {OUT.name}")
        return

    goal = args.pilot or args.target
    if args.dry_run:
        for s in seeds[:3]:
            p = infeasible_prompt(s["product"], s["target"]["infeasible"], PER_SEED) if "infeasible" in s["target"] \
                else rewrite_prompt(s["target"]["body"], s["kind"], PER_SEED)
            print(f"\n--- {s['kind']} ---\n{p}")
        return

    from openai import OpenAI  # noqa: PLC0415
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k_, v_ = line.split("=", 1)
            env[k_.strip()] = v_.strip().strip('"').strip("'")
    key = os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    assert key, ".env 에 OPENAI_API_KEY 가 없다"  # 🚨 키 값은 찍지 않는다
    model = os.environ.get("OPENAI_MODEL") or env.get("OPENAI_MODEL") or "gpt-4o-mini"
    client = OpenAI(api_key=key)

    out_path = OUT.with_name("synth_stage1_pilot.jsonl") if args.pilot else OUT
    rows, seen_inputs, dropped = [], set(), {"golden": 0, "정답표": 0, "중복": 0, "형식": 0, "정답 관문": 0}
    t0 = time.time()
    # 씨앗이 모자라면 한 바퀴 더 돈다 — 형식 조합이 매번 달라 같은 씨앗에서도 다른 문구가 나온다
    for s in seeds * 3:
        if len(rows) >= goal:
            break
        if "body" in s["target"] and not gate("x", s["target"]["body"]).passed and s["kind"] != "건기식기능":
            dropped["정답 관문"] += 1  # 정답 자체가 관문에 걸리면 씨앗을 버린다(건기식 기능성은 팀 사전 오탐이 있어 예외)
            continue
        prompt = infeasible_prompt(s["product"], s["target"]["infeasible"], PER_SEED) if "infeasible" in s["target"] \
            else rewrite_prompt(s["target"]["body"], s["kind"], PER_SEED)
        try:
            items = call(client, model, prompt)
        except Exception as e:  # noqa: BLE001 — 한 씨앗 실패로 전체를 멈추지 않는다
            print(f"  API 오류 · {type(e).__name__}", flush=True)
            dropped["형식"] += 1
            continue
        for it in items:
            text = str(it.get("input") or "").strip()
            k = norm(text)
            if not text or len(text) > 120:
                dropped["형식"] += 1
            elif k in gset or k in gblob:
                dropped["golden"] += 1
            elif any(w in text.replace(" ", "") for w in answer_words) or any(
                    difflib.SequenceMatcher(None, k, a).ratio() >= SIM_MAX for a in answer_inputs):
                dropped["정답표"] += 1
            elif k in seen_inputs:
                dropped["중복"] += 1
            else:
                seen_inputs.add(k)
                vt = s["target"]["infeasible"] if "infeasible" in s["target"] else [
                    v for v in (it.get("violation_types") or ["거짓_과장"]) if v in ("거짓_과장", "소비자_기만", "부당_비교광고")
                ] or ["거짓_과장"]
                rows.append({"id": f"s{len(rows):05d}", "group": s["kind"], "input": text,
                             "violation_types": vt if isinstance(vt, list) else [vt], "output": s["target"],
                             "synthetic": True, "generator": model, "prompt_version": PROMPT_VERSION})
        if len(rows) % 100 < PER_SEED:
            print(f"{len(rows)}/{goal}  {time.time() - t0:.0f}s", flush=True)

    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n생성 {len(rows)} · 버림 {dropped} · {out_path.name} · {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
