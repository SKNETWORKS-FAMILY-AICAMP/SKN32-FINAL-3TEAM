"""`preprocess.text.quoted` — **인용부호 계수기는 하나뿐이다** (D-160).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 하나다 — 계수기가 **틀린 값을 만들지 않는다.**
못 뽑는 것은 수가 작아져 눈에 띄지만, **두 표현을 하나로 세면 수가 그럴듯해서 안 보인다.**
아래 케이스는 전부 `mfds_casebook`·`mfds_press` 실측에서 나온 실제 문자열이다.
"""

from __future__ import annotations

from preprocess.text import quoted


def test_source_closes_with_an_opening_mark() -> None:
    """⛔ 옛 계수기는 「‘난임예방‘」에서 못 멈추고 **다음 따옴표까지 물었다.**"""
    assert quoted("‘감기예방’, ‘난임예방‘, ’암예방‘ 등으로 광고") == [
        "감기예방",
        "난임예방",
        "암예방",
    ]


def test_two_expressions_never_become_one() -> None:
    """🔴 **이것이 제일 나쁜 실패다** — 종수가 줄지 않고 **틀린 종이 하나 생긴다.**

    실측: 「피로개선‘, ‘뇌건강」이 한 종으로 세어져 원장의 19종에 들어가 있었다.
    """
    got = quoted("▶ ‘인지력’, ‘기억력’, ‘피로개선‘, ‘뇌건강’ 등으로 광고")
    assert "피로개선‘, ‘뇌건강" not in got
    assert "피로개선" in got and "뇌건강" in got


def test_bullet_glued_to_the_quote_still_opens() -> None:
    """🚨 보도자료는 글머리표를 바짝 붙인다 — 공백만 여는 것으로 보면 **진짜가 사라진다.**"""
    assert quoted("▲‘다이어트보조제’ 등 일반 식품") == ["다이어트보조제"]
    assert quoted("▹‘골다공증 예방’ 등 질병의") == ["골다공증 예방"]


def test_circled_numeral_is_not_a_word_character() -> None:
    """⛔ `isalnum()` 은 `➌` 을 **숫자로 본다**(유니코드 No 범주).

    그 한 글자 때문에 「‘기억력 개선(향상)’」이 통째로 빠졌다. `isdecimal()` 은 아니다.
    """
    assert quoted("광고 13건(28.9%), ➌‘기억력 개선(향상)’") == ["기억력 개선(향상)"]


def test_closing_after_punctuation_still_closes() -> None:
    """🚨 안에서는 **닫는 쪽으로 기운다** — 밖과 같은 기준을 쓰면 `)` 뒤의 `’` 가 여는 것이 된다."""
    assert quoted("‘먹는 위고비(비만치료제)’") == ["먹는 위고비(비만치료제)"]
    assert quoted("‘화장품이 질염 예방, 여드름 치료?’") == ["화장품이 질염 예방, 여드름 치료?"]


def test_quote_does_not_cross_a_line() -> None:
    """🚨 넘게 두면 표가 실린 PDF 에서 인용 하나가 **옆 칸을 통째로 문다** (77 → 112종)."""
    assert quoted("‘체지방 감소\n월곶중앙로30 (유통전문판매업)’") == []


def test_between_two_quotes_is_not_a_quote() -> None:
    """⛔ 「같은 가족 아무 부호로 닫는다」로 갔을 때 표현 **사이의 글**이 잡혔다 (유령 6종)."""
    got = quoted("‘면역력’ 등으로 광고 ▲ ‘피로 개선’")
    assert got == ["면역력", "피로 개선"]


def test_range_is_a_declared_parameter_not_another_regex() -> None:
    """🚨 세는 범위가 다른 것은 **파라미터**로 갈라야 비교가 성립한다 (D-117 의 교훈)."""
    line = "‘암’ 과 ‘골다공증예방’"
    assert quoted(line) == ["암", "골다공증예방"]
    assert quoted(line, min_len=6) == ["골다공증예방"]


def test_families_do_not_bleed_into_each_other() -> None:
    """가족마다 따로 훑는다 — 큰따옴표 인용이 작은따옴표 인용을 자르지 않는다."""
    got = quoted("“취침 전에 1포씩”, “20대 김○○님 체형 전·후 사진”")
    assert got == ["취침 전에 1포씩", "20대 김○○님 체형 전·후 사진"]
