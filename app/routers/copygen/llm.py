"""후보 생성 — GPT 호출 (설계 요약 §3-1 · §8). 프롬프트는 시험 코드(`docs/ksr/llm_copy/llm.py`)의 10-12 판 그대로다.

🔴 여기가 **밖으로 나가는 유일한 자리**다 — 왜 붙였고 무엇이 나가는지는 `__init__.py` 머리말에 있다 (D-78 ② · 2026-10-13).
🚨 키는 `collect.env.get` 한 곳에서 읽는다(D-99 · 읽은 값은 가릴 비밀로 등록된다 · D-111). 화면 · 로그 · 오류 메시지에 찍지 않는다.
🚨 실패는 `CopyGenError` 로 올린다 — 프로세스를 끝내지 않고(시험 코드는 `SystemExit` 였다), 응답 본문을 메시지에 싣지 않는다.
⛔ 새 의존성을 들이지 않는다 — `uv.lock` 은 팀장 단독이다(D-87). 표준 라이브러리 `urllib` 로 부른다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .branches import ANGLES, PLACEHOLDER, Branch
from .errors import CopyGenError, CopyGenOff
from .filters import REASONS, Inputs

URL = "https://api.openai.com/v1/chat/completions"
#: 쓰는 모델 — 쉼표로 이으면 섞어 돌린다(`make`). `.env` 의 `COPYLANE_COPYGEN_MODEL` 로 바꾼다.
#: 🔄 2026-10-08 — 종전 `gpt-4o-mini` 는 20개를 요청하면 16개만 냈다(10-03 실행 1). 10-03 최종 3개를 뽑은 섞음으로 바꿨다
DEFAULT_MODEL = "gpt-5.6-luna,gpt-6-luna"
ENV_MODEL = "COPYLANE_COPYGEN_MODEL"
#: 호출 하나의 대기 상한(초) — 화면이 기다리는 시간이다. 시험 코드는 120 이었다
TIMEOUT_S = 90

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
        facts.append(f"제품 종류: {inputs.kind}")
    if inputs.phrase:
        facts.append(f"이용자가 적은 문구: {inputs.phrase}")
    if inputs.features:
        facts.append("특징: " + " / ".join(inputs.features))
    if inputs.ingredients:
        facts.append("성분·원료: " + ", ".join(inputs.ingredients))
    if inputs.certs and branch.needs_fixed:
        # 🔄 2026-10-12 — 고정 문구 분기에서는 인증 이름이 「문구에 쓸 사실」로 읽히지 않게 한다. 종전에는 「인증 사실:」 한 줄이라
        #    gpt-6-luna 가 자리표시자 대신 인증 이름(「…, 미백 기능성화장품 심사」)을 적어 그 모델의 후보가 전부 떨어졌다(10-12 실행 · 20/20)
        facts.append(
            "받은 심사 · 인정(문구에 적지 않는다 — 이 내용은 고정 문구 자리가 대신 말한다): "
            + ", ".join(inputs.certs)
        )
    elif inputs.certs:
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
            "그 자리에 인정 · 심사 문구가 글자 그대로 들어간다. "
            f"{PLACEHOLDER} 는 중괄호까지 이 글자 그대로 쓴다 — 심사 · 인정의 이름이나 다른 말로 바꿔 적지 않는다. "
            f"그 자리에는 완결된 문장이 들어간다 — {PLACEHOLDER} 는 문구의 맨 끝에 쉼표 · 마침표 뒤로 두거나, "
            f"맨 앞에 두고 줄표(—)로 잇는다. 조사를 붙이거나({PLACEHOLDER}로 · {PLACEHOLDER}와) "
            "문장 가운데에 끼우지 않고, 꾸미는 말 바로 뒤에 붙이지 않는다."
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
    from collect import env  # noqa: PLC0415 — 키를 손에 쥐는 곳은 하나다 (D-99 · D-111)

    key = env.get("OPENAI_API_KEY", required=False)
    if not key:
        raise CopyGenOff("카피 생성 엔진의 키가 설정되지 않았어요.")
    return key


def has_key() -> bool:
    from collect import env  # noqa: PLC0415

    return bool(env.get("OPENAI_API_KEY", required=False))


def make() -> OpenAIChat | MixLLM:
    """설정된 모델로 생성기를 만든다 — 쉼표로 이은 이름이면 섞는다."""
    from collect import env  # noqa: PLC0415

    names = [m.strip() for m in (env.setting(ENV_MODEL) or DEFAULT_MODEL).split(",") if m.strip()]
    llms = [OpenAIChat(m) for m in names]
    return llms[0] if len(llms) == 1 else MixLLM(llms)


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
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:  # noqa: S310
                data = json.load(res)
            content = data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            # 🚨 응답 본문을 싣지 않는다 — 보낸 프롬프트(이용자 입력)가 되돌아올 수 있다. 상태 코드만 남긴다
            raise CopyGenError(f"생성 모델 호출 실패 — HTTP {e.code} ({self.model})") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise CopyGenError(
                f"생성 모델에 닿지 못했다 — {type(e).__name__} ({self.model})"
            ) from e
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise CopyGenError(
                f"생성 모델의 응답이 깨졌다 — {type(e).__name__} ({self.model})"
            ) from e
        for k in ("prompt_tokens", "completion_tokens"):
            self.usage[k] += data.get("usage", {}).get(k, 0)
        self.usage["calls"] += 1
        return parse(content or "")


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

        def one(m) -> list[dict[str, str]]:  # noqa: ANN001
            return [
                {**c, "model": m.model} for c in m.generate(inputs, branch, per, kept, rejected)
            ]

        # 🔄 2026-10-13 — 모델들을 **동시에** 부른다. 화면이 기다리는 시간이 가장 느린 모델 하나만큼으로 준다(시험 코드는 차례로 불렀다).
        #    하나라도 실패하면 그 오류가 그대로 올라간다 — 한쪽 것만으로 채우지 않는다
        with ThreadPoolExecutor(max_workers=len(self.llms)) as pool:
            outs = list(pool.map(one, self.llms))
        # 번갈아 섞는다 — 앞 모델의 후보가 먼저 자리를 차지해 뒤 모델 것이 중복으로 밀리지 않게
        mixed = []
        for i in range(max(map(len, outs), default=0)):
            mixed.extend(o[i] for o in outs if i < len(o))
        return mixed
