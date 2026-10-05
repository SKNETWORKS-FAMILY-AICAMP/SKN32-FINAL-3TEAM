"""1차 법령해석 조문·조건 판 — 단위의 원천 대조와 품목별 판 (2026-10-04 · 원장 10-03 ㊿-13).

🔴 무엇을 막나
   ① 화장품 해석의 문구가 식품 근거 코드로 읽히는 것 — 품목과 지문 머리가 판을 정한다 (D-220)
   ② 파생물에 없는 해석 · 해석 글에 없는 문구가 단위로 드는 것
"""

from __future__ import annotations

import json

import pytest

from scripts import guide_statute_round as g

KF, KC = "if:aaaaaaaaaaaa", "ic:aaaaaaaaaaaa"


@pytest.fixture
def ip(tmp_path, monkeypatch):
    qa = tmp_path / "qa.jsonl"
    rows = [
        {
            "id": "1",
            "품목": "식품",
            "안건명": "제품명",
            "질의": "제품명에 하이 볼 을 써도 되나",
            "답변": "",
            "인용표현": ["하이볼"],
        },
        {
            "id": "2",
            "품목": "화장품",
            "안건명": "",
            "질의": "",
            "답변": "주름 개선 표현은",
            "인용표현": [],
        },
    ]
    qa.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(g, "IP_QA", qa)
    monkeypatch.setattr(g.registry, "assert_derivable", lambda rows, who: None)

    def unit(k, item, q, text):
        return {"지문": k, "품목": item, "문항": q, "자리": "질의", "문구": text}

    return unit


@pytest.mark.gate
def test_문구는_인용표현이나_해석_글에_있으면_된다(ip) -> None:
    assert list(g.ip_units([ip(KF, "식품", "1", "하이볼")], "식품")) == [KF]
    assert list(g.ip_units([ip(KF, "식품", "1", "하이 볼")], "식품")) == [KF]  # 공백만 다르게
    got = g.ip_units([ip(KC, "화장품", "2", "주름 개선")], "화장품")
    assert got[KC]["원천"] == g.IP_SOURCE and got[KC]["품목"] == "화장품"


@pytest.mark.gate
@pytest.mark.parametrize(
    ("unit", "item"),
    [
        ((KF, "식품", "1", "막걸리"), "식품"),  # 해석 글에 없는 문구
        ((KF, "식품", "9", "하이볼"), "식품"),  # 파생물에 없는 해석
        ((KF, "식품", "2", "주름 개선"), "식품"),  # 원천의 품목이 다르다
        ((KC, "화장품", "2", "주름 개선"), "식품"),  # 다른 판의 단위
        ((KC, "식품", "1", "하이볼"), "식품"),  # 지문 머리가 품목과 어긋난다
    ],
)
def test_어긋난_단위는_멈춘다(ip, unit, item) -> None:
    with pytest.raises(SystemExit, match="1차 해석"):
        g.ip_units([ip(*unit)], item)


@pytest.mark.gate
def test_품목마다_다른_근거_코드로_읽는다() -> None:
    assert g.ROUNDS["ipf"][0].cite_of is g.cite_of
    assert g.ROUNDS["ipc"][0].cite_of is g.cq_cite_of
    assert g.IPF.path("ADOPTED") != g.IPC.path("ADOPTED")
