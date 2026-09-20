"""scripts/raw_inbox.py — 팀원이 수집한 **원문**을 정본(클론 B)으로 옮긴다 (2026-09-20 · D-250).

  uv run python -m scripts.raw_inbox publish [--dry-run] [--yes]        # 수집 팀원 — 받은편지함에 올린다
  uv run python -m scripts.raw_inbox import --from <브랜치>               # 정본 — 병합 **전** 검사만
  uv run python -m scripts.raw_inbox import [--dry-run] [--yes]         # 정본 — 병합 뒤 제자리에 놓는다
  uv run python -m scripts.raw_inbox pending                            # 정본 — 합치지 않은 팀원 원문이 있나

팀장 — *「특정 팀원이 raw 데이터 수집작업을 하게 하려면」* · 흐름은 *「내 ohb 브랜치로 merge 후 검토한 뒤
수정 및 흡수하여 나만 main 에 pr」*.

★ **폴더를 방향으로 가른다** —
    `CopyLane_store`      파생물·라벨 — 정본만 쓴다 · 팀원은 뷰어 (D-247 · D-249)
    `CopyLane_raw_inbox`  원문       — 수집 팀원이 쓴다 · 정본만 합친다 (이 모듈)
  한 폴더면 원문을 올릴 권한으로 **완성본까지 덮을 수 있다.**
★ **무엇을 옮길지는 git 의 수집 원장이 정한다** — 팀원이 수집하면 `collect` 가 원장에 줄을 붙이고(기기 칸 포함),
  그 원장이 팀원 브랜치 → 검토 → ohb 로 온다. 받은편지함의 바이트는 **원장의 sha 와 맞아야** 놓인다.
🚨 막는 것 — ① 원장 밖 경로(`data/raw` 밖 · `..`) ② sha 가 안 맞는 바이트 ③ **키가 섞인 원문**(목록 응답의
   `OC=` 반사 · 2026-09-18 실측) ④ 재배포 제약 원천(AI Hub 등 · 약관상 팀원 사이 전달을 모른다 · D-71)
   ⑤ 이미 있는 파일 덮어쓰기(규약 2).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys

from scripts import data_store as ds
from scripts import derived_manifest as dm

ROOT = dm.ROOT
LAYOUT = "copylane-raw"
INBOX_NAME = ds.INBOX_NAME  # 이름의 정본은 data_store 한 곳 (D-99) — setup 이 찾는 이름
_SHA = re.compile(r"[0-9a-f]{64}")
#: 목록 응답이 키를 되비춘 꼴 — 법제처 DRF 는 `OC=<키>` 로 돌려준다 (2026-09-18 실측)
_KEY_PARAM = re.compile(rb"[?&](?:OC|serviceKey|ServiceKey|apikey|api_key)=", re.IGNORECASE)


class InboxError(RuntimeError):
    """받은편지함을 쓸 수 없거나 규칙을 어겼다."""


def inbox_root() -> pathlib.Path:
    from collect import env  # noqa: PLC0415

    raw = env.setting("RAW_INBOX")
    if not raw:
        raise InboxError(
            "RAW_INBOX 가 비어 있다 — 원문 받은편지함 폴더를 모른다.\n"
            f"  `launcher.py data-setup` 이 `{INBOX_NAME}` 를 찾아 적는다 (공유를 받아 바로가기를 추가한 뒤)"
        )
    root = pathlib.Path(raw).expanduser()
    if not root.is_dir():
        raise InboxError(f"RAW_INBOX 폴더가 없다 — {root}. 드라이브가 붙었는지 본다")
    return root / LAYOUT


def _obj(root: pathlib.Path, sha: str) -> pathlib.Path:
    if not _SHA.fullmatch(sha):
        raise InboxError(f"sha256 모양이 아니다 — {sha[:40]!r}")
    return root / "objects" / sha[:2] / sha


def _path_of(row: dict) -> str:
    return str(row.get("path") or "").replace("\\", "/")


def unsafe(rows: list[dict]) -> list[str]:
    """🔴 원장 행 중 **`data/raw` 밖을 가리키거나 sha 모양이 아닌 것** — 쓰기 전에 전부 본다 (data_store.unsafe 와 같은 이유)."""
    base = (ROOT / "data" / "raw").resolve()
    bad = []
    for r in rows:
        p, sha = _path_of(r), str(r.get("sha256", ""))
        target = (ROOT / p).resolve()
        if not (
            p.startswith("data/raw/") and ".." not in p.split("/") and target.is_relative_to(base)
        ):
            bad.append(f"경로 {p!r}")
        elif not _SHA.fullmatch(sha):
            bad.append(f"sha {p!r}")
    return bad


def secret_in(data: bytes) -> str | None:
    """원문에 키가 섞였는가 — 🚨 **이름만** 돌려준다. 값은 어디에도 찍지 않는다."""
    from collect import env  # noqa: PLC0415

    if _KEY_PARAM.search(data):
        return "키 매개변수(OC= 등)"
    for name in env.KEYS:
        v = env.get(name, required=False)
        if len(v) >= 6 and v.encode("utf-8") in data:
            return name
    return None


def _noredist(source_id: str) -> bool:
    from collect import registry  # noqa: PLC0415

    try:
        return not registry.redistributable(source_id)
    except registry.RegistryError:
        return True  # 🚨 모르는 원천은 막는 쪽 (D-220)


def _ledger_rows(text: str) -> list[dict]:
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def _local_ledger() -> list[dict]:
    from collect import store  # noqa: PLC0415

    return (
        _ledger_rows(store.MANIFEST.read_text(encoding="utf-8")) if store.MANIFEST.exists() else []
    )


def _branch_ledger(branch: str) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9._/\-]+", branch):
        raise InboxError(f"브랜치 이름이 이상하다 — {branch!r}")
    out = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{branch}:data/manifest.jsonl"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if out.returncode != 0:
        raise InboxError(
            f"`{branch}` 의 원장을 못 읽었다 — `git fetch` 했는지 본다\n  {out.stderr.strip()[:300]}"
        )
    return _ledger_rows(out.stdout)


def _mine(rows: list[dict]) -> list[dict]:
    """올릴 후보 — **이 기기 디스크에 있고 원장에 있는** 원문 (경로별 마지막 행).

    🔄 2026-09-20 (팀장 판정) — ⛔ 종전에는 「원장에 **내 기기 이름**으로 적힌 행」이었다. 그러면
       `.env` 를 새로 만들어 별칭이 바뀌면 **안 올린 원문이 빠진다.** 기기 이름은 겹침 경고에만 쓴다.
    ★ 팀원 PC 의 원문은 **자기가 받은 것뿐**이다 — 원문은 저장소로 동기화되지 않고, 정본에 이미 있는 것은
       원장을 보고 받지 않는다(`save_raw`). 받은편지함에 이미 있는 것은 `publish` 가 거른다.
    """
    last: dict[str, dict] = {}
    for r in rows:
        p = _path_of(r)
        if p:
            last[p] = r
    return [r for p, r in last.items() if (ROOT / p).is_file()]


def _foreign(rows: list[dict]) -> list[dict]:
    """다른 기기가 받았고 **이 기기에 없는** 행 — 합칠 후보. 🚨 기기 칸 없는 옛 행은 보지 않는다(정본 자신의 과거다)."""
    from collect import store  # noqa: PLC0415

    me = store.device_id()
    seen, out = set(), []
    for r in rows:
        who = r.get("device")
        p = _path_of(r)
        if not who or who in (me, store.CANONICAL_DEVICE) or p in seen:
            continue
        seen.add(p)
        if not (ROOT / p).exists():
            out.append(r)
    return out


def summary(rows: list[dict]) -> list[str]:
    """🆕 병합 검토용 요약 — 원천 · 기기별 **파일 수 · 새 판 수 · 크기** (런처 자동화 검토 발견 6).

    ⛔ 원장 diff 는 sha 나열이라 사람이 무엇이 오는지 못 읽는다. 🚨 파일 **내용**은 찍지 않는다.
    """
    from collect import store  # noqa: PLC0415

    agg: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        k = (str(r.get("source_id")), str(r.get("device")))
        a = agg.setdefault(k, [0, 0, 0])
        a[0] += 1
        a[1] += store.EDITION_MARK in _path_of(r)
        a[2] += int(r.get("bytes") or 0)
    return [
        f"    {sid:<28} {dev:<14} {n:>6}개 · 새 판 {ed:>4} · {b / 1024 / 1024:>7,.1f} MB"
        for (sid, dev), (n, ed, b) in sorted(agg.items())
    ]


def pending() -> list[dict]:
    """🆕 정본에서 **합치지 않은 팀원 원문** — 원장(병합됨)에는 있고 디스크에는 없다.

    팀장 — *「대처를 진행해줘」* (받는 쪽 점검 2026-09-20). ⛔ 원장은 git 병합으로 들어오고 원문은
    `raw-import` 로 따로 온다 — 그 사이에 추출·재생성을 돌리면 추출기는 디스크만 읽으므로
    **경고 없이 팀원 원문이 빠진 파생물**이 나온다. 그 자리를 막는다.
    🚨 G2(추출 뒤 원문 삭제 · D-17)와 재배포 제약 원천(받은편지함으로 못 온다 · D-71)은 세지 않는다 —
       디스크에 없는 것이 정상이거나, 합치기 검사(`--from`)가 이미 막는다.
    """
    from collect import registry  # noqa: PLC0415

    if dm.role() != "canonical":
        return []  # 사본은 원문을 안 갖는 것이 정상이다 (D-19)
    out = []
    for r in _foreign(_local_ledger()):
        sid = str(r.get("source_id"))
        try:
            if registry.is_g2(sid) or _noredist(sid):
                continue
        except registry.RegistryError:
            pass  # 모르는 원천은 센다 — 없음을 성공으로 세지 않는다 (D-72)
        out.append(r)
    return out


def check_pending() -> int:
    """런처 `extract`·`scan`, `data-publish` 가 앞에서 부른다. 🔴 있으면 1 — 그 명령을 멈춘다."""
    rows = pending()
    if not rows:
        return 0
    who = sorted({str(r.get("device")) for r in rows})
    print(
        f"🔴 합치지 않은 팀원 원문이 {len(rows)}개 있다 — 기기 {who} · 예: {[_path_of(r) for r in rows[:3]]}\n"
        "  원장은 병합됐는데 파일이 없다. 이대로 만들면 **팀원 원문이 빠진 파생물**이 된다 (D-250).\n"
        "  먼저: uv run python launcher.py raw-import\n"
        "  (받은편지함에 없다고 나오면 팀원에게 `raw-publish` 를 다시 요청한다)"
    )
    return 1


def publish(*, yes: bool = False, dry_run: bool = False) -> int:
    """수집 팀원 — 내가 받은 원문을 받은편지함에 올린다."""
    from collect import store  # noqa: PLC0415

    if dm.role() == "canonical":
        print(
            "🔴 정본은 원문을 올리지 않는다 — 받은편지함은 팀원 → 정본 방향이다 (D-250). 파생물은 `data-publish`"
        )
        return 1
    try:
        store.device_id()  # 별칭 없는 기기는 여기까지 올 수 없지만(수집이 멈춘다) — 기록에 적을 이름을 먼저 본다
    except store.StoreError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    rows = _mine(_local_ledger())
    bad = unsafe(rows)
    if bad:
        print(f"🔴 원장에 올릴 수 없는 행이 있다 — 아무것도 올리지 않았다: {bad[:5]}")
        return 1
    blocked = sorted({str(r["source_id"]) for r in rows if _noredist(str(r["source_id"]))})
    if blocked:
        print(
            f"🔴 재배포 제약 원천의 원문은 올리지 않는다 — {blocked} (D-71).\n"
            "  🚨 약관상 팀원 사이에 넘겨도 되는지 모른다. 정본 기기에서 직접 받는다"
        )
        rows = [r for r in rows if str(r["source_id"]) not in blocked]
    try:
        root = inbox_root()
    except InboxError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    new = [r for r in rows if not _obj(root, str(r["sha256"])).is_file()]
    leaked, changed = [], []
    for r in new:
        data = (ROOT / _path_of(r)).read_bytes()
        if hashlib.sha256(data).hexdigest() != r["sha256"]:
            changed.append(_path_of(r))  # 🚨 원장과 다른 바이트 — 받은 뒤 누가 고쳤다
            continue
        why = secret_in(data)
        if why:
            leaked.append(f"{_path_of(r)} ({why})")
    if changed:
        print(
            f"🔴 **원장과 다른 원문**이 있다 — 아무것도 올리지 않았다 ({len(changed)}개): {changed[:5]}"
        )
        print("  🚨 원문은 고치지 않는다(규약 2). 그 파일을 원장대로 되돌리거나 지우고 다시 받는다")
        return 1
    if leaked:
        print(f"🔴 **키가 섞인 원문**이 있다 — 아무것도 올리지 않았다 ({len(leaked)}개):")
        for x in leaked[:10]:
            print(f"    {x}")
        print("  🚨 그 파일을 지우고 수집기를 고친 뒤 다시 받는다. 키 재발급 여부는 팀장 판정이다")
        return 1
    size = sum(int(r.get("bytes") or 0) for r in new) / 1024 / 1024
    print(
        f"올릴 것 {len(new)}개 · {size:,.1f} MB (이 기기가 받은 원문 {len(rows)}개 중)\n  받은편지함 {root}"
    )
    if not new:
        print("올릴 것 없음")
        return 0
    if dry_run:
        print("🚨 --dry-run — 아무것도 올리지 않았다")
        return 0
    if not yes and not ds._ask("🚨 외부 전송이다 (팀 비공개 받은편지함 · D-78 ③). 올릴까"):  # noqa: SLF001
        print("멈췄다")
        return 1
    for r in new:
        ds._copy_verified(ROOT / _path_of(r), _obj(root, str(r["sha256"])), str(r["sha256"]))  # noqa: SLF001
    with (root / "inbox_log.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(
            json.dumps(
                {
                    "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    "device": store.device_id(),
                    "objects_new": len(new),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    print(
        f"올렸다 {len(new)}개.\n"
        "  다음 — 원장(`data/manifest.jsonl`)을 **내 브랜치에** 커밋·push 하고 팀장에게 알린다"
    )
    return 0


def import_(*, branch: str | None = None, yes: bool = False, dry_run: bool = False) -> int:
    """정본 — 다른 기기가 받은 원문을 받은편지함에서 꺼내 원장 경로에 놓는다.

    `branch` 를 주면 **병합 전 검사만** 한다 — 그 브랜치 원장의 새 줄마다 받은편지함에 맞는 바이트가 있는가.
    """
    check_only = branch is not None
    if not check_only and dm.role() != "canonical":
        print("🔴 합치지 않는다 — 정본(DATA_ROLE=canonical)만 원문을 합친다 (D-226)")
        return 1
    try:
        rows = _foreign(_branch_ledger(branch) if check_only else _local_ledger())
        root = inbox_root()
    except InboxError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    bad = unsafe(rows)
    if bad:
        print(f"🔴 원장에 받을 수 없는 행이 있다 — 아무것도 하지 않았다: {bad[:5]}")
        return 1
    lack, leaked, noredist = [], [], []
    for r in rows:
        if _noredist(str(r["source_id"])):
            noredist.append(_path_of(r))
            continue
        src = _obj(root, str(r["sha256"]))
        if not src.is_file() or ds._sha(src) != r["sha256"]:  # noqa: SLF001
            lack.append(_path_of(r))
            continue
        why = secret_in(src.read_bytes())
        if why:
            leaked.append(f"{_path_of(r)} ({why})")
    head = f"{'검사 — ' + branch if check_only else '합치기'} · 다른 기기가 받은 원문 {len(rows)}개"
    print(head)
    for line in summary(rows):
        print(line)
    for name, xs in (
        ("받은편지함에 없음·sha 불일치", lack),
        ("키 섞임", leaked),
        ("재배포 제약", noredist),
    ):
        if xs:
            print(f"  🔴 {name} {len(xs)}개 — 예: {xs[:3]}")
    if lack or leaked or noredist:
        print("  🚨 하나라도 있으면 합치지 않는다 — 팀원에게 `raw-publish` 를 다시 요청한다")
        return 1
    if check_only:
        print("  ✅ 병합해도 된다 — 병합 뒤 `launcher.py raw-import` 로 제자리에 놓는다")
        return 0
    if not rows:
        print("합칠 것 없음")
        return 0
    if dry_run:
        print("🚨 --dry-run — 아무것도 놓지 않았다")
        return 0
    if not yes and not ds._ask(f"{len(rows)}개를 data/raw 에 놓을까"):  # noqa: SLF001
        print("멈췄다")
        return 1
    for r in rows:
        dest = ROOT / _path_of(r)
        if dest.exists():  # 🚨 규약 2 — 덮어쓰지 않는다 (_foreign 이 거른 뒤 생긴 것)
            print(f"  🟡 이미 있다 — 건너뜀 {_path_of(r)}")
            continue
        ds._copy_verified(_obj(root, str(r["sha256"])), dest, str(r["sha256"]))  # noqa: SLF001
    print(
        f"놓았다 {len(rows)}개. 판(__c날짜)이 생겼으면 `launcher.py adopt` 로 고른다 (D-246).\n"
        "  다음 — 파생물 재생성 → `derived-manifest --write` → 커밋 → `data-publish`"
    )
    return 0


def main() -> int:
    dm._utf8_out()  # noqa: SLF001 — 파이프로 나갈 때도 한글 (CI 실측 · 같은 함수를 쓴다)
    ap = argparse.ArgumentParser(description="팀원 수집 원문의 받은편지함 (D-250)")
    ap.add_argument("cmd", choices=["publish", "import", "pending"])
    ap.add_argument(
        "--from", dest="branch", default=None, help="import — 병합 전 이 브랜치의 원장으로 검사만"
    )
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "publish":
        return publish(yes=a.yes, dry_run=a.dry_run)
    if a.cmd == "pending":
        return check_pending()
    return import_(branch=a.branch, yes=a.yes, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
