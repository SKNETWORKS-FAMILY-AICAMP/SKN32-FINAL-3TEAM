"""`preprocess.split` — 골든셋 분할 [P12] · 🚨 **출처 분리** (2026-09-09).

🚨 **거버넌스 게이트다.** 여기가 깨지면 F1 이 부풀려진 채로 발표까지 간다 —
   그리고 부풀려졌다는 것을 **아무도 모른다.** 누수는 조용하다.

무엇을 지키나
  ① 같은 문서가 train 과 test_holdout 에 **동시에** 있지 않는다 ([P12] 규칙 1)
  ② 평가셋은 **조문 라벨 원천**으로만 만든다 — 사람도 모델도 붙이지 않는다
  ③ 30 미만 유형은 `unmeasurable` 에 **적혀 있다** (D-40)
  ④ 같은 기관 슬라이스는 `same_source` 로 **표시돼 있다** — 감추지 않는다
"""

from __future__ import annotations

import pytest

from preprocess.split import MIN_MEASURABLE, plan


@pytest.fixture(scope="module")
def m() -> dict:
    return plan()


@pytest.mark.gate
def test_같은_문서가_양쪽에_있지_않는다(m: dict) -> None:
    """🔴 **누수는 조용하다.** 같은 의결서의 문구가 train 과 test 에 섞이면 F1 이 오른다.

    무작위 분할이 아니라 `seq`(의결서 번호) 단위로 가르는 이유가 이것이다 —
    한 의결서 안의 문구들은 표현·업종·시기가 닮아서, 하나를 보면 나머지를 맞춘다.
    """
    both = set(m["sealed_doc_ids"]) & set(m["train_doc_ids"])
    assert not both, (
        f"🚨 {len(both)}개 문서가 train 과 test_holdout 에 동시에 있다: {sorted(both)[:5]}"
    )


@pytest.mark.gate
def test_분할이_전량을_덮는다(m: dict) -> None:
    """양성 대조 — 조용히 빠진 문서가 없어야 한다. 빠지면 어느 쪽에서도 안 세어진다."""
    assert len(m["sealed_doc_ids"]) + len(m["train_doc_ids"]) == len(
        set(m["sealed_doc_ids"]) | set(m["train_doc_ids"])
    )


@pytest.mark.gate
def test_측정_불가를_숨기지_않는다(m: dict) -> None:
    """🚨 D-40 — 30 미만 유형은 지표를 내지 않고 **「측정 불가」로 적는다.**

    ⛔ 이 단언이 없으면 3건짜리 유형의 Recall 이 다른 지표와 나란히 표에 올라간다.
       「측정 불가」를 말할 수 있게 만드는 것은 슬라이드가 아니라 이 JSON 한 줄이다.
    """
    ev = m["counts"]["test_holdout"]
    short = {t for t, n in ev.items() if n < MIN_MEASURABLE}
    assert short <= set(m["unmeasurable"]), (
        f"🚨 30 미만인데 unmeasurable 에 없다 — {sorted(short - set(m['unmeasurable']))}"
    )
    for t in m["unmeasurable"]:
        assert ev.get(t, 0) < MIN_MEASURABLE, f"{t} 는 {ev.get(t)}건인데 측정 불가로 적혀 있다"


@pytest.mark.gate
def test_같은_기관_슬라이스를_표시한다(m: dict) -> None:
    """🚨 `ftc` 평가 슬라이스는 **학습과 같은 기관**이라 원천 편향을 못 잰다.

    감추면 「출처 분리 홀드아웃」이라는 말이 사실이 아니게 된다. 적으면 한계일 뿐이다.
    ★ 둘의 차이가 이 프로젝트의 정직성이고, 발표에서 가점이 되는 자리다 (기획문서 6-2).
    """
    ftc_in_eval = any(d.startswith("ftc:") for d in m["sealed_doc_ids"])
    if ftc_in_eval:
        assert "ftc_decisions_body" in m["same_source"], (
            "🚨 ftc 를 평가에 넣고서 same_source 에 적지 않았다 — "
            "그러면 「출처 분리」라는 말이 사실이 아니게 된다"
        )


@pytest.mark.gate
def test_평가셋에는_학습전용_원천이_섞이지_않는다(m: dict) -> None:
    """🔴 평가셋의 출처는 **선언돼 있어야** 한다 — 나중에 「어디서 왔더라」가 되면 늦는다."""
    assert m["source_sets"]["test_holdout"], "test_holdout 의 출처가 비어 있다"
    assert "주입본[P10]" not in m["source_sets"]["test_holdout"], (
        "🚨 주입본이 평가에 들어갔다 — 규칙이 곧 라벨인 합성 데이터로 평가하면 "
        "「규칙을 배웠는가」를 재게 된다 ([P10] 규약 5)"
    )
