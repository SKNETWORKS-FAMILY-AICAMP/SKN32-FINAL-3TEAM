"""검색 잡음 — 행정규칙 산문 조문의 계층 · 청킹 정책 · 규범당 상한 (🆕 2026-09-27 · 사실원장 ㊱).

🔴 막는 것
   ① 행정규칙 산문 조문이 `1)` `가)` 를 몰라 계층이 납작해지고, 「(1) 제품명」 이 부모 없이 되풀이되는 것(36814 · 91청크)
   ② 문맥이 자기 본문을 되풀이하는 것(종전 「제목 = 자기 본문 앞 40자」 · 107청크)
   ③ 짧은 목록 항목 · 자식 있는 짧은 머리 줄 · 삭제 표지 · 수치 조각 · 외국어 번역문이 청크가 되어 벡터 상위를 차지하는 것
   ④ 한 규범이 상위를 다 차지해 금지 조항이 `top_k` 밖으로 밀리는 것(75449 · 「면역력」 10/10)
🚨 원문은 합성이다 — 실물의 **모양**만 옮겼다.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from app import retrieve as rt
from preprocess import chunk
from preprocess import law_article as la

pytestmark = pytest.mark.gate

PROSE = """Ⅲ. 개별표시사항
1. 식품
파. 조미식품
1) 유형
가) 식초류 발효식초, 희석초산
2) 표시사항
(1) 제품명
(2) 식품유형
(3) 소비기한(식초류 및 멸균한 카레제품은 소비기한 또는 품질유지기한)
하. 절임식품
1) 표시사항
(1) 제품명
"""


def test_산문_조문은_괄호_번호_계층을_따르고_상위_항목을_싣는다() -> None:
    rows = la._prose(PROSE)
    by = {r["본문"]: r for r in rows}
    assert "1) 유형" not in by["파. 조미식품"]["본문"]  # 납작해지지 않는다
    item = [r for r in rows if r["본문"] == "(1) 제품명"]
    assert [r["항"] for r in item] == ["Ⅲ.1.파.2.(1)", "Ⅲ.1.하.1.(1)"]
    assert item[0]["제목"] == "Ⅲ. 개별표시사항"
    assert item[0]["항본문"].split("\n") == ["1. 식품", "파. 조미식품", "2) 표시사항"]
    assert chunk._context(item[0]) != chunk._context(item[1])  # 같은 본문이라도 문맥이 가른다
    # 글이 사라지지 않는다
    assert "".join(r["본문"] for r in rows).replace(" ", "") == PROSE.replace("\n", "").replace(
        " ", ""
    )


def test_짧은_끝_항목은_부모에_묶고_자식_있는_짧은_머리_줄은_뺀다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = la._prose(PROSE)
    for r in rows:
        r.update({"법령": "시험 고시", "파일": "admrul_99999_20260101.xml", "가지": ""})
    (tmp_path / "law_article.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    monkeypatch.setattr(chunk, "SKIPPED", chunk.collections.Counter())
    monkeypatch.setitem(chunk.LAW_OF_ID, "99999", "식품표시광고법")
    got, _ = chunk.from_articles()
    texts = [r["text"] for r in got]
    assert "2) 표시사항 (1) 제품명 (2) 식품유형" in texts  # 목록째 읽힌다
    assert "(1) 제품명" not in texts and "2) 표시사항" not in texts
    assert any(t.startswith("(3) 소비기한") for t in texts)  # 긴 항목은 따로 남는다
    assert chunk.SKIPPED["부모에 묶은 짧은 항목"] >= 2
    assert chunk.SKIPPED["자식이 있는 짧은 머리 줄"] >= 1


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("3. 삭제<2018.3.13>", "삭제 표지"),
        ("제21조 <삭제>(2016.12.21.)", "삭제 표지"),
        ("연번: 1 · 성분명: <삭 제> · 최대함량: <삭 제>", "삭제 표지"),
        ("6   55   0.3   0.4   +1.0   +0", "수치 조각"),
        ("① 누구든지 식품등의 명칭ㆍ제조방법을 삭제하거나 표시하여서는 아니 된다", None),
        ("원료명: 구아네티딘 및 그 염류 · CASNo.: 55-65-2", None),
    ],
)
def test_규범이_없는_줄만_뺀다(text: str, why: str | None) -> None:
    assert chunk.skip_reason(text) == why


def test_외국어_문안_이름표가_하나도_없으면_멈춘다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "law_norm"
    d.mkdir()
    row = {
        "law_id": "36814",
        "section": "본문",
        "path": "1",
        "text": "한국어 원문뿐이다",
        "annex_title": "인삼의 유래",
        "annex_no_head": None,
    }
    (d / "36814_0001.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    with pytest.raises(SystemExit, match="외국어 문안"):
        chunk.from_annex()


def _hit(cid: str, law_id: str, law: str = "식품표시광고법") -> rt.Hit:
    return rt.Hit(
        chunk_id=cid,
        law_id=law_id,
        article=None,
        paragraph=None,
        item=None,
        paragraph_no=None,
        context=None,
        part_no=None,
        part_total=None,
        doc_type="별표",
        annex_no=None,
        doc_title=None,
        law=law,
        text=cid,
        attribution=None,
        source_url=None,
        match=rt.MATCH_FUSED,
    )


def test_규범당_상한은_넘친_것을_버리지_않고_뒤로_민다() -> None:
    hits = [_hit(f"a{i}", "75449") for i in range(4)] + [_hit("b", "013094"), _hit("c", "013453")]
    got = [h.chunk_id for h in rt.diversify(hits, cap=2)]
    assert got == ["a0", "a1", "b", "c", "a2", "a3"]
    assert len(got) == len(hits)


def _ranked(ids: list[tuple[str, str, str]]) -> list[rt.Hit]:
    return [_hit(cid, law_id, law) for cid, law_id, law in ids]


def test_법별_보기는_갈래마다_자기_법만_거른_뒤_섞고_상한을_걸되_자르지_않는다() -> None:
    """D-267 — 검색은 한 번 넓게, 법별 노드는 자기 법의 근거만 거른다 (🆕 2026-09-28 · 사실원장 ㊲)."""
    F, C = "식품표시광고법", "화장품법"
    vec = _ranked([("c1", "C1", C), ("c2", "C2", C), ("f1", "75449", F), ("f2", "75449", F)])
    lex = _ranked([("c3", "C3", C), ("f3", "75449", F), ("f4", "013094", F)])
    got = [h.chunk_id for h in rt.law_view(vec, lex, F, cap=2)]
    assert sorted(got) == ["f1", "f2", "f3", "f4"]  # 다른 법은 빠지고 · 자르지 않는다
    assert got.index("f2") > got.index("f4")  # 75449 셋째는 뒤로 민다(버리지 않는다)
    assert (
        rt.law_view(vec, lex, "건강기능식품법") == []
    )  # 없는 법은 빈 목록 — 다른 법으로 채우지 않는다


def test_거른_뒤_섞은_순서는_법마다_따로_검색한_순서와_같다() -> None:
    """⛔ 섞은 뒤 거르면 다른 법 청크가 순위를 부풀려 두 갈래에 다 걸린 정답이 한 갈래 1 위에 밀린다 (09-28 기기 탐침 6 위 · 따로 검색 2 위)."""
    F, C = "식품표시광고법", "화장품법"
    # 넓은 목록 — 정답 w 는 두 갈래 다 걸렸지만 앞에 화장품 청크가 많다 · p 는 벡터 한 갈래 1 위
    vec = _ranked(
        [("p", "013094", F)] + [(f"c{i}", f"C{i}", C) for i in range(150)] + [("w", "013453", F)]
    )
    lex = _ranked([(f"d{i}", f"D{i}", C) for i in range(150)] + [("w", "013453", F)])
    own = [h.chunk_id for h in rt.law_view(vec, lex, F)]
    alone = [
        h.chunk_id
        for h in rt.diversify(
            rt.fuse([h for h in vec if h.law == F], [h for h in lex if h.law == F], limit=10)
        )
    ]
    assert own == alone == ["w", "p"]
    fused_first = [h.chunk_id for h in rt.fuse(vec, lex, limit=400) if h.law == F]
    assert fused_first == ["p", "w"]  # 옛 방식이 뒤집던 모양 — 이 테스트가 무엇을 막는지 남긴다


# ── 넓은 검색 — 법마다 폭만큼 (🆕 2026-09-28 · 사실원장 ㊳) ─────────────────────────
PER_LAW = (
    (rt.SQL_VECTOR, rt.SQL_VECTOR_PER_LAW, "distance, chunk_id"),
    (rt.SQL_LEXICAL, rt.SQL_LEXICAL_PER_LAW, "lexical DESC, chunk_id"),
)


@pytest.mark.parametrize(("base", "per_law", "order"), PER_LAW)
def test_법별_할당_질의가_원_질의를_감싸고_같은_순서로_자른다(
    base: str, per_law: str, order: str
) -> None:
    """🔴 원 질의를 다시 쓰지 않는다 — 감싼다(D-99). 순서가 원 질의와 다르면 「따로 찾은 것과 같다」가 깨진다."""
    inner, _, tail = base.rpartition("\nORDER BY ")
    assert inner in per_law  # 거버넌스 조인 · model_id · 법 필터가 글자 그대로 따라온다
    assert tail.split("\n")[0].replace("c.", "") == order  # 원 질의의 정렬 = 법 안 순번 · 바깥 정렬
    assert f"PARTITION BY w.law ORDER BY {order})" in per_law
    assert per_law.rstrip().endswith(f"ORDER BY {order}")
    assert "p.law_rank <= %s" in per_law
    assert per_law.count("%s") == base.count(
        "%s"
    )  # 자리표시자 순서가 같다 — LIMIT 자리가 순번 상한이 된다
    for needle in ("source_use", "'U2_rag'", "u.allowed", "v_current_chunk"):
        assert needle in per_law


def test_감싼_질의의_바깥_칸_이름이_겹치지_않는다() -> None:
    """⛔ 겹치면 `w.*` 가 모호해져 질의가 멈춘다 — `_SELECT` 에 칸을 더할 때 여기서 먼저 걸린다."""
    names = [e.rpartition(".")[2] for e, _ in rt._SELECT]
    assert len(names) == len(set(names)), names
    assert "law" in names  # 법 안 순번의 기준 칸


class _Cur:
    """실행한 SQL 만 적는 가짜 커서."""

    def __init__(self) -> None:
        self.sqls: list[str] = []

    def execute(self, sql: str, params: tuple = ()) -> None:  # noqa: ARG002
        self.sqls.append(sql)

    def fetchall(self) -> list:
        return []


def test_search_는_전역_상위를_wide_는_법별_할당을_쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 `search()`(API · 지금의 그래프)는 그대로다 — 법별 할당은 `wide()` 로만 들어온다 (㊳)."""
    monkeypatch.setattr(rt, "stored_model_id", lambda cur: "M")
    monkeypatch.setattr(rt, "check_inputs", lambda cur: None)
    monkeypatch.setattr(rt, "encode", lambda model_id, text: [0.0, 1.0])
    cur = _Cur()
    rt.search(cur, "면역력 강화")
    assert cur.sqls == [rt.SQL_VECTOR, rt.SQL_LEXICAL]
    cur = _Cur()
    vec, lex, st = rt.wide(cur, "면역력 강화", 7)
    assert cur.sqls == [rt.SQL_VECTOR_PER_LAW, rt.SQL_LEXICAL_PER_LAW]
    assert (vec, lex, st.pool) == ([], [], 7)


@pytest.mark.skipif(
    os.environ.get("COPYLANE_DB_IT") != "1",
    reason="실제 DB 를 읽는다 — COPYLANE_DB_IT=1 일 때만",
)
def test_실제_DB_에서_법별_할당_어휘_후보가_법_필터와_같다() -> None:
    """㊳ 의 등가를 실제 청크로 — 어휘 갈래만(인코더 없이 돈다). 벡터 갈래는 탐침의 「=」 표지가 본다."""
    from app.db import pg_connect  # noqa: PLC0415
    from collect.law_map import LAWS  # noqa: PLC0415

    with pg_connect() as conn, conn.cursor() as cur:
        for q in ("면역력 강화에 도움", "타사 제품보다 3배", "피부 미백 주름 개선", "제품"):
            wide = rt.by_lexical(cur, q, (), 50, per_law=True)
            for law in LAWS:
                own = rt.by_lexical(cur, q, (law,), 50)
                assert [h.chunk_id for h in wide if h.law == law] == [h.chunk_id for h in own], (
                    q,
                    law,
                )
