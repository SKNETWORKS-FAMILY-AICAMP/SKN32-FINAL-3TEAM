"""사용자 화면 nav 재구성 + ksr↔lse 병합 — 소유자 lse (병렬작업 계약 §5 · 2026-09-16).

★ ksr(skn32/ksr)의 review·generate·compose·mypage·landing 구현과 lse의 nav(4-pill+
  사이드바)·history(필터·페이지네이션·상세)를 합친 뒤의 회귀 확인이다.
  `docs/lse/ksr_lse_화면중복_비교_2026-09-16.md` 참고.
"""

from __future__ import annotations

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

    body = TestClient(app).get("/u/").text
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


@pytest.mark.parametrize("fmt", ["카드뉴스", "배너"])
def test_광고생성은_고른_종류와_내용을_다시_그린다(fmt: str) -> None:
    """🔄 10-08 (lse) — 「상세페이지」에 checked 가 박혀 있어 다른 종류를 골라 제출해도 상세페이지로 돌아갔다 · 적은 내용도 비었다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).post("/u/compose", data={"ad_format": fmt, "prompt": "보습 제품"}).text
    assert f'value="{fmt}" checked' in body
    assert 'value="상세페이지" checked' not in body
    assert ">보습 제품</textarea>" in body


def test_광고생성_미리보기는_픽스처의_종류에_체크한다() -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/compose/preview/12_compose_from_b").text
    assert 'value="카드뉴스" checked' in body
    assert 'value="상세페이지" checked' not in body


# ── 🆕 2026-10-10 — 카피 생성의 새 입력(분기 6종 + 제품 내용 · ksr 10-08)과 후보 → 광고 생성 넘기기.
#    흡수할 때 이 길을 타는 테스트가 없었다. 🚨 문구 · 이름은 여기서 지어낸 것이다 (D-175 · D-249)


def _gen_post(**data: str):  # noqa: ANN202
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    base = {"category": "food", "cert": "no", "age": "all", "sex": "all"}
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


def test_후보에서_넘어온_문구와_병기_문구는_광고생성_제출까지_간다() -> None:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

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
