"""HTTP 수집 — 재시도·간격 (수집기 공통 규약 5).

🚨 상대는 공공기관 서버다. 간격 없이 두드리면 우리가 막히는 것으로 끝나지 않고,
   레지스트리에 적어 둔 「공식 API 이용」이라는 근거 자체가 흔들린다.

표준 라이브러리만 쓴다 — 수집기는 팀원 누구의 기기에서도 돌아야 한다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "CopyLane/0.1 (SKN Final Project; research use)"

MIN_INTERVAL = 0.5  # 규약 5 — 최소 간격
MAX_RETRY = 3  # 규약 5 — 재시도 3회
BACKOFF = 2.0  # 지수 백오프 계수

_last_call = 0.0


class FetchError(RuntimeError):
    """재시도를 다 쓰고도 실패했다."""


def encode(url: str) -> str:
    """🚨 URL 에 ASCII 밖 문자가 있으면 퍼센트 인코딩한다.

    `urllib.request` 는 ASCII 만 받아 `UnicodeEncodeError` 로 죽는다 —
    **잡히지 않고 죽는다.** `FetchError` 가 아니라 재시도 루프 밖에서 터지므로
    한 소스가 전체를 멈춘다.

    2026-09-02 탐침 1회전에서 나스미디어 2건(`/정기보고서/…`)이 이렇게 터졌다.
    🚨 **탐침이 아니라 수집기의 버그다** — `collect/http.py` 는 둘의 공용이고,
    같은 URL 로 수집기를 돌렸어도 똑같이 죽었다. 국내 기관 사이트에 한글 경로는 흔하다.
    """
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            p.scheme,
            p.netloc.encode("idna").decode("ascii") if not p.netloc.isascii() else p.netloc,
            urllib.parse.quote(p.path, safe="/%"),
            urllib.parse.quote(p.query, safe="=&?/%"),
            urllib.parse.quote(p.fragment, safe="/%"),
        )
    )


def fetch(url: str, *, timeout: int = 30) -> bytes:
    """간격을 지키며 받아온다. 실패하면 지수 백오프로 재시도한다."""
    global _last_call

    url = encode(url)

    last_error: Exception | None = None
    for attempt in range(MAX_RETRY):
        gap = time.monotonic() - _last_call
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                _last_call = time.monotonic()
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            _last_call = time.monotonic()
            last_error = e
            if attempt < MAX_RETRY - 1:
                time.sleep(MIN_INTERVAL * (BACKOFF**attempt))

    raise FetchError(f"{url} — {MAX_RETRY}회 시도 실패: {last_error}")
