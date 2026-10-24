"""하한 가드 · 확정 관문 (🆕 2026-10-24 · D-348 보충 41 결정 2 · 3).

지키는 것
  ① 하한 가드는 지금 주장 가드보다 넓다 — 관형형 끝 · 동작 · 상태 명사 끝을 연다 · 주의 · 상담 · 거부 가드 · 빈 글자는 언제나 막는다
  ② 목록(생성물)이 없으면 하한 가드 = 지금 주장 가드 — 넓히지 않는다 (결정 3 · D-220)
  ③ 넓힌 하한이 붙어도 **답 없는 확정 · 품목 선택 필요는 서지 않는다** — 관문 `_absolute_types` 는 지금 주장 가드를 본다 (결정 2 ②)
  ④ 목록의 정의 — 낱말 머리의 한글 2 ~ 4 자 + 「하 · 되 · 시키 …」가 `MIN_COUNT` 회 이상 (`preprocess/claim_nouns.py`)
"""

from __future__ import annotations

import pytest

from app import claimscope
from app import graph as g
from app.contracts import (
    ENCODER_RECORD_MAX,
    EncoderTypeCandidate,
    HoldReason,
    Premise,
    Risk,
    SentenceJudgment,
    Verdict,
    Violation,
)
from preprocess import claim_nouns as cn
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

WORDS = frozenset({"예방", "차단", "설계", "강화"})


@pytest.fixture
def nouns(monkeypatch: pytest.MonkeyPatch) -> frozenset[str]:
    monkeypatch.setattr(claimscope, "claim_nouns", lambda: WORDS)
    return WORDS


@pytest.fixture
def no_nouns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claimscope, "claim_nouns", lambda: None)


# ── ① ② 글자 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "욕창 예방",
        "전자파 차단",
        "소아과 전문의 영양설계",
        "피부 장벽 강화.",
        "바이러스 등이 없는",
        "유해물질 발생이 적은",
    ],
)
def test_지금_가드가_막는_명사구_주장을_하한_가드는_연다(nouns: frozenset[str], text: str) -> None:
    assert not claimscope.claim_guard(text), "전제 — 지금 가드는 막는다"
    assert claimscope.floor_guard(text)


@pytest.mark.parametrize(
    "text",
    [
        "쫀쫀한 거품으로 세안하는 모닝글로우 클렌징폼.",  # 제품 묘사 명사 끝
        "별첨 9 참조",
        "홍삼 농축액",
        "임산부는 섭취에 주의하십시오",  # 주의 · 상담
        "수험생을 위한",  # 거부 가드 · 대상
        "정가 39,000원 할인 예방",  # 거부 가드 · 가격(동작 명사 끝이어도)
        "",
    ],
)
def test_하한_가드도_막는_꼴(nouns: frozenset[str], text: str) -> None:
    assert not claimscope.floor_guard(text)


@pytest.mark.parametrize(
    "text", ["피로 회복에 탁월한 효과가 있습니다.", "국내 판매 1위 홍삼", "면역력 쑥쑥!"]
)
def test_지금_가드가_여는_문장은_하한_가드도_연다(no_nouns: None, text: str) -> None:
    assert claimscope.claim_guard(text) and claimscope.floor_guard(text)


@pytest.mark.parametrize("text", ["욕창 예방", "바이러스 등이 없는", "소아과 전문의 영양설계"])
def test_목록이_없으면_넓히지_않는다(no_nouns: None, text: str) -> None:
    assert not claimscope.floor_guard(text), "🔴 목록이 없는데 넓혔다 (보충 41 결정 3 · D-220)"


def test_끝_문장부호_괄호_따옴표는_떼고_마지막_한글_덩어리의_끝을_본다() -> None:
    assert claimscope.noun_end("“욕창 예방”", WORDS)
    assert claimscope.noun_end("전자파 차단!!", WORDS)
    assert claimscope.noun_end("소아과 전문의 영양설계", WORDS)
    assert not claimscope.noun_end("예방 효과", WORDS)
    assert not claimscope.noun_end("ZERO", WORDS)


def test_목록_파일이_없으면_None(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    claimscope.claim_nouns.cache_clear()
    monkeypatch.setattr(claimscope, "CLAIM_NOUNS", tmp_path / "없음.jsonl")
    try:
        assert claimscope.claim_nouns() is None
        assert claimscope.nouns_stamp() is None
    finally:
        claimscope.claim_nouns.cache_clear()


# ── ③ 그래프 — 하한은 열고 답 없는 확정은 막는다 ─────────────────────────


def _rows() -> list[dict]:
    spec = sr.load_rules()
    assert sr.signature(spec) is not None, "원천이 서명 전이다 — 이 게이트의 전제가 깨진다"
    return sr.rule_rows(spec)


def _held(text: str, v: Violation) -> SentenceJudgment:
    c = EncoderTypeCandidate(violation=v, confidence=0.9)
    c = c.model_copy(
        update={
            "references": g._candidate_refs(
                c, tuple(g.LAW_OF_NODE[n] for n in ("law_ftc", "law_food")), {}
            )
        }
    )
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=[c],
    )


def test_명사구_주장에_하한이_서고_질병_치료_신호가_없으면_답_없는_확정은_서지_않는다(
    nouns: frozenset[str],
) -> None:
    # 🔄 2026-10-25 (D-348 보충 44 결정 1) 관문 = 지금 가드 ∨ (하한 가드 ∧ 질병 · 치료 신호) · 신호 없는 명사구는 종전대로 막힌다
    text = "피부 장벽 강화"
    s = g._with_encoder_risk(_held(text, Violation.질병_예방치료_표방), Premise.식품, _rows())
    assert s.risk.encoder is Risk.R1, "하한 가드가 열었다"
    assert s.risk.encoder.level <= ENCODER_RECORD_MAX.level
    assert (s.verdict, s.hold_reason) == (Verdict.hold, HoldReason.low_conf), "판정은 그대로다"
    assert not claimscope.disease_signal(text)
    assert g._absolute_types(s) == set(), (
        "🔴 질병 · 치료 신호 없는 명사구로 답 없는 확정 관문이 열렸다 (보충 44 결정 1 · 보충 41 결정 2 ②)"
    )


def test_질병_치료_신호가_있는_명사구는_확정_관문을_연다(nouns: frozenset[str]) -> None:
    """🆕 2026-10-25 (D-348 보충 44 결정 1 (라)) — 「욕창 예방」(예방) · 「당뇨 걱정 없는」(질병명) · 시행령 [별표 1] 1.가 는 내용 기준이다."""
    for text in ("욕창 예방", "당뇨 걱정 없는"):
        assert not claimscope.claim_guard(text) and claimscope.confirm_gate(text), text
        s = g._with_encoder_risk(_held(text, Violation.질병_예방치료_표방), Premise.식품, _rows())
        assert Violation.질병_예방치료_표방 in g._absolute_types(s), text
    assert not claimscope.confirm_gate("모발강화"), (
        "질병 · 치료 신호 없는 화장품 낱말(원장 10-25(B) ① 의 적법 오탐)"
    )


def test_질병명_목록은_사전_빌드와_한_곳이다() -> None:
    from preprocess import dictionary  # noqa: PLC0415

    assert dictionary.DISEASE_NAMES is claimscope.DISEASE_NAMES, (
        "🔴 질병명 목록이 두 벌이다 (D-99 · 보충 44 결정 1)"
    )


def test_지금_가드를_지나는_같은_주장은_관문이_종전대로다(nouns: frozenset[str]) -> None:
    text = "욕창을 예방합니다."
    s = g._with_encoder_risk(_held(text, Violation.질병_예방치료_표방), Premise.식품, _rows())
    assert claimscope.claim_guard(text) and s.risk.encoder is Risk.R1
    assert Violation.질병_예방치료_표방 in g._absolute_types(s), (
        "기준 — 질병 표방은 C · 지금 가드를 지난다"
    )


def test_목록이_없으면_하한도_종전대로_막힌다(no_nouns: None) -> None:
    s = _held("욕창 예방", Violation.질병_예방치료_표방)
    assert g._with_encoder_risk(s, Premise.식품, _rows()) is s


def test_하한_자리만_하한_가드를_쓰고_확정_자리는_지금_가드다(nouns: frozenset[str]) -> None:
    assert g.encoder_floor_cap("욕창 예방") is ENCODER_RECORD_MAX
    assert g.encoder_cap("욕창 예방") is None, (
        "🔴 전제가 답인 확정 경로의 가드가 넓어졌다 (결정 2 ②)"
    )


# ── ④ 목록의 정의 ──────────────────────────────────────────────────────


def test_목록은_낱말_머리의_명사와_하다_되다의_꼴을_센다() -> None:
    got = cn.nouns(
        ["질병을 예방하고 예방한다", "자외선 차단되어", "차단시키는", "예방함"], min_count=2
    )
    assert got == {"예방": 3, "차단": 2}
    assert "예방" not in cn.count(["질병예방하고"]), (
        "낱말 머리에서만 센다 — 「질병예방」 안의 「예방」은 세지 않는다"
    )


def test_목록에는_dev_와_봉인_행이_들지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"id": "a#1", "text": "학습", "split": "train"},
        {"id": "b#1", "text": "dev", "split": "train"},
        {"id": "c#1", "text": "봉인", "split": "test_sentence"},
    ]
    monkeypatch.setattr(cn.devsplit, "dev_ids", lambda rs: ["b#1"])
    monkeypatch.setattr(cn.rsp, "plan", lambda rs: {"c#1": cn.rsp.SEALED})
    assert cn.design_golden(rows) == ["학습"]
