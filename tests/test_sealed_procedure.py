"""봉인 회차 절차 — 두 모드를 한 실행에 · 작업 트리가 커밋 하나일 때만 · 기록 위험도 칸 (🆕 2026-10-20 · D-339 결정 7 · D-306 · D-348 보충 31).

지키는 것
  ① 봉인 회차(`--sealed`)는 무조건부 · 조건부를 **한 실행에** 잰다 — `--conditional` 을 붙이면 멈춘다(한쪽만 재고 다음 날 다시 여는 길을 막는다)
  ② 작업 트리 상태 — git 을 못 부르면 「미확인」(깨끗함으로 치지 않는다) · 깨끗하지 않으면 봉인을 열지 않는다(판정 그래프 · 판정기 B 같은 검사)
  ③ 모드별 행 — 조건부는 품목 · 전제를 아는 행만 · `--limit` 은 그 뒤에 자른다
  ④ 결과 행의 `risk_max` — 기록 문장들의 최종 위험도 최댓값 · 없으면 None
"""

from __future__ import annotations

import pathlib

import pytest

from app.contracts import HoldReason, Risk, RiskAssessment, SentenceJudgment, Verdict, Violation
from scripts import eval_graph as eg
from scripts import sealed_log

pytestmark = pytest.mark.gate


def test_봉인_회차는_조건부만_따로_열지_않는다() -> None:
    with pytest.raises(SystemExit, match="한 실행에"):
        eg.main(["--sealed", "--conditional", "--stub"])


def test_git_이_아닌_곳은_작업_트리_미확인이고_봉인을_막는다(tmp_path: pathlib.Path) -> None:
    assert sealed_log.worktree_state(tmp_path) == sealed_log.WORKTREE_UNKNOWN
    why = sealed_log.worktree_refusal(tmp_path)
    assert why and "커밋 하나" in why


def test_깨끗하면_막지_않고_변경이_있으면_막는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sealed_log, "worktree_state", lambda root=None: sealed_log.WORKTREE_CLEAN)
    assert sealed_log.worktree_refusal() is None
    monkeypatch.setattr(sealed_log, "worktree_state", lambda root=None: "커밋 안 된 변경 2 파일")
    assert "2 파일" in (sealed_log.worktree_refusal() or "")


def test_모드별_행은_조건부를_거른_뒤_자른다() -> None:
    rows = [
        {"id": "a", "품목": "식품", "전제": "식품"},
        {"id": "b", "품목": None, "전제": None},
        {"id": "c", "품목": "화장품", "전제": "화장품"},
    ]
    assert [r["id"] for r in eg._mode_rows(rows, False, None)] == ["a", "b", "c"]
    assert [r["id"] for r in eg._mode_rows(rows, True, None)] == ["a", "c"]
    assert [r["id"] for r in eg._mode_rows(rows, True, 1)] == ["a"]


def _s(sid: str, risk: RiskAssessment) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id=sid,
        text="지은 문장",
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        violations=[Violation.거짓_과장],
        risk=risk,
    )


def test_결과_행의_risk_max_는_기록_위험도의_최댓값() -> None:
    st = {
        "sentences": [
            _s("s0", RiskAssessment(floor=Risk.R1, final=Risk.R1)),
            _s("s1", RiskAssessment(floor=Risk.R2, final=Risk.R2)),
        ]
    }
    assert eg.predict(st)["risk_max"] == Risk.R2.value
    assert eg.predict({"sentences": [_s("s0", RiskAssessment())]})["risk_max"] is None
