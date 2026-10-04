"""응답시간 측정 도구(`scripts/time_graph.py`) — 🆕 2026-10-02 (D-77 L3).

🔴 무엇을 막나
   ① 평균이나 엉뚱한 분위수를 내는 것 — 가장 가까운 순위(nearest-rank)로 p50 · p95 · p99
   ② 표본이 없을 때 0 을 내는 것 — 멈춘다 (D-220)
   ③ 같은 씨앗에 다른 원고가 나오는 것 — 기기끼리 견줄 수 없다 (D-149)
   ④ 법별 노드 셋이 따로 흩어져 「검색보다 법 노드가 싸다」를 못 읽는 것
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace as NS

import pytest

from scripts import time_graph as tg


@pytest.mark.gate
def test_분위수는_가장_가까운_순위다() -> None:
    xs = [float(i) for i in range(1, 101)]
    assert (tg.pct(xs, 50), tg.pct(xs, 95), tg.pct(xs, 99)) == (50.0, 95.0, 99.0)
    assert tg.pct([7.0], 95) == 7.0
    assert tg.pct([3.0, 1.0, 2.0], 50) == 2.0
    with pytest.raises(ValueError, match="표본이 없다"):
        tg.pct([], 95)


@pytest.mark.gate
def test_원고는_씨앗이_같으면_같고_문장_수만큼이다() -> None:
    sents = [f"문장{i}" for i in range(50)]
    a = tg.make_docs(sents, 5, 4)
    assert a == tg.make_docs(sents, 5, 4), "같은 씨앗이면 같은 원고"
    assert all(len(d.split("\n")) == 5 for d in a) and len(a) == 4
    assert tg.make_docs(sents, 10, 4) != a


@pytest.mark.gate
def test_법별_노드는_하나로_합치고_요약은_노드마다_분위수를_낸다() -> None:
    t = [NS(node="retrieve", ms=30.0), NS(node="law_ftc", ms=1.0), NS(node="law_food", ms=2.0)]
    assert tg.node_ms(t) == {"retrieve": 30.0, "law_*": 3.0}

    class Fake:
        def invoke(self, state, config):  # noqa: ANN001, ANN201
            n = len(state["text"].split("\n"))
            return {"sents": ["x"] * n, "timings": [NS(node="retrieve", ms=10.0 * n)]}

    rows = tg.measure(Fake(), {}, ["a\nb", "a\nb\nc"], product=None)
    assert [r["sents"] for r in rows] == [2, 3]
    s = tg.summarize(rows)
    assert s["n"] == 2 and s["sents"] == [2, 3]
    assert s["nodes"]["retrieve"] == {50: 20.0, 95: 30.0}
    assert set(s["total"]) == {50, 95, 99}


@pytest.mark.gate
def test_골든이_없거나_학습_문장이_없으면_멈춘다(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit, match="가 없다"):
        tg.train_sentences(tmp_path / "none.jsonl")
    p = tmp_path / "g.jsonl"
    p.write_text('{"split": "test_sentence", "unit": "문장", "text": "x"}\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="학습 쪽 문장이 없다"):
        tg.train_sentences(p)
    p.write_text(
        '{"split": "train", "unit": "문장", "text": "가"}\n{"split": "test_sentence", "unit": "문장", "text": "나"}\n',
        encoding="utf-8",
    )
    assert tg.train_sentences(p) == ["가"], "봉인 평가 행은 읽지 않는다 (D-175)"


@pytest.mark.gate
def test_검색_분해는_같은_함수를_감싸_재고_되돌린다() -> None:
    """🆕 2026-10-02 — 검색 코드를 베끼지 않는다(D-99). 감싼 함수는 예외가 나도 되돌린다 · 이름이 없으면 멈춘다(D-220)."""
    calls: list[str] = []

    def mk(name: str):  # noqa: ANN202
        def fn(*a, **k):  # noqa: ANN002, ANN003, ANN202
            calls.append(name)
            return "m" if name == "stored_model_id" else []

        return fn

    rtmod = NS(**{n: mk(n) for n in tg.SEARCH_PARTS})

    def wide(cur, text):  # noqa: ANN001, ANN202
        rtmod.stored_model_id(cur)
        rtmod.check_inputs(cur)
        rtmod.encode("m", text)
        rtmod.by_vector(cur, text)
        rtmod.by_lexical(cur, text)

    rtmod.wide = wide
    before = {n: getattr(rtmod, n) for n in tg.SEARCH_PARTS}
    got = tg.search_parts(rtmod, None, "문장")
    assert set(got) == {
        "모델 판 조회",
        "입력판 검사",
        "임베딩(한 문장)",
        "벡터 질의",
        "어휘 갈래",
        "검색 한 번",
    }
    assert all(v >= 0 for v in got.values())
    assert calls == list(tg.SEARCH_PARTS)
    assert {n: getattr(rtmod, n) for n in tg.SEARCH_PARTS} == before, "감싼 함수를 되돌린다"

    def boom(cur, text):  # noqa: ANN001, ANN202
        raise RuntimeError("x")

    rtmod.wide = boom
    with pytest.raises(RuntimeError):
        tg.search_parts(rtmod, None, "문장")
    assert {n: getattr(rtmod, n) for n in tg.SEARCH_PARTS} == before, "예외가 나도 되돌린다"
    del rtmod.encode
    with pytest.raises(SystemExit, match="이름이 바뀌었다"):
        tg.search_parts(rtmod, None, "문장")


@pytest.mark.gate
def test_묶음_임베딩은_올라온_모델로만_잰다() -> None:
    seen: list[int] = []
    model = NS(encode=lambda xs: seen.append(len(xs)))
    rtmod = NS(_model_cache={"m": model}, stored_model_id=lambda cur: "m")
    out = tg.batch_encode_ms(rtmod, None, [f"s{i}" for i in range(100)], size=20, rounds=3)
    assert len(out) == 3 and seen == [20, 20, 20]
    with pytest.raises(SystemExit, match="올라와 있지 않다"):
        tg.batch_encode_ms(NS(_model_cache={}, stored_model_id=lambda cur: "m"), None, ["a"])
