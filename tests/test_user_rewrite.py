"""검수 → 지적 문장 고쳐 쓰기(sLLM 재생성) BFF — 소유자 lse (2026-10-06).

★ sLLM 서버(`docs/lse/sllm_service.py`)와 판정 코어는 **가짜로 바꿔 끼운다** — GPU · DB 없이 돈다.
  원문 판정은 골든 픽스처(`JudgeResponse`)로, 고친 문구의 재판정은 가벼운 가짜로.
🔴 지키는 것
   - 결과는 검수 화면의 그 문장 아래에 붙는다 · 판정(`JudgeResponse`)의 `candidates` 는 비운 채다 (D-265 계약)
   - 위반 유형은 서버의 판정 결과에서 읽는다 (폼을 믿지 않는다)
   - 서버가 없으면 후보를 그리지 않는다 (D-146 · D-147)
   - 고친 문구는 판정 코어로 다시 판정하고, 위반이 붙으면 후보가 아니다 (D-119)
   - 「위반 못 찾음」을 통과로 그리지 않는다 · 사유 A(자격형)는 고쳐 쓰지 않는다 (D-59)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "judge"


def _fixture(name: str):  # noqa: ANN202
    from app.contracts import JudgeResponse  # noqa: PLC0415

    return JudgeResponse.model_validate_json(
        (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    )


def _light(violations=(), outcome="hold"):  # noqa: ANN001, ANN202
    """재판정용 가벼운 가짜 — `_rejudge` 가 읽는 칸만."""
    sent = SimpleNamespace(
        violations=[SimpleNamespace(value=v) for v in violations],
        verdict=SimpleNamespace(value="hold"),
        hold_reason=SimpleNamespace(value="low_conf"),
    )
    return SimpleNamespace(sentences=[sent], outcome=SimpleNamespace(value=outcome))


BODY = "원료를 담았습니다"
_CANDIDATE = {
    "outcome": "candidate",
    "rewrite": {"body": BODY, "mandatory_note": "원재료 함량을 함께 표시", "placement": None},
    "infeasible": None,
    "reasons": [],
    "repairs": [],
    "model": "v12",
    "latency_ms": 9000,
}
ORIGINAL = "붓기 관리에 좋은 원료를 담았습니다."  # 02_hold_low_conf 의 문장 · 거짓_과장


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """판정 코어 · sLLM 서버를 가짜로. 무엇을 불렀는지 남긴다."""
    from app.routers import sllm_client  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    st = SimpleNamespace(
        judge=[],
        sllm=[],
        judge_out={ORIGINAL: ("ok", _fixture("02_hold_low_conf")), BODY: ("ok", _light())},
        sllm_out=("ok", _CANDIDATE),
    )

    def fake_judge(text: str):  # noqa: ANN202
        st.judge.append(text)
        return st.judge_out[text]

    def fake_sllm(text: str, violations: list[str]):  # noqa: ANN202
        st.sllm.append((text, violations))
        return st.sllm_out

    monkeypatch.setattr(user_router, "_core_judge", fake_judge)
    monkeypatch.setattr(sllm_client, "rewrite", fake_sllm)
    return st


def _post(pairs: list[tuple[str, str]], status: int = 200) -> str:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post(
        "/u/review/rewrite",
        content=urlencode(pairs).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == status, r.text[:300]
    return r.text


def _go(text: str = ORIGINAL, target: str = "1:s1") -> str:
    return _post([("text", text), ("target", target)])


def test_지적_문장을_판정_결과의_위반_유형으로_고쳐_쓰고_재판정한다(wired) -> None:  # noqa: ANN001
    html = _go()
    assert wired.sllm == [(ORIGINAL, ["거짓_과장"])], "🔴 위반 유형을 판정 결과에서 읽지 않았다"
    assert wired.judge == [ORIGINAL, BODY], "🔴 고친 문구를 다시 판정하지 않았다 (D-119)"
    assert "고친 문구 후보" in html and BODY in html
    assert "필수 병기 · 원재료 함량을 함께 표시" in html
    assert "위반 못 찾음 (통과 아님)" in html, "🔴 「위반 못 찾음」을 통과처럼 그렸다"
    assert "재판정 · 통과" not in html
    assert "근거 보기" in html, "검수 결과 화면 안에 그려야 한다"


def test_폼에_실린_위반_유형은_믿지_않는다(wired) -> None:  # noqa: ANN001
    _post([("text", ORIGINAL), ("target", "1:s1"), ("violation", "의약품_오인")])
    assert wired.sllm == [(ORIGINAL, ["거짓_과장"])]


def test_재판정에서_위반이_붙으면_후보가_아니다(wired) -> None:  # noqa: ANN001
    wired.judge_out[BODY] = ("ok", _light(["건강기능식품_오인"]))
    html = _go()
    assert "재판정에서 위반 의심" in html
    assert "고친 문구 후보" not in html


def test_서버가_없으면_후보를_지어내지_않는다(wired) -> None:  # noqa: ANN001
    wired.sllm_out = ("down", None)
    html = _go()
    assert "후보를 만들지 않았어요" in html
    assert "고친 문구 후보" not in html
    assert wired.judge == [ORIGINAL], "🔴 후보가 없는데 재판정을 불렀다"


def test_판정_코어가_없으면_고쳐_쓰지_않는다(wired) -> None:  # noqa: ANN001
    wired.judge_out[ORIGINAL] = ("down", None)
    html = _go()
    assert wired.sllm == [], "🔴 판정 없이 고쳐 썼다"
    assert "고친 문구 후보" not in html


def test_사유_A는_고쳐_쓰지_않는다(wired) -> None:  # noqa: ANN001
    text = "면역력 강화에 도움을 줍니다."
    wired.judge_out[text] = ("ok", _fixture("05_certificate_a"))
    html = _go(text)
    assert wired.sllm == [], "🔴 자격형인데 재생성을 불렀다 (D-59)"
    assert "고쳐 쓰지 않아요" in html


@pytest.mark.parametrize(
    ("out", "want"),
    [
        ({"outcome": "infeasible", "infeasible": "거짓_과장"}, "합법화 불가"),
        ({"outcome": "infeasible", "infeasible": "지어낸 사유"}, "유형 미상"),
        ({"outcome": "hold", "reasons": ["원문에 없는 낱말: 곶감"]}, "원문에 없는 낱말: 곶감"),
        ({"outcome": "hold", "reasons": ["원문 그대로"]}, "고칠 곳을 찾지 못했어요"),
    ],
)
def test_후보가_아닌_종착을_그린다(wired, out: dict, want: str) -> None:  # noqa: ANN001
    base = {"rewrite": None, "reasons": [], "repairs": [], "infeasible": None, "model": "v12"}
    wired.sllm_out = ("ok", {**base, "latency_ms": 5000, **out})
    html = _go()
    assert want in html
    assert "고친 문구 후보" not in html
    assert "지어낸 사유" not in html, "🔴 모델이 지어낸 불가 사유를 그렸다"


@pytest.mark.parametrize("target", ["", "1", "x:s1", "1:s1;rm", "9:s1"])
def test_모르는_대상은_고쳐_쓰지_않는다(wired, target: str) -> None:  # noqa: ANN001
    if target == "9:s1":
        html = _go(target=target)
        assert "고쳐 쓸 문장을 찾지 못했어요" in html
    else:
        _post([("text", ORIGINAL), ("target", target)], status=422)
    assert wired.sllm == []


def test_문구는_이스케이프해서_되돌린다(wired) -> None:  # noqa: ANN001
    text = "<script>x</script>"
    wired.judge_out[text] = ("ok", _fixture("02_hold_low_conf"))
    html = _go(text)
    assert "<script>x" not in html, "🔴 이스케이프 안 된 문구가 나왔다 (XSS)"


@pytest.mark.parametrize(
    ("fixture", "has_button"), [("02_hold_low_conf", True), ("05_certificate_a", False)]
)
def test_검수_화면의_지적_문장에_고쳐_쓰기_버튼이_있다(fixture: str, has_button: bool) -> None:
    """사유 A 문장에는 버튼이 없다 (D-59)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    html = TestClient(app).get(f"/u/preview/{fixture}").text
    assert ('action="/u/review/rewrite"' in html) is has_button


def test_카피생성_화면에는_고쳐_쓰기가_없다() -> None:
    """재생성은 검수 쪽이다 — 카피생성(새 카피)과 섞지 않는다 (10-06 결정)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    assert "rewrite" not in TestClient(app).get("/u/generate").text


def test_서버_주소가_닫혀_있으면_down(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import sllm_client  # noqa: PLC0415

    monkeypatch.setattr(sllm_client, "SLLM_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(sllm_client, "TIMEOUT_S", 2)
    assert sllm_client.rewrite("문구", []) == ("down", None)


def test_위반_유형이_없는_문장은_고쳐_쓰지_않는다(wired) -> None:  # noqa: ANN001
    """확신 부족 보류만 있는 문장 — 유형 없이 보내면 모델이 엉뚱한 불가를 낸다(10-06 실측)."""
    text = "피부 보습에 도움을 줄 수 있습니다."
    wired.judge_out[text] = ("ok", _fixture("01_pass"))
    html = _go(text)
    assert wired.sllm == []
    assert "위반 유형을 찾지 못했어요" in html
