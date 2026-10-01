"""판정표 · 감사표를 공유 저장소에 둔다 (`scripts/sheet_share.py`) · 감사 두 표를 들여온다 (🆕 2026-10-01 · 팀장 판정 (나)).

🔴 무엇을 막나
   ① 사람이 채운 표를 새 빈 표가 **덮는 것** — 채운 행이 하나라도 있으면 건너뛴다 (D-220)
   ② 팀 내부 공유도 안 되는 원천을 받은 기기가 표를 올리는 것 — `data-publish` 와 같은 함수 (D-303 · D-99)
   ③ 채운 감사표가 **기록으로 갈 길이 없는 것** — 해설서 위반문구 · 인정 조건문 감사 (⬜ 이었던 읽는 명령)
   ④ 판정자가 빈 행 · 채택 행이 아닌 행이 섞여도 일부만 쓰는 것 — 하나라도 있으면 아무것도 안 쓴다
   ⑤ 사본 기기가 `labels/`(원천)에 쓰는 것 — 들여오기는 정본에서만 (D-226)
"""

from __future__ import annotations

import csv
import json
import pathlib

import pytest

from collect import statute
from scripts import guide_statute_round as gs
from scripts import sheet_share as sh


def _csv(path: pathlib.Path, head: list[str], rows: list[list[str]]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows(rows)
    return path


HEAD = ["지문", "문구", "조건", "판정자"]


@pytest.fixture
def shareable(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setattr(sh.ds, "_noredist_seen", lambda: [])


@pytest.mark.gate
def test_채운_표는_덮지_않고_빈_표만_새_판으로_바꾼다(tmp_path, shareable) -> None:
    local, store = tmp_path / "build", tmp_path / "store"
    _csv(local / "a__팀장판정표.csv", HEAD, [["k1", "문", "", ""]])
    _csv(local / "감사_J6" / "b.csv", HEAD, [["k2", "문", "", ""], ["k3", "문", "", ""]])
    _csv(local / "c.csv", ["지문", "문구"], [["k", "x"]])  # 판정자 칸이 없으면 표가 아니다
    _csv(local / "same.csv", HEAD, [["k", "x", "", ""]])
    dest = store / sh.LAYOUT
    _csv(dest / "a__팀장판정표.csv", HEAD, [["k1", "문", "D", "오한빈"]])  # 채우는 중
    _csv(dest / "감사_J6" / "b.csv", HEAD, [["k2", "문", "", ""]])  # 옛 빈 표
    (dest / "same.csv").write_bytes((local / "same.csv").read_bytes())

    plan = {p["rel"]: p["act"] for p in sh.plan_push(sh.local_sheets(local), local, dest)}
    assert plan == {
        "a__팀장판정표.csv": "채우는 중 · 덮지 않음 (1행 채움)",
        "same.csv": "같음",
        "감사_J6/b.csv": "빈 표 교체",
    }
    filled_before = (dest / "a__팀장판정표.csv").read_bytes()
    assert sh.push(base=local, root=store) == 0
    assert (dest / "a__팀장판정표.csv").read_bytes() == filled_before, "🚨 사람이 채운 표를 덮었다"
    assert sh.filled(dest / "감사_J6" / "b.csv") == (0, 2)
    (old,) = (dest / sh.OLD).rglob("b.csv")
    assert sh.filled(old) == (0, 1), "옛 빈 표는 _old 에 남는다"
    assert not (dest / "c.csv").exists()


@pytest.mark.gate
def test_팀_공유가_안_되는_원천을_받은_기기는_표를_올리지_않는다(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sh.ds, "_noredist_seen", lambda: ["x (받은 기기 ['c2'])"])
    _csv(tmp_path / "build" / "a.csv", HEAD, [["k", "x", "", ""]])
    assert sh.push(base=tmp_path / "build", root=tmp_path / "store") == 1
    assert not (tmp_path / "store").exists()


@pytest.mark.gate
def test_현황은_표마다_들여오는_명령을_가른다(tmp_path) -> None:
    gf = _csv(tmp_path / "guide_fix__팀장판정표.csv", HEAD, [])
    ga = _csv(
        tmp_path / "x.csv",
        [
            "지문",
            "표",
            "제품유형",
            "문구",
            "주근거",
            "부근거",
            "조건",
            "제외목",
            "원천결손",
            "메모",
            "판정자",
        ],
        [],
    )
    ca = _csv(tmp_path / "y.csv", ["지문", "원천", "문구", "조건", "메모", "판정자"], [])
    ra = _csv(tmp_path / "z.csv", ["지문", "문구", *gs.AUDIT_TAIL], [])
    assert [sh.kind_of(p) for p in (gf, ga, ca, ra)] == [
        "gf-import-decisions",
        "audit-import",
        "caution-audit-import",
        "<판>-audit",
    ]


# ── 감사 두 표 들여오기 ────────────────────────────────────────────────


GA_HEAD = [
    "지문",
    "표",
    "제품유형",
    "문구",
    "주근거",
    "부근거",
    "조건",
    "제외목",
    "원천결손",
    "메모",
    "판정자",
]


@pytest.fixture
def canonical(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setattr(gs, "_canonical_only", lambda what: None)


def _adopted(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    ad = tmp_path / "adopted.jsonl"
    rows = [
        {"지문": "g1", "판독": "독립판독_합의", "조건": "C", "근거": [statute.food(1)]},
        {
            "지문": "g2",
            "판독": "독립판독_합의",
            "조건": "B",
            "근거": [],
            "근거_후보": [[statute.food(4)], [statute.food(7)]],
        },
        {"지문": "g3", "판독": "독립판독_합의", "조건": "D", "근거": []},
        {"지문": "g4", "판독": "팀장판정", "조건": "C", "근거": [statute.food(1)]},
    ]
    ad.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    monkeypatch.setattr(gs, "ADOPTED", ad)


@pytest.mark.gate
def test_해설서_감사표를_들여와_합의_정확도를_낸다(tmp_path, monkeypatch, canonical) -> None:
    _adopted(tmp_path, monkeypatch)
    f = _csv(
        tmp_path / "ga.csv",
        GA_HEAD,
        [
            ["g1", "", "", "", "1", "", "C", "", "", "", "오한빈"],  # 같다
            ["g2", "", "", "", "7", "", "B", "", "", "", "오한빈"],  # 후보 하나와 같다
            ["g3", "", "", "", "", "", "M", "", "", "", "오한빈"],  # 조건이 다르다
            ["g9", "", "", "", "", "", "", "", "", "", ""],  # 안 본 행 — 건너뜀
        ],
    )
    out = tmp_path / "audit.jsonl"
    r = gs.guide_audit(f, out)
    assert (r["감사"], r["일치"], r["불일치"]) == (3, 2, ["g3"])
    with pytest.raises(SystemExit, match="덮지 않는다"):
        gs.guide_audit(f, out)


@pytest.mark.gate
@pytest.mark.parametrize(
    ("row", "why"),
    [
        (["g1", "", "", "", "1", "", "C", "", "", "", ""], "판정자"),
        (["g4", "", "", "", "1", "", "C", "", "", "", "오한빈"], "합의 채택 행이 아니다"),
        (["g1", "", "", "", "9.가", "", "C", "", "", "", "오한빈"], "근거 코드"),
    ],
)
def test_해설서_감사표에_문제_행이_있으면_아무것도_안_쓴다(
    tmp_path, monkeypatch, canonical, row, why
) -> None:  # noqa: ANN001
    _adopted(tmp_path, monkeypatch)
    ok = ["g3", "", "", "", "", "", "D", "", "", "", "오한빈"]
    f = _csv(tmp_path / "ga.csv", GA_HEAD, [ok, row])
    out = tmp_path / "audit.jsonl"
    with pytest.raises(SystemExit, match=why):
        gs.guide_audit(f, out)
    assert not out.exists()


@pytest.mark.gate
def test_인정_조건문_감사는_D_를_적은_비율이다(tmp_path, monkeypatch, canonical) -> None:
    from preprocess import split as sp

    monkeypatch.setattr(sp, "caution_docs", lambda: [{"doc_id": "c1"}, {"doc_id": "c2"}])
    head = ["지문", "원천", "문구", "조건", "메모", "판정자"]
    f = _csv(
        tmp_path / "ca.csv",
        head,
        [["c1", "", "", "D", "", "오한빈"], ["c2", "", "", "L", "", "오한빈"]],
    )
    r = gs.caution_audit(f, tmp_path / "a.jsonl")
    assert (r["감사"], r["일치"], r["정확도"]) == (2, 1, "50.0%")
    bad = _csv(tmp_path / "cb.csv", head, [["zz", "", "", "D", "", "오한빈"]])
    with pytest.raises(SystemExit, match="인정 조건문에 없다"):
        gs.caution_audit(bad, tmp_path / "b.jsonl")
    empty = _csv(tmp_path / "cc.csv", head, [["c1", "", "", "", "", ""]])
    with pytest.raises(SystemExit, match="0"):
        gs.caution_audit(empty, tmp_path / "c.jsonl")


@pytest.mark.gate
def test_들여오기는_정본에서만이다(tmp_path, monkeypatch) -> None:
    from scripts import derived_manifest as dm

    monkeypatch.setattr(dm, "not_canonical", lambda what: f"🔴 {what} 는 정본(클론 B)에서만")
    f = _csv(tmp_path / "ca.csv", ["지문", "원천", "문구", "조건", "메모", "판정자"], [])
    with pytest.raises(SystemExit, match="정본"):
        gs.caution_audit(f, tmp_path / "a.jsonl")
    with pytest.raises(SystemExit, match="정본"):
        gs.guide_audit(f, tmp_path / "b.jsonl")
