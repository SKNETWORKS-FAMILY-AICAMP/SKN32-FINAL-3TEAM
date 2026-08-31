"""HTTP 수집 — 재시도·간격 (수집기 공통 규약 5).

🚨 상대는 공공기관 서버다. 간격 없이 두드리면 우리가 막히는 것으로 끝나지 않고,
   레지스트리에 적어 둔 「공식 API 이용」이라는 근거 자체가 흔들린다.

표준 라이브러리만 쓴다 — 수집기는 팀원 누구의 기기에서도 돌아야 한다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

USER_AGENT = "CopyLane/0.1 (SKN Final Project; research use)"

MIN_INTERVAL = 0.5  # 규약 5 — 최소 간격
MAX_RETRY = 3  # 규약 5 — 재시도 3회
BACKOFF = 2.0  # 지수 백오프 계수

_last_call = 0.0


class FetchError(RuntimeError):
    """재시도를 다 쓰고도 실패했다."""


def fetch(url: str, *, timeout: int = 30) -> bytes:
    """간격을 지키며 받아온다. 실패하면 지수 백오프로 재시도한다."""
    global _last_call

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
