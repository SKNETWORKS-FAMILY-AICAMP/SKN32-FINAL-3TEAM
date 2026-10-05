"""사례집 2021 조문·조건 판 — 단위의 원천 대조와 법별 판 (2026-10-04 · 판정 묶음 ① · 지시서 2026-10-03 사례집2021).

🔴 무엇을 막나
   ① 화장품 화면이 식품 근거 코드로 읽히는 것 — 코드 `1` 이 두 법에서 다른 조문이다. 단위의 `법` 이 판을 정한다
   ② 쪽 전사가 바뀌어 행 번호가 밀렸는데 옛 단위가 다른 화면에 붙는 것 — 쪽 · 칸이 다르면 멈춘다 (D-220)
   ③ 원천 화면에 없는 줄이 단위 문구에 든 것 — 줄마다 화면 글에 있어야 한다(공백 · 표시 자국만 다르게)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import statute
from scripts import guide_statute_round as g


def _jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def cb(tmp_path, monkeypatch):
    """두 판의 경로를 전부 임시 폴더로 — 실제 원자료 · 판정을 덮지 않는다."""
    for pre in ("CBF", "CBC"):
        for name, fn in (
            ("READINGS", "readings.jsonl"),
            ("ADOPTED", "adopted.jsonl"),
            ("DECISIONS", "decisions.jsonl"),
            ("AUDIT", "audit.jsonl"),
            ("TEAM_SHEET", "team.csv"),
        ):
            monkeypatch.setattr(g, f"{pre}_{name}", tmp_path / pre / fn)
    sheet = tmp_path / "sheet.jsonl"
    _jsonl(
        sheet,
        [
            {
                "쪽": "10",
                "칸": "1",
                "문구": "치매예방",
                "화면글": [{"글": "기억력 ⟦치매예방⟧!", "표시": "형광"}],
            },
            {
                "쪽": "49",
                "칸": "2",
                "문구": "",
                "화면글": [
                    {"글": "남성 호르몬  쉽게 채운다", "표시": "없음"},
                    {"글": "성인병 예방", "표시": "없음"},
                ],
                "식약처설명": ["의약품 오인"],
            },
            {
                "쪽": "72",
                "칸": "2",
                "문구": "",
                "화면글": [{"글": "·⟦항염증 작용⟧ 및 항균", "표시": "색글자"}],
            },
        ],
    )
    monkeypatch.setattr(g, "CB_SHEET", sheet)
    return tmp_path


def _u(key, row, page, cell, law, text):
    return {"지문": key, "행": row, "쪽": page, "칸": cell, "법": law, "원천호": "1", "문구": text}


@pytest.mark.gate
def test_단위는_행의_쪽_칸이_같고_줄마다_화면에_있어야_한다(cb) -> None:
    food = g.cb_units(
        [
            _u("cb:aaaaaaaaaaaa", "1", "10", "1", "식품", "치매예방"),
            # 표시 문구가 없는 화면 — 화면 글을 이어 붙인 문구 · 공백만 다르다
            _u("cb:bbbbbbbbbbbb", 2, 49, 2, "식품", "남성 호르몬 쉽게 채운다 / 성인병 예방"),
        ],
        "식품",
    )
    assert food["cb:bbbbbbbbbbbb"]["행"] == 2 and food["cb:bbbbbbbbbbbb"]["원천"] == g.CB_SOURCE
    # 표시 자국(⟦ ⟧)은 대조에서 보지 않는다
    cosm = g.cb_units(
        [_u("cb:cccccccccccc", "3", "72", "2", "화장품", "·항염증 작용 및 항균")], "화장품"
    )
    assert cosm["cb:cccccccccccc"]["법"] == "화장품"


@pytest.mark.gate
@pytest.mark.parametrize(
    ("unit", "law", "why"),
    [
        (_u("cb:aaaaaaaaaaaa", "1", "10", "1", "화장품", "치매예방"), "식품", "이 판은 식품"),
        (
            _u("cb:aaaaaaaaaaaa", "2", "10", "1", "식품", "치매예방"),
            "식품",
            "쪽 · 칸이 원천과 다르다",
        ),
        (
            _u("cb:aaaaaaaaaaaa", "9", "10", "1", "식품", "치매예방"),
            "식품",
            "쪽 · 칸이 원천과 다르다",
        ),
        (
            _u("cb:aaaaaaaaaaaa", "2", "49", "2", "식품", "성인병 예방 / 없는 줄"),
            "식품",
            "원천에 없는 줄",
        ),
        (_u("cb:aaaaaaaaaaaa", "1", "10", "1", "식품", " / "), "식품", "원천에 없는 줄"),
        (_u("cq:aaaaaaaaaaaa", "1", "10", "1", "식품", "치매예방"), "식품", "지문 꼴"),
    ],
)
def test_원천과_어긋난_단위는_멈춘다(cb, unit: dict, law: str, why: str) -> None:
    with pytest.raises(SystemExit, match=why):
        g.cb_units([unit], law)


@pytest.mark.gate
def test_같은_코드가_법마다_다른_조문으로_읽힌다(cb) -> None:
    """🔴 코드 `1` — 식품 판은 식품표시광고법 제8조①1호, 화장품 판은 화장품법 제13조①1호다."""
    line = "cb:aaaaaaaaaaaa\tY\t1\t-\t-\tC\t-\t"
    assert g._parse(g.CBF, line)["근거"] == [statute.food(1)]
    assert g._parse(g.CBC, line)["근거"] == [statute.cite(*statute.COSM, 1)]
    # 화장품 별표5목은 식품 판에서 판독 문제다
    assert g._parse(g.CBF, "cb:aaaaaaaaaaaa\tY\t1\t-\t가\tC\t-\t")["문제"]


@pytest.mark.gate
def test_병합한_뒤_원자료만으로_다시_계산된다(cb) -> None:
    up = cb / "units.json"
    up.write_text(
        json.dumps([_u("cb:aaaaaaaaaaaa", "1", "10", "1", "식품", "치매예방")], ensure_ascii=False),
        encoding="utf-8",
    )
    head = "지문\t대상\t주근거\t부근거\t별표5목\t조건\t제외목\t메모\n"
    for n in ("r1.tsv", "r2.tsv"):
        (cb / n).write_text(head + "cb:aaaaaaaaaaaa\tY\t1.가\t-\t-\tC\t-\t\n", encoding="utf-8")
    assert g._merge(g.CBF, up, cb / "r1.tsv", cb / "r2.tsv")["채택"] == 1
    assert (
        g._rebuild(g.CBF)["채택"] == 1
    )  # 원자료가 행 · 쪽 · 칸 · 법을 들고 있어 원천 대조가 다시 선다
    row = json.loads(g.CBF_ADOPTED.read_text(encoding="utf-8").splitlines()[0])
    assert (row["법"], row["쪽"], row["조건"]) == ("식품", "10", "C")
