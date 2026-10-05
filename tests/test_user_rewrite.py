"""원문 고쳐 쓰기(재생성 · 진입점 B) BFF — 소유자 lse (2026-10-06).

★ sLLM 서버(`docs/lse/sllm_service.py`)와 판정 코어는 **가짜로 바꿔 끼운다** — GPU · DB 없이 돈다.
🔴 지키는 것
   - 서버가 없으면 후보를 그리지 않는다 (D-146 · D-147)
   - 고친 문구는 판정 코어로 다시 판정하고, 위반이 붙으면 후보가 아니다 (D-119)
   - 「위반 못 찾음」을 통과로 그리지 않는다
   - 사유 A(자격형)는 고쳐 쓰지 않는다 (D-59) · 검수 화면은 넘기기만 한다 (D-265)
   - 원문은 이스케이프해서 되돌린다 (P2-9)
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlencode

import pytest


def _sent(violations=(), verdict="hold", hold="low_conf", infeas=None):  # noqa: ANN001, ANN202
    return SimpleNamespace(
        violations=[SimpleNamespace(value=v) for v in violations],
        verdict=SimpleNamespace(value=verdict),
        hold_reason=SimpleNamespace(value=hold) if hold else None,
        infeasibility=SimpleNamespace(value=infeas) if infeas else None,
    )


def _judged(*sents, outcome="hold"):  # noqa: ANN002, ANN202
    return SimpleNamespace(sentences=list(sents), outcome=SimpleNamespace(value=outcome))


_CANDIDATE = {
    "outcome": "candidate",
    "rewrite": {
        "body": "문경 오미자를 설탕에 100일 숙성한 오미자청",
        "mandatory_note": None,
        "placement": None,
    },
    "infeasible": None,
    "reasons": [],
    "repairs": [],
    "model": "v12",
    "latency_ms": 9000,
}


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """판정 코어 · sLLM 서버를 가짜로. `calls` 에 무엇을 불렀는지 남긴다."""
    from app.routers import sllm_client  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    st = SimpleNamespace(judge=[], sllm=[], judge_out={}, sllm_out=("ok", _CANDIDATE))

    def fake_judge(text: str):  # noqa: ANN202
        st.judge.append(text)
        return st.judge_out.get(text, ("ok", _judged(_sent())))

    def fake_sllm(text: str, violations: list[str]):  # noqa: ANN202
        st.sllm.append((text, violations))
        return st.sllm_out

    monkeypatch.setattr(user_router, "_core_judge", fake_judge)
    monkeypatch.setattr(sllm_client, "rewrite", fake_sllm)
    return st


def _post(form: dict | list) -> str:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post(
        "/u/rewrite",
        content=urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    return r.text


ORIGINAL = "고혈압 낮추는 오미자청, 문경 오미자를 설탕에 100일 숙성"


def test_판정_코어가_찾은_위반_유형을_넘기고_후보를_재판정한다(wired) -> None:  # noqa: ANN001
    wired.judge_out[ORIGINAL] = ("ok", _judged(_sent(["질병_예방치료_표방"])))
    html = _post({"text": ORIGINAL})
    assert wired.sllm == [(ORIGINAL, ["질병_예방치료_표방"])]
    assert wired.judge == [ORIGINAL, _CANDIDATE["rewrite"]["body"]], (
        "🔴 고친 문구를 다시 판정하지 않았다 (D-119)"
    )
    assert "문경 오미자를 설탕에 100일 숙성한 오미자청" in html
    assert "위반 못 찾음 (통과 아님)" in html, "🔴 「위반 못 찾음」을 통과처럼 그렸다"
    assert "재판정 · 통과" not in html


def test_재판정에서_위반이_붙으면_후보가_아니다(wired) -> None:  # noqa: ANN001
    wired.judge_out[_CANDIDATE["rewrite"]["body"]] = ("ok", _judged(_sent(["건강기능식품_오인"])))
    html = _post({"text": ORIGINAL})
    assert "재판정에서 위반 의심" in html
    assert "고친 문구 후보" not in html


def test_서버가_없으면_후보를_지어내지_않는다(wired) -> None:  # noqa: ANN001
    wired.sllm_out = ("down", None)
    html = _post({"text": ORIGINAL})
    assert "후보를 만들지 않았어요" in html
    assert "고친 문구 후보" not in html
    assert len(wired.judge) == 1, "🔴 후보가 없는데 재판정을 불렀다"


def test_판정_코어가_없으면_위반_유형_없이_보내고_그렇다고_적는다(wired) -> None:  # noqa: ANN001
    wired.judge_out[ORIGINAL] = ("down", None)
    wired.judge_out[_CANDIDATE["rewrite"]["body"]] = ("down", None)
    html = _post({"text": ORIGINAL})
    assert wired.sllm == [(ORIGINAL, [])]
    assert "판정 코어에 연결하지 못해" in html
    assert "재판정 못 함" in html


def test_검수에서_넘어오면_검수의_위반_유형을_쓴다(wired) -> None:  # noqa: ANN001
    form = [
        ("from", "review"),
        ("text", ORIGINAL),
        ("violation", "질병_예방치료_표방"),
        ("violation", "없는_유형"),
        ("violation", "질병_예방치료_표방"),
    ]
    _post(form)
    assert wired.sllm == [(ORIGINAL, ["질병_예방치료_표방"])], (
        "🔴 모르는 유형 · 중복을 거르지 않았다"
    )
    assert wired.judge == [_CANDIDATE["rewrite"]["body"]], (
        "검수가 이미 판정했다 — 원문을 다시 판정하지 않는다"
    )


def test_사유_A는_고쳐_쓰지_않는다(wired) -> None:  # noqa: ANN001
    wired.judge_out[ORIGINAL] = ("ok", _judged(_sent(["건강기능식품_오인"], infeas="A")))
    html = _post({"text": ORIGINAL})
    assert wired.sllm == [], "🔴 자격형인데 재생성을 불렀다 (D-59)"
    assert "대체 문구를 만들지 않아요" in html


@pytest.mark.parametrize(
    ("out", "want"),
    [
        ({"outcome": "infeasible", "infeasible": "질병_예방치료_표방"}, "합법화 불가"),
        ({"outcome": "hold", "reasons": ["원문에 없는 낱말: 곶감"]}, "원문에 없는 낱말: 곶감"),
        ({"outcome": "hold", "reasons": ["원문 그대로"]}, "고칠 곳을 찾지 못했어요"),
    ],
)
def test_후보가_아닌_종착을_그린다(wired, out: dict, want: str) -> None:  # noqa: ANN001
    wired.sllm_out = (
        "ok",
        {
            "rewrite": None,
            "reasons": [],
            "repairs": [],
            "infeasible": None,
            "model": "v12",
            "latency_ms": 5000,
            **out,
        },
    )
    html = _post({"text": ORIGINAL})
    assert want in html
    assert "고친 문구 후보" not in html


def test_원문은_이스케이프해서_되돌린다(wired) -> None:  # noqa: ANN001
    html = _post({"text": "<script>x</script> 위암 치료"})
    assert "<script>x" not in html, "🔴 이스케이프 안 된 원문이 나왔다 (XSS)"
    assert "&lt;script&gt;" in html


def test_빈_원문은_서버를_부르지_않는다(wired) -> None:  # noqa: ANN001
    html = _post({"text": "   "})
    assert wired.sllm == [] and wired.judge == []
    assert "고쳐 쓸 원문을 넣어 주세요" in html


def test_카피생성_화면에_원문_칸이_있다() -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    html = TestClient(app).get("/u/generate").text
    assert 'action="/u/rewrite"' in html and 'name="text"' in html


@pytest.mark.parametrize(
    ("fixture", "has_button"), [("02_hold_low_conf", True), ("05_certificate_a", False)]
)
def test_검수_화면은_지적_문장을_넘기기만_한다(fixture: str, has_button: bool) -> None:
    """D-265 — 검수 화면에는 대체 문구가 없고 「고쳐 쓰기로 넘기기」만 있다. 사유 A 는 넘기지 않는다 (D-59)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    html = TestClient(app).get(f"/u/preview/{fixture}").text
    assert ("이 문장 고쳐 쓰기" in html) is has_button


def test_서버_주소가_닫혀_있으면_down(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import sllm_client  # noqa: PLC0415

    monkeypatch.setattr(sllm_client, "SLLM_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(sllm_client, "TIMEOUT_S", 2)
    assert sllm_client.rewrite("문구", []) == ("down", None)


def test_모델이_지어낸_불가_사유는_그리지_않는다(wired) -> None:  # noqa: ANN001
    """위반 유형 없이 보내면 모델이 사유를 제 말로 쓴다(10-06 실측) — 아는 유형만 사유로 그린다."""
    wired.sllm_out = (
        "ok",
        {
            "outcome": "infeasible",
            "infeasible": "지어낸 사유",
            "rewrite": None,
            "reasons": [],
            "repairs": [],
            "model": "v12",
            "latency_ms": 4000,
        },
    )
    html = _post({"text": "암을 이기는 진액"})
    assert "지어낸 사유" not in html
    assert "유형 미상" in html
