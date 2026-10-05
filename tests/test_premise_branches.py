"""품목 분기 — 전제마다 판정을 내고 기록을 가장 보수적인 쪽으로 맞춘다 (🆕 2026-10-05 · D-319 · D-229 ⑥ · D-263 · D-267 · D-276).

지키는 것
  ① 품목을 모르면 **모든 전제에서 같은 위반이 설 때만 확정**이다 — 한 전제라도 판정하지 못하면 보류(`cat_unknown`) + 분기 (D-319 ①)
  ② 보류에도 유형 · 가장 보수적인 위험도가 실리고 응답이 계약을 지난다 (`_recorded_is_conservative` · `_branch_hold_has_branches`)
  ③ 전제가 유형을 바꾸는 자리 — 건강기능식품 전제의 3호 · 4.나 · 질병 표방의 목 (D-319 ④′)
  ⑤ 판정하지 못하는 전제는 **보류**다 — 3호가 서지 않는 것을 통과로, 남은 적중만으로 확정으로 내지 않는다 (D-319 ④′ · D-220)
  ⑥ 품목이 주어졌고 전제가 판정을 바꾸지 않으면 분기를 내지 않는다
  ④ 기준 문안이 확정되지 않았거나 DB 가 없으면 **분기를 내지 않는다** — 초안 문안 · 지어낸 위험도로 응답을 내지 않는다 (D-147 · D-220)
"""

from __future__ import annotations

import pytest

from app import premise as pm
from app.contracts import (
    Category,
    HoldReason,
    Infeasibility,
    Outcome,
    Premise,
    ProductContext,
    Risk,
    Verdict,
    Violation,
)
from app.graph import (
    CORE_AFTER_LAWS,
    CORE_OUT,
    LAW_NODES,
    DictHit,
    DictScan,
    LawResult,
    assess_risk,
    judge,
    premise_branches,
    to_response,
    upsert_sentences,
)
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

FOOD1 = "013094:제8조제1항제1호"
FOOD1_NA = "013094:제8조제1항제1호|나목"
FOOD3 = "013094:제8조제1항제3호"
FOOD4 = "013094:제8조제1항제4호"
FAIR1 = "002011:제3조제1항제1호"
TEXT = "낱말이 든 문장입니다."


class _Cur:
    """`v_risk_lookup` 대역 — `tests/test_risk_floor.py` 의 것과 같은 모양이다(서명된 원천의 행)."""

    def __init__(self) -> None:
        spec = sr.load_rules()
        assert sr.signature(spec) is not None, "원천이 서명 전이다 — 이 게이트의 전제가 깨진다"
        self.rows = sr.rule_rows(spec)

    def execute(self, sql: str, params: object = None) -> None:
        assert "v_risk_lookup" in sql

    def fetchall(self) -> list[tuple]:
        return [
            (r["id"], r["law_id"], r["type"], r["kind"], r.get("annex1"), r.get("cover"), r["quote"], r.get("fact"))
            for r in self.rows
        ]  # fmt: skip


def _hit(*basis: str) -> DictHit:
    return DictHit(term="낱말", violation_type=None, basis=basis, span=(0, 2))


def _run(by_law: dict[str, list[DictHit]], category: Category | None = None) -> tuple[dict, dict]:
    """문장 하나 · 법별 적중으로 `judge` → `assess_risk` → `premise_branches` 를 실제로 돌린다. `(상태, 분기 노드가 낸 것)`."""
    laws = LAW_NODES if category is None else tuple(by_law) or ("law_ftc",)
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": ProductContext(category=category),
        "laws": laws,
        "dict_scans": [
            DictScan(sent_id="s0", ran=True, hits=tuple(h for hs in by_law.values() for h in hs))
        ],
        "law_results": [
            LawResult(law=law, sent_ids=("s0",), dict_hits=(("s0", tuple(by_law.get(law, ()))),))
            for law in laws
        ],
    }
    cfg = {"configurable": {"conn": _Cur()}}
    st["sentences"] = judge(st)["sentences"]
    st["sentences"] = upsert_sentences(st["sentences"], assess_risk(st, cfg).get("sentences", []))
    out = premise_branches(st, cfg)
    st["sentences"] = upsert_sentences(st["sentences"], out.get("sentences", []))
    st["branches"] = out.get("branches", [])
    return st, out


@pytest.fixture
def criteria(monkeypatch: pytest.MonkeyPatch) -> None:
    """기준 문안이 전부 확정된 상태 — 🚨 시험용 글자다. 실제 표(`pm.CRITERIA`)는 승인된 줄만 든다."""
    monkeypatch.setattr(pm, "CRITERIA", {p: f"(시험) {p.value} 기준" for p in Premise})


def _quiet(out: dict) -> bool:
    """분기 노드가 아무것도 안 냈는가 — 계측(`timings`)은 늘 붙는다."""
    return "branches" not in out and "sentences" not in out


def _branch(st: dict, premise: Premise):  # noqa: ANN202
    return next(b for b in st["branches"] if b.premise is premise)


def test_분기_노드가_코어_순서와_출력에_들어_있다() -> None:
    assert "premise_branches" in CORE_AFTER_LAWS, "분기 노드가 코어 순서에 없다 (D-319)"
    assert CORE_AFTER_LAWS.index("assess_risk") < CORE_AFTER_LAWS.index("premise_branches"), (
        "분기는 위험도 뒤에 선다 — 같은 문장을 바꿔 끼운다"
    )
    assert "branches" in CORE_OUT, (
        "🚨 `branches` 가 코어 출력에 없으면 검수 그래프가 분기를 못 받는다 (오류 없이 빈 목록)"
    )


def test_기준_문안이_확정되지_않으면_분기를_내지_않는다() -> None:
    assert pm.CRITERIA == {} or all(pm.CRITERIA.values()), "빈 문안이 표에 있다"
    st, out = _run({"law_food": [_hit(FOOD4)]})
    if not pm.criteria_ready(pm.PREMISES_OF[None]):
        assert _quiet(out), (
            "🚨 문안이 비었는데 분기 노드가 무언가 냈다 — 초안 · 빈 문안으로 응답을 내지 않는다 (D-147 · D-220)"
        )
        assert st["sentences"][0].verdict is Verdict.confirmed, "문안 전에는 종전 판정 그대로다"


def test_DB_가_없으면_분기를_내지_않는다(criteria: None) -> None:
    st, _ = _run({"law_food": [_hit(FOOD4)]})
    assert _quiet(premise_branches({**st, "branches": []}, None)), (
        "🚨 하한을 못 읽는데 분기를 냈다 — 위험도를 지어내지 않는다 (D-09)"
    )


def test_품목을_모르고_식품법으로만_걸리면_보류와_분기다(criteria: None) -> None:
    st, _ = _run({"law_food": [_hit(FOOD4)]})
    s = st["sentences"][0]
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.cat_unknown, (
        "🚨 화장품 · 일반상품 전제에서는 판정하지 못했는데 확정으로 기록했다 — 적용되는지 모르는 법으로 확정하지 않는다 (D-319 ①)"
    )
    assert s.violations == [Violation.거짓_과장] and s.risk.final is not None, (
        "보류에도 유형과 가장 보수적인 위험도가 실린다 (D-263 ①)"
    )
    assert {b.premise for b in st["branches"]} == set(Premise), (
        "품목을 모르면 분기는 전제 전부다 (D-229 ⑥)"
    )
    food, cos = _branch(st, Premise.식품).sentences[0], _branch(st, Premise.화장품).sentences[0]
    assert food.verdict is Verdict.confirmed and food.violations
    assert cos.verdict is Verdict.hold and cos.hold_reason is HoldReason.low_conf, (
        "식품법 낱말은 화장품 전제에서 「위반 없음」이 아니라 사전 침묵이다 (D-269)"
    )
    r = to_response({**st, "outcome": Outcome.hold})
    assert len(r.branches) == len(Premise), "응답이 분기를 싣는다"


def test_표시광고법으로_걸리면_품목을_몰라도_확정이다(criteria: None) -> None:
    st, _ = _run({"law_ftc": [_hit(FAIR1)]})
    s = st["sentences"][0]
    assert s.verdict is Verdict.confirmed and s.violations == [Violation.거짓_과장], (
        "표시광고법은 모든 전제의 법 묶음에 든다 — 모든 전제에서 같은 위반이다 (D-319 ①)"
    )
    tops = [b.sentences[0].risk.final for b in st["branches"]]
    assert all(t is not None for t in tops) and s.risk.final.level == max(t.level for t in tops), (
        "등급만 다르면 가장 높은 등급으로 기록한다 (D-319 ①′)"
    )
    to_response({**st, "outcome": Outcome.hold})


def test_건강기능식품_오인은_건기식_전제에서_서지_않는다(criteria: None) -> None:
    st, _ = _run({"law_food": [_hit(FOOD3)]})
    assert st["sentences"][0].hold_reason is HoldReason.cat_unknown
    food = _branch(st, Premise.식품).sentences[0]
    assert (
        food.violations == [Violation.건강기능식품_오인] and food.infeasibility is Infeasibility.A
    )
    for p in (Premise.건기식_인정, Premise.일반식품_기능성):
        b = _branch(st, p)
        s0 = b.sentences[0]
        assert Violation.건강기능식품_오인 not in s0.violations, (
            f"{p.value} 에서 3호가 섰다 — 「건강기능식품이 아닌 것을」 (D-319 ④′ ① ④)"
        )
        assert s0.verdict is Verdict.hold and s0.hold_reason is HoldReason.low_conf, (
            f"🚨 {p.value} 에서 3호가 서지 않는 것을 판정으로 내렸다 — 서지 않는다 ≠ 통과다. "
            "인정 · 고시된 문구와의 대조가 없다 (D-220)"
        )
        assert s0.risk.final is None and b.outcome is Outcome.hold, (
            "판정하지 못한 분기가 통과 · 위험도를 냈다"
        )
    un = _branch(st, Premise.건기식_비인정).sentences[0]
    assert un.violations == [Violation.거짓_과장] and un.infeasibility is Infeasibility.A, (
        "인정하지 않은 기능성은 [별표 1] 4.나 — 거짓 · 과장이고 자격형이다 (D-319 ④′ ②)"
    )
    assert any(e.item.endswith("제4호나목") for e in un.evidence), "근거가 4호 나목이 아니다"
    assert un.risk.final is Risk.R1, "[별표 7] 에 4.나 의 목이 없다 — 「그 밖에」 시정명령이다"


def test_건기식_인정의_질병_표방은_목을_모르면_판정하지_못한다(criteria: None) -> None:
    st, _ = _run({"law_food": [_hit(FOOD1)]})
    b = _branch(st, Premise.건기식_인정).sentences[0]
    assert b.verdict is Verdict.hold and b.violations == [Violation.질병_예방치료_표방], (
        "🚨 목을 모르는 질병 표방을 통과나 위반으로 내렸다 — 단서는 가 · 라목에만 있다 (D-319 ④′ ③ · D-220)"
    )
    st, _ = _run({"law_food": [_hit(FOOD1_NA)]})
    b = _branch(st, Premise.건기식_인정).sentences[0]
    assert b.verdict is Verdict.confirmed and b.violations == [Violation.질병_예방치료_표방], (
        "치료 효과(나목)에는 건기식 단서가 없다 — 이 전제에서도 위반이다"
    )


def test_판정하지_못하는_적중이_있으면_남은_적중만으로_확정하지_않는다(criteria: None) -> None:
    st, _ = _run({"law_food": [_hit(FOOD1)], "law_ftc": [_hit(FAIR1)]})
    b = _branch(st, Premise.건기식_인정).sentences[0]
    assert b.verdict is Verdict.hold, (
        "🚨 목을 모르는 질병 표방을 떨어뜨리고 표시광고법 적중만으로 확정했다 — 그 분기는 "
        "「거짓 · 과장뿐」이라고 말하게 된다 (D-319 ④′ ③ · D-220)"
    )
    assert set(b.violations) == {Violation.질병_예방치료_표방, Violation.거짓_과장}, (
        "보류에는 걸린 것이 전부 유형 후보로 실린다 (D-311)"
    )
    assert b.risk.final is None, "유형 후보에는 하한을 걸지 않는다 (D-311 · D-313 ③)"
    food = _branch(st, Premise.식품).sentences[0]
    assert food.verdict is Verdict.confirmed, "다른 전제의 확정은 그대로다"
    to_response({**st, "outcome": Outcome.hold})


def test_어느_분기도_문구_대조_없이_통과를_내지_않는다(criteria: None) -> None:
    for by_law in ({"law_food": [_hit(FOOD3)]}, {"law_food": [_hit(FOOD3)], "law_ftc": []}):
        for cat in (None, Category.식품, Category.건기식):
            st, _ = _run(by_law, cat)
            for b in st["branches"]:
                assert b.outcome is not Outcome.passed, (
                    f"🚨 {cat} · {b.premise.value} 분기가 통과다 — 걸린 낱말이 있는데 대조 없이 통과를 냈다"
                )


def test_품목이_주어지고_전제가_판정을_바꾸지_않으면_분기가_없다(criteria: None) -> None:
    for cat in (Category.식품, Category.건기식):
        st, out = _run({"law_food": [_hit(FOOD4)], "law_ftc": []}, cat)
        assert _quiet(out), f"{cat.value} — 두 전제의 판정이 같은데 고를 것이 없는 분기를 냈다"
        assert st["sentences"][0].verdict is Verdict.confirmed, "종전 판정 그대로다"
        to_response({**st, "outcome": Outcome.hold})
    st, out = _run({"law_ftc": [_hit(FAIR1)]})
    assert not _quiet(out), "품목을 모르면 판정이 같아도 분기를 낸다 (D-229 ⑥)"


def test_품목이_식품이면_전제는_둘이고_사유는_premise_unknown_이다(criteria: None) -> None:
    st, _ = _run({"law_food": [_hit(FOOD3)], "law_ftc": []}, Category.식품)
    assert [b.premise for b in st["branches"]] == [Premise.식품, Premise.일반식품_기능성]
    assert st["sentences"][0].hold_reason is HoldReason.premise_unknown
    to_response({**st, "outcome": Outcome.hold})


def test_전제가_하나뿐이면_분기가_없다(criteria: None) -> None:
    _, out = _run({"law_cosmetic": [], "law_ftc": [_hit(FAIR1)]}, Category.화장품)
    assert _quiet(out), "화장품은 전제가 하나다 — 분기를 낼 것이 없다"


def test_어느_전제에서도_걸린_것이_없으면_종전_판정_그대로다(criteria: None) -> None:
    st, out = _run({})
    assert out["sentences"] == [], "사전 침묵 문장을 분기가 바꿨다"
    assert st["sentences"][0].hold_reason is HoldReason.low_conf
    to_response({**st, "outcome": Outcome.hold})


def test_평가_도구가_분기를_기록과_따로_센다(criteria: None) -> None:
    from scripts import eval_graph as eg

    st, _ = _run({"law_food": [_hit(FOOD4)]})
    p = eg.predict({**st, "outcome": Outcome.hold})
    assert p["class"] == "보류" and p["hold_reasons"] == ["cat_unknown"], (
        "기록은 보류다 — 분기를 예측으로 세지 않는다 (D-263 ①)"
    )
    assert (
        p["branches"]["식품"]["types"] == ["거짓_과장"] and p["branches"]["화장품"]["types"] == []
    )
    row = {
        "text": TEXT,
        "품목": "식품",
        "근거": [FOOD4],
        "labels": ["거짓_과장"],
        "조건": "B",
        "split": "test_sentence",
    }
    b = eg.branch_report([row], [p])
    assert (b["rows_with_branches"], b["positive"], b["confirmed"], b["ho_hit"]) == (1, 1, 1, 1), b
    row["품목"] = "화장품"
    b = eg.branch_report([row], [p])
    assert (b["positive"], b["confirmed"]) == (1, 0), (
        "화장품 분기는 판정하지 못했다 — 확정으로 세지 않는다"
    )
