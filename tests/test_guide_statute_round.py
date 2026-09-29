"""해설서 조문·조건 판의 채택 규칙 (D-285 · 지시서 09-24 §5).

🔴 무엇을 막나
   ① 두 판독의 **기대 응답**이 다른데 채택되는 것 — 🔄 개정 2: 기대 응답이 같은 갈림(D↔M · 호만)만 규칙으로 닫는다
   ② 적용 제외 목이 근거로 들어오는 것 (D-238)
   ③ 한쪽만 본 예외가 실리는 것 — 제외목은 교집합
   ④ 모르는 꼴이 조용히 버려지는 것 (D-220)
"""

from __future__ import annotations

import pytest

from collect import statute
from scripts import guide_statute_round as g


def _r(prim="5.다", sec="-", cond="C", exc="-", gap="N"):
    return g.parse_line(f"gs:x\t{prim}\t{sec}\t{cond}\t{exc}\t{gap}\t")


@pytest.mark.gate
def test_같으면_채택하고_목이_같으면_남긴다() -> None:
    got, why = g.agree(_r(), _r())
    assert why == "" and got["근거"] == [statute.food(5, "다")] and got["조건"] == "C"


@pytest.mark.gate
def test_목이_다르면_호까지만() -> None:
    got, _ = g.agree(_r("5.다"), _r("5.라"))
    assert got["근거"] == [statute.food(5)]


@pytest.mark.gate
def test_조건이나_호가_다르면_시트로() -> None:
    """🔄 D-285 개정 2 — 시트는 **기대 응답이 갈리는** 행이다. 호만 갈리면 후보로 채택(아래 테스트)."""
    assert g.agree(_r(cond="B"), _r(cond="M"))[0] is None
    assert g.agree(_r(cond="C"), _r("-", cond="D"))[0] is None
    assert g.agree(_r(cond="A"), _r(cond="B"))[0] is None  # A↔B 는 엄격함의 순서가 없다


@pytest.mark.gate
def test_제외목은_둘_다_적은_것만() -> None:
    got, _ = g.agree(_r("3", cond="A", exc="3.라,1.가.1"), _r("3", cond="A", exc="3.라"))
    assert got["제외목"] == ["3.라"]


@pytest.mark.gate
def test_주장_아님은_근거가_빈다() -> None:
    got, _ = g.agree(_r("-", cond="D"), _r("3", cond="D"))
    assert got["근거"] == [] and got["제외목"] == []


@pytest.mark.gate
def test_원천결손이나_판독_문제는_시트로() -> None:
    assert g.agree(_r("-", cond="D", gap="Y"), _r("5.다", cond="C"))[0] is None  # 갈리면 시트 (④′)
    assert (
        g.agree(_r("3.라", cond="A"), _r("3", cond="A"))[0] is None
    )  # 적용 제외 목이 근거 (D-238)
    assert g.agree(_r("기타:별표6-3.가"), _r("기타:별표6-3.가"))[0] is None
    assert g.agree(_r(cond="X"), _r(cond="X"))[0] is None
    assert g.agree(_r("-", cond="C"), _r("-", cond="C"))[0] is None  # C·A·B 는 근거가 있어야 한다


@pytest.mark.gate
def test_법8조_9_10호도_인용으로() -> None:
    assert g.cite_of("법8-10") == statute.food(10)
    with pytest.raises(ValueError):
        g.cite_of("9")  # [별표 1] 에 9호는 없다 — 법 호는 `법8-9` 로


@pytest.mark.gate
def test_M_은_호를_추측으로_채우지_않는다() -> None:
    """🔄 D-285 개정 — 둘 다 M 이면 같다 · 호는 둘이 같을 때만 남는다."""
    got, _ = g.agree(_r("-", cond="M"), _r("4", cond="M"))
    assert got["조건"] == "M" and got["근거"] == []
    got, _ = g.agree(_r("6", cond="M"), _r("6", cond="M"))
    assert got["근거"] == [statute.food(6)]
    got, _ = g.agree(_r("3", cond="M"), _r("4", cond="M"))
    assert got["근거"] == []


@pytest.mark.gate
def test_조제유류_목과_3나_유형_게이트가_있다() -> None:
    """🔴 제품유형에 달린 목은 합의만으로 채택하지 않는다 — 3.나 는 유형 9 만 (D-288) · 5.바·5.사 는 조제유류만."""
    assert g.NA_TYPES == ("9.",)
    assert (5, "사") in g.FORMULA_MOK and (5, "바") in g.FORMULA_MOK


@pytest.mark.gate
def test_겹치는_호만_남긴다() -> None:
    """🔄 09-24 밤 — 한쪽이 부근거를 더 적었으면 둘 다 적은 호만 (지시서 §5)."""
    got, _ = g.agree(_r("3", "4.라"), _r("3"))
    assert got["근거"] == [statute.food(3)]


@pytest.mark.gate
def test_원천결손은_둘_다_D_면_채택한다() -> None:
    """🔄 09-24 밤 — 블록 제목은 D · 원천결손으로 남는다. 판정 대상 아님이지 적법이 아니다 (지시서 §7 선행 게이트)."""
    got, _ = g.agree(_r("-", cond="D", gap="Y"), _r("-", cond="D"))
    assert got["조건"] == "D" and got["원천결손"] is True and got["근거"] == []


@pytest.mark.gate
def test_C_와_A_B_가_갈리면_보수_합성() -> None:
    """🔄 09-25 (D-285 개정) — 더 엄격한 C · 이견을 남긴다 · 제외목은 교집합이라 비는 것이 보통이다."""
    got, _ = g.agree(_r("3", cond="A", exc="3.나"), _r("3", cond="C"))
    assert got["조건"] == "C" and got["조건_이견"] == ["A", "C"] and got["제외목"] == []
    got, _ = g.agree(_r("6", cond="B"), _r("6", cond="C"))
    assert got["조건"] == "C" and got["조건_이견"] == ["B", "C"]
    got, _ = g.agree(_r("4", cond="B"), _r("5", cond="C"))  # 🔄 개정 2 — 호가 안 겹치면 후보
    assert (
        got["조건"] == "C"
        and got["근거"] == []
        and got["근거_후보"]
        == [
            [statute.food(4)],
            [statute.food(5)],
        ]
    )
    got, _ = g.agree(_r("3"), _r("3"))
    assert got["조건_이견"] == []


@pytest.mark.gate
def test_표시요건은_조문이_정한_목록으로() -> None:
    """🆕 09-25 (D-289) — 메모에 표시요건이 있으면 부류로 무엇을 밝혀야 하는지 · 못 가리면 미분류."""
    a = g.parse_line("gs:x\t6\t-\tB\t-\tN\t표시요건")
    b = g.parse_line("gs:x\t6\t-\tB\t-\tN\t입증")
    assert g.disclosure_of("판매 1위", a, b) == ["조사대상", "조사기관", "조사기간"]
    assert g.disclosure_of("저널에 발표된", a, b) == ["연구자", "문헌명", "발표 연월일"]
    assert g.disclosure_of("어떤 문구", a, b) == ["미분류"]
    assert g.disclosure_of("판매 1위", b, b) == []
    assert g.disclosure_of("체지방 감소에 도움", b, b, ["3.나"]) == list(
        g.FUNC_DISCLOSURE
    )  # 법이 요구


@pytest.mark.gate
def test_호만_안_겹치면_조건은_채택하고_근거는_후보() -> None:
    """🔄 09-25 (D-285 개정 2) — 합집합이 아니다(「둘 다 걸린다」가 된다) · 어느 쪽이든 정답인 후보 둘."""
    got, why = g.agree(_r("4.라"), _r("3"))
    assert why == "" and got["조건"] == "C" and got["근거"] == []
    assert got["근거_후보"] == [[statute.food(4, "라")], [statute.food(3)]]
    got, _ = g.agree(_r("4", "5"), _r("6"))
    assert got["근거_후보"] == [sorted([statute.food(4), statute.food(5)]), [statute.food(6)]]
    got, _ = g.agree(_r("3"), _r("3"))
    assert got["근거_후보"] == []  # 겹치면 후보를 두지 않는다
    assert (
        g.agree(_r("-", cond="C"), _r("5", cond="C"))[0] is None
    )  # 한쪽이 근거를 안 적었으면 시트


@pytest.mark.gate
def test_D_와_M_이_갈리면_M_으로_합성() -> None:
    """🔄 09-25 (D-285 개정 2) — M(보류)은 통과로 새지 않는다 · 원천결손은 둘 다 적었을 때만."""
    got, _ = g.agree(_r("-", cond="D", gap="Y"), _r("-", cond="M"))
    assert got["조건"] == "M" and got["조건_이견"] == ["D", "M"]
    assert got["근거"] == [] and got["원천결손"] is False
    got, _ = g.agree(_r("3", cond="M"), _r("-", cond="D"))
    assert got["근거"] == []  # M 쪽이 호를 적었어도 추측으로 채우지 않는다


@pytest.mark.gate
def test_지문은_base32_라_식별번호_꼴이_생기지_않는다() -> None:
    """🔄 09-25 — 16진 지문 `gs:ab0175558118` 이 반출 검사의 휴대전화 꼴로 잡혔다. 0·1·8·9 가 없는 알파벳으로 막는다."""
    from scripts import derived_manifest as dm

    keys = [g.key_of({"표": i, "원천라벨": "x", "문구": f"문구{i}"}) for i in range(3000)]
    assert all(g.KEY_RE.match(k) for k in keys)
    assert not any(set(k[3:]) & set("0189") for k in keys)
    assert not any(p.search(k) for k in keys for p in dm.PERSON_IDS.values())


@pytest.mark.gate
def test_원자료에서_다시_계산해도_채택이_같다(tmp_path, monkeypatch) -> None:
    """🆕 09-25 (D-285 개정 3) — 채택본은 생성물이다. 판독 원자료(JSON)를 거쳐 다시 계산해도 바이트까지 같아야 한다."""
    import json

    monkeypatch.setattr(g, "ADOPTED", tmp_path / "adopted.jsonl")
    monkeypatch.setattr(g, "SHEET", tmp_path / "sheet.csv")
    monkeypatch.setattr(
        g, "TEAM_SHEET", tmp_path / "team.csv"
    )  # 🔄 09-25 — 실제 팀장 판정표를 덮지 않는다
    src = {
        f"gs:{c * 12}": {
            "표": i,
            "제품유형": "9. 체중조절용",
            "원천라벨": "x",
            "문구": f"판매 1위 {i}",
            "원천": "t",
        }
        for i, c in enumerate("abc")
    }
    a = {k: {**_r(prim), "지문": k} for k, prim in zip(src, ("5.다", "4", "3"), strict=True)}
    b = {
        k: {**_r(prim, cond=c), "지문": k}
        for k, prim, c in zip(src, ("5.다", "5", "3"), "CCM", strict=True)
    }
    g.decide(src, a, b)
    first = (g.ADOPTED.read_bytes(), g.SHEET.read_bytes())
    back = lambda d: {k: json.loads(json.dumps(v, ensure_ascii=False)) for k, v in d.items()}  # noqa: E731
    g.decide(src, back(a), back(b))
    assert (g.ADOPTED.read_bytes(), g.SHEET.read_bytes()) == first
    assert len(first[0].splitlines()) == 2  # 5.다 합의 · 4↔5 후보 — C↔M 은 시트
