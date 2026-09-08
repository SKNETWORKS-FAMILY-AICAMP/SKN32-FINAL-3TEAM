"""`preprocess.mfds_casebook` — 사례집의 **조문이 확정이고 5호만 뭉친다** (D-158).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

해설서(D-151)와 짝을 이룬다. 거기서는 원천의 분류가 우리 6종을 뭉쳐 확정할 수 없었고,
여기서는 원천이 **호를 적어 주므로** 옮겨 적는다 — 딱 한 곳, 5호만 빼고.
"""

from __future__ import annotations

from preprocess.mfds_casebook import (
    _BLOCK,
    HO_TYPES,
    REGIME,
    _types,
    locate,
    own_text,
    printed,
    quotes,
    toc,
)
from scripts.collect import CANDIDATE_TYPES, VIOLATION_TYPES


def test_every_type_is_a_known_type() -> None:
    """🔴 오타 하나가 유령 라벨을 만든다."""
    known = set(VIOLATION_TYPES) | set(CANDIDATE_TYPES)
    for ho, ts in HO_TYPES.items():
        assert not set(ts) - known, f"{ho}호: 목록에 없는 유형 {set(ts) - known}"


def test_only_the_fifth_is_merged() -> None:
    """🚨 5호만 뭉친다 — 시행령 [별표 1] 5. 다목에 체험기와 「한방」·「주문쇄도」가 같이 산다."""
    merged = [h for h, ts in HO_TYPES.items() if len(ts) > 1]
    assert merged == [5]


def test_merged_ho_never_becomes_a_fixed_label() -> None:
    """🔴 뭉친 것을 확정으로 적으면 홀드아웃이 자기 채점이 된다 (D-40 · D-151)."""
    fixed, cand = _types([5])
    assert fixed == []
    assert cand == ["소비자_기만", "후기_체험기_기만"]


def test_multi_label_keeps_the_certain_part() -> None:
    """★ 한 항목에 호가 둘 이상인 것이 원천에 있다 — 확실한 쪽은 확정으로 남긴다."""
    fixed, cand = _types([3, 5])
    assert fixed == ["건강기능식품_오인"]
    assert cand == ["소비자_기만", "후기_체험기_기만"]


def test_block_header_has_five_spellings() -> None:
    """⛔ 「[부당광고 사례]」로 하드코딩했더니 5개 중 2개만 잡혔는데 **예외가 안 났다.**"""
    for name in ("[부당광고 사례]", "[부당광고사례]", "[광고사례]", "[위반사례]", "[점검 현황]"):
        m = _BLOCK.match(name)
        assert m, name
        kind = "점검현황" if "점검" in m.group(1) else "사례"
        assert kind == ("점검현황" if "점검" in name else "사례")


def test_quote_may_close_with_an_opening_mark() -> None:
    """🚨 원천이 여는 따옴표로 닫는다 — 「‘난임예방‘」·「’암예방‘」. 짝을 안 따진다."""
    got = quotes("식품 등을 ‘감기예방’, ‘난임예방‘, ’암예방‘ 등으로 광고")
    assert got == ["감기예방", "난임예방", "암예방"]


def test_own_text_excludes_the_umbrella_line() -> None:
    """⛔ `대분류` 를 섞어 세면 같은 표현이 형제 레코드마다 복제돼 표본이 부푼다."""
    rec = {"글": "‘감기예방’ 등으로 광고", "대분류": "‘감기예방’, ‘암예방’ 등 질병 예방 광고"}
    assert quotes(own_text(rec)) == ["감기예방"]


def test_toc_entries_are_read_with_their_page_numbers() -> None:
    """★ 목차는 본문과 **다른 경로**로 만들어진 선언이라 대조에 쓸 수 있다."""
    pgs = ["표지", "목차\nⅡ. 부당광고 사례 ······ 13\nⅢ. 주요 플랫폼별 ····· 50"]
    i, entries = toc(pgs)
    assert i == 1
    assert entries == [("Ⅱ. 부당광고 사례", 13), ("Ⅲ. 주요 플랫폼별", 50)]


def test_locate_walks_forward_in_toc_order() -> None:
    """⛔ 매번 처음부터 찾았더니 호 제목 다섯이 전부 **법령 전재 쪽**에서 잡혔다.

    Ⅰ부가 법 제8조 제1항을 통째로 전재하는데 각 호 문장이 목차 제목과 **글자까지 같다.**
    🚨 목차 대조가 없었으면 Ⅱ부 대신 법령을 파싱하고 조용히 끝났을 것이다.
    """
    pgs = [
        "목차\nⅡ. 부당광고 사례 ··· 13\n1. 거짓ㆍ과장된 표시 또는 광고 ··· 38",
        "1. 거짓ㆍ과장된 표시 또는 광고\n- 1 -",  # Ⅰ부 법령 전재
        "Ⅱ\n부당광고 사례\n- 13 -",
        "1. 거짓ㆍ과장된 표시 또는 광고\n- 38 -",
    ]
    i, entries = toc(pgs)
    found = locate(pgs, i, entries)
    assert printed(pgs[found["1. 거짓ㆍ과장된 표시 또는 광고"]]) == 38


def test_regime_is_the_current_one_not_the_guide_one() -> None:
    """🚨 해설서(2017 · 사전심의)와 섞이면 3층으로 새어 들어간다 (D-138)."""
    assert REGIME["연도"] == 2026 and "자율심의" in REGIME["심의제도"]
