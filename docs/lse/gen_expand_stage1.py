"""1단계(위반 제거) 데이터 늘리기 — 실제 위반 문장을 씨앗으로 (2026-10-16 · 10-15 회의 멘토 지적 「재생성 데이터가 너무 적다」).

q4b-v14 의 학습은 약 2천 행이다. 목표는 약 8천 행 — 묶음 넷:
   A. 실제 위반 문장(golden · 식품 · 건기식 · 화장품) → 교사 모델이 고쳐 쓴다 → 거른다
   B. 실제 위반 문장 하나당 변형 1개(같은 위반 방식 · 다른 제품 · 원료) → 고쳐 쓴다 → 거른다
   C. 식약처 가이드의 수정쌍(사람이 쓴 정답)
   D. 기존 q4b-v14 데이터
★ 9월(규칙으로 찍어낸 784쌍)과 다른 점 — 씨앗이 규칙 몇 개가 아니라 **실제 광고 문장 하나하나**다(문장 모양이 다양하다).

🚨 학습 편향 막이 (팀 10-16 「위반만 아니게 통과하도록 배우는 편향」) — 「통과한 것만 남기면」 다 지운 답이 가장 잘 통과한다.
   1. 사실 보존 — 교사가 원문에서 옮긴 사실 낱말이 고친 문장에 **모두** 남아야 한다 · 원문의 사실 숫자(`fact_numbers`)도 남아야 한다
   2. 지나친 거절 — 사실이 있는데 「불가」면 버린다(v9 정책: 사실은 살린다). 교사의 facts 목록만 믿지 않고 원문의 사실 신호
      (`FACT_SIGNAL`)도 본다 — 시범 v1 은 불가 127 · 고침 11 이었고 표본 30 중 5~6 이 살릴 사실이 있었다
   3. 유형 쏠림 · 같은 끝 표현 — 보고서에 유형별 통과율 · 끝 표현 빈도를 낸다(본 생성에서 상한을 건다)
   4. 순환 평가 금지 — 거르기에 쓴 재판정 통과율로 모델을 재지 않는다 · 평가는 사람 정답표(`_private/real_answer_key.jsonl`)
   보고서는 1 · 2 를 **뺐을 때** 몇 개가 더 통과했을지도 센다 — 그만큼이 편향의 크기다.

💸 API 예산 (사용자 10-16) — **누적 $10 까지**. 쓴 토큰은 `_private/expand_spend.json` 에 쌓고, 실행 전에 견적을 내며,
   누적이 상한에 닿으면 그 자리에서 멈춘다. 가격은 보수적으로 잡는다(`PRICE` · 실제보다 크게). 문장을 10 개씩 묶어 부른다.

🚨 재배포 불가 — golden 실제 문장은 광고주 문구다. 씨앗 · 생성물 · 결과는 `_private/` 에만 쓴다. 화면에는 개수만 낸다.
   외부 API(교사)에 보내는 것은 팀 확인(10-16)을 받았다. 정답표(평가 전용) 문장과 닮은 씨앗 · 생성물은 버린다(누수).

실행 (repo 루트 · `.venv` — 재판정에 로컬 DB 필요):
    .venv/Scripts/python.exe docs/lse/gen_expand_stage1.py seeds            # A 씨앗 → _private/expand_seeds.jsonl
    .venv/Scripts/python.exe docs/lse/gen_expand_stage1.py mfds             # C → _private/expand_mfds_rows.jsonl
    .venv/Scripts/python.exe docs/lse/gen_expand_stage1.py run A --n 200 --dry-run   # 견적만
    .venv/Scripts/python.exe docs/lse/gen_expand_stage1.py run A --n 200    # 시범 · _private/expand_A_raw.jsonl · _rows.jsonl
    .venv/Scripts/python.exe docs/lse/gen_expand_stage1.py run B --n 200
    .venv/Scripts/python.exe docs/lse/gen_expand_stage1.py report A B
교사 모델은 gpt-4o-mini 고정(`--model` 로만 바꾼다) · 키는 `.env` 의 OPENAI_API_KEY(화면 · 로그에 찍지 않는다).
"""

from __future__ import annotations

import argparse
import collections
import difflib
import json
import random
import re
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from gen_synthetic_stage1 import COSMETIC_PRODUCTS, FOODS, SIM_MAX, norm  # noqa: E402
from stage_gate import check as gate  # noqa: E402
from stage_gate import fact_numbers  # noqa: E402

PRIV = HERE / "_private"
SEEDS = PRIV / "expand_seeds.jsonl"
SPEND = PRIV / "expand_spend.json"
PROMPT_VERSION = "expand-v2-2026-10-16"
SEED = 20261016
DOMAIN = {"식품", "건기식", "화장품"}
MODEL = "gpt-4o-mini"
BUDGET_USD = 10.0
#: 100만 토큰당 달러(입력, 출력) — 🚨 보수적으로 실제 공시가보다 크게 잡는다. 모르는 모델은 비싼 쪽으로 본다
PRICE = {"gpt-4o-mini": (0.30, 1.20), "gpt-4.1": (3.0, 12.0)}
PRICE_UNKNOWN = (5.0, 20.0)
BATCH = 10  # 한 번 부를 때 묶는 문장 수
#: 「불가」의 유형 — 여러 유형이면 무거운 것부터(행정처분 수위 순)
SEVERITY = ["의약품_오인", "질병_예방치료_표방", "건강기능식품_오인", "기능성화장품_오인", "후기_체험기_기만",
            "소비자_기만", "부당_비교광고", "비방광고", "거짓_과장"]
#: 원문을 이만큼 닮은 변형(B)은 버린다 — 변형이 아니라 실제 광고를 베낀 것이다
COPY_MAX = 0.7
URL = "https://api.openai.com/v1/chat/completions"
#: 원문의 사실 신호 — 이것이 있는데 「불가」면 지나친 거절로 본다(편향 막이 2)
FACT_SIGNAL = re.compile(r"\d+(?:\.\d+)?\s*(?:%|g|mg|kg|ml|mL|l|L|kcal|년|일|시간|가지|종)|함유|추출물|분말|원료|원유|국내산|국산|"
                         r"[가-힣]{2,4}산(?=\s|$|[,.)의])|만들|제조|숙성|건조|발효|착즙|우려|배합|함량|압착|로스팅|볶은|구운")

SYSTEM = "당신은 한국 광고 준법 교정 도우미입니다. 출력은 JSON 하나만 씁니다."

#: 공개 학습 데이터(직접 만든 v6 · v9 · v14 행)와 직접 지은 예 — 실제 광고 문구가 아니다
FEWSHOT = [
    ("영양제 링거 맞은 듯 개운한 흑마늘즙, 의성 마늘을 21일 숙성", ["의약품_오인"],
     {"decision": "고침", "facts": ["의성 마늘", "21일 숙성", "흑마늘즙"], "body": "의성 마늘을 21일 숙성한 흑마늘즙"}),
    ("기적처럼 살이 빠지는 곤약 젤리, 당류 0g", ["거짓_과장"],
     {"decision": "고침", "facts": ["곤약 젤리", "당류 0g"], "body": "당류 0g 곤약 젤리"}),
    ("업계 1위! 방송에서 난리 난 그 떡, 국산 쌀을 저온 건조", ["거짓_과장", "소비자_기만"],
     {"decision": "고침", "facts": ["국산 쌀", "저온 건조", "떡"], "body": "국산 쌀을 저온 건조한 떡"}),
    ("관절이 부드러워지는 우엉 차", ["거짓_과장"], {"decision": "불가", "facts": [], "body": None}),
]

FIX_RULES = (
    "각 문구는 전문가가 적힌 유형의 위반으로 판정한 광고 문구입니다(품목 함께 적음).\n"
    "할 일: 위반 표현만 지우고, 문구에 실제로 적힌 사실만 남긴 짧은 문장(명사구 가능)을 만드세요.\n"
    "규칙\n"
    "1. 사실 = 원료명 · 성분 함량 · 영양성분 수치(지방 0g · 비율 85%) · 용량 · 원산지 · 산지 · 제조 · 가공 방법(건조 · 숙성 · "
    "발효 · 착즙) · 제품 종류. 원문 낱말을 그대로 씁니다(바꾸거나 줄이지 않음).\n"
    "2. 새 낱말 · 새 사실 · 기능성 문구(「~에 도움」)를 더하지 않습니다. 효능 · 효과 · 순위 · 최고 · 보장 · 후기 · 질병 · "
    "의약품 · 타사 비교 표현은 모두 지웁니다.\n"
    "3. 위 사실이 **하나라도** 있으면 decision 은 \"고침\"입니다(사실만 남깁니다). 제품 종류 말고는 사실이 하나도 없을 때만 \"불가\"입니다.\n"
    "4. 순위 · 수상 · 방송 · 인기 · 최초 · 특허 강조 · 후기 · 비교도 위반 표현입니다. 위반으로 볼 표현이 정말 하나도 없을 때만 "
    "decision 을 \"위반아님\"으로 합니다.\n"
    "5. facts 에는 고친 문장에 남긴 사실을 원문 표기 그대로 적습니다.\n"
)


def fix_prompt(batch: list[tuple[str, list[str], str | None]]) -> str:
    shots = "\n".join(f"예) 문구: {i} · 위반: {', '.join(t)} → {json.dumps(o, ensure_ascii=False)}" for i, t, o in FEWSHOT)
    items = "\n".join(f"{k}. [{', '.join(t)} · {m or '품목 모름'}] {x}" for k, (x, t, m) in enumerate(batch))
    return (FIX_RULES + shots + "\n\n문구 목록\n" + items + "\n\n"
            '출력: {"results": [{"i": 번호, "decision": "고침"|"불가"|"위반아님", "facts": [...], "body": "고친 문장" 또는 null}, ...]} '
            "— 목록의 모든 번호에 하나씩 답합니다.")


def variant_prompt(batch: list[tuple[str, list[str], str]]) -> str:
    items = "\n".join(f"{k}. [{', '.join(t)} → 새 제품: {sw}] {x}" for k, (x, t, sw) in enumerate(batch))
    return (
        "아래 각 위반 광고 문구마다, **같은 방식의 위반**을 쓰되 제품 · 원료를 적힌 「새 제품」으로 바꾼 새 가상 광고 문구를 1개씩 쓰세요.\n"
        "조건: 원문 낱말을 그대로 베끼지 말고 문장 구조도 바꿉니다. 실존 브랜드 · 회사 · 인물 이름을 쓰지 않습니다. "
        "원문에 원산지 · 제조 방법 · 용량 같은 사실이 있었다면 새 제품에 맞는 다른 사실로 바꿔 넣습니다. 길이는 원문과 비슷하게.\n"
        f"문구 목록\n{items}\n\n"
        '출력: {"results": [{"i": 번호, "input": "새 광고 문구"}, ...]} — 목록의 모든 번호에 하나씩.'
    )


class Budget:
    """누적 사용액 — 여러 번 나눠 돌려도 합계가 상한을 넘지 않게 `_private/expand_spend.json` 에 쌓는다."""

    def __init__(self, model: str) -> None:
        self.price = PRICE.get(model, PRICE_UNKNOWN)
        self.data = json.loads(SPEND.read_text(encoding="utf-8")) if SPEND.exists() else {"usd": 0.0, "runs": []}
        self.lock = threading.Lock()
        self.run_usd = 0.0

    def cost(self, pin: int, pout: int) -> float:
        return pin / 1e6 * self.price[0] + pout / 1e6 * self.price[1]

    def left(self) -> float:
        return BUDGET_USD - self.data["usd"]

    def add(self, pin: int, pout: int) -> None:
        with self.lock:
            c = self.cost(pin, pout)
            self.data["usd"] += c
            self.run_usd += c

    def save(self, note: str) -> None:
        self.data["runs"].append({"note": note, "usd": round(self.run_usd, 4)})
        self.data["usd"] = round(self.data["usd"], 4)
        SPEND.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


class Teacher:
    def __init__(self, model: str, budget: Budget) -> None:
        from collect import env  # noqa: PLC0415 — 키를 쥐는 곳은 하나다

        self.key = env.get("OPENAI_API_KEY")
        self.model = model
        self.budget = budget
        self.usage: collections.Counter[str] = collections.Counter()

    def ask(self, prompt: str, temperature: float) -> dict | None:
        if self.budget.left() <= 0:
            self.usage["예산 초과로 건너뜀"] += 1
            return None
        body = {"model": self.model, "temperature": temperature, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"),  # noqa: S310 — 주소는 상수다
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        for _ in range(2):
            try:
                with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310
                    data = json.load(res)
                u = data.get("usage", {})
                self.budget.add(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
                for k in ("prompt_tokens", "completion_tokens"):
                    self.usage[k] += u.get(k, 0)
                self.usage["calls"] += 1
                return json.loads(data["choices"][0]["message"]["content"])
            except urllib.error.HTTPError as e:
                self.usage[f"http{e.code}"] += 1  # 🚨 응답 본문은 싣지 않는다 — 보낸 문구가 되돌아올 수 있다
                if e.code in (400, 401, 403, 404):
                    return None
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
                self.usage["errors"] += 1
        return None


def answer_key_inputs() -> list[str]:
    out = []
    for name in ("real_answer_key.jsonl", "answer_key_v2_draft.jsonl"):
        p = PRIV / name
        if p.exists():
            out += [norm(json.loads(line)["input"]) for line in p.open(encoding="utf-8") if line.strip()]
    return out


def leaks(text: str, keys: list[str], words: list[str]) -> bool:
    """정답표(평가 전용) 문장과 같거나 닮았는가 — `gen_synthetic_stage1` 의 거르기와 같다."""
    k = norm(text)
    return any(w in text.replace(" ", "") for w in words) or any(
        difflib.SequenceMatcher(None, k, a).ratio() >= SIM_MAX or (len(a) >= 7 and a in k) for a in keys)


def cmd_seeds() -> None:
    keys = answer_key_inputs()
    words = json.loads((PRIV / "answer_words.json").read_text(encoding="utf-8"))
    seen, rows, drop = set(), [], collections.Counter()
    for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if not r.get("labels") or r.get("origin") != "real" or r.get("품목") not in DOMAIN:
            continue
        k = norm(r["text"])
        if k in seen:
            drop["중복"] += 1
        elif len(r["text"]) < 4 or len(r["text"]) > 120:
            drop["길이"] += 1
        elif leaks(r["text"], keys, words):
            drop["정답표 닮음"] += 1
        else:
            seen.add(k)
            rows.append({"sid": r["id"], "text": r["text"], "labels": r["labels"], "품목": r["품목"],
                         "provenance": r.get("provenance")})
    random.Random(SEED).shuffle(rows)
    with SEEDS.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"씨앗 {len(rows)} · 품목 {dict(collections.Counter(r['품목'] for r in rows))} · 버림 {dict(drop)} · 정답표 문장 {len(keys)}")


def cmd_mfds() -> None:
    keys = answer_key_inputs()
    words = json.loads((PRIV / "answer_words.json").read_text(encoding="utf-8"))
    rows, drop = [], collections.Counter()
    for line in (ROOT / "data/derived/mfds_guide_labels.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("종류") != "수정쌍":
            continue
        src, dst = (r.get("문구") or "").strip(), (r.get("수정문구") or "").strip()
        if not src or not dst or dst.startswith("*") or norm(src) == norm(dst):
            drop["정답 없음 · 표기 지시"] += 1
        elif leaks(src, keys, words):
            drop["정답표 닮음"] += 1
        elif not gate(src, dst).passed:
            # 사람 정답이어도 우리 관문과 어긋나면 넣지 않는다 — 2017 특수용도식품(환자식 · 영아식) 기준이라
            # 「당뇨환자용」 같은 표현이 정답에 있고, 「유럽기준」 같은 낱말 조각도 많다
            drop["관문"] += 1
        else:
            rows.append({"id": f"m{len(rows):04d}", "group": "식약처수정쌍", "input": src, "violation_types": [],
                         "output": {"body": dst, "mandatory_note": None, "placement": None}, "synthetic": False,
                         "source": "mfds_special_use_guide", "prompt_version": PROMPT_VERSION})
    with (PRIV / "expand_mfds_rows.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"식약처 수정쌍 받아들임 {len(rows)} · 버림 {dict(drop)}")


_HF: list[str] = []


def swap_target(item: str, rng: random.Random) -> str:
    if item == "화장품":
        return rng.choice(COSMETIC_PRODUCTS)
    if item == "건기식":
        if not _HF:
            _HF.extend(sorted({json.loads(x).get("APLC_RAWMTRL_NM", "").strip()
                               for x in (ROOT / "data/derived/hf_display_claims.jsonl").open(encoding="utf-8")} - {""}))
        return f"{rng.choice(_HF)} 건강기능식품"
    return rng.choice(FOODS)


def judge_one(text: str, types: list[str], ans: dict | None, keys: list[str], words: list[str]) -> dict:
    """교사 답 하나를 거른다 — 사유를 모두 적는다. `bias` 는 편향 막이(1 · 2)에만 걸린 사유다."""
    if not ans:
        return {"status": "교사 실패", "why": ["교사 실패"]}
    dec, body = ans.get("decision"), ans.get("body")
    facts = [f for f in ans.get("facts") or [] if isinstance(f, str) and f.strip()]
    why: list[str] = []
    bias: list[str] = []
    if dec == "위반아님":
        return {"status": "위반아님", "why": ["교사가 위반 아님"]}
    if dec == "불가":
        if [f for f in facts if norm(f) and norm(f) in norm(text)]:
            bias.append("사실 있는데 불가")
        elif FACT_SIGNAL.search(text):
            bias.append("사실 신호 있는데 불가")
        out: dict = {"infeasible": next((t for t in SEVERITY if t in types), types[0] if types else "거짓_과장")}
    elif dec == "고침" and isinstance(body, str) and body.strip():
        body = body.strip()
        if not facts:
            why.append("사실 목록 없음")
        if [f for f in facts if norm(f) not in norm(text)]:
            why.append("원문에 없는 사실")
        if [f for f in facts if norm(f) in norm(text) and norm(f) not in norm(body)]:
            bias.append("사실 빠짐(교사 목록)")
        if fact_numbers(text) - fact_numbers(body):
            bias.append("사실 숫자 빠짐")
        g = gate(text, body)
        if not g.passed:
            why += [f"관문: {w.split(':')[0]}" for w in g.reasons]
        if leaks(body, keys, words):
            why.append("정답표 닮음")
        out = {"body": body, "mandatory_note": None, "placement": None}
    else:
        return {"status": "형식", "why": ["형식"]}
    return {"status": "ok" if not why and not bias else "버림", "why": why, "bias": bias, "output": out,
            "facts": facts, "len_ratio": round(len(body) / max(1, len(text)), 2) if "body" in out else None}


def batched(xs: list, n: int) -> list[list]:
    return [xs[i: i + n] for i in range(0, len(xs), n)]


def ask_batches(teacher: Teacher, prompts: list[str], temperature: float) -> list[dict | None]:
    with ThreadPoolExecutor(4) as ex:
        return list(ex.map(lambda p: teacher.ask(p, temperature), prompts))


def by_index(ans: dict | None, n: int) -> list[dict | None]:
    out: list[dict | None] = [None] * n
    for r in (ans or {}).get("results") or []:
        if isinstance(r, dict) and isinstance(r.get("i"), int) and 0 <= r["i"] < n:
            out[r["i"]] = r
    return out


def estimate(part: str, n: int, budget: Budget) -> float:
    """견적 — 묶음 하나당 입력 · 출력 토큰을 넉넉히 잡는다(한글 1자 ≈ 1토큰 이상으로)."""
    calls = -(-n // BATCH) * (2 if part == "B" else 1)
    pin, pout = calls * (len(fix_prompt([("가" * 40, ["거짓_과장"], "식품")] * BATCH)) * 1.5), calls * BATCH * 120
    return budget.cost(int(pin), int(pout))


def cmd_run(part: str, n: int, offset: int, model: str, tag: str, dry: bool) -> None:
    budget = Budget(model)
    est = estimate(part, n, budget)
    print(f"견적 {part} {n}문장 · {model} · 약 ${est:.3f} (보수적) · 누적 ${budget.data['usd']:.3f} / 상한 ${BUDGET_USD}")
    if dry:
        return
    assert est <= budget.left(), f"예산 부족 — 남은 ${budget.left():.3f}"
    from rejudge import rejudge  # noqa: PLC0415 — DB 가 필요하다

    seeds = [json.loads(line) for line in SEEDS.open(encoding="utf-8")]
    # A 와 B 가 같은 씨앗을 쓰지 않게 나눠 쓴다(A 는 앞에서 · B 는 뒤에서)
    pick = seeds[offset: offset + n] if part == "A" else seeds[::-1][offset: offset + n]
    keys = answer_key_inputs()
    words = json.loads((PRIV / "answer_words.json").read_text(encoding="utf-8"))
    teacher = Teacher(model, budget)
    rng = random.Random(SEED + offset)

    texts = [s["text"] for s in pick]
    swaps: list[str | None] = [None] * len(pick)
    if part == "B":
        swaps = [swap_target(s["품목"], rng) for s in pick]
        groups = batched(list(range(len(pick))), BATCH)
        answers = ask_batches(teacher, [variant_prompt([(pick[i]["text"], pick[i]["labels"], swaps[i]) for i in g])
                                        for g in groups], 0.9)
        texts = [""] * len(pick)
        for g, ans in zip(groups, answers):
            for i, r in zip(g, by_index(ans, len(g))):
                v = (r or {}).get("input")
                texts[i] = v.strip() if isinstance(v, str) else ""

    todo = [i for i in range(len(pick)) if texts[i]]
    groups = batched(todo, BATCH)
    fixed: dict[int, dict | None] = {}
    answers = ask_batches(teacher, [fix_prompt([(texts[i], pick[i]["labels"], pick[i]["품목"]) for i in g]) for g in groups], 0.2)
    for g, ans in zip(groups, answers):
        for i, r in zip(g, by_index(ans, len(g))):
            fixed[i] = r

    raw, rows = [], []
    for i, s in enumerate(pick):
        text, ans = texts[i], fixed.get(i)
        rec = {"sid": s["sid"], "part": part, "품목": s["품목"], "types": s["labels"], "input": text, "swap": swaps[i],
               "answer": ans}
        if part == "B":
            if not text:
                rec.update(status="변형 실패", why=["변형 실패"])
            elif difflib.SequenceMatcher(None, norm(text), norm(s["text"])).ratio() >= COPY_MAX:
                rec.update(status="원문 베낌", why=["원문 베낌"])
            elif leaks(text, keys, words):
                rec.update(status="정답표 닮음", why=["정답표 닮음"])
        if "status" not in rec:
            rec.update(judge_one(text, s["labels"], ans, keys, words))
        # 재판정 — 고친 문장이 다른 검사를 모두 지났을 때만
        if rec.get("output", {}).get("body") and not rec.get("why") and not rec.get("bias"):
            rj = rejudge(rec["output"]["body"])
            rec["rejudge"] = rj.status
            if rj.status == "rejected":
                rec["why"].append("재판정 위반")
                rec["status"] = "버림"
        raw.append(rec)
        if rec["status"] == "ok":
            rows.append({"id": f"{part.lower()}{len(rows):05d}", "group": f"확장{part}", "input": text,
                         "violation_types": s["labels"], "output": rec["output"], "synthetic": part == "B",
                         "seed_sid": s["sid"], "generator": model, "prompt_version": PROMPT_VERSION})
    name = part + (f"_{offset}" if offset else "") + (f"_{tag}" if tag else "")
    for fname, data in ((f"expand_{name}_raw.jsonl", raw), (f"expand_{name}_rows.jsonl", rows)):
        with (PRIV / fname).open("w", encoding="utf-8", newline="\n") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    budget.save(f"run {name} n={n} {model}")
    print(f"{part}: 입력 {len(raw)} · 받아들임 {len(rows)} · {dict(teacher.usage)} · 이번 ${budget.run_usd:.4f} · "
          f"누적 ${budget.data['usd']:.4f} / ${BUDGET_USD}")


def cmd_report(names: list[str]) -> None:
    for name in names or ["A", "B"]:
        p = PRIV / f"expand_{name}_raw.jsonl"
        if not p.exists():
            print(f"(없음 {p.name})")
            continue
        raw = [json.loads(line) for line in p.open(encoding="utf-8")]
        st = collections.Counter(r["status"] for r in raw)
        ok = [r for r in raw if r["status"] == "ok"]
        bias_only = [r for r in raw if r["status"] == "버림" and r.get("bias") and not r.get("why")]
        why = collections.Counter(w for r in raw for w in (r.get("why") or []) + (r.get("bias") or []))
        kinds = collections.Counter("불가" if "infeasible" in r["output"] else "고침" for r in ok)
        print(f"\n== {name} · 입력 {len(raw)} · 받아들임 {len(ok)} ({len(ok) / max(1, len(raw)):.0%}) · {dict(kinds)}")
        print(f"   상태 {dict(st)}")
        print(f"   사유 {dict(why.most_common(14))}")
        print(f"   편향 막이 효과 — 막이를 빼면 더 들어왔을 것 {len(bias_only)} "
              f"(고침 {sum('body' in r['output'] for r in bias_only)} · 불가 {sum('infeasible' in r['output'] for r in bias_only)})")
        lr = sorted(r["len_ratio"] for r in ok if r.get("len_ratio") is not None)
        if lr:
            print(f"   길이 비율(고친/원문) 중앙값 {lr[len(lr) // 2]} · 하위 10% {lr[len(lr) // 10]}")
        lr_b = sorted(r["len_ratio"] for r in bias_only if r.get("len_ratio") is not None)
        if lr_b:
            print(f"   사실 빠짐으로 버린 고침의 길이 비율 중앙값 {lr_b[len(lr_b) // 2]}")
        by_type: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
        for r in raw:
            for t in r["types"]:
                by_type[t][0] += 1
                by_type[t][1] += r["status"] == "ok"
        print("   유형별 통과 " + " · ".join(f"{t} {b}/{a}" for t, (a, b) in sorted(by_type.items(), key=lambda x: -x[1][0])))
        ends = collections.Counter(r["output"]["body"].split()[-1] for r in ok if "body" in r["output"] and r["output"]["body"].split())
        print(f"   끝 낱말 상위 5 빈도 {[c for _, c in ends.most_common(5)]} (고침 {sum(ends.values())} 중)")
        print(f"   재판정 {dict(collections.Counter(r.get('rejudge') for r in raw if r.get('rejudge')))}")
    if SPEND.exists():
        print(f"\n💸 누적 ${json.loads(SPEND.read_text(encoding='utf-8'))['usd']:.4f} / ${BUDGET_USD}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seeds", "mfds", "run", "report"])
    ap.add_argument("part", nargs="*", help="run: A | B · report: 결과 이름표(A · B · A_v1 …)")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--tag", default="")
    ap.add_argument("--dry-run", action="store_true", help="견적만 낸다(API 안 씀)")
    args = ap.parse_args()
    if args.cmd == "seeds":
        cmd_seeds()
    elif args.cmd == "mfds":
        cmd_mfds()
    elif args.cmd == "run":
        assert args.part and args.part[0] in ("A", "B"), "run A | run B"
        cmd_run(args.part[0], args.n, args.offset, args.model, args.tag, args.dry_run)
    else:
        cmd_report(args.part)


if __name__ == "__main__":
    main()
