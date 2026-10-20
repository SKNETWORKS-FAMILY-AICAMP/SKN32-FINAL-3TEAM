"""품목을 모르면 전제가 답인 확정(답 없이)도 하지 않는다 (🆕 2026-10-20 · D-348 보충 31 (ㄱ) · 보충 8 결정 1 과 같은 문).

지키는 것 — 실제 노드(`judge` → `assess_risk` → `premise_branches` → `doc_rules`)를 인코더 신호와 함께 돌린다
  ① 품목 모름 — `식품` 분기 3호 · `건기식_비인정` 분기 4.나 확정이 서지 않는다(보류 · 인코더 하한 R1 층 그대로) ·
     기록은 「품목 선택 필요」(`cat_unknown`) · 기록 위험도는 R1 층을 넘지 않는다 · 응답이 계약을 지난다
  ② 품목이 식품 — `식품` 분기 3호 확정 그대로(되돌림 막이) · 품목이 건강기능식품 — `건기식_비인정` 확정 그대로
  ③ 품목 모름에서도 질문 갈래(`일반식품_기능성` 의 기능성 표시)는 그대로 선다
"""

from __future__ import annotations

import pytest

from app import graph as g
from app.contracts import (
    Category,
    HoldReason,
    Premise,
    ProductContext,
    Risk,
    Verdict,
    Violation,
)
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

TEXT = "피로 회복에 도움을 줍니다"  # 지은 문장 — `tests/test_food_premise.py` 와 같다


class _Cur:
    """`v_risk_lookup` 대역 — `tests/test_premise_branches.py` `_Cur` 와 같은 모양(서명된 원천의 행 · 시험 파일이라 한 벌 더 둔다)."""

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


def _enc(x: str, hf: bool) -> g.SentEncoding:
    if hf:
        return g.SentEncoding(
            sent_id="s0",
            scores=(("건강기능식품_오인", 0.8),),
            candidates=("건강기능식품_오인",),
            input=x,
        )
    return g.SentEncoding(
        sent_id="s0", scores=(("건강기능식품_오인", 0.1),), candidates=(), input=x
    )


def _run(category: Category | None) -> dict:
    """문장 하나 · 사전 침묵 · 인코더(식품 · 건기식 입력)만 건강기능식품 오인 — 코어의 판정 뒤 노드를 실제로 돌린다."""
    laws = g.laws_for(category)
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": ProductContext(category=category),
        "laws": laws,
        "dict_scans": [g.DictScan(sent_id="s0", ran=True)],
        "law_results": [g.LawResult(law=law, sent_ids=("s0",)) for law in laws],
        "encodings": [
            _enc(x, x in ("식품", "건기식")) for x in ("모름", "식품", "건기식", "화장품")
        ],
    }
    cfg = {"configurable": {"conn": _Cur()}}
    for node in (g.judge, g.assess_risk, g.premise_branches, g.doc_rules):
        out = node(st, cfg) if node in (g.assess_risk, g.premise_branches) else node(st)
        if "sentences" in out:
            st["sentences"] = g.upsert_sentences(st.get("sentences", []), out["sentences"])
        if "branches" in out:
            st["branches"] = out["branches"]
    return st


def _b(st: dict, p: Premise):  # noqa: ANN202
    (s,) = next(b for b in st["branches"] if b.premise is p).sentences
    return s


@pytest.fixture(autouse=True)
def _no_tau(monkeypatch: pytest.MonkeyPatch) -> None:
    """판 지문에 기대지 않는다 — 문턱 없음(τ 는 `tests/test_food_premise.py` 가 따로 본다)."""
    monkeypatch.setattr(g, "_premise_tau", lambda v: None)


def test_품목을_모르면_전제_확정이_서지_않고_기록은_품목_선택_필요() -> None:
    st = _run(None)
    for p in (Premise.식품, Premise.건기식_비인정):
        s = _b(st, p)
        assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf, p
        assert s.risk.encoder is Risk.R1, f"{p} — 하한 · 근거는 그대로 남는다"
    (rec,) = st["sentences"]
    assert rec.verdict is Verdict.hold and rec.hold_reason is HoldReason.cat_unknown
    assert rec.risk.final is not None and rec.risk.final.level <= Risk.R1.level, (
        "가정 위의 확정이 기록을 R1 층 위로 올리지 않는다(보충 8 · 보충 2 결정 5)"
    )
    res = g.to_response(st)  # type: ignore[arg-type] — 계약 검증(기록 ≥ 분기 · 품목 보류에 분기)을 지난다
    assert res.sentences[0].hold_reason is HoldReason.cat_unknown


def test_품목을_모르면_질문_갈래는_그대로다() -> None:
    s = _b(_run(None), Premise.일반식품_기능성)
    assert s.fact_check is not None and s.verdict is Verdict.hold


def test_품목이_식품이면_식품_분기_3호_확정은_그대로() -> None:
    s = _b(_run(Category.식품), Premise.식품)
    assert s.verdict is Verdict.confirmed and s.violations == [Violation.건강기능식품_오인]


def test_품목이_건강기능식품이면_비인정_확정은_그대로() -> None:
    s = _b(_run(Category.건기식), Premise.건기식_비인정)
    assert s.verdict is Verdict.confirmed and s.violations == [Violation.거짓_과장]
