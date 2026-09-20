"""`ingest register` — 원장을 읽고, 폴더를 고르지 못하면 멈춘다 (2026-09-20 · D-254 · D-250).

🚨 **게이트가 아니다** — 원장·원문을 건드리므로 tmp 로 돌린다.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import ingest, store


@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    raw = tmp_path / "raw_root"
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "RAW", raw)
    monkeypatch.setattr(store, "MANIFEST", ledger)
    monkeypatch.setattr(store, "_INDEX", None)
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(store, "FAMILY_OF", {"가짜소스": ("가짜계열",), "두폴더": ("가", "가_pdf")})
    monkeypatch.setattr(ingest.registry, "require", lambda sid, use: {"url": "http://x"})
    monkeypatch.setattr(ingest.registry, "spec", lambda sid: {"url": "http://x"})
    monkeypatch.setattr(ingest.registry, "mark_collected", lambda sid: None)
    monkeypatch.setattr(ingest.registry, "is_g2", lambda sid: False)
    src = tmp_path / "inbox"
    src.mkdir()
    return {"raw": raw, "ledger": ledger, "src": src, "fam": raw / "가짜계열"}


def _rows(ledger: pathlib.Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_새_파일은_복사하고_행을_붙인다(env: dict) -> None:
    (env["src"] / "a.txt").write_bytes(b"one\n")
    assert ingest.cmd_register("가짜소스", env["src"], "U1") == 0
    assert (env["fam"] / "a.txt").read_bytes() == b"one\n"
    rows = _rows(env["ledger"])
    assert len(rows) == 1 and rows[0]["path"].replace("\\", "/").endswith("가짜계열/a.txt")
    assert rows[0]["device"] == "pytest"


def test_원장에_같은_것이_있으면_복사하지_않는다(env: dict) -> None:
    """🔴 D-250 — 다른 기기가 받은 것(이 기기 디스크엔 없다)을 다시 넣지 않는다."""
    payload = b"same\n"
    store.manifest_append(
        source_id="가짜소스",
        url="",
        sha256=store.sha256(payload),
        bytes_=len(payload),
        path=str((env["fam"] / "a.txt").relative_to(store.ROOT)),
    )
    (env["src"] / "a.txt").write_bytes(payload)
    assert ingest.cmd_register("가짜소스", env["src"], "U1") == 0
    assert not (env["fam"] / "a.txt").exists(), "원장에 있는 것을 다시 복사했다"
    assert len(_rows(env["ledger"])) == 1


def test_디스크에_같은_파일이_있고_원장_행이_없으면_행을_붙인다(env: dict) -> None:
    """🟡 종전에는 조용히 건너뛰어 원장에 끝내 안 올랐다."""
    env["fam"].mkdir(parents=True)
    (env["fam"] / "a.txt").write_bytes(b"x\n")
    (env["src"] / "a.txt").write_bytes(b"x\n")
    assert ingest.cmd_register("가짜소스", env["src"], "U1") == 0
    rows = _rows(env["ledger"])
    assert len(rows) == 1 and rows[0]["sha256"] == store.sha256(b"x\n")
    # 두 번째는 원장에 있으니 스킵
    assert ingest.cmd_register("가짜소스", env["src"], "U1") == 0
    assert len(_rows(env["ledger"])) == 1


def test_같은_이름_다른_내용은_판으로_둔다(env: dict, capsys: pytest.CaptureFixture) -> None:
    env["fam"].mkdir(parents=True)
    (env["fam"] / "a.txt").write_bytes(b"old\n")
    (env["src"] / "a.txt").write_bytes(b"new\n")
    assert ingest.cmd_register("가짜소스", env["src"], "U1") == 0
    assert (env["fam"] / "a.txt").read_bytes() == b"old\n", "원본을 덮었다 (규약 2)"
    eds = list(env["fam"].glob(f"a{store.EDITION_MARK}*.txt"))
    assert len(eds) == 1 and eds[0].read_bytes() == b"new\n"
    row = _rows(env["ledger"])[-1]
    assert row["supersedes"].replace("\\", "/").endswith("가짜계열/a.txt")
    assert "adopt" in capsys.readouterr().out


def test_계열이_둘인_소스는_거부한다(env: dict, capsys: pytest.CaptureFixture) -> None:
    """🔴 `mfds_press` 모양 — 첫 폴더에 넣으면 추출기(`…_pdf`)가 못 읽는다."""
    (env["src"] / "a.pdf").write_bytes(b"%PDF")
    assert ingest.cmd_register("두폴더", env["src"], "U1") == 1
    assert not env["raw"].exists() or not any(env["raw"].rglob("*.pdf"))
    assert not _rows(env["ledger"])
    assert "가_pdf" in capsys.readouterr().out


def test_하위_폴더는_펴지_않고_거부한다(env: dict) -> None:
    (env["src"] / "annex").mkdir()
    (env["src"] / "annex" / "b.json").write_bytes(b"{}")
    assert ingest.cmd_register("가짜소스", env["src"], "U1") == 1
    assert not _rows(env["ledger"])


def test_별칭이_없으면_복사_전에_멈춘다(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "")
    monkeypatch.setenv("DATA_ROLE", "copy")
    monkeypatch.setattr("collect.env.setting", lambda k: "" if k == "DATA_DEVICE" else "copy")
    (env["src"] / "a.txt").write_bytes(b"one\n")
    with pytest.raises(store.StoreError):
        ingest.cmd_register("가짜소스", env["src"], "U1")
    assert not env["fam"].exists() or not any(env["fam"].iterdir())


def test_mfds_press_는_실제_표에서도_거부된다() -> None:
    """실제 표 — 계열이 둘이다. 이 표가 바뀌면 위 거부 규칙을 다시 본다."""
    assert len(store.families("mfds_press")) > 1
