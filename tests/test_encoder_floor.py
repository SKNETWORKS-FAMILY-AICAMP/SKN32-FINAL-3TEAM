"""인코더 하한 — 사전 하한과 **칸을 갈라** 보류 문장의 위험도를 채운다 (🆕 2026-10-16 · D-348 결정 3 ~ 5 · 보충 2).

지키는 것
  ① 칸이 다르다 — 사전 하한은 `risk.floor`, 인코더 하한은 `risk.encoder` · 최종 = max (보충 2 결정 1)
  ② 근거는 대응표의 호(후보의 참조 조항) — 호가 없으면 적지 않는다 (결정 2)
  ③ 보류 문장에만 · 판정(확정 · 보류) · 보류 사유 · 유형 · 종착은 바뀌지 않는다 (결정 3)
  ④ 분기마다 계산하고 기록 = 전제 최댓값 — 분기를 내지 않는 경로에서도 (결정 4) · 응답이 계약(기록 ≥ 분기)을 지난다
  ⑤ 기록에 들이는 높이는 신뢰 층(R1) · 주장 가드를 지난 문장만 (결정 5 · 보충 1 결정 1 · 3)
  ⑥ 모르면 비운다 — R1 층은 하한(R1 이상)을 아는 후보가 하나도 없으면 · 표가 비면 · DB 가 없으면 (D-220) · R0 하한은 모름 (D-273)
     R2 이상 층의 계산(`encoder_floor`)은 후보 하나라도 모르면 모른다 (보충 2 결정 4 개정)
"""

from __future__ import annotations

import pytest

from app import claimscope
from app import graph as g
from app import premise as pm
from app.contracts import (
    ENCODER_RECORD_MAX,
    Category,
    EncoderTypeCandidate,
    HoldReason,
    Outcome,
    Premise,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Verdict,
    Violation,
)
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

CLAIM = "피로 회복에 탁월한 효과가 있습니다."


def _rows() -> list[dict]:
    spec = sr.load_rules()
    assert sr.signature(spec) is not None, "원천이 서명 전이다 — 이 게이트의 전제가 깨진다"
    return sr.rule_rows(spec)


class _Cur:
    """`v_risk_lookup` 대역 — `tests/test_premise_branches.py` 의 것과 같은 모양이다."""

    def __init__(self) -> None:
        self.rows = _rows()

    def execute(self, sql: str, params: object = None) -> None:
        assert "v_risk_lookup" in sql

    def fetchall(self) -> list[tuple]:
        return [
            (r["id"], r["law_id"], r["type"], r["kind"], r.get("annex1"), r.get("cover"), r["quote"], r.get("fact"))
            for r in self.rows
        ]  # fmt: skip


def _cand(v: Violation, refs: bool = True) -> EncoderTypeCandidate:
    c = EncoderTypeCandidate(violation=v, confidence=0.9)
    if refs:
        c = c.model_copy(
            update={
                "references": g._candidate_refs(
                    c, tuple(g.LAW_OF_NODE[n] for n in ("law_ftc", "law_food")), {}
                )
            }
        )
    return c


def _held(text: str = CLAIM, *cands: EncoderTypeCandidate) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        encoder_candidates=list(cands) or [_cand(Violation.거짓_과장)],
    )


# ── ① ② ⑤ ⑥ 문장 하나 ──────────────────────────────────────────────────


def test_인코더만_잡은_보류_문장에_인코더_하한이_따로_선다() -> None:
    s = g._with_encoder_risk(_held(), Premise.식품, _rows())
    assert (s.verdict, s.hold_reason) == (Verdict.hold, HoldReason.low_conf), "판정은 그대로다"
    assert s.risk.floor is None, (
        "🔴 사전 하한 칸에 인코더 값을 섞었다 (보충 2 결정 1 · D-313 결정 3)"
    )
    assert s.risk.encoder is Risk.R1 and s.risk.final is Risk.R1
    assert s.risk.encoder.level <= ENCODER_RECORD_MAX.level


def test_근거_호가_없으면_적지_않고_계약도_막는다() -> None:
    bare = _held(CLAIM, _cand(Violation.거짓_과장, refs=False))
    assert g._with_encoder_risk(bare, Premise.식품, _rows()) is bare
    with pytest.raises(ValueError, match="근거 호"):
        SentenceJudgment(
            **{**bare.model_dump(), "risk": RiskAssessment(encoder=Risk.R1, final=Risk.R1)}
        )


@pytest.mark.parametrize(
    "text",
    [
        "임산부는 섭취에 주의하십시오.",  # 주의 · 상담
        "수험생을 위한",  # 거부 가드 · 대상
        "정가 39,000원",  # 거부 가드 · 가격
        "홍삼 농축액",  # 명사구 · 표지 없음
        "",
    ],
)
def test_주장_가드를_지나지_않으면_기록에_들이지_않는다(text: str) -> None:
    assert not claimscope.claim_guard(text)
    s = _held(text or "가")
    if text:
        assert g._with_encoder_risk(s, Premise.식품, _rows()) is s


def test_주장_가드를_지나는_꼴() -> None:
    assert claimscope.claim_guard(CLAIM)
    assert claimscope.claim_guard("국내 판매 1위 홍삼")  # 명사구여도 광고 표지
    assert g.encoder_cap(CLAIM) is ENCODER_RECORD_MAX


def test_R1_층은_하한을_아는_후보_하나면_선다() -> None:
    """보충 2 결정 4 개정 — 「위반이라면 적어도 R1」(D-273)은 유형이 틀려도 참이다. 모르는 후보가 섞여도 R1 은 선다."""
    rows = _rows()
    # 화장품 전제에 질병 표방 조항이 없다 — 그 후보는 모른다(원장 10-14(B) ③)
    assert g.estimate_of(rows, Premise.화장품, Violation.질병_예방치료_표방).floor is None
    s = _held(CLAIM, _cand(Violation.거짓_과장), _cand(Violation.질병_예방치료_표방))
    got = g._with_encoder_risk(s, Premise.화장품, rows)
    assert got.risk.encoder is Risk.R1 and got.risk.floor is None
    # R2 이상 층의 계산(`encoder_floor`)은 종전대로 — 하나라도 모르면 모른다
    assert g.encoder_floor(rows, Premise.화장품, s.encoder_candidates).floor is None


def test_아는_후보가_없으면_비운다() -> None:
    rows = _rows()
    only = _held(CLAIM, _cand(Violation.질병_예방치료_표방))
    assert g._with_encoder_risk(only, Premise.화장품, rows) is only
    assert g.encoder_floor(rows, Premise.식품, []).floor is None, (
        "후보가 없으면 R0 이 아니라 모른다"
    )
    assert g._with_encoder_risk(_held(), Premise.식품, []) == _held(), "표가 비면 모른다"


def test_R0_하한은_모름이다(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-273 — 위반이라면 R1 이상. 제재표가 R0 을 내면 그것은 그 결정을 바꾸는 일이다 — 보류 문장에 R0 을 적지 않는다(D-280)."""
    from app.contracts import RiskEstimate  # noqa: PLC0415

    monkeypatch.setattr(g, "estimate_of", lambda rows, p, v: RiskEstimate(floor=Risk.R0))
    s = _held()
    assert g._with_encoder_risk(s, Premise.식품, _rows()) is s
    assert g.encoder_floor(_rows(), Premise.식품, s.encoder_candidates).floor is None


@pytest.mark.parametrize(
    "s",
    [
        SentenceJudgment(
            sent_id="s0",
            text=CLAIM,
            verdict=Verdict.confirmed,
            not_claim=True,
            risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
            encoder_candidates=[_cand(Violation.거짓_과장)],
        ),
    ],
)
def test_보류가_아니면_적지_않는다(s: SentenceJudgment) -> None:
    assert g._with_encoder_risk(s, Premise.식품, _rows()) is s


def test_사전_하한이_있는_보류는_사전_칸을_지키고_최종은_큰_값() -> None:
    s = _held().model_copy(update={"risk": RiskAssessment(floor=Risk.R2, final=Risk.R2)})
    got = g._with_encoder_risk(s, Premise.식품, _rows())
    assert (got.risk.floor, got.risk.encoder, got.risk.final) == (Risk.R2, Risk.R1, Risk.R2)


# ── ③ ④ 그래프 — 분기마다 · 기록 = 최댓값 · 응답 계약 ─────────────────────────


@pytest.fixture
def criteria(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "CRITERIA", {p: f"(시험) {p.value} 기준" for p in Premise})


def _run(
    category: Category | None, cands: tuple[str, ...] = ("거짓_과장",), text: str = CLAIM
) -> dict:
    laws = g.laws_for(category)
    st: dict = {
        "text": text,
        "sents": [text],
        "product": ProductContext(category=category),
        "laws": laws,
        "dict_scans": [g.DictScan(sent_id="s0", ran=True)],
        "law_results": [g.LawResult(law=law, sent_ids=("s0",)) for law in laws],
        "encodings": [
            g.SentEncoding(sent_id="s0", scores=tuple((c, 0.9) for c in cands), candidates=cands)
        ],
    }
    cfg = {"configurable": {"conn": _Cur()}}
    st["sentences"] = g.judge(st)["sentences"]
    st["sentences"] = g.upsert_sentences(
        st["sentences"], g.assess_risk(st, cfg).get("sentences", [])
    )
    out = g.premise_branches(st, cfg)
    st["sentences"] = g.upsert_sentences(st["sentences"], out.get("sentences", []))
    st["branches"] = out.get("branches", [])
    return st


@pytest.mark.parametrize("category", [None, Category.식품, Category.건기식, Category.화장품])
def test_분기마다_계산하고_기록은_전제_최댓값이다(
    criteria: None, category: Category | None
) -> None:
    st = _run(category)
    (rec,) = st["sentences"]
    assert rec.verdict is Verdict.hold, "🔴 인코더 하한이 판정을 바꿨다 (보충 2 결정 3)"
    assert rec.risk.floor is None and rec.risk.encoder is Risk.R1 and rec.risk.final is Risk.R1
    finals = [b.sentences[0].risk.encoder for b in st["branches"] if b.sentences[0].risk.encoder]
    assert all(f.level <= rec.risk.final.level for f in finals), "기록 < 분기"
    resp = g.to_response({**st, "outcome": Outcome.hold})  # 계약(기록 ≥ 분기 · 근거 호)을 지난다
    assert resp.sentences[0].risk.encoder is Risk.R1


def test_분기를_내지_않는_경로에서도_기록에_붙는다(criteria: None) -> None:
    st = _run(Category.식품)
    assert not st["branches"], "전제 둘의 판정이 같으면 분기를 내지 않는다(종전 그대로)"
    assert st["sentences"][0].risk.encoder is Risk.R1


def test_주장_가드에_걸리면_기록도_분기도_비고_판정은_그대로(criteria: None) -> None:
    st = _run(None, text="수험생을 위한")
    (rec,) = st["sentences"]
    assert rec.risk.encoder is None and rec.risk.final is None
    assert all(b.sentences[0].risk.encoder is None for b in st["branches"])
    assert rec.verdict is Verdict.hold


def test_DB_가_없으면_적지_않는다(criteria: None) -> None:
    st = {
        "text": CLAIM,
        "sents": [CLAIM],
        "product": ProductContext(category=Category.화장품),
        "laws": g.laws_for(Category.화장품),
        "sentences": [_held()],
        "encodings": [
            g.SentEncoding(sent_id="s0", scores=(("거짓_과장", 0.9),), candidates=("거짓_과장",))
        ],
    }
    assert not g.assess_risk(st, {}).get("sentences")


# ── 평가 도구 · 화면 ─────────────────────────────────────────────────────


def test_평가_도구는_인코더_하한을_조건별로_세고_적법_분모는_적법_행_전체다() -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    rows = [{"조건": c} for c in ("A", "B", "D", "D", "L", "M")]
    preds = [{"encoded": True, "enc_risk": x} for x in (True, False, True, False, False, True)]
    rep = eg.encoder_risk_report(rows, preds)
    assert rep["violation"] == [1, 2] and rep["lawful"] == [1, 3] and rep["ambiguous"] == [1, 1]
    assert rep["lawful_upper"] == pytest.approx(eg.wilson(1, 3)[1])
    none = eg.encoder_risk_report([{"조건": "A"}], [{"encoded": True, "enc_risk": True}])
    assert none["lawful"] == [0, 0] and none["lawful_upper"] is None, (
        "적법이 없으면 잰 것 없음 (D-220)"
    )
    p = eg.predict(
        {
            "sentences": [g._with_encoder_risk(_held(), Premise.식품, _rows())],
            "outcome": Outcome.hold,
        }
    )
    assert p["enc_risk"] is True


def test_화면은_인코더_하한을_AI_추정으로_사전_하한과_따로_그린다(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    import json  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415

    raw = json.loads(
        (api.FIXTURE_ROOT / "judge" / "02_hold_low_conf.json").read_text(encoding="utf-8")
    )
    s = g._with_encoder_risk(_held(), Premise.식품, _rows())
    raw["sentences"] = [json.loads(s.model_dump_json())]
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "enc_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)
    html = TestClient(api.app).get("/u/preview/enc_case").text
    assert "AI 추정 · 낮은 위험" in html, "인코더 하한에서 온 등급이 사전 등급처럼 그려졌다"
    assert "사전 하한" in html and "인코더 하한 (AI 추정 · 판정 아님)" in html
