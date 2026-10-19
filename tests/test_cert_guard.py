"""인증 · 실증 꼴 거름 (🆕 2026-10-19 · D-348 보충 25).

지키는 것
  ① 지침 원문 낱말(인증 · ISO · 시험 · 테스트 · 검사 완료 · 입증)만 꼴이다 — 지침에 없는 특허 · 수상 · GMP · FDA 는 꼴이 아니다
  ② 질병 · 의학 낱말이 함께 있으면 거르지 않는다(「OO 아토피 협회 인증」은 C 그대로)
  ③ 화장품 전제의 인코더 의약품 오인만 C 에서 뺀다 — 식품 전제 · 다른 유형은 그대로
  ④ 확정과 품목 선택 필요가 같은 답(`_absolute_types` 한 곳)을 본다
"""

from __future__ import annotations

import pytest

from app import claimscope as cs
from app import graph as g
from app.contracts import (
    EncoderBasis,
    EvidenceArticle,
    HoldReason,
    Premise,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Span,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

COS1 = EvidenceArticle(law_id="002015", article="제13조제1항제1호")
FOOD3 = EvidenceArticle(law_id="013094", article="제8조제1항제3호")


@pytest.mark.parametrize(
    "text",
    [
        "ISO 22716 인증을 받은 공장에서 만들었습니다",
        "피부과 테스트 완료",
        "공인 시험검사기관에서 효과 입증",
        "식품의약품안전처 인증을 받은 제품",
    ],
)
def test_지침_원문_꼴은_거른다(text: str) -> None:
    assert cs.cert_not_drug(text)


@pytest.mark.parametrize(
    "text",
    [
        "OO 아토피 협회 인증 화장품",
        "여드름 피부 개선 효과 입증",
        "피부염 치료 효과 시험 완료",
        "특허 받은 성분",  # 지침에 없는 낱말 — 꼴이 아니다
        "FDA 등록 원료",
        "보습 효과가 뛰어납니다",
        "",
    ],
)
def test_질병_낱말이_있거나_꼴이_아니면_거르지_않는다(text: str) -> None:
    assert not cs.cert_not_drug(text)


def _held(text: str, premise: Premise, ref: EvidenceArticle) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(
            encoder=Risk.R1,
            final=Risk.R1,
            encoder_basis=[
                EncoderBasis(
                    premise=premise,
                    violation=Violation.의약품_오인,
                    floor=Risk.R2,
                    articles=[ref],
                )
            ],
        ),
    )


def test_화장품_의약품_오인은_인증_꼴이면_C_로_세우지_않는다() -> None:
    assert g._absolute_types(_held("피부염 치료에 효과", Premise.화장품, COS1)) == {
        Violation.의약품_오인
    }, "기준 — 질병 문장은 C 다(이 전제가 깨지면 아래 시험은 아무것도 지키지 않는다)"
    assert g._absolute_types(_held("ISO 22716 인증", Premise.화장품, COS1)) == set()


def test_질병_낱말이_같이_있으면_C_그대로() -> None:
    assert g._absolute_types(_held("아토피 협회 인증 화장품", Premise.화장품, COS1)) == {
        Violation.의약품_오인
    }


def test_식품_전제는_거르지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _held("ISO 22716 인증", Premise.식품, FOOD3)
    got = g._absolute_types(s)
    assert Violation.의약품_오인 in got, "기준 — 식품 3호 의약품 오인은 C 다"
    monkeypatch.setattr(cs, "cert_not_drug", lambda t: True)
    assert g._absolute_types(s) == got, "식품 전제는 이 거름 밖이다"


def test_막힌_문장은_답_없이_확정되지_않는다() -> None:
    def side(text: str) -> SentenceJudgment | None:
        return g._encoder_side(
            _held(text, Premise.화장품, COS1), [], [], Span(start=0, end=len(text), label="")
        )

    got = side("ISO 22716 인증")
    assert got is None or got.verdict is not Verdict.confirmed
    hit = side("피부염 치료에 효과")
    assert hit is not None and hit.verdict is Verdict.confirmed, "기준 — 질병 문장은 답 없이 확정"
