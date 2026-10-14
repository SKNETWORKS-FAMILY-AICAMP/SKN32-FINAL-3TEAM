"""사용자 화면 nav 재구성 + ksr↔lse 병합 — 소유자 lse (병렬작업 계약 §5 · 2026-09-16).

★ ksr(skn32/ksr)의 review·generate·compose·mypage·landing 구현과 lse의 nav(4-pill+
  사이드바)·history(필터·페이지네이션·상세)를 합친 뒤의 회귀 확인이다.
  `docs/lse/ksr_lse_화면중복_비교_2026-09-16.md` 참고.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/u/",
        "/u/review",
        "/u/generate",
        "/u/compose",
        "/u/segments",
        "/u/help",
        "/u/matching",
        "/u/cs",
        "/u/landing",
        "/u/login",
        "/u/signup",
        "/u/reset",
    ],
)
def test_화면_골격이_DB_없이도_뜬다(path: str) -> None:
    """🚨 엔진·DB 없이도 200 이어야 한다 — `/`(홈)·`/u/history` 만 DB 를 본다 (D-124)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get(path)
    assert r.status_code == 200, f"🔴 {path} 가 안 뜬다 — {r.status_code}"


def test_상단_pill은_구역_넷뿐이다() -> None:
    """🔴 고객센터·마이페이지·홈·도움말은 상단 pill 이 아니다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/review").text
    for label in ("copylane 소개", "검수 및 카피생성", "AI 광고 생성", "매칭"):
        assert f">{label}</a>" in body, f"🔴 상단 pill에 「{label}」이 없다"
    assert "고객센터" not in body, "🔴 고객센터가 상단 pill로 새어나왔다 — 사이드바 하단이어야 한다"


def test_사이드바에_하위_화면이_새지_않는다() -> None:
    """🔴 segments 는 사이드바 항목이 아니다 (back-link 로만 진입)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/review").text
    assert 'href="/u/segments"' not in body, "🔴 하위 화면이 사이드바에 새어나왔다"


def test_구역_없는_화면은_사이드바가_없다() -> None:
    """🚨 홈·마이페이지·고객센터는 디자인상 구역 밖이라 사이드바가 안 뜬다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    client = TestClient(app)
    for path in ("/u/", "/u/cs"):
        body = client.get(path).text
        assert 'class="user-sidebar"' not in body, (
            f"🔴 {path} 에 사이드바가 붙었다 — 구역 밖이어야 한다"
        )


def test_활성_pill과_사이드바_항목에_활성_표시가_붙는다() -> None:
    """🚨 지금 보고 있는 구역·항목이 시각적으로 구분돼야 한다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/matching").text
    assert "user-topnav-pill user-topnav-pill-active" in body, (
        "🔴 매칭 pill 에 활성 표시가 안 붙는다"
    )
    assert 'href="/u/matching">' in body, "🔴 매칭 pill 링크가 없다"


def test_copylane_소개_탭이_사용방법과_FAQ를_가른다() -> None:
    """🚨 디자인은 사용방법·자주 묻는 질문을 같은 화면의 탭으로 둔다 (?tab= 로 서버 렌더)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    client = TestClient(app)
    guide = client.get("/u/help?tab=guide").text
    faq = client.get("/u/help?tab=faq").text
    assert "사용방법" in guide
    assert "자주 묻는 질문" in faq
    assert "user-sidebar-item-active" in guide
    assert "user-sidebar-item-active" in faq


def test_검수_POST가_문구를_되돌려_그린다() -> None:
    """🚨 `POST /u/judge` 는 가짜 결과 없이 넣은 문구만 되돌린다 (D-147 · P2-9 이스케이프)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post("/u/judge", content=b"text=<script>x</script>")
    assert r.status_code == 200
    assert "<script>" not in r.text, "🔴 이스케이프 안 된 문구가 그대로 나왔다 (XSS)"
    assert "&lt;script&gt;" in r.text


def test_검수_픽스처_미리보기가_결과_화면을_그린다() -> None:
    """🚨 `JudgeResponse` 계약을 통과한 픽스처만 결과로 그린다 (D-124 ③)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/u/preview/01_pass")
    assert r.status_code == 200
    assert "위험도" in r.text


def test_카피생성_프론티어_좌표가_파이썬에서_계산된다() -> None:
    """🚨 SVG 점 좌표는 서버가 낸다 — 차트 라이브러리 없이 CSP 를 지킨다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/u/generate/preview/10_generate_frontier")
    assert r.status_code == 200
    assert "<circle" in r.text, "🔴 프론티어 점이 안 그려졌다"


def test_광고생성_섹션_골격이_순서대로_그려진다() -> None:
    """🚨 `ComposeResponse.sections` 를 서버가 순서대로 그린다 (D-93 · D-164)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/u/compose/preview/12_compose_from_b")
    assert r.status_code == 200
    assert "cp-sec" in r.text


def test_이력이_판정_원문을_보여준다() -> None:
    """🔴 ksr 의 CopySentence 조인이 살아있어야 한다 — 판정만 보이고 원문이 안 보이면 회귀다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/u/history")
    assert r.status_code == 200
    assert "history-row-text" in r.text


def test_마이페이지는_로그인_안하면_로그인으로_보낸다() -> None:
    """🔴 2026-09-29 — `user_account` 표가 서면서 프로필을 채우려면 로그인이 필요해졌다 (cs_detail 과 같은 문)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    client = TestClient(app)
    r = client.get("/u/mypage", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/u/login"

    r = client.post(
        "/u/mypage",
        content=b"section=profile&name=%EA%B6%8C%EC%86%8C%EB%9D%BC",
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/u/login"

    r = client.post(
        "/u/mypage/disable", content=b"confirm=%EB%81%84%EA%B8%B0", follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/u/login"


def test_고객센터_상세는_로그인_안하면_로그인으로_보낸다() -> None:
    """🔴 `/u/cs/{ticket_id}` — 내 문의가 아니면 없는 것과 같은 404 지만, 로그인부터 막힌다 (P1-5)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/u/cs/00000000-0000-0000-0000-000000000000", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/u/login"


def test_랜딩은_governor_로그인이_아니라_일반_회원_로그인으로_보낸다() -> None:
    """🔴 `/login`(governor 전용)으로 잘못 보내던 걸 `/u/login`·`/u/signup`으로 고쳤다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/landing").text
    assert 'href="/u/login"' in body
    assert 'href="/u/signup"' in body


def test_로그인_전에_들어오면_랜딩이_첫_화면이다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🆕 2026-10-14 (사용자 요청) — 로그인 전 `/u/` 는 그 자리에서 랜딩을 그린다(로그인 벽 아님 · D-66). 「copylane 소개」 메뉴는 랜딩이 아니라 사용방법이다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    monkeypatch.setattr(user_router, "reachable", lambda _s: True)
    monkeypatch.setattr(user_router, "current_user", lambda *_a: None)
    r = TestClient(app).get("/u/", follow_redirects=False)
    assert r.status_code == 200 and "ld-hero" in r.text, "🔴 로그인 전 첫 화면이 랜딩이 아니다"
    body = TestClient(app).get("/u/review").text
    assert 'href="/u/help?tab=guide">copylane 소개</a>' in body


@pytest.mark.gate
@pytest.mark.parametrize(("code", "want"), [(501, "pending"), (503, "down")])
def test_검수_BFF_는_501_과_503_을_가른다(
    monkeypatch: pytest.MonkeyPatch, code: int, want: str
) -> None:
    """🆕 2026-10-01 (ksr 병합) — 501 = 엔진 미착수 · 503 = 엔진 연결 실패. 둘을 한 갈래로 합치지 않는다.

    ⛔ ohb 와 ksr 가 같은 503 수정을 따로 했고, 자동 병합이 `in (501, 503)` → pending 을 앞에 두어
       503 → down 줄이 **닿지 않는 줄**이 됐다(충돌 표시 없이). 화면 그림은 같아도 상태는 넘긴다 (D-147).
    """
    from fastapi import HTTPException  # noqa: PLC0415

    import app.api  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    def boom(_req):  # noqa: ANN001, ANN202
        raise HTTPException(code)

    monkeypatch.setattr(app.api, "judge", boom)
    assert user_router._core_judge("문구") == (want, None)


def test_검수_분기_다시_선택은_5회다() -> None:
    """🆕 2026-10-06 — 「다시 선택」 3 → 5."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/preview/21_hold_cat_unknown_hair").text
    assert 'id="rvr-1-5"' in body
    assert 'id="rvr-1-6"' not in body


@pytest.mark.parametrize(
    ("fixture", "want"),
    [
        ("15_hold_premise_unknown", "인증 여부 선택 필요"),
        ("03_hold_cat_unknown", "유형 선택 필요"),
        ("21_hold_cat_unknown_hair", "유형 선택 필요"),
    ],
)
def test_검수_배지는_인증_여부만_물을_때_인증_여부_선택_필요다(fixture: str, want: str) -> None:
    """🆕 2026-10-13 (D-330) — 분기가 건강기능식품 인정 · 비인정뿐이면 유형은 묻지 않는다. 배지도 「인증 여부 선택 필요」다."""
    import re  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get(f"/u/preview/{fixture}").text
    badges = set(re.findall(r'class="rv-outcome o-hold o-ask">\s*([^<]+?)\s*<', body))
    assert badges == {want}


@pytest.mark.parametrize("fmt", ["SNS 피드", "배너"])
def test_광고생성은_고른_종류와_내용을_다시_그린다(
    monkeypatch: pytest.MonkeyPatch, fmt: str
) -> None:
    """🔄 10-08 (lse) — 「상세페이지」에 checked 가 박혀 있어 다른 종류를 골라 제출해도 상세페이지로 돌아갔다 · 적은 내용도 비었다.

    🔄 10-12 (ksr) — 종류가 SNS 피드 · 상세페이지 · 배너 셋이다. 제출은 판정을 부른다 — 엔진이 없을 때의 화면을 본다.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    _fake_judge(monkeypatch, "pending")
    body = TestClient(app).post("/u/compose", data={"ad_format": fmt, "prompt": "보습 제품"}).text
    assert f'value="{fmt}" checked' in body
    assert 'value="상세페이지" checked' not in body
    assert ">보습 제품</textarea>" in body


def test_광고생성_미리보기는_픽스처의_종류에_체크한다() -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    # 🔄 10-12 (ksr) — 픽스처의 「카드뉴스」는 화면의 종류 셋에 없다. 다른 종류에 체크하지 않는다
    body = TestClient(app).get("/u/compose/preview/12_compose_from_b").text
    assert " checked" not in body
    assert "섹션 골격 — 카드뉴스" in body


# ── 🆕 2026-10-10 — 카피 생성의 새 입력(분기 6종 + 제품 내용 · ksr 10-08)과 후보 → 광고 생성 넘기기.
#    흡수할 때 이 길을 타는 테스트가 없었다. 🚨 문구 · 이름은 여기서 지어낸 것이다 (D-175 · D-249)


def _gen_post(**data: str):  # noqa: ANN202
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    base = {"category": "food", "cert": "no", "age": "all", "sex": "all"}
    # 🔄 2026-10-14 — 생성은 회원만 쓴다(`_gen_gate`). 폼 검증을 재는 자리라 회원으로 보낸다
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(user_router, "_gen_gate", lambda *_a: None)
        return TestClient(app).post("/u/generate", data={**base, **data})


def test_생성_분기표의_전제는_시험코드의_품목과_맞는다() -> None:
    """`_GEN_BRANCHES` 의 `premise` 를 읽는 쪽 — 화면 분기와 시험 코드(`docs/ksr/llm_copy/branches.py`)가 같은 표인가.

    앱은 시험 폴더를 import 하지 않는다. 그래서 표가 둘이고, 어긋나면 생성 평가가 다른 전제로 잰다.
    """
    import importlib.util  # noqa: PLC0415
    import pathlib  # noqa: PLC0415
    import sys  # noqa: PLC0415

    from app import premise as pm  # noqa: PLC0415
    from app.routers.user import _GEN_BRANCHES  # noqa: PLC0415

    path = pathlib.Path(__file__).resolve().parents[1] / "docs/ksr/llm_copy/branches.py"
    if not path.exists():
        pytest.skip("시험 코드가 없다 — docs/ksr/llm_copy/branches.py")
    spec = importlib.util.spec_from_file_location("_ksr_branches", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 가 제 모듈을 찾는다
    try:
        spec.loader.exec_module(mod)
        assert set(_GEN_BRANCHES) == set(mod.BRANCHES)
        for key, b in _GEN_BRANCHES.items():
            assert b["label"] == mod.BRANCHES[key].label, key
            assert pm.PREMISE_CATEGORY[b["premise"]].value == mod.BRANCHES[key].category, key
    finally:
        del sys.modules[spec.name]


def test_생성_입력은_분기와_판정_전제를_되돌려_그린다() -> None:
    r = _gen_post(category="hf", cert="no", name="지어낸 곡물바", age="30", sex="f")
    assert r.status_code == 200
    assert "건강기능식품 · 인증 아니오" in r.text
    assert "판정 전제 <b>식품</b>" in r.text  # 인정 없는 건강기능식품은 일반식품으로 생성한다
    assert "30대 여성" in r.text


def test_생성_입력은_분기에_안_맞는_칸을_읽지_않는다() -> None:
    """숨긴 칸의 값도 같이 넘어온다 — 「아니오」인데 예전 인증이 입력 사실로 남으면 안 된다."""
    r = _gen_post(name="지어낸 곡물바", certs="지어낸인증가나다", fixed="지어낸고정문구라마")
    assert r.status_code == 200
    assert "지어낸인증가나다" not in r.text
    assert "지어낸고정문구라마" not in r.text


@pytest.mark.parametrize(
    "data",
    [
        {},  # 제품 내용이 하나도 없다
        {"category": "food", "cert": "yes", "name": "지어낸 곡물바"},  # 인증 이름이 없다
        {"category": "hf", "cert": "yes", "name": "지어낸 영양제"},  # 인정 문구가 없다
        {"category": "cos", "cert": "yes", "name": "지어낸 크림"},  # 심사 문구가 없다
    ],
)
def test_생성_입력이_모자라면_고칠_곳을_보이고_엔진_대기를_그리지_않는다(data: dict) -> None:
    r = _gen_post(**data)
    assert r.status_code == 200
    assert 'class="gn-errors"' in r.text
    assert 'class="gn-pending"' not in r.text


@pytest.mark.parametrize(
    "data",
    [
        {"category": "zz"},  # 없는 분기
        {"age": "99"},  # 없는 대상 고객
        {"features": ",".join(f"특징{i}" for i in range(13))},  # 개수 상한
        {"features": "가" * 65},  # 항목 길이 상한
        {"name": "가" * 129},  # 칸 길이 상한
    ],
)
def test_생성_입력은_넘치거나_없는_값을_자르지_않고_거부한다(data: dict) -> None:
    assert _gen_post(**{"name": "지어낸 곡물바", **data}).status_code == 422


def test_후보에서_넘어온_문구와_병기_문구는_광고생성_제출까지_간다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    _fake_judge(
        monkeypatch, "pending"
    )  # 🔄 10-12 — 제출은 판정을 부른다. 엔진이 없을 때의 화면을 본다
    c = TestClient(app)
    first = c.post(
        "/u/compose", data={"carry": "1", "prompt": "지어낸 후보 문구", "note": "지어낸 병기 문구"}
    ).text
    assert ">지어낸 후보 문구</textarea>" in first
    assert 'name="note" value="지어낸 병기 문구"' in first
    assert "고르신 것" not in first  # 넘어온 것은 제출이 아니다 — 입력 화면을 그린다
    second = c.post(
        "/u/compose",
        data={"ad_format": "배너", "prompt": "지어낸 후보 문구", "note": "지어낸 병기 문구"},
    ).text
    assert "필수 병기 문구 「지어낸 병기 문구」" in second
    assert 'name="note" value="지어낸 병기 문구"' in second


@pytest.mark.gate
def test_인코더_후보는_판정_아님으로_그리고_확률을_보이지_않는다(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """🆕 2026-10-13 (D-330) — 인코더 유형 후보는 「판정 아님」을 달아 접힌 「근거 보기」 안에 그리고 확률(%)은 그리지 않는다.
    인코더 출력은 보정된 확률이 아니다 — 「N%」는 「N% 확률로 위반」으로 읽힌다 (D-330 안건 1 (나) · 보충 10-13 · D-323)."""
    import json  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415

    raw = json.loads((api.FIXTURE_ROOT / "judge" / "01_pass.json").read_text(encoding="utf-8"))
    raw["judged_by"] = "rule-0.3.0-dict+encb:abcdef123456"  # 🔄 D-333 — 판 지문 표지
    raw["sentences"][0]["encoder_candidates"] = [{"violation": "거짓_과장", "confidence": 0.917}]
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "enc_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)

    html = TestClient(api.app).get("/u/preview/enc_case").text
    assert "AI 추정 유형 — 판정 아님" in html, (
        "🔴 인코더 후보가 「판정 아님」 표지로 그려지지 않았다 (D-330 보충)"
    )
    assert "거짓 과장" in html, "🔴 인코더 후보의 유형이 그려지지 않았다"
    assert "추정 확신" not in html and "92%" not in html, "🔴 인코더 확률이 화면에 나왔다 (D-330)"


@pytest.mark.gate
@pytest.mark.parametrize(("violations", "marked"), [([], True), (["거짓_과장"], False)])
def test_사전_유형_없이_인코더_후보만_있으면_접힌_칸_밖에_표지를_단다(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, violations: list, marked: bool
) -> None:
    """🆕 2026-10-14 (D-330 보충 2) — 겉 표지는 「근거 보기」 앞에 · 유형 이름과 확률은 겉에 쓰지 않는다.
    사전 유형이 있는 문장에는 달지 않는다 — 유형 줄이 이미 있다."""
    import json  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415
    from app import reasons  # noqa: PLC0415

    raw = json.loads(
        (api.FIXTURE_ROOT / "judge" / "02_hold_low_conf.json").read_text(encoding="utf-8")
    )
    raw["judged_by"] = "rule-0.3.0-dict+encb:abcdef123456"
    raw["sentences"][0]["violations"] = violations
    raw["sentences"][0]["encoder_candidates"] = [{"violation": "소비자_기만", "confidence": 0.917}]
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "mark_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)

    html = TestClient(api.app).get("/u/preview/mark_case").text
    assert (reasons.GUESSED_TYPE_MARK in html) is marked
    if marked:
        head = html.split("<summary>근거 보기</summary>", 1)[0]
        assert reasons.GUESSED_TYPE_MARK in head, "🔴 겉 표지가 접힌 칸 안에 있다 (D-330 보충 2)"
        mark_line = head[head.index(reasons.GUESSED_TYPE_MARK) - 80 :]
        assert "소비자 기만" not in mark_line and "92%" not in html, (
            "🔴 겉에 유형 이름 · 확률을 썼다"
        )


@pytest.mark.gate
@pytest.mark.parametrize(("enc", "marked"), [("거짓_과장", True), ("소비자_기만", False)])
def test_보류_문장에서_사전과_인코더가_같은_유형이면_표시한다(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, enc: str, marked: bool
) -> None:
    """🆕 2026-10-14 (D-330 보충 3) — 사전 유형 후보 ∩ 인코더 유형 후보가 있으면 유형 줄에 「같은 유형」(줄 머리가 「확정 아님」을 말한다).
    판정은 바뀌지 않는다 — 보류 그대로다. 합의로 확정할지는 사전 재작업 때(D-313 ⬜)."""
    import json  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415
    from app import reasons  # noqa: PLC0415

    raw = json.loads(
        (api.FIXTURE_ROOT / "judge" / "02_hold_low_conf.json").read_text(encoding="utf-8")
    )
    raw["judged_by"] = "rule-0.3.0-dict+encb:abcdef123456"
    assert raw["sentences"][0]["verdict"] == "hold" and raw["sentences"][0]["violations"]
    raw["sentences"][0]["encoder_candidates"] = [{"violation": enc, "confidence": 0.9}]
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "agree_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)

    html = TestClient(api.app).get("/u/preview/agree_case").text
    assert (reasons.AGREED_MARK in html) is marked
    assert "유형 후보 — 확정 아님" in html, "🔴 표시가 판정(보류)을 바꿨다"


# ── 🆕 2026-10-12 (ksr) — AI 광고 생성 섹션 편집기. 종류 셋(SNS 피드 · 상세페이지 · 배너 300×250).
#    문구는 판정을 지나야 지면에 얹힌다 — 얹는 기준은 `_lands` 한 곳이다. 🚨 문구는 여기서 지어낸 것이다 (D-175)


def _sent(sid: str, text: str, how: str):  # noqa: ANN202
    """판정 문장 하나 — `ok`(확정 · R0) · `unsure`(유형 후보 없는 확신 부족 보류) · `cand`(후보 있는 보류) · `none`(미판정)."""
    from app.contracts import SentenceJudgment  # noqa: PLC0415

    extra = {
        "ok": {"verdict": "confirmed", "risk": {"floor": "R0", "final": "R0"}},
        "unsure": {"verdict": "hold", "hold_reason": "low_conf"},
        "cand": {"verdict": "hold", "hold_reason": "low_conf", "violations": ["거짓_과장"]},
        "none": {"verdict": "unjudged"},
    }[how]
    return SentenceJudgment.model_validate({"sent_id": sid, "text": text, **extra})


def _fake_judge(monkeypatch: pytest.MonkeyPatch, status: str, *sentences) -> list[str]:  # noqa: ANN002
    """`_core_judge` 를 갈아 끼운다 — 화면이 판정 결과를 어떻게 읽는지만 본다. 받은 문구를 돌려준다."""
    from types import SimpleNamespace  # noqa: PLC0415

    from app.routers import user as user_router  # noqa: PLC0415

    seen: list[str] = []

    def fake(text: str, product=None):  # noqa: ANN001, ANN202
        seen.append(text)
        if status != "ok":
            return status, None
        return "ok", SimpleNamespace(sentences=list(sentences))

    monkeypatch.setattr(user_router, "_core_judge", fake)
    return seen


def _draft_of(body: str) -> dict:
    import json  # noqa: PLC0415
    import re  # noqa: PLC0415

    m = re.search(r'<script type="application/json" id="de-data">(.*?)</script>', body, re.DOTALL)
    assert m, "🔴 편집기 초안 칸(#de-data)이 없다"
    return json.loads(m.group(1))


@pytest.mark.parametrize(
    ("how", "want"), [("ok", "ok"), ("unsure", "unsure"), ("cand", "ng"), ("none", "ng")]
)
def test_얹는_기준은_통과와_후보_없는_확신부족_보류뿐이다(how: str, want: str) -> None:
    """🚨 유형 후보가 붙은 보류 · 미판정은 얹지 않는다. 사전의 침묵(후보 없는 보류)은 「확인 필요」로 얹는다."""
    from app.routers import user as user_router  # noqa: PLC0415

    assert user_router._lands(_sent("s0", "지어낸 문구", how)) == want


@pytest.mark.parametrize(
    ("fmt", "key", "w", "h"),
    [
        ("SNS 피드", "sns", 1080, 1080),
        ("상세페이지", "detail", 860, None),
        ("배너", "banner", 300, 250),
    ],
)
def test_광고생성은_판정을_지난_문구로_편집기를_연다(
    monkeypatch: pytest.MonkeyPatch, fmt: str, key: str, w: int, h: int | None
) -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    seen = _fake_judge(
        monkeypatch,
        "ok",
        _sent("s0", "지어낸 첫 문장.", "ok"),
        _sent("s1", "지어낸 둘째 문장.", "unsure"),
    )
    body = (
        TestClient(app)
        .post(
            "/u/compose",
            data={
                "ad_format": fmt,
                "prompt": "지어낸 첫 문장. 지어낸 둘째 문장.",
                "note": "지어낸 병기 문구",
            },
        )
        .text
    )
    assert seen == ["지어낸 첫 문장. 지어낸 둘째 문장."]
    draft = _draft_of(body)
    assert (draft["key"], draft["w"], draft["h"]) == (key, w, h)
    assert draft["copy"] == [
        {"text": "지어낸 첫 문장.", "unsure": False},
        {"text": "지어낸 둘째 문장.", "unsure": True},
    ]
    assert draft["note"] == "지어낸 병기 문구"
    assert 'src="/static/user_compose.js"' in body
    assert 'name="ad_format"' not in body  # 편집기가 뜨면 입력 폼은 감춘다
    # 「종류 다시 고르기」가 문구와 병기 문구를 들고 돌아간다
    assert 'name="note" value="지어낸 병기 문구"' in body


def test_광고생성은_얹지_못하는_문장이_있으면_편집기를_열지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🚨 판정을 지나지 않은 문구는 지면에 얹히지 않는다 (D-63 · D-119) — 그 판정을 그리고 입력 화면에 남는다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    _fake_judge(
        monkeypatch,
        "ok",
        _sent("s0", "지어낸 첫 문장.", "ok"),
        _sent("s1", "지어낸 둘째 문장.", "cand"),
    )
    body = (
        TestClient(app)
        .post(
            "/u/compose", data={"ad_format": "배너", "prompt": "지어낸 첫 문장. 지어낸 둘째 문장."}
        )
        .text
    )
    assert 'id="de-data"' not in body
    assert "user_compose.js" not in body
    assert "얹을 수 없는 문장이 <b>1건</b>" in body
    assert "입력 판정" in body
    assert 'value="배너" checked' in body
    assert body.count("지면에 배치되지 않아요") == 1  # 얹지 못하는 문장에만 적는다


def test_광고생성은_없는_종류와_빈_문구를_판정에_보내지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    seen = _fake_judge(monkeypatch, "ok", _sent("s0", "지어낸 문구", "ok"))
    c = TestClient(app)
    # 계약의 「카드뉴스」는 화면의 종류 셋에 없다 — 다른 종류로 바꿔 받지 않고 거부한다
    assert (
        c.post("/u/compose", data={"ad_format": "카드뉴스", "prompt": "지어낸 문구"}).status_code
        == 422
    )
    blank = c.post("/u/compose", data={"ad_format": "배너", "prompt": "   "})
    assert blank.status_code == 200
    assert "광고에 담을 문구를 적어 주세요." in blank.text
    assert seen == []


def test_광고생성_초안_칸은_적은_문구로_스크립트를_닫지_못한다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 초안은 JSON 칸으로 넘긴다 — 문구의 `</script>` 가 그 칸을 닫으면 뒤가 HTML 로 읽힌다 (P2-9)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    evil = "</script><b>지어낸 문구</b>"
    _fake_judge(monkeypatch, "ok", _sent("s0", evil, "ok"))
    body = (
        TestClient(app)
        .post("/u/compose", data={"ad_format": "배너", "prompt": evil, "note": evil})
        .text
    )
    assert evil not in body
    assert _draft_of(body)["copy"][0]["text"] == evil


@pytest.mark.parametrize(
    ("hows", "status", "want"),
    [
        (("ok",), "ok", "ok"),
        (("ok", "unsure"), "ok", "unsure"),
        (("unsure", "cand"), "ok", "ng"),
        ((), "pending", "pending"),
        ((), "down", "down"),
    ],
)
def test_편집기_칸_판정은_얹을지를_상태_하나로_돌려준다(
    monkeypatch: pytest.MonkeyPatch, hows: tuple[str, ...], status: str, want: str
) -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    _fake_judge(
        monkeypatch, status, *[_sent(f"s{i}", f"지어낸 문장 {i}", h) for i, h in enumerate(hows)]
    )
    r = TestClient(app).post("/u/compose/judge", json={"text": "지어낸 문구"})
    assert r.status_code == 200
    got = r.json()
    assert got["state"] == want
    # 얹지 못하는 문장만 까닭과 함께 싣는다
    if want == "ng":
        assert got["notes"] == [{"text": "지어낸 문장 1", "why": "보류 — 확신 부족 (거짓 과장)"}]
    else:
        assert got["notes"] == []


def test_편집기_칸_판정은_JSON_본문만_받는다(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.settings import PARAMS  # noqa: PLC0415

    seen = _fake_judge(monkeypatch, "ok", _sent("s0", "지어낸 문구", "ok"))
    c = TestClient(app)
    assert c.post("/u/compose/judge", data={"text": "지어낸 문구"}).status_code == 415
    assert c.post("/u/compose/judge", json={"text": "  "}).status_code == 422
    assert c.post("/u/compose/judge", json={"nope": 1}).status_code == 422
    assert c.post("/u/compose/judge", json=["지어낸 문구"]).status_code == 422
    too_long = "가" * (PARAMS.max_text_len + 1)
    assert c.post("/u/compose/judge", json={"text": too_long}).status_code == 422
    assert seen == []


@pytest.mark.gate
@pytest.mark.parametrize(
    ("value", "want"),
    [("unknown", "미확인"), ("", "미확인"), (None, "미확인"), ("2026-10-01", "2026-10-01")],
)
def test_모르는_법령판은_미확인으로_그린다(value: object, want: str) -> None:
    """🆕 2026-10-13 — 화면은 내부 값 `unknown` 을 그리지 않는다 · 빈 값도 「미확인」이다 (D-220)."""
    from app.templating import law_version_label

    assert law_version_label(value) == want


# ══════════════════════════════════════════════════════════════════════
#  카피 생성은 로그인한 회원만 (🆕 2026-10-14 권소라 · `_gen_gate`)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.gate
def test_비회원은_카피_생성_폼_대신_로그인_안내를_본다() -> None:
    """로그인 벽이 아니다(200 · D-66) — 폼 자리에 안내와 로그인 · 회원가입 두 갈래를 그린다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).get("/u/generate")
    assert r.status_code == 200, f"🔴 로그인 벽을 세웠다 — {r.status_code}"
    assert "로그인한 회원만 이용할 수 있어요" in r.text, "🔴 회원 전용 안내가 없다"
    assert 'href="/u/login?next=/u/generate"' in r.text, "🔴 로그인으로 가는 길이 없다"
    assert 'href="/u/signup?next=/u/generate"' in r.text, "🔴 회원가입으로 가는 길이 없다"
    assert 'id="gen-form"' not in r.text, "🔴 비회원에게 생성 폼을 그렸다"


@pytest.mark.gate
def test_비회원의_생성_제출은_엔진에_닿지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 화면만 가리면 제출이 열려 있다 — 생성은 밖(GPT)을 부르고 요금이 든다. 제출도 같은 문지기를 지난다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.routers import copygen  # noqa: PLC0415

    called: list[str] = []
    monkeypatch.setattr(copygen, "off_reason", lambda: None)
    monkeypatch.setattr(copygen, "generate", lambda *_a, **_k: called.append("generate"))
    data = {"category": "food", "cert": "no", "age": "all", "sex": "all", "name": "지어낸 곡물바"}
    r = TestClient(app).post("/u/generate", data=data)
    assert r.status_code == 401, f"🔴 비회원 제출을 받았다 — {r.status_code}"
    assert called == [], "🔴 비회원 제출이 생성 엔진을 불렀다"
    assert "로그인한 회원만 이용할 수 있어요" in r.text


def test_회원은_카피_생성_폼을_본다(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    monkeypatch.setattr(user_router, "current_user", lambda *_a: SimpleNamespace(name="테스트"))
    r = TestClient(app).get("/u/generate")
    assert r.status_code == 200
    assert 'id="gen-form"' in r.text, "🔴 회원에게 생성 폼이 안 떴다"
    assert "로그인한 회원만 이용할 수 있어요" not in r.text


@pytest.mark.gate
@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("/u/generate", "/u/generate"),
        ("/u/history", "/u/history"),
        ("", "/u/"),
        (None, "/u/"),
        ("https://evil.example/u/generate", "/u/"),
        ("//evil.example", "/u/"),
        ("/admin", "/u/"),
        ("/u/generate?x=1", "/u/"),
        ("/u/login", "/u/"),
        ("/u/signup", "/u/"),
    ],
)
def test_로그인_뒤_돌아갈_곳은_사용자_화면_안의_경로만_받는다(value: str | None, want: str) -> None:
    """🔴 열린 리다이렉트 방지 — 밖의 주소 · 다른 구역 · 로그인 화면 자신은 홈으로 돌린다."""
    from app.routers.user import _next_path  # noqa: PLC0415

    assert _next_path(value) == want


def test_로그인_가입_화면은_돌아갈_곳을_폼에_싣는다() -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    c = TestClient(app)
    for path, other in (("/u/login", "/u/signup"), ("/u/signup", "/u/login")):
        body = c.get(f"{path}?next=/u/generate").text
        assert '<input type="hidden" name="next" value="/u/generate">' in body, f"🔴 {path}"
        assert f'href="{other}?next=/u/generate"' in body, f"🔴 {path} — 옆 화면으로 갈 때 잃는다"
        plain = c.get(path).text
        assert 'name="next"' not in plain, f"🔴 {path} — 돌아갈 곳이 없는데 칸을 그렸다"
        bad = c.get(f"{path}?next=https://evil.example/").text
        assert 'name="next"' not in bad and "evil.example" not in bad, (
            f"🔴 {path} — 밖의 주소를 실었다"
        )
