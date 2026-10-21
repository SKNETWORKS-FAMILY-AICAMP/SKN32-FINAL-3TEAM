"""기록 · 분기 불변식 — 함수 단위 (🆕 2026-10-21 · D-348 보충 35 결정 1 · 인계 10-21 클론B §1 #1 (다′)).

지키는 것 — `app.graph._invariant`
  ① 기록 확정 ⇒ 모든 분기가 같은 위반 집합으로 확정 · 어긋나면 전제 보류로 내린다(운영) · 시험 환경은 거부
  ② 모든 분기가 같은 위반으로 확정인데 기록이 확정이 아니면 로그만(기록을 올리지 않는다)
  · 답으로 풀린 R0 확정(위반 없음)끼리는 같다 · 판정 대상 아님 · 분기 없음은 보지 않는다
그래프를 실제로 도는 시험은 `tests/test_fold_invariant.py` 끝(불변식 검사)에 있다.
"""

from __future__ import annotations

import pytest

from app import graph as g
from app.contracts import (
    EvidenceArticle,
    HoldReason,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

V = Violation.거짓_과장
#: 근거 조문 대역 — `tests/test_contracts.py` `_EV` 와 같은 좌표(식품표시광고법 제8조①4)
_EV = EvidenceArticle(law_id="013094", article="제8조", item="제1항제4호")


def _j(verdict: Verdict, vs: tuple[Violation, ...] = (), **k: object) -> SentenceJudgment:
    reason = HoldReason.low_conf if verdict is Verdict.hold else None
    return SentenceJudgment(
        sent_id="s0",
        text="지은 문장",
        verdict=verdict,
        hold_reason=k.pop("hold_reason", reason),
        violations=list(vs),
        infeasibility=k.pop(
            "infeasibility", g.Infeasibility.C if verdict is Verdict.confirmed and vs else None
        ),
        evidence=[_EV] if vs else [],
        risk=RiskAssessment(final=Risk.R1 if vs else Risk.R0, floor=Risk.R1 if vs else Risk.R0),
        **k,
    )


CONF = _j(Verdict.confirmed, (V,))
HOLD = _j(Verdict.hold)


def test_맞으면_None() -> None:
    assert g._invariant(CONF, [CONF, CONF], HoldReason.premise_unknown) is None
    assert g._invariant(HOLD, [HOLD, CONF], HoldReason.premise_unknown) is None


def test_답으로_풀린_R0_확정끼리는_같다() -> None:
    ok = _j(Verdict.confirmed)
    assert g._invariant(ok, [ok, ok], HoldReason.premise_unknown) is None


def test_기록_확정인데_분기가_갈리면_시험은_거부() -> None:
    with pytest.raises(g.InvariantBreach, match="불변식 ①"):
        g._invariant(CONF, [CONF, HOLD], HoldReason.premise_unknown)


def test_기록_확정인데_분기_위반이_다르면_시험은_거부() -> None:
    other = _j(Verdict.confirmed, (V, Violation.소비자_기만))
    with pytest.raises(g.InvariantBreach):
        g._invariant(CONF, [CONF, other], HoldReason.premise_unknown)


@pytest.mark.parametrize("reason", [HoldReason.premise_unknown, HoldReason.cat_unknown])
def test_운영은_전제_보류로_내리고_로그(
    reason: HoldReason, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(g.INVARIANT_ENV, raising=False)
    with caplog.at_level("WARNING", logger=g.INVARIANT_LOG):
        got = g._invariant(CONF, [CONF, HOLD], reason)
    assert got is not None and got.verdict is Verdict.hold and got.hold_reason is reason
    assert (
        got.violations == [V] and got.risk.final is Risk.R1 and got.evidence == [_EV]
    )  # 유형 · 위험도는 그대로
    assert got.substantiation is None and got.fact_check is None
    assert any("불변식 ①" in m and "전제 보류로 내림" in m for m in caplog.messages)
    assert "지은 문장" not in " ".join(caplog.messages)  # 문장 글자는 싣지 않는다


def test_모든_분기가_같은_위반인데_기록이_보류면_로그만(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(g.INVARIANT_ENV, raising=False)
    with caplog.at_level("WARNING", logger=g.INVARIANT_LOG):
        got = g._invariant(HOLD, [CONF, CONF], HoldReason.premise_unknown)
    assert got is None
    assert any("불변식 ②" in m and "로그만" in m for m in caplog.messages)


def test_판정_대상_아님_분기_없음은_보지_않는다() -> None:
    nc = _j(Verdict.confirmed, not_claim=True)
    assert g._invariant(nc, [HOLD], HoldReason.premise_unknown) is None
    assert g._invariant(CONF, [], HoldReason.premise_unknown) is None
