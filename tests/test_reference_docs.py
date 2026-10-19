"""참고 조문은 판정 뒤에 유형 · 법 안에서 고른다 (🆕 2026-10-19 · D-348 「검색 · 리랭커의 자리」 (나)).

지키는 것
  ① 표(`statute.REFERENCE_DOCS`) — 유형 · 법 축은 계약 값이다 · 문서는 그 법 축의 법 ID 다(`LAW_OF_ID`) · 법 축마다 법률이 든다
  ② 노드(`graph.references`) — 그 문장 유형의 문서 안 후보만 참고 조문으로 · 유형이 없으면 싣지 않는다 · 근거 조문은 그대로 ·
     판정 칸(판정 · 유형 · 위험도)은 바뀌지 않는다 · 분기 문장은 그 전제의 법으로 고른다 · 후보가 없으면 아무것도 하지 않는다
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import retrieve as rt
from app.contracts import (
    Branch,
    EncoderTypeCandidate,
    EvidenceArticle,
    HoldReason,
    Outcome,
    Premise,
    SentenceJudgment,
    Verdict,
    Violation,
)
from collect import statute
from collect.law_map import LAW_OF_ID, LAWS, STATUTE_ID

pytestmark = pytest.mark.gate


def test_표는_계약_값과_같은_법_축의_문서만_든다() -> None:
    for (v, law), docs in statute.REFERENCE_DOCS.items():
        assert v in Violation.__members__, v
        assert law in LAWS, law
        assert docs, (v, law)
        for d in docs:
            assert LAW_OF_ID.get(d) == law, (v, law, d)
        assert STATUTE_ID[law] in docs, f"법률 자신이 빠졌다 {(v, law)}"
    assert statute.reference_docs(["없는_유형"], "표시광고법") == frozenset()


def _hit(law_id: str, article: str, chunk: str) -> rt.Hit:
    d: dict = dict(
        chunk_id=chunk,
        law_id=law_id,
        article=article,
        paragraph="",
        item="",
        paragraph_no=None,
        context="",
        part_no=1,
        part_total=1,
        exempt_of="",
        coord_block="",
        doc_type="법령",
        annex_no=None,
        doc_title=None,
        law=LAW_OF_ID[law_id],
        text="…",
        attribution=None,
        source_url=None,
    )
    return rt.Hit(
        **d, match=rt.MATCH_FUSED, citation=rt.citation(d), basis_citation=rt.basis_citation(d)
    )


DECEIVE = _hit("38124", "제3조", "c-deceive")  # 기만 심사지침
COMPARE = _hit("20207", "제3조", "c-compare")  # 비교 심사지침
BASIS = EvidenceArticle(law_id="002011", article="제3조", item="제1항제2호", basis=True)
OLD = EvidenceArticle(law_id="20207", article="제3조", item="", chunk_id="c-compare")


def _state(s: SentenceJudgment, branches: list[Branch] | None = None) -> dict:
    hits = (DECEIVE, COMPARE)
    return {
        "laws": ["law_ftc"],
        "evidence": [g.SentEvidence(sent_id="s0", vector_hits=hits, lexical_hits=hits)],
        "sentences": [s],
        "branches": branches or [],
        "law_results": [g.LawResult(law="law_ftc", sent_ids=("s0",), articles=(("s0", (OLD,)),))],
        "annex_scope": [],
        "body_scope": [("38124", "제3조"), ("20207", "제3조")],
    }


def _sent(cands: list[Violation]) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text="지금 가입하면 평생 무료",
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        evidence=[BASIS, OLD],
        encoder_candidates=[EncoderTypeCandidate(violation=v, confidence=0.8) for v in cands],
    )


def test_유형의_문서_안에서만_참고_조문을_고른다() -> None:
    out = g.references(_state(_sent([Violation.소비자_기만])))
    (s,) = out["sentences"]
    assert s.evidence[0] == BASIS, "근거 조문은 그대로 · 앞자리"
    ids = [a.law_id for a in s.evidence[1:]]
    assert ids == ["38124"], "기만 문장에 비교 심사지침(종전 참고 조문)이 남지 않는다"
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf


def test_유형이_없으면_참고_조문을_싣지_않는다() -> None:
    (s,) = g.references(_state(_sent([])))["sentences"]
    assert s.evidence == [BASIS]


def test_분기_문장은_그_전제의_법으로_고른다() -> None:
    sent = _sent([Violation.부당_비교광고])
    b = Branch(
        premise=Premise.일반상품, outcome=Outcome.hold, sentences=[sent], criteria="일반상품이라면"
    )
    out = g.references(_state(sent, [b]))
    (bs,) = out["branches"][0].sentences
    assert [a.law_id for a in bs.evidence[1:]] == ["20207"]


def test_후보가_없으면_아무것도_하지_않는다() -> None:
    out = g.references({"sentences": [_sent([Violation.소비자_기만])], "evidence": []})
    assert "sentences" not in out and "branches" not in out
