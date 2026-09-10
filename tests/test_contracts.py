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
    """D-100 — 근거를 못 찾은 경우의 상태는 `no_basis` 이지 `confirmed` 가 아니다."""
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
