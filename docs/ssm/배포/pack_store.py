#!/usr/bin/env python3
"""pack_store.py — 서버로 SFTP 할 **파생물 묶음**을 내 PC 에서 만든다 (2026-10-15 · 소성민).

서버는 공유 저장소(팀 Google Drive)를 붙이지 않는다(요청 ② 제안 (가)). 대신 이 PC 의 공유 저장소에서
**배포 커밋의 파생물 원장이 가리키는 객체만** 골라, 서버의 `data-sync` 가 읽는 구조 그대로 복사한다.

쓰는 법 — 내 PC · 저장소 루트 · Google Drive for desktop 이 켜져 있을 때
  git checkout <배포 커밋>                                    # 서버의 DEPLOY_REF 와 같은 커밋
  uv run python docs/ssm/배포/pack_store.py --out C:\\CopyLane_upload
  uv run python docs/ssm/배포/pack_store.py --out C:\\CopyLane_upload --check   # 복사 없이 무엇이 갈지만

결과
  C:\\CopyLane_upload\\copylane-derived\\objects\\<sha 앞 2자>\\<sha256>
  → MobaXterm SFTP 로 `copylane-derived` 폴더째 서버의 `~/CopyLane_store/` 아래에 올린다
  → 서버 `.env` 의 `DATA_STORE=/home/ubuntu/CopyLane_store`

무엇을 고르나 — 정본은 저장소 코드다. 여기서 다시 정하지 않는다
  · 원장(`data/derived_manifest.jsonl`)의 행 중 `scripts.derived_manifest.moved()` 가 참인 것
    (원천 · 표본 · 생성물 · git 이 나르는 분할표 제외 · 원문캐시는 옮기지 않는다 — D-247 · D-249)
  · 같은 sha 는 한 번만
  · 복사한 바이트의 sha256 을 다시 재서 원장과 다르면 **멈춘다** (D-220 · 서버의 data-sync 도 다시 잰다)

🚨 요청 ② 3번(재배포 불가 행을 서버에 실을지)이 판정되기 전에는 묶음을 만들어도 **올리지 않는다.**
   부류별 개수 · 크기를 출력하니 판정 자료로 쓴다.
🚨 `--out` 은 저장소 폴더 밖이어야 한다 — 저장소 안에 두면 git 에 섞인다.
🚨 묶음 폴더는 서버에 올린 뒤 지운다. 발표 뒤 서버 사본은 디스크 삭제로 지운다.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts import data_store as ds  # noqa: E402
from scripts import derived_manifest as dm  # noqa: E402


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def wanted() -> list[dict[str, object]]:
    """원장에서 서버가 받아야 할 행 — data-sync 와 같은 규칙(dm.moved)."""
    led = dm.ledger()
    if not led:
        raise SystemExit(
            "[중단] data/derived_manifest.jsonl 이 없다 — 저장소 루트에서, 배포 커밋을 체크아웃하고 실행한다"
        )
    rows = [r for p, r in led.items() if dm.moved(p, str(r["부류"]))]
    bad = ds.unsafe(rows)
    if bad:
        raise SystemExit(f"[중단] 원장에 경로 · sha 모양이 이상한 행이 있다 — {bad[:3]}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", required=True, help="묶음을 만들 폴더 (저장소 밖)")
    ap.add_argument("--check", action="store_true", help="복사하지 않고 무엇이 갈지만 본다")
    args = ap.parse_args()

    out = pathlib.Path(args.out).expanduser().resolve()
    if out == ROOT or ROOT in out.parents:
        print(f"[중단] --out 이 저장소 안이다 — {out}")
        return 1

    rows = wanted()
    by_sha: dict[str, dict[str, object]] = {}
    for r in rows:
        by_sha.setdefault(str(r["sha256"]), r)

    kinds: collections.Counter[str] = collections.Counter()
    sizes: collections.Counter[str] = collections.Counter()
    for r in rows:
        kinds[str(r["부류"])] += 1
        sizes[str(r["부류"])] += int(r["bytes"])  # type: ignore[call-overload]
    print("서버가 받아야 할 파생물 (배포 커밋의 원장 기준)")
    for k in sorted(kinds):
        print(f"  {k:<6} {kinds[k]:>4}개  {sizes[k] / 1e6:>7.1f} MB")
    print(
        f"  {'합계':<6} {len(rows):>4}개  {sum(sizes.values()) / 1e6:>7.1f} MB  (객체 {len(by_sha)}개 — 같은 내용은 한 번)"
    )

    try:
        src = ds.store_root()  # <DATA_STORE>/copylane-derived — 없으면 이유를 말하고 멈춘다
    except ds.StoreError as e:
        print(f"[중단] {e}")
        return 1
    missing = [
        r["경로"] for s, r in by_sha.items() if not ds.object_ok(ds._obj(src, s), r["bytes"])
    ]
    if missing:
        print(
            f"[중단] 이 PC 의 공유 저장소에 없거나 크기가 다른 객체 {len(missing)}개 — 드라이브 동기화를 기다리거나 정본 기기에 data-publish 를 요청한다"
        )
        for p in missing[:10]:
            print(f"    {p}")
        return 1
    if args.check:
        print(f"[확인] 원본 {src} 에 모두 있다 — --check 를 빼고 다시 돌리면 {out} 에 만든다")
        return 0

    dst_root = out / ds.LAYOUT
    copied = skipped = 0
    for sha, r in by_sha.items():
        s, d = ds._obj(src, sha), ds._obj(dst_root, sha)
        if ds.object_ok(d, r["bytes"]) and _sha256(d) == sha:
            skipped += 1
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(s, d)
        if _sha256(d) != sha:
            d.unlink(missing_ok=True)
            print(
                f"[중단] 복사한 바이트의 sha 가 원장과 다르다 — {r['경로']} (원본이 오염됐을 수 있다 · 팀장에게 알린다)"
            )
            return 1
        copied += 1
    print(f"[OK]   {dst_root}  복사 {copied} · 이미 있음 {skipped}")
    print(
        "다음  MobaXterm SFTP → 서버 ~/CopyLane_store/ 아래로 copylane-derived 폴더째 끌어다 놓는다"
    )
    print("      서버에서 bash deploy_server.sh data 가 sha 를 다시 재며 받는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
