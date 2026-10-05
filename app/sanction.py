"""위험도 하한 조회 — **제재표 행 → 하한 · 가능 상한** (🆕 2026-10-02 · W5 · D-305 · D-310 · D-09).

★ 왜 이 파일인가 — 하한 규칙은 원천 검사(`scripts/sanction_rule.py` · yaml 을 읽는다)와 판정 그래프(`app/graph.py` `assess_risk` ·
  DB 뷰 `v_risk_lookup` 을 읽는다)가 **같이** 쓴다. 한 곳에 두지 않으면 서명한 표와 판정이 조용히 갈린다 (D-99).
  ⛔ `app/` 은 `scripts/` 를 import 하지 않는다 — 그래서 규칙이 이쪽에 있고 `scripts/sanction_rule.py` 가 이 파일을 들여 쓴다.

행의 모양(`Row`) — yaml 행과 DB 행이 **같은 열쇠**로 온다:
    id · law_id(처분 원천 법) · type(유형) · kind(처분 종류) · annex1(별표1 목 목록 · 없으면 None) · cover(전부/일부) · quote(원문 인용) · fact
🚨 위험도는 처분 **종류**로만 정한다 — `KIND_RISK` 한 곳 (D-227). 행에 위험도를 따로 적지 않는다.
🚨 서명 여부는 여기서 보지 않는다 — 부르는 쪽이 본다(yaml 은 `signature()` · DB 는 뷰가 서명된 행만 보인다 · D-309 · 0013).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.contracts import Risk, Violation
from collect import statute

Row = Mapping[str, Any]

#: 처분 종류 → 위험도 (D-227 「종류로 가른다」 · 출처 `[문헌]` 각 법의 처분 사다리 — 초안 09-16 §1 · 09-12 §3-2).
#: 🚨 정지에 **갈음하는 과징금**도 R2 다(식품 제19조 · 화장품 제28조) — 금액은 쓰지 않는다(D-182).
KIND_RISK: dict[str, Risk] = {
    "시정명령": Risk.R1,
    "시정조치": Risk.R1,  # 표시광고법 제7조 — 정지 · 취소 사다리가 없다
    "영업정지": Risk.R2,
    "품목제조정지": Risk.R2,
    "품목류제조정지": Risk.R2,
    "광고업무정지": Risk.R2,
    "판매업무정지": Risk.R2,
    "영업허가등록취소": Risk.R3,
    "영업소폐쇄": Risk.R3,
}

#: 🆕 2026-10-01 (D-310) — **목 단위 하한**을 쓰는 축 · 유형. 식품 별표7 은 법 제8조① 4~7호를 [별표 1] 목마다 다르게 처분하고
#:    나머지는 「그 밖에 → 시정명령」이다. 그래서 그 유형은 근거 인용의 목(`annex1`)이 맞는 행만 쓰고, 없으면 R1 이다(D-308 ⑥).
#:    ⛔ 유형 max 로 접으면 보통의 과장 문구에 「영업정지 수준」이 붙는다 — 근거 없는 등급이다(D-305 · D-130).
MOK_AXIS = "013475"
MOK_TYPES = frozenset(
    {
        Violation.거짓_과장,
        Violation.소비자_기만,
        Violation.후기_체험기_기만,
        Violation.비방광고,
        Violation.부당_비교광고,
    }
)
#: 목을 못 맞힐 때의 하한 — 별표7 블록 1 거) · 블록 3 카) · 블록 4 2)다) 「그 밖에 … 부당한 표시ㆍ광고 → 시정명령」 `[문헌]`
OTHERWISE = Risk.R1
ANNEX1 = re.compile(r"^[4-7]\.[가-하]$")
#: 🆕 2026-10-01 (D-310 개정 2 · (다)) 별표7 행이 별표1 목을 덮는 정도 — 전부면 목이 맞을 때 하한 · 일부면 가능 상한만.
#:    ⛔ 기본값을 두지 않는다 — 목 칸이 있는 행은 둘 중 하나를 적어야 한다(lint · 없음이 「전부」로 읽히면 하한이 과대된다 · D-220)
COVER = ("전부", "일부")
#: 목 칸이 빈 행(`annex1: []`)의 근거 — 별표1 목이 아니라 고시로 닿는다(유형 오인 · 혼동). 상한 근거 줄에 쓴다
NO_MOK_BASIS = "고시 69549 제2조 3.너"
#: 식품표시광고법(법률) ID — 근거 인용의 법. 처분 원천(시행규칙 013475)과 다른 ID 다
FOOD_ACT = "013094"

#: 위험도 이름 — 화면 근거 줄에 쓴다 (`app.contracts.Risk` docstring · D-280)
RISK_NAME = {Risk.R1: "시정명령", Risk.R2: "업무정지", Risk.R3: "영업 상실"}

#: 🆕 2026-10-02 (W5) **법 축 → 처분 원천 법 ID** — 판정 그래프의 법별 노드(`app/graph.py` `LAW_OF_NODE` 의 값)가 이 표로 제재표를 찾는다.
#:    식품 · 화장품은 처분 기준이 **시행규칙 별표**에 있고(013475 별표7 · 008741 별표7) 표시광고법은 **법 제7조**(002011)다 —
#:    출처 `[문헌]` `scripts/sanction_review.yaml` `sources` 의 `law_id`. 🔴 게이트 `test_법_축마다_처분_원천이_있다` 가 그 파일과 댄다 (D-99).
SANCTION_LAW: dict[str, str] = {
    "식품표시광고법": "013475",
    "화장품법": "008741",
    "표시광고법": "002011",
}


@dataclasses.dataclass(frozen=True)
class Floor:
    """하한 조회 결과 — 🔄 2026-10-01 (D-310 개정 (다)) 하한 + **가능 상한**.

    `floor` 는 「확실한 최소」 · `ceiling` 은 「목에 따라 그럴 수 있는 최대」(하한보다 높을 때만) · `basis` 는 근거 행 id.
    🚨 상한은 표시 전용이다 — 래칫 · 통과에 쓰지 않는다(`RiskAssessment.ceiling`).
    """

    floor: Risk | None
    ceiling: Risk | None = None
    ceiling_note: str | None = None
    basis: tuple[str, ...] = ()


def annex1_code(cite: str) -> str | None:
    """근거 인용 → [별표 1] 목 코드(`4.마`). 식품표시광고법 4~7호의 목 인용만 · 그 밖에는 None."""
    try:
        law, _jo, _hang, ho, mok = statute.parse(cite)
    except ValueError:
        return None
    return f"{ho}.{mok}" if law == FOOD_ACT and 4 <= ho <= 7 and mok else None


def _top(rows: Iterable[Row]) -> Risk:
    order = list(Risk)
    return max((KIND_RISK[r["kind"]] for r in rows), key=order.index)


def mok_where(rows: Iterable[Row]) -> str:
    """상한 근거 줄의 「어디에 해당하면」 — 별표1 목 · 목 없는 행은 고시 근거."""
    rows = list(rows)
    codes = sorted({c for r in rows for c in r.get("annex1") or []})
    if any(not r.get("annex1") for r in rows):
        codes.append(NO_MOK_BASIS)
    return f"{' · '.join(codes)} 에 해당하면" if codes else "별표7 전용 목에 해당하면"


def floor_rows(rows: Iterable[Row], vtype: str, law_id: str, cites: Iterable[str]) -> Floor:
    """(행들 · 유형 · 처분 원천 법 · 근거 인용) → 하한 · 가능 상한. 맞는 행이 없으면 `Floor(None)`.

    식품 4~7호(D-310) — 근거 인용의 목이
      · `cover: 전부` 행에 맞으면 그 행의 처분이 **하한**
      · `cover: 일부` 행에만 맞으면 하한 **그 밖에 R1** · 그 행의 처분은 **가능 상한**(근거 줄에 그 행의 원문) — D-310 개정 2 (다)
      · 아무 행에도 안 맞거나 목이 없으면 하한 그 밖에 R1 · 그 유형 행 중 가장 무거운 처분이 가능 상한
    ⛔ 상한을 하한으로 올리지 않는다 — 하한은 확실한 최소다(D-310 개정 (다)).
    🚨 행이 없는 (유형 · 법)은 **하한을 모른다**(`None`)이다 — R0 이 아니다. 없음을 낮음으로 세지 않는다 (D-72 · D-220).
    """
    mine = [r for r in rows if r["type"] == vtype and r["law_id"] == law_id]
    if law_id == MOK_AXIS and Violation(vtype) in MOK_TYPES:
        codes = {c for c in map(annex1_code, cites) if c}
        hit = [r for r in mine if codes & set(r.get("annex1") or [])]
        full = [r for r in hit if r.get("cover") == "전부"]
        part = [r for r in hit if r.get("cover") == "일부"]
        floor = _top(full) if full else OTHERWISE
        basis = tuple(sorted(r["id"] for r in full)) if full else ("그 밖에(별표7)",)
        if part:
            top = _top(part)
            if top.level <= floor.level:
                return Floor(floor, basis=basis)
            # 업종 블록마다 같은 행위의 행이 있다 — (목 · 사실 칸)마다 첫 행의 원문 하나만 보인다
            first: dict[tuple[tuple[str, ...], Any], str] = {}
            for r in part:
                if KIND_RISK[r["kind"]] is top:
                    first.setdefault((tuple(r["annex1"]), r.get("fact")), r["quote"])
            quotes = " · ".join(f"「{q}」" for q in first.values())
            hit_codes = " · ".join(sorted(codes & {c for r in part for c in r["annex1"]}))
            return Floor(
                floor,
                ceiling=top,
                ceiling_note=f"목에 따라 {top.value}({RISK_NAME[top]})까지 — 별표1 {hit_codes} 중 {quotes} 이면 별표7 전용 처분",
                basis=basis,
            )
        if full:
            return Floor(floor, basis=basis)
        if not mine:
            return Floor(OTHERWISE, basis=basis)
        top = _top(mine)
        if top.level <= OTHERWISE.level:
            return Floor(OTHERWISE, basis=basis)
        where = mok_where([r for r in mine if KIND_RISK[r["kind"]] is top])
        return Floor(
            OTHERWISE,
            ceiling=top,
            ceiling_note=f"목에 따라 {top.value}({RISK_NAME[top]})까지 — 별표1 {where} 별표7 전용 처분",
            basis=basis,
        )
    if not mine:
        return Floor(None)
    # 🔴 근거 행 id 는 **정렬해서** 낸다 — 원천(파일 순서)과 DB 뷰(열쇠 순서)가 같은 값을 내야 한다 (D-99)
    return Floor(_top(mine), basis=tuple(sorted(r["id"] for r in mine)))
