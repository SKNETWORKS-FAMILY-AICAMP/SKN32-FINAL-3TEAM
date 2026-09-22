"""테스트 공통 — 🆕 2026-09-20 (D-250).

★ 수집 원장에 줄을 붙이는 테스트는 **기기 별칭**이 있어야 돈다 — 팀원 기기에서 별칭이 비면
  `store.device_id()` 가 쓰기 전에 멈추기 때문이다(PC 이름 해시를 폐기했다). CI 에는 `.env` 가 없다.
🚨 별칭이 **없을 때**의 동작을 보는 테스트는 스스로 `monkeypatch.setenv("DATA_DEVICE", "")` 로 비운다.

🔄 2026-09-22 — **오류 로그 DB 기록을 끈다** (`COPYLANE_ERROR_LOG=off` · `app/error_log.py`).
  게이트가 `app.api` 를 import 하면 `setup_logging()` 이 돈다 — onprem 기기의 `.env` 로 켜지면
  테스트가 남긴 WARNING 이 **실제 DB 에 쌓인다**. ★ 모듈 수준에서 박는다 — fixture 보다 import 가 먼저다.
  `.env` 는 `override=False` 로 읽으므로(`collect/env.py`) 이 값이 이긴다.
  켜진 동작은 `test_error_log.py` 가 설정 객체를 직접 만들어 잰다.
"""

from __future__ import annotations

import os

import pytest

os.environ["COPYLANE_ERROR_LOG"] = "off"


@pytest.fixture(autouse=True)
def _device_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "pytest")
