"""`collect.mfds_board` — 첨부 고르기 (2026-09-08 · D-148).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 둘이다 —
  ① **중복을 안 받는다** — 같은 자료가 pdf·hwp 두 벌 붙으면 PDF 만
  ② **자료를 안 잃는다** — PDF 가 없으면 hwp 를 받는다

⛔ 원래 규칙은 「PDF 만」이었고, 그래서 `mfds_special_use_guide`(값 A · 1층)가
   **hwp 단독이라는 이유로 아예 못 받고 있었다.** 규칙이 막으려던 것은 중복이지 hwp 가 아니다.
"""

from __future__ import annotations

from collect.mfds_board import KIND, attachments

_A = '<strong>{}</strong> <a href="/brd/down.do?f={}">'


def test_prefers_pdf_when_both_exist() -> None:
    """둘 다 있으면 PDF 만 — 같은 자료를 두 벌 보관하지 않는다."""
    got = attachments(
        _A.format("특수용도식품 해설서.pdf", 2) + _A.format("특수용도식품 해설서.hwp", 3)
    )
    assert [n for n, _ in got] == ["특수용도식품 해설서.pdf"]


def test_falls_back_to_hwp() -> None:
    """🔴 PDF 가 없으면 hwp — 이것이 없어서 값 A 자료가 막혀 있었다."""
    got = attachments(_A.format("특수용도식품 표시광고 해설서.hwp", 1))
    assert [n for n, _ in got] == ["특수용도식품 표시광고 해설서.hwp"]


def test_no_attachment_is_empty() -> None:
    """🚨 「못 찾았다」와 「없다」는 부르는 쪽에서 갈린다 — 여기서는 빈 목록이다."""
    assert attachments("<p>본문만 있는 게시물</p>") == []


def test_magic_bytes_are_per_kind() -> None:
    """🚨 크기만 보면 오류 페이지가 통과한다 (D-118 ②) — 매직바이트를 함께 본다.

    hwp 5.x 는 OLE2 복합문서, hwpx 는 ZIP 이다. 둘을 같은 그물로 잡을 수 없다.
    """
    assert KIND["pdf"][0] == b"%PDF"
    assert KIND["hwp"][0] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    assert KIND["hwpx"][0] == b"PK\x03\x04"
    assert all(floor > 0 for _, floor in KIND.values())
