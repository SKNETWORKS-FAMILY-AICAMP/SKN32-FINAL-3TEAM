"""건강기능식품 두 전제의 인코더 쪽 판정 (🆕 2026-10-18 · D-348 보충 23 결정 4 · D-348 결정 1).

지키는 것
  ① 인코더(건기식 입력)가 건강기능식품 오인 후보를 낸 문장 — `건기식_비인정` 은 옮긴 근거(4.나)로 확정 위반 · 사유 A · 실증 분기 없음
  ② `건기식_인정` 은 묻는다(`인정_기능성`) — 예 → R0 · 아니오 → 거짓 · 과장 확정(4.가 2) · 사유 A) · 해당없음 → 보류 + 출처 · 확인 전 위험도가 있다
  ③ 손대지 않는다 — 후보가 없다 · 주장이 아니다 · 구간을 모른다 · 확신 부족 보류가 아니다 · 비인정에 옮기지 않은 근거가 섞였다 · 인정에 다른 근거가 섰다
  ④ 문안은 정본 §16 과 글자가 같고, 질병 분기(`_enc_disease` · 보충 22 결정 3 으로 걷음)는 켜지지 않는다 — 문안 표(`FACT_TEXTS`) 밖에 둔다
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from app import factcheck as fc
from app import graph as g
from app import premise as pm
from app.contracts import (
    Answer,
    EncoderBasis,
    EvidenceArticle,
    FactKind,
    HoldReason,
    Infeasibility,
    Premise,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Span,
    UserFact,
    Verdict,
    Violation,
)

pytestmark = pytest.mark.gate

TEXT = "혈당을 확 낮춰 줍니다"
SPAN = Span(start=0, end=len(TEXT), label=Violation.거짓_과장.value)
HF = g.SentEncoding(
    sent_id="s0", scores=(("건강기능식품_오인", 0.8),), candidates=("건강기능식품_오인",)
)
NONE = g.SentEncoding(sent_id="s0", scores=(("건강기능식품_오인", 0.2),), candidates=())


@pytest.fixture(autouse=True)
def _floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """제재표 없이 — 「위반이라면」의 하한을 R1 로 둔다(시험용)."""
    monkeypatch.setattr(g, "estimate_of", lambda rows, premise, v: SimpleNamespace(floor=Risk.R1))


def _held(basis: list[EncoderBasis] | None = None, text: str = TEXT) -> SentenceJudgment:
    b = basis or []
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(encoder=Risk.R1, final=Risk.R1, encoder_basis=b)
        if b
        else RiskAssessment(),
    )


def _moved() -> list[EncoderBasis]:
    ref = EvidenceArticle(law_id="013094", article="제8조제1항제4호")
    return [
        EncoderBasis(
            premise=Premise.건기식_비인정,
            violation=Violation.거짓_과장,
            moved_from=Violation.건강기능식품_오인,
            floor=Risk.R1,
            articles=[ref],
        )
    ]


def test_비인정은_옮긴_근거로_확정_위반_사유_A() -> None:
    got = g._hf_premise(Premise.건기식_비인정, _held(_moved()), HF, [], SPAN, [])
    assert got.verdict is Verdict.confirmed and got.violations == [Violation.거짓_과장]
    assert got.infeasibility is Infeasibility.A and got.substantiation is None
    assert got.evidence and got.spans


def test_비인정에_옮기지_않은_근거가_섞이면_그대로() -> None:
    mixed = _moved() + [
        EncoderBasis(
            premise=Premise.건기식_비인정,
            violation=Violation.소비자_기만,
            floor=Risk.R1,
            articles=[EvidenceArticle(law_id="013094", article="제8조제1항제5호")],
        )
    ]
    j = _held(mixed)
    assert g._hf_premise(Premise.건기식_비인정, j, HF, [], SPAN, []) is j


def test_인정은_묻고_확인_전_위험도가_있다() -> None:
    got = g._hf_premise(Premise.건기식_인정, _held(), HF, [], SPAN, [])
    assert got.verdict is Verdict.hold and got.fact_check is not None
    assert got.fact_check.kind is FactKind.인정_기능성 and got.fact_check.confirmed_max is Risk.R0
    assert got.fact_check.criteria == fc.RECOGNIZED_TEXT.criteria
    assert got.risk.final is Risk.R1
    (b,) = got.risk.encoder_basis
    assert b.premise is Premise.건기식_인정 and b.moved_from is Violation.건강기능식품_오인
    got_arts = {f"{a.article}{a.item or ''}" for a in b.articles}
    assert any("가목" in x for x in got_arts) and any("나목" in x for x in got_arts), (
        "4.가 · 4.나 의 조항을 싣는다(보충 24 결정 2)"
    )


@pytest.mark.parametrize(
    ("answer", "verdict", "violations"),
    [
        (Answer.예, Verdict.confirmed, []),
        (Answer.아니오, Verdict.confirmed, [Violation.거짓_과장]),
        (Answer.해당없음, Verdict.hold, []),
    ],
)
def test_인정의_답(answer: Answer, verdict: Verdict, violations: list[Violation]) -> None:
    uf = UserFact(text=TEXT, kind=FactKind.인정_기능성, answer=answer)
    got = g._hf_premise(Premise.건기식_인정, _held(), HF, [uf], SPAN, [])
    assert got.verdict is verdict
    if verdict is Verdict.confirmed:
        assert list(got.violations) == violations
    assert got.user_facts == [uf] and got.fact_check is None
    if answer is Answer.예:
        assert got.risk.final is Risk.R0
    if answer is Answer.아니오:
        assert got.infeasibility is Infeasibility.A


@pytest.mark.parametrize("text", ["관절 건강을 치료해 줍니다", "먹고 나서 다 나았어요"])
def test_인정은_치료_꼴에는_묻지_않는다(text: str) -> None:
    j = _held(text=text)
    assert g._hf_premise(Premise.건기식_인정, j, HF, [], SPAN, []) is j


def test_인정은_질병_후보가_걸린_문장에는_묻지_않는다() -> None:
    j = _held(text="노안개선, 백내장예방").model_copy(
        update={"violations": [Violation.질병_예방치료_표방]}
    )
    assert g._hf_premise(Premise.건기식_인정, j, HF, [], SPAN, []) is j, (
        "「예」가 질병 주장을 R0 으로 풀면 안 된다"
    )


def test_인정에_다른_근거가_섰으면_그대로() -> None:
    j = _held(
        [
            EncoderBasis(
                premise=Premise.건기식_인정,
                violation=Violation.소비자_기만,
                floor=Risk.R1,
                articles=[EvidenceArticle(law_id="013094", article="제8조제1항제5호")],
            )
        ]
    )
    assert g._hf_premise(Premise.건기식_인정, j, HF, [], SPAN, []) is j


@pytest.mark.parametrize("premise", [Premise.건기식_인정, Premise.건기식_비인정])
def test_손대지_않는_문장(premise: Premise) -> None:
    j = _held(_moved() if premise is Premise.건기식_비인정 else None)
    assert g._hf_premise(premise, j, NONE, [], SPAN, []) is j, "후보가 없다"
    assert g._hf_premise(premise, j, HF, [], None, []) is j, "구간을 모른다"
    nc = j.model_copy(update={"not_claim": True})
    assert g._hf_premise(premise, nc, HF, [], SPAN, []) is nc, "판정 대상 아님"
    price = _held(_moved() if premise is Premise.건기식_비인정 else None, text="정가 29,000원")
    assert g._hf_premise(premise, price, HF, [], SPAN, []) is price, "주장이 아니다(거부 가드)"
    assert g._hf_premise(Premise.식품, j, HF, [], SPAN, []) is j, "건강기능식품 전제만"


def test_문안은_정본과_같고_질병_분기는_켜지지_않는다() -> None:
    doc = pathlib.Path("docs/ohb/기준문안_초안_2026-10-02.md").read_text(encoding="utf-8")
    sec = doc[doc.index("## 16.") :]
    assert f"질문: {fc.RECOGNIZED_QUESTION}" in sec
    assert f"기준: {fc.RECOGNIZED_TEXT.criteria}" in sec
    assert f"증빙: {fc.RECOGNIZED_TEXT.accepted_evidence[0]}" in sec
    assert fc.fact_question(FactKind.인정_기능성) == fc.RECOGNIZED_QUESTION
    assert FactKind.인정_기능성 not in fc.FACT_TEXTS, (
        "넣으면 걷은 질병 분기(`_enc_disease`)가 다시 켜진다"
    )
    assert pm.RECOGNIZED_DIFF_CITE.endswith("가목")


def test_비인정_확정은_전제_확신_문턱_아래면_보류(monkeypatch: pytest.MonkeyPatch) -> None:
    """🆕 2026-10-19 (D-348 보충 29) — 건강기능식품 오인 점수 0.8 이 문턱 아래면 확정하지 않는다 · 위면 종전대로."""
    monkeypatch.setattr(g, "_premise_tau", lambda v: 0.85)
    held = _held(_moved())
    assert g._hf_premise(Premise.건기식_비인정, held, HF, [], SPAN, []) is held
    monkeypatch.setattr(g, "_premise_tau", lambda v: 0.75)
    got = g._hf_premise(Premise.건기식_비인정, _held(_moved()), HF, [], SPAN, [])
    assert got.verdict is Verdict.confirmed
