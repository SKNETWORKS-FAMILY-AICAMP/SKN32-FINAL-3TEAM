"""scripts/admin_account.py — `governor` 계정을 만든다 (D-66 · D-213).

  uv run python -m scripts.admin_account add <이니셜>            # 새로 만든다 — 있으면 멈춘다
  uv run python -m scripts.admin_account add --reset <이니셜>    # 비밀번호만 바꾼다
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


def add(initials: str, *, reset: bool = False) -> int:
    """계정을 **새로** 만든다. 이미 있으면 멈춘다 — 비밀번호를 바꾸는 것은 `--reset` 으로만.

    🆕 2026-09-20 (D-254 · 감사 §2 admin-add) — ⛔ 종전에는 `ON CONFLICT DO UPDATE` 로
       **있는 계정의 비밀번호를 말없이 덮고, 꺼 둔 계정(`disabled_at`)을 되살렸다** — 그리고 ✅.
       오타 난 이니셜 하나로 남의 계정을 가로채거나, 일부러 끈 계정이 다시 켜졌다.
    ★ 기본값이 안전한 쪽이다 — 만들기만 한다. `--reset` 은 비밀번호·표시 이름만 바꾸고
      **꺼진 계정은 꺼진 채로 둔다** (켜는 것은 따로 판단할 일이다).
    """
    if initials not in _known_initials():
        print(f"🔴 `docs/{initials}/` 이 없다 — 명단의 정본은 디스크다 (D-99).")
        print(f"   있는 것: {_known_initials()}")
        return 1

    try:
        import psycopg
    except ImportError:
        print("🔴 psycopg 가 없다 — uv sync")
        return 1

    try:
        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            # 🚨 비밀번호를 묻기 **전에** 본다 — 있는 계정이면 평문을 받을 이유가 없다
            cur.execute("SELECT disabled_at FROM app_account WHERE initials = %s", (initials,))
            row = cur.fetchone()
            exists, disabled = row is not None, bool(row and row[0])
            if exists and not reset:
                print(f"🔴 {initials} 계정이 이미 있다 — 아무것도 바꾸지 않았다.")
                print(
                    "   비밀번호를 바꾸려면: uv run python -m scripts.admin_account add --reset "
                    + initials
                )
                return 1
            if reset and not exists:
                print(
                    f"🔴 {initials} 계정이 없다 — --reset 은 있는 계정만 바꾼다. 만들려면 --reset 없이."
                )
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

            if reset:
                cur.execute(
                    "UPDATE app_account SET pw_hash = %s, display_name = %s WHERE initials = %s",
                    (pw_hash, name, initials),
                )
                changed = cur.rowcount == 1
            else:
                # 🚨 그 사이 누가 만들었으면 덮지 않는다 — DO NOTHING 뒤 행 수로 가른다
                cur.execute(
                    """INSERT INTO app_account (id, initials, display_name, role, pw_hash)
                       VALUES (%s, %s, %s, 'governor', %s)
                       ON CONFLICT (initials) DO NOTHING""",
                    (uuid.uuid4(), initials, name, pw_hash),
                )
                changed = cur.rowcount == 1
    except psycopg.Error as e:
        print(f"🚨 DB 에 못 붙었다 — {type(e).__name__}")
        print("   uv run python launcher.py db-up && uv run python launcher.py migrate")
        return 1
    if not changed:
        print(f"🔴 {initials} — 쓰는 사이 계정 상태가 바뀌었다. 아무것도 바꾸지 않았다. 다시 본다.")
        return 1
    if reset:
        print(f"✅ 비밀번호를 바꿨다 — {initials} ({name}). 🚨 값은 어디에도 안 찍혔다.")
        if disabled:
            print("   ⬜ 이 계정은 **꺼져 있다** — 켜지 않았다.")
    else:
        print(f"✅ 새로 만들었다 — {initials} ({name}) · governor. 🚨 값은 어디에도 안 찍혔다.")
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
    a = sub.add_parser("add", help="계정을 만든다 — 이미 있으면 멈춘다")
    a.add_argument("initials", help="docs/<이니셜>/ 과 같은 철자")
    a.add_argument(
        "--reset", action="store_true", help="있는 계정의 비밀번호만 바꾼다 (꺼진 계정은 안 켠다)"
    )
    sub.add_parser("list", help="누가 있나 — 해시는 안 찍는다")
    args = ap.parse_args()
    return add(args.initials, reset=args.reset) if args.cmd == "add" else show()


if __name__ == "__main__":
    sys.exit(main())
