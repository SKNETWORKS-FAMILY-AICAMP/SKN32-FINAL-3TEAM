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

#: 🔴 **갈래가 늘면 여기 한 줄만 늘린다** — 아래 게이트들이 전부 이 표를 돈다 (D-99).
#:    ⛔ 2026-09-12 오후에 `SQL_LEXICAL` 이 늘었다. 표를 안 고쳤으면 새 갈래만
#:       거버넌스 조인 검사를 **안 받은 채** 지나갔다 — 그것이 U2 가 새는 자리다.
QUERIES = (rt.SQL_VECTOR, rt.SQL_LITERAL, rt.SQL_LEXICAL)


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
def test_모든_질의가_거버넌스_조인을_든다(sql: str, needle: str) -> None:
    """⛔ 하나에만 빠져도 그 갈래로 들어온 결과가 범위를 벗어난다."""
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


def test_match_값이_넷이다() -> None:
    """⛔ 갈래가 늘면 화면이 모르는 값을 받는다. 늘릴 때는 화면과 같이 늘린다.

    🚨 `MATCH_TEXT` 는 **옛 이름**이고 `MATCH_LITERAL` 과 같은 값이라야 한다 (D-192).
       ⛔ 갈라 두면 옛 이름으로 거르던 코드가 조용히 0건을 낸다.
    """
    assert {rt.MATCH_VECTOR, rt.MATCH_LEXICAL, rt.MATCH_LITERAL, rt.MATCH_FUSED} == {
        "vector",
        "lexical",
        "literal",
        "fused",
    }
    assert rt.MATCH_TEXT == rt.MATCH_LITERAL


def _hit(cid: str = "c1", **kw: object) -> rt.Hit:
    """빈 `Hit` 한 줄. 🔴 **칸이 늘면 여기만 고친다** — 테스트마다 적으면 두 벌이 된다.

    ⛔ 종전에는 테스트가 인자를 손으로 나열했고, 0008 이 `paragraph_no`·`context` 를
       더했을 때 **`TypeError` 로 깨진 채** 남아 있었다 (게이트가 아니라 안 걸렸다).
    """
    base: dict = {
        "chunk_id": cid,
        "law_id": None,
        "article": None,
        "paragraph": None,
        "item": None,
        "paragraph_no": None,
        "context": None,
        "doc_type": None,
        "category": [],
        "text": "…",
        "attribution": None,
        "source_url": None,
        "match": rt.MATCH_LITERAL,
    }
    return rt.Hit(**{**base, **kw})


def test_어휘_기호_갈래는_거리가_없다() -> None:
    """🚨 0.0 으로 채우면 「완전 일치」가 되어 **없는 값이 가장 좋은 값**이 된다."""
    assert _hit(match=rt.MATCH_LITERAL).distance is None
    assert _hit(match=rt.MATCH_LEXICAL).distance is None
    # 🚨 반대쪽도 같다 — 벡터 갈래에 `lexical` 0.0 을 넣으면 「어휘가 하나도 안 겹쳤다」가 된다
    assert _hit(match=rt.MATCH_VECTOR, distance=0.6).lexical is None


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
def test_모든_질의가_항과_호를_싣는다() -> None:
    """⛔ 이 둘이 빠지면 화면이 **어느 호가 걸렸는지 말할 수 없다** (D-158 · D-100)."""
    for sql in QUERIES:
        assert "c.paragraph" in sql
        assert "c.item" in sql


# ── 0008 자립 텍스트·입력 지문 ────────────────────────────────────────────
@pytest.mark.gate
def test_모든_질의가_문맥과_항서수를_싣는다() -> None:
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


# ── 어휘 갈래 (0010 · D-193 · D-194) ──────────────────────────────────────
@pytest.mark.gate
def test_어휘_질의가_생성열을_쓴다() -> None:
    """🔴 질의가 `to_tsvector(...)` 를 **다시 적으면** 정의가 두 벌이 된다 (D-99).

    ⛔ 한쪽만 고치면 결과는 맞는데 인덱스를 안 타서 **조용히 느려진다** —
       틀린 것보다 찾기 어렵다. 색인의 정의는 `db/schema.sql` 의 생성열 한 줄뿐이다.
    """
    assert "c.tsv" in rt.SQL_LEXICAL
    assert "to_tsvector" not in rt.SQL_LEXICAL


@pytest.mark.gate
def test_어휘_질의가_걸린_것만_낸다() -> None:
    """⛔ `@@` 없이 `ts_rank_cd` 로만 정렬하면 **안 걸린 행도 0점으로 전부** 딸려 온다.

    그러면 후보 50개가 「겹치는 것 50개」가 아니라 「아무거나 50개」가 되고,
    RRF 가 그 잡음에 순위를 준다 (D-72 — 없음이 성공으로 집계되지 않게).
    """
    assert "c.tsv @@ query" in rt.SQL_LEXICAL


@pytest.mark.gate
def test_조사표가_길이_내림차순이다() -> None:
    """🔴 「에서는」을 「는」보다 먼저 만나야 **한 겹만** 깎인다.

    ⛔ 짧은 것이 앞에 오면 「에서는」이 「에서」로만 깎여 접두어가 어긋난다.
    """
    lens = [len(j) for j in rt._JOSA]
    assert lens == sorted(lens, reverse=True), f"조사표 순서가 어긋났다: {rt._JOSA}"


@pytest.mark.gate
def test_tsquery_에_구문문자가_안_섞인다() -> None:
    """🔴 `&`·`|`·`!`·`(`·`)` 가 그대로 들어가면 `to_tsquery` 가 **구문 오류로 500** 이다.

    🚨 사용자가 치는 말이다 — 「효과 100%! (최고)」 같은 것이 그대로 온다.
    """
    for q in ("효과 100%! (최고)", "a & b | c", "제5호 아목!!", "'; DROP TABLE chunk; --"):
        out = rt.tsquery(q)
        assert not set(out) & set("&!()'\";-"), f"{q!r} → {out!r} 에 구문문자가 남았다"


@pytest.mark.parametrize(
    ("word", "want"),
    [
        ("면역력이", "면역력"),
        ("제품보다", "제품"),
        ("질병의", "질병"),
        ("광고에서는", "광고"),
        # 🔴 **낱말 자체가 조사로 끝나는 것은 안 깎는다** — 깎으면 뜻 없는 한 글자가 된다
        ("효과", "효과"),
        ("제품", "제품"),
        ("사과", "사과"),
        # 조사가 아닌 끝 — 그대로
        ("표시광고", "표시광고"),
    ],
)
def test_조사_한_겹만_깎는다(word: str, want: str) -> None:
    assert rt._stem(word) == want


def test_질의가_OR_로_묶인다() -> None:
    """🚨 AND 면 광고 문구는 거의 언제나 0건이다 — 조문이 어절 전부를 담지 않는다."""
    out = rt.tsquery("면역력이 쑥쑥 올라갑니다")
    assert out == "면역력:* | 쑥쑥:* | 올라갑니다:*"
    assert "&" not in out


def test_검색어가_없으면_빈_질의다() -> None:
    """🔴 빈 `to_tsquery` 를 넣으면 0건이 나오는데, 그 0 은 「겹치는 조문이 없다」와 다르다."""
    assert rt.tsquery("!!! ???") == ""
    assert rt.tsquery("이 의 는") == ""  # 어절이 전부 조사뿐


def test_조사만인_어절은_검색어가_아니다() -> None:
    """⛔ `이:*` 는 접두어라 「이하」·「이상」·「이내」에 다 붙는다 — 잡음이 순위를 먹는다.

    🚨 **한 글자라서 빼는 것이 아니다.** 「암」은 남아야 한다 — 조사인 것만 뺀다.
    """
    assert rt.terms("이 제품은 암 예방에 좋습니다") == ["제품", "암", "예방", "좋습니다"]


# ── RRF 결합 (D-193) ──────────────────────────────────────────────────────
def test_RRF_는_두_갈래_모두에_있는_것을_올린다() -> None:
    """★ 이것이 합치는 이유 그 자체다 — 한쪽 6위가 다른 쪽 1위를 이기지 못하지만,
    **양쪽에 걸친 것**은 한쪽만 1위인 것을 이긴다."""
    vec = [_hit("both", match=rt.MATCH_VECTOR), _hit("v_only", match=rt.MATCH_VECTOR)]
    lex = [_hit("l_only", match=rt.MATCH_LEXICAL), _hit("both", match=rt.MATCH_LEXICAL)]
    out = rt.fuse(vec, lex, limit=5)
    assert out[0].chunk_id == "both"
    assert out[0].rank_vector == 1
    assert out[0].rank_lexical == 2


def test_RRF_가_한쪽에만_있는_것을_버리지_않는다() -> None:
    """🚨 후보 밖은 **「모른다」이지 「최하위」가 아니다** (D-188) — 최하위로 채워 넣지 않는다."""
    out = rt.fuse([_hit("v", match=rt.MATCH_VECTOR)], [_hit("l", match=rt.MATCH_LEXICAL)], limit=5)
    assert {h.chunk_id for h in out} == {"v", "l"}
    got = {h.chunk_id: h for h in out}
    assert got["v"].rank_lexical is None  # ⛔ 0 도 아니고 51 도 아니다
    assert got["l"].rank_vector is None


def test_RRF_가_동점을_chunk_id_로_가른다() -> None:
    """같은 질의가 두 번 다른 답을 내면 재현이 안 된다 (D-176)."""
    a = rt.fuse([_hit("b"), _hit("a")], [], limit=2)
    assert [h.rrf for h in a] == sorted((h.rrf for h in a), reverse=True)
    tie = rt.fuse([_hit("z")], [_hit("a")], limit=2)
    assert [h.chunk_id for h in tie] == ["a", "z"]


@pytest.mark.gate
def test_합친_줄이_양쪽_점수를_다_들고_있다() -> None:
    """⛔ 합치면서 한쪽 점수를 잃으면 **그 갈래가 올렸다고 말하면서 근거는 안 보여 준다.**

    🔴 2026-09-12 오후 실측에서 실제로 그랬다 — `rank_lexical: 3` 인데 `lexical: null`.
       종전 구현이 `base.setdefault` 로 **벡터 쪽 행 통째**를 들고 갔기 때문이다.
    🚨 종전 게이트는 `distance` 만 봤다. **한쪽만 보는 대칭 검사는 반대쪽을 못 잡는다** (D-170).
    """
    vec = [_hit("x", match=rt.MATCH_VECTOR, distance=0.62)]
    lex = [_hit("x", match=rt.MATCH_LEXICAL, lexical=0.04)]
    for a, b in ((vec, lex), (lex, vec)):  # 🚨 넣는 순서가 바뀌어도 같아야 한다
        out = rt.fuse(a if a is vec else vec, b if b is lex else lex, limit=1)
        assert out[0].distance == 0.62, "거리를 잃었다"
        assert out[0].lexical == 0.04, "어휘 점수를 잃었다"
        assert out[0].match == rt.MATCH_FUSED
    # ⛔ 한쪽에만 있는 줄은 **없는 쪽이 None 그대로**라야 한다 — 0.0 으로 채우지 않는다
    only = rt.fuse(vec, [], limit=1)[0]
    assert only.distance == 0.62
    assert only.lexical is None
