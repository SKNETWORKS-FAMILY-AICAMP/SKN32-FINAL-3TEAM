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


@pytest.mark.parametrize(
    ("text", "span_text"),
    [
        ("중요한 약속 전날 밤에", None),  # 「편안한 약속」 류 — 증명서 오탐의 자리 (D-334)
        ("진귀한 약재 침향", None),
        ("키 약 하나로 쑥쑥", "키 약"),  # 낱말 첫 글자에서 시작 — 그대로 울린다
        ("(키 약) 광고", "키 약"),  # 낱말 앞 문장부호는 첫머리로 본다
        ("중요한 약속 그리고 한약 성분", "한약"),  # 걸린 자리를 건너 다음 자리를 본다
        ("고급한약재", "한약"),  # 공백을 건너지 않으면 그대로다
    ],
)
def test_짧은_항목은_낱말_가운데서_공백을_건너_울리지_않는다(
    text: str, span_text: str | None
) -> None:
    """🔴 D-334 — 두 글자 이하 항목이 낱말 가운데서 시작해 공백을 건너면 적중이 아니다. 판정기 B 도 같다 (D-99)."""
    entries = [dm.Entry(term="한약"), dm.Entry(term="키약")]
    got = [text[m.span[0] : m.span[1]] for m in dm.find(text, entries)]
    assert got == ([] if span_text is None else [span_text])
    assert dm.terms_in(text, ["한약", "키약"]) == (
        set() if span_text is None else {dm.norm(span_text)}
    )


def test_세_글자_이상은_낱말_가운데서_공백을_건너도_울린다() -> None:
    """D-334 의 길이 조건 — 「전립선암 예방」의 「암 예방」은 낱말 가운데서 시작해도 질병 표방이다."""
    text = "골다공증, 전립선암 예방"
    (m,) = dm.find(text, [dm.Entry(term="암예방")])
    assert text[m.span[0] : m.span[1]] == "암 예방"


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
