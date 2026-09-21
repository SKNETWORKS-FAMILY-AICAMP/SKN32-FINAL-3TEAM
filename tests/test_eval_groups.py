"""보고용 묶음 지표 (D-255 · `scripts/eval_rule.py`).

팀장 — 후기_체험기_기만을 소비자_기만에 **합치지 않고**, 평가 보고에서만 5호 묶음으로 함께 잰다.
🚨 여기서 막는 것 — ① 묶음이 라벨을 합쳐 버리는 것(유형별 표가 사라짐) ② 묶음 밖 유형이 묶음 점수에 섞이는 것
"""

from __future__ import annotations

import pytest

from scripts import eval_rule as er

pytestmark = pytest.mark.gate

S, H, F = "소비자_기만", "후기_체험기_기만", "거짓_과장"


def test_묶음_안에서_유형을_바꿔_골라도_적중이다() -> None:
    pairs = [({S}, {H}), ({H}, {H}), (set(), {S}), ({S}, set())]
    ((g, tp, fp, fn),) = er.group_scores(pairs).values()
    assert (g, tp, fp, fn) == (3, 2, 1, 1)


def test_묶음_밖_유형은_세지_않는다() -> None:
    pairs = [({F}, {F}), ({F}, set())]
    ((g, tp, fp, fn),) = er.group_scores(pairs).values()
    assert (g, tp, fp, fn) == (0, 0, 0, 0)


def test_묶음은_5호_두_유형이고_라벨_목록은_그대로다() -> None:
    from scripts.collect import VIOLATION_TYPES

    assert set(er.REPORT_GROUPS["5호 묶음(소비자_기만∪후기)"]) == {S, H}
    assert S in VIOLATION_TYPES and H in VIOLATION_TYPES, "🔴 묶음이 라벨을 합치면 안 된다 (D-231)"
