"""식약처 1차 법령해석 추출기(`preprocess/mfds_interp.py`) — 표시·광고 그물 · 품목 · 기준시점 (2026-10-03).

🚨 원문 XML 은 저장소에 없다(CI) — 실제 해석에서 본 **모양**을 가짜 필드로 옮겨 대조한다.
   실측(클론 B 원문 · 작업공간): 해석 5,129 → 조문 그물 427(식품 240 · 화장품 187).
🔄 2026-10-04 — 그물은 **읽어 가른 목록**(`preprocess/mfds_interp_scope.py`)이다. 조문 그물은 후보(`candidate`)로 남았다.
   실측: 목록 289(식품 157 · 화장품 132) · 판정 대기 14 · 읽은 해석 5,129(원장 10-03 ㉔ ~ ㉗).
"""

from __future__ import annotations

import hashlib

import pytest

from preprocess import mfds_interp as mi


def _f(n: int, **kw: str) -> dict[str, str]:
    base = {
        "법령해석일련번호": str(n),
        "안건명": "",
        "질의요지": "",
        "회답": "",
        "이유": "",
        "관련법령": "",
        "해석일자": "",
    }
    base.update(kw)
    return base


FIELDS = [
    # 화장품 — 관련법령 칸은 비었는데 답변이 조문과 지침을 든다
    _f(
        1,
        질의요지="화장품 광고 시 '독소배출'이나 '디톡싱'이라는 표현을 사용할 수 있나요?",
        회답="「화장품법」 제13조에서는 부당한 표시·광고를 금지하고 있습니다. 「화장품 표시·광고 관리 지침」 [별표 1]에서 "
        "'피부 독소를 제거(디톡스)'가 금지되어 있는바 적절하지 않습니다. 문의는 대한화장품협회(02-785-7985)로 하십시오.",
        해석일자="20241212",
    ),
    # 식품 — 제8조가 걸렸지만 제품명 표시 기준 질의다(그물은 판정이 아니다)
    _f(
        2,
        질의요지="제품명 일부로 '오곡'을 사용할 때 함량을 표시하나요?",
        회답="-------------------\n2025년 11월 현재 유효한 법규를 토대로 작성되었습니다.\n-------------------\n"
        "(예시) 흑마늘○○(흑마늘 ○○%) 로 표시합니다.",
        관련법령="식품 등의 표시ㆍ광고에 관한 법률  제8조(부당한 표시 또는 광고행위의 금지)",
        해석일자="20251130",
    ),
    # 옛 질의회신 — 해석일자가 없고 구법을 든다
    _f(
        3,
        질의요지="‘해독주스’ 광고 문구가 허위광고인가",
        회답="식품위생법 제13조제1항제3호 위반에 해당된다고 판단됨.",
    ),
    # 조항은 없고 질의에 「광고」가 있다 — 식품
    _f(
        4,
        질의요지='제품의 광고문구로 "저탄고지" 표시가 가능한가요?',
        회답="(답변 출처) 2023년 자주하는 질문집 : 가능합니다.",
        관련법령="식품 등의 표시ㆍ광고에 관한 법률  제4조",
        해석일자="20241210",
    ),
    # 범위 밖 — 의료기기 광고 · 절차 질의
    _f(
        5,
        질의요지="의료기기 광고 심의는 어디서 받나요?",
        회답="협회입니다.",
        관련법령="의료기기법 제24조",
    ),
    _f(
        6,
        질의요지="수입신고 절차가 궁금합니다",
        회답="신고합니다.",
        관련법령="수입식품안전관리 특별법 제20조",
    ),
    _f(7, 질의요지="의료기기 광고를 위해 자율심의를 받으려 합니다.", 회답="기구는 둘입니다."),
    # 같은 질의가 두 번 실렸다(2 와 같다 · 더 늦다)
    _f(
        8,
        질의요지="제품명 일부로 '오곡'을 사용할 때 함량을 표시하나요?",
        회답="같은 답입니다.",
        관련법령="식품 등의 표시ㆍ광고에 관한 법률  제8조(부당한 표시 또는 광고행위의 금지)",
        해석일자="20260417",
    ),
]


@pytest.mark.gate
def test_조문_그물은_표시광고_규범을_드는_해석과_광고를_물은_식품_화장품_해석이다() -> None:
    rows, stat = mi.parse(FIELDS, pick=mi.candidate)
    assert [r["id"] for r in rows] == ["1", "2", "3", "4", "8"] and stat["해석"] == 8
    by = {r["id"]: r for r in rows}
    # 글 전체에서 조문을 찾는다 — 관련법령 칸이 비어도
    assert by["1"]["조항"] == ["화장품법 제13조", "화장품 지침"] and by["1"]["품목"] == "화장품"
    assert by["2"]["조항"] == ["식품표시광고법 제8조"] and by["2"]["품목"] == "식품"
    assert by["4"]["조항"] == [] and by["4"]["광고질의"] and by["4"]["품목"] == "식품"
    # 🚨 그물은 판정이 아니다 — 표시 기준 질의도 든다. 「광고」를 물었는지만 기계가 싣는다
    assert by["2"]["광고질의"] is False and by["1"]["광고질의"] is True
    assert mi.verify(FIELDS, pick=mi.candidate) == []


@pytest.mark.gate
def test_기준시점_구법_출처_판정지위를_레코드마다_남긴다() -> None:
    rows, _ = mi.parse(FIELDS, pick=mi.candidate)
    by = {r["id"]: r for r in rows}
    assert by["1"]["기준시점"] == "2024-12" and by["1"]["해석일자"] == "2024-12-12"
    assert by["2"]["기준시점"] == "2025-11"  # 답변의 「2025년 11월 현재」가 해석일자보다 먼저다
    assert by["3"]["기준시점"] is None and by["3"]["해석일자"] is None
    # 식품위생법 제13조는 2019 년에 식품표시광고법으로 옮겨 갔다 — 조문 번호를 지금 번호로 읽지 않는다
    assert by["3"]["구법"] is True and by["1"]["구법"] is False
    assert by["4"]["답변_출처"] == "2023년 자주하는 질문집"
    assert all(r["판정지위"] == "질의회신" and r["원천"] == "mfds_cgm_expc" for r in rows)  # D-240
    assert "라벨" not in rows[0] and "유형" not in rows[0]


@pytest.mark.gate
def test_인용표현은_따옴표_안_문구이고_전화번호와_구분선은_지운다() -> None:
    rows, stat = mi.parse(FIELDS, pick=mi.candidate)
    by = {r["id"]: r for r in rows}
    assert by["1"]["인용표현"][:2] == ["독소배출", "디톡싱"]
    assert "화장품법" not in by["1"]["인용표현"]  # 낫표는 법령명이다
    assert "대한화장품협회([전화])" in by["1"]["답변"] and stat["전화"] == 1
    assert "---" not in by["2"]["답변"] and by["2"]["답변"].startswith("2025년 11월 현재")


@pytest.mark.gate
def test_같은_질의는_늦은_것을_남기고_앞의_것에_표시한다() -> None:
    rows, stat = mi.parse(FIELDS, pick=mi.candidate)
    by = {r["id"]: r for r in rows}
    assert by["2"]["같은_질의"] == "8" and by["8"]["같은_질의"] is None and stat["같은_질의"] == 1


@pytest.mark.gate
def test_받은_것과_어긋나면_검증이_실패한다() -> None:
    assert any("겹친다" in b for b in mi.verify([*FIELDS, FIELDS[0]], pick=mi.candidate))
    empty = [dict(FIELDS[0], 회답="")]
    # 답변이 비면 조문도 사라져 그물 밖으로 나가므로 관련법령으로 붙든다
    empty[0]["관련법령"] = "「화장품법」 제13조"
    assert any("답변이 빈" in b for b in mi.verify(empty, pick=mi.candidate))
    # 받은 양이 잰 판보다 적다 — 실제 원문에만 거는 대조다
    assert mi.check_received({"해석": 10}, 3)
    assert mi.check_received({"해석": mi.EXPECTED_TOTAL_MIN}, mi.EXPECTED_MIN) == []


@pytest.mark.gate
def test_사람_축은_좁게_걸려_제품명_예시가_깨지지_않는다() -> None:
    """정책(org · person)은 그대로다 — 이 원천은 `PERSON_STRICT` 라 직함 · 호칭 · 조사가 곁에 있을 때만 바뀐다."""
    from preprocess.mask import PERSON_STRICT, POLICY

    assert POLICY[mi.SOURCE_ID] == frozenset({"org", "person"}) and mi.SOURCE_ID in PERSON_STRICT
    rows, _ = mi.parse(FIELDS, pick=mi.candidate)
    out, changed, log = mi.masked(rows)
    by = {r["id"]: r for r in out}
    assert "흑마늘○○(흑마늘 ○○%)" in by["2"]["답변"] and not changed
    assert by["1"]["인용표현"][:2] == ["독소배출", "디톡싱"]
    assert mi.check_person(log) == []


@pytest.mark.gate
def test_사람_축_치환이_생기면_멈춘다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 이 원천은 치환 0 이 정상이다 — 한 건이라도 생기면 사람이 본다. 확인된 해석은 지나간다."""
    named = [
        *FIELDS,
        _f(9, 질의요지="대표 김○○ 씨가 광고해도 되나요?", 회답="담당자 박민수에게 문의하십시오."),
    ]
    rows, _ = mi.parse(named, pick=mi.candidate)
    out, _, log = mi.masked(rows)
    last = next(r for r in out if r["id"] == "9")
    assert last["질의"].startswith("대표 [대표] 씨") and "담당자 [대표]에게" in last["답변"]
    bad = mi.check_person(log)
    assert len(bad) == 2 and all("해석 9" in b for b in bad)
    assert "김" not in "".join(bad) and "박민수" not in "".join(bad)  # 멈춤 글에 이름을 싣지 않는다
    monkeypatch.setattr(mi, "PERSON_SEEN", frozenset({"9"}))
    assert mi.check_person(log) == []


@pytest.mark.gate
def test_그물은_읽어_가른_목록이고_갈린_해석은_밖이다() -> None:
    sc = mi.scope
    # 합성 글의 일련번호는 목록에 없다 — 조문을 들어도 그물 밖이다(조문 그물은 후보일 뿐이다)
    assert mi.parse(FIELDS)[0] == [] and mi.parse(FIELDS)[1]["조문_그물"] == 5  # noqa: PLR2004
    ad = next(iter(sc.AD))
    f = _f(
        int(ad),
        질의요지="제품명에 '무가당' 을 써도 되나요?",
        회답="「식품등의 표시기준」에 따라 가능합니다.",
    )
    rows, stat = mi.parse([*FIELDS, f])
    # 조문을 안 드는 해석도 목록에 있으면 든다 · 품목은 목록의 것을 쓴다(`item_of` 는 조문 없는 해석에서 틀린다)
    assert (
        [r["id"] for r in rows] == [ad]
        and rows[0]["조항"] == []
        and rows[0]["품목"] == sc.AD[ad][1]
    )
    pend = next(iter(sc.PENDING))
    g = _f(
        int(pend),
        질의요지="'온 가족이 사용' 광고 가능 여부",
        회답="「화장품법」 제13조에 따라 판단합니다.",
    )
    assert mi.candidate(g) and not mi.in_scope(g) and mi.parse([g])[1]["대기"] == 1


@pytest.mark.gate
def test_목록은_자리와_지문만_들고_서로_겹치지_않는다() -> None:
    sc = mi.scope
    assert len(sc.AD) == mi.EXPECTED_MIN == 289 and len(sc.PENDING) == 14  # noqa: PLR2004 — [측정] 2026-10-04
    assert not set(sc.AD) & set(sc.PENDING) and set(sc.AD) | set(sc.PENDING) <= sc.REVIEWED
    assert all(
        k.isdigit() and len(v[0]) == 12 and v[1] in ("식품", "화장품") for k, v in sc.AD.items()
    )  # noqa: PLR2004
    # 읽은 해석 묶음이 손으로 바뀌면 멈춘다
    ids = sorted(sc.REVIEWED, key=int)
    assert len(ids) == sc.REVIEWED_N == mi.EXPECTED_TOTAL_MIN
    assert hashlib.sha256("\n".join(ids).encode()).hexdigest()[:12] == sc.REVIEWED_SHA


@pytest.mark.gate
def test_읽지_않은_해석과_질의가_바뀐_해석은_멈춘다() -> None:
    sc = mi.scope
    assert not {f["법령해석일련번호"] for f in FIELDS} & sc.REVIEWED  # 합성 글은 읽은 적이 없다
    got = mi.check_scope(FIELDS)
    assert len(got) == 1 and "읽지 않은 해석 8" in got[0] and "조문 그물에 걸리는 것 5" in got[0]
    ad = next(iter(sc.AD))
    same = _f(int(ad), 질의요지="가")
    # 지문은 글자 · 숫자만 본다 — 띄어쓰기 · 부호가 달라도 같은 질의다
    assert mi.ask_key(_f(1, 질의요지="가 나?")) == mi.ask_key(_f(2, 질의요지="가나"))
    assert any("질의가 바뀌었다" in b for b in mi.check_scope([same]))
