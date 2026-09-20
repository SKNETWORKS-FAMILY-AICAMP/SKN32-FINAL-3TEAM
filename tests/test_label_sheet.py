"""🔴 **사람은 번호만 채운다** — 라벨 시트 ↔ CSV 왕복 (2026-09-10).

⛔ 종전에는 JSONL 을 손으로 고치게 했다. 다섯 사람이 편집기로 열어
   `"확정유형": ["질병_예방치료_표방"]` 을 타이핑하면 이런 일이 난다 —
   대괄호를 빠뜨려 그 줄이 JSON 이 아니게 되고, 유형 이름을 한 글자 틀려 조용히 다른 라벨이 되고,
   `문구` 칸을 건드려 키가 어긋난다.

🚨 이 파일의 요점은 **막는 것이 실제로 막히는지**다 (D-170).
   실측 — 처음 구현은 시트↔지문만 대조해서, CSV 의 `문구` 를 고쳐도 **그냥 통과했다.**
   막으려던 바로 그것을 못 막고 있었고, 반대 대조로 잡았다.
"""

from __future__ import annotations

import csv
import json
import pathlib

import pytest

from scripts import label_sheet as ls

pytestmark = pytest.mark.gate


@pytest.fixture
def sheet(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "sheet.jsonl"
    rows = [
        {"문구": "변비에 효과가 있습니다", "후보유형": ["거짓_과장"]},
        {"문구": "타사 제품보다 2배 빠릅니다", "후보유형": ["거짓_과장"]},
    ]
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return p


def _csv(tmp_path: pathlib.Path, sheet: pathlib.Path, nos: list[str]) -> pathlib.Path:
    rows = ls._rows(sheet)
    p = tmp_path / "누구.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ls.HEADER)
        w.writeheader()
        for i, (r, no) in enumerate(zip(rows, nos, strict=True), 1):
            t = ls._text(r)
            w.writerow({"행": i, "문구": t, "유형번호": no, "붙인이": "권소라", "지문": ls._fp(t)})
    return p


def test_번호가_라벨로_바뀐다(tmp_path, sheet, monkeypatch) -> None:
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    ls.import_(_csv(tmp_path, sheet, ["1", "6"]), sheet, "")
    got = [
        json.loads(x)
        for x in (tmp_path / "data/derived/labels/권소라__sheet.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [r["확정유형"] for r in got] == [["질병_예방치료_표방"], ["부당_비교광고"]]
    assert all(r["붙인이"] == "권소라" for r in got)


def test_빈칸은_안_들어간다(tmp_path, sheet, monkeypatch) -> None:
    """🚨 빈칸은 실패가 아니라 판단이다 — 억지로 채우지 않게 하려면 버려야 한다."""
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    ls.import_(_csv(tmp_path, sheet, ["", "8"]), sheet, "")
    got = (
        (tmp_path / "data/derived/labels/권소라__sheet.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(got) == 1


def test_모르는_번호는_멈춘다(tmp_path, sheet, monkeypatch) -> None:
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as e:
        ls.import_(_csv(tmp_path, sheet, ["9", "1"]), sheet, "")
    assert "1~8" in str(e.value)


def test_문구를_고치면_멈춘다(tmp_path, sheet, monkeypatch) -> None:
    """🔴 **이것이 이 파일의 본체다.** 처음 구현은 여기서 통과했다.

    시트↔지문만 대조하면 CSV 의 `문구` 를 고쳐도 지문이 그대로라 지나간다.
    문구가 키이므로(D-160) 어긋나면 취합에서 짝을 못 찾고 **조용히 사라진다.**
    """
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    p = _csv(tmp_path, sheet, ["1", "6"])
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    rows[0]["문구"] = "손으로 고친 문구"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    with pytest.raises(SystemExit) as e:
        ls.import_(p, sheet, "")

    assert "문구" in str(e.value) and "조용히 사라진다" in str(e.value)


def test_붙인이가_없으면_멈춘다(tmp_path, sheet, monkeypatch) -> None:
    """누가 붙였는지가 라벨의 일부다 (D-66)."""
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    p = _csv(tmp_path, sheet, ["1", "6"])
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    rows[0]["붙인이"] = ""
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(SystemExit):
        ls.import_(p, sheet, "")


def test_번호표가_지시서와_같은_순서다() -> None:
    """🔴 번호는 **판정 순서**다 — 두 곳이 갈리면 사람이 딴 라벨을 적는다 (D-99)."""
    doc = (ls.ROOT / "docs" / "ohb" / "라벨링_지시서_2026-09-10.md").read_text(encoding="utf-8")
    order = [t for t in ls.TYPES if t in doc]
    assert order == list(ls.TYPES), "지시서에 없는 유형이 번호표에 있다"
    pos = [doc.index(f"→ {t}") for t in ls.TYPES]
    assert pos == sorted(pos), (
        f"🚨 지시서 §3 의 판정 순서와 번호표가 다르다 — {ls.TYPES}\n"
        "   번호를 바꾸려면 지시서와 **같은 커밋에서** 바꾼다."
    )


def test_0_은_범위밖이다(tmp_path, sheet, monkeypatch) -> None:
    """🆕 2026-09-20 — 칸을 하나 더 두지 않는다. `0` 을 적으면 「여덟 유형 어디에도 없다」."""
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    ls.import_(_csv(tmp_path, sheet, ["0", "8"]), sheet, "")
    got = [
        json.loads(x)
        for x in (tmp_path / "data/derived/labels/권소라__sheet.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert got[0]["판단"] == "범위밖" and got[0]["확정유형"] == []


def test_옛_판_CSV_도_읽는다(tmp_path, sheet, monkeypatch) -> None:
    """이미 채워 둔 옛 판(`후보유형`·`붙인날` 칸) CSV 가 가져오기에서 막히지 않는다."""
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    p = tmp_path / "옛.csv"
    rows = ls._rows(sheet)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["행", "문구", "후보유형", "유형번호", "붙인이", "붙인날", "지문"])
        for i, r in enumerate(rows, 1):
            t = ls._text(r)
            w.writerow([i, t, "", "8", "권소라", "2026-09-10", ls._fp(t)])
    ls.import_(p, sheet, "")
    assert (tmp_path / "data/derived/labels/권소라__sheet.jsonl").exists()


def test_보기는_번호와_함께_보인다() -> None:
    got = ls.choices({"후보유형": ["질병_예방치료_표방", "의약품_오인"]})
    assert got.startswith("1 질병_예방치료_표방 · 2 의약품_오인")
    assert "0=범위밖" in got
