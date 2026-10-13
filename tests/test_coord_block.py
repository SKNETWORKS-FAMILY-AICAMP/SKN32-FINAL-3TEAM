"""좌표 자격 — 경로가 문서 안에 하나뿐 ∧ 형제 순서가 맞을 때만 좌표가 선다 (🆕 2026-10-12 · D-293 개정).

🔴 막는 것
   ① 목 글자표가 「하」 에서 끝나 「거. 너. …」 를 앞 항목에 붙이는 것 · 마커 바로 뒤 「 를 못 읽는 것 (파서 결함)
   ② 번호가 되돌아가거나 빈 번호를 줄로 안은 노드에 좌표가 서는 것 (`law_norm.order_breaks`)
   ③ 좌표 자격을 안 단 파생물 · 재적재 전 DB 가 「막지 않는다」로 읽히는 것 (D-220)
   ④ 산문 고시 좌표가 「1.」 과 「1)」 을 가르지 못하는 것 (안건 2 (나) — 꼴 보존)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import graph as g
from app import retrieve as rt
from preprocess import chunk
from preprocess import law_article as la
from preprocess import law_norm as ln

pytestmark = pytest.mark.gate


def _paths(content: str) -> list[str]:
    return [str(n["path"]) for n in ln.parse(content)]


def _broken(content: str) -> list[str]:
    nodes = ln.parse(content)
    out = ln.order_breaks(
        [(n["section"], str(n["path"]), n["level"], n["marker"], n["lines"]) for n in nodes]
    )
    return [str(nodes[i]["path"]) for i in sorted(out)]


def test_목_글자표는_하_다음_거부터_이어_간다() -> None:
    jo = "가나다라마바사아자차카타파하거너"
    content = "1. 머리\n" + "".join(f"{c}. {c} 항목\n" for c in jo)
    paths = _paths(content)
    assert "1.거" in paths and "1.너" in paths
    assert ln.JO == rt._JO  # noqa: SLF001 — 짝이 갈리면 인용 조립이 거목을 모른다


def test_마커_바로_뒤의_꺾쇠를_마커로_읽는다() -> None:
    assert _paths("1. 첫째\n2. 둘째\n3.「다른 고시」와의 관계\n") == ["1", "2", "3"]


def test_마커_바로_뒤_한글은_마커로_읽지_않고_순서_검사가_그_노드를_막는다() -> None:
    content = "3. 머리\n가. 목\n1) 하나\n2) 둘\n3) 셋\n4)시장출하\n5) 다섯\n"
    assert "3.가.4" not in _paths(content)
    assert _broken(content) == ["3.가.3"]  # 「4)」 를 줄로 안은 앞 형제만


def test_번호가_되돌아가면_형제_묶음_전체를_막고_자손은_막지_않는다() -> None:
    content = "1. 머리\n가. 하나\n1) 손자\n나. 둘\n가. 본문 안 열거\n"
    broken = _broken(content)
    assert broken == ["1.가", "1.나", "1.가"]
    assert "1.가.1" not in broken and "1" not in broken


@pytest.mark.parametrize(
    "content",
    [
        "1. 머리\n가. 하나\n다. 셋\n",  # 원문 자체의 빈 번호 — 앞 노드가 「나.」 를 안지 않았다
        "1. 머리\n(바) 이어 매긴 번호\n(사) 다음\n",  # 이어 매긴 번호
    ],
)
def test_원문의_빈_번호와_이어_매긴_번호는_통과한다(content: str) -> None:
    assert _broken(content) == []


def test_별표_행은_모두_좌표_자격_칸을_든다() -> None:
    rows = [
        {"path": "1"},
        {"path": "1~1", "경로중복": True, "순서깨짐": True},
        {"path": "2", "순서깨짐": True},
    ]
    ln.coord_block(rows)
    assert [r["좌표막힘"] for r in rows] == ["", "겹침", "순서"]
    assert all("순서깨짐" not in r for r in rows)


def test_산문_경로는_마커의_꼴을_보존한다() -> None:
    rows = la._prose("Ⅰ. 목적\nⅡ. 기준\n1. 숫자\n1) 괄호 숫자\n가) 괄호 글자\n")  # noqa: SLF001
    assert [r["항"] for r in rows] == ["Ⅰ", "Ⅱ", "Ⅱ.1", "Ⅱ.1.1)", "Ⅱ.1.1).가)"]


def test_산문_좌표_자격은_겹침과_순서를_가르고_검사용_칸을_지운다() -> None:
    rows = la._prose("Ⅰ. 머리\n1. 하나\n2. 둘\n1. 본문 안 열거\n2:x\n")  # noqa: SLF001
    la.mark_coord_block(rows)
    got = {(r["항"], r["좌표막힘"]) for r in rows}
    assert ("Ⅰ", "") in got and ("Ⅰ.1", "겹침") in got and ("Ⅰ.2", "순서") in got
    assert not any(k.startswith("_") for r in rows for k in r if k != "_상위")


def test_다시_쓰인_장_번호는_다른_구역이라_형제가_아니다() -> None:
    rows = la._prose("Ⅰ. 목적\nⅡ. 본문\nⅢ. 일반\nⅢ. 재검토기한\n")  # noqa: SLF001
    la.mark_coord_block(rows)
    assert {r["항"]: r["좌표막힘"] for r in rows} == {"Ⅰ": "", "Ⅱ": "", "Ⅲ": "", "2:Ⅲ": ""}


@pytest.mark.parametrize(
    ("row", "want"),
    [
        ({"doc_type": "법령", "paragraph": "Ⅲ.2.가", "coord_block": ""}, "Ⅲ.2.가"),
        ({"doc_type": "법령", "paragraph": "Ⅱ.1.거.1).가)", "coord_block": ""}, "Ⅱ.1.거.1).가)"),
        ({"doc_type": "법령", "paragraph": "Ⅲ.2.가", "coord_block": "순서"}, None),
        ({"doc_type": "법령", "paragraph": "Ⅲ.2.가", "coord_block": "겹침"}, None),
        ({"doc_type": "법령", "paragraph": "Ⅲ.2.가", "coord_block": None}, None),  # 재적재 전
        # 「2:」 는 우리가 센 구역이다
        ({"doc_type": "법령", "paragraph": "2:Ⅲ", "coord_block": ""}, None),
        (
            {
                "doc_type": "별표",
                "annex_no": 4,
                "item": "본문",
                "paragraph": "1.거",
                "coord_block": "",
            },
            "[별표 4]제1호거목",
        ),
        (
            {
                "doc_type": "별표",
                "annex_no": 1,
                "item": "본문",
                "paragraph": "3.나.3",
                "coord_block": "순서",
            },
            None,
        ),
        (
            {
                "doc_type": "별표",
                "annex_no": 1,
                "item": "본문",
                "paragraph": "2",
                "coord_block": None,
            },
            None,
        ),
        # 조문은 이 칸을 안 본다 — 원천 키가 조 · 항 · 호다
        (
            {
                "doc_type": "법령",
                "article": "제8조",
                "paragraph": "①",
                "item": "",
                "coord_block": None,
            },
            "제8조제1항",
        ),
    ],
)
def test_좌표는_막지_않을_때만_선다(row: dict, want: str | None) -> None:
    assert rt.citation(row) == want


def test_장은_산문_경로에서만_읽는다() -> None:
    assert rt.prose_chapter("Ⅲ.2.가") == "Ⅲ"
    assert rt.prose_chapter("2:Ⅲ") == "2:Ⅲ"
    assert rt.prose_chapter("①") is None and rt.prose_chapter("1.가") is None


def test_칸이_없는_별표_파생물이면_청크가_멈춘다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "law_norm"
    d.mkdir()
    row = {"law_id": "013475", "section": "본문", "path": "1", "text": "본문", "lines": ["1. 본문"]}
    (d / "013475_0006.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    with pytest.raises(SystemExit, match="좌표막힘"):
        chunk.from_annex()


def test_칸이_없는_산문_파생물이면_청크가_멈춘다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = {
        "키": "prose-0",
        "조": "Ⅰ",
        "가지": "",
        "항": "Ⅰ",
        "본문": "Ⅰ. 목적 이 고시는 광고를 정한다",
        "법령": "x",
        "파일": "admrul_20207_x.xml",
    }
    (tmp_path / "law_article.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    with pytest.raises(SystemExit, match="좌표막힘"):
        chunk.from_articles()


def test_근거_조문에_문서_이름이_실린다() -> None:
    d: dict = dict(
        chunk_id="c",
        law_id="20246",
        article="",
        paragraph="Ⅲ.1",
        item="",
        paragraph_no=None,
        context="",
        part_no=1,
        part_total=1,
        exempt_of="",
        coord_block="",
        doc_type="법령",
        annex_no=None,
        doc_title="표시ㆍ광고 내용의 실증에 관한 운영 고시",
        law="표시광고법",
        text="…",
        attribution=None,
        source_url=None,
    )
    hit = rt.Hit(
        **d, match=rt.MATCH_FUSED, citation=rt.citation(d), basis_citation=rt.basis_citation(d)
    )
    ev = g._evidence_article(hit)  # noqa: SLF001
    assert ev is not None and ev.article == "Ⅲ.1" and ev.doc_title == d["doc_title"]
