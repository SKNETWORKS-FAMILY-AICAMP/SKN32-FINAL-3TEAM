"""인코더 후보의 **추정 위험도**와 **대표 순서** (🆕 2026-10-15 · D-340 결정 5 · D-346 결정 3 ~ 6 · D-347 결정 6).

지키는 것
  ① 추정 위험도는 분기 문장의 **사전 유형이 없는 문장**(인코더만 잡은 문장) · 표시 목록(`ESTIMATE_TYPES`)의 (전제 · 유형)에만 실린다
  ② 판정 칸(판정 · 유형 · 위험도)은 한 글자도 바뀌지 않는다 — 후보 칸만 바뀐다(표시 전용 · D-131 개정 ① 판정 전)
  ③ 값은 서명된 제재표에서 그 전제의 법 ∩ 그 유형의 조항이 있는 법으로 찾는다 · 법 하나라도 모르면 모른다(D-220) · 표가 비면 모른다
  ④ 하한 합치기는 판정(`floor_of_sentence`)과 같은 함수다(`_combine_floors` · D-99)
  ⑤ 후보 순서는 원시 확률 내림차순 · 동률은 직접 낸 후보 → 유형 이름 · 후보를 줄이지 않는다(초안 박수진 D4-13)
  ⑥ 화면 — 후보가 둘 이상이면 첫 줄에만 대표 표지 · 추정 위험도는 「근거 보기」 안에 「확정되면」을 달고 · 확률(%)은 그리지 않는다
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from app import graph as g
from app import reasons
from app.contracts import (
    EncoderTypeCandidate,
    Premise,
    Risk,
    RiskAssessment,
    RiskEstimate,
    SentenceJudgment,
    Verdict,
    Violation,
)
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate


def _rows() -> list[dict]:
    spec = sr.load_rules()
    assert sr.signature(spec) is not None, "원천이 서명 전이다 — 이 게이트의 전제가 깨진다"
    return sr.rule_rows(spec)


def _sent(
    *cands: tuple[str, float], violations: tuple[str, ...] = (), not_claim: bool = False
) -> SentenceJudgment:
    common = {
        "sent_id": "s0",
        "text": "가",
        "encoder_candidates": [
            EncoderTypeCandidate(violation=Violation(v), confidence=p) for v, p in cands
        ],
    }
    if not_claim:  # 판정 대상 아님은 확정 · 위반 없음 · R0 이다 (D-275)
        return SentenceJudgment(
            **common,
            verdict=Verdict.confirmed,
            not_claim=True,
            risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
        )
    return SentenceJudgment(
        **common,
        verdict=Verdict.hold,
        hold_reason="low_conf",
        violations=[Violation(v) for v in violations],
    )


# ── ③ ④ 값 ─────────────────────────────────────────────────────────────


def test_표시_목록_유형의_추정_위험도는_서명된_표에서_찾는다() -> None:
    rows = _rows()
    food = g.estimate_of(rows, Premise.식품, Violation.거짓_과장)
    assert food.floor is Risk.R1 and food.ceiling is Risk.R2 and food.ceiling_note
    assert g.estimate_of(rows, Premise.식품, Violation.소비자_기만).floor is Risk.R1
    assert g.estimate_of(rows, Premise.화장품, Violation.의약품_오인).floor is Risk.R2


def test_모르면_모른다고_싣는다() -> None:
    #: 표가 비었다(서명 전 · 적재 전) — R0 이 아니다
    assert g.estimate_of([], Premise.식품, Violation.거짓_과장) == RiskEstimate()
    #: 그 전제의 법 어디에도 이 유형의 조항이 없다(화장품 전제의 질병 표방)
    assert g.estimate_of(_rows(), Premise.화장품, Violation.질병_예방치료_표방).floor is None


def test_하한_합치기는_판정과_같은_함수다() -> None:
    import inspect  # noqa: PLC0415

    assert "_combine_floors(" in inspect.getsource(g.floor_of_sentence)
    assert "_combine_floors(" in inspect.getsource(g.estimate_of)


# ── ① ② 싣는 자리 ─────────────────────────────────────────────────────


def test_인코더만_잡은_문장의_목록_유형에만_싣는다() -> None:
    rows = _rows()
    s = _sent(("거짓_과장", 0.9), ("비방광고", 0.8))
    got = g._with_estimates(s, Premise.식품, rows)
    est = {c.violation.value: c.estimate for c in got.encoder_candidates}
    assert est["거짓_과장"] is not None and est["거짓_과장"].floor is Risk.R1
    assert est["비방광고"] is None  # 목록 밖(비방광고는 제외 · D-340 결정 5)
    #: 판정 칸은 그대로다
    drop = {"encoder_candidates"}
    assert got.model_dump(exclude=drop) == s.model_dump(exclude=drop)


@pytest.mark.parametrize(
    ("sent", "premise"),
    [
        (_sent(("거짓_과장", 0.9), violations=("거짓_과장",)), Premise.식품),  # 사전 유형이 있다
        (_sent(("거짓_과장", 0.9), not_claim=True), Premise.식품),  # 판정 대상 아님
        (_sent(("거짓_과장", 0.9)), Premise.화장품),  # 목록 밖의 전제
        (_sent(("의약품_오인", 0.9)), Premise.식품),  # 목록 밖의 (전제 · 유형)
    ],
)
def test_대상이_아니면_싣지_않는다(sent: SentenceJudgment, premise: Premise) -> None:
    got = g._with_estimates(sent, premise, _rows())
    assert all(c.estimate is None for c in got.encoder_candidates)


def test_분기_문장에서만_부른다() -> None:
    """기록 판정(품목 미상)에는 싣지 않는다 — 전제 최댓값은 R2 로 뭉갠다(D-340 결정 5). 부르는 자리는 분기 문장 하나다."""
    import inspect  # noqa: PLC0415

    src = inspect.getsource(g)
    assert src.count("_with_estimates(j, premise, rows)") == 1
    assert "_with_estimates(j, premise, rows)" in inspect.getsource(g._premise_sentences)


# ── ⑤ 순서 (초안 박수진 · `docs/psj/e2e_prototype/test_reasons_representative_draft.py`) ──────────


def _c(v: str, p: float, moved: str | None = None) -> N:
    return N(violation=N(value=v), confidence=p, moved_from=moved)


def _names(xs: list) -> list[str]:
    return [x.violation.value for x in xs]


def test_원시_확률_순이고_첫_원소가_대표다() -> None:
    s = N(encoder_candidates=[_c("소비자_기만", 0.45), _c("거짓_과장", 0.62), _c("비방광고", 0.31)])
    assert _names(reasons.ordered_candidates(s)) == ["거짓_과장", "소비자_기만", "비방광고"]
    assert reasons.representative(s).violation.value == "거짓_과장"
    #: 문턱으로 나누지 않는다 — 나누면 소비자_기만(0.45 / 0.40)이 앞선다
    s2 = N(encoder_candidates=[_c("소비자_기만", 0.45), _c("거짓_과장", 0.50)])
    assert reasons.representative(s2).violation.value == "거짓_과장"


def test_옮긴_후보는_원래_확률로_동률은_직접_낸_후보_먼저() -> None:
    s = N(
        encoder_candidates=[_c("소비자_기만", 0.5), _c("거짓_과장", 0.7, moved="건강기능식품_오인")]
    )
    assert reasons.representative(s).violation.value == "거짓_과장"
    t = N(
        encoder_candidates=[
            _c("의약품_오인", 0.6, moved="질병_예방치료_표방"),
            _c("소비자_기만", 0.6),
            _c("거짓_과장", 0.6),
        ]
    )
    assert _names(reasons.ordered_candidates(t)) == ["거짓_과장", "소비자_기만", "의약품_오인"]


def test_후보를_줄이지_않고_없으면_대표도_없다() -> None:
    assert (
        len(
            reasons.ordered_candidates(
                N(encoder_candidates=[_c("a", 0.1), _c("b", 0.9), _c("c", 0.5)])
            )
        )
        == 3
    )
    assert reasons.representative(N(encoder_candidates=[])) is None
    assert reasons.representative(N()) is None


def test_추정_위험도_글자() -> None:
    assert reasons.estimate_text(N(estimate=None)) is None
    assert reasons.estimate_text(N(estimate=RiskEstimate())) == reasons.ESTIMATE_UNKNOWN
    got = reasons.estimate_text(N(estimate=RiskEstimate(floor=Risk.R1, ceiling=Risk.R2)))
    assert got == "확정되면 위험도 R1(시정명령) · 목에 따라 R2(업무정지)까지"


# ── ⑥ 화면 ───────────────────────────────────────────────────────────


def test_화면은_대표를_첫_줄에_추정_위험도를_근거_보기_안에(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415

    raw = json.loads(
        (api.FIXTURE_ROOT / "judge" / "02_hold_low_conf.json").read_text(encoding="utf-8")
    )
    raw["judged_by"] = "rule-0.3.0-dict+encb:abcdef123456"
    raw["sentences"][0]["encoder_candidates"] = [
        {"violation": "소비자_기만", "confidence": 0.55},
        {"violation": "거짓_과장", "confidence": 0.9, "estimate": {"floor": "R1", "ceiling": "R2"}},
    ]
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "est_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)
    html = TestClient(api.app).get("/u/preview/est_case").text
    head, inner = html.split("<summary>근거 보기</summary>", 1)
    want = "확정되면 위험도 R1(시정명령) · 목에 따라 R2(업무정지)까지"
    assert want in inner and want not in head
    assert reasons.REPRESENTATIVE_MARK not in head
    #: 대표(확률 높은 거짓 과장)가 먼저 · 표지는 한 번
    assert inner.index("거짓 과장") < inner.index("소비자 기만")
    assert inner.count(reasons.REPRESENTATIVE_MARK) == 1
    assert f"거짓 과장 · {reasons.REPRESENTATIVE_MARK}" in inner
    assert "0.9" not in inner and "90%" not in inner  # 확률은 그리지 않는다(D-330 안건 1 (나))
