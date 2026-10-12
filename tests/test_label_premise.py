"""골든 `전제` 칸 — 라벨이 정답이 되는 제품 전제 하나 (`preprocess/golden.py` `label_premise` · 🆕 2026-10-10).

🔴 정답은 문구가 아니라 (문구 · 전제)의 짝에 붙는다 — 생성 화면의 분기 · 생성 평가 입력 · 조건부 판정 평가가 이 칸을 읽는다.
   출처나 조문이 말해 줄 때만 적고 모르면 `None` 이다. 판정의 표(`app/premise.py`)로는 검산만 한다.
🚨 행은 여기서 지어낸 것이다 — 골든 문장을 옮겨 오지 않는다 (D-175 · D-249).
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import premise as pm
from app.contracts import Premise
from collect import statute
from preprocess import golden
from preprocess.golden import check_premise, label_premise
from preprocess.split import APPROVED_READING

pytestmark = pytest.mark.gate

HF = "건강기능식품_오인"
UNRECOGNIZED = pm.UNRECOGNIZED_FUNCTION_CITE


def _row(item: str | None, cites: list[str], **kw: object) -> dict:
    return {"id": "r", "품목": item, "근거": cites, "origin": "real", "unit": "문장", **kw}


@pytest.mark.parametrize(
    ("row", "want"),
    [
        (_row("식품", [statute.food(3)]), "식품"),
        (_row("식품", []), "식품"),  # 적법 · 주장 아님 — 그 제품의 문장이다
        (_row("화장품", ["002015:제13조제1항제1호"]), "화장품"),
        # 승인 문구 — 원천은 건강기능식품 게시판이고 라벨은 「일반식품이 쓰면」이다 (판정 J1)
        (_row("건기식", [statute.food(3)], 판독=APPROVED_READING, origin="approved"), "식품"),
        # 인정하지 않은 기능성 — 조문이 전제를 말한다 ([별표 1] 4.나 · D-319 ④′ ②)
        (_row("건기식", [UNRECOGNIZED]), "건기식_비인정"),
        (_row("건기식", [statute.food(1), UNRECOGNIZED]), "건기식_비인정"),
    ],
)
def test_출처나_조문이_말해_주면_전제를_적는다(row: dict, want: str) -> None:
    assert label_premise(row) == want


@pytest.mark.parametrize(
    "row",
    [
        _row("건기식", [statute.food(1)]),  # 건강기능식품의 질병 표방 — 인정 여부를 모른다
        _row("건기식", []),
        _row(
            None, ["002011:제3조제1항제1호"]
        ),  # 공정위 — 표시광고법으로 본 정답이지 제품 전제가 아니다
        _row("건기식", [statute.food(1)], origin="injected"),  # 주입 — 학습 전용
        _row(
            "건기식", [], origin="approved", 판독="규칙_인정조건문_D"
        ),  # 인정 조건문 — 주장이 아니다
        _row(None, [statute.food(4)], unit="낱말"),  # 사전 낱말
        _row("식품", [UNRECOGNIZED]),  # 4.나는 건강기능식품의 조항이다 — 품목 칸이 의심스럽다
        _row("일반상품", ["002011:제3조제1항제1호"]),  # 골든에 없는 품목 값
    ],
)
def test_모르면_적지_않는다(row: dict) -> None:
    """품목 칸으로 짐작하지 않는다 (D-220) — 읽는 쪽이 품목 · 무조건부로 내려간다."""
    assert label_premise(row) is None


def test_적는_값은_계약의_전제다() -> None:
    rows = [
        _row("식품", [statute.food(3)]),
        _row("화장품", []),
        _row("건기식", [UNRECOGNIZED]),
        _row("건기식", [statute.food(3)], 판독=APPROVED_READING, origin="approved"),
    ]
    assert {Premise(label_premise(r)) for r in rows} == {
        Premise.식품,
        Premise.화장품,
        Premise.건기식_비인정,
    }


def test_검산은_전제의_법_밖인_근거와_서지_않는_3호에서_멈춘다() -> None:
    ok = [
        _row("식품", [statute.food(3)], 전제="식품"),
        _row("건기식", [UNRECOGNIZED], 전제="건기식_비인정"),
        _row(None, ["002011:제3조제1항제1호"], 전제=None),
    ]
    check_premise(ok)
    with pytest.raises(SystemExit, match="법 묶음 밖"):
        check_premise([_row("식품", ["002015:제13조제1항제1호"], 전제="식품")])
    with pytest.raises(SystemExit, match="서지 않는다"):
        check_premise([_row("건기식", [statute.food(3)], 전제="건기식_비인정")])


def test_검산의_법_이름_표는_그래프의_것과_같다() -> None:
    """그래프를 `preprocess` 에서 import 하지 않으려고 옮겨 적은 표다 — 어긋나면 검산이 다른 법으로 본다."""
    assert golden._LAW_OF_NODE == g.LAW_OF_NODE
