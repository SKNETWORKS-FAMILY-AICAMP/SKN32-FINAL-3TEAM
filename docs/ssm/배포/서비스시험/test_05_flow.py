"""5. 화면 흐름 — 사람이 검수 화면에서 누르는 버튼(폼 제출)을 그대로 보낸다.

★ 화면은 버튼 하나 = 폼 제출 하나(`op`)다. 브라우저 없이 같은 폼을 보내면 같은 서버 코드를 지난다.
🚨 **로그아웃 상태로만** 돈다 — 로그인한 회원이면 검수 결과가 이력에 저장된다.
"""

from __future__ import annotations

import pytest
from conftest import WITH_LLM, Client, assert_no_server_error, note

import report

case = pytest.mark.case
AREA = "화면 흐름"

TEXT = "이 크림 하나면 2주 만에 주름이 완전히 사라집니다."


def review(http: Client, texts: list[str], op: str) -> object:
    data = [("text", t) for t in texts] + [("op", op)]
    return http.post("/u/review", data=data)


@case(id="FLW-01", area=AREA, title="문구 검수 — 한 건 「검수하기」", expect="200 · 결과 영역이 그려진다 · 엔진 연결 실패 문구 없음")
def test_review_one(http: Client) -> None:
    r = review(http, [TEXT], "all")
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert_no_server_error(r)
    # 클래스 이름(rv-pending)은 화면 안 <style> 에 늘 있다 — 문구로 본다
    assert "판정 엔진에 연결하지 못했어요" not in r.text, "「판정 엔진에 연결하지 못했어요」가 떴다"
    assert "판정 엔진이 아직 붙지 않았어요" not in r.text, "「판정 엔진이 아직 붙지 않았어요」가 떴다"
    assert "cl-result-copy" in r.text, "검수 결과 영역이 없다"


@case(id="FLW-02", area=AREA, title="문구 검수 — 두 건 한 번에", expect="200 · 결과 영역 2개")
def test_review_two(http: Client) -> None:
    r = review(http, [TEXT, "국내산 원료로 정성껏 만든 수제 그래놀라."], "all")
    assert r.status_code == 200, f"상태 {r.status_code}"
    n = r.text.count('class="cl-result-copy"')
    assert n == 2, f"결과 영역이 {n}개"


@case(id="FLW-03", area=AREA, title="문구 칸 추가 버튼", expect="200 · 입력 칸이 하나 늘어난다")
def test_review_add(http: Client) -> None:
    r = review(http, [TEXT], "add")
    assert r.status_code == 200, f"상태 {r.status_code}"
    n = report.count_inputs(r.text, "text")
    assert n >= 2, f"입력 칸이 {n}개"


@case(id="FLW-04", area=AREA, title="예시 넣기 버튼", expect="200 · 예시 문구가 칸에 들어간다")
def test_review_sample(http: Client) -> None:
    r = review(http, [""], "sample:1")
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert "눈 피로" in r.text, "예시 문구가 안 들어갔다"


@case(id="FLW-05", area=AREA, title="빈 칸으로 검수", expect="200 · 「검수할 문구를 입력해주세요」")
def test_review_blank(http: Client) -> None:
    r = review(http, [""], "all")
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert "검수할 문구를 입력해주세요" in r.text, "안내 문구가 없다"


@case(id="FLW-06", area=AREA, title="문구 6건 (상한 5건)", expect="422")
def test_review_too_many(http: Client) -> None:
    r = review(http, [TEXT] * 6, "all")
    assert r.status_code == 422, f"상태 {r.status_code}"


@case(id="FLW-07", area=AREA, title="2,001자 문구", expect="422")
def test_review_too_long(http: Client) -> None:
    r = review(http, ["가" * 2001], "all")
    assert r.status_code == 422, f"상태 {r.status_code}"


@case(id="FLW-08", area=AREA, title="모르는 동작(op) 값", expect="422")
def test_review_bad_op(http: Client) -> None:
    r = review(http, [TEXT], "drop-table")
    assert r.status_code == 422, f"상태 {r.status_code}"


@case(id="FLW-09", area=AREA, title="결과 주소를 주소창에서 다시 열기 (GET /u/judge)", expect="303 → /u/review (405 원문이 안 뜬다)")
def test_result_url_get(http: Client) -> None:
    r = http.get("/u/judge")
    assert r.status_code == 303, f"상태 {r.status_code}"
    assert r.headers.get("Location", "").endswith("/u/review"), f"Location={r.headers.get('Location')}"


@case(id="FLW-10", area=AREA, title="다크 모드 전환", expect="303 → 보던 화면 · 테마 쿠키")
def test_theme(http: Client) -> None:
    r = http.post("/u/theme", data={"theme": "dark", "next": "/u/review"})
    assert r.status_code == 303, f"상태 {r.status_code}"
    assert r.headers.get("Location", "") == "/u/review", f"Location={r.headers.get('Location')}"
    assert http.s.cookies.get("copylane_theme") == "dark", "테마 쿠키가 없다"


@case(id="FLW-11", area=AREA, title="지적 문장 고쳐 쓰기 (sLLM)", expect="200 · 「고친 문구 후보」 또는 다시 판정 결과가 그려진다")
def test_rewrite(http: Client) -> None:
    if not WITH_LLM:
        pytest.skip("고쳐 쓰기는 sLLM 을 불러 수십 초 걸린다 — --with-llm 으로 포함")
    first = review(http, [TEXT], "all")
    assert first.status_code == 200, f"검수 {first.status_code}"
    forms = [f for f in report.parse_forms(first.text) if f["action"] == "/u/review/rewrite"]
    if not forms:
        pytest.skip("검수 결과에 「이 문장 고쳐 쓰기」 버튼이 없다 (고쳐 쓸 위반 문장이 없음)")
    data = [(f["name"], f["value"]) for f in forms[0]["fields"]]
    r = http.post("/u/review/rewrite", data=data)
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert_no_server_error(r)
    assert 'class="rv-fix" style="margin-top:.6rem"' in r.text, "고쳐 쓰기 결과 영역이 없다"
    assert "잠시 뒤 다시 눌러 주세요" not in r.text, "sLLM 에 연결하지 못했다"
    got = "고친 문구 후보" in r.text
    note("고친 문구 후보 있음" if got else "후보 없음 — 다시 판정에서 걸러짐(사람 검토로)")
