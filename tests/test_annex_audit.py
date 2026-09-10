"""[별표] 파싱 감사가 **실패할 수 있는지**를 본다 (S2-04 · D-98 개정 · D-170).

🚨 이 파일의 요점은 「감사가 통과한다」가 아니다. 2026-09-09 현재 실제 데이터에서
   감사는 신호 0 으로 통과한다 — 그러면 **「잘 돼서 0」인지 「못 잡아서 0」인지
   구분되지 않는다.** D-170 이 그 자리다(「실패할 수 없는 단언은 단언이 아니다」).
   그래서 여기서는 조작한 행을 넣어 **감사가 실제로 무너지는지**를 확인한다.

🚨 오탐 통제도 함께 둔다. 2026-09-09 실측 — 「처분 칸에 글자가 있는데 sanctions 가 비었다」가
   243행 중 54행인데 **54행 전부가 과징금·과태료·수수료·영양성분 별표**다. 처분 종류가
   없는 표라 못 읽은 게 아니라 읽을 것이 없다. 이걸 잡으면 감사는 오탐 54건으로 시작하고,
   오탐으로 시작한 검사는 곧 꺼진다.
"""

from __future__ import annotations

import pytest

from scripts.annex_audit import judge, measure

SANCTION = "행정처분의 기준(제29조제1항 관련)"
LEVY = "과태료의 부과기준(제17조제1항 관련)"


def _row(title: str, *, cells: list[str], sanctions: list, article: str = "법 제24조제1항") -> dict:
    return {
        "law_id": "008741",
        "kind": "별표",
        "annex_no": "0007",
        "annex_branch": "00",
        "title": title,
        "article": article,
        "article_inherited": False,
        "sanctions": sanctions,
        "fragments": [["위반내용"], ["조문"], *[[c] for c in cells]],
    }


def _base(rows: int, title: str = SANCTION) -> dict:
    return {"008741_별표_0007_00": {"title": title, "rows": rows}}


@pytest.mark.gate
def test_처분칸에_글자가_있는데_못_읽으면_실패한다() -> None:
    """「식품 [별표 7] 처분 칸 197개 중 160개를 못 잡았다」가 재발하는 자리다."""
    rows = [_row(SANCTION, cells=["영업정지 1개월"], sanctions=[])]
    bad = judge(measure(rows), _base(1))
    assert bad, "처분 칸에 글자가 있는데 sanctions 가 비었는데도 감사가 통과했다"
    assert any("못 읽은" in b for b in bad), bad


@pytest.mark.gate
def test_처분칸이_비어_있으면_실패하지_않는다() -> None:
    """상위 항목 행(가. 나. 다.)은 처분 칸이 원래 비어 있다 — 오탐이면 안 된다."""
    rows = [_row(SANCTION, cells=["", "", ""], sanctions=[])]
    assert not judge(measure(rows), _base(1))


@pytest.mark.gate
def test_과징금_별표는_처분이_없어도_실패하지_않는다() -> None:
    """실측 54행이 여기다. 처분 종류가 없는 표에 처분을 요구하면 오탐이 된다 (D-167)."""
    rows = [_row(LEVY, cells=["1천만원"], sanctions=[])]
    assert not judge(measure(rows), _base(1, LEVY))


@pytest.mark.gate
def test_상속_후에도_조문이_없으면_실패한다() -> None:
    """조문 없는 처분 행은 4층 라벨이 근거를 잃는다."""
    rows = [_row(SANCTION, cells=["시정명령"], sanctions=[{"action": "시정명령"}], article="")]
    bad = judge(measure(rows), _base(1))
    assert any("조문" in b for b in bad), bad


@pytest.mark.gate
def test_행이_줄면_실패한다() -> None:
    """감사의 본체다 — 지금 값이 깨끗해도 다음 수집에서 조용히 줄어드는 것을 잡는다."""
    rows = [_row(SANCTION, cells=["시정명령"], sanctions=[{"action": "시정명령"}])]
    bad = judge(measure(rows), _base(71))
    assert any("줄었다" in b for b in bad), bad


@pytest.mark.gate
def test_기준선에_없는_별표는_실패한다() -> None:
    """법이 개정돼 별표가 생기면 사람이 한 번 보고 등재한다 (fail-closed · D-72)."""
    rows = [_row(SANCTION, cells=["시정명령"], sanctions=[{"action": "시정명령"}])]
    bad = judge(measure(rows), {})
    assert any("기준선에 없다" in b for b in bad), bad


@pytest.mark.gate
def test_별표가_통째로_사라지면_실패한다() -> None:
    """🔴 **「줄면 실패」인데 100% 줄면 통과했다** (2026-09-10 · D-149).

    ⛔ `judge()` 가 `stats`(이번에 읽은 것)만 순회해서, 기준선에 있고 산출물에 없는
       별표는 **비교 대상 자체가 없어** 아무 줄도 안 남겼다.
       한 행이 줄면 잡고 **전 행이 사라지면 통과**하는 감사였다.
    """
    bad = judge({}, _base(71))

    assert bad, "기준선에 있던 별표가 통째로 사라졌는데 감사가 통과했다"
    assert "008741_별표_0007_00" in bad[0]
    assert "71행 → 0" in bad[0] or "71" in bad[0]


@pytest.mark.gate
def test_반대_대조_기준선과_산출물이_같으면_통과한다() -> None:
    """🚨 위 게이트가 **아무 때나 실패하는 것**이 아님을 보인다 (D-170).

    오탐으로 시작한 검사는 곧 꺼진다 — 이 파일 머리말이 적어 둔 그대로다.
    """
    rows = [_row(SANCTION, cells=["가"], sanctions=[{"처분": "영업정지"}])]
    assert not judge(measure(rows), _base(1))
