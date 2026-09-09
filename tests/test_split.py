"""`preprocess.split` — 골든셋 분할 [P12] · 🚨 **출처 분리** (2026-09-09).

🚨 **거버넌스 게이트다.** 여기가 깨지면 F1 이 부풀려진 채로 발표까지 간다 —
   그리고 부풀려졌다는 것을 **아무도 모른다. 누수는 조용하다.**

무엇을 지키나
  ① 배정 값이 아는 이름인가 — 오타 하나로 문서가 통째로 사라진다
  ② 🔴 사전이 **평가 문구로** 만들어지지 않았는가 (분할이 사전보다 먼저다)
  ③ 평가에 **적법(음성) 표본**이 있는가 — 없으면 Precision 이 정의되지 않는다
  ④ 30 미만 유형이 `unmeasurable` 에 **적혀 있는가** (D-40)
  ⑤ 같은 기관 슬라이스가 `same_source` 로 **표시돼 있는가** — 감추지 않는다
  ⑥ 주입본이 평가에 섞이지 않았는가 ([P10] 규약 5)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from preprocess.dictionary import norm
from preprocess.split import MIN_MEASURABLE, plan

DICT = pathlib.Path("data/derived/banned_terms.jsonl")
GOLDEN = pathlib.Path("data/derived/golden/golden.jsonl")


@pytest.fixture(scope="module")
def m() -> dict:
    return plan()


@pytest.mark.gate
def test_배정값이_아는_이름이다(m: dict) -> None:
    """🚨 `assign` 이 dict 라 한 문서는 구조상 한 쪽에만 간다.

    그래서 여기서 볼 것은 「양쪽에 있나」가 아니라 **「아는 이름으로 갔나」**다 —
    오타 난 값 하나면 그 문서는 어느 집합에서도 안 세어지고 **조용히 사라진다.**
    """
    known = {"train", "test_sentence"}
    bad = {k: v for k, v in m["assign"].items() if v not in known}
    assert not bad, f"🚨 모르는 split 값 — {list(bad.items())[:5]}"


@pytest.mark.gate
def test_사전이_평가문구로_만들어지지_않았다() -> None:
    """🔴 **분할이 사전·주입보다 먼저다.**

    ⛔ 종전 순서(사전 → 주입 → 분할)에서는 사전이 **평가 문구로** 만들어졌다 —
       실측: 봉인된 평가 문구 118개 중 **118개**가 사전에 그대로 있었다.
       그 사전으로 매칭기를 재면 외운 것을 맞힌다. 지표가 아니라 착시다.
    ★ 순서를 지켰는지 묻지 않고 **산출물이 실제로 그 규칙을 지켰는지**를 본다.
    """
    if not (DICT.exists() and GOLDEN.exists()):
        pytest.skip("사전·골든셋이 아직 없다 — uv run python launcher.py golden --write")
    lines = [x for x in DICT.read_text(encoding="utf-8").splitlines() if x.strip()]
    terms = {json.loads(x)["term"] for x in lines}
    ev = [
        r
        for r in (
            json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()
        )
        if r["split"] == "test_sentence"
    ]
    leaked = [r for r in ev if r["labels"] and norm(r["text"]) in terms]
    assert not leaked, (
        f"🚨 평가 문구 {len(leaked)}개가 사전에 **그대로** 있다 — 매칭기가 외운 것을 맞힌다.\n"
        f"   예: {[r['text'][:30] for r in leaked[:3]]}\n"
        "   분할을 먼저 돌린 뒤 사전을 다시 만든다 (`launcher golden` 의 순서)."
    )


@pytest.mark.gate
def test_평가에_적법_표본이_있다(m: dict) -> None:
    """🔴 시험지가 전부 위반이면 **「전부 위반」이라 답해도 Recall 100%** 다.

    Precision 이 정의되려면 위반이 아닌 것이 있어야 한다. 종전 시험지에는 없었다.
    """
    assert m["negatives"]["test_sentence"] > 0, (
        "🚨 평가에 적법(음성) 표본이 0 이다 — 이 시험지로는 Precision 을 못 잰다"
    )


@pytest.mark.gate
def test_측정_불가를_숨기지_않는다(m: dict) -> None:
    """🚨 D-40 — 30 미만 유형은 지표를 내지 않고 **「측정 불가」로 적는다.**

    ⛔ 이 단언이 없으면 3건짜리 유형의 Recall 이 다른 지표와 나란히 표에 올라간다.
       「측정 불가」를 말할 수 있게 만드는 것은 슬라이드가 아니라 이 JSON 한 줄이다.
    """
    ev = m["counts"]["test_sentence"]
    un = set(m["unmeasurable"]["test_sentence"])
    short = {t for t, n in ev.items() if n < MIN_MEASURABLE}
    assert short <= un, f"🚨 30 미만인데 unmeasurable 에 없다 — {sorted(short - un)}"
    for t in un:
        assert ev.get(t, 0) < MIN_MEASURABLE, f"{t} 는 {ev.get(t)}건인데 측정 불가로 적혀 있다"


@pytest.mark.gate
def test_같은_기관_슬라이스를_표시한다(m: dict) -> None:
    """🚨 `ftc` 평가 슬라이스는 **학습과 같은 기관**이라 원천 편향을 못 잰다.

    감추면 「출처 분리 홀드아웃」이라는 말이 사실이 아니게 된다. 적으면 한계일 뿐이다.
    ★ 둘의 차이가 이 프로젝트의 정직성이고, 발표에서 가점이 되는 자리다 (기획문서 6-2).
    """
    ftc_in_eval = any(k.startswith("ftc:") and v == "test_sentence" for k, v in m["assign"].items())
    if ftc_in_eval:
        assert "ftc_decisions_body" in m["same_source"], (
            "🚨 ftc 를 평가에 넣고서 same_source 에 적지 않았다 — "
            "그러면 「출처 분리」라는 말이 사실이 아니게 된다"
        )


@pytest.mark.gate
def test_주입본이_평가에_섞이지_않는다(m: dict) -> None:
    """🔴 합성으로 평가하면 **「규칙을 배웠는가」**를 재게 된다 ([P10] 규약 5)."""
    assert m["source_sets"]["test_sentence"], "test_sentence 의 출처가 비어 있다"
    assert "주입본[P10]" not in m["source_sets"]["test_sentence"], (
        "🚨 주입본이 평가에 들어갔다 — 규칙이 곧 라벨인 합성 데이터로 평가하면 "
        "「규칙을 배웠는가」를 재게 된다"
    )
    if GOLDEN.exists():
        ev = [
            r
            for r in (
                json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()
            )
            if r["split"] == "test_sentence"
        ]
        inj = [r for r in ev if r.get("origin") == "injected"]
        assert not inj, f"🚨 주입본 {len(inj)}행이 평가에 들어 있다"
