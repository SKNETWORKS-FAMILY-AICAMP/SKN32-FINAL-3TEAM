"""[별표] 산문 파서가 **틀릴 수 있는지**를 본다 (D-170).

⛔ 2026-09-09 실측 — 013453 [별표 1] 은 8호까지가 위법 유형이고 그 뒤에 「비고」가 붙어
   **「부당한 표시·광고로 보지 않는다」는 적용 제외 2호**가 온다. 번호가 1 부터 다시 시작한다.
   구역을 안 가르면 **「식품접객업 영업소의 표시·광고」가 위법 유형 1호로 읽힌다.**
   판정을 정확히 뒤집는 오류다 (D-153 · D-156).

⛔ 그리고 구역 이름을 잡는 조건이 **「비고」를 먹었다** — 「…표시ㆍ광고」로 끝나는 줄을
   거르려고 `endswith("고")` 를 넣었는데 「비고」가 그 조건에 걸렸다. 오늘 여섯 번째
   「부분문자열·문자 모양으로 헛디딘」 건이다.
"""

from __future__ import annotations

import collections

import pytest

from preprocess.law_norm import parse

BIGO = """■ 식품 등의 표시ㆍ광고에 관한 법률 시행령 [별표 1]
  부당한 표시 또는 광고의 내용(제3조제1항 관련)
  1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 다음 각 목의 표
  시 또는 광고
    가. 질병군의 발생을 예방한다는 내용의 표시ㆍ광고
  2. 식품등을 의약품으로 인식할 우려가 있는 표시 또는 광고
  비고
  제1호 및 제3호에도 불구하고 다음 각 호는 부당한 표시 또는 광고로 보지 않는다.
  1. 식품접객업 영업소에서 조리ㆍ판매하는 식품에 대한 표시ㆍ광고
  2. 영업신고 대상에서 제외되는 경우로서 위생상 위해가 없는 표시ㆍ광고
"""


@pytest.mark.gate
def test_비고는_본문과_다른_구역이다() -> None:
    """적용 제외가 위법 유형으로 읽히면 판정이 정확히 뒤집힌다."""
    nodes = parse(BIGO)
    tops = [n for n in nodes if n["level"] == 1]
    body = [n for n in tops if n["section"] == "본문"]
    assert len(body) == 2, [(n["section"], n["lines"][0]) for n in tops]
    exempt = [n for n in tops if n["section"] != "본문"]
    assert len(exempt) == 2, exempt
    assert all("식품접객업" not in "".join(n["lines"]) for n in body)


@pytest.mark.gate
def test_구역_이름이_비고를_먹지_않는다() -> None:
    """`endswith("고")` 로 거르면 「비고」가 걸린다 — 실제로 걸렸다."""
    sections = {n["section"] for n in parse(BIGO)}
    assert "비고" in sections, sections


@pytest.mark.gate
def test_구역_안에서_path_가_유일하다() -> None:
    """구역을 안 가르면 여기서 1·2 가 겹친다."""
    dup = [
        k
        for k, v in collections.Counter((n["section"], n["path"]) for n in parse(BIGO)).items()
        if v > 1
    ]
    assert not dup, dup


@pytest.mark.gate
def test_이어지는_줄은_새_노드를_만들지_않는다() -> None:
    """고정폭으로 접힌 줄이 노드가 되면 한 조항이 둘로 쪼개진다."""
    nodes = parse(BIGO)
    first = next(n for n in nodes if n["level"] == 1)
    assert len(first["lines"]) == 2, first["lines"]
    assert "".join(x.strip() for x in first["lines"]).endswith("표시 또는 광고")


@pytest.mark.gate
def test_깊이는_마커_모양이_정한다() -> None:
    """들여쓰기로 정하면 안 된다 — 이어지는 줄의 들여쓰기가 마커 줄과 같다."""
    levels = {n["marker"]: n["level"] for n in parse(BIGO)}
    assert levels["1"] == 1
    assert levels["가"] == 2
