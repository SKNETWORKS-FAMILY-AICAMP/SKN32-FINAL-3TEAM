"""오류 로그 화면의 쪽 번호 처리 (2026-09-21 · 코드 리뷰 6번).

★ 재는 것 셋 —
  ① 쪽 번호에 상한이 있다 — 거대한 수가 SQL `OFFSET` 을 bigint 밖으로 밀지 못한다
  ② 🔴 DB 가 멀쩡한데 쪽 번호만 나빴다고 **더미 화면으로 떨어지지 않는다**
  ③ 실제 쪽 수를 넘는 번호는 마지막 쪽으로 본다

🚨 DB 없이 돈다 — 가짜 연결로 `OFFSET` 값과 `source` 만 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.routers import admin_errors as ae

_INT8_MAX = 2**63 - 1


class _FakeCursor:
    def __init__(self, total: int, log: list[tuple[str, list]]) -> None:
        self._total = total
        self._log = log

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: list | None = None) -> None:
        self._log.append((sql, list(params or [])))

    def fetchone(self) -> dict:
        return {"n": self._total}

    def fetchall(self) -> list[dict]:
        return []


class _FakeConn:
    def __init__(self, total: int, log: list[tuple[str, list]]) -> None:
        self._total = total
        self._log = log

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._total, self._log)


def _fake_db(monkeypatch: pytest.MonkeyPatch, total: int) -> list[tuple[str, list]]:
    log: list[tuple[str, list]] = []
    monkeypatch.setattr(ae, "_connect", lambda: _FakeConn(total, log))
    return log


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 1),
        ("", 1),
        ("abc", 1),
        ("0", 1),
        ("-5", 1),
        ("3", 3),
        ("99999999999999999999999", ae._MAX_PAGE),
    ],
)
def test_쪽_번호는_1과_상한_사이로_들어온다(value: str | None, expected: int) -> None:
    assert ae._clean_page(value) == expected


def test_상한_쪽의_OFFSET_이_bigint_안이다() -> None:
    assert (ae._MAX_PAGE - 1) * ae.PAGE_SIZE <= _INT8_MAX


def test_거대한_쪽_번호가_DB_정상인데_더미로_떨어지지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _fake_db(monkeypatch, total=120)
    page = ae._clean_page("99999999999999999999999")

    data = ae._load_list(None, None, page)

    assert data["source"] == "db"
    offset = log[-1][1][-1]
    assert offset <= _INT8_MAX


def test_실제_쪽_수를_넘는_번호는_마지막_쪽이_된다(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _fake_db(monkeypatch, total=120)  # 50 · 50 · 20 → 3쪽

    data = ae._load_list(None, None, 999)

    assert data["page"] == 3
    assert log[-1][1][-2:] == [ae.PAGE_SIZE, 2 * ae.PAGE_SIZE]  # LIMIT · OFFSET


def test_범위_안의_쪽_번호는_그대로다(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_db(monkeypatch, total=120)

    assert ae._load_list(None, None, 2)["page"] == 2


def test_건수가_0이어도_1쪽이다(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _fake_db(monkeypatch, total=0)

    data = ae._load_list(None, None, 7)

    assert data["page"] == 1
    assert log[-1][1][-1] == 0


def test_DB_가_없으면_빈_1쪽과_모름으로_그린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔄 2026-09-22 — 더미 5건을 지웠다(D-147). 못 읽었으면 행 없음 · 건수 **None**(0 이 아니다 · D-72)."""

    def _boom() -> None:
        raise ConnectionError("no db")

    monkeypatch.setattr(ae, "_connect", _boom)

    data = ae._load_list(None, None, 5)

    assert data["source"] == "no_db"
    assert data["page"] == 1
    assert data["rows"] == []
    assert data["total"] is None, "🔴 못 읽은 건수를 수로 적었다"


def test_DB_가_없으면_단건도_없음이_아니라_모름이다(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> None:
        raise ConnectionError("no db")

    monkeypatch.setattr(ae, "_connect", _boom)

    data = ae._load_one("00000000-0000-0000-0000-000000000000")

    assert data == {"source": "no_db", "row": None, "same": []}


def test_더미_행이_코드에_남아_있지_않다() -> None:
    """🔴 가짜 오류를 그리면 「오류가 있다」가 거짓이 된다 (D-147) — 되살아나는 것을 막는다."""
    src = Path(ae.__file__).read_text(encoding="utf-8")
    assert "_DUMMY" not in src and "dummy_no_" not in src
