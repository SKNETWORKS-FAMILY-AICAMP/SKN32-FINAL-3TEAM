"""소성민 코드 리뷰(2026-09-21) 고침 — 기존 테스트가 못 잡던 결함들.

🚨 **게이트가 아니다**(#8 만 게이트 — 2026-09-24) — 파일은 tmp 로, 명령은 기록기로 돈다. 네트워크·postgres 없음.
   마스킹(#2)은 `tests/test_mask.py` · `tests/test_derived_manifest.py`, `collect --dry-run`(#4)은
   `tests/test_launcher_automation.py` 에 있다 — 그 규칙이 사는 파일 옆에 둔다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── #1 sync_project — `subprocess.run(newline=…)` 로 부를 때마다 TypeError ─────────
def test_last_commit_이_죽지_않는다() -> None:
    """⛔ 종전에는 `Popen.__init__() got an unexpected keyword argument 'newline'` 로 아무것도 못 썼다."""
    import sys

    # 🚨 `sync_project` 는 import 할 때 `scripts/` 를 sys.path 맨 앞에 넣는다(`docmeta` 를 찾으려고) —
    #    그대로 두면 뒤의 `from collect import …` 가 패키지 대신 `scripts/collect.py` 를 집는다. 되돌린다.
    saved = list(sys.path)
    try:
        from scripts import sync_project
    finally:
        sys.path[:] = saved

    sha, date = sync_project.last_commit("README.md")
    assert isinstance(sha, str) and isinstance(date, str)


def test_subprocess_호출에_newline_인자가_없다() -> None:
    """🔴 같은 실수가 다른 곳에 생기지 않게 — `newline` 은 `open`·`write_text` 의 인자다."""
    bad = []
    for p in ROOT.rglob("*.py"):
        if {".venv", "node_modules"} & set(p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if name in {"run", "Popen", "check_output", "check_call", "call"} and any(
                k.arg == "newline" for k in n.keywords
            ):
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    assert not bad, f"🔴 subprocess 에 newline= — {bad}"


# ── #8 통과 문턱 — R2(업무정지 위험)가 통과로 판정되던 것 ─────────────────────────
#    🔄 2026-09-24 — D-273 으로 문턱이 R1 → **R0** 이 됐다. 이 테스트만 옛 정의(≤ R1)에 남아
#       「확정 · 위반 없음 · R1」 문장을 만들다 불변식(`_confirmed_risk_invariant`)에 막혀 CI 가 빨갰다.
#       ⛔ 게이트 표시가 없어 로컬 `check`(`-m gate`)는 못 봤다 — 그래서 **게이트로 올린다**.
#    ★ 문턱 상수의 정본 대조는 `test_contracts.py::test_통과는_확정_그리고_R0_이다` 다. 여기는 ssm 리뷰 #8 의
#       원래 걱정(업무정지 위험이 통과로 샌다)과 「위험도 없음은 통과가 아니다」를 계속 지킨다.
@pytest.mark.gate
def test_통과_문턱은_R0_이다() -> None:
    """🔴 D-273 (D-130 · D-227 개정) — 통과 = 확정 ∧ R0. 확정 위반은 R1(시정명령 위험)부터 통과가 아니다."""
    from app.contracts import (
        EvidenceArticle,
        Infeasibility,
        Risk,
        RiskAssessment,
        SentenceJudgment,
        Verdict,
        Violation,
        is_pass,
    )

    def clean() -> SentenceJudgment:
        return SentenceJudgment(
            sent_id="s", text="t", verdict=Verdict.confirmed,
            risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
        )  # fmt: skip

    def violated(r: Risk) -> SentenceJudgment:
        return SentenceJudgment(
            sent_id="s", text="t", verdict=Verdict.confirmed,
            violations=[Violation.거짓_과장], infeasibility=Infeasibility.B,
            evidence=[EvidenceArticle(law_id="002011", article="제3조", item="제1항제1호")],
            risk=RiskAssessment(floor=r, final=r),
        )  # fmt: skip

    assert is_pass(clean())
    assert not is_pass(violated(Risk.R1)), "🔴 시정명령 위험(확정 위반)이 통과가 됐다 (D-273)"
    assert not is_pass(violated(Risk.R2)), "🔴 업무정지 위험이 통과가 됐다"
    assert not is_pass(
        SentenceJudgment(sent_id="s", text="t", verdict=Verdict.confirmed, risk=RiskAssessment())
    ), "🔴 위험도가 없는데 통과로 셌다 (D-220)"


# ── #10 setkey 메뉴 — 비밀이 아닌 값을 가린 입력창으로 받던 것 ────────────────────
def test_MLFLOW_주소는_설정이고_DB_주소는_키다() -> None:
    """`MLFLOW_TRACKING_URI` 는 비밀이 아니다 — 값이 보여야 고친다(`SETTINGS`).
    🚨 반대 대조 — `DATABASE_URL` 은 비밀번호가 들어 있어 가려서 받는다(`KEYS`)."""
    from collect import env

    assert "MLFLOW_TRACKING_URI" in env.SETTINGS and "MLFLOW_TRACKING_URI" not in env.KEYS
    assert "DATABASE_URL" in env.KEYS
