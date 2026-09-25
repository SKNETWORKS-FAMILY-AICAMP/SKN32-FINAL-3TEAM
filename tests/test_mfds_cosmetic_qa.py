"""질의응답집 추출기 — 문항 경계 · 관련규정 인용 · 목차 대조 (2026-09-25).

🚨 원문 PDF 는 저장소에 없다(CI) — 실제 문서에서 본 **모양**을 합성 쪽으로 옮겨 대조한다.
   실측(클론 B 원문 · 작업공간): 123문항 · 목차와 분야별 수 · 번호 · 쪽 전부 일치 · 관련규정 123/123.
"""

from __future__ import annotations

import pytest

from preprocess import mfds_cosmetic_qa as qa

#: 목차 — 🚨 실물처럼 옆 칸 글자(「분 야」)가 표지 앞에 붙고, 제목이 줄을 넘는다
TOC = "\n".join(
    [
        "1. 의약품 오인 우려 광고",
        "화장품",
        "Q1. 보톡스 관련 광고 4",
        "분 야 Q2. 코스메슈티컬, 더마코스메틱 등의 표현 사용 4",
        "Q3. 수입 화장품 광고에 영문 브로슈어를 번역본 사용 가능",
        "여부 5",
        "[참고 1] 화장품 광고 관련 법령 등 6",
    ]
)
BODY_4 = "\n".join(
    [
        "화장품･의료기기･의약외품 허위･과대광고 질의응답집",
        "1. 의약품 오인 우려 광고",
        "Q1 패치류 화장품에 ‘보톡스 주사 대신 붙이면~’ 이라는 내용의 광고가 가능한지?",
        "해당 광고 표현의 경우 의약품으로 잘못 인식할 우려가 있는 광고에 해당함",
        "관련규정",
        "「화장품법」 제13조제1항제1호",
        # 🚨 다음 문항의 질의가 **표지 앞에서** 시작한다
        "책임판매업자가 제약회사로 등록되어 있거나, 기술제휴로 만들어진 화장품에",
        "Q2",
        "대해서도 ‘코스메슈티컬’로 광고 불가한가요?",
        "그 자체로 오인 우려가 있다고 보기는 어려울 것이나 ‘더마’ 광고는 저촉됨",
        "관련규정",
        "「화장품법」 제13조제1항제1호, 제4호 및 제14조제1항",
        "04",
    ]
)
BODY_5 = "\n".join(
    [
        "Ⅰ. 화장품 분야",
        "Q3 수입 화장품 광고에 번역본을 써도 되는지?",
        "‘천연’ 표현은 사실과 다르면 저촉됨",
        "관련규정",
        "「화장품법｣ 제13조1항제4호",  # 🚨 반각 닫는 괄호 · 항 앞 「제」 빠짐 — 둘 다 실측
        "05",
    ]
)
APPENDIX = "\n".join(
    [
        "화장품･의료기기･의약외품 허위･과대광고 질의응답집",
        "참고 1 화장품 광고 관련 법령 등",
        "Q9 여기는 담지 않는다?",
        "06",
    ]
)
PAGES = ["", TOC, "Ⅰ. 화장품 분야", "1. 의약품 오인 우려 광고", BODY_4, BODY_5, APPENDIX]


@pytest.mark.gate
def test_목차는_옆칸_글자와_줄넘김을_견딘다() -> None:
    got, chapters = qa.toc(PAGES)
    assert [(f, q, p) for f, q, _, p in got] == [
        ("화장품", 1, 4),
        ("화장품", 2, 4),
        ("화장품", 3, 5),
    ]
    assert got[2][2].endswith("사용 가능 여부")
    assert chapters == ["1. 의약품 오인 우려 광고"]


@pytest.mark.gate
def test_문항은_관련규정에서_끝나고_표지_앞_질의는_다음_문항으로_간다() -> None:
    rows, stat = qa.parse(PAGES)
    assert [r["문항"] for r in rows] == [1, 2, 3]
    q2 = rows[1]
    assert q2["질의"].startswith("책임판매업자가") and q2["질의"].endswith("불가한가요?")
    assert q2["답변"].startswith("그 자체로")
    assert "책임판매업자가" not in rows[0]["답변"]
    assert rows[0]["쪽"] == 4 and rows[2]["쪽"] == 5
    assert rows[0]["장"] == "1. 의약품 오인 우려 광고"
    assert stat["관련규정_없음"] == [] and stat["질의_물음표_없음"] == []


@pytest.mark.gate
def test_부록_참고_1_부터는_담지_않는다() -> None:
    rows, stat = qa.parse(PAGES)
    assert all(r["문항"] != 9 for r in rows)
    assert stat["부록에서_멈춘_쪽"] == [6]


@pytest.mark.gate
def test_관련규정은_위반_조항의_호만_인용이_된다() -> None:
    cite, other = qa.cites("「화장품법」 제13조제1항제1호, 제4호 및 제14조제1항")
    assert cite == ["002015:제13조제1항제1호", "002015:제13조제1항제4호"]
    assert other == ["「화장품법」 제14조제1항"]
    # 🔴 제2조(정의)의 「제9호」는 위반 호가 아니다 (D-220)
    cite, other = qa.cites("「화장품법」 제2조제9호")
    assert cite == [] and other == ["「화장품법」 제2조제9호"]
    # 반각 괄호 · 항 앞 「제」 빠짐 · 가운뎃점 변이
    assert qa.cites("「화장품법｣ 제13조1항제4호")[0] == ["002015:제13조제1항제4호"]
    assert qa.cites("「표시･광고의 공정화에 관한 법률」 제3조제1항제1호")[0] == [
        "002011:제3조제1항제1호"
    ]
    # 시행규칙 [별표5] 목 · 다른 법 — 인용으로 만들지 않고 원문을 남긴다
    cite, other = qa.cites("「화장품법 시행규칙」 [별표5] 제2호다목")
    assert cite == [] and other


@pytest.mark.gate
def test_기준시점과_판정지위가_레코드마다_있다() -> None:
    rows, _ = qa.parse(PAGES)
    for r in rows:
        assert r["기준시점"] == "2020-12" and r["판정지위"] == "질의회신"
    assert rows[0]["인용표현"] == ["보톡스 주사 대신 붙이면~"]


@pytest.mark.gate
def test_목차와_어긋나면_검증이_실패한다() -> None:
    assert qa.verify(PAGES) == []
    broken = [*PAGES[:5], BODY_5.replace("Q3 ", "Q4 "), APPENDIX]
    assert qa.verify(broken)


@pytest.mark.gate
def test_문항에_붙지_않은_글이_남으면_멈춘다() -> None:
    tail = BODY_5.replace("05", "문항 없이 남은 글\n05")
    with pytest.raises(ValueError, match="붙지 않은 글"):
        qa.parse([*PAGES[:5], tail])
    # 🚨 부록이 시작될 때도 — 부록 앞에서 조용히 버리지 않는다
    with pytest.raises(ValueError, match="붙지 않은 글"):
        qa.parse([*PAGES[:5], tail, APPENDIX])
