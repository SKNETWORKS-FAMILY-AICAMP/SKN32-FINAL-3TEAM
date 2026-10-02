"""화장품 표시·광고 관리 지침 추출기 — 항목 단위 · 쪽 넘김 · 단서 · 구조 대조 (2026-10-03).

🚨 원문 PDF 는 저장소에 없다(CI) — 실제 문서에서 본 **모양**을 합성 표로 옮겨 대조한다.
   실측(클론 B 원문 · 작업공간): [별표 1] 85(제1호 54 · 제2호 6 · 제4호 25) · [별표 2] 20 · 구조 대조 통과.
"""

from __future__ import annotations

import pytest

from preprocess import mfds_cosmetic_guideline as cg

HEAD_1 = ["구 분", "금 지 표 현", "비 고"]
HEAD_2 = ["구 분", "실증 대상", "비 고"]


def _page(lines: list[str], *tables: list[list]) -> dict:
    return {"줄": lines, "표": list(tables)}


#: 🚨 실물처럼 — 구분 칸은 첫 행에만 있고(병합 칸), 한 칸에 항목이 여럿이고, 줄이 낱말 한가운데서 넘는다
PAGES = [
    _page(["담당자 홍길동", "- 2 -"], [["등록대상", "점검표"]]),  # 별표 앞 — 담지 않는다
    _page(
        [
            "[별표 1]",
            "화장품 표시·광고의 표현 범위 및 기준",
            "□ 화장품법 제13조 제1항 제1호 관련",
            "- 9 -",
        ],
        [
            HEAD_1,
            ["질병을 진단·\n치료 관련", "· 아토피\n· 모낭충", ""],
            [None, "· 여드름", "단, 기능성화장품의 심사(보고)된\n‘효능효과’ 표현은 제외"],
            [None, "· 메디슨(medicine), 코스\n메슈티컬, 약용 등을\n사용한 표현", ""],
        ],
    ),
    _page(
        ["□ 화장품법 제13조 제1항 제2호 관련", "- 12 -"],
        [
            HEAD_1,
            [
                "기능성 관련\n표현",
                "· 심사하지 아니한 제품에 미백 표현\n· 심사 결과와 다른 내용",
                "단, 공통 단서",
            ],
        ],
    ),
    _page(
        ["□ 화장품법 제13조 제1항 제4호 관련", "- 13 -"],
        [
            HEAD_1,
            [
                "인체 유래 성분\n관련 표현",
                "· 줄기세포가 들어 있는 것으로 오인할 수 있는 표현\n<예시> 줄기세포 화장품, stem\ncell 등\n· 특정성분(엑소\n좀, 줄기세포)이 들어 있는 것으",
                "․식물 등 인체 외에서 유래한 경우\n에는 제외",
            ],
        ],
    ),
    _page(
        ["- 14 -"],
        [
            HEAD_1,
            # 🚨 앞 쪽 마지막 항목이 넘어왔다 — 구분이 비고 가운뎃점으로 시작하지 않는다
            ["", "로 오인할 수 있는 표현\n<예시> 엑소좀 화장품 등", ""],
            ["저속한 표현", "· 성생활 암시 표현\n- 여성크림\n- 쾌감을 증대시킨다.", ""],
        ],
    ),
    _page(
        ["[별표 2]", "화장품 표시․광고 주요 실증대상", "- 15 -"],
        [
            HEAD_2,
            [
                "1. 고시 별표에\n따른 표현",
                "· 붓기 완화\n· 다크서클 완화",
                "․인체 적용시험 자료로 입증",
            ],
            [None, "· 빠지는 모발을 감소시킨다.", "· 기능성화장품으로서 이미 심사"],
        ],
    ),
    _page(
        ["1) 각주", "- 16 -"],
        [
            HEAD_2,
            ["", "", "받은 자료로 입증"],  # 🚨 비고만 넘어왔다
            [
                "2. 효능·효과에\n관한 내용",
                "· 특정성분이 들어 있지\n않다는 ‘무(無) oo' 표현1)",
                "· 시험 분석 자료로 입증",
            ],
            [
                "3. ISO 지수에\n관한 내용",
                "· ISO 지수2) 표시·광고\n<예시>\n- 천연지수 00% (ISO 16128 계산\n적용)\n- 유기농지수 00%\n· 시험 결과 표현\n<예시> 피부과 테스트 완료\noo시험검사기관의 oo 효과\n입증",
                "· 실증자료로 입증",
            ],
        ],
    ),
    _page(
        ["발 행 일 2025년 8월 14일", "발 행 인 홍길동"], [HEAD_1, ["판권면", "· 담지 않는다", ""]]
    ),
]


@pytest.mark.gate
def test_항목은_가운뎃점_한_줄이고_구분은_병합_칸을_잇는다() -> None:
    rows, _ = cg.parse(PAGES)
    one = [r for r in rows if r["별표"] == 1]
    assert [r["표현"] for r in one[:3]] == ["아토피", "모낭충", "여드름"]
    assert {r["구분"] for r in one[:4]} == {"질병을 진단·치료 관련"}
    assert one[0]["근거"] == "002015:제13조제1항제1호" and one[0]["쪽"] == 9
    # 🚨 붙일 자리는 이음 표가 정한다 — 표에 없는 줄넘김은 빈칸이다
    assert one[3]["표현"] == "메디슨(medicine), 코스메슈티컬, 약용 등을 사용한 표현"
    assert one[3]["줄넘김"] is True and one[0]["줄넘김"] is False


@pytest.mark.gate
def test_단서는_같은_행의_비고이고_함께_쓰면_표시한다() -> None:
    rows, _ = cg.parse(PAGES)
    by = {r["표현"]: r for r in rows}
    assert by["아토피"]["단서"] is None and by["아토피"]["단서_공유"] is False
    assert (
        by["여드름"]["단서"].startswith("단, 기능성화장품") and by["여드름"]["단서_공유"] is False
    )
    two = [r for r in rows if r["근거"] == "002015:제13조제1항제2호"]
    assert len(two) == 2 and all(r["단서"] == "단, 공통 단서" and r["단서_공유"] for r in two)


@pytest.mark.gate
def test_쪽을_넘은_항목과_비고를_앞_항목에_잇는다() -> None:
    rows, stat = cg.parse(PAGES)
    by = {r["표현"]: r for r in rows}
    cut = by["특정성분(엑소좀, 줄기세포)이 들어 있는 것으로 오인할 수 있는 표현"]
    assert cut["예시"] == ["엑소좀 화장품 등"] and cut["쪽"] == 13 and cut["줄넘김"] is True
    assert (
        by["빠지는 모발을 감소시킨다."]["입증"] == "· 기능성화장품으로서 이미 심사받은 자료로 입증"
    )
    assert stat["이은_쪽"] == [14, 16]
    assert all(not v for k, v in stat.items() if k not in ("이은_쪽", "줄넘김_수", "안_쓴_이음"))


@pytest.mark.gate
def test_예시와_하위_항목과_각주_표지를_가른다() -> None:
    rows, _ = cg.parse(PAGES)
    by = {r["표현"]: r for r in rows}
    assert by["줄기세포가 들어 있는 것으로 오인할 수 있는 표현"]["예시"] == [
        "줄기세포 화장품, stem cell 등"
    ]
    assert by["성생활 암시 표현"]["하위"] == ["여성크림", "쾌감을 증대시킨다."]
    # 각주 표지 「1)」 · 「2)」는 표현에서 뗀다
    assert "특정성분이 들어 있지 않다는 ‘무(無) oo' 표현" in by
    iso = by["ISO 지수 표시·광고"]
    assert iso["예시"] == ["천연지수 00% (ISO 16128 계산 적용)", "유기농지수 00%"]
    # 🚨 가운뎃점 없는 예시는 `EXAMPLE_BREAKS` 의 자리에서만 갈린다 — 그 밖은 한 예시가 줄을 넘은 것이다
    assert by["시험 결과 표현"]["예시"] == ["피부과 테스트 완료", "oo시험검사기관의 oo 효과 입증"]
    assert iso["별표"] == 2 and iso["근거"] is None and iso["입증"] == "· 실증자료로 입증"


@pytest.mark.gate
def test_별표_앞과_판권면은_담지_않고_판본과_구속력이_레코드마다_있다() -> None:
    rows, _ = cg.parse(PAGES)
    assert all("홍길동" not in str(r) and r["표현"] != "담지 않는다" for r in rows)
    for r in rows:
        assert r["문서"] == "안내서-0086-07" and r["기준시점"] == "2025-08"
        assert r["구속력"] == "해설" and r["층"] == "3층 판단규범"  # D-290 ②


@pytest.mark.gate
def test_구조가_어긋나면_검증이_실패한다() -> None:
    assert cg.verify(PAGES) == []
    # 호 절 하나가 빠진다
    assert any("호" in b for b in cg.verify([*PAGES[:2], *PAGES[3:]]))
    # 절 제목 없이 표가 온다 — 근거 호를 지어내지 않는다 (D-220)
    lost = [PAGES[0], _page(["[별표 1]", "- 9 -"], PAGES[1]["표"][0]), *PAGES[2:]]
    assert any("절_없는_표" in b for b in cg.verify(lost))
    # 모르는 머리의 표
    odd = [
        *PAGES[:2],
        _page(["- 10 -"], [["구 분", "모르는 칸", "비 고"], ["가", "· 나", ""]]),
        *PAGES[2:],
    ]
    assert any("모르는_표" in b for b in cg.verify(odd))
    # 쪽 첫 행이 아닌데 가운뎃점 없이 시작한다 — 조용히 버리지 않는다
    stray = _page(
        ["□ 화장품법 제13조 제1항 제2호 관련", "- 12 -"],
        [HEAD_1, ["기능성", "· 가", ""], [None, "가운뎃점 없는 글", ""]],
    )
    assert any("머리_없는_이음" in b for b in cg.verify([*PAGES[:2], stray, *PAGES[3:]]))


@pytest.mark.gate
def test_마스킹_정책대로_지나고_별표의_글은_바뀌지_않는다() -> None:
    """레지스트리 문언은 「2쪽 점검표의 담당자·부서장 성명 · 부서 전화·팩스」다 — 축이 없고, 그 쪽은 **담지 않아** 지킨다."""
    from preprocess.mask import POLICY

    assert POLICY[cg.SOURCE_ID] == frozenset()
    rows, _ = cg.parse(PAGES)
    out, changed, log = cg.masked(rows)
    assert out == rows and not changed and log == []


@pytest.mark.gate
def test_이음_표는_판에_묶인다() -> None:
    """줄넘김 수가 다르거나 안 쓰인 이음이 있으면 판이 바뀐 것이다 — 조용히 옛 표로 잇지 않는다."""
    ok = {"줄넘김_수": cg.EXPECTED_BREAKS, "안_쓴_이음": []}
    assert cg.check_edition(ok) == []
    assert cg.check_edition({**ok, "줄넘김_수": cg.EXPECTED_BREAKS + 1})
    assert cg.check_edition({**ok, "안_쓴_이음": [("코스", "메슈티컬,")]})
    # 붙이는 쌍과 예시를 가르는 쌍은 겹치지 않는다
    assert not (cg.JOINS & cg.EXAMPLE_BREAKS)
