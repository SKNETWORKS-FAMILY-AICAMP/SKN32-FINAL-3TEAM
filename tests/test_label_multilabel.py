"""다중 라벨의 합의는 유형별로 — 🆕 2026-09-22 (D-262 · D-252 개정 · 2차 판 실측).

★ 재는 것 —
  ① {8} 과 {5,8} 은 **부분합의**다 — 8 은 합의, 5 만 갈림. 묶음이 다르다고 통째로 갈림이 아니다
  ② 범위밖 ↔ 유형은 여전히 갈림 · 범위밖끼리는 합의
  ③ 부분합의는 판정 전까지 **평가로 나가지 않는다** — 갈린 유형을 음성으로 두면 오탐으로 채점된다
  ④ 유형별 κ 는 부분합의를 공유 유형의 일치로 센다 (묶음 κ 와 다르다)
  ⑤ 2차 판에서 난 두 사고 — `;` 구분자 · 엑셀이 지수 표기로 바꾼 지문 — 가 가져오기를 멈추지 않는다
     (단, 문구를 고친 행은 여전히 멈춘다)
"""

from __future__ import annotations

import csv
import json
import pathlib

import pytest

from preprocess import labels
from scripts import label_merge
from scripts import label_sheet as ls

pytestmark = pytest.mark.gate

F = frozenset


# ── ① ② 합의 규칙 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("answers", "rel", "agreed", "contested"),
    [
        ([F({"8"}), F({"8"})], labels.AGREED, F({"8"}), F()),
        ([F({"8"}), F({"5", "8"})], labels.PARTIAL, F({"8"}), F({"5"})),
        ([F({"1", "3"}), F({"1"}), F({"1", "4"})], labels.PARTIAL, F({"1"}), F({"3", "4"})),
        ([F({"1"}), F({"3"})], labels.SPLIT, F(), F({"1", "3"})),
        ([F({"0"}), F({"3"})], labels.SPLIT, F(), F({"0", "3"})),
        ([F({"0"}), F({"0"})], labels.AGREED, F({"0"}), F()),
    ],
)
def test_합의는_유형별로_본다(answers, rel, agreed, contested) -> None:
    assert labels.agreement(answers, "0") == (rel, agreed, contested)


def _line(person: str, text: str, types: list[str] | None, scope: str | None = None) -> str:
    r = {"원천": "g", "원천라벨": "", "문구": text, "글": "", "쪽": "", "호": "", "붙인이": person}
    if types:
        r["확정유형"] = types
    if scope:
        r["판단"] = scope
    return json.dumps(r, ensure_ascii=False)


# ── ③ 부분합의는 판정 전까지 안 나간다 ─────────────────────────────


def test_부분합의는_세고_판정_전에는_내보내지_않는다(tmp_path, monkeypatch) -> None:
    d = tmp_path / "labels"
    d.mkdir()
    (d / "A__s.jsonl").write_text(
        _line("A", "p1", ["거짓_과장"]) + "\n" + _line("A", "a1", ["비방광고"]) + "\n",
        encoding="utf-8",
    )
    (d / "B__s.jsonl").write_text(
        _line("B", "p1", ["거짓_과장", "소비자_기만"])
        + "\n"
        + _line("B", "a1", ["비방광고"])
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(labels, "DIR", d)
    picked, stat = labels.consensus()
    assert stat == {"부분합의": 1, "합의": 1}, stat
    assert [r["문구"] for r in picked.values()] == ["a1"], "🔴 부분합의가 판정 없이 평가로 나갔다"
    # 판정 레코드가 오면 들어온다
    dec = json.loads(_line("팀장", "p1", ["거짓_과장", "소비자_기만"]))
    dec[labels.DECIDED] = labels.DECIDED
    (d / "_판정__s.jsonl").write_text(json.dumps(dec, ensure_ascii=False) + "\n", encoding="utf-8")
    picked, stat = labels.consensus()
    assert stat.get("판정") == 1 and {r["문구"] for r in picked.values()} == {"a1", "p1"}


# ── ④ 유형별 κ ─────────────────────────────────────────────


def test_유형별_κ_는_부분합의를_공유_유형의_일치로_센다() -> None:
    a = {f"k{i}": "거짓_과장" for i in range(10)} | {f"n{i}": "비방광고" for i in range(10)}
    b = {f"k{i}": "거짓_과장|소비자_기만" for i in range(10)} | {
        f"n{i}": "비방광고" for i in range(10)
    }
    by = label_merge.kappa_by_type({"A": a, "B": b})
    assert by["거짓_과장"][0] == pytest.approx(1.0), by
    assert by["비방광고"][0] == pytest.approx(1.0), by
    # 반대 대조 — 묶음 κ 는 같은 쌍을 절반 불일치로 센다
    k, n, agree = label_merge.kappa(a, b)
    assert agree == 10 and n == 20, "🔴 대조가 무의미하다 — 묶음 κ 도 부분합의를 일치로 셌다"


def test_유형별_κ_는_범위밖_쌍을_빼고_잰다() -> None:
    a = {"k1": labels.OUT_OF_SCOPE, "k2": "거짓_과장", "k3": "비방광고"}
    b = {"k1": "거짓_과장", "k2": "거짓_과장", "k3": "거짓_과장"}
    by = label_merge.kappa_by_type({"A": a, "B": b})
    assert by["거짓_과장"][1] == 2, "🔴 범위밖이 낀 쌍을 셌다"


# ── ⑤ 2차 판 사고 ─────────────────────────────────────────────


@pytest.fixture
def sheet(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "sheet.jsonl"
    rows = [{"문구": "5미크론 이상 입자 제거효율 99%"}, {"문구": "타사 제품보다 2배 빠릅니다"}]
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return p


def _csv(tmp: pathlib.Path, sheet: pathlib.Path, recs: list[dict]) -> pathlib.Path:
    p = tmp / "박수진__sheet.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ls.HEADER)
        w.writeheader()
        for r in recs:
            w.writerow({k: r.get(k, "") for k in ls.HEADER})
    return p


def test_세미콜론_구분자를_읽는다() -> None:
    assert ls.parse_no("1;2;3", 1) == list(ls.TYPES[:3])
    assert ls.parse_no("6; 7", 1) == [ls.TYPES[5], ls.TYPES[6]]


def test_지문은_글자_접두어를_달고_나간다(sheet, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ls, "OUT_DIR", tmp_path)
    out = ls.export(sheet, "누구", None, quiet=True)
    rec = next(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert rec["지문"] == ls.csv_fp(rec["문구"]), (
        "🔴 내보낸 지문에 접두어가 없다 — 엑셀이 숫자로 바꿀 수 있다"
    )


def test_깨진_지문이라도_문구가_같으면_받고_문구를_고치면_멈춘다(
    sheet, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    rows = ls._rows(sheet)
    t0, t1 = ls._text(rows[0]), ls._text(rows[1])
    ok = _csv(
        tmp_path,
        sheet,
        [
            {"행": 1, "문구": t0, "유형번호": "8", "붙인이": "박수진", "지문": "7.69762E+11"},
            {"행": 2, "문구": t1, "유형번호": "6;8", "붙인이": "박수진", "지문": ls._fp(t1)},
        ],
    )
    assert ls.import_(ok, sheet, "2026-09-22") == 0
    got = [
        json.loads(x)
        for x in (tmp_path / "data/derived/labels/박수진__sheet.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [g["확정유형"] for g in got] == [["거짓_과장"], ["부당_비교광고", "거짓_과장"]]
    # 반대 대조 — 지문도 깨지고 문구도 바뀌면 멈춘다
    bad = _csv(
        tmp_path,
        sheet,
        [{"행": 1, "문구": t0 + " ", "유형번호": "8", "붙인이": "박수진", "지문": "7.69762E+11"}],
    )
    with pytest.raises(SystemExit, match="문구"):
        ls.import_(bad, sheet, "2026-09-22")


def test_row_matches_는_옛_지문과_새_지문을_둘_다_받는다() -> None:
    base = {"문구": "타사 제품보다 2배 빠릅니다"}
    t = base["문구"]
    assert ls.row_matches(base, {"문구": t, "지문": ls._fp(t)}) == (True, False)
    assert ls.row_matches(base, {"문구": t, "지문": ls.csv_fp(t)}) == (True, False)
    assert ls.row_matches(base, {"문구": t + "!", "지문": ls._fp(t)}) == (False, True)
