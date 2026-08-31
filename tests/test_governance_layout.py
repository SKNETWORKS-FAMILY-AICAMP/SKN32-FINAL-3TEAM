"""거버넌스 게이트 — 저장소 구조 자체를 검사한다 (D-19 · D-51).

🚨 doctor 와 중복이 아니다. doctor 는 "내 기기" 를 보고,
   이 테스트는 "저장소" 를 본다. CI 와 pre-push 에서 도는 쪽은 이쪽이다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

# D-19 — 등급별 물리 분리. 위치가 곧 게이트다.
GRADE_DIRS = ["g3", "g2_facts", "g2_norepub", "quarantine", ".g1_blocked"]

VALID_GRADES = {"G0", "G1", "G2", "G3"}
VALID_USES = {"U1", "U2", "U3", "U4"}


@pytest.mark.gate
@pytest.mark.parametrize("name", GRADE_DIRS)
def test_등급_디렉터리가_존재한다(name: str) -> None:
    """등급 디렉터리가 없으면 수집 스크립트가 어디에 쓸지 알 수 없다."""
    path = ROOT / "data" / name
    assert path.is_dir(), f"data/{name}/ 가 없다 — D-19 물리 분리 위반"


@pytest.mark.gate
def test_g1_blocked_는_비어있다() -> None:
    """G1(배제) 자료가 저장소에 들어와 있으면 즉시 실패다."""
    blocked = ROOT / "data" / ".g1_blocked"
    strays = [p.name for p in blocked.iterdir() if p.name != ".gitkeep"]
    assert not strays, f"data/.g1_blocked/ 에 파일이 있다 — 즉시 제거: {strays}"


@pytest.mark.gate
def test_env_파일이_추적되지_않는다() -> None:
    """.env 가 git 에 올라가면 그 순간 키가 히스토리에 박힌다 (P0-2)."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, ".env 가 git 에 추적되고 있다 — 즉시 git rm --cached .env"


def _registry() -> dict:
    return yaml.safe_load((ROOT / "data_sources.yaml").read_text(encoding="utf-8"))


def _sources() -> dict:
    """개별 소스만 돌려준다.

    🚨 sources.blocked 는 소스가 아니라 「편입 금지 목록」이다 (기획서 4-2).
       형태가 리스트라 개별 소스와 같은 규칙을 적용할 수 없다.
    """
    return {k: v for k, v in (_registry().get("sources") or {}).items() if isinstance(v, dict)}


@pytest.mark.gate
def test_모든_소스에_등급과_용도가_있다() -> None:
    """등록되지 않았거나 등급이 없는 소스는 수집이 거부되어야 한다 (D-15)."""
    sources = _sources()
    assert sources, "data_sources.yaml 에 소스가 하나도 없다"

    for key, src in sources.items():
        grade = src.get("grade")
        assert grade in VALID_GRADES, f"{key}: grade 가 없거나 잘못됨 ({grade!r})"

        use = src.get("use") or {}
        missing = VALID_USES - set(use)
        assert not missing, f"{key}: use 에 {sorted(missing)} 가 빠졌다"

        for axis, verdict in use.items():
            assert verdict in {"allow", "deny"}, (
                f"{key}.use.{axis} = {verdict!r} — allow/deny 만 허용"
            )


@pytest.mark.gate
def test_G1_소스는_모든_용도가_deny다() -> None:
    """G1 은 배제다. allow 가 하나라도 있으면 등급 표기가 거짓이다."""
    for key, src in _sources().items():
        if src.get("grade") != "G1":
            continue
        allowed = [axis for axis, verdict in (src.get("use") or {}).items() if verdict == "allow"]
        assert not allowed, f"{key}: G1 인데 {allowed} 가 allow 다"


@pytest.mark.gate
def test_편입금지_목록은_전부_G1이고_사유가_있다() -> None:
    """blocked 는 협상 불가 목록이다 (기획서 4-2). 사유 없는 항목은 재론을 부른다."""
    blocked = (_registry().get("sources") or {}).get("blocked") or []
    assert isinstance(blocked, list) and blocked, "sources.blocked 가 비어 있다"

    for item in blocked:
        name = item.get("name", "?")
        assert item.get("grade") == "G1", f"blocked[{name}]: grade 가 G1 이 아니다"
        assert item.get("reason"), f"blocked[{name}]: reason 이 없다"


@pytest.mark.gate
def test_모든_모델에_라이선스와_등급이_있다() -> None:
    """모델 가중치도 G-게이트 대상이다 (D-23)."""
    models = _registry().get("models") or {}
    assert models, "models 섹션이 비어 있다"

    for key, spec in models.items():
        assert spec.get("license"), f"{key}: license 표기가 없다"
        grade = spec.get("grade")
        assert grade in VALID_GRADES, f"{key}: grade 가 없거나 잘못됨 ({grade!r})"
