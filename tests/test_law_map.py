"""법 이름 · 법 ID → 법 축 대응표 (`collect/law_map.py` · 🆕 2026-09-24 · D-271 ①).

🔴 막는 것 —
   ① `TARGETS` 에 법 ID 가 늘었는데 법 축이 없다 · 대응표에만 있는 ID 가 있다 (양방향)
   ② 법률 ID 와 시행령 ID 를 헷갈린다(`005361`)
   ③ 「식품표시광고법 …」 근거를 표시광고법으로 읽는다(짧은 이름이 긴 이름의 꼬리)
   ④ 사전(`banned_terms`)의 근거 중 법을 못 정하는 것이 조용히 기본값으로 떨어진다
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from collect import law_map as lm
from collect.law_api import TARGETS

pytestmark = pytest.mark.gate

ROOT = pathlib.Path(__file__).resolve().parents[1]
BANNED = ROOT / "data" / "derived" / "banned_terms.jsonl"


def _target_ids() -> set[str]:
    return {i for rows in (TARGETS["law"], TARGETS["admrul"]) for i, _, _ in rows}


def test_TARGETS_의_모든_ID_에_법이_있고_남는_것이_없다() -> None:
    ids = _target_ids()
    assert not ids - set(lm.LAW_OF_ID), f"🔴 법 축이 없는 법 ID: {sorted(ids - set(lm.LAW_OF_ID))}"
    assert not set(lm.LAW_OF_ID) - ids, f"🔴 TARGETS 에 없는 ID: {sorted(set(lm.LAW_OF_ID) - ids)}"


def test_법_축은_넷이고_모두_법률_ID_를_가진다() -> None:
    assert set(lm.LAW_OF_ID.values()) == set(lm.LAWS) == set(lm.STATUTE_ID)
    law_ids = {i for i, _, _ in TARGETS["law"]}
    for law, sid in lm.STATUTE_ID.items():
        assert sid in law_ids and lm.LAW_OF_ID[sid] == law


def test_시행령_ID_는_법률_ID_가_아니다() -> None:
    assert lm.LAW_OF_ID["005361"] == "표시광고법"
    assert lm.STATUTE_ID["표시광고법"] == "002011" != "005361"


@pytest.mark.parametrize(
    ("basis", "law"),
    [
        ("표시광고법 제3조제1항제1호", "표시광고법"),
        ("식품표시광고법 제8조제1항제4호", "식품표시광고법"),
        ("식품 등의 표시ㆍ광고에 관한 법률 제8조", "식품표시광고법"),
        ("표시ㆍ광고의 공정화에 관한 법률 제3조", "표시광고법"),
        ("화장품법 제13조제1항", "화장품법"),
        ("건강기능식품에 관한 법률 제18조제1항제1호", "건강기능식품법"),
        ("화장품법 시행규칙 제22조", None),  # 시행규칙을 법률 조문으로 읽지 않는다
        ("의료기기법 제24조", None),  # 우리가 안 가진 법 — 기본값으로 떨어지지 않는다 (D-277)
        ("", None),
    ],
)
def test_근거_문자열의_법(basis: str, law: str | None) -> None:
    assert lm.law_of_basis(basis) == law


def test_참고_전용_법은_축_안에_있다() -> None:
    assert set(lm.LAWS) >= lm.REFERENCE_ONLY


def test_사전의_근거는_전부_법이_정해진다() -> None:
    """🔴 Q4 — 사전 근거가 판정 근거가 된다. 법을 못 정하는 근거가 있으면 그 문장의 근거 조문이 비어 나간다."""
    if not BANNED.exists():
        pytest.skip(
            "banned_terms.jsonl 이 이 기기에 없다 — 기기 축 (D-19) · 대응표 자체는 위 게이트가 본다"
        )
    bad = sorted(
        {
            b
            for line in BANNED.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for b in json.loads(line).get("근거") or []
            if lm.law_of_basis(b) is None
        }
    )
    assert not bad, f"🔴 법을 못 정한 사전 근거 {len(bad)}종: {bad[:5]}"


# ── 🆕 W6 (2026-09-24 · 0019) — 대응표를 **읽는 쪽**이 같은 값을 드는가 ─────────────────────
MIG_0019 = ROOT / "db" / "migrations" / "0019_chunk_law.sql"
SCHEMA = ROOT / "db" / "schema.sql"
CHUNKS = ROOT / "data" / "derived" / "chunks.jsonl"
_PAIR = re.compile(r"\('(\w+)',\s*'(\w+)'\)")
_CHECK = re.compile(r"ck_chunk_law\s+CHECK\s*\(law IN \(([^)]*)\)\)", re.S)


def test_0019_의_대응표가_law_map_과_같다() -> None:
    """🔴 마이그레이션은 그날의 값을 SQL 로 든다(모듈을 부르지 않는다) — 그래서 **글자까지** 댄다 (D-99)."""
    sql = MIG_0019.read_text(encoding="utf-8")
    body = sql[
        sql.index("INSERT INTO _law_of_id") : sql.index(";", sql.index("INSERT INTO _law_of_id"))
    ]
    assert dict(_PAIR.findall(body)) == lm.LAW_OF_ID


@pytest.mark.parametrize("path", [MIG_0019, SCHEMA], ids=["0019", "schema.sql"])
def test_청크_법_CHECK_은_법_축_넷이다(path: pathlib.Path) -> None:
    m = _CHECK.search(path.read_text(encoding="utf-8"))
    assert m, f"🔴 {path.name} 에 ck_chunk_law 가 없다"
    assert set(re.findall(r"'(\w+)'", m.group(1))) == set(lm.LAWS)


def test_검색의_법_필터는_모르는_법을_멈춘다() -> None:
    """⛔ 옛 범주(「일반」·「식품」)를 넘기면 SQL 은 **0건**을 낸다 — 오류 없이 근거가 빈다. 여기서 멈춘다 (D-220)."""
    from app import retrieve as rt  # noqa: PLC0415

    assert rt.law_filter(()) == []
    assert rt.law_filter(["식품표시광고법"]) == ["식품표시광고법"]
    for bad in (["일반"], ["식품"], ["표시광고법", "화장품"]):
        with pytest.raises(ValueError, match="모르는 법"):
            rt.law_filter(bad)
    for sql in (rt.SQL_LITERAL, rt.SQL_LEXICAL, rt.SQL_VECTOR):
        assert "c.law = ANY(" in sql and "category" not in sql


def test_search_요청은_모르는_법을_422_로_돌려보낸다() -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from app.api import SearchRequest  # noqa: PLC0415

    assert SearchRequest(q="면역력").law == []
    assert SearchRequest(q="면역력", law=["화장품법"]).law == ["화장품법"]
    with pytest.raises(ValidationError):
        SearchRequest(q="면역력", law=["일반"])


def test_청크의_법은_법_ID_로_정해져_있다() -> None:
    """🔴 `chunks.jsonl` 의 `law` 가 대응표와 같은가. ⛔ W6 전 판(`category`)이면 정본은 빨강, 사본은 skip."""
    from scripts import derived_manifest as dm  # noqa: PLC0415

    dm.gate_guard(CHUNKS)
    rows = [json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x.strip()]
    if any("law" not in r for r in rows):
        why = "chunks.jsonl 이 W6 전 판이다 — 정본: `launcher.py chunk --dump` · 사본: 정본의 data-publish 뒤 `data-sync`"
        if dm.role() == "canonical":
            pytest.fail(f"🔴 {why}")
        pytest.skip(why)
    bad = [r["chunk_id"] for r in rows if r["law"] != lm.LAW_OF_ID.get(r["law_id"])]
    assert not bad, f"🔴 법이 법 ID 와 어긋난 청크 {len(bad)}개: {bad[:3]}"


def test_검색_탐침의_정답은_법_ID_로_댄다() -> None:
    """🆕 2026-09-24 — 「[별표 1]제1호가목」은 시행령(질병 예방 표방)에도 시행규칙(「제품명」)에도 있다.
    ⛔ 인용 글자만 대면 목록 청크를 정답으로 센다. 끝의 `*` 는 하위 항목까지 — 「제1호*」가 「제10호」를 맞히지 않는다."""
    from scripts import search_probe as sp  # noqa: PLC0415

    class H:
        def __init__(self, law_id: str, citation: str) -> None:
            self.law_id, self.citation = law_id, citation

    want = ["013094:제8조제1항제1호", "013453:[별표 1]제1호*"]
    assert (
        sp.rank_of([H("013475", "[별표 1]제1호가목"), H("013453", "[별표 1]제1호다목")], want) == 2
    )
    assert sp.rank_of([H("013453", "[별표 1]제10호가목")], want) is None
    assert sp.rank_of([H("013094", "제8조제1항제1호")], want) == 1
    assert sp.rank_of([H("999999", "제8조제1항제1호")], "제8조제1항제1호") == 1  # 옛 모양 — 인용만
