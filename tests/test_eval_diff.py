"""결과 파일 대조 도구 (🆕 2026-10-21 · D-348 보충 35 결정 2) — `scripts/eval_diff.py`.

지키는 것
  ① `diff` — 같은 id 의 바뀐 칸 · 분류 이동 · 한쪽에만 있는 칸은 세지 않고 알린다
  ② `equiv` — 고른 전제의 기록 = 품목만 넘긴 판정의 그 전제 분기(보이면) · 접혔으면 기록 · 위험도는 분기가 보일 때만
  ③ 옛 결과 파일(`product` · 분기 칸 없음)이면 멈춘다 — 없는 칸을 「같다」로 세지 않는다(D-220) · 짝이 없어도 멈춘다
  ④ 어긋난 행 · 불변식 행이 있으면 1 로 끝난다
"""

from __future__ import annotations

import json
import pathlib

import pytest

from scripts import eval_diff as ed

pytestmark = pytest.mark.gate


def _rec(**k: object) -> dict:
    base = {
        "class": "보류",
        "verdicts": ["hold"],
        "hold_reasons": ["low_conf"],
        "types": [],
        "cond_types": [],
        "questions": ["s0:subst"],
        "committed": False,
        "risk_max": "R1",
        "branches": {},
        "invariant": [],
    }
    return base | k


def _doc(rows: list[dict], **k: object) -> dict:
    return {"rows": rows, "judged_by": "x"} | k


def test_diff_는_바뀐_칸과_분류_이동을_센다() -> None:
    a = _doc([{"id": "1"} | _rec(), {"id": "2"} | _rec()])
    b = _doc(
        [
            {"id": "1"} | _rec(),
            {"id": "2"} | _rec(**{"class": "확정위반", "types": ["거짓_과장"]}),
            {"id": "3"} | _rec(),
        ]
    )
    d = ed.diff(a, b)
    assert d["changed_rows"] == 1 and d["by_field"] == {"class": 1, "types": 1}
    assert d["moves"] == {"보류 → 확정위반": 1} and d["only_b"] == ["3"]


def test_diff_는_한쪽에만_있는_칸을_세지_않는다() -> None:
    a = _doc([{"id": "1", "class": "보류"}])
    b = _doc([{"id": "1", "class": "보류", "questions": ["s0:subst"]}])
    d = ed.diff(a, b)
    assert d["changed_rows"] == 0 and d["fields_only_b"] == ["questions"]


def _cat(row: dict) -> dict:
    return {"product": {"category": "식품", "premise": None}} | row


def _chosen(row: dict, premise: str = "식품") -> dict:
    return {"product": {"category": "식품", "premise": premise}} | row


def test_equiv_분기가_보이면_그_전제_분기와_맞댄다() -> None:
    branch = {
        k: v for k, v in _rec(**{"class": "x"}).items() if k in (*ed.EQUIV_FIELDS, ed.EQUIV_RISK)
    }
    cat = _doc(
        [
            _cat(
                {"id": "1"}
                | _rec(
                    hold_reasons=["premise_unknown"],
                    branches={"식품": branch, "일반식품_기능성": {}},
                )
            )
        ]
    )
    ok = _doc([_chosen({"id": "1"} | _rec())])
    assert ed.equiv(cat, ok)["mismatch"] == 0
    bad = _doc([_chosen({"id": "1"} | _rec(questions=[]))])
    e = ed.equiv(cat, bad)
    assert (
        e["mismatch"] == 1 and e["by_field"] == {"questions": 1} and e["rows"][0]["where"] == "분기"
    )


def test_equiv_접혔으면_기록과_맞대고_위험도는_보지_않는다() -> None:
    cat = _doc([_cat({"id": "1"} | _rec(risk_max="R2"))])  # 접힌 기록의 위험도 = 전제 최댓값
    chosen = _doc([_chosen({"id": "1"} | _rec(risk_max="R1"))])
    e = ed.equiv(cat, chosen)
    assert e["mismatch"] == 0 and e["folded"] == 1


def test_equiv_옛_결과_파일이면_멈춘다() -> None:
    old = _doc([{"id": "1"} | _rec()])
    with pytest.raises(SystemExit, match="product"):
        ed.equiv(old, _doc([_chosen({"id": "1"} | _rec())]))
    cat = _doc([_cat({"id": "1"} | _rec(branches={"식품": {"types": []}}))])
    with pytest.raises(SystemExit, match="보충 35 전"):
        ed.equiv(cat, _doc([_chosen({"id": "1"} | _rec())]))


def test_equiv_짝이_없으면_멈춘다() -> None:
    a = _doc([_chosen({"id": "1"} | _rec())])  # 앞 파일도 전제를 고른 판정 — 짝이 아니다
    with pytest.raises(SystemExit, match="짝"):
        ed.equiv(a, a)


def test_main_어긋나면_1(tmp_path: pathlib.Path) -> None:
    cat = tmp_path / "c.json"
    ch = tmp_path / "d.json"
    cat.write_text(json.dumps(_doc([_cat({"id": "1"} | _rec())])), encoding="utf-8")
    ch.write_text(json.dumps(_doc([_chosen({"id": "1"} | _rec(questions=[]))])), encoding="utf-8")
    assert ed.main(["equiv", str(cat), str(ch)]) == 1
    ch.write_text(json.dumps(_doc([_chosen({"id": "1"} | _rec())])), encoding="utf-8")
    assert ed.main(["equiv", str(cat), str(ch), "--out", str(tmp_path / "o.json")]) == 0
    assert json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))["pairs"] == 1
    ch.write_text(
        json.dumps(_doc([_chosen({"id": "1"} | _rec(invariant=["불변식 ①"]))])), encoding="utf-8"
    )
    assert ed.main(["equiv", str(cat), str(ch)]) == 1


def test_load_는_겹친_id_를_거부(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps(_doc([{"id": "1"}, {"id": "1"}])), encoding="utf-8")
    with pytest.raises(SystemExit, match="같은 id"):
        ed.load(p)
