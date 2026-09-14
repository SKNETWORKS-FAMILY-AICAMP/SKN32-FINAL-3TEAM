"""scripts/schema_drift_check.py — **`db/schema.sql` 과 `alembic head` 가 같은 모양인가**
(2026-09-14 · D-99 · D-221 의 짝).

    uv run python launcher.py db-drift          # 임시 DB 둘을 만들어 대조하고 지운다
    uv run python launcher.py db-drift --keep   # 남겨 두고 들여다본다

🔴 **왜 있나 — 2026-09-14 에 팀원 둘(lse · psj)이 이틀 연속 같은 자리에서 막혔다.**
   `0001` 은 DDL 을 자기 안에 안 적고 **실행 시점에 `db/schema.sql` 을 읽는다.** 그 파일은
   09-09 이후 여덟 번 바뀌었다. 그래서 **「3번 마이그레이션이 도는 DB 의 모양」이 사람마다
   다르다** — 새로 클론한 사람은 오늘자 모양 위에서, 쓰던 사람은 그때 모양 위에서 돈다.
   ⛔ **버전형 체인의 불변식은 「0번이 고정」이다.** 그게 깨지면 나머지는 순서가 있을 뿐이다.

★ **이 검사가 `0001` 동결의 선결이다.** 동결(= 오늘자 `schema.sql` 스냅샷을 박는 것)은
  두 벌이 **지금 같다**는 전제 위에 선다. 다르면 그 차이가 **영구히** 굳는다.
  동결 뒤에는 이 검사가 **게이트**가 된다 — 「`schema.sql` 만 고치고 마이그레이션을 안 썼다」를
  사람이 잊어도 여기서 잡는다.

🚨 **정적 검사로는 못 잡는다.** `tests/test_db_schema.py` 는 텍스트만 본다. 어느 제약이 어느
   타입을 붙잡는지, 뷰 정의가 정규화되면 어떻게 되는지는 **PostgreSQL 만 안다.**

🚨 **진짜 DB 를 건드리지 않는다.** 옆에 임시 DB **둘**을 새로 만들어 거기에만 적용하고 지운다
   (`scripts/db_fresh_check.py` 의 `guard_real_db`·`make_db`·`drop_db`). 이름이 진짜 DB 와
   같으면 아무것도 안 하고 멈춘다 (D-220 fail-closed).

⬜ **여기서 안 보는 것** (D-188) —
   ① **런타임 층.** `app/models.py` 가 만드는 표는 `schema.sql` 에 없다 — **선언에 없는 것은
      차이가 아니다.** 이름만 참고로 낸다.
   ② **데이터.** 빈 표만 만든다.
   ③ **downgrade.**
   ④ **성능.** 인덱스가 있는지는 보지만 쓰이는지는 안 본다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.db_fresh_check import (  # noqa: E402 — 위에서 sys.path 를 세운 뒤라야 든다
    _connect,
    _with_db,
    drop_db,
    guard_real_db,
    make_db,
)

#: 🚨 진짜 DB 이름과 겹칠 수 없는 이름 둘. ⛔ 짧게 줄이지 않는다 — 지우는 대상이다.
DECL = "copylane_driftcheck_decl"  # `db/schema.sql` 만 적용한 자리 — **선언**
HEAD = "copylane_driftcheck_head"  # `alembic upgrade head` 를 건 자리 — **실제**

SCHEMA = ROOT / "db" / "schema.sql"

#: 🚨 **차이를 어디서 보나.** 축마다 `(이름, …)` 행을 낸다 — 첫 칸이 객체 이름이고
#:    나머지가 그 객체의 모양이다. ⛔ 자리번호로 꺼내지 않는다 (`app/retrieve.py` 어법).
FINGERPRINT: dict[str, str] = {
    "열": """
        SELECT c.relname, a.attname,
               format_type(a.atttypid, a.atttypmod),
               a.attnotnull::text,
               coalesce(pg_get_expr(d.adbin, d.adrelid), '')
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE c.relkind IN ('r', 'v', 'm')
        ORDER BY 1, 2
    """,
    # 🔴 순서도 본다 — ENUM 은 값의 **순서**가 비교 연산자의 뜻을 정한다 (D-130 순서형).
    "ENUM 값": """
        SELECT t.typname, e.enumlabel, e.enumsortorder::text
        FROM pg_type t
        JOIN pg_enum e ON e.enumtypid = t.oid
        JOIN pg_namespace n ON n.oid = t.typnamespace AND n.nspname = 'public'
        ORDER BY 1, 3
    """,
    # 🚨 CHECK·FK·UNIQUE 를 한 축으로 본다. `pg_get_constraintdef` 가 정규화해 주므로
    #    「띄어쓰기만 다른 같은 제약」은 차이로 안 뜬다.
    "제약": """
        SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace AND n.nspname = 'public'
        WHERE c.conrelid <> 0
        ORDER BY 1, 2
    """,
    "인덱스": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1, 2
    """,
    # 🔴 뷰는 **정의**를 본다 — 이름만 보면 0009 가 되만든 뷰가 열 하나를 빠뜨려도 초록이다.
    "뷰 정의": """
        SELECT viewname, pg_get_viewdef(('public.' || quote_ident(viewname))::regclass, true)
        FROM pg_views WHERE schemaname = 'public' ORDER BY 1
    """,
}

#: ⬜ 마이그레이션이 자기 자리를 적는 표다 — 선언에 있을 수가 없다. 차이가 아니다.
IGNORE_NAMES = {"alembic_version"}


def apply_schema_sql(url: str, name: str) -> None:
    """`db/schema.sql` 을 그 DB 에 그대로 적용한다.

    🔴 **파라미터 경로로 보내지 않는다** — 스키마 주석에 `%` 가 둘 있고, psycopg 는 그것을
       자리표시자 시작으로 읽는다 (`incomplete placeholder: '%'`).
       ⛔ 같은 판단이 `alembic/versions/0001_governance_layer.py` 의 `_run()` 에도 있다.
          한쪽만 고치면 두 DB 가 **다른 방식으로 세워진다** — 이 검사 자체가 거짓이 된다 (D-99).
    """
    if not SCHEMA.exists():
        raise SystemExit(f"🔴 {SCHEMA} 가 없다 — 거버넌스 층의 선언이다.")
    sql = SCHEMA.read_text(encoding="utf-8")
    with _connect(_with_db(url, name)) as conn, conn.cursor() as cur:
        cur.execute(sql)


def fingerprint(url: str, name: str) -> dict[str, dict[str, set[tuple[str, ...]]]]:
    """축마다 `{객체 이름: {행, …}}` 를 만든다."""
    out: dict[str, dict[str, set[tuple[str, ...]]]] = {}
    with _connect(_with_db(url, name)) as conn, conn.cursor() as cur:
        for axis, sql in FINGERPRINT.items():
            by_obj: dict[str, set[tuple[str, ...]]] = {}
            cur.execute(sql)
            for row in cur.fetchall():
                obj = str(row[0])
                if obj in IGNORE_NAMES:
                    continue
                by_obj.setdefault(obj, set()).add(tuple("" if v is None else str(v) for v in row))
            out[axis] = by_obj
    return out


def compare(decl: dict[str, dict[str, set]], head: dict[str, dict[str, set]]) -> int:
    """선언에 있는 객체만 대조한다. 🚨 **head 에만 있는 것은 차이가 아니다** — 런타임 층이다.

    반환 — 차이가 난 객체 수. 0 이면 두 벌이 같다.
    """
    diffs = 0
    for axis in FINGERPRINT:
        d, h = decl[axis], head[axis]
        for obj in sorted(d):
            if obj not in h:
                diffs += 1
                print(f"\n  🔴 [{axis}] `{obj}` — **선언에는 있고 head 에는 없다**")
                print("     ★ 마이그레이션이 지웠거나, 애초에 안 만들었다.")
                continue
            only_decl, only_head = sorted(d[obj] - h[obj]), sorted(h[obj] - d[obj])
            if not only_decl and not only_head:
                continue
            diffs += 1
            print(f"\n  🔴 [{axis}] `{obj}`")
            for r in only_decl:
                print(f"     선언에만  {r[1:]}")
            for r in only_head:
                print(f"     head 에만 {r[1:]}")

        extra = sorted(set(h) - set(d))
        if extra:
            print(f"\n  ⬜ [{axis}] head 에만 있는 객체 {len(extra)}개 — **차이가 아니다**")
            print(f"     {', '.join(extra)}")
            print("     ★ 런타임 층(`app/models.py`)과 마이그레이션이 새로 만든 것이다.")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description="schema.sql 과 alembic head 의 구조 대조")
    ap.add_argument("--keep", action="store_true", help="임시 DB 둘을 안 지운다")
    args = ap.parse_args()

    from app.settings import sqlalchemy_url  # noqa: PLC0415 — sys.path 를 세운 뒤라야 든다
    from scripts.db_fresh_check import alembic_head  # noqa: PLC0415

    url = sqlalchemy_url()
    real = guard_real_db(url, DECL, HEAD)
    print(f"🚨 임시 DB 둘 `{DECL}`·`{HEAD}` 를 만든다 — 진짜 DB `{real}` 은 안 건드린다.\n")

    try:
        print(f"  ① `{DECL}` ← db/schema.sql 직접 적용")
        make_db(url, DECL)
        apply_schema_sql(url, DECL)

        print(f"  ② `{HEAD}` ← alembic upgrade head")
        make_db(url, HEAD)
        code = alembic_head(url, HEAD)
        if code:
            # 🔴 여기서 죽으면 대조할 것이 없다. **초록을 내지 않는다** (D-72 fail-closed).
            print(
                "\n🔴 **빈 DB 에서 마이그레이션이 안 돈다** — 대조할 수가 없다.\n"
                "   ★ 먼저 `uv run python launcher.py db-fresh` 로 그 자리를 본다 (D-221)."
            )
            return 1

        print("\n  ③ 대조")
        diffs = compare(fingerprint(url, DECL), fingerprint(url, HEAD))
    finally:
        if args.keep:
            print(f"\n⬜ 임시 DB `{DECL}`·`{HEAD}` 를 남겼다 — 다 보고 나면 직접 지운다.")
        else:
            drop_db(url, DECL)
            drop_db(url, HEAD)
            print(f"\n🚨 임시 DB `{DECL}`·`{HEAD}` 를 지웠다.")

    if diffs:
        print(
            f"\n🔴 **두 벌이 갈려 있다 — 객체 {diffs}개.**\n"
            "   ⛔ 이 상태로 `0001` 을 동결하면 **위 차이가 영구히 굳는다.**\n"
            "   ★ 고치는 법 — 차이마다 둘 중 하나다:\n"
            "     ① `schema.sql` 이 맞다 → 그 차이를 **새 마이그레이션**으로 쓴다\n"
            "     ② 마이그레이션이 맞다 → `schema.sql` 을 그 모양으로 맞춘다\n"
            "   🚨 어느 쪽이 맞는지는 **사람이 정한다.** 이 검사는 다르다는 것만 말한다."
        )
        return 1
    print("\n✅ `db/schema.sql` 과 `alembic head` 가 같은 모양이다 — 동결해도 갈리지 않는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
