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
PROMPT_VERSION = "expand-v3-2026-10-16"
SEED = 20261016
DOMAIN = {"식품", "건기식", "화장품"}
MODEL = "gpt-4o-mini"
BUDGET_USD = 10.0
#: 🆕 v3 — 본 생성은 누적이 이 값에 닿으면 새 호출을 멈춘다(상한 $10 까지 여유를 남긴다 · `--stop-at`)
STOP_AT_USD = 8.0
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
#: 🆕 v3 — 변형이 광고가 아니라 위반을 설명하는 글이 됐다(「인증된 것처럼 보이지만, 이 …는」)
META = re.compile(r"(?:처럼|듯이?|것\s*같은)\s*(?:보이지만|말하지만|하지만)|표현이지만|강조하지만|암시하듯|오해를\s*줄\s*수")
#: 🆕 v3 — 관문의 「원문 숫자 남음」을 **데이터 거르기에서만** 푼다: 고친 문장의 숫자가 모두 단위가 붙은 사실(함량 90% · 20mg ·
#:    48시간)이면 사실 숫자다. 앱의 관문은 그대로다(실제 광고의 「100% 효과」 같은 주장 숫자를 막는 일). 풀지 않으면 시범 B v3 50 중
#:    22 가 이 사유로 버려져 「숫자는 지운다」를 배운다 — 팀이 걱정한 「다 지우는 편향」이 이 길로 생긴다
UNIT_NUM = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|mg|g|kg|ml|mL|L|kcal|cm|mm|시간|일|개월|년|개|종|가지|포|봉|팩|알|분량|억|만)")
#: 🆕 v3 — 고친 문장이 술어 없이 낱말 나열만 남았다 — 사실이 아니라 낱말 조각이다
LIST_ONLY = re.compile(r"^[가-힣A-Za-z]+(?:\s*[,·]\s*[가-힣A-Za-z]+)+$")
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
        "🆕 새 문구에는 위반 표현과 함께 새 제품에 맞는 **구체적인 사실 1~2개**(원료명 · 함량이나 용량 수치 · 원산지 · 제조 · "
        "가공 방법)를 반드시 넣습니다 — 위반만 빼면 사실이 남는 문구여야 합니다. 사실은 그럴듯한 가상의 것으로 씁니다. "
        "길이는 원문과 비슷하거나 조금 길게. 🆕 광고 문구 자체를 씁니다 — 「~처럼 보이지만」 · 「~하는 표현이지만」처럼 "
        "위반을 설명하는 글은 쓰지 않습니다.\n"
        f"문구 목록\n{items}\n\n"
        '출력: {"results": [{"i": 번호, "input": "새 광고 문구"}, ...]} — 목록의 모든 번호에 하나씩.'
    )


def cost(model: str, pin: int, pout: int) -> float:
    price = PRICE.get(model, PRICE_UNKNOWN)
    return pin / 1e6 * price[0] + pout / 1e6 * price[1]


class Budget:
    """누적 사용액 — 여러 번 나눠 돌려도 합계가 상한을 넘지 않게 `_private/expand_spend.json` 에 쌓는다."""

    def __init__(self) -> None:
        self.data = json.loads(SPEND.read_text(encoding="utf-8")) if SPEND.exists() else {"usd": 0.0, "runs": []}
        self.lock = threading.Lock()
        self.stop_at = STOP_AT_USD
        self.run_usd = 0.0

    def left(self) -> float:
        return BUDGET_USD - self.data["usd"]

    def add(self, model: str, pin: int, pout: int) -> None:
        with self.lock:
            c = cost(model, pin, pout)
            self.data["usd"] += c
            self.run_usd += c
            # 🆕 v3 — 호출마다 바로 쌓는다. 조각 끝에만 쓰면 중간에 멈춘 조각의 사용액이 빠진다(10-16 본 생성 2조각째)
            SPEND.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

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
        if self.budget.left() <= 0 or self.budget.data["usd"] >= self.budget.stop_at:
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
                self.budget.add(self.model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
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


def has_words(fact: str, s: str) -> bool:
    """🆕 v3 — 사실의 낱말이 모두 `s` 에 있는가(순서 무관 · 끝 한 글자 활용 차이 허용). 통째 문자열로 견주면 교사가 순서만 바꿔 적은
    사실(원문 「30% 고농축 히알루론산」 → 「히알루론산 30%」)까지 「원문에 없는 사실」로 버렸다(본 생성 B 1조각 159행)."""
    t = norm(s)
    return all(norm(w) in t or (len(w) > 2 and norm(w[:-1]) in t) for w in re.findall(r"[가-힣A-Za-z0-9.%]+", fact))


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
        if [f for f in facts if not has_words(f, text)]:
            why.append("원문에 없는 사실")
        if [f for f in facts if has_words(f, text) and not has_words(f, body)]:
            bias.append("사실 빠짐(교사 목록)")
        if fact_numbers(text) - fact_numbers(body):
            bias.append("사실 숫자 빠짐")
        if LIST_ONLY.match(body):
            why.append("낱말 나열만 남음")
        g = gate(text, body)
        reasons = [w.split(":")[0] for w in g.reasons]
        if "원문 숫자 남음" in reasons and not re.search(r"\d", UNIT_NUM.sub("", body)):
            reasons.remove("원문 숫자 남음")  # 숫자가 모두 단위 붙은 사실이다
        why += [f"관문: {w}" for w in reasons]
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


def estimate(part: str, n: int, model: str, vmodel: str) -> float:
    """견적 — 시범에서 잰 묶음 하나당 토큰(교정 입력 약 1,050 · 출력 약 270 / 변형 입력 약 900 · 출력 약 500)에 3할을 얹는다."""
    calls = -(-n // BATCH)
    est = cost(model, calls * 1400, calls * 360)
    if part == "B":
        est += cost(vmodel, calls * 1200, calls * 700)
    return est


def cmd_run(part: str, n: int, offset: int, model: str, tag: str, dry: bool, stop_at: float, vmodel: str,
            variants: int) -> None:
    if part == "B" and (PRIV / "expand_pause_B").exists():
        print("B 멈춤 표시(_private/expand_pause_B) — 건너뜀", flush=True)  # 🆕 v3 — 돌고 있는 묶음 실행의 순서를 바꿀 때
        return
    budget = Budget()
    budget.stop_at = min(stop_at, BUDGET_USD)
    seeds = [json.loads(line) for line in SEEDS.open(encoding="utf-8")]
    # A 와 B 가 같은 씨앗을 쓰지 않게 나눠 쓴다(A 는 앞에서 · B 는 뒤에서)
    pick = seeds[offset: offset + n] if part == "A" else seeds[::-1][offset: offset + n]
    if part == "A":
        # 🆕 v3 — 인코더 평가용 문장(golden test_sentence)은 학습 적재(`train_stage1_v5.load_rows`)에서 빠진다 — 미리 건너뛰어 돈을 아낀다.
        #    씨앗 파일의 순서는 그대로 둔다(나눠 돌리는 조각의 배정이 흐트러지지 않게)
        test_ids = {json.loads(line)["id"] for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")
                    if '"test_sentence"' in line}
        skipped = sum(s["sid"] in test_ids for s in pick)
        pick = [s for s in pick if s["sid"] not in test_ids]
        print(f"   인코더 평가 문장 건너뜀 {skipped}", flush=True)
    est = estimate(part, len(pick) * (variants if part == "B" else 1), model, vmodel)
    print(f"견적 {part} {n}문장{f' × 변형 {variants}' if part == 'B' else ''} · 교정 {model}"
          f"{f' · 변형 {vmodel}' if part == 'B' else ''} · 약 ${est:.3f} (보수적) · 누적 ${budget.data['usd']:.3f} · "
          f"멈춤선 ${budget.stop_at} · 상한 ${BUDGET_USD}")
    if dry:
        return
    assert est <= budget.stop_at - budget.data["usd"], f"멈춤선까지 남은 ${budget.stop_at - budget.data['usd']:.3f} — 견적 초과"
    from rejudge import rejudge  # noqa: PLC0415 — DB 가 필요하다

    if part == "B":
        pick = pick * variants  # 씨앗당 변형 여러 개 — 바꿔 끼울 제품이 달라 문구가 달라진다
    teacher = Teacher(model, budget)
    vteacher = Teacher(vmodel, budget)
    rng = random.Random(SEED + offset)

    texts = [s["text"] for s in pick]
    swaps: list[str | None] = [None] * len(pick)
    if part == "B":
        swaps = [swap_target(s["품목"], rng) for s in pick]
        groups = batched(list(range(len(pick))), BATCH)
        answers = ask_batches(vteacher, [variant_prompt([(pick[i]["text"], pick[i]["labels"], swaps[i]) for i in g])
                                        for g in groups], 0.9)
        texts = [""] * len(pick)
        for g, ans in zip(groups, answers, strict=True):
            for i, r in zip(g, by_index(ans, len(g)), strict=True):
                v = (r or {}).get("input")
                texts[i] = v.strip() if isinstance(v, str) else ""

    todo = [i for i in range(len(pick)) if texts[i]]
    groups = batched(todo, BATCH)
    fixed: dict[int, dict | None] = {}
    answers = ask_batches(teacher, [fix_prompt([(texts[i], pick[i]["labels"], pick[i]["품목"]) for i in g]) for g in groups], 0.2)
    for g, ans in zip(groups, answers, strict=True):
        for i, r in zip(g, by_index(ans, len(g)), strict=True):
            fixed[i] = r

    metas = [{"sid": s["sid"], "part": part, "품목": s["품목"], "types": s["labels"], "seed_text": s["text"], "input": texts[i],
              "swap": swaps[i], "answer": fixed.get(i), "generator": model, "variant_model": vmodel if part == "B" else None}
             for i, s in enumerate(pick)]
    name = part + (f"_{offset}" if offset else "") + (f"_{tag}" if tag else "")
    budget.save(f"run {name} n={n} {model}" + (f" · 변형 {vmodel}" if part == "B" else ""))
    raw, rows = judge_records(metas, rejudge)
    write_run(name, raw, rows)
    print(f"{part}: 입력 {len(raw)} · 받아들임 {len(rows)} · 교정 {dict(teacher.usage)}"
          + (f" · 변형 {dict(vteacher.usage)}" if part == "B" else "")
          + f" · 이번 ${budget.run_usd:.4f} · 누적 ${budget.data['usd']:.4f} / ${BUDGET_USD}")


def judge_records(metas: list[dict], rejudge: object) -> tuple[list[dict], list[dict]]:
    """저장된 교사 답에 거르기를 건다 — `run` 과 `refilter`(API 없이 다시 거르기)가 같이 쓴다."""
    keys = answer_key_inputs()
    words = json.loads((PRIV / "answer_words.json").read_text(encoding="utf-8"))
    raw, rows = [], []
    for m in metas:
        rec = {k: m.get(k) for k in ("sid", "part", "품목", "types", "seed_text", "input", "swap", "answer", "generator",
                                     "variant_model")}
        text, part = rec["input"] or "", rec["part"]
        if part == "B":
            if not text:
                rec.update(status="변형 실패", why=["변형 실패"])
            elif difflib.SequenceMatcher(None, norm(text), norm(rec["seed_text"] or "")).ratio() >= COPY_MAX:
                rec.update(status="원문 베낌", why=["원문 베낌"])
            elif META.search(text):
                rec.update(status="설명문 변형", why=["설명문 변형"])
            elif leaks(text, keys, words):
                rec.update(status="정답표 닮음", why=["정답표 닮음"])
        if "status" not in rec:
            rec.update(judge_one(text, rec["types"], rec["answer"], keys, words))
        # 재판정 — 고친 문장이 다른 검사를 모두 지났을 때만
        if (rec.get("output") or {}).get("body") and not rec.get("why") and not rec.get("bias"):
            body = rec["output"]["body"]
            # 🆕 v3 — 다시 거를 때 같은 문장의 재판정은 재사용한다(한 건에 1~2초 · 판정 코어는 그대로)
            if m.get("rejudge") and (m.get("output") or {}).get("body") == body:
                rec["rejudge"] = m["rejudge"]
            else:
                rec["rejudge"] = rejudge(body).status  # type: ignore[operator]
            rj = argparse.Namespace(status=rec["rejudge"])
            if rj.status == "rejected":
                rec["why"].append("재판정 위반")
                rec["status"] = "버림"
        raw.append(rec)
        if rec["status"] == "ok":
            rows.append({"id": f"{part.lower()}{len(rows):05d}", "group": f"확장{part}", "input": text,
                         "violation_types": rec["types"], "output": rec["output"], "synthetic": part == "B",
                         "seed_sid": rec["sid"], "generator": rec["generator"], "prompt_version": PROMPT_VERSION})
    return raw, rows


def write_run(name: str, raw: list[dict], rows: list[dict]) -> None:
    for fname, data in ((f"expand_{name}_raw.jsonl", raw), (f"expand_{name}_rows.jsonl", rows)):
        with (PRIV / fname).open("w", encoding="utf-8", newline="\n") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_refilter(names: list[str]) -> None:
    """🆕 v3 — 저장된 교사 답에 지금의 거르기를 다시 건다(API 를 부르지 않는다 · 재판정은 DB 필요)."""
    from rejudge import rejudge  # noqa: PLC0415

    for name in names:
        metas = [json.loads(line) for line in (PRIV / f"expand_{name}_raw.jsonl").open(encoding="utf-8")]
        raw, rows = judge_records(metas, rejudge)
        write_run(name, raw, rows)
        print(f"{name}: 다시 거름 · 입력 {len(raw)} · 받아들임 {len(rows)}")


#: 🆕 v4 (10-17) — 조건부 묶음(K). RunPod 학습(q4b-n1 · q4b-v16)이 실제 광고 31 에서 살림 3 → 1 · v16 포장 1 로 나빠졌다.
#:    원인: 정답표에서 살릴 21 중 20 이 **조건부**(공식 기능성 문구 · 「○○ 함유(함량 병기)」 + 조건)인데, 확장 고침 1,921 은
#:    「도움」 문구 0 · 병기 0 — 교정 지침이 기능성 문구를 금하고 병기를 비웠다. 그래서 정답을 **공개 원천에서 규칙으로** 정하고
#:    (`gen_synthetic_stage1.build_seeds` — 고시 기능성 문구 · 원료명 · 기능성화장품 범주 · 순위 인증) GPT 는 위반 문구만 쓴다
COND_KINDS = ("건기식기능", "화장품기능", "원료사실", "사실·인증순위")
#: 관문의 체험기 꼴이 놓친 것(「…사라졌어요」 · 「먹고 …줄었어요」 · 「#내돈내산」) — 시범 K 에서 봤다
COND_TESTI = re.compile(r"(?:졌|었|았|였|했|봤|됐)(?:어요|어|음|당)|먹고\s|바르고\s|써\s*보|내돈내산|인생템|리얼|솔직|저도|제가")
HF_FORMS = ["캡슐", "정", "분말", "젤리", "음료", "스틱", "환", "액상"]
COND_VTYPES = ["거짓_과장", "소비자_기만", "부당_비교광고", "건강기능식품_오인", "기능성화장품_오인", "후기_체험기_기만"]


def clean_claim(body: str) -> bool:
    """정답으로 쓸 만한 공식 문구인가 — 단서가 달린 문구(「…있으나 인체시험…」 · 「(동물시험을 통하여 …)」) · 공식 문구 둘이 붙은 것 ·
    40 자 넘는 설명문(「○○은 …에서 정제 · 추출한 원료로서 …」)은 뺀다(시범 K 20 씨앗에서 4)."""
    return (not body.startswith("(") and len(body) <= 40 and "으나" not in body and "원료로서" not in body
            and body.count("도움") <= 1)


def cond_seeds(rng: random.Random) -> list[dict]:
    import gen_synthetic_stage1 as gs  # noqa: PLC0415

    golden = [norm(json.loads(line)["text"]) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    words = json.loads((PRIV / "answer_words.json").read_text(encoding="utf-8"))
    seeds = [s for s in gs.build_seeds(rng, words, set(golden), "\n".join(golden))
             if s["kind"] in COND_KINDS and clean_claim(s["target"]["body"])]
    for s in seeds:
        if s["kind"] == "건기식기능":
            s["product"] = rng.choice(HF_FORMS) + " 건강기능식품"
    # 화장품 원료명(재배포 가능) — 「○○ 함유」 + 함량 병기. 정답표 고유 원료 · 표현은 뺀다
    cos = sorted({json.loads(x)["INGR_KOR_NAME"].strip() for x in (ROOT / "data/derived/cosmetic_ingredient.jsonl").open(encoding="utf-8")
                  if json.loads(x).get("redistributable")})
    cos = [c for c in cos if 4 <= len(c) <= 12 and re.search(r"(추출물|오일|씨유|수|워터)$", c)
           and not any(w in c for w in words)]
    for c in rng.sample(cos, min(80, len(cos))):
        seeds.append({"kind": "원료사실", "target": {"body": f"{c} 함유", "mandatory_note": "원재료 함량을 함께 표시",
                                                 "placement": "원료명 표시 근처"}, "product": rng.choice(COSMETIC_PRODUCTS)})
    rng.shuffle(seeds)
    return seeds


def cond_prompt(batch: list[dict], k: int) -> str:
    items = "\n".join(f"{i}. [제품: {s.get('product') or '일반'}] 적법한 문구: {s['target']['body']}" for i, s in enumerate(batch))
    return (
        f"각 '적법한 문구'를 쓸 수 있는 제품의 광고주가 욕심을 내어 위반 요소를 덧붙인 **위반 광고 문구**를 {k}개씩 만드세요.\n"
        "- 위반 요소 예: 효과 과장(완전히 · 즉시 · 100% · 기적) · 근거 없는 수치 · 기간 · 1위 · 유일 · 최고 · 타사 비교 · "
        "일반식품이 기능성을 인정받은 것처럼.\n"
        "- 조건: 위반 요소만 빼면 그 적법한 문구의 뜻으로 돌아가야 합니다. **적법한 문구에 없는 사실(원산지 · 용량 · 제조 방법 · 다른 원료)은 "
        "넣지 않습니다.** 원료명은 철자 그대로 씁니다. 질병 치료 · 의약품 표현과 체험담 · 후기 말투(「먹어 보니」 · "
        "「써 봤어요」)는 넣지 않습니다 — 그런 문구는 고칠 수 없는 위반이라 이 묶음과 다릅니다.\n"
        "- 형식을 서로 다르게: 짧은 키워드형 · 한 문장 카피 · SNS 말투 · 상세페이지 소제목 · 라이브커머스 멘트.\n"
        "- 실존 브랜드 · 회사 · 인물 이름을 쓰지 않습니다. 광고 문구 자체를 씁니다(위반을 설명하는 글 아님).\n"
        f"목록\n{items}\n\n"
        '출력: {"results": [{"i": 번호, "items": [{"input": "위반 광고 문구", "violation_types": ["…"]}, …]}, …]} — 모든 번호에. '
        f"violation_types 는 다음 중에서: {', '.join(COND_VTYPES)}"
    )


def cmd_cond(n: int, per: int, model: str, tag: str, dry: bool, stop_at: float) -> None:
    """🆕 v4 — 조건부 묶음(K). 씨앗 `n` 개 × 문구 `per` 개. 정답은 씨앗의 규칙 정답 그대로."""
    from stage_gate import (  # noqa: PLC0415
        DISEASE,
        DRUG,
        TESTIMONY,
        TESTIMONY_SRC,
        ingredient_changed,
    )

    rng = random.Random(SEED + 17)
    seeds = cond_seeds(rng)[:n]
    budget = Budget()
    budget.stop_at = min(stop_at, BUDGET_USD)
    calls = -(-len(seeds) // 5)
    est = cost(model, calls * 900, calls * 5 * per * 60)
    print(f"조건부 씨앗 {len(seeds)} · {dict(collections.Counter(s['kind'] for s in seeds))} · × {per} · 견적 약 ${est:.3f} · "
          f"누적 ${budget.data['usd']:.3f} · 멈춤선 ${budget.stop_at}")
    if dry:
        return
    assert est <= budget.stop_at - budget.data["usd"], "견적 초과"
    teacher = Teacher(model, budget)
    groups = batched(seeds, 5)
    answers = ask_batches(teacher, [cond_prompt(g, per) for g in groups], 0.9)
    keys = answer_key_inputs()
    words = json.loads((PRIV / "answer_words.json").read_text(encoding="utf-8"))
    golden = [norm(json.loads(line)["text"]) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    gset, gblob = set(golden), "\n".join(golden)
    raw, rows, seen = [], [], set()
    for g, ans in zip(groups, answers, strict=True):
        for s, r in zip(g, by_index(ans, len(g)), strict=True):
            for it in (r or {}).get("items") or []:
                text = (it.get("input") or "").strip() if isinstance(it, dict) else ""
                body = s["target"]["body"]
                vt = [t for t in (it.get("violation_types") or []) if t in COND_VTYPES] or ["거짓_과장"]
                k = norm(text)
                why = []
                if not text or len(text) > 120:
                    why.append("형식")
                elif k in gset or k in gblob:
                    why.append("golden 겹침")
                elif leaks(text, keys, words):
                    why.append("정답표 닮음")
                elif k in seen:
                    why.append("중복")
                elif META.search(text):
                    why.append("설명문")
                elif DISEASE.search(text) or DRUG.search(text):
                    why.append("질병 · 의약품 표현")  # 정책상 불가 — 조건부로 가르치면 포장을 배운다
                elif TESTIMONY.search(text) or TESTIMONY_SRC.search(text) or COND_TESTI.search(text):
                    why.append("체험담 말투")  # 정책상 불가(후기_체험기_기만)
                elif norm(text) == norm(body):
                    why.append("원문 그대로")
                elif ingredient_changed(text, body):
                    why.append("원료명 불일치")  # 정답의 원료명이 문구와 다르면 「원료명을 바꿔 써도 된다」를 가르친다
                elif fact_numbers(text) - fact_numbers(body) or (FACT_SIGNAL.search(text) and not FACT_SIGNAL.search(body)
                                                                 and s["kind"] != "원료사실"):
                    why.append("정답에 없는 사실")  # 정답이 그 사실을 지우면 「사실은 지운다」를 가르친다
                seen.add(k)
                raw.append({"kind": s["kind"], "input": text, "target": s["target"], "types": vt, "why": why})
                if not why:
                    rows.append({"id": f"k{len(rows):05d}", "group": f"조건부:{s['kind']}", "input": text, "violation_types": vt,
                                 "output": s["target"], "synthetic": True, "generator": model, "prompt_version": PROMPT_VERSION})
    name = "K" + (f"_{tag}" if tag else "")
    for fname, data in ((f"expand_{name}_raw.jsonl", raw), (f"expand_{name}_cond.jsonl", rows)):
        with (PRIV / fname).open("w", encoding="utf-8", newline="\n") as f:
            for x in data:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    budget.save(f"cond {name} n={n} × {per} {model}")
    drop = collections.Counter(w for x in raw for w in x["why"])
    print(f"조건부: 문구 {len(raw)} · 받아들임 {len(rows)} · {dict(collections.Counter(r['group'] for r in rows))} · 버림 {dict(drop)} · "
          f"{dict(teacher.usage)} · 이번 ${budget.run_usd:.4f} · 누적 ${budget.data['usd']:.4f}")


#: 🆕 v3 — 최종 묶음에서 불가가 차지할 몫의 상한(새 행 기준). golden 씨앗은 대부분 불가 감이라 다 넣으면 거절로 기운다
MAX_INFEASIBLE = 0.35
#: 같은 끝 낱말로 끝나는 고침의 상한(틀 반복 막이 · 편향 막이 3)
MAX_SAME_END = 0.08
#: 🆕 v4 — 두 번째 묶음(`mix --tag v2` → `expand_mix2.jsonl`) — 사실 남기기 상한 · 조건부 꼴별 상한
MAX_FACT_V2 = 900
COND_CAP = {"조건부:원료사실": 300}
#: 🆕 v3 — 막연한 말 — 사실이 아니라 꾸밈이거나 그 자체로 주의 표현(「천연」 · 「100% 자연」). 4o-mini 가 쓴 변형에 많았다
#:    (본 생성 1조각: 고침 439 중 구체적 사실 신호 190 · 막연한 말 95 — 4.1 변형은 29 중 25 · 1)
VAGUE = re.compile(r"천연|자연|신선한|고급|프리미엄|엄선|비법|전문가|건강한|다양한|풍부한|가득|특별한|정성")


def cmd_mix(v2: bool = False) -> None:
    """🆕 v3 — 4.1 교정 결과(`*_rows.jsonl` · generator gpt-4.1)를 모아 `_private/expand_mix.jsonl` 로. 4o-mini 교정은 넣지 않는다
    (시범에서 받아들인 고침의 절반이 위반이 남았다). 입력 중복을 빼고, 끝 낱말 상한 · 불가 상한을 건다. C(식약처 수정쌍)는 2배."""
    rng = random.Random(SEED)
    rows, seen, drop = [], set(), collections.Counter()
    for p in sorted(PRIV.glob("expand_*_rows.jsonl")):
        if p.name == "expand_mfds_rows.jsonl":
            continue
        for r in map(json.loads, p.open(encoding="utf-8")):
            if r.get("generator") != "gpt-4.1":
                drop["4o-mini 교정"] += 1
                continue
            k = norm(r["input"])
            if k in seen:
                drop["입력 중복"] += 1
                continue
            body = r["output"].get("body")
            if body and (not FACT_SIGNAL.search(body) or VAGUE.search(body)):
                drop["구체적 사실 없음 · 막연한 말"] += 1  # 「성분이 포함된 꿀」 · 「천연 재료로 만든 된장」
                continue
            seen.add(k)
            rows.append(r)
    fixed = [r for r in rows if "body" in r["output"]]
    infeasible = [r for r in rows if "infeasible" in r["output"]]
    rng.shuffle(fixed)
    ends: collections.Counter[str] = collections.Counter()
    cap_end = max(20, int(len(fixed) * MAX_SAME_END))
    kept_fixed = []
    for r in fixed:
        e = (r["output"]["body"].split() or [""])[-1]
        if ends[e] >= cap_end:
            drop["끝 낱말 상한"] += 1
            continue
        ends[e] += 1
        kept_fixed.append(r)
    # 불가는 유형을 고르게 — 유형별로 돌아가며 뽑는다
    cap_inf = int(len(kept_fixed) * MAX_INFEASIBLE / (1 - MAX_INFEASIBLE))
    by_t: dict[str, list[dict]] = collections.defaultdict(list)
    for r in infeasible:
        by_t[r["output"]["infeasible"]].append(r)
    for v in by_t.values():
        rng.shuffle(v)
    kept_inf: list[dict] = []
    while len(kept_inf) < cap_inf and any(by_t.values()):
        for t in sorted(by_t):
            if by_t[t] and len(kept_inf) < cap_inf:
                kept_inf.append(by_t[t].pop())
    drop["불가 상한"] += sum(len(v) for v in by_t.values())
    mfds = [json.loads(line) for line in (PRIV / "expand_mfds_rows.jsonl").open(encoding="utf-8")]
    cond: list[dict] = []
    if v2:
        # 🆕 v4 — 사실 남기기는 상한까지만(정답표는 불가 · 조건부 위주 — 살릴 21 중 사실만 남기기는 1)
        kept_fixed = kept_fixed[:MAX_FACT_V2]
        # 「○○ 함유」만 남은 고침에 함량 병기를 규칙으로 붙인다(정답표 「○○추출물 함유 (함량 병기)」 · 숫자가 이미 있으면 두지 않는다)
        for r in kept_fixed:
            b = r["output"]["body"]
            if "함유" in b and not re.search(r"\d", b) and not r["output"].get("mandatory_note"):
                r["output"] = {**r["output"], "mandatory_note": "원재료 함량을 함께 표시", "placement": "원료명 표시 근처"}
        # 조건부 묶음 — 원료 함유 꼴은 상한(578 이 다른 꼴을 덮지 않게)
        by_k: dict[str, list[dict]] = collections.defaultdict(list)
        for r in map(json.loads, (PRIV / "expand_K_full_cond.jsonl").open(encoding="utf-8")):
            if norm(r["input"]) not in seen:
                seen.add(norm(r["input"]))
                by_k[r["group"]].append(r)
        for g, v in by_k.items():
            rng.shuffle(v)
            cap = COND_CAP.get(g, len(v))
            drop[f"조건부 상한 {g}"] += max(0, len(v) - cap)
            cond += v[:cap]
    out = kept_fixed + kept_inf + cond + mfds * 2
    rng.shuffle(out)
    with (PRIV / ("expand_mix2.jsonl" if v2 else "expand_mix.jsonl")).open("w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    inf_t = collections.Counter(r["output"]["infeasible"] for r in kept_inf)
    n = len(out)
    print(f"묶음 {n} = 사실 남기기 {len(kept_fixed)} ({len(kept_fixed) / n:.0%}) + 조건부 {len(cond)} ({len(cond) / n:.0%}) + "
          f"불가 {len(kept_inf)} ({len(kept_inf) / n:.0%}) + 식약처 {len(mfds)}×2 · 함량 병기 붙임 "
          f"{sum(r['output'].get('mandatory_note') == '원재료 함량을 함께 표시' for r in kept_fixed)}")
    print(f"   조건부 {dict(collections.Counter(r['group'] for r in cond))}")
    print(f"   버림 {dict(drop)} · 불가 유형 {dict(inf_t)} · 끝 낱말 상위 {[c for _, c in ends.most_common(5)]}")


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
    ap.add_argument("cmd", choices=["seeds", "mfds", "run", "refilter", "cond", "mix", "report"])
    ap.add_argument("part", nargs="*", help="run: A | B · report: 결과 이름표(A · B · A_v1 …)")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--model", default=MODEL, help="교정(정답) 교사")
    ap.add_argument("--variant-model", default=MODEL, help="B 의 변형 문구를 쓰는 교사(싼 모델로 충분)")
    ap.add_argument("--variants", type=int, default=1, help="B 씨앗당 변형 수")
    ap.add_argument("--tag", default="")
    ap.add_argument("--dry-run", action="store_true", help="견적만 낸다(API 안 씀)")
    ap.add_argument("--stop-at", type=float, default=STOP_AT_USD, help="누적이 이 값에 닿으면 새 호출을 멈춘다")
    args = ap.parse_args()
    if args.cmd == "seeds":
        cmd_seeds()
    elif args.cmd == "mfds":
        cmd_mfds()
    elif args.cmd == "run":
        assert args.part and args.part[0] in ("A", "B"), "run A | run B"
        cmd_run(args.part[0], args.n, args.offset, args.model, args.tag, args.dry_run, args.stop_at,
                args.variant_model, args.variants)
    elif args.cmd == "cond":
        cmd_cond(args.n, args.variants if args.variants > 1 else 3, args.model, args.tag, args.dry_run, args.stop_at)
    elif args.cmd == "mix":
        cmd_mix(v2=args.tag == "v2")
    elif args.cmd == "refilter":
        cmd_refilter(args.part)
    else:
        cmd_report(args.part)


if __name__ == "__main__":
    main()
