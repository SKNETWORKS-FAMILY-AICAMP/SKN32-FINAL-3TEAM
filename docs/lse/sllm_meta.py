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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # `app.model_lock` — 표준 라이브러리만 쓴다(torch 없이 읽힌다)

#: 채택본. 🔄 2026-10-11 — Qwen2.5-3B(v12 · 라이선스 qwen-research 이용 제한) → **Qwen3-4B-Instruct-2507(apache-2.0) · q4b-v13**.
#:    근거 — 직접 만든 117 문장에서 살림 64 → 66 · 불가 확대 막음 31 → 38 · 진짜 포장 1 → 0, dev 511 재판정 지표 동등,
#:    3B 가 멈추고 4B 가 고친 19 행 검수의 위법 의심 3 은 관문 보강으로 0(`docs/lse/고쳐쓰기_dev평가_2026-10-11.md` §6).
#:    2단계도 4B 로 다시 학습했다(`…persona_adapter_q4b` · 규칙 통과 54/54). 3B 로 돌아가려면 환경 변수 셋을
#:    COPYLANE_SLLM_BASE=Qwen/Qwen2.5-3B-Instruct · COPYLANE_SLLM_STAGE1=v12 · COPYLANE_SLLM_STAGE2=models\copylane_sllm_persona_adapter
#:    🚨 `train_stage1_v5.py` 도 이 베이스를 읽는다 — 3B 판(v5 ~ v12)을 다시 학습하려면 COPYLANE_SLLM_BASE 를 3B 로 준다
#: 🔄 2026-10-12 — 1단계 q4b-v13 → **q4b-v14**(보강 2차 · 직접 만든 55 행). 실제 광고 87 — 포장 4 → 0 · 불가를 불가로 47 → 55,
#:    dev 바뀐 위험 33 행 검수의 위법 의심 2 는 관문 보강으로 0(`docs/lse/고쳐쓰기_dev평가_2026-10-11.md` §6-3).
#:    보강 3차 q4b-v15 는 실제 광고에서 v14 보다 나빠(포장 1 · 불가 막음 48) 채택하지 않았다. v13 으로 돌아가려면 COPYLANE_SLLM_STAGE1=q4b-v13
#: 🔄 2026-10-17 — 1단계 q4b-v14 → **q4b-n2**(확장 2차만 · 2,570 행 · `gen_expand_stage1.py`) + 화장품 기능 주장 되살리기
#:    (`postfix.rescue_cosmetic` · `persona_pipeline_e2e.RESCUE` 기본 켬). 실제 광고 87 — 불가를 불가로 55 → 66 · 살림 3 → 4 · 포장 0 ·
#:    지나친 거절 6 그대로 · 보류 23 → 11, 직접 만든 119 동등 · 포장 0. dev 511 은 불가가 크게 늘었다(450 · 표본 30 검토에서 대부분
#:    불가가 맞고, 식품 · 화장품 밖 업종은 살릴 것도 거절) — 식품 · 건기식 · 화장품 위주라 채택(사용자 10-17 · `데이터확장_시범결과_2026-10-16.md`).
#:    v14 로 돌아가려면 COPYLANE_SLLM_STAGE1=q4b-v14 · COPYLANE_SLLM_RESCUE=0
#: ⛔ 2026-10-19 — 위 교체는 **잠금(models.lock.json · D-335) 등재 전이라 되돌렸다.** q4b-n2 는 잠금에 없어 서버가 뜨지 않았다
#:    (`LockOutside` — 앱 고쳐 쓰기 「연결하지 못했어요」). 팀장이 잠금에 q4b-n2 를 등재하면 이 줄을 "q4b-n2" 로 · RESCUE 기본을 켠다.
#:    그 전에 n2 를 쓰려면 잠금 등재 판이 아니므로 서버가 막는다 — 시험은 `eval_*.py`(잠금을 보지 않는다)로만
DEFAULT_STAGE1 = "q4b-v14"
DEFAULT_BASE = "Qwen/Qwen3-4B-Instruct-2507"
#: 🔄 2026-10-12 — 2단계는 다듬기 데이터(`persona_polish.jsonl`)를 더해 다시 학습한 판(`…_q4b_polish`). 고객층 없이 다듬기 39/39 통과
#:    (종전 판 16/39 · 「건강 · 도움」을 붙여 막힘). 종전 판으로 돌아가려면 COPYLANE_SLLM_STAGE2=models\copylane_sllm_persona_adapter_q4b
DEFAULT_STAGE2 = ROOT / "models" / "copylane_sllm_persona_adapter_q4b_polish"

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


#: 🆕 2026-10-19 — 추론 정밀도. 배포 서버가 **Tesla T4**(AWS g4dn.xlarge · Turing sm_75)라 bf16 을 하드웨어로 못 한다 —
#:    bf16 고정이면 안 돌거나 매우 느리다. `auto`(기본)는 GPU 가 bf16 을 하면 bf16, 아니면 fp16 · 바꾸려면 `COPYLANE_SLLM_DTYPE=bf16|fp16`.
#:    학습 스크립트는 Ampere 이상(RTX 3080 · RunPod)에서만 돌려 bf16 그대로다
ENV_DTYPE = "COPYLANE_SLLM_DTYPE"


def serve_dtype():  # noqa: ANN201 — torch.dtype (이 모듈은 torch 없이 읽혀야 해서 여기서 가져온다)
    import torch  # noqa: PLC0415

    want = (_env(ENV_DTYPE) or "auto").lower()
    if want in ("bf16", "bfloat16"):
        return torch.bfloat16
    if want in ("fp16", "float16", "half"):
        return torch.float16
    return torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16


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


# ── 🆕 2026-10-13 모델 잠금 (D-333 · 팀장 요청) ─────────────────────────────────────────
#: 서버(앱 경로)는 잠금(`models.lock.json`)의 채택 · 되돌림 판만 올린다. 대조는 `app/model_lock.py` 를 그대로 부른다 —
#: 여기서 다시 짜지 않는다(D-99). 판을 고르는 것은 종전대로 환경 변수지만, 고른 폴더가 잠금 밖이면 올리지 않는다.
ROLE_STAGE1 = "sllm_stage1"
ROLE_STAGE2 = "sllm_stage2"

#: 잠금 밖 판도 올리는가 — **평가 · 실험 도구만** 켠다(`permit_unlocked`). 서버(`--serve`)는 켜지 않는다 (D-205 · D-333)
_UNLOCKED_OK = False


class LockOutside(AdapterMismatch):
    """어댑터 폴더가 잠금의 채택 · 되돌림 판이 아니다(또는 잠금을 읽지 못했다)."""


def permit_unlocked() -> None:
    """이 프로세스에서 잠금 밖 판도 올린다 — 평가 · 실험 도구가 부른다. 🚨 서버는 부르지 않는다."""
    global _UNLOCKED_OK  # noqa: PLW0603 — 프로세스 단위 스위치다
    _UNLOCKED_OK = True


def lock_match(adapter_dir: Path, role: str):  # noqa: ANN201 — app.model_lock.Match
    """폴더를 잠금에 대 본다(파일 전부 sha256). 🔴 잠금을 못 읽으면 `LockOutside` — 모르는 판을 아는 판으로 세지 않는다 (D-220)."""
    from app import model_lock  # noqa: PLC0415

    try:
        return model_lock.match(adapter_dir, role)
    except (model_lock.LockError, OSError) as e:
        raise LockOutside(f"모델 잠금으로 판을 확인하지 못했다 — {e}") from e


def checked(adapter_dir: Path, role: str):  # noqa: ANN201 — app.model_lock.Match
    """올려도 되는 판인가 — 채택 · 되돌림이면 대조 결과, 잠금 밖이면 `LockOutside`(도구가 허락했으면 결과를 그대로)."""
    from app import model_lock  # noqa: PLC0415

    m = lock_match(adapter_dir, role)
    if m.status == model_lock.OUTSIDE and not _UNLOCKED_OK:
        raise LockOutside(
            f"잠금(models.lock.json)에 없는 {role} 판이다 — {m.why} ({adapter_dir.name}). "
            "  잠금의 채택 · 되돌림 판 폴더로 바꾸거나(COPYLANE_SLLM_STAGE1 · COPYLANE_SLLM_STAGE2) · "
            "실험은 평가 도구로 한다(docs/lse/eval_*.py)"
        )
    return m
