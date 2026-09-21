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
LAYOUT = (
    ds.INBOX_LAYOUT
)  # 🔄 2026-09-21 — 정본은 data_store (바로가기 대상을 내용으로 알아볼 때 쓴다 · D-99)
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


def _branch_name(branch: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._/\-]+", branch):
        raise InboxError(f"브랜치 이름이 이상하다 — {branch!r}")
    return branch


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _branch_ledger(branch: str) -> list[dict]:
    out = _git("show", f"{_branch_name(branch)}:data/manifest.jsonl")
    if out.returncode != 0:
        raise InboxError(
            f"`{branch}` 의 원장을 못 읽었다 — `git fetch` 했는지 본다\n  {out.stderr.strip()[:300]}"
        )
    return _ledger_rows(out.stdout)


def _base_ledger(branch: str) -> list[dict]:
    """🆕 D-254 — 팀원 브랜치가 **갈라진 자리**(merge-base)의 원장. 브랜치는 이 뒤에 **붙이기만** 해야 한다.

    🚨 못 읽으면 멈춘다 — 「비교할 것 없음」을 「붙이기만 했다」로 세지 않는다 (D-220).
    """
    mb = _git("merge-base", "HEAD", _branch_name(branch))
    if mb.returncode != 0 or not mb.stdout.strip():
        raise InboxError(
            f"`{branch}` 와 이 기기 HEAD 의 갈래점을 못 찾았다 — `git fetch` 했는지 본다\n"
            f"  {mb.stderr.strip()[:300]}"
        )
    out = _git("show", f"{mb.stdout.strip()}:data/manifest.jsonl")
    if out.returncode != 0:
        raise InboxError(f"갈래점의 원장을 못 읽었다\n  {out.stderr.strip()[:300]}")
    return _ledger_rows(out.stdout)


def rewritten(base: list[dict], branch: list[dict]) -> list[str]:
    """🔴 원장은 **붙이기만** 한다 — 갈래점 원장이 브랜치 원장의 앞머리가 아니면 무엇이 어긋났는지.

    ⛔ D-254 전에는 새 줄만 봤다 — 팀원 브랜치가 옛 줄을 **지우거나 고쳐도** 「✅ 병합해도 된다」였다.
       원장의 옛 줄은 이 기기 파일의 sha 근거다(doctor `--hash` · `save_raw` 의 「받은 적 있다」). 고치면 둘 다 틀린다.
    """
    head = branch[: len(base)]
    if head == base:
        return []
    bad = [i for i, r in enumerate(base) if i >= len(head) or head[i] != r]
    what = "줄 수가 줄었다" if len(branch) < len(base) else "옛 줄이 바뀌었거나 지워졌다"
    return [
        f"{what} — 갈래점 원장 {len(base)}줄 중 {len(bad)}줄이 다르다 · 첫 자리 {bad[0] + 1}번째 줄"
    ]


def conflicts(new: list[dict], local: list[dict]) -> list[str]:
    """🔴 브랜치의 **새 줄**이 이 기기에 이미 있는 경로를 **다른 sha** 로 적었다.

    ⛔ D-254 전에는 `_foreign` 이 이 기기에 있는 경로를 조용히 건너뛰어 「✅ 병합해도 된다」가 났다.
       병합하면 한 경로에 두 sha 가 적히고 — 디스크는 한쪽뿐이라 `doctor --hash` 가 훼손으로 찍거나
       `save_raw` 가 틀린 쪽을 「이미 받았다」로 본다. 새 내용은 판(`__c날짜`)으로 와야 한다 (D-250 결정 3).
    """
    known: dict[str, set[str]] = {}
    for r in local:
        known.setdefault(_path_of(r), set()).add(str(r.get("sha256")))
    out = []
    for r in new:
        p, sha = _path_of(r), str(r.get("sha256"))
        if p in known:
            if sha not in known[p]:
                out.append(f"{p} (원장에 다른 sha)")
        elif (ROOT / p).is_file() and ds._sha(ROOT / p) != sha:  # noqa: SLF001
            out.append(f"{p} (디스크에 다른 바이트)")
    return out


def _last(rows: list[dict]) -> dict[str, dict]:
    """경로 → 그 경로의 **마지막** 원장 행."""
    last: dict[str, dict] = {}
    for r in rows:
        p = _path_of(r)
        if p:
            last[p] = r
    return last


def _mine(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """올릴 후보 — **이 기기 디스크에 있고 원장에 있는** 팀원 수집 원문 (경로별 마지막 행) · 뺀 것의 이유별 수.

    🔄 2026-09-20 (팀장 판정) — ⛔ 종전에는 「원장에 **내 기기 이름**으로 적힌 행」이었다. 그러면
       `.env` 를 새로 만들어 별칭이 바뀌면 **안 올린 원문이 빠진다.** 기기 이름은 겹침 경고에만 쓴다.
    🔄 D-254 (런처 전수 감사 §2 raw-publish) — 그래도 **정본의 것**은 뺀다. 기기 칸 없는 옛 행은 정본이 받은 것이고
       (D-250 결정 4) `canonical` 은 정본의 이름이다. ⛔ 빼지 않으면 옛 원문이 있는 사본(클론 A)은 정본의 과거분
       수천 개를 받은편지함에 올린다. ★ 다른 팀원 별칭 행은 남긴다 — 내 옛 별칭과 가를 수 없다(위 판정).
    ★ 팀원 PC 의 원문은 **자기가 받은 것뿐**이다 — 원문은 저장소로 동기화되지 않고, 정본에 이미 있는 것은
       원장을 보고 받지 않는다(`save_raw`). 받은편지함에 이미 있는 것은 `publish` 가 거른다.
    """
    from collect import store  # noqa: PLC0415

    out: list[dict] = []
    skipped = {"legacy": 0, "canonical": 0}
    for p, r in _last(rows).items():
        if not (ROOT / p).is_file():
            continue
        who = str(r.get("device") or "")
        if not who:
            skipped["legacy"] += 1
        elif who == store.CANONICAL_DEVICE:
            skipped["canonical"] += 1
        else:
            out.append(r)
    return out, skipped


#: `collect.missing.classify` 가 「디스크에 없는 것이 정상」이라 가른 이유 중 **받은편지함에서 가져오면 안 되는 것**.
#: 🚨 `other`(다른 기기 것)는 넣지 않는다 — 그것이 바로 합칠 후보다. `g2` 는 `_held_back` 이 가른다 (한 곳 · D-99).
#:    moved    같은 내용이 디스크의 다른 경로에 있다 — 판을 채택(`adopt`)한 흔적. 다시 놓으면 판이 되살아난다
#:    excluded 수집기가 안 받는다고 선언한 것 — 돌아오면 안 된다 (D-253)
#:    cleared  오류 응답 판을 치웠고 정상 판이 있다
SETTLED = frozenset({"moved", "excluded", "cleared"})


def _foreign(rows: list[dict]) -> list[dict]:
    """다른 기기가 받았고 **이 기기에 없는** 행 — 합칠 후보. 🚨 기기 칸 없는 옛 행은 보지 않는다(정본 자신의 과거다).

    🔄 D-254 (런처 전수 감사 §1-1) — ⛔ 종전에는 「다른 기기 행 · 디스크에 없다」만 봤다. 팀원 판(`x__c날짜`)을
       정본이 `adopt` 로 `x` 로 옮기면 판 경로가 사라져 **영영 합치지 않은 원문**으로 셌다 — `pending` 이
       extract·data-refresh·data-publish 를 막고, `raw-import` 는 판을 다시 놓고, 추출기는 판 때문에 멈추고 …
       ★ 없는 이유는 `collect.missing.classify` 가 가른다 — doctor·inventory 와 같은 함수 (D-253 · D-99).
       그 함수는 **받은 원장 전부**를 봐야 `moved`(같은 sha 가 다른 경로에) 를 안다 — 걸러 낸 행만 주지 않는다.
    🔄 D-254 — 경로마다 **마지막** 행을 본다(종전 첫 행). 같은 경로에 줄이 둘이면 뒤의 것이 지금의 sha 다.
    """
    from collect import missing, store  # noqa: PLC0415

    me = store.device_id()
    cand = [
        r
        for p, r in _last(rows).items()
        if r.get("device")
        and r.get("device") not in (me, store.CANONICAL_DEVICE)
        and not (ROOT / p).exists()
    ]
    if not cand:
        return []
    why = missing.classify(rows, root=ROOT, me=me)
    return [r for r in cand if why.get(_path_of(r), ("",))[0] not in SETTLED]


def _held_back(source_id: str) -> str | None:
    """받은편지함으로 **오지 않는** 원천이면 그 이유 — `pending` 과 `import_` 가 같이 읽는다 (D-99 · D-254).

    ⛔ D-254 전에는 `pending` 만 G2·재배포 제약을 뺐다 — `import_` 는 정본이 추출 뒤 지운 G2 원문을
       되살리거나(받은편지함에 있으면) 「없음」으로 **전체를 거부**했다(없으면).
      `g2`       사실을 뽑은 뒤 원문을 지운다(D-92) — 다시 할 때는 보관본이 아니라 **재수집**이다
      `noredist` 재배포 제약(D-71) — `raw-publish` 가 올리지 않는다
      `unknown`  레지스트리에 없다 — 🚨 모르는 것은 막는 쪽 (D-220)
    """
    from collect import registry  # noqa: PLC0415

    try:
        if registry.is_g2(source_id):
            return "g2"
    except registry.RegistryError:
        return "unknown"
    return "noredist" if _noredist(source_id) else None


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
    🚨 G2(추출 뒤 원문 삭제 · D-92)와 재배포 제약 원천(받은편지함으로 못 온다 · D-71)은 세지 않는다 —
       디스크에 없는 것이 정상이거나, 합치기 검사(`--from`)가 이미 막는다. 거르는 곳은 `_held_back` 하나다.
    """
    if dm.role() != "canonical":
        return []  # 사본은 원문을 안 갖는 것이 정상이다 (D-19)
    # 🚨 모르는 원천(`unknown`)은 센다 — 없음을 성공으로 세지 않는다 (D-220)
    return [
        r
        for r in _foreign(_local_ledger())
        if _held_back(str(r.get("source_id"))) in (None, "unknown")
    ]


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
        "  (받은편지함에 없다고 나오면 팀원에게 `raw-publish` 를 다시 요청한다 · "
        "레지스트리에 없는 원천이면 등재가 먼저다)"
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
    rows, skipped = _mine(_local_ledger())
    if any(skipped.values()):
        print(
            f"⬜ 정본의 원문은 올리지 않는다 — 기기 칸 없는 옛 행 {skipped['legacy']}개(정본의 과거분 · D-250 결정 4) · "
            f"`{store.CANONICAL_DEVICE}` 행 {skipped['canonical']}개. 이 기기 디스크에 있어도 정본에 이미 있다"
        )
    bad = unsafe(rows)
    if bad:
        print(f"🔴 원장에 올릴 수 없는 행이 있다 — 아무것도 올리지 않았다: {bad[:5]}")
        return 1
    # 🔄 2026-09-21 (전수 재검토 I5) — 거르는 규칙은 `_held_back` 하나다 (D-99 · `pending`·`import_`·거울과 같다).
    #    ⛔ 여기만 재배포 제약을 **따로** 걸러 G2(추출 뒤 원문 삭제 · D-92)가 받은편지함에 올라갔다 — 정본의
    #       `import_` 는 G2 를 안 가져가므로 그 원문은 팀 공유 폴더에 **남기만** 했다. 모르는 원천(`unknown`)도 막는다.
    held = {s: why for s in {str(r["source_id"]) for r in rows} if (why := _held_back(s))}
    if held:
        print(
            f"🔴 받은편지함으로 보내지 않는 원천이 있다 — {sorted(held.items())}\n"
            "  g2 추출 뒤 원문을 지운다(D-92) · noredist 약관상 넘겨도 되는지 모른다(D-71) · unknown 레지스트리에 없다(D-220).\n"
            "  🚨 그 원천은 정본 기기에서 직접 받는다"
        )
        rows = [r for r in rows if str(r["source_id"]) not in held]
    try:
        root = inbox_root()
    except InboxError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    new = [r for r in rows if not ds.object_ok(_obj(root, str(r["sha256"])), r.get("bytes"))]
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


def _check_branch(branch: str, rows: list[dict]) -> list[str]:
    """병합 전 검사의 앞 두 줄 — 원장이 붙이기만 했는가 · 새 줄이 있는 경로의 sha 를 바꾸는가 (D-254)."""
    base = _base_ledger(branch)
    out = [f"원장 고침 — {x}" for x in rewritten(base, rows)]
    out += [f"같은 경로 다른 sha — {x}" for x in conflicts(rows[len(base) :], _local_ledger())]
    return out


def import_(*, branch: str | None = None, yes: bool = False, dry_run: bool = False) -> int:
    """정본 — 다른 기기가 받은 원문을 받은편지함에서 꺼내 원장 경로에 놓는다.

    `branch` 를 주면 **병합 전 검사만** 한다 — 그 브랜치 원장이 붙이기만 했는가 · 이미 있는 경로의 sha 를
    바꾸지 않는가 · 새 줄마다 받은편지함에 맞는 바이트가 있는가.
    🔄 D-254 — G2·재배포 제약은 `pending` 과 **같은 함수**(`_held_back`)로 거른다.
    """
    check_only = branch is not None
    if not check_only and dm.role() != "canonical":
        print("🔴 합치지 않는다 — 정본(DATA_ROLE=canonical)만 원문을 합친다 (D-226)")
        return 1
    try:
        ledger = _branch_ledger(branch) if check_only else _local_ledger()
        broken = _check_branch(branch, ledger) if check_only else []
        rows = _foreign(ledger)
        root = inbox_root()
    except InboxError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1
    bad = unsafe(rows)
    if bad:
        print(f"🔴 원장에 받을 수 없는 행이 있다 — 아무것도 하지 않았다: {bad[:5]}")
        return 1
    held: dict[str, list[str]] = {"g2": [], "noredist": [], "unknown": []}
    carry = []
    for r in rows:
        why = _held_back(str(r["source_id"]))
        if why:
            held[why].append(_path_of(r))
        else:
            carry.append(r)
    lack, leaked = [], []
    for r in carry:
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
    # 🚨 G2 는 받은편지함으로 가져오지 않는다 — 정본이 추출 뒤 지운 것을 되살리지 않는다(D-92). 막지도 않는다(`pending` 과 같다)
    if held["g2"]:
        print(
            f"  🟡 G2 {len(held['g2'])}개는 가져오지 않는다 — 추출 뒤 원문을 지우는 원천이다 (D-92).\n"
            f"     필요하면 정본이 직접 재수집한다 · 예: {held['g2'][:3]}"
        )
    # 🔄 D-254 — 재배포 제약은 **병합 전 검사에서만** 🔴 다. 병합 뒤 합치기에서 🔴 로 두면 영영 안 끝난다
    #    (`raw-publish` 는 그 원천을 올리지 않으므로 받은편지함에 올 일이 없다) — `pending` 과 같이 건너뛴다.
    noredist_bad = held["noredist"] if check_only else []
    if held["noredist"] and not check_only:
        print(
            f"  🟡 재배포 제약 {len(held['noredist'])}개는 가져오지 않는다 — 받은편지함으로 오지 않는다 (D-71).\n"
            f"     정본에 필요하면 정본이 직접 받는다 · 예: {held['noredist'][:3]}"
        )
    fails = (
        ("원장 고침·같은 경로 다른 sha", broken),
        ("받은편지함에 없음·sha 불일치", lack),
        ("키 섞임", leaked),
        ("재배포 제약", noredist_bad),
        ("레지스트리에 없는 원천", held["unknown"]),
    )
    for name, xs in fails:
        if xs:
            print(f"  🔴 {name} {len(xs)}개 — 예: {xs[:3]}")
    if any(xs for _, xs in fails):
        print("  🚨 하나라도 있으면 합치지 않는다 —")
        if broken:
            print(
                "     · 원장은 붙이기만 한다. 팀원 브랜치에서 옛 줄을 되돌리고, 새 내용은 판(__c날짜)으로 받게 한다 (D-250 결정 3)"
            )
        if lack:
            print("     · 받은편지함에 없음 — 팀원에게 `raw-publish` 를 다시 요청한다")
        if leaked:
            print(
                "     · 키 섞임 — 팀원이 그 파일을 지우고 수집기를 고친 뒤 다시 받는다. 키 재발급은 팀장 판정"
            )
        if noredist_bad:
            print(
                "     · 재배포 제약 — `raw-publish` 는 이 원천을 **올리지 않는다**(D-71) · 다시 요청해도 안 온다.\n"
                "       팀원 브랜치에서 그 원장 줄을 빼고, 정본에 필요하면 정본이 직접 받는다"
            )
        if held["unknown"]:
            print("     · 모르는 원천 — 레지스트리에 등재한 뒤 다시 검사한다 (D-220)")
        return 1
    if check_only:
        print("  ✅ 병합해도 된다 — 병합 뒤 `launcher.py raw-import` 로 제자리에 놓는다")
        return 0
    if not carry:
        print("합칠 것 없음")
        return 0
    if dry_run:
        print("🚨 --dry-run — 아무것도 놓지 않았다")
        return 0
    if not yes and not ds._ask(f"{len(carry)}개를 data/raw 에 놓을까"):  # noqa: SLF001
        print("멈췄다")
        return 1
    for r in carry:
        dest = ROOT / _path_of(r)
        if dest.exists():  # 🚨 규약 2 — 덮어쓰지 않는다 (_foreign 이 거른 뒤 생긴 것)
            print(f"  🟡 이미 있다 — 건너뜀 {_path_of(r)}")
            continue
        ds._copy_verified(_obj(root, str(r["sha256"])), dest, str(r["sha256"]))  # noqa: SLF001
    print(
        f"놓았다 {len(carry)}개. 판(__c날짜)이 생겼으면 `launcher.py adopt` 로 고른다 (D-246).\n"
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
