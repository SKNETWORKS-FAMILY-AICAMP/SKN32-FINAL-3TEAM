"""확정 막기 가드 · 새 사전의 단독판정 (🆕 2026-10-18 · D-348 보충 15 결정 3 · 보충 16).

지키는 것
  ① 사전 적중이 주장이 아닌 자리(정체 부정 · 효능 부정 · 주의 · 부작용 · 통계 정보)에 있으면 **확정하지 않는다** — 후보로 내린다
  ② 진짜 위반을 내리지 않는다 — 수식어 부정(「~ 걱정 없이」) · 다른 절의 주의 · 타사를 향한 부정 · 원료 효능 설명은 확정 그대로
  ③ 가드는 통과를 내지 않는다 — 내린 적중이 있으면 판정 대상 아님(주의 문구)을 열지 못한다
"""

from __future__ import annotations

import pytest

from app import claimscope, sentsplit
from app.contracts import Verdict
from app.graph import DictHit, DictScan, LawResult, judge

pytestmark = pytest.mark.gate


def _span(text: str, term: str) -> tuple[int, int]:
    i = text.index(term)
    return (i, i + len(term))


@pytest.mark.parametrize(
    ("text", "term", "reason"),
    [
        ("변비약이 아닙니다", "변비약", "정체부정"),
        ("암 예방 효과는 확인되지 않았습니다", "암 예방", "효능부정"),
        ("과잉섭취 시 위장장애나 불면증을 유발할 수 있음", "불면증", "부작용"),
        ("고혈압 환자는 섭취 전 의사와 상담하세요", "고혈압", "주의"),
        ("우리나라 성인 3명 가운데 1명은 비만이라고 한다", "비만", "통계정보"),
        (
            "분유먹는 아기는 만 4~5개월부터, 모유를 먹거나 아토피가 있는 아기는 만 6개월부터 시작을 합니다",
            "아토피",
            "대상",
        ),  # 🆕 보충 19 — 누가 먹을지(섭취 대상) · 원장 10-18(B) ⑪ 의 사전 오탐
        ("당뇨 환자의 경우 하루 1포로 시작하세요", "당뇨", "대상"),
    ],
)
def test_주장이_아닌_자리는_막는다(text: str, term: str, reason: str) -> None:
    assert claimscope.confirm_block(text, _span(text, term)) == reason


@pytest.mark.parametrize(
    ("text", "term"),
    [
        ("탈모 걱정 없이 풍성하게", "탈모"),  # 수식어 부정은 효능 주장이다
        ("아토피 고민 없는 피부", "아토피"),
        ("불면증 없는 꿀잠", "불면증"),
        (
            "고혈압, 당뇨, 비만, 스트레스 부작용 없는 천연의 성분으로 세계 유일의 제품",
            "고혈압",
        ),  # 다른 절
        ("당뇨에 좋고, 임산부는 섭취에 주의하세요", "당뇨"),  # 주의는 다른 절
        ("경쟁사 제품은 효과 없음", "경쟁사"),  # 타사를 향한 부정은 비방
        ("삼채의 유황성분은 암 예방에 효과", "암 예방"),  # 원료 효능 설명은 위반
        ("비만의 원인은 의외로 지방이 아닌 탄수화물!", "비만"),
        ("당뇨가 있는 분께 좋습니다", "당뇨"),  # 🆕 보충 19 — 대상 꼴 + 효능 = 질병 표방
        ("아토피가 있는 아이에게 추천합니다", "아토피"),
        ("고혈압이 있는 분도 혈압 관리에 도움", "고혈압"),
    ],
)
def test_진짜_위반은_막지_않는다(text: str, term: str) -> None:
    assert claimscope.confirm_block(text, _span(text, term)) is None


def test_구간을_모르면_막지_않는다() -> None:
    assert claimscope.confirm_block("변비약이 아닙니다", None) is None


def _judge(text: str, hits: list[DictHit], weak: tuple[DictHit, ...] = ()) -> object:
    state = {
        "text": text,
        "sents": sentsplit.split(text),
        "laws": ("law_food",),
        "dict_scans": [DictScan(sent_id="s0", ran=True, hits=tuple(hits), weak=weak)],
        "law_results": [
            LawResult(law="law_food", sent_ids=("s0",), dict_hits=(("s0", tuple(hits)),))
        ],
    }
    (s,) = judge(state)["sentences"]
    return s


DISEASE = ("013094:제8조제1항제1호",)


def test_막힌_적중은_확정하지_않고_후보로_남긴다() -> None:
    text = "암 예방 효과는 확인되지 않았습니다"
    s = _judge(text, [DictHit("암예방", "질병_예방치료_표방", DISEASE, _span(text, "암 예방"))])
    assert s.verdict is Verdict.hold and not s.not_claim, "확정하지 않되 통과로도 내지 않는다"


def test_막히지_않은_적중은_확정한다() -> None:
    text = "암 예방에 탁월합니다"
    s = _judge(text, [DictHit("암예방", "질병_예방치료_표방", DISEASE, _span(text, "암 예방"))])
    assert s.verdict is Verdict.confirmed


def test_내린_후보가_있으면_주의_문구도_판정_대상_아님이_아니다() -> None:
    text = "다이어트 효과가 있으며 임산부는 섭취에 주의하세요"
    lowered = DictHit(
        "다이어트효과",
        "거짓_과장",
        ("013094:제8조제1항제4호",),
        _span(text, "다이어트 효과"),
        demoted=True,
    )
    s = _judge(text, [], weak=(lowered,))
    assert not s.not_claim, "내린 단독판정 항목(위반 낱말)이 주의 문맥에서 통과로 새면 안 된다"
