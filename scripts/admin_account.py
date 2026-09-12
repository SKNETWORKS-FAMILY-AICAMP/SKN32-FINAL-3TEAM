"""scripts/admin_account.py — `governor` 계정을 만든다 (D-66 · D-213).

  uv run python -m scripts.admin_account add <이니셜>
  uv run python -m scripts.admin_account list

🚨 **가입 화면은 없다** (D-66 — 온프레미스는 계정 주입). 만드는 길이 여기 하나뿐이다.

⛔ **비밀번호를 인자로 받지 않는다.** `getpass` 로만 받는다 — `collect/setkey.py` 와 같은 모양이고
   같은 이유다: PowerShell 기록 파일에 값이 그대로 남는다 (D-111).
🔴 **명단의 정본은 디스크다** — `docs/<이니셜>/` 이 있어야 만들어진다 (D-99 · `experiment.py` 와
   같은 방식). 이니셜 목록을 코드에 적으면 원장 「팀」 표와 두 벌이 된다.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import uuid
from pathlib import Path

from app.auth import hash_password
from app.settings import dsn

ROOT = Path(__file__).resolve().parents[1]

#: 🚨 짧은 비밀번호를 막는다. 고시는 길이를 숫자로 못박지 않지만, **Argon2id 도 짧은 것은 못 지킨다.**
MIN_PASSWORD = 12


def _known_initials() -> list[str]:
    """`docs/<이니셜>/` 이 있는 것만. **디스크가 명단이다** (D-99)."""
    docs = ROOT / "docs"
    skip = {"01_기획", "02_설계", "03_데이터", "04_보안", "05_배포"}
    return sorted(p.name for p in docs.iterdir() if p.is_dir() and p.name not in skip)


def add(initials: str) -> int:
    if initials not in _known_initials():
        print(f"🔴 `docs/{initials}/` 이 없다 — 명단의 정본은 디스크다 (D-99).")
        print(f"   있는 것: {_known_initials()}")
        return 1

    pw = getpass.getpass("비밀번호 (화면에 안 뜬다): ")
    if len(pw) < MIN_PASSWORD:
        print(f"🔴 {MIN_PASSWORD}자 이상. Argon2id 도 짧은 것은 못 지킨다.")
        return 1
    if pw != getpass.getpass("한 번 더: "):
        print("🔴 두 번이 다르다.")
        return 1

    name = input("표시 이름 (엔터 = 이니셜): ").strip() or initials
    pw_hash = hash_password(pw)
    del pw  # 🚨 평문을 오래 들고 있지 않는다

    try:
        import psycopg
    except ImportError:
        print("🔴 psycopg 가 없다 — uv sync")
        return 1
    try:
        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app_account (id, initials, display_name, role, pw_hash)
                   VALUES (%s, %s, %s, 'governor', %s)
                   ON CONFLICT (initials) DO UPDATE SET pw_hash = EXCLUDED.pw_hash,
                                                        display_name = EXCLUDED.display_name,
                                                        disabled_at = NULL""",
                (uuid.uuid4(), initials, name, pw_hash),
            )
    except psycopg.Error as e:
        print(f"🚨 DB 에 못 붙었다 — {type(e).__name__}")
        print("   uv run python launcher.py db-up && uv run python launcher.py migrate")
        return 1
    print(f"✅ {initials} ({name}) — governor. 🚨 값은 어디에도 안 찍혔다.")
    return 0


def show() -> int:
    """누가 있나. ⛔ **해시는 안 찍는다** — 지문도 안 찍는다 (해시가 곧 지문이다)."""
    try:
        import psycopg

        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT initials, display_name, last_login_at, disabled_at "
                "FROM app_account ORDER BY initials"
            )
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"🚨 DB 에 못 붙었다 — {type(e).__name__}")
        return 1
    if not rows:
        print("⬜ 계정이 없다 — uv run python launcher.py admin-add <이니셜>")
        print("   🚨 가입 화면은 없다 (D-66 — 온프레미스는 계정 주입).")
        return 0
    print(f"{'이니셜':<10}{'이름':<14}{'마지막 로그인':<22}상태")
    for ini, name, last, off in rows:
        print(f"{ini:<10}{name:<14}{str(last or '—'):<22}{'꺼짐' if off else '켜짐'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="governor 계정 (D-66 · D-213)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="계정을 만들거나 비밀번호를 바꾼다")
    a.add_argument("initials", help="docs/<이니셜>/ 과 같은 철자")
    sub.add_parser("list", help="누가 있나 — 해시는 안 찍는다")
    args = ap.parse_args()
    return add(args.initials) if args.cmd == "add" else show()


if __name__ == "__main__":
    sys.exit(main())
