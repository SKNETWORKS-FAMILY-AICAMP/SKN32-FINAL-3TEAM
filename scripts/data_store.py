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

🚨 **옮기는 것은 생성물뿐이다.** 원천·표본은 git 이 옮기고(D-244), 원문캐시는 **옮기지 않는다**
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
import shutil
import socket
import subprocess
import sys

from scripts import derived_manifest as dm

ROOT = dm.ROOT
LAYOUT = "copylane-derived"
#: 사본이 덮어쓸 때 옛 파일을 옮겨 두는 곳 — **레포 밖**이다 (git status 에 안 뜬다)
BACKUP = ROOT.parent / "CopyLane_backup"
#: 🚨 `data/raw` 가 **있는지만** 본다 — 열지 않는다. `RAW_EXCEPTIONS` 에 이유와 함께 적었다.
RAW_MARK = ROOT / "data" / "raw"
#: 🚨 저장소가 옮기는 부류는 이것 하나다 — 이름의 정본은 dm.KIND_RULES / DEFAULT_KIND
MOVED = "생성물"
assert MOVED == dm.DEFAULT_KIND, "생성물 부류 이름이 derived_manifest 와 갈렸다 (D-99)"


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


def _obj(root: pathlib.Path, sha: str) -> pathlib.Path:
    return root / "objects" / sha[:2] / sha


def _sha(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _copy_verified(src: pathlib.Path, dest: pathlib.Path, sha: str) -> None:
    """임시 이름으로 복사 → sha 확인 → 제자리로. 🚨 **반쯤 쓴 파일이 제자리에 남지 않는다.**

    ⛔ 동기화 폴더는 「아직 다 안 내려온 파일」을 보여 줄 수 있다. sha 가 안 맞으면 놓지 않는다.
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
    os.replace(tmp, dest)


def _get(root: pathlib.Path, sha: str, dest: pathlib.Path) -> None:
    src = _obj(root, sha)
    if not src.is_file():
        raise StoreError(
            f"저장소에 {sha[:16]} 이 없다 — 정본에서 `data-publish` 를 안 했을 수 있다"
        )
    _copy_verified(src, dest, sha)


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

    🚨 원천·표본이 다르면 여기 넣지 않는다 — **git 이 옮기는 파일**이다. 저장소에서 받아 덮으면
       git 과 두 벌이 된다. `diff` 가 그것을 따로 알려 준다(`git_side`).
    """
    led = dm.ledger()
    d = dm.diff("replica")
    want = [p for p in d["missing"] + d["changed"] if led[p]["부류"] == MOVED]
    return [led[p] for p in sorted(want)]


def git_side() -> list[str]:
    """원천·표본인데 이 기기와 다른 것 — `git pull`/`git status` 의 일이다."""
    led = dm.ledger()
    d = dm.diff("replica")
    return [p for p in d["missing"] + d["changed"] if led[p]["부류"] in ("원천", "표본")]


def _size(rows: list[dict[str, object]]) -> str:
    n = sum(int(r["bytes"]) for r in rows)  # type: ignore[arg-type]
    return f"{n / 1024 / 1024:,.1f} MB"


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
    if dry_run:
        print("🚨 --dry-run — 아무것도 받지 않았다")
        return 0

    try:
        root = store_root()
        # 🔴 **먼저 전부 있는지 본다** — 반만 받고 멈추면 파생물이 두 판으로 섞인다.
        lack = [r for r in todo if not _obj(root, str(r["sha256"])).is_file()]
    except StoreError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    if lack:
        print(f"🔴 저장소에 없는 것 {len(lack)}개 — 아무것도 받지 않았다", file=sys.stderr)
        for r in lack[:10]:
            print(f"    {r['경로']}  {str(r['sha256'])[:16]}", file=sys.stderr)
        print(
            "  🚨 정본(클론 B)에서 `launcher.py data-publish` 를 했는지 확인한다", file=sys.stderr
        )
        return 1

    # 🚨 raw 가 있는 기기에서 덮어쓸 때는 **한 번 묻는다** — 클론 B 의 DATA_ROLE 이 틀렸을 수 있다.
    if over and RAW_MARK.is_dir() and not yes:
        print(
            f"\n⚠️ 이 기기에는 원문(data/raw)이 있다. 옛 판 {len(over)}개를 저장소 판으로 바꾼다.\n"
            "   클론 A 라면 맞다. 🔴 **클론 B(정본)라면 DATA_ROLE 이 틀렸다** — 방금 만든 것이 옛 판으로 돌아간다."
        )
        if not _ask("계속할까"):
            print("멈췄다 — 아무것도 바꾸지 않았다")
            return 1

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for r in todo:
        dest = ROOT / str(r["경로"])
        if dest.exists():
            keep = BACKUP / stamp / str(r["경로"])
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, keep)
        try:
            _get(root, str(r["sha256"]), dest)
        except StoreError as e:
            print(f"🔴 {e}", file=sys.stderr)
            print(f"  옛 파일은 {BACKUP / stamp} 에 있다", file=sys.stderr)
            return 1
    if over:
        print(f"  옛 판 {len(over)}개는 {BACKUP / stamp} 로 옮겨 두었다 (되돌릴 수 있다)")
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
    """이 기기가 **받은 적 있는** 재배포 제약 소스 — 수집 원장(git)에서 본다. 원문은 열지 않는다."""
    from collect import registry, store  # noqa: PLC0415

    if not store.MANIFEST.exists():
        return []
    seen: set[str] = set()
    for line in store.MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            seen.add(json.loads(line)["source_id"])
    bad = []
    for sid in sorted(seen):
        try:
            if not registry.redistributable(sid):
                bad.append(sid)
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


def publish(*, yes: bool = False, dry_run: bool = False) -> int:
    """🔴 정본만 올린다. 올리기 전에 셋을 본다 — 원장 최신 · 마스킹 잔여 0 · 재배포 제약 0."""
    if dm.role() != "canonical":
        print("🔴 올리지 않는다 — 정본(DATA_ROLE=canonical)만 올린다 (D-226)")
        return 1
    d = dm.diff("canonical")
    if dm.failed("canonical", d):
        print(
            "🔴 파생물 원장이 디스크와 다르다 — 먼저 `launcher.py derived-manifest --write` 후 커밋한다.\n"
            "  🚨 원장과 다른 바이트를 올리면 사본이 받을 수 없다 (sha 가 안 맞는다)"
        )
        return 1
    bad = _noredist_seen()
    if bad:
        print(
            f"🔴 재배포 제약 소스를 받은 기기다 — {bad}\n"
            "  🚨 저장소는 제3자 계정이다 (D-78 ③). 파생물에 그 행이 섞였을 수 있어 올리지 않는다 (D-71).\n"
            "     행 단위 `redistributable` 거름이 생기기 전까지 막는다"
        )
        return 1
    leaked, _cache = dm.leaks()
    if leaked:
        print(
            f"🔴 생성물에 마스킹 잔여가 있다 — {leaked[:5]} (D-17). `derived-manifest --export-check`"
        )
        return 1

    led = dm.ledger()
    rows = [r for r in led.values() if r["부류"] == MOVED]
    try:
        root = store_root()
    except StoreError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    new = [r for r in rows if not _obj(root, str(r["sha256"])).is_file()]
    print(
        f"올릴 것 {len(new)}개 · {_size(new)} (생성물 {len(rows)}개 중 · 원천·표본은 git · 원문캐시는 안 올린다)\n"
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
    entry = {
        "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "device": socket.gethostname(),
        "manifest_sha256": _sha(dm.OUT),
        "objects_new": len(new),
        "objects_listed": len(rows),
    }
    with (root / "publish_log.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"올렸다 {len(new)}개 — 커밋 {entry['commit']} 의 원장과 같다")
    print("  🚨 원장(`data/derived_manifest.jsonl`)을 **커밋·push 해야** 사본이 이 판을 받는다")
    return 0


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
    ap.add_argument("cmd", choices=["plan", "sync", "publish", "ensure"])
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
    return ensure()


if __name__ == "__main__":
    raise SystemExit(main())
