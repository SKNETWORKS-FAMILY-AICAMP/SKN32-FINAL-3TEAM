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

from collect import env

os.environ["COPYLANE_ERROR_LOG"] = "off"
# 🆕 2026-10-13 (ksr) — **카피 생성 엔진(GPT 호출)을 끈다** (`COPYLANE_COPYGEN` · `app/routers/copygen`). 같은 까닭이다 —
#    켜 둔 기기의 `.env` 로 `/u/generate` 를 누르는 테스트가 **실제로 밖을 부르면 안 된다.** 켜진 동작은 대역을 끼워 잰다.
os.environ["COPYLANE_COPYGEN"] = "off"
# 🆕 2026-10-13 (D-333) — **판정 인코더를 끈다** (`COPYLANE_MODEL_DIR`). 인코더는 이제 `.env` 에서도 켜진다(`collect.env.setting`) —
#    켜 둔 기기에서 그래프를 도는 테스트가 수백 MB 모델을 올리고 결과가 기기마다 갈리면 안 된다. 켜진 동작은 대역을 끼워 잰다.
os.environ["COPYLANE_MODEL_DIR"] = ""
# 🆕 2026-10-21 (D-348 보충 35 결정 1) — **기록 · 분기 불변식이 깨지면 시험은 거부한다** (`app.graph.INVARIANT_ENV`).
#    운영 · 평가는 바로잡고(전제 보류로 내림) 로그를 남긴다 — 시험에서 바로잡으면 결함이 초록불 뒤에 숨는다(D-162).
os.environ["COPYLANE_INVARIANT"] = "raise"
# 🆕 2026-10-14 — **`.env` 를 여기서 한 번 읽는다** (`override=False` — 위에서 박은 값이 이긴다).
#    ⛔ 처음 읽는 때가 실행 순서에 달려 있었다 — 값을 지운(`delenv`) 테스트 뒤에 처음 읽히면 `.env` 값이 다시 채워져
#       파일 몇 개만 돌리면 깨지고 전체로 돌리면 지나갔다(`tests/test_encode_node.py` `off` · 2026-10-14).
#    ⛔ `.env` 를 아예 막지 않는다 — DB 게이트(`tests/test_risk_floor.py`)가 `.env` 의 `DATABASE_URL` 로 붙고,
#       못 붙으면 **조용히 건너뛴다**(D-220 의 「없음이 통과」). 클론 B 의 주소는 기본값과 다르다.
env.load()
# 🔐 비밀 키는 비운다 — 테스트가 실수로라도 진짜 키로 밖을 부르지 않게. 이름의 정본은 `collect.env.KEYS` (D-99).
#    `DATABASE_URL` 은 남긴다 — 위의 DB 게이트가 쓴다. 키가 필요한 동작은 대역을 끼워 잰다(`llm.has_key` 등).
for _name in env.KEYS:
    if _name != "DATABASE_URL":
        os.environ[_name] = ""


@pytest.fixture(autouse=True)
def _device_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DEVICE", "pytest")
