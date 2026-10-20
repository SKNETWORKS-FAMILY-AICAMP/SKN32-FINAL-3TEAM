"""app/logging_conf.py — 로그에 **광고 문구가 안 실리게** 하는 한 곳 (보안점검 P1-4 · D-76).

⛔ **무엇이 있었나** — `app/` 전체에 `logging` 이 **한 줄도 없었다.** 보안점검이
   *"가장 중요한 발견"* 이라 표시한 P1-4 의 조치 셋(마스킹 필터 · `echo=False` 고정 ·
   doctor 검사)이 **하나도 반영되지 않았다.**

🔴 **왜 지금인가** — 팀원 4명이 곧 화면·BFF 를 붙인다. 그들이 `print` 와 `logger.info` 를
   뿌리기 **전에** 로거가 서 있어야 필터가 뜻이 있다. 붙은 뒤에 세우면, 그때까지 나간 로그는
   되돌릴 수 없다.

★ **막는 방식은 「조심하기」가 아니라 「구조」다** (D-117).

    1. 문구는 **URL 에 안 싣는다** — `/search` 를 POST 로 옮겼다. 접근 로그에 안 남는다
    2. 그래도 새면 **필터가 지운다** — 아래 `RedactFilter`
    3. 코드가 문구를 참조해야 하면 `mask()` 를 쓴다 — **길이와 지문만** 남는다

🚨 **필터는 그물이지 벽이 아니다.** 벽은 1번이다. 필터는 2번이고, 새는 모양을 다 알 수 없다 —
   그래서 `mask()` 를 쓰는 습관이 셋째다. 셋을 다 둔다.
"""

from __future__ import annotations

import hashlib
import logging
import re
import traceback

#: 로그 문자열 안에서 **값을 지울 열쇠말.** `?q=…` · `text=…` · `prompt=…` 형태를 잡는다.
#: 🚨 이름을 늘릴 때는 `app/contracts.py` 의 사용자 입력 필드와 맞춘다.
_SENSITIVE_KEYS = ("q", "text", "prompt", "copy", "sentence", "password", "token", "key")

#: 열쇠말의 앞뒤 경계 — **영숫자만** 경계가 아니다. 🔄 2026-09-21 ⛔ 종전의 `\b` 는 `_` 를 낱말로 봐서
#:    `api_key=…` · `access_token=…` 의 `key`·`token` 을 못 잡았다(실행 확인). `token_count=…` 는
#:    뒤가 `_` 라 `=` 가 바로 안 붙으므로 여전히 안 걸린다.
_KEY_B = r"(?<![A-Za-z0-9])"
_KEY_E = r"(?![A-Za-z0-9])"
_KEYS_ALT = "|".join(_SENSITIVE_KEYS)

#: `?q=값` · `&text=값` · `q="값"` · `prompt: 값` 을 잡는다.
#: 🔄 2026-09-21 — 값의 끝을 **넘치게** 잡는다 (D-220 · 아래 `_QUERY` 와 같은 원칙).
#:    ⛔ 종전에는 `,` `]` `}` 에서 끊었다. 한국어 광고 문구는 쉼표를 흔하게 쓴다 —
#:       「text=면역력, 암을 예방합니다」가 `text=<가림 3자>, 암을 예방합니다` 로 **뒤가 그대로 남았다.**
#:       그리고 값 클래스가 `"` 를 빼서 `q="값"` 은 **매치 자체가 안 섰다**(이 주석이 잡는다고 적었는데).
#:    ★ 따옴표로 시작하면 **닫는 따옴표까지**(없으면 줄 끝까지), 아니면 `&`·줄바꿈·따옴표 전까지.
#: 🔄 2026-09-21 (전수 재검토) — 열쇠말이 **따옴표 안**이어도 잡는다. ⛔ `{"q": "…"}` · `{'text': '…'}`
#:    (dict·JSON 모양)은 열쇠 뒤가 `"` 라 `[=:]` 가 바로 안 붙어 **통째로 지나갔다**(실행 확인).
_QS = re.compile(
    r"(?P<key>[\"']?" + _KEY_B + r"(?:" + _KEYS_ALT + r")" + _KEY_E + r"[\"']?\s*[=:]\s*)"
    r"(?P<val>\"[^\"\n]*\"?|'[^'\n]*'?|[^&\n\"']+)",
    re.IGNORECASE,
)

#: 사람이 읽는 자리표시자. **원문 길이와 지문만** 남긴다 — 같은 문구였는지는 물을 수 있고
#: 무슨 문구였는지는 못 읽는다.
_PLACEHOLDER = "<가림 {n}자·{fp}>"


def fingerprint(text: str) -> str:
    """문구의 지문 8자. 🚨 **되돌릴 수 없다** — 같은 문구인지만 물을 수 있다."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def mask(text: str | None) -> str:
    """사용자 입력을 로그·예외에 실을 때 **반드시 통과시키는 함수.**

    ⛔ `logger.info(f"질의: {q}")` 는 P1-4 위반이다. `mask(q)` 를 쓴다.
    """
    if not text:
        return "<빈 값>"
    return _PLACEHOLDER.format(n=len(text), fp=fingerprint(text))


#: 🔴 **질의 문자열은 통째로 지운다.** 값 단위로 지우면 공백에서 끊긴다 —
#:    한국어 문구는 공백을 담고, 로그 포맷에 따라 인코딩이 풀린 채로 찍히기도 한다.
#:    ⛔ 실측: `q=우리 제품은 면역력이 쑥쑥` 을 값 단위로 지우면 「우리」만 가려졌다.
#: 🚨 **넘치게 지운다** — `?` 부터 요청 줄 끝까지. 덜 지우는 쪽으로 틀리면 문구가 샌다 (D-220).
_QUERY = re.compile(r"\?(?P<qs>.*?)(?=\sHTTP/|[\"']|$)")
#: 🔄 2026-09-21 — 경계는 위 `_QS` 와 **같은 것**을 쓴다 (D-99). `\b` 였을 때 `?api_key=…` 가 안 걸렸다.
_SENSITIVE_IN_QS = re.compile(_KEY_B + r"(?:" + _KEYS_ALT + r")=", re.IGNORECASE)


def redact(line: str) -> str:
    """로그 한 줄에서 민감한 값을 지운다. 🚨 **그물이다** — 모양을 다 알 수 없다."""

    def _sub_qs(m: re.Match[str]) -> str:
        qs = m.group("qs")
        return "?" + mask(qs) if _SENSITIVE_IN_QS.search(qs) else m.group(0)

    def _sub(m: re.Match[str]) -> str:
        return m.group("key") + mask(m.group("val"))

    return _QS.sub(_sub, _QUERY.sub(_sub_qs, line))


def safe_exception_text(exc_info: tuple) -> str:
    """트레이스백을 **예외 메시지만 가리고** 다시 짠다. 🆕 2026-09-22 (보안점검 P1-4 「예외 트레이스백에 request body 가 통째로」).

    ⛔ 종전 `RedactFilter` 는 `msg`·`args` 만 지웠다 — 트레이스백(`exc_info`)은 필터 밖이라 **stdout 에 그대로** 찍혔다.
       처리되지 않은 예외는 `uvicorn.error` 가 트레이스백과 함께 남기고, 예외 메시지에는 입력 값이 실릴 수 있다
       (pydantic 검증 오류의 `input_value=` · 우리 코드의 `ValueError(f"...{text}")` · psycopg 의 호스트·사용자명).
    ★ **위치는 남기고 메시지만 가린다** — 파일·줄·함수·소스 줄은 우리 코드이고 입력이 아니다. 지역 변수는 원래 안 찍힌다.
       메시지는 **통째로** `mask()` 한다 — 열쇠말만 지우면 `input_value=` 같은 모르는 모양이 샌다(넘치게 지운다 · D-220).
    🚨 원인 연쇄(`__cause__`·`__context__`)도 같은 방식으로 — 표준 트레이스백과 같은 순서·구분 문장.
    """
    etype, value, tb = exc_info
    if value is None:
        return "" if etype is None else etype.__name__
    chain: list[BaseException] = []
    seen: set[int] = set()
    cur: BaseException | None = value
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain.append(cur)
        cur = cur.__cause__ or (None if cur.__suppress_context__ else cur.__context__)
    parts: list[str] = []
    for i, exc in enumerate(reversed(chain)):
        if i:
            parts.append(
                "\nThe above exception was the direct cause of the following exception:\n\n"
                if exc.__cause__ is chain[len(chain) - i]
                else "\nDuring handling of the above exception, another exception occurred:\n\n"
            )
        frames = traceback.format_tb(exc.__traceback__) if exc.__traceback__ else []
        if frames:
            parts.append("Traceback (most recent call last):\n" + "".join(frames))
        text = str(exc)
        parts.append(
            f"{type(exc).__qualname__}: {mask(text)}\n" if text else f"{type(exc).__qualname__}\n"
        )
    return "".join(parts).rstrip("\n")


#: 레코드에 「이미 가렸다」를 적는 속성 이름 — `RedactFilter.filter` 가 두 번 가리지 않게.
_REDACTED = "_copylane_redacted"


class RedactFilter(logging.Filter):
    """모든 로그 레코드를 지나며 값을 지운다.

    🚨 **`record.msg` 와 `record.args` 둘 다 본다** — uvicorn 접근 로그는 경로를 `args` 로
       넘기므로 `msg` 만 보면 안 걸린다. 실제로 그 모양이다:
       `'%s - "%s %s HTTP/%s" %d'` + `args=(client, method, path, ver, status)`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # 🆕 2026-09-22 — **한 레코드에 한 번만.** ⛔ `redact()` 는 멱등이 아니다 — 가린 자리
        #    `text=<가림 15자·sha256:…>` 를 다시 지나면 그 표식을 또 가려 **길이·지문이 바뀐다**(실측 15자 → 24자).
        #    필터는 로거와 핸들러 양쪽에 붙어 있어(자식 로거 → root 핸들러 · `app_error_log` 핸들러) 같은 레코드를
        #    두세 번 지난다 — stdout 과 DB 의 지문이 어긋나 「같은 문구였는가」를 못 묻게 된다.
        if getattr(record, _REDACTED, False):
            return True
        setattr(record, _REDACTED, True)
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        else:
            # 🔄 2026-09-21 — `logger.info(payload_dict)` 처럼 msg 자체가 객체면 문자열로 펴서 지운다
            record.msg = redact(str(record.msg))
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(_scrub(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _scrub(v) for k, v in record.args.items()}
        # 🆕 2026-09-22 — 트레이스백도 가린다. ★ `exc_text` 를 **먼저 채워 두면** 모든 Formatter 가 그것을 쓴다
        #    (`logging.Formatter.format` 은 `exc_text` 가 비었을 때만 `formatException` 을 부른다) —
        #    uvicorn 의 포매터를 갈아 끼우지 않고도 모든 출력이 가린 판을 낸다.
        if record.exc_info and record.exc_info[0] is not None:
            record.exc_text = safe_exception_text(record.exc_info)
        return True


def _scrub(a: object) -> object:
    """로그 인자 하나. 🔄 2026-09-21 (전수 재검토) — ⛔ 문자열만 지웠다. `logger.info("req %s", body_dict)` 는
    dict 가 **포맷 시점에** 문자열이 되므로 필터를 그대로 지나갔다. 수(%d·%f 자리)와 None 은 그대로 둔다."""
    if a is None or isinstance(a, (bool, int, float)):
        return a
    return redact(a if isinstance(a, str) else str(a))


#: 필터를 붙일 로거들. 🚨 **`uvicorn.access` 가 핵심**이다 — 경로가 거기로 나간다.
_TARGETS = ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy.engine")


def setup_logging(level: int = logging.INFO) -> None:
    """앱이 뜰 때 한 번. 🚨 **`app/api.py` 가 import 시점에 부른다** — 잊을 자리를 없앤다.

    ⛔ SQLAlchemy 는 `echo=True` 면 바인딩 파라미터(=문구 원문)를 찍는다. 여기서 그 로거를
       `WARNING` 으로 눌러 둔다 — 팀원이 `echo=True` 를 켜도 **필터를 지난다.**
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    f = RedactFilter()
    for name in _TARGETS:
        logger = logging.getLogger(name)
        if not any(isinstance(x, RedactFilter) for x in logger.filters):
            logger.addFilter(f)
        for handler in logger.handlers:
            if not any(isinstance(x, RedactFilter) for x in handler.filters):
                handler.addFilter(f)
    # 🚨 엔진 로그는 기본으로 누른다 — 켜더라도 위 필터를 지난다
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # 🆕 2026-09-22 — 오류 로그 표(`app_error_log`). 🚨 켜는 조건은 `settings.error_log_enabled()` 한 곳이다 (D-99) —
    #    `onprem`·`demo` 만(`auto`). 개발 기기(`local`)·테스트·`cloud` 는 붙지 않는다. 핸들러는 백그라운드로 쓴다.
    from app.settings import error_log_enabled  # noqa: PLC0415 — 부를 때만 `.env` 를 읽는다

    if error_log_enabled():
        from app import error_log  # noqa: PLC0415

        error_log.install()
