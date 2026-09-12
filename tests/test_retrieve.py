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
