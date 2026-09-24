"""법 이름 · 법 ID → 법 축 대응표 (`collect/law_map.py` · 🆕 2026-09-24 · D-271 ①).

🔴 막는 것 —
   ① `TARGETS` 에 법 ID 가 늘었는데 법 축이 없다 · 대응표에만 있는 ID 가 있다 (양방향)
   ② 법률 ID 와 시행령 ID 를 헷갈린다(`005361`)
   ③ 「식품표시광고법 …」 근거를 표시광고법으로 읽는다(짧은 이름이 긴 이름의 꼬리)
   ④ 사전(`banned_terms`)의 근거 중 법을 못 정하는 것이 조용히 기본값으로 떨어진다
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import law_map as lm
from collect.law_api import TARGETS

pytestmark = pytest.mark.gate

ROOT = pathlib.Path(__file__).resolve().parents[1]
BANNED = ROOT / "data" / "derived" / "banned_terms.jsonl"


def _target_ids() -> set[str]:
    return {i for rows in (TARGETS["law"], TARGETS["admrul"]) for i, _, _ in rows}


def test_TARGETS_의_모든_ID_에_법이_있고_남는_것이_없다() -> None:
    ids = _target_ids()
    assert not ids - set(lm.LAW_OF_ID), f"🔴 법 축이 없는 법 ID: {sorted(ids - set(lm.LAW_OF_ID))}"
    assert not set(lm.LAW_OF_ID) - ids, f"🔴 TARGETS 에 없는 ID: {sorted(set(lm.LAW_OF_ID) - ids)}"


def test_법_축은_넷이고_모두_법률_ID_를_가진다() -> None:
    assert set(lm.LAW_OF_ID.values()) == set(lm.LAWS) == set(lm.STATUTE_ID)
    law_ids = {i for i, _, _ in TARGETS["law"]}
    for law, sid in lm.STATUTE_ID.items():
        assert sid in law_ids and lm.LAW_OF_ID[sid] == law


def test_시행령_ID_는_법률_ID_가_아니다() -> None:
    assert lm.LAW_OF_ID["005361"] == "표시광고법"
    assert lm.STATUTE_ID["표시광고법"] == "002011" != "005361"


@pytest.mark.parametrize(
    ("basis", "law"),
    [
        ("표시광고법 제3조제1항제1호", "표시광고법"),
        ("식품표시광고법 제8조제1항제4호", "식품표시광고법"),
        ("식품 등의 표시ㆍ광고에 관한 법률 제8조", "식품표시광고법"),
        ("표시ㆍ광고의 공정화에 관한 법률 제3조", "표시광고법"),
        ("화장품법 제13조제1항", "화장품법"),
        ("건강기능식품에 관한 법률 제18조제1항제1호", "건강기능식품법"),
        ("화장품법 시행규칙 제22조", None),  # 시행규칙을 법률 조문으로 읽지 않는다
        ("의료기기법 제24조", None),  # 우리가 안 가진 법 — 기본값으로 떨어지지 않는다 (D-277)
        ("", None),
    ],
)
def test_근거_문자열의_법(basis: str, law: str | None) -> None:
    assert lm.law_of_basis(basis) == law


def test_참고_전용_법은_축_안에_있다() -> None:
    assert set(lm.LAWS) >= lm.REFERENCE_ONLY


def test_사전의_근거는_전부_법이_정해진다() -> None:
    """🔴 Q4 — 사전 근거가 판정 근거가 된다. 법을 못 정하는 근거가 있으면 그 문장의 근거 조문이 비어 나간다."""
    if not BANNED.exists():
        pytest.skip(
            "banned_terms.jsonl 이 이 기기에 없다 — 기기 축 (D-19) · 대응표 자체는 위 게이트가 본다"
        )
    bad = sorted(
        {
            b
            for line in BANNED.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for b in json.loads(line).get("근거") or []
            if lm.law_of_basis(b) is None
        }
    )
    assert not bad, f"🔴 법을 못 정한 사전 근거 {len(bad)}종: {bad[:5]}"
