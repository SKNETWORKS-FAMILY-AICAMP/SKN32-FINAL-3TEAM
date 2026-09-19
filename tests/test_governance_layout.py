"""거버넌스 게이트 — 저장소 구조 자체를 검사한다 (D-19 · D-51 · D-89).

🚨 doctor 와 중복이 아니다. doctor 는 "내 기기" 를 보고,
   이 테스트는 "저장소" 를 본다. CI 와 pre-push 에서 도는 쪽은 이쪽이다.

판단 기준 (D-89): 기기마다 답이 다르면 doctor, 저장소에서 답이 하나면 pytest.
"""

from __future__ import annotations

import ast
import json
import os
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


# 🚨 **트리를 통째로 훑지 않는다** (2026-09-09).
#    ⛔ `ROOT.rglob("*.py")` 는 걸러내기 **전에** `.venv` 를 다 열거한다. 2026-09-09 에
#       `sentence-transformers`(torch·transformers)를 넣자 `.venv` 의 .py 가 수만 개가 됐고,
#       게이트 하나가 **3분을 넘겨** 전체 스위트가 못 끝났다. 건너뛰는 조건은 있었지만
#       그 조건이 도는 시점이 이미 늦었다 — **걷지 않는 것과 걷고 버리는 것은 다르다.**
_PRUNE = {
    ".venv",
    ".git",
    "build",
    "dist",
    "data",
    "__pycache__",
    "node_modules",
    ".ruff_cache",
    ".pytest_cache",
    "Claude outputs",
    ".uv",
}


def _py_files(root: Path) -> list[Path]:
    """`root` 아래 .py 를 낸다. 위 디렉터리는 **들어가지 않는다.**"""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE]
        out += [Path(dirpath) / f for f in filenames if f.endswith(".py")]
    return sorted(out)


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

#: 🚨 `data/raw` 를 **정당하게** 만지는 예외. 이름과 이유를 여기 적는다 (2026-09-10).
#:    ⛔ 종전에는 이 목록이 없었고, 대신 검사가 뚫려서 조용히 지나가고 있었다 —
#:       `scripts/doctor.py:83` 이 `ROOT / "data" / "raw"` 로 **분절해** 써서
#:       `"data/raw" in code` 를 통과했다. 예외가 필요하면 목록으로 두지, 검사를 약하게 두지 않는다.
RAW_EXCEPTIONS = {
    # 원장 ↔ 디스크 대조가 이 도구의 일 자체다. 읽기만 하고 소비 경로가 아니다 (D-89).
    Path("scripts/doctor.py"),
    # 게이트 자신과, raw 를 다루는 코드를 검사하는 테스트들.
    Path("tests/test_governance_layout.py"),
    Path("tests/test_sanctions_scan.py"),
    Path("tests/test_store_edition.py"),
    Path("tests/test_store_read_editions.py"),
    # 🔄 2026-09-18 — 판 채택은 `data/raw` 안에서 판을 원본 자리로 올리는 일 **그 자체**라
    #    그 경로를 들지 않고는 검사할 수 없다 (`test_store_edition.py` 와 같은 자리).
    #    ⛔ 이 검사를 약하게 하지 않는다 — 경로를 안 드는 꼴로 테스트를 고치면
    #       2026-09-18 사고(소스 id 폴더에 넣어 334노드 소실)를 막는 검사가 사라진다 (D-162).
    Path("tests/test_adopt.py"),
    # 🔄 2026-09-19 (D-247) — 사본 받기가 옛 판을 덮기 전에 **원문 폴더가 있는지만** 본다.
    #    raw 가 있는 기기에서 덮어쓰면 그것이 클론 B(정본)일 수 있어 한 번 묻는다. 열지 않는다.
    #    ⛔ `store.RAW` 를 빌려 써서 이 검사를 조용히 지나가지 않는다 — 예외는 목록으로 둔다.
    Path("scripts/data_store.py"),
}


def _path_segments(tree: ast.AST) -> set[tuple[str, ...]]:
    """`ROOT / "data" / "raw"` 같은 **분절 경로**를 조각 튜플로 모은다 (2026-09-10).

    ⛔ 문자열 `"data/raw"` 만 찾으면 분절 표기가 통과한다. 실측 — `scripts/doctor.py` 가
       그렇게 게이트를 지나고 있었고, 바로 그 게이트가 지키려던 규칙을 어기고 있었다.
    ★ `pathlib` 의 `/` 는 `BinOp(Div)` 다. 사슬을 펴서 상수 조각만 이어 붙인다.
    """
    got: set[tuple[str, ...]] = set()

    def flatten(node: ast.AST) -> list[str | None]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return flatten(node.left) + flatten(node.right)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        return [None]

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = flatten(node)
            for i in range(len(parts) - 1):
                if parts[i] and parts[i + 1]:
                    got.add((parts[i], parts[i + 1]))
    return got


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
    for path in _py_files(ROOT):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        # 🚨 `Claude outputs/` 는 Claude 앱이 떨어뜨리는 사본이다 — `.gitignore` 에 이미 있다.
        #    레포 소스가 아니라서 게이트 대상도 아니다 (2026-09-06 에 여기 걸렸다).
        if parts[0] in {".venv", "build", "dist", ".git", "Claude outputs"}:
            continue
        if parts[0] in RAW_READERS or rel in RAW_EXCEPTIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "raw" not in text:
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
        # 🚨 **두 표기를 다 본다** — 한 덩어리 문자열과 `/` 로 분절한 것 (2026-09-10).
        if "data/raw" in code or "data\\raw" in code or ("data", "raw") in _path_segments(tree):
            offenders.append(str(rel))

    assert not offenders, (
        "data/raw/ 를 수집·전처리 밖에서 참조한다 — 소비 경로는 등급 디렉터리와 "
        f"derived/ 만 읽는다 (D-92): {offenders}\n"
        "  🚨 정당한 예외면 `RAW_EXCEPTIONS` 에 **이유와 함께** 적는다 — 검사를 약하게 두지 않는다."
    )


@pytest.mark.gate
def test_반대_대조_분절_경로도_잡힌다() -> None:
    """🚨 위 게이트가 **실패할 수 있는지** 스스로 보인다 (D-170).

    ⛔ 2026-09-10 까지 `"data/raw" in code` 뿐이라 `ROOT / "data" / "raw"` 가 통과했다.
       게이트가 지키려던 규칙을 게이트 대상이 어기고 있었는데 초록불이었다.
    """
    joined = ast.parse('p = ROOT / "data/raw" / "x"')
    split_ = ast.parse('p = ROOT / "data" / "raw" / "x"')
    innocent = ast.parse('p = ROOT / "data" / "derived"')

    assert "data/raw" in ast.unparse(joined)
    assert "data/raw" not in ast.unparse(split_), "이 표기가 종전 검사를 지나갔다"
    assert ("data", "raw") in _path_segments(split_)
    assert ("data", "raw") not in _path_segments(innocent)


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
    for path in _py_files(ROOT / "preprocess"):
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
    # 🚨 **여기도 AST 로 본다** (2026-09-10). ⛔ 종전 두 줄은 `src`(원문 텍스트)를 봤다 —
    #    바로 위 주석이 「문자열이 아니라 AST 로 본다」고 선언해 놓고 **두 줄 뒤에 어겼다.**
    #    주석에 `# ROOT / "docs` 라고 적어 두면 탐침이 `data/` 에 써도 통과한다.
    #    ★ 지킬 것은 「그 문장이 있다」가 아니라 **「data/ 로 나가는 경로가 없다」**이다 (D-19).
    roots = {a for a, _ in _path_segments(tree)} | {b for _, b in _path_segments(tree)}
    assert "data" not in roots, (
        f"🚨 탐침이 data/ 아래 경로를 만든다 — 탐침은 저장하지 않는다 (D-109 · D-19): {sorted(roots)}"
    )
    assert {"docs", "build"} & roots, (
        f"🚨 탐침이 docs/·build/ 로 나가는 경로를 안 만든다 — 리포트를 어디에 쓰나? {sorted(roots)}"
    )

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
# 🔄 2026-09-10 — 추적 끄기 둘을 등재한다. 비밀이 아니라 **꺼져 있어야 하는 기본값**이라
#    값이 보여야 뜻이 산다 (D-43). 아래 두 게이트가 이 값을 실제로 검사한다.
# 🔄 2026-09-12 밤 (D-213) — `COPYLANE_EDITION` 을 등재한다. 비밀이 아니라 **어느 판으로
#    뜨는가**이고, 기본값 `local` 이 **보여야** 팀원이 무엇을 바꾸는지 안다.
#    🚨 이 게이트가 실제로 잡았다 — 값을 채우고 여기 등재를 잊었더니 낙방했다.
#       ⛔ `COPYLANE_SESSION_SECRET` 은 **여기 없다.** 비어 있어야 하고, 값이 생기면
#          그것은 비밀이므로 이 게이트가 잡아야 한다.
EXAMPLE_DEFAULTS = {
    "DATABASE_URL",
    "MLFLOW_TRACKING_URI",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "COPYLANE_EDITION",
    # 🔄 2026-09-19 (D-247) — 기기 역할. 비밀이 아니라 **이 기기가 받는 쪽인가**이고,
    #    기본값 `replica` 가 보여야 새 기기(팀원)가 저절로 받는 쪽이 된다.
    #    ⛔ `DATA_STORE` 는 **여기 없다** — 경로는 기기마다 달라 예제에 값이 있으면 안 된다.
    "DATA_ROLE",
}


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


#: 🆕 2026-09-12 밤 — **배포 담당이 곧 받는 것들** (D-208 · D-211 · 보안점검 P0-2).
#:    ⛔ `.ppk` 를 빠뜨리지 않는다 — 배포계획이 **MobaXterm** 을 쓰기로 했고 그것이 쓰는 형식이다.
#:       「pem 만 막으면 된다」가 정확히 `.env~` 때 밟은 「덮은 줄 알았던 이름」이다.
#: 🚨 로그도 여기 넣는다 — `app/logging_conf.py` 의 마스킹은 **그물이지 벽이 아니다** (D-210).
LEAKY_SECRET_NAMES = (
    "deploy.pem",
    "key.ppk",
    "cert.p12",
    "cert.pfx",
    "id_rsa",
    "id_ed25519",
    "credentials",
    ".aws/credentials",
    "app.log",
    "logs/uvicorn.log",
)

#: 🔴 **반대 방향** — 이것들은 살아 있어야 한다. 무시 규칙이 넓어지면 여기서 걸린다.
MUST_STAY = (
    ".env.example",
    "README.md",
    "app/templates/base.html",
    "app/static/vendor/htmx.min.js",
    "scripts/registry_head.yaml",
    "data/manifest.jsonl",
)


@pytest.mark.gate
def test_열쇠와_로그가_이름을_바꿔_새지_않는다() -> None:
    """🚨 `.env` 만 막으면 되는 시기는 끝났다 (2026-09-12 밤).

    배포 담당이 생기면서 **`.pem`·`.ppk`·IAM 자격증명**이 기기에 내려온다. 배포계획 §3-1 은
    *".pem 을 저장소 폴더 안에 두지 않습니다"* 라고 **사람에게** 지시하는데, D-117 이 적은 대로
    **기록으로는 안 막히고 코드로만 막힌다.** 무시 규칙 한 줄이 그 지시보다 세다.

    🔴 **패턴 문자열이 아니라 동작을 본다** — `.env~` 때 배운 그대로다. 규칙을 어떻게 쓰든
       상관없다. 위 이름들이 막히고 `MUST_STAY` 가 살아 있으면 통과다.
    ⛔ **반대 방향을 같이 본다.** 무시를 넓히다 `app/static/vendor/*.js`(받아서 커밋한다)나
       `data/manifest.jsonl`(유일하게 커밋되는 원장)을 삼키면 여기서 걸린다.
    """
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", *LEAKY_SECRET_NAMES, *MUST_STAY],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 128:  # pragma: no cover — git 없는 환경
        pytest.skip("git 이 없다 — 무시 규칙의 동작을 확인할 수 없다")
    got = {ln.strip().strip('"') for ln in proc.stdout.splitlines() if ln.strip()}
    missing = [n for n in LEAKY_SECRET_NAMES if n not in got]
    assert not missing, (
        f"🚨 `.gitignore` 가 이 이름들을 안 덮는다 — {missing}\n"
        "   열쇠·자격증명·로그다. 한 번 push 되면 되돌릴 수 없고 키는 재발급이다.\n"
        "   ⛔ 이름을 배포계획에 적는 것과 규칙이 그것을 덮는 것은 다른 일이다 (D-117)."
    )
    swallowed = [n for n in MUST_STAY if n in got]
    assert not swallowed, (
        f"🔴 커밋돼야 하는 것이 무시된다 — {swallowed}\n"
        "   무시 규칙을 넓히다 삼킨 것이다. gitignore 는 **뒤에 오는 규칙이 이긴다**."
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


# ══════════════════════════════════════════════════════════
# 🔴 「지금은 안 받는다」를 코드가 지키는가 (2026-09-09 · D-72)
#
# ⛔ `require()` 가 `status` 를 **아예 안 보고 있었다.** `manual` 검사는 `probe()` 에만 있어,
#    탐침은 막고 **실제로 받아 오는 쪽은 안 막는** 모양이었다.
#    D-109 에서 GATED 로 똑같은 일이 있었고 그때 GATED 만 옮겨 오고 status 는 두었다.
#    **같은 함정을 두 번째로 밟았다.** 팀장 지적으로 드러났다 —
#    「거버넌스에 위배되면 수집하지 않기로 한 것들은 수집 안 해야 하잖아」.
# ══════════════════════════════════════════════════════════


@pytest.mark.gate
def test_hold_과_manual_은_수집이_막힌다() -> None:
    """적어 두기만 하고 아무것도 안 막으면 그건 보류가 아니라 표시다."""
    from collect import registry

    sources = _registry().get("sources") or {}
    checked = {"hold": 0, "manual": 0}
    for key, spec in sources.items():
        if not isinstance(spec, dict):
            continue
        st = spec.get("status")
        if st not in ("hold", "manual"):
            continue
        for use, verdict in (spec.get("use") or {}).items():
            if verdict != "allow":
                continue  # 용도가 이미 닫혀 있으면 이 게이트가 볼 자리가 아니다
            # 🚨 **막히기만 하면 되는 게 아니다 — 다른 이유로 막히면 이 검사가 아니다.**
            #    `aihub_71843` 은 hold 이면서 GATED 라 승인 검사가 먼저 걸린다.
            #    순서는 「되돌릴 수 없는 것부터」이므로 그게 맞다 — 여기서는 세지 않는다.
            with pytest.raises(registry.RegistryError) as err:
                registry.require(key, use=use)
            if st in str(err.value):
                checked[st] += 1
    # 🚨 **셀 것이 없으면 이 검사는 아무것도 안 한 것이다** (D-170).
    #    `hold`/`manual` 인데 용도가 열린 소스가 하나도 없으면 여기서 알린다.
    # 🔴 **합산하면 한쪽이 0 이어도 초록이다** (2026-09-10 정정).
    #    ⛔ 실측 — hold 6건 · manual **1건**(`mfds_cosmetic_sanction`)이다.
    #       그 하나가 재분류되거나 `require()` 의 manual 분기가 사라져도
    #       hold 6건이 합계를 채워 이 게이트가 계속 초록을 냈다.
    zero = [st for st in ("hold", "manual") if checked[st] == 0]
    assert not zero, (
        f"{zero} 를 **하나도 세지 않았다** — 그 status 로 막히는 소스가 없거나 "
        "`require()` 의 그 분기가 사라졌다. 합산으로 가리지 않는다 (D-170).\n"
        f"  실제로 센 것 — {dict(checked)}"
    )


# ══════════════════════════════════════════════════════════
# 🔴 생성기가 pre-commit 훅과 싸우지 않는가 (2026-09-09)
#
# ⛔ `scripts/data_status.py` 를 만들자마자 `end-of-file-fixer` 가 매번 그 파일을 고쳐
#    커밋이 중단됐다. 생성기가 끝에 빈 줄을 하나 더 붙였기 때문이다.
#    🚨 **한 번 고치면 끝나는 문제가 아니다** — 생성기가 다섯이고 앞으로 더 는다.
#       다음 사람이 새 생성기를 쓰면 같은 자리를 밟고, 아무도 알려주지 않는다.
#    🚨 그리고 이 싸움이 반복되면 **둘 중 하나를 끄게 된다** — 훅을 끄면 서식이 무너지고,
#       생성기를 손으로 고치면 그게 곧 「생성물을 손으로 고친다」다 (D-90 이 막는 것).
#
# 그래서 규칙을 검사로 옮긴다. 훅을 실제로 돌리지 않고 **훅이 요구하는 모양**만 본다 —
# 훅을 돌리려면 네트워크와 설치가 필요하고, 그러면 이 검사가 CI 밖에서 안 돈다.
# ══════════════════════════════════════════════════════════

#: 생성기가 쓰는 파일들. 🚨 **새 생성기를 만들면 여기 넣는다.**
#   여기 없으면 이 검사는 그 파일을 안 본다 — 목록이 낡으면 검사도 낡는다.
GENERATED = (
    "data_sources.yaml",  # scripts/gen_registry.py
    "docs/03_데이터/_matrix/sources.json",  # scripts/build_matrix.py
    "docs/03_데이터/판정매트릭스.html",  # scripts/build_matrix.py
    "scripts/registry_rationale.yaml",  # scripts/extract_rationale.py
    "docs/03_데이터/데이터현황판.md",  # scripts/data_status.py
    "docs/03_데이터/S0-14_2인확인_검토표.md",  # scripts/review_sheet.py
)


@pytest.mark.gate
def test_생성물이_훅의_고정점이다() -> None:
    """생성기 출력이 pre-commit 을 그대로 지나야 한다.

    보는 것은 둘이다 — 이 둘이 2026-09-09 에 실제로 물었다.
      `end-of-file-fixer`  파일은 개행 **하나**로 끝난다
      `trailing-whitespace` 줄 끝에 공백이 없다
        🚨 `.md` 는 예외가 있다 — 훅이 `--markdown-linebreak-ext=md` 로 돌아
           **공백 두 개**는 줄바꿈이라 남긴다. 그래서 md 는 「둘이 아닌 공백」만 잡는다.
    """
    bad: list[str] = []
    for rel in GENERATED:
        path = ROOT / rel
        if not path.exists():
            continue  # 아직 안 만든 생성물은 이 검사의 자리가 아니다
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n") or text.endswith("\n\n"):
            bad.append(
                f"{rel}: 끝이 개행 하나가 아니다 ({text[-6:]!r}) — end-of-file-fixer 가 고친다"
            )
        for i, line in enumerate(text.split("\n"), 1):
            stripped = line.rstrip()
            if line == stripped:
                continue
            tail = line[len(stripped) :]
            if path.suffix == ".md" and tail == "  ":
                continue  # 마크다운 줄바꿈 — 훅이 남긴다
            bad.append(f"{rel}:{i}: 줄 끝 공백 {tail!r} — trailing-whitespace 가 고친다")
            break
    assert not bad, (
        "생성물이 pre-commit 훅과 싸운다 — 돌릴 때마다 훅이 고쳐 커밋이 중단된다.\n"
        "  🚨 훅을 끄지 말고 **생성기가 훅의 모양을 지키게** 고친다 (D-90 — 생성물을 "
        "손으로 고치지 않는다).\n  " + "\n  ".join(bad)
    )


#: 텍스트를 쓰는 곳을 훑는 자리. 🚨 `wb`(바이너리)와 `newline=""`(csv 모듈이 요구한다)는 제외한다.
_TEXT_WRITE_MODES = {"w", "wt", "a", "at", "x", "xt", "w+", "r+", "a+"}


def _text_writers(path: Path) -> list[tuple[int, str]]:
    """`(줄번호, 호출이름)` — 개행을 고정하지 않은 텍스트 쓰기 자리."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover — 문법이 깨졌으면 다른 게이트가 잡는다
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name == "write_text":
            pass
        elif name == "open":
            # 🔴 2026-09-19 — `open(path, mode)` 은 모드가 **둘째** 인자지만 `Path.open(mode)` 는 **첫째**다.
            #    ⛔ 둘째만 봐서 `MANIFEST.open("a", encoding=…)` 가 「읽기」로 보였고, 수집 원장이
            #       Windows 에서 CRLF 로 5,148줄 붙는 동안 이 게이트는 초록이었다.
            pos = node.args[0:1] if isinstance(fn, ast.Attribute) else node.args[1:2]
            mode = next(
                (
                    a.value
                    for a in pos + [k.value for k in node.keywords if k.arg == "mode"]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ),
                "r",
            )
            if mode not in _TEXT_WRITE_MODES:
                continue
        else:
            continue
        kw = {k.arg for k in node.keywords}
        if "encoding" in kw and "newline" not in kw:
            out.append((node.lineno, name))
    return out


@pytest.mark.gate
def test_텍스트를_쓰는_곳은_개행을_고정한다() -> None:
    """🔴 **파이썬은 Windows 에서 `\n` 을 `\r\n` 으로 바꿔 쓴다** (2026-09-17 실측).

    ⛔ `.gitattributes` 가 `* text=auto eol=lf` 인데 생성기가 CRLF 로 써서 —
       · 추적되는 생성물은 `git add` 마다 **「CRLF will be replaced by LF」 경고**가 나고
         재생성할 때마다 **내용이 같은데도 modified 로 뜬다**
       · 추적 안 되는 `data/**` 는 **클론마다 바이트가 다르다.**
         `evalset_by_statute.jsonl` 이 클론 B 에서 **869,426 B**, 리눅스에서 **867,592 B**
         (차이 1,834 = 줄 수). **되받아 바이트로 대조하는 절차(D-149)가 통째로 무의미해진다.**

    ★ 그래서 텍스트를 쓰는 모든 자리가 `newline=` 을 **명시**한다.
      🚨 `newline=""` 도 명시다 — csv 모듈이 그것을 요구한다. 여기서 막는 것은 **안 적은 것**이다.
    """
    bad = [
        f"{p.relative_to(ROOT).as_posix()}:{line} — {name}(…) 에 newline= 이 없다"
        for d in ("scripts", "preprocess", "collect", "app", "db")
        if (ROOT / d).is_dir()
        for p in sorted((ROOT / d).rglob("*.py"))
        for line, name in _text_writers(p)
    ]
    assert not bad, (
        "생성물의 개행이 기기마다 갈린다 — Windows 에서 CRLF 로 쓰인다.\n"
        '  ★ 고치는 법: `encoding="utf-8"` 옆에 `newline="\\n"` 을 붙인다.\n  ' + "\n  ".join(bad)
    )


@pytest.mark.gate
def test_생성물이_CRLF_로_쓰여_있지_않다() -> None:
    """🚨 **바이트로 읽는다.** `read_text()` 는 universal newlines 라 CRLF 를 못 본다 —

    앞 게이트(`test_생성물이_훅의_고정점이다`)가 CRLF 를 지나보낸 이유가 그것이다.
    """
    crlf = b"\r\n"
    bad = []
    for rel in GENERATED:
        path = ROOT / rel
        if not path.exists():
            continue
        n = path.read_bytes().count(crlf)
        if n:
            bad.append(f"{rel}: CRLF {n:,}줄")
    assert not bad, (
        '생성물이 CRLF 로 쓰여 있다 — 생성기가 newline="\\n" 을 안 걸었거나, '
        "손으로 고친 뒤 편집기가 바꿨다 (D-90 · D-92).\n  " + "\n  ".join(bad)
    )


# ══════════════════════════════════════════════════════════
# 🔴 **수집기 디스패치** — 산문이 아니라 표가 판정한다 (2026-09-10 · D-179)
# ══════════════════════════════════════════════════════════


@pytest.mark.gate
def test_수집하기로_한_소스는_받는_경로가_정해져_있다() -> None:
    """🔴 `status: collect` 는 「수집기가 실행한다」는 뜻이다 — 그런데 아무도 안 물었다.

    ⛔ 2026-09-10 실측 — `status: collect` 31건 중 실제로 받아지는 것은 **7건**뿐이었다.
       `launcher.py collect` 가 소스와 무관하게 `collect.openapi` 한 곳으로만 보냈고,
       D-108 게이트는 「열린 용도가 있는가」만 봤지 **수집기가 있는가**는 안 봤다.
    ★ 「빠진 것」인지 「사람이 받는 것」인지 둘 다 이름으로 적는다 (D-110 의 not_adopted 와 같은 뜻).
    """
    from collect import COLLECTORS, MANUAL_SOURCES  # noqa: PLC0415

    sources = _registry().get("sources") or {}
    coll = {k for k, v in sources.items() if isinstance(v, dict) and v.get("status") == "collect"}
    orphan = sorted(coll - set(COLLECTORS) - MANUAL_SOURCES)

    assert not orphan, (
        f"🚨 받기로 해 놓고 받는 경로가 없는 소스 {len(orphan)}건 — {orphan}\n"
        "  → collect/__init__.py 의 COLLECTORS(수집기가 돈다) 또는\n"
        "     MANUAL_SOURCES(사람이 받아 register 로 올린다) 에 적는다."
    )


@pytest.mark.gate
def test_HTML_을_긁는_소스는_robots_확인_기록이_있다() -> None:
    """🔴 규약 6 — 판단은 **표**가 한다 (D-179).

    ⛔ 종전에는 `access` 산문에 `{크롤링, 게시판, 스크래핑}` 이 있는지로 봤다.
       「자료실 PDF 다운로드」·「보도자료 웹 공개」·「웹 서비스」가 낱말표에 없어
       **HTML 을 실제로 긁는 소스들이 robots 검사를 통째로 지나갔다.**
       `collect/mfds_board.py` 는 게시물 HTML 을 파싱하는 명백한 스크래퍼인데 한 번도 안 걸렸다.
    ★ 고치는 곳은 생성물이 아니라 원장이다 — `scripts/registry_review.yaml` 에
      `robots_checked_at` 을 적고 `launcher.py registry` 로 다시 생성한다.
    """
    from collect import is_scraper  # noqa: PLC0415

    sources = _registry().get("sources") or {}
    bad = sorted(
        k
        for k, v in sources.items()
        if isinstance(v, dict)
        and v.get("status") == "collect"
        and is_scraper(k)
        and not v.get("robots_checked_at")
    )

    assert not bad, (
        f"🚨 HTML 을 긁는데 robots 확인 기록이 없는 소스 {len(bad)}건 — {bad}\n"
        "  🚨 종전 낱말표로는 이 소스들이 한 번도 안 걸렸다 — 게이트가 새로 보게 된 자리다.\n"
        "  → scripts/registry_review.yaml 의 해당 소스에 `robots_checked_at: <잰 날>` 을 적고\n"
        "     uv run python launcher.py registry 로 다시 생성한다.\n"
        "     🚨 이미 잰 기록이 있으면 scripts/registry_rationale.yaml 을 본다."
    )


# ══════════════════════════════════════════════════════════
#  D-43 · LangSmith 배제 — 전이 의존이 생겼다 (2026-09-10)
# ══════════════════════════════════════════════════════════
#
# 🔴 `langgraph` 를 넣으면서 `langchain-core → langsmith` 가 **딸려 왔다.** 하드 의존이라
#    패키지를 뺄 수 없다. D-43 은 「외부 전송 금지」이고, 그 이유가 **제품 요구사항**이다 —
#    온프레미스는 서사가 아니라 요구사항이라, 개발 중 트레이스도 나가면 안 된다.
# 🚨 **완전 차단은 불가능하다.** `app` 을 안 거치고 langchain 을 직접 쓰면 그만이다.
#    그래서 「막았다」고 적지 않는다. 여기서 하는 일은 둘이다 —
#      ① 저장소의 기본값이 꺼짐인지 본다   ② 지금 이 환경에서 꺼져 있는지 본다
#    실행 경로에서 멈추는 것은 `app.graph.build_graph()` 가 맡는다 (D-220 fail-closed).

TRACING_VARS = ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING")


@pytest.mark.gate
def test_env_example_이_추적을_꺼_둔다() -> None:
    """🚨 `.env.example` 이 `.env` 의 출발점이다 — 기본이 꺼짐이어야 한다."""
    lines = (ROOT / ".env.example").read_text(encoding="utf-8-sig").splitlines()
    got = {}
    for line in lines:
        s = line.strip()
        if "=" in s and not s.startswith("#"):
            k, v = s.split("=", 1)
            if k.strip() in TRACING_VARS:
                got[k.strip()] = v.strip().lower()
    for var in TRACING_VARS:
        assert got.get(var) == "false", (
            f"🚨 `.env.example` 의 `{var}` 가 false 가 아니다 — {got.get(var)!r}\n"
            "   ⛔ 켜지면 광고 문구 원문이 외부로 나간다 (D-43)."
        )


@pytest.mark.gate
def test_지금_환경에서_추적이_꺼져_있다() -> None:
    """🚨 저장소가 아니라 **실행 환경**을 본다 — 셸에서 켜 놓고 돌리는 경로가 있다.

    ⛔ 조용히 끄지 않는다. 켠 사람이 자기가 켠 것이 무시된 줄 모르면 더 나쁘다.
    """
    on = [v for v in TRACING_VARS if os.environ.get(v, "").strip().lower() in ("1", "true", "yes")]
    assert not on, (
        f"🚨 추적이 켜져 있다 — {on} (D-43 이 배제했다)\n"
        "   켜면 광고 문구 원문이 외부로 나간다. 온프레미스는 서사가 아니라 제품 요구사항이다.\n"
        "   끄는 법: 그 변수를 지우거나 false 로 둔다."
    )


# ── 미채택 판정이 되살아나지 않는가 (D-90 ② 의 집행) ────────────────────────────
#: 🚨 **새 판정이 아니다.** D-90 ② 가 `blocked`(협상 불가)와 `not_adopted`(안 쓰기로 했다)를
#:    이미 갈랐고, 미채택은 `sources` 에 없다는 것이 그 판정의 귀결이다 (D-223 도 같은 말을
#:    적재 쪽에서 한다 — *「정본이 미채택이면 사본에서도 없어야 한다」*).
#:    ⛔ 그런데 **그 귀결을 지키는 검사가 없었다.**


def _not_adopted_keys() -> set[str]:
    return {
        item.get("key")
        for item in (_registry().get("not_adopted") or [])
        if isinstance(item, dict) and item.get("key")
    }


def _review_ledger() -> dict:
    return yaml.safe_load((ROOT / "scripts/registry_review.yaml").read_text(encoding="utf-8")) or {}


@pytest.mark.gate
def test_미채택_키가_등재에도_생성기_목록에도_없다() -> None:
    """🔴 미채택을 내린 실제 수단이 **`ORDER` 의 주석 한 줄**이었다.

    ⛔ `gen_registry.py` 의 `NOT_ADOPTED_IDS` 는 **생성을 막지 않는다** — 「미등재」 진단
       출력을 계산할 때만 쓴다. 막는 것은 `ORDER` 에서 그 줄을 지우거나 주석 처리하는 것뿐이고,
       주석을 되살리면 미채택 소스가 `sources` 로 되살아난다.
    🚨 그리고 되살아나도 **2인 확인 게이트가 즉시 통과한다** — 서명이 검토표에 남아 있기
       때문이다(아래 게이트가 그쪽을 본다). 2026-09-13 에 `source` 표에서 실제로
       `foodsafety_admin_measure` 가 「2인 확인 완료」로 앉아 있는 것이 나왔다 (D-223).

    ★ **주석은 게이트가 아니다.** 지운 사람이 알아채는 자리를 만든다.
    """
    na = _not_adopted_keys()
    assert na, "not_adopted 가 비어 있다 — 이 게이트가 아무것도 안 보고 있다"

    both = sorted(na & set(_sources()))
    assert not both, (
        f"🚨 미채택으로 내린 소스가 `sources` 에도 있다 — {both}\n"
        "  ⛔ 정본이 두 말을 한다. `not_adopted` 에서 빼거나 등재를 내린다 (D-90 ②)."
    )

    # 🚨 생성기까지 본다 — `sources` 만 보면 「다시 생성하기 전」에는 초록이다.
    tree = ast.parse((ROOT / "scripts/gen_registry.py").read_text(encoding="utf-8"))
    order: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "ORDER" for t in node.targets):
            continue
        order = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    assert order, "🚨 `gen_registry.py` 에서 ORDER 를 못 읽었다 — 게이트가 눈을 잃었다"

    revived = sorted(na & set(order))
    assert not revived, (
        f"🚨 미채택 소스가 생성기 `ORDER` 에 들어 있다 — {revived}\n"
        "  ⛔ `rebuild` 를 돌리는 순간 `sources` 로 되살아난다.\n"
        "  → 되살리려면 `not_adopted` 에서 먼저 내리고 사유를 남긴다 (D-90 ② · D-72)."
    )


@pytest.mark.gate
def test_서명이_끝난_키가_정본에_없으면_미채택_기록이_있다() -> None:
    """🔴 **검토표는 정본보다 길다** — 미채택·차단된 것의 서명이 남는다.

    `test_레지스트리_서명은_2인확인_원장과_같다` 는 **`sources` 를 돌며 원장을 조회**한다.
    ⛔ 반대 방향 — **원장에만 있는 키** — 는 그 게이트의 검사 밖이다(그쪽은 `continue` 한다).
    🚨 그래서 **미채택 소스의 완료된 2인 서명이 아무 표시 없이 남아 있을 수 있고**,
       그 키가 `ORDER` 로 되살아나면 `ck_source_four_eyes` 가 **처음부터 통과**한다.

    ★ 서명을 지우라는 게이트가 아니다 — 서명은 이력이다.
      **「왜 정본에 없는가」가 키로 적혀 있기만 하면 된다.**
    ⛔ `blocked` 는 키를 `{name, grade, reason}` 로 **제한**하고 있어(같은 파일 위쪽 게이트)
      id 로 대조할 수 없다. 그래서 이 게이트는 **서명이 끝난 것**만 본다 —
      차단 목록의 것들은 서명이 없다(2026-09-13 실측).
    """
    ledger = _review_ledger()
    signed = {
        key
        for key, entry in ledger.items()
        if isinstance(entry, dict)
        and entry.get("decided_by")
        and entry.get("reviewed_by")
        and entry.get("decided_by") != entry.get("reviewed_by")
    }
    assert signed, "🚨 검토표에 서명이 끝난 항목이 하나도 없다 — 원장을 못 읽었다"

    orphan = sorted(signed - set(_sources()) - _not_adopted_keys())
    assert not orphan, (
        f"🚨 2인 서명이 끝났는데 정본에도 미채택 기록에도 없는 키 {len(orphan)}건 — {orphan}\n"
        "  ⛔ 이 상태에서 그 키가 `ORDER` 로 들어가면 2인 확인이 **처음부터 통과**한다.\n"
        "  → 등재하든 미채택으로 내리든, **판정을 키로 적는다** (D-90 ② · D-110)."
    )
