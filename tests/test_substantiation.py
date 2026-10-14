"""실증 분기 — 확정된 실증형(B) 거짓_과장 위반에 「실증하면 여기까지」를 붙여 지시(D-268)가 서게 한다 (🆕 2026-10-14 · D-337).

🔴 지키는 것
   - 문안 · 자료 종류는 승인본(`docs/ohb/기준문안_초안_2026-10-02.md` §13)과 글자가 같다 (D-147 · D-263 ②)
   - 붙는 유형은 거짓_과장뿐 · 상한 R0 — 비방은 R1 이상이라(D-304) 1 단계 밖이다
   - 법 축이 둘 이상 섞이면 붙이지 않는다 · 위험도가 없으면 붙이지 않는다(계약 `_subst_is_for_B`)
   - 화장품 전제의 인코더 후보 옮김은 인코더 전용이다 — 사전 경로의 거름표(`pm.NO_HF_MISLEAD`)는 그대로 (D-338)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app import graph as g
from app import reasons as rs
from app.contracts import (
    EvidenceArticle,
    JudgeResponse,
    Premise,
    Risk,
    Violation,
)

pytestmark = pytest.mark.gate

DOC = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md")
FIX = pathlib.Path("tests/fixtures/judge/07_guidance_subst.json")


def _confirmed_b():  # noqa: ANN202
    """픽스처 07 의 확정 B 문장(식품 4 호 인용 · 뺄 구간 · 위험도 R2)에서 실증 분기만 지운 것."""
    res = JudgeResponse.model_validate_json(FIX.read_text(encoding="utf-8"))
    return res.sentences[0].model_copy(update={"substantiation": None})


def test_문안과_자료_종류는_승인본과_글자가_같다() -> None:
    doc = DOC.read_text(encoding="utf-8")
    approved = doc.split("## 13.", 1)[1]
    assert set(rs.SUBST_TEXT) == {"식품표시광고법", "화장품법", "표시광고법"}
    for law, t in rs.SUBST_TEXT.items():
        assert t.criteria in approved, f"{law} — 승인본 §13 과 글자가 다르다 (D-147)"
        assert "초안" not in t.criteria and "적법" not in t.criteria, f"{law} — D-130"
        for e in t.evidence:
            assert e in approved, f"{law} 자료 「{e}」 — 승인본에 없다"
            assert not any(w in e for w in ("특허", "수상", "인증", "기타", "그 밖에")), (
                f"{law} — 실증 자료가 아닌 것 · 넓은 칸이 섞였다 (D-228)"
            )
    # 🔄 2026-10-14 §13 개정 1 — 옛 끝 문장으로 되돌아가지 않는다. 승인본 대조는 「§13 뒤 어딘가에 있나」라 옛 글자가 문서에 남으면 못 잡는다
    ftc = rs.SUBST_TEXT["표시광고법"].criteria
    assert "내용의 실증 자료가 아닙니다" not in ftc, (
        "🔴 「인증을 받았다」 문장에서 증서를 받지 않는다고 읽힌다"
    )
    assert "그 사실이 맞아야" in ftc and "성능 · 효능이 실증되지는 않습니다" in ftc, (
        "🔴 두 갈래(거짓 사실 · 효능 차용) 중 하나가 빠졌다"
    )


def test_붙는_유형은_거짓과장뿐이고_상한은_R0이다() -> None:
    assert {Violation.거짓_과장: Risk.R0} == rs.SUBST_MAX
    sb = rs.subst_branch([Violation.거짓_과장], {"표시광고법"})
    assert sb is not None and sb.substantiated_max is Risk.R0
    assert sb.criteria == rs.SUBST_TEXT["표시광고법"].criteria
    # ⛔ 비방(D-304 · R1 이상) · 섞인 유형 · 법 축 둘 · 모르는 축 — 붙이지 않는다
    assert rs.subst_branch([Violation.비방광고], {"표시광고법"}) is None
    assert rs.subst_branch([Violation.거짓_과장, Violation.소비자_기만], {"표시광고법"}) is None
    assert rs.subst_branch([Violation.거짓_과장], {"표시광고법", "식품표시광고법"}) is None
    assert rs.subst_branch([Violation.거짓_과장], {"건강기능식품법"}) is None
    assert rs.subst_branch([], {"표시광고법"}) is None


def test_확정_B_거짓과장에_실증_분기가_붙고_지시의_재료가_선다() -> None:
    s = _confirmed_b()
    assert not g.guidance_ready([s]), "지우고 나면 지시 재료가 없어야 한다 — 시험의 전제"
    got = g._substantiated(s)
    assert got.substantiation is not None
    assert got.substantiation.criteria == rs.SUBST_TEXT["식품표시광고법"].criteria
    assert got.substantiation.substantiated_max is Risk.R0
    assert g.guidance_ready([got]), "🔴 실증 분기 · 뺄 구간이 있으면 지시가 선다 (D-268)"


def test_붙일_수_없으면_그대로다() -> None:
    s = _confirmed_b()
    # 위험도가 없다 — 실증 전 등급을 모르면 상한을 잴 수 없다 (계약 `_subst_is_for_B` · D-72)
    assert (
        g._substantiated(
            s.model_copy(update={"risk": s.risk.model_copy(update={"final": None, "floor": None})})
        ).substantiation
        is None
    )
    # 두 법이 섞인 인용
    ftc = EvidenceArticle(law_id="002011", article="제3조", item="제1항제1호", basis=True)
    assert (
        g._substantiated(s.model_copy(update={"evidence": [*s.evidence, ftc]})).substantiation
        is None
    )
    # 보류 문장
    held = s.model_copy(update={"verdict": g.Verdict.hold, "hold_reason": g.HoldReason.low_conf})
    assert g._substantiated(held).substantiation is None


def test_화장품_전제에서는_질병_표방과_건기식_오인_후보를_의약품_오인으로_옮긴다() -> None:
    """🆕 2026-10-14 (D-338) — 우리 라벨 규약에서 화장품의 질병 · 건강 기능 주장은 의약품 오인이다. 원래 유형을 적는다."""
    e = g.SentEncoding(
        sent_id="s0",
        scores=(("질병_예방치료_표방", 0.7), ("건강기능식품_오인", 0.6), ("거짓_과장", 0.5)),
        candidates=("질병_예방치료_표방", "건강기능식품_오인", "거짓_과장"),
    )

    def got(premises: tuple[Premise, ...]) -> list[tuple[str, float, str | None]]:
        return [
            (c.violation.value, c.confidence, c.moved_from.value if c.moved_from else None)
            for c in g._encoder_candidates(e, premises)
        ]

    assert got((Premise.화장품,)) == [
        ("거짓_과장", 0.5, None),
        ("의약품_오인", 0.7, "질병_예방치료_표방"),  # 같은 곳으로 옮겨 가면 확률이 높은 쪽 하나
    ]
    # 품목 미상 기록(합집합)에서는 옮기지 않는다 — 원래 후보가 식품 전제에서 선다
    assert ("의약품_오인", 0.7, "질병_예방치료_표방") not in got(g.pm.PREMISES_OF[None])
    assert got((Premise.식품,))[0] == ("질병_예방치료_표방", 0.7, None)
    # 인코더가 의약품 오인을 직접 냈으면 더하지 않는다
    direct = g.SentEncoding(
        sent_id="s0",
        scores=(("질병_예방치료_표방", 0.7), ("의약품_오인", 0.65)),
        candidates=("질병_예방치료_표방", "의약품_오인"),
    )
    assert [
        (c.violation.value, c.moved_from) for c in g._encoder_candidates(direct, (Premise.화장품,))
    ] == [("의약품_오인", None)]


def test_화장품에서_옮긴_후보는_화장품법_조항만_싣고_사전_경로는_그대로다() -> None:
    e = g.SentEncoding(
        sent_id="s0", scores=(("질병_예방치료_표방", 0.7),), candidates=("질병_예방치료_표방",)
    )
    laws = tuple(g.LAW_OF_NODE.values())  # 법을 셋 다 보낸 경우에도
    (c,) = g._encoder_candidates(e, (Premise.화장품,), laws)
    assert c.violation is Violation.의약품_오인 and c.references
    assert {a.law_id for a in c.references} <= {"002015", "008741"}, (
        "🔴 화장품이라면의 후보에 다른 법 조항이 붙었다"
    )
    assert rs.moved_note(c) and "화장품" in rs.moved_note(c)
    # 🔴 사전 경로의 거름표는 건강기능식품 전제 셋 그대로 — 화장품을 넣으면 화장품 분기에 식품 4.나 인용이 붙는다
    assert (
        frozenset({Premise.건기식_인정, Premise.건기식_비인정, Premise.일반식품_기능성})
        == g.pm.NO_HF_MISLEAD
    )


def test_옮긴_후보_아래_말은_갈래마다_다르다() -> None:
    hf = g.EncoderTypeCandidate(
        violation=Violation.거짓_과장, confidence=0.8, moved_from=Violation.건강기능식품_오인
    )
    assert "인정받지 않았다면" in rs.moved_note(hf)
    plain = g.EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.8)
    assert rs.moved_note(plain) is None
    assert json  # noqa: B018 — 모듈 머리의 import 를 남긴다(픽스처 읽기 도구)
