"""검색 코어의 계약 — DB 없이 검사할 수 있는 것만 (2026-09-12).

🔴 **이 파일이 보장하지 못하는 것을 먼저 적는다** (D-170 · D-188).
   여기 있는 것은 전부 **질의문과 자료형에 대한 정적 검사**다. 실제 DB 에 붙여
   행이 맞게 나오는지는 **검사하지 않는다.** 그것은 사람이 `/search` 를 열어서 본다.
   ⛔ 그러므로 이 파일이 초록이라고 「검색이 된다」고 말하지 않는다.

★ 그래도 값이 있는 이유 — 여기서 막는 것은 **조용히 틀리는 것**이다.
  거버넌스 조인이 빠지면 U2 가 안 열린 원천이 RAG 에 실리는데, 그것은 눈으로 안 보인다.
"""

from __future__ import annotations

import dataclasses

import pytest

from app import retrieve as rt

QUERIES = (rt.SQL_VECTOR, rt.SQL_TEXT)


@pytest.mark.gate
@pytest.mark.parametrize("sql", QUERIES)
@pytest.mark.parametrize(
    "needle",
    [
        # 🔴 거버넌스를 **질의로** 건다 — 게이트가 아니라 WHERE 절이다
        "source_use",
        "'U2_rag'",
        "use_code",
        "u.allowed",
        # 폐지된 조문·제외된 프래그먼트가 섞이지 않게 하는 뷰
        "v_current_chunk",
    ],
)
def test_두_질의_모두_거버넌스_조인을_든다(sql: str, needle: str) -> None:
    """⛔ 둘 중 하나에만 있으면 그 갈래로 들어온 결과가 범위를 벗어난다."""
    assert needle in sql, f"질의에 {needle!r} 이 없다 — 거버넌스가 새는 자리다"


@pytest.mark.gate
def test_벡터_질의가_model_id_를_대조한다() -> None:
    """저장한 벡터와 다른 모델로 만든 질의를 비교하면 거리는 뜻 없는 수다.

    🚨 `embed.py` 가 행마다 `model_id` 를 넣는 이유가 이것인데, 이 대조가 유일한 소비자다.
    """
    assert "e.model_id = %s" in rt.SQL_VECTOR


@pytest.mark.gate
def test_코사인_연산자를_쓴다() -> None:
    """`scripts/embed.py` 는 정규화 없이 `encode()` 한다 — `<->`(L2)는 길이에 끌려간다."""
    assert rt.VECTOR_OP == "<=>"
    assert "<->" not in rt.SQL_VECTOR


@pytest.mark.parametrize("sql", QUERIES)
def test_정렬이_있다(sql: str) -> None:
    """정렬 없는 `LIMIT` 은 비결정적이다 — 같은 질의가 다른 답을 낸다."""
    assert "ORDER BY" in sql
    assert "LIMIT %s" in sql


@pytest.mark.parametrize("sql", QUERIES)
def test_동점을_chunk_id_로_가른다(sql: str) -> None:
    """거리가 같거나 조문이 같을 때도 순서가 고정돼야 재현된다 (D-176)."""
    order = sql[sql.index("ORDER BY") :]
    assert "c.chunk_id" in order


def test_match_는_두_값뿐이다() -> None:
    """⛔ 갈래가 늘면 화면이 모르는 값을 받는다. 늘릴 때는 화면과 같이 늘린다."""
    assert {rt.MATCH_VECTOR, rt.MATCH_TEXT} == {"vector", "text"}


def test_text_갈래는_거리가_없다() -> None:
    """🚨 0.0 으로 채우면 「완전 일치」가 되어 **없는 값이 가장 좋은 값**이 된다."""
    hit = rt.Hit(
        chunk_id="c1",
        law_id=None,
        article=None,
        doc_type=None,
        category=[],
        text="…",
        attribution=None,
        source_url=None,
        match=rt.MATCH_TEXT,
    )
    assert hit.distance is None


def test_Hit_가_SearchHit_과_같은_칸을_든다() -> None:
    """`api.search` 가 `SearchHit(**asdict(hit))` 로 넘긴다 — 칸이 어긋나면 500 이다.

    ⛔ 두 모양이 두 파일에 산다(D-99). 합칠 수 없는 이유는 하나가 DB 자료형이고
       다른 하나가 HTTP 계약이라서다 — 그래서 **어긋남을 검사로 잡는다.**
    """
    from app.api import SearchHit  # noqa: PLC0415 — fastapi 는 이 테스트에서만 든다

    assert {f.name for f in dataclasses.fields(rt.Hit)} == set(SearchHit.model_fields)


# ── citation 조립 (2026-09-12) ────────────────────────────────────────────
@pytest.mark.parametrize(
    ("row", "want"),
    [
        (
            {"doc_type": "법령", "article": "제8조", "paragraph": "①", "item": "1."},
            "제8조제1항제1호",
        ),
        (
            {"doc_type": "법령", "article": "제8조의3", "paragraph": "②", "item": "5."},
            "제8조의3제2항제5호",
        ),
        ({"doc_type": "법령", "article": "제8조", "paragraph": "①", "item": ""}, "제8조제1항"),
        ({"doc_type": "법령", "article": "제18조", "paragraph": "", "item": ""}, "제18조"),
        # ⛔ 별표는 계층 표기가 `2.가.10` 이라 같은 규칙이 안 먹는다 — 조립하지 않는다
        (
            {"doc_type": "별표", "article": "제19조제7항", "paragraph": "7.나.2", "item": "본문"},
            None,
        ),
        # ★ 0008 — 원문에 「①」가 없어도 **우리가 센 서수**가 있으면 인용이 선다
        (
            {
                "doc_type": "법령",
                "article": "제10조",
                "paragraph": "",
                "item": "3.",
                "paragraph_no": 1,
            },
            "제10조제1항제3호",
        ),
        (
            {
                "doc_type": "법령",
                "article": "제10조",
                "paragraph": "",
                "item": "2.",
                "paragraph_no": 2,
            },
            "제10조제2항제2호",
        ),
        # 🔴 항번호가 없는데 호가 있다 — 「항 없음」이 아니라 **번호 안 쓴 제1항**이다.
        #    조까지만 내면 「제10조제3호」인데 실은 「제10조제1항제3호」다 (실측 283건).
        ({"doc_type": "법령", "article": "제10조", "paragraph": "", "item": "3."}, None),
        # 🚨 모르는 항 표기 — 조까지만 내지 않고 **통째로 포기한다**
        ({"doc_type": "법령", "article": "제8조", "paragraph": "제1항", "item": "1."}, None),
        ({"doc_type": "법령", "article": "제8조", "paragraph": "①", "item": "가."}, None),
        ({"doc_type": "법령", "article": "", "paragraph": "①", "item": "1."}, None),
    ],
)
def test_citation_조립(row: dict, want: str | None) -> None:
    """🔴 부분 인용을 내지 않는다 — 「제8조」가 실은 제3항이면 틀린 근거다 (D-100)."""
    assert rt.citation(row) == want


@pytest.mark.gate
def test_두_질의_모두_항과_호를_싣는다() -> None:
    """⛔ 이 둘이 빠지면 화면이 **어느 호가 걸렸는지 말할 수 없다** (D-158 · D-100)."""
    for sql in QUERIES:
        assert "c.paragraph" in sql
        assert "c.item" in sql


# ── 0008 자립 텍스트·입력 지문 ────────────────────────────────────────────
@pytest.mark.gate
def test_두_질의_모두_문맥과_항서수를_싣는다() -> None:
    """⛔ `context` 는 **임베딩이 본 것과 같은 값**이다. 응답에 없으면 화면이 검색이 본
    문맥을 모른 채 보여 준다 — 그러면 둘이 갈린 줄도 모른다 (D-99)."""
    for sql in QUERIES:
        assert "c.context" in sql
        assert "c.paragraph_no" in sql


@pytest.mark.gate
def test_임베딩_입력판_섞임을_막는다() -> None:
    """🔴 전부 옛판·전부 새판은 통과, **반쯤 옮긴 것만** 막는다 (D-176).

    ⛔ `model_id` 는 문맥판과 무문맥판을 구별하지 못한다. 섞이면 거리가 조용히 뜻을 잃는다.
    """

    class _Cur:
        def __init__(self, row: tuple[int, int]) -> None:
            self.row = row

        def execute(self, *_: object) -> None:
            return None

        def fetchone(self) -> tuple[int, int]:
            return self.row

    rt.check_inputs(_Cur((0, 0)))  # 빈 표
    rt.check_inputs(_Cur((0, 2585)))  # 전부 새판
    rt.check_inputs(_Cur((2585, 2585)))  # 전부 옛판
    with pytest.raises(rt.InputsMixed):
        rt.check_inputs(_Cur((100, 2585)))  # 🔴 섞였다


def test_임베딩_입력이_문맥과_본문을_잇는다() -> None:
    """🚨 `text` 는 그대로 두고 **입력만** 키운다 — 인용 단위가 살아 있어야 한다 (D-158)."""
    from scripts import embed  # noqa: PLC0415 — 이 테스트에서만 든다

    ctx = "제8조(부당한 표시 또는 광고행위의 금지)\n① 누구든지 …아니 된다"
    row = {"context": ctx, "text": "1. 마약"}
    assert embed.embed_input(row) == f"{ctx}\n1. 마약"
    assert embed.embed_input({"context": "", "text": "1. 마약"}) == "1. 마약"
    # ⛔ 문맥이 다르면 지문도 달라야 한다 — 같으면 섞임을 못 잡는다
    assert embed.input_fingerprint(row) != embed.input_fingerprint(
        {"context": "", "text": "1. 마약"}
    )
