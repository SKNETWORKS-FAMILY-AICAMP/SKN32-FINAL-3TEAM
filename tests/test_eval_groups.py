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


# ── 🆕 2026-09-25 · 구조적 0 (사실원장 09-25 ⑰ · D-188) ──────────────────────────────────


def test_사전에_항목이_없는_칸은_구조적_0_으로_찍는다() -> None:
    """🔴 「시도하고 틀린 0」과 「잴 수 없는 0」을 같은 0.000 으로 찍으면 표가 거짓말을 한다."""
    from collect import statute

    have = er.covered({"당뇨": "질병_예방치료_표방"}, {"당뇨": [statute.food(1)]})
    assert have == {"질병_예방치료_표방", statute.food(1)}
    assert "구조적" in er._mark(151, 0, statute.food(6), have)
    assert "구조적" in er._mark(68, 0, "부당_비교광고", have)
    assert er._mark(70, 3, statute.food(1), have) == ""  # 항목이 있으면 0 이어도 성능이다
    assert "정답 0" in er._mark(0, 2, statute.food(6), have), "오탐 경고가 먼저다"
    assert "D-40" in er._mark(9, 0, statute.food(1), have), "항목이 있으면 D-40 은 그대로"


def test_보고서가_구조적_0_을_실제로_내보낸다(tmp_path, monkeypatch, capsys) -> None:
    """값이 입구(사전)부터 출구(표)까지 흐르는지 — `covered` 만 있고 표가 안 읽으면 소용없다."""
    import json

    from collect import statute

    d = tmp_path / "banned_terms.jsonl"
    term = {
        "term": "당뇨",
        "유형": ["질병_예방치료_표방"],
        "짝": [["질병_예방치료_표방", statute.food(1)]],
        "단독판정": True,
    }
    d.write_text(json.dumps(term, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(er, "DICT", d)
    rows = [
        {"text": "당뇨 개선", "labels": ["질병_예방치료_표방"], "근거": [statute.food(1)]},
        {"text": "국내 최고", "labels": ["비방광고"], "근거": [statute.food(6)]},
    ]
    er.report(rows, er.load_rules())
    out = capsys.readouterr().out
    line6 = next(x for x in out.splitlines() if statute.food(6) in x)
    line1 = next(x for x in out.splitlines() if statute.food(1) in x)
    assert "구조적" in line6 and "구조적" not in line1
