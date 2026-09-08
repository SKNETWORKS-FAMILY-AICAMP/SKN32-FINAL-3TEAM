"""`preprocess.hwp` — HWP 5.x 레코드·글자 읽기 (2026-09-08 · D-150).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

🚨 실물 검증은 여기서 못 한다 — 파일이 `data/`(비배포)에 있다.
   실물 쪽은 `Table.check()` 가 **원천의 선언(행 수·행별 셀 수)과 대조**해서 잡는다.
   여기서 지키는 것은 **선언과 대조할 수 없는 것**, 즉 바이트 해석 규칙이다.
"""

from __future__ import annotations

import struct

from preprocess.hwp import Cell, Table, para_text, records


def _rec(tag: int, level: int, payload: bytes) -> bytes:
    assert len(payload) < 0xFFF
    return struct.pack("<I", tag | (level << 10) | (len(payload) << 20)) + payload


def test_records_reads_tag_level_size() -> None:
    buf = _rec(67, 2, b"ab") + _rec(72, 1, b"cdef")
    assert list(records(buf)) == [(67, 2, b"ab"), (72, 1, b"cdef")]


def test_records_handles_extended_size() -> None:
    """🚨 크기가 0xFFF 면 **다음 4바이트가 진짜 크기**다 — 이걸 놓치면 전부 밀린다."""
    big = b"x" * 5000
    buf = struct.pack("<I", 67 | (2 << 10) | (0xFFF << 20)) + struct.pack("<I", len(big)) + big
    assert list(records(buf)) == [(67, 2, big)]


def test_para_text_plain() -> None:
    assert para_text("가나다".encode("utf-16-le")) == "가나다"


def test_para_text_skips_inline_control() -> None:
    """🔴 **인라인 제어문자는 8 wchar 를 먹는다.** 1 로 세면 뒤 글자가 통째로 밀린다 —

    읽히기는 하는데 내용이 어긋나는, 오늘 내내 본 종류의 조용한 실패다.
    """
    data = (
        "가".encode("utf-16-le")
        + struct.pack("<8H", 9, 0, 0, 0, 0, 0, 0, 9)
        + "나".encode("utf-16-le")
    )
    assert para_text(data) == "가\t나"


def test_para_text_line_break() -> None:
    data = "가".encode("utf-16-le") + struct.pack("<H", 10) + "나".encode("utf-16-le")
    assert para_text(data) == "가\n나"


def test_table_check_catches_mismatch() -> None:
    """🔴 원천의 선언과 어긋나면 **멈춘다.** 어긋난 채로 라벨을 만들면 되돌릴 수 없다."""
    t = Table(rows=2, cols=1, row_cells=(1, 1), cells=[Cell(0, 0, 1, 1), Cell(1, 0, 1, 1)])
    assert t.check() == ""
    t.cells.pop()
    assert "선언과 다르다" in t.check()


def test_grid_places_cells_by_address() -> None:
    t = Table(
        rows=2,
        cols=2,
        row_cells=(2, 2),
        cells=[
            Cell(0, 0, 1, 1, ["가"]),
            Cell(0, 1, 1, 1, ["나"]),
            Cell(1, 0, 1, 1, ["다"]),
            Cell(1, 1, 1, 1, ["라"]),
        ],
    )
    assert t.grid() == [["가", "나"], ["다", "라"]]
