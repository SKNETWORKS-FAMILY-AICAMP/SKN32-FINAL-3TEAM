"""대구청 사례(2013) — 확정 문구 전사의 파생과 조문·조건 판의 원천 대조 (2026-10-05 · 원장 10-03 ㊿-14).

🔴 무엇을 막나
   ① 전사가 없는데 빈 파생물이 나가는 것 · 빈 칸 · 겹친 번호가 든 전사 (D-220)
   ② 마스킹 정책을 지나지 않은 문구가 파생물로 나가는 것 · 규칙 축이 바꾼 수가 기대와 달라졌는데 모르고 지나는 것 (D-72 · D-17)
   ③ 전사에서 제외한 행 · 파생물과 글자가 다른 행이 단위로 드는 것
"""

from __future__ import annotations

import json

import pytest

from scripts import daegu2013_sheet as sheet
from scripts import guide_statute_round as g

K = "dg:aaaaaaaaaaaa"


def _row(no: int, text: str, drop: str = "") -> dict:
    return {
        "번호": no,
        "쪽": 2,
        "묶음": "질병 예방·치료",
        "품목": "식품",
        "문구": text,
        "제외": drop,
    }


@pytest.mark.gate
def test_전사가_없거나_어긋나면_멈춘다(tmp_path) -> None:
    with pytest.raises(sheet.SheetError, match="없다"):
        sheet.load(tmp_path / "none.json")
    p = tmp_path / "p.json"
    p.write_text(json.dumps([_row(1, "가"), _row(1, "나")], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(sheet.SheetError, match="두 번"):
        sheet.load(p)
    p.write_text(json.dumps([_row(1, "")], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(sheet.SheetError, match="빈 칸"):
        sheet.load(p)


@pytest.mark.gate
def test_문구는_정책을_지나고_바뀐_수가_기대와_다르면_멈춘다(tmp_path) -> None:
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps(
            [_row(1, "혈액순환에 좋은 차"), _row(2, "(주)가나다식품이 만든 차")], ensure_ascii=False
        ),
        encoding="utf-8",
    )
    got, _ = sheet.rows(p)
    assert got[0]["원천"] == sheet.SOURCE_ID and got[0]["기준시점"] == "2013"
    assert "가나다식품" not in got[1]["문구"] and got[1]["바뀜"]
    with pytest.raises(sheet.SheetError, match="기대"):
        sheet.verify(got)
    sheet.verify(got[:1])


@pytest.fixture
def dg(tmp_path, monkeypatch):
    rows = [_row(1, "혈액순환에 좋은 차"), _row(2, "도마", "이번 판 제외 — 기구")]
    p = tmp_path / "dg.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(g, "DG_ROWS", p)
    monkeypatch.setattr(g.registry, "assert_derivable", lambda rows, who: None)
    return rows


@pytest.mark.gate
def test_단위는_파생물의_행과_같아야_한다(dg) -> None:
    src = g.dg_units([{"지문": K, **dg[0]}])
    assert src[K]["번호"] == 1 and src[K]["원천"] == g.DG_SOURCE


@pytest.mark.gate
@pytest.mark.parametrize(
    "unit",
    [
        {"번호": 1, "문구": "혈액순환에 좋은 차!"},  # 글자가 다르다
        {"번호": 9},  # 파생물에 없는 번호
        {"번호": 2, "문구": "도마"},  # 전사에서 제외한 행
        {"지문": "mn:aaaaaaaaaaaa"},  # 다른 판의 지문
    ],
)
def test_어긋난_단위는_멈춘다(dg, unit) -> None:
    with pytest.raises(SystemExit, match="대구청"):
        g.dg_units([{"지문": K, **dg[0], **unit}])
