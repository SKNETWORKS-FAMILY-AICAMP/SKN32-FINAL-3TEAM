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


def _today() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


#: 판을 가르는 표. 🚨 `__c` 두 글자다 — 한 글자면 원천의 이름과 부딪힌다.
#:    법령 파일이 이미 `law_002011_20250121.xml` 처럼 밑줄 하나를 쓰고 있어서,
#:    `_c...` 로 두면 원천이 준 이름의 일부인지 우리가 붙인 것인지 구분이 안 된다.
EDITION_MARK = "__c"


def edition_name(filename: str, day: str) -> str:
    """`page_0001.json` · `20260906` → `page_0001__c20260906.json`.

    🚨 이미 판 표시가 붙은 이름에 또 붙이지 않는다 — `__c20260906__c20260907` 이 되면
       원래 이름이 무엇이었는지 사람이 못 읽는다. 날짜만 갈아 끼운다.
    """
    p = Path(filename)
    stem = p.stem.split(EDITION_MARK, 1)[0]
    return f"{stem}{EDITION_MARK}{day}{p.suffix}"


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
        Path  — 새로 저장했다 (🚨 **이름이 넘긴 것과 다를 수 있다** — 아래 「새 판」)
        None  — sha256 이 같아 스킵했다 (규약 4)

    🚨 **덮어쓰지 않는다** (규약 2). 전처리는 언제든 재실행 가능해야 하고, 그 전제가
       원본 불변이다. 이건 안 바뀌었다 — 아래도 덮어쓰지 않는다.

    ── 🔴 같은 이름, 다른 내용 → **새 판으로 저장한다** (2026-09-06 · 팀장 결정) ──

    예전에는 여기서 `StoreError` 로 멈추고 「새 파일명으로 저장하라」고 사람에게 시켰다.
    2026-09-06 전수조사에서 그 자리가 **셋** 나왔고 셋 다 원인이 같았다 —

        law_002011_20250121.xml             −5 B   시행일 그대로, 본문 정정
        mfds_sanctions/page_0001.json     +179 B   시계열 — 처분이 추가됨
        mfds_hf_individual/page_0001.json   ±0 B   길이 그대로, 값 정정

    🚨 **파일명이 「원천의 어느 시점인가」를 담지 않는다.** `{ID}_{시행일}` 은 「시행일이
       같으면 같은 판」을, `page_{N}` 은 「N번째 장은 늘 같다」를 전제하는데 둘 다 깨졌다.
       원천이 살아 있는 한 이 자리는 계속 늘고, 그때마다 팀원의 수집이 멈춘다.

    ★ 그래서 **`StoreError` 메시지가 사람에게 시키던 일을 그대로 자동화한다** —
      `page_0001.json` → `page_0001__c20260906.json` (`c` = collected).
      규약 2(덮어쓰지 않음)도 규약 4(동일하면 스킵)도 그대로 산다.

    🚨 **하루에 두 번 갈리면 그때는 멈춘다.** 그건 원천이 바뀐 것이 아니라 **응답이
       호출마다 다른 것**이고(레코드 순서 비결정 등), 자동으로 판을 만들면 돌릴 때마다
       파일이 불어난다. 자동화의 유일한 위험이 그것이라 거기에 사람 검문소를 남겼다.
       (`mfds_hf_individual` 은 재호출로 안정성을 확인했다 — 2026-09-06.)

    🚨 새 판을 만들 때는 **반드시 화면에 남긴다.** 조용히 다른 이름으로 저장하는 것이
       이 설계의 값이자 위험이다. 부르는 쪽은 자기가 넘긴 `filename` 을 찍으므로
       여기서 안 찍으면 아무도 모른다.
    """
    digest = sha256(payload)
    path = raw_dir(family) / filename
    supersedes: str | None = None

    if path.exists():
        if sha256(path.read_bytes()) == digest:
            return None  # 규약 4 — 동일하면 스킵

        versioned = path.with_name(edition_name(filename, _today()))
        if versioned.exists():
            if sha256(versioned.read_bytes()) == digest:
                return None  # 오늘 판을 이미 받았다
            raise StoreError(
                f"{versioned} 가 이미 있고 **또 내용이 다르다**.\n"
                "  🚨 하루에 두 번 갈렸다 — 원천이 바뀐 것이 아니라 **응답이 호출마다\n"
                "     다를** 수 있다 (레코드 순서 비결정 · 응답에 유동 필드 …).\n"
                "  자동으로 판을 더 만들지 않는다 — 돌릴 때마다 파일이 불어난다.\n"
                "  두 판을 비교해 무엇이 다른지 보고, 원천의 성질을 원장에 적어라."
            )

        supersedes = str(path.relative_to(ROOT))
        # 🚨 라이브러리에서 화면에 찍는 것이 깔끔하지 않다는 건 안다. 그런데 이 한 줄이
        #    없으면 파일 이름이 조용히 바뀐다 — 안 보이는 것보다 안 깔끔한 편이 낫다.
        print(
            f"  🔴 새 판 — {filename} 이(가) 이미 있고 내용이 다르다.\n"
            f"     {versioned.name} 으로 저장한다. 원본은 그대로 둔다 (규약 2).\n"
            f"     🚨 원천이 같은 이름으로 다른 것을 준다는 뜻이다 — 원장에 적어라 (D-54)."
        )
        path = versioned

    path.write_bytes(payload)
    manifest_append(
        source_id=source_id,
        url=url,
        sha256=digest,
        bytes_=len(payload),
        rows=rows,
        path=str(path.relative_to(ROOT)),
        supersedes=supersedes,
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
    supersedes: str | None = None,
) -> None:
    """원장에 1행 append (규약 3).

    🚨 게이트 18 이 이 파일을 읽는다 — source_id 가 레지스트리에 있고 G1 이 아닐 것.
       원장이 곧 「raw 에 무엇이 들어왔는가」의 유일한 증언이다.

    🚨 `supersedes` — 이 행이 **어느 파일의 새 판인가** (2026-09-06 신설).
       파일명만으로도 짐작은 되지만, 짐작과 기록은 다르다. 판이 여럿 쌓인 뒤에
       「이게 무엇의 다음 판인가」를 이름 규칙으로 되짚게 만들지 않는다.
       옛 행에는 이 칸이 없다 — 없으면 `None` 이고, 그것은 「새 판이 아니다」는 뜻이다.
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
    # 🚨 새 판일 때만 칸을 만든다 — 안 그러면 기존 1만 행과 새 행의 모양이 달라지고,
    #    `null` 만 든 칸이 10,000줄 붙는다. 없는 것과 비어 있는 것은 다르다.
    if supersedes:
        row["supersedes"] = supersedes
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
