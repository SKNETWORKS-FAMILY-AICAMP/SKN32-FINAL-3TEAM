"""판정엔진 호출 — 팀장 판정 코어를 **그대로** 쓴다 (설계 요약 §3-3 · 점검목록 4-3-6).

검수 그래프(`app.graph.build_review`)를 문장 하나씩 돌린다. 여기서 판정을 새로 쓰지 않는다.
🚨 통과 = 검수 종착 `pass` (확정 ∧ R0). 보류 · 근거없음 · 미판정은 통과가 아니다.
🚨 「통과」는 「위반을 못 찾았다」다 — 엔진이 아는 표현만 잡는다 (설계 요약 §9).
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

from branches import Branch

ROOT = pathlib.Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Judged:
    passed: bool
    outcome: str
    detail: str = ""


class NoJudge:
    """판정을 건너뛴다 — 코드 필터까지만 본 결과다. 🚨 이 결과를 「통과」로 부르지 않는다."""

    name = "off"

    def judge(self, text: str, branch: Branch) -> Judged:
        return Judged(True, "판정 안 함")

    def close(self) -> None:
        pass


class GraphJudge:
    """검수 그래프를 프로세스 안에서 부른다 — DB(마이그레이션 · 적재 · 임베딩)가 서 있어야 한다."""

    name = "graph"

    def __init__(self, reject_only: bool = False) -> None:
        #: 🆕 엔진이 아직 통과를 내지 않는다(인코더 전 판정 — 사전이 침묵하면 늘 보류). 그동안은 **탈락 판정용**으로만 쓴다:
        #:    위반 확정 · 유형 후보가 붙으면 탈락, 유형 없는 보류는 보관. 인코더가 붙으면 `reject_only=False` 로 돌린다
        self.reject_only = reject_only
        if reject_only:
            self.name = "reject"
        sys.path.insert(0, str(ROOT))
        from app import graph as g  # noqa: PLC0415
        from app.db import pg_connect  # noqa: PLC0415

        self._g = g
        self._review = g.build_review()
        self._conn = pg_connect()
        self._cur = self._conn.cursor()

    def judge(self, text: str, branch: Branch) -> Judged:
        from app.contracts import Category, Outcome, ProductContext  # noqa: PLC0415

        product = ProductContext(
            category=Category(branch.category), has_recognized_function=branch.recognized
        )
        state = self._review.invoke(
            {"text": text, "product": product}, config={"configurable": {"conn": self._cur}}
        )
        res = self._g.to_response(state)
        detail = " / ".join(
            f"{s.verdict.value}"
            + (f"({s.hold_reason.value})" if s.hold_reason else "")
            + (f" {[v.value for v in s.violations]}" if s.violations else "")
            for s in res.sentences
        )
        if self.reject_only:
            from app.contracts import Verdict  # noqa: PLC0415

            clean = all(
                not s.violations and s.verdict is not Verdict.unjudged for s in res.sentences
            )
            return Judged(clean, "위반 못 찾음" if clean else res.outcome.value, detail)
        return Judged(res.outcome is Outcome.passed, res.outcome.value, detail)

    def close(self) -> None:
        self._cur.close()
        self._conn.close()
