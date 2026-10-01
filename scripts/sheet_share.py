#!/usr/bin/env python3
"""sheet_share.py — **사람이 채우는 판정표 · 감사표를 공유 저장소에 둔다** (2026-10-01 · 팀장 판정 (나)).

  uv run python -m scripts.sheet_share push [--dry-run]   # build/labels 의 빈 표 → 저장소 (채우는 중인 표는 덮지 않는다)
  uv run python -m scripts.sheet_share status             # 저장소의 표 · 채운 행 수 · 들여오는 명령

★ **왜 있나** — 판정표 · 감사표는 `build/labels/` 에 생긴다. git 도 저장소도 나르지 않는 자리라
  ① 사람이 채운 CSV 가 **들여오기 전까지 한 기기에만** 있었다(백업 없음 · 실수한 rebuild 가 덮을 수 있다)
  ② 들여오기(`*-import-decisions` · `*-audit`)는 정본(클론 B)에서만 하는데 **다른 기기에서 채우면 옮길 길이 없었다**
  → 표를 저장소의 `copylane-sheets/` 에 두고 **어느 기기에서든 거기서 채운다.** 정본은 거기서 바로 들여온다(`--csv <경로>`).

    <DATA_STORE>/copylane-sheets/<build/labels 아래 상대 경로>
    <DATA_STORE>/copylane-sheets/_old/<시각>/<상대 경로>        ← 빈 표를 새 판으로 바꿀 때 옛 판

🔴 **표의 정의 — 머리줄에 `판정자` 칸이 있는 CSV** (사람이 적는 칸 · D-66 · `_import_sheet` · `_audit` 이 그 칸으로 받는다).
   ⛔ 이름 목록을 따로 적지 않는다 — 새 판의 표가 생기면 목록이 낡는다 (D-99).
🔴 **채운 표는 덮지 않는다** — 저장소 쪽에 `판정자` 가 적힌 행이 하나라도 있으면 그 파일은 건너뛰고 이름을 낸다.
   빈 표(판정자 0)만 새 판으로 바꾸고, 옛 판은 `_old/` 에 둔다 (D-220 · 사람의 작업을 잃지 않는다).
🚨 저장소는 팀 비공개다(D-249 ⑤ · D-303) — 올리기 전에 `data-publish` 와 **같은 함수**로 「팀 내부 공유도 안 되는 원천을
   받은 기기인가」를 본다(`data_store._noredist_seen` · D-99). 걸리면 아무것도 올리지 않는다.
🚨 Excel 로 열고 저장할 때 **「CSV UTF-8」** 로 저장한다 — 그냥 「CSV」는 한글이 깨진다(들여오기가 지문을 못 읽고 멈춘다).
🚨 같은 표를 두 사람이 동시에 열면 동기화가 충돌 사본(`… (1).csv`)을 만든다 — `status` 가 그것도 표로 보여 준다.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import pathlib
import shutil
import sys

from scripts import data_store as ds

ROOT = ds.ROOT
#: 표가 생기는 자리 — 판 명령(`guide_statute_round` 의 `*_TEAM_SHEET` · `*-audit-sheet --out`)이 여기 쓴다
LOCAL = ROOT / "build" / "labels"
LAYOUT = "copylane-sheets"
OLD = "_old"
#: 사람이 적는 칸 — 이 칸이 있는 CSV 가 「채우는 표」다
WHO = "판정자"

#: 파일 이름 → 들여오는 명령(정본). 🚨 감사표는 머리줄로 가른다(`kind_of`) — 이름은 `--out` 으로 사람이 정한다
IMPORT_BY_NAME = {
    "guide_statute__팀장판정표.csv": "import-decisions",
    "cosmetic_qa__팀장판정표.csv": "cq-import-decisions",
    "ftc_press_old__팀장판정표.csv": "fp-import-decisions",
    "guide_fix__팀장판정표.csv": "gf-import-decisions",
    "ftc_sealed__팀장판정표.csv": "fs-import-decisions",
}


def header(path: pathlib.Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f), [])


def is_sheet(path: pathlib.Path) -> bool:
    """머리줄에 `판정자` 가 있는 CSV. 🔴 못 읽으면(깨진 인코딩 등) 표가 아니라고 하지 않고 **멈춘다** (D-220)."""
    if path.suffix.lower() != ".csv":
        return False
    try:
        return WHO in header(path)
    except UnicodeDecodeError as e:
        raise SystemExit(
            f"🔴 {path} 를 UTF-8 로 못 읽는다 — Excel 에서 「CSV UTF-8」로 다시 저장한다 ({e.reason})"
        ) from e


def filled(path: pathlib.Path) -> tuple[int, int]:
    """(채운 행, 전체 행) — 채운 행 = `판정자` 칸이 빈칸이 아닌 행."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return sum(bool((r.get(WHO) or "").strip()) for r in rows), len(rows)


def kind_of(path: pathlib.Path) -> str:
    """들여오는 명령(정본에서 칠 것). 모르면 「?」 — 지어내지 않는다."""
    if path.name in IMPORT_BY_NAME:
        return IMPORT_BY_NAME[path.name]
    cols = set(header(path))
    if {"표", "제품유형", "원천결손"} <= cols:
        return "audit-import"  # 해설서 위반문구 판 감사(`audit-sheet`)
    if cols == {"지문", "원천", "문구", "조건", "메모", WHO}:
        return "caution-audit-import"  # 인정 조건문 감사(`caution-audit-sheet`)
    if {"대상", "별표5목"} <= cols:
        return "<판>-audit"  # 화장품 · 보도자료 · 수정문구 · 봉인 문구 판 감사 — 판은 지문 앞머리(cq · fp · gf · fs)
    return "?"


def local_sheets(base: pathlib.Path = LOCAL) -> list[pathlib.Path]:
    return sorted(p for p in base.rglob("*.csv") if is_sheet(p)) if base.is_dir() else []


def plan_push(local: list[pathlib.Path], base: pathlib.Path, dest: pathlib.Path) -> list[dict]:
    """파일마다 할 일 — `새로` · `같음` · `빈 표 교체` · `채우는 중 · 덮지 않음`. 쓰지 않는다(순수)."""
    out = []
    for src in local:
        rel = src.relative_to(base)
        to = dest / rel
        if not to.exists():
            act = "새로"
        elif ds._sha(to) == ds._sha(src):
            act = "같음"
        else:
            n, _ = filled(to)
            act = "빈 표 교체" if n == 0 else f"채우는 중 · 덮지 않음 ({n}행 채움)"
        out.append({"rel": rel.as_posix(), "src": src, "to": to, "act": act})
    return out


def push(
    *, dry_run: bool = False, base: pathlib.Path = LOCAL, root: pathlib.Path | None = None
) -> int:
    bad = ds._noredist_seen()
    if bad:
        print(
            "🔴 이 기기가 팀 내부 공유도 안 되는 원천을 받았다 — 표를 올리지 않는다:\n  "
            + "\n  ".join(bad)
        )
        return 1
    dest = (root or ds.store_root()) / LAYOUT
    plan = plan_push(local_sheets(base), base, dest)
    if not plan:
        print(f"올릴 표 없음 — {base} 에 `{WHO}` 칸이 있는 CSV 가 없다")
        return 0
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for p in plan:
        print(f"  {p['act']:<24} {p['rel']}")
        if dry_run or p["act"] in ("같음",) or p["act"].startswith("채우는 중"):
            continue
        if p["act"] == "빈 표 교체":
            keep = dest / OLD / stamp / p["rel"]
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p["to"], keep)
        ds._copy_verified(p["src"], p["to"], ds._sha(p["src"]))
    held = [p["rel"] for p in plan if p["act"].startswith("채우는 중")]
    if held:
        print(
            "🟡 채우는 중인 표는 덮지 않았다 — 판이 바뀌었으면 들여온 뒤(정본) 저장소 쪽을 지우고 다시 push 한다"
        )
    print(f"\n저장소 → {dest}" + ("  (--dry-run · 쓰지 않았다)" if dry_run else ""))
    return 0


def status(root: pathlib.Path | None = None) -> int:
    dest = (root or ds.store_root()) / LAYOUT
    rows = [p for p in local_sheets(dest) if OLD not in p.relative_to(dest).parts]
    if not rows:
        print(f"저장소에 표 없음 — {dest}")
        return 0
    for p in rows:
        n, total = filled(p)
        print(f"  {n:>4} / {total:<4} 채움   {kind_of(p):<22} {p.relative_to(dest).as_posix()}")
    print(
        f'\n들여오기(정본 · 클론 B) — uv run python -m scripts.guide_statute_round <명령> --csv "{dest}{os_sep()}<파일>"'
        "\n  🚨 감사는 `--out data/derived/labels/<판>/audit__팀장.jsonl` 로 앞 감사를 덮지 않는다"
    )
    return 0


def os_sep() -> str:
    return "\\" if sys.platform == "win32" else "/"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push", help="빈 표를 저장소에 둔다 (채우는 중인 표는 덮지 않는다)")
    p.add_argument("--dry-run", action="store_true")
    sub.add_parser("status", help="저장소의 표 · 채운 행 수 · 들여오는 명령")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "push":
            return push(dry_run=a.dry_run)
        return status()
    except ds.StoreError as e:
        print(f"🔴 {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
