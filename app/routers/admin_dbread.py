"""app/routers/admin_dbread.py — 관리자 화면이 운영 표를 **읽는** 한 곳 · 소유자 **psj** (병렬작업 계약 §5).

🆕 2026-10-20 — 문의(`ticket`) · 공지(`notice`) · 약관(`terms`) · 회원(`user_account`) · 검수 통계(`judgment`)
   화면이 더미 대신 DB 를 읽는다. 다섯 화면이 같은 연결 · 같은 상태 구분을 쓰게 여기 한 벌로 둔다 (D-99).

★ 상태는 셋이다 — `admin_errors.py` 와 같다 (D-72 · D-147).
    db        읽었다 (0건이어도 「읽었다」)
    no_table  표가 아직 없다 — 마이그레이션 전
    no_db     DB 에 못 붙었다
  뒤의 둘은 **0건이 아니라 「못 읽었다」** 로 그린다 — 화면은 `admin/_db_notice.html` 로 알린다.

✅ 읽기 전용이다 — 이 모듈은 SELECT 만 돌린다.
🔴 원인 문자열을 화면 · 로그에 담지 않는다 — 호스트 · 포트 · 사용자명이 그 안에 있다. WARNING 한 줄, 예외 이름만.
🚨 SQL 은 부르는 쪽의 **고정 조각**만 이어 붙이고 값은 전부 파라미터로 넘긴다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

_log = logging.getLogger("copylane.admin.dbread")

#: 화면 시각 — 사용자 화면(`user.py` `_KST`)과 같은 고정 +9 (tzdata 없이 Windows 에서도 돈다)
KST = timezone(timedelta(hours=9))

#: 쪽 번호 상한 — `OFFSET` 이 커져 「DB 가 죽었다」로 읽히는 것을 막는다 (`admin_errors.py` 와 같은 값)
MAX_PAGE = 100_000


def clean_page(value: str | None) -> int:
    try:
        return min(max(1, int(value or 1)), MAX_PAGE)
    except ValueError:
        return 1


def page_count(total: int, size: int) -> int:
    return max(1, -(-total // size))


def _connect():
    """DB 연결 — `app.db.pg_connect`(연결 대기 상한 한 곳 · D-99). import 를 안에 둔다 — DB 가 없어도 모듈은 선다 (D-51)."""
    from psycopg.rows import dict_row  # noqa: PLC0415

    from app.db import pg_connect  # noqa: PLC0415

    return pg_connect(row_factory=dict_row)


def _is_undefined_table(e: Exception) -> bool:
    try:
        from psycopg import errors as pg_errors  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    return isinstance(e, pg_errors.UndefinedTable)


def run(queries: list[tuple[str, list[Any]]], *, what: str) -> tuple[str, list[list[dict]]]:
    """여러 SELECT 를 한 연결에서 돌린다. `(source, [쿼리마다 행 목록])`.

    못 읽으면 `(no_table | no_db, [])` — 부르는 쪽은 빈 화면 + 안내를 그린다(0건이라 말하지 않는다).
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            out: list[list[dict]] = []
            for sql, params in queries:
                cur.execute(sql, params)
                out.append(cur.fetchall())
            return "db", out
    except Exception as e:  # noqa: BLE001
        if _is_undefined_table(e):
            return "no_table", []
        _log.warning("admin.%s: 조회 실패 — %s", what, type(e).__name__)
        return "no_db", []


def like_param(text: str) -> str:
    """부분 일치용 LIKE 값 — `%` · `_` · `\\` 를 이스케이프한다 (`ESCAPE '\\'` 와 같이 쓴다)."""
    return "%" + text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


def fmt_dt(value: Any, pattern: str = "%Y.%m.%d %H:%M") -> str:
    """시각 · 날짜를 화면 글자로. 없으면 「-」. 시각은 한국 시간으로 바꿔 적는다."""
    if value is None:
        return "-"
    if hasattr(value, "astimezone") and getattr(value, "tzinfo", None) is not None:
        value = value.astimezone(KST)
    return value.strftime(pattern)


def today_kst() -> date:
    return datetime.now(KST).date()
