"""모델 잠금 — **어느 모델 판을 쓰는지는 git 이 정한다** (🆕 2026-10-13 · D-333).

⛔ **무엇이 있었나** — 판정 인코더의 판은 기기마다 환경 변수(`COPYLANE_MODEL_DIR`) 하나로 골랐고,
   그 폴더가 어느 판인지는 **가중치 지문(`model.safetensors` 앞 12자)** 으로만 확인했다.
   카드 17 의 F1 최대 판과 채택 판은 가중치가 같고 `label_scheme.json`(문턱)만 다르다 — 지문이 같아
   가를 수 없었고, 팀원 한 명이 다른 문턱의 판으로 28 건을 돌렸다(클론 A 인계 10-13 §4 ⑤).
   그리고 판을 바꾼 사실이 아무 데도 남지 않았다 — 판정 파라미터를 환경으로 열지 않는다는 원칙(D-205)의 구멍이다.

★ 그래서 셋을 나눈다 —
    제출   공유 드라이브 `CopyLane_store/copylane-models/` — 팀원이 올린다(편집자). 올렸다고 쓰이지 않는다
    채택   이 파일이 읽는 `models.lock.json`(git) — 판 이름 · **파일별 sha256 · 크기** · 베이스 · 근거 D 번호
    사용   기기의 `models/<판>/` — 열 때 이 파일과 **파일 전부**를 맞춰 본다

🔴 판정은 **내용**으로 한다 — 폴더 이름은 기기마다 달라도 된다. 파일 집합과 sha 가 잠금의 한 판과 같아야
   그 판이다. 하나라도 다르면 「잠금 밖」이다 (D-220 — 모르는 것을 아는 판으로 세지 않는다).
🚨 앱은 잠금 밖 판을 올리지 않는다(`app/encoder.py` `checked_dir`) — 실험은 도구 인자로 한다
   (`scripts/eval_graph.py --encoder` · D-205). 도구는 잠금 밖도 돌리되 표지에 「잠금 밖」을 남긴다.
🚨 이 파일은 **읽기만** 한다. 잠금을 쓰는 것은 `scripts/model_lock.py` 하나다 (D-99).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "models.lock.json"
MODELS = ROOT / "models"

#: 잠금 형식의 판. 형식이 바뀌면 올리고, 읽는 쪽이 모르는 판이면 멈춘다 (D-220)
VERSION = 1
#: 역할 — 인코더 · 고쳐 쓰기(sLLM) 1단계 · 2단계. 🚨 sLLM 두 칸은 자리만 있다(D-333 결정 5 — 연결은 다음 단계)
ROLES = ("encoder", "sllm_stage1", "sllm_stage2")
#: 드라이브 · 탐색기가 폴더에 **스스로 만드는** 파일 — 판의 일부가 아니므로 대조에서 뺀다. `[관행]`
#: ⛔ 빼지 않으면 공유 드라이브에서 폴더째 받은 판이 전부 「잠금 밖」이 된다 —
#:    `CopyLane_store/copylane-models/` 의 모든 폴더에 `desktop.ini` 가 있다(2026-10-13 실측).
IGNORED = frozenset({"desktop.ini", "Thumbs.db", ".DS_Store"})

ADOPTED = "채택"
ROLLBACK = "되돌림"
OUTSIDE = "잠금 밖"

_SHA = re.compile(r"[0-9a-f]{64}")
_DECISION = re.compile(r"D-\d+")


class LockError(RuntimeError):
    """잠금 파일을 읽지 못했거나 형식이 틀렸다 — 무엇을 고치면 되는지를 담는다."""


def sha256_file(path: Path) -> str:
    """파일의 sha256 — 1 MiB 씩 읽는다(가중치는 수백 MB 다)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan(folder: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """폴더 바로 아래 파일의 `{이름: {sha256, bytes}}` 와 **하위 폴더 이름**.

    🚨 하위 폴더는 판의 일부가 아니다 — 있으면 부르는 쪽이 「잠금 밖」으로 센다. 그 안을 읽지 않는다.
       ⛔ 카드 17 공유 폴더가 바로 아래와 `seed49/` 에 `label_scheme.json` 을 둘 두고 있었다(오늘 사고의 자리).
    """
    if not folder.is_dir():
        raise LockError(f"모델 폴더가 없다 — {folder}")
    files: dict[str, dict[str, Any]] = {}
    subdirs: list[str] = []
    for p in sorted(folder.iterdir()):
        if p.name in IGNORED:
            continue
        if p.is_dir():
            subdirs.append(p.name)
        elif p.is_file():
            files[p.name] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    return files, subdirs


def bundle_sha(files: dict[str, dict[str, Any]]) -> str:
    """판 지문 12자 — (이름, sha256) 목록 전체의 sha256. **파일 하나만 달라도 바뀐다.**

    ★ 가중치 지문과 다르다 — 문턱 파일(`label_scheme.json`)만 바꾼 판도 다른 값이 나온다.
    """
    text = "".join(f"{name}\t{files[name]['sha256']}\n" for name in sorted(files))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def validate(data: Any) -> list[str]:
    """잠금 내용의 틀린 곳 — 비면 맞다. 🚨 읽는 쪽 · 쓰는 쪽 · 게이트가 **같은 함수**로 본다 (D-99)."""
    bad: list[str] = []
    if not isinstance(data, dict):
        return ["최상위가 객체가 아니다"]
    if data.get("version") != VERSION:
        bad.append(f"version 이 {VERSION} 이 아니다 — {data.get('version')!r}")
    roles, bundles = data.get("roles"), data.get("bundles")
    if not isinstance(roles, dict) or not isinstance(bundles, dict):
        return [*bad, "roles · bundles 가 객체가 아니다"]
    for role in roles:
        if role not in ROLES:
            bad.append(f"모르는 역할 {role!r} — 아는 것 {list(ROLES)}")
    for name, b in bundles.items():
        if not isinstance(b, dict):
            bad.append(f"{name}: 판이 객체가 아니다")
            continue
        if b.get("role") not in ROLES:
            bad.append(f"{name}: 역할 {b.get('role')!r} 을 모른다")
        if not _DECISION.fullmatch(str(b.get("decision", ""))):
            bad.append(f"{name}: 근거 D 번호가 없다 — 채택은 판정이다 (D-100)")
        if not str(b.get("base", "")).strip():
            bad.append(f"{name}: 베이스(레지스트리 `models:` 키)가 없다 (D-23)")
        files = b.get("files")
        if not isinstance(files, dict) or not files:
            bad.append(f"{name}: 파일이 없다")
            continue
        for fname, meta in files.items():
            if fname in IGNORED or "/" in fname or "\\" in fname:
                bad.append(f"{name}: 판에 둘 수 없는 이름 {fname!r}")
            if not isinstance(meta, dict) or not _SHA.fullmatch(str(meta.get("sha256", ""))):
                bad.append(f"{name}/{fname}: sha256 이 64자 16진이 아니다")
            elif not isinstance(meta.get("bytes"), int) or meta["bytes"] < 0:
                bad.append(f"{name}/{fname}: bytes 가 0 이상의 정수가 아니다")
    for role, r in roles.items():
        if not isinstance(r, dict):
            bad.append(f"{role}: 역할 칸이 객체가 아니다")
            continue
        adopted, rollback = r.get("adopted"), r.get("rollback", [])
        if not isinstance(rollback, list):
            bad.append(f"{role}: rollback 이 목록이 아니다")
            continue
        for name in ([adopted] if adopted else []) + rollback:
            if name not in bundles:
                bad.append(f"{role}: 판 {name!r} 이 bundles 에 없다")
            elif bundles[name].get("role") != role:
                bad.append(f"{role}: 판 {name!r} 의 역할이 {bundles[name].get('role')!r} 이다")
        if adopted and adopted in rollback:
            bad.append(f"{role}: {adopted!r} 가 채택과 되돌림에 같이 있다")
    return bad


def load(path: Path = LOCK) -> dict[str, Any]:
    """잠금을 읽는다. 🔴 없거나 틀리면 멈춘다 — 「잠금이 없으니 아무 판이나」로 풀지 않는다 (D-220)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise LockError(f"잠금 파일이 없다 — {path.name} (git pull 로 받는다)") from e
    except (OSError, ValueError) as e:
        raise LockError(f"잠금 파일을 읽지 못했다 — {path.name}: {e}") from e
    bad = validate(data)
    if bad:
        raise LockError(f"잠금 파일 형식이 틀렸다 — {path.name}: " + " · ".join(bad[:5]))
    return data


@dataclass(frozen=True)
class Match:
    """폴더 하나를 잠금에 대 본 결과."""

    status: str  # 채택 · 되돌림 · 잠금 밖
    name: str | None  # 맞은 잠금의 판 이름 — 잠금 밖이면 None
    bundle: str  # 이 폴더의 판 지문 12자
    why: str = ""  # 잠금 밖이면 그 이유 — 채택 판과 무엇이 다른가


def _diff(files: dict[str, dict[str, Any]], want: dict[str, dict[str, Any]]) -> str:
    gone = sorted(set(want) - set(files))
    extra = sorted(set(files) - set(want))
    changed = sorted(n for n in set(want) & set(files) if want[n] != files[n])
    parts = []
    if gone:
        parts.append(f"빠진 파일 {gone}")
    if extra:
        parts.append(f"더 있는 파일 {extra}")
    if changed:
        parts.append(f"내용이 다른 파일 {changed}")
    return " · ".join(parts)


def match(folder: Path, role: str, lock: dict[str, Any] | None = None) -> Match:
    """폴더가 잠금의 어느 판인가 — **내용으로** 본다(폴더 이름은 보지 않는다)."""
    if role not in ROLES:
        raise LockError(f"모르는 역할 {role!r} — 아는 것 {list(ROLES)}")
    files, subdirs = scan(folder)
    mark = bundle_sha(files)
    data = lock if lock is not None else load()
    r = data["roles"].get(role) or {"adopted": None, "rollback": []}
    adopted = r.get("adopted")
    if not subdirs:
        for status, names in (
            (ADOPTED, [adopted] if adopted else []),
            (ROLLBACK, r.get("rollback", [])),
        ):
            for name in names:
                if data["bundles"][name]["files"] == files:
                    return Match(status, name, mark)
    why = []
    if subdirs:
        why.append(f"하위 폴더 {subdirs}")
    if adopted:
        d = _diff(files, data["bundles"][adopted]["files"])
        if d:
            why.append(f"채택 판({adopted})과 — {d}")
    else:
        why.append(f"잠금에 {role} 채택 판이 없다")
    return Match(OUTSIDE, None, mark, " · ".join(why) or "잠금의 어느 판과도 다르다")


def quick(folder: Path, name: str, lock: dict[str, Any] | None = None) -> str:
    """**해시 없이** 이름 · 크기만 대 본다 — 틀린 곳(비면 맞다). 진단(`doctor --env`)의 3초 안 검사용.

    🚨 크기가 같고 내용만 다른 것은 못 잡는다 — 그것은 `scripts/model_lock.py check` 가 sha 로 본다.
    """
    data = lock if lock is not None else load()
    want = data["bundles"][name]["files"]
    if not folder.is_dir():
        return f"폴더가 없다 — {folder}"
    have = {
        p.name: p.stat().st_size for p in folder.iterdir() if p.is_file() and p.name not in IGNORED
    }
    subdirs = sorted(p.name for p in folder.iterdir() if p.is_dir())
    bad = []
    gone = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    size = sorted(n for n in set(want) & set(have) if want[n]["bytes"] != have[n])
    if gone:
        bad.append(f"빠진 파일 {gone}")
    if extra:
        bad.append(f"더 있는 파일 {extra}")
    if size:
        bad.append(f"크기가 다른 파일 {size}")
    if subdirs:
        bad.append(f"하위 폴더 {subdirs}")
    return " · ".join(bad)


def entry(folder: Path, role: str, base: str, decision: str) -> dict[str, Any]:
    """폴더를 잠금의 한 판으로 — `scripts/model_lock.py add` 가 쓴다. 🔴 하위 폴더가 있으면 멈춘다."""
    files, subdirs = scan(folder)
    if subdirs:
        raise LockError(
            f"하위 폴더가 있다 — {subdirs}. 판은 폴더 바로 아래 파일만이다 — 쓸 파일만 남긴 폴더로 다시 한다"
        )
    if not files:
        raise LockError(f"파일이 없다 — {folder}")
    return {"role": role, "base": base, "decision": decision, "files": files}
