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
from collect import statute
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


def _run(
    by_law: dict[str, list[DictHit]], category: Category | None = None, facts: list | None = None
) -> tuple[dict, dict]:
    """문장 하나 · 법별 적중으로 `judge` → `assess_risk` → `premise_branches` 를 실제로 돌린다. `(상태, 분기 노드가 낸 것)`."""
    laws = LAW_NODES if category is None else tuple(by_law) or ("law_ftc",)
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": ProductContext(category=category, facts=facts or []),
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


def test_기준_문안이_확정되지_않으면_분기를_내지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pm, "CRITERIA", {p: v for p, v in pm.CRITERIA.items() if p is not Premise.화장품}
    )
    st, out = _run({"law_food": [_hit(FOOD4)]})
    assert _quiet(out), (
        "🚨 문안이 한 줄 비었는데 분기 노드가 무언가 냈다 — 초안 · 빈 문안으로 응답을 내지 않는다 (D-147 · D-220)"
    )
    assert st["sentences"][0].verdict is Verdict.confirmed, "문안 전에는 종전 판정 그대로다"


def test_기준_문안_표는_승인본이고_픽스처와_한_벌이다() -> None:
    """✅ 2026-10-06 승인본 — 전제 여섯이 다 있고, 화면이 보는 픽스처의 분기 문안과 글자가 같다 (D-99 · D-263 ②)."""
    import json
    import pathlib

    assert set(pm.CRITERIA) == set(Premise) and all(v.strip() for v in pm.CRITERIA.values()), (
        "기준 문안이 빈 전제가 있다 — 분기가 꺼진다"
    )
    for p, v in pm.CRITERIA.items():
        assert "초안" not in v and "적법" not in v and "안전" not in v, (
            f"{p.value} — 초안 표시나 「적법」 · 「안전」이 문안에 있다 (D-147 · D-05 · D-130)"
        )
    seen = 0
    for f in sorted(pathlib.Path("tests/fixtures/judge").glob("*.json")):
        for b in json.loads(f.read_text(encoding="utf-8")).get("branches", []):
            seen += 1
            assert b["criteria"] == pm.CRITERIA[Premise(b["premise"])], (
                f"🚨 {f.name} 의 {b['premise']} 문안이 표와 다르다 — 화면은 픽스처를 보고 만든다. 두 벌이 되면 "
                "응답과 화면의 글자가 갈린다 (D-99)"
            )
    assert seen, "분기가 든 픽스처가 없다 — 이 게이트가 아무것도 보지 않는다"


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
        "전제": "식품",
        "근거": [FOOD4],
        "labels": ["거짓_과장"],
        "조건": "B",
        "split": "test_sentence",
    }
    b = eg.branch_report([row], [p])
    assert (b["rows_with_branches"], b["positive"], b["confirmed"], b["ho_hit"]) == (1, 1, 1, 1), b
    assert b["by_premise"] == {"식품": (1, 1, 1)}
    # 🔄 2026-10-10 — 정답 전제는 골든 `전제` 칸이다. 품목만 알고 전제를 모르면 세지 않는다 (D-220)
    assert eg.branch_report([{**row, "전제": None}], [p])["positive"] == 0
    row["전제"] = "화장품"
    b = eg.branch_report([row], [p])
    assert (b["positive"], b["confirmed"]) == (1, 0), (
        "화장품 분기는 판정하지 못했다 — 확정으로 세지 않는다"
    )


# ── 🆕 2026-10-11 — 단독 자격 없는 적중(보류 문장의 유형 후보)도 전제를 따른다 (D-319 ④′ · 원장 10-10 ⑭ ⑮) ──
#    ⛔ 종전에는 자격 없는 적중이 전제 거름을 타지 않았다 — 건강기능식품이라고 알려 줘도 후보가 「건강기능식품 오인」이었다.

FOOD4_NA = pm.UNRECOGNIZED_FUNCTION_CITE


def _run_weak(weak: list[DictHit], category: Category | None = None) -> tuple[dict, dict]:
    """`_run` 과 같되 **자격 없는 적중**(`weak_hits`)만 식품표시광고법 노드에 싣는다."""
    laws = LAW_NODES if category is None else ("law_food", "law_ftc")
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": ProductContext(category=category),
        "laws": laws,
        "dict_scans": [DictScan(sent_id="s0", ran=True, weak=tuple(weak))],
        "law_results": [
            LawResult(
                law=law,
                sent_ids=("s0",),
                weak_hits=(("s0", tuple(weak) if law == "law_food" else ()),),
            )
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


def _cites(s) -> list[tuple[str, str]]:  # noqa: ANN001
    return [(e.article, e.item) for e in s.evidence if e.basis]


def test_건강기능식품_제품의_보류_후보에_건강기능식품_오인이_남지_않는다(criteria: None) -> None:
    st, out = _run_weak([_hit(FOOD3)], Category.건기식)
    s = st["sentences"][0]
    assert (s.verdict, s.hold_reason) == (Verdict.hold, HoldReason.low_conf), "판정은 그대로 보류다"
    assert s.violations == [Violation.거짓_과장], (
        "3 호는 건강기능식품 전제에서 서지 않는다 — 4.나로 옮긴다"
    )
    _law, article, item = statute.article_item(FOOD4_NA)
    assert (article, item) in _cites(s), "근거가 4.나여야 화면이 조건을 말할 수 있다"
    assert not st["branches"], (
        "🔴 어느 전제를 골라도 보류인데 분기를 냈다 — 후보만 다른 것은 판정이 다른 것이 아니다"
    )
    assert s.risk.final is None, "보류 문장의 유형 후보에는 하한을 걸지 않는다 (D-311)"
    to_response({**st, "outcome": Outcome.hold})


def test_3호와_다른_인용이_함께_든_후보는_3호만_빠진다(criteria: None) -> None:
    """사전의 「혈당」 꼴 — 인용이 3 호와 4 호 둘이다. 건강기능식품에서는 거짓_과장만 남는다."""
    st, _ = _run_weak([_hit(FOOD3, FOOD4)], Category.건기식)
    assert st["sentences"][0].violations == [Violation.거짓_과장]
    assert not st["branches"]


def test_식품_제품의_보류_후보는_그대로다(criteria: None) -> None:
    st, out = _run_weak([_hit(FOOD3)], Category.식품)
    assert _quiet(out), "식품 전제에서는 3 호 후보가 선다 — 바꿀 것이 없고 분기도 없다"
    assert st["sentences"][0].violations == [Violation.건강기능식품_오인]


def test_품목을_모르면_기록은_그대로이고_분기의_후보만_전제를_따른다(criteria: None) -> None:
    st, out = _run_weak([_hit(FOOD3)])
    assert out["sentences"] == [], "품목을 모를 때의 기록 판정은 손대지 않는다 — 식품일 수 있다"
    assert st["sentences"][0].violations == [Violation.건강기능식품_오인]
    want = {
        Premise.식품: [Violation.건강기능식품_오인],
        Premise.일반식품_기능성: [],
        Premise.건기식_인정: [],
        Premise.건기식_비인정: [Violation.거짓_과장],
    }
    for premise, types in want.items():
        b = _branch(st, premise)
        assert b.sentences[0].verdict is Verdict.hold, (
            f"{premise.value} — 후보는 확정을 만들지 않는다"
        )
        assert b.sentences[0].violations == types, premise.value
        assert b.outcome is not Outcome.passed, f"{premise.value} — 후보가 빠졌다고 통과가 아니다"
    to_response({**st, "outcome": Outcome.hold})


def test_판정이_갈리는_분기는_그대로_선다(criteria: None) -> None:
    """자격 있는 3 호 적중 — 인정 전제는 보류, 비인정 전제는 4.나 확정이다. 판정 칸이 달라 분기가 선다."""
    st, _ = _run({"law_food": [_hit(FOOD3)], "law_ftc": []}, Category.건기식)
    assert [b.premise for b in st["branches"]] == [Premise.건기식_인정, Premise.건기식_비인정]
    assert FOOD4_NA.endswith("|나목")


def test_평가_도구가_분기_안의_보류_후보를_적는다(criteria: None) -> None:
    """결과 파일끼리 견줄 때 분기 안의 후보가 보이게 — 종전에는 확정 유형만 적었다 (원장 10-10 ⑮)."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    st, _ = _run_weak([_hit(FOOD3)])
    view = eg.predict(st)["branches"]
    assert view["식품"]["candidates"] == ["건강기능식품_오인"]
    assert view["건기식_인정"]["candidates"] == []
    assert view["건기식_비인정"]["candidates"] == ["거짓_과장"]
    assert all(not v["types"] for v in view.values()), "후보는 확정 유형 칸에 들지 않는다"


def test_조건부_후보에는_조건_문안이_붙는다(criteria: None) -> None:
    """건강기능식품 제품의 `거짓_과장` 후보는 「인정이 없다면」의 것이다 — 근거의 4.나가 그 조건이다 (D-319 보충 10-11)."""
    import pathlib  # noqa: PLC0415

    from app import reasons  # noqa: PLC0415

    st, _ = _run_weak([_hit(FOOD3)], Category.건기식)
    assert reasons.candidate_condition(st["sentences"][0]) == reasons.UNRECOGNIZED_CANDIDATE_NOTE
    # 식품 제품 — 후보는 건강기능식품 오인이고 4.나가 없다
    st, _ = _run_weak([_hit(FOOD3)], Category.식품)
    assert reasons.candidate_condition(st["sentences"][0]) is None
    # 조건 없는 거짓_과장(4 호) — 건강기능식품 제품이어도 붙이지 않는다
    st, _ = _run_weak([_hit(FOOD4)], Category.건기식)
    assert st["sentences"][0].violations == [Violation.거짓_과장]
    assert reasons.candidate_condition(st["sentences"][0]) is None
    # 확정 문장 — 조건은 불가 사유(자격형)가 말한다
    st, _ = _run({"law_food": [_hit(FOOD4_NA)], "law_ftc": []}, Category.건기식)
    assert st["sentences"][0].verdict is Verdict.confirmed
    assert reasons.candidate_condition(st["sentences"][0]) is None
    # 글자는 승인본(기준 문안 §11)과 같다
    doc = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md").read_text(encoding="utf-8")
    assert f"| {reasons.UNRECOGNIZED_CANDIDATE_NOTE} |" in doc.split("## 11.")[1]


def test_건기식_인정의_질병_표방은_문안이_서면_사실_확인_분기다(
    criteria: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🆕 2026-10-16 (D-348 결정 6 · 보충 3 결정 2 · D-319 ③ 개정) — 「판정하지 못함」 자리를 사용자가 고르는 분기로. 답은 그 문장에만."""
    from app import factcheck as fc  # noqa: PLC0415
    from app.contracts import FactKind, UserFact, is_conditional  # noqa: PLC0415

    monkeypatch.setattr(
        fc,
        "FACT_TEXTS",
        {FactKind.인정_기능성: fc.FactText(["(시험) 인정서"], "(시험) 인정 문구 그대로인가")},
    )
    st, _ = _run({"law_food": [_hit(FOOD1)]}, Category.건기식)
    b = _branch(st, Premise.건기식_인정).sentences[0]
    assert is_conditional(b) and b.fact_check.kind is FactKind.인정_기능성
    assert b.violations == [Violation.질병_예방치료_표방] and b.risk.final is not None, (
        "가장 나쁜 쪽의 하한"
    )
    assert _branch(st, Premise.건기식_비인정).sentences[0].verdict is Verdict.confirmed
    yes = UserFact(text=TEXT, kind=FactKind.인정_기능성, true=True)
    st, _ = _run({"law_food": [_hit(FOOD1)]}, Category.건기식, [yes])
    b = _branch(st, Premise.건기식_인정).sentences[0]
    assert b.verdict is Verdict.confirmed and not b.violations and b.user_facts == [yes]
    no = UserFact(text=TEXT, kind=FactKind.인정_기능성, true=False)
    st, out = _run({"law_food": [_hit(FOOD1)]}, Category.건기식, [no])
    assert "branches" not in out, "「거짓」이면 두 전제의 판정이 같아 분기를 내지 않는다"
    rec = st["sentences"][0]
    assert rec.verdict is Verdict.confirmed and rec.violations == [Violation.질병_예방치료_표방]
    assert rec.user_facts == [no], "분기가 생략돼도 사용자의 답은 기록에 출처로 남는다"
