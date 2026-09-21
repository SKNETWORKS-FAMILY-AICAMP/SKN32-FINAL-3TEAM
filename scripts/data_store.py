#!/usr/bin/env python3
"""data_store.py — **부족한 파생물을 공유 저장소에서 받는다** (2026-09-19 · D-247 · 검토 2026-09-19 §5).

  uv run python -m scripts.data_store plan           # 무엇이 부족한가 (쓰지 않는다 · 네트워크 없음)
  uv run python -m scripts.data_store sync [--yes]    # 사본 — 부족분을 받는다
  uv run python -m scripts.data_store publish [--yes] # 정본 — 생성물을 올린다
  uv run python -m scripts.data_store ensure         # 런처가 데이터 명령 앞에서 부른다

──────────────────────────────────────────────────────────────
★ **「무엇이 있어야 하나」는 git 이 이미 나른다** — `data/derived_manifest.jsonl`(경로 → sha256).
  없는 것은 **바이트를 sha256 으로 찾아올 곳** 하나였다. 그것이 이 모듈이다.

    <DATA_STORE>/copylane-derived/objects/<sha 앞 2자>/<sha256>     ← 파일 이름 = 내용의 해시
    <DATA_STORE>/copylane-derived/publish_log.jsonl                 ← 누가 · 어느 커밋 · 몇 개

  - 「부족한 것만」이 공짜다 — 가진 sha 는 안 받는다
  - 판이 쌓여도 같은 내용은 한 번만 — 옛 커밋으로 돌아가도 그 판이 선다
  - 🔴 **무엇을 받을지는 git 이 정한다.** 저장소에는 판정이 없다. 받은 바이트의 sha 가 원장과
    다르면 **놓지 않는다** (D-220 fail-closed)

🚨 **저장소는 폴더다** — 판정 ②(어느 서비스인가)가 나기 전에도 돌게, 가장 작은 공통분모로 만들었다.
   Google Drive for desktop · NAS · USB 가 전부 폴더로 붙는다. 서비스가 정해져 폴더가 아니게 되면
   `_get`·`_put` 두 함수만 바뀐다.

🔄 **옮기는 것은 원천·표본·생성물이다** (2026-09-20 · D-249 — 종전 「생성물뿐 · 원천·표본은 git」).
   공개 git 에 인용 광고 문구가 올라가 있어 원천·표본을 저장소로 옮겼다. 원문캐시는 **옮기지 않는다**
   (마스킹 전 원문 · D-17). 올리기 전에 코드가 막는다 — 사람의 약속으로 두지 않는다 (D-117).
🚨 저장소는 **제3자 계정**이다 (D-78 ③) — 재배포 제약 소스(`redistributable: false`)를 한 번이라도
   받은 기기에서는 **올리지 않는다.** 그 순간 파생물 어딘가에 그 행이 섞였을 수 있다 (D-71).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import string
import subprocess
import sys

from scripts import derived_manifest as dm

ROOT = dm.ROOT
LAYOUT = "copylane-derived"
#: 사본이 덮어쓸 때 옛 파일을 복사해 두는 곳 — **레포 밖**이다 (git status 에 안 뜬다)
BACKUP = ROOT.parent / "CopyLane_backup"
#: 🚨 `data/raw` 에 **파일이 있는지만** 본다 — 열지 않는다. `RAW_EXCEPTIONS` 에 이유와 함께 적었다.
RAW_MARK = ROOT / "data" / "raw"
#: 🚨 저장소가 옮기는 부류는 이것 하나다 — 이름의 정본은 dm.KIND_RULES / DEFAULT_KIND
#: 🔄 2026-09-20 (D-249) — 생성물만이 아니다. **원천·표본도 옮긴다** — 공개 git 에서 인용 원문을 뺐다.
#:    무엇을 옮기는지의 정본은 `dm.moved()` 하나다 (D-99).
MOVED = dm.STORE_KINDS


class StoreError(RuntimeError):
    """저장소를 쓸 수 없거나 규칙을 어겼다 — 무엇을 고치면 되는지를 담는다."""


# ══════════════════════════════════════════════════════════
# 저장소 — 폴더 하나. 서비스가 바뀌면 이 절만 바뀐다
# ══════════════════════════════════════════════════════════
def store_root() -> pathlib.Path:
    """`.env` 의 `DATA_STORE`. 🔴 없으면 **멈춘다** — 조용히 「받을 것 없음」으로 끝내지 않는다."""
    from collect import env  # noqa: PLC0415 — `.env` 를 여는 곳은 한 곳이다 (D-99)

    raw = env.setting("DATA_STORE")
    if not raw:
        raise StoreError(
            "DATA_STORE 가 비어 있다 — 공유 저장소 폴더를 모른다.\n"
            "  기입  .env 에 `DATA_STORE=<폴더 경로>` (예: G:\\내 드라이브\\CopyLane_store)\n"
            "  🚨 저장소 서비스는 판정 ② 대기다 (검토 2026-09-19 §11-2)"
        )
    root = pathlib.Path(raw).expanduser()
    if not root.is_dir():
        raise StoreError(
            f"DATA_STORE 폴더가 없다 — {root}\n"
            "  🚨 드라이브가 안 붙었거나 동기화 앱이 꺼져 있을 수 있다. 폴더를 연 뒤 다시 한다"
        )
    return root / LAYOUT


_SHA = re.compile(r"[0-9a-f]{64}")


def _obj(root: pathlib.Path, sha: str) -> pathlib.Path:
    if not _SHA.fullmatch(sha):  # 🚨 이름이 곧 경로다 — 64자 16진이 아니면 경로로 쓰지 않는다
        raise StoreError(f"sha256 모양이 아니다 — {sha[:40]!r}")
    return root / "objects" / sha[:2] / sha


def unsafe(rows: list[dict[str, object]]) -> list[str]:
    """🔴 원장 행 중 **파생물 폴더 밖을 가리키거나 sha 모양이 아닌 것** (2026-09-19 · 보안 점검).

    ⛔ 받을 경로는 git 의 원장이 정한다. 원장은 팀원 누구나 push 할 수 있는 파일이라
       `data/derived/../../.git/hooks/pre-commit` 같은 행 하나면 **레포 밖이나 훅 자리에 쓴다.**
       sha 가 맞아야 놓이지만, 저장소에도 쓸 수 있는 사람이면 sha 도 맞출 수 있다.
    ★ 그래서 쓰기 **전에** 전부 본다 — 하나라도 있으면 아무것도 받지 않는다.
    """
    base = (ROOT / "data" / "derived").resolve()
    bad = []
    for r in rows:
        path, sha = str(r.get("경로", "")), str(r.get("sha256", ""))
        target = (ROOT / path).resolve()
        inside = target.is_relative_to(base) and target != base
        if not (path.startswith("data/derived/") and ".." not in path.split("/") and inside):
            bad.append(f"경로 {path!r}")
        elif not _SHA.fullmatch(sha):
            bad.append(f"sha {path!r}")
    return bad


def _sha(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _stage(src: pathlib.Path, dest: pathlib.Path, sha: str) -> pathlib.Path:
    """`dest` 옆 임시 이름(`.part`)에 복사하고 sha 를 확인한다 — **제자리에는 놓지 않는다.** 돌려주는 값은 임시 파일.

    ⛔ 동기화 폴더는 「아직 다 안 내려온 파일」을 보여 줄 수 있다. sha 가 안 맞으면 임시 파일도 지우고 멈춘다.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    shutil.copyfile(src, tmp)
    got = _sha(tmp)
    if got != sha:
        tmp.unlink()
        raise StoreError(
            f"받은 바이트가 원장과 다르다 — {dest.name}\n"
            f"  원장 {sha[:16]} · 받은 것 {got[:16]}\n"
            "  🚨 동기화가 덜 끝났거나 저장소가 오염됐다. 놓지 않았다 (D-220)"
        )
    return tmp


def _copy_verified(src: pathlib.Path, dest: pathlib.Path, sha: str) -> None:
    """임시 이름으로 복사 → sha 확인 → 제자리로. 🚨 **반쯤 쓴 파일이 제자리에 남지 않는다.**"""
    os.replace(_stage(src, dest, sha), dest)


def _put(root: pathlib.Path, src: pathlib.Path, sha: str) -> bool:
    """올렸으면 True, 이미 있으면 False. 🚨 있는 것은 다시 올리지 않는다 — 이름이 곧 내용이다."""
    dest = _obj(root, sha)
    if dest.is_file() and _sha(dest) == sha:
        return False
    _copy_verified(src, dest, sha)
    return True


# ══════════════════════════════════════════════════════════
# 무엇이 부족한가
# ══════════════════════════════════════════════════════════
def plan() -> list[dict[str, object]]:
    """이 기기에 **없거나 원장과 다른 생성물** — 받아야 할 것. 네트워크를 쓰지 않는다.

    🚨 **git 이 나르는 파일**(`dm.GIT_CARRIES`)이 다르면 여기 넣지 않는다 — 저장소에서 받아 덮으면
       git 과 두 벌이 된다. `git_side` 가 그것을 따로 알려 준다.
    🔄 2026-09-20 (D-249) — 원천·표본(라벨 · 라벨 시트)도 여기서 받는다. git 에서 뺐다.
    """
    led = dm.ledger()
    d = dm.diff("replica")
    want = [p for p in d["missing"] + d["changed"] if dm.moved(p, str(led[p]["부류"]))]
    return [led[p] for p in sorted(want)]


def git_side() -> list[str]:
    """git 이 나르는데 이 기기와 다른 것 — `git pull`/`git status` 의 일이다."""
    d = dm.diff("replica")
    return [p for p in d["missing"] + d["changed"] if p in dm.GIT_CARRIES]


def _size(rows: list[dict[str, object]]) -> str:
    """🔄 2026-09-21 — 1024² 로 나누므로 단위는 **MiB** 다. ⛔ 종전에는 「MB」라 적어 탐색기(10⁶)와 5% 갈렸다."""
    n = sum(int(r["bytes"]) for r in rows)  # type: ignore[arg-type]
    return f"{n / 1024 / 1024:,.1f} MiB"


def has_raw(mark: pathlib.Path | None = None) -> bool:
    """이 기기에 원문이 **있는가** — `.gitkeep` 말고 파일이 하나라도 있으면 참. 첫 파일에서 멈춘다.

    🔄 D-254 (런처 전수 감사 §2 data-sync) — ⛔ 종전 조건은 `RAW_MARK.is_dir()` 였다. `data/raw/.gitkeep` 이
       git 에 추적되므로 **모든 기기에서 참**이라, 사본마다 매번 뜨는 확인이 됐다 — 안 읽히는 확인은 없는 것과 같다.
    🚨 이름만 훑는다 — 파일을 열지 않는다. 폴더를 못 읽으면 「있다」로 본다(묻는 쪽이 안전하다 · D-220).
    """
    mark = RAW_MARK if mark is None else mark
    if not mark.is_dir():
        return False
    try:
        return any(f.name != ".gitkeep" and f.is_file() for f in mark.rglob("*"))
    except OSError:
        return True


def _ask(question: str) -> bool:
    try:
        return input(f"{question} [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


# ══════════════════════════════════════════════════════════
# 받기 — 사본
# ══════════════════════════════════════════════════════════
def sync(*, yes: bool = False, dry_run: bool = False) -> int:
    """🔴 사본만 받는다. 정본은 받지 않는다 — 방금 만든 것을 옛 판으로 되돌리면 안 된다."""
    who = dm.role()
    if who != "replica":
        print(
            f"🔴 받지 않는다 — 이 기기의 역할이 {who or '없음'} 이다.\n"
            "  받는 쪽이면 .env 에 `DATA_ROLE=replica` (클론 A · 팀원 · 서버).\n"
            "  🚨 정본(클론 B)은 받지 않고 `data-publish` 로 올린다 (D-226)"
        )
        return 1
    todo = plan()
    bad = unsafe(todo)
    if bad:
        print(
            f"🔴 원장에 받을 수 없는 행이 있다 — 아무것도 받지 않았다: {bad[:5]}", file=sys.stderr
        )
        print(
            "  🚨 파생물 폴더 밖을 가리키거나 sha 모양이 아니다. 원장 커밋을 확인한다",
            file=sys.stderr,
        )
        return 1
    for p in git_side():
        print(f"  🟡 git 이 옮기는 파일인데 이 기기와 다르다 — {p}  (`git status` · `git pull`)")
    if not todo:
        print("받을 것 없음 — 이 기기의 생성물이 원장과 같다")
        return 0
    over = [r for r in todo if (ROOT / str(r["경로"])).exists()]
    print(
        f"받을 것 {len(todo)}개 · {_size(todo)} — 새로 {len(todo) - len(over)} · 옛 판 교체 {len(over)}"
    )
    for r in todo[:10]:
        print(f"    {'🔄' if r in over else '⬇'} {r['경로']}")
    if len(todo) > 10:
        print(f"    … 외 {len(todo) - 10}개")
    # 🔄 2026-09-21 — 저장소 준비(폴더 · 객체가 다 있는가)를 **dry-run 에서도** 본다.
    #    ⛔ 종전에는 dry-run 이 이 검사 전에 끝나, 「받을 것 42개」를 보고 실제로 돌리면
    #       `DATA_STORE` 가 비었다거나 객체가 모자라다며 멈췄다 — 미리보기가 답을 못 줬다.
    #    🚨 저장소 폴더를 **읽기만** 한다(이름·있음 확인). 아무것도 안 쓴다.
    try:
        root = store_root()
        # 🔴 **먼저 전부 있는지 본다** — 반만 받고 멈추면 파생물이 두 판으로 섞인다.
        lack = [r for r in todo if not _obj(root, str(r["sha256"])).is_file()]
    except StoreError as e:
        print(f"🔴 {e}", file=sys.stderr)
        if dry_run:
            print("🚨 --dry-run — 아무것도 받지 않았다. 이대로 받으면 여기서 멈춘다")
        return 1
    if lack:
        print(f"🔴 저장소에 없는 것 {len(lack)}개 — 아무것도 받지 않았다", file=sys.stderr)
        for r in lack[:10]:
            print(f"    {r['경로']}  {str(r['sha256'])[:16]}", file=sys.stderr)
        print(
            "  🚨 정본(클론 B)에서 `launcher.py data-publish` 를 했는지 확인한다", file=sys.stderr
        )
        return 1
    if dry_run:
        print(f"✅ 저장소에 {len(todo)}개가 다 있다 — {root}")
        print("🚨 --dry-run — 아무것도 받지 않았다")
        return 0

    # 🚨 raw 가 있는 기기에서 덮어쓸 때는 **한 번 묻는다** — 클론 B 의 DATA_ROLE 이 틀렸을 수 있다.
    if over and has_raw() and not yes:
        print(
            f"\n⚠️ 이 기기에는 원문(data/raw)이 있다. 옛 판 {len(over)}개를 저장소 판으로 바꾼다.\n"
            "   클론 A 라면 맞다. 🔴 **클론 B(정본)라면 DATA_ROLE 이 틀렸다** — 방금 만든 것이 옛 판으로 돌아간다."
        )
        if not _ask("계속할까"):
            print("멈췄다 — 아무것도 바꾸지 않았다")
            return 1

    # 🔄 2026-09-21 — **두 단계로 바꾼다.** ① 전부 임시 파일(`.part`)로 받아 sha 를 확인한다 —
    #    하나라도 틀리면 임시 파일을 다 지우고 **아무것도 안 바꾼다.** ② 전부 맞을 때만 옛 판을
    #    백업(복사)하고 제자리로 바꿔 끼운다.
    #    ⛔ 종전에는 한 파일씩 「백업 → 받기」를 돌아, 중간 파일의 sha 가 틀리면 앞 파일들은 새 판 ·
    #       뒤 파일들은 옛 판인 **섞인 상태**로 멈췄다(위 `lack` 검사는 「있는가」만 보고 「맞는가」는 안 본다).
    staged: list[tuple[pathlib.Path, pathlib.Path]] = []
    try:
        for r in todo:
            dest = ROOT / str(r["경로"])
            staged.append((_stage(_obj(root, str(r["sha256"])), dest, str(r["sha256"])), dest))
    except (StoreError, OSError) as e:
        for tmp, _dest in staged:
            tmp.unlink(missing_ok=True)
        print(f"🔴 {e}", file=sys.stderr)
        print("  ⬜ 아무것도 바꾸지 않았다 — 받은 임시 파일은 지웠다", file=sys.stderr)
        return 1

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for (tmp, dest), r in zip(staged, todo, strict=True):
        if dest.exists():
            keep = BACKUP / stamp / str(r["경로"])
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, keep)
        os.replace(tmp, dest)
    if over:
        print(f"  옛 판 {len(over)}개는 {BACKUP / stamp} 에 복사해 두었다 (되돌릴 수 있다)")
    left = plan()
    if left:
        print(f"🔴 받은 뒤에도 {len(left)}개가 원장과 다르다", file=sys.stderr)
        return 1
    print(f"받았다 {len(todo)}개 — 이 기기의 생성물이 원장과 같다")
    return 0


# ══════════════════════════════════════════════════════════
# 올리기 — 정본
# ══════════════════════════════════════════════════════════
def _noredist_seen() -> list[str]:
    """이 기기가 **받은 적 있는** 재배포 제약 소스 — 수집 원장(git)에서 본다. 원문은 열지 않는다.

    🔄 D-254 (런처 전수 감사 §2 data-publish) — ⛔ 종전에는 기기 칸을 안 봤다. 원장은 git 으로 팀원 줄까지 합쳐지므로
       팀원 **한 명**이 재배포 제약 원천을 받으면 정본의 publish 가 「이 기기가 받았다」는 틀린 말로 **영영** 막혔다.
    ★ 파생물은 정본 디스크의 원문으로만 만든다(D-226) — 그러니 볼 것은 「**이 기기 디스크에 그 원문이 있었던 적이
       있는가**」다. 세는 줄 —
         · 기기 칸이 이 기기이거나 `canonical` 이거나 **비었다**(D-250 이전 · 정본의 과거분 · D-250 결정 4)
         · 기기 칸이 다른 팀원이어도 **파일이 이 기기 디스크에 있다**(손으로 옮겼을 수 있다)
       다른 팀원 줄이고 파일도 없으면 세지 않는다 — `raw-publish`·`raw-import` 가 그 원천을 옮기지 않는다(D-71).
    ⛔ 「파생물에 그 행이 실제로 섞였는가」로 가르는 것이 더 정확하지만, 파생물 행마다 원천을 적는 거름(`store.stamp`)이
       전 파생물에 깔렸는지 확인하지 않았다 — 모르는 것으로 풀지 않고 **이 기기가 받았는가**로 막는다 (D-220).
    🚨 이 기기 별칭을 모르면 전부 센다(막는 쪽).
    """
    from collect import registry, store  # noqa: PLC0415

    if not store.MANIFEST.exists():
        return []
    try:
        me: str | None = store.device_id()
    except store.StoreError:
        me = None
    here = {"", store.CANONICAL_DEVICE, me}
    seen: dict[str, set[str]] = {}
    for line in store.MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        who = str(r.get("device") or "")
        path = str(r.get("path") or "").replace("\\", "/")
        on_disk = bool(path) and (ROOT / path).is_file()
        if me is None or who in here or on_disk:
            seen.setdefault(str(r["source_id"]), set()).add(who or "기기 칸 이전")
    bad = []
    for sid in sorted(seen):
        try:
            if not registry.redistributable(sid):
                bad.append(f"{sid} (받은 기기 {sorted(seen[sid])})")
        except registry.RegistryError:
            bad.append(f"{sid} (레지스트리에 없다)")  # 🚨 모르는 것은 막는 쪽 (D-220)
    return bad


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return out.stdout.strip() or "?"
    except OSError:
        return "?"


def manifest_in_head() -> bool | None:
    """작업 트리의 파생물 원장이 **HEAD 의 것과 바이트가 같은가**. 모르면 None.

    🆕 D-254 (런처 전수 감사 §2 data-publish) — ⛔ 기록·화면이 「커밋 X 의 원장과 같다」고 말했는데 X 는 HEAD 이고,
       안내 순서는 **publish 먼저 · 커밋 나중**이라 대개 거짓이었다. 원장 sha 를 적고, HEAD 와 같은지를 따로 말한다.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"HEAD:{dm.OUT.relative_to(ROOT).as_posix()}"],
            capture_output=True,
        )
    except (OSError, ValueError):
        return None
    if out.returncode != 0:
        # HEAD 에 그 파일이 없거나(처음 쓴 원장) git 이 아니다 — 앞의 것은 「커밋 안 됨」이다
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD"], capture_output=True
        )
        return False if probe.returncode == 0 else None
    return hashlib.sha256(out.stdout).hexdigest() == _sha(dm.OUT)


def store_device() -> str:
    from collect import store  # noqa: PLC0415

    return store.device_id()


def publish(*, yes: bool = False, dry_run: bool = False) -> int:
    """🔴 정본만 올린다. 올리기 전에 셋을 본다 — 원장 최신 · 마스킹 잔여 0 · 재배포 제약 0."""
    if dm.role() != "canonical":
        print("🔴 올리지 않는다 — 정본(DATA_ROLE=canonical)만 올린다 (D-226)")
        return 1
    # 🆕 D-250 — 합치지 않은 팀원 원문이 있으면 지금 파생물에 그것이 빠져 있다. 사본에 퍼뜨리지 않는다
    from scripts import raw_inbox  # noqa: PLC0415 — raw_inbox 가 이 모듈을 부른다(순환 회피)

    if raw_inbox.check_pending():
        return 1
    d = dm.diff("canonical")
    if dm.failed("canonical", d):
        keep = [k for k in d["missing"] + d["changed"] if dm._kind(k) in dm.KEEP_KINDS]  # noqa: SLF001
        if keep:
            # 🔄 D-254 — 원천·표본이 없거나 바뀐 것에 「--write」를 권하지 않는다 (그 길로 원장에서 조용히 빠졌다)
            print(
                f"🔴 원천·표본 {len(keep)}개가 없거나 원장과 다르다 — 예: {keep[:3]}\n{dm.RESTORE_HINT}"
            )
            return 1
        print(
            "🔴 파생물 원장이 디스크와 다르다 — 먼저 `launcher.py derived-manifest --write` 후 커밋한다.\n"
            "  🚨 원장과 다른 바이트를 올리면 사본이 받을 수 없다 (sha 가 안 맞는다)"
        )
        return 1
    bad = _noredist_seen()
    if bad:
        print(
            f"🔴 이 기기(정본)가 재배포 제약 소스를 받았다 — {bad}\n"
            "  🚨 저장소는 제3자 계정이다 (D-78 ③). 파생물에 그 행이 섞였을 수 있어 올리지 않는다 (D-71).\n"
            "     행 단위 `redistributable` 거름이 생기기 전까지 막는다"
        )
        return 1
    # 🔴 **개인 식별이 먼저다** (2026-09-19 · 팀장 지적 · D-17). 법인 표기보다 앞에서 멈춘다.
    found = dm.people()
    if found:
        dm._report_people(found)  # noqa: SLF001 — 같은 보고를 두 번 쓰지 않는다 (D-99)
        return 1
    leaked, _cache = dm.leaks()
    if leaked:
        print(
            f"🔴 생성물에 마스킹 잔여가 있다 — {leaked[:5]} (D-17). `derived-manifest --export-check`"
        )
        return 1

    led = dm.ledger()
    # 🆕 2026-09-20 — 개인 식별·마스킹 검사가 **못 읽는 형식**은 올리지 않는다 (0건으로 세지 않는다 · D-72).
    #    ⛔ `.txt` 원문캐시가 「생성물」로 분류돼 이 검사 둘을 건너뛰고 올라갈 수 있었다(런처 자동화 검토 발견 2).
    odd = dm.unscanned(list(led.values()))
    if odd:
        print(
            f"🔴 검사가 못 읽는 형식이 올릴 목록에 있다 — 올리지 않는다 ({len(odd)}개): {odd[:5]}\n"
            "  마스킹 전 원문이면 부류를 원문캐시로(`derived_manifest.KIND_RULES`), 아니면 json/jsonl 로 쓴다"
        )
        return 1
    rows = [r for r in led.values() if dm.moved(str(r["경로"]), str(r["부류"]))]
    bad = unsafe(rows)
    if bad:
        print(f"🔴 원장에 올릴 수 없는 행이 있다: {bad[:5]}")
        return 1
    try:
        root = store_root()
    except StoreError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    new = [r for r in rows if not _obj(root, str(r["sha256"])).is_file()]
    print(
        f"올릴 것 {len(new)}개 · {_size(new)} (원천·표본·생성물 {len(rows)}개 중 · 원문캐시는 안 올린다)\n"
        f"  저장소 {root}"
    )
    if not new:
        print("올릴 것 없음 — 저장소에 이미 다 있다")
        return 0
    if dry_run:
        print("🚨 --dry-run — 아무것도 올리지 않았다")
        return 0
    if not yes and not _ask("🚨 외부 전송이다 (제3자 계정 · D-78 ③). 올릴까"):
        print("멈췄다 — 아무것도 올리지 않았다")
        return 1

    for r in new:
        _put(root, ROOT / str(r["경로"]), str(r["sha256"]))
    in_head = manifest_in_head()
    entry = {
        "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        # 🔄 D-254 — `commit` 은 올린 순간의 HEAD 일 뿐이다. 이 판의 정체는 `manifest_sha256` 이고,
        #    그 원장이 HEAD 에 들어 있었는지는 `manifest_in_head` 가 말한다(None = 모름)
        "commit": _commit(),
        # 🔄 D-250 — PC 이름이 아니라 기기 별칭. 저장소는 팀원(뷰어)이 읽는다
        "device": store_device(),
        "manifest_sha256": _sha(dm.OUT),
        "manifest_in_head": in_head,
        "objects_new": len(new),
        "objects_listed": len(rows),
    }
    with (root / "publish_log.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"올렸다 {len(new)}개 — 원장 sha256 {entry['manifest_sha256'][:16]} 의 판")
    if in_head:
        print(f"  원장이 HEAD({entry['commit']}) 의 것과 같다 — push 하면 사본이 이 판을 받는다")
    else:
        state = (
            "원장 미커밋 — HEAD 와 다르다"
            if in_head is False
            else "HEAD 와 같은지 모른다(git 을 못 읽었다)"
        )
        print(
            f"  🚨 {state}. 원장(`data/derived_manifest.jsonl`)을 **커밋·push 해야** 사본이 이 판을 받는다"
        )
    return 0


# ══════════════════════════════════════════════════════════
# 🆕 설정 — 새 기기가 명령 하나로 받는 쪽이 된다 (2026-09-20 · 팀장 요구)
# ══════════════════════════════════════════════════════════
#  팀장 — *「env 키도 런처 통해서 넣도록 · 팀원이나 클론 A 에서 데이터 받을 때 런처 이용해서 자동화」*
#  ⛔ 종전에는 `.env` 를 편집기로 열어 두 줄을 손으로 적게 했다 — 드라이브 글자(G:/H:/J:)가 기기마다
#     달라 틀리기 쉽고, 틀려도 「폴더가 없다」가 나올 때까지 모른다.
#  ★ 저장소 폴더 이름은 하나로 정한다 — Drive for desktop 이 어느 글자에 붙든 **찾아서** 적는다.
STORE_NAME = "CopyLane_store"
#: Drive for desktop 의 최상위 폴더 이름 — 한국어 · 영어 설정
DRIVE_DIRS = ("내 드라이브", "My Drive")


#: 🆕 D-250 — 수집 팀원의 원문 받은편지함. 저장소와 **다른 폴더**다(쓰는 사람이 다르다) · `scripts/raw_inbox.py` 와 같은 이름
INBOX_NAME = "CopyLane_raw_inbox"
#: 받은편지함 안의 배치 폴더 — 🔄 2026-09-21 `scripts/raw_inbox.py` 에서 이리 옮겼다(그쪽이 이것을 읽는다 · D-99).
#:    `candidates()` 가 바로가기 대상 폴더를 **내용으로** 알아보는 데 쓴다.
INBOX_LAYOUT = "copylane-raw"

#: Drive for desktop 이 **다른 사람이 공유한 폴더의 바로가기** 대상을 실제로 두는 곳 (드라이브 최상위).
#: 🆕 2026-09-21 — ⛔ `내 드라이브` 에 바로가기를 추가해도 그 자리의 항목은 **폴더가 아니다**(`is_dir()` 거짓) —
#:    클론 A 실측: `G:\내 드라이브` 의 폴더 목록에 `CopyLane_store` 가 없고, 내용은
#:    `G:\.shortcut-targets-by-id\<폴더 id>\copylane-derived` 에 있었다. 그래서 `data-setup` 이 「못 찾았다」로 멈췄고
#:    사람이 `--store` 로 id 경로를 손으로 줬다. 안내서 ②(바로가기 추가)를 따른 팀원이 전부 밟는 자리다.
#: 🆕 2026-09-21 (D-256) — 정본 원문 **거울**. 팀장 계정에만 공유한다 — 원문은 마스킹 전이다. `scripts/raw_mirror.py` 가 읽는다
MIRROR_NAME = "CopyLane_raw_mirror"
MIRROR_LAYOUT = "copylane-raw-mirror"
SHORTCUT_TARGETS = ".shortcut-targets-by-id"
#: 이름 → 그 폴더 안에 있어야 하는 배치 폴더. id 폴더에는 원래 이름이 안 남으므로 **내용으로** 알아본다.
SIGNATURE: dict[str, str] = {
    STORE_NAME: LAYOUT,
    INBOX_NAME: INBOX_LAYOUT,
    MIRROR_NAME: MIRROR_LAYOUT,
}


def default_roots(home: pathlib.Path) -> list[pathlib.Path]:
    """Windows 가 아닌 기기의 Drive 위치 후보.

    🆕 2026-09-20 (받는 쪽 점검) — ⛔ 종전에는 `~` · `~/Google Drive` 만 봤다. 지금 Mac 의 Drive for desktop 은
       `~/Library/CloudStorage/GoogleDrive-<계정>/` 아래에 `My Drive`(`내 드라이브`) 를 붙인다 — 계정마다 하나씩.
    """
    cloud = home / "Library" / "CloudStorage"
    try:
        drives = sorted(cloud.glob("GoogleDrive-*")) if cloud.is_dir() else []
    except OSError:
        drives = []
    return [home, home / "Google Drive", *drives]


def candidates(
    roots: list[pathlib.Path] | None = None, name: str = STORE_NAME
) -> list[pathlib.Path]:
    """이 기기에 붙은 공유 폴더 후보. 🚨 네트워크를 쓰지 않는다 — 붙은 드라이브만 본다."""
    if roots is None:
        if os.name == "nt":
            roots = [pathlib.Path(f"{c}:\\") for c in string.ascii_uppercase if c not in "AB"]
        else:
            roots = default_roots(pathlib.Path.home())
    out: list[pathlib.Path] = []
    for r in roots:
        for d in DRIVE_DIRS:
            p = r / d / name
            try:
                if p.is_dir():
                    out.append(p)
            except OSError:  # 빈 카드 리더 같은 자리 — 없는 것으로 친다
                continue
        out += _shortcut_targets(r, name)
    return out


def _shortcut_targets(root: pathlib.Path, name: str) -> list[pathlib.Path]:
    """🆕 2026-09-21 — 바로가기 대상 폴더(`<드라이브>/.shortcut-targets-by-id/<id>`) 중 `name` 인 것.

    ★ 두 모양을 다 본다 — ① id 폴더 안에 `name` 폴더가 있다 ② id 폴더 **자체**가 그 폴더다(원래 이름이 안 남는다 —
      클론 A 실측). ②는 이름으로 못 알아보므로 **안에 배치 폴더(`SIGNATURE`)가 있는지**로 본다.
    🚨 그래서 한 번도 올린 적 없는 **빈** 저장소는 ②로 못 찾는다 — 그때는 안내대로 `--store` 로 준다.
    ⛔ 파일을 열지 않는다 — 이름과 폴더인지만 본다. 드라이브 동기화 앱이 파일을 내려받게 만들지 않는다.
    """
    base = root / SHORTCUT_TARGETS
    sig = SIGNATURE.get(name)
    found: list[pathlib.Path] = []
    try:
        if not base.is_dir():
            return []
        for c in sorted(base.iterdir()):
            if not c.is_dir():
                continue
            if (c / name).is_dir():
                found.append(c / name)
            elif sig and (c / sig).is_dir():
                found.append(c)
    except OSError:
        return found
    return found


def setup(
    *,
    role: str | None = None,
    store: str | None = None,
    yes: bool = False,
    inbox: str | None = None,
    device: str | None = None,
    mirror: str | None = None,
) -> int:
    """🆕 역할과 저장소를 `.env` 에 적고, 받는 쪽이면 **바로 받는다**.

    🔴 정본(canonical)은 **클론 B 한 곳**이다 (D-226) — 고르면 한 번 더 묻는다.
    🚨 쓰는 곳은 `collect.setkey.put_setting()` 하나다 — `.env` 를 여는 곳을 늘리지 않는다 (D-99).
    """
    from collect import env, setkey  # noqa: PLC0415

    now_role, now_store = env.setting("DATA_ROLE"), env.setting("DATA_STORE")
    if role is None:
        dflt = now_role or "replica"
        if yes:
            role = dflt
        else:
            print(
                "역할을 고른다 —\n"
                "  replica    받는 쪽 — 클론 A · 팀원 · 서버 (대부분 이것)\n"
                "  canonical  만드는 쪽 — 🔴 클론 B 한 곳만"
            )
            try:
                role = input(f"역할 [{dflt}] > ").strip() or dflt
            except EOFError:
                role = dflt
    if role not in dm.ROLES:
        print(f"🔴 모르는 역할 {role!r} — 아는 것은 {list(dm.ROLES)} (D-220)")
        return 1
    first_canon = role == "canonical" and not yes and now_role != "canonical"
    if first_canon and not _ask("🔴 정본은 클론 B 한 곳이다. 이 기기가 클론 B 인가"):
        print("멈췄다 — .env 는 그대로다")
        return 1

    if store:
        chosen = pathlib.Path(store).expanduser()
    else:
        found = candidates()
        if not found:
            print(
                f"🔴 공유 저장소 폴더 `{STORE_NAME}` 를 못 찾았다 — .env 는 그대로다.\n"
                "  ① Google Drive for desktop 을 설치하고 **초대받은 계정**으로 로그인한다\n"
                f"  ② drive.google.com → 공유 문서함 → `{STORE_NAME}` 우클릭 → 바로가기 추가 → 내 드라이브\n"
                "  ③ 탐색기에 `<글자>:\\내 드라이브\\CopyLane_store` 가 보이면 다시 실행한다\n"
                f"     🚨 바로가기 대상은 `<글자>:\\{SHORTCUT_TARGETS}\\<폴더 id>` 에 있다 — 여기도 찾아봤다.\n"
                "        빈 저장소(한 번도 올린 적 없음)는 내용으로 못 알아본다 — 그 폴더를 `--store` 로 준다\n"
                "  (다른 곳이면 `--store <폴더>` 로 준다)"
            )
            return 1
        if len(found) == 1 or yes:
            chosen = found[0]
        else:
            for i, p in enumerate(found, 1):
                print(f"  {i}. {p}")
            try:
                k = int(input("몇 번 > ").strip() or "1")
                chosen = found[k - 1]
            except (ValueError, IndexError, EOFError):
                print("멈췄다 — .env 는 그대로다")
                return 1
    if not chosen.is_dir():
        print(f"🔴 폴더가 없다 — {chosen}. .env 는 그대로다")
        return 1

    from collect import store as cstore  # noqa: PLC0415 — 모양의 정본은 store 한 곳 (D-99)

    # 🔄 2026-09-21 — 판정은 `store.device_problem` 한 곳 (D-99). 지금 쓰려는 `role` 로 잰다.
    why = cstore.device_problem(device, role) if device is not None else None
    if why:
        print(
            f"🔴 기기 이름 {device!r} 은 못 쓴다 — {why}.\n"
            "  🚨 원장은 공개 저장소에 올라간다 — **실명을 쓰지 않는다**. .env 는 그대로다"
        )
        return 1
    # 🆕 D-250 — 받은편지함은 **수집 팀원·정본만** 붙인다. 뷰어는 공유받지 않았으니 못 찾는 것이 정상이다
    box = pathlib.Path(inbox).expanduser() if inbox else None
    if box is None:
        found_box = candidates(name=INBOX_NAME)
        box = found_box[0] if found_box else None
    elif not box.is_dir():
        print(f"🔴 받은편지함 폴더가 없다 — {box}. .env 는 그대로다")
        return 1
    # 🆕 D-256 — 원문 거울은 **팀장 계정에만** 공유된다 — 다른 기기는 못 찾는 것이 정상이다
    mir = pathlib.Path(mirror).expanduser() if mirror else None
    if mir is None:
        found_mir = candidates(name=MIRROR_NAME)
        mir = found_mir[0] if found_mir else None
    elif not mir.is_dir():
        print(f"🔴 원문 거울 폴더가 없다 — {mir}. .env 는 그대로다")
        return 1
    if mir is not None and mir.resolve() in {chosen.resolve(), *([box.resolve()] if box else [])}:
        print(
            "🔴 원문 거울이 저장소·받은편지함과 같은 폴더다 — 마스킹 전 원문이 섞인다 (D-256). .env 는 그대로다"
        )
        return 1

    setkey.put_setting("DATA_ROLE", role)
    setkey.put_setting("DATA_STORE", str(chosen))
    print(f"  .env — DATA_ROLE={role} (전: {now_role or '없음'})")
    print(f"  .env — DATA_STORE={chosen} (전: {now_store or '없음'})")
    if box is not None:
        setkey.put_setting("RAW_INBOX", str(box))
        print(f"  .env — RAW_INBOX={box} (원문 받은편지함 · D-250)")
    if device:
        setkey.put_setting("DATA_DEVICE", device)
        print(f"  .env — DATA_DEVICE={device}")
    if mir is not None:
        setkey.put_setting("RAW_MIRROR", str(mir))
        print(f"  .env — RAW_MIRROR={mir} (정본 원문 거울 · 팀장 기기 · D-256)")

    if role == "canonical":
        print("  다음 — `launcher.py data-publish --dry-run` 으로 무엇이 올라갈지 본다")
        return 0
    if not (chosen / LAYOUT / "publish_log.jsonl").is_file():
        print(
            "  🟡 저장소에 아직 올라온 판이 없다 — 정본(클론 B)이 `data-publish` 를 한 뒤에 받는다.\n"
            "     그 뒤로는 `load`·`chunk`·`embed`·`search-probe` 가 부족분을 **스스로 받는다** (D-247)"
        )
        return 0
    print("  받는다 — 이 커밋의 원장대로 (D-247)")
    return sync(yes=yes)


# ══════════════════════════════════════════════════════════
# 런처가 데이터 명령 앞에서 부르는 것 (판정 ③)
# ══════════════════════════════════════════════════════════
def ensure() -> int:
    """사본이면 부족분을 받고, 아니면 아무것도 안 한다. 🔴 받지 못하면 1 — 그 명령을 멈춘다."""
    who = dm.role()
    if who != "replica":
        return 0
    if not plan():
        return 0
    print("🔄 이 명령이 읽는 파생물이 부족하거나 옛 판이다 — 먼저 받는다 (D-247)")
    return sync()


def main() -> int:
    ap = argparse.ArgumentParser(description="부족한 파생물을 공유 저장소에서 받는다 (D-247)")
    ap.add_argument("cmd", choices=["plan", "sync", "publish", "ensure", "setup"])
    ap.add_argument("--role", default=None, help="setup — canonical | replica")
    ap.add_argument("--store", default=None, help="setup — 저장소 폴더 (비우면 찾는다)")
    ap.add_argument("--inbox", default=None, help="setup — 원문 받은편지함 (비우면 찾는다 · D-250)")
    ap.add_argument("--device", default=None, help="setup — 이 기기 이름 (실명 금지 · D-250)")
    ap.add_argument("--mirror", default=None, help="setup — 원문 거울 (비우면 찾는다 · D-256)")
    ap.add_argument("--yes", action="store_true", help="묻지 않는다")
    ap.add_argument("--dry-run", action="store_true", help="무엇을 할지만 보여 준다")
    a = ap.parse_args()
    if a.cmd == "plan":
        todo = plan()
        print(f"역할 {dm.role() or '없음'} · 부족 {len(todo)}개 · {_size(todo)}")
        for r in todo:
            print(f"    {r['경로']}")
        return 0
    if a.cmd == "sync":
        return sync(yes=a.yes, dry_run=a.dry_run)
    if a.cmd == "publish":
        return publish(yes=a.yes, dry_run=a.dry_run)
    if a.cmd == "setup":
        return setup(
            role=a.role, store=a.store, yes=a.yes, inbox=a.inbox, device=a.device, mirror=a.mirror
        )
    return ensure()


if __name__ == "__main__":
    raise SystemExit(main())
