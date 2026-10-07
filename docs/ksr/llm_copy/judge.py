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
#: 판정 인코더 — 10-07 에 받은 v10(합성O · 이유O · 8종). `models/` 는 git 이 무시한다
ENCODER_DIR = ROOT / "models" / "copylane-encoder-kcbert-v10-합성O-이유O"


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


class EncoderJudge:
    """판정 인코더(KC-BERT)를 판정 단계에 붙인다 — 유형 후보가 하나라도 문턱을 넘으면 탈락.

    검수 그래프는 아직 인코더를 부르지 않는다(`rule-0.3.0-dict`). 그래서 여기서 `app.encoder` 를 직접 부른다.
    `inner`(사전 엔진)를 먼저 돌리고, 거기서 안 걸린 것만 인코더에 넣는다.
    🚨 「통과」는 여전히 「위반을 못 찾았다」다 — 인코더는 후보 신호만 내고 확정 · 위험도는 정하지 않는다.
    """

    def __init__(self, inner: NoJudge | GraphJudge, model_dir: pathlib.Path = ENCODER_DIR) -> None:
        sys.path.insert(0, str(ROOT))
        from app.encoder import JudgeEncoder  # noqa: PLC0415

        self._inner = inner
        self._enc = JudgeEncoder(model_dir)
        self.name = "encoder" if isinstance(inner, GraphJudge) else "encoder-only"

    def judge(self, text: str, branch: Branch) -> Judged:
        j = self._inner.judge(text, branch)
        if not j.passed:
            return j
        cands = self._enc.predict(text).candidates
        if cands:
            detail = " / ".join(
                f"{c.violation.value} {c.confidence:.2f}≥{c.threshold}" for c in cands
            )
            return Judged(False, "인코더 유형 후보", detail)
        return Judged(True, "위반 못 찾음", j.detail)

    def close(self) -> None:
        self._inner.close()
