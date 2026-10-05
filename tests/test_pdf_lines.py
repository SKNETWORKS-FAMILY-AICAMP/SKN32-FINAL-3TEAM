"""PDF 줄넘김 되살리기(`preprocess/pdf_lines.py`) — 붙일 줄과 띄울 줄 (2026-10-03).

🚨 원문 PDF 는 저장소에 없다(CI) — 실제 문서에서 잰 줄의 모양(줄 끝 빈칸 글자 · 오른쪽 끝 · 글자 크기)을 값으로 옮겼다.
   실측(클론 B 원문 · 작업공간): 2020 질문집 줄넘김 3,072 중 붙임 834 · 2012 질의응답집 대조 어긋남 1.3%.
"""

from __future__ import annotations

import pytest

from preprocess import pdf_lines as pl
from preprocess.pdf_lines import Line

RIGHT = 525.4  # 쪽의 오른쪽 끝


def _ln(text: str, *, sp: bool = False, x1: float = 524.1, size: float = 12.0) -> dict:
    return {"text": text, "sp": sp, "x1": x1, "size": size}


@pytest.mark.gate
def test_낱말_안에서_넘은_줄만_붙인다() -> None:
    none: set = set()
    # 줄 끝에 빈칸 글자가 없고 오른쪽 끝에 닿았다 — 「화장/품」
    assert pl._why_space(_ln("[별표 5]에서는 화장"), "품에서", RIGHT, none) is None
    # 빈칸에서 넘었다 — PDF 에 빈칸 글자가 남아 있다
    assert pl._why_space(_ln("건강을 유지 또는", sp=True), "증진하기", RIGHT, none) == "띄움_빈칸"
    # 짧은 줄은 문단의 끝이다
    assert pl._why_space(_ln("거친 피부", x1=214.6), "건★으로", RIGHT, none) == "띄움_짧은줄"
    # 문장 부호로 끝난 줄은 꽉 차 있어도 붙이지 않는다
    assert pl._why_space(_ln("해당됩니다."), "귀", RIGHT, none) == "띄움_부호"
    # 문서 안에서 띄어 쓴 꼴만 나오는 쌍 — 줄 끝 빈칸 글자가 빠진 자리
    assert pl._why_space(_ln("오인될 우려가"), "있는", RIGHT, {("우려가", "있는")}) == "띄움_쌍"
    # 쪽의 마지막 줄
    assert pl._why_space(_ln("끝"), None, RIGHT, none) == "쪽_끝"


@pytest.mark.gate
def test_띄어_쓴_꼴만_나오는_쌍을_문서에서_찾는다() -> None:
    doc = [
        [_ln("오인될 우려가 있는 표시"), _ln("그 화장품 을 쓴다")],
        [_ln("이 화장품을 바른 뒤")],
    ]
    veto = pl._veto(doc)
    assert ("우려가", "있는") in veto  # 「우려가있는」은 어디에도 없다
    assert (
        "화장품",
        "을",
    ) not in veto  # 「화장품을」이 줄 안쪽에 있다 — 붙여 쓴 꼴이 있으면 막지 않는다


@pytest.mark.gate
def test_잇기는_붙는_줄만_붙이고_새_항목의_머리는_띄운다() -> None:
    lines = [Line("거칠거", glue=True), Line("칠한 피부를", glue=False), Line("가꾼다")]
    assert pl.join(lines) == "거칠거칠한 피부를 가꾼다"
    # 글머리표 · 목록 번호 · 「(예」로 시작하는 줄은 앞 줄이 꽉 차 있어도 붙이지 않는다
    assert pl.join([Line("표시한다)", glue=True), Line("¡ 또한")]) == "표시한다) ¡ 또한"
    assert pl.join([Line("제조업자", glue=True), Line("다. 시험실")]) == "제조업자 다. 시험실"
    assert pl.join([Line("하나요?", glue=True), Line("(예: 10mL)")]) == "하나요? (예: 10mL)"
    # 손질(글머리표 떼기)은 붙일지를 정한 **뒤에** 건다
    got = pl.join(
        [Line("¡ 화장", glue=True), Line("품입니다.")], clean=lambda s: s.removeprefix("¡")
    )
    assert got == "화장품입니다."


@pytest.mark.gate
def test_좌표_없는_글은_전부_빈칸으로_잇는다() -> None:
    """합성 글 · 좌표를 못 읽은 글 — 모르면 띄운다(종전 동작)."""
    lines = pl.as_lines("화장\n품  법\n\n제13조")
    assert [str(s) for s in lines] == ["화장", "품 법", "제13조"]
    assert not any(s.glue for s in lines)
    assert pl.join(lines) == "화장 품 법 제13조"
