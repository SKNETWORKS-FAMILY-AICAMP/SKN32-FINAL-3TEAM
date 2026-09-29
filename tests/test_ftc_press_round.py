"""공정위 보도자료 1997~2007 문구 판 — 사건 레코드 → 판독 → 채택 → 평가 (2026-09-30 · 동결 전 판정 ⑤-1·3 (나)).

🔴 무엇을 막나
   ① 마스킹 정책 없이 보도자료 문구가 판독 원자료 · 골든셋으로 가는 것 (D-72 fail-closed)
   ② 원천 본문에 없는 문구(뽑은 이가 고쳐 쓴 것 · 원천이 바뀐 것)가 채택되는 것 (D-220)
   ③ 화장품 코드(1 · 2 · 4 · 별표5목)가 보도자료 판독에 섞이는 것
   ④ 판정 대기가 남았는데 평가에 들어가는 것 · 대상 N 이 평가에 들어가는 것
   ⑤ 화장품 판과 채택 규칙이 갈리는 것 — 같은 `_agree` 를 쓴다 (D-99)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import statute
from preprocess import mask, split
from scripts import guide_statute_round as g

HEAD = "지문\t대상\t주근거\t부근거\t별표5목\t조건\t제외목\t메모\n"


def _jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def fp(tmp_path, monkeypatch):
    d = tmp_path / "fp"
    for name, fn in (
        ("FP_READINGS", "readings.jsonl"),
        ("FP_ADOPTED", "adopted.jsonl"),
        ("FP_DECISIONS", "decisions.jsonl"),
        ("FP_AUDIT", "audit.jsonl"),
        ("FP_TEAM_SHEET", "team.csv"),
    ):
        monkeypatch.setattr(g, name, d / fn)
    cases = tmp_path / "cases.jsonl"
    _jsonl(
        cases,
        [
            {"사건": "1", "본문": "듀라셀은 2배,\n 3배 최고 5배 오래갑니다 라고 광고"},
            {"사건": "2", "본문": "경쟁사는 부도덕한 기업이라고 광고"},
        ],
    )
    monkeypatch.setattr(g, "FP_CASES", cases)
    monkeypatch.setattr(split, "FTC_PRESS_READINGS", d / "readings.jsonl")
    monkeypatch.setattr(split, "FTC_PRESS_ADOPTED", d / "adopted.jsonl")
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    k1 = g.fp_key_of("1", "듀라셀은 2배, 3배 최고 5배 오래갑니다")
    k2 = g.fp_key_of("2", "부도덕한 기업")
    units = [
        {
            "지문": k1,
            "사건": "1",
            "문구": "듀라셀은 2배, 3배 최고 5배 오래갑니다",
            "원천판단": "부당한 비교광고",
        },
        {"지문": k2, "사건": "2", "문구": "부도덕한 기업", "원천판단": "비방광고"},
    ]
    up = tmp_path / "units.json"
    up.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    r1 = tmp_path / "r1.tsv"
    r1.write_text(
        HEAD + f"{k1}\tY\t공3\t-\t-\tC\t-\t\n{k2}\tY\t공4\t-\t-\tC\t-\t\n", encoding="utf-8"
    )
    r2 = tmp_path / "r2.tsv"
    r2.write_text(
        HEAD + f"{k1}\tY\t공3\t-\t-\tB\t실증\t\n{k2}\tY\t공4\t-\t-\tL\t-\t\n", encoding="utf-8"
    )
    return up, r1, r2, k1, k2


@pytest.mark.gate
def test_보도자료_판독은_표시광고법_호만_받는다() -> None:
    assert g.fp_parse_line("fp:x\tY\t공3\t공4\t-\tC\t-\t")["근거"] == [
        statute.fair(3),
        statute.fair(4),
    ]
    assert g.fp_parse_line("fp:x\tY\t1\t-\t-\tC\t-\t")["문제"]  # 화장품법 코드
    assert g.fp_parse_line("fp:x\tY\t공3\t-\t가\tC\t-\t")["문제"]  # 별표5목은 화장품 칸
    assert g.fp_parse_line("fp:x\tY\t공3\t-\t-\tB\t기능성심사\t")["문제"]  # 화장품 제외목


@pytest.mark.gate
def test_지문은_사건과_공백을_접은_문구로_정해진다() -> None:
    assert g.fp_key_of("1", "가 나\n 다") == g.fp_key_of("1", "가 나 다")
    assert g.fp_key_of("1", "가 나 다") != g.fp_key_of("2", "가 나 다")
    assert g.FP_KEY_RE.match(g.fp_key_of("1", "문구"))


@pytest.mark.gate
def test_마스킹_정책이_없으면_멈춘다(fp, monkeypatch) -> None:
    up, r1, r2, *_ = fp
    monkeypatch.delitem(mask.POLICY, "ftc_press")
    with pytest.raises(mask.MaskPolicyError):
        g.fp_merge(up, r1, r2)
    assert not g.FP_READINGS.exists()


@pytest.mark.gate
def test_원천_본문에_없는_문구면_멈춘다(fp, tmp_path) -> None:
    *_, k1, _k2 = fp
    with pytest.raises(SystemExit, match="원천과 어긋난다"):
        g.fp_units([{"지문": k1, "사건": "1", "문구": "고쳐 쓴 문구", "원천판단": "x"}])


@pytest.mark.gate
def test_채택은_화장품과_같은_규칙이고_다시_계산해도_같다(fp) -> None:
    up, r1, r2, k1, _k2 = fp
    got = g.fp_merge(up, r1, r2)
    first = g.FP_ADOPTED.read_bytes()
    assert got["채택"] == 1 and got["시트"] == 1  # C↔B → C · C↔L 은 시트
    assert g.fp_rebuild() == got and g.FP_ADOPTED.read_bytes() == first
    row = json.loads(first.decode().splitlines()[0])
    assert row["지문"] == k1 and row["조건"] == "C" and row["근거"] == [statute.fair(3)]
    assert row["사건"] == "1" and row["원천판단"] == "부당한 비교광고"


@pytest.mark.gate
def test_대기가_남으면_평가에_없다(fp) -> None:
    up, r1, r2, *_ = fp
    g.fp_merge(up, r1, r2)
    assert split.ftc_press_state() == {"전체": 2, "채택": 1, "대기": 1}
    assert split.ftc_press_docs() == []
    assert split.FTC_PRESS_ADOPTED not in split.inputs()
