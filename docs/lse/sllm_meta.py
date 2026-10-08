"""sLLM 판 표지 — 어느 어댑터 · 어느 베이스로 도는지 (🆕 2026-10-07 · 팀장 요청으로 팀장 쪽에서 추가).

왜 따로 두나
  · `sllm_service.py` 는 올릴 때 환경 변수를 건드린다(`HF_HUB_OFFLINE`). 이 모듈은 **torch 도 부작용도 없다** —
    GPU 없는 기기 · 테스트(`tests/test_sllm_meta.py`)에서 그대로 읽힌다.
  · 판을 바꾸는 자리를 한 곳에 모은다(D-99). 값이 없으면 종전 채택본 그대로다.

바꾸는 법 (전부 선택 — 비우면 종전과 같다)
  COPYLANE_SLLM_STAGE1   1단계 어댑터 판. `models/copylane_sllm_lora_adapter_<판>/` 을 읽는다          기본 v12
  COPYLANE_SLLM_STAGE2   2단계(말투) 어댑터 폴더 경로                                                기본 models/copylane_sllm_persona_adapter
  COPYLANE_SLLM_BASE     베이스 모델 이름. 🔴 어댑터가 학습된 베이스와 다르면 서비스가 **올리기 전에 멈춘다**   기본 Qwen/Qwen2.5-3B-Instruct

🚨 베이스를 바꾸는 것은 폴더만 갈아 끼우는 일이 아니다 — 어댑터를 그 베이스로 다시 학습해야 하고, 후처리(`postfix.py`) ·
   관문(`stage_gate.py`)은 지금 베이스의 출력 버릇에 맞춰 다듬은 것이라 평가를 다시 돌려야 한다. 여기서 하는 일은
   **짝이 안 맞는 어댑터와 베이스가 조용히 올라가지 않게** 하는 것까지다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 채택본 — 종전에 코드에 박혀 있던 값 그대로다 (`persona_pipeline_e2e.STAGE1_VER` · `persona_experiment.BASE`)
DEFAULT_STAGE1 = "v12"
DEFAULT_BASE = "Qwen/Qwen2.5-3B-Instruct"
DEFAULT_STAGE2 = ROOT / "models" / "copylane_sllm_persona_adapter"

ENV_STAGE1 = "COPYLANE_SLLM_STAGE1"
ENV_STAGE2 = "COPYLANE_SLLM_STAGE2"
ENV_BASE = "COPYLANE_SLLM_BASE"


class AdapterMismatch(RuntimeError):
    """어댑터를 읽지 못했거나, 어댑터가 학습된 베이스가 올리려는 베이스와 다르다."""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def stage1_version() -> str:
    return _env(ENV_STAGE1) or DEFAULT_STAGE1


def stage1_dir(version: str | None = None) -> Path:
    return ROOT / "models" / f"copylane_sllm_lora_adapter_{version or stage1_version()}"


def stage2_dir() -> Path:
    raw = _env(ENV_STAGE2)
    return Path(raw) if raw else DEFAULT_STAGE2


def base_model() -> str:
    return _env(ENV_BASE) or DEFAULT_BASE


def adapter_base(adapter_dir: Path) -> str:
    """어댑터가 학습된 베이스 — `adapter_config.json` 의 `base_model_name_or_path`. 못 읽으면 멈춘다 (D-220)."""
    path = adapter_dir / "adapter_config.json"
    try:
        base = json.loads(path.read_text(encoding="utf-8")).get("base_model_name_or_path")
    except (OSError, ValueError) as e:
        raise AdapterMismatch(f"어댑터 설정을 읽지 못했다: {path}") from e
    if not isinstance(base, str) or not base:
        raise AdapterMismatch(f"어댑터 설정에 베이스 모델 이름이 없다: {path}")
    return base


def check_base(adapter_dir: Path, base: str) -> None:
    """어댑터와 베이스가 짝인지. 🔴 다르면 멈춘다 — 다른 베이스에 얹은 어댑터는 오류 없이 엉뚱한 문장을 낸다."""
    trained_on = adapter_base(adapter_dir)
    if trained_on != base:
        raise AdapterMismatch(
            f"어댑터 {adapter_dir.name} 는 {trained_on} 로 학습됐는데 올리려는 베이스는 {base} 다 — "
            f"{ENV_BASE} 를 맞추거나 그 베이스로 학습한 어댑터를 쓴다"
        )


def adapter_sha12(adapter_dir: Path) -> str:
    """어댑터 가중치의 sha256 앞 12자 — 수를 낸 판과 도는 판이 같은지 대조하는 지문이다."""
    path = adapter_dir / "adapter_model.safetensors"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError as e:
        raise AdapterMismatch(f"어댑터 가중치를 읽지 못했다: {path}") from e
    return h.hexdigest()[:12]
