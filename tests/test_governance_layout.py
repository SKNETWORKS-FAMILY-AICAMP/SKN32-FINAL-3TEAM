"""거버넌스 게이트 — 저장소 구조 자체를 검사한다 (D-19 · D-51 · D-89).

🚨 doctor 와 중복이 아니다. doctor 는 "내 기기" 를 보고,
   이 테스트는 "저장소" 를 본다. CI 와 pre-push 에서 도는 쪽은 이쪽이다.

판단 기준 (D-89): 기기마다 답이 다르면 doctor, 저장소에서 답이 하나면 pytest.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

# D-19 — 등급별 물리 분리. 위치가 곧 게이트다.
GRADE_DIRS = ["g3", "g2_facts", "g2_norepub", "quarantine", ".g1_blocked"]

VALID_GRADES = {"G0", "G1", "G2", "G3"}
VALID_USES = {"U1", "U2", "U3", "U4"}
VALID_FLAGS = {
    "BY",
    "NC",
    "SA",
    "PII",
    "TOS",
    "GATED",  # 기존
    "NOREDIST",  # D-71
    "NOSTORE",
    "QUERYLOG",
    "PREAPPROVAL",  # D-73
}

# 🚨 등급이 허용하는 용도 상한 (data_sources.yaml 머리말과 같은 표다)
#    G2 = 사실만 추출 · 원문 미보관  →  U2(원문 색인) · U3(화면 인용) 은 정의상 불가
#    G0 = 미표기 · 미확인            →  fail-closed. 확인 후 2인 판정으로만 승격
GRADE_CAP: dict[str, set[str]] = {
    "G3": {"U1", "U2", "U3", "U4"},
    "G2": {"U1", "U4"},
    "G1": set(),
    "G0": set(),
}


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
    """.env 가 git 에 올라가면 그 순간 키가 히스토리에 박힌다 (P0-2).

    🚨 D-78 이후 위험의 크기가 달라졌다 — DB 접속 정보가 아니라 금액이 붙은
       클라우드 키(AWS 30만원 · RunPod $300)가 5인 공유로 들어온다.
    """
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


# ══════════════════════════════════════════════════════════════
# 아래 5건은 2026-08-31 추가 — 형태만 보던 게이트에 「의미」를 넣는다.
#   기존 게이트는 grade 가 G0~G3 안에 있는지, use 네 축이 다 있는지만 봤다.
#   그래서 G0 소스에 U1·U2 를 allow 로 열어 두어도 통과했다. 실제로 열려 있었다.
# ══════════════════════════════════════════════════════════════


@pytest.mark.gate
def test_등급이_허용하는_용도_상한을_넘지_않는다() -> None:
    """🚨 등급과 용도가 어긋나면 등급 표기가 거짓이 된다.

    G2 는 「사실만 추출 · 원문 미보관」이다. 그런 등급에 U2(원문 색인)와
    U3(화면 인용)이 열려 있으면 등급이 아니라 장식이다.
    G0 는 「미확인」이므로 전 용도를 닫는다 — 확인 후 2인 판정으로만 승격한다 (D-72).
    """
    for key, src in _sources().items():
        grade = src["grade"]
        cap = GRADE_CAP[grade]
        allowed = {a for a, v in (src.get("use") or {}).items() if v == "allow"}
        over = allowed - cap
        assert not over, (
            f"{key}: 등급 {grade} 인데 {sorted(over)} 가 allow 다 — "
            f"{grade} 의 상한은 {sorted(cap) or '없음'}"
        )


@pytest.mark.gate
def test_제약_플래그는_정의된_것만_쓴다() -> None:
    """오타 하나가 조용히 제약을 없앤다 — NOREDIST 를 NOREDST 로 쓰면 전파 규칙이 안 걸린다."""
    for key, src in _sources().items():
        unknown = set(src.get("constraints") or []) - VALID_FLAGS
        assert not unknown, f"{key}: 정의되지 않은 제약 플래그 {sorted(unknown)}"


@pytest.mark.gate
def test_NOREDIST_와_redistributable_이_일치한다() -> None:
    """🚨 D-71 의 전파 규칙 `데이터셋 공개 = { f | NOREDIST 없음 }` 을 코드로 세운다.

    사람이 읽는 규칙은 문서에만 있었다. G3 를 보고 「원문 자유니까 공개해도 되겠지」로
    가는 경로가 열려 있었고, AI Hub 6종이 정확히 그 함정이다 — 등급은 G3 인데
    데이터셋 재배포는 막혀 있다. 등급과 재배포는 다른 축이다.
    """
    for key, src in _sources().items():
        has_flag = "NOREDIST" in (src.get("constraints") or [])
        redist = src.get("redistributable")
        assert redist is not None, f"{key}: redistributable 필드가 없다 (D-71)"
        assert redist is not has_flag, (
            f"{key}: NOREDIST={has_flag} 인데 redistributable={redist} 다 — 둘은 같은 사실이다"
        )


@pytest.mark.gate
def test_수집이_시작된_소스는_2인_확인이_끝나_있다() -> None:
    """🚨 collected_at 이 찍혔다는 것은 판정이 끝났다는 뜻이다 (D-66).

    「수집 전에 2인 확인」을 지시로만 두면 반드시 뒤로 밀린다. 시점을 못 박는다 —
    수집을 시작하는 순간이 마지노선이고, 그때는 이미 되돌릴 수 없다.
    DB 의 CHECK (grade_decided_by <> grade_reviewed_by) 와 같은 제약을 레지스트리에서 건다.
    """
    for key, src in _sources().items():
        if not src.get("collected_at"):
            continue
        decided, reviewed = src.get("decided_by"), src.get("reviewed_by")
        assert decided, f"{key}: 수집이 시작됐는데 decided_by 가 없다"
        assert reviewed, f"{key}: 수집이 시작됐는데 reviewed_by 가 없다 — 2인 확인 미완 (D-66)"
        assert decided != reviewed, (
            f"{key}: decided_by 와 reviewed_by 가 같다 ({decided}) — 2인 확인이 아니다"
        )


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
def test_미채택_목록은_실제_등급을_유지한다() -> None:
    """🚨 blocked 와 not_adopted 를 섞지 않는다.

    「가치가 없어서 안 쓴다」와 「법적·윤리적으로 막혔다」는 다른 판정이다.
    전자에 G1 을 찍으면 등급 축이 오염되고, 나중에 필요해졌을 때 재판정 비용이 생긴다.
    not_adopted 에 G1 이 있으면 그것은 blocked 로 가야 할 항목이다 (D-72).
    """
    items = _registry().get("not_adopted") or []
    assert isinstance(items, list) and items, "not_adopted 가 비어 있다"

    for item in items:
        key = item.get("key", "?")
        grade = item.get("grade")
        assert grade in VALID_GRADES, f"not_adopted[{key}]: grade 가 없거나 잘못됨 ({grade!r})"
        assert grade != "G1", (
            f"not_adopted[{key}]: G1 은 blocked 로 옮긴다 — 미채택이 아니라 배제다"
        )
        assert item.get("reason"), f"not_adopted[{key}]: reason 이 없다"


@pytest.mark.gate
def test_모든_모델에_라이선스와_등급과_배포용도가_있다() -> None:
    """모델 가중치도 G-게이트 대상이다 (D-23).

    🚨 use.U4 를 필드로 요구하는 것이 핵심이다. KLUE-RoBERTa 의 「배포 금지」가
       주석으로만 있으면 학습 설정에 들어가도 아무것도 실패하지 않는다.
       게이트는 주석을 읽지 못한다 (D-89 · 차별점 ⑤ 「코드로 강제한다」).
    """
    models = _registry().get("models") or {}
    assert models, "models 섹션이 비어 있다"

    for key, spec in models.items():
        assert spec.get("license"), f"{key}: license 표기가 없다"
        grade = spec.get("grade")
        assert grade in VALID_GRADES, f"{key}: grade 가 없거나 잘못됨 ({grade!r})"

        use = spec.get("use") or {}
        assert "U4" in use, f"{key}: use.U4(배포 가능 여부) 가 없다 — 주석은 게이트가 못 읽는다"
        assert use["U4"] in {"allow", "deny"}, f"{key}.use.U4 = {use['U4']!r}"

        if spec.get("license") in (None, "", "없음"):
            assert use["U4"] == "deny", (
                f"{key}: 라이선스가 없는데 U4 가 allow 다 — 배포하면 근거 없는 재배포가 된다"
            )


# ══════════════════════════════════════════════════════════
# D-92 — raw/ 는 소비 금지 구역이다
#
# 🚨 원문은 등급 디렉터리 밖(data/raw/)에 둔다. D-18(판정 단위는 FRAGMENT)과
#    D-19(위치가 곧 게이트)를 동시에 만족시키는 유일한 배치다 — 한 원문 파일 안에
#    등급이 갈리는 조각이 섞이면, 그 파일은 어느 등급 디렉터리에도 놓을 수 없다.
#
#    그 대가로 raw/ 안에서는 등급이 섞인다. D-19 가 실제로 막으려는 것은
#    「소비 경로가 낮은 등급을 읽는 것」이므로, 소비가 raw/ 를 보지 않도록
#    아래 두 게이트가 그 자리를 대신한다.
# ══════════════════════════════════════════════════════════

# raw/ 를 읽어도 되는 곳 — 수집기와 전처리기뿐이다.
RAW_READERS = {"collect", "preprocess"}


@pytest.mark.gate
def test_raw_는_수집_전처리_밖에서_참조되지_않는다() -> None:
    """학습·RAG·배포가 data/raw/ 를 직접 읽으면 D-19 가 무력화된다.

    🚨 구조가 못 막는 것을 코드가 막는다. 검사 16(판정 경로 외부 API = 0)과 같은 방식이다.
       raw/ 에는 등급이 섞여 있으므로, 여기를 글롭하는 학습 스크립트가 하나만 있어도
       G2·G0 원문이 학습에 들어간다.
    """
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if parts[0] in {".venv", "build", "dist", ".git"}:
            continue
        if parts[0] in RAW_READERS or rel == Path("tests/test_governance_layout.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "data/raw" in text or "data\\raw" in text:
            offenders.append(str(rel))

    assert not offenders, (
        "data/raw/ 를 수집·전처리 밖에서 참조한다 — 소비 경로는 등급 디렉터리와 "
        f"derived/ 만 읽는다 (D-92): {offenders}"
    )


@pytest.mark.gate
def test_manifest의_소스는_레지스트리에_있고_G1이_아니다() -> None:
    """raw/ 에 무엇이 들어왔는지는 manifest 가 증언한다 (수집기 공통 규약 3).

    🚨 G1 은 수집 자체를 하지 않는다. raw/ 는 등급 디렉터리가 아니라서 구조가
       막지 못하므로, 원장에 G1 이 찍히는 순간 실패시킨다 (doctor 검사 18 의 확장).
    """
    manifest = ROOT / "data" / "manifest.jsonl"
    assert manifest.exists(), "data/manifest.jsonl 이 없다 — 수집 원장은 저장소에 남는다"

    sources = _sources()
    for lineno, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        sid = row.get("source_id")
        assert sid, f"manifest:{lineno} — source_id 가 없다"
        assert sid in sources, f"manifest:{lineno} — {sid!r} 가 레지스트리에 없다"
        assert sources[sid].get("grade") != "G1", (
            f"manifest:{lineno} — {sid!r} 는 G1 이다. 수집 자체를 하지 않는다"
        )
