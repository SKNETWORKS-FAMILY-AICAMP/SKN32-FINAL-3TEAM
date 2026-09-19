"""거버넌스 층 스키마 — `db/schema.sql` 이 원본이다 (2026-09-09).

🚨 **거버넌스 게이트다.** 층이 둘이라 어긋나는 자리가 셋 있다.

    설계 문서 부록   docs/02_설계/거버넌스데이터층_DDL.md
    현재 선언        db/schema.sql                       ← 사람이 읽는 정본
    🧊 동결본        db/schema_0001.sql                  ← 0번 마이그레이션의 입력
    마이그레이션      alembic/versions/0001_*.py          ← 동결본을 읽어 실행만 한다

무엇을 지키나
  ① 문서 부록과 `db/schema.sql` 이 **한 글자도 다르지 않다**
  ② 마이그레이션이 DDL 을 **복사하지 않았다** (D-99)
  ③ `env.py` 의 `include_object` 가 거버넌스 객체를 **전부** 덮는다
     — 하나라도 빠지면 `--autogenerate` 가 그 테이블에 DROP 을 생성한다
  ④ 🆕 **0번이 읽는 파일이 동결본이고, 그 동결본이 안 바뀌었다** (2026-09-14 · D-221)

🚨 **여기서 안 보는 것** — 「선언과 실제가 같은가」는 정적으로 못 본다. 뷰 정의가 정규화되면
   어떻게 되는지, 어느 제약이 어느 타입을 붙잡는지는 PostgreSQL 만 안다.
   그것은 `uv run python launcher.py db-drift` 가 임시 DB 둘을 떠서 본다.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
from pathlib import Path

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
#: 🧊 0번 마이그레이션의 **동결된 입력** (2026-09-14).
FROZEN = ROOT / "db" / "schema_0001.sql"
#: 🔴 동결본의 sha256 — **줄 끝 공백과 파일 끝 줄바꿈을 고른 뒤**의 값이다 (`_pin()`).
#:    ⛔ 이 수를 「게이트가 빨개졌으니」 갱신하지 않는다. 빨개졌다는 것은
#:       **동결이 깨졌다**는 뜻이다. 파일을 되살린다: git checkout -- db/schema_0001.sql
FROZEN_PIN = "63f32c85018cda6d2ccdc9088e4c1bf9e5f68ddbd0862be88af04a78ad1fe50a"
DOC = ROOT / "docs" / "02_설계" / "거버넌스데이터층_DDL.md"
ENV = ROOT / "alembic" / "env.py"
MIGRATION = ROOT / "alembic" / "versions" / "0001_governance_layer.py"


def _pin(text: str) -> str:
    """핀용 해시 — 줄 끝 공백과 파일 끝 줄바꿈을 고른 뒤 센다.

    🚨 **왜 정규화하나.** `.pre-commit-config.yaml` 의 `trim trailing whitespace`·
       `fix end of files` 와 git 의 줄끝 변환이 파일을 만질 수 있다. 그 셋 때문에 핀이
       어긋나면 「동결이 깨졌다」로 **거짓 경보**가 나고, 거짓 경보는 곧 안 읽힌다 (D-167).
    ⛔ 그 밖의 변경은 전부 잡는다 — 한 글자만 달라도 어긋난다.
    """
    body = "\n".join(line.rstrip() for line in text.splitlines())
    return hashlib.sha256((body + "\n").encode("utf-8")).hexdigest()


def _objects(sql: str) -> set[str]:
    return set(re.findall(r"^CREATE (?:TABLE|VIEW)\s+(\w+)", sql, re.M))


#: 🔴 2026-09-12 — `SELECT c.*` 는 뷰를 만들 때 **열 목록으로 전개돼 고정된다.**
#:    0008 이 `chunk` 에 열 둘을 더했는데 `v_current_chunk` 를 안 고쳐 검색이 503 이 났다.
#:    게이트 193 은 못 잡았다 — 정적 검사는 질의 문자열만 보고, 재임베딩은 뷰를 안 지난다.
MIGRATIONS = ROOT / "db" / "migrations"
_ADD_CHUNK_COL = re.compile(r"ALTER\s+TABLE\s+chunk\s+ADD\s+COLUMN", re.I)
_REFRESH_VIEW = re.compile(r"(?:CREATE(?:\s+OR\s+REPLACE)?|DROP)\s+VIEW[^;]*v_current_chunk", re.I)


@pytest.mark.gate
def test_chunk_에_열을_더하면_뷰도_다시_만든다() -> None:
    """⛔ **뷰가 낡으면 검색이 통째로 죽는다.** 그리고 그것은 실제 질의에서만 드러난다.

    🚨 `db/schema.sql` 로 만드는 **새 DB 는 멀쩡하다** — 갈리는 것은 이미 돌던 DB 뿐이라
       개발 기기와 배포 기기가 다르게 돈다. 0007 이 경고한 바로 그 모양이다.
    ★ 사람이 기억할 일로 두지 않고 **순서로 검사한다** — 열을 더한 마이그레이션보다
      뒤에(또는 **같은 파일의 더 아래에서**) 뷰를 다시 만들어야 한다.

    🔄 2026-09-12 오후 — 종전에는 `refreshed[-1] > added[-1]`, 즉 **다른 파일**이라야 통과했다.
       ⛔ 그러면 0010 처럼 **열 추가와 뷰 재생성을 한 파일에 담은 것**이 떨어진다.
          그런데 한 파일에 담는 쪽이 낫다 — 한 트랜잭션이라 반만 적용될 수가 없다.
       🚨 게이트가 **더 나은 방법을 막고 있었다.** 규칙을 「뒤 파일」이 아니라
          「뒤 순서」로 고친다 — 같은 파일이면 본문 안의 위치로 본다.
    """
    bad = view_refresh_violation(MIGRATIONS)
    if bad == _NO_ADD:
        pytest.skip("chunk 에 열을 더한 마이그레이션이 아직 없다")
    assert bad is None, bad


#: 「검사할 대상이 없다」와 「통과했다」를 가른다 — 둘을 같은 `None` 으로 내면
#: 마이그레이션 폴더가 통째로 비어도 초록이 된다 (D-170).
_NO_ADD = "no-add"


def view_refresh_violation(migrations: Path) -> str | None:
    """열을 더한 마지막 마이그레이션이 뷰를 다시 만들었는가. 어겼으면 **사유 문장**을 낸다.

    🔴 2026-09-12 밤 — 검사 본문을 함수로 뺐다 (D-203). ⛔ 종전에는 테스트 안에 있어서
       **「이 게이트가 0008 형을 실제로 잡는가」를 잴 방법이 없었다.** D-197 이
       *"게이트를 고치려면 종전 규칙이 잡던 것을 새 규칙도 잡는다는 것을 보여야 한다"* 고
       요구했는데, 09-12 오후에는 **논증으로만** 보였다.
    ★ 함수로 빼면 **일부러 어긴 입력**을 넣어 볼 수 있다 — 아래 음성 픽스처가 그것이다.
    """
    files = sorted(p.name for p in migrations.glob("*.sql"))
    added = [
        n for n in files if _ADD_CHUNK_COL.search((migrations / n).read_text(encoding="utf-8"))
    ]
    if not added:
        return _NO_ADD
    last = added[-1]
    src = (migrations / last).read_text(encoding="utf-8")
    add_at = _ADD_CHUNK_COL.search(src)
    refresh_at = _REFRESH_VIEW.search(src)
    # ① 같은 파일 안에서 ADD 뒤에 뷰 재생성이 오면 통과 — 한 트랜잭션이라 가장 안전하다
    if refresh_at and add_at and refresh_at.start() > add_at.start():
        return None
    # ② 아니면 **더 뒤 파일**에서 다시 만들었어야 한다
    later = [
        n
        for n in files
        if n > last and _REFRESH_VIEW.search((migrations / n).read_text(encoding="utf-8"))
    ]
    if later:
        return None
    return (
        f"🔴 {last} 이 chunk 에 열을 더했는데 v_current_chunk 를 다시 만들지 않았다 — "
        "같은 파일의 ADD 뒤에 두거나, 더 뒤 마이그레이션에서 다시 만든다. "
        "`SELECT c.*` 는 생성 시점에 열 목록으로 고정된다."
    )


@pytest.mark.gate
def test_뷰_게이트가_실제로_0008형을_잡는다(tmp_path: Path) -> None:
    """🚨 **통과만 하는 게이트는 게이트가 아니다** — 집행계약이 세 번 적은 문장이다.

    D-197 이 게이트를 느슨하게 고쳤다(다른 파일 → 뒤 순서). 그 조건은
    *"종전 규칙이 잡던 것을 새 규칙도 잡는다는 것을 같은 커밋에서 보여야 한다"* 였는데
    09-12 오후에는 **읽어서 그렇다고 말했을 뿐**이다. 여기서 실제로 잰다 (D-203).

    ⛔ 검사 대상은 저장소의 진짜 마이그레이션이 아니라 **일부러 어긴 임시 폴더**다 —
       진짜를 건드리면 검사가 스스로 사고를 만든다.
    """
    add_only = "ALTER TABLE chunk ADD COLUMN IF NOT EXISTS zzz TEXT;"
    refresh = "DROP VIEW IF EXISTS v_current_chunk;\nCREATE VIEW v_current_chunk AS SELECT 1;"

    # ① 0008 형 — 열만 더하고 뷰를 안 만든다. **잡혀야 한다**
    (tmp_path / "0001_add.sql").write_text(add_only, encoding="utf-8")
    assert view_refresh_violation(tmp_path), "🔴 0008 형(열 추가 · 뷰 없음)을 못 잡는다"

    # ② 0009 형 — **뒤 파일**에서 다시 만든다. 통과해야 한다 (종전 규칙이 허용하던 모양)
    (tmp_path / "0002_view.sql").write_text(refresh, encoding="utf-8")
    assert view_refresh_violation(tmp_path) is None, "🔴 뒤 파일 재생성을 떨어뜨린다"

    # ③ 0010 형 — **같은 파일**의 ADD 뒤에 둔다. D-197 이 열어 준 모양
    one_file = tmp_path / "one"
    one_file.mkdir()
    (one_file / "0001_both.sql").write_text(f"{add_only}\n{refresh}", encoding="utf-8")
    assert view_refresh_violation(one_file) is None, "🔴 한 파일에 담은 것을 떨어뜨린다 (D-197)"

    # ④ 순서를 뒤집으면 다시 잡혀야 한다 — 뷰를 만든 **뒤에** 열을 더하면 낡은 채로 남는다
    rev = tmp_path / "rev"
    rev.mkdir()
    (rev / "0001_both.sql").write_text(f"{refresh}\n{add_only}", encoding="utf-8")
    assert view_refresh_violation(rev), "🔴 같은 파일 안의 **순서**를 안 본다"

    # ⑤ 열을 더한 적이 없으면 「검사 대상 없음」이다 — 통과와 구별한다 (D-170)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert view_refresh_violation(empty) == _NO_ADD


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
    # 🔄 2026-09-14 — 읽는 파일이 **동결본**으로 바뀌었다. 참조 대상만 바뀌고 뜻은 같다:
    #    「DDL 을 품지 않고 파일을 읽어 실행한다」. 어느 파일인지는 아래 게이트가 본다.
    assert "schema_0001.sql" in src, "🚨 마이그레이션이 db/schema_0001.sql 을 참조하지 않는다"


@pytest.mark.gate
def test_0001_이_읽는_파일은_동결본이다() -> None:
    """🔴 **0번의 입력이 고정되어야 뒤의 열셋이 전제를 갖는다** (2026-09-14 · D-221).

    ⛔ 종전에는 0번이 **실행 시점에** `db/schema.sql` 을 읽었다. 그 파일이 여덟 번 바뀌면서
       「0003 이 도는 DB 의 모양」이 사람마다 달라졌다 — 09-13(이서은)·09-14(박수진) 이틀
       연속 같은 자리에서 막힌 원인이다. **버전형 체인의 불변식은 「0번이 고정」이다.**
    🚨 **대입문만 본다.** docstring 에는 `db/schema.sql` 이 여러 번 나온다 — 무슨 일이
       있었는지 적어 두었기 때문이다. 낱말을 세면 그 설명까지 위반으로 잡는다
       (게이트 163 이 자기 자신을 오탐했던 것과 같은 함정).
    """
    src = MIGRATION.read_text(encoding="utf-8")
    m = re.search(r"^SCHEMA\s*=\s*(.+)$", src, re.M)
    assert m, "🚨 0001 에 SCHEMA 대입문이 없다"
    target = m.group(1)
    assert "schema_0001.sql" in target, (
        f"🚨 0001 이 동결본을 안 읽는다 — 지금 `{target.strip()}`\n"
        "   ⛔ `db/schema.sql` 로 되돌리면 09-13·14 의 증상이 그대로 돌아온다 (D-221)."
    )
    assert FROZEN.exists(), f"🚨 {FROZEN} 이 없다 — 0번의 입력이다"


@pytest.mark.gate
def test_동결본이_바뀌지_않았다() -> None:
    """🧊 **동결본은 한 글자도 바뀌지 않는다** (2026-09-14 · D-221).

    ⛔ 바뀌면 「이미 0번을 지난 DB」와 「지금 처음 지나는 DB」가 **다른 모양**이 된다.
       그 어긋남은 조용하다 — 고친 사람의 기기에서는 안 나고, 새로 온 사람만 밟는다.
    ★ 스키마를 바꿀 때 고치는 것은 `db/schema.sql` **+ 새 마이그레이션** 둘이다.
      이 파일은 그 둘 중 어느 쪽도 아니다.
    """
    assert FROZEN.exists(), f"🚨 {FROZEN} 이 없다 — 0번의 입력이다"
    got = _pin(FROZEN.read_text(encoding="utf-8"))
    assert got == FROZEN_PIN, (
        "🚨 **동결본이 바뀌었다.**\n"
        f"   핀  {FROZEN_PIN}\n   지금 {got}\n"
        "   ⛔ 핀을 갱신하지 않는다 — 파일을 되살린다:\n"
        "      git checkout -- db/schema_0001.sql\n"
        "   ★ 스키마를 바꾸려던 것이면 `db/schema.sql` 과 **새 마이그레이션**을 고친다."
    )


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


# ═══════════════════════════════════════════════════════════════════
# 🔴 **값**을 본다 — 이 파일에 없던 축이다 (2026-09-10 · D-178)
#
# ⛔ 위 게이트 다섯은 전부 **파일 텍스트 검사**다(문서 동일성 · DDL 미복사 · include_object ·
#    vector 차원 · ini ASCII). **ENUM 값이 파이프라인 산출값을 덮는지 보는 검사가 없었다.**
#    그래서 `split_t` 에 `test_sentence` 가 없는 채로 골든셋 1,908행이 이틀 동안 DB 밖에
#    서 있었고, 아무 게이트도 울리지 않았다.
# ═══════════════════════════════════════════════════════════════════

_ENUM = re.compile(r"CREATE TYPE\s+(\w+)\s+AS ENUM\s*\((.*?)\);", re.S)
# 🔄 값을 **더하기만** 하는 마이그레이션 (0005). `CREATE TYPE` 재생성과 달리 앞 모양을 남긴다.
_ADD_VALUE = re.compile(r"ALTER TYPE\s+(\w+)\s+ADD VALUE(?:\s+IF NOT EXISTS)?\s+'([^']+)'", re.I)


def _enums() -> dict[str, set[str]]:
    sql = SCHEMA.read_text(encoding="utf-8")
    return {name: set(re.findall(r"'([^']+)'", body)) for name, body in _ENUM.findall(sql)}


@pytest.mark.gate
def test_파이프라인이_쓰는_라벨이_violation_t_에_다_있다() -> None:
    """🔴 라벨이 타입에 없으면 그 행은 **DB 에 못 들어간다** — 조용히 빠지는 것이 아니라 막힌다.

    ⛔ 종전 `violation_t` 는 'V0'~'V8' 이었고 뜻이 스키마 어디에도 없었다. 접으면
       5종이 2칸으로 뭉갠다(V6 ← 소비자_기만 + 후기_체험기_기만 + 추천_보증_뒷광고).
    """
    from scripts.collect import CANDIDATE_TYPES, VIOLATION_TYPES  # noqa: PLC0415

    want = set(VIOLATION_TYPES) | set(CANDIDATE_TYPES)
    got = _enums()["violation_t"]

    assert want <= got, (
        f"🚨 `violation_t` 에 없는 라벨 {sorted(want - got)}\n"
        "   라벨 목록(scripts/collect.py)과 스키마가 갈렸다 — 그 행은 적재에서 막힌다."
    )


@pytest.mark.gate
def test_파이프라인이_배정하는_split_이_split_t_에_다_있다() -> None:
    """🔴 **이것이 없어서 골든셋이 이틀 동안 DB 밖에 있었다.**

    `preprocess/split.py` 는 `train` / `test_sentence` 만 배정한다.
    ⛔ `test_holdout` 은 예약값이라 배정된 적이 없고, `dev` 는 죽은 값이다 —
       스키마에는 그 둘만 있었다.
    """
    assert {"train", "test_sentence"} <= _enums()["split_t"]


@pytest.mark.gate
def test_골든셋_산출물의_값이_전부_스키마에_있다() -> None:
    """★ 상수가 아니라 **실제 산출물**로 대조한다 — 코드가 아니라 데이터가 진실이다."""
    golden = ROOT / "data" / "derived" / "golden" / "golden.jsonl"
    from scripts import derived_manifest as dm  # noqa: PLC0415

    dm.gate_guard(golden)  # 🔄 2026-09-19 — 역할대로 fail/skip · 옛 판 위에서 돌지 않는다 (F1)
    import json  # noqa: PLC0415

    rows = [json.loads(x) for x in golden.read_text(encoding="utf-8").splitlines() if x.strip()]
    enums = _enums()
    used = {
        "violation_t": {t for r in rows for t in r["labels"]},
        "split_t": {r["split"] for r in rows},
        "origin_t": {r["origin"] for r in rows},
    }
    for name, vals in used.items():
        assert vals <= enums[name], (
            f"🚨 `{name}` 에 없는 값이 골든셋에 있다 — {sorted(vals - enums[name])}\n"
            "   적재하면 그 행에서 막힌다. 스키마와 파생물 중 어느 쪽이 맞는지 정한다."
        )
    assert {r["unit"] for r in rows} <= {"문장", "낱말"}, "단위 축이 갈렸다 (D-155 · D-172)"


@pytest.mark.gate
def test_반대_대조_없는_값을_넣으면_잡힌다() -> None:
    """🚨 위 셋이 **실패할 수 있는 단언**임을 보인다 (D-170)."""
    enums = _enums()
    assert "없는_유형" not in enums["violation_t"]
    assert not ({"train", "없는_split"} <= enums["split_t"])


MIG_DIR = ROOT / "db" / "migrations"


def _views(sql: str) -> dict[str, str]:
    return {n: b.strip() for n, b in re.findall(r"CREATE VIEW (\w+) AS(.*?);", sql, re.S)}


@pytest.mark.gate
def test_마이그레이션이_만드는_모양이_schema_sql_과_같다() -> None:
    """🔴 **새 DB 와 옮긴 DB 가 갈리면 안 된다** (D-99).

    새 기기는 `db/schema.sql` 하나로 서고, 이미 있는 DB 는 `db/migrations/*.sql` 로 옮긴다.
    ⛔ 둘이 갈리면 **기기마다 스키마가 다르고 그 차이는 조용하다** — 한쪽에서만 적재가 막힌다.

    🔴 **파일 하나씩이 아니라 「전부 적용한 뒤」로 본다** (2026-09-10).
       ⛔ 종전에는 마이그레이션마다 `CREATE TYPE` 을 따로 꺼내 `schema.sql` 과 맞췄다.
          그러면 **나중 마이그레이션이 값을 더하는 순간 앞엣것이 틀린 것이 된다** —
          0003 은 `violation_t` 10종을 만들고 0005 가 하나를 더하는데, 옮긴 DB 의
          최종 모양은 11종으로 `schema.sql` 과 같다. 앞 파일은 **그때는 맞았던 값**이다.
       ★ 이 게이트가 지키려는 것은 파일별 일치가 아니라 **끝난 뒤의 모양**이다.
    """
    schema = SCHEMA.read_text(encoding="utf-8")
    s_enum = {n: re.findall(r"'([^']+)'", b) for n, b in _ENUM.findall(schema)}
    s_view = _views(schema)

    files = sorted(MIG_DIR.glob("*.sql")) if MIG_DIR.exists() else []
    assert files, f"🚨 {MIG_DIR} 에 마이그레이션 SQL 이 없다"

    # 마이그레이션을 순서대로 적용한 뒤의 ENUM 모양
    m_enum: dict[str, list[str]] = {}
    for f in files:
        sql = f.read_text(encoding="utf-8")
        for name, body in _ENUM.findall(sql):
            m_enum[name] = re.findall(r"'([^']+)'", body)
        for name, val in _ADD_VALUE.findall(sql):
            assert name in m_enum, (
                f"🚨 {f.name} 이 마이그레이션에서 만든 적 없는 타입 {name} 에 값을 더한다 —\n"
                "   옮긴 DB 에는 그 타입이 어떤 모양인지 이 파일들만 보고는 알 수 없다."
            )
            if val not in m_enum[name]:
                m_enum[name].append(val)

    for name, vals in m_enum.items():
        assert name in s_enum, f"🚨 마이그레이션이 `schema.sql` 에 없는 타입 {name} 을 만든다"
        assert vals == s_enum[name], (
            f"🚨 마이그레이션을 다 적용한 뒤의 `{name}` 이 `db/schema.sql` 과 다르다.\n"
            f"   마이그레이션 {vals}\n   schema.sql  {s_enum[name]}\n"
            "   새 DB 와 옮긴 DB 가 갈린다 — 한쪽에서만 적재가 막힌다."
        )

    # 🔴 **뷰도 ENUM 과 같이 접는다 — 「끝난 뒤의 모양」이다** (2026-09-13).
    #    ⛔ 종전에는 **파일마다** `schema.sql` 과 맞췄다. 그러면 **뷰 정의를 한 번이라도
    #       바꾸는 순간 앞 파일이 전부 틀린 것이 된다** — 실측: 0013 이 `v_risk_lookup` 에
    #       2인 확인 조건을 더하자 **0003(그 뷰를 떼었다 되만든 파일)이 빨개졌다.**
    #    ★ 이 게이트의 docstring 이 이미 그렇게 적어 뒀다 — *「지키려는 것은 파일별 일치가
    #      아니라 끝난 뒤의 모양」*. ENUM 쪽만 접고 뷰 쪽은 안 접혀 있었다.
    #    🚨 고치는 쪽을 **0003 이 아니라 게이트**로 정했다 — 돈 마이그레이션의 본문을 고치면
    #       그 파일이 하지 않은 일을 했다고 적게 된다 (0007 이 세운 규칙).
    m_view: dict[str, str] = {}
    for f in files:
        for name, body in _views(f.read_text(encoding="utf-8")).items():
            assert name in s_view, f"🚨 {f.name} 이 `schema.sql` 에 없는 뷰 {name} 을 만든다"
            m_view[name] = body  # 마지막에 만든 것이 옮긴 DB 의 모양이다
    for name, body in m_view.items():
        assert body == s_view[name], (
            f"🚨 마이그레이션을 다 적용한 뒤의 뷰 `{name}` 이 `db/schema.sql` 과 다르다.\n"
            f"   마이그레이션 {body!r}\n   schema.sql  {s_view[name]!r}\n"
            "   새 DB 와 옮긴 DB 가 갈린다 — 한쪽에서만 질의가 다른 답을 낸다."
        )


@pytest.mark.gate
def test_뷰_접기가_실제로_어긋남을_잡는다(tmp_path: Path) -> None:
    """반대 대조 — **접었더니 아무것도 안 잡는 게이트**가 되지 않았는지 본다 (D-170).

    🚨 접는 것은 「앞 파일이 옛 정의를 들고 있어도 된다」는 뜻이지
       「마지막 정의가 틀려도 된다」는 뜻이 아니다. 그 경계를 여기서 고정한다.
    """
    old = "\nCREATE VIEW v_x AS\nSELECT 1;\n"
    new = "\nCREATE VIEW v_x AS\nSELECT 2;\n"
    (tmp_path / "0001_a.sql").write_text(old, encoding="utf-8")
    (tmp_path / "0002_b.sql").write_text(new, encoding="utf-8")

    def folded(d: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in sorted(d.glob("*.sql")):
            out.update(_views(f.read_text(encoding="utf-8")))
        return out

    got = folded(tmp_path)
    # ✅ 앞 파일의 옛 정의는 통과한다 (그것이 이번에 고친 것)
    assert got["v_x"] == _views(new)["v_x"], "🚨 접기가 마지막 정의를 안 집는다"
    # 🔴 마지막 정의가 schema 와 다르면 여전히 잡힌다
    assert got["v_x"] != _views(old)["v_x"], "🚨 접기가 어긋남을 통째로 삼킨다 — 게이트가 죽었다"


@pytest.mark.gate
def test_타입을_바꾸는_마이그레이션은_제약을_먼저_뗀다() -> None:
    """🚨 **뷰만 붙잡는 게 아니다 — CHECK 제약도 컬럼 타입을 붙잡는다** (2026-09-10 실측).

    ⛔ 처음에 뷰만 떼고 돌렸다가 `operator does not exist: text = split_t` 로 죽었다.
       `ck_golden_injected_not_holdout` 이 `split = 'test_holdout'::split_t` 를 들고 있어서,
       컬럼을 text 로 바꾸는 순간 제약 식이 `text = split_t` 가 된다.
    ★ 컬럼 타입을 건드리는 마이그레이션은 **그 테이블의 제약을 먼저 떼고** 끝에서 되건다.
    """
    for f in sorted(MIG_DIR.glob("*.sql")) if MIG_DIR.exists() else []:
        sql = f.read_text(encoding="utf-8")
        typed = {t for t, _ in re.findall(r"ALTER TABLE (\w+) ALTER COLUMN (\w+) TYPE", sql)}
        if not typed:
            continue
        added = set(re.findall(r"ALTER TABLE (\w+) ADD CONSTRAINT", sql))
        for table in typed & added:
            first_type = sql.index(f"ALTER TABLE {table} ALTER COLUMN")
            drops = [m.start() for m in re.finditer(rf"ALTER TABLE {table} DROP CONSTRAINT", sql)]
            assert drops and min(drops) < first_type, (
                f"🚨 {f.name}: `{table}` 의 컬럼 타입을 바꾸기 전에 제약을 떼지 않는다.\n"
                "   제약 식이 옛 타입을 들고 있으면 `operator does not exist` 로 죽는다."
            )


@pytest.mark.gate
def test_타입을_바꾸는_마이그레이션은_뷰를_먼저_뗀다() -> None:
    """🚨 뷰가 컬럼 타입을 붙잡는다 — 안 떼면 `cannot alter type ... used by a view` 로 죽는다.

    ⛔ 처음에 이걸 안 보고 썼다가 `v_risk_lookup`(sanction_rule.violation_type)과
       `v_publishable_golden`(golden_sample.*) 에서 막힐 뻔했다.
    """
    for f in sorted(MIG_DIR.glob("*.sql")) if MIG_DIR.exists() else []:
        sql = f.read_text(encoding="utf-8")
        made = set(_views(sql))
        if not made:
            continue
        dropped = set(re.findall(r"DROP VIEW IF EXISTS (\w+)", sql))
        assert made <= dropped, (
            f"🚨 {f.name} 이 뷰 {sorted(made - dropped)} 를 만들면서 먼저 떼지 않는다"
        )
        for name in made:
            assert sql.index(f"DROP VIEW IF EXISTS {name}") < sql.index(f"CREATE VIEW {name}"), (
                f"🚨 {f.name}: `{name}` 을 떼기 전에 만든다 — 순서가 뒤집혔다"
            )


def test_골든셋_계보는_모두_프래그먼트로_등재돼_있다() -> None:
    """🔴 `GOLDEN_FRAGMENT` 가 가리키는 프래그먼트는 `load_fragments()` 가 만든다 (2026-09-19).

    ⛔ 한쪽만 등재하면 `golden_sample.fragment_id` 외래키가 적재 중에 깨진다 — 두 표가 한 쌍이다.
    """
    from scripts import load_db

    made = {f[0] for f in load_db.FRAGMENTS}
    missing = [fid for fid in load_db.GOLDEN_FRAGMENT.values() if fid not in made]
    assert not missing, f"load_fragments() 에 없는 프래그먼트: {missing}"


@pytest.mark.gate
def test_G2_조각은_재배포_불가로_적힌다() -> None:
    """🔴 D-249 (D-133 ① 개정) — 광고주 저작물 조각(G2)이면 골든셋 행도 재배포 불가다.

    ⛔ 2026-09-20 까지 적재기는 G2 로 만들고 골든셋은 `redistributable: True` 를 상수로 박았다 — 인용 문구 5,801행.
    """
    from preprocess.lineage import GOLDEN_LINEAGE
    from scripts import load_db

    grade = {f[0]: f[3] for f in load_db.FRAGMENTS}
    bad = [
        (k, fid, grade.get(fid), redist)
        for k, (fid, redist) in GOLDEN_LINEAGE.items()
        if redist != (grade.get(fid) != "G2")
    ]
    assert not bad, f"등급과 재배포 표시가 어긋난다 (D-249): {bad}"
