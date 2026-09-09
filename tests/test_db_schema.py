"""거버넌스 층 스키마 — `db/schema.sql` 이 원본이다 (2026-09-09).

🚨 **거버넌스 게이트다.** 층이 둘이라 어긋나는 자리가 셋 있다.

    설계 문서 부록   docs/02_설계/거버넌스데이터층_DDL.md
    원본            db/schema.sql                       ← 이것이 실제로 도는 것
    마이그레이션      alembic/versions/0001_*.py          ← 파일을 읽어 실행만 한다

무엇을 지키나
  ① 문서 부록과 `db/schema.sql` 이 **한 글자도 다르지 않다**
  ② 마이그레이션이 DDL 을 **복사하지 않았다** (D-99)
  ③ `env.py` 의 `include_object` 가 거버넌스 객체를 **전부** 덮는다
     — 하나라도 빠지면 `--autogenerate` 가 그 테이블에 DROP 을 생성한다
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
DOC = ROOT / "docs" / "02_설계" / "거버넌스데이터층_DDL.md"
ENV = ROOT / "alembic" / "env.py"
MIGRATION = ROOT / "alembic" / "versions" / "0001_governance_layer.py"


def _objects(sql: str) -> set[str]:
    return set(re.findall(r"^CREATE (?:TABLE|VIEW)\s+(\w+)", sql, re.M))


@pytest.mark.gate
def test_문서_부록과_schema_sql_이_같다() -> None:
    """🚨 **원본은 파일이고 문서는 사본이다** — 문서가 스스로 그렇게 적었다.

    ⛔ 둘이 갈리면 사람은 문서를 읽고 DB 는 파일대로 돈다. 그 어긋남은 조용하다 —
       설계 검토에서는 맞는데 실제 스키마가 다르다.
    """
    assert SCHEMA.exists(), f"🚨 {SCHEMA} 가 없다 — 거버넌스 층의 원본이다"
    m = re.search(r"```sql\n(.*?)```", DOC.read_text(encoding="utf-8").split("## 부록")[1], re.S)
    assert m, "🚨 설계 문서 부록에서 sql 블록을 못 찾았다"
    assert m.group(1) == SCHEMA.read_text(encoding="utf-8"), (
        "🚨 설계 문서 부록과 `db/schema.sql` 이 다르다.\n"
        "   **파일이 원본이다** — 문서 쪽을 파일로 맞춘다."
    )


@pytest.mark.gate
def test_마이그레이션이_DDL_을_복사하지_않는다() -> None:
    """🔴 같은 판정을 두 곳에 두지 않는다 (D-99).

    마이그레이션이 DDL 을 품으면 세 곳이 된다 — 문서·파일·마이그레이션.
    그러면 한 곳만 고쳐지고, **고쳐지지 않은 쪽이 실제로 도는 쪽**일 수 있다.
    """
    assert MIGRATION.exists(), "🚨 첫 마이그레이션이 없다"
    src = MIGRATION.read_text(encoding="utf-8")
    # 🚨 **낱말이 아니라 문장 모양**을 본다. `CREATE TABLE` 이라는 글자는 downgrade 의
    #    정규식 문자열에도 들어 있다 — 낱말만 세면 그것까지 DDL 로 잡는다.
    #    ⛔ 처음에 그렇게 썼다가 이 게이트가 자기 자신을 오탐했다.
    #    실제 DDL 은 `CREATE TABLE <이름> (` 처럼 **진짜 공백과 여는 괄호**가 온다.
    ddl = re.findall(r"CREATE\s+(?:TABLE|TYPE|VIEW)\s+\w+\s*\(", src)
    assert not ddl, (
        f"🚨 마이그레이션 안에 DDL 이 있다 ({ddl[:2]}) — `db/schema.sql` 을 읽어 실행만 한다 (D-99)"
    )
    assert "schema.sql" in src, "🚨 마이그레이션이 db/schema.sql 을 참조하지 않는다"


@pytest.mark.gate
def test_autogenerate_가_거버넌스_테이블을_지우지_못한다() -> None:
    """🔴 **이걸 안 막으면 `migrate-new` 가 DROP 을 생성한다.**

    `target_metadata` 는 런타임 층(`app/models.py`)뿐이다. alembic 은 DB 에 있는데
    메타데이터에 없는 테이블을 「지워야 할 것」으로 본다 — 거버넌스 18테이블이 전부 그렇다.
    ⛔ 생성된 초안을 눈으로 보면 잡히지만, **안 보면 스키마가 통째로 날아간다.**
    ★ `include_object` 가 그것을 구조로 막는다. 목록은 `db/schema.sql` 에서 읽는다.
    """
    env = ENV.read_text(encoding="utf-8")
    assert "def include_object(" in env, "🚨 env.py 에 include_object 가 없다"
    assert env.count("include_object=include_object") == 2, (
        "🚨 include_object 가 offline·online 두 경로에 다 걸려 있어야 한다 — "
        f"지금 {env.count('include_object=include_object')}곳"
    )
    assert 'ROOT / "db" / "schema.sql"' in env, (
        "🚨 include_object 의 목록을 손으로 적지 않는다 — db/schema.sql 에서 읽는다 (D-99)"
    )
    # 파일에서 뽑은 목록이 실제로 18테이블 + 3뷰를 덮는가
    objs = _objects(SCHEMA.read_text(encoding="utf-8"))
    assert len(objs) >= 21, f"🚨 거버넌스 객체가 {len(objs)}개뿐이다 — 18테이블 + 3뷰여야 한다"


@pytest.mark.gate
def test_벡터_차원이_한_곳에만_있다() -> None:
    """🚨 `vector(N)` 은 **1W 미확정 항목**이다 (DDL §8-1 · KURE-v1 실제 차원 미확인).

    확정되면 마이그레이션으로 갈아 끼워야 하는데, 두 곳에 적혀 있으면 한 곳만 고친다.
    ⛔ **차원 불일치는 적재 시점에 터진다** — DDL §9-4 가 그렇게 경고했다.
    """
    dims = set(re.findall(r"vector\((\d+)\)", SCHEMA.read_text(encoding="utf-8")))
    assert len(dims) == 1, f"🚨 벡터 차원이 여러 개다 — {sorted(dims)}"


@pytest.mark.gate
def test_alembic_ini_는_ascii_만_담는다() -> None:
    """🔴 **alembic 은 자기 설정 파일을 `encoding="locale"` 로 읽는다.**

    한국어 Windows 에서 그건 cp949 다. UTF-8 바이트가 하나라도 있으면
    `alembic upgrade` 가 **DB 를 보기도 전에** `UnicodeDecodeError` 로 죽는다 —

        UnicodeDecodeError: 'cp949' codec can't decode byte 0xe2 in position 14

    ⛔ 2026-09-05 부터 잠복해 있었다. `alembic/versions/` 가 비어 있어 아무도
       `upgrade` 를 돌린 적이 없었기 때문에 **안 터졌을 뿐**이다. 첫 마이그레이션을
       넣는 순간 터졌다. 🚨 **기기마다 답이 다르면 doctor** (D-89) — 이건 그보다 나쁘다.
       리눅스에서는 UTF-8 locale 이라 영영 안 터진다.

    ★ 설명은 `alembic/env.py` 에 둔다 — **파이썬 소스는 언제나 UTF-8 로 읽힌다.**
    """
    ini = ROOT / "alembic.ini"
    raw = ini.read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not bad, (
        f"🚨 `alembic.ini` 에 비ASCII 바이트가 {len(bad)}개 있다 "
        f"(첫 위치 {bad[0][0]}, 0x{bad[0][1]:02x}).\n"
        "   한국어 Windows 에서 alembic 이 이 파일을 못 읽는다.\n"
        "   한글 설명은 `alembic/env.py` 의 docstring 으로 옮긴다."
    )
    # 양성 대조 — 실제로 cp949 로 읽히는가
    ini.read_text(encoding="cp949")
