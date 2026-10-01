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
    assert sr.floor_by_type(spec, signed_only=False) == {"의약품_오인": {"013475": "R2"}}
    spec["signoff"] = {"sha": sr.plan_sha(spec), "verified_by": "오한빈", "reviewed_by": "권소라"}
    assert sr.floor_by_type(spec) == {"의약품_오인": {"013475": "R2"}}


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
