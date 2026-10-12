"""유형별 참조 조항표 — 표 · 후보에 붙는 조항 (🆕 2026-10-12 · D-327).

🔴 막는 것
   ① 그 법에 조항이 없는 유형에 **다른 조항이 붙는 것** — 빈칸은 빈 채로 둔다 (D-220)
   ② 참조 조항이 **근거(`evidence`)에 섞이거나 판정을 바꾸는 것** — 「이 유형이라면 이 조항」이지 찾아낸 근거가 아니다 (D-323 결정 2 · 3)
   ③ 화장품법 제13조제1항제4호가 **유형을 얻는 것** — 표는 보여 줄 조항만 정한다. 라벨 · 채점은 그대로다 (D-282 · D-321)
   ④ 옮긴 후보([별표 1] 4.나)에 유형의 일반 조항이 붙는 것
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import premise as pm
from app.contracts import EncoderTypeCandidate, EvidenceArticle, Premise, Violation
from collect import statute

pytestmark = pytest.mark.gate

FAIR, FOOD, COSM = "표시광고법", "식품표시광고법", "화장품법"


def test_표는_금지_조항을_먼저_세부_기준을_뒤에_낸다() -> None:
    assert statute.references("거짓_과장", FAIR) == ("002011:제3조제1항제1호", "005361:제3조제1항")
    assert statute.references("거짓_과장", FOOD) == (
        "013094:제8조제1항제4호",
        "013453:[별표 1]제4호",
    )
    assert statute.references("후기_체험기_기만", FOOD) == (
        "013094:제8조제1항제5호",
        "013453:[별표 1]제5호다목",
    )


def test_화장품법_대응은_판정한_여섯_칸이다() -> None:
    assert statute.references("거짓_과장", COSM) == (
        "002015:제13조제1항제4호",
        "008741:[별표 5]제2호사목",
        "008741:[별표 5]제2호아목",
    )
    assert statute.references("소비자_기만", COSM) == (
        "002015:제13조제1항제4호",
        "008741:[별표 5]제2호사목",
    )
    assert statute.references("부당_비교광고", COSM) == ("008741:[별표 5]제2호바목",)
    assert statute.references("비방광고", COSM) == ("008741:[별표 5]제2호카목",)
    assert statute.references("의약품_오인", COSM) == (
        "002015:제13조제1항제1호",
        "008741:[별표 5]제2호가목",
    )
    assert statute.references("기능성화장품_오인", COSM) == (
        "002015:제13조제1항제2호",
        "008741:[별표 5]제2호나목",
    )


def test_그_법에_조항이_없으면_비운다() -> None:
    assert statute.references("건강기능식품_오인", COSM) == ()
    assert statute.references("질병_예방치료_표방", FAIR) == ()
    assert statute.references("없는_유형", FOOD) == ()


def test_표는_라벨의_유형을_바꾸지_않는다() -> None:
    # 화장품법 제4호는 거짓 · 과장 후보에 **보여 줄** 조항이지만 여전히 유형을 주지 않는다
    assert statute.type_of("002015:제13조제1항제4호") is None
    assert ("002015:제13조제1항제4호", "거짓_과장") not in statute.table()


def _cand(v: str, moved: str | None = None) -> EncoderTypeCandidate:
    return EncoderTypeCandidate(
        violation=Violation(v), confidence=0.9, moved_from=Violation(moved) if moved else None
    )


def test_후보의_조항은_보낸_법마다_실리고_basis_는_거짓이다() -> None:
    refs = g._candidate_refs(_cand("거짓_과장"), (FAIR, COSM), None)
    assert [(r.law_id, r.article) for r in refs] == [
        ("002011", "제3조제1항제1호"),
        ("005361", "제3조제1항"),
        ("002015", "제13조제1항제4호"),
        ("008741", "[별표 5]제2호사목"),
        ("008741", "[별표 5]제2호아목"),
    ]
    assert all(r.basis is False and r.quote is None for r in refs)  # 좌표만 — DB 가 없다
    assert g._candidate_refs(_cand("거짓_과장"), (), None) == []  # 법을 모르면 붙이지 않는다


def test_원문이_있으면_그_줄을_쓴다() -> None:
    quoted = EvidenceArticle(
        law_id="002011", article="제3조제1항제1호", quote="1. 거짓ㆍ과장의 표시ㆍ광고"
    )
    refs = g._candidate_refs(_cand("거짓_과장"), (FAIR,), {"002011:제3조제1항제1호": quoted})
    assert refs[0] is quoted and refs[1].quote is None


def test_옮긴_후보는_옮겨_간_인용의_조항을_싣는다() -> None:
    moved = _cand("거짓_과장", moved="건강기능식품_오인")
    refs = g._candidate_refs(moved, (FAIR, FOOD), None)
    assert [(r.law_id, r.article) for r in refs] == [
        ("002011", "제3조제1항제1호"),
        ("005361", "제3조제1항"),
        ("013094", "제8조제1항제4호"),
        ("013453", "[별표 1]제4호나목"),
    ]
    assert statute.reference_of_cite(pm.UNRECOGNIZED_FUNCTION_CITE)[1] == "013453:[별표 1]제4호나목"


def test_인코더_후보에_조항이_붙어도_판정은_그대로다() -> None:
    e = g.SentEncoding(sent_id="s0", candidates=("거짓_과장",), scores=(("거짓_과장", 0.9),))
    plain = g._encoder_candidates(e, (Premise.화장품,))
    with_refs = g._encoder_candidates(e, (Premise.화장품,), (FAIR, COSM), None)
    assert plain[0].references == [] and len(with_refs[0].references) == 5
    assert [(c.violation, c.confidence, c.moved_from) for c in plain] == [
        (c.violation, c.confidence, c.moved_from) for c in with_refs
    ]
