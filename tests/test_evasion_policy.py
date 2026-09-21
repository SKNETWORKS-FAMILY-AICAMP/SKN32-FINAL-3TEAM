"""`preprocess/evasion_scan.py` — 폴더 이름이 아니라 **원천 id** 로 마스킹 정책을 찾는다 (D-254).

⛔ `scan mfds_press_pdf` 가 폴더 이름을 정책 키로 넘겨 `MaskPolicyError` 로 멈췄다 (감사 §2 scan ▶).
★ 폴더 → 원천은 `collect.store.FAMILY_OF` 한 곳이다 (D-99) — POLICY 에 폴더 이름을 더하지 않는다.
"""

from __future__ import annotations

import pytest

from collect import store
from preprocess import SCANNERS
from preprocess.evasion_scan import policy_source
from preprocess.mask import POLICY, apply_policy


@pytest.mark.gate
def test_부속_폴더는_원천의_정책을_쓴다() -> None:
    assert policy_source("mfds_press_pdf") == "mfds_press"
    apply_policy("‘기억력 개선’ 광고", "", policy_source("mfds_press_pdf"))  # 멈추지 않는다


@pytest.mark.gate
def test_evasion_scan_이_받는_폴더는_전부_정책이_있다() -> None:
    """SCANNERS 표에서 이 모듈로 가는 이름 전부 — 정책을 찾지 못하면 여기서 걸린다."""
    for folder, mod in SCANNERS.items():
        if mod == "preprocess.evasion_scan":
            assert policy_source(folder) in POLICY, folder


def test_표에_없는_폴더는_그대로다() -> None:
    assert policy_source("mfds_casebook") == "mfds_casebook"


def test_여러_원천이_쓰는_폴더는_고르지_않고_멈춘다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "FAMILY_OF", {"a": ("공용",), "b": ("공용",)})
    with pytest.raises(SystemExit):
        policy_source("공용")
