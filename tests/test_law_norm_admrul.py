"""행정규칙 [별표] → 노드 (`preprocess/law_norm.py` · 🆕 2026-09-26 · 사실원장 ㉚).

🔴 막는 것
   ① 굵은 괘선(`┏━┯━┓ ┃`)으로 그린 표가 0행이 되는 것 — 식약처 고시는 굵은 괘선을 쓴다(36814 · 37971 실측)
   ② 마커 없는 목록(41277 「○ … ▸ …」)이 첫 마커 앞이라 통째로 버려지는 것
   ③ 같은 (구역, 경로)가 둘이라 청크 ID 가 겹쳐 적재에서 조용히 덮이는 것(36122 · 37098 실측)
   ④ 「[표 4]」를 「[별표 4]」로 읽는 것 — 원문이 부른 이름으로만 번호를 읽는다 (D-224)
   ⑤ 서식 · 체크리스트가 규범 노드로 들어오는 것 — 「별표」가 아니면 `ADMRUL_EXTRA` 에 적힌 것만
   ⑥ 🆕 09-26 오후 — 괄호 번호 `(1)` · `(가)` 를 몰라 목록이 상위 호 본문에 통째로 붙는 것(36122 [별표 4] 제4호 1,324자)
   ⑦ 🆕 [부표] 가 앞 호에 붙는 것(36122 [별표 3] 제11호 아래 설문 `11.1~11.8`) · 부표를 부르는 줄을 경계로 읽는 것
   ⑧ 🆕 고시가 거꾸로 쓴 번호(「(3) 최고용량 :」 아래 「1)」)를 형제로 읽는 것 — 법령 별표는 종전대로 형제
   ⑨ 🆕 파서를 고치며 글이 사라지는 것 — 마커 없는 줄은 전부 어느 노드엔가 남는다
🚨 원문 파일은 합성이다 — 실물의 **모양**만 옮겼다.
"""

from __future__ import annotations

import pathlib

import pytest

from preprocess import law_norm as ln

pytestmark = pytest.mark.gate

XML = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
<별표>
<별표단위><별표번호>0001</별표번호><별표가지번호>00</별표가지번호><별표구분>별표</별표구분>
<별표제목>사용할 수 없는 원료</별표제목><별표내용>[별표 1]

사용할 수 없는 원료

┏━━━━━━━━┯━━━━━┓
┃원료명          │CAS No.   ┃
┠────────┼─────┨
┃갈란타민        │357-70-0  ┃
┠────────┼─────┨
┃중추신경계에 작용│300-62-9  ┃
┃하는 아민       │          ┃
┠────────┼─────┨
┃원료명          │CAS No.   ┃
┗━━━━━━━━┷━━━━━┛

※ 유의사항
1. 대표 CAS No.를 예시로 적었다.
2. 염류의 예 : 소듐
</별표내용></별표단위>
<별표단위><별표번호>0002</별표번호><별표가지번호>00</별표가지번호><별표구분>별표</별표구분>
<별표제목>실증자료</별표제목><별표내용>[표 2]

실증자료

○ 여드름성 피부에 적합

&amp;#9656; 인체 적용시험 자료 제출

1. 첫째
  (1) 효능 가
  (2) 효능 나
  (용법은 다음과 같다)
  (1) 용법 가
    ① 바른다
</별표내용></별표단위>
<별표단위><별표번호>0001</별표번호><별표가지번호>00</별표가지번호><별표구분>별지</별표구분>
<별표제목>신청서</별표제목><별표내용>신청인 성명</별표내용></별표단위>
</별표>
</AdmRulService>
"""


@pytest.fixture
def units(tmp_path: pathlib.Path) -> list[dict]:
    p = tmp_path / "admrul_99999_20260101.xml"
    p.write_text(XML, encoding="utf-8")
    return ln.admrul_units(p)


def test_별표만_싣고_서식은_뺀다(units: list[dict]) -> None:
    assert [(u["kind"], u["annex_no"]) for u in units] == [("별표", "0001"), ("별표", "0002")]


def test_굵은_괘선_표는_행_노드가_되고_다시_나온_머리글은_뺀다(units: list[dict]) -> None:
    rows = ln.build_admrul(units[0])
    tab = [r for r in rows if str(r["path"]).startswith("표")]
    assert [r["text"] for r in tab] == [
        "원료명: 갈란타민 · CASNo.: 357-70-0",
        "원료명: 중추신경계에 작용하는 아민 · CASNo.: 300-62-9",
    ]
    assert tab[0]["section"] == "본문"  # 표 앞 줄이 제목이면 이름표가 아니다
    assert rows[0]["annex_no_head"] == 1


def test_표_뒤_유의사항은_산문_노드로_남는다(units: list[dict]) -> None:
    rows = ln.build_admrul(units[0])
    prose = [r["text"] for r in rows if not str(r["path"]).startswith("표")]
    assert any("대표 CAS No." in t for t in prose)


def test_첫_마커_앞의_목록을_버리지_않는다_이스케이프도_푼다(units: list[dict]) -> None:
    rows = ln.build_admrul(units[1])
    head = next(r for r in rows if r["path"] == "머리")
    assert "여드름성 피부에 적합" in head["text"] and "▸ 인체 적용시험" in head["text"]
    assert "[표 2]" not in head["text"] and "실증자료" not in head["lines"][0]


def test_표_라고_부른_별표는_번호를_읽지_않는다(units: list[dict]) -> None:
    assert ln.build_admrul(units[1])[0]["annex_no_head"] is None


def test_겹친_경로는_전부_가르고_표시한다(units: list[dict]) -> None:
    rows = ln.build_admrul(units[1])
    keys = [(r["section"], r["path"]) for r in rows]
    assert len(keys) == len(set(keys))
    marked = [r["path"] for r in rows if r.get("경로중복")]
    # 원문이 같은 번호 목록을 번호 없는 소제목만 사이에 두고 되풀이한다(36122 [별표 4] 제4호) — 겹침은 남고 표시된다
    assert marked == ["1.(1)~1", "1.(1)~2"]
    # 🚨 그 아래 ①은 **제 부모를 따라간다** — 안 따라가면 없는 부모(`1.(1)`)를 가리켜 문맥에서 부모가 빠진다
    assert "1.(1)~2.①" in [r["path"] for r in rows]


def test_괄호_번호는_계층이고_상위_호에_붙지_않는다() -> None:
    """🔴 2026-09-26 — 36122 [별표 4] 제4호가 `(1)~(7)` 목록을 통째로 품어 1,324자가 됐고, 그 아래 ①들이 부모를 잃어
    `4.①~1 … ~4` 로 겹쳤다. 그 거대 노드가 자식 13행의 문맥에 붙어 입력이 900자를 넘었다(사실원장 ㉛ · ㉜)."""
    content = """[별표 4]
4. 모발의 색상을 변화시키는 제품
  (1) 염모제 : 모발의 염모
  (6) 1제형 신청의 경우
   ① 이 제품을 바른다
   ② 1제형의 예에 따라 기재한다
  (7) 분리 신청의 경우
   ① 산화제와 섞는다
"""
    rows = ln.build_admrul(_unit(content))
    by = {r["path"]: r["text"] for r in rows}
    assert "염모제" not in by["4"] and "(1)" not in by["4"]
    assert {"4.(1)", "4.(6)", "4.(6).①", "4.(6).②", "4.(7)", "4.(7).①"} <= set(by)
    assert not [r for r in rows if r.get("경로중복")]


def test_부표는_구역이고_머리_글을_남긴다() -> None:
    """🔴 2026-09-26 — [부표 1] 선정기준 · 설문이 앞 호 제11호 본문과 하위 항목(`11.1~11.8`)으로 붙었다."""
    content = """[별표 3]
11. (등급 표시방법) 자외선A차단지수에 따라 표시한다.
[부표 1]
피험자 선정기준
피부질환이 없는 사람을 선정한다.
1) 최근 1년간 병원에 간 일이 있습니까?
2) 민감피부입니까?
[부표 5]
[부표 1]의 피험자 선정기준에 따른다.
"""
    rows = ln.build_admrul(_unit(content))
    eleven = next(r for r in rows if r["section"] == "본문" and r["path"] == "11")
    assert "병원" not in eleven["text"] and "선정기준" not in eleven["text"]
    sub1 = {r["path"]: r["text"] for r in rows if r["section"] == "[부표 1]"}
    assert "피부질환이 없는" in sub1["머리"] and set(sub1) == {"머리", "1", "2"}
    # 🚨 부표를 **부르는** 줄은 경계가 아니다 — 경계로 읽으면 빈 구역이 생기고 글이 사라진다
    sub5 = {r["path"]: r["text"] for r in rows if r["section"] == "[부표 5]"}
    assert "[부표 1]의 피험자 선정기준에 따른다" in sub5["머리"]


def test_고시가_거꾸로_쓴_번호는_자식이고_법령_별표는_종전대로다() -> None:
    """🔴 2026-09-26 — 「(3) 최고용량 :」 아래 「1) 2)」가 `(3)` 을 밀어내고 형제가 되면, 뒤의 「(4)」가 「2)」 아래로 들어간다."""
    content = """8. 유전독성시험
  가. 복귀돌연변이시험
  (3) 최고용량 :
     1) 비독성 시험물질은 5mg/plate
     2) 세포독성 시험물질은 세포독성 농도
  (4) S9 mix를 병행한다.
"""
    rows = ln.build_admrul(_unit(content))
    paths = [r["path"] for r in rows if r["path"] != "머리"]
    assert paths == ["8", "8.가", "8.가.(3)", "8.가.(3).1", "8.가.(3).2", "8.가.(4)"]
    assert [r["path"] for r in rows if r.get("역순")] == ["8.가.(3).1"]
    # 법령 별표(`parse` 기본값) — 머리 목록 「가. 나.」 뒤의 「1.」은 형제다(013475 [별표 4])
    law = ln.parse("가. 대형 영업\n나. 소형 영업\n1. 대상 식품\n  가. 과자류\n")
    assert [n["path"] for n in law] == ["가", "나", "1", "1.가"]


def test_마커_없는_줄은_전부_어느_노드엔가_남는다() -> None:
    """파서를 고치며 글이 사라지지 않았는지 — 머리글 · 제목 · 「[부표 N]」 줄(구역 이름이 된다)을 뺀 모든 줄."""
    content = XML_4_LIKE = """[별표 4]
4. 모발 제품
  (제형은 분말제에 한함)
  (1) 염모제
  (용법은 다음과 같다)
  (1) 3제형 산화염모제
   제1제와 제2제를 섞는다.
[부표 1]
설문
1) 질문 하나
"""
    rows = ln.build_admrul(_unit(XML_4_LIKE))
    kept = {x.strip() for r in rows for x in r["lines"]}
    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith(("[별표", "[부표")) or s == "시험 별표":
            continue
        assert s in kept, s


def _unit(content: str) -> dict:
    return {
        "law_id": "99999",
        "kind": "별표",
        "annex_no": "0009",
        "title": "시험 별표",
        "content": content,
        "file": "admrul_99999_20260101.xml",
    }
