"""sLLM 재생성 서버 클라이언트 — 소유자 **lse** (2026-10-06 · 진입점 B 원문 고쳐 쓰기).

★ **왜 HTTP 인가** — 앱 `.venv` 는 CPU torch 다(팀 lock). sLLM 은 GPU torch · transformers · peft 가 있는
  `.venv-sllm` 에서 **따로 띄운다**(`docs/lse/sllm_service.py --serve`). 한 프로세스에 합치면 패키지가 부딪힌다.
  연결 안내: `docs/lse/sLLM_연결_안내_2026-10-05.md`.

⛔ **새 의존성을 들이지 않는다** — `uv.lock` 은 팀장 단독이다(D-87). 표준 라이브러리 `urllib` 로 부른다.
🚨 서버가 없거나 응답이 깨지면 `("down", None)` — **후보를 지어내지 않는다**(D-146 · D-147).
🚨 서버는 `127.0.0.1` 에만 연다 — 앱과 sLLM 서버는 **같은 PC** 에서 돈다(외부 공개 안 함).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

#: sLLM 서버 주소 — 바꿀 일이 있으면 환경 변수로(예: 포트를 바꿔 띄웠을 때).
SLLM_URL = os.environ.get("COPYLANE_SLLM_URL", "http://127.0.0.1:8765").rstrip("/")
#: 문장당 4~12초(RTX 3080) · 첫 요청은 더 걸린다 — 넉넉히 잡되 무한히 기다리지 않는다.
TIMEOUT_S = 90

#: 서버가 돌려주는 종착 — 이 밖의 값은 깨진 응답으로 본다.
OUTCOMES = ("candidate", "hold", "infeasible")


def rewrite(text: str, violation_types: list[str]) -> tuple[str, dict | None]:
    """원문 하나를 sLLM 서버에 보낸다. `("ok", 응답)` 또는 `("down", None)`.

    재판정은 여기서 켜지 않는다 — 앱이 **앱의 판정 코어**로 다시 판정한다(D-119 · 판정 코어는 하나).
    """
    body = json.dumps(
        {"text": text, "violation_types": violation_types, "rejudge": False}, ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — 주소는 위 상수(로컬)다
        f"{SLLM_URL}/rewrite",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
            out = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "down", None
    if not isinstance(out, dict) or out.get("outcome") not in OUTCOMES:
        return "down", None
    return "ok", out
