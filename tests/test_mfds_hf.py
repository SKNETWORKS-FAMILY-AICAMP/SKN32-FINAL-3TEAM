"""`preprocess.mfds_hf` — 2층 적법라벨의 **근거가 마스킹을 지나 살아남는가** (D-156).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 둘이다.
  ① 한 줄에 붙어 온 「○ 키」를 편다 — 안 펴면 **필드가 조용히 섞인다.**
  ② 마스킹이 **인정번호와 기능성내용**을 건드리면 산출을 멈춘다.
"""

from __future__ import annotations

from preprocess.mfds_hf import (
    INTACT,
    KEEP,
    MASKED,
    explode,
    fields,
    intact_report,
    split_claims,
)


def test_two_keys_on_one_line_are_split() -> None:
    """⛔ 66건이 「○ 원료명 : … ○ 인정번호 : …」로 한 줄에 붙어 있었다.

    안 펴면 인정번호가 **없는 것**이 되고, 더 나쁘게는 다음 키의 값이 앞 필드에 섞인다.
    """
    got, _ = fields(["○ 원료명 : 감잎주정추출분말 ○ 인정번호 : 제2022-18호(2022.4.18.)"])
    assert got["원료명"] == "감잎주정추출분말"
    assert got["인정번호"] == "제2022-18호(2022.4.18.)"


def test_value_does_not_swallow_the_next_field() -> None:
    """🔴 기능성내용에 일일섭취량이 섞이면 **필드가 비지 않아 계수로도 안 잡힌다.**"""
    got, _ = fields(
        ["○ 기능성내용 : 건조한 눈을 개선하여 눈건강에 도움을 줄 수 있음 ○ 일일섭취량 : 600 mg/일"]
    )
    assert got["기능성내용"] == "건조한 눈을 개선하여 눈건강에 도움을 줄 수 있음"
    assert got["일일섭취량"] == "600 mg/일"


def test_circle_inside_a_value_is_not_a_split_point() -> None:
    """🚨 값 안에도 `○` 가 온다 (가림 표기). **아는 키일 때만** 자른다."""
    assert explode(["○ 섭취주의사항 : 김○○ 관련 문의"]) == ["○ 섭취주의사항 : 김○○ 관련 문의"]


def test_continuation_lines_belong_to_the_previous_key() -> None:
    """「○ 기능성내용 :」 뒤에 `- …` 여러 줄이 오는 형태가 실재한다."""
    got, _ = fields(
        [
            "○ 기능성내용 :",
            "- 피부 보습에 도움을 줄 수 있음",
            "- 체지방감소에 도움을 줄 수 있음",
            "○ 일일섭취량 : 300 mg/일",
        ]
    )
    assert split_claims(got["기능성내용"]) == [
        "피부 보습에 도움을 줄 수 있음",
        "체지방감소에 도움을 줄 수 있음",
    ]


def test_english_block_is_not_taken() -> None:
    """★ 영문 상호는 우리 한국어 규칙이 못 잡는다 — **못 잡는 그물 뒤에 두느니 안 담는다.**"""
    got, _ = fields(
        [
            "○ 원료명 : 감잎추출분말",
            "※ English version ※",
            "○ Company or institution : WhanInPharm",
        ]
    )
    assert got == {"원료명": "감잎추출분말"}


def test_unknown_key_is_reported_not_dropped() -> None:
    """🚨 모르는 키를 조용히 버리지 않는다 — 버린 것을 세야 다음 사람이 고친다."""
    _, unknown = fields(["○ 새로운키 : 값"])
    assert unknown == ["새로운키"]


def test_title_is_not_a_field() -> None:
    """🔴 제목은 담지 않는다 — 업체 필드를 뺐는데 제목으로 같은 이름이 들어왔다."""
    assert "제목" not in MASKED and "제목" not in KEEP


def test_intact_violation_stops_the_dump() -> None:
    """🔴 D-156 — 인정번호가 지워지면 **근거 없는 「적법」 딱지**만 남는다."""
    a = {"게시물": "1", "인정번호": "제2014-64호", "기능성내용": "눈 건강", **{k: "" for k in KEEP}}
    a["인정번호"], a["기능성내용"] = "제2014-64호", "눈 건강"
    b = dict(a, 인정번호="[업체]")
    assert intact_report([a], [b])


def test_recognition_number_outside_its_own_field_is_watched() -> None:
    """⛔ ①만 보면 놓친다 — 인정번호는 **자기 필드 밖에도** 산다 (섭취주의사항 안 실측)."""
    base = {"게시물": "1", **{k: "" for k in KEEP}}
    a = dict(base, 섭취주의사항="기존에 인정받은 제2009-83호와 동일한 원료임")
    ok = dict(a, 섭취주의사항="기존에 인정받은 제2009-83호와 동일한 원료임")
    lost = dict(a, 섭취주의사항="기존에 인정받은 [업체]와 동일한 원료임")
    assert not intact_report([a], [ok])
    assert intact_report([a], [lost])


def test_intact_fields_are_the_two_the_registry_named() -> None:
    """레지스트리 `masking:` 이 이름으로 적어 둔 둘이다 — 코드가 말없이 줄이지 않는다."""
    assert INTACT == ("인정번호", "기능성내용")
