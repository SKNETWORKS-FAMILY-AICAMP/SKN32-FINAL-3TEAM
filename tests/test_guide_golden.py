"""해설서 조문·조건 판이 **평가에 들어가는 길** (2026-09-25 · D-285 개정 4 · 지시서 §7 선행 게이트).

🔴 무엇을 막나
   ① 판정 대기 행이 남았는데 해설서가 평가에 들어가는 것 — 가장 어려운 행이 빠진 평가셋 · 평가셋이 두 번 바뀐다
   ② 조건 M(보류) · D(판정 대상 아님) · 근거가 후보로만 있는 행이 **적법 표본**으로 세지는 것
   ③ 후보가 있는 행을 「둘 다 걸린다」로 채점하는 것 — 어느 쪽이든 정답이다 (D-285 개정 2)
   ④ 조건 칸이 없는 DB 에 M · D 행이 빈 위반으로 들어가 적법으로 읽히는 것
   ⑤ 사람 판정이 합의 게이트(3.나 유형 · 조제유류 목 · 판정자)를 건너뛰는 것
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import statute
from preprocess import golden, split
from scripts import guide_statute_round as g


def _write(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _adopted(k: str, cond: str, cites: list[str], cand=None) -> dict:
    return {
        "지문": k,
        "문구": f"문구 {k}",
        "조건": cond,
        "근거": cites,
        "근거_후보": cand or [],
        "판독": "독립판독_합의",
        "원천결손": False,
        "labels": statute.types_of(cites),
    }


@pytest.fixture
def guide(tmp_path, monkeypatch):
    rd, ad = tmp_path / "readings.jsonl", tmp_path / "adopted.jsonl"
    monkeypatch.setattr(split, "GUIDE_READINGS", rd)
    monkeypatch.setattr(split, "GUIDE_ADOPTED", ad)
    return rd, ad


@pytest.mark.gate
def test_대기가_남으면_해설서는_평가에_없다(guide) -> None:
    rd, ad = guide
    _write(rd, [{"지문": "gs:a"}, {"지문": "gs:b"}])
    _write(ad, [_adopted("gs:a", "C", [statute.food(1)])])
    assert split.guide_state() == {"전체": 2, "채택": 1, "대기": 1}
    assert split.guide_docs() == []
    assert ad not in split.inputs()  # 대기 중에는 분할의 입력이 아니다 — 봉인 파일이 안 바뀐다


@pytest.mark.gate
def test_대기가_0_이면_조건과_함께_들어간다(guide) -> None:
    rd, ad = guide
    _write(rd, [{"지문": "gs:a"}, {"지문": "gs:b"}])
    _write(ad, [_adopted("gs:a", "C", [statute.food(1)]), _adopted("gs:b", "M", [])])
    docs = split.guide_docs()
    assert [d["조건"] for d in docs] == ["C", "M"]
    assert docs[1]["유형"] == [] and docs[1]["원천"] == "mfds_special_use_guide"
    assert ad in split.inputs()  # 전환 순간 입력이 늘어 분할을 다시 쓰게 된다


@pytest.mark.gate
def test_원자료에_없는_채택_행이면_멈춘다(guide) -> None:
    rd, ad = guide
    _write(rd, [{"지문": "gs:a"}])
    _write(ad, [_adopted("gs:z", "C", [statute.food(1)])])
    with pytest.raises(ValueError):
        split.guide_state()


@pytest.mark.gate
def test_조건_칸이_있으면_빈_유형이_적법이_아니다() -> None:
    base = {"text": "t", "labels": [], "근거": []}
    assert golden.is_negative(base)  # 조건 칸 없는 행 — 종전 규칙 그대로
    for cond in ("M", "D", "C"):
        assert not golden.is_negative({**base, "조건": cond})
    assert golden.is_positive(
        {**base, "조건": "C", "근거_후보": [[statute.food(4)], [statute.food(5)]]}
    )
    assert not golden.is_positive({**base, "조건": "M"})


@pytest.mark.gate
def test_조건_칸의_꼴을_검사한다() -> None:
    ok = {
        "id": "x",
        "labels": [],
        "근거": [],
        "조건": "C",
        "근거_후보": [[statute.food(4)], [statute.food(5)]],
    }
    golden.check_basis([ok])
    for bad in (
        {**ok, "근거_후보": []},  # C 인데 근거도 후보도 없다
        {
            **ok,
            "조건": "D",
            "근거": [statute.food(4)],
            "labels": statute.types_of([statute.food(4)]),
        },
        {**ok, "조건": "X"},
    ):
        with pytest.raises(SystemExit):
            golden.check_basis([bad])


@pytest.mark.gate
def test_판정기_B_는_M_D_를_채점하지_않고_후보는_어느_쪽이든_정답() -> None:
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import eval_rule

    assert not eval_rule.scored({"조건": "M"}) and not eval_rule.scored({"조건": "D"})
    assert eval_rule.scored({"조건": "C"}) and eval_rule.scored({})
    r = {"labels": [], "근거": [], "근거_후보": [[statute.food(4)], [statute.food(5)]]}
    assert eval_rule.truth_types(r, {"소비자_기만"}) == {"소비자_기만"}  # 5호를 맞히면 5호가 정답
    assert eval_rule.truth_types(r, set()) == {"거짓_과장"}  # 못 맞히면 앞 후보 — 정답 하나로 센다
    assert eval_rule.truth_ho(r, {statute.food(5)}) == {statute.food(5)}


@pytest.mark.gate
def test_DB_에는_조건_칸_없는_M_D_후보_행을_넣지_않는다(monkeypatch) -> None:
    from scripts import load_db

    row = {
        "id": "gs:a#0",
        "text": "t",
        "근거": [],
        "labels": [],
        "unit": "문장",
        "origin": "real",
        "provenance": "mfds_special_use_guide",
        "redistributable": False,
        "split": "test_sentence",
    }
    rows = [
        {**row, "id": "m", "조건": "M"},
        {**row, "id": "d", "조건": "D"},
        {**row, "id": "c", "조건": "C", "근거_후보": [[statute.food(4)], [statute.food(5)]]},
        {
            **row,
            "id": "ok",
            "조건": "C",
            "근거": [statute.food(1)],
            "labels": statute.types_of([statute.food(1)]),
        },
    ]
    monkeypatch.setattr(load_db, "_jsonl_at", lambda *_a, **_k: rows)
    n, stat, _ = load_db.load_golden(None, True)
    assert n == 1 and stat["DB미적재_조건칸없음"] == 3


def _src(k: str, text: str = "문구", kind: str = "9. 체중조절용 조제식품") -> dict:
    return {"표": 1, "제품유형": kind, "원천라벨": "x", "문구": text, "원천": "t"}


@pytest.mark.gate
def test_팀장_판정이_판독을_덮고_거래조건은_대기(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(g, "ADOPTED", tmp_path / "adopted.jsonl")
    monkeypatch.setattr(g, "SHEET", tmp_path / "sheet.csv")
    monkeypatch.setattr(g, "TEAM_SHEET", tmp_path / "team.csv")
    src = {
        "gs:a": _src("gs:a"),
        "gs:b": _src("gs:b", "가격 경쟁력 면에서 장점 보유"),
        "gs:c": _src("gs:c"),
    }
    r = g.parse_line("gs:x\t5.다\t-\tC\t-\tN\t")
    m = g.parse_line("gs:x\t-\t-\tM\t-\tN\t")
    a = {"gs:a": r, "gs:b": r, "gs:c": r}
    b = {"gs:a": r, "gs:b": r, "gs:c": m}  # c 는 C↔M — 시트
    dec = {
        "gs:c": {
            "지문": "gs:c",
            "판정": g.parse_line("gs:c\t1\t-\tC\t-\tN\t묶음 2"),
            "판정자": "OHB",
        }
    }
    got = g.decide(src, a, b, dec)
    rows = {
        x["지문"]: x for x in map(json.loads, g.ADOPTED.read_text(encoding="utf-8").splitlines())
    }
    assert set(rows) == {"gs:a", "gs:c"}  # b 는 거래 조건 — 합의여도 대기 (D-272 개정)
    assert rows["gs:c"]["판독"] == "팀장판정" and rows["gs:c"]["근거"] == [statute.food(1)]
    assert got["시트_이유"] == {"거래조건": 1}
    assert "판독1" in g.TEAM_SHEET.read_text(encoding="utf-8-sig").splitlines()[0]


@pytest.mark.gate
def test_판정_가져오기는_판정자와_게이트를_지키고_반쯤_쓰지_않는다(tmp_path, monkeypatch) -> None:
    rd = tmp_path / "readings.jsonl"
    _write(rd, [{"지문": "gs:a"}, {"지문": "gs:b"}])
    monkeypatch.setattr(g, "READINGS", rd)
    monkeypatch.setattr(g, "ADOPTED", tmp_path / "none.jsonl")
    monkeypatch.setattr(g, "DECISIONS", tmp_path / "decisions.jsonl")
    head = ",".join(g.TEAM_COLS) + "\n"

    def csv_of(*lines: str) -> pathlib.Path:
        p = tmp_path / "in.csv"
        p.write_text(head + "".join(x + "\n" for x in lines), encoding="utf-8-sig")
        return p

    row = "gs:a,문구,9. 체중조절용,x,사유,p1,p2,{prim},-,{cond},{exc},N,메모,{who}"
    good = row.format(prim="1", cond="C", exc="-", who="OHB")
    with pytest.raises(SystemExit):  # 판정자 빈 행 — 전부 거부
        g.import_decisions(
            csv_of(good, row.format(prim="4", cond="B", exc="-", who="").replace("gs:a", "gs:b", 1))
        )
    assert not g.DECISIONS.exists()
    with pytest.raises(SystemExit):  # 3.나 는 유형 9 만
        g.import_decisions(
            csv_of(
                row.format(prim="3", cond="A", exc="3.나", who="OHB").replace(
                    "9. 체중조절용", "5. 환자용"
                )
            )
        )
    got = g.import_decisions(
        csv_of(good, "gs:b,문구,9.,x,사유,p1,p2,,,,,,,")
    )  # 조건 빈 행은 건너뛴다
    assert got["받음"] == 1 and got["건너뜀(조건 빈 행)"] == 1
    rec = json.loads(g.DECISIONS.read_text(encoding="utf-8"))
    assert (
        rec["판정자"] == "OHB"
        and rec["판정"]["근거"] == [statute.food(1)]
        and "문제" not in rec["판정"]
    )
