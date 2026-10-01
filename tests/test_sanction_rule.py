"""위험도 하한 원천(`scripts/sanction_review.yaml`) · 원문 대조(`scripts/sanction_rule.py`) (🆕 2026-10-01 · W5 · D-305 · D-308).

🔴 무엇을 막나
   ① 원문과 다른 글자 위에서 서명하는 것 — 인용 · 1차 처분을 **원문 괘선 표**에서 못 찾으면 멈춘다 (D-149 · D-220)
   ② 위험도를 행마다 손으로 적어 처분 종류와 어긋나는 것 — 종류 → 위험도는 `KIND_RISK` 한 곳 (D-227 · D-99)
   ③ 범위 밖 유형(뒷광고 · D-255)에 하한이 생기는 것 · 같은 사람이 검증 · 확인하는 것 (D-66)
   ④ 원문이 없는 기기에서 대조 없이 「통과」가 찍히는 것 (D-220)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.contracts import Risk
from scripts import sanction_rule as sr

TABLE = "\n".join(
    [
        "  │라. 법 제8조제1항을 위반한 경우        │법 제14조 │            │            │",
        "  │ 1) 질병의 예방ㆍ치료에 효능이 있는    │          │영업정지    │영업허가    │",
        "  │것으로 인식할 우려가 있는 표시         │          │2개월과     │ㆍ등록 취소 │",
        "  │ 2) 식품등을 의약품으로 인식할 우려가  │          │영업정지    │영업정지    │",
        "  │있는 표시 또는 광고                    │          │15일        │1개월       │",
        "  │마. 법 제9조제3항을 위반한 경우        │법 제14조 │시정명령    │            │",
        "  │ 1) 식품등을 의약품으로 인식할 우려가  │          │영업정지    │            │",
        "  │있는 표시                              │          │99일        │            │",
    ]
)


def _spec(**row) -> dict:  # noqa: ANN003
    base = {
        "id": "t.1",
        "src": "food",
        "block": "라. 법 제8조제1항을 위반한 경우",
        "nth": 1,
        "mok": "2)",
        "quote": "식품등을 의약품으로 인식할 우려",
        "first": "영업정지15일",
        "kind": "영업정지",
        "type": "의약품_오인",
    }
    return {
        "sources": {"food": {"law_id": "013475", "annex_no": "0007", "path": "a.json"}},
        "rows": [base | row],
    }


@pytest.mark.gate
def test_원천_파일이_원문_없이도_지킬_규칙을_지킨다() -> None:
    """실제 원천 — 유형 · 처분 종류 · 사실 칸 · id · 범위 밖 · 서명 2인. 원문 대조는 원문이 있는 기기에서(`check`)."""
    spec = sr.load_rules()
    assert sr.lint(spec) == []
    kinds = {r["kind"] for r in spec["rows"]}
    assert kinds <= set(sr.KIND_RISK)
    assert not {r["type"] for r in spec["rows"]} & {v.value for v in sr.OUT_OF_SCOPE}, (
        "뒷광고는 D-255 범위 밖"
    )


@pytest.mark.gate
def test_원문_괘선_표에서_블록_안의_목과_1차_칸을_찾는다(tmp_path) -> None:
    (tmp_path / "a.json").write_text(
        json.dumps({"content": TABLE}, ensure_ascii=False), encoding="utf-8"
    )
    assert sr.verify(_spec(), tmp_path) == []
    # 1차 칸이 다르면 — 다음 블록(마.)의 같은 인용(99일)으로 새지 않는다
    bad = sr.verify(_spec(first="영업정지99일"), tmp_path)
    assert bad and "1차 칸" in bad[0]
    assert sr.verify(_spec(quote="원문에 없는 글자"), tmp_path)[0].startswith("t.1 블록 안에서")
    assert "처분 종류" in sr.verify(_spec(kind="품목제조정지", first="영업정지15일"), tmp_path)[0]


@pytest.mark.gate
def test_원문이_없는_기기에서는_대조_없이_통과하지_않는다(tmp_path) -> None:
    with pytest.raises(SystemExit, match="원문이 이 기기에 없다"):
        sr.verify(_spec(), tmp_path)


@pytest.mark.gate
def test_위험도는_처분_종류로만_정한다() -> None:
    """D-227 — 시정명령 · 시정조치 R1 · 정지 R2 · 취소 · 폐쇄 R3."""
    assert sr.KIND_RISK["시정명령"] is Risk.R1 and sr.KIND_RISK["시정조치"] is Risk.R1
    assert {sr.KIND_RISK[k] for k in ("영업정지", "품목제조정지", "광고업무정지")} == {Risk.R2}
    assert sr.KIND_RISK["영업허가등록취소"] is Risk.R3


@pytest.mark.gate
@pytest.mark.parametrize(
    ("row", "why"),
    [
        ({"type": "추천_보증_뒷광고"}, "범위 밖"),
        ({"kind": "과징금"}, "모르는 처분 종류"),
        ({"fact": "특허"}, "모르는 사실 칸"),
        ({"verified_by": "오한빈"}, "행에 서명 칸"),
        ({"type": "없는유형"}, "모르는 유형"),
    ],
)
def test_원천_규칙을_어기면_잡는다(row: dict, why: str) -> None:
    bad = sr.lint(_spec(**row))
    assert bad and why in bad[0], bad


@pytest.mark.gate
def test_하한_요약은_같은_법_안에서_max_이고_서명_전_행은_안_센다() -> None:
    spec = _spec()
    spec["rows"].append(spec["rows"][0] | {"id": "t.2", "kind": "시정명령", "first": "시정명령"})
    assert sr.floor_by_type(spec) == {}, "서명 전 판은 하한이 아니다 (v_risk_lookup)"
    assert sr.floor_by_type(spec, signed_only=False)["의약품_오인"] == {"013475": "R2"}
    spec["signoff"] = {"sha": sr.plan_sha(spec), "verified_by": "오한빈", "reviewed_by": "권소라"}
    assert sr.floor_by_type(spec)["의약품_오인"] == {"013475": "R2"}


@pytest.mark.gate
def test_별표5_목은_다음_목_머리까지다() -> None:
    text = "2. 화장품 표시ㆍ광고 시 준수사항\n 다. 문헌을 인용할 수 있으며 밝혀야 한다.\n 라. 외국제품을 국내제품으로"
    assert "밝혀야한다." in sr.mok_segment(text, "다")
    assert "외국제품" not in sr.mok_segment(text, "다")
    assert sr.mok_segment(text, "라").startswith("라.외국제품")


@pytest.mark.gate
def test_검토표는_서명_상태와_위험도를_싣는다(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "s.csv"
    assert sr.write_sheet(_spec(), out) == 1
    text = out.read_text(encoding="utf-8-sig")
    assert "R2" in text and "서명 전(안 쓴다)" in text


@pytest.mark.gate
def test_판_서명은_그_판에만_유효하고_한_글자만_바뀌어도_무효다() -> None:
    """🆕 2026-10-01 (D-309) — 판 단위 2인 서명. 서명 뒤 행이 바뀌면 서명이 남아 하한으로 쓰이는 사고를 막는다."""
    spec = _spec()
    assert sr.signature(spec) is None and sr.lint(spec) == []
    spec["signoff"] = {"sha": sr.plan_sha(spec), "verified_by": "오한빈", "reviewed_by": "권소라"}
    assert sr.signature(spec) == ("오한빈", "권소라") and sr.lint(spec) == []
    spec["rows"][0]["first"] = "영업정지1개월"  # 판이 바뀌었다
    assert sr.signature(spec) is None
    assert any("서명이 무효" in b for b in sr.lint(spec))
    same = _spec()
    same["signoff"] = {"sha": sr.plan_sha(same), "verified_by": "오한빈", "reviewed_by": "오한빈"}
    assert sr.signature(same) is None and any("같다" in b for b in sr.lint(same))
    nosha = _spec()
    nosha["signoff"] = {"sha": None, "verified_by": "오한빈", "reviewed_by": "권소라"}
    assert sr.signature(nosha) is None and any("sha 가 없다" in b for b in sr.lint(nosha))


@pytest.mark.gate
def test_판_sha_는_서명_칸을_보지_않는다() -> None:
    a = _spec()
    b = _spec()
    b["signoff"] = {"sha": "x", "verified_by": "가", "reviewed_by": "나"}
    assert sr.plan_sha(a) == sr.plan_sha(b)


def _food(rows: list[dict]) -> dict:
    spec = {
        "sources": {
            "food": {"law_id": "013475", "annex_no": "0007", "path": "a.json"},
            "cosm": {"law_id": "008741", "annex_no": "0007", "path": "b.json"},
        },
        "rows": rows,
    }
    spec["signoff"] = {"sha": sr.plan_sha(spec), "verified_by": "가", "reviewed_by": "나"}
    return spec


ROW = {"src": "food", "block": "b", "mok": "마)", "quote": "q", "first": "영업정지7일"}


@pytest.mark.gate
def test_식품_4_7호는_목이_맞을_때만_그_처분이고_아니면_그_밖에_R1() -> None:
    """🆕 2026-10-01 (D-310) — 유형 max 로 접으면 보통의 과장에 「영업정지 수준」이 붙는다. 목이 맞을 때만 그 행이다."""
    spec = _food(
        [
            ROW
            | {
                "id": "m",
                "kind": "영업정지",
                "type": "거짓_과장",
                "annex1": ["4.마"],
                "cover": "전부",
            },
            ROW | {"id": "d", "kind": "영업정지", "type": "의약품_오인"},
            {
                "id": "c",
                "src": "cosm",
                "block": "b",
                "mok": "2)",
                "quote": "q",
                "first": "f",
                "kind": "광고업무정지",
                "type": "거짓_과장",
            },
        ]
    )
    hit = sr.floor_of(spec, "거짓_과장", "013475", ["013094:제8조제1항제4호|마목"])
    assert (hit.floor, hit.ceiling, hit.basis) == (Risk.R2, None, ("m",)), (
        "목이 맞으면 그 행 · 상한 없음"
    )
    miss = sr.floor_of(spec, "거짓_과장", "013475", ["013094:제8조제1항제4호"])
    assert (miss.floor, miss.ceiling) == (Risk.R1, Risk.R2), (
        "목을 모르면 하한 그 밖에 R1 · 가능 상한 R2"
    )
    assert "4.마" in miss.ceiling_note and "업무정지" in miss.ceiling_note
    # 🚨 상한을 하한으로 올리지 않는다 (D-310 개정 (다))
    assert miss.floor is not miss.ceiling
    none = sr.floor_of(spec, "비방광고", "013475", [])
    assert (none.floor, none.ceiling) == (Risk.R1, None), "행이 없으면 그 밖에 R1 · 상한 없음"
    # 1~3호 · 화장품은 목으로 갈리지 않는다
    assert sr.floor_of(spec, "의약품_오인", "013475", []) == sr.Floor(Risk.R2, basis=("d",))
    assert sr.floor_of(spec, "거짓_과장", "008741", []) == sr.Floor(Risk.R2, basis=("c",))
    unsigned = dict(spec, signoff={})
    assert sr.floor_of(unsigned, "거짓_과장", "013475", []) == sr.Floor(None)
    assert sr.annex1_code("002011:제3조제1항제1호") is None, "표시광고법 인용은 별표1 목이 아니다"


@pytest.mark.gate
@pytest.mark.parametrize(
    ("row", "why"),
    [
        (
            ROW | {"id": "x", "kind": "영업정지", "type": "거짓_과장"},
            "annex1(별표1 목 목록)이 없다",
        ),
        (
            ROW | {"id": "x", "kind": "영업정지", "type": "의약품_오인", "annex1": ["2.가"]},
            "annex1 은 식품 4~7호 행에만",
        ),
        (
            ROW
            | {
                "id": "x",
                "kind": "영업정지",
                "type": "거짓_과장",
                "annex1": ["4마"],
                "cover": "전부",
            },
            "꼴이 아니다",
        ),
        (
            ROW | {"id": "x", "kind": "영업정지", "type": "거짓_과장", "annex1": ["4.마"]},
            "cover 가 없거나 틀렸다",
        ),
        (
            ROW
            | {
                "id": "x",
                "kind": "영업정지",
                "type": "거짓_과장",
                "annex1": ["4.마"],
                "cover": "대부분",
            },
            "cover 가 없거나 틀렸다",
        ),
        (
            ROW
            | {"id": "x", "kind": "영업정지", "type": "소비자_기만", "annex1": [], "cover": "일부"},
            "cover 는 annex1 목이 있는 행에만",
        ),
    ],
)
def test_목_칸_규칙(row: dict, why: str) -> None:
    spec = _food([row])
    bad = sr.lint(spec)
    assert any(why in b for b in bad), bad


@pytest.mark.gate
def test_원천의_10_01_판정_셋이_들어_있다() -> None:
    """🆕 2026-10-01 (D-310) — 하) 건기식 오인 · 화장품 2.다 기만 · 7호 행에는 사실 확인 분기가 없다."""
    rows = {r["id"]: r for r in sr.load_rules()["rows"]}
    assert rows["food.b1.4ha"]["type"] == "건강기능식품_오인"
    assert rows["cosm.2.da"]["type"] == "소비자_기만" and rows["cosm.2.da"]["rule"]["mok"] == "다"
    assert not rows["food.b1.4a.cmp"].get("fact") and not rows["food.b3.4sa.cmp"].get("fact")


@pytest.mark.gate
def test_가능_상한은_하한보다_높을_때만_근거와_함께다() -> None:
    """🆕 2026-10-01 (D-310 개정 (다)) — 표시 전용 칸. 하한 없는 상한 · 근거 없는 상한 · 하한 이하 상한을 계약이 거부한다."""
    from pydantic import ValidationError

    from app.contracts import RiskAssessment

    ok = RiskAssessment(floor=Risk.R1, final=Risk.R1, ceiling=Risk.R2, ceiling_note="목에 따라 R2")
    assert ok.ceiling is Risk.R2 and ok.final is Risk.R1, "상한은 최종 위험도를 올리지 않는다"
    for bad, why in (
        ({"floor": None, "ceiling": Risk.R2, "ceiling_note": "x"}, "하한 없이"),
        ({"floor": Risk.R2, "ceiling": Risk.R2, "ceiling_note": "x"}, "높지 않다"),
        ({"floor": Risk.R1, "ceiling": Risk.R2}, "근거 줄"),
        ({"floor": Risk.R1, "ceiling_note": "x"}, "상한이 없다"),
    ):
        with pytest.raises(ValidationError, match=why):
            RiskAssessment(**bad)


@pytest.mark.gate
def test_넓은_목은_맞아도_하한이_아니라_가능_상한이다() -> None:
    """🆕 2026-10-01 (D-310 개정 2 · 팀장 판정 (다)) — 별표1 목이 별표7 행보다 넓으면 목만으로 그 행이라 할 수 없다.

    🔴 4.마(수상 · 인증 · 보증 · 선정 · 특허)가 맞았다고 「식약처 인증」 문구에 업무정지 하한을 붙이면 하한이 확실한 최소가 아니다.
    """
    spec = _food(
        [
            ROW
            | {
                "id": "aw",
                "kind": "영업정지",
                "type": "거짓_과장",
                "quote": "사실과 다른 수상",
                "fact": "수상_상장",
                "annex1": ["4.마"],
                "cover": "일부",
            },
            ROW
            | {
                "id": "aw3",
                "kind": "영업정지",
                "type": "거짓_과장",
                "quote": "사실과 다른 수상(블록 3)",
                "fact": "수상_상장",
                "annex1": ["4.마"],
                "cover": "일부",
            },
            ROW
            | {
                "id": "ex",
                "kind": "품목제조정지",
                "type": "후기_체험기_기만",
                "annex1": ["5.다"],
                "cover": "전부",
            },
            ROW | {"id": "ty", "kind": "품목제조정지", "type": "소비자_기만", "annex1": []},
            ROW
            | {
                "id": "io",
                "kind": "영업정지",
                "type": "소비자_기만",
                "annex1": ["5.차"],
                "cover": "전부",
            },
        ]
    )
    broad = sr.floor_of(spec, "거짓_과장", "013475", ["013094:제8조제1항제4호|마목"])
    assert (broad.floor, broad.ceiling) == (Risk.R1, Risk.R2), "넓은 목은 하한 R1 · 상한 R2"
    assert broad.ceiling_note.count("「") == 1, (
        f"블록마다 같은 행위는 한 번만: {broad.ceiling_note}"
    )
    assert "4.마 중 「사실과 다른 수상」" in broad.ceiling_note
    exact = sr.floor_of(spec, "후기_체험기_기만", "013475", ["013094:제8조제1항제5호|다목"])
    assert (exact.floor, exact.ceiling, exact.basis) == (Risk.R2, None, ("ex",))
    # 목을 모르면 상한 근거에 고시 근거 행도 보인다
    miss = sr.floor_of(spec, "소비자_기만", "013475", ["013094:제8조제1항제5호"])
    assert (miss.floor, miss.ceiling) == (Risk.R1, Risk.R2)
    assert "5.차" in miss.ceiling_note and sr.NO_MOK_BASIS in miss.ceiling_note
    hit = sr.floor_of(spec, "소비자_기만", "013475", ["013094:제8조제1항제5호|차목"])
    assert (hit.floor, hit.ceiling) == (Risk.R2, None)


@pytest.mark.gate
def test_원천의_목_덮음은_판정대로다() -> None:
    """🆕 2026-10-01 (D-310 개정 2 · (다)) — 전부: 5.다 · 5.차 · 5.카 / 일부: 4.다 · 4.마 · 5.나 · 7.나."""
    rows = [r for r in sr.load_rules()["rows"] if r.get("annex1")]
    by = {c: {r["cover"] for r in rows if c in r["annex1"]} for r in rows for c in r["annex1"]}
    assert by == {
        "5.다": {"전부"},
        "5.차": {"전부"},
        "5.카": {"전부"},
        "4.다": {"일부"},
        "4.마": {"일부"},
        "5.나": {"일부"},
        "7.나": {"일부"},
    }, by
