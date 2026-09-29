"""화장품 질의응답집 조문·조건 판 — 판독 → 채택 → 골든셋 경로 (2026-09-30 · D-285 개정 5 · 화장품 지시서 09-25 §5 · §7).

🔴 무엇을 막나
   ① 적법(L) ↔ 그 밖의 갈림이 보수 합성으로 **위반이나 보류로 채택**되는 것 — 기대 응답이 정반대다 (지시서 §5)
   ② 조건 L 행이 위반으로도 적법으로도 안 세져 **조용히 빠지는** 것 (지시서 §7 · D-220)
   ③ 대상 N(광고 표현 아님) 행이 평가에 들어가거나 **대기로 세지는** 것
   ④ 삭제된 호(화장품법 §13①3) · §1-1 표와 어긋난 [별표 5] 목이 합의로 채택되는 것
   ⑤ 원천에서 사라진 문구가 단위 표에 남아 채택되는 것 — 지문 규칙을 못 되살려 원천 대조로 막는다
   ⑥ 팀장 판정표 13 이 끝나기 전에 화장품 행이 평가에 들어가는 것 (해설서와 같은 대기 규칙)
   ⑦ 판정자가 빈 판정 · 합의 채택이 아닌 감사 행이 받아들여지는 것
"""

from __future__ import annotations

import csv
import json
import pathlib

import pytest

from collect import statute
from preprocess import golden, split
from scripts import guide_statute_round as g

C1 = statute.cite(*statute.COSM, 1)
C4 = statute.cite(*statute.COSM, 4)


def _r(target="Y", prim="1", sec="-", mok="가", cond="C", exc="-", key="cq:x"):
    return g.cq_parse_line(f"{key}\t{target}\t{prim}\t{sec}\t{mok}\t{cond}\t{exc}\t")


def _jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def cq(tmp_path, monkeypatch):
    """화장품 판의 경로를 전부 임시 폴더로 — 실제 판정표 · 원자료를 덮지 않는다."""
    d = tmp_path / "cq"
    for name, fn in (
        ("CQ_READINGS", "readings.jsonl"),
        ("CQ_ADOPTED", "adopted.jsonl"),
        ("CQ_DECISIONS", "decisions.jsonl"),
        ("CQ_AUDIT", "audit.jsonl"),
        ("CQ_TEAM_SHEET", "team.csv"),
    ):
        monkeypatch.setattr(g, name, d / fn)
    qa = tmp_path / "qa.jsonl"
    _jsonl(
        qa,
        [
            {"분야": "화장품", "문항": "1", "인용표현": ["보톡스 대신", "화장품법"]},
            {"분야": "화장품", "문항": "2", "인용표현": ["최고의 크림", "피지", "천연 성분"]},
            {"분야": "의료기기", "문항": "1", "인용표현": ["다른 분야"]},
        ],
    )
    monkeypatch.setattr(g, "CQ_QA", qa)
    monkeypatch.setattr(split, "COSMETIC_READINGS", d / "readings.jsonl")
    monkeypatch.setattr(split, "COSMETIC_ADOPTED", d / "adopted.jsonl")
    units = [
        {"지문": "cq:aaaaaaaaaaaa", "문항": 1, "자리": "질의", "문구": "보톡스 대신"},
        {"지문": "cq:bbbbbbbbbbbb", "문항": 2, "자리": "답변", "문구": "최고의 크림"},
        {"지문": "cq:cccccccccccc", "문항": 2, "자리": "답변", "문구": "피지"},
        {"지문": "cq:dddddddddddd", "문항": 2, "자리": "답변", "문구": "천연 성분"},
    ]
    up = tmp_path / "units.json"
    up.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    head = "지문\t대상\t주근거\t부근거\t별표5목\t조건\t제외목\t메모\n"
    r1 = tmp_path / "r1.tsv"
    r1.write_text(
        head
        + "cq:aaaaaaaaaaaa\tY\t4\t1\t아\tC\t-\t\n"
        + "cq:bbbbbbbbbbbb\tY\t4\t-\t바\tC\t-\t\n"
        + "cq:cccccccccccc\tN\t-\t-\t-\t-\t-\t해부 용어\n"
        + "cq:dddddddddddd\tY\t-\t-\t-\tL\t-\t\n",
        encoding="utf-8",
    )
    r2 = tmp_path / "r2.tsv"
    r2.write_text(
        head
        + "cq:aaaaaaaaaaaa\tY\t4\t-\t아\tC\t-\t\n"
        + "cq:bbbbbbbbbbbb\tY\t4\t-\t바\tB\t-\t\n"
        + "cq:cccccccccccc\tN\t-\t-\t-\t-\t-\t\n"
        + "cq:dddddddddddd\tY\t-\t-\t-\tM\t-\t\n",
        encoding="utf-8",
    )
    return up, r1, r2


# ── 판독 한 줄 ─────────────────────────────────────────────────────────────────


@pytest.mark.gate
def test_화장품_판독_꼴과_인용() -> None:
    r = _r()
    assert r["근거"] == [C1] and r["별표5목"] == "가" and not r["문제"]
    assert g.cq_parse_line("cq:x\tY\t공3\t-\t-\tB\t실증\t")["근거"] == [statute.fair(3)]


@pytest.mark.gate
def test_삭제된_3호와_표에_어긋난_목은_판독_문제다() -> None:
    assert _r(prim="3", mok="-")["문제"]  # §13①3 은 2025-01-31 삭제
    assert _r(prim="4", mok="가")["문제"]  # 가 목은 1호
    assert _r(prim="-", mok="바", cond="M")["문제"]  # 목만 있고 호가 없다
    assert _r(mok="타")["문제"]
    assert _r(exc="3.라")["문제"]  # 식품 제외목은 화장품 예외가 아니다


@pytest.mark.gate
def test_대상_N_은_뒤_칸이_비어야_하고_L_D_는_근거가_빈다() -> None:
    assert not _r("N", "-", "-", "-", "-")["문제"]
    assert _r("N", "1", "-", "-", "C")["문제"]
    assert _r(cond="L", mok="-")["문제"]  # L 인데 1호가 적혔다
    assert not _r(prim="-", mok="-", cond="L")["문제"]


# ── 채택 규칙 ─────────────────────────────────────────────────────────────────


@pytest.mark.gate
def test_L_은_합성하지_않는다() -> None:
    l_ = _r(prim="-", mok="-", cond="L")
    got, why = g.cq_agree(l_, l_)
    assert why == "" and got["조건"] == "L" and got["근거"] == []
    for other in (_r(prim="-", mok="-", cond="M"), _r(prim="-", mok="-", cond="D"), _r()):
        got, why = g.cq_agree(l_, other)
        assert got is None and "L" in why


@pytest.mark.gate
def test_대상이_갈리면_시트_둘_다_N_이면_대상아님() -> None:
    n = _r("N", "-", "-", "-", "-")
    assert g.cq_agree(n, n) == ({"대상": "N"}, "")
    got, why = g.cq_agree(n, _r())
    assert got is None and why.startswith("대상")


@pytest.mark.gate
def test_보수_합성과_목은_같을_때만() -> None:
    got, _ = g.cq_agree(_r(prim="4", mok="사", cond="C"), _r(prim="4", mok="사", cond="B"))
    assert got["조건"] == "C" and got["조건_이견"] == ["B", "C"] and got["별표5목"] == "사"
    got, _ = g.cq_agree(_r(prim="4", mok="사"), _r(prim="4", mok="아"))
    assert got["근거"] == [C4] and got["별표5목"] == ""
    got, _ = g.cq_agree(_r(prim="1", mok="가"), _r(prim="4", mok="사"))
    assert (
        got["근거"] == [] and got["근거_후보"] and got["별표5목"] == ""
    )  # 호가 갈리면 목을 싣지 않는다


# ── 원천 대조 · 원자료 ────────────────────────────────────────────────────────


@pytest.mark.gate
def test_원천에_없는_문구가_단위에_있으면_멈춘다(cq, tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps([{"지문": "cq:aaaaaaaaaaaa", "문항": 1, "자리": "질의", "문구": "없는 문구"}]),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="원천과 어긋난다"):
        g.cq_units(json.loads(bad.read_text(encoding="utf-8")))


@pytest.mark.gate
def test_합치고_다시_계산해도_채택이_같다(cq) -> None:
    up, r1, r2 = cq
    got = g.cq_merge(up, r1, r2)
    first = g.CQ_ADOPTED.read_bytes()
    assert got["채택"] == 3 and got["채택_대상아님(N)"] == 1 and got["시트"] == 1  # L↔M 은 시트
    assert g.cq_rebuild() == got and g.CQ_ADOPTED.read_bytes() == first
    rows = {json.loads(x)["지문"]: json.loads(x) for x in first.decode().splitlines()}
    assert rows["cq:aaaaaaaaaaaa"]["근거"] == [C4] and rows["cq:aaaaaaaaaaaa"]["별표5목"] == "아"
    assert rows["cq:bbbbbbbbbbbb"]["조건"] == "C"  # C↔B → C
    assert "labels" not in rows["cq:cccccccccccc"]


# ── 대기 규칙 · 골든셋 ───────────────────────────────────────────────────────


@pytest.mark.gate
def test_팀장_판정이_끝나기_전에는_평가에_없다(cq) -> None:
    up, r1, r2 = cq
    g.cq_merge(up, r1, r2)
    assert split.cosmetic_state() == {"전체": 4, "채택": 3, "대기": 1}  # N 은 대기가 아니다
    assert split.cosmetic_docs() == []
    assert split.COSMETIC_ADOPTED not in split.inputs()


def _fill(path: pathlib.Path, who: str, **cells) -> pathlib.Path:
    with g.CQ_TEAM_SHEET.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.update(cells, 판정자=who)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


@pytest.mark.gate
def test_판정자가_비면_아무것도_안_쓴다(cq, tmp_path) -> None:
    up, r1, r2 = cq
    g.cq_merge(up, r1, r2)
    sheet = _fill(tmp_path / "t.csv", "", 대상="Y", 조건="L")
    with pytest.raises(SystemExit, match="아무것도 쓰지 않았다"):
        g.cq_import_decisions(sheet)
    assert not g.CQ_DECISIONS.exists()


@pytest.mark.gate
def test_판정이_끝나면_L_은_적법으로_들어간다(cq, tmp_path) -> None:
    up, r1, r2 = cq
    g.cq_merge(up, r1, r2)
    sheet = _fill(tmp_path / "t.csv", "팀장", 대상="Y", 조건="L")
    assert g.cq_import_decisions(sheet)["받음"] == 1
    got = g.cq_rebuild()
    assert got["시트"] == 0 and got["채택_판독"] == {"독립판독_합의": 3, "팀장판정": 1}
    docs = {d["doc_id"]: d for d in split.cosmetic_docs()}
    assert set(docs) == {"cq:aaaaaaaaaaaa", "cq:bbbbbbbbbbbb", "cq:dddddddddddd"}  # N 은 빠진다
    assert docs["cq:aaaaaaaaaaaa"]["별표5목"] == "아"
    assert split.COSMETIC_ADOPTED in split.inputs()
    row = {"labels": docs["cq:dddddddddddd"]["유형"], "조건": "L", "근거": []}
    assert golden.is_negative(row) and not golden.is_positive(row)


@pytest.mark.gate
def test_L_은_적법_M_D_는_적법이_아니다() -> None:
    base = {"id": "x", "labels": [], "근거": []}
    assert golden.is_negative({**base, "조건": "L"})
    assert golden.is_negative(base)  # 조건 칸이 없는 승인 문구
    assert not golden.is_negative({**base, "조건": "M"})
    assert not golden.is_negative({**base, "조건": "D"})
    assert golden.is_positive({**base, "조건": "C", "근거": [C4]})  # 4호는 유형이 없어도 위반이다
    golden.check_basis([{**base, "조건": "L"}, {**base, "조건": "C", "근거": [C4]}])
    with pytest.raises(SystemExit):
        golden.check_basis([{**base, "조건": "L", "근거": [C4], "labels": []}])


# ── 합의 감사 ─────────────────────────────────────────────────────────────────


@pytest.mark.gate
def test_감사는_합의_채택_행만_받고_일치를_센다(cq, tmp_path) -> None:
    up, r1, r2 = cq
    g.cq_merge(up, r1, r2)
    cols = ["지문", "대상", "주근거", "부근거", "별표5목", "조건", "제외목", "메모", "판정자"]

    def sheet(rows):
        p = tmp_path / "audit.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        return p

    got = g.cq_audit(
        sheet(
            [
                [
                    "cq:aaaaaaaaaaaa",
                    "Y",
                    "4",
                    "-",
                    "사",
                    "C",
                    "-",
                    "",
                    "팀장",
                ],  # 목만 다르다 → 일치
                ["cq:bbbbbbbbbbbb", "Y", "4", "-", "바", "B", "-", "", "팀장"],  # 조건이 다르다
                ["cq:cccccccccccc", "N", "", "", "", "", "", "", "팀장"],
            ]
        )
    )
    assert (got["감사"], got["일치"], got["불일치"]) == (3, 2, ["cq:bbbbbbbbbbbb"])
    with pytest.raises(SystemExit, match="합의 채택 행이 아니다"):
        g.cq_audit(sheet([["cq:dddddddddddd", "Y", "-", "-", "-", "L", "-", "", "팀장"]]))
