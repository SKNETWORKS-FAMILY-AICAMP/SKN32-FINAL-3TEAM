"""인코더 쪽 절대형 확정의 세 가지 거름 (🆕 2026-10-19 · D-348 보충 26).

지키는 것
  ① 기능성 정형 낱말(시행규칙 제2조 · 지시서 제2호 절)뿐이면 화장품 의약품 오인을 C 로 세우지 않는다 · 치료 · 제거 · 비고 예외 없는 질병 낱말이 있으면 C 그대로
  ② 전제가 옮긴 근거(`moved_from`)로는 C 를 세우지 않는다 — 의약품 오인 문턱 우회를 막는다
  ③ 확신 문턱 τ — 직접 후보 확신이 τ 아래면 C 로 세우지 않는다 · 표에 없는 판은 문턱 없음 · 잠금 채택 판은 표에 값이 있다
"""

from __future__ import annotations

import pytest

from app import claimscope as cs
from app import graph as g
from app import model_lock
from app.contracts import (
    EncoderBasis,
    EncoderTypeCandidate,
    EvidenceArticle,
    HoldReason,
    Premise,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

COS1 = EvidenceArticle(law_id="002015", article="제13조제1항제1호")
FOOD1 = EvidenceArticle(law_id="013094", article="제8조제1항제1호")


@pytest.mark.parametrize(
    "text",
    [
        "피부 미백에 도움을 준다",
        "피부장벽 개선",
        "튼살완화",
        "자외선 차단 기능",
        "여드름성 피부에 적합",
        "주름 개선에 도움",
    ],
)
def test_기능성_정형_낱말은_거른다(text: str) -> None:
    assert cs.functional_not_drug(text)


@pytest.mark.parametrize(
    "text",
    [
        "아토피 피부의 피부장벽 치료",
        "기미 제거 미백 크림",
        "주름 개선과 세포 재생",
        "피부 진정",  # 제2조 낱말이 없다
        "",
    ],
)
def test_치료_제거_질병_낱말이_있거나_정형_낱말이_없으면_거르지_않는다(text: str) -> None:
    assert not cs.functional_not_drug(text)


def _held(
    text: str,
    premise: Premise,
    ref: EvidenceArticle,
    v: Violation = Violation.의약품_오인,
    conf: float = 0.9,
    moved: Violation | None = None,
) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=[EncoderTypeCandidate(violation=v, confidence=conf, moved_from=moved)],
        risk=RiskAssessment(
            encoder=Risk.R1,
            final=Risk.R1,
            encoder_basis=[
                EncoderBasis(
                    premise=premise, violation=v, floor=Risk.R2, articles=[ref], moved_from=moved
                )
            ],
        ),
    )


def test_화장품_기능성_문장은_C_로_세우지_않는다() -> None:
    assert g._absolute_types(_held("피부염 치료에 효과", Premise.화장품, COS1)) == {
        Violation.의약품_오인
    }, "기준 — 질병 문장은 C 다"
    assert g._absolute_types(_held("피부 미백에 도움을 준다", Premise.화장품, COS1)) == set()


def test_옮긴_근거로는_C_를_세우지_않는다() -> None:
    s = _held(
        "피부 미백에 좋은 세럼",
        Premise.화장품,
        COS1,
        conf=0.49,
        moved=Violation.건강기능식품_오인,
    )
    assert g._absolute_types(s) == set()
    direct = _held("피부염 치료에 효과", Premise.화장품, COS1)
    assert g._absolute_types(direct) == {Violation.의약품_오인}, "기준 — 직접 후보는 C"


def test_확신_문턱_아래면_C_로_세우지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(g, "_absolute_tau", lambda: 0.699)
    low = _held("고혈압 예방에 효과", Premise.식품, FOOD1, Violation.질병_예방치료_표방, 0.69)
    high = _held("고혈압 예방에 효과", Premise.식품, FOOD1, Violation.질병_예방치료_표방, 0.70)
    assert g._absolute_types(low) == set()
    assert g._absolute_types(high) == {Violation.질병_예방치료_표방}


def test_문턱이_없으면_종전대로(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(g, "_absolute_tau", lambda: None)
    low = _held("고혈압 예방에 효과", Premise.식품, FOOD1, Violation.질병_예방치료_표방, 0.30)
    assert g._absolute_types(low) == {Violation.질병_예방치료_표방}


def test_인코더가_꺼지면_문턱도_없다() -> None:
    assert g._absolute_tau() is None, "시험은 인코더를 끈다(conftest) — 문턱 없음"


def test_잠금_채택_판에는_문턱_값이_있다() -> None:
    """채택 판이 바뀌면 같은 규칙으로 τ 를 다시 재서 `ENCODER_ABSOLUTE_TAU` 에 적는다(보충 1 결정 5 · 보충 26 결정 3)."""
    data = model_lock.load()
    name = data["roles"]["encoder"]["adopted"]
    mark = model_lock.bundle_sha(data["bundles"][name]["files"])
    assert mark in g.ENCODER_ABSOLUTE_TAU, (
        f"채택 판 {name}({mark})의 절대형 확정 τ 가 없다 — 확장 dev · 데이터 밖으로 다시 고른다"
    )


def test_잠금_채택_판에는_전제_확정_문턱_값이_있다() -> None:
    """🆕 2026-10-19 (D-348 보충 29) — 채택 판이 바뀌면 같은 규칙으로 전제 확정 τ(건강기능식품 오인)도 다시 잰다."""
    data = model_lock.load()
    name = data["roles"]["encoder"]["adopted"]
    mark = model_lock.bundle_sha(data["bundles"][name]["files"])
    assert Violation.건강기능식품_오인 in g.ENCODER_PREMISE_TAU.get(mark, {}), (
        f"채택 판 {name}({mark})의 전제 확정 τ 가 없다 — 확장 dev 로 다시 고른다"
    )


def test_인코더가_꺼지면_전제_문턱도_없다() -> None:
    assert g._premise_tau(Violation.건강기능식품_오인) is None
