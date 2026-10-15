"""판정 대상 아님 — 주의 · 상담 문구 (🆕 2026-10-15 · D-348 보충 1 결정 1 · D-275).

🔴 무엇을 막나
   ① 주의 · 상담 문구가 사전 침묵으로 「보류(확신 부족)」에 남는 것 — 주장이 아닌 문장이다
   ② 주장과 주의가 섞인 문장에서 **사전 자격 적중을 지우는 것** — 자격 적중이 있으면 이 규칙을 쓰지 않는다
   ③ 판정 대상 아님 문장에 AI 추정 유형이 함께 실리는 것 — 「주장이 아니다」와 「AI 가 위반 유형을 추정했다」를 같이 내지 않는다
   ④ 위반에도 걸리는 꼴(대상 · 가격 · 면책)이 판정 대상 아님 규칙에 들어오는 것 — 판정 대상 아님은 통과 쪽이다(비대칭 원칙)
"""

from __future__ import annotations

import pytest

from app import claimscope, sentsplit
from app.contracts import HoldReason, Verdict, Violation
from app.graph import DictHit, DictScan, LawResult, judge

FOOD = "013094:제8조제1항제1호"


def _state(text: str, hits=(), weak=()) -> dict:  # noqa: ANN001
    sents = sentsplit.split(text)
    return {
        "text": text,
        "sents": sents,
        "laws": ("law_food", "law_ftc"),
        "dict_scans": [DictScan(sent_id="s0", ran=True, hits=tuple(hits), weak=tuple(weak))],
        "law_results": [
            LawResult(
                law="law_food",
                sent_ids=("s0",),
                dict_hits=(("s0", tuple(hits)),),
                weak_hits=(("s0", tuple(weak)),),
            ),
            LawResult(law="law_ftc", sent_ids=("s0",)),
        ],
    }


def _one(state: dict):  # noqa: ANN202
    (s,) = judge(state)["sentences"]
    return s


@pytest.mark.gate
@pytest.mark.parametrize(
    "text",
    [
        "임산부, 수유부는 섭취에 주의",
        "알레르기 체질은 섭취에 주의할 것",
        "질병으로 치료 중인 분은 전문가와 상담할 것",
        "혈액응고저해제를 복용하는 분은 의사와 상담하십시오",
        "과다 섭취 시 위장 장애가 나타날 수 있습니다",
        "식사조절, 운동을 병행하는 것이 바람직함",
    ],
)
def test_주의_상담_문구는_판정_대상_아님이다(text: str) -> None:
    assert claimscope.is_caution(text)
    s = _one(_state(text))
    assert s.verdict is Verdict.confirmed and s.not_claim
    assert not s.violations and not s.spans and s.substantiation is None
    assert s.risk.final is None, (
        "위험도(R0)는 `assess_risk` 가 적는다 — 판정 노드는 지어내지 않는다"
    )


@pytest.mark.gate
@pytest.mark.parametrize(
    "text",
    [
        "알레르기 유발 물질을 99.95% 정화합니다",  # 「알레르기」 단독은 위반 문장에도 나온다
        "오랫동안 묵혀온 살들을 제거하고 싶으신 분",  # 대상 꼴 — 위반에도 걸린다(거부 가드 쪽)
        "43% 35,000원 → 19,800원",  # 가격 — 판정 대상 아님이 아니다(D-272 개정 ②)
        "본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다",  # 면책 — 위반에도 걸린다
        "하루 한 포",
    ],
)
def test_위반에도_걸리는_꼴은_판정_대상_아님으로_내지_않는다(text: str) -> None:
    assert not claimscope.is_caution(text)
    s = _one(_state(text))
    assert not s.not_claim
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf


@pytest.mark.gate
def test_사전_자격_적중이_있으면_주의_문구여도_확정이다() -> None:
    text = "당뇨에 좋고, 임산부는 섭취에 주의"
    h = DictHit("당뇨에좋", "질병_예방치료_표방", (FOOD,), (0, 4))
    s = _one(_state(text, hits=[h]))
    assert not s.not_claim
    assert s.verdict is Verdict.confirmed and s.violations == [Violation.질병_예방치료_표방]


@pytest.mark.gate
def test_자격_없는_적중만_있으면_주의_문구는_판정_대상_아님이다() -> None:
    """🔴 이 규칙의 목적 — 주의 문맥의 「당뇨」(비주장문맥 · 자격 없음)가 보류 후보로 남지 않게 한다 (관문 ㉠ 의 꼴)."""
    text = "당뇨 치료가 필요한 경우에는 의사와 상담 하에 사용하십시오"
    w = DictHit("당뇨", "질병_예방치료_표방", (FOOD,), (0, 2))
    s = _one(_state(text, weak=[w]))
    assert s.not_claim and s.verdict is Verdict.confirmed and not s.violations


@pytest.mark.gate
def test_판정_대상_아님에는_AI_추정_유형을_싣지_않는다() -> None:
    import inspect

    from app import graph

    src = inspect.getsource(graph.judge) + inspect.getsource(graph._premise_sentences)
    assert src.count("if sid in encs and not j.not_claim") == 2, (
        "기록 판정 · 분기 판정 둘 다 판정 대상 아님에 인코더 후보를 싣지 않아야 한다 (D-348 보충 1)"
    )


def _nc(sid: str = "s0"):  # noqa: ANN202
    from app.contracts import SentenceJudgment

    return SentenceJudgment(
        sent_id=sid, text="임산부는 섭취에 주의", verdict=Verdict.confirmed, not_claim=True
    )


@pytest.mark.gate
def test_판정_대상_아님은_품목을_몰라도_R0_이다() -> None:
    """🔴 품목 미확정 · DB 없음에서도 R0 — 비면 기록(없음) < 분기(R0)로 계약 `_recorded_is_conservative` 가 응답을 거부한다."""
    from app.contracts import Risk
    from app.graph import assess_risk

    (s,) = assess_risk({"sentences": [_nc()]})["sentences"]  # type: ignore[typeddict-item]
    assert s.not_claim and s.risk.final is Risk.R0 and s.risk.floor is Risk.R0


@pytest.mark.gate
def test_판정_대상_아님만_있는_문서는_품목을_모르면_보류_알면_통과다() -> None:
    """D-319 결정 2(품목 미확정에는 맨 위 통과 없음) · D-275(계약 고정물 16 — 품목을 알면 통과)."""
    from app.contracts import Category, ProductContext, Risk, RiskAssessment
    from app.graph import route_review

    s = _nc().model_copy(update={"risk": RiskAssessment(floor=Risk.R0, final=Risk.R0)})
    assert route_review({"sentences": [s]}) == "hold"  # type: ignore[typeddict-item]
    food = {"sentences": [s], "product": ProductContext(category=Category.식품)}
    assert route_review(food) == "passed"  # type: ignore[arg-type]
    other = {"sentences": [s], "product": ProductContext(category=Category.일반상품)}
    assert route_review(other) == "hold", "주된 광고법을 안 본 품목은 통과가 없다 (D-314)"  # type: ignore[arg-type]
