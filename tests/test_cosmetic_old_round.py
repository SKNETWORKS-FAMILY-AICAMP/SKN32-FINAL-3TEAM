"""옛 화장품 질의응답(2012 · FAQ 2020) 조문·조건 판 — 단위의 원천 대조와 판 경로 (2026-10-04 · 판정 묶음 ①).

🔴 무엇을 막나
   ① 두 원천의 문항 표기(「장-문항」 · 「Q번호」)가 섞여 **다른 문항**에 붙는 것 — 지문 머리가 원천을 정한다
   ② 원천에서 사라진 문구가 단위 표에 남아 채택되는 것 — 인용표현에도 문항 글에도 없으면 멈춘다 (D-220)
   ③ 의약외품 편(범위 밖 · D-192)의 문항이 화장품 편의 같은 번호로 읽히는 것
   ④ 판독 원자료만으로 다시 계산할 때(`co-rebuild`) 원천 칸이 없어 멈추는 것 — 원자료는 `원천` 을 싣지 않는다
"""

from __future__ import annotations

import json
import pathlib

import pytest

from scripts import guide_statute_round as g

A, F = "mfds_cosmetic_ad_qa_2012", "mfds_cosmetic_faq_2020"


def _jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def co(tmp_path, monkeypatch):
    """판의 경로를 전부 임시 폴더로 — 실제 원자료 · 판정을 덮지 않는다."""
    d = tmp_path / "co"
    for name, fn in (
        ("CO_READINGS", "readings.jsonl"),
        ("CO_ADOPTED", "adopted.jsonl"),
        ("CO_DECISIONS", "decisions.jsonl"),
        ("CO_AUDIT", "audit.jsonl"),
        ("CO_TEAM_SHEET", "team.csv"),
    ):
        monkeypatch.setattr(g, name, d / fn)
    a, f = tmp_path / "a.jsonl", tmp_path / "f.jsonl"
    _jsonl(
        a,
        [
            {
                "편": "화장품",
                "장": "1. 화장품 표시광고 : 일반사항",
                "문항": 4,
                "제목": "체취 방지",
                "질의": "다음 표현이 가능한지",
                "답변": "피부를 맑고  청결하게\n가꾼다는 표현은 가능",
                "인용표현": ["탈취 효과"],
            },
            {
                "편": "의약외품",
                "장": "1. 의약외품 품목분류",
                "문항": 4,
                "질의": "외품 질의",
                "답변": "외품 답변 탈취 효과",
                "인용표현": ["외품 문구"],
            },
        ],
    )
    _jsonl(
        f,
        [
            {
                "편": "Ⅳ. 광고",
                "문항": 109,
                "질의": "붓기",
                "답변": "",
                "인용표현": ["다리 붓기 완화"],
            }
        ],
    )
    monkeypatch.setattr(g, "CO_QA", {A: a, F: f})
    return tmp_path


def _u(key, q, text, **kw):
    return {"지문": key, "문항": q, "자리": "답변", "문구": text, **kw}


def test_문항_표기는_원천마다_다르고_의약외품_편은_범위_밖이다() -> None:
    assert g.co_question(F, {"문항": 7}) == "Q7"
    assert g.co_question(A, {"편": "화장품", "장": "4. 화장품 품목분류", "문항": 12}) == "4-12"
    assert g.co_question(A, {"편": "의약외품", "장": "1. 의약외품 품목분류", "문항": 1}) is None


@pytest.mark.gate
def test_단위는_인용표현이나_문항_글에_있어야_한다(co) -> None:
    src = g.co_units(
        [
            _u("ca:aaaaaaaaaaaa", "1-4", "탈취 효과", 원천=A),  # 인용표현
            _u(
                "ca:bbbbbbbbbbbb", "1-4", "피부를 맑고 청결하게 가꾼다"
            ),  # 문항 글 · 공백만 다르다 · 원천 칸 없음
            _u("cf:cccccccccccc", "Q109", "다리 붓기 완화", 원천=F),
        ]
    )
    assert [src[k]["원천"] for k in sorted(src)] == [A, A, F]
    assert src["ca:bbbbbbbbbbbb"]["문항"] == "1-4"


@pytest.mark.gate
@pytest.mark.parametrize(
    ("unit", "why"),
    [
        (_u("ca:aaaaaaaaaaaa", "1-4", "없는 문구"), "원천에 없는 문구"),
        (_u("ca:aaaaaaaaaaaa", "1-4", "외품 문구"), "원천에 없는 문구"),  # 의약외품 편의 같은 번호
        (
            _u("ca:aaaaaaaaaaaa", "Q109", "다리 붓기 완화"),
            "없는 문항",
        ),  # 2012 지문에 2020 문항 표기
        (_u("cf:aaaaaaaaaaaa", "Q109", "다리 붓기 완화", 원천=A), "지문 머리와 원천"),
        (_u("cq:aaaaaaaaaaaa", "1-4", "탈취 효과"), "지문 꼴"),
    ],
)
def test_원천과_어긋난_단위는_멈춘다(co, unit: dict, why: str) -> None:
    with pytest.raises(SystemExit, match=why):
        g.co_units([unit])


@pytest.mark.gate
def test_병합한_뒤_원자료만으로_다시_계산된다(co) -> None:
    units = [
        _u("ca:aaaaaaaaaaaa", "1-4", "탈취 효과", 원천=A),
        _u("cf:cccccccccccc", "Q109", "다리 붓기 완화", 원천=F),
    ]
    up = co / "units.json"
    up.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    head = "지문\t대상\t주근거\t부근거\t별표5목\t조건\t제외목\t메모\n"
    body = "ca:aaaaaaaaaaaa\tY\t-\t-\t-\tL\t-\t\ncf:cccccccccccc\tY\t1\t-\t가\tB\t실증\t\n"
    for n in ("r1.tsv", "r2.tsv"):
        (co / n).write_text(head + body, encoding="utf-8")
    got = g._merge(g.CO, up, co / "r1.tsv", co / "r2.tsv")
    assert got["채택"] == 2 and got["시트"] == 0
    again = g._rebuild(g.CO)  # 원자료에는 `원천` 칸이 없다 — 지문 머리로 정한다
    assert again["채택"] == 2
    rows = [json.loads(x) for x in g.CO_ADOPTED.read_text(encoding="utf-8").splitlines()]
    assert {r["지문"]: r["원천"] for r in rows} == {"ca:aaaaaaaaaaaa": A, "cf:cccccccccccc": F}
    assert {r["지문"]: r["조건"] for r in rows} == {"ca:aaaaaaaaaaaa": "L", "cf:cccccccccccc": "B"}
