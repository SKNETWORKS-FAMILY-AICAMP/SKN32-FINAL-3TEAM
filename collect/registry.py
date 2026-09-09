"""레지스트리 게이트 — 수집기의 첫 줄 (수집기 공통 규약 1 · D-15).

🚨 게이트를 우회하는 경로를 만들지 않는다.
   등록되지 않았거나, 등급이 G1이거나, 그 용도가 deny면 **수집 자체를 거부**한다.
   "일단 받아두고 나중에 판정한다"는 경로가 있으면 그 경로로만 다니게 된다.
"""

from __future__ import annotations

import functools
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data_sources.yaml"  # 🚨 생성물 — 손으로 고치지 않는다
LEDGER = ROOT / "scripts/registry_review.yaml"  # 2인 확인 원장 — 이쪽이 입력이다

VALID_USES = {"U1", "U2", "U3", "U4"}

# 🚨 크롤링형은 robots 확인 기록 없이는 돌지 않는다 (규약 6).
#    access 값에 아래가 들어 있으면 크롤링으로 본다.
CRAWL_ACCESS = {"크롤링", "게시판", "스크래핑"}


class RegistryError(RuntimeError):
    """수집을 거부한 이유. 🚨 삼키지 말 것 — 이 예외가 게이트다."""


@functools.lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    """레지스트리를 읽는다.

    🚨 **한 번만 읽는다.** 이 함수는 `spec()`·`redistributable()` 을 거쳐
       `store.stamp()` 에서 **산출 행마다** 불린다. 캐시가 없으면 행 하나에
       62KB YAML 파싱이 붙는다 — 2026-09-09 실측 **142ms/건**이고,
       1,420행짜리 추출 하나가 **202초**가 된다(그래서 발견했다).
       골든셋 1,910행 · ftc 16,506행도 같은 값을 내고 있었다.

    🚨 실행 중에 이 파일은 바뀌지 않는다 — 바꾸는 것은 `gen_registry.py` 이고
       별도 실행이다. `mark_collected()` 도 원장(`registry_review.yaml`)에만 쓴다.
       그래도 바꿔야 하면 `_load.cache_clear()` 를 부른다.
    """
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}


def spec(source_id: str) -> dict[str, Any]:
    """소스 정의를 돌려준다. 없으면 거부한다."""
    sources = _load().get("sources") or {}
    entry = sources.get(source_id)
    if not isinstance(entry, dict):
        raise RegistryError(
            f"{source_id!r} 가 data_sources.yaml 에 없다. "
            "등록되지 않은 소스는 수집하지 않는다 (D-15)."
        )
    return entry


def require(source_id: str, use: str) -> dict[str, Any]:
    """수집기의 첫 줄. 통과하면 소스 정의를, 아니면 RegistryError 를 던진다.

    검사 순서는 되돌릴 수 없는 것부터다 — G1 은 받는 순간 끝이다.
    """
    if use not in VALID_USES:
        raise RegistryError(f"use={use!r} 는 U1~U4 가 아니다")

    s = spec(source_id)
    grade = s.get("grade")

    if grade == "G1":
        raise RegistryError(
            f"{source_id!r} 는 G1(배제)이다. 🚨 수집 자체를 하지 않는다 — "
            "받아서 지우는 것과 받지 않는 것은 다르다."
        )
    if grade not in {"G0", "G2", "G3"}:
        raise RegistryError(f"{source_id!r}: grade 가 없거나 잘못됐다 ({grade!r})")

    verdict = (s.get("use") or {}).get(use)
    if verdict != "allow":
        raise RegistryError(
            f"{source_id!r} 의 {use} 는 {verdict!r} 다. 등급 {grade} 에서 이 용도는 열려 있지 않다."
        )

    if not s.get("reviewed_by"):
        raise RegistryError(
            f"{source_id!r} 에 reviewed_by 가 없다. "
            "🚨 수집을 시작하는 순간이 2인 확인의 마지노선이다 (D-66 · D-90 ④)."
        )

    # 🚨 **수집기는 GATED 를 아예 보지 않고 있었다.** 탐침(probe)이 막던 조건을
    #    정작 실제로 받아 오는 쪽은 검사하지 않았다 — 승인 없이 받는 경로가 열려 있었다.
    #    탐침을 만들면서 드러났다 (D-109).
    if "GATED" in set(s.get("constraints") or []) and not s.get("approved_at"):
        raise RegistryError(
            f"{source_id!r} 는 GATED 인데 approved_at 이 없다 — 승인 없이 받지 않는다. "
            "승인 후 scripts/registry_review.yaml 에 approved_at·approved_by 를 적는다."
        )

    access = str(s.get("access") or "")
    if any(k in access for k in CRAWL_ACCESS) and not s.get("robots_checked_at"):
        raise RegistryError(
            f"{source_id!r} 는 크롤링형인데 robots_checked_at 이 없다 (규약 6). "
            "robots.txt 를 확인하고 레지스트리에 날짜를 적은 뒤 다시 실행하라."
        )

    return s


def probe(source_id: str) -> dict[str, Any]:
    """🚨 **탐침의 첫 줄** — `require()` 와 다른 게이트다 (D-109).

    탐침은 **열어보고 세는 것**이고 수집이 아니다. 그래서 `reviewed_by` 를 요구하지 않는다 —
    요구하면 자기모순이 된다. D-72 가 *"확인 후 2인 판정으로 승격한다"* 고 말하는데,
    **확인 수단 자체를 판정 뒤로 미루면 아무것도 확인할 수 없다.**

    막는 것은 그대로 막는다.

    * **G1** — 받는 순간 끝이다. 열어보는 것도 하지 않는다
    * **`manual`** — 🚨 자동 접근이 약관 위반이다. 탐침도 자동 접근이다 (D-108)
    * **`GATED`** — 신청·승인이 선행이다. 승인 전 접근은 조건 위반이다
    * **크롤링형인데 `robots_checked_at` 없음** — 규약 6 은 수집이 아니라 **접근**의 조건이다

    🚨 **용도(`use`)는 보지 않는다.** 용도는 「가져온 것을 무엇에 쓰는가」이고 탐침은
    아무것도 가져오지 않는다. G0 가 전 용도 `deny` 인 채로 탐침 대상인 것이 정상이다 —
    오히려 **G0 야말로 탐침이 가장 필요한 등급**이다.
    """
    s = spec(source_id)
    grade = s.get("grade")

    if grade == "G1":
        raise RegistryError(
            f"{source_id!r} 는 G1(배제)이다. 🚨 탐침도 하지 않는다 — "
            "받아서 지우는 것과 받지 않는 것은 다르다."
        )
    if s.get("status") == "manual":
        raise RegistryError(
            f"{source_id!r} 는 status: manual 이다. 🚨 자동 접근이 약관 위반이라 "
            "사람이 수기로만 본다 (D-108). 탐침도 자동 접근이다."
        )
    flags = set(s.get("constraints") or [])
    if "GATED" in flags and not s.get("approved_at"):
        raise RegistryError(
            f"{source_id!r} 는 GATED 인데 approved_at 이 없다 — 신청·승인이 선행이다. "
            "🚨 「신청했다」가 아니라 「승인됐다」를 적는다. 승인 전 접근은 조건 위반이고, "
            "그것은 탐침이라도 같다. 승인 후 scripts/registry_review.yaml 에 날짜를 적는다."
        )
    access = str(s.get("access") or "")
    if any(k in access for k in CRAWL_ACCESS) and not s.get("robots_checked_at"):
        raise RegistryError(
            f"{source_id!r} 는 크롤링형인데 robots_checked_at 이 없다 (규약 6). "
            "🚨 규약 6 은 수집이 아니라 **접근**의 조건이다 — 탐침에도 걸린다."
        )
    return s


def is_g2(source_id: str) -> bool:
    """G2 여부 — raw 를 사실 추출 후 삭제해야 하는 소스인가 (D-17 · D-92)."""
    return spec(source_id).get("grade") == "G2"


def redistributable(source_id: str) -> bool:
    """데이터 재배포 가능 여부. 🚨 등급과 다른 축이다 (D-71).

    AI Hub 6종이 그 함정이다 — 등급은 G3 인데 데이터셋 재배포는 막혀 있다.
    """
    return bool(spec(source_id).get("redistributable"))


def mark_collected(source_id: str) -> None:
    """수집 시각을 원장에 찍는다 (규약 3 · 게이트 15).

    🚨 data_sources.yaml 이 아니라 scripts/registry_review.yaml 에 쓴다.
       전자는 gen_registry.py 의 **생성물**이라, 거기에 적으면 다음 생성 때 사라진다
       (집행계약 §6 「생성 경로 — 손으로 고치지 않는 것」).

    require() 를 통과해야 여기 도달하므로, collected_at 이 찍히는 소스는
    reviewed_by 가 이미 있다 — 게이트 15 가 요구하는 순서 그대로다.
    """
    spec(source_id)  # 미등록이면 거부

    text = LEDGER.read_text(encoding="utf-8")
    today = date.today().isoformat()
    needle = f"\n{source_id}:\n"
    if needle not in text:
        raise RegistryError(
            f"{source_id!r} 가 {LEDGER.name} 에 없다. "
            "레지스트리를 다시 생성했다면 원장도 함께 갱신하라."
        )

    start = text.index(needle) + 1
    end = text.find("\n\n", start)
    end = len(text) if end == -1 else end
    block = text[start:end]
    if "collected_at:" not in block:
        raise RegistryError(f"{source_id!r} 블록에 collected_at 이 없다")

    new_block = re.sub(r"collected_at:\s*\S+", f"collected_at: {today}", block, count=1)
    LEDGER.write_text(text[:start] + new_block + text[end:], encoding="utf-8")

    # 🚨 원장을 고쳤으면 생성물도 다시 만들어야 게이트가 같은 것을 본다.
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/gen_registry.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
