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

#: `require()` 를 부르는 **경로** — 🆕 2026-09-22 (권소라 보고). `register` 만 `status: manual` 을 받는다.
#:    🚨 둘 밖의 값은 거부한다 — 오타가 조용히 수집기 경로(더 엄격한 쪽)로 떨어지지 않게 (D-72).
VIA_COLLECT = "collect"
VIA_REGISTER = "register"
VALID_VIA = frozenset({VIA_COLLECT, VIA_REGISTER})

#: G2 원문 삭제(`store.drop_raw_for_g2`)를 부르는 곳 — `"모듈경로:함수명"`. 비어 있으면 G2 는 `require()` 에서 막힌다.
#: 🚨 손으로 켜지 않는다 — 게이트 테스트가 적힌 함수 본문에 `drop_raw_for_g2(` 가 있는지 본다 (D-92 · 2026-09-21).
G2_DROP_WIRED: tuple[str, ...] = ()

# 🚨 크롤링형은 robots 확인 기록 없이는 돌지 않는다 (규약 6).
# 🔴 **판단은 `collect.COLLECTORS` 표가 한다** (2026-09-10 · D-179).
#    ⛔ 종전에는 `access` 산문에 아래 낱말이 있는지로 봤다. 「자료실 PDF 다운로드」·
#       「보도자료 웹 공개」·「웹 서비스」가 목록에 없어 **HTML 을 긁는 소스 6건이
#       robots 검사를 통째로 지나갔다.** 표기 한 줄로 뚫리는 판정이었다 (D-167 · D-89).
#    ⬜ 아래 집합은 **표에 없는 소스**를 위한 보조 그물로만 남긴다 — 정본이 아니다.
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


def require(source_id: str, use: str, *, via: str = VIA_COLLECT) -> dict[str, Any]:
    """수집기의 첫 줄. 통과하면 소스 정의를, 아니면 RegistryError 를 던진다.

    검사 순서는 되돌릴 수 없는 것부터다 — G1 은 받는 순간 끝이다.

    `via` — 부르는 경로. 기본은 자동 수집기(`collect`). 사람이 받아 온 파일을 올리는
    `ingest register` 만 `via="register"` 로 부른다 — 그 경로에서만 `status: manual` 을 통과시킨다 (D-108).
    🚨 나머지 검사(G1 · 용도 · 2인 확인 · GATED · hold · G2 · 규약 6)는 **경로와 무관하게 같다** —
       사람이 손으로 받아 왔다는 사실이 판정을 면제하지 않는다.
    """
    if use not in VALID_USES:
        raise RegistryError(f"use={use!r} 는 U1~U4 가 아니다")
    if via not in VALID_VIA:
        raise RegistryError(f"via={via!r} 는 {sorted(VALID_VIA)} 가 아니다")

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

    # 🔴 **`require()` 가 `status` 를 아예 안 보고 있었다** (2026-09-09 · 팀장 지적).
    #    ⛔ `manual` 검사는 `probe()` 에만 있었다. 탐침은 막고 **실제로 받아 오는 쪽은
    #       안 막는** 모양이다 — D-109 에서 GATED 로 똑같은 일이 있었고, 그때 GATED 만
    #       옮겨 오고 `status` 는 그대로 두었다. **같은 함정을 두 번째로 밟았다.**
    #    🚨 적어 두기만 하고 아무것도 안 막으면 그건 보류가 아니라 **표시**다 (D-72).
    #    🚨 순서는 **되돌릴 수 없는 것부터**다(이 함수의 규칙) — G1 · 용도 · 2인 확인 ·
    #       GATED(외부 조건 위반) 다음이 우리 쪽 판정 상태다.
    # 🔄 2026-09-22 (권소라 보고 · mfds_cosmetic_sanction 엑셀 186건) — ⛔ 이 분기가 **경로를 안 봤다.**
    #    `ingest register` 도 첫 줄에서 여기를 부르므로, 거부 메시지가 안내하는 그 길(`register`)이 **같은 이유로 막혔다.**
    #    D-108 의 `manual` 은 「수집기가 절대 돌면 안 된다」이지 「받지 않는다」가 아니다 — 사람이 받은 파일은 올린다.
    #    ★ `register` 경로에서만 통과시킨다. 자동 수집기(기본 `via`)는 그대로 막는다.
    status = s.get("status")
    if status == "manual" and via != VIA_REGISTER:
        raise RegistryError(
            f"{source_id!r} 는 status: manual 이다 — 자동 접근이 약관 위반이라 "
            "사람이 수기로만 받는다 (D-108). 받아 온 파일은 `launcher.py register` 로 올린다."
        )
    if status == "hold":
        raise RegistryError(
            f"{source_id!r} 는 status: hold 다 — 판정이 끝나지 않았다. "
            "🚨 보류는 「나중에 보자」가 아니라 「지금은 안 받는다」다 (D-72). "
            "🚨 탐침(`probe`)은 막지 않는다 — 판정을 끝내려면 열어 봐야 한다 (D-109). "
            "풀려면 판정 근거를 남기고 scripts/gen_registry.py 의 STATUS 에서 내린다."
        )

    # 🔴 **G2 는 삭제 경로가 붙기 전에 받지 않는다** (2026-09-21 · 전수 재검토 G2 · 팀장 판정 (나)).
    #    D-92 — 「G2 소스의 raw 는 사실 추출 후 삭제하고 sha256 만 남긴다」(D-17 원문 미보관의 집행).
    #    ⛔ 삭제 함수(`store.drop_raw_for_g2`)는 있는데 **부르는 곳이 없다** — 받으면 원문이 영구히 남는다.
    #       지금은 G2 10개가 전부 hold/manual · 용도 deny 라 위에서 먼저 막히지만, 그것은 **우연**이다.
    #       판정이 풀리는 날 이 문이 없으면 「원문 없음」이 조용히 거짓이 된다 (D-72 — 적기만 하면 표시다).
    #    🚨 여는 법: G2 추출기가 사실 파일을 쓴 **뒤** `drop_raw_for_g2` 를 부르게 붙이고, 그 호출부를
    #       `G2_DROP_WIRED` 에 적는다. 게이트 테스트가 그 호출부가 실제로 있는지 본다 — 플래그만 켜면 실패한다.
    if grade == "G2" and not G2_DROP_WIRED:
        raise RegistryError(
            f"{source_id!r} 는 G2 다 — 사실 추출 뒤 원문을 지우는 경로가 아직 없어 받지 않는다 (D-92).\n"
            "  받으면 원문이 영구히 남아 「G2 는 원문 미보관」(D-17)이 거짓이 된다.\n"
            "  → G2 추출기에 `store.drop_raw_for_g2` 호출을 붙이고 collect/registry.py 의 G2_DROP_WIRED 에 그 위치를 적는다."
        )

    from collect import COLLECTORS, is_scraper  # noqa: PLC0415 — 순환 import 방지

    access = str(s.get("access") or "")
    scrapes = is_scraper(source_id) or (
        source_id not in COLLECTORS and any(k in access for k in CRAWL_ACCESS)
    )
    if scrapes and not s.get("robots_checked_at"):
        raise RegistryError(
            f"{source_id!r} 는 HTML 을 긁는 수집기로 가는데 robots_checked_at 이 없다 (규약 6).\n"
            "  🚨 판단은 `access` 산문이 아니라 `collect.COLLECTORS` 표가 한다 (D-179) —\n"
            "     종전에는 「자료실 PDF 다운로드」 같은 표기가 낱말표에 없어 그냥 지나갔다.\n"
            "  → robots.txt 를 확인하고 레지스트리에 날짜를 적은 뒤 다시 실행한다.\n"
            "     🚨 이미 잰 기록이 있으면 scripts/registry_rationale.yaml 을 본다."
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
    # ⛔ 2026-09-09 — 여기에 `hold` 검사를 넣었다가 **뺐다.** 기존 게이트가 잡았다:
    #    `test_탐침_게이트는_G1과_수기와_승인선행을_막는다` 가 「G0 가 탐침에서 막힌다」로 깨졌다.
    #    🚨 **탐침은 판정을 끝내려고 도는 것이다.** `hold` 인 소스야말로 탐침이 필요하다 —
    #       막으면 판정이 영영 안 끝난다. 이 함수의 docstring 이 이미 그렇게 적어 두었다.
    #    `hold` 는 **실제로 받아 오는 쪽**(`require`)에서 막는다.
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


#: 파생 행이 원천을 적는 칸 — 추출기는 `원천`, `store.stamp` 는 `provenance`, 사전은 `출처`(목록).
#: 🚨 셋 다 본다. 하나만 보면 다른 칸을 쓰는 산출물이 검사를 조용히 지나간다.
SOURCE_KEYS = ("provenance", "원천", "출처")


def sources_of(row: dict[str, Any]) -> set[str]:
    """행이 적은 원천 소스 id 들. 🚨 목록 칸(`출처`)과 글자 칸을 함께 편다."""
    got: set[str] = set()
    for k in SOURCE_KEYS:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            got.add(v.strip())
        elif isinstance(v, (list, tuple)):
            got |= {str(x).strip() for x in v if str(x).strip()}
    return got


def no_derivatives(source_id: str) -> bool:
    """`ND`(변경금지)가 붙은 소스인가 — 원문 그대로 색인 · 인용만 되고 파생 데이터셋은 안 된다."""
    return "ND" in set(spec(source_id).get("constraints") or [])


def assert_derivable(rows: Any, *, who: str, default: str | None = None) -> int:
    """🔴 **파생 데이터셋을 쓰기 직전의 게이트** (2026-09-25 · 팀장 판정 (가) · D-110).

    라벨 · 사전 · 학습 · 평가셋처럼 원문을 바꿔 만든 산출물은 `ND` 소스의 행을 담을 수 없다.
    ⛔ `U1: deny` 를 보지 않는다 — 그 칸은 「평가 전용」 뜻으로도 쓰였다(D-155 사례집이 deny 인데 사전으로 학습에 든다).
       법적 금지는 `ND` 가 진다.
    🔴 원천을 못 읽는 행은 **멈춘다** (D-220) — 모르는 행을 통과로 세면 이 게이트가 fail-open 이 된다.
       원천 칸이 없는 입력(예: 판독 원장)은 부르는 쪽이 `default` 로 원천을 적는다.
    🔴 레지스트리에 없는 원천도 멈춘다(`spec()` 이 거부한다).

    돌려주는 값은 검사한 행 수다 — 0 건 검사를 「통과」로 읽지 않게 부르는 쪽이 볼 수 있다.
    """
    n = 0
    blind = 0
    bad: dict[str, int] = {}
    for r in rows:
        n += 1
        srcs = sources_of(r) if isinstance(r, dict) else set()
        if not srcs and default:
            srcs = {default}
        if not srcs:
            blind += 1
            continue
        for sid in srcs:
            if no_derivatives(sid):
                bad[sid] = bad.get(sid, 0) + 1
    if blind:
        raise RegistryError(
            f"🔴 {who}: 원천을 적지 않은 행이 {blind}건 있다({'/'.join(SOURCE_KEYS)} 칸 없음). "
            "파생 데이터셋에는 원천을 모르는 행을 싣지 않는다 (D-220 · 변경금지 게이트)."
        )
    if bad:
        listed = ", ".join(f"{k} {v}행" for k, v in sorted(bad.items()))
        raise RegistryError(
            f"🔴 {who}: 변경금지(ND) 소스의 행이 파생 데이터셋에 들어오려 한다 — {listed}. "
            "ND 소스는 원문 그대로 색인 · 인용만 된다 (공공누리 제3·4유형 · D-110 · 2026-09-25 팀장 판정 (가))."
        )
    return n


def is_g2(source_id: str) -> bool:
    """G2 여부 — raw 를 사실 추출 후 삭제해야 하는 소스인가 (D-92 · D-17 원문 미보관)."""
    return spec(source_id).get("grade") == "G2"


def redistributable(source_id: str) -> bool:
    """데이터 재배포 가능 여부. 🚨 등급과 다른 축이다 (D-71).

    AI Hub 6종이 그 함정이다 — 등급은 G3 인데 데이터셋 재배포는 막혀 있다.
    """
    return bool(spec(source_id).get("redistributable"))


def mark_if_complete(source_id: str, *, saved: int, partial: bool) -> bool:
    """수집이 끝난 뒤 `collected_at` 을 찍을지 — 찍었으면 True. 🆕 2026-09-21 (전수 재검토 I8).

    ⛔ 같은 규칙(「저장 0 이면 안 찍는다 · `--limit` 이면 안 찍는다」)이 수집기마다 **손으로** 쓰여 있었고,
       `mfds_hf_board` 만 `--limit` 을 막았다. `law_api`·`ftc_body`·`mfds_press` 는 앞 5건만 받아도 「수집함」으로 찍었다 —
       **찍혔다 ≠ 받았다**(D-177 의 사촌). 같은 날 런처가 `--limit` 을 두 수집기에 더 넘기게 돼(코드 리뷰 #4) 드러났다.
    ★ 규칙은 여기 하나 (D-99). `partial` 은 부르는 쪽이 안다 — `--limit`·일부 페이지만 받은 경우.
    """
    if partial:
        print("🚨 일부만 받았다(--limit 등) — collected_at 을 찍지 않는다 (원장의 날짜는 그대로)")
        return False
    if not saved:
        print("⬜ 새로 저장한 것이 없다 — collected_at 을 찍지 않는다 (원장의 날짜는 그대로)")
        return False
    mark_collected(source_id)
    print("collected_at 을 원장에 기록하고 data_sources.yaml 을 재생성했다.")
    return True


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

    # 🔄 2026-09-21 (전수 재검토) — ⛔ `\s*\S+` 는 값이 **비었을 때 줄을 넘어** 다음 줄의 첫 낱말을 먹었다
    #    (`collected_at:\n  reviewed_by: kim` → `collected_at: 2026-09-21 kim` — `reviewed_by` 가 사라진다).
    #    지금 값이 전부 null·날짜라 안 터졌을 뿐이다. 한 줄 안에서만 바꾼다.
    new_block = re.sub(r"collected_at:[ \t]*[^\n]*", f"collected_at: {today}", block, count=1)
    LEDGER.write_text(text[:start] + new_block + text[end:], encoding="utf-8", newline="\n")

    # 🚨 원장을 고쳤으면 생성물도 다시 만들어야 게이트가 같은 것을 본다.
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/gen_registry.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
