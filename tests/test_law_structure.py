"""법령 · 조문형식 행정규칙의 **구조가 청크까지 오는가** (🆕 2026-09-28 · 사실원장 ㊴).

🔴 막는 것
   ① `<목>` 이 통째로 빠지는 것 — 법령 9건 목 159개가 청크 어디에도 없었다(화장품법 제2조제2호 기능성화장품의 범위 가~목 …)
   ② 가지번호 호 「3의2」가 「제3호」로 인용되는 것 — `<호가지번호>` 를 안 읽었다(법령 4건 63곳)
   ③ 조문형식 행정규칙의 조 본문이 한 덩이라 항 · 호가 안 서는 것 — 69549 제2조 11조각이 전부 「제2조」
   ④ 원문자 경로가 숫자로 읽혀 「[별표 2]제①호」가 되는 것 — `'①'.isdigit()` 은 참이다
🚨 원문은 합성이다 — 실물의 **모양**만 옮겼다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app import retrieve as rt
from preprocess import law_article as la

pytestmark = pytest.mark.gate

LAW = """<?xml version="1.0" encoding="UTF-8"?>
<법령><기본정보><법령명_한글>화장품법</법령명_한글></기본정보>
<조문>
<조문단위 조문키="0002001"><조문번호>2</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목>
<조문내용>제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.</조문내용>
<항>
<호><호번호>2.</호번호><호내용>2. "기능성화장품"이란 다음 각 목의 어느 하나에 해당되는 것을 말한다.</호내용>
<목><목번호>가.</목번호><목내용>가. 피부의 미백에 도움을 주는 제품</목내용></목>
<목><목번호>나.</목번호><목내용>나. 피부의 주름개선에 도움을 주는 제품</목내용></목>
</호>
<호><호번호>3.</호번호><호내용>3. 삭제</호내용></호>
<호><호번호>3.</호번호><호가지번호>2</호가지번호><호내용>3의2. "맞춤형화장품"이란 다음 각 목의 화장품을 말한다.</호내용>
<목><목번호>가.</목번호><목내용>가. 원료를 추가하여 혼합한 화장품</목내용></목>
</호>
</항>
</조문단위>
</조문></법령>
"""

ADM = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService><행정규칙기본정보><행정규칙명>부당한 표시 또는 광고의 내용 기준</행정규칙명><조문형식여부>Y</조문형식여부></행정규칙기본정보>
<조문내용>제1조(목적) 이 고시는 부당한 표시 또는 광고의 구체적인 내용을 예시한다.</조문내용>
<조문내용>제2조(부당한 표시 또는 광고의 내용) 부당한 표시 또는 광고 내용은 다음 각 호와 같다.
  1. 식품등을 의약품으로 인식할 우려가 있는 표시 또는 광고
    가. 한약의 처방명을 사용한 표시ㆍ광고
  2. 소비자를 기만하는 표시 또는 광고
    가. 사용하지 못하도록 정한 원재료가 없다는 표시ㆍ광고
       (예시) 김치류에 "색소 무첨가" 표시ㆍ광고
    나. 보존료가 없다는 표시ㆍ광고</조문내용>
<조문내용>제3조(정의) ① 이 고시에서 사용하는 용어의 뜻은 다음과 같다.
  1. "원재료"란 제조에 사용되는 물질이다.
② 제1항에서 정하지 않은 용어는 법에서 정한 바에 따른다.</조문내용>
</AdmRulService>
"""


def _parse(tmp_path: pathlib.Path, name: str, xml: str) -> list[dict]:
    p = tmp_path / name
    p.write_text(xml, encoding="utf-8")
    return la.parse(p)


def test_법령의_목은_호_본문에_잇고_가지번호_호는_의로_선다(tmp_path: pathlib.Path) -> None:
    rows = _parse(tmp_path, "law_002015_20260402.xml", LAW)
    hos = {r["호"]: r for r in rows if r.get("호")}
    assert set(hos) == {"2.", "3.", "3의2."}
    assert (
        "피부의 미백" in hos["2."]["본문"] and "주름개선" in hos["2."]["본문"]
    )  # ① 목이 빠지지 않는다
    assert "원료를 추가" in hos["3의2."]["본문"]
    assert hos["3."]["본문"] == "3. 삭제"  # 삭제 표지는 그대로(청킹이 뺀다)
    cite = {
        h: rt.citation({"doc_type": "법령", "article": "제2조", "item": h, "paragraph_no": 1})
        for h in hos
    }
    assert cite == {
        "2.": "제2조제1항제2호",
        "3.": "제2조제1항제3호",
        "3의2.": "제2조제1항제3호의2",
    }  # ② 둘이 갈린다


def test_조문형식_행정규칙은_항_호로_나뉘고_글이_사라지지_않는다(tmp_path: pathlib.Path) -> None:
    rows = _parse(tmp_path, "admrul_69549_20251204.xml", ADM)
    arts = [r for r in rows if "호" not in r and not r.get("항")]
    assert [r["키"] for r in arts] == [
        "adm-0",
        "adm-1",
        "adm-2",
    ]  # 🚨 조 행의 키는 종전 그대로 — 청크 ID 가 밀리지 않는다
    hos = [r for r in rows if r.get("호")]
    assert [(r["조"], r["호"]) for r in hos] == [("2", "1."), ("2", "2."), ("3", "1.")]
    two = next(r for r in hos if r["조"] == "2" and r["호"] == "2.")
    assert (
        "색소 무첨가" in two["본문"] and "보존료" in two["본문"]
    )  # 목 · (예시)는 호 본문에 잇는다
    assert "다음 각 호와 같다" in two["항본문"]  # 번호 없는 제1항 — 조 머리 문장이 문맥이다
    assert (
        rt.citation({"doc_type": "법령", "article": "제2조", "item": "2.", "paragraph_no": 1})
        == "제2조제1항제2호"
    )
    hangs = [(r["항"], r["항서수"]) for r in rows if r.get("항") and not r.get("호")]
    assert hangs == [("①", 1), ("②", 2)]  # 머리 줄 안의 「①」도 항이다
    whole = re.sub(r"\s+", "", "".join(r["본문"] for r in rows))
    for line in ADM.split("<조문내용>")[1:]:
        for x in line.split("</조문내용>")[0].split("\n"):
            assert re.sub(r"\s+", "", x) in whole  # 글이 사라지지 않는다


def test_마커가_없는_조는_종전처럼_한_행이다(tmp_path: pathlib.Path) -> None:
    rows = _parse(tmp_path, "admrul_69549_20251204.xml", ADM)
    first = [r for r in rows if r["조"] == "1"]
    assert len(first) == 1 and first[0]["키"] == "adm-0"


@pytest.mark.parametrize(
    ("path", "want"),
    [("①", None), ("1.①", None), ("2.가", "[별표 2]제2호가목"), ("머리", "[별표 2] 비고")],
)
def test_별표_인용은_ASCII_숫자만_호로_읽는다(path: str, want: str | None) -> None:
    section = "비고" if path == "머리" else "본문"
    got = rt.citation({"doc_type": "별표", "annex_no": 2, "item": section, "paragraph": path})
    assert got == want
