"""설정 경계 — **읽는 자리가 하나인가** (2026-09-12 밤 · D-99 · 병렬작업 계약 §1 #4).

⛔ `dsn()` 이 네 벌이었고, 네 곳 다 `.env` 를 안 읽었다. 규칙으로 막히지 않아서
   (같은 세션에서 D-99 를 세 번 인용하고도 한 벌을 더 만들었다) **검사로 옮긴다** (D-117).

🚨 이 파일은 **정적 검사**다 — 실제 DB 에 붙는지는 보지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import settings as st

ROOT = Path(__file__).resolve().parent.parent

#: 훑지 않는 곳 — 가상환경·생성물·캐시·데이터. `.gitignore` 와 같은 뜻이다 (집행계약 §6).
_SKIP = {".venv", "build", "dist", "data", "models", "mlruns", "__pycache__", ".ruff_cache"}


def _sources() -> list[Path]:
    """저장소의 우리 파이썬 파일. 🚨 목록을 손으로 적지 않는다 — 새 파일이 새면 안 된다.

    ⛔ **자기 자신은 뺀다.** 이 파일은 찾는 문자열을 **검사 대상으로** 들고 있어서, 안 빼면
       게이트가 자기를 오탐한다 — `test_마이그레이션이_DDL_을_복사하지_않는다` 가 처음에
       똑같이 겪었다. 🚨 파일 이름 하나만 빼고, 다른 예외는 두지 않는다.
    """
    me = Path(__file__).resolve()
    return [
        p
        for p in ROOT.rglob("*.py")
        if not (_SKIP & set(p.relative_to(ROOT).parts)) and p.resolve() != me
    ]


@pytest.mark.gate
def test_dsn_정의가_저장소에_하나뿐이다() -> None:
    """🔴 **`def dsn(` 은 `app/settings.py` 하나다.**

    ⛔ 네 벌이던 것을 한 벌로 모았다. 다음 사람이 옆 파일 패턴을 복사하면 여기서 걸린다 —
       그것이 실제로 일어난 일이다 (`scripts/search_probe.py`, 2026-09-12 밤).
    """
    where = [
        f"{p.relative_to(ROOT)}"
        for p in _sources()
        if re.search(r"^def dsn\(", p.read_text(encoding="utf-8"), re.M)
    ]
    assert where == ["app/settings.py"], (
        f"🔴 `def dsn(` 이 여기 있다: {where}\n"
        "   설정은 `app/settings.py` 하나가 든다 — `from app.settings import dsn` (D-99)"
    )


@pytest.mark.gate
def test_기본_DSN_문자열이_저장소에_하나뿐이다() -> None:
    """⛔ 함수를 합쳐도 **기본값 문자열**이 흩어져 있으면 갈린다.

    🚨 `docker-compose.yml` 은 사용자·비밀번호를 **환경변수 치환**으로 들고 있어 이 문자열을
       그대로 적지 않는다 — 그래서 이 검사의 대상은 파이썬 소스뿐이다.
    """
    needle = "postgresql://copylane:copylane@localhost:5432/copylane"
    where = [
        f"{p.relative_to(ROOT)}" for p in _sources() if needle in p.read_text(encoding="utf-8")
    ]
    assert where == ["app/settings.py"], f"🔴 기본 DSN 이 여기도 있다: {where}"


@pytest.mark.gate
def test_env_를_읽는_자리가_하나다() -> None:
    """🚨 `.env` 를 읽는 것은 `collect/env.py` 하나다 — 그 파일이 스스로 그렇게 적었다.

    ⛔ 두 곳이 되면 「어느 인코딩으로 읽었나」·「override 를 걸었나」가 갈린다.
       2026-09-02 에 UTF-8 BOM 으로 한 번 겪었다.
    """
    where = [
        f"{p.relative_to(ROOT)}"
        for p in _sources()
        if "load_dotenv(" in p.read_text(encoding="utf-8")
    ]
    assert where == ["collect/env.py"], f"🔴 `.env` 를 읽는 자리가 여럿이다: {where}"


@pytest.mark.gate
def test_설정은_얼려_있다() -> None:
    """⛔ 돌던 중에 바뀌면 **어느 값으로 돌았는지 못 말한다** (D-176 — 재현의 근거)."""
    s = st.Settings(database_url=st.DEFAULT_DATABASE_URL)
    with pytest.raises(ValidationError):
        s.database_url = "postgresql://other/db"


@pytest.mark.gate
def test_postgres_가_아니면_이름을_대고_막는다() -> None:
    """🔴 D-95 — 저장 계층은 PostgreSQL 이다. MySQL 은 벡터를 별도 인프라로 뺀다.

    🚨 **막는 것만으로는 부족하다** — 오류가 고치는 법을 말해야 한다 (D-51).
    """
    with pytest.raises(ValidationError) as e:
        st.Settings(database_url="mysql://copylane@localhost/copylane")
    msg = str(e.value)
    assert "D-95" in msg
    assert "postgresql://" in msg


def test_기본값이면_기본_DSN_이_나온다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 게이트가 아니다 — `.env` 가 있는 기기에서는 값이 다를 수 있다 (D-19)."""
    st.settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # `.env` 를 안 읽고 **순수 기본값**만 본다 — 지연 import 라 모듈에서 가로챈다
    import collect.env as ce  # noqa: PLC0415

    monkeypatch.setattr(ce, "load", lambda: None)
    try:
        assert st.dsn() == st.DEFAULT_DATABASE_URL
    finally:
        st.settings.cache_clear()
