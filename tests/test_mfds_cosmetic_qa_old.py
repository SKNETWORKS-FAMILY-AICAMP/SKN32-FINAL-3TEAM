"""옛 화장품 질의응답집 둘의 추출기 — 2012 질의·응답집 · 2020 자주하는 질문집 (2026-10-03).

🚨 원문 PDF 는 저장소에 없다(CI) — 실제 문서에서 본 **모양**을 합성 쪽으로 옮겨 대조한다.
   실측(클론 B 원문 · 작업공간): 2012 문항 130(표시광고 장 62) · 2020 문항 235(광고 범위 30) · 둘 다 목차 대조 통과.
"""

from __future__ import annotations

import pytest

from preprocess import mfds_cosmetic_faq_2020 as faq
from preprocess import mfds_cosmetic_qa_2012 as old

RUN = "화장품의약외품 표시광고 등 질의응답집"

#: 2012 — 목차 · 편 표지 · 장 표지(세 줄) · 머리글 + 제목 + 「문 N」 + 날짜 + 「회신」 · 답변이 쪽을 넘는다 · 판권면
PAGES_2012 = [
    "2012년\n화장품 의약외품 표시 광고 등\n질의 응답집\n- 2012.2월 -",
    "목 차\n일러두기\nⅠ. 화장품\n1. 화장품 표시광고 : 일반사항\n"
    "○ 건선에 효과·····················2\n○ 무( )보존제···················4\n"
    "2. 화장품 품목분류 : 화장품 해당여부\n○ 고형비누···················5\n"
    "Ⅱ. 의약외품\n1. 의약외품 표시광고 : 일반사항\n○ 가글류 광고 문구···········6",
    "일러두기\n이 질의응답집은 민원회신(공문 또는 인터넷\n회신)을 종합하여 정리한 것으로 참고용입니다.\n배열 순서는 가나다순입니다.",
    "Ⅰ. 화 장 품",
    "화장품\n일반사항\n표시 광고",
    f"{RUN} 2\n건선에 효과\n문 1 다음 표현이 의약품 오인 우려 광고인지 여부\n'거칠거\n칠한 피부'\n2011/04/07\n회신\n"
    "「화장품법」제12조에 따라 오인될 우려가",
    f"{RUN} 3\n있는 광고를 하지 말아야 합니다. 문의는 02-6000-1851 로 하십시오.",
    f'{RUN} 4\n무( )보존제\n문 2 "무보존제" 표시 가능한지?\n2010/4/15\n회신\n객관적 증거자료가 있다면 가능합니다.',
    "화장품\n화장품 해당여부\n품목분류",
    f"{RUN} 5\n고형비누\n문 3 고형비누가 화장품인지?\n2011/01/02\n회신\n화장품이 아닙니다.",
    "Ⅱ. 의약외품",
    "의약외품\n일반사항\n표시 광고",
    f"{RUN} 6\n가글류 광고 문구\n문 1 '구취 제거' 광고 가능한지?\n회신\n허가 범위 안에서 가능합니다.",
    f"{RUN} 7\n● 발행인 : 바이오생약국장 홍길동\n● 편집위원 : 김철수",
]


@pytest.mark.gate
def test_2012_문항은_새_쪽에서_시작하고_장은_표지_쪽이_넘긴다() -> None:
    assert old.verify(PAGES_2012) == []
    rows, stat = old.parse(PAGES_2012)
    assert [(r["편"], r["문항"], r["제목"], r["쪽"]) for r in rows] == [
        ("화장품", 1, "건선에 효과", 2),
        ("화장품", 2, "무( )보존제", 4),
        ("화장품", 3, "고형비누", 5),
        ("의약외품", 1, "가글류 광고 문구", 6),
    ]
    assert [r["광고장"] for r in rows] == [True, True, False, True]
    # 답변이 쪽을 넘는다 · 전화번호는 추출기가 바꾼다 · 한 자리 달 · 날을 편다
    assert rows[0]["답변"].endswith("문의는 [전화] 로 하십시오.") and stat["전화"] == 1
    assert rows[0]["회신일"] == "2011-04-07" and rows[1]["회신일"] == "2010-04-15"
    assert rows[0]["질의"].startswith("다음 표현이") and "2011/04/07" not in rows[0]["질의"]
    # 날짜가 없는 문항은 멈추지 않고 계측에 올린다
    assert rows[3]["회신일"] is None and stat["날짜_없음"] == [("의약외품", 1)]
    for r in rows:
        assert r["기준시점"] == "2012-02" and r["판정지위"] == "질의회신"  # D-240 · D-290 ③
        assert "관련규정_인용" not in r  # 🚨 2010 화장품법의 조문 번호를 지금 번호로 읽지 않는다


@pytest.mark.gate
def test_줄넘김은_좌표가_붙이라_한_줄만_붙인다() -> None:
    """🚨 낱말 한가운데서 넘은 줄(「거칠거/칠한」)은 붙고, 좌표 없는 합성 글은 빈칸으로 남는다 — 인용 문구가 깨지지 않는다."""
    from preprocess.pdf_lines import Line, as_lines

    rows, _ = old.parse(PAGES_2012)
    assert rows[0]["질의"].endswith("'거칠거 칠한 피부'")
    pages = [as_lines(p) for p in PAGES_2012]
    pages[5] = [Line(s, glue=(s == "'거칠거")) for s in pages[5]]
    rows, _ = old.parse(pages)
    assert rows[0]["질의"].endswith("'거칠거칠한 피부'")
    assert "거칠거칠한 피부" in rows[0]["인용표현"]
    # 2020 — 답변의 글머리표를 떼면서도 붙는다
    pages = [as_lines(p) for p in PAGES_2020]
    pages[5] = [Line(s, glue=s.endswith("바람직하지 않")) for s in pages[5]]
    rows, _ = faq.parse(pages)
    assert rows[3]["답변"] == "‘소독’ 표현은 바람직하지 않습니다."


@pytest.mark.gate
def test_2012_판권면과_일러두기는_담지_않는다() -> None:
    rows, _ = old.parse(PAGES_2012)
    blob = str(rows)
    assert "홍길동" not in blob and "김철수" not in blob and "가나다순" not in blob


@pytest.mark.gate
def test_2012_목차와_어긋나면_검증이_실패한다() -> None:
    # 문항 하나가 빠진다
    assert any("장별 문항 수" in b for b in old.verify([*PAGES_2012[:7], *PAGES_2012[8:]]))
    # 제목이 목차와 다르다
    wrong = [p.replace("\n고형비누\n문 3", "\n물비누\n문 3") for p in PAGES_2012]
    assert any("목차 「고형비누」" in b for b in old.verify(wrong))
    # 「회신」이 없다 — 질의와 답변을 못 가른다
    lost = [p.replace("2011/01/02\n회신\n", "2011/01/02\n") for p in PAGES_2012]
    assert any("회신_없음" in b for b in old.verify(lost))
    # 장 표지가 목차의 장보다 많다
    extra = [*PAGES_2012[:12], "의약외품\n제조 수입 등\n기타사항", *PAGES_2012[12:]]
    assert old.verify(extra)


#: 2020 — 머리말(전화) · 목차 · 편은 목차의 쪽으로 · 절은 목차가 말한 쪽의 「N. 제목」 줄 · 「□」 소제목 · 「¡」 답변
PAGES_2020 = [
    "본 안내서에 대한 문의\n전화번호: 043-719-3402, 팩스번호: 043-719-3400",
    "목 차\nⅠ. 화장품 업 등록 관련 ················1\n1. 업 등록 ··················1\n"
    "Ⅳ. 광고 ················3\n1. 질병 및 의학적 효능·효과 관련 ··········4\n"
    "2. 우수화장품 제조 및 품질관리기준(CGMP) 인증 ·········4\nⅤ. 제품 분류 ·············5\n참고문헌 ············6",
    "1. 업 등록\n& 관련 조항 화장품법 제3조(영업의 등록)\n1. 제조 작업을 하는 시설\n□ 제조업 등록 대상\nQ1\n"
    "화장품을 만들려면 등록이 필요한가요?\n¡ 등록이 필요합니다.\n- 지방식약청에 등록합니다.\n- 1 -",
    "Q2\n소분도 등록 대상인가요? (예) 10mL 로 나눔\n¡ 대상입니다. 협회(02-2162-8051)로 문의하십시오.\n- 2 -",
    "Ⅳ 광고\n& 관련 조항 화장품법 제13조\nQ3\n광고할 때 무엇을 주의하나요?\n¡ 「화장품법」 제13조를 봅니다.\n- 3 -",
    "1. 질병 및 의학적 효능·효과 관련\nQ4\n‘소독’ 이라는 단어를 써도 되나요?\n¡ ‘소독’ 표현은 바람직하지 않\n습니다.\n"
    "2. CGMP 인증\nQ5\n인증 사실을 광고해도 되나요?\n¡ 가능합니다.\n- 4 -",
    "□ 비누\nQ6\n고형비누는 화장품인가요?\n¡ 화장품입니다.\n- 5 -",
    "Q7\n물티슈는요?\n¡ 화장품입니다.\n[참고 문헌]\n2014년 1분기 자주하는 질문(FAQ)집, 2014.3.28.\n- 6 -",
]


@pytest.mark.gate
def test_2020_편은_목차의_쪽으로_절은_목차가_말한_쪽의_줄로_정한다() -> None:
    assert faq.verify(PAGES_2020) == []
    rows, stat = faq.parse(PAGES_2020)
    assert [(r["문항"], r["편"], r["절"], r["소제목"], r["쪽"]) for r in rows] == [
        (1, "Ⅰ. 화장품 업 등록 관련", "1. 업 등록", "제조업 등록 대상", 1),
        (2, "Ⅰ. 화장품 업 등록 관련", "1. 업 등록", "제조업 등록 대상", 2),
        (3, "Ⅳ. 광고", None, None, 3),  # 🚨 절 앞의 총론 문항
        (4, "Ⅳ. 광고", "1. 질병 및 의학적 효능·효과 관련", None, 4),
        # 🚨 본문이 절 제목을 줄여 적는다 — 「CGMP 인증」
        (5, "Ⅳ. 광고", "2. 우수화장품 제조 및 품질관리기준(CGMP) 인증", None, 4),
        (6, "Ⅴ. 제품 분류", None, "비누", 5),
        (7, "Ⅴ. 제품 분류", None, "비누", 6),
    ]
    # 🚨 「1. 제조 작업을 하는 시설」은 절이 아니다(법령 전재 상자) — 문항 앞의 줄로 세고 담지 않는다
    assert stat["문항_앞_줄"] == 3 and "제조 작업" not in str(rows)
    assert rows[0]["질의"] == "화장품을 만들려면 등록이 필요한가요?"
    assert rows[0]["답변"] == "등록이 필요합니다. - 지방식약청에 등록합니다."
    assert rows[3]["인용표현"] == ["소독"]
    # 답변이 광고 금지 조문을 드는가 — 범위 밖 문항의 추가 후보를 가른다
    assert [r["광고조문"] for r in rows] == [False, False, True, False, False, False, False]


@pytest.mark.gate
def test_2020_광고_범위는_절_제목으로_정하고_머리말과_참고문헌은_담지_않는다() -> None:
    rows, stat = faq.parse(PAGES_2020)
    assert [r["문항"] for r in rows if r["광고범위"]] == [3, 4, 5]
    blob = str(rows)
    assert "043-719" not in blob and "2014년 1분기" not in blob
    # 본문의 전화번호는 추출기가 바꾼다 — 마스킹 축에 전화가 없다
    assert "협회([전화])" in rows[1]["답변"] and stat["전화"] == 1
    # 물음 뒤에 덧글이 붙어도 질의다
    assert rows[1]["질의"].endswith("(예) 10mL 로 나눔") and not stat["질의_물음표_없음"]
    for r in rows:
        assert r["기준시점"] == "2020-12" and r["판정지위"] == "질의회신"


@pytest.mark.gate
def test_2020_목차와_어긋나면_검증이_실패한다() -> None:
    # 절 제목 줄이 사라진다 — 절을 지어내지 않는다 (D-220)
    lost = [p.replace("2. CGMP 인증\n", "") for p in PAGES_2020]
    assert any("못_찾은_절" in b for b in faq.verify(lost))
    # 문항 번호가 건너뛴다
    skip = [p.replace("Q6\n", "Q8\n") for p in PAGES_2020]
    assert any("이어지지 않는다" in b for b in faq.verify(skip))
    # 답변 표지가 없다
    mute = [p.replace("¡ 화장품입니다.\n- 5 -", "화장품입니다.\n- 5 -") for p in PAGES_2020]
    assert any("답변_없음" in b for b in faq.verify(mute))
    # 쪽 번호가 없다 — 편을 못 정한다
    assert faq.verify([p.replace("- 5 -", "") for p in PAGES_2020])


@pytest.mark.gate
def test_마스킹_정책은_레지스트리_문언의_축이다() -> None:
    from preprocess.mask import POLICY

    assert POLICY[old.SOURCE_ID] == frozenset({"org", "brand"})
    assert POLICY[faq.SOURCE_ID] == frozenset({"org"})
    rows, _ = faq.parse(PAGES_2020)
    out, _, _ = faq.masked(rows)
    assert [r["문항"] for r in out] == [r["문항"] for r in rows]
    rows, _ = old.parse(PAGES_2012)
    out, _, _ = old.masked(rows)
    assert len(out) == len(rows) and all("인용표현" in r for r in out)
