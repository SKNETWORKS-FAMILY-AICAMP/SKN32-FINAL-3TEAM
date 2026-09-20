"""테스트 공통 — 🆕 2026-09-20 (D-250).

★ 수집 원장에 줄을 붙이는 테스트는 **기기 별칭**이 있어야 돈다 — 팀원 기기에서 별칭이 비면
  `store.device_id()` 가 쓰기 전에 멈추기 때문이다(PC 이름 해시를 폐기했다). CI 에는 `.env` 가 없다.
🚨 별칭이 **없을 때**의 동작을 보는 테스트는 스스로 `monkeypatch.setenv("DATA_DEVICE", "")` 로 비운다.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _device_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "pytest")
