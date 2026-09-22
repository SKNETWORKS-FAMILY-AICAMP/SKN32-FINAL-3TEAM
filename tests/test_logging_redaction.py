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
    # 🆕 2026-09-21 — ⛔ 위 넷에는 **쉼표도 괄호도 따옴표도 없었다.** 실제 광고 문구는 쉼표를 흔하게 쓰고,
    #    그 모양에서 값이 끊겨 뒷부분이 그대로 남았다(실행 확인). 픽스처가 입력 분포를 안 닮으면
    #    음성 대조(D-203)가 있어도 새는 모양을 못 본다.
    "text=우리 제품은, 면역력이 쑥쑥",
    "text=우리 제품은] 면역력이 쑥쑥",
    "text={우리 제품은} 면역력이 쑥쑥",
    'q="우리 제품은 면역력이 쑥쑥" 이라고 적혀 있었다',
    "sentence='이 제품은 암을 예방합니다'",
)

#: 비밀 — 🆕 2026-09-21 ⛔ `\b` 경계가 `_` 를 낱말로 봐서 `api_key=`·`access_token=` 이 안 가려졌다.
_SECRET = (
    "api_key=SECRETVALUE123",
    "access_token=SECRETVALUE123",
    '"GET /x?api_key=SECRETVALUE123 HTTP/1.1" 200',
)

#: 지우면 안 되는 것 — **넘치게 지운다고 아무거나 지우면 로그가 쓸모없어진다.**
_KEEP = (
    '127.0.0.1 - "POST /search HTTP/1.1" 200',
    '"GET /docs HTTP/1.1" 200',
    "DB 접속 실패 원인=OperationalError",
    "chunk_id=abc123 · part_no=2",
    "token_count=512 · keyword_n=3",  # 🆕 열쇠말이 **낱말 안**에 있으면 안 건다 (경계를 넓힌 반대 대조)
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
@pytest.mark.parametrize("line", _SECRET)
def test_비밀값이_로그에_안_남는다(line: str) -> None:
    """🔴 열쇠말 앞에 `_` 가 붙어도 가린다 — `api_key`·`access_token` 은 흔한 이름이다."""
    out = redact(line)
    assert "SECRETVALUE123" not in out, f"🔴 비밀값이 남았다: {out}"


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


# ── 🆕 2026-09-22 — 트레이스백 · 두 번 가리기 ─────────────────────────────


#: 🚨 입력은 **변수로** 넘긴다 — 트레이스백은 소스 줄을 찍는다. 문구를 `raise` 줄에 적으면 그것은 「우리 코드」라
#:    가려지지 않는 것이 맞고, 검사가 소스 줄을 새는 것으로 오인한다. 실제 입력은 변수로 들어온다.
_INNER = "text=면역력이 쑥쑥"
_OUTER = "input_value='이 제품은 암을 예방합니다'"


def _raise_chain() -> tuple:
    import sys  # noqa: PLC0415

    try:
        try:
            raise KeyError(_INNER)
        except KeyError as inner:
            raise ValueError(_OUTER) from inner
    except ValueError:
        return sys.exc_info()


@pytest.mark.gate
def test_트레이스백의_예외_메시지가_가려진다() -> None:
    """🔴 P1-4 「예외 트레이스백에 request body 가 통째로」 — ⛔ 종전 필터는 `msg`·`args` 만 봤다."""
    rec = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Exception in ASGI application",
        None,
        _raise_chain(),
    )
    RedactFilter().filter(rec)
    out = logging.Formatter().format(rec)
    for leak in ("면역력", "쑥쑥", "암을 예방"):
        assert leak not in out, f"🔴 트레이스백에 문구가 남았다:\n{out}"
    # ★ 위치는 남는다 — 장애를 쫓을 수 있어야 한다
    assert "_raise_chain" in out and "KeyError" in out and "ValueError" in out
    assert "The above exception was the direct cause" in out, "🔴 원인 연쇄의 구분 문장이 틀렸다"


def test_음성_대조_필터를_빼면_트레이스백이_샌다() -> None:
    """🚨 게이트가 아니다 — 위 검사가 「원래 안 새는 트레이스백」이라 통과한 것이 아님을 잰다 (D-203)."""
    rec = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1, "x", None, _raise_chain())
    assert "면역력" in logging.Formatter().format(rec)


@pytest.mark.gate
def test_같은_레코드를_두_번_지나도_한_번만_가린다() -> None:
    """🔴 `redact()` 는 멱등이 아니다 — 로거와 핸들러 양쪽의 필터를 지나면 표식을 또 가려 지문이 바뀐다."""
    once = redact("text=우리 제품은, 면역력이 쑥쑥")
    assert redact(once) != once, "🔴 음성 대조 — redact 가 멱등이면 이 검사가 무의미하다"
    rec = logging.LogRecord(
        "copylane.x", logging.WARNING, __file__, 1, "text=우리 제품은, 면역력이 쑥쑥", None, None
    )
    f = RedactFilter()
    f.filter(rec)
    f.filter(rec)
    RedactFilter().filter(rec)
    assert rec.getMessage() == once, f"🔴 두 번 가렸다: {rec.getMessage()}"
