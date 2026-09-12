"""app/settings.py — 설정을 읽는 **한 곳** (2026-09-12 밤 · D-99 · 병렬작업 계약 §1 #4).

⛔ **무엇이 있었나** — `dsn()` 이 **네 벌**이었다.

    app/api.py:51 · scripts/load_db.py:63 · scripts/embed.py:172 · scripts/search_probe.py:51

  네 곳 모두 `os.environ.get("DATABASE_URL") or "postgresql://…"` 를 그대로 적고 있었다.
  🚨 **그중 하나는 2026-09-12 밤에 새로 복제됐다** — D-99 를 같은 세션에서 세 번 인용하고도
  옆 파일 패턴을 옮겨 적었다. 사람이 지키는 규칙의 실패율이 그것이다 (D-117).

🔴 **그리고 네 곳 다 `.env` 를 안 읽고 있었다.**
   `collect/env.py` 가 *"`.env` 를 실제로 읽는 유일한 곳"* 이고 `DATABASE_URL` 을 `KEYS` 에
   등록해 두었는데, DB 경로는 `load_dotenv` 를 **한 번도 부르지 않는다.**
   ⛔ 그래서 `.env` 에 `DATABASE_URL` 을 적어도 **조용히 기본값으로 떨어졌다** —
   `collect/env.py` 자신이 *"`.env` 가 장식이었다"* 라고 적어 둔 그 사고의 재발이고,
   값이 있는데 없다고 나오는 가장 찾기 어려운 종류다.
   ⬜ **수집 경로까지 안 읽는다는 뜻은 아니다** — 나는 `collect/` 전부를 보지 않았다 (D-188).
      확인한 것은 **`dsn()` 네 곳과 `launcher.py`** 다.

★ **그래서 여기는 읽는 자리를 새로 만들지 않는다.** `.env` 를 읽는 것은 여전히
  `collect/env.py` 하나이고, 이 모듈은 **거기서 읽은 값에 타입과 기본값을 씌우는 자리**다.
  두 벌을 없애려고 만든 모듈이 세 벌째가 되면 안 된다.

🚨 **Pydantic 은 쓰되 `pydantic-settings` 는 아직 안 쓴다.** 그것은 **새 의존성**이고
   `uv.lock` 이 바뀐다 — lock 은 팀장 단독이고 충돌이 팀 전체로 번진다(D-87 · `pyproject.toml`
   주석). 지금 필요한 것(한 곳 · 타입 · 검증)은 `BaseModel` 로 전부 된다.
   ⬜ `pydantic-settings` 로 올리는 것은 **lock 을 만지는 커밋과 같은 판**에서 한다.
"""

from __future__ import annotations

import functools
import os

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: 🚨 `docker-compose.yml` 의 기본 사용자·비밀번호와 같아야 한다. 값이 갈리면
#:    「내 기기에서는 붙는데」가 난다. 이 문자열이 **저장소에서 유일**해야 하는 이유다.
#: ⛔ 진짜 비밀번호를 여기 적지 않는다 — 로컬 개발 기본값이고 `127.0.0.1` 에만 열려 있다.
DEFAULT_DATABASE_URL = "postgresql://copylane:copylane@localhost:5432/copylane"


class Settings(BaseModel):
    """읽은 설정 한 벌. 🚨 **얼려 둔다** — 돌던 중에 바뀌면 어느 값으로 돌았는지 못 말한다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_url: str = Field(min_length=1)

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres(cls, v: str) -> str:
        """🔴 **PostgreSQL 이다. MySQL 이 아니다** (D-95).

        ⛔ 팀 5인의 이전 프로젝트가 MySQL 기반이라 `mysql://` 를 적을 수 있다. 그러면
           psycopg 가 훨씬 뒤에서 알아보기 어려운 오류로 죽는다 — **여기서 이름을 대고 막는다**
           (D-51 — 오류는 고치는 법을 보여준다).
        """
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError(
                f"DATABASE_URL 이 postgres 가 아니다 — {v.split('://')[0]}://…\n"
                "  🚨 저장 계층은 PostgreSQL + pgvector 다 (D-95 · D-41). MySQL 은 벡터를 "
                "별도 인프라로 빼야 하고 삭제가 2단계가 된다.\n"
                "  고치는 법 — .env 의 DATABASE_URL 을 postgresql://… 로. 기본값은 "
                "docker-compose.yml 그대로 쓰면 된다"
            )
        return v


@functools.cache
def settings() -> Settings:
    """설정 한 벌. 🚨 **프로세스당 한 번만 읽는다** — 중간에 바뀌지 않는다.

    ⛔ `.env` 를 읽는 것은 `collect/env.py` 다. 여기서 `load_dotenv` 를 부르지 않는다 (D-99).
    🚨 **지연 import 다.** `collect.env` 는 `collect.http`(수집기의 HTTP 층)를 끌고 온다 —
       모듈 최상단에서 부르면 **판정 API 프로세스가 수집 계층을 통째로 import** 한다.
       계층을 섞지 않으려고 부르는 순간에만 들인다. `app/api.py` 가 `psycopg` 를,
       `app/graph.py` 가 `langgraph` 를 지연 import 하는 것과 같은 이유다.
    """
    from collect import env as _env  # noqa: PLC0415 — 위 주석 참조

    _env.load()
    return Settings(database_url=os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL)


def dsn() -> str:
    """postgres 접속 문자열. 🚨 **저장소에서 이 함수는 하나뿐이라야 한다.**

    게이트 `test_dsn_정의가_저장소에_하나뿐이다` 가 그것을 본다 — 규칙이 아니라 검사로 (D-117).
    """
    return settings().database_url
