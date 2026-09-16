"""scripts/db_fresh_check.py — **빈 DB 에서 `alembic upgrade head` 가 도는가** (2026-09-13 · D-221).

  uv run python launcher.py db-fresh          # 임시 DB 를 만들어 돌리고 지운다
  uv run python launcher.py db-fresh --keep   # 남겨 두고 들여다본다

🔴 **왜 있나 — 2026-09-13 에 팀원(lse)이 새 기기에서 막혔다.**

    psycopg.errors.DependentObjectsStillExist: cannot drop type violation_t
    DETAIL:  column violation of table violation_article depends on type violation_t

  ⛔ **다섯 명 중 아무도 빈 DB 에서 처음부터 돌린 적이 없었다.** 다들 쓰던 DB 에
     새 마이그레이션만 이어 붙였다. 그래서 **가장 흔한 첫 경험**(클론 → db-up → migrate)이
     아무 게이트에도 안 걸려 있었다 — D-146 이 말한 *「실행하지 않은 코드」* 다.

★ **정적 검사로는 못 잡는다.** `tests/test_db_schema.py` 는 텍스트만 본다 — 어느 표가 어느
  타입을 붙잡는지는 **PostgreSQL 만 안다.** 그래서 이 검사는 pytest 가 아니라 여기 있다
  (DB 가 있어야 돌고, 기기마다 답이 다르다 — D-89 가 doctor 를 가른 것과 같은 기준).

🚨 **진짜 DB 를 건드리지 않는다.** 옆에 **임시 DB 를 새로 만들어** 거기에만 적용하고 지운다.
   ⛔ 이름이 진짜 DB 와 같으면 **아무것도 안 하고 멈춘다** — 지우는 명령에 오타가 나면
      되돌릴 수 없다 (D-220 fail-closed).

🔄 **2026-09-14 — 임시 DB 를 세우는 넷(`guard_real_db`·`make_db`·`drop_db`·`alembic_head`)을
   이 파일에 **공용으로** 뺐다. `scripts/schema_drift_check.py` 가 그대로 쓴다 (D-99).
   ⛔ 저쪽에 복사해 두지 않는다 — 지우는 명령이 두 벌이 되는 것이 가장 위험하다.

⬜ **여기서 안 보는 것** (D-188) —
   ① **downgrade.** 되돌리기는 안 돌려 본다.
   ② **데이터.** 빈 표만 만든다 — 적재는 `load` 가 본다.
   ③ **런타임 층의 내용.** 표가 서는 것만 본다.
   ④ 🆕 **`db/schema.sql` 과 `alembic head` 가 같은 모양인가.** 여기는 *돌았는가*만 본다 —
      **같은가**는 `uv run python launcher.py db-drift` 가 본다 (`schema_drift_check.py`).
"""

from __future__ import annotations

import argparse
import os
import subprocess  # noqa: S404 — alembic 을 자식 프로세스로 돌린다 (아래 주석)
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]

#: 🚨 진짜 DB 이름과 겹칠 수 없는 이름. ⛔ 짧게 줄이지 않는다 — 지우는 대상이다.
SCRATCH = "copylane_freshcheck"


def _dbname(url: str) -> str:
    name = urlsplit(url).path.lstrip("/")
    if not name:
        raise SystemExit("🔴 DATABASE_URL 에 DB 이름이 없다 — …://…/<여기>")
    return name


def _with_db(url: str, name: str) -> str:
    """DB 이름만 갈아 끼운다.

    ⛔ **문자열을 이어 붙이지 않는다.** 소켓 접속은 `?host=/tmp&port=5432` 처럼 질의가
       붙고, 이름을 뒤에 붙이면 **질의 끝에 달라붙는다.** 처음에 그렇게 썼다가 잡았다.
    """
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc, "/" + name, u.query, u.fragment))


def _connect(url: str):
    """🚨 psycopg 는 `postgresql+psycopg://` 를 모른다 — SQLAlchemy 접미사를 뗀다."""
    import psycopg  # noqa: PLC0415

    return psycopg.connect(url.replace("+psycopg", "", 1), autocommit=True)


def _admin_conn(url: str):
    """`postgres` 관리 DB 에 붙는다 — 자기 자신을 만들거나 지울 수는 없다."""
    return _connect(_with_db(url, "postgres"))


# ══════════════════════════════════════════════════════════════════════
#  임시 DB 를 만들고·지우고·마이그레이션을 거는 넷
#  🚨 **여기 하나만 둔다** — `scripts/schema_drift_check.py` 가 그대로 쓴다 (D-99).
#     ⛔ 복사해 가지 않는다. 고칠 일이 생기면 이 자리를 고친다.
# ══════════════════════════════════════════════════════════════════════
def guard_real_db(url: str, *names: str) -> str:
    """🔴 fail-closed — 진짜 DB 를 지울 수 있는 상황이면 **아무것도 안 한다** (D-220).

    ⛔ 임시 DB 이름 중 **하나라도** 진짜 DB 와 같으면 멈춘다. 이름을 늘릴 때마다
       이 자리를 지나게 한다 — 지우는 명령에 오타가 나면 되돌릴 수 없다.
    """
    real = _dbname(url)
    for n in names:
        if real == n:
            raise SystemExit(
                f"🔴 진짜 DB 이름이 `{n}` 다 — 이 검사가 그것을 지우게 된다.\n"
                "   .env 의 DATABASE_URL 을 다른 이름으로 바꾼다."
            )
    return real


def make_db(url: str, name: str) -> None:
    """임시 DB 를 **새로** 만든다 — 있으면 지우고 다시. `vector` 확장까지 건다."""
    with _admin_conn(url) as conn, conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{name}"')
    with _connect(_with_db(url, name)) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")


def drop_db(url: str, name: str) -> None:
    with _admin_conn(url) as conn, conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def alembic_head(url: str, name: str) -> int:
    """`alembic upgrade head` 를 그 DB 에만 건다. 종료코드를 그대로 낸다.

    🚨 **자식 프로세스로** 돌린다 — alembic 을 이 프로세스에 import 하면 `env.py` 가
       읽는 DATABASE_URL 을 되돌릴 수 없고, 그다음에 도는 것이 **진짜 DB 를 볼 수 있다.**
    """
    env = {**os.environ, "DATABASE_URL": _with_db(url, name)}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=False
    ).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="빈 DB 에서 alembic upgrade head (D-221)")
    ap.add_argument("--keep", action="store_true", help="임시 DB 를 안 지운다")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from app.settings import sqlalchemy_url  # noqa: PLC0415

    url = sqlalchemy_url()
    real = guard_real_db(url, SCRATCH)

    print(f"🚨 임시 DB `{SCRATCH}` 를 만든다 — 진짜 DB `{real}` 은 건드리지 않는다.")
    make_db(url, SCRATCH)
    code = alembic_head(url, SCRATCH)

    if not args.keep:
        drop_db(url, SCRATCH)
        print(f"🚨 임시 DB `{SCRATCH}` 를 지웠다.")
    else:
        print(f"⬜ 임시 DB `{SCRATCH}` 를 남겼다 — 다 보고 나면 직접 지운다.")

    if code:
        print(
            "\n🔴 **빈 DB 에서 마이그레이션이 안 돈다.**\n"
            "   ⛔ 지금 쓰는 DB 에서는 돌 수 있다 — 새로 클론한 사람만 밟는다.\n"
            "   ★ 위 오류의 마지막 마이그레이션을 연다. 대개 **새 DB 에는 이미 있는 것**을\n"
            "     또 만들거나 지우려는 자리다 (0001 이 읽는 `db/schema.sql` 이 정본이므로\n"
            "     새 DB 는 **끝난 모양에서 시작한다** — D-221)."
        )
        return 1
    print("\n✅ 빈 DB → `alembic upgrade head` 가 끝까지 돌았다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
