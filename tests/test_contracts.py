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
    with pytest.raises(ValidationError):
        SentenceJudgment(
            sent_id="s", text="t", verdict=Verdict.confirmed, violations=[Violation.거짓_과장]
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
    fx = json.loads((ROOT / "tests/fixtures/judge/01_pass_frontier.json").read_text("utf-8"))
    fx["sentences"][0]["infeasibility"] = "A"
    with pytest.raises(ValidationError):
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
