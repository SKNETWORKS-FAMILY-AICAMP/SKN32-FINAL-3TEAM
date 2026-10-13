"""판정 화면의 참고 조문 — 광고를 다루는 별표만 싣는다 (🆕 2026-10-12 · D-328).

🔴 막는 것
   ① 광고와 무관한 별표(독성시험법 · 품질관리기준 · 영양표시 대상 …)가 **참고 조문으로 오르는 것**
   ② 위임 근거를 **모르는** 별표가 실리는 것 — 모르면 싣지 않는다 (D-220)
   ③ 적용 제외 목이 근거로 바뀐 **뒤에** 걸러 문서를 잃는 것 — `Hit` 단계에서 거른다
   ④ 별표 거름이 법령 · 행정규칙 **본문**까지 지우는 것 — 본문은 이 규칙의 대상이 아니다
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import retrieve as rt

pytestmark = pytest.mark.gate

LAW_FILE = "law_013475_20241230.xml"
ADM_FILE = "admrul_75449_20250101.xml"


def test_법령_별표는_위임_조문의_제목에_광고가_있어야_실린다() -> None:
    titles = {"제8조": "광고의 기준", "제6조": "영양표시", "제17조": "과징금 부과 제외 대상"}
    assert g.annex_in_scope("식품등 광고 시 준수사항(제8조 관련)", "시행규칙", LAW_FILE, titles)
    assert not g.annex_in_scope(
        "영양표시 대상 식품등(제6조제1항 관련)", "시행규칙", LAW_FILE, titles
    )
    assert not g.annex_in_scope("과징금 부과 제외 대상(제17조 관련)", "시행규칙", LAW_FILE, titles)


def test_위임_조문이_여럿이면_하나라도_맞으면_실린다() -> None:
    titles = {"제5조": "표시방법 등", "제7조": "광고 예시"}
    assert g.annex_in_scope("표시방법(제5조제2항 및 제7조제2항 관련)", "x", LAW_FILE, titles)


def test_행정규칙_별표는_고시_이름으로_가른다() -> None:
    assert g.annex_in_scope(
        "기능성 범위(제4조제1항 관련)", "…식품등의 기능성 표시 또는 광고에 관한 규정", ADM_FILE, {}
    )
    assert not g.annex_in_scope(
        "독성시험법", "기능성화장품 심사에 관한 규정", "admrul_36122_x.xml", {}
    )


@pytest.mark.parametrize(
    ("title", "law_title", "src", "titles"),
    [
        (
            "광고 시 준수사항(제8조 관련)",
            "시행규칙",
            None,
            {"제8조": "광고의 기준"},
        ),  # 딸린 법령 문서를 못 찾음
        (
            "광고 시 준수사항",
            "시행규칙",
            LAW_FILE,
            {"제8조": "광고의 기준"},
        ),  # 위임 조문이 제목에 없음
        ("광고 시 준수사항(제8조 관련)", "시행규칙", LAW_FILE, {}),  # 조문 제목을 못 읽음
    ],
)
def test_모르면_싣지_않는다(title: str, law_title: str, src: str | None, titles: dict) -> None:
    assert not g.annex_in_scope(title, law_title, src, titles)


class _Cur:
    """`annex_scope` 의 두 질의에 답하는 대역 — 질의는 상수의 **동일성**으로 가른다."""

    def __init__(self, docs: list[tuple], chunks: list[tuple]) -> None:
        self.docs, self.chunks, self.rows, self.calls = docs, chunks, [], []

    def execute(self, sql: str, args: tuple | None = None) -> None:
        self.calls.append(sql)
        if sql is g.SQL_ANNEX_DOCS:
            self.rows = self.docs
        elif sql is g.SQL_ARTICLE_HEADS:
            laws, arts = args
            self.rows = [c for c in self.chunks if c[0] in laws and c[1] in arts]
        else:
            raise AssertionError(f"모르는 질의 {sql[:40]!r}")

    def fetchall(self) -> list[tuple]:
        return self.rows


def test_조문_제목은_조_행의_머리와_항_행의_문맥에서_읽는다() -> None:
    """013453 제3조처럼 제목뿐인 조 머리 행이 청크에 없으면 항 행의 문맥이 제목이다. 호 행의 문맥(제목 + 항 본문)은 읽지 않는다."""
    docs = [
        (
            "013453",
            1,
            "부당한 표시 또는 광고의 내용(제3조제1항 관련)",
            "시행령",
            "law_013453_x.xml",
        ),
        ("013475", 6, "식품등 광고 시 준수사항(제8조 관련)", "시행규칙", "law_013475_x.xml"),
        ("013475", 4, "영양표시 대상 식품등(제6조제1항 관련)", "시행규칙", "law_013475_x.xml"),
        ("75449", 2, "기능성 범위(제4조제1항 관련)", "…표시 또는 광고에 관한 규정", ADM_FILE),
        ("36122", 1, "독성시험법", "기능성화장품 심사에 관한 규정", "admrul_36122_x.xml"),
    ]
    chunks = [
        ("013453", "제3조", "① 법 제8조제1항에 따른 …", "부당한 표시 또는 광고의 내용", ""),
        ("013475", "제8조", "제8조(광고의 기준) 법 제7조제2항에 따른 …", "", ""),
        ("013475", "제6조", "① 영양표시 …", "[2028-01-01 시행 예정]\n영양표시", ""),
        (
            "013475",
            "제6조",
            "1. 열량",
            "영양표시\n① 광고 문구가 아닌 항 본문",
            "1.",
        ),  # 호 행 — 읽지 않는다
    ]
    assert g.annex_scope(_Cur(docs, chunks)) == (("013453", 1), ("013475", 6), ("75449", 2))


def test_조문_제목이_엇갈리면_모르는_것이다() -> None:
    docs = [("013475", 6, "광고 시 준수사항(제8조 관련)", "시행규칙", "law_013475_x.xml")]
    chunks = [
        ("013475", "제8조", "제8조(광고의 기준) …", "", ""),
        ("013475", "제8조", "① …", "다른 제목", ""),
    ]
    assert g.annex_scope(_Cur(docs, chunks)) == ()


def _hit(**kw: object) -> rt.Hit:
    d: dict = dict(
        chunk_id="c",
        law_id="013475",
        article="제6조",
        paragraph="1",
        item="본문",
        paragraph_no=None,
        context="",
        part_no=1,
        part_total=1,
        exempt_of="",
        coord_block="",
        doc_type="별표",
        annex_no=4,
        doc_title=None,
        law="식품표시광고법",
        text="…",
        attribution=None,
        source_url=None,
    )
    d.update(kw)
    return rt.Hit(
        **d, match=rt.MATCH_FUSED, citation=rt.citation(d), basis_citation=rt.basis_citation(d)
    )


def test_거름은_별표만_본다() -> None:
    scope = frozenset({("013475", 6)})
    assert g.in_reference_scope(_hit(annex_no=6), scope)
    assert not g.in_reference_scope(_hit(annex_no=4), scope)
    assert not g.in_reference_scope(_hit(annex_no=None), scope)
    assert not g.in_reference_scope(_hit(annex_no=6), frozenset())  # 모르면 싣지 않는다
    # 🔄 2026-10-12 (D-329) — 본문도 범위를 탄다(종전 「본문은 규칙 밖」). 별표 표는 본문을 가르지 않는다
    body = _hit(doc_type="법령", annex_no=None, article="제8조", paragraph="①", item="")
    assert not g.in_reference_scope(body, scope)  # 본문 범위가 비면 싣지 않는다
    assert g.in_reference_scope(body, frozenset(), frozenset({("013475", "제8조")}))


def _state(hits: list[rt.Hit], scope: tuple, body: tuple = ()) -> dict:
    ev = g.SentEvidence(
        sent_id=g.sent_id(0),
        vector_hits=tuple(hits),
        lexical_hits=(),
        vector=True,
        lexical=True,
        pool=len(hits),
    )
    return g.law_payload(
        {"sents": ["문장"], "evidence": [ev], "annex_scope": scope, "body_scope": body}
    )


def test_법별_노드가_허용_밖의_별표를_참고_조문에서_뺀다() -> None:
    hits = [
        _hit(chunk_id="out", annex_no=4, paragraph="1.가"),
        _hit(chunk_id="in", annex_no=6, paragraph="1"),
        _hit(
            chunk_id="body", doc_type="법령", annex_no=None, article="제8조", paragraph="①", item=""
        ),
    ]
    node = g._law_node("law_food")  # noqa: SLF001
    body = (("013475", "제8조"),)
    out = node(_state(hits, (("013475", 6),), body))["law_results"][0].articles[0][1]
    assert {a.chunk_id for a in out} == {"in", "body"}
    # 별표 허용 표가 비면 별표는 하나도 안 실리고 본문은 본문 범위대로다
    out = node(_state(hits, (), body))["law_results"][0].articles[0][1]
    assert {a.chunk_id for a in out} == {"body"}
    # 🆕 D-329 — 본문 범위가 비면 본문도 안 실린다
    out = node(_state(hits, (("013475", 6),)))["law_results"][0].articles[0][1]
    assert {a.chunk_id for a in out} == {"in"}


def test_법별_노드로_보내는_것에_허용_표가_실린다() -> None:
    """⛔ `law_payload` 에 없으면 컴파일본(`Send`)의 노드는 허용 표를 못 본다 — 오류 없이 별표가 전부 빠진다."""
    assert g.law_payload({"annex_scope": (("013475", 6),)})["annex_scope"] == (("013475", 6),)
    assert g.law_payload({})["annex_scope"] == ()
    assert g.law_payload({"body_scope": (("013475", "제8조"),)})["body_scope"] == (
        ("013475", "제8조"),
    )
    assert g.law_payload({})["body_scope"] == ()


# ── 본문 범위 (🆕 2026-10-12 · D-329) ─────────────────────────────────────────────


def test_참고_조문_표는_줄마다_기준과_제목이_있고_조가_겹치지_않는다() -> None:
    from collect import statute

    rows = statute.REFERENCE_ARTICLES
    assert len(rows) == 28
    assert all(c in "abcd" and t for _l, _a, t, c in rows)
    assert len({(r[0], r[1]) for r in rows}) == len(rows)
    # 일반 정의 · 매체 정의는 표에 없다
    assert ("002011", "제2조") not in {(r[0], r[1]) for r in rows}
    assert ("005361", "제2조") not in {(r[0], r[1]) for r in rows}


class _BodyCur:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def execute(self, sql: str, args: tuple | None = None) -> None:
        assert sql is g.SQL_BODY_HEADS

    def fetchall(self) -> list[tuple]:
        return self.rows


LAW_F = "law_013475_20241230.xml"
LAW_N = "식품 등의 표시ㆍ광고에 관한 법률 시행규칙"


def test_법령_본문은_표의_조_중_제목이_같은_것만_실린다(caplog: pytest.LogCaptureFixture) -> None:
    rows = [
        ("013475", "제8조", "제8조(광고의 기준) 법 제7조…", "", "", LAW_N, LAW_F, ""),
        (
            "013475",
            "제9조",
            "제9조(다른 제목) …",
            "",
            "",
            LAW_N,
            LAW_F,
            "",
        ),  # 개정으로 밀렸다 — 표는 「실증방법 등」
        ("013475", "제13조", "제13조(등록사항의 변경) …", "", "", LAW_N, LAW_F, ""),  # 표에 없다
    ]
    out = g.body_scope(_BodyCur(rows))
    assert ("013475", "제8조") in out
    assert ("013475", "제9조") not in out
    assert ("013475", "제13조") not in out
    assert "013475:제9조" in caplog.text


def test_고시_본문은_이름에_광고가_있어야_하고_상투_조문은_뺀다() -> None:
    ad_f, ad_n = "admrul_41277_x.xml", "화장품 표시·광고 실증에 관한 규정"
    rows = [
        ("41277", "제1조", "제1조(목적) …", "", "", ad_n, ad_f, ""),
        ("41277", "제3조", "제3조(실증자료) …", "", "", ad_n, ad_f, ""),
        ("41277", "제6조", "제6조(규제의 재검토) …", "", "", ad_n, ad_f, ""),
        (
            "37098",
            "제6조",
            "제6조(유통화장품의 안전관리 기준) …",
            "",
            "",
            "화장품 안전기준 등에 관한 규정",
            "admrul_37098_x.xml",
            "",
        ),
    ]
    out = g.body_scope(_BodyCur(rows))
    assert ("41277", "제3조") in out
    assert ("41277", "제1조") not in out and ("41277", "제6조") not in out
    assert not any(lid == "37098" for lid, _ in out)


PROSE_F, PROSE_N = "admrul_20207_x.xml", "비교표시·광고에 관한 심사지침"


def _prose_row(paragraph: str, text: str, context: str = "") -> tuple:
    return ("20207", "", text, context, "", PROSE_N, PROSE_F, paragraph)


def test_산문_고시는_장_단위로_싣고_상투_장은_뺀다() -> None:
    """🆕 2026-10-12 (D-293 개정 집행) — 종전 고시 단위(`"*"`)였다. 산문 좌표가 서면 「Ⅰ. 목적」 · 「Ⅵ. 재검토기한」이 참고 조문 자리를 먹는다."""
    rows = [
        _prose_row("Ⅰ", "Ⅰ. 목적 이 심사지침은 …"),
        _prose_row("Ⅱ", "Ⅱ. 적용범위 이 심사지침은 …"),
        # 장 노드가 청크에 없다 — 문맥 첫 줄이 장 머리다
        _prose_row("Ⅳ.1", "1. 일반원칙 …", "Ⅳ. 세부심사지침\n"),
        _prose_row("Ⅵ", "Ⅵ. 재검토기한 공정거래위원회는 …"),
        _prose_row("2:Ⅲ", "Ⅲ. 재검토 기한 …"),  # 다시 쓰인 장 번호의 구역
        # 장 머리 글을 못 읽었다 — 모르면 싣지 않는다
        _prose_row("Ⅴ.1", "1. …", "[시행 예정 표시]"),
    ]
    out = g.body_scope(_BodyCur(rows))
    assert ("20207", "Ⅱ") in out and ("20207", "Ⅳ") in out
    assert ("20207", "Ⅰ") not in out and ("20207", "Ⅵ") not in out and ("20207", "2:Ⅲ") not in out
    assert ("20207", "Ⅴ") not in out
    assert ("20207", "*") not in out


def test_상투_장은_낱말_경계로_가른다() -> None:
    assert g._boilerplate_chapter("목적 이 고시는")  # noqa: SLF001
    assert g._boilerplate_chapter("재검토기한")  # noqa: SLF001
    assert not g._boilerplate_chapter("목적물의 표시")  # noqa: SLF001


def test_본문_거름은_산문_고시를_장으로_받는다() -> None:
    prose = _hit(
        law_id="20207", doc_type="법령", annex_no=None, article="", paragraph="Ⅱ.1", item=""
    )
    assert g.in_reference_scope(prose, frozenset(), frozenset({("20207", "Ⅱ")}))
    assert not g.in_reference_scope(prose, frozenset(), frozenset({("20207", "Ⅰ")}))
    # 고시 단위(`"*"`)는 없어졌다
    assert not g.in_reference_scope(prose, frozenset(), frozenset({("20207", "*")}))
