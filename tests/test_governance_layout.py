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

    🔄 **주석과 docstring 은 보지 않는다** (2026-09-02). 런처의 `register` 설명에
       *"data/raw/<소스id>/ 로 복사한다"* 라고 적었더니 **그 설명이 위반으로 잡혔다** —
       게이트 23 에서 겪은 것과 같은 형태다. 🚨 **게이트가 산문을 검사하기 시작하면
       사람이 주석을 지운다.** 막으려는 것은 「읽는 코드」이지 「읽는다고 적은 문장」이 아니다.
    """
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        # 🚨 `Claude outputs/` 는 Claude 앱이 떨어뜨리는 사본이다 — `.gitignore` 에 이미 있다.
        #    레포 소스가 아니라서 게이트 대상도 아니다 (2026-09-06 에 여기 걸렸다).
        if parts[0] in {".venv", "build", "dist", ".git", "Claude outputs"}:
            continue
        if parts[0] in RAW_READERS or rel == Path("tests/test_governance_layout.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "data/raw" not in text and "data\\raw" not in text:
            continue
        # 주석·docstring 을 걷어낸 뒤 다시 본다 — 남아 있으면 그것은 코드다.
        try:
            tree = ast.parse(text)
        except SyntaxError:
            offenders.append(str(rel))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                node.value.value = ""  # docstring 을 비운다
        code = ast.unparse(tree)
        if "data/raw" in code or "data\\raw" in code:
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
def test_derived_로_나가는_원문은_마스킹을_지난다() -> None:
    """🔴 **마스킹은 「즉시」여야 하는데 지금까지 「부르면」이었다** (D-17 · 2026-09-06).

    사양 [P3] 은 마스킹을 「등급과 무관하게 **수집 직후 즉시**」로 못 박았다. 그런데
    `preprocess/mask.py` 는 함수일 뿐이라 **부르지 않으면 안 돈다.**

    ⛔ 실제로 새고 있었다 — `preprocess/ftc_triage.py` 가
       `data/derived/ftc_layer1_triage.json` 에 사건명을 **원문 그대로** 썼다:

           {"사건명": "㈜비에스비푸드의 가맹사업법 위반행위에 대한 건", …}

       업체명이 마스킹 없이 derived 로 나가 있었고, `ftc_decisions_body` 는
       `redistributable: true` 라 그 산출물이 **공개 배포까지 간다** (D-71).

    🚨 그래서 검사한다 — **`data/raw/` 를 읽으면서 `data/derived/` 에 쓰는 모듈은
       `preprocess.mask` 를 import 한다.** 규칙이 좋아지는 것과 규칙이 도는 것은 다른 일이고,
       오늘 하루가 앞의 것만 다듬은 날이었다.

    🚨 **import 만 본다. 「제대로 마스킹했는가」는 이 게이트가 못 본다** —
       그것은 `mask --apply` 의 잔여 계수와 사람이 본다. 여기서 막는 것은
       **아예 안 부르는 것**이다. 못 하는 것을 하는 척하지 않는다.

    🚨 주석·docstring 은 보지 않는다 (바로 위 게이트와 같은 이유).
    """
    offenders: list[str] = []
    for path in (ROOT / "preprocess").rglob("*.py"):
        rel = path.relative_to(ROOT)
        if path.name in {"__init__.py", "mask.py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                node.value.value = ""
        code = ast.unparse(tree)
        reads_raw = "data/raw" in code or "data\\raw" in code
        writes_derived = "data/derived" in code or "data\\derived" in code
        if reads_raw and writes_derived and "preprocess.mask" not in code:
            offenders.append(str(rel))

    assert not offenders, (
        "raw 를 읽어 derived 로 쓰면서 preprocess.mask 를 부르지 않는다 — "
        f"마스킹이 「즉시」가 아니라 「부르면」이 된다 (D-17 · D-71): {offenders}"
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

    # 🚨 **쓰기의 개수가 아니라 목적지를 본다** (2026-09-02 정정).
    #    처음에는 `write_text` 를 한 자리로 못박았는데, 그 제약이 실제 결함을 낳았다 —
    #    단일 소스 탐침이 **전체 리포트를 덮어써** 32건 결과가 사라졌고, 고치려면
    #    누적 캐시에 한 번 더 써야 했다. 지킬 것은 「한 번만 쓴다」가 아니라
    #    **「data/ 에는 쓰지 않는다」**이므로 그쪽을 검사한다 (D-19).
    assert 'ROOT / "docs' in src, "탐침 리포트는 docs/ 로 나간다"
    assert 'ROOT / "build"' in src, "탐침 캐시는 build/ 로 나간다"

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
    # 🔄 승인이 난 GATED 는 이제 통과한다 (approved_at · 2026-09-02 AI Hub 5건).
    #    표본은 **아직 승인이 없는** GATED 여야 한다 — 게이트 27 이 그 짝을 검사한다.
    gated = [
        k
        for k, v in srcs.items()
        if "GATED" in (v.get("constraints") or []) and not v.get("approved_at")
    ]
    assert manual and gated, "표본이 없다 — 레지스트리가 바뀌었으면 이 게이트를 다시 본다"

    for key in manual[:1] + gated[:1]:
        with pytest.raises(RegistryError):
            probe(key)

    # 🔄 반대로 **승인이 난 GATED 는 통과해야 한다** — 막는 것은 승인 부재이지 GATED 자체가 아니다.
    approved = [
        k
        for k, v in srcs.items()
        if "GATED" in (v.get("constraints") or []) and v.get("approved_at")
    ]
    for key in approved[:1]:
        assert probe(key), f"{key}: 승인이 났는데도 탐침이 막힌다"

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


@pytest.mark.gate
@pytest.mark.parametrize(
    "url",
    [
        "https://www.nasmedia.co.kr/정기보고서/2026-fb-trend-report/",
        "https://www.data.go.kr/data/15103301/fileData.do",
        "https://adf.kfia.or.kr/company/open/openData.do?menuKey=406",
    ],
)
def test_수집_url_은_ascii_로_인코딩된다(url: str) -> None:
    """🚨 한글 경로 URL 이 `urllib` 에서 **잡히지 않고** 죽던 자리 (2026-09-02 탐침 1회전).

    `UnicodeEncodeError` 는 `FetchError` 가 아니라 **재시도 루프 밖에서** 터진다 —
    한 소스가 전체 실행을 멈춘다. 국내 기관 사이트에 한글 경로는 흔하고,
    `collect/http.py` 는 **탐침과 수집기의 공용**이라 같은 URL 로 수집기도 죽었다.

    ★ 탐침이 먼저 돈 덕에 **수집 착수 전에** 나왔다 — D-109 가 노린 효과가 이것이다.
    """
    from collect.http import encode  # noqa: PLC0415

    out = encode(url)
    assert out.isascii(), f"인코딩 후에도 ASCII 가 아니다: {out!r}"
    assert encode(out) == out, "🚨 멱등하지 않다 — 이미 인코딩된 URL 이 두 번 인코딩된다"
    assert out.encode("ascii"), "urllib 이 받을 수 없다"


@pytest.mark.gate
@pytest.mark.parametrize(
    ("path", "name"),
    [("scripts/gen_registry.py", "EXTRA"), ("scripts/gen_registry.py", "STATUS")],
)
def test_수동보강_표에_중복_키가_없다(path: str, name: str) -> None:
    """🚨 dict 리터럴의 중복 키는 **조용히 뒤엣것이 이긴다.**

    2026-09-02 탐침 소견을 `EXTRA` 에 넣다가 `kcc_media`·`ftc_decisions_api`·`kcia_guideline`
    셋을 중복으로 적었고, 그 순간 **기존의 `masking`·`fragment_note` 가 통째로 사라졌다.**
    파이썬은 경고하지 않고 ruff 도 잡지 않는다 — 실행도 성공하고 게이트도 초록불이다.

    🚨 **이 저장소의 반복 결함과 같은 형태다** — 값이 두 칸 사이에서 조용히 사라지고,
    사라진 자리를 검사하는 것이 없다 (역검토 v1.3 부록). 그래서 여기에 검사를 둔다.
    """
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if name not in targets or not isinstance(node.value, ast.Dict):
            continue
        keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        assert not dupes, f"🚨 {path}:{name} 에 중복 키가 있다 — 앞의 값이 조용히 버려진다: {dupes}"
        return
    pytest.fail(f"{path} 에서 {name} dict 를 찾지 못했다 — 이름이 바뀌었으면 게이트도 고친다")


@pytest.mark.gate
def test_gated_소스는_승인_기록_없이는_열리지_않는다() -> None:
    """🚨 **수집기가 GATED 를 아예 보지 않고 있었다** (D-109 · 2026-09-02).

    탐침(`probe()`)이 *"승인 전 접근은 조건 위반"* 이라며 막던 조건을, 정작 **실제로
    받아 오는 `require()` 는 검사하지 않았다.** 승인 없이 받는 경로가 열려 있었던 것이고,
    **탐침을 만들지 않았으면 드러나지 않았을 자리**다.

    승인은 사람이 신청해 받아 오는 사실이라 사람이 적는다 — `robots_checked_at` 과 같은 종류다.
    🚨 그리고 **「신청했다」가 아니라 「승인됐다」의 날짜**여야 한다. 둘을 같은 칸에 적으면
    승인 대기 중인 소스가 승인된 것으로 읽히고, 그 오독은 약관 위반으로 끝난다.
    """
    from collect.registry import RegistryError, probe, require  # noqa: PLC0415

    srcs = _sources()
    gated = {k: v for k, v in srcs.items() if "GATED" in (v.get("constraints") or [])}
    assert gated, "GATED 소스가 없다 — 레지스트리가 바뀌었으면 이 게이트를 다시 본다"

    for key, src in gated.items():
        if src.get("approved_at"):
            assert src.get("approved_by"), (
                f"{key}: approved_at 만 있고 approved_by 가 없다 — "
                "누가 신청했는지가 남아야 한다 (AI Hub 는 내국인 한정 데이터셋이 있다)"
            )
            continue
        # 승인 기록이 없으면 탐침도 수집기도 거부해야 한다
        with pytest.raises(RegistryError, match="approved_at"):
            probe(key)
        opened = [u for u in sorted(VALID_USES) if (src.get("use") or {}).get(u) == "allow"]
        if opened:
            with pytest.raises(RegistryError):
                require(key, use=opened[0])


@pytest.mark.gate
def test_등록은_2인확인_게이트를_지나야_한다() -> None:
    """🚨 **탐침의 반대편**이다 — 게이트 23 이 「저장하지 않음」을 지켰다면 여기는 반대다 (D-109).

    AI Hub 처럼 **사람이 신청해 내려받는** 소스는 수집기가 가져오지 않는다. 그래서
    `manifest_append` · `mark_collected` 가 한 번도 안 불리고, **파일은 있는데 원장에는 없는**
    상태가 된다. `collect/ingest.py` 가 그 자리를 메운다.

    🚨 **사람이 손으로 받아 왔다는 사실이 2인 확인을 면제하지 않는다.** 오히려 수집기가
    돌지 않는 소스에서는 이 문이 **유일하게 남은 게이트**다. 그래서 `register` 는
    `registry.require()`(= `reviewed_by` 검사)로 시작해야 하고, 탐침의 느슨한 문
    `registry.probe()` 를 쓰면 안 된다.
    """
    src = (ROOT / "collect" / "ingest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "cmd_register" in fns, "등록 진입점이 없다"

    def calls(node: ast.AST) -> set[str]:
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                out.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        return out

    reg = calls(fns["cmd_register"])
    assert "require" in reg, (
        "🚨 register 가 registry.require() 로 시작하지 않는다 — "
        "reviewed_by 검사를 지나지 않고 원장에 올라간다 (규약 1 · D-66)"
    )
    assert "probe" not in reg, (
        "🚨 register 가 탐침의 느슨한 문(registry.probe)을 쓴다 — "
        "탐침은 reviewed_by 를 면제한다. 등록에 그 면제를 물려주면 게이트가 사라진다"
    )
    assert {"manifest_append", "mark_collected"} <= reg, (
        "등록이 원장에 남기지 않는다 — provenance 는 나중에 못 붙인다 (규약 3·7 · D-71)"
    )

    # 🚨 count 는 반대로 **아무것도 바꾸면 안 된다.** 2인 확인 전에도 도는 자리다.
    cnt = calls(fns["cmd_count"])
    forbidden = {"manifest_append", "mark_collected", "copy2", "move", "write_bytes", "write_text"}
    assert not (cnt & forbidden), (
        f"🚨 count 가 상태를 바꾼다 — 읽기 전용이어야 한다 (D-109): {sorted(cnt & forbidden)}"
    )


@pytest.mark.gate
def test_파생_소스는_원천보다_넓게_열리지_않는다() -> None:
    """🚨 파생물이 원천보다 넓게 열리면 **등급 체계가 파생 경로로 새어 나간다** (권소라 §6-8).

    `self_sanction_stat` 은 공정위 의결문 · 식약처 행정처분 API · **과징금 고시**에서 계산한
    자체 통계다. 원천이 셋인데 판정 근거는 **둘만 적고 있었고**, 원천 하나가 재판정으로
    닫혀도 파생물은 열린 채 남는다 — 아무도 그 연결을 보지 않기 때문이다.

    그래서 `derived_from` 을 **필드로** 두고 두 가지를 검사한다.
      ① **allow 집합의 포함** — 파생물이 연 용도는 **모든 원천이 함께 연** 것이어야 한다
      ② **서명 순서** — 파생물에 `reviewed_by` 가 있으면 원천에도 있어야 한다.
         🚨 원천을 확인하지 않은 사람이 파생물의 등급을 재현할 수는 없다 (D-66).
    """
    srcs = _sources()
    derived = {k: v for k, v in srcs.items() if v.get("derived_from")}
    assert derived, "파생 소스가 없다 — self_sanction_stat 가 사라졌으면 이 게이트를 다시 본다"

    for key, src in derived.items():
        origins = src.get("derived_from") or []
        for o in origins:
            assert o in srcs, f"{key}.derived_from 의 {o!r} 가 레지스트리에 없다"

        opened = {u for u in sorted(VALID_USES) if (src.get("use") or {}).get(u) == "allow"}
        for o in origins:
            o_open = {u for u in sorted(VALID_USES) if (srcs[o].get("use") or {}).get(u) == "allow"}
            assert opened <= o_open, (
                f"🚨 {key} 가 원천 {o} 보다 넓게 열려 있다 — {sorted(opened - o_open)}. "
                "파생물의 용도는 모든 원천이 함께 연 것이어야 한다 (D-71 · 규약 7)"
            )

        if src.get("reviewed_by"):
            unsigned = [o for o in origins if not srcs[o].get("reviewed_by")]
            assert not unsigned, (
                f"🚨 {key} 는 서명됐는데 원천 {unsigned} 가 미검토다 — "
                "파생물이 원천보다 먼저 서명되는 순서다. 원천을 확인하지 않은 사람이 "
                "파생물의 등급을 재현할 수 없다 (D-66 · 권소라 2인확인 §6-8)"
            )


# ══════════════════════════════════════════════════════════
# 키 — 유출은 언제나 「덮은 줄 알았던 경로」로 난다 (2026-09-02)
#
# 🚨 이 세 게이트는 사고 뒤에 생겼다. API 키가 대화창에 붙여넣어졌고, 원인을 따라가니
#    막힌 경로는 하나(.env 커밋)뿐이고 나머지가 열려 있었다.
#      ① 화면    — 확인하려고 .env 를 편집기로 열면 그때 화면에 뜬다
#      ② 셸 기록 — 값을 인자로 주면 ConsoleHost_history.txt 에 남는다
#      ③ 이름    — .env 는 덮여 있지만 .env.bak · .env.example 은 커밋된다
#    ①은 `launcher.py keys`(지문), ②는 getpass 가 맡고, 여기서는 ②③을 검사한다.
#    🚨 검사 대상은 **사람이 지킬 약속이 아니라 저장소의 상태**다 — 약속은 잊힌다.
# ══════════════════════════════════════════════════════════

# .env.example 에서 값을 가져도 되는 것 — 비밀이 아니라 기본값인 줄뿐이다.
EXAMPLE_DEFAULTS = {"DATABASE_URL", "MLFLOW_TRACKING_URI"}


@pytest.mark.gate
def test_env_example_에는_실제_값이_없다() -> None:
    """🚨 `.env` 는 gitignore 에 있고 `.env.example` 은 **커밋된다** — 한 글자 차이다.

    발급받은 키를 채울 때 파일을 잘못 여는 것은 드문 실수가 아니라 **예상되는 실수**다.
    두 파일이 나란히 있고 내용이 거의 같기 때문이다. gitleaks 훅이 마지막 그물이지만
    그것은 키 **모양**을 보고 걸러서, 모양이 평범한 키는 지나간다.
    여기서는 모양이 아니라 **자리**를 본다 — 예제에 값이 있으면 그 자체가 위반이다.
    """
    path = ROOT / ".env.example"
    assert path.exists(), ".env.example 이 없다 — 키 이름의 단일 출처다"

    filled = []
    for no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        if value.strip() and name not in EXAMPLE_DEFAULTS:
            filled.append(f"{no}행 {name}")

    assert not filled, (
        f"🚨 .env.example 에 값이 채워져 있다 — {filled}. 이 파일은 커밋된다.\n"
        f"   값은 .env 에 넣는다: uv run python launcher.py setkey <이름>\n"
        f"   기본값이라 값이 있어야 한다면 EXAMPLE_DEFAULTS 에 등재하고 왜인지 적는다."
    )


@pytest.mark.gate
def test_키_입력_경로가_값을_인자로_받지_않는다() -> None:
    """🚨 값이 인자로 지나가면 셸 기록에 남는다 — 마스킹 입력을 만든 뜻이 사라진다.

    `--key` 옵션 하나가 편의를 이유로 다시 생기는 것을 막는다. 「급하니까 이번만」이
    커밋되면 그 뒤로는 그것이 표준 사용법이 된다.

    검사는 **AST** 로 한다. 문자열로 찾으면 주석·docstring 이 걸려서, 사람이
    주석을 지워 게이트를 통과시키는 쪽으로 움직인다 (게이트 17 에서 겪은 그대로).
    """
    src = (ROOT / "collect" / "setkey.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "getpass" in names | attrs, (
        "🚨 collect/setkey.py 가 getpass 를 쓰지 않는다 — 입력이 화면에 뜬다"
    )

    # 런처 쪽 — setkey 명령의 인자가 「이름」 하나뿐이어야 한다
    ltree = ast.parse((ROOT / "launcher.py").read_text(encoding="utf-8"))
    fn = next(
        (n for n in ltree.body if isinstance(n, ast.FunctionDef) and n.name == "setkey"),
        None,
    )
    assert fn is not None, "launcher.py 에 setkey 명령이 없다"
    params = [a.arg for a in fn.args.args]
    assert params == ["name"], (
        f"🚨 launcher.setkey 의 인자가 {params} 다 — 이름 하나여야 한다.\n"
        "   값을 받는 인자가 생기면 PowerShell 기록에 키가 남는다."
    )


#: 🔴 **키가 들어앉는 이름들.** 편집기·direnv·손복사가 만든다 — 안에 든 것은 같은 키다.
#:    ⛔ 2026-09-09 이전에는 이 목록이 **docstring 에만** 있었고 검사는 `.env.*` 라는
#:       **패턴 문자열이 파일에 있는지**만 봤다. 그래서 `.env~` 가 목록에 적혀 있으면서도
#:       실제로는 안 걸리고 있었다 — `.env.*` 는 점 뒤에 글자가 와야 하는데 물결표 앞에는
#:       점이 없다. **적어 놓은 것과 검사한 것이 달랐다.**
LEAKY_ENV_NAMES = (".env", ".env~", ".envrc", ".env.bak", ".env.save", ".env.local")


@pytest.mark.gate
def test_설정파일이_이름을_바꿔_새지_않는다() -> None:
    """🚨 `.gitignore` 의 `.env` 한 줄로는 모자라다.

    편집기와 OS 가 `.env~` · `.env.bak` · `.env.save` · `.env.local` 을 만들고
    direnv 는 `.envrc` 를 만든다. 안에 든 것은 똑같은 키인데 이름이 달라서
    그 한 줄에 안 걸린다. **유출은 항상 「덮은 줄 알았던 이름」으로 난다.**

    🔴 **패턴 문자열이 아니라 동작을 본다** (2026-09-09).

    종전에는 `.gitignore` 안에 `.env.*` 라는 **글자가 있는지**만 봤다. 그러면
    「규칙이 무엇을 실제로 덮는가」를 아무도 안 보게 된다 — 실제로 `.env~` 가
    docstring 에 이름까지 적혀 있으면서 패턴 밖에 있었고, 이 게이트는 초록이었다.
    ★ **이제 `git check-ignore` 에게 직접 묻는다.** 규칙을 어떻게 쓰든 상관없다 —
      위 이름들이 막히고 `.env.example` 은 살아 있으면 통과다.

    🔴 **`--no-index` 가 없으면 뒤쪽 단언이 실패할 수 없다.** `git check-ignore` 는
       **추적 중인 파일을 「무시되지 않음」으로 답한다.** `.env.example` 은 추적 중이라
       `!.env.example` 을 통째로 지워도 답이 같다 — 규칙을 안 보고 인덱스를 본 것이다.
       ⛔ 이 게이트를 고치면서 실제로 그 상태로 한 번 통과시켰다. 반대 대조를 돌려 보고서야
       나왔다. **단언은 실패할 수 있어야 단언이다** (D-146 의 같은 모양).

    🚨 그리고 규칙이 맞아도 **이미 추적 중이면 gitignore 는 아무것도 못 한다** — 아래.
       그것은 인덱스를 봐야 하는 검사라 `git ls-files` 로 따로 묻는다.
    """
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", *LEAKY_ENV_NAMES, ".env.example"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    # 종료코드 0(전부 무시) · 1(일부만) 둘 다 정상 출력이다. 128 은 git 이 없는 것.
    if ignored.returncode == 128:  # pragma: no cover — git 없는 환경
        pytest.skip("git 이 없다 — 무시 규칙의 동작을 확인할 수 없다")
    got = {ln.strip() for ln in ignored.stdout.splitlines() if ln.strip()}
    missing = [n for n in LEAKY_ENV_NAMES if n not in got]
    assert not missing, (
        f"🚨 `.gitignore` 가 이 이름들을 안 덮는다 — {missing}\n"
        "   키가 그대로 들어 있는 파일들이다. `.env*` 한 줄이면 전부 덮인다.\n"
        "   ⛔ 이름을 주석에 적는 것과 규칙이 그것을 덮는 것은 다른 일이다."
    )
    assert ".env.example" not in got, (
        "🚨 `.env.example` 까지 무시된다 — `!.env.example` 이 없거나 앞에 있다.\n"
        "   gitignore 는 **뒤에 오는 규칙이 이긴다.** 예제가 커밋되지 않으면 "
        "팀원이 키 이름을 알 수 없다."
    )

    # 실제 추적 상태 — 규칙이 맞아도 이미 추적 중이면 gitignore 는 아무것도 못 한다
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", ".env", ".env.*"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        tracked = {p for p in proc.stdout.split("\0") if p and p != ".env.example"}
        assert not tracked, (
            f"🚨 키 파일이 이미 git 에 추적되고 있다 — {sorted(tracked)}. "
            "gitignore 는 **추적되지 않는 파일**에만 듣는다. "
            "`git rm --cached <파일>` 로 먼저 떼어 내고, 이미 push 했다면 키를 재발급한다."
        )


@pytest.mark.gate
def test_오류_메시지가_키를_그대로_찍지_않는다() -> None:
    """🚨 D-111 이 센 경로는 셋이었다 — 화면 입력 · 셸 기록 · 키 이름. **넷째가 있었다.**

    2026-09-02, `cosmetic_*` 두 건이 403 으로 실패했고 `FetchError` 가 요청 URL 을
    통째로 찍어 `serviceKey` 값이 터미널·스크롤백·대화 기록에 남았다. 키를 재발급했다.

    앞의 셋과 성질이 다르다 — **사람이 실수해야 새는 것이 아니라 코드가 정상 동작할 때
    샌다.** 실패할 때마다 샌다. 그리고 `probe.py` 는 이 메시지를 `실측_<날짜>.md` 와
    `build/probe_results.json` 에 적고 **그것이 커밋된다.** 터미널은 닫으면 사라지지만
    커밋은 남는다.

    두 겹으로 본다.
      ① 구조 — `raise FetchError(...)` 안에 **가공되지 않은 `url`** 이 들어가지 않는다 (AST)
      ② 동작 — 실제로 가려지는가. 구조만 보면 `redact` 가 빈 껍데기여도 통과한다
    """
    src = (ROOT / "collect" / "http.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # ── ① 구조 — raise FetchError(f"{url} …") 를 막는다
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        callee = node.exc.func
        if getattr(callee, "id", getattr(callee, "attr", None)) != "FetchError":
            continue
        for sub in ast.walk(node.exc):
            # f-string 안의 `{url}` 은 FormattedValue 의 값이 Name 으로 온다
            if isinstance(sub, ast.FormattedValue) and isinstance(sub.value, ast.Name):
                assert sub.value.id != "url", (
                    "🚨 collect/http.py 의 FetchError 가 url 을 그대로 찍는다.\n"
                    "   키는 쿼리(serviceKey·OC)에도, **경로**(식품안전나라 /api/<키>/…)에도 있다.\n"
                    "   `redact(url)` 을 거쳐야 한다 — 예외를 만드는 이 한 곳을 막으면\n"
                    "   그것을 받아쓰는 probe.py 의 실측 문서·리포트까지 함께 막힌다."
                )

    # ── ② 동작 — 세 겹이 실제로 도는가
    from collect import http  # noqa: PLC0415

    http.register_secret("게이트_시험키", "ZZtestSECRET0123456789+/=")

    누출 = "ZZtestSECRET"
    검사 = [
        # 값으로 — 원문 · 인코딩 · 🚨 이중 인코딩(2026-09-02 실제로 나온 형태)
        "https://apis.data.go.kr/a/b?serviceKey=ZZtestSECRET0123456789%2B%2F%3D&pageNo=1",
        "https://apis.data.go.kr/a/b?serviceKey=ZZtestSECRET0123456789%252B%252F%253D&pageNo=1",
        "https://apis.data.go.kr/a/b?serviceKey=ZZtestSECRET0123456789+/=&pageNo=1",
        # 🚨 경로에 키가 있는 규약 — 쿼리만 가리는 마스킹은 이쪽을 못 막는다
        "http://openapi.foodsafetykorea.go.kr/api/ZZtestSECRET0123456789/I0470/json/1/100",
    ]
    for url in 검사:
        가림 = http.redact(url)
        assert 누출 not in 가림, f"🚨 키가 가려지지 않는다 — {url[:60]}… → {가림}"

    # 이름 그물 — 등록되지 않은 키(손으로 만든 URL)도 잡는다
    assert "hong1234" not in http.redact(
        "https://www.law.go.kr/DRF/lawSearch.do?OC=hong1234&target=ftc&type=XML"
    ), "🚨 등록되지 않은 키를 파라미터 이름으로도 못 잡는다"

    # 🚨 과잉 마스킹도 결함이다 — 오류 메시지를 읽을 수 없으면 고칠 수 없다
    정상 = "http://openapi.foodsafetykorea.go.kr/api/sample/I-0040/json/1/5"
    assert http.redact(정상) == 정상, f"🚨 키가 아닌 곳을 가렸다 — {http.redact(정상)}"


@pytest.mark.gate
def test_키를_읽는_곳이_가릴_것을_등록한다() -> None:
    """🚨 가리기는 **값으로** 해야 강하다 — 쿼리든 경로든, 인코딩이 어떻든 잡힌다.

    그러려면 누군가 값을 알려 줘야 하는데, 키를 손에 쥐는 곳은 `env.get()` **하나뿐**이다
    (D-51 이래로 `.env` 를 읽는 유일한 자리). 그 자리가 등록을 빠뜨리면 ①이 통째로
    꺼지고, 남는 것은 파라미터 이름 그물뿐이다 — 이름을 모르는 API 에서는 그물이 없다.

    🚨 의존 방향에 주의한다. `http` 가 `env` 를 부르면 순환이 된다. 반대로 뒤집혀 있어야 한다.
    """
    tree = ast.parse((ROOT / "collect" / "env.py").read_text(encoding="utf-8"))

    fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get"),
        None,
    )
    assert fn is not None, "collect/env.py 에 get() 이 없다"

    부름 = {
        getattr(n.func, "attr", getattr(n.func, "id", None))
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
    }
    assert "register_secret" in 부름, (
        "🚨 collect/env.py 의 get() 이 http.register_secret() 을 부르지 않는다.\n"
        "   키를 읽고도 「가릴 것」으로 등록하지 않으면 오류 메시지에 값이 그대로 남는다."
    )

    # 순환 방지 — http 는 env 를 import 하지 않는다
    htree = ast.parse((ROOT / "collect" / "http.py").read_text(encoding="utf-8"))
    수입 = {
        alias.name for n in ast.walk(htree) if isinstance(n, ast.ImportFrom) for alias in n.names
    } | {n.module or "" for n in ast.walk(htree) if isinstance(n, ast.ImportFrom)}
    assert "env" not in 수입, (
        "🚨 collect/http.py 가 env 를 import 한다 — 순환이다. 등록은 env → http 방향으로만 흐른다."
    )


# ══════════════════════════════════════════════════════════
# 🚨 data_sources.yaml 은 **생성물**이다 — 손으로 고치면 다음 생성 때 사라진다
#
# ⛔ 2026-09-09 에 실제로 사라졌다. `mfds_press` 의 마스킹 정책 10줄을
#    `data_sources.yaml` 에 직접 써서 커밋했고(13ddb4f), 세 시간 뒤 다른 작업 중
#    `gen_registry.py` 가 한 번 더 돌면서 **통째로 지워진 채 커밋됐다**(1292407).
#    커밋 메시지 어디에도 그 말이 없다. 조용히 사라졌다.
#    `reviewed_at: 2026-09-09` 도 `2026-09-02` 로 되돌아갔다 — 2인 확인의 날짜다.
#
#    🚨 `collect/registry.py` 와 `gen_registry.py` 둘 다 「생성물이니 손으로 고치지
#       말라」고 **주석으로** 적어 두고 있었다. 주석은 게이트가 못 읽는다 (D-89).
#       아래 둘이 그 주석을 검사로 바꾼 것이다.
# ══════════════════════════════════════════════════════════

_SIGN_FIELDS = ("decided_by", "decided_at", "reviewed_by", "reviewed_at")


@pytest.mark.gate
def test_레지스트리_서명은_2인확인_원장과_같다() -> None:
    """서명 필드의 단일 출처는 `scripts/registry_review.yaml` 이다 (D-54 · D-99).

    🚨 `collected_at` 은 뺀다 — `mark_collected()` 가 원장에만 찍고 생성물은
       다음 생성 때 따라오므로, 수집 직후에는 정상적으로 어긋나 있다.
       서명 넷은 그런 시차가 없다. 어긋나면 손으로 고친 것이다.
    """
    import yaml

    ledger = yaml.safe_load((ROOT / "scripts/registry_review.yaml").read_text(encoding="utf-8"))
    sources = _registry().get("sources") or {}

    bad: list[str] = []
    for key, spec in sources.items():
        if not isinstance(spec, dict):
            continue  # `blocked` 처럼 소스가 아닌 항목이 섞여 있다
        entry = (ledger or {}).get(key)
        if not isinstance(entry, dict):
            continue  # 원장에 없는 항목(꼬리말에 손으로 쓴 소스)은 이 검사 밖이다
        for f in _SIGN_FIELDS:
            got, want = spec.get(f), entry.get(f)
            if got != want:
                bad.append(f"{key}.{f}: 생성물 {got!r} ≠ 원장 {want!r}")
    assert not bad, (
        "data_sources.yaml 이 2인 확인 원장과 다르다 — 생성물을 손으로 고쳤다.\n"
        "  고치는 법 — scripts/registry_review.yaml 에 적고 "
        "`python scripts/gen_registry.py` 를 다시 돌린다.\n  " + "\n  ".join(bad)
    )


@pytest.mark.gate
def test_생성물에만_있는_문언이_없다() -> None:
    """`masking`·`attribution`·`license` 의 단일 출처는 `scripts/gen_registry.py` 다.

    🚨 서명 게이트만으로는 부족하다. 2026-09-09 에 사라진 것은 `reviewed_at`(원장에 있다)과
       `masking`(원장에 없다) **둘**이었다. masking 만 손으로 넣으면 위 게이트를 지난다.

    🚨 공백을 지우고 비교한다 — 생성기 안에서는 한 문장이 여러 줄로 쪼개져 있고
       (`>-` 접힘 · 암시적 문자열 이어붙이기), 포매터가 그 줄을 다시 나눌 수 있다.
       줄바꿈 위치가 검사 결과를 바꾸면 그건 문언 검사가 아니라 서식 검사다.
    """
    gen = "".join((ROOT / "scripts/gen_registry.py").read_text(encoding="utf-8").split())
    sources = _registry().get("sources") or {}

    bad: list[str] = []
    for key, spec in sources.items():
        if not isinstance(spec, dict):
            continue
        for field in ("masking", "attribution", "license"):
            wording = str(spec.get(field) or "").strip()
            if not wording:
                continue
            head = "".join(wording.split())[:24]
            if head not in gen:
                bad.append(f"{key}.{field}: 「{wording[:28]}…」 가 gen_registry.py 에 없다")
    assert not bad, (
        "판정 문언이 생성물에만 있다 — 다음 생성 때 사라진다.\n"
        "  고치는 법 — scripts/gen_registry.py 의 EXTRA · ATTRIB 에 넣고 다시 생성한다.\n  "
        + "\n  ".join(bad)
    )
