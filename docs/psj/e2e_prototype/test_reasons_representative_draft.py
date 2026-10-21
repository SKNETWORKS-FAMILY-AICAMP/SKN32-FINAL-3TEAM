"""reasons_representative_draft 경계 — 모델 · DB 없이 돈다."""
from types import SimpleNamespace as N

from reasons_representative_draft import ordered_candidates, representative


def c(v, p, moved=None):
    return N(violation=N(value=v), confidence=p, moved_from=moved)


def names(xs):
    return [x.violation.value for x in xs]


def test_raw_probability_order_and_first_is_representative():
    s = N(encoder_candidates=[c("소비자_기만", 0.45), c("거짓_과장", 0.62), c("비방광고", 0.31)])
    assert names(ordered_candidates(s)) == ["거짓_과장", "소비자_기만", "비방광고"]
    assert representative(s).violation.value == "거짓_과장"


def test_raw_not_divided_by_threshold():
    # 확률 ÷ 문턱이면 소비자_기만(0.45/0.40=1.125)이 거짓_과장(0.50/0.475=1.05)을 앞서지만 원시 확률로는 거짓_과장이 대표다
    s = N(encoder_candidates=[c("소비자_기만", 0.45), c("거짓_과장", 0.50)])
    assert representative(s).violation.value == "거짓_과장"


def test_moved_candidate_ranks_by_original_probability():
    # 건기식_비인정: 건강기능식품_오인 0.7 → 거짓_과장으로 옮김(확률은 원래 유형의 것)
    s = N(encoder_candidates=[c("소비자_기만", 0.5), c("거짓_과장", 0.7, moved="건강기능식품_오인")])
    assert representative(s).violation.value == "거짓_과장"


def test_tie_prefers_direct_then_name():
    s = N(encoder_candidates=[c("의약품_오인", 0.6, moved="질병_예방치료_표방"), c("소비자_기만", 0.6), c("거짓_과장", 0.6)])
    assert names(ordered_candidates(s)) == ["거짓_과장", "소비자_기만", "의약품_오인"]


def test_keeps_every_candidate_and_empty_is_none():
    s = N(encoder_candidates=[c("a", 0.1), c("b", 0.9), c("c", 0.5)])
    assert len(ordered_candidates(s)) == 3
    assert representative(N(encoder_candidates=[])) is None
    assert representative(N()) is None
