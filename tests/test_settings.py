"""설정 경계 — **읽는 자리가 하나인가** (2026-09-12 밤 · D-99 · 병렬작업 계약 §1 #4).

⛔ `dsn()` 이 네 벌이었고, 네 곳 다 `.env` 를 안 읽었다. 규칙으로 막히지 않아서
   (같은 세션에서 D-99 를 세 번 인용하고도 한 벌을 더 만들었다) **검사로 옮긴다** (D-117).

🚨 이 파일은 **정적 검사**다 — 실제 DB 에 붙는지는 보지 않는다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import settings as st

ROOT = Path(__file__).resolve().parent.parent

#: 훑지 않는 곳 — 가상환경·생성물·캐시·데이터. `.gitignore` 와 같은 뜻이다 (집행계약 §6).
_SKIP = {".venv", "build", "dist", "data", "models", "mlruns", "__pycache__", ".ruff_cache"}


def _rel(p: Path) -> str:
    """저장소 기준 상대 경로를 **`/` 로 정규화**해서 낸다.

    🔴 **2026-09-12 밤 — 여기서 게이트 셋이 Windows 에서 떨어졌다.**
       `str(p.relative_to(ROOT))` 는 Windows 에서 `app\\settings.py` 를 낸다. 기대값을
       `"app/settings.py"` 로 적어 두었으니 **팀 5인 전원과 CI(windows-latest)에서 실패**한다.
    ⛔ 리눅스에서 검증하고 Windows 팀에 보낸 것이고, `gate.yml` 이 러너를 Windows 로 둔 이유가
       *"「내 기기에서는 되는데」를 CI 가 못 잡는다"* 였다 — **그 문장을 반대 방향으로 밟았다** (D-206).
    ★ 그래서 비교 직전에 고치지 않고 **경로를 내는 자리 하나**에서 정규화한다. 호출부가
       `str()` 을 쓸 수 없게 만드는 것이 이 함수의 목적이다 (D-117 — 코드로 막는다).
    """
    return p.relative_to(ROOT).as_posix()


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
        _rel(p) for p in _sources() if re.search(r"^def dsn\(", p.read_text(encoding="utf-8"), re.M)
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
    where = [_rel(p) for p in _sources() if needle in p.read_text(encoding="utf-8")]
    assert where == ["app/settings.py"], f"🔴 기본 DSN 이 여기도 있다: {where}"


@pytest.mark.gate
def test_env_를_읽는_자리가_하나다() -> None:
    """🚨 `.env` 를 읽는 것은 `collect/env.py` 하나다 — 그 파일이 스스로 그렇게 적었다.

    ⛔ 두 곳이 되면 「어느 인코딩으로 읽었나」·「override 를 걸었나」가 갈린다.
       2026-09-02 에 UTF-8 BOM 으로 한 번 겪었다.
    """
    where = [_rel(p) for p in _sources() if "load_dotenv(" in p.read_text(encoding="utf-8")]
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


@pytest.mark.gate
def test_경로_비교가_OS_에_안_흔들린다() -> None:
    """🚨 **이 게이트 셋이 Windows 에서 떨어진 자리를 검사로 만든다** (D-206).

    ⛔ `str(Path.relative_to(...))` 는 Windows 에서 `\\` 를 낸다. 기대값을 `/` 로 적어 두면
       **리눅스에서만 통과하는 게이트**가 된다 — 팀 5인 전원과 CI 러너가 Windows 인데.
    ★ 그래서 이 파일은 경로를 `_rel()` 로만 낸다. 누가 `str()`·f-string 으로 되돌리면
       여기서 걸린다 — 규칙이 아니라 검사다 (D-117).
    """
    src = Path(__file__).read_text(encoding="utf-8")
    assert "as_posix()" in src, "🔴 `_rel()` 이 posix 정규화를 잃었다"
    # 🚨 찾는 모양을 **글자 그대로 적지 않는다** — 적으면 이 검사가 자기를 잡는다.
    #    ⛔ 오늘만 세 번째다(파일 자체 오탐 · 기본 DSN · 여기). 정규식으로 **모양**을 본다.
    bad = re.search(r'f"\{\s*p\.relative_to', src)
    assert not bad, (
        "🔴 경로를 f-string 으로 직접 냈다 — Windows 에서 역슬래시가 나온다. `_rel(p)` 를 쓴다"
    )
    # 🚨 **정규화가 실제로 동작하는가** — 논증이 아니라 실행으로 (D-203)
    assert _rel(ROOT / "app" / "settings.py") == "app/settings.py"


# ══════════════════════════════════════════════════════════════════════
#  🆕 2026-09-12 밤 — 파라미터를 코드에 흩지 않는다 (D-99 · D-208)
# ══════════════════════════════════════════════════════════════════════

#: 🔴 `app/settings.py` 로 옮긴 이름들. **다시 숫자를 물리면 여기서 걸린다.**
#:    ⛔ 이름을 글자로 적되 **모양은 정규식으로** 본다 — 이 파일이 자기를 잡지 않게 (D-206).
_MOVED = (
    "POOL",
    "RRF_K",
    "MAX_ATTEMPT",
    "MIN_MEASURABLE",
    "MIN_SAMPLES",
    "DIM",
    "BATCH",
    "MAX_CHARS",
    "MODEL_ID",
    "_MIN_STEM",
)


@pytest.mark.gate
def test_판정_파라미터를_코드에_다시_적지_않는다() -> None:
    """🔴 **D-99 의 실물.** `MIN_MEASURABLE = 30` 이 다섯 곳, `2`(재생성 K)가 세 곳이었다.

    ⛔ 하나를 바꾸면 나머지가 **조용히 안 따라온다.** 그리고 `preprocess/golden.py` 는
       상수도 주석도 없는 생리터럴 `30` 이었다 — D-40 을 바꾸면 거기만 남았을 것이다.
    ★ 값은 `app/settings.py` 의 `PARAMS` 가 든다. 여기서는 **이름에 숫자를 다시 물리는 것**을 막는다.
    """
    me = Path(__file__).resolve()
    pat = re.compile(
        r"^\s*(" + "|".join(_MOVED) + r")\s*(?::\s*\w+\s*)?=\s*[\"']?\d|"
        r"^\s*(" + "|".join(_MOVED) + r")\s*=\s*[\"'][^\"']*/",
        re.MULTILINE,
    )
    bad: list[str] = []
    for p in _sources():
        if p.resolve() == me or _rel(p) == "app/settings.py":
            continue
        for m in pat.finditer(p.read_text(encoding="utf-8")):
            bad.append(f"{_rel(p)}:{m.string[: m.start()].count(chr(10)) + 1}")
    assert not bad, (
        f"🔴 파라미터에 숫자를 다시 물렸다: {bad}\n"
        "   고치는 법 — app/settings.py 의 PARAMS 를 import 해서 쓴다 (D-99)"
    )


#: 🆕 2026-09-21 — 인용 상한을 **산문으로** 적는 자리. 숫자는 코드가 아니라 문장 속에 있어 위 검사를 안 지난다.
#:    ⛔ D-249 가 40 → 120 으로 고칠 때 `PARAMS` 한 곳만 바뀌고 **산문 다섯 벌**(레지스트리 생성기 ·
#:       판정매트릭스 원천 · 수집기 docstring 과 출력문 · 전처리 사양)이 40 을 들고 남았다. 생성물
#:       `data_sources.yaml` 까지 40 을 말했고 `rebuild` 를 돌려도 40 이 다시 나왔다 — 원장이 폐기된 수를 말했다.
_QUOTE_CAP_PROSE = (
    "scripts/gen_registry.py",
    "docs/03_데이터/_matrix/data.js",
    "data_sources.yaml",
    "scripts/registry_rationale.yaml",
    "docs/03_데이터/_matrix/sources.json",
    "docs/03_데이터/판정매트릭스.html",
    "docs/03_데이터/전처리_사양.md",
)
#: 🚨 일부러 빼는 것 — `scripts/registry_review.yaml` 은 2인 확인 **서명 당시 문언**이라 고치지 않는다
#:    (그 자리에 🔄 줄을 붙였다). 결정기록·사실원장·인계는 그날의 기록이다.
_QUOTE_CAP_LINE = re.compile(r"(\d+)\s*자\s*상한|상한\s*(\d+)\s*자")


@pytest.mark.gate
def test_인용_상한을_적은_산문은_PARAMS_와_같다() -> None:
    """🔴 인용 광고 문구의 보관 상한을 문장으로 적은 자리가 `PARAMS.quote_max_chars` 와 같은가 (D-249 · D-99).

    ★ 인용 문구 줄만 본다 — 같은 줄에 `NOREDIST` 나 `인용` 이 있을 때. 청크 700자 같은 다른 상한과 안 섞인다.
    """
    from app.settings import PARAMS

    files = [ROOT / p for p in _QUOTE_CAP_PROSE] + sorted((ROOT / "collect").glob("*.py"))
    bad: list[str] = []
    for p in files:
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "NOREDIST" not in line and "인용" not in line:
                continue
            for m in _QUOTE_CAP_LINE.finditer(line):
                n = int(m.group(1) or m.group(2))
                if n != PARAMS.quote_max_chars:
                    bad.append(f"{_rel(p)}:{i} — {n}자")
    assert not bad, (
        f"🔴 인용 상한이 PARAMS({PARAMS.quote_max_chars}자)와 다르다: {bad}\n"
        "   고치는 법 — 원천(생성기·data.js·수집기)을 고치고 `launcher.py rebuild` (D-90)"
    )


def test_반대_대조_옛_40자_문언을_잡는다() -> None:
    """위 게이트가 실제로 실패할 수 있는가 — D-249 이전 문언을 그대로 넣어 본다 (D-170)."""
    line = "문구만 취해 G2+NOREDIST·40자 상한으로 다룬다 (D-133 ①②③)."
    m = _QUOTE_CAP_LINE.search(line)
    assert m and int(m.group(1)) == 40 and "NOREDIST" in line


@pytest.mark.gate
def test_파라미터에_출처_태그가_붙어_있다() -> None:
    """🚨 판정·게이트·적재에 걸리는 값에는 출처를 적는다 (D-201 → D-205).

    ⛔ 출처 없는 값은 「누가 왜 정했는지 모르는 판정 파라미터」다.
    """
    src = (ROOT / "app" / "settings.py").read_text(encoding="utf-8")
    body = src.split("class Params", 1)[1].split("PARAMS = Params()", 1)[0]
    fields = re.findall(r"^\s{4}(\w+):\s", body, re.MULTILINE)
    assert fields, "🔴 Params 에 필드가 없다"
    tags = ("[측정]", "[문헌]", "[관행]", "[임의]", "[설계]")
    for name in fields:
        before = body.split(f"    {name}:", 1)[0]
        block = before.rsplit("\n\n", 1)[-1]
        assert any(t in block for t in tags), (
            f"🔴 `{name}` 에 출처 태그가 없다 — {tags} 중 하나를 주석에 적는다 (D-201)"
        )


@pytest.mark.gate
@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@h:5432/d", "postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"],
)
def test_env_example_형태를_전부_받는다(url: str) -> None:
    """🔴 **문서대로 복사한 사람이 밟던 자리다** (2026-09-12 밤).

    ⛔ `.env.example` 이 「기본값 · 그대로 두면 됩니다」라 적어 둔 값은
       `postgresql+psycopg://…` 인데, 검증기가 그것을 **거부하고 있었다.**
       alembic(SQLAlchemy)은 `+psycopg` 를 **요구**하고 psycopg 직결은 그것을 **못 읽는다** —
       소비자가 둘이라 값도 두 형태다.
    """
    from app.settings import Settings

    assert Settings(database_url=url).database_url == url


@pytest.mark.gate
def test_한_값에서_두_형태가_나온다() -> None:
    """🚨 psycopg 는 접미사를 떼고, SQLAlchemy 는 붙인다. **값은 하나다** (D-99)."""
    import app.settings as S

    for given in ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"):
        os.environ["DATABASE_URL"] = given
        S.settings.cache_clear()
        assert "+psycopg" not in S.dsn(), f"🔴 psycopg 용에 드라이버가 남았다 — {S.dsn()}"
        assert "+psycopg" in S.sqlalchemy_url(), "🔴 SQLAlchemy 용에 드라이버가 없다"
    os.environ.pop("DATABASE_URL", None)
    S.settings.cache_clear()


@pytest.mark.gate
def test_env_example_의_기본값이_실제로_통과한다() -> None:
    """🔴 **문서와 코드를 대조한다** — 둘이 갈리면 팀원 4명이 첫날 밟는다 (D-99 의 문서판)."""
    import app.settings as S

    line = next(
        ln
        for ln in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if ln.startswith("DATABASE_URL=")
    )
    value = line.split("=", 1)[1].strip()
    os.environ["DATABASE_URL"] = value
    S.settings.cache_clear()
    try:
        assert S.dsn().startswith("postgresql://"), f"🔴 .env.example 의 값이 안 통한다 — {value}"
    finally:
        os.environ.pop("DATABASE_URL", None)
        S.settings.cache_clear()
