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
from collections.abc import Iterable

from collect.law_map import LAW_OF_ID, STATUTE_ID, law_of_basis

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


#: 🆕 2026-10-08 — 근거 조문 칸(`EvidenceArticle` 의 article · item) 꼴. `article_item` 이 만들고 `from_article_item` 이 되읽는다.
_ART = re.compile(r"^제(\d+)조$")
_ITEM = re.compile(r"^제(\d+)항제(\d+)호(?:([가-힣])목)?$")


def article_item(c: str) -> tuple[str, str, str]:
    """인용 → 근거 조문 칸 `(법 ID, 「제N조」, 「제N항제N호[X목]」)` — 판정 그래프가 사전 근거를 계약에 옮길 때 쓴다.

    🆕 2026-10-08 — `app/graph.py` `_basis_article` 이 따로 조립하던 꼴을 여기로 옮겼다. 되읽는 쪽(`from_article_item`)과
       한 곳에 두어야 꼴이 갈리지 않는다 (D-99) — 갈렸을 때 평가 도구가 목 붙은 근거를 조용히 버렸다(`scripts/eval_graph.py` `_ho`).
    """
    law, jo, hang, ho, mok = parse(c)
    return law, f"제{jo}조", f"제{hang}항제{ho}호" + (f"{mok}목" if mok else "")


def from_article_item(law_id: str, article: str, item: str) -> str | None:
    """`article_item` 의 역 — 그 꼴이 아니면 **None** (D-220 · 지어내지 않는다).

    ⛔ 검색 근거(`article`=「제8조제1항제4호」 · `item`=「4.」 · 별표 「[별표 1]제5호다목」)는 이 꼴이 아니다 — None.
       검색이 찾은 조문은 판정의 근거 문맥이지 위반 인용이 아니다. 별표 → 조문 호 대응(D-281)도 여기서 하지 않는다 ⬜.
    """
    a, i = _ART.match(article or ""), _ITEM.match(item or "")
    if not law_id or a is None or i is None:
        return None
    return cite(law_id, int(a[1]), int(i[1]), int(i[2]), i[3])


def law_of(c: str) -> str | None:
    """인용 → **법 축**(`collect/law_map.LAWS`). 꼴이 틀리거나 모르는 법 ID 면 **None** — 기본 법으로 떨어지지 않는다 (D-220).

    🆕 2026-09-28 (W4) — 판정 그래프의 법별 노드가 사전 적중의 근거를 제 법 것만 고를 때 쓴다.
    ⛔ 종전에는 `tests/test_law_map.py` 안의 지역 함수로만 있었다 — 그래프가 따로 적으면 두 번째 사본이다 (D-99).
    """
    try:
        return LAW_OF_ID.get(parse(c)[0])
    except ValueError:
        return None


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


# ── 참조 조항표 (🆕 2026-10-12 · D-327) ──────────────────────────────────────────
#: 유형 후보 옆에 「이 유형을 정한 조항」으로 보여 줄 좌표 — **(유형 · 법 축) → 금지 조항과 세부 기준**.
#:    ★ 방향이 `_HO` · `_MOK`(조문 → 유형 · D-282)와 **반대**다. 그 표에서 뽑을 수 있는 줄은 뽑고(`references`), 여기에는
#:      그 표에 없는 대응만 적는다 — 두 표가 따로 놀지 않게 (D-99).
#:    🚨 **보여 주는 값이다 — 라벨 · 채점 · 판정을 바꾸지 않는다.** 화장품법 제13조제1항제4호는 여전히 유형을 주지 않는다
#:       (`type_of` 는 None · 그 행은 「유형 없는 위반」으로 채점에서 빠진다 · D-321).
#:    좌표 꼴은 `법ID:` + 검색 좌표(`app/retrieve.py` `citation()` 이 내는 글자)다 — 청크를 그 좌표로 찾는다.
#: 세부 기준이 든 하위 규범 — 🚨 법 ID 는 `collect/law_map.LAW_OF_ID` 에 있는 값이다(아래에서 대조한다)
FOOD_ANNEX = "013453:[별표 1]"  # 식품표시광고법 시행령 [별표 1] 부당한 표시 또는 광고의 내용 — 호 번호가 법 제8조제1항과 대응한다(D-281)
FAIR_DECREE = "005361:제3조"  # 표시광고법 시행령 제3조 — 제n항이 법 제3조제1항제n호를 푼다
COSM_ANNEX = (
    "008741:[별표 5]제2호"  # 화장품법 시행규칙 [별표 5] 제2호 — 화장품 표시 · 광고 시 준수사항
)

#: 화장품법의 대응 — **[문헌] 조문 원문 대조 + 판정(D-327 · 2026-10-12)**. `_HO` 에 없는 줄이다.
#:    제13조제1항제4호(「그 밖에 사실과 다르게 …」)는 호만으로 유형을 못 가르지만, 거짓 · 과장과 기만 후보에 **보여 줄** 조항이다.
#:    [별표 5] 제2호 — 가 의약품 오인 / 나 기능성화장품 오인 / 바 비교 · 「최고」 / 사 사실과 다름 · 속임 / 아 확인되지 않은 효능 / 카 비방
_COSM_REF: dict[str, tuple[str, ...]] = {
    "거짓_과장": (f"{COSM[0]}:제13조제1항제4호", f"{COSM_ANNEX}사목", f"{COSM_ANNEX}아목"),
    "소비자_기만": (f"{COSM[0]}:제13조제1항제4호", f"{COSM_ANNEX}사목"),
    "부당_비교광고": (f"{COSM_ANNEX}바목",),
    "비방광고": (f"{COSM_ANNEX}카목",),
    "의약품_오인": (f"{COSM_ANNEX}가목",),
    "기능성화장품_오인": (f"{COSM_ANNEX}나목",),
}


def _detail(law_id: str, ho: int, mok: str | None = None) -> str | None:
    """법률의 호 → 그 호를 푼 세부 기준 좌표. 화장품법은 `_COSM_REF` 가 맡는다 — 여기서는 None."""
    if law_id == FOOD[0]:
        return f"{FOOD_ANNEX}제{ho}호" + (f"{mok}목" if mok else "")
    if law_id == FAIR[0]:
        return f"{FAIR_DECREE}제{ho}항"
    return None


def reference_of_cite(c: str) -> tuple[str, ...]:
    """위반 인용 하나 → 보여 줄 좌표(금지 조항 · 세부 기준). 꼴이 틀리면 `ValueError`(`parse`) — 지어내지 않는다.

    옮긴 후보([별표 1] 4.나 · `app/premise.UNRECOGNIZED_FUNCTION_CITE`)처럼 **인용이 이미 정해진** 후보가 쓴다.
    """
    law_id, jo, hang, ho, mok = parse(c)
    out = [f"{law_id}:제{jo}조제{hang}항제{ho}호"]
    if (d := _detail(law_id, ho, mok)) is not None:
        out.append(d)
    return tuple(out)


def references(violation: str, law: str) -> tuple[str, ...]:
    """(유형 · 법 축) → 보여 줄 좌표들 — 금지 조항 먼저, 세부 기준 뒤. 🔴 그 법에 그 유형의 조항이 없으면 **빈 튜플**이다.

    ⛔ 빈칸을 다른 법의 조항으로 메우지 않는다 — 없음이 「다른 조항」으로 보이지 않게 (D-220).
    """
    out: list[str] = []
    for (law_id, jo, hang, ho), t in _HO.items():
        if t == violation and LAW_OF_ID.get(law_id) == law:
            out += reference_of_cite(cite(law_id, jo, hang, ho))
    for (law_id, jo, hang, ho, mok), t in _MOK.items():
        if t == violation and LAW_OF_ID.get(law_id) == law:
            out += reference_of_cite(cite(law_id, jo, hang, ho, mok))
    if law == LAW_OF_ID[COSM[0]]:
        out += _COSM_REF.get(violation, ())
    return tuple(dict.fromkeys(out))


# 🔴 표가 어긋나면 import 에서 멈춘다 (D-220) — 모르는 법 ID 의 좌표는 청크를 못 찾고 조용히 좌표만 나간다
for _c in (FOOD_ANNEX, FAIR_DECREE, COSM_ANNEX, *(c for v in _COSM_REF.values() for c in v)):
    if _c.split(":", 1)[0] not in LAW_OF_ID:
        raise RuntimeError(
            f"🔴 참조 조항표의 법 ID 를 모른다 — {_c!r} (`collect/law_map.LAW_OF_ID`)"
        )
if {LAW_OF_ID[c.split(":", 1)[0]] for v in _COSM_REF.values() for c in v} != {LAW_OF_ID[COSM[0]]}:
    raise RuntimeError("🔴 `_COSM_REF` 에 화장품법이 아닌 좌표가 있다 (D-327)")


def table() -> list[tuple[str, str]]:
    """(인용, 파생 유형) 전부 — DB `violation_article` 적재와 게이트가 읽는다."""
    got = [(cite(*k), v) for k, v in _HO.items()]
    got += [(cite(k[0], k[1], k[2], k[3], k[4]), v) for k, v in _MOK.items()]
    return sorted(got)


# ── 참고 조문으로 싣는 법령 조문 (🆕 2026-10-12 · D-329) ──────────────────────────────────────────
#: 판정 화면의 참고 조문(검색 근거 · `basis=False`)으로 실어도 되는 **법령 본문의 조**. 표에 없는 조는 싣지 않는다 (D-220).
#: 🚨 `[판정]` D-329 — 고르는 기준(조문 내용으로 판단):
#:    a 광고 내용의 금지 · 기준   b 실증   c 광고 전후의 의무(사전 심의 · 광고에 넣을 사항 · 대상별 자료)
#:    d 주장의 범주를 정하는 정의(기능성화장품 · 건강기능식품 등)
#:    ⛔ 빼는 것 — 매체 · 용어의 일반 정의(표시광고법 제2조 · 시행령 제2조 「광고의 방법」) · 조직 · 절차 · 제재 · 행정
#: 🔴 **제목을 같이 적는다** — 실행할 때 DB 의 조 제목과 다르면 그 조를 싣지 않는다(`app/graph.py` `body_scope`).
#:    개정으로 조 번호가 밀려 다른 조문을 가리키는 것을 막는다.
#: ★ 고르는 절차(D-329) — ① 후보: 광고 조항(금지 · 실증 · 광고 기준 · 심의 · 정의)과 그 조항을 위임받은 하위법령 조문
#:    (본문의 「법 제N조」) ② 위 기준으로 고른다 ③ 줄마다 기준과 제목을 남긴다. 뺀 후보와 사유는 D-329 초안의 「뺀 조문」이다.
#: ⛔ 판정 · 사전 인용 근거 · D-327 참조 조항은 이 표를 읽지 않는다 — 참고 조문의 범위만 정한다.
REFERENCE_ARTICLES: tuple[tuple[str, str, str, str], ...] = (
    ("002011", "제3조", "부당한 표시ㆍ광고 행위의 금지", "a"),
    ("002011", "제4조", "중요정보의 고시 및 통합공고", "a"),
    ("002011", "제5조", "표시ㆍ광고 내용의 실증 등", "b"),
    ("005361", "제3조", "부당한 표시ㆍ광고의 내용", "a"),
    ("005361", "제4조", "실증방법 등", "b"),
    ("005361", "제5조", "실증자료", "b"),
    ("005361", "제6조", "실증자료의 공개", "b"),
    ("013094", "제2조", "정의", "d"),
    ("013094", "제7조", "광고의 기준", "c"),
    ("013094", "제8조", "부당한 표시 또는 광고행위의 금지", "a"),
    ("013094", "제8조의2", "마약류 표시ㆍ광고 영업자 등에 대한 권고", "a"),
    ("013094", "제9조", "표시 또는 광고 내용의 실증", "b"),
    ("013094", "제10조", "표시 또는 광고의 자율심의", "c"),
    ("013453", "제2조", "부당한 표시 또는 광고행위의 금지 대상", "a"),
    ("013453", "제3조", "부당한 표시 또는 광고의 내용", "a"),
    ("013475", "제8조", "광고의 기준", "c"),
    ("013475", "제8조의2", "식품등이 아닌 물품의 범위", "a"),
    ("013475", "제8조의3", "마약류 등 표시ㆍ광고의 범위", "a"),
    ("013475", "제9조", "실증방법 등", "b"),
    ("013475", "제10조", "표시 또는 광고 심의 대상 식품등", "c"),
    ("002015", "제2조", "정의", "d"),
    ("002015", "제4조의2", "영유아 또는 어린이 사용 화장품의 관리", "c"),
    ("002015", "제13조", "부당한 표시ㆍ광고 행위 등의 금지", "a"),
    ("002015", "제14조", "표시ㆍ광고 내용의 실증 등", "b"),
    ("008741", "제2조", "기능성화장품의 범위", "d"),
    ("008741", "제10조의2", "영유아 또는 어린이 사용 화장품의 표시ㆍ광고", "c"),
    ("008741", "제22조", "표시ㆍ광고의 범위 등", "a"),
    ("008741", "제23조", "표시ㆍ광고 실증의 대상 등", "b"),
)
#: 고시 안의 상투 조문 — 고시 이름에 「광고」가 있어도 싣지 않는다(D-329 안건 2). 법령 본문은 표가 이미 이 조들을 뺀다.
BOILERPLATE_TITLES: frozenset[str] = frozenset(
    {"목적", "규제의 재검토", "재검토 기한", "재검토기한"}
)


#: 🆕 2026-10-19 (D-348 「검색 · 리랭커의 자리」 (나) · ⬜ **표 내용 판정 대기 — 초안**) **(유형 · 법 축) → 참고 조문을 고를 규범 문서**.
#:    판정 뒤에 문장의 유형(확정 · 인코더 근거 · 후보)이 정해지면 그 유형 · 법의 문서 안에서만 참고 조문을 고른다(`app/graph.py` `references`).
#:    ★ 판정 · 근거 조문(호) · 라벨 · 채점은 이 표를 읽지 않는다 — 화면 「근거 보기」의 참고 조문 자리만 바뀐다(D-327 과 같은 선).
#:    문서는 법 ID(`collect/law_map.LAW_OF_ID`)다 — 법률 · 시행령 · 시행규칙과 그 법 축의 고시 · 지침. 묶음은 **고시 · 지침의 제목**으로 골랐다 `[설계]`.
#:    🔴 표에 없는 (유형 · 법)은 참고 조문을 싣지 않는다(D-220) · 법 축이 다른 문서는 넣지 않는다(게이트가 `LAW_OF_ID` 와 대조).
_FTC_BASE = (
    "002011",
    "005361",
    "34717",
)  # 표시광고법 · 시행령 · 부당한 표시·광고행위의 유형 및 기준 지정고시
_FOOD_BASE = (
    "013094",
    "013453",
    "013475",
    "69549",
)  # 식품표시광고법 · 시행령([별표 1]) · 시행규칙 · 부당한 표시·광고 내용 기준
_COS_BASE = ("002015", "005668", "008741")  # 화장품법 · 시행령 · 시행규칙([별표 5])
REFERENCE_DOCS: dict[tuple[str, str], tuple[str, ...]] = {
    # 표시광고법 축 — 20246 실증 운영고시 · 35034 수상·인증 · 35037 환경 · 2052445 인터넷 · 38124 기만 · 20207 비교 · 35032 추천·보증
    ("거짓_과장", "표시광고법"): (*_FTC_BASE, "20246", "35034", "35037", "2052445"),
    ("소비자_기만", "표시광고법"): (*_FTC_BASE, "38124", "2052445", "35037"),
    ("부당_비교광고", "표시광고법"): (*_FTC_BASE, "20207", "20246"),
    ("비방광고", "표시광고법"): (*_FTC_BASE, "20207"),
    ("후기_체험기_기만", "표시광고법"): (*_FTC_BASE, "35032", "38124", "2052445"),
    # 식품표시광고법 축 — 36814 식품등의 표시기준(무첨가 등) · 75449 기능성 표시 식품등(기능성 표시 규정)
    ("거짓_과장", "식품표시광고법"): (*_FOOD_BASE, "36814"),
    ("소비자_기만", "식품표시광고법"): (*_FOOD_BASE, "36814"),
    ("건강기능식품_오인", "식품표시광고법"): (*_FOOD_BASE, "75449"),
    ("질병_예방치료_표방", "식품표시광고법"): _FOOD_BASE,
    ("의약품_오인", "식품표시광고법"): _FOOD_BASE,
    ("부당_비교광고", "식품표시광고법"): _FOOD_BASE,
    ("비방광고", "식품표시광고법"): _FOOD_BASE,
    ("후기_체험기_기만", "식품표시광고법"): _FOOD_BASE,
    # 화장품법 축 — 41277 표시·광고 실증 규정 · 36122 기능성화장품 심사 규정 · 37098 안전기준(사용 제한 원료)
    ("거짓_과장", "화장품법"): (*_COS_BASE, "41277"),
    ("소비자_기만", "화장품법"): (*_COS_BASE, "41277"),
    ("부당_비교광고", "화장품법"): (*_COS_BASE, "41277"),
    ("비방광고", "화장품법"): _COS_BASE,
    ("의약품_오인", "화장품법"): (*_COS_BASE, "37098"),
    ("질병_예방치료_표방", "화장품법"): _COS_BASE,
    ("기능성화장품_오인", "화장품법"): (*_COS_BASE, "36122"),
    ("후기_체험기_기만", "화장품법"): (*_COS_BASE, "41277"),
}


def reference_docs(violations: Iterable[str], law: str) -> frozenset[str]:
    """유형들 · 법 축 → 참고 조문을 고를 문서(법 ID)의 합. 표에 없으면 빈 집합 — 싣지 않는다 (D-220)."""
    return frozenset(d for v in violations for d in REFERENCE_DOCS.get((v, law), ()))


# 🔴 표가 어긋나면 import 에서 멈춘다 (D-220)
_ARTICLE_KEY = re.compile(r"^제\d+조(?:의\d+)?$")
for _lid, _art, _title, _crit in REFERENCE_ARTICLES:
    if _lid not in LAW_OF_ID or not _ARTICLE_KEY.match(_art) or _crit not in "abcd" or not _title:
        raise RuntimeError(
            f"🔴 참고 조문 표의 줄이 어긋났다 — {(_lid, _art, _title, _crit)!r} (D-329)"
        )
if len({(r[0], r[1]) for r in REFERENCE_ARTICLES}) != len(REFERENCE_ARTICLES):
    raise RuntimeError("🔴 참고 조문 표에 같은 조가 두 번 있다 (D-329)")
