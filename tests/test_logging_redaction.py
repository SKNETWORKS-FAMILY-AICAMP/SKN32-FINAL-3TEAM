"""로그에 **광고 문구가 안 실리는가** (2026-09-12 밤 · 보안점검 P1-4 · D-76).

⛔ **무엇이 있었나** — 보안점검이 *"가장 중요한 발견"* 이라 표시한 P1-4 의 조치가
   **하나도 반영돼 있지 않았고**, `app/` 전체에 `logging` 이 한 줄도 없었다.
   그리고 `/search` 가 문구를 **GET 쿼리스트링**으로 받고 있었다 — P1-4 가
   *"문구는 절대 URL 에 싣지 않는다"* 라고 못박은 바로 그 형태다.

★ **막는 것이 셋이다** — 여기서 셋을 다 잰다.
   1. 문구가 URL 에 안 실린다 (`/search` 는 POST)
   2. 그래도 새면 필터가 지운다 (`RedactFilter`)
   3. 코드가 참조하면 `mask()` 를 지난다

🚨 **넘치게 지우는 쪽으로 틀린다** (D-72). 덜 지우면 문구가 새고, 더 지우면 로그가 조금 답답하다.
"""

from __future__ import annotations

import logging

import pytest

from app.logging_conf import RedactFilter, fingerprint, mask, redact, setup_logging

#: 실제로 샐 모양들. 🚨 uvicorn 접근 로그는 **인코딩된 것과 풀린 것** 둘 다 나온다.
_LEAKY = (
    '127.0.0.1 - "GET /search?q=우리 제품은 면역력이 쑥쑥&category=건기식 HTTP/1.1" 200',
    "GET /search?q=%EB%A9%B4%EC%97%AD%EB%A0%A5%EC%9D%B4%20%EC%91%A5%EC%91%A5 HTTP/1.1",
    "text=면역력이 쑥쑥",
    "prompt: 이 제품은 암을 예방합니다",
)

#: 지우면 안 되는 것 — **넘치게 지운다고 아무거나 지우면 로그가 쓸모없어진다.**
_KEEP = (
    '127.0.0.1 - "POST /search HTTP/1.1" 200',
    '"GET /docs HTTP/1.1" 200',
    "DB 접속 실패 원인=OperationalError",
    "chunk_id=abc123 · part_no=2",
)


@pytest.mark.gate
@pytest.mark.parametrize("line", _LEAKY)
def test_문구가_로그에_안_남는다(line: str) -> None:
    """🔴 **P1-4 의 실물.** 원문 조각이 남으면 D-76 의 열람 경계가 로그에서 무너진다."""
    out = redact(line)
    for leak in ("면역력", "쑥쑥", "암을 예방", "%EB%A9%B4"):
        assert leak not in out, f"🔴 로그에 문구가 남았다: {out}"
    assert "가림" in out, f"🔴 가린 흔적이 없다 — 지워졌는지 알 수 없다: {out}"


@pytest.mark.gate
@pytest.mark.parametrize("line", _KEEP)
def test_안_지워도_되는_것은_남는다(line: str) -> None:
    """⛔ 다 지우면 장애를 못 쫓는다. 필터는 **그물이지 벽이 아니다.**"""
    assert redact(line) == line, f"🔴 지우지 말아야 할 줄이 지워졌다: {redact(line)}"


@pytest.mark.gate
def test_가린_값은_되돌릴_수_없고_같은지는_물을_수_있다() -> None:
    """🚨 지문이라 **무슨 문구였는지는 못 읽고, 같은 문구였는지는 물을 수 있다.**"""
    a, b = "면역력이 쑥쑥", "면역력이 쑥쑥"
    assert mask(a) == mask(b)
    assert mask(a) != mask("다른 문구")
    assert a not in mask(a)
    assert len(fingerprint(a)) == len("sha256:") + 8


@pytest.mark.gate
def test_필터가_접근_로그에_붙어_있다() -> None:
    """🔴 **`uvicorn.access` 가 핵심이다** — 경로가 거기로 나간다.

    ⛔ 필터를 만들어 두고 안 붙이면 없는 것과 같다 (D-170 — 통과만 하는 검사는 장식이다).
    """
    setup_logging()
    for name in ("uvicorn.access", ""):
        logger = logging.getLogger(name)
        assert any(isinstance(f, RedactFilter) for f in logger.filters), (
            f"🔴 로거 {name!r} 에 RedactFilter 가 없다 — 접근 로그가 문구를 그대로 찍는다"
        )


@pytest.mark.gate
def test_필터가_레코드의_args_도_본다() -> None:
    """🚨 uvicorn 은 경로를 `msg` 가 아니라 **`args`** 로 넘긴다 — `msg` 만 보면 안 걸린다."""
    rec = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/search?q=면역력이 쑥쑥", "1.1", 200),
        None,
    )
    RedactFilter().filter(rec)
    assert "면역력" not in (rec.getMessage()), f"🔴 args 가 안 가려졌다: {rec.getMessage()}"


def test_음성_픽스처_필터를_빼면_샌다() -> None:
    """🚨 게이트가 아니다 — **필터가 일한다는 것을 잰다** (D-203).

    ⛔ 위 검사들이 전부 통과해도 「원래 안 새는 문자열이었다」면 아무것도 증명 못 한다.
    """
    leaky = '127.0.0.1 - "GET /search?q=면역력이 쑥쑥 HTTP/1.1" 200'
    assert "면역력" in leaky, "🔴 음성 픽스처가 애초에 안 샌다 — 검사가 무의미하다"
    assert "면역력" not in redact(leaky)
