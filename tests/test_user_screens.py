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


def test_상단에_작업메뉴와_이용가이드가_통합된다() -> None:
    from fastapi.testclient import TestClient

    from app.api import app

    body = TestClient(app).get("/u/review").text
    nav = body.split('<nav class="user-topnav"', 1)[1].split("</nav>", 1)[0]
    for label in ("홈", "문구 검수", "카피 생성", "AI 광고 생성", "검수 이력"):
        assert f">{label}</a>" in nav
    assert "이용 가이드" in nav
    assert ">매칭</a>" not in nav
    assert 'src="/static/brand/symbol-180.png"' in nav
    for href in ("/u/help?tab=guide", "/u/help?tab=faq", "/u/cs"):
        assert f'href="{href}"' in nav
    assert 'aria-current="page"' in body


def test_사이드바에_하위_화면이_새지_않는다() -> None:
    """🔴 segments 는 사이드바 항목이 아니다 (back-link 로만 진입)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/review").text
    assert 'href="/u/segments"' not in body, "🔴 하위 화면이 사이드바에 새어나왔다"


def test_작업_화면은_사이드바_없이_공통_상단메뉴를_쓴다() -> None:
    from fastapi.testclient import TestClient

    from app.api import app

    client = TestClient(app)
    for path in ("/u/review", "/u/cs", "/u/compose"):
        body = client.get(path).text
        assert 'class="user-sidebar"' not in body
        assert 'id="cl-user-navigation"' in body
        for label in ("홈", "문구 검수", "카피 생성", "AI 광고 생성", "검수 이력"):
            assert label in body


def test_현재_작업이_상단메뉴에서_선택된다() -> None:
    from fastapi.testclient import TestClient

    from app.api import app

    body = TestClient(app).get("/u/review").text
    assert 'href="/u/review" aria-current="page"' in body


def test_copylane_소개_탭이_사용방법과_FAQ를_가른다() -> None:
    """🚨 디자인은 사용방법·자주 묻는 질문을 같은 화면의 탭으로 둔다 (?tab= 로 서버 렌더)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    client = TestClient(app)
    guide = client.get("/u/help?tab=guide").text
    faq = client.get("/u/help?tab=faq").text
    assert "사용방법" in guide
    assert "자주 묻는 질문" in faq
    assert 'href="/u/help?tab=guide" aria-current="page"' in guide
    assert 'href="/u/help?tab=faq" aria-current="page"' in faq


@pytest.mark.parametrize(
    ("topic", "title", "href"),
    [
        ("review", "광고 문구, 이렇게 확인하세요", "/u/review"),
        ("copy", "제품 정보로 새 문구를 만들어보세요", "/u/generate"),
        ("ad", "문구를 광고 형식에 맞춰 구성해요", "/u/compose"),
        ("unknown", "광고 문구, 이렇게 확인하세요", "/u/review"),
    ],
)
def test_이용가이드_목적별_내용과_실행화면이_연결된다(topic: str, title: str, href: str) -> None:
    from fastapi.testclient import TestClient

    from app.api import app

    response = TestClient(app).get("/u/help", params={"topic": topic})
    assert response.status_code == 200
    assert f'<h2 id="hg-guide-title">{title}</h2>' in response.text
    assert f'class="hg-launch" href="{href}"' in response.text
    assert response.text.count('class="hg-step"') == 4
    assert response.text.count('class="hg-purpose is-active"') == 1


def test_검수_POST가_문구를_되돌려_그린다() -> None:
    """🚨 `POST /u/judge` 는 가짜 결과 없이 넣은 문구만 되돌린다 (D-147 · P2-9 이스케이프)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post("/u/judge", content=b"text=<script>x</script>")
    assert r.status_code == 200
    assert "<script>" not in r.text, "🔴 이스케이프 안 된 문구가 그대로 나왔다 (XSS)"
    assert "&lt;script&gt;" in r.text


def _textareas(html: str) -> list[str]:
    """검수 화면의 문구 칸 값들 (순서대로)."""
    import html as h  # noqa: PLC0415
    import re  # noqa: PLC0415

    return [
        h.unescape(v)
        # 🔄 10-21 — 문구 칸 복제용 `<template>` 안의 빈 칸은 제출되지 않는다 — 세지 않는다
        for v in re.findall(
            r'<textarea[^>]*name="text"[^>]*>(.*?)</textarea>',
            re.sub(r"<template\b.*?</template>", "", html, flags=re.S),
            re.S,
        )
    ]


@pytest.mark.parametrize("filled", [0, 1, 4])
def test_빈_문구_칸이_있어도_추가는_5칸까지_된다(filled: int) -> None:
    """🚨 빈 칸을 버리면 칸이 2개에서 멈췄다 (시나리오 테스트 10-14 · `_form` 의 `keep_blank_values`)."""
    from urllib.parse import urlencode  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    c = TestClient(app)
    copies = [""]
    for _ in range(4):
        copies = [f"문구{i}" if i < filled else t for i, t in enumerate(copies)]
        body = urlencode([*(("text", t) for t in copies), ("op", "add")])
        r = c.post(
            "/u/judge",
            content=body.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        copies = _textareas(r.text)
    assert len(copies) == 5
    body = urlencode([*(("text", t) for t in copies), ("op", "add")])
    r = c.post(
        "/u/judge",
        content=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert len(_textareas(r.text)) == 5
    assert "최대 5건" in r.text


def test_빈_칸이_섞여도_칸_번호가_어긋나지_않는다() -> None:
    """🚨 1번이 비고 2번에 문구가 있을 때 — 삭제 · 예시 넣기가 다른 칸을 건드리거나 422 가 나면 안 된다."""
    from urllib.parse import urlencode  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    c = TestClient(app)
    hdr = {"Content-Type": "application/x-www-form-urlencoded"}

    def post(texts: list[str], op: str):  # noqa: ANN202
        return c.post(
            "/u/judge",
            content=urlencode([*(("text", t) for t in texts), ("op", op)]).encode(),
            headers=hdr,
        )

    r = post(["", ""], "del:2")
    assert r.status_code == 200 and _textareas(r.text) == [""]
    r = post(["", "붓기 관리"], "sample:1")
    assert r.status_code == 200
    got = _textareas(r.text)
    assert len(got) == 2 and got[0] and got[1] == "붓기 관리", "🔴 예시 넣기가 2번 칸 문구를 지웠다"
    r = post(["", "붓기 관리"], "del:1")
    assert _textareas(r.text) == ["붓기 관리"]


def test_줄바꿈은_한_글자로_센다() -> None:
    """🚨 브라우저는 줄바꿈을 1자로 세고 `\\r\\n` 으로 보낸다 — 화면에서 2000자 안이면 서버도 받아야 한다 (10-14)."""
    from urllib.parse import urlencode  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.settings import PARAMS  # noqa: PLC0415

    line = "피부 보습에 좋아요."
    n = PARAMS.max_text_len // (len(line) + 1)
    text = "\r\n".join([line] * n)
    assert len(text.replace("\r\n", "\n")) <= PARAMS.max_text_len < len(text)
    r = TestClient(app).post(
        "/u/judge",
        content=urlencode([("text", text), ("op", "add")]).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, "🔴 줄바꿈을 2자로 세서 거부했다"
    assert _textareas(r.text)[0] == text.replace("\r\n", "\n")


def test_다섯_칸을_꽉_채운_한글_문구도_받는다() -> None:
    """🚨 본문 상한이 칸 하나 몫이라 2000자 한글 두 칸이면 413 이 났다 (10-14). 퍼센트 인코딩 한글은 글자당 9바이트다."""
    from urllib.parse import urlencode  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.settings import PARAMS  # noqa: PLC0415

    full = "가" * PARAMS.max_text_len
    r = TestClient(app).post(
        "/u/judge",
        content=urlencode([*(("text", full),) * 5, ("op", "add")]).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"🔴 {r.status_code} — 다섯 칸을 채운 문구를 거부했다"
    assert "최대 5건" in r.text


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


def test_랜딩_로그인_상태에는_작업_바로가기를_표시한다(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.api import app
    from app.routers import user as user_router

    monkeypatch.setattr(
        user_router, "_nav_user", lambda _request: SimpleNamespace(name="유저", initials="유")
    )
    response = TestClient(app).get("/u/landing")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "유저 님 계정 메뉴" in response.text
    assert "문구 검수하기 →" in response.text
    assert "작업 공간으로 돌아가기 →" in response.text
    assert 'href="/u/login"' not in response.text
    assert 'href="/u/signup"' not in response.text
    assert "로그인 없이 문구 검수해 보기" not in response.text


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
    # 🔄 10-21 — 「이용 가이드」는 상단 드롭다운 제목이 됐고, 안의 「사용방법」이 가이드 탭으로 간다
    assert "이용 가이드" in body and 'href="/u/help?tab=guide"' in body


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
    assert "재검수 0/5" in body
    assert 'value="redo:1"' in body
    assert 'type="checkbox" id="rvr-' not in body


@pytest.mark.gate
def test_품목을_모르면_고르기_전에는_품목_선택만_안내한다() -> None:
    """🆕 2026-10-18 (D-348 보충 18) — 품목을 모르면 고르기 전 자리(`rv-rec`)에 기록 판정(「모름」 입력의 후보 · 질문 · 판정)을 그리지 않는다 ·
    품목을 고르면 그 품목의 분기 결과가 보인다 · 지적 건수 자리는 「특이사항 없음」이 아니라 「품목 선택 필요」다.
    품목을 아는데 인증 여부만 모르면(건강기능식품) 종전대로 기록 판정을 보인다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    body = TestClient(app).get("/u/preview/03_hold_cat_unknown").text
    recs = [part.split('class="rv-round ')[0] for part in body.split('<div class="rv-rec">')[1:]]
    assert recs and all("rv-wait" in r for r in recs), "고르기 전 자리에 품목 선택 안내가 있다"
    assert all("rv-sent" not in r and "rv-todo" not in r for r in recs), (
        "🔴 고르기 전 자리에 문장 판정 · 질문이 그려졌다"
    )
    assert 'class="rv-res rv-res-food"' in body, "품목을 고르면 볼 분기 결과는 그대로 있다"
    assert 'content: "품목 선택 필요"' in body
    known = TestClient(app).get("/u/preview/15_hold_premise_unknown").text
    krec = [part.split('class="rv-round ')[0] for part in known.split('<div class="rv-rec">')[1:]]
    assert krec and all("rv-wait" not in r for r in krec), "품목을 알면 기록 판정을 그대로 보인다"


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
    assert "생성 기준 <b>식품</b>" in r.text  # 인정 없는 건강기능식품은 일반식품으로 생성한다
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
    import re  # noqa: PLC0415

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
    assert re.search(r'src="/static/user_compose\.js(?:\?[^"]*)?"', body)
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


# ── 2026-10-15 전수 점검 — 빈 칸 · 이벤트 루프 · 엔진 장애 문구 ─────────────────────────────


def _judge_fixture():  # noqa: ANN202
    from app.contracts import JudgeResponse  # noqa: PLC0415

    path = Path(__file__).parent / "fixtures" / "judge" / "02_hold_low_conf.json"
    return JudgeResponse.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.gate
def test_빈_문구_칸도_칸_번호를_지킨다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 재현 — 빈 칸(`text=`)을 버리면 뒤 칸 번호가 당겨진다. 「문구 추가 → 예시 넣기」가 422 였고,
    가운데 칸이 빈 채 `judge:3` 을 누르면 「그런 칸이 없다」, `judge:2` 는 셋째 칸을 「문구 2」로 판정했다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    seen: list[str] = []

    def fake(text, product=None):  # noqa: ANN001, ANN202
        seen.append(text)
        return ("ok", _judge_fixture())

    monkeypatch.setattr(user_router, "_core_judge", fake)
    client = TestClient(app)
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    # 칸 둘(둘째는 방금 추가해 빈 칸) → 둘째 칸에 예시 넣기
    r = client.post("/u/judge", content=b"text=AAA&text=&op=sample%3A2", headers=form)
    assert r.status_code == 200, r.text
    assert user_router._SAMPLE_COPY in r.text
    # 칸 셋(가운데 빈 칸) → 셋째 칸만 판정
    r = client.post("/u/judge", content=b"text=AAA&text=&text=CCC&op=judge%3A3", headers=form)
    assert r.status_code == 200, r.text
    assert seen == ["CCC"]
    # 칸 셋 → 칸 추가는 넷을 그린다(빈 칸을 잃지 않는다)
    r = client.post("/u/judge", content=b"text=AAA&text=&text=CCC&op=add", headers=form)
    assert r.text.count('name="text"') >= 4


@pytest.mark.gate
def test_검수는_판정_코어를_이벤트_루프_밖에서_부른다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 재현 — `async` 라우트에서 동기 판정 코어를 그대로 부르면 한 사람의 검수가 서버 전체를 멈춘다.
    코어가 도는 스레드가 이벤트 루프의 스레드와 달라야 한다(`run_in_threadpool`)."""
    import threading  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    threads: dict[str, int] = {}
    real_render = user_router._render

    def fake(text, product=None):  # noqa: ANN001, ANN202
        threads["core"] = threading.get_ident()
        return ("ok", _judge_fixture())

    def render(*a, **k):  # noqa: ANN002, ANN003, ANN202
        threads["loop"] = threading.get_ident()  # `_render` 는 라우트 본문(루프)에서 불린다
        return real_render(*a, **k)

    monkeypatch.setattr(user_router, "_core_judge", fake)
    monkeypatch.setattr(user_router, "_render", render)
    r = TestClient(app).post(
        "/u/judge",
        content=b"text=AAA&op=all",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    assert threads["core"] != threads["loop"]


@pytest.mark.gate
@pytest.mark.parametrize(
    ("code", "want", "not_want"),
    [
        (503, "연결하지 못했어요", "아직 붙지 않았어요"),
        (501, "아직 붙지 않았어요", "연결하지 못했어요"),
    ],
)
def test_검수_화면은_엔진_장애와_미착수를_다르게_그린다(
    monkeypatch: pytest.MonkeyPatch, code: int, want: str, not_want: str
) -> None:
    """🔴 재현 — 503(연결 실패)을 「아직 붙지 않았어요」로 그렸다. 광고 생성 화면과 같은 말로 가른다."""
    from fastapi import HTTPException  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api  # noqa: PLC0415
    from app.api import app as web  # noqa: PLC0415

    def boom(_req):  # noqa: ANN001, ANN202
        raise HTTPException(code)

    monkeypatch.setattr(app.api, "judge", boom)
    body = (
        TestClient(web)
        .post(
            "/u/judge",
            content=b"text=AAA&op=all",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        .text
    )
    assert want in body
    assert not_want not in body


# ── 2026-10-15 (D-340 결정 1 · 3 · 4 집행 · D-344 ⑨) ────────────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize(
    ("enc", "moved", "marked"),
    [
        ("거짓_과장", None, True),
        ("건강기능식품_오인", None, False),
        ("거짓_과장", "건강기능식품_오인", False),
    ],
)
def test_사전_확정에_인코더가_다른_유형을_내면_근거_보기_안에_표시한다(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, enc: str, moved: str | None, marked: bool
) -> None:
    """D-340 결정 3 — 사전 확정은 인코더가 뒤집지 않는다 · 다른 유형은 「AI 추정 유형 다름 — 판정 아님」 표시만. 유형 이름은 접힌 칸 안에만
    (D-330 보충 2). 옮긴 후보는 세지 않는다(칸 판단 · `agreed_types` 와 같은 거름)."""
    import json  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415
    from app import reasons  # noqa: PLC0415

    raw = json.loads(
        (api.FIXTURE_ROOT / "judge" / "05_certificate_a.json").read_text(encoding="utf-8")
    )
    raw["judged_by"] = "rule-0.3.0-dict+encb:abcdef123456"
    assert raw["sentences"][0]["violations"] == ["건강기능식품_오인"]
    cand = {"violation": enc, "confidence": 0.9}
    if moved:
        cand["moved_from"] = moved
    raw["sentences"][0]["encoder_candidates"] = [cand]
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "diff_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)
    html = TestClient(api.app).get("/u/preview/diff_case").text
    assert (reasons.ENC_DIFFERS_MARK in html) is marked
    if marked:
        head, inner = html.split("<summary>근거 보기</summary>", 1)
        assert reasons.ENC_DIFFERS_MARK not in head, (
            "🔴 겉에 그렸다 — 유형 이름은 접힌 칸 안에만 (D-330 보충 2)"
        )
        assert f"{reasons.ENC_DIFFERS_MARK} · 거짓 과장" in inner


@pytest.mark.gate
def test_조합_판정_칸은_reasons_한_곳이고_평가_도구가_그것을_쓴다() -> None:
    """D-340 결정 1 — 칸 판단은 `app/reasons.py` 한 곳. 평가 도구는 행 단위 예측을 넣는다."""
    from app import reasons  # noqa: PLC0415
    from scripts import eval_graph as eg  # noqa: PLC0415

    c = reasons.COMBO_CELLS
    assert eg.COMBO_CELLS is c
    cases = [
        ((True, ["거짓_과장"], ["소비자_기만"]), c[0]),
        ((False, ["거짓_과장"], ["거짓_과장"]), c[1]),
        ((False, ["거짓_과장"], ["소비자_기만"]), c[2]),
        ((False, ["거짓_과장"], []), c[3]),
        ((False, [], ["거짓_과장"]), c[4]),
        ((False, [], []), c[5]),
    ]
    for (committed, dq, en), want in cases:
        assert reasons.combo_cell(committed, dq, en) == want
        assert (
            eg.combo_cell({"committed": committed, "candidates": dq, "enc_candidates": en}) == want
        )


@pytest.mark.gate
def test_결정_4_는_새_글자를_두지_않고_AI_추정_없음_줄로_갈음한다(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """D-344 ⑨ (가) — 사전 확정 ∧ 인코더 조용(D-340 결정 4)은 「근거 보기」의 「AI 추정 유형 없음 — …」 줄이 표시다.
    「AI 위반 신호 없음」은 확정 위반 옆에서 AI 가 반대한 것처럼 읽혀 그리지 않는다."""
    import json  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    import app.api as api  # noqa: PLC0415

    raw = json.loads(
        (api.FIXTURE_ROOT / "judge" / "05_certificate_a.json").read_text(encoding="utf-8")
    )
    raw["judged_by"] = "rule-0.3.0-dict+encb:abcdef123456"
    raw["sentences"][0]["encoder_candidates"] = []
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "quiet_case.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURE_ROOT", tmp_path)
    html = TestClient(api.app).get("/u/preview/quiet_case").text
    inner = html.split("<summary>근거 보기</summary>", 1)[1]
    assert "AI 추정 유형 없음 — 「문제없음」이라는 뜻은 아니에요." in inner
    assert "AI 위반 신호 없음" not in html
