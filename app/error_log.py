"""app/error_log.py — WARNING 이상 앱 로그를 `app_error_log` 에 쌓는다 · 🆕 2026-09-22.

요청 — 소성민 (`docs/ssm/요청_2026-09-16_app_error_log.md`). 요청 §3 의 네 약속을 그대로 지키고, 검토에서 넷을 더했다.

  요청 §3                                         검토에서 더한 것
  ① 핸들러 **자신에게** `RedactFilter` 를 단다      ⑤ **백그라운드 기록기** — `emit()` 은 줄을 대기열에 넣기만 한다
  ② DB 실패가 앱을 죽이지 않고 다시 로그가 되지 않는다  ⑥ 쓰기가 실패하면 **쉬었다가**(`ERROR_LOG_BACKOFF_S`) 다시 — 죽은 DB 에 줄마다 붙지 않는다
  ③ 오류 원인 문자열을 남기지 않는다(클래스 이름만)     ⑦ **버린 줄을 센다** — 대기열이 차거나 쓰기가 실패하면 stderr 로 한 줄 (D-72 · 없음이 성공으로 안 보이게)
  ④ `sqlalchemy.engine` 레코드를 받지 않는다          ⑧ 한 줄 상한(`ERROR_LOG_MESSAGE_MAX`)에서 자른다 · 보관 기간(`ERROR_LOG_RETENTION_DAYS`)이 지난 행을 지운다

🔴 **왜 백그라운드인가** — `emit()` 에서 바로 INSERT 하면 DB 가 응답하지 않을 때 **WARNING 한 줄마다** 연결을 기다린다.
   그런데 DB 가 죽으면 앱은 「DB 접속 실패」 경고를 남기고, 그 경고가 다시 DB 를 부른다 — 느려짐이 불어난다.
🔴 **켜는 조건은 `settings.error_log_enabled()` 한 곳이다** — `auto` 는 `onprem`·`demo` 만. `local`(개발 기기·테스트)과
   `cloud`(볼 화면이 없다 · D-213)는 끈다. 테스트는 `tests/conftest.py` 가 `off` 로 못 박는다 — 게이트가 `app.api` 를 import 한다.
🚨 이 모듈은 **로그를 남기지 않는다** — 자기 실패를 `logging` 으로 알리면 그 줄이 다시 여기로 온다. 알릴 것은 `sys.stderr` 로 쓴다.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import queue
import sys
import threading
import time
from typing import Any

from app.logging_conf import RedactFilter
from app.models import ERROR_LOG_LEVELS
from app.settings import (
    ERROR_LOG_BACKOFF_S,
    ERROR_LOG_MESSAGE_MAX,
    ERROR_LOG_QUEUE_MAX,
    ERROR_LOG_RETENTION_DAYS,
)

#: 받지 않는 로거(앞부분 일치). 🚨 `sqlalchemy`·`psycopg` 는 바인딩 파라미터(=문구 원문)를 담을 수 있고(요청 §3 ④),
#:    기록기가 쓰는 드라이버 자신의 경고가 다시 여기로 오면 되먹임이 된다.
EXCLUDED_LOGGERS = ("sqlalchemy", "psycopg", "alembic", "copylane.error_log")

#: `[임의]` 지난 행을 지우는 주기. 기록기가 뜰 때 한 번, 그 뒤 이 간격마다.
PURGE_EVERY_S = 6 * 3600
#: `[임의]` 한 번에 모아 쓰는 줄 수 — 오류가 몰려도 연결 한 번에 넣는다.
BATCH_MAX = 100

_TRUNC_MARK = "…(잘림)"
_INSERT = (
    "INSERT INTO app_error_log (level, logger_name, message, exc_type, module, func_name, lineno) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_PURGE = "DELETE FROM app_error_log WHERE occurred_at < now() - make_interval(days => %s)"


def to_row(record: logging.LogRecord) -> tuple[Any, ...]:
    """레코드 → 표 한 줄. 🚨 **필터를 지난 뒤**에 부른다 — `getMessage()` 가 가린 문장을 낸다.

    ★ 예외는 **클래스 이름만** — 트레이스백도 예외 메시지도 안 담는다(요청 §2 · 필터 밖이었다).
    """
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001 — 인자 개수가 틀린 로그 호출. 형식 문자열만 남긴다
        message = str(record.msg)
    if len(message) > ERROR_LOG_MESSAGE_MAX:
        message = message[: ERROR_LOG_MESSAGE_MAX - len(_TRUNC_MARK)] + _TRUNC_MARK
    exc = record.exc_info[0] if record.exc_info else None
    return (
        record.levelname,
        record.name[:80],
        message,
        exc.__name__[:120] if exc is not None else None,
        (record.module or None) and record.module[:120],
        (record.funcName or None) and record.funcName[:120],
        record.lineno,
    )


class _Writer:
    """대기열 하나 · 스레드 하나. 🚨 여기서 난 일은 **stderr** 로만 알린다 (모듈 머리말)."""

    def __init__(self, connect: Any, *, backoff_s: float = ERROR_LOG_BACKOFF_S) -> None:
        self._connect = connect
        self._backoff_s = backoff_s
        self.q: queue.Queue[tuple[Any, ...] | None] = queue.Queue(maxsize=ERROR_LOG_QUEUE_MAX)
        self.dropped_full = 0
        self.dropped_db = 0
        self.written = 0
        self._reported = 0
        self._retry_at = 0.0
        self._purge_at = 0.0
        self.thread = threading.Thread(target=self._run, name="copylane-error-log", daemon=True)

    # ── 요청 스레드 쪽 — 막지 않는다 ──
    def put(self, row: tuple[Any, ...]) -> None:
        try:
            self.q.put_nowait(row)
        except queue.Full:
            self.dropped_full += 1

    # ── 기록기 스레드 ──
    def _run(self) -> None:
        while True:
            item = self.q.get()
            if item is None:
                return
            batch = [item]
            while len(batch) < BATCH_MAX:
                try:
                    nxt = self.q.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    self._write(batch)
                    return
                batch.append(nxt)
            self._write(batch)

    def _write(self, batch: list[tuple[Any, ...]]) -> None:
        now = time.monotonic()
        if now < self._retry_at:
            self.dropped_db += len(batch)  # 🚨 쉬는 중 — 붙지 않고 버린다. 버린 수는 센다
            self._report()
            return
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.executemany(_INSERT, batch)
                if now >= self._purge_at:
                    cur.execute(_PURGE, (ERROR_LOG_RETENTION_DAYS,))
                    self._purge_at = now + PURGE_EVERY_S
            self.written += len(batch)
        except Exception as e:  # noqa: BLE001 — 🚨 원인 문자열은 안 적는다(호스트·포트·사용자명 · 요청 §3 ③)
            self.dropped_db += len(batch)
            self._retry_at = now + self._backoff_s
            self._report(type(e).__name__)
        else:
            self._report()

    def _report(self, why: str = "") -> None:
        """버린 수가 늘었으면 stderr 로 한 줄 — 🚨 `logging` 을 쓰지 않는다(되먹임)."""
        total = self.dropped_full + self.dropped_db
        if total == self._reported:
            return
        self._reported = total
        with contextlib.suppress(Exception):
            sys.stderr.write(
                f"[copylane.error_log] app_error_log 에 못 쓴 줄 누적 {total} "
                f"(대기열 가득 {self.dropped_full} · DB 실패 {self.dropped_db})"
                + (f" — {why} · {self._backoff_s:g}초 쉬고 다시" if why else "")
                + " · stdout 로그에는 남아 있다\n"
            )

    def stop(self, timeout: float = 2.0) -> None:
        with contextlib.suppress(queue.Full):
            self.q.put_nowait(None)
        self.thread.join(timeout)


class DbErrorHandler(logging.Handler):
    """WARNING 이상을 대기열에 넣는다. 🚨 **`emit()` 은 DB 를 부르지 않는다.**"""

    def __init__(self, writer: _Writer) -> None:
        super().__init__(level=logging.WARNING)
        self.writer = writer
        # 🔴 요청 §3 ① — 자식 로거(`copylane.admin` …)의 레코드는 부모 로거의 필터를 안 지난다. **핸들러에 직접** 단다.
        #    ★ 순서가 뜻이 있다 — 받지 않을 로거를 먼저 거르고, 남은 것을 가린다.
        self.addFilter(self._accept)
        self.addFilter(RedactFilter())

    def _accept(self, record: logging.LogRecord) -> bool:
        if record.levelname not in ERROR_LOG_LEVELS:
            return False  # 사용자 정의 레벨 — 표의 CHECK 가 받지 않는다
        if record.name.startswith(EXCLUDED_LOGGERS):
            return False
        # 🚨 기록기 스레드가 남긴 줄은 받지 않는다 — 되먹임의 마지막 구멍
        return record.thread != self.writer.thread.ident

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.writer.put(to_row(record))
        except Exception:  # noqa: BLE001 — 🚨 로그 한 줄이 요청을 죽이지 않는다
            self.writer.dropped_full += 1


_installed: DbErrorHandler | None = None


def install(connect: Any = None, *, logger: logging.Logger | None = None) -> DbErrorHandler:
    """핸들러를 root 에 붙이고 기록기를 띄운다. 🚨 **두 번 불러도 하나다.**

    `connect` — 연결을 여는 함수(기본 `app.db.pg_connect(autocommit=True)` · 대기 상한 한 곳 · D-99).
    """
    global _installed
    if _installed is not None:
        return _installed
    if connect is None:
        from app.db import pg_connect  # noqa: PLC0415 — DB 가 없어도 import 는 선다

        def connect() -> Any:
            return pg_connect(autocommit=True)

    writer = _Writer(connect)
    writer.thread.start()
    handler = DbErrorHandler(writer)
    (logger or logging.getLogger()).addHandler(handler)
    atexit.register(writer.stop)
    _installed = handler
    return handler


def uninstall(logger: logging.Logger | None = None) -> None:
    """테스트용 — 핸들러를 떼고 기록기를 멈춘다."""
    global _installed
    if _installed is None:
        return
    (logger or logging.getLogger()).removeHandler(_installed)
    _installed.writer.stop()
    _installed = None
