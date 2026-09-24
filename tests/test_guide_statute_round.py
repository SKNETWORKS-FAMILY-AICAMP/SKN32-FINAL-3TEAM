"""해설서 조문·조건 판의 채택 규칙 (D-285 · 지시서 09-24 §5).

🔴 무엇을 막나
   ① 두 판독이 다른데 채택되는 것 — 조건 · 호 집합 중 하나라도 다르면 사람 시트로
   ② 적용 제외 목이 근거로 들어오는 것 (D-238)
   ③ 한쪽만 본 예외가 실리는 것 — 제외목은 교집합
   ④ 모르는 꼴이 조용히 버려지는 것 (D-220)
"""

from __future__ import annotations

import pytest

from collect import statute
from scripts import guide_statute_round as g


def _r(prim="5.다", sec="-", cond="C", exc="-", gap="N"):
    return g.parse_line(f"gs:x\t{prim}\t{sec}\t{cond}\t{exc}\t{gap}\t")


@pytest.mark.gate
def test_같으면_채택하고_목이_같으면_남긴다() -> None:
    got, why = g.agree(_r(), _r())
    assert why == "" and got["근거"] == [statute.food(5, "다")] and got["조건"] == "C"


@pytest.mark.gate
def test_목이_다르면_호까지만() -> None:
    got, _ = g.agree(_r("5.다"), _r("5.라"))
    assert got["근거"] == [statute.food(5)]


@pytest.mark.gate
def test_조건이나_호가_다르면_시트로() -> None:
    assert g.agree(_r(cond="B"), _r(cond="M"))[0] is None
    assert g.agree(_r("4.라"), _r("3"))[0] is None
    assert g.agree(_r("4", "5"), _r("6"))[0] is None  # 전혀 안 겹치면 시트


@pytest.mark.gate
def test_제외목은_둘_다_적은_것만() -> None:
    got, _ = g.agree(_r("3", cond="A", exc="3.라,1.가.1"), _r("3", cond="A", exc="3.라"))
    assert got["제외목"] == ["3.라"]


@pytest.mark.gate
def test_주장_아님은_근거가_빈다() -> None:
    got, _ = g.agree(_r("-", cond="D"), _r("3", cond="D"))
    assert got["근거"] == [] and got["제외목"] == []


@pytest.mark.gate
def test_원천결손이나_판독_문제는_시트로() -> None:
    assert g.agree(_r("-", cond="D", gap="Y"), _r("5.다", cond="C"))[0] is None  # 갈리면 시트 (④′)
    assert (
        g.agree(_r("3.라", cond="A"), _r("3", cond="A"))[0] is None
    )  # 적용 제외 목이 근거 (D-238)
    assert g.agree(_r("기타:별표6-3.가"), _r("기타:별표6-3.가"))[0] is None
    assert g.agree(_r(cond="X"), _r(cond="X"))[0] is None
    assert g.agree(_r("-", cond="C"), _r("-", cond="C"))[0] is None  # C·A·B 는 근거가 있어야 한다


@pytest.mark.gate
def test_법8조_9_10호도_인용으로() -> None:
    assert g.cite_of("법8-10") == statute.food(10)
    with pytest.raises(ValueError):
        g.cite_of("9")  # [별표 1] 에 9호는 없다 — 법 호는 `법8-9` 로


@pytest.mark.gate
def test_M_은_호를_추측으로_채우지_않는다() -> None:
    """🔄 D-285 개정 — 둘 다 M 이면 같다 · 호는 둘이 같을 때만 남는다."""
    got, _ = g.agree(_r("-", cond="M"), _r("4", cond="M"))
    assert got["조건"] == "M" and got["근거"] == []
    got, _ = g.agree(_r("6", cond="M"), _r("6", cond="M"))
    assert got["근거"] == [statute.food(6)]
    got, _ = g.agree(_r("3", cond="M"), _r("4", cond="M"))
    assert got["근거"] == []


@pytest.mark.gate
def test_조제유류_목과_3나_유형_게이트가_있다() -> None:
    """🔴 제품유형에 달린 목은 합의만으로 채택하지 않는다 — 3.나 는 유형 9 만 (D-288) · 5.바·5.사 는 조제유류만."""
    assert g.NA_TYPES == ("9.",)
    assert (5, "사") in g.FORMULA_MOK and (5, "바") in g.FORMULA_MOK


@pytest.mark.gate
def test_겹치는_호만_남긴다() -> None:
    """🔄 09-24 밤 — 한쪽이 부근거를 더 적었으면 둘 다 적은 호만 (지시서 §5)."""
    got, _ = g.agree(_r("3", "4.라"), _r("3"))
    assert got["근거"] == [statute.food(3)]


@pytest.mark.gate
def test_원천결손은_둘_다_D_면_채택한다() -> None:
    """🔄 09-24 밤 — 블록 제목은 D · 원천결손으로 남는다. 판정 대상 아님이지 적법이 아니다 (지시서 §7 선행 게이트)."""
    got, _ = g.agree(_r("-", cond="D", gap="Y"), _r("-", cond="D"))
    assert got["조건"] == "D" and got["원천결손"] is True and got["근거"] == []
