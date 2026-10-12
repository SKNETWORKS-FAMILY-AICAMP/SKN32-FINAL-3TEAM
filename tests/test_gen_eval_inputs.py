"""생성 평가 입력 목록 (`scripts/gen_eval_inputs.py` · D-322 결정 C · 🆕 2026-10-10).

🔴 고쳐 쓰기를 잴 때 어떤 문구를 어떤 제품 전제로 넣는가를 한 곳에서 정한다 — 제품 정보는 아는 만큼만 넘긴다.
🚨 행은 여기서 지어낸 것이다 — 골든 문장을 옮겨 오지 않는다 (D-175 · D-249).
"""

from __future__ import annotations

import pytest

from collect import statute
from preprocess.split import APPROVED_READING
from scripts import gen_eval_inputs as gi

pytestmark = pytest.mark.gate

FTC = "002011:제3조제1항제1호"


def _row(
    rid: str, item: str | None, premise: str | None, cond: str, cites: list[str], **kw
) -> dict:
    return {
        "id": rid,
        "text": f"지어낸 문구 {rid}",
        "품목": item,
        "전제": premise,
        "조건": cond,
        "근거": cites,
        "labels": statute.types_of(cites),
        **kw,
    }


ROWS = [
    _row("식품", "식품", "식품", "B", [statute.food(4)]),
    # 승인 문구 — 원천은 건강기능식품이고 전제는 식품이다. 넘기는 품목은 전제의 것이다
    _row("승인", "건기식", "식품", "A", [statute.food(3)], 판독=APPROVED_READING),
    _row("비인정", "건기식", "건기식_비인정", "A", ["013094:제8조제1항제4호|나목"]),
    _row("건기식", "건기식", None, "C", [statute.food(1)]),  # 품목만 안다
    _row("의결서", None, None, "B", [FTC]),  # 둘 다 모른다
    _row("맥락", "식품", "식품", "M", [statute.food(4)]),  # 채점 밖 — 고칠 대상이 아니다
    _row("적법", "식품", "식품", "L", []),
    # 근거는 있는데 8유형이 없다(화장품법 4호) — 판정 평가가 채점에서 빼는 행이다 (D-321)
    _row("유형없음", "화장품", "화장품", "C", ["002015:제13조제1항제4호"]),
    _row("주장아님", "건기식", None, "D", []),
]


def test_아는_만큼만_넘긴다() -> None:
    got = {it["id"]: it for it in gi.gen_inputs(ROWS)}
    assert set(got) == {"식품", "승인", "비인정", "건기식", "의결서"}, (
        "조건 A · B · C 이고 유형이 있는 행만 든다"
    )
    assert (got["식품"]["층"], got["식품"]["품목"], got["식품"]["인정"]) == ("전제", "식품", False)
    assert (got["승인"]["층"], got["승인"]["전제"], got["승인"]["품목"]) == (
        "전제",
        "식품",
        "식품",
    ), "원천(건기식)이 아니라 전제(식품)다"
    assert (got["비인정"]["전제"], got["비인정"]["품목"], got["비인정"]["인정"]) == (
        "건기식_비인정",
        "건기식",
        False,
    )
    # 전제를 모르면 인정 여부를 적지 않는다 — 「아니오」와 「모름」을 합치지 않는다 (D-220)
    assert (got["건기식"]["층"], got["건기식"]["품목"], got["건기식"]["인정"]) == (
        "품목",
        "건기식",
        None,
    )
    assert (got["의결서"]["층"], got["의결서"]["품목"], got["의결서"]["인정"]) == (
        "참고",
        None,
        None,
    )
    assert got["식품"]["불가_사유"] == "B" and got["식품"]["정답_유형"] == ["거짓_과장"]


def test_층과_사유별로_센다() -> None:
    assert gi.counts(gi.gen_inputs(ROWS)) == {
        "전제 · 건기식_비인정": {"A": 1},
        "전제 · 식품": {"B": 1, "A": 1},
        "품목 · 건기식": {"C": 1},
        "참고 · 제품 정보 없음": {"B": 1},
    }


def test_전제_칸이_없는_판이면_멈춘다() -> None:
    """재동결 전 골든으로 품목만 보고 조용히 만들지 않는다 (D-220)."""
    with pytest.raises(SystemExit, match="전제"):
        gi.gen_inputs([{"id": "a", "text": "가", "품목": "식품", "조건": "B", "근거": [FTC]}])


def test_광고_문구가_든_출력은_build_밖에_쓰지_않는다(tmp_path) -> None:  # noqa: ANN001
    with pytest.raises(SystemExit, match="build"):
        gi.main(["--out", str(tmp_path / "x.jsonl")])
