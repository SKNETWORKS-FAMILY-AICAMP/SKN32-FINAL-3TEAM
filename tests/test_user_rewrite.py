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
        cats=[],
        products=[],
    )

    def fake_judge(text: str, product=None):  # noqa: ANN001, ANN202
        st.judge.append(text)
        st.products.append(product.category.value if product and product.category else None)
        return st.judge_out[text]

    def fake_sllm(text: str, violations: list[str], category: str | None = None):  # noqa: ANN202
        st.sllm.append((text, violations))
        st.cats.append(category)
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


def test_버튼이_없으면_이유를_적는다() -> None:
    """버튼이 안 뜨는 문장은 왜 안 뜨는지 보인다 — 사유 A · 위반 유형 없음 (10-06 화면 확인)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    html = TestClient(app).get("/u/preview/05_certificate_a").text
    assert "고쳐 쓰기 없음 · 사유 A(자격형)" in html


# ── 2026-10-06 흡수 검토 — 깨진 응답은 후보가 아니다 (D-220 · D-146) ─────────────────────
@pytest.mark.parametrize(
    "broken",
    [
        {**_CANDIDATE, "rewrite": None},  # 후보인데 문구가 없다
        {**_CANDIDATE, "rewrite": {"body": "  ", "mandatory_note": None, "placement": None}},
        {k: v for k, v in _CANDIDATE.items() if k != "latency_ms"},
        {k: v for k, v in _CANDIDATE.items() if k != "model"},
        {**_CANDIDATE, "outcome": "done"},
        ["candidate"],
    ],
)
def test_칸이_빠진_응답은_깨진_응답이다(broken: object) -> None:
    from app.routers import sllm_client  # noqa: PLC0415

    assert not sllm_client._well_formed(broken)
    assert sllm_client._well_formed(_CANDIDATE)


def test_깨진_응답이면_화면은_후보를_그리지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 재현 — 고치기 전에는 `rw.rejudge` 를 읽다 500 이었다. 가짜는 서버 응답까지만 바꾼다(검사는 진짜)."""
    import io  # noqa: PLC0415
    import json  # noqa: PLC0415

    from app.routers import sllm_client  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    payload = json.dumps({**_CANDIDATE, "rewrite": None}).encode()
    monkeypatch.setattr(sllm_client.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload))
    monkeypatch.setattr(
        user_router, "_core_judge", lambda text: ("ok", _fixture("02_hold_low_conf"))
    )
    html = _go()
    assert "연결하지 못했어요" in html
    assert "고친 문구 후보" not in html


def test_화면에_서버_실행_명령을_보이지_않는다(wired) -> None:  # noqa: ANN001
    wired.sllm_out = ("down", None)
    html = _go()
    assert "연결하지 못했어요" in html
    assert ".venv-sllm" not in html
    assert "sllm_service.py" not in html


# ── 품목 분기가 있는 문구 — 분기를 고른 뒤에만 고쳐 쓴다 (ksr 2026-10-06 · main 병합) ─────────────
#: 03_hold_cat_unknown — 기록 판정은 건강기능식품_오인(A) · 화장품 분기는 의약품_오인(C) · 식품 분기는 A
BRANCHED = "면역력 강화에 도움을 줍니다."


def _light_branched(premise: str, violations=()):  # noqa: ANN001, ANN202
    """재판정용 가짜 — 기록 판정에는 위반을 두고, 고른 전제의 분기에는 `violations` 만 둔다."""
    branch = _light(violations)
    branch.premise = SimpleNamespace(value=premise)
    res = _light(["건강기능식품_오인"])
    res.branches = [branch]
    return res


def test_분기가_있으면_고른_전제의_위반_유형으로_고쳐_쓴다(wired) -> None:  # noqa: ANN001
    wired.judge_out[BRANCHED] = ("ok", _fixture("03_hold_cat_unknown"))
    wired.judge_out[BODY] = ("ok", _light_branched("화장품"))
    html = _post([("text", BRANCHED), ("target", "1:s1"), ("premise", "화장품"), ("round", "2")])
    assert wired.sllm == [(BRANCHED, ["의약품_오인"])], (
        "🔴 품목을 모를 때의 기록 판정(건강기능식품_오인)으로 고쳐 썼다 — 고른 분기의 판정을 읽어야 한다"
    )
    assert "고친 문구 후보" in html, (
        "🔴 재판정을 고른 전제의 분기로 읽지 않았다(기록 판정의 위반으로 탈락)"
    )
    # 다시 그릴 때 고른 자리(2회차 · 화장품)가 펼쳐져 있어야 결과가 보인다
    assert 'id="rvk-1-2-cos" aria-label="화장품" checked' in html
    assert 'id="rvr-1-2"' in html and html.count('회차" checked') == 2


def test_분기를_고르지_않으면_고쳐_쓰지_않는다(wired) -> None:  # noqa: ANN001
    wired.judge_out[BRANCHED] = ("ok", _fixture("03_hold_cat_unknown"))
    html = _post([("text", BRANCHED), ("target", "1:s1")])
    assert wired.sllm == [], "🔴 분기를 고르기 전의 판정으로 고쳐 썼다"
    assert "제품 유형을 먼저 골라 주세요" in html


def test_분기의_사유_A는_고쳐_쓰지_않는다(wired) -> None:  # noqa: ANN001
    wired.judge_out[BRANCHED] = ("ok", _fixture("03_hold_cat_unknown"))
    html = _post([("text", BRANCHED), ("target", "1:s1"), ("premise", "식품"), ("round", "0")])
    assert wired.sllm == []
    assert "고쳐 쓰지 않아요" in html


@pytest.mark.parametrize(
    "extra", [[("premise", "없는_전제")], [("premise", "화장품"), ("round", "9")], [("round", "x")]]
)
def test_모르는_전제와_회차는_거부한다(wired, extra: list) -> None:  # noqa: ANN001
    wired.judge_out[BRANCHED] = ("ok", _fixture("03_hold_cat_unknown"))
    _post([("text", BRANCHED), ("target", "1:s1"), *extra], status=422)
    assert wired.sllm == []


def test_고쳐_쓰기_버튼은_분기를_고른_뒤의_문장에만_있다() -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    html = TestClient(app).get("/u/preview/03_hold_cat_unknown").text
    # 기록되는 판정은 회차의 맨 끝이다 — 다음 회차가 시작하는 데서 자른다
    rec = [part.split('class="rv-round ')[0] for part in html.split('<div class="rv-rec">')[1:]]
    assert rec and all("/u/review/rewrite" not in part for part in rec), (
        "🔴 고르기 전(기록되는 판정)에 고쳐 쓰기 버튼이 있다"
    )
    assert 'name="premise" value="화장품"' in html, "화장품 분기의 지적 문장에는 버튼이 있어야 한다"
    assert 'name="premise" value="건기식_인정"' not in html, "위반이 없는 분기에는 버튼이 없다"


def test_판정_결과의_품목을_서버와_재판정에_넘긴다(wired) -> None:  # noqa: ANN001
    """🆕 10-06 (팀장 전달 §2 #3) — 품목을 문구에서 추측하지 않게 판정 결과의 품목을 넘긴다(D-319)."""
    from app.contracts import Category  # noqa: PLC0415

    judged = _fixture("02_hold_low_conf").model_copy(update={"category": Category.화장품})
    wired.judge_out[ORIGINAL] = ("ok", judged)
    _go()
    assert wired.cats == ["화장품"], "🔴 품목을 sLLM 서버에 넘기지 않았다"
    assert wired.products == [None, "화장품"], (
        "🔴 원문 판정은 품목 없이 · 고친 문구 재판정은 원문 판정의 품목으로"
    )


def test_품목이_미확정이면_넘기지_않는다(wired) -> None:  # noqa: ANN001
    judged = _fixture("02_hold_low_conf").model_copy(update={"category": None})
    wired.judge_out[ORIGINAL] = ("ok", judged)
    _go()
    assert wired.cats == [None] and wired.products == [None, None]


def test_클라이언트가_품목을_보낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    import io  # noqa: PLC0415
    import json  # noqa: PLC0415

    from app.routers import sllm_client  # noqa: PLC0415

    sent = {}

    def fake_urlopen(req, timeout=None):  # noqa: ANN001, ANN202, ARG001
        sent.update(json.loads(req.data.decode("utf-8")))
        return io.BytesIO(json.dumps(_CANDIDATE).encode())

    monkeypatch.setattr(sllm_client.urllib.request, "urlopen", fake_urlopen)
    assert sllm_client.rewrite("문구", ["거짓_과장"], "건기식")[0] == "ok"
    assert sent["category"] == "건기식" and sent["rejudge"] is False
