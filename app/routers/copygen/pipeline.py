"""생성 흐름 — 20개 뽑고 · 코드 필터 · 판정 · 보관 · 3개 미만이면 반복 (설계 요약 §3 · §5 · §6)."""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.settings import PARAMS

from .branches import PLACEHOLDER, Branch
from .filters import Inputs, check, render, squeeze

#: 최종 출력 — 🔄 2026-10-15 (전수 점검) 화면의 `gen_want` 와 같은 값(`PARAMS.candidate_n`)을 한 곳에서 읽는다 (D-99 · 종전 3 을 두 곳에 적었다)
WANT = PARAMS.candidate_n
PER_ROUND = 20  # 1회 생성
MAX_ROUNDS = 3  # 자동 반복 상한 — 최대 60 후보


#: 고른 셋의 이름 — 문턱에서 먼 순서. 프로토타입 · 계약의 「보수안 / 균형안 / 공격안」(D-34)과 같은 말이다
TIERS = ("보수안", "균형안", "공격안")


@dataclass
class Kept:
    text: str
    angle: str
    round: int
    judged: str
    model: str = ""
    #: 문턱까지의 거리(`judge.Judged.closeness`)와 가장 가까운 유형 — 보수 · 균형 · 공격을 가른다
    closeness: float = 0.0
    top: str = ""
    top_prob: float = 0.0
    top_threshold: float = 0.0
    #: 고른 셋에 붙는 이름(`TIERS`). 셋을 못 채웠으면 비어 있다 — 둘을 놓고 「보수 · 공격」이라 부르지 않는다
    tier: str = ""
    #: 🆕 2026-10-13 — 인정 · 심사 문구를 끼우기 **전**의 글자(자리표시자가 든 것). 생성 모델에 되돌려 보낼 때는 이것만 쓴다
    raw: str = ""


@dataclass
class Result:
    branch: str
    notice: str
    kept: list[Kept] = field(default_factory=list)
    picked: list[Kept] = field(default_factory=list)
    rounds: list[dict[str, Any]] = field(default_factory=list)
    #: 탈락 후보 — 🚨 로그에만 남긴다. 다음 라운드 프롬프트에는 넣지 않는다 (§5-4)
    dropped: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        """3개를 못 채우면 탐색 실패다 — 기준을 낮추거나 억지로 채우지 않는다 (§6-1)."""
        return "ok" if len(self.picked) >= WANT else "search_failed"

    def reasons(self) -> Counter[str]:
        return Counter(d["reason"] for d in self.dropped)


def pick(kept: list[Kept], want: int = WANT) -> list[Kept]:
    """**보수 · 균형 · 공격** 셋을 고른다 — 문턱에서 먼 것 · 가운데 · 가까운 것 (🔄 2026-10-13 · 권소라).

    보관분을 문턱까지의 거리(`closeness`) 순으로 세워 셋으로 나눈다. 보수안은 가장 먼 것 하나로 정하고,
    공격안은 가까운 구간에서 · 균형안은 가운데 구간에서 **이미 고른 것과 각도가 다르고 글자가 덜 닮은 것**을 고른다.
    구간 안에 그런 것이 없으면 구간(위험도 간격)을 지키고 닮은 정도를 양보한다.
    🔄 종전(시험 코드 10-12)에는 「서로 가장 다른 셋」이었다 — 각도 · 글자 · 모델이 먼 것을 탐욕으로 골랐다.
    🚨 셋을 못 채우면 이름을 붙이지 않는다. 「공격안」도 문턱을 넘지 않은 후보다 — 더 센 문구라는 보증이 아니다.
    """
    ranked = sorted(kept, key=lambda k: k.closeness)
    if len(ranked) < want or want != len(TIERS):
        return ranked[:want]

    def far(k: Kept, chosen: list[Kept]) -> tuple[bool, float]:
        """(각도가 새것인가, 고른 것들과의 글자 거리) — 클수록 덜 닮았다."""
        text = min(
            1 - difflib.SequenceMatcher(None, squeeze(k.text), squeeze(c.text)).ratio()
            for c in chosen
        )
        return k.angle not in {c.angle for c in chosen}, round(text, 2)

    a = len(ranked) // 3
    low, mid, high = ranked[:a], ranked[a : len(ranked) - a], ranked[len(ranked) - a :]
    safe = low[0]
    # 공격안 — 덜 닮은 것을 앞세우고, 같으면 문턱에 더 가까운 것
    bold = max(high, key=lambda k: (*far(k, [safe]), k.closeness))
    # 균형안 — 둘과 덜 닮은 것을 앞세우고, 같으면 구간 한가운데에 가까운 것
    centre = (safe.closeness + bold.closeness) / 2
    even = max(mid, key=lambda k: (*far(k, [safe, bold]), -abs(k.closeness - centre)))
    for k, name in zip((safe, even, bold), TIERS, strict=True):
        k.tier = name
    return [safe, even, bold]


def run(
    inputs: Inputs,
    branch: Branch,
    llm: Any,  # noqa: ANN401 — `generate()` 만 있으면 된다
    judge: Any,  # noqa: ANN401 — `judge()` 만 있으면 된다 (`judge.EncoderJudge`)
    *,
    rounds: int = MAX_ROUNDS,
    per_round: int = PER_ROUND,
    carry: Result | None = None,
    exclude: tuple[str, ...] = (),
) -> Result:
    """`carry` 를 주면 보관분을 들고 한 번 더 돈다 (§6-3).

    `exclude` — **이미 이용자에게 보여 준 문구**(자리표시자가 든 글자). 화면의 「더 탐색하기」가 넘긴다(🆕 2026-10-13).
    그것과 닮은 후보는 중복으로 떨구고, 생성 모델에는 「이미 뽑힌 문구」로 알려 다른 각도 · 표현을 쓰게 한다.
    🔴 생성 모델에 되돌려 보내는 문구는 **인정 · 심사 문구를 끼우기 전의 글자**다(`Kept.raw`).
       ⛔ 종전(시험 코드 포함)에는 끼운 뒤의 글자(`Kept.text`)를 보냈다 — 2라운드부터 인정 문구가 밖으로 나갔다.
    """
    res = carry or Result(branch=branch.key, notice=branch.notice)
    # 프롬프트의 좋은 예를 거의 그대로 돌려준 후보는 중복으로 떨군다 — GPT 가 쓴 것이 아니다
    seen = [
        *(k.raw or k.text for k in res.kept),
        *(d["text"] for d in res.dropped),
        *branch.good,
        *exclude,
    ]
    start = len(res.rounds)

    for i in range(start, start + rounds):
        # 🚨 탈락 문구 원문은 넘기지 않는다 — 사유 유형 · 건수만 (§5-3)
        known = [*exclude, *(k.raw or k.text for k in res.kept)]
        cands = llm.generate(inputs, branch, per_round, known, res.reasons())
        stat: Counter[str] = Counter(generated=len(cands))
        for c in cands:
            raw = c["text"]
            if why := check(raw, inputs, branch, seen):
                res.dropped.append({"round": i, "text": raw, "reason": why[0], "hit": why[1]})
                stat[why[0]] += 1
                seen.append(raw)
                continue
            seen.append(raw)
            text = render(raw, inputs)
            # 🚨 고정 문구(인정 · 심사 문구)는 판정에 넣지 않는다 — 엔진이 「도움을 줄 수 있음」을 유형 후보로 올려
            #    인정 문구가 든 후보가 전부 탈락한다(10-03 실측). 인정 문구는 글자 그대로 끼운 것이라 나머지만 본다
            j = judge.judge(raw.replace(PLACEHOLDER, " ").strip(), branch)
            if not j.passed:
                res.dropped.append(
                    {
                        "round": i,
                        "text": text,
                        "reason": "judge",
                        "hit": f"{j.outcome} · {j.detail}",
                    }
                )
                stat["judge"] += 1
                continue
            res.kept.append(
                Kept(
                    text,
                    c["angle"],
                    i,
                    j.outcome,
                    c.get("model", ""),
                    j.closeness,
                    j.top,
                    j.top_prob,
                    j.top_threshold,
                    raw=raw,
                )
            )
            stat["kept"] += 1
        res.rounds.append(dict(stat))
        if len(res.kept) >= WANT:
            break

    res.picked = pick(res.kept)
    return res
