"""생성 흐름 — 20개 뽑고 · 코드 필터 · 판정 · 보관 · 3개 미만이면 반복 (설계 요약 §3 · §5 · §6)."""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from branches import PLACEHOLDER, Branch
from filters import Inputs, check, render, squeeze

WANT = 3  # 최종 출력
PER_ROUND = 20  # 1회 생성
MAX_ROUNDS = 3  # 자동 반복 상한 — 최대 60 후보


@dataclass
class Kept:
    text: str
    angle: str
    round: int
    judged: str
    model: str = ""


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
    """서로 가장 다른 것을 고른다 — 각도가 안 겹치는 것을 앞세우고, 글자가 가장 먼 것부터 (탐욕)."""
    if len(kept) <= want:
        return list(kept)

    def dist(a: Kept, b: Kept) -> float:
        d = 1 - difflib.SequenceMatcher(None, squeeze(a.text), squeeze(b.text)).ratio()
        return d + (0.3 if a.angle != b.angle else 0.0) + (0.3 if a.model != b.model else 0.0)

    chosen = [kept[0]]
    while len(chosen) < want:
        rest = [k for k in kept if k not in chosen]
        chosen.append(max(rest, key=lambda k: min(dist(k, c) for c in chosen)))
    return chosen


def run(
    inputs: Inputs,
    branch: Branch,
    llm: Any,  # noqa: ANN401 — `generate()` 만 있으면 된다
    judge: Any,  # noqa: ANN401 — `judge()` 만 있으면 된다
    *,
    rounds: int = MAX_ROUNDS,
    per_round: int = PER_ROUND,
    carry: Result | None = None,
) -> Result:
    """`carry` 를 주면 「더 탐색하기」다 — 보관분을 들고 한 번 더 돈다 (§6-3)."""
    res = carry or Result(branch=branch.key, notice=branch.notice)
    # 프롬프트의 좋은 예를 거의 그대로 돌려준 후보는 중복으로 떨군다 — GPT 가 쓴 것이 아니다
    seen = [k.text for k in res.kept] + [d["text"] for d in res.dropped] + list(branch.good)
    start = len(res.rounds)

    for i in range(start, start + rounds):
        # 🚨 탈락 문구 원문은 넘기지 않는다 — 사유 유형 · 건수만 (§5-3)
        cands = llm.generate(inputs, branch, per_round, [k.text for k in res.kept], res.reasons())
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
            res.kept.append(Kept(text, c["angle"], i, j.outcome, c.get("model", "")))
            stat["kept"] += 1
        res.rounds.append(dict(stat))
        if len(res.kept) >= WANT:
            break

    res.picked = pick(res.kept)
    return res
