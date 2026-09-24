"""`preprocess/chunk.py` 하한 래칫 (2026-09-20 · D-254 · 감사 §1-8).

⛔ 09-18 조문 노드가 2,207 → 1,873 으로 **조용히** 줄었고 게이트는 초록이었다.
   그 판이 `chunks.jsonl` 로 쓰이면 `embed` 가 DB 에서 그만큼 지운다.
★ 여기서는 이전 판 대비 `SHRINK_LIMIT` 를 넘게 줄면 **쓰기 전에** 멈추는지를 본다.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

from preprocess import chunk


def _row(i: int, frag: str) -> dict:
    return {
        "chunk_id": f"{frag}#{i}",
        "fragment_id": frag,
        "law": "표시광고법",
        "text": f"본문 {i}",
        "part_total": 1,
    }


def _rows(n_art: int, n_annex: int) -> list[dict]:
    return [_row(i, "law_go_kr:article") for i in range(n_art)] + [
        _row(i, "law_go_kr:annex") for i in range(n_annex)
    ]


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    monkeypatch.setattr(chunk, "ROOT", tmp_path.parent)
    monkeypatch.setattr(chunk.store, "stamp", lambda r, _sid: r)

    def run(n_art: int, n_annex: int, *argv: str) -> int:
        new = _rows(n_art, n_annex)
        monkeypatch.setattr(
            chunk, "from_articles", lambda: ([r for r in new if "article" in r["fragment_id"]], 0)
        )
        monkeypatch.setattr(
            chunk, "from_annex", lambda: [r for r in new if "annex" in r["fragment_id"]]
        )
        monkeypatch.setattr(sys, "argv", ["chunk", *argv])
        return chunk.main()

    def seed(n_art: int, n_annex: int) -> pathlib.Path:
        out = tmp_path / "chunks.jsonl"
        out.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in _rows(n_art, n_annex)),
            encoding="utf-8",
        )
        return out

    return run, seed


@pytest.mark.gate
def test_이전_판보다_크게_줄면_쓰지_않고_멈춘다(world) -> None:
    run, seed = world
    out = seed(100, 20)
    before = out.read_bytes()
    assert run(85, 20, "--dump") == 1  # 조문 −15% — 09-18 사고의 모양
    assert out.read_bytes() == before, "🔴 멈췄는데 이전 판이 덮였다"


@pytest.mark.gate
def test_한_층만_줄어도_잡는다(world) -> None:
    """🚨 전체로는 −4% 라도 별표 층이 −50% 면 멈춘다 — 층별로 본다."""
    run, seed = world
    seed(200, 10)
    assert run(200, 5, "--dump") == 1


def test_allow_shrink_면_쓴다(world) -> None:
    run, seed = world
    out = seed(100, 20)
    assert run(85, 20, "--dump", "--allow-shrink") == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 105


def test_문턱_안의_변동과_증가는_막지_않는다(world) -> None:
    run, seed = world
    seed(100, 20)
    assert run(96, 20, "--dump") == 0  # −4% (문턱 5% 안)
    assert run(300, 40, "--dump") == 0  # 늘어난 것은 막지 않는다


def test_이전_판이_없으면_비교하지_않는다(world) -> None:
    run, _seed = world
    assert run(3, 1, "--dump") == 0


def test_미리보기는_줄어도_rc0_이고_쓰지_않는다(world) -> None:
    run, seed = world
    out = seed(100, 20)
    before = out.read_bytes()
    assert run(50, 20) == 0
    assert out.read_bytes() == before


def test_층이_통째로_사라지면_줄어든_것이다() -> None:
    assert chunk.shrinkage({"전체": 10, "a": 5, "b": 5}, {"전체": 10, "a": 10})
    assert chunk.shrinkage({"a": 100}, {"a": 95}) == []  # 정확히 5% 는 문턱 안
    assert chunk.shrinkage({"a": 100}, {"a": 94})


@pytest.mark.gate
def test_법을_못_정한_청크가_있으면_쓰지_않고_멈춘다(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🆕 W6 (2026-09-24 · D-271 ①) — ⛔ 종전 `category_of()` 는 모르면 「일반」을 줬다. 기본값으로 떨어뜨리지 않는다."""
    run, seed = world
    out = seed(10, 2)
    before = out.read_bytes()
    orig_rows = (
        _rows  # 🚨 `world.run` 은 부를 때마다 이 모듈의 `_rows` 를 찾는다 — 그것을 바꿔 끼운다
    )

    def rows_with_unknown(n_art: int, n_annex: int) -> list[dict]:
        rs = orig_rows(n_art, n_annex)
        rs[0] = {**rs[0], "law": None, "law_id": "999999"}
        return rs

    monkeypatch.setattr(sys.modules[__name__], "_rows", rows_with_unknown)
    assert run(10, 2, "--dump") == 1
    assert out.read_bytes() == before, "🔴 멈췄는데 이전 판이 덮였다"


@pytest.mark.gate
def test_별표_청크는_별표_제목과_상위_항목을_문맥으로_든다() -> None:
    """🆕 2026-09-24 (W6 재측정) — 「제품명」 같은 목록 청크가 벡터 상위를 점령했다. 조문(0008)과 같은 처방이다.

    🚨 `text` 는 그대로 · 상위 항목은 **같은 구역**에서만 찾는다 · 못 찾으면 있는 것만 붙인다(지어내지 않는다).
    """
    by_path = {
        ("본문", "1"): "수입 식품등",
        ("본문", "1.가"): "가 항목",
        ("비고", "1"): "비고 본문",
    }
    base = {"annex_no_head": 1, "annex_title": "식품등의 일부 표시사항", "section": "본문"}
    assert chunk._annex_context({**base, "path": "1"}, by_path) == "[별표 1] 식품등의 일부 표시사항"
    assert chunk._annex_context({**base, "path": "1.가.3"}, by_path) == (
        "[별표 1] 식품등의 일부 표시사항\n수입 식품등\n가 항목"
    )
    assert chunk._annex_context({**base, "section": "비고", "path": "1.가"}, by_path) == (
        "[별표 1] 식품등의 일부 표시사항 · 비고\n비고 본문"
    ), "🔴 다른 구역(본문)의 항목을 끌어왔다"
    assert (
        chunk._annex_context({**base, "path": "9.가"}, by_path) == "[별표 1] 식품등의 일부 표시사항"
    )
