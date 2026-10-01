"""재판정 — sLLM 이 내놓은 최종 문장을 팀 판정 코어(`/judge` 와 같은 검수 그래프)에 다시 넣는다 (2026-10-01 · D-119).

관문(`stage_gate.py`)은 lse 의 규칙 검사이고, 재판정은 **팀 공식 판정 코어**다 — 사전 매칭 + 법령 근거 검색 + 법별 판정.
그래프를 여기서 새로 짓지 않는다 — `app/graph.py` `build_review` 한 곳을 부른다(D-99). 커서는 `config` 로 넣는다.

🚨 **2026-10-01 판정 코어(W4 1판)의 한계를 그대로 옮긴다 — 지어내지 않는다.**
   - 사전 적중 → 위반 확정(`confirmed`) · 근거 못 세움 → `no_basis` · 그 밖 → 보류(`hold`, 확신 부족 · D-269)
   - **「통과」는 아직 나올 수 없다** — 통과는 확정 ∧ R0 인데 위험도 하한(W5 제재표)이 서명 전이다(D-125 · D-273).
   그래서 재판정 결과는 셋으로만 읽는다:
     `rejected`      — 어느 문장이든 위반 확정 · 근거 없음 → 후보에서 탈락
     `no_violation`  — 위반 확정이 없다(전부 보류) → 후보 유지, **통과 보증은 아니다**
     `passed`        — 판정 코어가 통과를 냈다(코어가 완성되면) → 후보 유지
   팀이 인코더 · 위험도를 붙이면 이 파일을 고치지 않아도 `passed` 가 나오기 시작한다.

DB 가 필요하다(로컬 Docker postgres · `launcher.py db-up`). 없으면 `RejudgeUnavailable` 을 던진다 — 돌지 않은 것을 돈 것처럼
말하지 않는다(D-146).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class RejudgeUnavailable(RuntimeError):
    """DB 나 판정 그래프 의존성이 없어 재판정을 못 돌렸다."""


@dataclass(frozen=True)
class Rejudge:
    status: str  # rejected | no_violation | passed
    outcome: str  # 판정 코어의 종착(hold · certificate · guidance · passed)
    verdicts: tuple[str, ...] = field(default_factory=tuple)
    violations: tuple[str, ...] = field(default_factory=tuple)
    basis: tuple[str, ...] = field(default_factory=tuple)


@cache
def _graph() -> Any:  # noqa: ANN401 — langgraph 컴파일본
    try:
        from app import graph as g  # noqa: PLC0415
    except ImportError as e:
        raise RejudgeUnavailable(f"판정 그래프를 불러오지 못했다: {type(e).__name__}") from e
    return g.build_review()


def rejudge(text: str, product: Any = None) -> Rejudge:  # noqa: ANN401
    """문장(들)을 판정 코어에 넣는다. `product` 는 `app.contracts.ProductContext` — 없으면 미확정(D-72)."""
    import psycopg  # noqa: PLC0415

    from app.contracts import ProductContext, Verdict  # noqa: PLC0415
    from app.db import pg_connect  # noqa: PLC0415

    review = _graph()
    try:
        with pg_connect() as conn, conn.cursor() as cur:
            state = review.invoke({"text": text, "product": product or ProductContext()},
                                  config={"configurable": {"conn": cur}})
    except psycopg.Error as e:
        raise RejudgeUnavailable(f"DB 에 못 붙었다: {type(e).__name__}") from e
    sents = state.get("sentences", [])
    outcome = getattr(state.get("outcome"), "value", str(state.get("outcome")))
    verdicts = tuple(s.verdict.value for s in sents)
    violations = tuple(sorted({v.value for s in sents for v in (s.violations or [])}))
    basis = tuple(sorted({f"{a.law_id}:{a.article}" for s in sents for a in (s.evidence or [])
                          if s.verdict in (Verdict.confirmed, Verdict.no_basis)}))
    if any(s.verdict in (Verdict.confirmed, Verdict.no_basis) for s in sents):
        status = "rejected"
    elif outcome == "passed":
        status = "passed"
    else:
        status = "no_violation"
    return Rejudge(status=status, outcome=outcome, verdicts=verdicts, violations=violations, basis=basis)


if __name__ == "__main__":
    # 손으로: .venv/Scripts/python.exe docs/lse/rejudge.py "문장"
    for t in sys.argv[1:] or ["홍삼은 피로개선에 도움을 줄 수 있습니다", "먹기만 해도 위염이 싹 낫는 양배추즙"]:
        try:
            print(t, "→", rejudge(t))
        except RejudgeUnavailable as e:
            print(t, "→ 재판정 불가:", e)
