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
_QS = re.compile(
    r"(?P<key>" + _KEY_B + r"(?:" + _KEYS_ALT + r")" + _KEY_E + r"\s*[=:]\s*)"
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


class RedactFilter(logging.Filter):
    """모든 로그 레코드를 지나며 값을 지운다.

    🚨 **`record.msg` 와 `record.args` 둘 다 본다** — uvicorn 접근 로그는 경로를 `args` 로
       넘기므로 `msg` 만 보면 안 걸린다. 실제로 그 모양이다:
       `'%s - "%s %s HTTP/%s" %d'` + `args=(client, method, path, ver, status)`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {
                    k: (redact(v) if isinstance(v, str) else v) for k, v in record.args.items()
                }
        return True


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
