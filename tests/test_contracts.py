"""판정 계약 게이트 (D-124 ④).

🚨 **계약이 구현보다 먼저다.** 팀원 4인이 화면·BFF 를 붙이는 대상이 `app/contracts.py`
   하나이므로, 그것이 조용히 어긋나면 통합 시점에 전부 어긋난다.

무엇을 지키나
  ① 픽스처 9건이 계약으로 **파싱된다** — 화면이 보는 모양과 우리가 내는 모양이 같다
  ② 계약의 enum 이 **`db/schema.sql`·`app/models.py` 와 같다** (D-54 단일 출처)
  ③ 계약의 불변식이 **실패할 수 있다** (D-170) — 통과만 하는 검사는 검사가 아니다
  ④ 픽스처가 **분기를 덮는다** — 종착 넷·판정 상태 넷·불가 사유 셋
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from pydantic import ValidationError

from app.contracts import (
    Certificate,
    HoldReason,
    Infeasibility,
    JudgeResponse,
    Outcome,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Span,
    Verdict,
    Violation,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = sorted((ROOT / "tests" / "fixtures" / "judge").glob("*.json"))
SCHEMA = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
MODELS = (ROOT / "app" / "models.py").read_text(encoding="utf-8")


def _schema_enum(name: str) -> list[str]:
    m = re.search(rf"CREATE TYPE\s+{name}\s+AS ENUM\s*\((.*?)\);", SCHEMA, re.S)
    assert m, f"🚨 `db/schema.sql` 에 {name} 이 없다"
    return re.findall(r"'([^']+)'", m.group(1))


def _models_check(name: str) -> set[str]:
    """`app/models.py` 의 CHECK 에 적힌 허용값. 런타임층은 ORM 이 원본이다."""
    m = re.search(rf'"([^"]*in \([^)]*\))",\s*name="{name}"', MODELS)
    assert m, f"🚨 `app/models.py` 에 {name} 제약이 없다"
    return set(re.findall(r"'([^']+)'", m.group(1)))


# ── ① 픽스처가 계약으로 파싱된다 ──────────────────────────────────────


@pytest.mark.gate
def test_픽스처가_있다() -> None:
    """⛔ 픽스처가 사라지면 아래 검사들이 **전부 조용히 통과한다** (D-170)."""
    assert len(FIXTURES) >= 8, (
        f"🚨 골든 픽스처가 {len(FIXTURES)}건뿐이다 — D-124 ③ 은 6~8건을 요구한다.\n"
        "   화면·BFF 가 분기를 그리는 유일한 재료다."
    )


@pytest.mark.gate
@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_픽스처가_계약으로_파싱된다(path: pathlib.Path) -> None:
    """🚨 화면이 보는 모양과 우리가 내는 모양이 같아야 한다."""
    JudgeResponse.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.gate
def test_픽스처가_분기를_덮는다() -> None:
    """★ 종착 넷 · 판정 상태 넷 · 불가 사유 셋 (D-125 · D-127 · D-59).

    ⛔ 한 분기라도 픽스처가 없으면 팀원이 그 화면을 **못 그린다.** 그리고 못 그린 채로
       통합에 들어가면 그 분기는 발표 당일에 처음 그려진다.
    """
    seen = [JudgeResponse.model_validate_json(p.read_text(encoding="utf-8")) for p in FIXTURES]
    outcomes = {r.outcome for r in seen}
    verdicts = {s.verdict for r in seen for s in r.sentences}
    infeas = {s.infeasibility for r in seen for s in r.sentences if s.infeasibility}
    assert outcomes == set(Outcome), f"🚨 종착 미덮음 {sorted(set(Outcome) - outcomes)}"
    assert verdicts == set(Verdict), f"🚨 판정 상태 미덮음 {sorted(set(Verdict) - verdicts)}"
    assert infeas == set(Infeasibility), (
        f"🚨 불가 사유 미덮음 {sorted(set(Infeasibility) - infeas)}"
    )


# ── ② 계약의 enum 이 DB 와 같다 ───────────────────────────────────────


@pytest.mark.gate
def test_계약의_enum_이_DB_와_같다() -> None:
    """🔴 D-54 — 값의 단일 출처는 `db/schema.sql` 이다.

    ⛔ 계약에만 값을 늘리면 **계약은 받아 주고 DB 가 거부한다.** 적재 시점에 터지므로
       가장 늦게, 가장 비싸게 발견된다.
    """
    assert [v.value for v in Violation] == _schema_enum("violation_t")
    assert [v.value for v in Risk] == _schema_enum("risk_t")
    assert [v.value for v in Infeasibility] == _schema_enum("infeas_t")


@pytest.mark.gate
def test_계약의_판정축이_런타임층_제약과_같다() -> None:
    """런타임층은 `app/models.py` 가 원본이다 (거버넌스층과 출처가 다르다)."""
    assert {v.value for v in Verdict} == _models_check("ck_judgment_verdict")
    assert {v.value for v in HoldReason} == _models_check("ck_judgment_hold_reason_values")


# ── ③ 불변식이 실패할 수 있다 (D-170) ────────────────────────────────


@pytest.mark.gate
def test_하한_없이_위험도를_적으면_막힌다() -> None:
    """D-09 — 상향의 정의가 「하한보다 높다」인데 하한이 없으면 상향이 정의되지 않는다.

    ⛔ DB 에서는 이 구멍이 널로 우회되고 있었다 (마이그레이션 0006). 계약도 같이 막는다.
    """
    with pytest.raises(ValidationError):
        RiskAssessment(final=Risk.R4)


@pytest.mark.gate
def test_근거_스팬_없이_상향하면_막힌다() -> None:
    """D-131 — 인코더가 하한 위로 올릴 때 반드시 스팬이 붙는다."""
    with pytest.raises(ValidationError):
        RiskAssessment(floor=Risk.R1, encoder=Risk.R4, final=Risk.R4)
    # 스팬이 있으면 통과한다 — 막는 것이 조건이지 상향 자체가 아니다
    RiskAssessment(floor=Risk.R1, final=Risk.R4, evidence_span=Span(start=0, end=3))


@pytest.mark.gate
def test_보류와_사유는_함께_있거나_함께_없다() -> None:
    """`app/models.py` ck_judgment_hold_reason 과 같은 규칙 (D-127)."""
    with pytest.raises(ValidationError):
        SentenceJudgment(sent_id="s", text="t", verdict=Verdict.hold)
    with pytest.raises(ValidationError):
        SentenceJudgment(
            sent_id="s", text="t", verdict=Verdict.confirmed, hold_reason=HoldReason.rd1
        )


@pytest.mark.gate
def test_위반을_확정하면_근거_조문이_붙는다() -> None:
    """D-224 — 근거를 못 찾은 경우의 상태는 `no_basis` 이지 `confirmed` 가 아니다."""
    # 🔄 2026-09-23 — 불가 사유를 넣어 둔다. ⛔ 없으면 D-273 검증기(사유 필수)가 **같이** 터져
    #    이 게이트가 두 이유로 통과한다 — 한쪽 규칙이 죽어도 모른다 (D-170).
    with pytest.raises(ValidationError, match="D-224"):
        SentenceJudgment(
            sent_id="s",
            text="t",
            verdict=Verdict.confirmed,
            violations=[Violation.거짓_과장],
            infeasibility=Infeasibility.B,
        )


@pytest.mark.gate
def test_B_실증형에는_증명서를_내지_않는다() -> None:
    """🚨 D-59 가 금지한 「B 를 C 처럼 답하기」 — 그때는 `search_failed` 다 (D-125)."""
    with pytest.raises(ValidationError):
        JudgeResponse(
            outcome=Outcome.certificate,
            certificate=Certificate(reason=Infeasibility.B, explanation="x"),
        )


@pytest.mark.gate
def test_A_자격형에는_대체_문구를_내지_않는다() -> None:
    """D-59 — 표현이 아니라 자격의 문제라 재생성이 같은 위반을 반복한다.

    ⛔ 이 구분이 없어서 기획서 2-3 시나리오 A 가 자격 미충족 문구를 고쳐 놓고
       「재판정 통과」로 적었다.
    """
    # 🔄 2026-09-23 — 검수 픽스처에서 후보가 빠졌다(D-265 · `01_pass`). 후보는 여기서 만든다.
    fx = json.loads((ROOT / "tests/fixtures/judge/01_pass.json").read_text("utf-8"))
    fx["candidates"] = [
        {
            "label": "보수안",
            "rewrite": {"body": "x"},
            "residual_risk": "R0",
            "appeal_retention": 0.5,
        }
    ]
    JudgeResponse.model_validate(fx)  # 반대 대조 — A 가 없으면 지난다
    fx["sentences"][0]["infeasibility"] = "A"
    with pytest.raises(ValidationError, match="D-59"):
        JudgeResponse.model_validate(fx)


@pytest.mark.gate
def test_재생성_라운드는_셋을_넘지_않는다() -> None:
    """D-126 — 0-base, 총 라운드 K+1=3 이므로 0·1·2 만 (ck_judgment_attempt)."""
    with pytest.raises(ValidationError):
        JudgeResponse(outcome=Outcome.hold, attempt=3)


# ══════════════════════════════════════════════════════════════════════
#  진입점 B · C — 삼원 (D-119 · D-181)
# ══════════════════════════════════════════════════════════════════════
#
# 🔴 **2026-09-10 까지 계약이 진입점 A 만 덮고 있었다.** 화면은 SCR-GN 3 · SCR-AD 3 으로
#    이미 서 있는데 응답 모양이 없었다 — 「팀원 대기 해제」가 셋 중 하나만이었다.
# 🚨 아래 검사는 D-93 이 경계한 것(「위장 광고 생성 도구로 읽힌다」)을 **코드로** 만든다.

from app.contracts import (  # noqa: E402
    AdaptedCopy,
    AdFormat,
    AdSection,
    Candidate,
    Channel,
    ComposeRequest,
    ComposeResponse,
    GenerateRequest,
    GenerateResponse,
    KeywordScreen,
    RewriteSet,
    Segment,
)

FX_GENERATE = sorted((ROOT / "tests" / "fixtures" / "generate").glob("*.json"))
FX_COMPOSE = sorted((ROOT / "tests" / "fixtures" / "compose").glob("*.json"))


@pytest.mark.gate
@pytest.mark.parametrize("path", FX_GENERATE, ids=lambda p: p.stem)
def test_생성_픽스처가_계약으로_파싱된다(path: pathlib.Path) -> None:
    GenerateResponse.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.gate
@pytest.mark.parametrize("path", FX_COMPOSE, ids=lambda p: p.stem)
def test_광고생성_픽스처가_계약으로_파싱된다(path: pathlib.Path) -> None:
    ComposeResponse.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.gate
def test_세_진입점_모두_픽스처가_있다() -> None:
    """⛔ 하나라도 비면 팀원이 그 화면을 못 그린다 (D-181)."""
    assert FIXTURES and FX_GENERATE and FX_COMPOSE, (
        f"🚨 픽스처 — 판정 {len(FIXTURES)} · 생성 {len(FX_GENERATE)} · 광고생성 {len(FX_COMPOSE)}"
    )


@pytest.mark.gate
def test_대상고객은_K익명_20_을_지킨다() -> None:
    """DB `ck_segment_k_anon` 과 **같은 규칙**이다. 두 곳이 다르면 늦게 터진다."""
    Segment(segment_id="s", label="x", member_count=20)
    with pytest.raises(ValidationError):
        Segment(segment_id="s", label="x", member_count=19)


@pytest.mark.gate
def test_차단_키워드에는_사유가_붙는다() -> None:
    """화면: 「차단된 키워드를 누르면 사유를 볼 수 있어요」.

    ⛔ 사유 없는 차단은 「왜 안 되는지 모르는 회색」이다 — 그건 판정이 아니다.
    """
    with pytest.raises(ValidationError):
        KeywordScreen(term="주름 개선", allowed=False)
    KeywordScreen(term="주름 개선", allowed=False, reason="기능성 심사를 안 받은 제품")


@pytest.mark.gate
def test_차단된_키워드로_생성하지_않는다() -> None:
    seg = Segment(segment_id="s", label="x", member_count=100)
    blocked = KeywordScreen(term="최고", allowed=False, reason="절대적 표현")
    with pytest.raises(ValidationError):
        GenerateRequest(segment=seg, keywords=[blocked])


@pytest.mark.gate
def test_지배당하는_후보는_프론티어에_안_올라간다() -> None:
    """화면: 「파레토 최적 3안만 표시 — 지배당하는 후보는 자동 제외돼요」 (D-31)."""
    c = Candidate(
        label="x",
        rewrite=RewriteSet(body="본문"),
        residual_risk=Risk.R1,
        appeal_retention=0.5,
        pareto=False,
    )
    with pytest.raises(ValidationError):
        GenerateResponse(candidates=[c])


@pytest.mark.gate
def test_각색본은_표시문구_없이_못_나간다() -> None:
    """🚨 D-93 방어의 핵심 — 「광고」 표시 없는 출력 경로를 만들지 않는다."""
    ok = SentenceJudgment(sent_id="s", text="t", verdict=Verdict.confirmed)
    with pytest.raises(ValidationError):
        AdaptedCopy(
            channel=Channel.인스타,
            rewrite=RewriteSet(body="본문"),
            disclosure="",
            disclosure_placement="첫 줄",
            recheck=ok,
        )


@pytest.mark.gate
def test_C_는_두_경로_중_하나로만_들어온다() -> None:
    """B 의 각색본이거나 직접 입력이거나 — 둘 다이거나 둘 다 없으면 정해지지 않는다."""
    with pytest.raises(ValidationError):
        ComposeRequest(ad_format=AdFormat.배너)
    ComposeRequest(ad_format=AdFormat.배너, prompt="신제품")


@pytest.mark.gate
def test_광고표시_섹션이_없으면_거부한다() -> None:
    """🚨 구조적 강제 (D-93 · D-164). 번호만 적고 칸이 없어도 거부한다."""
    ok = SentenceJudgment(sent_id="s", text="t", verdict=Verdict.confirmed)
    S = [AdSection(order=0, kind="헤드라인", text="문구")]
    with pytest.raises(ValidationError):
        ComposeResponse(ad_format=AdFormat.배너, sections=S, screening=[ok])
    with pytest.raises(ValidationError):
        ComposeResponse(
            ad_format=AdFormat.배너, sections=S, screening=[ok], disclosure_section_order=9
        )


@pytest.mark.gate
def test_판정_안_지난_문구는_지면에_안_얹힌다() -> None:
    """D-63 — 재검증 대기 상태로는 템플릿에 사용되지 않는다."""
    pending = SentenceJudgment(sent_id="s", text="t", verdict=Verdict.unjudged)
    S = [AdSection(order=0, kind="표시문구", text="광고")]
    with pytest.raises(ValidationError):
        ComposeResponse(
            ad_format=AdFormat.배너, sections=S, screening=[pending], disclosure_section_order=0
        )
    # 자리만 잡아 두는 것은 된다 — 사용자가 채우기 전 상태다
    ComposeResponse(
        ad_format=AdFormat.배너,
        sections=[AdSection(order=0, kind="표시문구", placeholder="판정 통과 후")],
        screening=[pending],
        disclosure_section_order=0,
    )


@pytest.mark.gate
def test_매체_프로파일은_판정을_못_바꾼다() -> None:
    """🔴 D-93 표의 오른쪽 열 — **필드가 없는 것이 계약이다.**

    ⛔ 프로파일에 판정 기준·허용 어휘·근거 조문 필드가 생기면 그 순간 우회로가 열린다.
    """
    from app.contracts import MediaProfile

    forbidden = {"violations", "risk", "evidence", "verdict", "allowed_terms", "vocabulary"}
    assert not (set(MediaProfile.model_fields) & forbidden), (
        f"🚨 프로파일에 판정 축 필드가 생겼다 — {set(MediaProfile.model_fields) & forbidden}"
    )
    assert set(MediaProfile.model_fields) == {
        "channel",
        "max_chars",
        "max_sentences",
        "tone",
        "disclosure_placement",
    }


# 🆕 2026-09-21 (전수 재검토 I2) — 루프에 안 들어간 `pass` 는 문장이 전부 통과여야 한다 (D-125)
def test_통과_종착은_통과가_아닌_문장을_받지_않는다() -> None:
    import pytest as _pt

    # 🔄 2026-09-23 — 위반 없는 확정은 R0 뿐이라(D-273 불변식) 「확정 · R3」은 위반을 단 문장으로 만든다
    bad = SentenceJudgment(
        sent_id="s1",
        text="t",
        verdict=Verdict.confirmed,
        violations=[Violation.거짓_과장],
        infeasibility=Infeasibility.B,
        evidence=[_EV],
        risk=RiskAssessment(floor=Risk.R3, final=Risk.R3),
    )
    with _pt.raises(ValueError, match="통과가 아닌 문장"):
        JudgeResponse(outcome=Outcome.passed, sentences=[bad])
    # 🆕 D-273 — **확정 위반 · R1(시정명령 위험)** 도 통과가 아니다. ⛔ 종전 문턱(≤R1)에서는 이것이 통과로 지났다
    r1 = bad.model_copy(update={"risk": RiskAssessment(floor=Risk.R1, final=Risk.R1)})
    with _pt.raises(ValueError, match="통과가 아닌 문장"):
        JudgeResponse(outcome=Outcome.passed, sentences=[r1])
    un = SentenceJudgment(sent_id="s2", text="t", verdict=Verdict.unjudged)
    with _pt.raises(ValueError, match="통과가 아닌 문장"):
        JudgeResponse(outcome=Outcome.passed, sentences=[un])


def test_래칫은_하한_아래로_내려가지_않는다() -> None:
    """⛔ docstring 은 「인코더는 내릴 수 없다」인데 `floor=R3 · final=R0` 이 지났다."""
    import pytest as _pt

    with _pt.raises(ValueError, match="하한보다 낮다"):
        RiskAssessment(floor=Risk.R3, final=Risk.R0)


# ══════════════════════════════════════════════════════════════════════
#  🆕 2026-09-23 — W3 계약 (D-273 ~ D-278) · 새 검증기는 **거부되는 음성 예**와 짝으로 (D-170)
# ══════════════════════════════════════════════════════════════════════

from app.contracts import (  # noqa: E402
    PASS_RISK_MAX,
    Branch,
    Category,
    EvidenceArticle,
    GenerateOutcome,
    Premise,
    SubstBranch,
    is_pass,
)

_EV = EvidenceArticle(law_id="013094", article="제8조", item="제1항제4호")
_SUBST = SubstBranch(
    substantiated_max=Risk.R1, accepted_evidence=["시험 또는 조사 결과"], criteria="초안"
)


def _viol(
    sid: str = "s1",
    *,
    infeas: Infeasibility | None = Infeasibility.B,
    final: Risk = Risk.R2,
    **kw: object,
) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=sid,
        text="소비자 선호도 11년 연속 1위",
        verdict=Verdict.confirmed,
        violations=[Violation.거짓_과장],
        infeasibility=infeas,
        evidence=[_EV],
        risk=RiskAssessment(floor=final, final=final),
        **kw,
    )


def _clean(sid: str = "s1", *, final: Risk = Risk.R0, **kw: object) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=sid,
        text="t",
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=final, final=final),
        **kw,
    )


@pytest.mark.gate
def test_통과는_확정_그리고_R0_이다() -> None:
    """D-273 — 통과 = 확정 ∧ R0. ⛔ 종전 문턱 R1 은 시정명령 수준의 확정 위반을 통과로 흘렸다."""
    assert PASS_RISK_MAX is Risk.R0
    assert is_pass(_clean())
    assert not is_pass(_viol(final=Risk.R1))


@pytest.mark.gate
def test_확정_문장은_위반이_없으면_R0_있으면_R1_이상이다() -> None:
    """D-273 결정 2 — 불변식. DB `ck_judgment_confirmed_risk` 와 같은 규칙이다."""
    _clean()
    _viol(final=Risk.R1)
    with pytest.raises(ValidationError, match="위반이 없으면 R0"):
        _clean(final=Risk.R1)
    with pytest.raises(ValidationError, match="R1 이상"):
        _viol(final=Risk.R0)


@pytest.mark.gate
def test_확정_위반에는_불가_사유가_붙는다() -> None:
    """D-273 결정 3 — 사유가 비면 라우터가 증명서·지시로 못 보낸다. 사유를 못 정하면 보류다."""
    _viol(infeas=Infeasibility.C)
    with pytest.raises(ValidationError, match="불가 사유"):
        _viol(infeas=None)
    # 반대 대조 — 보류 문장은 사유가 없어도 된다
    SentenceJudgment(
        sent_id="s",
        text="t",
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        violations=[Violation.거짓_과장],
    )


@pytest.mark.gate
def test_판정_대상_아님은_위반도_구간도_없는_R0_확정이다() -> None:
    """D-275 — 「특이사항 없음」과 가르는 칸. 걸린 것이 있으면 판정 대상 아님이 아니다."""
    _clean(not_claim=True)
    with pytest.raises(ValidationError, match="D-275"):
        _clean(not_claim=True, spans=[Span(start=0, end=1)])
    with pytest.raises(ValidationError, match="D-275"):
        SentenceJudgment(
            sent_id="s",
            text="t",
            verdict=Verdict.hold,
            hold_reason=HoldReason.low_conf,
            not_claim=True,
        )


@pytest.mark.gate
def test_실증_분기는_B_에만_붙고_등급을_올리지_않는다() -> None:
    """D-263 ④ · D-61 — C 절대형은 선택지가 없다 · 실증은 내리기만 한다."""
    _viol(substantiation=_SUBST)
    with pytest.raises(ValidationError, match="B 실증형에만"):
        _viol(infeas=Infeasibility.C, substantiation=_SUBST)
    up = SubstBranch(substantiated_max=Risk.R3, accepted_evidence=["x"], criteria="x")
    with pytest.raises(ValidationError, match="올리지 않는다"):
        _viol(substantiation=up)


@pytest.mark.gate
def test_지시는_실증형_확정_위반에_구간과_실증_분기를_단다() -> None:
    """D-268 · D-278 — 지시는 뺄 구간 · 실증 자료 · 내려갈 등급을 준다. 없으면 빈 카드다."""
    ok = _viol(substantiation=_SUBST, spans=[Span(start=0, end=5, label="거짓_과장")])
    JudgeResponse(outcome=Outcome.guidance, sentences=[ok])
    with pytest.raises(ValidationError, match="실증 분기나 뺄 구간"):
        JudgeResponse(outcome=Outcome.guidance, sentences=[_viol()])
    with pytest.raises(ValidationError, match="증명서다"):
        JudgeResponse(outcome=Outcome.guidance, sentences=[ok, _viol("s2", infeas=Infeasibility.C)])
    hold = SentenceJudgment(
        sent_id="s2", text="t", verdict=Verdict.hold, hold_reason=HoldReason.low_conf
    )
    with pytest.raises(ValidationError, match="보류다"):
        JudgeResponse(outcome=Outcome.guidance, sentences=[ok, hold])


def _hold(reason: HoldReason, final: Risk = Risk.R2) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s1",
        text="t",
        verdict=Verdict.hold,
        hold_reason=reason,
        violations=[Violation.건강기능식품_오인],
        infeasibility=Infeasibility.A,
        risk=RiskAssessment(floor=final, final=final),
    )


def _branch(premise: Premise, s: SentenceJudgment, *, verified: bool = False) -> Branch:
    outcome = Outcome.passed if is_pass(s) else Outcome.hold
    return Branch(
        premise=premise, verified=verified, outcome=outcome, sentences=[s], criteria="초안"
    )


@pytest.mark.gate
def test_검증_안_된_분기는_기록을_낮추지_못한다() -> None:
    """D-263 ① · D-276 — 기록되는 판정은 가장 보수적인 경우다."""
    rec = _hold(HoldReason.premise_unknown)
    JudgeResponse(
        outcome=Outcome.hold, sentences=[rec], branches=[_branch(Premise.건기식_인정, _clean())]
    )
    low = _hold(HoldReason.premise_unknown, final=Risk.R1)
    high = _viol(infeas=Infeasibility.A, final=Risk.R2)
    with pytest.raises(ValidationError, match="가장 보수적"):
        JudgeResponse(
            outcome=Outcome.hold, sentences=[low], branches=[_branch(Premise.건기식_비인정, high)]
        )
    two = [
        _branch(Premise.건기식_인정, _clean(), verified=True),
        _branch(Premise.건기식_비인정, high, verified=True),
    ]
    with pytest.raises(ValidationError, match="검증된 분기"):
        JudgeResponse(outcome=Outcome.hold, sentences=[rec], branches=two)


@pytest.mark.gate
def test_전제를_몰라_보류하면_분기를_준다() -> None:
    """D-263 ② · D-229 ⑥ — 선택지 없이 「전제를 정하라」고 하지 않는다."""
    for r in (HoldReason.cat_unknown, HoldReason.premise_unknown):
        with pytest.raises(ValidationError, match="분기가 없다"):
            JudgeResponse(outcome=Outcome.hold, sentences=[_hold(r)])
    same = [_branch(Premise.식품, _clean()), _branch(Premise.식품, _clean())]
    with pytest.raises(ValidationError, match="겹친다"):
        JudgeResponse(
            outcome=Outcome.hold, sentences=[_hold(HoldReason.cat_unknown)], branches=same
        )


@pytest.mark.gate
def test_전용법_품목은_통과가_없고_미검수_고지가_붙는다() -> None:
    """D-271 ⑤ · D-277 — 안 본 법을 본 것처럼 말하지 않는다."""
    s = SentenceJudgment(
        sent_id="s1", text="t", verdict=Verdict.hold, hold_reason=HoldReason.law_uncovered
    )
    JudgeResponse(
        outcome=Outcome.hold,
        category=Category.전용법_미수록,
        not_reviewed=["의료기기법"],
        sentences=[s],
    )
    with pytest.raises(ValidationError, match="D-277"):
        JudgeResponse(outcome=Outcome.hold, category=Category.전용법_미수록, sentences=[s])
    with pytest.raises(ValidationError, match="통과"):
        JudgeResponse(
            outcome=Outcome.passed,
            category=Category.전용법_미수록,
            not_reviewed=["의료기기법"],
            sentences=[_clean()],
        )
    with pytest.raises(ValidationError, match="전용법 품목에서만"):
        JudgeResponse(outcome=Outcome.hold, category=Category.식품, sentences=[s])


@pytest.mark.gate
def test_생성_종착과_후보가_맞는다() -> None:
    """D-274 — 프론티어는 후보가 있을 때만 · 탐색 실패는 원문 유지 (후보 없음)."""
    GenerateResponse(outcome=GenerateOutcome.search_failed)
    with pytest.raises(ValidationError, match="D-274"):
        GenerateResponse(outcome=GenerateOutcome.frontier)


@pytest.mark.gate
def test_검수_종착에_탐색_실패가_없다() -> None:
    """D-274 — 검수는 재생성 루프를 돌지 않는다. 탐색 실패는 생성 종착의 것이다."""
    assert "search_failed" not in {o.value for o in Outcome}
    assert "search_failed" in {o.value for o in GenerateOutcome}


@pytest.mark.gate
@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_검수_픽스처에는_후보도_재생성도_없다(path: pathlib.Path) -> None:
    """D-265 — 검수는 대체 문구를 내지 않고 루프를 돌지 않는다. 근거 불일치는 재생성 이벤트라 검수에서 안 난다."""
    r = JudgeResponse.model_validate_json(path.read_text(encoding="utf-8"))
    assert r.candidates == [], "🔴 검수 픽스처에 후보가 있다 (D-265)"
    assert r.attempt == 0, "🔴 검수 픽스처의 라운드가 0 이 아니다 (D-265)"
    assert not any(s.evidence_mismatch for s in r.sentences), "🔴 검수에 근거 불일치 (D-127)"


@pytest.mark.gate
def test_0018_의_제약_글자가_모델과_같다() -> None:
    """🔴 D-99 — 런타임층 정본은 `app/models.py` 다. 마이그레이션 글자가 다르면 새 DB 와 옮긴 DB 가 갈린다."""
    import importlib.util  # noqa: PLC0415

    from app.models import Judgment  # noqa: PLC0415

    p = ROOT / "alembic" / "versions" / "20260923_0018_judgment_w3.py"
    spec = importlib.util.spec_from_file_location("m0018", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    model = {
        c.name: " ".join(str(c.sqltext).split()) for c in Judgment.__table__.constraints if c.name
    }
    for name, check, _ in m._CHECKS:
        assert name in model, f"🔴 모델에 {name} 이 없다"
        assert " ".join(check.split()) == model[name], f"🔴 {name} 글자가 모델과 다르다"
