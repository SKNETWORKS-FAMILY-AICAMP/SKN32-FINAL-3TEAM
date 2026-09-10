"""app/graph.py — walking skeleton (D-124 · Phase 0 게이트).

  uv run python -m app.graph            # 스텁 한 바퀴를 돌려 방문 순서를 찍는다

🚨 **모델도 판정 로직도 없이 end-to-end 한 바퀴가 돈다** — 그것이 Phase 0 게이트의
   정의(*"문구 하나가 end-to-end 한 바퀴"*)와 정확히 같다 (D-124).

★ D-124 가 검사 항목 셋을 정해 뒀다 —
   ① **라우터 함수는 그래프 없이 단독 테스트한다** → 그래서 이 파일은 langgraph 를
      **모듈 최상단에서 import 하지 않는다.** 라우터는 순수 함수이고, 의존성 없이 돈다.
   ② **스텁 노드로 컴파일해 방문 순서만** 본다 → `run_stub()` 이 langgraph 없이도
      같은 순서를 내므로, 의존성이 붙기 전에도 순서를 고정할 수 있다.
   ③ **리듀서 키를 따로 확인한다** → 잘못된 annotation 이 append 대신 **조용히 덮어쓴다.**
      `sentences` · `timings` · `rejects` 셋이 누적 키다.

🔴 **스텁은 비어 있는 것이지 틀린 것이 아니다.** 각 노드는 자기 자리에 무엇이 올지
   적어 두고 상태를 그대로 넘긴다. ⛔ 그럴듯한 값을 지어 넣으면 그 값이 화면으로 흘러가고,
   진짜가 붙을 때 무엇이 바뀌었는지 아무도 모른다 (D-147 의 그래프 판).
"""

from __future__ import annotations

import operator
import time
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from app.contracts import (
    Infeasibility,
    JudgeResponse,
    Outcome,
    ProductContext,
    SentenceJudgment,
    Timing,
    Verdict,
)

#: D-126 — 총 라운드 K+1=3. `attempt` 는 0-base 이므로 마지막 시도는 2 다
MAX_ATTEMPT = 2


class JudgeState(TypedDict, total=False):
    """상태 스키마 문서 「상태에 반드시 담을 것」이 그대로 이 모양이다.

    🚨 **누적 키에는 반드시 리듀서가 붙는다.** `Annotated[..., operator.add]` 가 없으면
       LangGraph 는 **마지막 노드의 값으로 조용히 덮어쓴다.** 문장이 여럿인데 마지막
       문장만 남는 사고가 여기서 난다 — 오류가 안 나서 발견이 늦다 (D-124 ③).
    """

    # ── 입력 ──────────────────────────────────────────────────────
    text: str
    product: ProductContext
    # ── 분할 ──────────────────────────────────────────────────────
    sents: list[str]
    # ── 판정 누적 🔴 누적 키 ─────────────────────────────────────
    sentences: Annotated[list[SentenceJudgment], operator.add]
    # ── 재생성 루프 (D-126) ──────────────────────────────────────
    #: 0-base. 거부 3종(주장 원장·인용 검증·사후 대조)은 **한 카운터**를 쓴다
    attempt: int
    rejects: Annotated[list[str], operator.add]  # 🔴 누적 키 — 실패 사유
    # ── 종료 ─────────────────────────────────────────────────────
    outcome: Outcome
    # ── 계측 (D-77 · D-43 이 LangSmith 를 배제해 이것이 유일한 경로) 🔴 누적 키 ──
    timings: Annotated[list[Timing], operator.add]


#: 누적 키 목록 — 게이트가 이 셋에 리듀서가 붙어 있는지 본다
REDUCER_KEYS = ("sentences", "rejects", "timings")


# ══════════════════════════════════════════════════════════════════════
#  계측 — 데코레이터 하나 (D-77 ⑥ 「공수는 데코레이터 하나 + 상태 필드 하나다」)
# ══════════════════════════════════════════════════════════════════════


def timed(fn: Callable[[JudgeState], dict[str, Any]]) -> Callable[[JudgeState], dict[str, Any]]:
    """노드 진입·종료 시각을 상태에 적재한다.

    ⛔ 나중에 붙이면 그때까지의 측정치가 없다 — walking skeleton 에서 함께 넣는다.
    """

    def wrapped(state: JudgeState) -> dict[str, Any]:
        t0 = time.perf_counter()
        out = fn(state)
        ms = (time.perf_counter() - t0) * 1000
        out.setdefault("timings", [])
        out["timings"] = [*out["timings"], Timing(node=fn.__name__, ms=ms)]
        return out

    wrapped.__name__ = fn.__name__
    return wrapped


# ══════════════════════════════════════════════════════════════════════
#  스텁 노드 — 자리와 계약만 있고 판정은 없다
# ══════════════════════════════════════════════════════════════════════


@timed
def split(state: JudgeState) -> dict[str, Any]:
    """문장 분할. 🔜 `preprocess/text.py` 의 분할기가 온다."""
    return {"sents": [state["text"]], "attempt": 0}


@timed
def classify(state: JudgeState) -> dict[str, Any]:
    """카테고리 판별. 🚨 사용자에게 묻지 않는다 — 우리가 판별한다 (D-82).

    🔜 `product_fact` 대조 + 분류기. 못 정하면 `hold(cat_unknown)` 으로 간다.
    """
    return {}


@timed
def retrieve(state: JudgeState) -> dict[str, Any]:
    """조문 검색. 🔜 `chunk_embedding` 벡터 검색 + bge-reranker (512 토큰 상한)."""
    return {}


@timed
def judge(state: JudgeState) -> dict[str, Any]:
    """판정. 🔜 룰(사전 536행) + 인코더.

    🚨 스텁은 `unjudged` 를 낸다 — **통과로 집계 금지** (D-127). 비어 있음을 비어 있다고
       말하는 값이고, 그럴듯한 `confirmed` 를 지어내지 않는다.
    """
    return {
        "sentences": [
            SentenceJudgment(sent_id=f"s{i}", text=t, verdict=Verdict.unjudged)
            for i, t in enumerate(state.get("sents", []))
        ]
    }


@timed
def assess_risk(state: JudgeState) -> dict[str, Any]:
    """위험도. 🔜 D-09 래칫 `max(코드 하한, 인코더 예측)`.

    🔴 코드 하한은 `sanction_rule` · `v_risk_lookup` 에서 온다 — **지금 0행이라 스텁이다.**
       ⛔ 하한 없이 최종만 적으면 계약이 거부한다. 그래서 아무것도 적지 않는다.
    """
    return {}


@timed
def certificate(state: JudgeState) -> dict[str, Any]:
    """합법화 불가 증명서 (D-32). **A 자격형 · C 절대형에만** (D-125)."""
    return {"outcome": Outcome.certificate}


@timed
def generate(state: JudgeState) -> dict[str, Any]:
    """대체 문구 생성. 🔜 N=3 (D-34) · 3종 세트 (D-33)."""
    return {"attempt": state.get("attempt", 0) + 1}


@timed
def verify(state: JudgeState) -> dict[str, Any]:
    """거부 3종 — 주장 원장 · 인용 검증 · 사후 대조. **한 카운터를 쓴다** (D-126)."""
    return {}


@timed
def frontier(state: JudgeState) -> dict[str, Any]:
    """리스크–소구력 프론티어 (D-31). 단일 답을 주지 않는다."""
    return {"outcome": Outcome.passed}


@timed
def hold(state: JudgeState) -> dict[str, Any]:
    """전문가 검토 종착 (D-125).

    🔴 **종착에도 노드가 있어야 한다** (2026-09-10 실측). ⛔ 처음에는 라우터가 `hold` 를
       내면 곧장 `END` 로 보냈다. 그랬더니 컴파일본은 `outcome` 이 **None 인 채로 끝났고**,
       같은 입력에서 스텁은 `hold` 를 냈다. 방문 순서는 같은데 결과가 달랐다 —
       라우터 단독 테스트로는 안 잡히는 자리다. D-124 ② 가 「컴파일해서 본다」고 한 이유다.
    """
    return {"outcome": Outcome.hold}


@timed
def search_failed(state: JudgeState) -> dict[str, Any]:
    """표현 탐색 실패 — B 가 K 를 소진했다 (D-125).

    🚨 증명서를 내지 않는다. D-59 가 금지한 「B 를 C 처럼 답하기」다.
    """
    return {"outcome": Outcome.search_failed}


NODES: dict[str, Callable[[JudgeState], dict[str, Any]]] = {
    f.__name__: f
    for f in (
        split,
        classify,
        retrieve,
        judge,
        assess_risk,
        certificate,
        generate,
        verify,
        frontier,
        hold,
        search_failed,
    )
}


# ══════════════════════════════════════════════════════════════════════
#  라우터 — 순수 함수. 🚨 그래프 없이 단독으로 테스트한다 (D-124)
# ══════════════════════════════════════════════════════════════════════


def route_after_judge(state: JudgeState) -> str:
    """판정 직후의 갈림. **A·C 는 루프에 들어가지 않는다** (D-125).

    ⛔ A 자격형을 생성 노드로 보내면 재생성이 같은 위반을 반복한다 — 기획서 2-3
       시나리오 A 가 실제로 그렇게 적혀 있었다 (D-59).
    """
    sents = state.get("sentences", [])
    if not sents:
        return "hold"
    # 🔴 **통과 후보는 전부 `confirmed` 일 때만이다** (D-125).
    #    ⛔ 처음에 `hold` 만 걸러 냈더니, 스텁이 내는 `unjudged` 가 프론티어로 흘러가
    #       종착이 `pass` 로 찍혔다. **미판정을 통과로 집계**한 것이고, 상태 스키마가
    #       「🚨 통과로 집계 금지」라고 적어 둔 바로 그 사고다. 한 바퀴를 돌려 보고 잡혔다.
    #    ★ 보류·근거없음·미판정 셋 다 통과가 아니다. 갈 곳은 전문가 검토다.
    if any(s.verdict is not Verdict.confirmed for s in sents):
        return "hold"
    reasons = {s.infeasibility for s in sents if s.infeasibility}
    if reasons & {Infeasibility.A, Infeasibility.C}:
        return "certificate"
    if Infeasibility.B in reasons:
        return "generate"
    return "frontier"


def route_after_verify(state: JudgeState) -> str:
    """재생성 루프의 갈림 (D-126 · D-125).

    🚨 K 를 소진한 B 는 **증명서가 아니라** 「표현 탐색 실패」다 — D-59 가 금지한
       「B 를 C 처럼 답하기」를 막는 자리가 여기다.
    """
    if not state.get("rejects"):
        return "frontier"
    if state.get("attempt", 0) >= MAX_ATTEMPT:
        return "search_failed"
    return "generate"


ROUTES_AFTER_JUDGE = ("hold", "certificate", "generate", "frontier")
ROUTES_AFTER_VERIFY = ("frontier", "generate", "search_failed")


# ══════════════════════════════════════════════════════════════════════
#  한 바퀴 — langgraph 없이도 같은 순서를 낸다
# ══════════════════════════════════════════════════════════════════════


def run_stub(text: str, product: ProductContext | None = None) -> tuple[JudgeState, list[str]]:
    """스텁 한 바퀴. 상태와 **방문 순서**를 돌려준다.

    🚨 이것이 langgraph 컴파일본과 같은 순서를 내야 한다 (D-124 ②). 의존성이 붙기 전에
       순서를 고정해 두면, 붙인 뒤에 순서가 바뀐 것을 게이트가 잡는다.
    """
    state: JudgeState = {
        "text": text,
        "product": product or ProductContext(),
        "sentences": [],
        "rejects": [],
        "timings": [],
        "attempt": 0,
    }
    visited: list[str] = []

    def step(name: str) -> None:
        visited.append(name)
        out = NODES[name](state)
        for k, v in out.items():
            if k in REDUCER_KEYS:
                state[k] = [*state.get(k, []), *v]  # type: ignore[literal-required]
            else:
                state[k] = v  # type: ignore[literal-required]

    for name in ("split", "classify", "retrieve", "judge", "assess_risk"):
        step(name)

    nxt = route_after_judge(state)
    if nxt != "generate":
        step(nxt)  # hold · certificate · frontier — 전부 노드다
        return state, visited

    while True:  # B 실증형 — 재생성 루프
        step("generate")
        step("verify")
        nxt = route_after_verify(state)
        if nxt != "generate":
            step(nxt)  # frontier · search_failed
            return state, visited


def to_response(state: JudgeState) -> JudgeResponse:
    """상태를 계약으로 옮긴다. 🚨 계약이 거부하면 여기서 터진다 — 화면보다 먼저다."""
    return JudgeResponse(
        outcome=state.get("outcome", Outcome.hold),
        sentences=state.get("sentences", []),
        attempt=state.get("attempt", 0),
        timings=state.get("timings", []),
        law_version="2026-09-10",
        judged_by="stub-0.1.0",
    )


def build_graph():  # noqa: ANN201 — langgraph 타입은 지연 import 라 여기서 못 적는다
    """LangGraph 컴파일본. 🔜 의존성이 붙으면 돈다.

    🚨 **지연 import 다.** langgraph 가 없어도 이 모듈의 나머지(라우터·스텁 한 바퀴)는
       돌아야 한다 — D-124 가 「라우터 함수는 그래프 없이 단독 테스트」라고 정했다.
    """
    # 🔴 **추적이 켜져 있으면 멈춘다** (D-43 · D-72 fail-closed · 2026-09-10).
    #    ⛔ `langgraph` → `langchain-core` → `langsmith` 가 전이 의존이라 패키지를 못 뺀다.
    #       켜지면 광고 문구 원문이 밖으로 나간다 — 온프레미스는 서사가 아니라 제품 요구사항이다.
    #    ⛔ **조용히 끄지 않는다.** `os.environ` 을 덮어쓰면 켠 사람이 자기가 켠 것이
    #       무시된 줄 모른다. 그리고 `app` 을 안 거치는 경로가 남아 「막은 척」이 된다 (D-146).
    #    ★ 여기가 langgraph 를 실제로 쓰는 유일한 자리다. import 부작용이 아니라 함수 실행이라
    #      멈추는 지점이 분명하다.
    from langsmith.utils import tracing_is_enabled  # noqa: PLC0415

    if tracing_is_enabled():
        raise SystemExit(
            "🔴 LangSmith 추적이 켜져 있다 — D-43 이 배제했다.\n"
            "   🚨 켜면 광고 문구 원문이 외부로 나간다.\n"
            "   끄는 법: LANGCHAIN_TRACING_V2 · LANGSMITH_TRACING 을 지우거나 false 로 둔다."
        )

    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    g = StateGraph(JudgeState)
    for name, fn in NODES.items():
        g.add_node(name, fn)
    g.add_edge(START, "split")
    for a, b in (
        ("split", "classify"),
        ("classify", "retrieve"),
        ("retrieve", "judge"),
        ("judge", "assess_risk"),
        ("generate", "verify"),
    ):
        g.add_edge(a, b)
    g.add_conditional_edges(
        "assess_risk",
        route_after_judge,
        {
            "hold": "hold",
            "certificate": "certificate",
            "generate": "generate",
            "frontier": "frontier",
        },
    )
    g.add_conditional_edges(
        "verify",
        route_after_verify,
        {"frontier": "frontier", "generate": "generate", "search_failed": "search_failed"},
    )
    for terminal in ("certificate", "frontier", "hold", "search_failed"):
        g.add_edge(terminal, END)
    return g.compile()


def main() -> int:
    state, visited = run_stub("면역력 강화에 도움을 줍니다.")
    print("방문 순서 —", " → ".join(visited))
    r = to_response(state)
    print(f"종착 {r.outcome.value} · 문장 {len(r.sentences)} · attempt {r.attempt}")
    for t in r.timings:
        print(f"    {t.node:12s} {t.ms:7.3f} ms")
    print("\n🚨 스텁이다 — 판정도 모델도 없다. 한 바퀴가 돈다는 것만 보인다 (D-124).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
