"""`scripts/load_db.py` — 사전 거두기 · 수집 원장 계약 (2026-09-20 · D-254 · 감사 §2 load).

⛔ `load_dict` 만 옛 행을 안 지웠다 — 사전에서 뺀 금지 표현이 DB 에 영구히 남는다.
⛔ `load_manifest` 는 원장이 없으면 0 을 내고, 모르는 원천 행을 조용히 건너뛰었다.
🔴 DB 없이 돈다 — 가짜 커서.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from scripts import load_db


class _Cur:
    def __init__(self, terms: list[str]) -> None:
        self.terms = terms
        self.calls: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.calls.append((sql, params))

    def fetchall(self) -> list[tuple[str]]:
        return [(t,) for t in self.terms]

    def deletes(self) -> list[tuple[str, object]]:
        return [c for c in self.calls if c[0].startswith("DELETE")]


def _dict_file(tmp: pathlib.Path, terms: list[str]) -> None:
    (tmp / "banned_terms.jsonl").write_text(
        "".join(
            json.dumps({"term": t, "유형": ["거짓_과장"]}, ensure_ascii=False) + "\n" for t in terms
        ),
        encoding="utf-8",
    )


@pytest.fixture
def derived(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setattr(load_db, "DERIVED", tmp_path)
    monkeypatch.setattr(load_db, "ALLOW_MISSING", False)
    return tmp_path


@pytest.mark.gate
def test_사전에서_빠진_용어를_거둔다(derived: pathlib.Path) -> None:
    _dict_file(derived, ["완치", "특효"])
    cur = _Cur(["완치", "특효", "만병통치"])
    load_db.load_dict(cur, dry=False)
    dels = cur.deletes()
    assert len(dels) == 1
    assert dels[0][1][2] == ["만병통치"]
    # 🚨 이 적재기가 넣는 칸 안에서만 거둔다
    assert dels[0][1][:2] == (load_db.DICT_FRAGMENT, load_db.DICT_KIND)


@pytest.mark.gate
def test_빈_사전이면_거두지_않고_멈춘다(derived: pathlib.Path) -> None:
    _dict_file(derived, [])
    cur = _Cur(["완치"])
    with pytest.raises(SystemExit):
        load_db.load_dict(cur, dry=False)
    assert not cur.deletes()


def test_allow_missing_으로_파일이_없으면_거두지_않고_넘어간다(
    derived: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load_db, "ALLOW_MISSING", True)
    cur = _Cur(["완치"])
    assert load_db.load_dict(cur, dry=False) == (0, 0)
    assert not cur.deletes()


def test_dry_run_은_거두지_않는다(derived: pathlib.Path) -> None:
    _dict_file(derived, ["완치"])
    assert load_db.load_dict(_Cur([]), dry=True) == (1, 1)


@pytest.mark.gate
def test_수집_원장이_없으면_멈춘다(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "ALLOW_MISSING", False)
    with pytest.raises(SystemExit):
        load_db.load_manifest(_Cur([]), dry=True)


def test_수집_원장이_없어도_allow_missing_이면_0(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "ALLOW_MISSING", True)
    assert load_db.load_manifest(_Cur([]), dry=True) == 0


def test_모르는_원천_행은_세서_찍는다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.jsonl").write_text(
        "".join(
            json.dumps({"source_id": s, "sha256": f"{i}"}) + "\n"
            for i, s in enumerate(["알던것", "모르는것", "모르는것"])
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "_sources", lambda: {"알던것": {}})
    assert load_db.load_manifest(_Cur([]), dry=True) == 1
    out = capsys.readouterr().out
    assert "모르는것 2" in out
