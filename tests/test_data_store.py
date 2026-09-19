"""공유 저장소로 파생물을 옮기는 길 (2026-09-19 · D-247 · 검토 2026-09-19 §5).

팀장 요구 — *「런처로 클론 A 나 팀원이 실행하면 부족한 데이터(파생물 등)를 자동으로 받아서
동등성을 유지하고 싶다.」*

★ 전부 **임시 폴더**에서 돈다 — 가짜 레포(정본 · 사본)와 가짜 저장소를 만들고 올리고 받는다.
  진짜 `data/` 와 진짜 저장소는 건드리지 않는다. 네트워크도 없다.
🚨 여기서 막는 것 —
   ① 원문캐시(마스킹 전 원문)가 저장소로 나가는 것 (D-17 · D-244)
   ② 저장소에 없거나 **sha 가 안 맞는** 바이트가 파생물 자리에 놓이는 것 (D-220)
   ③ 정본이 받는 것 · 사본이 올리는 것 (D-226)
   ④ 재배포 제약 소스를 받은 기기에서 올리는 것 (D-78 ③ · D-71)
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from collect import store
from scripts import data_store as ds
from scripts import derived_manifest as dm

GEN = "golden/golden.jsonl"  # 생성물
CACHE = "mfds_press_pdf/tables/x.json"  # 원문캐시
LABEL = "labels/누군가.jsonl"  # 원천 — git 이 옮긴다


def _repo(root: pathlib.Path, files: dict[str, bytes]) -> pathlib.Path:
    for rel, data in files.items():
        p = root / "data" / "derived" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def _point(mp: pytest.MonkeyPatch, root: pathlib.Path) -> None:
    """모듈들이 가짜 레포를 보게 한다. 🚨 「만든 모듈」 탐색은 가짜 레포에 코드가 없으므로 흉내 낸다."""
    mp.setattr(dm, "ROOT", root)
    mp.setattr(dm, "DERIVED", root / "data" / "derived")
    mp.setattr(dm, "OUT", root / "data" / "derived_manifest.jsonl")
    mp.setattr(dm, "writers", lambda: dm.Table())
    mp.setattr(dm, "match_writers", lambda rel, table: {"가짜.모듈"})
    mp.setattr(ds, "ROOT", root)
    mp.setattr(ds, "BACKUP", root.parent / f"{root.name}_backup")
    mp.setattr(ds, "RAW_MARK", root / "원문_없음")  # 가짜 레포에는 원문 폴더가 없다


def _write_manifest() -> None:
    dm.OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in dm.rows()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """정본 하나 · 가짜 저장소 하나. 수집 원장은 비워 둔다(재배포 제약 없음)."""
    storage = tmp_path / "store"
    storage.mkdir()
    ledger = tmp_path / "manifest.jsonl"
    ledger.write_text("", encoding="utf-8", newline="\n")
    monkeypatch.setattr(store, "MANIFEST", ledger)
    monkeypatch.setenv("DATA_STORE", str(storage))
    canon = _repo(
        tmp_path / "B",
        {GEN: b'{"text":"v2"}\n', CACHE: b'{"t":"(\xec\xa3\xbc)'},  # 캐시 내용은 무엇이든
    )
    _repo(canon, {LABEL: b'{"l":1}\n'})
    _point(monkeypatch, canon)
    _write_manifest()
    return tmp_path, storage, canon


def _publish(mp: pytest.MonkeyPatch) -> int:
    mp.setenv("DATA_ROLE", "canonical")
    return ds.publish(yes=True)


@pytest.mark.gate
def test_올리는_것은_생성물뿐이다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 원문캐시는 마스킹 전 원문이다 — 제3자 계정에 나가면 안 된다 (D-17 · D-78 ③)."""
    _tmp, storage, canon = world
    assert _publish(monkeypatch) == 0
    objs = {p.name for p in (storage / ds.LAYOUT / "objects").rglob("*") if p.is_file()}
    gen_sha = hashlib.sha256((canon / "data" / "derived" / GEN).read_bytes()).hexdigest()
    cache_sha = hashlib.sha256((canon / "data" / "derived" / CACHE).read_bytes()).hexdigest()
    assert objs == {gen_sha}, f"생성물 하나만 올라가야 한다: {objs}"
    assert cache_sha not in objs
    log = (storage / ds.LAYOUT / "publish_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(log[-1])["objects_new"] == 1


@pytest.mark.gate
def test_사본은_부족분만_받고_옛판은_백업한다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """★ 팀장 요구 그 자체 — 옛 판을 든 클론 A 가 받으면 정본과 같아진다. 옛 것은 레포 밖에 남는다."""
    tmp, _storage, canon = world
    assert _publish(monkeypatch) == 0
    manifest = dm.OUT.read_bytes()

    # 클론 A — git 이 원장과 라벨을 옮겼고, 생성물은 옛 판이고, 원문캐시는 없다
    a = _repo(tmp / "A", {GEN: b'{"text":"v1"}\n', LABEL: b'{"l":1}\n'})
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")

    assert [r["경로"] for r in ds.plan()] == [f"data/derived/{GEN}"]
    assert ds.sync(yes=True) == 0
    assert (a / "data" / "derived" / GEN).read_bytes() == (
        canon / "data" / "derived" / GEN
    ).read_bytes()
    assert not (a / "data" / "derived" / CACHE).exists(), "원문캐시를 받으면 안 된다"
    backups = list((tmp / "A_backup").rglob("golden.jsonl"))
    assert backups and backups[0].read_bytes() == b'{"text":"v1"}\n', "옛 판이 백업되지 않았다"
    assert not dm.failed("replica", dm.diff("replica")), "받은 뒤에도 사본 --check 가 빨강이다"


@pytest.mark.gate
def test_저장소에_없으면_아무것도_받지_않는다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 반만 받으면 파생물이 두 판으로 섞인다 — 전부 있을 때만 받는다."""
    tmp, _storage, _canon = world  # publish 를 안 했다
    manifest = dm.OUT.read_bytes()
    a = _repo(tmp / "A", {GEN: b"old\n", LABEL: b'{"l":1}\n'})
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ds.sync(yes=True) == 1
    assert (a / "data" / "derived" / GEN).read_bytes() == b"old\n"


@pytest.mark.gate
def test_받은_바이트가_원장과_다르면_놓지_않는다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 동기화가 덜 끝났거나 저장소가 오염됐을 때 — sha 가 안 맞으면 제자리에 두지 않는다 (D-220)."""
    tmp, storage, _canon = world
    assert _publish(monkeypatch) == 0
    for obj in (storage / ds.LAYOUT / "objects").rglob("*"):
        if obj.is_file():
            obj.write_bytes(b"corrupted")
    manifest = dm.OUT.read_bytes()
    a = _repo(tmp / "A", {LABEL: b'{"l":1}\n'})
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ds.sync(yes=True) == 1
    assert not (a / "data" / "derived" / GEN).exists()
    assert not list((a / "data" / "derived").rglob("*.part")), "반쯤 쓴 파일이 남았다"


@pytest.mark.gate
def test_정본은_받지_않고_사본은_올리지_않는다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 정본이 받으면 방금 만든 것이 옛 판으로 돌아간다 · 사본이 올리면 파생물 출처가 둘이 된다 (D-226)."""
    monkeypatch.setenv("DATA_ROLE", "canonical")
    assert ds.sync(yes=True) == 1
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ds.publish(yes=True) == 1
    monkeypatch.delenv("DATA_ROLE")
    assert ds.sync(yes=True) == 1
    assert ds.ensure() == 0, "역할이 없으면(CI) 데이터 명령을 막지 않는다"


@pytest.mark.gate
def test_재배포_제약_소스를_받은_기기는_올리지_않는다(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 AI Hub 를 받는 순간 파생물 어딘가에 그 행이 섞였을 수 있다 (D-71 · 동등성 문서 §2)."""
    store.MANIFEST.write_text(
        json.dumps({"source_id": "aihub_558", "path": "x"}) + "\n", encoding="utf-8", newline="\n"
    )
    assert _publish(monkeypatch) == 1


def test_마스킹_잔여가_있으면_올리지_않는다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """법인 표기가 남은 생성물은 올리지 않는다 (D-17). 🚨 거름망이지 증명이 아니다 — 개인 이름은 못 잡는다."""
    _tmp, _storage, canon = world
    _repo(canon, {"leak.jsonl": '{"t":"가나다라㈜ 광고"}\n'.encode()})
    _write_manifest()
    assert _publish(monkeypatch) == 1
