"""질병 핵심 표현(조문 꼴 × 질병명) 사전 원천 (🆕 2026-10-18 · D-348 보충 21).

지키는 것
  ① 조합은 이름 × 동사 − 뺀 조합이다 · 근거는 식품 축 1호 하나(유형 하나 — 둘이면 `모호`로 자격을 잃는다)
  ② 사례집 · 의결서가 이미 낸 낱말은 덮지 않는다 — 그 항목의 근거 · 판독이 정본이다
  ③ 섭취 주의사항에 그대로 나오는 조합은 다른 항목과 똑같이 단독판정을 잃는다(D-311)
  ④ 주입(`preprocess/inject.py`)은 이 원천의 항목을 질병어로 쓰지 않는다 — 골든의 주입 행이 사전 확장에 끌려가지 않는다(보충 21 결정 4)
★ 산출물 없이 돈다 — tmp 입력으로 `build` 를 직접 부른다(`tests/test_dictionary_leak.py` 와 같은 꼴 · D-146).
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import registry, statute
from preprocess import dictionary, inject, split

pytestmark = pytest.mark.gate


def test_조합은_이름_곱하기_동사에서_뺀_조합을_덜어낸_것이다() -> None:
    got = dictionary.disease_pattern_terms()
    want = len(dictionary.DISEASE_NAMES) * len(dictionary.CLAIM_VERBS) - len(
        dictionary.PATTERN_DROP
    )
    assert len(got) == len(set(got)) == want
    assert not dictionary.PATTERN_DROP & set(got)
    assert "고혈압예방" in got and "비만치료" not in got
    assert all(t == dictionary.norm(t) for t in got)
    for name in ("부종", "갑상선", "소화불량", "숙취"):  # 판정으로 뺀 이름 (보충 21 결정 1)
        assert name not in dictionary.DISEASE_NAMES


def test_원천은_레지스트리에_있고_2차_저작이_막히지_않았다() -> None:
    registry.spec(dictionary.PATTERN_SOURCE)  # 없으면 멈춘다
    assert not registry.no_derivatives(dictionary.PATTERN_SOURCE)


@pytest.fixture
def built(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    """사례집 없음 · 의결서 문구 하나(「고혈압예방」 · 판 없음) · 주의사항 한 줄로 사전을 짓는다."""
    ftc = tmp_path / "ftc.json"
    ftc.write_text(
        json.dumps(
            [{"seq": "1", "유형": [{"article": "제3조제1항제1호"}], "문구": ["고혈압 예방"]}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dictionary, "FTC", ftc)
    monkeypatch.setattr(dictionary, "assign_map", lambda: {"ftc:1": "train"})
    monkeypatch.setattr(dictionary, "_jsonl", lambda p: [])
    monkeypatch.setattr(split, "ftc_train_marks", lambda: None)
    monkeypatch.setattr(dictionary, "approved_terms", lambda train: [])
    monkeypatch.setattr(
        dictionary, "caution_terms", lambda train: ["고혈압 치료제 등 복용 시 전문가와 상담할 것"]
    )
    rows, stat = dictionary.build()
    return {r["term"]: r for r in rows}, stat


def test_조문_꼴_항목은_식품_1호_하나로_단독판정이다(built: tuple[dict, dict]) -> None:
    rows, stat = built
    r = rows["아토피개선"]
    assert r["출처"] == [dictionary.PATTERN_SOURCE]
    assert r["근거"] == [statute.food(1)]
    assert r["유형"] == ["질병_예방치료_표방"]
    assert r["단독판정"] is True and r["신뢰도"] == "단일"
    assert stat["조문꼴"] == len(dictionary.disease_pattern_terms()) - stat["조문꼴_겹침"]


def test_이미_있는_낱말은_덮지_않는다(built: tuple[dict, dict]) -> None:
    rows, stat = built
    r = rows["고혈압예방"]
    assert r["출처"] == ["ftc_decisions_body"], "의결서 항목의 출처 · 근거가 정본이다"
    assert statute.food(1) not in r["근거"]
    assert stat["조문꼴_겹침"] == 1


def test_주의사항에_나오는_조합은_단독판정을_잃는다(built: tuple[dict, dict]) -> None:
    rows, _ = built
    r = rows["고혈압치료"]
    assert r["단독판정"] is False and r["신뢰도"] == "비주장문맥"


def test_주입은_조문_꼴_항목을_질병어로_쓰지_않는다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "data/derived/banned_terms.jsonl"
    p.parent.mkdir(parents=True)
    rows = [
        {"term": "소아비만예방", "유형": ["질병_예방치료_표방"], "출처": ["mfds_casebook"]},
        {"term": "녹내장예방", "유형": ["질병_예방치료_표방"], "출처": [dictionary.PATTERN_SOURCE]},
        {
            "term": "백내장치료",
            "유형": ["질병_예방치료_표방"],
            "출처": ["mfds_casebook", dictionary.PATTERN_SOURCE],
        },  # 사례집도 낸 낱말 — 주입 대상이다
    ]
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert inject.disease_terms() == ["백내장", "소아비만"]
