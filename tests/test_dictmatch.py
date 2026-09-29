"""`app/dictmatch.py` — 사전 매칭의 한 곳 (🆕 2026-09-28 · W4 · D-99).

★ 판정 그래프(`match_dict`)와 판정기 B(`scripts/eval_rule.py`)와 사전 빌더(`preprocess/dictionary.py`)가 **같은** 정규화 · 매칭을 쓰는지 본다.
"""

from __future__ import annotations

import pytest

from app import dictmatch as dm

pytestmark = pytest.mark.gate


@pytest.mark.parametrize(
    "text",
    ["이 제품은  암 예방에 좋습니다", "ＡＢＣ 면역력\t강화", "  ", "①② 조항", "가　나"],
)
def test_좌표판_정규화가_통째_정규화와_같다(text: str) -> None:
    n, where = dm.norm_with_map(text)
    assert n == dm.norm(text)
    assert len(where) == len(n)


def test_공백을_건너_울리고_원문_좌표를_낸다() -> None:
    text = "이 제품은 암 예방에 좋습니다"
    (m,) = dm.find(text, [dm.Entry(term="암예방")])
    assert text[m.span[0] : m.span[1]] == "암 예방"


def test_전각_글자도_울린다() -> None:
    assert dm.terms_in("ＳＰＦ１００ 차단", ["SPF100"]) == {"SPF100"}


def test_안_걸리면_빈_목록이다() -> None:
    assert dm.find("평범한 문장", [dm.Entry(term="암예방")]) == []


def test_세_곳이_같은_정규화를_쓴다() -> None:
    """🔴 D-99 — 사전 빌더 · 판정기 B 가 `app/dictmatch.norm` 을 쓴다. 사본이 다시 생기면 빨갛다."""
    from preprocess import dictionary

    assert dictionary.norm is dm.norm


def test_판정기_B_는_같은_적중을_낸다() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_rule

    rules = {"암예방": "질병_예방치료_표방", "면역력": "거짓_과장"}
    assert eval_rule.judge("이 제품은 암 예방에 좋습니다", rules) == {"질병_예방치료_표방"}
    assert eval_rule.judge("평범", rules) == set()
