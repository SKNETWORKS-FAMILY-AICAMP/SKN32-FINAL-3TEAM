"""적용 제외 목 — 검색에는 남기고 위반 근거 좌표는 부모로 올린다 (🆕 2026-09-28 · 팀장 판정 (나) · D-238 개정).

🔴 **왜 있는가** — 「다만 … 제외한다」의 하위 목은 해당하면 **위반이 아닌** 경우다. 그런데 그 청크의 문맥이 부모 목의
   금지 문장을 들고 있어 검색이 금지 본문보다 먼저 올렸다(「암 예방」 식품 근거 1위 = 특수의료용도식품 제외 목 · 사실원장 ㊷).
   판정 노드가 그 좌표를 위반 근거로 쓰면 D-238 이 라벨에서 막은 오류가 판정에 들어간다.
★ 값은 **한 함수**(`preprocess/law_norm.exemption_parents`)에서 나와 청크 → DB → 검색 → 판정 그래프 · 탐침까지 흐른다.
   이 파일은 그 길의 마디마다 한 번씩 댄다.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from app import graph as g
from app import retrieve as rt
from preprocess import chunk, guide_label, law_norm

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "derived" / "chunks.jsonl"


def _node(path: str, text: str, section: str = "본문") -> dict:
    return {
        "law_id": "013453",
        "annex_no": 1,
        "annex_no_head": 1,
        "section": section,
        "annex_title": "부당한 표시 또는 광고의 내용(제3조제1항 관련)",
        "article": "제3조제1항",
        "path": path,
        "level": 1,
        "text": text,
    }


#: 013453 [별표 1] 과 013475 [별표 3] 의 모양을 줄인 것 — 글귀는 원문 그대로다
NODES = [
    _node(
        "1", "질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 다음 각 목의 표시 또는 광고"
    ),
    _node(
        "1.가",
        "질병 또는 질병군(疾病群)의 발생을 예방한다는 내용의 표시ㆍ광고. 다만, 다음의 어느 하나에 해당하는 경우는 제외한다.",
    ),
    _node(
        "1.가.1",
        "특수의료용도식품에 섭취대상자의 질병명 및 영양조절을 위한 식품임을 표시ㆍ광고하는 경우",
    ),
    _node("1.가.2", "건강기능식품에 기능성을 인정받은 사항을 표시ㆍ광고하는 경우"),
    _node("1.나", "질병 또는 질병군에 치료 효과가 있다는 내용의 표시ㆍ광고"),
    _node("2", "한글로 표시한다. 다만, 다음 각 목의 어느 하나에 해당하는 경우에는 제외한다."),
    _node("2.나", "한글표시를 생략할 수 있는 경우"),
    _node("2.나.1", "자사에서 제조ㆍ가공할 목적으로 수입하는 식품등"),
    # 단서가 목 **안에** 있고 하위 목이 없다 — 목 전체가 위반 유형이다(D-238 표의 뒤 모양)
    _node("5.가", "… 표시ㆍ광고. 다만, 영업자가 제조ㆍ판매하는 경우는 제외한다."),
    _node(
        "머리",
        "제1호 및 제3호에도 불구하고 다음 각 호에 해당하는 표시ㆍ광고는 부당한 표시또는 광고행위로 보지 않는다.",
        "비고",
    ),
    _node("1", "… 다만, 다음의 경우는 제외한다.", "비고"),
    _node("1.가", "비고 아래 목", "비고"),
]


@pytest.mark.gate
def test_단서를_든_목의_하위_목이_가장_가까운_단서로_올라간다() -> None:
    assert law_norm.exemption_parents(NODES) == {
        "1.가.1": "1.가",
        "1.가.2": "1.가",
        "2.나": "2",
        "2.나.1": "2",  # 손자 목 — 중간 목 2.나 에는 단서가 없다
    }


@pytest.mark.gate
def test_라벨_게이트와_청크_표시가_같은_함수를_쓴다() -> None:
    """🔴 두 벌이면 라벨이 막는 목과 검색이 올리는 목이 갈린다 (D-99)."""
    assert guide_label.EXC is law_norm.EXC
    assert guide_label.excluded_paths(NODES) == set(law_norm.exemption_parents(NODES))


def _write_norm(tmp_path: pathlib.Path, stem: str, nodes: list[dict]) -> None:
    d = tmp_path / "law_norm"
    d.mkdir(exist_ok=True)
    (d / f"{stem}.jsonl").write_text(
        "".join(json.dumps(n, ensure_ascii=False) + "\n" for n in nodes), encoding="utf-8"
    )


@pytest.mark.gate
def test_청크가_제외_목에만_부모_경로를_단다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_norm(tmp_path, "013453_0001", NODES)
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    rows = {(r["item"], r["paragraph"]): r for r in chunk.from_annex()}
    assert rows[("본문", "1.가.1")]["exempt_of"] == "1.가"
    assert rows[("본문", "2.나.1")]["exempt_of"] == "2"
    # 🚨 빈 문자열 = 「제외 목이 아니다」 — 부모 목 · 단서가 목 안에 있는 목 · 비고 구역
    assert rows[("본문", "1.가")]["exempt_of"] == ""
    assert rows[("본문", "5.가")]["exempt_of"] == ""
    assert rows[("비고", "1.가")]["exempt_of"] == ""
    # 🔴 임베딩 입력은 그대로다 — 재임베딩이 없다
    assert "exempt_of" not in rows[("본문", "1.가.1")]["context"]


@pytest.mark.gate
def test_013453_에서_단서가_하나도_안_걸리면_멈춘다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 원문 판이 바뀌어 단서 글귀가 사라지면 표시 없이 조용히 실린다 — 쓰기 전에 멈춘다 (D-220)."""
    _write_norm(tmp_path, "013453_0001", [n for n in NODES if "다만" not in n["text"]])
    monkeypatch.setattr(chunk, "DERIVED", tmp_path)
    with pytest.raises(SystemExit, match="단서가 한 곳도"):
        chunk.from_annex()


def _row(**kw: object) -> dict:
    return {
        "doc_type": "별표",
        "annex_no": 1,
        "item": "본문",
        "paragraph": "1.가.1",
        "exempt_of": "1.가",
        **kw,
    }


@pytest.mark.gate
@pytest.mark.parametrize(
    ("row", "want"),
    [
        (_row(), "[별표 1]제1호가목"),  # 제외 목 → 부모 목의 좌표
        (_row(paragraph="1.가", exempt_of=""), "[별표 1]제1호가목"),  # 제외 목이 아니다 → 자기 좌표
        (_row(exempt_of=None), None),  # 🚨 재적재 전 — 제외 목인지 모른다 (D-220)
        (
            {"doc_type": "법령", "article": "제8조", "paragraph": "①", "item": "1."},
            "제8조제1항제1호",
        ),
    ],
)
def test_위반_근거_좌표는_제외_목을_부모로_올린다(row: dict, want: str | None) -> None:
    assert rt.basis_citation(row) == want
    # 🔴 청크 자신의 좌표는 그대로다 — 화면은 「이 글이 어디 있나」를 본다
    if row.get("exempt_of"):
        assert rt.citation(row) == "[별표 1]제1호가목1)"


def _hit(cid: str, paragraph: str, exempt_of: str) -> rt.Hit:
    d = {
        "chunk_id": cid,
        "law_id": "013453",
        "article": "제3조제1항",
        "paragraph": paragraph,
        "item": "본문",
        "paragraph_no": None,
        "context": "",
        "part_no": 1,
        "part_total": 1,
        "exempt_of": exempt_of,
        "doc_type": "별표",
        "annex_no": 1,
        "doc_title": None,
        "law": "식품표시광고법",
        "text": cid,
        "attribution": None,
        "source_url": None,
    }
    return rt.Hit(
        **d, match=rt.MATCH_FUSED, citation=rt.citation(d), basis_citation=rt.basis_citation(d)
    )


@pytest.mark.gate
def test_법별_노드가_제외_목을_부모_좌표로_올리고_단서로_나른다() -> None:
    arts, provs = g._pick([_hit("x1", "1.가.1", "1.가"), _hit("x2", "1.가.2", "1.가")])
    # 제외 목 둘이 같은 부모로 올라온다 — 좌표는 한 번 · 제외 목의 글이 위반 근거 자리에 안 보이게 청크는 비운다
    assert [(a.article, a.chunk_id) for a in arts] == [("[별표 1]제1호가목", None)]
    assert [(p.citation, p.parent, p.chunk_id) for p in provs] == [
        ("[별표 1]제1호가목1)", "[별표 1]제1호가목", "x1"),
        ("[별표 1]제1호가목2)", "[별표 1]제1호가목", "x2"),
    ]


@pytest.mark.gate
def test_부모_청크_자신이_걸리면_청크가_있는_줄로_바꾼다() -> None:
    arts, _ = g._pick([_hit("x1", "1.가.1", "1.가"), _hit("p", "1.가", "")])
    assert [(a.article, a.chunk_id) for a in arts] == [("[별표 1]제1호가목", "p")]


@pytest.mark.gate
def test_겹침을_걷은_뒤에_LAW_TOP_K_로_자른다() -> None:
    kids = [_hit(f"k{i}", f"1.가.{i}", "1.가") for i in range(1, 4)]
    others = [_hit(f"o{j}", f"1.{'나다라마바사아자'[j]}", "") for j in range(g.LAW_TOP_K)]
    arts, _ = g._pick(kids + others)
    assert len(arts) == g.LAW_TOP_K
    assert arts[0].article == "[별표 1]제1호가목"
    assert arts[1].chunk_id == "o0"  # 겹친 제외 목 둘이 자리를 먹지 않았다


@pytest.mark.gate
def test_판정이_부모로_올린_서로_다른_좌표를_뭉개지_않는다() -> None:
    """⛔ 종전 열쇠 `chunk_id` 로는 `chunk_id=None` 인 줄이 좌표가 달라도 하나로 뭉개졌다."""
    arts, provs = g._pick([_hit("x1", "1.가.1", "1.가"), _hit("y1", "2.나.1", "2")])
    state = {
        "sents": ["문장"],
        "law_results": [
            g.LawResult(
                law="law_food",
                sent_ids=("s0",),
                articles=(("s0", arts),),
                provisos=(("s0", provs),),
            )
        ],
    }
    ev = g.judge(state)["sentences"][0].evidence
    assert [a.article for a in ev] == ["[별표 1]제1호가목", "[별표 1]제2호"]


@pytest.mark.gate
def test_탐침은_위반_근거_좌표로_채점한다() -> None:
    """⛔ 종전에는 청크 자신의 좌표로 채점해 와일드카드가 제외 목을 정답으로 셌다(사실원장 ㊷ · 31건 중 12건)."""
    from scripts import search_probe as sp  # noqa: PLC0415

    kid = _hit("x1", "1.가.1", "1.가")
    assert sp.rank_of([kid], ["013453:[별표 1]제1호가목"]) == 1  # 부모 좌표로 맞는다
    assert sp.rank_of([kid], ["013453:[별표 1]제1호가목1)"]) is None  # 제외 목 좌표로는 안 맞는다
    unknown = dataclasses.replace(_hit("x2", "1.가.1", "1.가"), basis_citation=None)
    assert sp.rank_of([unknown], ["013453:[별표 1]제1호*"]) is None


@pytest.mark.gate
def test_청크의_제외_목이_라벨_게이트의_경로와_같다() -> None:
    """🔴 기기 `chunks.jsonl` 의 제외 표시가 D-238 표(013453 [별표 1] 8경로)와 같은가. 표시 전 판이면 정본은 빨강, 사본은 skip."""
    from scripts import derived_manifest as dm  # noqa: PLC0415

    dm.gate_guard(CHUNKS)
    rows = [json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x.strip()]
    if any("exempt_of" not in r for r in rows):
        why = (
            "chunks.jsonl 이 적용 제외 표시 전 판이다 — 정본: `launcher.py chunk --dump` · "
            "사본: 정본의 data-publish 뒤 `data-sync`"
        )
        if dm.role() == "canonical":
            pytest.fail(f"🔴 {why}")
        pytest.skip(why)
    got = {
        r["paragraph"]
        for r in rows
        if r["law_id"] == "013453" and r["doc_type"] == "별표" and r["exempt_of"]
    }
    assert got == {"1.가.1", "1.가.2", "1.라.1", "1.라.2", "3.가", "3.나", "3.다", "3.라"}
    assert all(r["doc_type"] == "별표" for r in rows if r["exempt_of"])


class _Cur:
    """`exempt_map` 이 쓰는 커서 면만 흉내 낸다 — 칸 이름은 `SQL_EXEMPT` 에서 읽는다."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.sql = ""

    def execute(self, sql: str) -> None:
        self.sql = sql

    @property
    def description(self) -> list:
        from scripts import search_probe as sp  # noqa: PLC0415

        head = sp.SQL_EXEMPT.split("FROM")[0].removeprefix("SELECT")
        names = [x.strip().split(".")[-1] for x in head.split(",")]
        return [type("Col", (), {"name": n}) for n in names]

    def fetchall(self) -> list[tuple]:
        return self._rows


@pytest.mark.gate
def test_탐침_제외_목_지도는_검색과_같은_함수로_좌표를_세운다() -> None:
    """🔴 좌표를 여기서 다시 조립하면 규칙이 두 벌이 된다 (D-99) — `rt.citation` · `rt.basis_citation` 이 낸 값이어야 한다."""
    from scripts import search_probe as sp  # noqa: PLC0415

    #        law_id    doc_type article      paragraph item    paragraph_no exempt_of annex_no
    rows = [
        ("013453", "별표", "제3조제1항", "3.나", "본문", None, "3", 1),
        ("013453", "별표", "제3조제1항", "1.가.1", "본문", None, "1.가", 1),
        # 별표 번호 없음 → 좌표가 안 선다 (D-224)
        ("013453", "별표", "제3조제1항", "3.나", "본문", None, "3", None),
    ]
    cur = _Cur(rows)
    got = sp.exempt_map(cur)
    assert "exempt_of <> ''" in cur.sql
    assert got == {
        ("013453", "[별표 1]제3호나목"): "[별표 1]제3호",
        ("013453", "[별표 1]제1호가목1)"): "[별표 1]제1호가목",
    }


@pytest.mark.gate
@pytest.mark.parametrize(
    ("want", "blocked"),
    [
        ("013453:[별표 1]제3호나목", True),  # 2026-09-29 실물 — 제외 목을 위반 근거로 적었다
        ("013453:[별표 1]제3호나목*", True),  # 와일드카드여도 부모 좌표로 영영 안 맞는다
        ("[별표 1]제3호나목", True),  # 법 ID 없는 옛 모양도 막는다
        ("013453:[별표 1]제3호*", False),  # 부모 — 정정한 모양
        ("013453:[별표 1]제3호", False),
        ("013475:[별표 1]제3호나목", False),  # 다른 법의 같은 글자 좌표는 제외 목이 아니다
        ("013094:제8조제1항제3호", False),
    ],
)
def test_탐침_정답이_제외_목을_가리키면_멈춘다(want: str, blocked: bool) -> None:
    """🔴 D-238 ① 의 탐침 판 (2026-09-29 · 팀장 판정 (가)) — 라벨에만 걸려 있던 게이트가 탐침 정답에는 없었다."""
    from scripts import search_probe as sp  # noqa: PLC0415

    exempt = {("013453", "[별표 1]제3호나목"): "[별표 1]제3호"}
    bad = sp.exempt_wants([{"q": "면역력 강화에 도움을 줍니다.", "want": [want]}], exempt)
    assert bool(bad) is blocked
    if blocked:
        assert "[별표 1]제3호`" in bad[0] and "D-238" in bad[0]
