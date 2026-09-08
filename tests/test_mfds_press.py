"""`preprocess.mfds_press` — 보도자료 붙임 표에서 **열의 뜻으로** 문구를 찾는다 (D-167).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

원천이 회차마다 표를 다르게 짠다 — 머리글 39종. 나열해 맞추면 다음 회차에 40번째가 나온다.
"""

from __future__ import annotations

from preprocess.mfds_press import DROP, industry_of, kind_of, role_of


def test_ad_column_is_found_by_meaning_not_by_one_word() -> None:
    """⛔ 문구 키를 「광고」 한 낱말로 뒀더니 **부서명과 법률명**이 걸려 레코드 0 이 나왔다."""
    assert role_of("주요 부당광고") == "문구"
    assert role_of("광고 내용") == "문구"
    assert role_of("식품안전정책국 식품표시광고정책과") is None
    assert role_of("식품 등의 표시광고에 관한 법률") is None


def test_violation_kind_is_not_a_phrase() -> None:
    """🚨 「위반 내용」은 유형 서술이다 — 실측: 「거짓·과장된 표시·광고 등」."""
    assert role_of("위반 내용") == "원천유형"
    assert role_of("위반유형") == "원천유형"


def test_company_and_address_columns_are_dropped() -> None:
    """🔴 마스킹으로 가리는 것이 아니라 **안 담는다** (D-159)."""
    for col in ("판매업체명 (업종, 소재지)", "업소명", "소재지", "제조업체명 (소재지)"):
        assert role_of(col) != "문구"
        assert any(d in col for d in DROP), col


def test_industry_is_lifted_but_name_and_place_are_not() -> None:
    """★ 한 셀에 셋이 들어 있다 — **업종만** 떠낸다. 「…업」으로 끝나는 조각이 표지다."""
    cell = "주식회사 제트샵 (건강기능식품유통 전문판매업, 강원 화천군)"
    got = industry_of(cell)
    assert got == "건강기능식품유통 전문판매업"
    assert "제트샵" not in got and "화천" not in got


def test_food_kind_only_when_hangul() -> None:
    """🚨 괄호 안이 늘 식품유형은 아니다 — 「덴티오클린(Dentio clean)」은 영문 제품명이다."""
    assert kind_of("덱카닉정(고형차)") == "고형차"
    assert kind_of("덴티오클린(Dentio clean)") == ""
    assert kind_of("주식회사 가나 (유통전문판매업, 서울)") == ""
