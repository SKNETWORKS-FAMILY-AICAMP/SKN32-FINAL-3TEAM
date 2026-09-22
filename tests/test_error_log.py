"""오류 로그 표(`app_error_log`)와 그 기록기 — 🆕 2026-09-22 (ssm 요청 · 보안점검 P1-4).

★ 재는 것 —
  ① 표에 들어가는 줄은 **가린 문장**과 예외 **클래스 이름**뿐이다 (예외 메시지·트레이스백 없음)
  ② 한 줄 상한에서 자른다 — 자르기 수와 표의 CHECK 가 **같은 수**다
  ③ 받지 않는 로거(`sqlalchemy`·`psycopg` …)와 기록기 스레드 자신의 줄은 안 받는다 (되먹임)
  ④ 🔴 `emit()` 은 **막지 않는다** — DB 가 매달려도, 죽어도. 죽으면 쉬었다 다시 · 버린 수는 센다 (D-72)
  ⑤ 켜는 조건은 `error_log_enabled()` 한 곳 — cloud 는 `on` 이어도 끈다 (D-213)
  ⑥ `app/` 에서 `psycopg.connect` 를 바로 부르는 곳은 `app/db.py` 하나다 (대기 상한 한 곳 · D-99)
  ⑦ (DB 있을 때만) 실제 표에 쓰고, 보관 기간이 지난 행을 지운다

🚨 ①~⑥ 은 DB 없이 돈다 — 가짜 연결로 잰다. ⑦ 은 `COPYLANE_DB_IT=1` 일 때만 돈다 —
   테스트가 개발 DB 에 행을 남기지 않게(기본 꺼짐 · `tests/conftest.py`).
"""

from __future__ import annotations

import ast
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from app import error_log as el
from app.models import ERROR_LOG_LEVELS
from app.settings import (
    ERROR_LOG_MESSAGE_MAX,
    ERROR_LOG_RETENTION_DAYS,
    Settings,
    error_log_enabled,
)

ROOT = Path(__file__).resolve().parents[1]
_MIGRATION = ROOT / "alembic" / "versions" / "20260922_0016_app_error_log.py"
_LEAK = "면역력이 쑥쑥"


# ── 가짜 기록기 · 가짜 연결 ──────────────────────────────────────


class _ListWriter:
    """`DbErrorHandler` 가 넣는 줄을 모은다 — 스레드를 띄우지 않는다."""

    def __init__(self) -> None:
        self.rows: list[tuple[Any, ...]] = []
        self.dropped_full = 0
        # ident None — 어떤 레코드의 스레드와도 안 겹친다
        self.thread = threading.Thread(target=lambda: None)

    def put(self, row: tuple[Any, ...]) -> None:
        self.rows.append(row)


def _handler() -> tuple[el.DbErrorHandler, _ListWriter]:
    w = _ListWriter()
    return el.DbErrorHandler(w), w  # type: ignore[arg-type]


def _record(
    msg: str,
    *args: object,
    name: str = "copylane.test",
    level: int = logging.WARNING,
    exc_info: Any = None,
) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 7, msg, args or None, exc_info)


def _exc_info(message: str) -> Any:
    try:
        raise ValueError(message)
    except ValueError:
        import sys  # noqa: PLC0415

        return sys.exc_info()


class _Conn:
    def __init__(self, sink: list[Any]) -> None:
        self._sink = sink

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def cursor(self) -> _Conn:
        return self

    def executemany(self, sql: str, rows: list[Any]) -> None:
        self._sink.extend(rows)

    def execute(self, sql: str, params: Any = None) -> None:
        self._sink.append(("purge", params))


def _drain(w: el._Writer, timeout: float = 2.0) -> None:
    w.stop(timeout)
    assert not w.thread.is_alive(), "🔴 기록기가 멈추지 않았다"


# ── ① 가린 문장 · 클래스 이름만 ───────────────────────────────────


@pytest.mark.gate
def test_표에_들어가는_줄은_가린_문장이다() -> None:
    h, w = _handler()
    h.handle(_record("판정 실패 text=%s", _LEAK))
    assert len(w.rows) == 1
    level, name, message, exc_type, *_ = w.rows[0]
    assert (level, name, exc_type) == ("WARNING", "copylane.test", None)
    assert "면역력" not in message and "가림" in message, f"🔴 문구가 표로 샜다: {message}"


@pytest.mark.gate
def test_예외는_클래스_이름만_남고_메시지는_어디에도_없다() -> None:
    h, w = _handler()
    h.handle(_record("처리 중 실패", exc_info=_exc_info(f"입력={_LEAK}")))
    row = w.rows[0]
    assert row[3] == "ValueError"
    assert all("면역력" not in str(v) for v in row), f"🔴 예외 메시지가 표로 샜다: {row}"


def test_음성_대조_필터를_빼면_문구가_표로_간다() -> None:
    """🚨 게이트가 아니다 — ①이 「원래 안 새는 입력」이라 통과한 것이 아님을 잰다 (D-203)."""
    row = el.to_row(_record("판정 실패 text=%s", _LEAK))
    assert "면역력" in row[2], "🔴 음성 픽스처가 애초에 안 샌다 — ①의 검사가 무의미하다"


# ── ② 상한 ─────────────────────────────────────────────────


@pytest.mark.gate
def test_긴_줄은_상한에서_자르고_잘렸다고_적는다() -> None:
    row = el.to_row(_record("x" * (ERROR_LOG_MESSAGE_MAX * 3)))
    assert len(row[2]) == ERROR_LOG_MESSAGE_MAX
    assert row[2].endswith("(잘림)")
    edge = el.to_row(_record("y" * ERROR_LOG_MESSAGE_MAX))[2]
    assert edge == "y" * ERROR_LOG_MESSAGE_MAX, "🔴 경계 — 상한과 같은 길이는 안 자른다"


@pytest.mark.gate
def test_자르기_수와_표의_CHECK_가_같다() -> None:
    """🔴 둘이 어긋나면 긴 줄이 CHECK 에 걸려 **배치째** 버려진다."""
    src = _MIGRATION.read_text(encoding="utf-8")
    m = re.search(r"char_length\(message\) <= (\d+)", src)
    assert m and int(m.group(1)) == ERROR_LOG_MESSAGE_MAX, "🔴 마이그레이션 상한 ≠ 설정값"
    levels = re.search(r"level in \(([^)]*)\)", src)
    assert levels and tuple(re.findall(r"'(\w+)'", levels.group(1))) == ERROR_LOG_LEVELS


# ── ③ 받지 않는 것 ───────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize(
    "name", ["sqlalchemy.engine", "psycopg.pool", "alembic.runtime", "copylane.error_log"]
)
def test_받지_않는_로거는_안_받는다(name: str) -> None:
    h, w = _handler()
    h.handle(_record("x", name=name))
    assert w.rows == []


@pytest.mark.gate
def test_INFO_와_사용자_정의_레벨은_안_받는다() -> None:
    h, w = _handler()
    h.handle(_record("x", level=logging.INFO))
    rec = _record("x", level=35)
    rec.levelname = "NOTICE"
    h.handle(rec)
    assert w.rows == []
    h.handle(_record("x", level=logging.ERROR))
    assert len(w.rows) == 1, "🔴 대조 — ERROR 는 받아야 한다"


@pytest.mark.gate
def test_기록기_스레드가_남긴_줄은_안_받는다() -> None:
    """🔴 되먹임의 마지막 구멍 — 드라이버가 기록기 스레드에서 경고를 남기면 그 줄이 다시 대기열로 온다."""
    w = el._Writer(lambda: _Conn([]))
    h = el.DbErrorHandler(w)
    got: list[bool] = []
    w.thread = threading.Thread(target=lambda: got.append(h.filter(_record("x"))))
    w.thread.start()
    w.thread.join()
    assert got == [False]
    assert h.filter(_record("x")) is not False, "🔴 대조 — 다른 스레드의 줄은 받아야 한다"


# ── ④ 막지 않는다 ────────────────────────────────────────────


@pytest.mark.gate
def test_DB_가_매달려도_emit_은_막지_않는다() -> None:
    gate = threading.Event()

    def _hang() -> _Conn:
        gate.wait(5)
        raise TimeoutError

    w = el._Writer(_hang)
    w.thread.start()
    h = el.DbErrorHandler(w)
    try:
        t0 = time.monotonic()
        for i in range(200):
            h.handle(_record("경고 %d", i))
        assert time.monotonic() - t0 < 0.5, "🔴 emit 이 DB 를 기다렸다"
    finally:
        gate.set()
        _drain(w)


@pytest.mark.gate
def test_DB_가_죽으면_쉬었다_다시_하고_버린_수를_센다(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[int] = []

    def _down() -> _Conn:
        calls.append(1)
        raise ConnectionError("host=secret-host user=secret-user")

    w = el._Writer(_down, backoff_s=60)
    w._write([("WARNING", "a", "m", None, None, None, 1)])
    w._write([("WARNING", "a", "m", None, None, None, 1)] * 3)  # 쉬는 중 — 연결을 안 연다
    assert len(calls) == 1, "🔴 쉬는 중에 다시 붙었다 — 죽은 DB 에 줄마다 붙는다"
    assert w.dropped_db == 4
    err = capsys.readouterr().err
    assert "못 쓴 줄 누적 4" in err and "ConnectionError" in err
    assert "secret-host" not in err and "secret-user" not in err, "🔴 원인 문자열이 stderr 로 샜다"


@pytest.mark.gate
def test_대기열이_차면_버리고_센다() -> None:
    w = el._Writer(lambda: _Conn([]))  # 스레드를 안 띄운다 — 대기열이 찬다
    for _ in range(w.q.maxsize + 5):
        w.put(("WARNING", "a", "m", None, None, None, 1))
    assert w.dropped_full == 5


@pytest.mark.gate
def test_쓰고_보관기간이_지난_행을_지운다() -> None:
    sink: list[Any] = []
    w = el._Writer(lambda: _Conn(sink))
    w.thread.start()
    w.put(("WARNING", "a", "m", None, None, None, 1))
    _drain(w)
    assert sink[0] == ("WARNING", "a", "m", None, None, None, 1)
    assert ("purge", (ERROR_LOG_RETENTION_DAYS,)) in sink
    assert w.written == 1


def test_기록기는_logging_을_쓰지_않는다() -> None:
    """🚨 자기 실패를 `logging` 으로 알리면 그 줄이 다시 여기로 온다 — 모듈에 로거 호출이 없어야 한다."""
    tree = ast.parse(Path(el.__file__).read_text(encoding="utf-8"))
    calls = [
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"debug", "info", "warning", "error", "exception", "critical", "log"}
    ]
    assert calls == [], f"🔴 기록기 모듈이 로그를 남긴다: {calls}"


# ── ⑤ 켜는 조건 ─────────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize(
    ("edition", "mode", "on"),
    [
        ("local", "auto", False),
        ("demo", "auto", True),
        ("onprem", "auto", True),
        ("cloud", "auto", False),
        ("local", "on", True),
        ("cloud", "on", False),  # 🔴 볼 화면이 없다 (D-213) — `on` 이어도 끈다
        ("onprem", "off", False),
    ],
)
def test_켜는_조건(edition: str, mode: str, on: bool) -> None:
    s = Settings(edition=edition, error_log=mode, database_url="postgresql://x", session_secret="")
    assert error_log_enabled(s) is on


@pytest.mark.gate
def test_모르는_값은_설정에서_멈춘다() -> None:
    with pytest.raises(ValueError, match="COPYLANE_ERROR_LOG"):
        Settings(edition="local", error_log="yes", database_url="postgresql://x", session_secret="")


@pytest.mark.gate
def test_테스트에서는_꺼져_있다() -> None:
    """🔴 게이트가 `app.api` 를 import 한다 — 켜져 있으면 테스트 경고가 실제 DB 에 쌓인다 (`conftest.py`)."""
    assert os.environ.get("COPYLANE_ERROR_LOG") == "off"
    assert not error_log_enabled()
    assert not any(isinstance(h, el.DbErrorHandler) for h in logging.getLogger().handlers)


# ── ⑥ 연결 대기 상한 한 곳 ─────────────────────────────────────


@pytest.mark.gate
def test_psycopg_connect_를_바로_부르는_곳은_db_py_하나다() -> None:
    """⛔ 종전 admin·auth·api 가 `psycopg.connect(dsn())` 을 대기 상한 없이 불렀다 — 응답 없는 DB 에 화면이 매달렸다."""
    hits: list[str] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "connect"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "psycopg"
            ):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{n.lineno}")
    assert [h.split(":")[0] for h in hits] == ["app/db.py"], (
        f"🔴 `app.db.pg_connect` 를 안 거친다: {hits}"
    )


# ── ⑦ 실제 표 (선택) ─────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("COPYLANE_DB_IT") != "1",
    reason="실제 DB 에 행을 쓴다 — COPYLANE_DB_IT=1 일 때만",
)
def test_실제_표에_쓰고_지난_행을_지운다() -> None:
    from app.db import pg_connect  # noqa: PLC0415

    name = "copylane.test_error_log"
    with pg_connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM app_error_log WHERE logger_name = %s", (name,))
        cur.execute(
            "INSERT INTO app_error_log (occurred_at, level, logger_name, message) "
            "VALUES (now() - make_interval(days => %s), 'WARNING', %s, 'old')",
            (ERROR_LOG_RETENTION_DAYS + 1, name),
        )
    w = el._Writer(lambda: pg_connect(autocommit=True))
    h = el.DbErrorHandler(w)
    w.thread.start()
    try:
        h.handle(_record("실측 text=%s", _LEAK, name=name))
        h.handle(_record("z" * (ERROR_LOG_MESSAGE_MAX + 50), name=name))
    finally:
        _drain(w)
    try:
        assert w.dropped_db == 0 and w.written == 2
        with pg_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT message FROM app_error_log WHERE logger_name = %s ORDER BY char_length(message)",
                (name,),
            )
            msgs = [r[0] for r in cur.fetchall()]
        assert "old" not in msgs, "🔴 보관 기간이 지난 행이 남았다"
        assert len(msgs) == 2 and "면역력" not in msgs[0] and len(msgs[1]) == ERROR_LOG_MESSAGE_MAX
    finally:
        with pg_connect(autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_error_log WHERE logger_name = %s", (name,))
