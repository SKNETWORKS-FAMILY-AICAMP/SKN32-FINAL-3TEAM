"""sLLM 판 표지(`docs/lse/sllm_meta.py`) — 판 · 베이스를 환경 변수로 바꾸고, 짝이 안 맞으면 멈춘다 (🆕 2026-10-07).

⛔ GPU · torch · 실제 어댑터 없이 돈다 — 서비스(`sllm_service.py`)는 여기서 올리지 않는다(올리면 `HF_HUB_OFFLINE` 을 건드린다).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "docs" / "lse" / "sllm_meta.py"
_spec = importlib.util.spec_from_file_location("sllm_meta", _PATH)
assert _spec is not None and _spec.loader is not None
meta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(meta)


def _adapter(tmp_path: Path, base: object) -> Path:
    (tmp_path / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": base}), encoding="utf-8"
    )
    return tmp_path


def test_값이_없으면_종전_채택본이다(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (meta.ENV_STAGE1, meta.ENV_STAGE2, meta.ENV_BASE):
        monkeypatch.delenv(name, raising=False)
    assert meta.stage1_version() == "v12"
    assert meta.stage1_dir().name == "copylane_sllm_lora_adapter_v12"
    assert meta.stage2_dir().name == "copylane_sllm_persona_adapter"
    assert meta.base_model() == "Qwen/Qwen2.5-3B-Instruct"


def test_환경_변수로_판과_베이스를_바꾼다(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(meta.ENV_STAGE1, " v13 ")
    monkeypatch.setenv(meta.ENV_STAGE2, str(tmp_path))
    monkeypatch.setenv(meta.ENV_BASE, "Qwen/Qwen3-4B")
    assert meta.stage1_dir().name == "copylane_sllm_lora_adapter_v13"
    assert meta.stage2_dir() == tmp_path
    assert meta.base_model() == "Qwen/Qwen3-4B"


def test_어댑터와_베이스가_다르면_멈춘다(tmp_path: Path) -> None:
    """🔴 다른 베이스에 얹은 어댑터는 오류 없이 엉뚱한 문장을 낸다 — 올리기 전에 막는다 (D-220)."""
    adapter = _adapter(tmp_path, "Qwen/Qwen2.5-3B-Instruct")
    meta.check_base(adapter, "Qwen/Qwen2.5-3B-Instruct")
    with pytest.raises(meta.AdapterMismatch, match="로 학습됐는데"):
        meta.check_base(adapter, "Qwen/Qwen3-4B")


@pytest.mark.parametrize("base", [None, "", 3])
def test_베이스_이름을_못_읽으면_멈춘다(tmp_path: Path, base: object) -> None:
    with pytest.raises(meta.AdapterMismatch):
        meta.adapter_base(_adapter(tmp_path, base))


def test_설정_파일이_없으면_멈춘다(tmp_path: Path) -> None:
    with pytest.raises(meta.AdapterMismatch, match="읽지 못했다"):
        meta.adapter_base(tmp_path)
    with pytest.raises(meta.AdapterMismatch, match="가중치"):
        meta.adapter_sha12(tmp_path)


def test_가중치_지문은_파일_내용으로_정해진다(tmp_path: Path) -> None:
    (tmp_path / "adapter_model.safetensors").write_bytes(b"abc")
    assert meta.adapter_sha12(tmp_path) == "ba7816bf8f01"
