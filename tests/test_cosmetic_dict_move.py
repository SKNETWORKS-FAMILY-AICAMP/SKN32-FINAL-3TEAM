"""화장품 전제의 사전 쪽 옮김 (🆕 2026-10-18 · D-348 보충 23 결정 2 · D-338 개정).

지키는 것
  ① 화장품법 노드는 식품 축 질병 표방 · 의약품 오인 인용(칸 C)을 가진 단독판정 적중을 화장품법 13①1(의약품 오인)로 옮겨 받는다
  ② 옮기지 않는다 — 기능성 정형 문구 · 낱말만 있는 꼴(탈모 · 탈모완화 · 탈모개선) · 건강기능식품 오인 인용(식품 칸 A) · 이미 화장품법 인용이 있는 적중 · 자격 없는 적중(후보)
  ③ 식품 · 표시광고법 노드는 그대로다 — 옮김은 화장품법 노드에만
  ④ 인코더 쪽 옮김과 같은 표(`rs.COSMETIC_MOVE`)의 유형으로 옮긴다 — 두 경로가 같은 규약이다(D-99)
"""

from __future__ import annotations

import pytest

from app import graph as g
from app import reasons as rs
from app.contracts import Violation
from collect import statute

pytestmark = pytest.mark.gate

FOOD1 = statute.food(1)  # 질병 표방
FOOD2 = statute.food(2)  # 의약품 오인
FOOD3 = statute.food(3)  # 건강기능식품 오인 (칸 A)


def _hit(term: str, *basis: str) -> g.DictHit:
    return g.DictHit(term, None, tuple(basis), (0, len(term)))


def test_식품_질병_의약품_C_인용은_화장품법_13조1항1호로_옮긴다() -> None:
    moved = g._cosmetic_dict_moved([_hit("아토피", FOOD1), _hit("간약", FOOD2)])
    assert [h.term for h in moved] == ["아토피", "간약"]
    for h in moved:
        assert h.violation_type == Violation.의약품_오인.value
        assert h.basis == (rs.COSMETIC_DRUG_CITE,)
        assert statute.law_of(h.basis[0]) == "화장품법"
        assert statute.type_of(h.basis[0]) == Violation.의약품_오인.value
    assert set(rs.COSMETIC_MOVE.values()) == {Violation.의약품_오인}, "인코더 쪽 옮김과 같은 유형"


@pytest.mark.parametrize(
    "hit",
    [
        _hit("탈모", FOOD1),  # 화장품에서는 낱말만 있는 M · 기능성 정형 문구(A)
        _hit("탈모완화", FOOD1),
        _hit("탈모개선", FOOD1),
        _hit("다이어트", FOOD3),  # 건강기능식품 오인(식품 칸 A) — A 를 C 로 바꾸지 않는다
        _hit("건선", rs.COSMETIC_DRUG_CITE, FOOD1),  # 화장품법 인용이 이미 있다 — 그 인용이 정본
    ],
)
def test_옮기지_않는_적중(hit: g.DictHit) -> None:
    assert g._cosmetic_dict_moved([hit]) == ()


def _node_hits(node_name: str, strong: tuple[g.DictHit, ...], weak: tuple[g.DictHit, ...] = ()):  # noqa: ANN202
    node = g._law_node(node_name)
    sid = g.sent_id(0)
    out = node(
        {
            "sents": ["문장"],
            "dict_scans": [g.DictScan(sent_id=sid, ran=True, hits=strong, weak=weak)],
        }
    )
    (r,) = out["law_results"]
    return dict(r.dict_hits)[sid], dict(r.weak_hits)[sid]


def test_화장품법_노드만_옮겨_받고_식품_노드는_그대로다() -> None:
    h = _hit("아토피", FOOD1)
    cosm, _ = _node_hits("law_cosmetic", (h,))
    assert [(x.term, x.violation_type, x.basis) for x in cosm] == [
        ("아토피", Violation.의약품_오인.value, (rs.COSMETIC_DRUG_CITE,))
    ]
    food, _ = _node_hits("law_food", (h,))
    assert [(x.term, x.basis) for x in food] == [("아토피", (FOOD1,))]
    ftc, _ = _node_hits("law_ftc", (h,))
    assert ftc == ()


def test_자격_없는_적중은_옮기지_않는다() -> None:
    _, weak = _node_hits("law_cosmetic", (), (_hit("아토피", FOOD1),))
    assert weak == (), "품목 미상 기록의 후보에 화장품 사본이 붙으면 소음이다(D-338)"
