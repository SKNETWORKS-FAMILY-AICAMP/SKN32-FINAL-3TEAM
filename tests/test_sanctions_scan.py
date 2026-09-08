"""`preprocess.sanctions_scan` — **수가 맞는 것은 다 받았다는 뜻이 아니다** (D-161).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

지키는 것은 둘이다.
  ① 유일 행이 원천 선언에 못 미치면 **실패로 끝난다** (종료코드 1).
  ② 중복이 **페이지를 걸치는지**로 원인을 가른다 — 원천의 중복과 우리의 누락은 다르다.
"""

from __future__ import annotations

import json

import pytest

from preprocess.sanctions_scan import AD_LAW_HIT, QUOTE_FAMILIES_AD, scan
from preprocess.text import quoted


def _page(tmp, name, rows, total):
    (tmp / name).write_text(
        json.dumps({"X": {"total_count": str(total), "row": rows}}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def raw(tmp_path, monkeypatch):
    d = tmp_path / "data" / "raw" / "src"
    d.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return d


def test_count_matches_but_rows_are_missing(raw) -> None:
    """🔴 실측 그대로의 모양 — 받은 수는 선언과 같은데 **서로 다른 행이 모자란다.**"""
    a = [{"DSPSDTLS_SEQ": "1"}, {"DSPSDTLS_SEQ": "2"}]
    b = [{"DSPSDTLS_SEQ": "2"}, {"DSPSDTLS_SEQ": "3"}]  # 앞 페이지의 끝을 다시 준다
    _page(raw, "page_0001.json", a, 4)
    _page(raw, "page_0002.json", b, 4)
    s = scan("src")
    assert s["받은행"] == 4 and s["선언"] == [4]
    assert s["유일행"] == 3  # ← 하나가 비었다
    assert s["페이지걸침"] == 1 and s["한페이지안"] == 0


def test_duplicate_inside_one_page_is_the_source_not_us(raw) -> None:
    """★ 한 페이지 안의 중복은 원천에 정말 같은 행이 둘 있는 것이다 — 우리 잘못이 아니다."""
    _page(raw, "page_0001.json", [{"a": "1"}, {"a": "1"}, {"a": "2"}], 3)
    s = scan("src")
    assert s["한페이지안"] == 1 and s["페이지걸침"] == 0


def test_law_net_is_a_net_not_a_verdict(raw) -> None:
    """🚨 조문명 그물은 판정이 아니다 — 넓게 잡고 그 다음에 좁힌다."""
    assert AD_LAW_HIT({"LAWORD_CD_NM": "식품 등의 표시·광고에 관한 법률 제8조"})
    assert not AD_LAW_HIT({"LAWORD_CD_NM": "식품위생법 제36조(시설기준)"})


def test_law_name_in_corner_brackets_is_not_an_ad_phrase() -> None:
    """⛔ 낫표를 넣어 세면 「축산물 위생관리법 시행령」이 **광고 문구**로 잡힌다."""
    t = "법 제4조제1항 및 「축산물 위생관리법 시행령」 제21조에 따른 표시사항을 거짓으로 표시"
    assert quoted(t, min_len=2, families=QUOTE_FAMILIES_AD) == []
    assert quoted(t, min_len=2) == ["축산물 위생관리법 시행령"]
