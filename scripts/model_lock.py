#!/usr/bin/env python3
"""scripts/model_lock.py — **모델 잠금을 보고 쓰는 곳** (🆕 2026-10-13 · D-333).

  uv run python -m scripts.model_lock show                                   # 잠금의 역할별 판 · 판 지문
  uv run python -m scripts.model_lock check [<폴더>] [--role encoder]        # 이 폴더가 잠금의 어느 판인가 (sha 전수)
  uv run python -m scripts.model_lock add <폴더> --role encoder --as rollback --base kcbert_base --decision D-331

★ 읽고 맞춰 보는 규칙은 `app/model_lock.py` 하나다 — 여기는 그것을 부르고, 잠금을 **쓰는** 유일한 곳이다 (D-99).
🔴 `add` 는 채택(판정)을 기록한다 — 근거 D 번호 없이는 쓰지 않는다 (D-100). 잠금 파일은 git 이 나르고,
   커밋은 사람이 한다. 이 명령은 파일만 고친다.
🔴 이미 있는 이름에 **다른 내용**을 쓰지 않는다 — 공유 폴더 README 의 「올린 판은 고치지 않는다」를 코드로 지킨다.
🔴 베이스가 레지스트리 `models:` 에 없거나 배포 용도(U4)가 allow 가 아니면 쓰지 않는다 (D-23 · D-333 결정 6).
⬜ 공유 저장소의 보관소 복사 · 기기로 받기(`model-adopt` · `model-sync`)는 다음 단계다 (D-333 결정 4).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if sys.path[:1] != [
    str(ROOT)
]:  # 🚨 스크립트 경로로 불러도 `app` 을 찾게 (derived_manifest 와 같은 처방)
    sys.path.insert(0, str(ROOT))

from app import model_lock as ml  # noqa: E402

REGISTRY = ROOT / "data_sources.yaml"


def registry_problem(base: str, registry: Path = REGISTRY) -> str | None:
    """베이스 키가 레지스트리 `models:` 에 있고 배포 용도(U4)가 allow 인가 — 아니면 그 까닭. 🚨 게이트도 이 함수를 쓴다."""
    import yaml  # noqa: PLC0415 — 이 함수만 쓴다

    models = (yaml.safe_load(registry.read_text(encoding="utf-8")) or {}).get("models") or {}
    if base not in models:
        return f"베이스 {base!r} 가 레지스트리 `models:` 에 없다 — 아는 것 {sorted(models)} (D-23)"
    use = (models[base] or {}).get("use") or {}
    if use.get("U4") != "allow":
        return f"베이스 {base!r} 의 배포 용도(U4)가 allow 가 아니다 — {use.get('U4')!r} (D-71)"
    return None


def write(data: dict[str, Any], path: Path = ml.LOCK) -> None:
    """정렬해서 쓴다 — 같은 내용이면 같은 바이트다(diff 가 읽힌다)."""
    bad = ml.validate(data)
    if bad:
        raise ml.LockError("쓰려는 잠금이 틀렸다 — " + " · ".join(bad[:5]))
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def empty() -> dict[str, Any]:
    return {
        "version": ml.VERSION,
        "roles": {r: {"adopted": None, "rollback": []} for r in ml.ROLES},
        "bundles": {},
    }


def add(
    folder: Path,
    *,
    role: str,
    as_: str,
    base: str,
    decision: str,
    name: str | None = None,
    path: Path = ml.LOCK,
    registry: Path = REGISTRY,
) -> tuple[str, str]:
    """폴더를 잠금에 올린다 — (판 이름, 판 지문). `as_` 는 `adopted` · `rollback`."""
    if role not in ml.ROLES:
        raise ml.LockError(f"모르는 역할 {role!r} — 아는 것 {list(ml.ROLES)}")
    if as_ not in ("adopted", "rollback"):
        raise ml.LockError(f"--as 는 adopted · rollback 이다 — {as_!r}")
    if why := registry_problem(base, registry):
        raise ml.LockError(why)
    data = ml.load(path) if path.exists() else empty()
    new = ml.entry(folder, role, base, decision)
    name = name or folder.name
    old = data["bundles"].get(name)
    if old is not None and old["files"] != new["files"]:
        raise ml.LockError(
            f"이름 {name!r} 은 이미 잠금에 있고 내용이 다르다 — 판은 고치지 않는다. 새 이름으로 올린다"
        )
    for other, b in data["bundles"].items():
        if other != name and b["files"] == new["files"]:
            raise ml.LockError(f"같은 내용이 이미 {other!r} 로 잠금에 있다 — 그 이름을 쓴다")
    data["bundles"][name] = new
    r = data["roles"].setdefault(role, {"adopted": None, "rollback": []})
    rollback = [n for n in r["rollback"] if n != name]
    if as_ == "adopted":
        prev = r["adopted"]
        if prev and prev != name:
            rollback.insert(
                0, prev
            )  # 옛 채택 판은 되돌림 칸 맨 앞으로 — 지우지 않는다 (D-331 「v10 은 남긴다」)
        r["adopted"] = name
    else:
        if r["adopted"] == name:
            raise ml.LockError(
                f"{name!r} 은 지금 채택 판이다 — 되돌림으로 내리려면 다른 판을 채택한다"
            )
        rollback.insert(0, name)
    r["rollback"] = rollback
    write(data, path)
    return name, ml.bundle_sha(new["files"])


def _show() -> int:
    data = ml.load()
    for role in ml.ROLES:
        r = data["roles"].get(role) or {"adopted": None, "rollback": []}
        print(f"\n[{role}]")
        if not r["adopted"] and not r["rollback"]:
            print("  (비었다)")
        for label, names in (
            ("채택", [r["adopted"]] if r["adopted"] else []),
            ("되돌림", r["rollback"]),
        ):
            for n in names:
                b = data["bundles"][n]
                print(
                    f"  {label}  {n}  · 판 지문 {ml.bundle_sha(b['files'])}"
                    f" · 파일 {len(b['files'])}개 · 베이스 {b['base']} · {b['decision']}"
                )
    return 0


def _check(folder: Path | None, role: str) -> int:
    if folder is None:
        from app import encoder as enc  # noqa: PLC0415

        folder = enc.configured_dir()
        if folder is None:
            print(f"🟡 {enc.ENV_MODEL_DIR} 가 비었다 — 볼 폴더를 인자로 준다")
            return 1
    m = ml.match(folder, role)
    if m.status == ml.OUTSIDE:
        print(f"🔴 {ml.OUTSIDE} — {folder.name} · 판 지문 {m.bundle}\n   {m.why}")
        return 1
    print(f"✅ {m.status} 판 {m.name} · 판 지문 {m.bundle}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="모델 잠금 — 보기 · 대조 · 올리기 (D-333)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="잠금의 역할별 판")
    c = sub.add_parser("check", help="폴더가 잠금의 어느 판인가 — sha 전수")
    c.add_argument("folder", nargs="?", type=Path)
    c.add_argument("--role", default="encoder", choices=ml.ROLES)
    a = sub.add_parser("add", help="폴더를 잠금에 올린다 — 채택 · 되돌림")
    a.add_argument("folder", type=Path)
    a.add_argument("--role", required=True, choices=ml.ROLES)
    a.add_argument("--as", dest="as_", required=True, choices=("adopted", "rollback"))
    a.add_argument("--base", required=True, help="레지스트리 `models:` 의 키 (예: kcbert_base)")
    a.add_argument("--decision", required=True, help="근거 D 번호 (예: D-331)")
    a.add_argument("--name", default=None, help="판 이름 — 비우면 폴더 이름")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "show":
            return _show()
        if args.cmd == "check":
            return _check(args.folder, args.role)
        name, mark = add(
            args.folder,
            role=args.role,
            as_=args.as_,
            base=args.base,
            decision=args.decision,
            name=args.name,
        )
        print(f"✅ 잠금에 올렸다 — {name} · 판 지문 {mark} ({args.as_})")
        print("   🚨 models.lock.json 을 커밋해야 다른 기기가 이 판을 안다")
        return 0
    except ml.LockError as e:
        print(f"🔴 {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
