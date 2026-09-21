"""2026-09-21 전수 재검토 · 페이지 가드 — 원천이 덜 줘도 「완료」로 끝나던 세 수집기.

🚨 **게이트가 아니다** — 네트워크는 가짜, 저장·원장 기록은 기록기로 돈다.
   ① `openapi` — 받은 행 < 신고면 완료로 안 찍고 1 · 전체 건수 못 읽음이면 안 찍음 · 끝 신호 없으면 상한에서 멈춤
   ② `ftc_body` — `totalCnt` 없음은 0 이 아니라 멈춤 · 중간 빈 장은 못 본 건수로 셈
   ③ `law_api._search_hits` — `totalCnt` 없음은 멈춤 · 깨진 장만큼을 부르는 쪽이 실패로 셈
"""

from __future__ import annotations

import json

import pytest

from collect import ftc_body, law_api, openapi


# ── ① openapi ─────────────────────────────────────────────────────────────
@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> dict:
    w: dict = {"pages": {}, "marked": [], "saved": []}
    monkeypatch.setattr(openapi.registry, "require", lambda sid, use: None)
    monkeypatch.setattr(openapi.registry, "is_g2", lambda sid: False)
    monkeypatch.setattr(
        openapi.registry,
        "mark_if_complete",
        lambda sid, *, saved, partial: w["marked"].append(partial) or not partial,
    )
    monkeypatch.setattr(openapi, "spec_of", lambda sid: {"url": "http://x"})
    monkeypatch.setattr(openapi.env, "load", lambda: None)
    monkeypatch.setattr(openapi.env, "get", lambda name: "k")
    monkeypatch.setattr(openapi.store, "family_path", lambda sid: openapi.store.ROOT / "x")
    monkeypatch.setattr(
        openapi.store, "save_raw", lambda sid, fam, fn, payload, *, url: w["saved"].append(fn) or fn
    )
    monkeypatch.setattr(openapi, "fetch_page", lambda ep, key, page: w["pages"](page))
    return w


def _page(rows: int, total: int | None, start: int = 0) -> bytes:
    body: dict = {"items": [{"id": start + i, "pad": "x" * 80} for i in range(rows)]}
    if total is not None:
        body["totalCount"] = total
    return json.dumps(body).encode()


def test_받은_행이_신고보다_적으면_완료로_찍지_않는다(api: dict, monkeypatch) -> None:
    """🔴 원천이 한 장에 ROWS 보다 적게 주면 `page * ROWS >= total` 에서 뒤쪽을 안 받고 끝났다."""
    monkeypatch.setattr(openapi, "ROWS", 10)
    api["pages"] = lambda p: _page(5, 20, start=p * 100)  # 한 장 5행 · 2장이면 멈춤 → 10 < 20
    assert openapi.collect("s", "U1", None) == 1
    assert api["marked"] == [True]


def test_신고만큼_받으면_완료다(api: dict, monkeypatch) -> None:
    monkeypatch.setattr(openapi, "ROWS", 10)
    api["pages"] = lambda p: _page(10, 20, start=p * 100)
    assert openapi.collect("s", "U1", None) == 0
    assert api["marked"] == [False]


def test_전체_건수를_못_읽으면_완료로_찍지_않는다(api: dict) -> None:
    api["pages"] = lambda p: _page(3, None, start=p * 100) if p < 3 else _page(0, None)
    assert openapi.collect("s", "U1", None) == 0
    assert api["marked"] == [True]


def test_끝_신호가_오지_않으면_상한에서_멈춘다(api: dict, monkeypatch) -> None:
    """🔴 범위 밖 장에 같은 행을 되풀이하는 원천이면 전체 건수 없이 영영 돌았다."""
    monkeypatch.setattr(openapi, "MAX_PAGES", 5)
    api["pages"] = lambda p: _page(3, None)  # 늘 같은 3행 · 늘 200바이트 이상
    assert openapi.collect("s", "U1", None) == 1
    assert api["marked"] == [True]
    assert len(api["saved"]) == 5


# ── ② ftc_body ────────────────────────────────────────────────────────────
def _ftc_list(total: str | None, n: int, start: int = 0) -> bytes:
    tc = f"<totalCnt>{total}</totalCnt>" if total is not None else ""
    items = "".join(
        f"<ftc><결정문일련번호>{start + i}</결정문일련번호><사건명>건{i}</사건명><결정일자>2020.1.1.</결정일자></ftc>"
        for i in range(n)
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><FtcSearch>{tc}{items}</FtcSearch>'.encode()


def test_ftc_목록에_전체_건수가_없으면_0_이_아니라_멈춘다(monkeypatch) -> None:
    monkeypatch.setattr(ftc_body.law_api, "_call", lambda base, oc, **p: _ftc_list(None, 0))
    with pytest.raises(SystemExit, match="totalCnt"):
        ftc_body.list_page("oc", 1, "", 2, "ddes")


def test_ftc_목록이_0_건이면_0_이다(monkeypatch) -> None:
    monkeypatch.setattr(ftc_body.law_api, "_call", lambda base, oc, **p: _ftc_list("0", 0))
    assert ftc_body.list_page("oc", 1, "", 2, "ddes") == (0, [])


def test_ftc_중간에_빈_장이_오면_못_본_건수를_돌려준다(monkeypatch) -> None:
    """🔴 신고 250 · 1장 100건 뒤 2장이 비면 ⛔ 종전에는 조용히 끝났다."""
    monkeypatch.setattr(ftc_body.registry, "require", lambda sid, use: None)
    monkeypatch.setattr(ftc_body.env, "get", lambda name: "oc")
    monkeypatch.setattr(ftc_body.store, "raw_dir", lambda fam: ftc_body.store.ROOT / "ftc")
    monkeypatch.setattr(ftc_body.store, "already_have", lambda p: True)  # 본문은 부르지 않는다
    pages = {1: (250, [(str(i), "n", "2020.1.1.") for i in range(100)]), 2: (250, [])}
    monkeypatch.setattr(ftc_body, "list_page", lambda oc, page, q, s, so: pages[page])
    got = ftc_body.collect(
        query="", search=2, sort="ddes", limit=None, dry_run=False, refetch=False
    )
    assert got == (0, 100, 0, 0, 150)


# ── ③ law_api._search_hits ────────────────────────────────────────────────
def _law_list(total: str | None, ids: list[str]) -> bytes:
    tc = f"<totalCnt>{total}</totalCnt>" if total is not None else ""
    items = "".join(
        f"<prec><판례일련번호>{i}</판례일련번호><사건명>표시광고</사건명></prec>" for i in ids
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><PrecSearch>{tc}{items}</PrecSearch>'.encode()


def test_검색_응답에_전체_건수가_없으면_멈춘다(monkeypatch) -> None:
    monkeypatch.setattr(law_api, "_call", lambda base, oc, **p: _law_list(None, []))
    with pytest.raises(SystemExit, match="totalCnt"):
        law_api._search_hits("oc", "prec", "q", section=law_api.SEARCH_NAME)


def test_깨진_장만큼을_못_받은_건수로_돌려준다(monkeypatch) -> None:
    monkeypatch.setattr(law_api, "SEARCH_ROWS", 2)

    def fake(base: str, oc: str, **p: str) -> bytes:
        page = p.get("page")
        if page is None:
            return _law_list("4", [])
        return b"<html>oops" if page == "2" else _law_list("4", ["1", "2"])

    monkeypatch.setattr(law_api, "_call", fake)
    ids, short = law_api._search_hits("oc", "prec", "q", section=law_api.SEARCH_NAME)
    assert [i for i, _ in ids] == ["1", "2"]
    assert short == 2
