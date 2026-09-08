"""`preprocess.stage` — 두 판을 맞댈 때 **차이의 원인을 가른다** (D-143 · 2026-09-08).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 하나다 — **원천이 늘어난 날 규칙이 좋아진 것처럼 보이면 안 된다.**
원천은 살아 있다(식약처 게시판 650 → 655 · `ftc` 는 2026년 건이 계속 들어온다).
증감을 뭉뚱그리면 지표가 거짓말을 한다.
"""

from __future__ import annotations

from preprocess.stage import compare


def _row(seq: str, phrases: list[str], rule: str = "r1") -> dict:
    return {"seq": seq, "문구": phrases, "rule": rule}


def test_new_documents_are_source_not_rule() -> None:
    """🚨 문서가 들어와 늘어난 것은 **원천 탓**이다 — 규칙 탓으로 세면 안 된다."""
    old = {"1": _row("1", ["가", "나"])}
    new = {"1": _row("1", ["가", "나"]), "2": _row("2", ["다"])}
    c = compare(old, new)
    assert c["문구_원천탓"] == 1
    assert c["문구_규칙탓"] == 0
    assert c["문서_추가"] == 1


def test_rule_change_is_rule_not_source() -> None:
    """같은 문서에서 늘어난 것만 **규칙 탓**이다 — 오늘의 619 → 627 이 이 종류다."""
    old = {"1": _row("1", ["가"])}
    new = {"1": _row("1", ["가", "나"], rule="r2")}
    c = compare(old, new)
    assert c["문구_규칙탓"] == 1
    assert c["문구_원천탓"] == 0
    assert c["문서_내용바뀜"] == 1
    assert c["규칙판_지난"] == ["r1"] and c["규칙판_이번"] == ["r2"]


def test_both_causes_are_separated() -> None:
    """둘이 동시에 일어나도 갈린다. **합만 보면 규칙 효과가 원천 증가에 묻힌다.**"""
    old = {"1": _row("1", ["가"]), "9": _row("9", ["묵은것"])}
    new = {"1": _row("1", [], rule="r2"), "2": _row("2", ["새", "것"], rule="r2")}
    c = compare(old, new)
    assert c["문구_지난판"] == 2 and c["문구_이번판"] == 2  # 합은 그대로다 — 여기에 속는다
    assert c["문구_규칙탓"] == -1  # 문서 1 에서 규칙이 하나 먹었다
    assert c["문구_원천탓"] == 1  # 문서 9 가 빠지고 2 가 들어왔다


def test_detects_mixed_rule_versions() -> None:
    """🚨 **판이 섞이면 잡는다.** 규칙을 고친 뒤 일부만 재생성된 코퍼스는 겉으로 멀쩡하다."""
    mixed = {"1": _row("1", ["가"], rule="r1"), "2": _row("2", ["나"], rule="r2")}
    assert compare({}, mixed)["🚨판섞임"] is True
    assert compare({}, {"1": _row("1", ["가"])})["🚨판섞임"] is False


def test_text_change_is_visible_even_when_output_is_same() -> None:
    """🚨 **산출물이 같아도 본문은 바뀔 수 있다.**

    2026-09-08 에 조사 먹힘을 고쳤더니 `주문_마스킹` 이 63곳 바뀌었는데
    `문구` 는 그대로여서 「내용바뀜 0」으로 보고됐다.
    산출물만 보면 **마스킹 규칙 변경이 통째로 안 보인다.**
    """
    old = {"1": {"seq": "1", "문구": ["가"], "주문_마스킹": "석정건설[업체] 위탁", "rule": "r1"}}
    new = {"1": {"seq": "1", "문구": ["가"], "주문_마스킹": "[업체]에게 위탁", "rule": "r2"}}
    c = compare(old, new)
    assert c["문서_내용바뀜"] == 0  # 산출물은 같다
    assert c["문서_본문바뀜"] == 1  # 🚨 그래도 본문은 바뀌었다
