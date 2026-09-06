"""`preprocess.normalize` — [P2] 비파괴 정규화 층 (2026-09-06).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 불변식은 셋이다.

  ① `len(offset_map) == len(norm)` — 깨지면 하이라이트가 엉뚱한 자리를 칠한다
  ② `to_raw()` 로 되돌린 구간이 **원문에서 실제로 그 낱말을 덮는다**
  ③ 정규화가 **원문을 바꾸지 않는다** (`raw` 는 그대로)

🚨 ②가 이 모듈의 존재 이유다. 「매칭은 `norm` 에서, 보고는 `raw` 좌표로」가 성립하는지를
   회피 표기가 **낀 채로** 확인한다 — `치<ZWSP>료` 를 `치료` 로 잡고, 사용자에게는
   ZWSP 를 포함한 세 글자를 칠해 줘야 한다.
"""

from __future__ import annotations

import unicodedata

import pytest

from preprocess.normalize import NormalizedText, has_decomposed_hangul, normalize


def _span(n: NormalizedText, word: str) -> str:
    """`norm` 에서 낱말을 찾아 `raw` 좌표로 되돌린 뒤, 원문에서 그 구간을 떠 온다."""
    i = n.norm.index(word)
    a, b = n.to_raw(i, i + len(word))
    return n.raw[a:b]


# ─────────────────────────────────────────────────────────────
#  불변식 ① · ③
# ─────────────────────────────────────────────────────────────

SAMPLES = [
    "ｄｉｅｔ 100％ 천연",
    "치​료 효과",
    "치­료",  # soft hyphen — 화면에 안 보이는데 낱말을 가른다
    "대박!!!!! 좋아요",
    "비타민  C   함유",
    "⑴ 첫째\t둘째",
    "정상 문장입니다.",
    "",
    "   ",
]


@pytest.mark.parametrize("raw", SAMPLES)
def test_offset_map_length_matches_norm(raw: str) -> None:
    """🚨 이것이 깨지면 뒤의 모든 좌표가 조용히 어긋난다."""
    n = normalize(raw)
    assert len(n.offset_map) == len(n.norm)


@pytest.mark.parametrize("raw", SAMPLES)
def test_raw_is_untouched(raw: str) -> None:
    """비파괴 — 원문은 그대로 들고 있다 (사양 1-2)."""
    assert normalize(raw).raw == raw


@pytest.mark.parametrize("raw", SAMPLES)
def test_offsets_are_monotonic_and_in_range(raw: str) -> None:
    """오프셋은 뒤로 가지 않는다. 🚨 한 raw 글자가 여럿이 되면 **같은 값이 반복**된다."""
    n = normalize(raw)
    assert all(0 <= o < len(raw) for o in n.offset_map)
    assert all(a <= b for a, b in zip(n.offset_map, n.offset_map[1:], strict=False))


# ─────────────────────────────────────────────────────────────
#  🚨 불변식 ② — 이 모듈의 본론
# ─────────────────────────────────────────────────────────────


def test_zero_width_span_covers_the_evasion_character() -> None:
    """🚨 `치<ZWSP>료` 를 `치료` 로 잡고, **ZWSP 를 포함한 세 글자**를 되돌려준다.

    두 글자만 칠하면 사용자 화면에서 낱말이 잘려 보인다.
    """
    n = normalize("치​료 효과")
    assert n.norm == "치료 효과"
    assert _span(n, "치료") == "치​료"


def test_expanding_character_does_not_truncate_the_span() -> None:
    """🚨 `⑴` → `(1)` 로 **한 글자가 셋이 된다.** 끝 좌표 계산이 틀리면 여기서 잘린다."""
    n = normalize("⑴ 치료")
    assert n.norm == "(1) 치료"
    assert _span(n, "치료") == "치료"
    assert _span(n, "(1)") == "⑴"


def test_fullwidth_span_maps_back() -> None:
    n = normalize("ｄｉｅｔ 치료")
    assert n.norm == "diet 치료"
    assert _span(n, "diet") == "ｄｉｅｔ"


def test_empty_span_is_a_point() -> None:
    """빈 구간은 빈 구간으로 돌아온다 — 삽입 위치를 가리키는 자리다."""
    n = normalize("치료")
    assert n.to_raw(1, 1) == (1, 1)
    assert n.to_raw(2, 2) == (2, 2)


def test_out_of_range_span_is_refused() -> None:
    """🚨 조용히 자르지 않는다 — 잘린 좌표는 틀린 자리를 칠하고도 통과한다."""
    n = normalize("치료")
    with pytest.raises(ValueError):
        n.to_raw(0, 3)
    with pytest.raises(ValueError):
        n.to_raw(2, 1)


# ─────────────────────────────────────────────────────────────
#  규칙별 — 무엇이 발동했다고 말하는가
# ─────────────────────────────────────────────────────────────


def test_repeat_shrinks_to_two() -> None:
    assert normalize("대박!!!!! 좋아요").norm == "대박!! 좋아요"


def test_digits_survive_repeat() -> None:
    """🚨 숫자는 판정 대상이다 (사양 1-4). 「2000년」이 「200년」이 되면 안 된다."""
    n = normalize("2000년 1111-2222")
    assert n.norm == "2000년 1111-2222"
    assert "REPEAT" not in n.applied_rules


def test_spaces_are_not_reported_as_repeat() -> None:
    """⛔ 첫 판의 실수 — 공백 셋이 N5 에 먼저 걸려 `REPEAT` 로 찍혔다.

    🚨 결과 문자열은 어느 쪽이든 같다. 그래서 눈에 안 띈다.
       그런데 **어느 규칙이 발동했는가가 위험도 근거 문장**이 된다 (사양 1-5) —
       「반복 문자가 있어 위험도를 올렸습니다」가 띄어쓰기 때문에 나가면 안 된다.
    """
    n = normalize("비타민  C   함유")
    assert n.norm == "비타민 C 함유"
    assert n.applied_rules == ["SPACE"]


def test_newlines_survive() -> None:
    """🚨 [P4] 가 줄바꿈을 문장 경계로 쓴다 — 여기서 지우면 그 경계를 미리 없앤다."""
    n = normalize("첫 줄\n둘째 줄")
    assert "\n" in n.norm


# ─────────────────────────────────────────────────────────────
#  🚨 evasion_flags 와 applied_rules 는 다른 것이다
# ─────────────────────────────────────────────────────────────


def test_repeat_and_space_are_not_evasion() -> None:
    """전부 켜지는 피처는 피처가 아니다 — 위 모듈 docstring 마지막 절.

    🚨 이건 **사양 1-3 을 좁힌 것**이라 팀장 확인 대상이다. 확인 전까지 이 테스트가
       「우리가 그렇게 정했다」의 증거다.
    """
    n = normalize("대박!!!!!  좋아요")
    assert set(n.applied_rules) >= {"REPEAT", "SPACE"}
    assert n.evasion_flags == []


@pytest.mark.parametrize(
    ("raw", "flag"),
    [("치​료", "ZWSP"), ("ｄｉｅｔ", "FULLWIDTH")],
)
def test_evasion_signals_are_reported(raw: str, flag: str) -> None:
    assert flag in normalize(raw).evasion_flags


def test_clean_text_reports_nothing() -> None:
    """양성 대조 — 멀쩡한 문장에 깃발이 서면 위험도가 통째로 올라간다."""
    n = normalize("체지방 감소에 도움을 줄 수 있음")
    assert n.norm == n.raw
    assert n.applied_rules == []
    assert n.evasion_flags == []


# ─────────────────────────────────────────────────────────────
#  ⬜ 아직 못 하는 것 — 숨기지 않고 실패로 남긴다
# ─────────────────────────────────────────────────────────────


def test_decomposed_hangul_is_detected_not_fixed() -> None:
    """분해된 한글을 **찾아내되 고치지는 않는다** — 글자 단위 NFKC 의 한계다.

    ⛔ 첫 판은 확장 A~B 를 한 범위로 잡아 **완성형을 통째로 삼켰다.**
       유니코드 블록은 이름이 이어져도 코드포인트가 이어지지 않는다.
    """
    assert has_decomposed_hangul(unicodedata.normalize("NFD", "한글")) is True
    assert has_decomposed_hangul(unicodedata.normalize("NFC", "한글")) is False
    assert has_decomposed_hangul("치료 효과") is False


@pytest.mark.xfail(
    strict=True,
    reason=(
        "N4(SEP_INSERT)는 [P6] 사전이 서야 한다 — 사양 1-4 가 「사전 어휘의 문자 사이에서만」 "
        "이라고 못 박았다. 전역 치환하면 「비타민 C」가 깨진다. "
        "🚨 XPASS 로 뒤집혔다면 누가 N4 를 넣은 것이다 — 「비타민 C」·「45개 선불식」이 "
        "살아 있는지부터 확인해라."
    ),
)
def test_separator_insertion_not_implemented_yet() -> None:
    """⬜ `치·료` → `치료`. 지금은 안 된다."""
    assert normalize("치·료 효과").norm == "치료 효과"


@pytest.mark.xfail(
    strict=True,
    reason="N3(JAMO_SPLIT)도 [P6] 사전 대기. 미해결 #1·#2 와 같은 자리다.",
)
def test_jamo_split_not_implemented_yet() -> None:
    """⬜ `ㅊl료` → `치료`. 지금은 안 된다."""
    assert normalize("ㅊl료 효과").norm == "치료 효과"
