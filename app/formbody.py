"""app/formbody.py — 폼 본문을 **상한까지만** 읽는 한 곳 (보안점검 P2-11 · D-99). 🆕 2026-09-21 (전수 재검토).

⛔ 두 라우터(`routers/auth.py` 로그인 · `routers/user.py` 검수 폼)가 `await request.body()` 로 **전부 읽은 뒤**
   길이를 쟀다. 상한은 거절 사유는 됐지만 메모리는 이미 다 잡은 뒤다 — 막으려던 것(큰 본문)을 먼저 받았다.
★ `Content-Length` 가 상한을 넘으면 읽지 않고 거부하고, 없거나 거짓이어도 **흘려 읽다가** 넘는 순간 멈춘다.
⛔ 자르지 않고 거부한다 — 자르면 사용자는 자기 문구가 잘린 줄 모른다 (D-220).
"""

from __future__ import annotations

from fastapi import HTTPException, Request


async def read_capped(request: Request, limit: int, message: str = "본문이 너무 크다") -> bytes:
    """본문 전체. `limit` 바이트를 넘으면 413."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, message)
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(413, message)
    return bytes(buf)
