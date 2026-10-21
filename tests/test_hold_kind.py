"""보류의 종류 — 계약 `hold_kind` (🆕 2026-10-21 · D-348 보충 36 결정 4 · (나) 계산 칸).

지키는 것 — 순서(앞이 이긴다): 질문이 서면 답 대기 → 품목 · 전제 보류면 고르기 대기 → 확신 부족 ∧ 후보 있음 = 확인 못 함 →
  확신 부족 ∧ 후보 없음 = 걸린 것 없음 → 그 밖 · 보류가 아니면 None · 응답 JSON 에 실리고 되읽어도 깨지지 않는다(저장 칸 · DB 제약 그대로)
"""

from __future__ import annotations

import pytest

from app.contracts import (
    EncoderTypeCandidate,
    HoldKind,
    HoldReason,
    Infeasibility,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    SubstBranch,
    Verdict,
    Violation,
    hold_kind,
)

pytestmark = pytest.mark.gate

_SUBST = SubstBranch(
    substantiated_max=Risk.R0, accepted_evidence=["시험 또는 조사 결과"], criteria="초안"
)


def _hold(reason: HoldReason, **k: object) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0", text="지은 문장", verdict=Verdict.hold, hold_reason=reason, **k
    )


def test_질문이_서면_답_대기() -> None:
    s = _hold(
        HoldReason.premise_unknown,
        infeasibility=Infeasibility.B,
        risk=RiskAssessment(floor=Risk.R1, final=Risk.R1),
        substantiation=_SUBST,
    )
    assert hold_kind(s) is HoldKind.awaiting_answer


@pytest.mark.parametrize("reason", [HoldReason.cat_unknown, HoldReason.premise_unknown])
def test_품목_전제_보류는_고르기_대기(reason: HoldReason) -> None:
    assert hold_kind(_hold(reason)) is HoldKind.awaiting_pick


def test_후보가_있으면_확인_못_함_없으면_걸린_것_없음() -> None:
    cand = EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.8)
    assert hold_kind(_hold(HoldReason.low_conf, encoder_candidates=[cand])) is HoldKind.unconfirmed
    assert (
        hold_kind(_hold(HoldReason.low_conf, violations=[Violation.거짓_과장]))
        is HoldKind.unconfirmed
    )
    assert hold_kind(_hold(HoldReason.low_conf)) is HoldKind.nothing_found


def test_그_밖의_사유와_보류_아님() -> None:
    assert hold_kind(_hold(HoldReason.law_uncovered)) is HoldKind.other
    clean = SentenceJudgment(
        sent_id="s0",
        text="t",
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
    )
    assert hold_kind(clean) is None


def test_응답_JSON_에_실리고_되읽어도_깨지지_않는다() -> None:
    s = _hold(HoldReason.low_conf)
    assert s.model_dump()["hold_kind"] == "nothing_found"
    assert (
        SentenceJudgment.model_validate_json(s.model_dump_json()).hold_kind
        is HoldKind.nothing_found
    )
    assert (
        "hold_kind" not in type(s).model_fields
    )  # 계산 칸 — 저장 · 복사(`model_fields` 훑기)에 들지 않는다
