"""scripts/raw_mirror.py — 정본 원문을 **팀장 기기**에 읽기용으로 비춘다 (2026-09-21 · D-256).

  uv run python -m scripts.raw_mirror publish [--dry-run] [--yes]   # 정본(클론 B) — 원문 거울에 올린다
  uv run python -m scripts.raw_mirror sync    [--dry-run] [--yes]   # 사본(클론 A) — 거울을 받아 정본과 같게 한다
  uv run python -m scripts.raw_mirror plan                          # 무엇이 다른가 (쓰지 않는다)

팀장 — *「원문이 있어야 프로젝트 작업에 이해도가 올라가는 것 아닌가」* → 대안 (나) 판정 (2026-09-21).
⛔ 종전에는 원문이 **팀원 → 정본** 한 방향으로만 흘렀다(D-250). 정본에서 사본으로 가는 길은 누가 막은 것이
   아니라 **정한 적이 없는 자리**였다(D-226 은 파생물의 출처를, D-247 은 파생물의 전달을 정했다).
   그래서 클론 A 에서는 마스킹 고침의 영향을 못 재고 B 로 넘겼다 — 원문이 없거나 옛 판이었다.

★ **무엇을 하는가** — 정본 디스크의 원문(원장 경로 중 **실제로 있는 것**)을 sha256 이름으로 거울 폴더에 두고,
  그 순간의 `경로 → sha` 목록(`index.jsonl`)을 같이 둔다. 사본은 목록대로 받아 **정본 디스크와 같아진다.**
★ **무엇을 하지 않는가**
  · 사본은 여전히 파생물을 만들지 않는다 (D-226). 원문은 **읽고 미리보기**(`extract <id> --preview`)에만 쓴다
  · 팀원 기기에는 주지 않는다 — 원문은 **마스킹 전**이다(공정위 의결서의 피심인 실명 등). 거울 폴더는 팀장 계정에만 공유한다
  · G2(추출 뒤 원문을 지운다 · D-92) · 재배포 제약(D-71 · AI Hub 포함) · 레지스트리에 없는 원천은 **올리지 않는다**
🚨 거울 폴더는 **제3자 계정**이다 (D-78 ③) — 올리기는 외부 전송이라 한 번 묻는다. 키가 섞인 원문이 하나라도 있으면
   **하나도 올리지 않는다**(받은편지함과 같은 검사 · 같은 함수).
🚨 받을 때 사본의 옛 원문이 정본과 다르면 **레포 밖에 복사해 두고** 바꾼다(`CopyLane_backup/raw-<시각>`).
   사본의 원문은 정본이 아니다 — 판을 고르는 것은 정본의 `adopt` 다(D-246). 사본에서 원장은 안 바뀐다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys

from scripts import data_store as ds
from scripts import derived_manifest as dm
from scripts import raw_inbox as ri

ROOT = dm.ROOT
MIRROR_NAME = ds.MIRROR_NAME
LAYOUT = ds.MIRROR_LAYOUT
INDEX = "index.jsonl"
LOG = "mirror_log.jsonl"


class MirrorError(RuntimeError):
    """거울을 쓸 수 없거나 규칙을 어겼다."""


def mirror_root() -> pathlib.Path:
    """`.env` 의 `RAW_MIRROR` 아래 배치 폴더. 🔴 없으면 멈춘다 — 조용히 「받을 것 없음」으로 끝내지 않는다.

    🚨 팀 공유 저장소·받은편지함과 **같은 폴더면 멈춘다** — 마스킹 전 원문이 팀원이 읽는 곳에 놓인다.
    """
    from collect import env  # noqa: PLC0415 — `.env` 를 여는 곳은 한 곳이다 (D-99)

    raw = env.setting("RAW_MIRROR")
    if not raw:
        raise MirrorError(
            "RAW_MIRROR 가 비어 있다 — 원문 거울 폴더를 모른다.\n"
            f"  `launcher.py data-setup` 이 `{MIRROR_NAME}` 를 찾아 적는다 (팀장 계정에 공유된 기기만 보인다)"
        )
    root = pathlib.Path(raw).expanduser()
    if not root.is_dir():
        raise MirrorError(f"RAW_MIRROR 폴더가 없다 — {root}. 드라이브가 붙었는지 본다")
    for other in ("DATA_STORE", "RAW_INBOX"):
        o = env.setting(other)
        if o and pathlib.Path(o).expanduser().resolve() == root.resolve():
            raise MirrorError(
                f"RAW_MIRROR 가 {other} 와 같은 폴더다 — 🔴 마스킹 전 원문이 팀원이 읽는 곳에 놓인다.\n"
                f"  `{MIRROR_NAME}` 는 따로 만들고 **팀장 계정에만** 공유한다 (D-256)"
            )
    return root / LAYOUT


def _index_path(root: pathlib.Path) -> pathlib.Path:
    return root / INDEX


def read_index(root: pathlib.Path) -> list[dict]:
    p = _index_path(root)
    if not p.is_file():
        raise MirrorError(
            f"거울 목록이 없다 — {p}\n  정본(클론 B)에서 `launcher.py raw-mirror-publish` 를 했는지 본다"
        )
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def snapshot() -> tuple[list[dict], dict[str, list[str]]]:
    """정본 디스크의 원문 — 원장 경로(경로마다 마지막 행) 중 **실제로 있는 것**의 `경로·sha·크기·원천`.

    🚨 sha 는 원장이 아니라 **디스크 파일**에서 잰다 — 거울은 「정본 디스크의 지금」이다. 원장의 sha 와 다르면
       (원본이 바뀐 것 · 규약 2) 그 경로는 올리지 않고 이유를 돌려준다 — `doctor --data --hash` 가 볼 일이다.
    돌려주는 값 — (올릴 행, 이유별 뺀 경로). 이유: g2 · noredist · unknown · changed
    """
    rows = ri._local_ledger()  # noqa: SLF001 — 원장을 읽는 곳을 늘리지 않는다 (D-99)
    known_sha: dict[str, set[str]] = {}
    for r in rows:
        known_sha.setdefault(ri._path_of(r), set()).add(str(r.get("sha256") or ""))  # noqa: SLF001
    out: list[dict] = []
    held: dict[str, list[str]] = {"g2": [], "noredist": [], "unknown": [], "changed": []}
    for p, r in sorted(ri._last(rows).items()):  # noqa: SLF001
        f = ROOT / p
        if not f.is_file():
            continue
        sid = str(r.get("source_id") or "")
        why = ri._held_back(sid)  # noqa: SLF001 — 받은편지함과 같은 거름 (D-99)
        if why:
            held[why].append(p)
            continue
        sha = ds._sha(f)  # noqa: SLF001
        if sha not in known_sha.get(p, set()):
            held["changed"].append(p)
            continue
        out.append({"path": p, "sha256": sha, "bytes": f.stat().st_size, "source_id": sid})
    return out, held


def publish(*, yes: bool = False, dry_run: bool = False) -> int:
    """정본 — 디스크의 원문을 거울에 올리고 목록을 새로 쓴다."""
    if dm.role() != "canonical":
        print(
            "🔴 정본(DATA_ROLE=canonical)만 거울에 올린다 — 거울은 정본 디스크의 사본이다 (D-256)"
        )
        return 1
    try:
        root = mirror_root()
    except MirrorError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    rows, held = snapshot()
    bad = ri.unsafe(rows)
    if bad:
        print(f"🔴 원장에 올릴 수 없는 경로가 있다 — 아무것도 올리지 않았다: {bad[:5]}")
        return 1
    for name, label in (
        ("g2", "G2 — 추출 뒤 원문을 지운다 (D-92)"),
        ("noredist", "재배포 제약 (D-71 · AI Hub 포함)"),
        ("unknown", "레지스트리에 없는 원천 (D-220)"),
    ):
        if held[name]:
            print(f"  ⬜ {label} {len(held[name])}개는 올리지 않는다 · 예: {held[name][:2]}")
    if held["changed"]:
        print(
            f"  🟡 원장의 어느 sha 와도 다른 원문 {len(held['changed'])}개는 올리지 않는다 — 원본이 바뀌었다(규약 2)\n"
            f"     `uv run python scripts/doctor.py --data --hash` 로 본다 · 예: {held['changed'][:2]}"
        )
    new = [r for r in rows if not ds.object_ok(ri._obj(root, r["sha256"]), r["bytes"])]  # noqa: SLF001
    leaked = []
    for r in new:
        why = ri.secret_in((ROOT / r["path"]).read_bytes())
        if why:
            leaked.append(f"{r['path']} ({why})")
    if leaked:
        print(f"🔴 **키가 섞인 원문**이 있다 — 아무것도 올리지 않았다 ({len(leaked)}개):")
        for x in leaked[:10]:
            print(f"    {x}")
        print("  🚨 그 파일을 지우고 수집기를 고친 뒤 다시 받는다. 키 재발급 여부는 팀장 판정이다")
        return 1
    size = sum(r["bytes"] for r in new) / 1024 / 1024
    print(f"거울 — 원문 {len(rows):,}개 중 새로 올릴 것 {len(new):,}개 · {size:,.1f} MiB\n  {root}")
    if dry_run:
        print("🚨 --dry-run — 아무것도 올리지 않았다 (목록도 안 바꿨다)")
        return 0
    if not yes and not ds._ask(  # noqa: SLF001
        "🚨 외부 전송이다 — 마스킹 전 원문을 팀장 전용 거울에 올린다 (D-78 ③ · D-256). 올릴까"
    ):
        print("멈췄다")
        return 1
    for r in new:
        ds._copy_verified(ROOT / r["path"], ri._obj(root, r["sha256"]), r["sha256"])  # noqa: SLF001
    # 🚨 목록은 **객체를 다 올린 뒤** 바꿔 끼운다 — 목록이 먼저 바뀌면 사본이 「거울에 없음」으로 멈춘다
    tmp = _index_path(root).with_name(INDEX + ".part")
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, _index_path(root))
    with (root / LOG).open("a", encoding="utf-8", newline="\n") as f:
        f.write(
            json.dumps(
                {
                    "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    "files": len(rows),
                    "objects_new": len(new),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    print(
        f"올렸다 {len(new):,}개 · 목록 {len(rows):,}개. 사본은 `launcher.py raw-mirror-sync` 로 받는다"
    )
    return 0


def plan(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """거울 목록 대비 이 기기에서 **받을 것** — (없는 것, 내용이 다른 것). 🚨 크기가 같을 때만 sha 를 잰다."""
    missing, differ = [], []
    for e in entries:
        f = ROOT / e["path"]
        if not f.is_file():
            missing.append(e)
        elif f.stat().st_size != int(e["bytes"]) or ds._sha(f) != e["sha256"]:  # noqa: SLF001
            differ.append(e)
    return missing, differ


def sync(*, yes: bool = False, dry_run: bool = False) -> int:
    """사본 — 거울 목록대로 원문을 받는다. 파생물은 안 건드린다."""
    who = dm.role()
    if who != "replica":
        print(
            "🔴 사본(DATA_ROLE=replica)만 거울을 받는다 — "
            + ("정본은 원문의 출처다 (D-256)" if who == "canonical" else "역할이 없다 (data-setup)")
        )
        return 1
    try:
        root = mirror_root()
        entries = read_index(root)
    except MirrorError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    bad = ri.unsafe(entries)
    # 🔴 목록에 올 수 없는 원천이 있으면 받지 않는다 — 정본의 거름을 믿지 않고 여기서 다시 본다 (D-220)
    held = [e["path"] for e in entries if ri._held_back(str(e.get("source_id") or ""))]  # noqa: SLF001
    if bad or held:
        print(f"🔴 거울 목록에 받을 수 없는 행이 있다 — 아무것도 받지 않았다: {(bad + held)[:5]}")
        return 1
    missing, differ = plan(entries)
    todo = missing + differ
    lack = [e for e in todo if not ds.object_ok(ri._obj(root, e["sha256"]), e["bytes"])]  # noqa: SLF001
    size = sum(int(e["bytes"]) for e in todo) / 1024 / 1024
    print(
        f"거울 목록 {len(entries):,}개 — 받을 것 {len(todo):,}개 · {size:,.1f} MiB "
        f"(새로 {len(missing):,} · 옛 판 교체 {len(differ):,})"
    )
    if lack:
        print(
            f"🔴 거울에 없는 객체 {len(lack)}개 — 아무것도 받지 않았다 · 예: {[e['path'] for e in lack[:3]]}"
        )
        print("  🚨 정본이 올리는 중이었을 수 있다 — 잠시 뒤 다시 한다")
        return 1
    if not todo:
        print("받을 것 없음 — 이 기기의 원문이 정본 거울과 같다")
        return 0
    if dry_run:
        print("🚨 --dry-run — 아무것도 받지 않았다")
        return 0
    if differ and not yes:
        print(
            f"\n⚠️ 이 기기의 원문 {len(differ)}개가 정본과 다르다 — 레포 밖에 복사해 두고 정본 판으로 바꾼다.\n"
            "   사본의 원문은 정본이 아니다 (D-226). 🔴 이 기기가 클론 B 라면 DATA_ROLE 이 틀렸다."
        )
        if not ds._ask("계속할까"):  # noqa: SLF001
            print("멈췄다 — 아무것도 바꾸지 않았다")
            return 1
    # 두 단계 — 전부 임시 파일로 받아 sha 를 맞춘 뒤에만 바꿔 끼운다 (data_store.sync 와 같다 · D-99)
    staged: list[tuple[pathlib.Path, pathlib.Path, dict]] = []
    try:
        for e in todo:
            dest = ROOT / e["path"]
            staged.append((ds._stage(ri._obj(root, e["sha256"]), dest, e["sha256"]), dest, e))  # noqa: SLF001
    except (ds.StoreError, OSError) as err:
        for tmp, _d, _e in staged:
            tmp.unlink(missing_ok=True)
        print(f"🔴 {err}\n  ⬜ 아무것도 바꾸지 않았다 — 받은 임시 파일은 지웠다", file=sys.stderr)
        return 1
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    keep_root = ds.BACKUP / f"raw-{stamp}"
    for tmp, dest, e in staged:
        if dest.exists():
            keep = keep_root / e["path"]
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, keep)
        os.replace(tmp, dest)
    if differ:
        print(f"  옛 원문 {len(differ)}개는 {keep_root} 에 복사해 두었다")
    left_missing, left_differ = plan(entries)
    if left_missing or left_differ:
        print(
            f"🔴 받은 뒤에도 {len(left_missing) + len(left_differ)}개가 거울과 다르다",
            file=sys.stderr,
        )
        return 1
    print(
        f"받았다 {len(todo):,}개 — 이 기기의 원문이 정본 거울과 같다.\n"
        "  미리보기: uv run python launcher.py extract <원천> --preview   (파생물은 안 바꾼다)"
    )
    return 0


def show_plan() -> int:
    try:
        entries = read_index(mirror_root())
    except MirrorError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    missing, differ = plan(entries)
    print(
        f"거울 목록 {len(entries):,}개 · 이 기기에 없는 것 {len(missing):,} · 내용이 다른 것 {len(differ):,}"
    )
    return 0


def main() -> int:
    dm._utf8_out()  # noqa: SLF001
    ap = argparse.ArgumentParser(description="정본 원문 거울 — 팀장 기기 읽기용 (D-256)")
    ap.add_argument("cmd", choices=["publish", "sync", "plan"])
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "publish":
        return publish(yes=a.yes, dry_run=a.dry_run)
    if a.cmd == "sync":
        return sync(yes=a.yes, dry_run=a.dry_run)
    return show_plan()


if __name__ == "__main__":
    raise SystemExit(main())
