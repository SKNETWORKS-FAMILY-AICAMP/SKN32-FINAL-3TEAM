"""팀원 수집 → 원문 받은편지함 → 정본 (2026-09-20 · D-250).

팀장 — *「특정 팀원이 raw 데이터 수집작업을 하게 하려면」* · *「원천을 하나하나 지정해야 되면 힘들지 않나」* ·
*「내 ohb 브랜치로 merge 후 검토한 뒤 수정 및 흡수하여 나만 main 에 pr」*.

★ 전부 **임시 폴더**에서 돈다 — 가짜 레포 · 가짜 원장 · 가짜 받은편지함. 진짜 `data/` · 진짜 `.env` 는 안 본다.
🚨 여기서 막는 것 —
   ① 팀원 PC 에 원문이 없다고 **정본에 이미 있는 것을 다시 받는 것** (원장을 본다)
   ② 원장에 누가 받았는지 안 남는 것 (기기 칸)
   ③ 두 사람이 같은 소스를 모르고 겹쳐 받는 것 (겹침 경고)
   ④ 키가 섞인 원문 · 재배포 제약 원천이 받은편지함으로 나가는 것
   ⑤ sha 가 안 맞는 바이트 · `data/raw` 밖 경로 · 정본 아닌 기기의 합치기 · 덮어쓰기
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib

import pytest
from typer.testing import CliRunner

import launcher
from collect import env, store
from scripts import data_store as ds
from scripts import raw_inbox as ri

SRC = "law_go_kr"  # 재배포 가능 · 등재된 소스 (실물 레지스트리를 쓴다)
FAM = "probe_fam"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def repo(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """가짜 레포 하나. 🚨 `.env` 를 읽지 않게 막는다 — 클론 B 의 진짜 역할·기기 이름이 끼면 안 된다."""
    root = tmp_path / "repo"
    (root / "data" / "raw").mkdir(parents=True)
    monkeypatch.setattr(env, "_loaded", True)
    for k in ("DATA_ROLE", "RAW_INBOX"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("DATA_DEVICE", "collector-1")
    monkeypatch.setattr(store, "ROOT", root)
    monkeypatch.setattr(store, "RAW", root / "data" / "raw")
    monkeypatch.setattr(store, "MANIFEST", root / "data" / "manifest.jsonl")
    monkeypatch.setattr(ri, "ROOT", root)
    return root


def _rows(root: pathlib.Path) -> list[dict]:
    p = root / "data" / "manifest.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _ledger(root: pathlib.Path, rows: list[dict]) -> None:
    p = root / "data" / "manifest.jsonl"
    p.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
        newline="\n",
    )


def _row(rel: str, data: bytes, device: str | None, at: str = "2026-09-19T00:00:00+00:00"):
    r = {
        "source_id": SRC,
        "path": rel,
        "sha256": _sha(data),
        "bytes": len(data),
        "fetched_at": at,
    }
    if device:
        r["device"] = device
    return r


def _save(payload: bytes, name: str = "page_0001.json"):
    return store.save_raw(SRC, FAM, name, payload, url="https://example.invalid/x")


# ══════════════════════════════════════════════════════════
# ① 원장을 보는 저장 · ② 기기 칸
# ══════════════════════════════════════════════════════════
@pytest.mark.gate
def test_파일이_없어도_원장에_같은_것이_있으면_받지_않는다(repo, monkeypatch) -> None:
    """🔴 팀원 PC 에는 정본의 원문이 없다 — 디스크만 보면 정본에 있는 것을 **다시 받는다**."""
    body = b'{"a":1}'
    _ledger(repo, [_row(f"data/raw/{FAM}/page_0001.json", body, None)])
    assert _save(body) is None
    assert not (repo / "data" / "raw" / FAM / "page_0001.json").exists()
    assert len(_rows(repo)) == 1, "받지 않았는데 원장이 늘었다"


@pytest.mark.gate
def test_원장과_내용이_다르면_새_판으로_둔다(repo, monkeypatch) -> None:
    """🔴 같은 경로·다른 바이트가 두 기기에 생기면 합칠 때 갈린다 — 디스크 규칙과 같게 새 판 이름으로."""
    _ledger(repo, [_row(f"data/raw/{FAM}/page_0001.json", b'{"a":1}', None)])
    got = _save(b'{"a":2}')
    assert got is not None and "__c" in got.name, got
    last = _rows(repo)[-1]
    assert last["supersedes"].replace("\\", "/") == f"data/raw/{FAM}/page_0001.json"


@pytest.mark.gate
def test_원장의_옛_판과_같아도_받지_않는다(repo) -> None:
    """판이 여럿이면 최신이 아니라 **옛 판**과 같을 수 있다 — 그래도 같은 것이다."""
    old, new = b'{"a":1}', b'{"a":2}'
    _ledger(
        repo,
        [
            _row(f"data/raw/{FAM}/page_0001.json", new, None),
            _row(f"data/raw/{FAM}/page_0001__c20260901.json", old, None),
        ],
    )
    assert _save(old) is None


@pytest.mark.gate
def test_원장에_팀원이_정한_별칭이_남는다(repo) -> None:
    _save(b'{"x":1}', "a.json")
    assert _rows(repo)[-1]["device"] == "collector-1"


@pytest.mark.gate
def test_별칭이_없으면_팀원_기기는_쓰기_전에_멈춘다(repo, monkeypatch) -> None:
    """🔴 팀장 판정 2026-09-20 — PC 이름 해시는 **대입으로 되돌려진다**(공개 원장). 별칭은 팀원이 정한다.

    🚨 파일만 놓이고 원장 행이 없는 상태를 만들지 않는다 — 쓰기 **전에** 멈춘다 (D-72).
    """
    monkeypatch.setenv("DATA_DEVICE", "")
    monkeypatch.setenv("DATA_ROLE", "replica")
    with pytest.raises(store.StoreError, match="data-setup --device"):
        _save(b'{"x":1}', "a.json")
    assert not (repo / "data" / "raw" / FAM / "a.json").exists()
    assert not (repo / "data" / "manifest.jsonl").exists()


@pytest.mark.gate
def test_정본은_별칭이_없어도_받는다(repo, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "")
    monkeypatch.setenv("DATA_ROLE", "canonical")
    _save(b'{"x":1}', "a.json")
    assert _rows(repo)[-1]["device"] == store.CANONICAL_DEVICE


@pytest.mark.gate
@pytest.mark.parametrize("bad", ["홍길동 노트북", "a b", "x" * 33])
def test_별칭_모양이_틀리면_멈춘다(repo, monkeypatch, bad) -> None:
    monkeypatch.setenv("DATA_DEVICE", bad)
    with pytest.raises(store.StoreError):
        _save(b'{"x":1}', "a.json")


@pytest.mark.gate
def test_런처_수집은_별칭이_없으면_받기_전에_멈춘다(monkeypatch) -> None:
    ran: list[tuple] = []
    monkeypatch.setattr(launcher, "run", lambda *a: ran.append(a) or 0)
    monkeypatch.setattr(env, "_loaded", True)
    monkeypatch.setenv("DATA_DEVICE", "")
    monkeypatch.setenv("DATA_ROLE", "replica")
    r = CliRunner().invoke(launcher.app, ["collect", SRC])
    assert r.exit_code == 1 and "data-setup --device" in r.output and not ran, r.output


# ══════════════════════════════════════════════════════════
# ③ 겹침 경고
# ══════════════════════════════════════════════════════════
NOW = dt.datetime(2026, 9, 20, tzinfo=dt.UTC)


@pytest.mark.gate
def test_다른_기기가_최근에_받은_소스를_알린다(repo, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "me")
    _ledger(
        repo,
        [
            _row("data/raw/f/a.json", b"1", "collector-1", "2026-09-18T00:00:00+00:00"),
            _row("data/raw/f/b.json", b"2", "me", "2026-09-19T00:00:00+00:00"),  # 나
            _row("data/raw/f/c.json", b"3", "collector-2", "2026-09-01T00:00:00+00:00"),  # 오래됨
        ],
    )
    got = store.recent_by_others(SRC, now=NOW)
    assert got == {"collector-1": "2026-09-18T00:00:00+00:00"}
    assert store.recent_by_others("mfds_press", now=NOW) == {}, "다른 소스까지 셌다"


@pytest.mark.gate
def test_기기_칸_없는_옛_행은_정본의_것이다(repo, monkeypatch) -> None:
    """09-20 이전 행은 정본만 수집했다 (D-226) — 정본에서는 조용하고, 팀원에게는 알린다."""
    _ledger(repo, [_row("data/raw/f/a.json", b"1", None, "2026-09-19T00:00:00+00:00")])
    monkeypatch.setenv("DATA_ROLE", "canonical")
    assert store.recent_by_others(SRC, now=NOW) == {}
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert list(store.recent_by_others(SRC, now=NOW)) == ["정본(기기 칸 이전)"]


@pytest.mark.gate
def test_런처_수집은_겹치면_멈추고_force_면_받는다(monkeypatch) -> None:
    ran: list[tuple] = []
    monkeypatch.setattr(launcher, "run", lambda *a: ran.append(a) or 0)
    monkeypatch.setattr(store, "recent_by_others", lambda s, **k: {"collector-1": "2026-09-19"})
    cli = CliRunner()
    r = cli.invoke(launcher.app, ["collect", SRC])
    assert r.exit_code == 1 and "collector-1" in r.output and not ran, r.output
    r = cli.invoke(launcher.app, ["collect", SRC, "--force"])
    assert r.exit_code == 0 and ran, r.output


# ══════════════════════════════════════════════════════════
# ④ 올리기 (수집 팀원)
# ══════════════════════════════════════════════════════════
@pytest.fixture
def inbox(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    box = tmp_path / ds.INBOX_NAME
    box.mkdir()
    monkeypatch.setenv("RAW_INBOX", str(box))
    return box / ri.LAYOUT


def _collected(repo: pathlib.Path, monkeypatch, body: bytes, name: str = "a.json") -> str:
    monkeypatch.setenv("DATA_DEVICE", "collector-1")
    path = _save(body, name)
    assert path is not None
    return _rows(repo)[-1]["sha256"]


@pytest.mark.gate
def test_올리기는_이_기기_디스크에_있는_원문만_올린다(repo, inbox, monkeypatch) -> None:
    """원장에 있어도 디스크에 없으면(정본·다른 팀원이 받은 것) 올리지 않는다."""
    sha = _collected(repo, monkeypatch, b'{"mine":1}')
    other = _row("data/raw/f/theirs.json", b"x", "clone-b")
    _ledger(repo, [*_rows(repo), other])
    assert ri.publish(yes=True) == 0
    objs = sorted(p.name for p in (inbox / "objects").rglob("*") if p.is_file())
    assert objs == [sha]


@pytest.mark.gate
def test_키가_섞인_원문은_하나도_안_올린다(repo, inbox, monkeypatch) -> None:
    """🔴 법제처 목록 응답은 `OC=<키>` 를 되비춘다 (2026-09-18 실측). 🚨 오류에 값을 찍지 않는다."""
    _collected(repo, monkeypatch, b'{"ok":1}', "a.json")
    _collected(repo, monkeypatch, b'{"link":"https://x/DRF?OC=abcdef123&type=XML"}', "b.json")
    assert ri.publish(yes=True) == 1
    assert not (inbox / "objects").exists(), "한 파일이라도 올라갔다"


@pytest.mark.gate
def test_재배포_제약_원천은_올리지_않는다(repo, inbox, monkeypatch) -> None:
    """🚨 AI Hub 등 — 약관상 팀원 사이 전달을 모른다 (D-71). 걸러 내고 나머지는 올린다."""
    _collected(repo, monkeypatch, b'{"a":1}')
    monkeypatch.setattr(ri, "_noredist", lambda s: True)
    assert ri.publish(yes=True) == 0
    assert not (inbox / "objects").exists()


@pytest.mark.gate
def test_받은편지함이_없으면_멈춘다(repo, monkeypatch) -> None:
    _collected(repo, monkeypatch, b'{"a":1}')
    assert ri.publish(yes=True) == 1


@pytest.mark.gate
def test_별칭이_바뀌어도_안_올린_원문을_올린다(repo, inbox, monkeypatch) -> None:
    """🔴 팀장 — *「.env 가 바뀌거나 새로 만들면 …」* · 올릴 대상은 기기 이름이 아니라 디스크로 고른다."""
    sha = _collected(repo, monkeypatch, b'{"a":1}')
    monkeypatch.setenv("DATA_DEVICE", "collector-9")
    assert ri.publish(yes=True) == 0
    assert (inbox / "objects" / sha[:2] / sha).is_file()


@pytest.mark.gate
def test_원장과_바이트가_다른_원문은_하나도_안_올린다(repo, inbox, monkeypatch) -> None:
    """받은 뒤 고친 파일이 원장의 sha 이름으로 올라가면 정본이 합칠 때 멈춘다 — 올리기 전에 막는다."""
    _collected(repo, monkeypatch, b'{"a":1}', "a.json")
    _collected(repo, monkeypatch, b'{"b":1}', "b.json")
    (repo / _rows(repo)[-1]["path"]).write_bytes(b'{"b":2}')
    assert ri.publish(yes=True) == 1
    assert not (inbox / "objects").exists()


@pytest.mark.gate
def test_정본은_원문을_올리지_않는다(repo, inbox, monkeypatch) -> None:
    _collected(repo, monkeypatch, b'{"a":1}')
    monkeypatch.setenv("DATA_ROLE", "canonical")
    assert ri.publish(yes=True) == 1
    assert not (inbox / "objects").exists()


# ══════════════════════════════════════════════════════════
# ⑤ 합치기 (정본)
# ══════════════════════════════════════════════════════════
def _uploaded(repo, inbox, monkeypatch, body: bytes) -> dict:
    """팀원 기기에서 받고 올린 뒤, 정본 기기로 옮겨 온 것처럼 — 원장만 남기고 파일은 지운다."""
    _collected(repo, monkeypatch, body)
    assert ri.publish(yes=True) == 0
    row = _rows(repo)[-1]
    (repo / row["path"]).unlink()
    monkeypatch.setenv("DATA_DEVICE", "clone-b")
    monkeypatch.setenv("DATA_ROLE", "canonical")
    return row


@pytest.mark.gate
def test_정본은_sha_가_맞는_원문을_제자리에_놓는다(repo, inbox, monkeypatch) -> None:
    body = b'{"a":1}'
    row = _uploaded(repo, inbox, monkeypatch, body)
    assert ri.import_(yes=True) == 0
    assert (repo / row["path"]).read_bytes() == body
    assert ri.import_(yes=True) == 0, "두 번째는 할 일이 없어야 한다"


@pytest.mark.gate
def test_정본이_아니면_합치지_않는다(repo, inbox, monkeypatch) -> None:
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ri.import_(yes=True) == 1
    assert not (repo / row["path"]).exists()


@pytest.mark.gate
def test_sha_가_안_맞으면_하나도_놓지_않는다(repo, inbox, monkeypatch) -> None:
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    obj = inbox / "objects" / row["sha256"][:2] / row["sha256"]
    obj.write_bytes(b'{"a":"tampered"}')
    assert ri.import_(yes=True) == 1
    assert not (repo / row["path"]).exists()


@pytest.mark.gate
def test_원장이_data_raw_밖을_가리키면_멈춘다(repo, inbox, monkeypatch) -> None:
    monkeypatch.setenv("DATA_ROLE", "canonical")
    monkeypatch.setenv("DATA_DEVICE", "clone-b")
    for bad in ("data/raw/../../evil.txt", "app/settings.py"):
        _ledger(repo, [_row(bad, b"x", "collector-1")])
        assert ri.import_(yes=True) == 1
    assert not (repo.parent / "evil.txt").exists()


@pytest.mark.gate
def test_병합_전_검사는_브랜치_원장으로_보고_아무것도_놓지_않는다(repo, inbox, monkeypatch) -> None:
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    branch_rows = _rows(repo)
    _ledger(repo, [])  # 정본의 원장에는 아직 없다 — 병합 전이다
    monkeypatch.setattr(ri, "_branch_ledger", lambda b: branch_rows)
    monkeypatch.setenv("DATA_ROLE", "replica")  # 검사는 역할을 안 묻는다
    assert ri.import_(branch="origin/collector") == 0
    assert not (repo / row["path"]).exists(), "검사가 파일을 놓았다"
    (inbox / "objects" / row["sha256"][:2] / row["sha256"]).unlink()
    assert ri.import_(branch="origin/collector") == 1, "받은편지함에 없는데 통과했다"


@pytest.mark.gate
def test_브랜치_이름에_명령을_섞지_못한다() -> None:
    with pytest.raises(ri.InboxError):
        ri._branch_ledger("x; rm -rf /")  # noqa: SLF001


# ══════════════════════════════════════════════════════════
# data-setup — 받은편지함 · 기기 이름
# ══════════════════════════════════════════════════════════
def _env_file(tmp: pathlib.Path, mp: pytest.MonkeyPatch) -> pathlib.Path:
    from collect import setkey

    p = tmp / "dotenv"
    p.write_text("", encoding="utf-8", newline="\n")
    mp.setattr(setkey, "ENV_PATH", p)
    for k in ("DATA_ROLE", "DATA_STORE", "RAW_INBOX", "DATA_DEVICE"):
        mp.setenv(k, "")
    return p


@pytest.mark.gate
def test_설정이_받은편지함을_찾고_기기_이름을_적는다(tmp_path, monkeypatch) -> None:
    store_dir = tmp_path / ds.STORE_NAME
    box = tmp_path / ds.INBOX_NAME
    store_dir.mkdir()
    box.mkdir()
    p = _env_file(tmp_path, monkeypatch)
    monkeypatch.setattr(ds, "candidates", lambda roots=None, name=ds.STORE_NAME: [tmp_path / name])
    assert ds.setup(role="replica", yes=True, device="collector-1") == 0
    text = p.read_text(encoding="utf-8")
    assert f"RAW_INBOX={box}" in text and "DATA_DEVICE=collector-1" in text, text


@pytest.mark.gate
def test_기기_이름에_공백_한글은_안_받는다(tmp_path, monkeypatch) -> None:
    """🚨 원장은 공개 저장소다 — 실명을 막을 수는 없지만 「오한빈 노트북」 같은 꼴은 거른다."""
    p = _env_file(tmp_path, monkeypatch)
    (tmp_path / ds.STORE_NAME).mkdir()
    before = p.read_bytes()
    assert (
        ds.setup(role="replica", store=str(tmp_path / ds.STORE_NAME), yes=True, device="홍길동 PC")
        == 1
    )
    assert p.read_bytes() == before
