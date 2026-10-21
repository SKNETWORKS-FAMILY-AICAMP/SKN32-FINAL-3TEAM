"""접든 펼치든 기록은 같다 — 품목을 넘긴 판정의 접힌 분기 (🆕 2026-10-20 · D-348 보충 32 · 결함 A).

지키는 것 — 실제 노드(`judge` → `assess_risk` → `premise_branches` → `doc_rules`)를 인코더 신호와 함께 돌린다
  ① 품목이 식품 · 건강기능식품(하위 전제 둘)이고 전제마다 판정이 같아 분기가 접혀도 **기록에 실증 질문이 선다**
     (종전: 접힌 기록 문장은 근거 전제가 둘이라 `_enc_subst` 가 None — 질문이 빠지고 답도 버려졌다)
  ② 실증 「아니오」 답이 기록에 반영된다(확정 위반) · 「예」 답은 R0 로 닫힌다
  ③ **불변식** — 같은 문장 · 같은 품목 · 같은 답이면 접은 경로의 기록 = 강제로 펼친 경로의 기록(판정 · 사유 · 질문 · 답 · 위험도)
  ④ 기록이 막다른 보류(선택지 없는 전제 보류)인데 분기가 숨겨지는 일이 없다 — 응답이 계약을 지난다
  ④′ 펼침 규칙 — 질문을 붙인 뒤 한쪽 전제에만 질문이 서면 분기를 드러낸다
  ⑤ 단일 전제 품목(화장품)은 종전 그대로
"""

from __future__ import annotations

import pytest

from app import graph as g
from app.contracts import (
    Answer,
    Category,
    HoldReason,
    Premise,
    ProductContext,
    UserSubst,
    Verdict,
    Violation,
)
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

TEXT = "이 제품은 피로 회복에 탁월한 효과가 있습니다."  # 지은 문장


class _Cur:
    """`v_risk_lookup` 대역 — `tests/test_premise_known.py` `_Cur` 와 같은 모양(시험 파일이라 한 벌 더 둔다)."""

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


def _run(category: Category | None, answer: Answer | None = None) -> dict:
    """문장 하나 · 사전 침묵 · 인코더는 모든 품목 입력에서 거짓_과장 — 판정 뒤 노드를 실제로 돌린다."""
    laws = g.laws_for(category)
    substs = [] if answer is None else [UserSubst(text=TEXT, answer=answer)]
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": ProductContext(category=category, substs=substs),
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


def _sig(st: dict) -> tuple:
    (r,) = st["sentences"]
    return (
        r.verdict,
        r.hold_reason,
        tuple(r.violations),
        r.risk.final,
        r.substantiation is not None,
        r.fact_check is not None,
        r.user_subst.answer if r.user_subst is not None else None,
    )


@pytest.fixture(autouse=True)
def _no_tau(monkeypatch: pytest.MonkeyPatch) -> None:
    """판 지문에 기대지 않는다 — 문턱 없음."""
    monkeypatch.setattr(g, "_premise_tau", lambda v: None)


TWO = (Category.식품, Category.건기식)


@pytest.mark.parametrize("cat", TWO)
def test_접혀도_기록에_실증_질문이_선다(cat: Category) -> None:
    st = _run(cat)
    assert not st.get("branches"), "전제마다 판정 · 질문이 같다 — 분기는 접힌 채다"
    (r,) = st["sentences"]
    assert r.substantiation is not None, "접힌 기록에도 실증 질문이 선다(결함 A)"
    g.to_response(st)  # type: ignore[arg-type] — 계약을 지난다


@pytest.mark.parametrize("cat", TWO)
def test_접힌_기록에_실증_아니오_답이_반영된다(cat: Category) -> None:
    (r,) = _run(cat, Answer.아니오)["sentences"]
    assert r.verdict is Verdict.confirmed and r.violations == [Violation.거짓_과장]
    assert r.user_subst is not None and r.user_subst.answer is Answer.아니오


@pytest.mark.parametrize("cat", TWO)
def test_접힌_기록에_실증_예_답은_닫힌다(cat: Category) -> None:
    (r,) = _run(cat, Answer.예)["sentences"]
    assert r.verdict is Verdict.confirmed and not r.violations
    assert r.user_subst is not None and r.user_subst.answer is Answer.예


@pytest.mark.parametrize("answer", [None, Answer.예, Answer.아니오, Answer.해당없음])
@pytest.mark.parametrize("cat", TWO)
def test_불변식_접든_펼치든_기록은_같다(
    cat: Category, answer: Answer | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    folded = _sig(_run(cat, answer))
    # 강제로 펼친다 — 전제마다 열쇠가 다르게(분기를 낼지 보는 열쇠만 바꾼다 · 판정 · 질문은 그대로)
    monkeypatch.setattr(g, "_branch_key", lambda j: id(j))
    st = _run(cat, answer)
    assert st.get("branches"), "강제로 펼쳤다"
    assert folded == _sig(st)


@pytest.mark.parametrize("cat", TWO)
def test_막다른_전제_보류에_분기가_숨지_않는다(cat: Category) -> None:
    for answer in (None, Answer.예, Answer.아니오, Answer.해당없음):
        st = _run(cat, answer)
        for r in st["sentences"]:
            if g._premise_dependent(r):
                assert st.get("branches"), (cat, answer, "기록이 전제에 달렸는데 분기가 숨었다")
        g.to_response(st)  # type: ignore[arg-type]


def test_한쪽_전제에만_질문이_서면_분기를_드러낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    """펼침 규칙 — 질문 전 판정은 같아 접혔지만 질문을 붙인 뒤 전제끼리 갈리면 고를 것이 생긴 것이다."""
    orig = g._with_condition

    def one_side(s, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        if {b.premise for b in s.risk.encoder_basis} == {Premise.일반식품_기능성}:
            return None  # 이 전제에서는 질문이 서지 않는 문장으로 둔다(대역)
        return orig(s, *a, **k)

    monkeypatch.setattr(g, "_with_condition", one_side)
    st = _run(Category.식품)
    assert st.get("branches"), "한쪽 전제에만 질문이 선다 — 숨기면 그 전제의 질문이 보이지 않는다"
    by = {b.premise: b.sentences[0] for b in st["branches"]}
    assert by[Premise.식품].substantiation is not None
    assert by[Premise.일반식품_기능성].substantiation is None
    g.to_response(st)  # type: ignore[arg-type]


@pytest.mark.parametrize("cat", TWO)
def test_두_하위_전제가_같은_위반으로_확정하면_기록도_확정(
    cat: Category, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🆕 2026-10-21 — 접힌 분기에서 두 하위 전제가 모두 인코더 쪽 절대형(C)으로 같은 위반을 확정하면 기록도 그 판정이다.

    🔴 되돌림 막이 — 첫 고침에서 기록 위험도가 분기와 같으면(R1) 기록을 올리지 않아 보류로 남았다(dev 조건부 7 행 · 원장 10-21 ①).
    """
    monkeypatch.setattr(
        g,
        "_absolute_types",
        lambda s: (
            {b.violation for b in s.risk.encoder_basis if b.moved_from is None}
            & {Violation.거짓_과장}
        ),
    )
    st = _run(cat)
    hidden = st.get("folded") or []
    assert not st.get("branches") and hidden, "두 전제 결과가 같다 — 접힌 채다"
    assert all(b.sentences[0].verdict is Verdict.confirmed for b in hidden)
    (r,) = st["sentences"]
    assert r.verdict is Verdict.confirmed and r.violations == [Violation.거짓_과장]
    g.to_response(st)  # type: ignore[arg-type]
    # 불변식 — 강제로 펼친 경로도 같은 기록
    folded = _sig(st)
    monkeypatch.setattr(g, "_branch_key", lambda j: id(j))
    assert _sig(_run(cat)) == folded


@pytest.mark.parametrize("cat", TWO)
def test_한_전제만_확정하고_다른_전제가_위험도_없는_보류면_기록은_확정하지_않는다(
    cat: Category, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🆕 2026-10-21 (D-348 보충 33 · 답하기 전은 답 대기) — 한 하위 전제만 확정하면 기록은 확정하지 않는다 · 위험도가 없는 분기도 센다.

    🔴 되돌림 막이 — 「위험도가 선 분기」만 세게 고쳤을 때 무조건부 4 · 조건부 4 행이 한 전제의 확정만으로 기록 확정됐다(원장 10-21 ③ ·
       조건부 4 행은 라벨과 맞았지만 답하지 않은 하위 전제를 가정한 확정이다).
    ★ 기록 모음(`_record_at_least`)은 품목을 알든 모르든 한 함수다 — 품목 모름은 분기 확정이 막혀(보충 8 · 31) 여기서는 품목을 넘겨 확정 분기를 만든다.
    """
    monkeypatch.setattr(
        g,
        "_absolute_types",
        lambda s: (
            {b.violation for b in s.risk.encoder_basis if b.moved_from is None}
            & {Violation.거짓_과장}
        ),
    )
    st = _run(cat)
    branches = st.get("branches") or st.get("folded") or []
    (rec,) = st["sentences"]
    one, *rest = [b.sentences[0] for b in branches]
    assert one.verdict is Verdict.confirmed and rest
    # 다른 전제들을 위험도 없는 보류로 바꿔 기록을 다시 모은다
    held = [
        x.model_copy(
            update={
                "verdict": Verdict.hold,
                "hold_reason": HoldReason.low_conf,
                "violations": [],
                "infeasibility": None,
                "spans": [],
                "risk": type(x.risk)(),
            }
        )
        for x in rest
    ]
    base = rec.model_copy(
        update={"verdict": Verdict.hold, "hold_reason": HoldReason.low_conf, "violations": []}
    )
    got = g._record_at_least(base, [one, *held])
    assert got is None or got.verdict is not Verdict.confirmed, (
        "한 전제의 확정으로 기록을 확정하지 않는다"
    )
    # 모든 분기가 같은 위반으로 확정하면 확정
    got = g._record_at_least(base, [one, *(one for _ in rest)])
    assert got is not None and got.verdict is Verdict.confirmed


def test_단일_전제_품목은_종전_그대로() -> None:
    st = _run(Category.화장품)
    assert not st.get("branches") and not st.get("folded")
    (r,) = st["sentences"]
    assert r.substantiation is not None and r.hold_reason is HoldReason.low_conf


# ── 🆕 2026-10-21 (D-348 보충 35 결정 1) 불변식 검사 — 기록 확정인데 분기가 갈리면 ─────────────────────


def _wrong_record_at_least(rec, per):  # noqa: ANN001, ANN202
    """일부러 넓게 고친 기록 모음(대역) — 분기가 확정하지 않았는데도 기록을 확정한다(원장 10-21 ③ 의 꼴)."""
    return rec.model_copy(
        update={
            "verdict": Verdict.confirmed,
            "hold_reason": None,
            "violations": [Violation.거짓_과장],
            "substantiation": None,
            "fact_check": None,
        }
    )


@pytest.mark.parametrize("cat", TWO)
def test_불변식_시험에서는_기록_확정이_분기와_어긋나면_거부한다(
    cat: Category, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(g, "_record_at_least", _wrong_record_at_least)
    with pytest.raises(g.InvariantBreach, match="불변식 ①"):
        _run(cat)


@pytest.mark.parametrize("cat", TWO)
def test_불변식_운영에서는_전제_보류로_내리고_분기를_드러내고_로그를_남긴다(
    cat: Category, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """(다′) — 운영 · 평가는 바로잡는다(확정 → 전제 보류 · 분기가 선택지) · 로거 `copylane.invariant` 에 남긴다."""
    monkeypatch.delenv(g.INVARIANT_ENV, raising=False)
    monkeypatch.setattr(g, "_record_at_least", _wrong_record_at_least)
    with caplog.at_level("WARNING", logger=g.INVARIANT_LOG):
        st = _run(cat)
    (r,) = st["sentences"]
    assert r.verdict is Verdict.hold and r.hold_reason is HoldReason.premise_unknown
    assert st.get("branches"), "막다른 전제 보류 — 분기를 드러낸다"
    assert any("불변식 ①" in m for m in caplog.messages)
    g.to_response(st)  # type: ignore[arg-type]


@pytest.mark.parametrize("cat", TWO)
def test_불변식_정상_경로에서는_로그가_없다(
    cat: Category, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(g.INVARIANT_ENV, raising=False)
    for answer in (None, Answer.예, Answer.아니오, Answer.해당없음):
        with caplog.at_level("WARNING", logger=g.INVARIANT_LOG):
            _run(cat, answer)
    assert not [m for m in caplog.messages if "불변식" in m]
