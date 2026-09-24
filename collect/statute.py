"""collect/statute.py — **조문 인용이 라벨의 정본이다. 유형은 인용에서 계산한다** (D-237 집행 · 🆕 2026-09-24 D-282).

★ 라벨의 정본은 **(법 ID, 조, 항, 호[, 목])** 이다. `app.contracts.Violation` 의 이름(거짓_과장 · 비방광고 …)은
   **이 표로 계산하는 파생값**이고, 화면 배지·법을 가로지르는 집계에만 쓴다 (D-282 ①).
   판정·위험도·D-40 의 셈은 인용(호)으로 한다 — 식품표시광고법은 1~3호와 4~10호의 형량이 다르다
   (법 제26조 · 제27조 · 제20조 · D-227).

🔴 **호 → 유형 대응은 여기 한 곳이다** (D-99). 종전에는 네 벌이 따로 있었고 5호·8호 처리가 서로 달랐다 —
   `mfds_casebook.HO_TYPES` · `interp_scan.HO_TYPE` · `guide_label.TYPE_OF` · `casebook2021_sheet.TYPE`.
   남은 사본(앵커 경로 · 시트 도구)은 이 표를 가리키는 주석을 달고, 게이트 `tests/test_statute.py` 가 대조한다.

🚨 **같은 이름이 법마다 범위가 다르다** — 공통 유형은 **여러 조문이 모이는 분류**이지 조문의 동의어가 아니다.
   · 비방 — 식품 제6호(시행령 [별표 1] 6호)는 「비교로 우월하게 인식」까지 넣는다 · 표시광고법 제3조①4호는 「객관적 근거 없음」이 요건
   · 체험기 — 명시 금지는 식품 [별표 1] 5호 **다목**뿐이다
   그래서 판정·위험도를 이 파생값으로 계산하지 않는다.

🔴 **모르는 조문은 None** — 기본 유형으로 떨어지지 않는다 (D-220 · fail-closed).
   · 식품 제8조①8~10호(사행·음란 · 상호 오인 · 미심의)는 `Violation` 에 자리가 없다 → None
   · 화장품법 제13조①4호(「그 밖에 사실과 다르게…」)는 거짓·과장과 기만을 한 호에 담아 **호만으로는 못 가른다** → None
     (시행규칙 [별표 5] 제2호의 목으로 가를 수 있으나 그 대응은 아직 없다 ⬜)

인용 문자열 꼴 — `법ID:제N조제N항제N호` · 목이 있으면 `|다목` 을 붙인다.
    013094:제8조제1항제4호            식품표시광고법 §8①4
    013094:제8조제1항제5호|다목         식품표시광고법 §8①5 · 시행령 [별표 1] 5호 다목(체험기)
    002011:제3조제1항제3호            표시광고법 §3①3
검색 탐침의 정답 꼴(`013453:[별표 1]제5호다목` · D-281)과는 **다른 층**이다 — 그쪽은 청크 좌표, 이쪽은 위반 근거.
"""

from __future__ import annotations

import re

from collect.law_map import STATUTE_ID, law_of_basis

#: 위반 근거가 되는 법률 조항 — (법률 ID, 조, 항). 🚨 이 셋 밖의 조문은 유형을 주지 않는다.
FOOD = (STATUTE_ID["식품표시광고법"], 8, 1)  # 식품 등의 표시·광고에 관한 법률 제8조 제1항
FAIR = (STATUTE_ID["표시광고법"], 3, 1)  # 표시·광고의 공정화에 관한 법률 제3조 제1항
COSM = (STATUTE_ID["화장품법"], 13, 1)  # 화장품법 제13조 제1항

#: (법률 ID, 조, 항, 호) → 파생 유형. **조문 본문으로 대조했다** [문헌] (코퍼스 `law_article.jsonl` · 2026-09-24).
#: 🚨 식품 6호가 **비방**, 7호가 **부당 비교**다 — 사람 라벨 시트 번호(6 부당비교 · 7 비방)와 반대였다(폐기 · D-283).
_HO: dict[tuple[str, int, int, int], str] = {
    # 식품표시광고법 §8① — 1 질병 예방·치료 / 2 의약품 인식 / 3 건강기능식품 인식 / 4 거짓·과장 / 5 기만 / 6 비방 / 7 부당 비교
    (*FOOD, 1): "질병_예방치료_표방",
    (*FOOD, 2): "의약품_오인",
    (*FOOD, 3): "건강기능식품_오인",
    (*FOOD, 4): "거짓_과장",
    (*FOOD, 5): "소비자_기만",
    (*FOOD, 6): "비방광고",
    (*FOOD, 7): "부당_비교광고",
    # 표시광고법 §3① — 1 거짓·과장 / 2 기만적 / 3 부당하게 비교 / 4 비방적
    (*FAIR, 1): "거짓_과장",
    (*FAIR, 2): "소비자_기만",
    (*FAIR, 3): "부당_비교광고",
    (*FAIR, 4): "비방광고",
    # 화장품법 §13① — 1 의약품 오인 / 2 기능성화장품 오인 · 3 삭제<2025.1.31> · 4 는 호만으로 못 가른다(None)
    (*COSM, 1): "의약품_오인",
    (*COSM, 2): "기능성화장품_오인",
}

#: 목이 호보다 좁은 유형을 주는 자리. 🔄 D-255 ① 개정 (D-282) — `후기_체험기_기만` 은 **형식 라벨이 아니라
#: 식품 [별표 1] 5호 다목의 파생 유형**이다(「각종 감사장 또는 체험기 등을 이용하거나 …」).
_MOK: dict[tuple[str, int, int, int, str], str] = {
    (*FOOD, 5, "다"): "후기_체험기_기만",
}

_CITE = re.compile(r"^(\d+):제(\d+)조제(\d+)항제(\d+)호(?:\|([가-힣])목)?$")


def cite(law_id: str, jo: int, hang: int, ho: int, mok: str | None = None) -> str:
    """인용 문자열을 만든다. 🚨 여기서만 만든다 — 꼴이 두 벌이면 대조가 조용히 갈린다 (D-99)."""
    s = f"{law_id}:제{int(jo)}조제{int(hang)}항제{int(ho)}호"
    return f"{s}|{mok}목" if mok else s


def parse(c: str) -> tuple[str, int, int, int, str | None]:
    """인용 문자열 → (법 ID, 조, 항, 호, 목). 🔴 꼴이 틀리면 **멈춘다** — 조용히 버리지 않는다."""
    m = _CITE.match(c)
    if not m:
        raise ValueError(f"인용 꼴이 아니다: {c!r} — `법ID:제N조제N항제N호[|가목]`")
    return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)


def ho_key(c: str) -> str:
    """목을 뗀 **호 단위** 인용 — D-40 셈의 단위다 (D-282)."""
    law, jo, hang, ho, _ = parse(c)
    return cite(law, jo, hang, ho)


def type_of(c: str) -> str | None:
    """인용 → 파생 유형. 모르면 **None** (D-220)."""
    law, jo, hang, ho, mok = parse(c)
    if mok and (law, jo, hang, ho, mok) in _MOK:
        return _MOK[(law, jo, hang, ho, mok)]
    return _HO.get((law, jo, hang, ho))


def types_of(cites: list[str]) -> list[str]:
    """인용 목록 → 파생 유형 목록(정렬 · 중복 없음). 🚨 None 은 **빼고** 따로 센다(`untyped`)."""
    return sorted({t for c in cites if (t := type_of(c))})


def untyped(cites: list[str]) -> list[str]:
    """유형이 없는 인용 — 식품 8~10호 · 화장품 13①4 등. 🚨 버리지 않고 **보이게** 한다."""
    return [c for c in cites if type_of(c) is None]


#: 근거 문자열(한국어) — 「식품표시광고법 제8조제1항제4호」 · 「표시광고법 제3조제1항제3호」.
_KO = re.compile(r"제\s*(\d+)\s*조\s*제\s*(\d+)\s*항\s*제\s*(\d+)\s*호")
#: 목 — 「… 제5호(시행령 [별표 1] 제5호다목)」. 🚨 **같은 호의 목일 때만** 받는다.
_KO_MOK = re.compile(r"\[별표\s*1\]\s*제?\s*(\d+)\s*호\s*([가-힣])\s*목")


def from_korean(basis: str) -> str:
    """「식품표시광고법 제8조제1항제5호(시행령 [별표 1] 제5호다목)」 → `013094:제8조제1항제5호|다목`.

    🔴 법·조문을 못 읽으면 **멈춘다** · 목이 다른 호의 목이면 멈춘다 — 조용히 떼지 않는다 (D-220).
    ★ 법은 `collect.law_map.law_of_basis` 로 정한다 — 법 이름을 두 곳에서 읽지 않는다 (D-99).
    """
    law = law_of_basis(basis)
    m = _KO.search(basis)
    if not law or not m:
        raise ValueError(f"근거 문자열을 인용으로 못 읽는다: {basis!r}")
    ho = int(m.group(3))
    mm = _KO_MOK.search(basis)
    if mm and int(mm.group(1)) != ho:
        raise ValueError(f"목이 다른 호의 것이다: {basis!r}")
    return cite(STATUTE_ID[law], int(m.group(1)), int(m.group(2)), ho, mm.group(2) if mm else None)


def food(ho: int, mok: str | None = None) -> str:
    """식품표시광고법 §8① 호 인용 — 사례집·해설서처럼 법이 정해진 원천이 쓴다."""
    return cite(*FOOD, ho, mok)


def fair(ho: int) -> str:
    """표시광고법 §3① 호 인용 — 공정위 의결서가 쓴다."""
    return cite(*FAIR, ho)


def table() -> list[tuple[str, str]]:
    """(인용, 파생 유형) 전부 — DB `violation_article` 적재와 게이트가 읽는다."""
    got = [(cite(*k), v) for k, v in _HO.items()]
    got += [(cite(k[0], k[1], k[2], k[3], k[4]), v) for k, v in _MOK.items()]
    return sorted(got)
