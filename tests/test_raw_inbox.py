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
def test_이_기기가_받았는데_없는_원문은_되살린다(repo) -> None:
    """🔴 2026-09-21 (소성민 코드 리뷰 #3) — ⛔ 종전에는 원장에 같은 sha 가 있으면 **누가 받았든** 건너뛰어,
    이 기기가 받은 원문을 잃으면 다시 수집해도 조용히 안 돌아왔다. doctor 의 `lost` 안내(「이 기기에서 다시 받는다」)와
    모순이었다. ★ `lost` 와 같은 조건 — 기기 칸이 **이 기기**일 때만 되살린다."""
    body = b'{"a":1}'
    rel = f"data/raw/{FAM}/page_0001.json"
    _ledger(repo, [_row(rel, body, "collector-1")])
    got = _save(body)
    assert got is not None and (repo / rel).read_bytes() == body, "🔴 잃은 원문이 안 돌아왔다"
    assert len(_rows(repo)) == 1, "같은 바이트면 원장 행을 또 적지 않는다"


@pytest.mark.gate
def test_되살린_판은_그_판의_경로로_돌아간다(repo) -> None:
    """판(`__c날짜`)으로 받았던 것을 잃으면 **그 판 이름**으로 돌아가야 한다 — 원본 이름에 쓰면 판이 섞인다."""
    old, new = b'{"a":1}', b'{"a":2}'
    base, ed = f"data/raw/{FAM}/page_0001.json", f"data/raw/{FAM}/page_0001__c20260901.json"
    _ledger(repo, [_row(base, new, "other-2"), _row(ed, old, "collector-1")])
    got = _save(old)
    assert got is not None and got.name == "page_0001__c20260901.json", got
    assert not (repo / base).exists()


@pytest.mark.gate
def test_다른_기기나_옛_행이면_되살리지_않는다(repo) -> None:
    """🚨 반대 대조 — 다른 기기 것은 그 기기(정본)에 있다(D-250). 기기 칸 없는 옛 행은 누구 것인지 모른다(`legacy`)."""
    body = b'{"a":1}'
    rel = f"data/raw/{FAM}/page_0001.json"
    for who in ("other-2", None):
        _ledger(repo, [_row(rel, body, who)])
        store._INDEX = None  # noqa: SLF001 — 원장을 바꿔 끼웠다
        assert _save(body) is None, who
        assert not (repo / rel).exists(), who


@pytest.mark.gate
def test_G2_는_이_기기_것이어도_되살리지_않는다(repo, monkeypatch) -> None:
    """🚨 G2 는 사실을 뽑은 뒤 원문을 **일부러** 지운다(D-92) — doctor 도 `g2` 를 정상으로 가른다.
    되살리면 평소 수집 한 번에 지운 원문이 전부 돌아온다."""
    monkeypatch.setattr(store.registry, "is_g2", lambda sid: True)
    body = b'{"a":1}'
    rel = f"data/raw/{FAM}/page_0001.json"
    _ledger(repo, [_row(rel, body, "collector-1")])
    assert _save(body) is None
    assert not (repo / rel).exists()


@pytest.mark.gate
def test_바뀐_원천을_다시_받아도_같은_판을_또_만들지_않는다(repo, monkeypatch) -> None:
    """🔴 2026-09-21 (전수 재검토 I6) — ⛔ 디스크 갈래가 **오늘 판만** 봐서, 한 번 바뀐 원천은 수집할 때마다
    날짜만 다른 같은 판이 생겼다(`__c0907`·`__c0908`·`__c0909` 바이트 동일). 읽는 쪽은 판이 있으면 멈춘다."""
    monkeypatch.setattr(store, "_today", lambda: "20260907")
    _save(b'{"a":1}')
    assert _save(b'{"a":2}').name == "page_0001__c20260907.json"
    monkeypatch.setattr(store, "_today", lambda: "20260908")
    assert _save(b'{"a":2}') is None, "🔴 같은 것을 새 판으로 또 썼다"
    assert sorted(p.name for p in (repo / "data" / "raw" / FAM).iterdir()) == [
        "page_0001.json",
        "page_0001__c20260907.json",
    ]


@pytest.mark.gate
def test_채택한_뒤_잃으면_원본_이름으로_되살린다(repo) -> None:
    """🔴 전수 재검토 I7 — ⛔ `adopt` 로 치운 옛 판 이름을 되살렸다(색인 순서). 원본 이름이 먼저다."""
    body = b'{"a":2}'
    base, ed = f"data/raw/{FAM}/page_0001.json", f"data/raw/{FAM}/page_0001__c20260907.json"
    _ledger(
        repo,
        [
            _row(base, b'{"a":1}', "collector-1"),
            _row(ed, body, "collector-1", at="2026-09-07T00:00:00+00:00"),
            _row(base, body, "collector-1", at="2026-09-08T00:00:00+00:00"),  # adopt 가 붙인 행
        ],
    )
    got = _save(body)
    assert got is not None and got.name == "page_0001.json", got


@pytest.mark.gate
def test_되살릴_자리에_다른_바이트가_있으면_덮지_않는다(repo, monkeypatch) -> None:
    """🚨 규약 2 — 원장과 다른 파일이 그 자리에 있으면 되살리지 않고 새 판으로 둔다."""
    monkeypatch.setattr(store, "_today", lambda: "20260909")
    rel = f"data/raw/{FAM}/page_0001.json"
    _ledger(repo, [_row(rel, b'{"a":1}', "collector-1")])
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_bytes(b'{"local":1}')
    got = _save(b'{"a":1}')
    assert (repo / rel).read_bytes() == b'{"local":1}', "🔴 덮어썼다"
    assert got is not None and got.name == "page_0001__c20260909.json", got


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
def test_팀원_기기는_예약어_canonical_을_별칭으로_못_쓴다(repo, monkeypatch) -> None:
    """🔴 2026-09-21 — `.env` 에 손으로 `DATA_DEVICE=canonical` 을 적으면 원장에 `canonical` 로 남고,
    `raw-publish` 는 그 행을 「정본에 이미 있다」로 건너뛴다 — **받은 원문이 정본에 안 간다.**
    ⛔ 종전에는 `data-setup` 만 막았다. 쓰기 **전에** 멈추는지까지 본다 (D-72).
    """
    monkeypatch.setenv("DATA_DEVICE", store.CANONICAL_DEVICE)
    monkeypatch.setenv("DATA_ROLE", "replica")
    with pytest.raises(store.StoreError, match="예약어"):
        _save(b'{"x":1}', "a.json")
    assert not (repo / "data" / "raw" / FAM / "a.json").exists()
    # 반대 대조 — 정본은 같은 이름을 적어도 받는다 (별칭 없이 받을 때 적는 이름과 같다)
    monkeypatch.setenv("DATA_ROLE", "canonical")
    _save(b'{"x":1}', "a.json")
    assert _rows(repo)[-1]["device"] == store.CANONICAL_DEVICE


def test_별칭_판정은_한_곳이다() -> None:
    """🚨 `device_id` · `data_store.setup` · `doctor` 가 같은 함수를 부른다 (D-99) — 소스로 본다."""
    import inspect

    from scripts import doctor

    for fn in (store.device_id, ds.setup, doctor._check_data_env):
        src = inspect.getsource(fn)
        assert "device_problem(" in src, f"🔴 {fn.__qualname__} 가 별칭 판정을 따로 한다"
        assert "DEVICE_RE.fullmatch" not in src, f"🔴 {fn.__qualname__} 가 모양을 따로 잰다"


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
# ③-2 한 사람 · 두 기기 — 별칭은 **기기마다** 하나 (2026-09-22)
# ══════════════════════════════════════════════════════════
#  팀장 — *「수집작업을 하는 팀원도 여러 기기를 쓰는데 여러 계정을 써야 하나」* → 계정은 사람 하나에 하나,
#  별칭(`DATA_DEVICE`)은 기기 하나에 하나. 🚨 같은 별칭을 두 기기에 쓰면 원장만으로는 두 기기를 못 가른다 —
#  `5b8cece`(코드 리뷰 #3 · 「이 기기가 받았는데 없으면 되살린다」) 뒤로는 **서로의 원문을 유실로 보고 다시 받는다.**
#  D-250 「⬜ 고치지 못하는 것」의 별칭 줄이 이 두 테스트를 가리킨다.


def _second_device(
    tmp_path: pathlib.Path, monkeypatch, repo: pathlib.Path, alias: str
) -> pathlib.Path:
    """같은 사람의 두 번째 기기 — 원장만 pull 로 받았고(원문은 git 으로 안 온다 · D-19) 디스크는 비었다."""
    other = tmp_path / "second"
    (other / "data" / "raw").mkdir(parents=True)
    (other / "data" / "manifest.jsonl").write_bytes((repo / "data" / "manifest.jsonl").read_bytes())
    monkeypatch.setattr(store, "ROOT", other)
    monkeypatch.setattr(store, "RAW", other / "data" / "raw")
    monkeypatch.setattr(store, "MANIFEST", other / "data" / "manifest.jsonl")
    monkeypatch.setattr(ri, "ROOT", other)
    monkeypatch.setenv("DATA_DEVICE", alias)
    return other


def _seen_on(root: pathlib.Path, alias: str) -> dict[str, str]:
    from collect import missing  # noqa: PLC0415

    got = missing.classify(_rows(root), root=root, me=alias, grade_of=lambda s: "G3", rules={})
    return {pathlib.PurePosixPath(p).name: why for p, (why, _) in got.items()}


@pytest.mark.gate
def test_한_사람이_두_기기를_쓰면_별칭도_둘이고_서로의_원문을_다시_받지_않는다(
    repo, tmp_path, monkeypatch
) -> None:
    """🔴 별칭이 다르면 두 번째 기기는 첫 기기가 받은 것을 **다른 기기 것**으로 보고 건너뛰며, 겹침을 알린다."""
    assert _save(b'{"v":1}', "p1.json") is not None  # 첫 기기 — `collector-1`
    at = dt.datetime.fromisoformat(_rows(repo)[-1]["fetched_at"])
    other = _second_device(tmp_path, monkeypatch, repo, "collector-1b")
    target = other / "data" / "raw" / FAM / "p1.json"

    assert store.already_have(target), "첫 기기가 받은 것을 다시 부른다"
    assert list(store.recent_by_others(SRC, now=at)) == ["collector-1"], "겹침 경고가 안 뜬다"
    assert _seen_on(other, "collector-1b") == {"p1.json": "other"}, "첫 기기 것을 유실로 본다"
    assert _save(b'{"v":1}', "p1.json") is None, "같은 원문을 두 번째 기기에 또 저장했다"
    assert not target.exists() and len(_rows(other)) == 1
    assert ri._mine(_rows(other))[0] == [], "두 번째 기기가 남의 원문을 올릴 후보로 셌다"


@pytest.mark.gate
def test_같은_별칭을_두_기기에_쓰면_서로의_원문을_유실로_보고_다시_받는다(
    repo, tmp_path, monkeypatch
) -> None:
    """반대 대조 — 위 테스트가 **별칭 때문에** 통과한다는 것을 보인다. 🚨 이 동작을 고치려는 테스트가 아니다 —
    원장이 두 기기를 가를 칸은 별칭뿐이다. 막는 것은 사람의 약속(기기마다 별칭 하나 · README)이다."""
    assert _save(b'{"v":1}', "p1.json") is not None
    at = dt.datetime.fromisoformat(_rows(repo)[-1]["fetched_at"])
    other = _second_device(tmp_path, monkeypatch, repo, "collector-1")  # 🚨 같은 별칭
    target = other / "data" / "raw" / FAM / "p1.json"

    assert not store.already_have(target)
    assert store.recent_by_others(SRC, now=at) == {}, "같은 별칭인데 겹침을 알렸다"
    assert _seen_on(other, "collector-1") == {"p1.json": "lost"}
    assert _save(b'{"v":1}', "p1.json") is not None and target.exists(), "되살리기가 안 돌았다"


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
def test_받은편지함_사본에_확장자가_붙어도_sha_가_맞으면_놓는다(repo, inbox, monkeypatch) -> None:
    """🆕 2026-09-25 — 팀원 PDF 25개가 받은편지함에 `<sha>.pdf` 로 있었다(사실원장 ⑲). 이름이 아니라 sha 로 찾는다."""
    body = b"%PDF-1.4 probe"
    row = _uploaded(repo, inbox, monkeypatch, body)
    obj = inbox / "objects" / row["sha256"][:2] / row["sha256"]
    obj.rename(obj.with_name(obj.name + ".pdf"))
    assert ri.import_(yes=True) == 0
    assert (repo / row["path"]).read_bytes() == body


@pytest.mark.gate
def test_확장자가_붙은_사본도_sha_가_안_맞으면_하나도_놓지_않는다(repo, inbox, monkeypatch) -> None:
    """확장자를 받아 준다고 느슨해지지 않는다 — 바이트가 원장 sha 와 다르면 「없음」이다 (D-220)."""
    row = _uploaded(repo, inbox, monkeypatch, b"%PDF-1.4 probe")
    obj = inbox / "objects" / row["sha256"][:2] / row["sha256"]
    obj.unlink()
    obj.with_name(obj.name + ".pdf").write_bytes(b"%PDF-1.4 tampered")
    assert ri.import_(yes=True) == 1
    assert not (repo / row["path"]).exists()


@pytest.mark.gate
def test_확장자가_붙은_사본이_있으면_다시_올리지_않는다(repo, inbox, monkeypatch) -> None:
    """팀원이 다시 `raw-publish` 해도 같은 바이트를 또 올리지 않는다 — 읽는 자리와 올릴지 보는 자리가 같다 (D-99)."""
    _collected(repo, monkeypatch, b"%PDF-1.4 probe", "a.pdf")
    assert ri.publish(yes=True) == 0
    sha = _rows(repo)[-1]["sha256"]
    obj = inbox / "objects" / sha[:2] / sha
    obj.rename(obj.with_name(obj.name + ".pdf"))
    assert ri.publish(yes=True) == 0
    assert not obj.exists(), "확장자 붙은 사본이 있는데 확장자 없는 사본을 또 올렸다"


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
    monkeypatch.setattr(ri, "_base_ledger", lambda b: [])  # 🆕 D-254 — 빈 원장에서 갈라졌다
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


# ══════════════════════════════════════════════════════════
# 🆕 받는 쪽 점검 (2026-09-20) — `raw-import` 를 잊으면 만들기 전에 멈춘다
# ══════════════════════════════════════════════════════════
@pytest.mark.gate
def test_합치지_않은_팀원_원문이_있으면_정본의_추출과_올리기가_멈춘다(
    repo, inbox, monkeypatch
) -> None:
    """🔴 원장은 git 병합으로, 원문은 `raw-import` 로 따로 온다 — 그 사이 추출하면 **경고 없이** 빠진다."""
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')  # 정본 · 원장만 병합된 상태
    assert [r["path"] for r in ri.pending()] == [row["path"]]
    assert ri.check_pending() == 1
    assert ds.publish(yes=True) == 1, "합치지 않은 원문이 있는데 파생물을 올렸다"
    assert ri.import_(yes=True) == 0
    assert ri.pending() == [] and ri.check_pending() == 0


@pytest.mark.gate
def test_사본과_G2_는_합치지_않은_원문으로_세지_않는다(repo, inbox, monkeypatch) -> None:
    """사본은 원문이 없는 것이 정상(D-19) · G2 는 추출 뒤 지운다(D-92) — 세면 영영 멈춘다."""
    _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    monkeypatch.setattr(ri, "_noredist", lambda s: False)
    from collect import registry

    monkeypatch.setattr(registry, "is_g2", lambda s: True)
    assert ri.pending() == []
    monkeypatch.setattr(registry, "is_g2", lambda s: False)
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ri.pending() == []


@pytest.mark.gate
def test_런처_추출은_합치지_않은_원문이_있으면_멈춘다(monkeypatch) -> None:
    calls: list[tuple] = []

    def fake_run(*a):
        calls.append(a)
        return 1 if "pending" in a else 0

    monkeypatch.setattr(launcher, "run", fake_run)
    r = CliRunner().invoke(launcher.app, ["extract"])
    assert r.exit_code == 1, r.output
    assert len(calls) == 1 and "pending" in calls[0], calls


@pytest.mark.gate
def test_Mac_의_Drive_위치에서도_저장소를_찾는다(tmp_path) -> None:
    """🆕 Mac 의 Drive for desktop 은 `~/Library/CloudStorage/GoogleDrive-<계정>/` 아래에 붙는다."""
    home = tmp_path / "home"
    want = home / "Library" / "CloudStorage" / "GoogleDrive-team@x" / "My Drive" / ds.STORE_NAME
    want.mkdir(parents=True)
    assert ds.candidates(ds.default_roots(home)) == [want]


# ══════════════════════════════════════════════════════════
# 🆕 D-254 — 런처 전수 감사 (2026-09-20) 에서 나온 결함
# ══════════════════════════════════════════════════════════
def _canonical(monkeypatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "clone-b")
    monkeypatch.setenv("DATA_ROLE", "canonical")


@pytest.mark.gate
def test_채택한_팀원_판은_합치지_않은_원문으로_세지_않는다(repo, inbox, monkeypatch) -> None:
    """🔴 §1-1 — 팀원 판(`__c`)을 정본이 `adopt` 로 원래 이름으로 옮기면 판 경로가 사라진다.

    ⛔ 종전: `pending` 이 영영 1 → extract·data-publish 가 막히고, `raw-import` 가 판을 다시 놓는다 → 또 adopt …
    ★ `collect.missing.classify` 가 `moved`(같은 sha 가 디스크의 다른 경로에) 로 가른다 (D-253 · D-99).
    """
    _canonical(monkeypatch)
    body = b'{"a":2}'
    ed = f"data/raw/{FAM}/page_0001__c20260919.json"
    base = f"data/raw/{FAM}/page_0001.json"
    # 팀원이 받은 판 → raw-import 로 놓임 → 정본이 adopt: 판 이름이 원래 이름으로 바뀌고 원장에 새 줄
    (repo / base).parent.mkdir(parents=True, exist_ok=True)
    (repo / base).write_bytes(body)
    _ledger(repo, [_row(ed, body, "collector-1"), _row(base, body, "clone-b")])
    obj = inbox / "objects" / _sha(body)[:2] / _sha(body)
    obj.parent.mkdir(parents=True)
    obj.write_bytes(body)  # 받은편지함에 판이 그대로 있어도
    assert ri.pending() == [], "채택한 판을 합치지 않은 원문으로 셌다 — extract 가 영영 막힌다"
    assert ri.check_pending() == 0
    assert ri.import_(yes=True) == 0
    assert not (repo / ed).exists(), (
        "채택한 판을 raw-import 가 되살렸다 — 추출기가 판 때문에 멈춘다"
    )


@pytest.mark.gate
def test_크기가_다르면_옮겨진_것으로_보지_않는다(repo, inbox, monkeypatch) -> None:
    """`moved` 는 크기까지 맞아야 한다 — 같은 sha 라고 적힌 자리의 파일이 다르면 여전히 합칠 후보다."""
    _canonical(monkeypatch)
    body = b'{"a":2}'
    ed = f"data/raw/{FAM}/page_0001__c20260919.json"
    base = f"data/raw/{FAM}/page_0001.json"
    (repo / base).parent.mkdir(parents=True, exist_ok=True)
    (repo / base).write_bytes(body + b" ")
    _ledger(repo, [_row(ed, body, "collector-1"), _row(base, body, "clone-b")])
    assert [r["path"] for r in ri.pending()] == [ed]


@pytest.mark.gate
@pytest.mark.parametrize("why", ["g2", "noredist"])
def test_합치기는_pending_과_같은_거름을_쓴다(repo, inbox, monkeypatch, why) -> None:
    """🔴 §1-4 ① — G2·재배포 제약은 `pending` 이 안 센다. `import_` 가 따로 굴면 G2 를 되살리거나 전체를 거부했다."""
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    (inbox / "objects" / row["sha256"][:2] / row["sha256"]).unlink()  # 받은편지함에 없다
    from collect import registry

    monkeypatch.setattr(registry, "is_g2", lambda s: why == "g2")
    monkeypatch.setattr(ri, "_noredist", lambda s: why == "noredist")
    assert ri.pending() == []
    assert ri.import_(yes=True) == 0, "pending 이 안 세는 것을 합치기가 「없음」으로 전체 거부했다"
    assert not (repo / row["path"]).exists()


@pytest.mark.gate
def test_G2_는_받은편지함에_있어도_되살리지_않는다(repo, inbox, monkeypatch) -> None:
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    from collect import registry

    monkeypatch.setattr(registry, "is_g2", lambda s: True)
    assert ri.import_(yes=True) == 0
    assert not (repo / row["path"]).exists(), "정본이 지운 G2 원문을 되살렸다 (D-92)"


@pytest.mark.gate
def test_모르는_원천은_합치지_않고_센다(repo, inbox, monkeypatch) -> None:
    """🚨 레지스트리에 없는 원천 — 막는 쪽 (D-220). `pending` 은 세고 `import_` 는 거부한다."""
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    from collect import registry

    def unknown(s):
        raise registry.RegistryError(s)

    monkeypatch.setattr(registry, "is_g2", unknown)
    assert [r["path"] for r in ri.pending()] == [row["path"]]
    assert ri.import_(yes=True) == 1
    assert not (repo / row["path"]).exists()


def _branch(monkeypatch, base: list[dict], rows: list[dict]) -> None:
    monkeypatch.setattr(ri, "_branch_ledger", lambda b: rows)
    monkeypatch.setattr(ri, "_base_ledger", lambda b: base)


@pytest.mark.gate
def test_병합_전_검사는_재배포_제약을_막고_안내가_맞다(repo, inbox, monkeypatch, capsys) -> None:
    """재배포 제약은 `raw-publish` 가 **안 올린다** — 「raw-publish 다시」라고 하면 영영 안 끝난다."""
    row = _uploaded(repo, inbox, monkeypatch, b'{"a":1}')
    _ledger(repo, [])
    _branch(monkeypatch, [], [row])
    monkeypatch.setattr(ri, "_noredist", lambda s: True)
    capsys.readouterr()
    assert ri.import_(branch="origin/collector") == 1
    out = capsys.readouterr().out
    assert "재배포 제약" in out and "올리지 않는다" in out
    assert "`raw-publish` 를 다시 요청" not in out, out


@pytest.mark.gate
def test_병합_전_검사는_같은_경로_다른_sha_를_막는다(repo, inbox, monkeypatch) -> None:
    """🔴 §1-4 ② — 정본에 이미 있는 경로를 **다른 바이트**로 적은 브랜치가 「✅ 병합해도 된다」였다."""
    _canonical(monkeypatch)
    p = f"data/raw/{FAM}/page_0001.json"
    (repo / p).parent.mkdir(parents=True)
    (repo / p).write_bytes(b'{"a":1}')
    local = [_row(p, b'{"a":1}', "clone-b")]
    _ledger(repo, local)
    _branch(monkeypatch, local, [*local, _row(p, b'{"a":2}', "collector-1")])
    assert ri.import_(branch="origin/collector") == 1
    # 원장에 없고 디스크에만 있는 경로도 같다
    _ledger(repo, [])
    _branch(monkeypatch, [], [_row(p, b'{"a":2}', "collector-1")])
    assert ri.import_(branch="origin/collector") == 1
    # 같은 sha 면 통과 (이미 합친 줄)
    _branch(monkeypatch, [], [_row(p, b'{"a":1}', "collector-1")])
    assert ri.import_(branch="origin/collector") == 0


@pytest.mark.gate
def test_병합_전_검사는_원장의_옛_줄을_고치거나_지운_브랜치를_막는다(
    repo, inbox, monkeypatch
) -> None:
    """원장은 붙이기만 한다 — 갈래점 원장이 브랜치 원장의 앞머리가 아니면 🔴."""
    _canonical(monkeypatch)
    a = _row("data/raw/f/a.json", b"1", "clone-b")
    b = _row("data/raw/f/b.json", b"2", "clone-b")
    (repo / "data/raw/f").mkdir(parents=True)
    (repo / "data/raw/f/a.json").write_bytes(b"1")
    (repo / "data/raw/f/b.json").write_bytes(b"2")
    _ledger(repo, [a, b])
    _branch(monkeypatch, [a, b], [a])  # 지웠다
    assert ri.import_(branch="origin/collector") == 1
    _branch(monkeypatch, [a, b], [a, {**b, "bytes": 99}])  # 고쳤다
    assert ri.import_(branch="origin/collector") == 1
    _branch(monkeypatch, [a, b], [a, b])  # 그대로
    assert ri.import_(branch="origin/collector") == 0
    assert ri.rewritten([a, b], [b, a])


@pytest.mark.gate
def test_올리기는_정본의_옛_원문을_올리지_않는다(repo, inbox, monkeypatch, capsys) -> None:
    """🟡 §2 raw-publish — 옛 원문이 있는 사본(클론 A)이 기기 칸 없는 과거분·`canonical` 줄을 올리지 않는다."""
    sha = _collected(repo, monkeypatch, b'{"mine":1}')
    for name, dev in (("legacy.json", None), ("canon.json", store.CANONICAL_DEVICE)):
        f = repo / "data" / "raw" / FAM / name
        f.write_bytes(name.encode())
        _ledger(repo, [*_rows(repo), _row(f"data/raw/{FAM}/{name}", name.encode(), dev)])
    capsys.readouterr()
    assert ri.publish(yes=True) == 0
    objs = sorted(p.name for p in (inbox / "objects").rglob("*") if p.is_file())
    assert objs == [sha]
    out = capsys.readouterr().out
    assert "옛 행 1개" in out and "행 1개" in out, out


@pytest.mark.gate
def test_수집기는_다른_기기가_받은_것을_다시_부르지_않는다(repo) -> None:
    """🔴 2026-09-21 (전수 재검토) — ⛔ 수집기가 디스크만 봐서 팀원 기기가 정본이 받은 것을 다시 불렀고,
    조회수처럼 부를 때마다 바뀌는 원천은 새 판으로 깔렸다. ★ 이 기기가 받은 기록만 있고 없으면 다시 부른다(유실)."""
    rel = f"data/raw/{FAM}/hf_board_1.html"
    p = repo / rel
    _ledger(repo, [_row(rel, b"x", "canonical")])
    assert store.already_have(p), "다른 기기 것은 부르지 않는다"
    _ledger(repo, [_row(rel, b"x", "collector-1")])
    store._INDEX = None  # noqa: SLF001
    assert not store.already_have(p), "이 기기가 받았는데 없으면 다시 받는다 — 되살림"
    _ledger(repo, [])
    store._INDEX = None  # noqa: SLF001
    assert not store.already_have(p)
