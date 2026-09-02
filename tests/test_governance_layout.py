"""거버넌스 게이트 — 저장소 구조 자체를 검사한다 (D-19 · D-51 · D-89).

🚨 doctor 와 중복이 아니다. doctor 는 "내 기기" 를 보고,
   이 테스트는 "저장소" 를 본다. CI 와 pre-push 에서 도는 쪽은 이쪽이다.

판단 기준 (D-89): 기기마다 답이 다르면 doctor, 저장소에서 답이 하나면 pytest.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

# D-19 — 등급별 물리 분리. 위치가 곧 게이트다.
GRADE_DIRS = ["g3", "g2_facts", "g2_norepub", "quarantine", ".g1_blocked"]

VALID_GRADES = {"G0", "G1", "G2", "G3"}
VALID_USES = {"U1", "U2", "U3", "U4"}
# D-108 — status 는 「수집기가 실행하는가」다. blocked·not_adopted 는 값이 아니라 별도 섹션이다.
VALID_STATUS = {"collect", "manual", "hold"}
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

    # 🚨 models 도 같은 규칙을 받는다. 소스 쪽은 D-90 ④-1 로 해소됐는데(G0 인데 용도가 열린
    #    소스 0건) **모델 섹션만 남아 있었다** — `klue_roberta` 가 G0 인데 U1: allow 다.
    #    D-90 ④-1 이 만들어진 이유가 정확히 이 결함이고, 잡는 자리를 반쪽만 만들었다
    #    (권소라 역검토 v1.2 §4).
    for key, spec in (_registry().get("models") or {}).items():
        grade = spec.get("grade")
        if grade not in GRADE_CAP:
            continue
        allowed = {a for a, v in (spec.get("use") or {}).items() if v == "allow"}
        over = allowed - GRADE_CAP[grade]
        assert not over, (
            f"models[{key}]: 등급 {grade} 인데 {sorted(over)} 가 allow 다 — "
            f"{grade} 의 상한은 {sorted(GRADE_CAP[grade]) or '없음'} (D-72)"
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
        # 🚨 reason 이 「비어 있지만 않으면」 통과했다. YAML 플로우 매핑에서 인용 없는 값의
        #    쉼표는 구분자라, 사유 뒷문장이 통째로 **유령 키**가 되고 앞 절반만 남는다.
        #    실제로 KOBACO AiSAC 이 그 상태였다 (권소라 역검토 v1.2 §3).
        assert set(item) == {"name", "grade", "reason"}, (
            f"blocked[{name}]: 키가 {sorted(item)} 다 — {{name, grade, reason}} 뿐이어야 한다. "
            '값에 쉼표가 있으면 "..." 로 감싼다'
        )


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


@pytest.mark.gate
def test_검토_대상_소스는_모두_판정_근거를_가진다() -> None:
    """2인 확인은 판정을 **재현**하는 절차다 (D-66). 근거가 없으면 재현할 것이 없다.

    🚨 이 게이트가 실제로 지키는 것은 「매트릭스 id ↔ 레지스트리 키」 매핑이다.
       둘은 단위가 다르다 — 매트릭스는 「판정 근거」 단위, 레지스트리는 「이용조건」
       단위다 (D-90). 그래서 이름이 어긋나거나 N:1 로 묶인 것이 있고, 그 매핑은
       extract_rationale.py 의 ALIAS 표가 들고 있다.

       표가 낡으면 근거가 **조용히** 사라진다. 검토표에는 「판정 근거 없음」만 뜨고,
       근거가 없어서인지 이름이 어긋나서인지 검토자는 구분할 수 없다.
       그 상태로 서명이 들어가면 그것이 D-66 이 막으려던 「동의만 찍는 검토」다.
    """
    rationale_path = ROOT / "scripts" / "registry_rationale.yaml"
    assert rationale_path.exists(), (
        "scripts/registry_rationale.yaml 이 없다 — "
        "uv run python scripts/extract_rationale.py 로 뽑는다"
    )
    rationale = yaml.safe_load(rationale_path.read_text(encoding="utf-8")) or {}

    targets = {
        k: v
        for k, v in _sources().items()
        if any((v.get("use") or {}).get(u) == "allow" for u in sorted(VALID_USES))
    }
    missing = [k for k in targets if not (rationale.get(k) or {}).get("why")]

    # 🚨 `why` 존재만 보면 「근거가 있긴 한데 재현에 못 쓰는 상태」가 그물을 빠져나간다.
    #    확인 항목 4 가 *"근거 URL 이 실제로 그 조건을 말하는가 — 링크를 열어 보십시오"* 인데,
    #    URL 이 없으면 그 항목이 성립하지 않는다 (권소라 역검토 v1.2 §5).
    #    외부 URL 이 없는 자체 산출물은 **산출 근거 문서 경로**를 넣는다 (D-99).
    no_url = [k for k, v in targets.items() if not v.get("evidence_url")]
    assert not no_url, (
        "용도가 열린 소스에 근거 URL 이 없다 — 확인 항목 4(링크를 열어 확인)가 성립하지 않는다 "
        f"(D-99). 자체 산출물이면 산출 근거 문서 경로를 넣는다: {no_url}"
    )

    assert not missing, (
        "용도가 열린 소스에 판정 근거가 없다 — 검토자가 등급을 재현할 수 없다 (D-66 · D-90). "
        "판정매트릭스에 엔트리를 넣거나, id 가 다를 뿐이라면 extract_rationale.py 의 "
        f"ALIAS 에 잇는다: {missing}"
    )


# 크롤링형으로 판정되는 `access` 표현 — collect/registry.py 의 CRAWL_ACCESS 와 같은 집합이다.
CRAWL_ACCESS = {"크롤링", "게시판", "스크래핑"}


@pytest.mark.gate
def test_크롤링형_소스는_robots_확인_기록을_가진다() -> None:
    """🚨 게이트는 초록불인데 수집기 첫 줄에서 죽던 자리다.

    `collect/registry.py` 의 규약 6 이 크롤링형 소스에 `robots_checked_at` 을 요구하는데,
    **그 필드를 만드는 코드가 어디에도 없었다** — `gen_registry.py` 의 `block()` 이 쓰는
    필드 목록에도, `EXTRA` 하드코딩에도 없었다. 그래서 `mfds_hf_ingredient_board`(S1-06 ·
    고시형 96 + 개별인정형 472 = 568건 · 2층 적법 라벨의 실체)가 **영구히 수집 불가**였다.

    🚨 **규약이 수집 시점에만 걸리면 CI 는 통과하고 사람이 부딪힌다.** 저장소에서 답이
    하나인 검사이므로 pytest 쪽이다 (D-89). 값은 **사람이 robots.txt 를 열어 본 날**이며,
    비워 두면 이 게이트가 막는다 — 확인 없이 여는 것을 막는 것이 목적이다 (D-72).
    """
    offenders = []
    for key, src in _sources().items():
        access = str(src.get("access") or "")
        if not any(w in access for w in CRAWL_ACCESS):
            continue
        if not any((src.get("use") or {}).get(u) == "allow" for u in sorted(VALID_USES)):
            continue  # 전 용도 닫힘 — 게이트가 이미 막는다
        if not src.get("robots_checked_at"):
            offenders.append(f"{key}(access={access!r})")

    assert not offenders, (
        "크롤링형인데 robots_checked_at 이 없다 — 수집기가 규약 6 에서 거부한다. "
        "robots.txt 를 열어 확인한 날을 scripts/registry_review.yaml 에 적는다: "
        f"{offenders}"
    )


@pytest.mark.gate
def test_판정은_다형_참조의_대상을_제약으로_고정한다() -> None:
    """다형 참조는 FK 무결성이 DB 수준에서 안 걸린다 — 그 자리를 CHECK 가 대신한다 (D-103).

    🚨 `judgment.subject_type` 이 열려 있으면 오타 하나가 조용히 새 종류의 판정을 만든다.
       주장 계층을 9/17 이후로 미룰 수 있게 하는 것이 이 컬럼인데, 값 집합이 고정되지
       않으면 미루는 것이 아니라 흐려지는 것이다.
    """
    from app.models import CopySentence, Judgment, WorkDoc

    def _checks(model) -> set[str]:
        return {
            c.name for c in model.__table__.constraints if c.__class__.__name__ == "CheckConstraint"
        }

    assert "ck_judgment_subject_type" in _checks(Judgment), (
        "judgment 에 subject_type CHECK 가 없다 — 다형 참조의 유일한 방어선이다 (D-103)"
    )
    assert "ck_copy_sentence_origin" in _checks(CopySentence), "copy_sentence.origin CHECK 가 없다"
    assert "ck_work_doc_kind" in _checks(WorkDoc), "work_doc.kind CHECK 가 없다"


@pytest.mark.gate
def test_status_는_수집기_실행_여부이고_collect_는_용도가_열려있다() -> None:
    """🚨 `status` 가 두 뜻으로 쓰이고 있었다 — 「수집기가 돈다」와 「작업 목록에 있다」 (D-108).

    같은 `collect` 값이 정반대 두 상황에 붙어 있었다.

    * `kfia_approved_list` · `krei_food` — 자동 수집기가 도는데 **G0 라 용도가 전부 닫혀**
      있었다. 가져오지만 쓸 곳이 없다. G0 를 fail-closed 로 닫아 둔 이유(D-72)가
      **수집 단계에서 우회**된다 — 확인이 수집보다 먼저다.
    * `meta_adlibrary` · `google_atc` — 자동 수집이 **약관 위반**이라 사람이 수기로 옮긴다.
      그 사실이 `caution` 자유 문장에만 있었고 **기계가 읽는 자리에 없었다.**

    그래서 값을 셋으로 고정하고(`collect`/`manual`/`hold`), `collect` 에만 교차 규칙을 건다.
    🚨 **역은 성립하지 않는다** — `hold` 인데 용도가 열려 있는 것은 「판정 끝, 착수만 남음」이며
    정상이다. 두 축은 다르다: `status` 는 가져오는가, `use` 는 가져온 것을 쓸 수 있는가.
    """
    offenders = []
    bad_value = []
    for key, src in _sources().items():
        status = src.get("status")
        if status not in VALID_STATUS:
            bad_value.append(f"{key}={status!r}")
            continue
        if status != "collect":
            continue
        use = src.get("use") or {}
        if not any(use.get(u) == "allow" for u in sorted(VALID_USES)):
            offenders.append(f"{key}(G{src.get('grade', '?')[-1]} · 전 용도 deny)")

    assert not bad_value, (
        f"status 값이 어휘 밖이다 {sorted(VALID_STATUS)} 만 허용한다 (D-108): {bad_value}"
    )
    assert not offenders, (
        "status: collect 인데 열린 용도가 하나도 없다 — 가져와서 쓸 곳이 없는 자동 수집이다. "
        "확인이 선행이면 hold, 수기 경로면 manual 로 옮긴다 (D-108): " + str(offenders)
    )


@pytest.mark.gate
def test_탐침은_저장_경로를_부를_수_없다() -> None:
    """🚨 탐침에 「저장 안 함」은 약속이 아니라 **구조**여야 한다 (D-109).

    규약 1 이 경고한 것이 정확히 이 자리다 — *"「일단 받아두고 나중에 판정한다」는 경로가
    있으면 그 경로로만 다니게 된다."* 탐침은 `reviewed_by` 를 요구하지 않으므로,
    **여기에 쓰기가 한 줄이라도 생기면 그것이 게이트 전체의 우회로**가 된다.

    그래서 사람이 지키는 규칙이 아니라 **없는 경로**로 만든다 (D-107 조건 1 과 같은 형태) —
    `store` 를 import 하지 않고, `mark_collected` 를 부르지 않고, 쓰기 API 를 쓰지 않는다.
    """
    # 🚨 **문자열이 아니라 AST 로 본다.** 산문에 「store 를 부르지 않는다」라고 쓰면
    #    문자열 검사는 그 문장에 걸린다 — 설명이 위반으로 읽히는 게이트는 못 쓴다.
    src = (ROOT / "collect" / "probe.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    FORBIDDEN_MOD = {"collect.store", "store"}
    FORBIDDEN_CALL = {
        "mark_collected": "수집 시각 기록 (규약 3 · 게이트 15)",
        "manifest_append": "수집 원장 append (규약 3)",
        "save_raw": "원본 파일 쓰기 (규약 2)",
        "drop_raw_for_g2": "G2 raw 삭제 (D-17)",
        "require": "수집기 게이트 — 탐침은 registry.probe 를 쓴다",
        "write_bytes": "파일 쓰기",
    }
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in FORBIDDEN_MOD:
            hits.append(f"from {node.module} import …")
        if isinstance(node, ast.ImportFrom) and node.module == "collect":
            hits += [f"collect.{a.name}" for a in node.names if a.name in FORBIDDEN_MOD]
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name in FORBIDDEN_MOD]
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in FORBIDDEN_CALL:
                hits.append(f"{name}() — {FORBIDDEN_CALL[name]}")
    assert not hits, (
        "🚨 탐침이 저장 경로에 손을 댔다 — 게이트 전체의 우회로가 된다 (D-109): " + str(hits)
    )

    # 🚨 쓰기는 딱 한 자리여야 하고 그 자리는 docs/ 다. 등급 디렉터리는 수집기만 쓴다 (D-19).
    writes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "write_text"
    ]
    assert len(writes) == 1, f"탐침의 쓰기는 리포트 한 자리뿐이어야 한다 (현재 {len(writes)}곳)"
    assert 'ROOT / "docs' in src, "탐침 산출은 docs/ 로만 나간다"

    # 🚨 **런타임으로 증명한다** — 문자열 검사는 「안 썼다」만 말하고
    #    「쓸 수 없다」는 말하지 못한다. 탐침을 새 프로세스에서 import 했을 때
    #    `collect.store` 가 sys.modules 에 없어야 한다.
    #    (한때 `collect/__init__.py` 가 store 를 재수출해서, 탐침 프로세스에
    #     저장 코드가 통째로 로드되고 있었다.)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import collect.probe; "
            "print('LOADED' if 'collect.store' in sys.modules else 'CLEAN')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"탐침 import 실패: {proc.stderr[-500:]}"
    assert proc.stdout.strip() == "CLEAN", (
        "🚨 탐침 프로세스에 collect.store 가 로드된다 — 「안 부른다」가 아니라 "
        "「부를 수 없다」여야 한다 (D-109)"
    )


@pytest.mark.gate
def test_탐침_게이트는_G1과_수기와_승인선행을_막는다() -> None:
    """🚨 탐침이 `reviewed_by` 를 면제받는 대신 **다른 넷은 그대로 막는다** (D-109).

    면제의 근거는 *"탐침은 아무것도 가져오지 않는다"* 인데, 그 논리가 통하지 않는 자리가 있다.
    G1 은 **여는 것 자체가 문제**이고, `manual` 과 `GATED` 는 **접근 방식이 조건 위반**이며,
    robots 는 애초에 수집이 아니라 **접근**의 조건이다. 면제 하나가 넷을 데려가면 안 된다.
    """
    from collect.registry import RegistryError, probe  # noqa: PLC0415

    srcs = _sources()
    manual = [k for k, v in srcs.items() if v.get("status") == "manual"]
    gated = [k for k, v in srcs.items() if "GATED" in (v.get("constraints") or [])]
    assert manual and gated, "표본이 없다 — 레지스트리가 바뀌었으면 이 게이트를 다시 본다"

    for key in manual[:1] + gated[:1]:
        with pytest.raises(RegistryError):
            probe(key)

    # 🚨 G0 는 **통과해야 한다.** 전 용도 deny 인 채로 탐침 대상인 것이 정상이다 —
    #    오히려 G0 야말로 탐침이 가장 필요한 등급이다 (D-72 의 「확인 후 승격」).
    g0 = [
        k
        for k, v in srcs.items()
        if v.get("grade") == "G0"
        and v.get("status") != "manual"
        and "GATED" not in (v.get("constraints") or [])
        and not any(w in str(v.get("access") or "") for w in CRAWL_ACCESS)
    ]
    for key in g0[:1]:
        assert probe(key), f"{key}: G0 가 탐침에서 막혔다 — 확인 수단이 판정 뒤로 밀린다"
