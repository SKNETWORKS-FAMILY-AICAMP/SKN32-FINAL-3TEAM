"""정본 원문 거울 — 팀장 기기 읽기용 (2026-09-21 · D-256 · `scripts/raw_mirror.py`).

★ 전부 **임시 폴더**다 — 가짜 정본 레포 · 가짜 사본 레포 · 가짜 거울. 진짜 `data/` · `.env` 는 안 본다.
🚨 여기서 막는 것 —
   ① G2 · 재배포 제약 · 모르는 원천의 원문이 거울로 나가는 것 (D-17 · D-71 · D-220)
   ② 키가 섞인 원문이 나가는 것 — 하나라도 있으면 하나도 안 올린다
   ③ 사본이 정본과 다른 옛 원문을 **복사해 두지 않고** 덮는 것 · 반만 받고 멈추는 것
   ④ 정본이 받거나 사본이 올리는 것 · 거울이 팀 저장소와 같은 폴더인 것 (마스킹 전 원문이 팀원에게)
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from collect import env, registry, store
from scripts import data_store as ds
from scripts import raw_inbox as ri
from scripts import raw_mirror as rm

pytestmark = pytest.mark.gate

SRC = "law_go_kr"  # 재배포 가능 · 등재된 소스 (실물 레지스트리)
G2 = "kcia_guideline"  # G2 — 실물 레지스트리


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _repo(root: pathlib.Path, files: dict[str, tuple[str, bytes]]) -> None:
    """`{경로: (원천, 바이트)}` — 디스크에 놓고 원장을 쓴다."""
    rows = []
    for rel, (sid, data) in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        rows.append({"source_id": sid, "path": rel, "sha256": _sha(data), "bytes": len(data)})
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "manifest.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _point(mp: pytest.MonkeyPatch, root: pathlib.Path, role: str) -> None:
    mp.setattr(store, "MANIFEST", root / "data" / "manifest.jsonl")
    mp.setattr(ri, "ROOT", root)
    mp.setattr(rm, "ROOT", root)
    mp.setattr(ds, "BACKUP", root.parent / f"{root.name}_backup")
    mp.setenv("DATA_ROLE", role)


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(env, "_loaded", True)
    for k in ("DATA_STORE", "RAW_INBOX", "DATA_ROLE"):
        monkeypatch.setenv(k, "")
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    monkeypatch.setenv("RAW_MIRROR", str(mirror))
    canon = tmp_path / "B"
    _repo(
        canon,
        {
            "data/raw/law/a.xml": (SRC, b"<a>new</a>"),
            "data/raw/law/b.xml": (SRC, b"<b/>"),
            f"data/raw/{G2}/g.pdf": (G2, b"%PDF g2"),
        },
    )
    return tmp_path, mirror, canon


def _publish(mp, canon) -> int:
    _point(mp, canon, "canonical")
    return rm.publish(yes=True)


def test_정본은_G2_를_빼고_올리고_목록을_쓴다(world, monkeypatch) -> None:
    _tmp, mirror, canon = world
    assert _publish(monkeypatch, canon) == 0
    idx = rm.read_index(mirror / rm.LAYOUT)
    assert [e["path"] for e in idx] == ["data/raw/law/a.xml", "data/raw/law/b.xml"]
    assert registry.is_g2(G2), "픽스처 전제 — G2 원천이어야 한다"
    objs = {p.name for p in (mirror / rm.LAYOUT / "objects").rglob("*") if p.is_file()}
    assert _sha(b"%PDF g2") not in objs, "🔴 G2 원문이 거울로 나갔다 (D-17)"


def test_키가_섞인_원문이_있으면_하나도_안_올린다(world, monkeypatch) -> None:
    _tmp, mirror, canon = world
    (canon / "data/raw/law/b.xml").write_bytes(b"<b url='x?OC=abc'/>")
    rows = [json.loads(x) for x in (canon / "data/manifest.jsonl").read_text().splitlines()]
    rows[1]["sha256"] = _sha(b"<b url='x?OC=abc'/>")
    (canon / "data/manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert _publish(monkeypatch, canon) == 1
    assert not (mirror / rm.LAYOUT / "objects").exists(), "🔴 하나라도 올라갔다"


def test_원장과_다른_디스크_원문은_안_올린다(world, monkeypatch) -> None:
    """🚨 원본이 바뀐 것(규약 2) — 거울에 퍼뜨리지 않는다."""
    _tmp, mirror, canon = world
    (canon / "data/raw/law/b.xml").write_bytes(b"<b>tampered</b>")
    assert _publish(monkeypatch, canon) == 0
    assert [e["path"] for e in rm.read_index(mirror / rm.LAYOUT)] == ["data/raw/law/a.xml"]


def test_사본은_없는_것을_받고_다른_것은_복사해_두고_바꾼다(world, monkeypatch) -> None:
    tmp, mirror, canon = world
    assert _publish(monkeypatch, canon) == 0
    a = tmp / "A"
    _repo(a, {"data/raw/law/a.xml": (SRC, b"<a>old</a>"), "data/raw/law/only_a.xml": (SRC, b"x")})
    _point(monkeypatch, a, "replica")
    assert rm.sync(yes=True) == 0
    assert (a / "data/raw/law/a.xml").read_bytes() == b"<a>new</a>"
    assert (a / "data/raw/law/b.xml").read_bytes() == b"<b/>"
    assert (a / "data/raw/law/only_a.xml").exists(), "거울에 없는 사본 원문을 지웠다"
    kept = list((tmp / "A_backup").rglob("a.xml"))
    assert kept and kept[0].read_bytes() == b"<a>old</a>", "🔴 옛 원문을 복사해 두지 않았다"
    assert not list((a / "data/raw").rglob("*.part"))
    assert rm.sync(yes=True) == 0  # 두 번째는 받을 것 없음


def test_거울_객체가_모자라면_아무것도_안_바꾼다(world, monkeypatch) -> None:
    tmp, mirror, canon = world
    assert _publish(monkeypatch, canon) == 0
    rm_obj = ri._obj(mirror / rm.LAYOUT, _sha(b"<b/>"))  # noqa: SLF001
    rm_obj.unlink()
    a = tmp / "A"
    _repo(a, {"data/raw/law/a.xml": (SRC, b"<a>old</a>")})
    _point(monkeypatch, a, "replica")
    assert rm.sync(yes=True) == 1
    assert (a / "data/raw/law/a.xml").read_bytes() == b"<a>old</a>", "🔴 반만 받았다"


def test_목록에_G2_가_끼어_있으면_사본이_받지_않는다(world, monkeypatch) -> None:
    """🔴 정본의 거름을 믿지 않고 받는 쪽에서 다시 본다 (D-220)."""
    tmp, mirror, canon = world
    assert _publish(monkeypatch, canon) == 0
    idx = mirror / rm.LAYOUT / rm.INDEX
    idx.write_text(
        idx.read_text()
        + json.dumps(
            {
                "path": f"data/raw/{G2}/g.pdf",
                "sha256": _sha(b"%PDF g2"),
                "bytes": 7,
                "source_id": G2,
            }
        )
        + "\n"
    )
    obj = ri._obj(mirror / rm.LAYOUT, _sha(b"%PDF g2"))  # noqa: SLF001 — 객체도 놓는다: 「거울에 없음」으로 멈추지 않게
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(b"%PDF g2")
    a = tmp / "A"
    _repo(a, {})
    _point(monkeypatch, a, "replica")
    assert rm.sync(yes=True) == 1
    assert not (a / "data/raw/law/a.xml").exists()
    assert not (a / f"data/raw/{G2}/g.pdf").exists(), "🔴 G2 원문을 받았다"


def test_정본은_받지_않고_사본은_올리지_않는다(world, monkeypatch) -> None:
    tmp, _mirror, canon = world
    _point(monkeypatch, canon, "canonical")
    assert rm.sync(yes=True) == 1
    _point(monkeypatch, canon, "replica")
    assert rm.publish(yes=True) == 1
    monkeypatch.setenv("DATA_ROLE", "")
    assert rm.sync(yes=True) == 1


def test_거울이_팀_저장소와_같은_폴더면_멈춘다(world, monkeypatch) -> None:
    """🔴 마스킹 전 원문이 팀원이 읽는 곳(`CopyLane_store`)에 놓인다 (D-256)."""
    _tmp, mirror, canon = world
    monkeypatch.setenv("DATA_STORE", str(mirror))
    assert _publish(monkeypatch, canon) == 1
    assert not (mirror / rm.LAYOUT).exists()


def test_거울은_내용으로_알아보고_저장소로_집지_않는다(tmp_path, monkeypatch) -> None:
    g = tmp_path / "G"
    sc = g / ds.SHORTCUT_TARGETS
    (sc / "m1" / ds.MIRROR_LAYOUT).mkdir(parents=True)
    assert ds.candidates([g], name=ds.MIRROR_NAME) == [sc / "m1"]
    assert ds.candidates([g], name=ds.STORE_NAME) == [], "거울을 저장소로 집었다"


# ══════════════════════════════════════════════════════════
# 🆕 2026-09-21 (전수 재검토) — 거울의 깨진 객체 · 받은편지함의 G2
# ══════════════════════════════════════════════════════════
def test_거울의_깨진_객체는_다시_올린다(world, monkeypatch) -> None:
    """🔴 I13 — ⛔ `is_file()` 로만 골라 0바이트 객체가 안 고쳐졌고 사본 받기가 sha 대조에서 영영 멈췄다."""
    import hashlib

    tmp, mirror, canon = world
    sha = hashlib.sha256(b"<a>new</a>").hexdigest()
    obj = mirror / rm.LAYOUT / "objects" / sha[:2] / sha
    obj.parent.mkdir(parents=True)
    obj.write_bytes(b"")
    assert _publish(monkeypatch, canon) == 0
    assert obj.read_bytes() == b"<a>new</a>"


def test_받은편지함으로_G2_를_올리지_않는다(tmp_path, monkeypatch, capsys) -> None:
    """🔴 I5 — ⛔ 재배포 제약만 따로 걸러 G2(추출 뒤 원문 삭제 · D-17)가 올라갔다. 거르는 규칙은 `_held_back` 하나다."""
    import hashlib
    import json

    from collect import env

    monkeypatch.setattr(env, "_loaded", True)
    for k in ("DATA_STORE", "RAW_MIRROR"):
        monkeypatch.setenv(k, "")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setenv("RAW_INBOX", str(inbox))
    rep = tmp_path / "M"
    _repo(rep, {f"data/raw/{G2}/g.pdf": (G2, b"%PDF g2"), "data/raw/law/a.xml": (SRC, b"<a/>")})
    led = rep / "data/manifest.jsonl"
    rows = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:
        r["device"] = "member1"
    led.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    _point(monkeypatch, rep, "replica")
    monkeypatch.setenv("DATA_DEVICE", "member1")
    assert ri.publish(yes=True) == 0
    objs = {p.name for p in (inbox / ri.LAYOUT / "objects").rglob("*") if p.is_file()}
    assert hashlib.sha256(b"%PDF g2").hexdigest() not in objs, "🔴 G2 원문이 받은편지함에 올라갔다"
    assert hashlib.sha256(b"<a/>").hexdigest() in objs, "반대 대조 — G3 은 올라간다"
    assert "g2" in capsys.readouterr().out
