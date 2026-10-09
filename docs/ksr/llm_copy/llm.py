"""후보 생성 — GPT 1회 호출로 20개 (설계 요약 §3-1 · §8).

🚨 `OPENAI_API_KEY` 는 팀 규칙상 **평가·비교 전용**이다 (D-78 ②). 이 폴더는 실험이고 `app/` 의 판정·생성 경로에 넣지 않는다.
   키는 `.env` 에서만 읽고 화면 · 로그에 찍지 않는다.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import urllib.error
import urllib.request
from collections import Counter

from branches import ANGLES, PLACEHOLDER, Branch
from filters import REASONS, Inputs

ROOT = pathlib.Path(__file__).resolve().parents[3]
URL = "https://api.openai.com/v1/chat/completions"
#: `--model` 을 안 줬을 때 쓰는 값 — 쉼표로 이으면 섞어 돌린다(`run.make_llm`).
#: 🔄 2026-10-08 — 종전 `gpt-4o-mini` 는 20개를 요청하면 16개만 냈다(10-03 실행 1). 10-03 최종 3개를 뽑은 섞음으로 바꿨다
DEFAULT_MODEL = "gpt-5.6-luna,gpt-6-luna"

SYSTEM = """너는 한국어 광고 카피라이터다. 제품 정보와 규칙을 받아 광고 문구 후보를 만든다.

원칙
1. 제품 정보에 적힌 것만 사실로 쓴다. 적히지 않은 수치 · 성분 · 인증 · 시험 · 수상을 지어내지 않는다.
2. 「쓸 수 있는 것」 안에서 다양하게 쓴다. 말투 · 길이 · 문장 끝을 서로 다르게 한다.
3. 최고 · 유일 · 1위 · 타사 대비 같은 비교 · 최상급을 쓰지 않는다.
4. 문구 하나는 한 문장, 15~40자 안팎이다. 「광고」 표시나 주의 문구는 붙이지 않는다.
5. JSON 만 출력한다: {"candidates": [{"angle": "<각도>", "text": "<문구>"}, ...]}"""


def _lines(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {x}" for x in items)


def user_prompt(
    inputs: Inputs, branch: Branch, n: int, kept: list[str], rejected: Counter[str]
) -> str:
    """분기의 허용 범위를 먼저 주고, 각도를 지정해 뽑는다 (§8-1 · §8-2)."""
    facts = []
    if inputs.name:
        facts.append(f"제품명: {inputs.name}")
    if inputs.kind:
        facts.append(f"제품 유형: {inputs.kind}")
    if inputs.phrase:
        facts.append(f"이용자가 적은 문구: {inputs.phrase}")
    if inputs.features:
        facts.append("특징: " + " / ".join(inputs.features))
    if inputs.ingredients:
        facts.append("성분·원료: " + ", ".join(inputs.ingredients))
    if inputs.certs:
        facts.append("인증 사실: " + ", ".join(inputs.certs))
    if inputs.target:
        facts.append(f"대상: {inputs.target}")

    # 재료가 없는 각도는 요청하지 않는다 — 빈 각도를 채우려고 지어내는 것을 막는다
    angles = [
        a
        for a in ANGLES
        if not (a == "원료 이야기" and not inputs.ingredients)
        and not (a == "대상" and not inputs.target)
        and not (a == "제품 사실" and not (inputs.name or inputs.kind or inputs.certs))
    ]
    per = max(1, -(-n // len(angles)))
    parts = [
        f"[분기] {branch.label}",
        "[제품 정보 — 이것이 사실의 전부다]\n" + "\n".join(facts),
        "[쓸 수 있는 것]\n" + _lines(branch.allowed),
        "[지킬 것]\n" + _lines(branch.rules),
        "[좋은 예 — 다른 제품의 것이다. 범위만 참고하고 문장 틀 · 낱말을 따라 쓰지 않는다]\n"
        + _lines(branch.good),
        "[나쁜 예]\n" + "\n".join(f"- {t} → {why}" for t, why in branch.bad),
    ]
    if not inputs.name:
        parts.append("[제품명] 주어지지 않았다 — 제품 이름 · 브랜드 이름을 지어내지 않는다.")
    if branch.needs_fixed:
        parts.append(
            f"[고정 문구] 기능성은 직접 쓰지 말고 {PLACEHOLDER} 를 문구마다 정확히 한 번 넣는다. "
            "그 자리에 인정 · 심사 문구가 글자 그대로 들어간다."
        )
    if kept:
        parts.append(
            "[이미 뽑힌 문구 — 이것과 겹치지 않게, 다른 각도 · 다른 표현으로]\n"
            + _lines(tuple(kept))
        )
    if rejected:
        # 🚨 탈락 문구 원문은 넘기지 않는다 — 사유 유형과 건수만 (§5-3 · §5-4)
        parts.append(
            "[지난 후보가 걸린 이유 — 같은 실수를 피한다]\n"
            + _lines(tuple(f"{REASONS[k]} {v}건" for k, v in rejected.most_common()))
        )
    parts.append(
        f"[요청] 후보 {n}개. 각도는 {' · '.join(angles)} {len(angles)}가지이고 "
        f"각도마다 {per}개 안팎으로 나눈다."
    )
    return "\n\n".join(parts)


def _api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        from dotenv import dotenv_values  # noqa: PLC0415

        key = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") or ""
    if not key:
        raise SystemExit(
            "OPENAI_API_KEY 가 없다 — `uv run python launcher.py setkey` 로 .env 에 넣는다 "
            "(키 없이 흐름만 보려면 --fake)"
        )
    return key


class OpenAIChat:
    def __init__(self, model: str, temperature: float | None = None) -> None:
        self.model = model
        self.temperature = temperature
        self.usage: Counter[str] = Counter()
        self._key = _api_key()

    def generate(
        self, inputs: Inputs, branch: Branch, n: int, kept: list[str], rejected: Counter[str]
    ) -> list[dict[str, str]]:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_prompt(inputs, branch, n, kept, rejected)},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        req = urllib.request.Request(  # noqa: S310 — 주소는 상수다
            URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310
                data = json.load(res)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise SystemExit(f"OpenAI 호출 실패 {e.code} — {detail}") from e
        for k in ("prompt_tokens", "completion_tokens"):
            self.usage[k] += data.get("usage", {}).get(k, 0)
        self.usage["calls"] += 1
        return parse(data["choices"][0]["message"]["content"])


def parse(content: str) -> list[dict[str, str]]:
    try:
        items = json.loads(content).get("candidates", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    out = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("text"), str) and it["text"].strip():
            out.append({"angle": str(it.get("angle", "")), "text": it["text"].strip()})
    return out


class MixLLM:
    """모델 여럿을 섞는다 — 라운드마다 요청 개수를 모델 수로 나눠 각자 뽑고 한 통에 모은다.

    후보마다 `model` 을 달아 어느 모델이 쓴 것인지 남긴다. 3개를 고를 때 모델이 겹치지 않는 쪽을 앞세운다(`pipeline.pick`).
    """

    def __init__(self, llms: list) -> None:  # noqa: ANN001
        self.llms = llms
        self.model = "+".join(m.model for m in llms)

    @property
    def usage(self) -> Counter[str]:
        total: Counter[str] = Counter()
        for m in self.llms:
            for k, v in m.usage.items():
                total[f"{m.model}:{k}"] += v
        return total

    def generate(
        self, inputs: Inputs, branch: Branch, n: int, kept: list[str], rejected: Counter[str]
    ) -> list[dict[str, str]]:
        per = -(-n // len(self.llms))
        outs = [
            [{**c, "model": m.model} for c in m.generate(inputs, branch, per, kept, rejected)]
            for m in self.llms
        ]
        # 번갈아 섞는다 — 앞 모델의 후보가 먼저 자리를 차지해 뒤 모델 것이 중복으로 밀리지 않게
        mixed = []
        for i in range(max(map(len, outs), default=0)):
            mixed.extend(o[i] for o in outs if i < len(o))
        return mixed


class FakeLLM:
    """키 없이 흐름을 돌려 보는 대역 — 좋은 후보와 일부러 틀린 후보를 섞어 낸다. 🚨 문구 품질을 재는 데 쓰지 않는다."""

    usage: Counter[str] = Counter()
    model = "fake"

    def __init__(self) -> None:
        self.round = 0

    def generate(
        self, inputs: Inputs, branch: Branch, n: int, kept: list[str], rejected: Counter[str]
    ) -> list[dict[str, str]]:
        feat = inputs.features[0] if inputs.features else "가볍게"
        ingr = inputs.ingredients[0] if inputs.ingredients else "원료"
        fx = f" {PLACEHOLDER}" if branch.needs_fixed else ""
        inputs = dataclasses.replace(
            inputs, name=inputs.name or "이 제품", kind=inputs.kind or branch.category
        )
        pool = [
            ("사용 장면", f"바쁜 아침에도 {feat} 즐기는 {inputs.name}{fx}"),
            ("감각", f"{feat}, 매일 손이 가는 {inputs.kind}{fx}"),
            ("원료 이야기", f"{ingr}을 담아 만든 {inputs.name}{fx}"),
            ("대상", f"하루를 시작하는 당신에게, {inputs.name}{fx}"),
            ("제품 사실", f"{inputs.kind}의 기본에 충실한 {inputs.name}{fx}"),
            ("사용 장면", f"퇴근 후 가볍게 꺼내는 {inputs.name}{fx}"),
            ("감각", f"{inputs.name} 97% 만족, 72시간 지속{fx}"),
            ("원료 이야기", f"세라마이드와 콜라겐을 더한 {inputs.name}{fx}"),
            ("제품 사실", f"임상 테스트를 마친 {inputs.name}{fx}"),
            ("대상", f"업계 1위, 최고의 {inputs.kind}{fx}"),
            ("감각", f"염증을 가라앉히고 치료하는 {inputs.name}{fx}"),
            ("사용 장면", f"주말 나들이에 챙기는 {inputs.name}{fx}"),
            ("대상", f"당뇨에 좋은 차처럼 즐기는 {inputs.name}{fx}"),
        ]
        self.round += 1
        shift = (self.round - 1) * 5
        return [{"angle": a, "text": t} for a, t in (pool[shift:] + pool[:shift])[:n]]
