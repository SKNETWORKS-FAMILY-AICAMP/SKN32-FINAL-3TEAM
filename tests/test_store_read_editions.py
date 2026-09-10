"""🔴 **읽는 쪽의 판 규칙** — D-177 (2026-09-10).

⛔ `save_raw` 는 「원본은 그대로 둔다(규약 2 · D-92)」만 정하고 **읽는 쪽 규칙이 없었다.**
   `data/raw/*` 를 `glob()` 하는 추출기 **16곳**이 원본과 판(`__c`)을 함께 읽고 있었다.

   실측 사고 — `preprocess/mfds_hf.py` `index()` 가 `hf_board_index_*__c20260907.json` 5개를
   함께 읽고, 정렬상 원본이 먼저 와서 `setdefault` 가 **새 판의 행을 조용히 버렸다.**
   그리고 `total_cnt` 가 한 번이라도 갈리면 `ValueError` 로 죽는다 — 655 로 우연히
   일치해 지나가고 있었을 뿐이다.

★ 규칙 — **원본을 읽는다. 판이 있으면 멈춘다.** 판이 생겼다는 것은 원천이 달라졌다는
  뜻이고 어느 것을 쓸지는 사람이 정한다 (D-143). 「최신을 쓴다」를 기본으로 두면
  2인 확인을 지난 적 없는 바이트가 조용히 판정 근거가 된다.
"""

from __future__ import annotations

import pathlib

import pytest

from collect import store

pytestmark = pytest.mark.gate


@pytest.fixture
def raw(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "page_0001.json").write_text("원본1", encoding="utf-8")
    (tmp_path / "page_0002.json").write_text("원본2", encoding="utf-8")
    return tmp_path


def test_판이_없으면_그냥_읽는다(raw: pathlib.Path) -> None:
    got = store.current_files(raw, "*.json")
    assert [p.name for p in got] == ["page_0001.json", "page_0002.json"]


def test_판이_있으면_멈춘다(raw: pathlib.Path) -> None:
    """🚨 이것이 이 파일의 본체다 — 종전에는 **함께 읽고 조용히 버렸다.**"""
    (raw / "page_0001__c20260907.json").write_text("새 판", encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        store.current_files(raw, "*.json")

    assert "page_0001__c20260907.json" in str(e.value)
    assert "D-143" in str(e.value), "누가 정해야 하는지 오류문이 말해야 한다 (D-51)"


def test_대조_규칙을_가진_호출자만_판을_허용한다(raw: pathlib.Path) -> None:
    """`allow_editions=True` 는 **자기 대조 규칙이 있는** 호출자만 쓴다 (`mfds_hf.posts`)."""
    (raw / "page_0001__c20260907.json").write_text("새 판", encoding="utf-8")

    got = store.current_files(raw, "*.json", allow_editions=True)

    assert [p.name for p in got] == ["page_0001.json", "page_0002.json"], (
        "판을 허용해도 **원본을 돌려준다** — 원본 무손상이 먼저다 (D-92)"
    )


def test_원본이_없고_판만_있으면_그_판이_원본이다(tmp_path: pathlib.Path) -> None:
    (tmp_path / "page_0009__c20260907.json").write_text("판만 있다", encoding="utf-8")

    got = store.current_files(tmp_path, "*.json", allow_editions=True)

    assert [p.name for p in got] == ["page_0009__c20260907.json"]


def test_없는_디렉터리는_빈_목록이다(tmp_path: pathlib.Path) -> None:
    assert store.current_files(tmp_path / "없다", "*.json") == []


def test_게시판_목록의_휘발_칸은_판을_만들지_않는다() -> None:
    """🔴 조회수·순번이 갈렸다고 판이 생기면, 볼 때마다 「원천이 바뀌었다」가 된다.

    실측 — 재수집 목록 5개가 「다르다」고 나왔는데 갈린 것은 조회수 12건·순번 42건뿐이었고
    게시물 번호는 **0건 차이**였다. D-168 의 `jsessionid` 와 같은 부류다.
    """
    a = '{"total_cnt":655,"list":[{"ntctxt_no":"1","no":"1","inqry_cnt":"393","titl":"가"}]}'.encode()
    b = '{"total_cnt":655,"list":[{"ntctxt_no":"1","no":"7","inqry_cnt":"394","titl":"가"}]}'.encode()
    src = "mfds_hf_ingredient_board"

    assert store.sha256(a) != store.sha256(b), "표본이 같으면 이 검사는 실패할 수 없다 (D-170)"
    assert store.identity_sha256(src, a) == store.identity_sha256(src, b)


def test_반대_대조_제목이_갈리면_판정_해시도_갈린다() -> None:
    """🚨 위 게이트가 **아무거나 같다고 하지 않음**을 보인다 (D-170)."""
    a = '{"list":[{"ntctxt_no":"1","no":"1","inqry_cnt":"393","titl":"가"}]}'.encode()
    b = '{"list":[{"ntctxt_no":"1","no":"1","inqry_cnt":"393","titl":"나"}]}'.encode()
    src = "mfds_hf_ingredient_board"

    assert store.identity_sha256(src, a) != store.identity_sha256(src, b)
