"""원본 저장과 수집 원장 (수집기 공통 규약 2·3·4·7 · D-92).

🚨 경로를 손으로 쓰지 않는다. 위치가 곧 게이트인데 사람이 위치를 고르면
   게이트가 사람 손에 달린다 (D-19).

배치 (D-92)
    data/raw/<계열>/          무손상 원본 · 등급 혼재 · 🚨 소비 금지
    data/derived/             파생물
    data/g3 · g2_facts · …    판정이 끝난 산출물
    data/manifest.jsonl       수집 원장 — 내용 없음. 유일하게 커밋되는 것
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collect import registry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
DERIVED = DATA / "derived"
MANIFEST = DATA / "manifest.jsonl"


class StoreError(RuntimeError):
    """저장을 거부한 이유."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def raw_dir(family: str) -> Path:
    """data/raw/<계열>/ — 없으면 만든다.

    계열은 수집리스트 v1.2 의 표기를 따른다 (law · mfds · ftc · kcia …).
    """
    d = RAW / family
    d.mkdir(parents=True, exist_ok=True)
    return d


def derived_dir(name: str) -> Path:
    d = DERIVED / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_raw(
    source_id: str,
    family: str,
    filename: str,
    payload: bytes,
    *,
    url: str,
    rows: int | None = None,
) -> Path | None:
    """원본을 무손상 저장하고 원장에 1행 남긴다.

    돌려주는 값:
        Path  — 새로 저장했다
        None  — sha256 이 같아 스킵했다 (규약 4)

    🚨 내용이 다른데 같은 이름이면 **덮어쓰지 않고 거부**한다 (규약 2).
       전처리는 언제든 재실행 가능해야 하고, 그 전제가 원본 불변이다.
    """
    digest = sha256(payload)
    path = raw_dir(family) / filename

    if path.exists():
        if sha256(path.read_bytes()) == digest:
            return None  # 규약 4 — 동일하면 스킵
        raise StoreError(
            f"{path} 가 이미 있고 내용이 다르다. 원본은 덮어쓰지 않는다 (규약 2). "
            "새 파일명(시행일·수집일 등)으로 저장하라."
        )

    path.write_bytes(payload)
    manifest_append(
        source_id=source_id,
        url=url,
        sha256=digest,
        bytes_=len(payload),
        rows=rows,
        path=str(path.relative_to(ROOT)),
    )
    return path


def manifest_append(
    *,
    source_id: str,
    url: str,
    sha256: str,
    bytes_: int,
    rows: int | None = None,
    path: str | None = None,
) -> None:
    """원장에 1행 append (규약 3).

    🚨 게이트 18 이 이 파일을 읽는다 — source_id 가 레지스트리에 있고 G1 이 아닐 것.
       원장이 곧 「raw 에 무엇이 들어왔는가」의 유일한 증언이다.
    """
    registry.spec(source_id)  # 미등록이면 여기서 거부된다
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "source_id": source_id,
        "fetched_at": _now(),
        "url": url,
        "sha256": sha256,
        "bytes": bytes_,
        "rows": rows,
        "path": path,
    }
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def stamp(row: dict[str, Any], source_id: str) -> dict[str, Any]:
    """산출 행에 provenance · redistributable 을 박는다 (규약 7 · D-71).

    🚨 나중에 못 한다. 섞인 뒤에는 어느 줄이 어디서 왔는지 알 수 없고,
       redistributable=false 가 한 줄이라도 섞이면 그 골든셋 전체를 공개할 수 없다.
       그래서 상속값을 **행에 복사**한다 — 소스 등급이 나중에 바뀌어도 조인의 답이 흔들리지 않게.
    """
    row["provenance"] = source_id
    row["redistributable"] = registry.redistributable(source_id)
    return row


def drop_raw_for_g2(source_id: str, family: str, filename: str, *, facts_path: Path) -> None:
    """G2 소스의 원본을 삭제한다 (D-17 · D-92).

    🚨 「G2 = 추출된 사실만 · 원문 없음」과 「원본 무손상 저장」은 정면으로 부딪친다.
       화해는 이것이다 — 사실을 뽑은 뒤 원본을 지우고 manifest 의 sha256 만 남긴다.
       재실행은 보관본이 아니라 **재수집**으로 한다.

    사실 파일이 실제로 만들어진 뒤에만 지운다. 순서가 뒤집히면 둘 다 잃는다.
    """
    if not registry.is_g2(source_id):
        raise StoreError(f"{source_id!r} 는 G2 가 아니다. 이 경로를 쓰지 않는다.")
    if not facts_path.exists() or facts_path.stat().st_size == 0:
        raise StoreError(f"{facts_path} 가 비어 있다. 사실을 뽑기 전에 원본을 지우면 둘 다 잃는다.")
    target = RAW / family / filename
    if target.exists():
        target.unlink()
