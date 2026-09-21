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
LABEL = "labels/누군가.jsonl"  # 원천 — 🔄 D-249 부터 저장소가 옮긴다 (종전 git)
SPLIT = (
    "golden/split_manifest.json"  # 표본 — git 이 나른다(dm.GIT_CARRIES) · 저장소에 올리지 않는다
)


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
    _repo(canon, {LABEL: b'{"l":1}\n', SPLIT: b'{"assign":{}}\n'})
    _point(monkeypatch, canon)
    _write_manifest()
    return tmp_path, storage, canon


def _publish(mp: pytest.MonkeyPatch) -> int:
    mp.setenv("DATA_ROLE", "canonical")
    return ds.publish(yes=True)


@pytest.mark.gate
def test_올리는_것은_원천_표본_생성물이고_원문캐시와_git_몫은_아니다(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 원문캐시는 마스킹 전 원문이다 — 제3자 계정에 나가면 안 된다 (D-17 · D-78 ③).

    🔄 2026-09-20 (D-249) — 라벨(원천)도 올린다. 공개 git 에서 인용 원문을 뺐기 때문이다.
       git 이 나르는 `split_manifest.json` 은 올리지 않는다 — 두 길로 나르면 두 벌이 된다 (D-99).
    """
    _tmp, storage, canon = world
    assert _publish(monkeypatch) == 0
    objs = {p.name for p in (storage / ds.LAYOUT / "objects").rglob("*") if p.is_file()}

    def sha(rel: str) -> str:
        return hashlib.sha256((canon / "data" / "derived" / rel).read_bytes()).hexdigest()

    assert objs == {sha(GEN), sha(LABEL)}, f"생성물과 라벨만 올라가야 한다: {objs}"
    assert sha(CACHE) not in objs and sha(SPLIT) not in objs
    log = (storage / ds.LAYOUT / "publish_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(log[-1])["objects_new"] == 2


@pytest.mark.gate
def test_사본은_부족분만_받고_옛판은_백업한다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """★ 팀장 요구 그 자체 — 옛 판을 든 클론 A 가 받으면 정본과 같아진다. 옛 것은 레포 밖에 남는다."""
    tmp, _storage, canon = world
    assert _publish(monkeypatch) == 0
    manifest = dm.OUT.read_bytes()

    # 클론 A — git 이 원장과 분할표를 옮겼고, 생성물은 옛 판이고, 라벨·원문캐시는 없다
    #    🔄 D-249 — 라벨은 이제 git 이 아니라 저장소에서 온다
    a = _repo(tmp / "A", {GEN: b'{"text":"v1"}\n', SPLIT: b'{"assign":{}}\n'})
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")

    assert [r["경로"] for r in ds.plan()] == [f"data/derived/{GEN}", f"data/derived/{LABEL}"]
    assert ds.sync(yes=True) == 0
    assert (a / "data" / "derived" / GEN).read_bytes() == (
        canon / "data" / "derived" / GEN
    ).read_bytes()
    assert not (a / "data" / "derived" / CACHE).exists(), "원문캐시를 받으면 안 된다"
    assert (a / "data" / "derived" / LABEL).read_bytes() == b'{"l":1}\n', "라벨을 못 받았다 (D-249)"
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


@pytest.mark.gate
@pytest.mark.parametrize(
    "path",
    [
        "data/derived/../../evil.txt",  # 레포 밖
        "data/derived/../.git/hooks/pre-commit",  # 훅 자리
        "data/manifest.jsonl",  # 파생물 폴더 밖 · 레포 안
    ],
)
def test_원장이_파생물_폴더_밖을_가리키면_아무것도_받지_않는다(
    world, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """🔴 보안 점검 (2026-09-19) — 받을 경로는 **git 원장이 정한다.** 원장은 누구나 push 할 수 있다.

    🚨 저장소에 **sha 가 맞는 바이트를 미리 넣어 둔다** — 저장소에도 쓸 수 있는 사람을 가정한다.
       그래야 경로 검사가 없을 때 실제로 밖에 써진다(반대 대조가 성립한다).
    """
    tmp, storage, _canon = world
    payload = b"planted\n"
    sha = hashlib.sha256(payload).hexdigest()
    obj = storage / ds.LAYOUT / "objects" / sha[:2] / sha
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(payload)

    a = _repo(tmp / "A", {LABEL: b'{"l":1}\n'})
    row = {"경로": path, "부류": "생성물", "sha256": sha, "bytes": len(payload)}
    (a / "data" / "derived_manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    _point(monkeypatch, a)
    monkeypatch.setattr(ds, "plan", lambda: [row])  # 경로 해석을 건너뛰고 받기 단계만 본다
    monkeypatch.setenv("DATA_ROLE", "replica")
    target = (a / path).resolve()
    before = target.read_bytes() if target.exists() else None
    assert ds.sync(yes=True) == 1
    after = target.read_bytes() if target.exists() else None
    assert after == before, f"원장이 가리킨 밖의 자리에 썼다: {target}"


@pytest.mark.gate
def test_sha_모양이_아니면_경로로_쓰지_않는다() -> None:
    """sha 는 저장소 안의 파일 이름이다 — `../` 가 들어오면 저장소 밖을 읽는다."""
    with pytest.raises(ds.StoreError):
        ds._obj(pathlib.Path("store"), "../../etc/passwd" + "0" * 48)
    assert ds.unsafe([{"경로": "data/derived/ok.jsonl", "sha256": "../x"}])


@pytest.mark.gate
def test_개인이_특정되면_올리지_않는다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 반출 검사의 첫 번째 축 (2026-09-19 · 팀장 지적) — 법인 표기보다 먼저 멈춘다."""
    _tmp, storage, canon = world
    _repo(canon, {"stage.jsonl": '{"사건명":"홍길동의 표시광고법 위반행위에 대한 건"}\n'.encode()})
    _write_manifest()
    assert _publish(monkeypatch) == 1
    assert not (storage / ds.LAYOUT / "objects").exists(), "한 파일이라도 올라갔다"


# ══════════════════════════════════════════════════════════
# 🆕 2026-09-20 — `data-setup` : 역할·저장소를 런처가 적고, 받는 쪽이면 바로 받는다
# ══════════════════════════════════════════════════════════
def _env_file(tmp: pathlib.Path, mp: pytest.MonkeyPatch) -> pathlib.Path:
    """`.env` 를 임시 파일로 돌린다 — 진짜 `.env` 는 건드리지 않는다."""
    from collect import setkey

    env_path = tmp / "dotenv"
    env_path.write_text("DATA_ROLE=\nDATA_STORE=\n", encoding="utf-8", newline="\n")
    mp.setattr(setkey, "ENV_PATH", env_path)
    # 🚨 진짜 드라이브를 뒤지지 않는다 — 클론 B 에는 진짜 `CopyLane_raw_inbox` 가 붙어 있다 (D-250)
    mp.setattr(ds, "candidates", lambda roots=None, name=ds.STORE_NAME: [])
    # 🚨 `put_setting` 은 `os.environ` 에 직접 쓴다 — 먼저 setenv 로 **원래 값을 기록**해야 끝나고 되돌린다
    for k in ("DATA_ROLE", "DATA_STORE", "RAW_INBOX", "DATA_DEVICE"):
        mp.setenv(k, "")
        mp.delenv(k)
    return env_path


@pytest.mark.gate
def test_드라이브_글자가_달라도_저장소_폴더를_찾는다(tmp_path: pathlib.Path) -> None:
    """★ 기기마다 G: · H: · J: 로 다르다 — 폴더 이름으로 찾는다. 한국어·영어 설정 둘 다."""
    j = tmp_path / "J"
    (j / "내 드라이브" / ds.STORE_NAME).mkdir(parents=True)
    k = tmp_path / "K"
    (k / "My Drive" / ds.STORE_NAME).mkdir(parents=True)
    (tmp_path / "H" / "내 드라이브").mkdir(parents=True)  # 드라이브는 있는데 폴더가 없다
    got = ds.candidates([tmp_path / "H", j, k])
    assert got == [j / "내 드라이브" / ds.STORE_NAME, k / "My Drive" / ds.STORE_NAME]


@pytest.mark.gate
def test_설정은_env_에_적고_받는_쪽이면_바로_받는다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 팀장 요구 — 클론 A · 팀원은 명령 하나로 역할·경로가 적히고 파생물이 채워진다."""
    tmp, storage, canon = world
    assert _publish(monkeypatch) == 0
    manifest = dm.OUT.read_bytes()
    a = _repo(tmp / "A", {SPLIT: b'{"assign":{}}\n'})
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    env_path = _env_file(tmp, monkeypatch)

    assert ds.setup(role="replica", store=str(storage), yes=True) == 0
    text = env_path.read_text(encoding="utf-8")
    assert "DATA_ROLE=replica" in text and f"DATA_STORE={storage}" in text, text
    assert (a / "data" / "derived" / GEN).read_bytes() == (
        canon / "data" / "derived" / GEN
    ).read_bytes()
    assert (a / "data" / "derived" / LABEL).exists(), "라벨도 받아야 한다 (D-249)"


@pytest.mark.gate
def test_설정은_모르는_역할과_없는_폴더를_적지_않는다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🚨 틀린 값이 `.env` 에 들어가면 다음 명령이 엉뚱한 곳을 본다 — 쓰기 전에 멈춘다 (D-220)."""
    env_path = _env_file(tmp_path, monkeypatch)
    before = env_path.read_bytes()
    assert ds.setup(role="canonnical", store=str(tmp_path), yes=True) == 1
    assert ds.setup(role="replica", store=str(tmp_path / "없다"), yes=True) == 1
    monkeypatch.setattr(ds, "candidates", lambda roots=None, name=ds.STORE_NAME: [])
    assert ds.setup(role="replica", yes=True) == 1
    assert env_path.read_bytes() == before, "실패했는데 .env 가 바뀌었다"


@pytest.mark.gate
def test_키는_설정_경로로_쓰지_않는다() -> None:
    """🚨 비밀은 `setkey`(화면에 안 뜬다)로만 — 설정 쓰기가 키를 받으면 값이 화면·기록에 남는다 (D-111)."""
    from collect import setkey

    with pytest.raises(setkey.SetKeyError):
        setkey.put_setting("LAW_OC_KEY", "x")


# ══════════════════════════════════════════════════════════
# 🆕 D-254 — 런처 전수 감사 (2026-09-20)
# ══════════════════════════════════════════════════════════
@pytest.mark.gate
def test_원문_확인은_gitkeep_만_있으면_묻지_않는다(tmp_path: pathlib.Path) -> None:
    """🟡 §2 data-sync — `.gitkeep` 이 추적되므로 「폴더가 있다」는 모든 기기에서 참이었다(안 읽히는 확인)."""
    mark = tmp_path / "raw"
    assert ds.has_raw(mark) is False, "폴더가 없는데 원문이 있다고 봤다"
    mark.mkdir()
    (mark / ".gitkeep").write_bytes(b"")
    assert ds.has_raw(mark) is False, ".gitkeep 만 있는데 원문이 있다고 봤다"
    (mark / "src" / "fam").mkdir(parents=True)
    assert ds.has_raw(mark) is False, "빈 하위 폴더를 원문으로 봤다"
    (mark / "src" / "fam" / "a.json").write_bytes(b"{}")
    assert ds.has_raw(mark) is True


#: 수집 원장의 경로 — 🚨 이 파일은 원문 폴더 이름을 적지 않는다(게이트 `RAW_EXCEPTIONS` 밖). 검사는 경로만 본다
RAWP = "원문_자리/x/"


def _ledger_rows(rows: list[dict]) -> None:
    store.MANIFEST.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n"
    )


@pytest.mark.gate
def test_팀원이_받은_재배포_제약_원천은_정본_publish_를_막지_않는다(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🟡 §2 data-publish — 원장은 git 으로 팀원 줄까지 합쳐진다. 기기 칸을 안 보면 정본이 **영영** 막혔다.

    ★ 파생물은 정본 디스크의 원문으로만 만든다 — 이 기기가 받았는가(기기 칸 · 디스크)로 가른다.
    """
    _tmp, _storage, canon = world
    monkeypatch.setenv("DATA_DEVICE", "clone-b")
    _ledger_rows([{"source_id": "aihub_558", "path": RAWP + "a.json", "device": "collector-1"}])
    assert _publish(monkeypatch) == 0, "다른 팀원이 받은 것으로 정본을 막았다"
    # 같은 줄인데 그 파일이 이 기기 디스크에 있다 — 손으로 옮겼을 수 있다 → 막는다
    f = canon / RAWP / "a.json"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"{}")
    assert _publish(monkeypatch) == 1
    f.unlink()
    # 이 기기 · canonical · 기기 칸 없음(정본의 과거분) — 막는다
    for dev in ("clone-b", "canonical", None):
        row = {"source_id": "aihub_558", "path": RAWP + "b.json"}
        if dev:
            row["device"] = dev
        _ledger_rows([row])
        assert _publish(monkeypatch) == 1, f"{dev} 가 받은 재배포 제약 원천을 못 봤다"


@pytest.mark.gate
def test_publish_기록은_원장_sha_와_커밋_여부를_남긴다(
    world, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🟡 §2 data-publish — 「커밋 X 의 원장과 같다」의 X 는 HEAD 였다. 안내 순서(올리고 커밋)에선 거짓이다."""
    _tmp, storage, _canon = world
    monkeypatch.setattr(ds, "manifest_in_head", lambda: False)
    capsys.readouterr()
    assert _publish(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "원장 미커밋" in out and "의 원장과 같다" not in out, out
    log = (storage / ds.LAYOUT / "publish_log.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(log[-1])
    assert entry["manifest_in_head"] is False
    assert entry["manifest_sha256"] == hashlib.sha256(dm.OUT.read_bytes()).hexdigest()


@pytest.mark.gate
def test_원장이_HEAD_에_없으면_미커밋으로_본다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """가짜 레포는 git 이 아니다 — 모르는 것은 「같다」로 세지 않는다 (None)."""
    assert ds.manifest_in_head() is None


@pytest.mark.gate
def test_중간_파일의_바이트가_틀리면_앞_파일도_안_바뀐다(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 2026-09-21 — ⛔ 종전에는 한 파일씩 「백업 → 받기」라, 두 번째 파일의 sha 가 틀리면 첫 파일은
    이미 새 판으로 바뀐 **섞인 상태**로 멈췄다. 이제 전부 확인한 뒤에만 바꿔 끼운다."""
    tmp, storage, canon = world
    assert _publish(monkeypatch) == 0
    sha_label = hashlib.sha256((canon / "data" / "derived" / LABEL).read_bytes()).hexdigest()
    ds._obj(storage / ds.LAYOUT, sha_label).write_bytes(b"corrupted")  # 라벨 객체만 오염
    manifest = dm.OUT.read_bytes()
    a = _repo(tmp / "A", {GEN: b'{"text":"v1"}\n', LABEL: b"old-label\n"})
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert [r["경로"] for r in ds.plan()] == [f"data/derived/{GEN}", f"data/derived/{LABEL}"]
    assert ds.sync(yes=True) == 1
    assert (a / "data" / "derived" / GEN).read_bytes() == b'{"text":"v1"}\n', (
        "🔴 앞 파일만 바뀌었다"
    )
    assert (a / "data" / "derived" / LABEL).read_bytes() == b"old-label\n"
    assert not list((a / "data" / "derived").rglob("*.part")), "임시 파일이 남았다"
    assert not (tmp / "A_backup").exists(), "아무것도 안 바꿨는데 백업을 만들었다"


@pytest.mark.gate
def test_dry_run_도_저장소_준비를_본다(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 2026-09-21 — ⛔ 종전 dry-run 은 저장소를 보기 전에 끝나 「받을 것 N개」만 말하고 0 을 냈다."""
    tmp, _storage, _canon = world  # publish 를 안 했다 — 저장소가 비었다
    manifest = dm.OUT.read_bytes()
    a = _repo(tmp / "A", {})
    (a / "data" / "derived").mkdir(parents=True)
    (a / "data" / "derived_manifest.jsonl").write_bytes(manifest)
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ds.sync(dry_run=True) == 1, "🔴 저장소에 없는데 dry-run 이 초록이다"
    monkeypatch.setenv("DATA_STORE", "")
    assert ds.sync(dry_run=True) == 1, "🔴 DATA_STORE 가 비었는데 dry-run 이 초록이다"
    # 반대 대조 — 올린 뒤에는 dry-run 이 0 이고 아무것도 받지 않는다
    monkeypatch.setenv("DATA_STORE", str(_storage))
    _point(monkeypatch, _canon)
    assert _publish(monkeypatch) == 0
    _point(monkeypatch, a)
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert ds.sync(dry_run=True) == 0
    assert not (a / "data" / "derived" / GEN).exists()


def test_크기_단위는_MiB_다() -> None:
    assert ds._size([{"bytes": 1024 * 1024}]) == "1.0 MiB"
