"""두 겹 안내(쉬운 풀이 · 원문 보기) — 승인된 것만 · 판정에 들지 않는다 (🆕 2026-10-20 · D-348 보충 32 결정 3).

지키는 것
  ① 승인 표가 비면 응답 어디에도 안내 칸이 없다(None) — 초안 글자가 나가지 않는다
  ② 승인된 열쇠는 품목 · 하위 전제 선택지(`Branch`) · 실증 질문(`SubstBranch`)에 붙는다 — 분기 안 문장 · 기록 문장 모두
  ③ 안내를 붙여도 판정은 바뀌지 않는다(안내 칸을 뺀 응답이 같다)
  ④ 실증 기준 문안 줄마다 열쇠가 하나씩 있다(문안 표가 한 곳 · 같은 글자 두 줄 없음)
  ⑤ 빈 안내는 계약이 거부한다 · 짝 표의 조문이 생성물에 없으면 잡는다
  ⑥ 원문은 수집본 글자 그대로 옮긴다 · 좌표가 수집본 한 줄이 아니면 멈춘다 · 커밋된 생성물이 수집본 · 짝 표와 같다(수집본이 있는 기기)
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import guide
from app import reasons as rs
from app.contracts import Guide, GuideArticle, Premise, ProductContext
from scripts import guide_build as gb
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

TEXT = "이 제품은 피로 회복에 탁월한 효과가 있습니다."  # 지은 문장 — `tests/test_fold_invariant.py` 와 같다


class _Cur:
    """`v_risk_lookup` 대역 — `tests/test_premise_known.py` `_Cur` 와 같은 모양(시험 파일이라 한 벌 더 둔다)."""

    def __init__(self) -> None:
        self.rows = sr.rule_rows(sr.load_rules())

    def execute(self, sql: str, params: object = None) -> None:
        assert "v_risk_lookup" in sql

    def fetchall(self) -> list[tuple]:
        return [
            (r["id"], r["law_id"], r["type"], r["kind"], r.get("annex1"), r.get("cover"), r["quote"], r.get("fact"))
            for r in self.rows
        ]  # fmt: skip


def _resp():  # noqa: ANN202
    """품목 모름 · 사전 침묵 · 인코더 거짓_과장 — 분기 여섯 · 분기마다 실증 질문."""
    st: dict = {
        "text": TEXT,
        "sents": [TEXT],
        "product": ProductContext(),
        "laws": g.laws_for(None),
        "dict_scans": [g.DictScan(sent_id="s0", ran=True)],
        "law_results": [g.LawResult(law=law, sent_ids=("s0",)) for law in g.laws_for(None)],
        "encodings": [
            g.SentEncoding(
                sent_id="s0", scores=(("거짓_과장", 0.9),), candidates=("거짓_과장",), input=x
            )
            for x in ("모름", "식품", "건기식", "화장품")
        ],
    }
    cfg = {"configurable": {"conn": _Cur()}}
    for node in (g.judge, g.assess_risk, g.premise_branches, g.doc_rules):
        out = node(st, cfg) if node in (g.assess_risk, g.premise_branches) else node(st)
        if "sentences" in out:
            st["sentences"] = g.upsert_sentences(st.get("sentences", []), out["sentences"])
        if "branches" in out:
            st["branches"] = out["branches"]
    return g.to_response(st)  # type: ignore[arg-type]


def _guides(resp) -> list:  # noqa: ANN001
    out = [b.guide for b in resp.branches]
    for s in [*resp.sentences, *(x for b in resp.branches for x in b.sentences)]:
        out += [
            s.substantiation.guide if s.substantiation else None,
            s.fact_check.guide if s.fact_check else None,
        ]
    return out


@pytest.fixture(autouse=True)
def _no_tau(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(g, "_premise_tau", lambda v: None)


ART = GuideArticle(law_name="시험 고시", where="제6조③", text="원문 글자", version="2025-01-01")


def _approve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        guide, "PLAIN", {guide.premise_key(Premise.일반식품_기능성): ("무엇", "확인", "헷갈림")}
    )
    monkeypatch.setattr(
        guide,
        "ARTICLES",
        {
            guide.premise_key(Premise.일반식품_기능성): ("c1",),
            "subst:식품표시광고법:거짓_과장": ("c1",),
        },
    )
    monkeypatch.setattr(guide, "TEXTS", {"c1": ART})


def test_승인_표가_비면_안내_칸이_없다() -> None:
    assert guide.PLAIN == {} and guide.ARTICLES == {}, (
        "승인 전 — 표가 비어 있어야 한다(초안은 문서에)"
    )
    resp = _resp()
    assert resp.branches and all(x is None for x in _guides(resp))


def test_승인된_열쇠에_안내가_붙는다(monkeypatch: pytest.MonkeyPatch) -> None:
    _approve(monkeypatch)
    resp = _resp()
    by = {b.premise: b for b in resp.branches}
    gd = by[Premise.일반식품_기능성].guide
    assert gd is not None and (gd.what, gd.check, gd.pitfall) == ("무엇", "확인", "헷갈림")
    assert gd.articles == [ART]
    assert by[Premise.화장품].guide is None, "승인 안 된 열쇠는 비어 있다"
    # 식품 분기의 실증 질문(식품표시광고법 줄)에는 원문만 붙는다 · 화장품 분기(화장품법 줄)는 없다
    (fs,) = by[Premise.식품].sentences
    assert fs.substantiation is not None and fs.substantiation.guide is not None
    assert fs.substantiation.guide.what is None and fs.substantiation.guide.articles == [ART]
    (cs,) = by[Premise.화장품].sentences
    assert cs.substantiation is not None and cs.substantiation.guide is None


def test_안내를_붙여도_판정은_같다(monkeypatch: pytest.MonkeyPatch) -> None:
    def strip(resp):  # noqa: ANN001, ANN202
        d = resp.model_dump(exclude={"timings"})
        for b in d["branches"]:
            b["guide"] = None
            for s in b["sentences"]:
                for k in ("substantiation", "fact_check"):
                    if s.get(k):
                        s[k]["guide"] = None
        for s in d["sentences"]:
            for k in ("substantiation", "fact_check"):
                if s.get(k):
                    s[k]["guide"] = None
        return d

    before = strip(_resp())
    _approve(monkeypatch)
    assert strip(_resp()) == before


def test_실증_기준_문안_줄마다_열쇠가_하나씩() -> None:
    n = len(rs.SUBST_TEXT) + len(rs.TYPE_SUBST_TEXT)
    assert len(guide.SUBST_KEYS) == n
    assert all(k.startswith("subst:") for k in guide.SUBST_KEYS.values())


def test_빈_안내는_거부하고_빠진_조문은_잡는다() -> None:
    with pytest.raises(ValueError, match="빈 안내"):
        Guide()
    assert guide.missing_texts({"k": ("a", "b")}, {"a": ART}) == ["b"]


def test_원문은_수집본_글자_그대로() -> None:
    corpus = {
        "admrul_1|6||③|": [
            {
                "파일": "admrul_1_20250101.xml",
                "조": "6",
                "가지": "",
                "항": "③",
                "본문": "③ 원문",
                "법령": "고시",
            }
        ],
        "admrul_1|3||②|3.": [
            {
                "파일": "admrul_1_20250101.xml",
                "조": "3",
                "가지": "",
                "항": "②",
                "호": "3.",
                "항본문": "② 다음은 제외한다.",
                "본문": "3. 영유아",
                "법령": "고시",
            }
        ],
    }
    a = gb.article("admrul_1|6||③|", corpus)
    assert (a.where, a.text, a.lead, a.version) == ("제6조③", "③ 원문", None, "2025-01-01")
    b = gb.article("admrul_1|3||②|3.", corpus)
    assert (b.where, b.lead, b.text) == ("제3조②제3호", "② 다음은 제외한다.", "3. 영유아")
    with pytest.raises(SystemExit, match="한 줄이 아니다"):
        gb.article("admrul_1|9|||", corpus)


def test_별표_원문도_수집본_글자_그대로() -> None:
    corpus = {
        "별표:013453_0001:3.나": [
            {"annex_no_head": "1", "annex_title": "부당한 표시 또는 광고의 내용", "path": "3.나", "text": "나. 원문", "_law": "시행령", "_version": "2025-09-19"}
        ]
    }  # fmt: skip
    a = gb.article("별표:013453_0001:3.나", corpus)
    assert (a.law_name, a.where, a.text, a.version) == (
        "시행령 [별표 1] 부당한 표시 또는 광고의 내용",
        "3.나",
        "나. 원문",
        "2025-09-19",
    )
    corpus["별표:013453_0001:3.나"][0]["_law"] = None
    with pytest.raises(SystemExit, match="법 이름을 모른다"):
        gb.article("별표:013453_0001:3.나", corpus)


def test_커밋된_생성물이_수집본_짝_표와_같다() -> None:
    if not gb.CORPUS.exists():
        pytest.skip("수집본 없음(클라우드 클론) — 정본 · 사본 기기에서 잰다")
    assert gb.main(["--check"]) == 0
