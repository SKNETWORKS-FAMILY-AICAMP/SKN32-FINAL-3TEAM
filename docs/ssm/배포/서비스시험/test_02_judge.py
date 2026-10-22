"""2. 문구 검수 API (`POST /judge`) — 판정이 계약 모양대로 오류 없이 돌아오는가.

★ 판정의 **옳고 그름**은 여기서 합격선으로 삼지 않는다 — 규칙 · 인코더가 바뀌면 같이 바뀐다.
   대신 무엇이 나왔는지를 보고서 「판정 결과 관찰」 표에 그대로 남긴다(사람이 본다).
★ 합격선으로 삼는 것은 **고장의 신호**다: 200 이 아님 · 계약 밖 값 · 미판정(unjudged) 문장 · 판정기 판 미상 · 같은 입력에 다른 답.
"""

from __future__ import annotations

import pytest
from conftest import JUDGE_OBS, Client, assert_no_server_error, note

case = pytest.mark.case
AREA = "검수 API"

OUTCOMES = {"pass", "certificate", "guidance", "hold"}
VERDICTS = {"confirmed", "hold", "no_basis", "unjudged"}

#: 🚨 전부 지어낸 문구다 (배포/load_test.py 와 같은 원칙)
SAMPLES = [
    ("JDG-01", "위반 의도", "이 크림 하나면 2주 만에 주름이 완전히 사라집니다."),
    ("JDG-02", "위반 의도", "매일 한 포로 혈당 걱정 끝, 당뇨에 좋은 차."),
    ("JDG-03", "위반 의도", "부작용 없는 100% 천연 다이어트 보조제, 한 달에 10kg 감량."),
    ("JDG-04", "위반 의도", "탈모 치료에 효과가 입증된 샴푸."),
    ("JDG-05", "위반 의도", "면역력을 높여 감기를 예방하는 홍삼 진액."),
    ("JDG-06", "경계", "피로 회복에 도움을 줄 수 있는 비타민 C 1000mg."),
    ("JDG-07", "경계", "아토피 피부도 안심하고 쓰는 순한 보습 로션."),
    ("JDG-08", "적법 의도", "국내산 원료로 정성껏 만든 수제 그래놀라."),
    ("JDG-09", "적법 의도", "주말 한정 무료 배송, 지금 주문하세요."),
]


def judge(http: Client, text: str, **extra) -> tuple[dict, float]:
    r = http.post("/judge", json={"text": text, **extra})
    assert r.status_code == 200, f"상태 {r.status_code} · {r.text[:150]}"
    assert "application/json" in r.headers.get("Content-Type", ""), "JSON 응답이 아니다"
    return r.json(), http_last_ms(http)


def http_last_ms(http: Client) -> float:
    import conftest  # noqa: PLC0415

    rows = conftest.CURRENT["requests"] if conftest.CURRENT else []
    return rows[-1]["ms"] if rows else 0.0


def check_contract(body: dict) -> None:
    """계약(`JudgeResponse`)에서 화면이 기대는 칸들이 제 모양인지."""
    assert body.get("outcome") in OUTCOMES, f"모르는 종착 outcome={body.get('outcome')!r}"
    sents = body.get("sentences")
    assert isinstance(sents, list) and sents, "판정 문장(sentences)이 비었다"
    for s in sents:
        assert s.get("sent_id"), "문장 id 가 없다"
        assert isinstance(s.get("text"), str), "문장 원문이 없다"
        v = s.get("verdict")
        assert v in VERDICTS, f"모르는 문장 판정 verdict={v!r} ({s.get('sent_id')})"
        if v == "hold":
            assert s.get("hold_reason"), f"보류인데 보류 사유가 없다 ({s.get('sent_id')})"
    assert isinstance(body.get("branches", []), list), "branches 가 목록이 아니다"
    assert body.get("judged_by") not in (None, "", "unknown"), f"판정기 판이 미상이다 judged_by={body.get('judged_by')!r}"


def observe(cid: str, intent: str, text: str, body: dict, ms: float) -> None:
    sents = body.get("sentences", [])
    viol: list[str] = []
    for s in sents:
        for v in s.get("violations") or []:
            if v not in viol:
                viol.append(v)
    obs = {
        "id": cid,
        "intent": intent,
        "text": text,
        "outcome": body.get("outcome"),
        "sentences": len(sents),
        "confirmed": sum(1 for s in sents if s.get("verdict") == "confirmed"),
        "hold": sum(1 for s in sents if s.get("verdict") == "hold"),
        "unjudged": sum(1 for s in sents if s.get("verdict") == "unjudged"),
        "violations": viol,
        "encoder_sentences": sum(1 for s in sents if s.get("encoder_candidates")),
        "branches": len(body.get("branches", [])),
        "certificate": body.get("certificate") is not None,
        "judged_by": body.get("judged_by", ""),
        "law_version": body.get("law_version", ""),
        "ms": ms,
    }
    JUDGE_OBS.append(obs)
    note(
        f"종착={obs['outcome']} · 문장 {obs['sentences']}(확정 {obs['confirmed']}·보류 {obs['hold']}) · "
        f"위반={','.join(viol) or '-'} · 분기 {obs['branches']}"
    )


@pytest.mark.parametrize(
    ("cid", "intent", "text"),
    [
        pytest.param(
            cid,
            intent,
            text,
            id=cid,
            marks=case(
                id=cid,
                area=AREA,
                title=f"판정 — {text[:24]}{'…' if len(text) > 24 else ''} ({intent})",
                expect="200 · 계약 모양 · 미판정 문장 없음",
            ),
        )
        for cid, intent, text in SAMPLES
    ],
)
def test_judge_sample(http: Client, cid: str, intent: str, text: str) -> None:
    body, ms = judge(http, text)
    check_contract(body)
    observe(cid, intent, text, body, ms)
    unjudged = [s["sent_id"] for s in body["sentences"] if s.get("verdict") == "unjudged"]
    assert not unjudged, f"미판정(오류·시간 초과) 문장이 있다: {unjudged}"


@case(id="JDG-10", area=AREA, title="여러 문장 문구 — 문장 나누기", expect="문장이 2개 이상으로 나뉘어 판정된다")
def test_judge_multi_sentence(http: Client) -> None:
    text = "하루 한 알로 간 건강을 지키세요. 피로가 싹 풀립니다. 지금 구매하면 1+1 행사 중입니다."
    body, ms = judge(http, text)
    check_contract(body)
    observe("JDG-10", "여러 문장", text, body, ms)
    assert len(body["sentences"]) >= 2, f"문장이 {len(body['sentences'])}개로만 나뉘었다"


@case(id="JDG-11", area=AREA, title="품목 정보를 함께 보낸 판정", expect="200 · 계약 모양")
def test_judge_with_product(http: Client) -> None:
    text = "눈 건강에 도움을 줄 수 있는 루테인."
    body, ms = judge(http, text, product={})
    check_contract(body)
    observe("JDG-11", "품목 기본값", text, body, ms)


@case(id="JDG-12", area=AREA, title="같은 문구 두 번 — 결과 일관성", expect="두 번의 종착 · 문장 판정이 같다")
def test_judge_deterministic(http: Client) -> None:
    text = "이 크림 하나면 2주 만에 주름이 완전히 사라집니다."
    a, _ = judge(http, text)
    b, _ = judge(http, text)
    assert a["outcome"] == b["outcome"], f"종착이 다르다: {a['outcome']} / {b['outcome']}"
    va = [s.get("verdict") for s in a["sentences"]]
    vb = [s.get("verdict") for s in b["sentences"]]
    assert va == vb, f"문장 판정이 다르다: {va} / {vb}"


@case(id="JDG-13", area=AREA, title="HTML·스크립트가 섞인 입력", expect="200 · 정상 판정(입력을 문자로 다룬다)")
def test_judge_markup_input(http: Client) -> None:
    text = '<script>alert("x")</script> 이 차는 혈압을 낮춰 줍니다.'
    body, ms = judge(http, text)
    check_contract(body)
    observe("JDG-13", "특수 입력", text, body, ms)


@case(id="JDG-14", area=AREA, title="빈 문구", expect="422 (입력 거부)")
def test_judge_empty(http: Client) -> None:
    r = http.post("/judge", json={"text": ""})
    assert r.status_code == 422, f"상태 {r.status_code}"


@case(id="JDG-15", area=AREA, title="2,001자 문구 (상한 2,000자)", expect="422 (자르지 않고 거부)")
def test_judge_too_long(http: Client) -> None:
    r = http.post("/judge", json={"text": "가" * 2001})
    assert r.status_code == 422, f"상태 {r.status_code}"


@case(id="JDG-16", area=AREA, title="text 칸이 없는 요청", expect="422")
def test_judge_missing_field(http: Client) -> None:
    r = http.post("/judge", json={"copy": "문구"})
    assert r.status_code == 422, f"상태 {r.status_code}"


@case(id="JDG-17", area=AREA, title="깨진 JSON 본문", expect="422 · 내부 오류 흔적 없음")
def test_judge_broken_json(http: Client) -> None:
    r = http.post("/judge", data='{"text": "문구"', headers={"Content-Type": "application/json"})
    assert r.status_code == 422, f"상태 {r.status_code}"
    assert_no_server_error(r)


@case(id="JDG-18", area=AREA, title="GET 으로 판정 호출", expect="405 (POST 만 받는다)")
def test_judge_get(http: Client) -> None:
    r = http.get("/judge")
    assert r.status_code == 405, f"상태 {r.status_code}"
