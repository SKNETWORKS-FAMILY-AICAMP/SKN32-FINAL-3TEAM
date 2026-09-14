"""walking skeleton 게이트 (D-124 · Phase 0).

D-124 가 검사 항목 셋을 정해 뒀다 —
  ① **라우터 함수는 그래프 없이 단독 테스트** — langgraph 없이 돈다
  ② **스텁 노드로 컴파일해 방문 순서만** 검증
  ③ **리듀서 키** — 잘못된 annotation 이 append 대신 조용히 덮어쓴다

🚨 ③ 이 이 파일에서 제일 값진 검사다. 리듀서가 빠지면 **오류가 안 난다.** 문장이 여럿인데
   마지막 하나만 남고, 행 수를 세지 않으면 아무도 모른다.
"""

from __future__ import annotations

import operator
import typing

import pytest

from app.contracts import (
    EvidenceArticle,
    HoldReason,
    Infeasibility,
    Outcome,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Verdict,
    Violation,
)
from app.graph import (
    MAX_ATTEMPT,
    NODES,
    REDUCER_KEYS,
    ROUTES_AFTER_JUDGE,
    ROUTES_AFTER_VERIFY,
    JudgeState,
    route_after_judge,
    route_after_verify,
    run_stub,
    to_response,
)

법 = EvidenceArticle(law_id="013094", article="제8조", item="제1항제1호")


def _s(
    verdict: Verdict, *, infeas: Infeasibility | None = None, sid: str = "s1"
) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=sid,
        text="문구",
        verdict=verdict,
        hold_reason=HoldReason.low_conf if verdict is Verdict.hold else None,
        violations=[Violation.거짓_과장] if verdict is Verdict.confirmed else [],
        evidence=[법] if verdict is Verdict.confirmed else [],
        infeasibility=infeas,
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
    )


# ── ① 라우터 단독 ────────────────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize(
    ("sents", "want"),
    [
        ([], "hold"),
        ([_s(Verdict.hold)], "hold"),
        ([_s(Verdict.unjudged)], "hold"),  # 🚨 미판정은 통과가 아니다 (D-127)
        ([_s(Verdict.no_basis)], "hold"),  # 🚨 근거없음도 통과가 아니다
        ([_s(Verdict.confirmed, infeas=Infeasibility.A)], "certificate"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.C)], "certificate"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.B)], "generate"),
        ([_s(Verdict.confirmed)], "frontier"),
    ],
)
def test_판정_직후_갈림(sents: list[SentenceJudgment], want: str) -> None:
    assert route_after_judge({"sentences": sents}) == want  # type: ignore[typeddict-item]


@pytest.mark.gate
def test_A_와_B_가_섞이면_증명서로_간다() -> None:
    """A 가 하나라도 있으면 루프에 넣지 않는다 (D-59) — 재생성이 같은 위반을 반복한다."""
    state = {
        "sentences": [
            _s(Verdict.confirmed, infeas=Infeasibility.B, sid="s1"),
            _s(Verdict.confirmed, infeas=Infeasibility.A, sid="s2"),
        ]
    }
    assert route_after_judge(state) == "certificate"  # type: ignore[arg-type]


@pytest.mark.gate
@pytest.mark.parametrize(
    ("rejects", "attempt", "want"),
    [
        ([], 0, "frontier"),
        (["인용 검증"], 0, "generate"),
        (["인용 검증"], MAX_ATTEMPT - 1, "generate"),
        (["인용 검증"], MAX_ATTEMPT, "search_failed"),  # 🚨 증명서가 아니다 (D-125)
    ],
)
def test_재생성_루프_갈림(rejects: list[str], attempt: int, want: str) -> None:
    assert route_after_verify({"rejects": rejects, "attempt": attempt}) == want  # type: ignore[arg-type]


@pytest.mark.gate
def test_라우터가_선언한_갈래만_낸다() -> None:
    """⛔ 라우터가 매핑에 없는 문자열을 내면 LangGraph 는 **런타임에** 죽는다."""
    for sents in (
        [],
        [_s(Verdict.hold)],
        [_s(Verdict.confirmed, infeas=Infeasibility.A)],
        [_s(Verdict.confirmed, infeas=Infeasibility.B)],
        [_s(Verdict.confirmed)],
    ):
        assert route_after_judge({"sentences": sents}) in ROUTES_AFTER_JUDGE  # type: ignore[arg-type]
    for rej, att in (([], 0), (["x"], 0), (["x"], MAX_ATTEMPT)):
        assert route_after_verify({"rejects": rej, "attempt": att}) in ROUTES_AFTER_VERIFY  # type: ignore[arg-type]


# ── ② 방문 순서 ──────────────────────────────────────────────────────


@pytest.mark.gate
def test_한_바퀴가_돈다() -> None:
    """🚨 Phase 0 게이트의 정의 — 문구 하나가 end-to-end 한 바퀴 (D-124)."""
    state, visited = run_stub("면역력 강화에 도움을 줍니다.")
    assert visited[:5] == ["split", "classify", "retrieve", "judge", "assess_risk"]
    assert state["outcome"] is Outcome.hold  # 스텁 판정은 unjudged 라 보류다
    to_response(state)  # 계약을 통과한다


@pytest.mark.gate
def test_스텁은_통과를_지어내지_않는다() -> None:
    """🔴 판정이 없는데 `pass` 가 나오면 **미판정을 통과로 집계**한 것이다 (D-127).

    ⛔ 실제로 처음 배선했을 때 그렇게 나왔다. 종착이 `pass` 였고 문장은 `unjudged` 였다.
    """
    state, _ = run_stub("아무 문구")
    assert state["outcome"] is not Outcome.passed
    assert all(s.verdict is Verdict.unjudged for s in state["sentences"])


@pytest.mark.gate
def test_노드마다_계측이_남는다() -> None:
    """D-77 ⑥ · D-43 이 LangSmith 를 배제해 이 필드가 유일한 계측 경로다."""
    state, visited = run_stub("아무 문구")
    assert [t.node for t in state["timings"]] == visited


# ── ③ 리듀서 키 ──────────────────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize("key", REDUCER_KEYS)
def test_누적_키에_리듀서가_붙어_있다(key: str) -> None:
    """🚨 **오류가 안 나는 결함이다.** 리듀서가 빠지면 append 대신 조용히 덮어쓴다.

    문장이 여럿인데 마지막 하나만 남고, 행 수를 세지 않으면 아무도 모른다 (D-124 ③).
    """
    hints = typing.get_type_hints(JudgeState, include_extras=True)
    meta = getattr(hints[key], "__metadata__", ())
    assert operator.add in meta, (
        f"🚨 `{key}` 에 리듀서가 없다 — `Annotated[list[...], operator.add]` 여야 한다.\n"
        "   ⛔ 없으면 LangGraph 가 마지막 노드의 값으로 덮어쓴다. 오류는 안 난다."
    )


@pytest.mark.gate
def test_반대_대조_리듀서가_없으면_잡힌다() -> None:
    """위 검사가 **실패할 수 있음**을 보인다 (D-170)."""
    hints = typing.get_type_hints(JudgeState, include_extras=True)
    assert operator.add not in getattr(hints["attempt"], "__metadata__", ()), (
        "🚨 `attempt` 는 누적 키가 아니다 — 거부 3종이 **한 카운터**를 쓴다 (D-126)"
    )


@pytest.mark.gate
def test_누적_키가_실제로_쌓인다() -> None:
    """선언만 보지 않고 한 바퀴 돌려서 확인한다."""
    state, visited = run_stub("문구")
    assert len(state["timings"]) == len(visited) > 1


# ── 노드 계약 ────────────────────────────────────────────────────────


@pytest.mark.gate
def test_모든_노드가_상태를_깨지_않는다() -> None:
    """스텁이라도 반환은 dict 여야 하고, 없는 키를 만들면 안 된다."""
    base: JudgeState = {"text": "문구", "sents": ["문구"], "sentences": [], "attempt": 0}
    allowed = set(typing.get_type_hints(JudgeState, include_extras=True))
    for name, fn in NODES.items():
        out = fn(dict(base))  # type: ignore[arg-type]
        assert isinstance(out, dict), f"{name} 이 dict 를 안 냈다"
        assert set(out) <= allowed, f"🚨 {name} 이 상태에 없는 키를 낸다 — {set(out) - allowed}"


# ══════════════════════════════════════════════════════════════════════
#  ② 컴파일본 — 스텁과 **같은 순서·같은 종착**이어야 한다 (D-124 ②)
# ══════════════════════════════════════════════════════════════════════
#
# 🔴 **라우터 단독 테스트로는 안 잡히는 자리가 있다** (2026-09-10 실측).
#    ⛔ 처음 배선에서 라우터가 `hold` 를 내면 곧장 `END` 로 보냈다. 라우터 테스트는
#       전부 통과했고 방문 순서도 같았는데, 컴파일본만 `outcome` 이 **None 인 채로**
#       끝났다. 스텁은 `hold` 를 냈다 — **같은 입력, 다른 결과.**
#    ★ 그래서 D-124 는 「컴파일해서 방문 순서를 본다」를 따로 적어 뒀다.

from app.graph import build_graph, timed  # noqa: E402
from app.graph import judge as judge_node  # noqa: E402


def _judge_stub(sents: list[SentenceJudgment]):  # noqa: ANN202
    """🚨 `timed` 를 반드시 두른다 — 안 두르면 그 노드만 계측에서 빠지고,
    「그래프가 judge 를 안 밟았다」로 잘못 읽힌다 (실제로 처음에 그렇게 실패했다)."""

    def node(state: JudgeState) -> dict:
        return {"sentences": list(sents)}

    node.__name__ = "judge"
    return timed(node)


def _init(text: str = "문구") -> JudgeState:
    from app.contracts import ProductContext

    return {
        "text": text,
        "product": ProductContext(),
        "sentences": [],
        "rejects": [],
        "timings": [],
        "attempt": 0,
    }


@pytest.mark.gate
@pytest.mark.parametrize(
    ("sents", "tail"),
    [
        (None, "hold"),  # 스텁 판정(unjudged) → 보류
        ([_s(Verdict.confirmed)], "frontier"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.A)], "certificate"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.C)], "certificate"),
        ([_s(Verdict.hold)], "hold"),
    ],
)
def test_컴파일본이_스텁과_같은_길을_간다(
    monkeypatch: pytest.MonkeyPatch, sents: list[SentenceJudgment] | None, tail: str
) -> None:
    """🚨 둘이 갈리면 「단독 테스트는 통과하는데 그래프는 다르게 돈다」가 된다."""
    node = judge_node if sents is None else _judge_stub(sents)
    monkeypatch.setitem(NODES, "judge", node)

    state, visited = run_stub("문구")
    out = build_graph().invoke(_init())

    assert [t.node for t in out["timings"]] == visited
    assert visited[-1] == tail
    assert out.get("outcome") == state.get("outcome")
    assert len(out["sentences"]) == len(state["sentences"])


@pytest.mark.gate
def test_모든_종착이_outcome_을_적는다() -> None:
    """⛔ 종착에서 `outcome` 을 안 적으면 응답이 None 으로 끝난다 — 계약이 거부한다."""
    for name in ("certificate", "frontier", "hold", "search_failed"):
        assert "outcome" in NODES[name]({}), f"🚨 종착 노드 `{name}` 이 outcome 을 안 적는다"  # type: ignore[arg-type]


@pytest.mark.gate
def test_컴파일본에서_문장이_실제로_쌓인다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 리듀서 **실증**이다 (D-124 ③).

    선언(`Annotated[..., operator.add]`)이 맞아도 LangGraph 가 실제로 append 하는지는
    돌려 봐야 안다. ⛔ 덮어쓰면 문장 셋이 하나가 되고 **오류는 안 난다.**
    """
    three = [_s(Verdict.confirmed, sid=f"s{i}") for i in range(3)]
    monkeypatch.setitem(NODES, "judge", _judge_stub(three))
    out = build_graph().invoke(_init())
    assert len(out["sentences"]) == 3, "🚨 문장이 덮어써졌다 — `sentences` 리듀서를 본다"
    assert [s.sent_id for s in out["sentences"]] == ["s0", "s1", "s2"]
    # 계측도 누적 키다 — 노드 수만큼 쌓여야 한다
    assert len(out["timings"]) == len({t.node for t in out["timings"]}) > 1


@pytest.mark.gate
def test_그래프_응답이_계약을_통과한다() -> None:
    """🚨 상태를 계약으로 옮기는 자리에서 터져야 한다 — 화면보다 먼저다."""
    out = build_graph().invoke(_init("면역력 강화에 도움을 줍니다."))
    r = to_response(out)  # type: ignore[arg-type]
    assert r.outcome is Outcome.hold
    assert r.timings


# ══════════════════════════════════════════════════════════════════════
#  retrieve → judge 배선 (2026-09-14 · 구현계획 §2-1 C)
# ══════════════════════════════════════════════════════════════════════


def _hit(**kw: object) -> object:
    from app import retrieve as rt

    d = dict(
        chunk_id="c0",
        law_id="013094",
        article="제8조",
        paragraph=None,
        item="1.",
        paragraph_no=1,
        context="",
        part_no=1,
        part_total=3,
        doc_type="법령",
        category=["일반"],
        text="…",
        attribution=None,
        source_url=None,
        match=rt.MATCH_FUSED,
        citation="제8조제1항제1호",
    )
    d.update(kw)
    return rt.Hit(**d)  # type: ignore[arg-type]


def _fake_search(hits: list[object], **state_kw: object):  # noqa: ANN202
    from app import retrieve as rt

    def inner(cur, q, category=rt.DEFAULT_CATEGORY, limit=None, pool=None):  # noqa: ANN001, ANN202
        st = dict(
            vector=rt.VECTOR_OK, lexical=rt.LEXICAL_OK, pool=50, pool_vector=1, pool_lexical=1
        )
        st.update(state_kw)
        return hits, rt.SearchState(**st)  # type: ignore[arg-type]

    return inner


def _split_stub(sents: list[str]):  # noqa: ANN202
    """문장 셋으로 갈라 주는 스텁. 🚨 `timed` 를 두른다 — `_judge_stub` 과 같은 이유다."""

    def node(state: JudgeState) -> dict:
        return {"sents": list(sents), "attempt": 0}

    node.__name__ = "split"
    return timed(node)


@pytest.mark.gate
def test_retrieve_가_config_를_받는_모양으로_보인다() -> None:
    """🔴 **LangGraph 는 노드의 시그니처를 보고 `config` 를 넘긴다** (2026-09-14 실측).

    ⛔ `timed` 가 `functools.wraps` 를 놓치면 밖에서 보이는 모양이 `(state, *rest, **kw)` 가
       되고 **커서가 조용히 사라진다.** 오류는 안 난다 — 「DB 없음」 경로로 떨어지고
       근거 없는 응답이 그럴듯하게 나온다. 실제로 한 번 그렇게 만들었다가 잡았다.
    🚨 **주석을 달면 안 온다** — 실측: `RunnableConfig`(런타임 해석)만 통과하고
       `Any`·`dict | None` 은 **config 가 안 온다.** 런타임 해석을 쓰려면 langchain_core 를
       모듈 최상단에서 import 해야 하는데 그것이 D-124 ①(의존성 없이 도는 라우터)을 깬다.
       그래서 **주석 없는 `config`** 가 답이다. 이 단언이 그 선택을 고정한다.
    """
    import inspect

    params = inspect.signature(NODES["retrieve"]).parameters
    assert "config" in params, "🚨 `config` 가 시그니처에서 사라졌다 — functools.wraps 를 본다"
    assert params["config"].annotation is inspect.Parameter.empty, (
        "🚨 `config` 에 주석이 붙었다 — 실측상 `Any`·`dict` 는 config 를 못 받는다 (2026-09-14)"
    )


@pytest.mark.gate
def test_커서가_없으면_근거를_지어내지_않는다() -> None:
    """🔴 DB 없이도 돈다 (D-124). 그렇다고 **빈 dict 로 삼키지 않는다** (D-220 fail-closed)."""
    state, _ = run_stub("면역력 강화에 도움을 줍니다.")
    ev = state["evidence"]
    assert len(ev) == len(state["sents"]), "🚨 문장마다 한 벌이어야 한다"
    assert not ev[0].vector and not ev[0].lexical, "🚨 안 돌았으면 False 다"
    assert ev[0].articles == (), "🚨 근거를 지어냈다"
    assert state["outcome"] is Outcome.hold, "🚨 근거 없이 통과로 집계됐다 (D-127)"


@pytest.mark.gate
def test_커서가_오면_문장마다_근거가_쌓이고_judge_가_짝짓는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """✅ 구현계획 §2-1 C 의 완료 판정 — `evidence` 가 `len(sents)` 개 · `timings` 에 `retrieve`.

    🔴 **짝짓기가 어긋나도 오류가 안 난다** — `judge` 가 빈 근거를 낼 뿐이다. 그래서
       `sent_id` 규칙을 한 곳(`graph.sent_id`)에 두고, 여기서 **실제로 붙는지** 본다.
    """
    from app import retrieve as rt

    monkeypatch.setattr(rt, "search", _fake_search([_hit()]))
    monkeypatch.setitem(NODES, "split", _split_stub(["가나다", "라마바", "사아자"]))
    out = build_graph().invoke(_init(), config={"configurable": {"conn": "CUR"}})
    assert [e.sent_id for e in out["evidence"]] == ["s0", "s1", "s2"]
    assert [s.sent_id for s in out["sentences"]] == ["s0", "s1", "s2"]
    assert all(len(s.evidence) == 1 for s in out["sentences"]), "🚨 judge 가 근거를 못 붙였다"
    assert out["sentences"][0].evidence[0].article == "제8조제1항제1호"
    assert any(t.node == "retrieve" for t in out["timings"])


@pytest.mark.gate
def test_좌표를_못_세운_근거는_안_나간다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 `citation` 이 `None` 이면 **버린다** (D-100). 별표는 계층 표기가 달라 조립이 안 된다.

    ⛔ 「제18조」로 줄여 적으면 실은 제3항인 근거를 제1항처럼 읽게 만든다 —
       **틀린 인용은 없는 인용보다 나쁘다.**
    """
    from app import retrieve as rt

    monkeypatch.setattr(
        rt, "search", _fake_search([_hit(), _hit(chunk_id="annex", doc_type="별표", citation=None)])
    )
    out = build_graph().invoke(_init(), config={"configurable": {"conn": "CUR"}})
    assert len(out["evidence"][0].articles) == 1, "🚨 좌표 없는 근거가 나갔다"
    assert out["evidence"][0].articles[0].chunk_id == "c0", "🚨 조각 여부가 따라가야 한다 (D-199)"
