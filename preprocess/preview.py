"""preprocess/preview.py — 추출을 **임시 폴더에** 돌려 지금 파생물과 맞대 본다 (2026-09-21 · D-256).

  uv run python -m preprocess.preview <원천 id>          # 무엇이 바뀌는지 — 수만 낸다
  uv run python -m preprocess.preview <원천 id> --keep   # 임시 폴더를 지우지 않는다(열어 볼 때)

팀장 판정 (나) — 사본(팀장 기기)은 원문 거울로 원문을 **읽되** 파생물은 만들지 않는다 (D-226 그대로).
⛔ 종전에는 「이 고침이 파생물을 몇 행 바꾸나」를 정본(클론 B)에서만 잴 수 있었다 — `extract --dump` 가 정본 전용이고,
   그 명령은 `data/derived/` 를 **덮어쓴다.** 2026-09-21 마스킹 고침의 영향을 A 에서 못 재고 B 로 넘겼다.

★ **어떻게** — 추출 모듈의 **모듈 수준 경로 상수** 중 `data/derived/…` 를 가리키는 것을 임시 폴더로 돌려 놓고
  `--dump` 로 돌린다. 원문(`data/raw`)은 그대로 읽는다. 끝나면 상수를 되돌린다.
🔴 **저장소 파생물을 한 바이트라도 건드렸으면 🔴 로 멈춘다** — 돌리기 전·후의 `data/derived` 파일 목록·크기·수정 시각을
   맞댄다. 추출기가 상수를 안 거치고 쓰는 자리가 생기면 여기서 드러난다(`tests/test_preview.py` 가 모양을 지킨다).
⛔ 내용은 찍지 않는다 — 파일마다 **같다/다르다 · 줄 수 · 더해진 줄 · 빠진 줄 수**만 낸다.
🚨 원문캐시(`mfds_press_pdf/tables` 등)도 임시 폴더로 간다 — 캐시가 없으면 원문을 다시 파싱하므로 느릴 수 있다.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import importlib
import pathlib
import shutil
import sys
import tempfile
from collections.abc import Iterator

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED_REL = pathlib.PurePath("data", "derived")


def _derived_rel(v: pathlib.PurePath) -> pathlib.PurePath | None:
    """경로 상수가 파생물 폴더를 가리키면 그 안의 상대 경로. 아니면 None."""
    p = pathlib.PurePath(v)
    if not p.is_absolute():
        parts = p.parts
        return pathlib.PurePath(*parts[2:]) if parts[:2] == DERIVED_REL.parts else None
    try:
        return p.relative_to(ROOT / DERIVED_REL)
    except ValueError:
        return None


def _state(base: pathlib.Path) -> dict[str, tuple[int, int]]:
    """`data/derived` 의 (크기, 수정 시각 ns) — 🚨 파일을 열지 않는다."""
    if not base.is_dir():
        return {}
    return {
        str(f.relative_to(base)): (f.stat().st_size, f.stat().st_mtime_ns)
        for f in base.rglob("*")
        if f.is_file()
    }


@contextlib.contextmanager
def redirected(module, tmp: pathlib.Path) -> Iterator[dict[str, pathlib.PurePath]]:
    """모듈의 파생물 경로 상수를 `tmp` 아래로 돌린다 — 나올 때 되돌린다. 돌린 것 `{이름: 상대 경로}`."""
    saved: dict[str, object] = {}
    moved: dict[str, pathlib.PurePath] = {}
    for name, v in list(vars(module).items()):
        if isinstance(v, pathlib.PurePath):
            rel = _derived_rel(v)
            if rel is not None:
                saved[name] = v
                moved[name] = rel
                setattr(module, name, tmp / rel)
    try:
        yield moved
    finally:
        for name, v in saved.items():
            setattr(module, name, v)


def _digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compare(tmp: pathlib.Path, base: pathlib.Path) -> list[tuple[str, str]]:
    """임시 폴더에 나온 파일마다 지금 파생물과 맞댄 한 줄 — `(상대 경로, 요약)`. 🚨 내용은 안 낸다."""
    out: list[tuple[str, str]] = []
    for f in sorted(x for x in tmp.rglob("*") if x.is_file()):
        rel = str(f.relative_to(tmp))
        orig = base / rel
        if not orig.is_file():
            out.append((rel, f"🆕 지금은 없는 파일 · {f.stat().st_size:,} B"))
            continue
        if _digest(f) == _digest(orig):
            out.append((rel, "✅ 같다"))
            continue
        try:
            a = orig.read_text(encoding="utf-8").splitlines()
            b = f.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            out.append(
                (rel, f"🔄 다르다 (바이너리) · {orig.stat().st_size:,} → {f.stat().st_size:,} B")
            )
            continue
        ca, cb = collections.Counter(a), collections.Counter(b)
        gone, came = sum((ca - cb).values()), sum((cb - ca).values())
        out.append(
            (rel, f"🔄 다르다 · {len(a):,} → {len(b):,}줄 · 더해진 줄 {came:,} · 빠진 줄 {gone:,}")
        )
    return out


def run(source: str, *, keep: bool = False) -> int:
    from preprocess import EXTRACTORS  # noqa: PLC0415 — 표는 한 곳 (D-99)

    name = EXTRACTORS.get(source)
    if name is None:
        print(f"🔴 {source} 의 추출 모듈이 없다 — 아는 것: {', '.join(sorted(EXTRACTORS))}")
        return 1
    module = importlib.import_module(name)
    base = ROOT / DERIVED_REL
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="copylane-preview-"))
    before = _state(base)
    rc = 1
    try:
        with redirected(module, tmp) as moved:
            if not moved:
                print(
                    f"🔴 {name} 에 파생물 경로 상수가 없다 — 어디에 쓰는지 몰라 미리보기를 못 한다"
                )
                return 1
            argv, sys.argv = sys.argv, [name, "--dump"]
            try:
                rc = int(module.main() or 0)
            finally:
                sys.argv = argv
        after = _state(base)
        touched = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if touched:
            print(f"🔴 미리보기가 저장소 파생물을 건드렸다 — {touched[:5]}")
            print("   추출기가 경로 상수를 안 거치고 쓴다. 그 자리를 상수로 옮긴다 (D-226 · D-256)")
            return 1
        if rc != 0:
            print(f"🔴 추출이 {rc} 로 끝났다 — 위 메시지를 본다. 저장소 파생물은 안 바뀌었다")
            return rc
        print(f"\n── 미리보기 — {source} ({name}) · 저장소 파생물은 안 바뀌었다 ──")
        rows = compare(tmp, base)
        for rel, what in rows:
            print(f"  {rel:48} {what}")
        if not rows:
            print("  ⬜ 나온 파일이 없다")
        if keep:
            print(f"\n  임시 폴더 — {tmp}  (🚨 마스킹 뒤 파생물이지만 커밋·공유하지 않는다)")
        return 0
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="추출 미리보기 — 임시 폴더에 돌려 지금 파생물과 맞댄다 (D-256)"
    )
    ap.add_argument("source")
    ap.add_argument("--keep", action="store_true", help="임시 폴더를 남긴다")
    a = ap.parse_args()
    return run(a.source, keep=a.keep)


if __name__ == "__main__":
    raise SystemExit(main())
