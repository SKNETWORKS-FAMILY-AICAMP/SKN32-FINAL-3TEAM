"""수집기가 짓는 원문 파일 이름 (2026-09-22 · 클론 A 재검토 2판 §3-4 · 3판 §0 ⑦).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89) — `test_mfds_board.py` 와 같은 자리.

지키는 것 둘 —
  ① 이름을 줄여도 **확장자가 남는다** — 잃으면 추출기가 파일을 못 읽는다
  ② 우리가 지은 이름에 **판 표시(`__c`)가 우연히 들지 않는다** — 들면 `store` 가 다른 파일의 판으로 읽는다
"""

from __future__ import annotations

from pathlib import Path

from collect import store
from collect.mfds_board import SLUG_MAX, _slug
from collect.mfds_press import attach_dest


def test_긴_이름은_몸통을_줄이고_확장자를_남긴다() -> None:
    got = _slug("가" * 200 + ".pdf")
    assert len(got) <= SLUG_MAX and got.endswith(".pdf"), got


def test_짧은_이름은_그대로다() -> None:
    """반대 대조 — 기존 파일 이름이 바뀌면 다시 받는다. 지금 이름들(최대 41자)은 그대로여야 한다."""
    name = "식품·의약품등의 온라인 자율관리 가이드라인(해설판)-(게시용).pdf"
    assert _slug(name) == "식품·의약품등의_온라인_자율관리_가이드라인(해설판)-(게시용).pdf"


def test_확장자가_없는_긴_이름은_잘라만_둔다() -> None:
    assert _slug("나" * 200) == "나" * SLUG_MAX


def test_공백과_밑줄이_판_표시를_만들지_않는다() -> None:
    got = _slug("보도자료 _cover.pdf")
    assert store.EDITION_MARK not in got, got
    assert Path(got).stem.split(store.EDITION_MARK, 1)[0] == Path(got).stem


def test_판인_게시물의_첨부도_판을_뗀_번호로_짓는다() -> None:
    assert attach_dest("45732", 1) == "45732_1.pdf"
    assert attach_dest("45732__c20260909", 2) == "45732_2.pdf"
    assert store.EDITION_MARK not in attach_dest("45732__c20260909", 1)
