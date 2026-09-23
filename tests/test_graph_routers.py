"""walking skeleton 게이트 (D-124 · Phase 0) — 🔄 2026-09-23 코어 서브그래프 + 진입점 그래프 (D-266 · D-267).

D-124 가 검사 항목 셋을 정해 뒀다 —
  ① **라우터 함수는 그래프 없이 단독 테스트** — langgraph 없이 돈다
  ② **스텁 노드로 컴파일해 방문 순서만** 검증
  ③ **리듀서 키** — 잘못된 annotation 이 append 대신 조용히 덮어쓴다

🚨 ③ 이 이 파일에서 제일 값진 검사다. 리듀서가 빠지면 **오류가 안 난다.** 문장이 여럿인데
   마지막 하나만 남고, 행 수를 세지 않으면 아무도 모른다.
🆕 D-266 · D-267 로 **오류가 안 나는 자리 둘**이 더 생겼다 — 둘 다 2026-09-23 실측으로 확인했다(리눅스 · D-206).
   ④ 서브그래프를 노드로 그대로 끼우면 **부모의 누적 키가 두 번 쌓인다**
   ⑤ 팬아웃(`Send`)이 0개면 **뒤 노드를 건너뛰고 그래프가 끝난다**
"""

from __future__ import annotations

import operator
import typing

import pytest

from app.contracts import (
    Category,
    EvidenceArticle,
    GenerateOutcome,
    HoldReason,
    Infeasibility,
    Outcome,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Timing,
    Verdict,
    Violation,
)
from app.graph import (
    CORE_AFTER_LAWS,
    CORE_BEFORE_LAWS,
    GENERATE_NODES,
    LAW_NODES,
    MAX_ATTEMPT,
    NODES,
    REVIEW_TERMINALS,
    ROUTES_AFTER_REJUDGE,
    ROUTES_REVIEW,
    STATE_REDUCERS,
    LawResult,
    laws_for,
    merge_laws,
    route_after_rejudge,
    route_laws,
    route_review,
    run_generate_stub,
    run_review_stub,
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


def _ok(sid: str = "s1") -> SentenceJudgment:
    """통과 문장 — 🔄 **확정 ∧ R0** (D-273). ⛔ 위반 + R2 는 불가 사유가 없어도 통과가 아니다(전수 재검토 I1)."""
    return SentenceJudgment(
        sent_id=sid,
        text="문구",
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
    )


def _no_reason(sid: str = "s1") -> SentenceJudgment:
    """🆕 2026-09-23 — **계약이 막는 모양**: 확정 위반인데 불가 사유가 없다 (D-273 결정 3).

    ⛔ 계약 검증을 **건너뛰고**(`model_construct`) 만든다 — 라우터가 계약 밖의 값을 받아도 **보류로 떨어지는지**
       (fail-closed · D-72) 보려는 것이다. 계약이 막는다고 라우터의 방어를 지우지 않는다.
    """
    return SentenceJudgment.model_construct(
        sent_id=sid,
        text="문구",
        verdict=Verdict.confirmed,
        hold_reason=None,
        violations=[Violation.거짓_과장],
        infeasibility=None,
        evidence=[법],
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
        evidence_mismatch=False,
        not_claim=False,
        spans=[],
        substantiation=None,
    )


# ══════════════════════════════════════════════════════════════════════
#  ① 라우터 단독 — langgraph 없이 돈다
# ══════════════════════════════════════════════════════════════════════


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
        # 🔄 D-268 — 확정된 실증형은 「지시」다. 종전에는 재생성(`generate`)으로 갔다 (D-265)
        ([_s(Verdict.confirmed, infeas=Infeasibility.B)], "guidance"),
        ([_ok()], "passed"),
        # 🔴 전수 재검토 I1 — 확정이어도 위험도 > 주의 · 위험도 없음은 통과가 아니다 (D-125)
        ([_no_reason()], "hold"),
        ([SentenceJudgment(sent_id="s1", text="문구", verdict=Verdict.confirmed)], "hold"),
        ([_ok("s1"), _no_reason("s2")], "hold"),
        # 우선순위 — 보류 > 증명서 > 지시 > 통과
        ([_s(Verdict.confirmed, infeas=Infeasibility.B), _s(Verdict.hold, sid="s2")], "hold"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.B), _ok("s2")], "guidance"),
    ],
)
def test_검수_종착_갈림(sents: list[SentenceJudgment], want: str) -> None:
    assert route_review({"sentences": sents}) == want  # type: ignore[typeddict-item]


@pytest.mark.gate
def test_A_와_B_가_섞이면_증명서로_간다() -> None:
    """A 가 하나라도 있으면 증명서다 (D-59) — 자격의 문제라 지시로 고칠 수 없다."""
    state = {
        "sentences": [
            _s(Verdict.confirmed, infeas=Infeasibility.B, sid="s1"),
            _s(Verdict.confirmed, infeas=Infeasibility.A, sid="s2"),
        ]
    }
    assert route_review(state) == "certificate"  # type: ignore[arg-type]


@pytest.mark.gate
def test_검수에는_재생성_갈래가_없다() -> None:
    """🔴 D-265 · D-266 — 검수는 문구를 만들지 않는다. 루프 노드가 검수 종착에 섞이면 이 게이트가 잡는다."""
    loop = {
        "assemble",
        "claim_ledger",
        "rejudge",
        "frontier",
        "search_failed",
        "generate",
        "verify",
    }
    assert not (set(ROUTES_REVIEW) & loop), (
        f"🚨 검수 종착에 루프 갈래 — {set(ROUTES_REVIEW) & loop}"
    )
    assert set(ROUTES_REVIEW) == set(REVIEW_TERMINALS)


@pytest.mark.gate
@pytest.mark.parametrize(
    ("rejects", "attempt", "want"),
    [
        ([], 0, "frontier"),
        (["인용 검증"], 0, "assemble"),
        (["인용 검증"], MAX_ATTEMPT - 1, "assemble"),
        (["인용 검증"], MAX_ATTEMPT, "search_failed"),  # 🚨 증명서가 아니다 (D-125)
    ],
)
def test_재생성_루프_갈림(rejects: list[str], attempt: int, want: str) -> None:
    assert route_after_rejudge({"rejects": rejects, "attempt": attempt}) == want  # type: ignore[arg-type]


@pytest.mark.gate
def test_이번_시도가_통과면_앞의_거부가_남아도_프론티어다() -> None:
    """🔴 전수 재검토 I3 — 누적 `rejects` 로 「이번 시도」를 읽으면 한 번 거부된 뒤 통과해도 탐색 실패로 끝난다."""
    state = {"rejects": ["인용 검증"], "rejected": False, "attempt": 1}
    assert route_after_rejudge(state) == "frontier"  # type: ignore[arg-type]
    state = {"rejects": ["인용 검증"], "rejected": True, "attempt": 1}
    assert route_after_rejudge(state) == "assemble"  # type: ignore[arg-type]


@pytest.mark.gate
def test_라우터가_선언한_갈래만_낸다() -> None:
    """⛔ 라우터가 매핑에 없는 문자열을 내면 LangGraph 는 **런타임에** 죽는다."""
    for sents in (
        [],
        [_s(Verdict.hold)],
        [_s(Verdict.confirmed, infeas=Infeasibility.A)],
        [_s(Verdict.confirmed, infeas=Infeasibility.B)],
        [_no_reason()],
        [_ok()],
    ):
        assert route_review({"sentences": sents}) in ROUTES_REVIEW  # type: ignore[arg-type]
    for rej, att in (([], 0), (["x"], 0), (["x"], MAX_ATTEMPT)):
        assert route_after_rejudge({"rejects": rej, "attempt": att}) in ROUTES_AFTER_REJUDGE  # type: ignore[arg-type]


# ── ① 법별 라우팅 (D-267) ────────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize(
    ("category", "want"),
    [
        (None, ("law_ftc", "law_food", "law_cosmetic")),  # 🚨 미확정이면 언제나 전부 (D-229 ⑥)
        (Category.일반상품, ("law_ftc",)),  # 🔄 D-271 — 일반 상품 → 표시광고법만 (D-229 ② 개정)
        (
            Category.전용법_미수록,
            ("law_ftc",),
        ),  # 🆕 D-277 — 우리가 가진 법은 표시광고법뿐 · 통과 금지는 계약이 본다
        (Category.식품, ("law_ftc", "law_food")),
        (Category.건기식, ("law_ftc", "law_food")),
        (Category.화장품, ("law_ftc", "law_cosmetic")),
    ],
)
def test_품목이_법을_고른다(category: Category | None, want: tuple[str, ...]) -> None:
    assert laws_for(category) == want


@pytest.mark.gate
def test_품목을_청크_범주로_넘기는_다리는_W6_전까지_일반으로_보낸다() -> None:
    """🔜 W6 에서 지운다 (D-271 ③). 🔄 W3 — 계약의 새 품목 이름을 청크 필터로 그대로 넘기면 **0건**이 된다.

    ⛔ 청크 값은 정본 B 재생성(0019) 전까지 「일반」이다. 오류 없이 근거가 비는 자리라 게이트로 박는다.
    """
    from app.graph import _chunk_category  # noqa: PLC0415
    from app.settings import DEFAULT_CATEGORY  # noqa: PLC0415

    assert _chunk_category(None) == DEFAULT_CATEGORY
    assert _chunk_category(Category.일반상품) == DEFAULT_CATEGORY
    assert _chunk_category(Category.전용법_미수록) == DEFAULT_CATEGORY
    assert _chunk_category(Category.식품) == "식품"


@pytest.mark.gate
def test_모든_품목에_표시광고법이_들어간다() -> None:
    """🔴 빈 팬아웃이 나올 수 없게 하는 자리다 — 표시광고법은 품목과 무관하게 걸린다 (D-267)."""
    for c in [None, *Category]:
        assert laws_for(c)[0] == "law_ftc", f"🚨 {c} 에 표시광고법이 없다"


@pytest.mark.gate
def test_빈_팬아웃은_멈춘다() -> None:
    """🔴 실측(2026-09-23) — `Send` 가 0개면 LangGraph 는 **뒤 노드를 건너뛰고 오류 없이 끝낸다.**
    그러면 판정 없이 응답이 나간다. 라우터가 먼저 멈춘다 (D-220)."""
    with pytest.raises(RuntimeError, match="적용할 법이 없다"):
        route_laws({})
    with pytest.raises(RuntimeError, match="법별 노드에 없는"):
        route_laws({"laws": ("law_tax",)})


@pytest.mark.gate
@pytest.mark.parametrize(
    ("results", "match"),
    [
        ([LawResult("law_ftc", ("s0",))], "보낸 법과 다르다"),  # 하나가 안 돌아왔다
        (
            [LawResult("law_ftc", ("s0",)), LawResult("law_ftc", ("s0",))],
            "보낸 법과 다르다",
        ),  # 두 번 쌓였다
        ([LawResult("law_ftc", ("s0",)), LawResult("law_food", ())], "문장을 다 보지 않은"),
    ],
)
def test_법별_결과가_어긋나면_모음이_멈춘다(results: list[LawResult], match: str) -> None:
    """🔴 병렬 노드 하나가 빠지거나 두 번 쌓여도 LangGraph 는 오류를 안 낸다 — 모음이 잡는다 (D-267 · D-220)."""
    state = {"laws": ("law_ftc", "law_food"), "sents": ["문구"], "law_results": results}
    with pytest.raises(RuntimeError, match=match):
        merge_laws(state)  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════════
#  ② 방문 순서 — 스텁
# ══════════════════════════════════════════════════════════════════════

CORE_ALL = (*CORE_BEFORE_LAWS, *LAW_NODES, *CORE_AFTER_LAWS)


@pytest.mark.gate
def test_한_바퀴가_돈다() -> None:
    """🚨 Phase 0 게이트의 정의 — 문구 하나가 end-to-end 한 바퀴 (D-124)."""
    state, visited = run_review_stub("면역력 강화에 도움을 줍니다.")
    assert tuple(visited) == (*CORE_ALL, "hold")  # 품목 미확정 → 세 법 전부 → 스텁 판정은 보류
    assert state["outcome"] is Outcome.hold
    to_response(state)  # 계약을 통과한다


@pytest.mark.gate
def test_스텁은_통과를_지어내지_않는다() -> None:
    """🔴 판정이 없는데 `pass` 가 나오면 **미판정을 통과로 집계**한 것이다 (D-127)."""
    state, _ = run_review_stub("아무 문구")
    assert state["outcome"] is not Outcome.passed
    assert all(s.verdict is Verdict.unjudged for s in state["sentences"])


@pytest.mark.gate
def test_노드마다_계측이_남는다() -> None:
    """D-77 ⑥ · D-43 이 LangSmith 를 배제해 이 필드가 유일한 계측 경로다. 🆕 법별로 따로 쌓인다 (D-267)."""
    state, visited = run_review_stub("아무 문구")
    assert [t.node for t in state["timings"]] == visited
    assert {t.node for t in state["timings"]} >= set(LAW_NODES)


@pytest.mark.gate
def test_지시_종착은_계약의_지시를_낸다() -> None:
    """🔄 2026-09-23 (W3) — `Outcome.guidance` 가 섰다 (D-268 · D-274). 종전에는 보류로 끝냈다."""
    assert REVIEW_TERMINALS["guidance"]({})["outcome"] is Outcome.guidance  # type: ignore[arg-type]


@pytest.mark.gate
def test_생성_스텁이_한_바퀴_돈다() -> None:
    """거부가 없으면 한 라운드 뒤 프론티어다. 🔴 **첫 조립이 attempt 0** 이다 (D-126 · 0-base)."""
    state, visited = run_generate_stub()
    assert visited == ["keyword_screen", "assemble", "claim_ledger", "rejudge", "frontier"]
    assert state["attempt"] == 0
    assert state["outcome"] is GenerateOutcome.frontier  # 🔄 D-274 — 생성 종착


def _always_reject():  # noqa: ANN202
    from app.graph import timed

    def claim_ledger(state: dict) -> dict:
        return {"rejected": True, "rejects": ["주장 원장"]}

    return timed(claim_ledger)


@pytest.mark.gate
def test_재생성은_K_더하기_1_라운드에서_멈춘다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 D-126 — 총 라운드 K+1=3 · 최악 sLLM 호출 N×(K+1)=9. ⛔ 종전(검수 안의 루프)에는 원문 판정이
    attempt 0 을 차지해 **조립이 두 번뿐**이었다. 🚨 끝에서 증명서가 아니라 탐색 실패다 (D-125)."""
    monkeypatch.setitem(GENERATE_NODES, "claim_ledger", _always_reject())
    state, visited = run_generate_stub()
    assert visited.count("assemble") == MAX_ATTEMPT + 1
    assert state["attempt"] == MAX_ATTEMPT
    assert visited[-1] == "search_failed"
    assert state["outcome"] is GenerateOutcome.search_failed  # 🔄 D-274 — 생성 종착


# ══════════════════════════════════════════════════════════════════════
#  ③ 리듀서 키 — 상태 넷 (D-266)
# ══════════════════════════════════════════════════════════════════════

_REDUCER_CASES = [(name, key) for name, (_, keys) in STATE_REDUCERS.items() for key in keys]


@pytest.mark.gate
@pytest.mark.parametrize(("state_name", "key"), _REDUCER_CASES)
def test_누적_키에_리듀서가_붙어_있다(state_name: str, key: str) -> None:
    """🚨 **오류가 안 나는 결함이다.** 리듀서가 빠지면 append 대신 조용히 덮어쓴다 (D-124 ③)."""
    cls = STATE_REDUCERS[state_name][0]
    hints = typing.get_type_hints(cls, include_extras=True)
    assert key in hints, f"🚨 {state_name} 에 `{key}` 가 없다"
    assert operator.add in getattr(hints[key], "__metadata__", ()), (
        f"🚨 {state_name}.`{key}` 에 리듀서가 없다 — `Annotated[list[...], operator.add]` 여야 한다.\n"
        "   ⛔ 없으면 LangGraph 가 마지막 노드의 값으로 덮어쓴다. 오류는 안 난다."
    )


@pytest.mark.gate
@pytest.mark.parametrize("state_name", list(STATE_REDUCERS))
def test_리듀서가_붙은_키는_표에_다_있다(state_name: str) -> None:
    """반대 방향 — 표에 안 적은 누적 키가 생기면 위 게이트가 그 키를 안 돈다 (D-99 · D-170)."""
    cls, keys = STATE_REDUCERS[state_name]
    hints = typing.get_type_hints(cls, include_extras=True)
    annotated = {k for k, h in hints.items() if operator.add in getattr(h, "__metadata__", ())}
    assert annotated == set(keys), f"🚨 {state_name} 표와 선언이 다르다 — {annotated ^ set(keys)}"


@pytest.mark.gate
def test_반대_대조_덮어쓰는_칸에는_리듀서가_없다() -> None:
    """위 검사가 **실패할 수 있음**을 보인다 (D-170). `attempt` 는 한 카운터(D-126) · `laws` 는 한 번 정한다."""
    gen = typing.get_type_hints(STATE_REDUCERS["generate"][0], include_extras=True)
    core = typing.get_type_hints(STATE_REDUCERS["core"][0], include_extras=True)
    assert operator.add not in getattr(gen["attempt"], "__metadata__", ())
    assert operator.add not in getattr(core["laws"], "__metadata__", ())


@pytest.mark.gate
def test_검수_상태에_재생성_키가_없다() -> None:
    """🔴 D-266 — `attempt`·`rejects`·`rejected` 는 생성 상태의 것이다. 칸이 있으면 누군가 쓴다."""
    review = typing.get_type_hints(STATE_REDUCERS["review"][0])
    assert not ({"attempt", "rejects", "rejected", "candidates"} & set(review))


@pytest.mark.gate
def test_모든_노드가_상태를_깨지_않는다() -> None:
    """스텁이라도 반환은 dict 여야 하고, 그 상태에 없는 키를 만들면 안 된다."""
    review_keys = set(typing.get_type_hints(STATE_REDUCERS["review"][0]))
    gen_keys = set(typing.get_type_hints(STATE_REDUCERS["generate"][0]))
    base = {
        "text": "문구",
        "sents": ["문구"],
        "sentences": [],
        "laws": ("law_ftc",),
        "law_results": [LawResult("law_ftc", ("s0",))],
    }
    for group in (NODES, REVIEW_TERMINALS):
        for name, fn in group.items():
            out = fn(dict(base))
            assert isinstance(out, dict), f"{name} 이 dict 를 안 냈다"
            assert set(out) <= review_keys, (
                f"🚨 {name} 이 상태에 없는 키 — {set(out) - review_keys}"
            )
    for name, fn in GENERATE_NODES.items():
        out = fn({})
        assert isinstance(out, dict), f"{name} 이 dict 를 안 냈다"
        assert set(out) <= gen_keys, f"🚨 {name} 이 상태에 없는 키 — {set(out) - gen_keys}"


# ══════════════════════════════════════════════════════════════════════
#  ② 컴파일본 — 스텁과 **같은 순서·같은 종착**이어야 한다 (D-124 ②)
# ══════════════════════════════════════════════════════════════════════
#
# 🔴 라우터 단독 테스트로는 안 잡히는 자리가 있다 (2026-09-10 실측) — 라우터가 `hold` 를 내면 곧장 `END` 로
#    보냈더니 컴파일본만 `outcome` 이 None 으로 끝났다. 🆕 D-266 · D-267 로 그런 자리가 둘 더 생겼다(④ ⑤).

from app.graph import build_generate, build_review, timed  # noqa: E402
from app.graph import judge as judge_node  # noqa: E402


def _judge_stub(sents: list[SentenceJudgment]):  # noqa: ANN202
    """🚨 `timed` 를 반드시 두른다 — 안 두르면 그 노드만 계측에서 빠진다."""

    def judge(state: dict) -> dict:
        return {"sentences": list(sents)}

    return timed(judge)


def _init(text: str = "문구", category: Category | None = None) -> dict:
    return {"text": text, "product": ProductContext(category=category), "timings": []}


@pytest.mark.gate
@pytest.mark.parametrize(
    ("sents", "category", "tail"),
    [
        (None, None, "hold"),  # 스텁 판정(unjudged) → 보류
        (None, Category.화장품, "hold"),  # 🆕 법 둘만 — 팬아웃 폭이 달라도 모음은 한 번
        ([_ok()], None, "passed"),
        ([_no_reason()], None, "hold"),  # 🔴 I1 · 🔄 계약이 막는 모양도 보류로 (D-273)
        ([_s(Verdict.confirmed, infeas=Infeasibility.A)], None, "certificate"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.C)], Category.식품, "certificate"),
        ([_s(Verdict.confirmed, infeas=Infeasibility.B)], None, "guidance"),
        ([_s(Verdict.hold)], Category.건기식, "hold"),
    ],
)
def test_컴파일본이_스텁과_같은_길을_간다(
    monkeypatch: pytest.MonkeyPatch,
    sents: list[SentenceJudgment] | None,
    category: Category | None,
    tail: str,
) -> None:
    """🚨 둘이 갈리면 「단독 테스트는 통과하는데 그래프는 다르게 돈다」가 된다."""
    monkeypatch.setitem(NODES, "judge", judge_node if sents is None else _judge_stub(sents))
    state, visited = run_review_stub("문구", ProductContext(category=category))
    out = build_review().invoke(_init(category=category))

    assert [t.node for t in out["timings"]] == visited
    assert visited[-1] == tail
    assert out.get("outcome") == state.get("outcome")
    assert len(out["sentences"]) == len(state["sentences"])
    assert tuple(out["laws"]) == laws_for(category)


@pytest.mark.gate
def test_모든_종착이_outcome_을_적는다() -> None:
    """⛔ 종착에서 `outcome` 을 안 적으면 응답이 None 으로 끝난다 — 계약이 거부한다."""
    for name, fn in REVIEW_TERMINALS.items():
        assert "outcome" in fn({}), f"🚨 검수 종착 `{name}` 이 outcome 을 안 적는다"  # type: ignore[arg-type]
    for name in ("frontier", "search_failed"):
        assert "outcome" in GENERATE_NODES[name]({}), (
            f"🚨 생성 종착 `{name}` 이 outcome 을 안 적는다"
        )  # type: ignore[arg-type]


@pytest.mark.gate
def test_컴파일본에서_문장이_실제로_쌓인다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 리듀서 **실증**이다 (D-124 ③). 선언이 맞아도 실제로 append 하는지는 돌려 봐야 안다."""
    three = [_s(Verdict.confirmed, infeas=Infeasibility.B, sid=f"s{i}") for i in range(3)]
    monkeypatch.setitem(NODES, "judge", _judge_stub(three))
    out = build_review().invoke(_init())
    assert len(out["sentences"]) == 3, "🚨 문장이 덮어써졌다 — `sentences` 리듀서를 본다"
    assert [s.sent_id for s in out["sentences"]] == ["s0", "s1", "s2"]
    assert len(out["timings"]) == len({t.node for t in out["timings"]}) > 1


@pytest.mark.gate
def test_병렬_법_노드의_결과가_다_쌓인다() -> None:
    """🔴 D-267 — 법 노드 셋이 **같은 단계에서 병렬로** 쓴다. 리듀서가 빠지면 하나만 남는다 — 오류는 안 난다."""
    out = build_review().invoke(_init())
    assert sorted(r.law for r in out["law_results"]) == sorted(LAW_NODES)


@pytest.mark.gate
def test_코어를_지나도_누적_키가_두_번_쌓이지_않는다() -> None:
    """🔴 ④ — 실측(2026-09-23 · 리눅스): 서브그래프를 `add_node` 로 그대로 끼우면 부모가 **이미 갖고 있던** 누적 키
    값이 두 번 쌓였다. 그래서 함수 노드가 `CORE_IN` 만 넣고 `CORE_OUT` 만 꺼낸다. 🚨 이 게이트가 Windows 판이다 (D-206)."""
    init = _init()
    init["timings"] = [Timing(node="pre", ms=0.0)]
    out = build_review().invoke(init)
    names = [t.node for t in out["timings"]]
    assert names.count("pre") == 1, f"🚨 부모의 누적 키가 두 번 쌓였다 — {names}"
    _, visited = run_review_stub("문구")
    assert names == ["pre", *visited]


@pytest.mark.gate
def test_법_노드가_빠지면_컴파일본도_멈춘다(monkeypatch: pytest.MonkeyPatch) -> None:
    """병렬 노드 하나가 결과를 안 적어도 LangGraph 는 오류를 안 낸다 — 모음이 멈춘다 (D-220)."""

    def law_food(state: dict) -> dict:
        return {}

    monkeypatch.setitem(NODES, "law_food", timed(law_food))
    with pytest.raises(RuntimeError, match="보낸 법과 다르다"):
        build_review().invoke(_init())


@pytest.mark.gate
def test_그래프_응답이_계약을_통과한다() -> None:
    """🚨 상태를 계약으로 옮기는 자리에서 터져야 한다 — 화면보다 먼저다."""
    out = build_review().invoke(_init("면역력 강화에 도움을 줍니다."))
    r = to_response(out)  # type: ignore[arg-type]
    assert r.outcome is Outcome.hold
    assert r.attempt == 0  # D-265 — 검수에서는 늘 0
    assert r.timings


@pytest.mark.gate
@pytest.mark.parametrize("reject", [False, True])
def test_생성_컴파일본이_스텁과_같은_길을_간다(
    monkeypatch: pytest.MonkeyPatch, reject: bool
) -> None:
    if reject:
        monkeypatch.setitem(GENERATE_NODES, "claim_ledger", _always_reject())
    state, visited = run_generate_stub()
    out = build_generate().invoke({"timings": []})
    assert [t.node for t in out["timings"]] == visited
    assert out["outcome"] == state["outcome"]
    assert out["attempt"] == state["attempt"]


# ══════════════════════════════════════════════════════════════════════
#  retrieve → judge 배선 (2026-09-14 · 구현계획 §2-1 C) — 🔄 코어 안에서
# ══════════════════════════════════════════════════════════════════════


def _hit(**kw: object) -> object:
    """`Hit` 한 줄. 🔴 **칸이 늘면 여기도 고친다** — `tests/test_retrieve.py::_hit` 와 짝이다.

    ⛔ 공장이 두 곳인 이유는 만드는 모양이 다르기 때문이다 — 저쪽은 **빈 줄**, 이쪽은 **인용이 서는 줄**이다 (D-99 의 예외).
    """
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
        annex_no=None,
        doc_title=None,
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
    """문장 셋으로 갈라 주는 스텁. 🚨 `timed` 를 두른다."""

    def split(state: dict) -> dict:
        return {"sents": list(sents)}

    return timed(split)


@pytest.mark.gate
def test_retrieve_가_config_를_받는_모양으로_보인다() -> None:
    """🔴 **LangGraph 는 노드의 시그니처를 보고 `config` 를 넘긴다** (2026-09-14 실측).

    🚨 **주석을 달면 안 온다** — `RunnableConfig`(런타임 해석)만 통과하고 `Any`·`dict | None` 은 config 가 안 온다.
       런타임 해석을 쓰려면 langchain_core 를 모듈 최상단에서 import 해야 하는데 그것이 D-124 ①을 깬다.
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
    state, _ = run_review_stub("면역력 강화에 도움을 줍니다.")
    ev = state["evidence"]
    assert len(ev) == len(state["sents"]), "🚨 문장마다 한 벌이어야 한다"
    assert not ev[0].vector and not ev[0].lexical, "🚨 안 돌았으면 False 다"
    assert ev[0].articles == (), "🚨 근거를 지어냈다"
    assert state["outcome"] is Outcome.hold, "🚨 근거 없이 통과로 집계됐다 (D-127)"


@pytest.mark.gate
def test_커서가_코어_안까지_가서_문장마다_근거가_쌓인다(monkeypatch: pytest.MonkeyPatch) -> None:
    """✅ 구현계획 §2-1 C 의 완료 판정 — 🔄 D-266: 커서가 **검수 → 코어 함수 노드 → `retrieve`** 까지 간다.

    🔴 **짝짓기가 어긋나도 오류가 안 난다** — `judge` 가 빈 근거를 낼 뿐이다. 그래서 실제로 붙는지 본다.
    🆕 법별 노드도 문장 셋을 다 봤는지 모음이 대조한다 (D-267).
    """
    from app import retrieve as rt

    monkeypatch.setattr(rt, "search", _fake_search([_hit()]))
    monkeypatch.setitem(NODES, "split", _split_stub(["가나다", "라마바", "사아자"]))
    out = build_review().invoke(_init(), config={"configurable": {"conn": "CUR"}})
    assert [e.sent_id for e in out["evidence"]] == ["s0", "s1", "s2"]
    assert [s.sent_id for s in out["sentences"]] == ["s0", "s1", "s2"]
    assert all(len(s.evidence) == 1 for s in out["sentences"]), "🚨 judge 가 근거를 못 붙였다"
    assert out["sentences"][0].evidence[0].article == "제8조제1항제1호"
    assert all(r.sent_ids == ("s0", "s1", "s2") for r in out["law_results"])
    assert any(t.node == "retrieve" for t in out["timings"])


@pytest.mark.gate
def test_좌표를_못_세운_근거는_안_나간다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 `citation` 이 `None` 이면 **버린다** (D-224). ⛔ 틀린 인용은 없는 인용보다 나쁘다."""
    from app import retrieve as rt

    monkeypatch.setattr(
        rt, "search", _fake_search([_hit(), _hit(chunk_id="annex", doc_type="별표", citation=None)])
    )
    out = build_review().invoke(_init(), config={"configurable": {"conn": "CUR"}})
    assert len(out["evidence"][0].articles) == 1, "🚨 좌표 없는 근거가 나갔다"
    assert out["evidence"][0].articles[0].chunk_id == "c0", "🚨 조각 여부가 따라가야 한다 (D-199)"
