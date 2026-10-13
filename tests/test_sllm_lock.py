"""sLLM 어댑터도 모델 잠금(`models.lock.json`)의 판만 올린다 — 소유자 lse (🆕 2026-10-13 · D-333 · 팀장 요청).

⛔ GPU · torch · 실제 어댑터 없이 돈다. 대조는 `app/model_lock.py` 를 그대로 부른다(`docs/lse/sllm_meta.py` `checked`).
🔴 지키는 것
   - 잠금의 채택 · 되돌림 판이면 올린다(대조 결과에 상태 · 판 지문)
   - 잠금 밖(파일 하나라도 다름 · 하위 폴더 · 역할 채택 판 없음)이면 서버는 멈춘다 — 지어낸 판으로 돌지 않는다
   - 평가 · 실험 도구는 `permit_unlocked()` 뒤에만 잠금 밖을 올린다
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app import model_lock

_PATH = Path(__file__).resolve().parents[1] / "docs" / "lse" / "sllm_meta.py"
_spec = importlib.util.spec_from_file_location("sllm_meta_lock", _PATH)
assert _spec is not None and _spec.loader is not None
meta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(meta)


def _adapter(folder: Path, weight: bytes = b"w") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "adapter_config.json").write_text(
        '{"base_model_name_or_path": "Qwen/Qwen3-4B-Instruct-2507"}', encoding="utf-8"
    )
    (folder / "adapter_model.safetensors").write_bytes(weight)
    return folder


def _lock(adopted: Path | None, role: str = "sllm_stage1") -> dict:
    bundles, roles = {}, {r: {"adopted": None, "rollback": []} for r in model_lock.ROLES}
    if adopted is not None:
        bundles[adopted.name] = model_lock.entry(adopted, role, "qwen3_4b_instruct_2507", "D-333")
        roles[role]["adopted"] = adopted.name
    return {"version": model_lock.VERSION, "roles": roles, "bundles": bundles}


@pytest.fixture(autouse=True)
def _locked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meta, "_UNLOCKED_OK", False)


def test_잠금의_채택_판이면_올린다(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _adapter(tmp_path / "copylane_sllm_lora_adapter_q4b-v14")
    monkeypatch.setattr(model_lock, "load", lambda path=model_lock.LOCK: _lock(a))
    m = meta.checked(a, meta.ROLE_STAGE1)
    assert m.status == model_lock.ADOPTED and m.name == a.name and len(m.bundle) == 12


def test_파일이_하나라도_다르면_잠금_밖이라_멈춘다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _adapter(tmp_path / "v14")
    lock = _lock(a)
    (a / "adapter_model.safetensors").write_bytes(b"other")  # 가중치가 바뀐 같은 이름의 폴더
    monkeypatch.setattr(model_lock, "load", lambda path=model_lock.LOCK: lock)
    with pytest.raises(meta.LockOutside, match="잠금"):
        meta.checked(a, meta.ROLE_STAGE1)


def test_역할에_채택_판이_없으면_잠금_밖이다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 sLLM 칸이 비어 있는 잠금(등재 전)에서 서버는 1단계를 올리지 않는다 — 앱은 「연결하지 못했어요」."""
    a = _adapter(tmp_path / "v14")
    monkeypatch.setattr(model_lock, "load", lambda path=model_lock.LOCK: _lock(None))
    with pytest.raises(meta.LockOutside, match="채택 판이 없다"):
        meta.checked(a, meta.ROLE_STAGE1)


def test_다른_역할의_판은_맞지_않는다(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _adapter(tmp_path / "polish")
    monkeypatch.setattr(
        model_lock, "load", lambda path=model_lock.LOCK: _lock(a, role="sllm_stage2")
    )
    assert meta.checked(a, meta.ROLE_STAGE2).status == model_lock.ADOPTED
    with pytest.raises(meta.LockOutside):
        meta.checked(a, meta.ROLE_STAGE1)


def test_도구가_허락하면_잠금_밖도_올리되_상태는_잠금_밖이다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _adapter(tmp_path / "v15")
    monkeypatch.setattr(model_lock, "load", lambda path=model_lock.LOCK: _lock(None))
    meta.permit_unlocked()
    assert meta.checked(a, meta.ROLE_STAGE1).status == model_lock.OUTSIDE


def test_잠금을_못_읽으면_멈춘다(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _adapter(tmp_path / "v14")

    def broken(path: Path = model_lock.LOCK) -> dict:
        raise model_lock.LockError("잠금 파일이 없다")

    monkeypatch.setattr(model_lock, "load", broken)
    with pytest.raises(meta.LockOutside, match="확인하지 못했다"):
        meta.checked(a, meta.ROLE_STAGE1)
