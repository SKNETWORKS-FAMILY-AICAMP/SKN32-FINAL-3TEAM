"""app/routers/copygen — 카피 생성 엔진(GPT 생성 → 코드 필터 → 인코더 판정) · 소유자 ksr (2026-10-13).

시험 코드 `docs/ksr/llm_copy/`(10-03 ~ 10-12 · 결과표 `docs/ksr/LLM_카피생성_분기별_프롬프트_결과표_ksr_2026-10-12.md`)를
화면(`POST /u/generate`)에 붙인 것이다. 흐름은 그때와 같다 —

    GPT 가 후보 20개를 쓴다(모델 둘 · 10개씩)  →  코드 필터(지어낸 수치 · 인증 · 성분 · 금지어 · 중복)
    →  인코더 판정(유형 후보가 문턱을 넘으면 탈락)  →  3개가 모일 때까지 최대 3라운드  →  서로 가장 다른 3개

🔴 **GPT API 를 생성 경로에서 부른다** — D-78 ② 는 「GPT 는 판정 · 생성 런타임 밖」이었다. 2026-10-13 권소라가 팀장과 협의해
   **생성에만** 붙이기로 했다(판정에는 넣지 않는다 — 판정은 우리 인코더가 한다). ⬜ 결정 원장(D-78)의 개정은 팀장 몫이다.
   · 밖으로 나가는 것 — 이용자가 적은 **제품 정보**(제품명 · 종류 · 간단한 문구 · 특징 · 원료 · 인증 이름 · 대상).
   · 나가지 않는 것 — **인정 · 심사 문구**(고정 문구 · 코드가 자리표시자에 끼운다) · 검수 문구 · 판정 결과.
   · 화면이 이 사실을 입력 칸 옆에 적는다(`gen_external`).
🚨 **켜는 스위치가 있다** — `.env` 의 `COPYLANE_COPYGEN=gpt` 일 때만 부른다. 비었으면 꺼짐이고 화면은 「준비 안 됨」을 그린다.
   키(`OPENAI_API_KEY`)가 있다는 것만으로는 켜지지 않는다 — 평가용 키가 있는 기기에서 테스트 · 다른 화면이 호출하지 않게.
🚨 「통과」는 **위반 후보를 못 찾았다**는 뜻이다. 적법 확인이 아니다 — 화면도 그렇게 적는다.
⛔ 탈락 문구 원문은 화면 · 로그에 남기지 않는다 — 사유 유형과 건수만 낸다 (설계 요약 §5-3).
⛔ 계약 `GenerateResponse`(잔여 리스크 · 소구력 보존)를 채우지 않는다 — 그 수치를 재는 노드가 없다. 지어내지 않는다 (D-147).
"""

from __future__ import annotations

import logging
from collections import Counter

from . import llm as _llm
from .branches import BRANCHES
from .errors import CopyGenError, CopyGenOff
from .filters import REASONS, Inputs
from .judge import EncoderJudge
from .pipeline import MAX_ROUNDS, PER_ROUND, WANT, Result
from .pipeline import run as _run

__all__ = [
    "BRANCHES",
    "MAX_ROUNDS",
    "PER_ROUND",
    "REASONS",
    "WANT",
    "CopyGenError",
    "CopyGenOff",
    "Result",
    "generate",
    "off_reason",
]

_log = logging.getLogger(__name__)

#: 켜는 값 — `.env` `COPYLANE_COPYGEN`. 이 밖의 값 · 빈 값은 꺼짐이다
ENV_SWITCH = "COPYLANE_COPYGEN"
ON_VALUE = "gpt"


def off_reason() -> str | None:
    """생성 엔진을 못 쓰는 까닭 — 쓸 수 있으면 `None`. 화면이 이 글자를 그대로 그린다.

    ★ 세 가지를 본다 — 스위치 · 키 · 판정 인코더. 인코더가 없으면 **생성하지 않는다** — 판정을 안 거친 후보를 내지 않는다.
    """
    from app import encoder as enc  # noqa: PLC0415
    from collect import env  # noqa: PLC0415 — `.env` 를 읽는 곳은 하나다 (D-99)

    if env.setting(ENV_SWITCH).lower() != ON_VALUE:
        return "이 환경에는 카피 생성 엔진을 켜 두지 않았어요."
    if not _llm.has_key():
        return "카피 생성 엔진의 키가 설정되지 않았어요."
    if enc.configured_dir() is None:
        return "판정 인코더가 설정되지 않았어요 — 판정을 거치지 않은 문구는 만들지 않아요."
    return None


def generate(branch_key: str, fields: dict) -> Result:
    """분기와 이용자가 적은 값으로 후보를 만든다. 🚨 수십 초 걸린다 — 부르는 쪽이 스레드로 돌린다.

    `CopyGenOff` — 엔진을 쓸 수 없다(스위치 · 키 · 인코더) · `CopyGenError` — 호출이 실패했다.
    """
    if why := off_reason():
        raise CopyGenOff(why)
    branch = BRANCHES[branch_key]
    inputs = Inputs.from_dict(fields)
    if branch.needs_fixed and not inputs.fixed:
        raise ValueError("이 분기는 고정 문구(fixed)가 있어야 한다")
    gen = _llm.make()
    res = _run(inputs, branch, gen, EncoderJudge())
    # 🚨 문구는 찍지 않는다 — 건수만 (이용자 입력과 생성 문구는 로그에 남기지 않는다)
    dropped: Counter[str] = res.reasons()
    _log.info(
        "카피 생성 · 분기=%s · 모델=%s · 라운드=%d · 보관=%d · 탈락=%s · 토큰=%s",
        branch_key,
        gen.model,
        len(res.rounds),
        len(res.kept),
        dict(dropped),
        dict(gen.usage),
    )
    return res
