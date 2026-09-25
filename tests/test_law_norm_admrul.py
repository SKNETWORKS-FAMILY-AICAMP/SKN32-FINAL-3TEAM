"""행정규칙 [별표] → 노드 (`preprocess/law_norm.py` · 🆕 2026-09-26 · 사실원장 ㉚).

🔴 막는 것
   ① 굵은 괘선(`┏━┯━┓ ┃`)으로 그린 표가 0행이 되는 것 — 식약처 고시는 굵은 괘선을 쓴다(36814 · 37971 실측)
   ② 마커 없는 목록(41277 「○ … ▸ …」)이 첫 마커 앞이라 통째로 버려지는 것
   ③ 같은 (구역, 경로)가 둘이라 청크 ID 가 겹쳐 적재에서 조용히 덮이는 것(36122 · 37098 실측)
   ④ 「[표 4]」를 「[별표 4]」로 읽는 것 — 원문이 부른 이름으로만 번호를 읽는다 (D-224)
   ⑤ 서식 · 체크리스트가 규범 노드로 들어오는 것 — 「별표」가 아니면 `ADMRUL_EXTRA` 에 적힌 것만
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
  ① 가
  ② 나
  (7) 마커가 아닌 줄
  ① 다시 가
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
    assert marked == ["1.①~1", "1.①~2"]


def test_별표_청크_문맥은_입력_상한에_맞춰_상위_항목만_줄인다() -> None:
    """🔴 2026-09-26 — 긴 상위 항목이 문맥에 통째로 붙어 24행이 512토큰을 넘었다(모델이 말없이 자른다)."""
    from preprocess import chunk

    head = "[별표 4] 자료제출이 생략되는 기능성화장품의 종류"
    ctx = f"{head}\n" + "상위항목" * 400
    fit = chunk._fit_context(ctx, 700)
    assert fit.startswith(head + "\n") and fit.endswith("…")
    assert len(fit) + 700 <= chunk.ANNEX_INPUT_MAX
    short = f"{head}\n짧은 상위 항목"
    assert chunk._fit_context(short, 300) == short  # 상한 안이면 그대로
