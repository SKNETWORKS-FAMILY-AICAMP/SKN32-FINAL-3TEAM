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
        "/u/mypage",
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
    for path in ("/u/", "/u/mypage", "/u/cs"):
        body = client.get(path).text
        assert 'class="user-sidebar"' not in body, f"🔴 {path} 에 사이드바가 붙었다 — 구역 밖이어야 한다"


def test_활성_pill과_사이드바_항목에_활성_표시가_붙는다() -> None:
    """🚨 지금 보고 있는 구역·항목이 시각적으로 구분돼야 한다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/matching").text
    assert "user-topnav-pill user-topnav-pill-active" in body, "🔴 매칭 pill 에 활성 표시가 안 붙는다"
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

    r = TestClient(app).get("/u/preview/01_pass_frontier")
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


def test_마이페이지_저장은_저장하지_않는다() -> None:
    """🚨 계정 테이블이 없다 — 저장했다고 말하지 않는다 (D-147)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post("/u/mypage", content=b"name=%EA%B6%8C%EC%86%8C%EB%9D%BC")
    assert r.status_code == 200
    assert "아직 저장되지 않았어요" in r.text


def test_랜딩은_governor_로그인이_아니라_일반_회원_로그인으로_보낸다() -> None:
    """🔴 `/login`(governor 전용)으로 잘못 보내던 걸 `/u/login`·`/u/signup`으로 고쳤다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/landing").text
    assert 'href="/u/login"' in body
    assert 'href="/u/signup"' in body
