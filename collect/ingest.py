"""등록 — 사람이 받아 온 파일을 원장에 올린다 (D-109 후속).

🚨 **탐침의 반대편이다.** 탐침(`collect/probe.py`)은 「읽되 저장하지 않는다」이고,
   여기는 「사람이 이미 받아 온 것을 **등록한다**」이다. 둘 다 수집기가 아니지만
   방향이 정반대라 게이트도 반대다 — 탐침은 `registry.probe()`, 여기는 `registry.require()`.

왜 필요한가 — AI Hub·나스미디어처럼 **신청·승인을 거쳐 사람이 내려받는** 소스는
수집기가 가져오지 않는다. 그래서 `save_raw` · `manifest_append` · `mark_collected` 가
한 번도 안 불리고, 파일은 있는데 **원장에는 없는** 상태가 된다.

🚨 **그 상태가 왜 위험한가** — `manifest.jsonl` 은 「raw 에 무엇이 들어왔는가」의 유일한 증언이고,
   `provenance` 는 나중에 못 붙인다. 골든셋에 `redistributable:false` 소스가 **한 줄이라도**
   섞이면 그 골든셋 전체를 공개할 수 없는데(D-71), 어느 줄이 어디서 왔는지 알 방법이 사라진다.

두 가지 일을 한다. 🚨 **섞지 않는다.**

    uv run python -m collect.ingest count <경로>
        읽기만 한다. 파일 수 · 줄 수 · 크기 · sha256 을 센다.
        아무것도 옮기지 않고 원장도 건드리지 않는다. **2인 확인 전에도 돈다.**

    uv run python -m collect.ingest register <소스id> <경로> --use U1
        `registry.require()` 를 통과해야 한다 — 🚨 `reviewed_by` 가 비면 여기서 거부된다.
        소스의 **원문 폴더**(`store.raw_dir_of`)로 복사하고 manifest 에 provenance 와 함께 1행 남긴다.
        🔴 원문 폴더 ≠ 소스 id 인 소스가 넷이다 (D-245). 이 줄이 예전에 「data/raw/<소스id>/」라고
           적혀 있었고, 그 설명대로 넣어서 화장품법 334노드가 사라졌다 (2026-09-18).
        ⛔ **다른 기기에서 받은 raw 를 합치는 데 쓰지 않는다** — `walk()` 뒤 `p.name` 만 써서
           하위 폴더(`law/annex/`)를 펴고, 첫 폴더로만 넣고(`mfds_press_pdf` → `mfds_press`),
           원장에 행을 또 붙인다 (검토 2026-09-19 §3-d). 합류는 따로 만든다.

🚨 **`register` 는 등급 디렉터리에 넣지 않는다.** 원문은 `data/raw/` 다 (D-92) —
   한 원문 파일 안에서 조각의 등급이 갈리면 어느 등급 디렉터리에도 놓을 수 없다 (D-18).
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from collect import registry, store

ROOT = Path(__file__).resolve().parent.parent
CHUNK = 1 << 20  # 🚨 통째로 읽지 않는다. AI Hub 압축본은 수백 MB 다.
TEXT_SUFFIX = {".txt", ".csv", ".tsv", ".json", ".jsonl", ".md", ".xml"}


def digest_of(path: Path) -> tuple[str, int]:
    """스트리밍 sha256 과 바이트 수. `store.sha256` 은 bytes 를 받아 메모리에 올린다."""
    h, n = hashlib.sha256(), 0
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def count_lines(path: Path) -> int | None:
    """텍스트면 줄 수를, 아니면 None. 🚨 줄 수는 「행 수」의 근사다 — 판정이 아니다."""
    if path.suffix.lower() not in TEXT_SUFFIX:
        return None
    n = 0
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            n += chunk.count(b"\n")
    return n


def walk(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.is_file())


def cmd_count(target: Path) -> int:
    """🚨 읽기만 한다. 규모 불일치를 **판정 전에** 확인하기 위한 자리다.

    레지스트리의 `scale` 이 실제와 갈린 것이 2026-09-02 탐침 2회전에서 3건 나왔다
    (`aihub_71486` · `aihub_71723` · `aihub_558`). 어느 쪽이 맞는지는 **실물이 답한다.**
    """
    files = walk(target)
    if not files:
        print(f"🚨 {target} 에 파일이 없다")
        return 1
    total_bytes = total_lines = 0
    print(f"{'파일':<52} {'크기':>13} {'줄':>12}  sha256")
    for p in files[:200]:
        d, n = digest_of(p)
        lines = count_lines(p)
        total_bytes += n
        total_lines += lines or 0
        rel = str(p.relative_to(target)) if target.is_dir() else p.name
        print(f"{rel[:52]:<52} {n:>13,} {(lines if lines is not None else '—'):>12}  {d[:12]}")
    if len(files) > 200:
        print(f"… 외 {len(files) - 200}개 (합계에는 포함되지 않음)")
    print(f"\n파일 {len(files)}개 · {total_bytes:,} bytes · 텍스트 줄 합계 {total_lines:,}")
    print("🚨 아무것도 옮기지 않았고 원장도 건드리지 않았습니다 (D-109).")
    return 0


def cmd_register(source_id: str, target: Path, use: str) -> int:
    """🚨 첫 줄이 `registry.require()` 다 — 수집기 공통 규약 1 과 같은 문이다.

    `reviewed_by` 가 비면 여기서 거부된다. **사람이 손으로 받아 왔다는 사실이
    2인 확인을 면제하지 않는다** — 오히려 게이트가 유일하게 남은 자리다.
    """
    spec = registry.require(source_id, use=use)
    files = walk(target)
    if not files:
        print(f"🚨 {target} 에 파일이 없다")
        return 1

    # 🔴 **소스 id 가 아니라 계열 폴더다** (2026-09-18 사고 · store.FAMILY_OF).
    #    ⛔ 종전에는 `raw_dir(source_id)` 라 `law_go_kr` 파일이 `data/raw/law_go_kr/` 로 갔다.
    #       추출기는 `data/raw/law/` 를 보므로 화장품법 334노드가 코퍼스에서 조용히 사라졌다
    #       (law_article 2,207 → 1,873). 폴더 이름이 소스 id 와 다른 소스가 **넷**이다.
    dest_dir = store.raw_dir_of(source_id)  # 등급 디렉터리가 아니다
    url = str(spec.get("url") or "")
    new = skipped = 0

    for p in files:
        digest, size = digest_of(p)
        dest = dest_dir / p.name
        if dest.exists():
            if digest_of(dest)[0] == digest:
                skipped += 1  # 규약 4 — 같으면 스킵
                continue
            raise store.StoreError(
                f"{dest} 가 이미 있고 내용이 다르다. 원본은 덮어쓰지 않는다 (규약 2). "
                "새 파일명(판본·수집일 등)으로 넣어라."
            )
        shutil.copy2(p, dest)
        store.manifest_append(
            source_id=source_id,
            url=url,
            sha256=digest,
            bytes_=size,
            rows=count_lines(dest),
            path=str(dest.relative_to(ROOT)),
        )
        new += 1

    if new:
        registry.mark_collected(source_id)  # 규약 3 · 게이트 15
    print(f"등록 {new}개 · 동일해 스킵 {skipped}개 → {dest_dir.relative_to(ROOT)}")
    if registry.is_g2(source_id):
        print(
            "🚨 G2 다 — 사실을 뽑은 뒤 원본을 지우고 manifest 의 sha256 만 남긴다 "
            "(D-17 · store.drop_raw_for_g2)."
        )
    if not spec.get("redistributable"):
        print(
            "🚨 redistributable: false — 이 소스에서 나온 문장이 섞인 골든셋은 "
            "공개 배포할 수 없다 (D-71). 파생 행마다 store.stamp() 로 provenance 를 박아라."
        )
    return 0


def cmd_adopt(source_id: str, stem: str) -> int:
    """판(`__c…`)을 **원본 자리로 올린다** (D-143 의 마지막 한 칸 · 2026-09-18).

    🔴 **비어 있던 자리다.** `collect` 는 판을 **만들고**(규약 2 — 원본은 덮어쓰지 않는다),
       `store.current_files()` 는 판이 있으면 **멈춘다**(「어느 것을 쓸지는 사람이 정한다」).
       그런데 **채택하는 쪽이 없었다** — 판을 만든 지 열흘이 넘도록 아무도 채택을 못 했다.

    ⛔ 손으로 하면 원장이 깨진다. 이름만 바꾸면 원본 경로의 바이트가 **그 경로에 기록된
       어느 sha 와도 다르므로** `doctor --hash` 가 🔴 훼손으로 찍는다. 그래서 여기서
       **원장에 그 경로의 새 행을 붙인다.**

    🚨 2인 확인을 요구하지 않는다 (팀장 판정 2026-09-18) — 채택은 이미 사람이 두 판을
       보고 내리는 판정이고, `require()` 를 한 번 더 세우면 같은 사람에게 같은 것을 두 번 묻는다.
       대신 **등록된 소스인지**는 본다. 그리고 판이 둘 이상이면 **멈춘다** — 어느 것인지 사람이 정한다.
    """
    registry.spec(source_id)  # 미등록이면 거부

    d = store.raw_dir_of(source_id)
    eds = sorted(p for p in d.glob(f"{stem}{store.EDITION_MARK}*") if p.is_file())
    if not eds:
        print(f"🚨 {d} 에 {stem}{store.EDITION_MARK}… 판이 없다 — 채택할 것이 없다")
        return 1
    if len(eds) > 1:
        names = ", ".join(p.name for p in eds)
        print(f"🔴 판이 {len(eds)}개다 — 어느 것을 올릴지 사람이 정한다 (D-143): {names}")
        return 1

    ed = eds[0]
    base = d / f"{stem}{ed.suffix}"
    digest, size = digest_of(ed)
    if base.exists():
        if digest_of(base)[0] == digest:
            print(f"⬜ 원본과 판이 같다 — 판만 치운다: {ed.name}")
            ed.unlink()
            return 0
        print(f"  ⛔ 원본을 버린다 — {base.name} ({base.stat().st_size:,} B)")
        base.unlink()

    ed.rename(base)
    store.manifest_append(
        source_id=source_id,
        url=str(registry.spec(source_id).get("url") or ""),
        sha256=digest,
        bytes_=size,
        rows=count_lines(base),
        path=str(base.relative_to(ROOT)),
    )
    print(f"채택 — {ed.name} → {base.name}  ({size:,} B · sha {digest[:16]})")
    print(f"  원장에 {base.relative_to(ROOT)} 의 새 행을 붙였다 — doctor 가 훼손으로 안 본다")
    print("  🚨 무엇이 바뀌었는지는 사람이 원장에 적는다 (D-54)")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="collect.ingest", description="사람이 받아 온 파일을 등록한다"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("count", help="읽기만 한다 — 파일 수·줄 수·sha256")
    c.add_argument("path", type=Path)

    r = sub.add_parser("register", help="원장에 올린다 — reviewed_by 가 있어야 한다")
    r.add_argument("source_id")
    r.add_argument("path", type=Path)
    r.add_argument("--use", required=True, choices=sorted(registry.VALID_USES))

    d = sub.add_parser("adopt", help="판(__c…)을 원본 자리로 올린다 — 2인 확인은 요구하지 않는다")
    d.add_argument("source_id")
    d.add_argument("stem", help="판을 뺀 원본 이름 (확장자 없이) 예: law_002015_20260402")

    a = ap.parse_args(argv[1:])
    if a.cmd == "adopt":
        return cmd_adopt(a.source_id, a.stem)
    # 🚨 `adopt` 는 경로가 아니라 이름을 받으므로 아래 존재 검사 앞을 지난다
    if not a.path.exists():
        print(f"🚨 {a.path} 가 없다")
        return 1
    if a.cmd == "count":
        return cmd_count(a.path)
    return cmd_register(a.source_id, a.path, a.use)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
