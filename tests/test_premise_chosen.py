"""고른 전제 — 그 전제 하나로 판정하고 기록 = 그 전제의 판정 (🆕 2026-10-21 · D-348 보충 34).

지키는 것 — 실제 노드(`judge` → `assess_risk` → `premise_branches` → `doc_rules`)를 인코더 신호와 함께 돌린다
  ① **동치** — 전제를 골라 넣은 판정의 기록 = 전제를 넣지 않고 분기를 펼쳐 그 전제 분기에서 읽은 문장
     (판정 · 사유 · 위반 · 위험도 · 질문 · 답) · 답 없음 · 「예」 · 「아니오」 모두
  ② 고르면 분기가 없다(보이는 분기 · 접힌 분기 모두) · 응답이 계약을 지난다
  ③ 계약 — 전제와 품목이 어긋나면 거부 · 품목을 비우면 전제의 품목 · `pm.product_of` 가 전제를 싣는다
  ④ 전제가 하나뿐인 품목(화장품)은 전제를 줘도 종전 그대로
  ⑤ 안전장치 (보충 33 결정 1 · 보충 34 결정 3) — 답한 뒤 분기끼리 결과가 갈리면 기록은 전제 보류다(가장 나쁜 분기를 확정하지 않는다)
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import premise as pm
from app.contracts import (
    Answer,
    Category,
    HoldReason,
    Premise,
    ProductContext,
    UserSubst,
    Verdict,
)
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

TEXT = "이 제품은 피로 회복에 탁월한 효과가 있습니다."  # 지은 문장 — `tests/test_fold_invariant.py` 와 같다


class _Cur:
    """`v_risk_lookup` 대역 — `tests/test_fold_invariant.py` `_Cur` 와 같은 모양(시험 파일이라 한 벌 더 둔다)."""

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


def _enc(x: str) -> g.SentEncoding:
    return g.SentEncoding(
        sent_id="s0", scores=(("거짓_과장", 0.9),), candidates=("거짓_과장",), input=x
    )


def _run(product: ProductContext) -> dict:
    """문장 하나 · 사전 침묵 · 인코더는 모든 품목 입력에서 거짓_과장 — 판정 뒤 노드를 실제로 돌린다."""
    laws = g.laws_for(product.category)
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": product,
        "laws": laws,
        "dict_scans": [g.DictScan(sent_id="s0", ran=True)],
        "law_results": [g.LawResult(law=law, sent_ids=("s0",)) for law in laws],
        "encodings": [_enc(x) for x in ("모름", "식품", "건기식", "화장품")],
    }
    cfg = {"configurable": {"conn": _Cur()}}
    for node in (g.judge, g.assess_risk, g.premise_branches, g.doc_rules):
        out = node(st, cfg) if node in (g.assess_risk, g.premise_branches) else node(st)
        if "sentences" in out:
            st["sentences"] = g.upsert_sentences(st.get("sentences", []), out["sentences"])
        for k in ("branches", "folded"):
            if k in out:
                st[k] = out[k]
    return st


def _sig(j) -> tuple:  # noqa: ANN001
    return (
        j.verdict,
        j.hold_reason,
        tuple(j.violations),
        j.risk.final,
        j.substantiation is not None,
        j.fact_check is not None,
        j.user_subst.answer if j.user_subst is not None else None,
    )


def _substs(answer: Answer | None) -> list[UserSubst]:
    return [] if answer is None else [UserSubst(text=TEXT, answer=answer)]


@pytest.fixture(autouse=True)
def _no_tau(monkeypatch: pytest.MonkeyPatch) -> None:
    """판 지문에 기대지 않는다 — 문턱 없음."""
    monkeypatch.setattr(g, "_premise_tau", lambda v: None)


TWO = (Category.식품, Category.건기식)
ANSWERS = (None, Answer.예, Answer.아니오)


@pytest.mark.parametrize("cat", TWO)
@pytest.mark.parametrize("answer", ANSWERS)
def test_동치_고른_전제의_기록은_그_전제_분기와_같다(
    cat: Category, answer: Answer | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """① 분기는 「고르면 이렇게 된다」의 미리보기다 — 고른 뒤 다시 판정한 결과가 미리보기와 다르면 사용자가 본 것과 받은 것이 갈린다."""
    for p in pm.PREMISES_OF[cat]:
        chosen = _run(ProductContext(category=cat, premise=p, substs=_substs(answer)))
        (rec,) = chosen["sentences"]
        with monkeypatch.context() as m:
            m.setattr(g, "_branch_key", lambda j: id(j))  # 강제로 펼친다 — 그 전제 분기를 읽는다
            m.setattr(g, "_shown_key", lambda j: id(j))
            whole = _run(ProductContext(category=cat, substs=_substs(answer)))
        (b,) = [b for b in whole["branches"] if b.premise is p]
        assert _sig(rec) == _sig(b.sentences[0]), (p, answer)


#: 한쪽 전제에서 질문이 서지 않게 하는 대역 — 두 하위 전제의 결과를 가른다(`tests/test_fold_invariant.py` 펼침 규칙 시험과 같은 손)
OFF = {Category.식품: Premise.일반식품_기능성, Category.건기식: Premise.건기식_인정}


@pytest.mark.parametrize("cat", TWO)
@pytest.mark.parametrize("answer", ANSWERS)
def test_동치_전제끼리_갈려도_고른_전제의_기록은_그_전제_분기와_같다(
    cat: Category, answer: Answer | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """① 갈리는 경우 — 위 시험은 두 전제 결과가 같아 고른 전제를 무시해도 통과한다(고치기 전 동작에서 통과 확인). 이 시험이 가른다."""
    orig = g._with_condition
    off = OFF[cat]

    def one_side(s, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        if {b.premise for b in s.risk.encoder_basis} == {off}:
            return None
        return orig(s, *a, **k)

    monkeypatch.setattr(g, "_with_condition", one_side)
    whole = _run(ProductContext(category=cat, substs=_substs(answer)))
    assert whole.get("branches"), "두 전제 결과가 갈린다 — 분기가 보인다"
    got = {}
    for p in pm.PREMISES_OF[cat]:
        (rec,) = _run(ProductContext(category=cat, premise=p, substs=_substs(answer)))["sentences"]
        (b,) = [b for b in whole["branches"] if b.premise is p]
        assert _sig(rec) == _sig(b.sentences[0]), (p, answer)
        got[p] = _sig(rec)
    assert len(set(got.values())) == 2, "전제마다 기록이 달라야 이 시험이 뜻이 있다"


@pytest.mark.parametrize("cat", TWO)
def test_고르면_분기가_없다(cat: Category) -> None:
    """② 고를 것이 남지 않았다 — 보이는 분기도 접힌 분기도 내지 않는다."""
    for p in pm.PREMISES_OF[cat]:
        st = _run(ProductContext(category=cat, premise=p))
        assert not st.get("branches") and not st.get("folded"), p
        g.to_response(st)  # type: ignore[arg-type]


def test_계약_전제와_품목이_어긋나면_거부() -> None:
    """③ 품목은 전제의 품목이어야 한다 — 어긋난 입력으로 아무 전제나 고르지 않는다(D-220)."""
    with pytest.raises(ValueError, match="보충 34"):
        ProductContext(category=Category.식품, premise=Premise.건기식_인정)


def test_계약_품목을_비우면_전제의_품목() -> None:
    """③ 전제가 품목을 정한다."""
    assert ProductContext(premise=Premise.건기식_비인정).category is Category.건기식


@pytest.mark.parametrize("p", list(Premise))
def test_product_of_는_전제를_싣는다(p: Premise) -> None:
    """③ 평가(골든 `전제`)와 화면(고른 분기)이 제품 정보를 만드는 한 곳 — 전제를 실어야 그래프가 그 전제로 판정한다."""
    ctx = pm.product_of(p)
    assert ctx.premise is p and ctx.category is pm.PREMISE_CATEGORY[p]


def test_전제가_하나뿐인_품목은_종전_그대로() -> None:
    """④ 화장품 — 고를 것이 없었다. 전제를 줘도 기록이 같다."""
    with_p = _run(ProductContext(category=Category.화장품, premise=Premise.화장품))
    without = _run(ProductContext(category=Category.화장품))
    assert [_sig(s) for s in with_p["sentences"]] == [_sig(s) for s in without["sentences"]]


@pytest.mark.parametrize("cat", TWO)
def test_답한_뒤_분기끼리_갈리면_기록은_전제_보류다(cat: Category) -> None:
    """⑤ 보충 33 결정 1 — 답한 뒤에도 남은 것이 전제면 답 대기다.

    🔴 되돌림 막이 — 10-17(1-b)부터 「답이 모든 분기에 들었으면 가장 나쁜 분기 = 기록」이었다. 한 분기 확정 위반 · 다른 분기 R0 이면
       기록이 확정 위반이었다(고치기 전 동작에서 실패 확인 · 대역 · 2026-10-21).
    ★ 같은 답이 법 축에 따라 갈리는 실제 꼴은 대역으로 못 만들어 두 답의 분기 문장을 짝지어 기록 모음 함수에 직접 넣는다.
    """
    no = _run(ProductContext(category=cat, substs=_substs(Answer.아니오)))
    yes = _run(ProductContext(category=cat, substs=_substs(Answer.예)))
    bad = (no.get("branches") or no["folded"])[0].sentences[0]
    ok = (yes.get("branches") or yes["folded"])[1].sentences[0]
    assert bad.verdict is Verdict.confirmed and bad.violations and bad.user_subst is not None
    assert ok.verdict is Verdict.confirmed and not ok.violations and ok.user_subst is not None
    (rec,) = no["sentences"]
    base = rec.model_copy(
        update={
            "verdict": Verdict.hold,
            "hold_reason": HoldReason.low_conf,
            "violations": [],
            "user_substs": [],
        }
    )
    got = g._record_condition(base, [bad, ok], HoldReason.premise_unknown)
    assert got is not None and got.verdict is Verdict.hold
    assert got.hold_reason is HoldReason.premise_unknown
    # 모든 분기가 같으면 종전대로 그 판정
    got = g._record_condition(base, [bad, bad], HoldReason.premise_unknown)
    assert got is not None and got.verdict is Verdict.confirmed and got.violations == bad.violations
