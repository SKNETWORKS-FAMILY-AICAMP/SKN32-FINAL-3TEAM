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

#: sLLM 서버 주소의 기본값 — 바꿀 일이 있으면 환경 변수 `COPYLANE_SLLM_URL` 로(예: 포트를 바꿔 띄웠을 때).
SLLM_URL = "http://127.0.0.1:8765"
#: 🆕 2026-10-08 — 이 환경에 고쳐 쓰기 서버를 **두지 않는다**는 표시: `COPYLANE_SLLM_URL=off` (또는 빈 값).
#:    GPU 가 없는 배포 기기(원장 「지원 리소스」 · 배포계획)에서 버튼이 남아 「잠시 뒤 다시 눌러 주세요」를 내면 거짓이다 —
#:    없는 기능은 없다고 그린다. ⛔ 기본값은 켜짐(로컬 주소) — 로컬 · 시연의 동작은 바뀌지 않는다.
#:    배포에 넣을지는 정하지 않았다(배포계획 「sLLM 미정」) — 이 스위치는 그 결정을 내리지 않는다.
OFF_VALUES = ("", "off")
#: 🆕 2026-10-10 — 서버 후처리가 **공식 기능성 문구**에 붙이는 조건(`docs/lse/postfix.py` `NOTE_FOOD_FUNC` 와 같은 글자 ·
#:    둘이 같은지는 `tests/test_user_rewrite.py` 가 본다 · D-99). 이 조건이 붙은 후보는 **인정받은 건강기능식품에서만** 쓸 수 있다 —
#:    앱이 고른 전제와 맞는지 본다(`app/routers/user.py` `_note_conflict`). 서버는 품목만 받고 전제를 모른다
NOTE_RECOGNIZED_HF = "기능성 인정 건강기능식품에 한해 표시"


def _env_url() -> str | None:
    """환경 변수 값 — **부를 때마다** 읽는다. `None` = 주지 않았다.

    🔴 2026-10-08 — `.env` 는 `app.settings.settings()` 가 처음 불릴 때 읽힌다(`collect/env.py` · D-99). 이 모듈이 import
       시점에 환경 변수를 읽으면 `.env` 에 적은 `off` 가 import 순서에 따라 먹히기도 하고 안 먹히기도 한다. 그래서 먼저 부른다.
    """
    from app.settings import settings  # noqa: PLC0415 — `.env` 를 읽는 곳은 하나다

    settings()
    v = os.environ.get("COPYLANE_SLLM_URL")
    return None if v is None else v.strip()


def enabled() -> bool:
    """이 환경에 고쳐 쓰기를 두었는가. 변수를 안 주면 켜짐이다."""
    v = _env_url()
    return v is None or v.lower() not in OFF_VALUES


def _url() -> str:
    v = _env_url()
    return v.rstrip("/") if v else SLLM_URL


#: 문장당 4~12초(RTX 3080) · 첫 요청은 더 걸린다 — 넉넉히 잡되 무한히 기다리지 않는다.
TIMEOUT_S = 90

#: 서버가 돌려주는 종착 — 이 밖의 값은 깨진 응답으로 본다.
OUTCOMES = ("candidate", "hold", "infeasible")


def rewrite(
    text: str, violation_types: list[str], category: str | None = None
) -> tuple[str, dict | None]:
    """원문 하나를 sLLM 서버에 보낸다. `("ok", 응답)` · `("down", None)` · `("off", None)`.

    재판정은 여기서 켜지 않는다 — 앱이 **앱의 판정 코어**로 다시 판정한다(D-119 · 판정 코어는 하나).
    `category` — 🆕 10-06 판정 결과의 품목(D-319). 없으면 서버가 문구에서 추측한다.
    🆕 2026-10-08 — 꺼 둔 환경(`enabled()` 거짓)이면 부르지 않고 `("off", None)` — 「연결 실패」와 가른다.
    """
    if not enabled():
        return "off", None
    body = json.dumps(
        {"text": text, "violation_types": violation_types, "rejudge": False, "category": category},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — 주소는 위 상수(로컬)다
        f"{_url()}/rewrite",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
            out = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "down", None
    if not _well_formed(out):
        return "down", None
    return "ok", out


def _well_formed(out: object) -> bool:
    """화면(`_review_rewrite.html`)이 읽는 칸이 다 있는가 — 없으면 깨진 응답이다 (D-220).

    🔴 2026-10-06 (흡수 검토 · 재현) — 종착만 보고 통과시켰더니 `candidate` 인데 `rewrite` 가 빈 응답,
       `latency_ms` 가 없는 응답에서 화면이 없는 값을 읽다 500 을 냈다. 서버(`docs/lse/sllm_service.py`)는
       후보 문장이 비면 `rewrite: None` 인 채 `candidate` 를 돌려줄 수 있다.
    ⛔ 화면에서 빈 값을 기본값으로 메우지 않는다 — 문구 없는 후보가 「후보」로 그려진다 (D-162).
    """
    if not isinstance(out, dict) or out.get("outcome") not in OUTCOMES:
        return False
    if not isinstance(out.get("model"), str) or not isinstance(out.get("latency_ms"), int | float):
        return False
    if not isinstance(out.get("reasons", []), list) or not isinstance(out.get("repairs", []), list):
        return False
    if out["outcome"] == "candidate":
        rw = out.get("rewrite")
        return isinstance(rw, dict) and isinstance(rw.get("body"), str) and bool(rw["body"].strip())
    return True
