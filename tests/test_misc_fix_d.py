"""런처 전수 감사 🟡 고침 — inventory · status · rebuild · admin-add · doctor (2026-09-20 · D-254).

🚨 **게이트가 아니다** — DB 는 가짜로, 파일은 tmp 로 돈다. 네트워크·postgres 없음.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── ⑤ inventory — collect 밖 소스의 원장 행이 사라지지 않는다 ─────────────────
def test_inventory_는_원장에_행이_있으면_상태와_무관하게_올린다() -> None:
    from preprocess import inventory

    reg = {
        "a": {"status": "collect"},
        "m": {"status": "manual"},
        "h": {"status": "hold"},
        "h0": {"status": "hold"},  # 원장 행 없음 — 종전처럼 안 올린다
    }
    led = {"m": {"p1"}, "h": {"p2"}, "ghost": {"p3"}}
    got = inventory.listed(reg, led)
    assert got == {"a": "collect", "m": "manual", "h": "hold", "ghost": "미등재"}


# ── ⑥ status — 팀 축은 원장에서 읽는다 · 없음을 성공으로 세지 않는다 ────────────
@pytest.fixture
def status_env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    from scripts import data_status
    from scripts import derived_manifest as dm

    monkeypatch.setattr(data_status, "ROOT", tmp_path)
    monkeypatch.setattr(data_status, "MANIFEST", tmp_path / "m.jsonl")
    monkeypatch.setattr(dm, "ROOT", tmp_path)
    monkeypatch.setattr(dm, "OUT", tmp_path / "dm.jsonl")
    return data_status, tmp_path


def test_status_원장이_없으면_멈춘다(status_env) -> None:
    ds, _ = status_env
    with pytest.raises(SystemExit) as e:
        ds._manifest()
    assert "모름" in str(e.value.code)


def test_status_깨진_줄을_센다(status_env) -> None:
    ds, tmp = status_env
    (tmp / "m.jsonl").write_text(
        '{"source_id": "a"}\n{broken\n{"source_id": "a"}\n[1]\n', encoding="utf-8"
    )
    c, broken = ds._manifest()
    assert c["a"] == 2 and broken == 2


def test_status_파생물은_디스크가_아니라_원장에서_읽는다(status_env) -> None:
    ds, tmp = status_env
    with pytest.raises(SystemExit):
        ds._derived()  # 원장 없음 → 멈춘다
    (tmp / "dm.jsonl").write_text(
        json.dumps({"경로": "data/derived/b.jsonl", "부류": "생성물", "bytes": 10, "행": 2})
        + "\n"
        + json.dumps({"경로": "data/derived/a.jsonl", "부류": "표본", "bytes": 5, "행": 1})
        + "\n",
        encoding="utf-8",
    )
    rows = ds._derived()
    assert [r["경로"] for r in rows] == ["data/derived/a.jsonl", "data/derived/b.jsonl"]
    src = pathlib.Path(ds.__file__).read_text(encoding="utf-8")
    assert "rglob(" not in src, "파생물 절이 아직 이 기기 디스크를 훑는다"


# ── ⑨ gen_registry — 미등재·STATUS 누락은 쓰기 전에 멈춘다 ─────────────────────
def _gen_copy(tmp: pathlib.Path) -> pathlib.Path:
    for rel in (
        "scripts/gen_registry.py",
        "scripts/registry_review.yaml",
        "scripts/registry_head.yaml",
        "scripts/registry_tail.yaml",
        "docs/03_데이터/_matrix/sources.json",
    ):
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp / rel)
    return tmp / "scripts/gen_registry.py"


def _run(script: pathlib.Path) -> subprocess.CompletedProcess:
    """🔴 CI 러너(Windows · cp1252)의 파이프를 **어느 기기에서나** 재현한다 (2026-09-20 · CI 실측).

    ⛔ 이 줄 없이는 로컬(UTF-8 콘솔)에서 초록이고 CI 에서만 `UnicodeEncodeError` 로 죽었다 —
       `test_derived_manifest.py` 의 09-19 처방과 같다.
    """
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    return subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_gen_registry_출력이_그대로다(tmp_path: pathlib.Path) -> None:
    """STATUS 를 명시로 바꿔도 `data_sources.yaml` 은 한 글자도 안 바뀐다."""
    r = _run(_gen_copy(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "data_sources.yaml").read_bytes() == (
        ROOT / "data_sources.yaml"
    ).read_bytes()


def test_gen_registry_새_미등재는_rc1_이고_쓰지_않는다(tmp_path: pathlib.Path) -> None:
    script = _gen_copy(tmp_path)
    sj = tmp_path / "docs/03_데이터/_matrix/sources.json"
    src = json.loads(sj.read_text(encoding="utf-8"))
    fake = dict(src[0])
    fake["id"] = "zz_new_source"
    src.append(fake)
    sj.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
    r = _run(script)
    assert r.returncode == 1
    assert "zz_new_source" in r.stdout + r.stderr
    assert not (tmp_path / "data_sources.yaml").exists()


def test_gen_registry_STATUS_누락은_기본값으로_열지_않는다(tmp_path: pathlib.Path) -> None:
    script = _gen_copy(tmp_path)
    text = script.read_text(encoding="utf-8")
    assert '    "nsmc": "collect",\n' in text
    script.write_text(text.replace('    "nsmc": "collect",\n', "", 1), encoding="utf-8")
    r = _run(script)
    assert r.returncode == 1 and "nsmc" in r.stderr
    assert not (tmp_path / "data_sources.yaml").exists()


def test_gen_registry_STATUS_오타를_잡는다(tmp_path: pathlib.Path) -> None:
    script = _gen_copy(tmp_path)
    text = script.read_text(encoding="utf-8")
    script.write_text(
        text.replace(
            '    "nsmc": "collect",\n', '    "nsmc": "collect",\n    "nsmcc": "hold",\n', 1
        ),
        encoding="utf-8",
    )
    r = _run(script)
    assert r.returncode == 1 and "nsmcc" in r.stderr


# ── ⑩ admin-add — 있는 계정을 말없이 덮지 않는다 (가짜 DB) ───────────────────
class _Cur:
    def __init__(self, db: dict) -> None:
        self.db, self.rowcount, self._one = db, 0, None

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        return None

    def execute(self, sql: str, args: tuple = ()) -> None:
        self.db["sql"].append(sql)
        if sql.startswith("SELECT disabled_at"):
            acc = self.db["acc"].get(args[0])
            self._one = None if acc is None else (acc["disabled_at"],)
        elif sql.startswith("UPDATE"):
            acc = self.db["acc"].get(args[2])
            if acc:
                acc.update(pw=args[0], name=args[1])
            self.rowcount = 1 if acc else 0
        elif "INSERT" in sql:
            ini = args[1]
            if ini in self.db["acc"]:
                self.rowcount = 0
            else:
                self.db["acc"][ini] = {"pw": args[3], "name": args[2], "disabled_at": None}
                self.rowcount = 1

    def fetchone(self):
        return self._one


class _Conn:
    def __init__(self, db: dict) -> None:
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        return None

    def cursor(self):
        return _Cur(self.db)


@pytest.fixture
def admin(monkeypatch: pytest.MonkeyPatch):
    import psycopg

    from scripts import admin_account as aa

    db: dict = {"acc": {}, "sql": []}
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _Conn(db))
    monkeypatch.setattr(aa, "dsn", lambda: "postgresql://x/y")
    monkeypatch.setattr(aa, "_known_initials", lambda: ["ohb"])
    monkeypatch.setattr(aa, "hash_password", lambda pw: f"H({pw})")
    monkeypatch.setattr(aa.getpass, "getpass", lambda prompt="": "correct-horse-battery")
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    return aa, db


def test_admin_새로_만든다(admin, capsys: pytest.CaptureFixture) -> None:
    aa, db = admin
    assert aa.add("ohb") == 0
    assert db["acc"]["ohb"]["pw"] == "H(correct-horse-battery)"
    assert "새로 만들었다" in capsys.readouterr().out
    assert not any("DO UPDATE" in s for s in db["sql"])


def test_admin_있는_계정은_reset_없이_안_바꾼다(admin) -> None:
    aa, db = admin
    db["acc"]["ohb"] = {"pw": "OLD", "name": "ohb", "disabled_at": "2026-09-01"}
    assert aa.add("ohb") == 1
    assert db["acc"]["ohb"] == {"pw": "OLD", "name": "ohb", "disabled_at": "2026-09-01"}


def test_admin_reset_은_비밀번호만_바꾸고_꺼진_계정을_안_켠다(
    admin, capsys: pytest.CaptureFixture
) -> None:
    aa, db = admin
    db["acc"]["ohb"] = {"pw": "OLD", "name": "ohb", "disabled_at": "2026-09-01"}
    assert aa.add("ohb", reset=True) == 0
    assert db["acc"]["ohb"]["pw"] == "H(correct-horse-battery)"
    assert db["acc"]["ohb"]["disabled_at"] == "2026-09-01"
    out = capsys.readouterr().out
    assert "바꿨다" in out and "꺼져 있다" in out


def test_admin_reset_은_없는_계정을_만들지_않는다(admin) -> None:
    aa, db = admin
    assert aa.add("ohb", reset=True) == 1
    assert "ohb" not in db["acc"]


# ── ④ doctor --env — head 대조 · 값 모양 ────────────────────────────────────
def test_doctor_alembic_head_는_DB_없이_읽힌다() -> None:
    from scripts import doctor

    heads = doctor._alembic_heads()
    assert len(heads) == 1
    (only,) = heads
    assert any(
        only in p.name or only in p.read_text(encoding="utf-8")
        for p in (ROOT / "alembic/versions").glob("*.py")
    )


def test_doctor_모르는_DATA_ROLE_과_틀린_DATA_DEVICE_는_빨강이다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import doctor

    vals = {"DATA_ROLE": "canonnical", "DATA_STORE": "", "DATA_DEVICE": "홍길동 노트북"}
    monkeypatch.setattr("collect.env.setting", lambda k: vals.get(k, ""))
    assert doctor._check_data_env() == 2


def test_doctor_팀원_기기의_예약어_별칭은_빨강이다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🆕 2026-09-21 — 모양은 맞아도 `canonical` 은 정본 예약어다. 정본이면 초록 (반대 대조)."""
    from scripts import doctor

    vals = {"DATA_ROLE": "replica", "DATA_STORE": "", "DATA_DEVICE": "canonical"}
    monkeypatch.setattr("collect.env.setting", lambda k: vals.get(k, ""))
    assert doctor._check_data_env() == 1
    vals["DATA_ROLE"] = "canonical"
    assert doctor._check_data_env() == 0


def test_doctor_DATA_STORE_폴더가_없으면_빨강이다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import doctor

    vals = {"DATA_ROLE": "replica", "DATA_STORE": str(tmp_path / "없음"), "DATA_DEVICE": "c-1"}
    monkeypatch.setattr("collect.env.setting", lambda k: vals.get(k, ""))
    assert doctor._check_data_env() == 1
    (tmp_path / "없음").mkdir()
    assert doctor._check_data_env() == 0


def test_doctor_head_가_아닌_리비전은_빨강이다(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from scripts import doctor

    class C:
        def __init__(self) -> None:
            self.q: list = []

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

        def cursor(self):
            return self

        def execute(self, sql: str, *a) -> None:
            self.q.append(sql)

        def fetchone(self):
            last = self.q[-1]
            if "pg_extension" in last:
                return (1,)
            if "to_regclass" in last:
                return ("alembic_version",)
            return ("0001_old",)

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: C())
    monkeypatch.setattr("app.settings.dsn", lambda: "postgresql://x/y")
    monkeypatch.setattr(doctor, "_sanction_signatures", lambda cur: None)
    monkeypatch.setattr(doctor, "_report_sanction", lambda s: None)
    assert doctor._check_db() == 1
    monkeypatch.setattr(doctor, "_alembic_heads", lambda: {"0001_old"})
    assert doctor._check_db() == 0


def test_doctor_틀린_DATABASE_URL_은_빨강이고_메시지를_낸다(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from app import settings as st
    from scripts import doctor

    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
    st.settings.cache_clear()
    try:
        assert doctor._check_db() == 1
        assert "postgres 가 아니다" in capsys.readouterr().out
    finally:
        st.settings.cache_clear()
