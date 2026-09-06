"""`collect.http.encode()` 왕복 검사 — 2026-09-05.

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).
   게이트는 「팀 전체가 못 나가는 규칙」이고, 이것은 모듈 하나의 단위 테스트다.

왜 생겼나 — `encode()` 가 `urlencode` 가 낸 `+`(공백)를 `%2B`(리터럴 더하기)로
다시 인코딩해서, 법제처 `--find` 가 **예외도 0건도 아닌 그럴듯한 다른 결과**를
돌려주고 있었다. 예외가 안 나는 실패라 눈으로는 못 잡는다.

🚨 이 모듈이 지키는 불변식은 하나다 —
   **`urlencode` 로 만든 질의는 `encode()` 를 지나도 뜻이 변하지 않는다.**
   서버가 되돌린 값(`parse_qs`)이 보내려던 값과 같아야 한다.

🚨 `scripts/law_api_smoke.py` 는 자기 `call()` 로 `urlopen` 을 직접 부른다 —
   `http.py` 를 안 탄다. 「그 질의가 된다」를 증명한 그 스모크가 정작 실제 경로를
   비켜 가고 있었다. 검증은 **실제 경로**를 타야 한다. 그래서 여기서 `encode()` 를
   직접 부른다.
"""

from __future__ import annotations

import urllib.parse

import pytest

from collect.http import encode

BASE = "https://www.law.go.kr/DRF/lawSearch.do"

#: ASCII 출력 가능 문자 95자 — 0x20(공백) ~ 0x7E(`~`)
ASCII_PRINTABLE = [chr(c) for c in range(0x20, 0x7F)]

#: 공백이 든 실제 법령명. `law_api.search()` 가 이 형태로 부른다.
LAW_NAMES = [
    "건강기능식품에 관한 법률",
    "건강기능식품의 기준 및 규격",
    "식품 등의 표시·광고에 관한 법률",
]


def roundtrip(value: str) -> str:
    """`urlencode` → `encode()` → 서버가 되돌리는 값.

    서버 쪽 해석을 `parse_qs` 로 흉내 낸다 — 질의 문자열에서 `+` 는 공백,
    `%XX` 는 해당 바이트다. **이 둘의 구분이 깨지는 것이 이 버그다.**
    """
    query = urllib.parse.urlencode({"query": value})
    encoded = encode(f"{BASE}?{query}")
    parsed = urllib.parse.parse_qs(urllib.parse.urlsplit(encoded).query, keep_blank_values=True)
    return parsed["query"][0]


@pytest.mark.parametrize("ch", ASCII_PRINTABLE, ids=lambda c: f"U+{ord(c):04X}")
def test_ascii_printable_roundtrip(ch: str) -> None:
    """ASCII 95자 전수. 🚨 수정 전에는 **U+0020(공백) 하나만** 실패한다.

    공백만 실패하는 이유 — `urlencode` 는 공백을 `+` 로 낸다. 다른 문자는 전부
    `%XX` 로 나가고 `%` 는 이미 `safe` 에 있어 그대로 통과한다. 리터럴 `+`(U+002B)
    조차 `urlencode` 단계에서 `%2B` 가 되므로 무사하다. **깨지는 것은 「+로 표기된
    공백」 하나**이고, 그 하나가 검색어에 가장 흔한 문자다.
    """
    value = f"A{ch}Z"
    assert roundtrip(value) == value


@pytest.mark.parametrize("name", LAW_NAMES)
def test_law_name_roundtrip(name: str) -> None:
    """공백이 든 법령명 — `--find` 가 실제로 보내는 질의."""
    assert roundtrip(name) == name


def test_non_ascii_path_is_encoded() -> None:
    """한글 경로는 여전히 퍼센트 인코딩된다 (2026-09-02 나스미디어 회귀 방지)."""
    encoded = encode("https://example.org/정기보고서/2024.pdf")
    assert encoded.isascii()
    assert urllib.parse.unquote(urllib.parse.urlsplit(encoded).path) == "/정기보고서/2024.pdf"


# ─────────────────────────────────────────────────────────────
#  🚨 아래는 **아직 못 고친 것**을 기록으로 남긴다 (§3 · 2026-09-05)
# ─────────────────────────────────────────────────────────────
#  `safe` 에 `+` 를 넣는 수정은 **호출부가 `urlencode` 를 탄다는 전제**에서만 옳다.
#  원문 URL 을 그대로 `encode()` 에 넘기는 경로(`mfds_press` 방식)에서는
#  `%` 와 `+` 둘 다 「원문인지 이스케이프인지」 구분이 불가능하다.
#  문자 하나만 보고는 알 방법이 없어서 `safe` 를 어떻게 조정해도 해결되지 않는다.
#
#  🚨 이 프로젝트가 다루는 것이 「50% 할인」·「1+1 행사」 같은 광고 문구다.
#     아직 안 터진 건 검색어에 `%` 가 없었기 때문일 뿐이다.
#
#  진짜 해법은 `fetch()` 가 조립된 URL 이 아니라 `(base, params)` 를 받아
#  인코딩을 한 곳에서 하는 것이다. **설계 변경이라 결정 사항이다.**
#
#  🚨 `strict=True` 다 — 이 테스트가 통과하기 시작하면 그때 실패로 알린다.
#     §3 이 해결된 순간 이 xfail 을 지우라는 신호다. 조용히 잊히지 않게 한다.


def has_malformed_escape(query: str) -> bool:
    """질의 문자열에 `%` 뒤 두 자리 16진수가 오지 않는 자리가 있는가."""
    hexdigits = set("0123456789abcdefABCDEF")
    return any(
        set(query[i + 1 : i + 3]) - hexdigits or len(query) - i < 3
        for i, ch in enumerate(query)
        if ch == "%"
    )


@pytest.mark.xfail(
    strict=True,
    reason="§3 — encode() 가 「원문 URL 을 인코딩하기」와 「기인코딩 URL 을 안 건드리기」를 "
    "겸해서 생기는 모호성. `%` 하나만 보고는 원문인지 이스케이프인지 알 수 없어 "
    "safe 를 어떻게 조정해도 못 고친다. fetch(base, params) 설계 변경 필요",
)
@pytest.mark.parametrize("raw", ["50% 할인", "100%"])
def test_raw_url_with_literal_percent(raw: str) -> None:
    """원문 URL 을 그대로 넘기는 경로에서 진짜 `%` 가 깨진다. **수정 A 로도 안 고쳐진다.**

    `50% 할인` → `k=50%%20…`  — `%%20` 은 잘못된 이스케이프다.
    `100%`    → `k=100%`     — 끝의 홑 `%` 는 잘못된 URL 이다.

    🚨 이 프로젝트가 다루는 것이 「50% 할인」·「100% 천연」 같은 광고 문구다.
       아직 안 터진 건 `mfds_press` 검색어에 `%` 가 없었기 때문일 뿐이다.
    """
    query = urllib.parse.urlsplit(encode(f"https://example.org/search?k={raw}")).query
    assert not has_malformed_escape(query), f"잘못된 이스케이프: {query}"
    assert urllib.parse.parse_qs(query)["k"][0] == raw


@pytest.mark.xfail(
    strict=True,
    reason="🚨 수정 A 가 만드는 반대 방향 버그 — `+` 를 safe 에 넣으면 원문 URL 의 "
    "리터럴 `+` 가 공백으로 읽힌다. A 는 「호출부가 urlencode 를 탄다」는 전제 위에서만 "
    "옳은 임시 처방이고, 이 xfail 이 그 대가다. §3 이 해결되면 함께 지운다",
)
def test_raw_url_with_literal_plus() -> None:
    """🚨 **수정 A 적용 전에는 이 테스트가 통과한다** — 그래서 XPASS 로 붉게 뜬다.

    그것이 의도다. A 를 적용하는 순간 이 자리가 xfail 로 넘어가면서, 우리가
    무엇을 내주고 무엇을 얻었는지가 테스트 결과에 남는다. 「고쳤다」로 끝나지 않게 한다.

    `1+1 행사` 는 지어낸 예가 아니다 — 이 프로젝트가 다루는 광고 문구다.
    """
    raw = "1+1 행사"
    query = urllib.parse.urlsplit(encode(f"https://example.org/search?k={raw}")).query
    assert urllib.parse.parse_qs(query)["k"][0] == raw
