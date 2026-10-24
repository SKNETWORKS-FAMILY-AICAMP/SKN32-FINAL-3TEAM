"""scripts/sealed_log.py — **봉인 평가셋(`test_sentence`)을 연 기록** 한 곳 (🆕 2026-10-15 · D-344 ⑧ · D-175 · D-339 결정 7).

★ 봉인 행을 읽는 도구가 둘이다 — 판정 그래프 평가(`scripts/eval_graph.py --sealed`)와 판정기 B(`scripts/eval_rule.py --sealed`).
   둘 다 **돌기 전에** 이 기록에 한 줄을 남긴다(도중에 죽어도 연 것은 센다). 기록 · 커밋 읽기를 두 벌 두지 않는다 (D-99).
🔴 줄마다 `tool` 이 있다 — 「날짜 하나에 한 번」(D-339 결정 7)은 **판정 그래프 봉인 회차**의 규칙이라 그 도구의 줄만 센다.
   `tool` 이 없는 옛 줄(2026-10-15 이전)은 판정 그래프의 것이다(그때는 그 도구만 적었다).
🚨 기록은 기기마다 따로다(`build/` · git 무시) — 원장에 판 표지와 함께 옮겨 적는 것이 정본이다.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
from typing import Any

SEALED_LOG = pathlib.Path("build/eval/sealed_runs.jsonl")
#: 판정 그래프 봉인 회차 — `tool` 이 없는 옛 줄도 이것이다
GRAPH = "eval_graph"
RULE = "eval_rule"
#: 🆕 2026-10-25 (D-348 보충 43 결정 2 ⑤) 봉인 회차와 같은 플래그의 **dev 선행 실행** 기록 — 이 기기 · 커밋마다.
#:    까닭 — 봉인 회차 1 번째(10-24)가 dev 에서 한 번도 돌지 않은 플래그 조합(무조건부 + 답 경로)으로 열려 계약 오류로 멈췄다(원장 10-24(B) ④)
DEV_LOG = pathlib.Path("build/eval/dev_runs.jsonl")


def git_head(root: pathlib.Path = pathlib.Path(".")) -> str:
    """지금 커밋 — `.git` 을 직접 읽는다(git 명령을 부르지 않는다). 못 읽으면 「미확인」 — 지어내지 않는다 (D-220).

    🚨 작업 트리에 커밋 안 된 변경이 있는지는 여기서 모른다 — 기록에 그 사실을 같이 적는다.
    """
    try:
        head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head[:12]
        ref = head[5:]
        loose = root / ".git" / ref
        if loose.exists():
            return loose.read_text(encoding="utf-8").strip()[:12]
        for line in (root / ".git" / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split()[0][:12]
    except OSError:
        pass
    return "미확인"


#: 작업 트리 상태 — 모르면 이 글자다(지어내지 않는다 · D-220)
WORKTREE_UNKNOWN = "커밋 안 된 변경 여부 미확인"
WORKTREE_CLEAN = "깨끗함"


def worktree_state(root: pathlib.Path = pathlib.Path(".")) -> str:
    """🆕 2026-10-20 (D-339 결정 7 「그날의 ohb 커밋 하나」) — **추적 중인 파일에 커밋 안 된 변경이 있나.**

    ★ `git status --porcelain --untracked-files=no` 한 번 — 추적 밖 파일(`build/` · 초안)은 보지 않는다 · 판정 코드는 모두 추적 중이다.
    🔴 git 을 못 부르거나 실패하면 `WORKTREE_UNKNOWN` — 「깨끗함」으로 치지 않는다 (D-220). ⛔ `git_head` 는 종전대로 git 을 부르지 않는다.
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return WORKTREE_UNKNOWN
    if out.returncode != 0:
        return WORKTREE_UNKNOWN
    lines = [x for x in out.stdout.splitlines() if x.strip()]
    return WORKTREE_CLEAN if not lines else f"커밋 안 된 변경 {len(lines)} 파일"


def worktree_refusal(root: pathlib.Path = pathlib.Path(".")) -> str | None:
    """봉인 회차를 열면 안 되는 작업 트리면 그 까닭 — 깨끗하면 `None`. 판정 그래프 · 판정기 B 의 `--sealed` 가 **돌기 전에** 부른다 (D-99)."""
    st = worktree_state(root)
    if st == WORKTREE_CLEAN:
        return None
    return (
        f"작업 트리가 커밋 하나로 서지 않았다({st}) — 봉인 회차는 그날의 커밋 하나로 연다(D-339 결정 7). "
        "커밋하거나 되돌린 뒤 연다 · `git status` 로 본다"
    )


def append_dev(rec: dict[str, Any], *, path: pathlib.Path = DEV_LOG) -> None:
    """dev 실행 한 줄 — 커밋 · 작업 트리와 함께(보충 43 결정 2 ⑤). 🔴 기록을 못 쓰면 멈춘다(조용히 넘기지 않는다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "commit": git_head(),
        "worktree": worktree_state(),
    } | rec
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


def dev_precheck_refusal(
    answers: bool, *, path: pathlib.Path = DEV_LOG, root: pathlib.Path = pathlib.Path(".")
) -> str | None:
    """봉인 회차를 열기 전 — **같은 커밋 · 깨끗한 작업 트리**에서 봉인과 같은 두 모드를 dev 전 행으로 끝까지 돌렸나 (보충 43 결정 2 ⑤).

    ★ 두 모드 = 무조건부(답 경로 없음 · `eval_graph.mode_answers`) · 조건부(봉인에 `--answers` 를 주면 답 경로도) · 품목만(`--category-only`) 줄은 세지 않는다.
    ★ 그 모드의 가장 최근 줄에서 불변식 위반 · 계약 오류 · 답 경로 계약 오류가 0 이어야 한다.
    🚨 경로 동치(`scripts/eval_diff.py equiv`)는 여기서 보지 않는다 — 결과 파일 둘을 맞대는 별도 도구다(봉인 조건은 원장에 적는다).
    """
    head = git_head(root)
    rows = [
        r
        for r in _rows(path)
        if r.get("commit") == head and r.get("worktree") == WORKTREE_CLEAN and r.get("full")
    ]
    why = []
    for name, cond, ans in (("무조건부", False, False), ("조건부", True, answers)):
        got = [
            r
            for r in rows
            if r.get("conditional") is cond
            and bool(r.get("answers")) is ans
            and not r.get("category_only")
        ]
        if not got:
            why.append(f"{name}{' · 답 경로' if ans else ''} 줄 없음")
            continue
        bad = [
            k
            for k in ("invariant_rows", "contract_errors", "answer_contract_errors")
            if got[-1].get(k)
        ]
        if bad:
            why.append(f"{name} — {' · '.join(bad)} 가 0 이 아니다")
    if why:
        return (
            f"같은 커밋({head}) · 깨끗한 작업 트리 · 같은 플래그의 dev 선행 실행이 없다 — {' / '.join(why)} "
            "(`eval_graph.py --dev --guide-dev` · `--dev --guide-dev --conditional[ --answers]` 를 먼저 · D-348 보충 43 결정 2 ⑤ · 원장 10-24(B) ④)"
        )
    return None


def _rows(path: pathlib.Path) -> list[dict]:
    """기록 줄 — 없으면 빈 목록. 🔴 읽지 못하는 줄은 멈춘다(지나치지 않는다)."""
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _of(row: dict, tool: str) -> bool:
    return row.get("tool", GRAPH) == tool


def runs_on(date: str, *, tool: str, path: pathlib.Path = SEALED_LOG) -> list[dict]:
    """이 기기에서 그 날짜(`YYYY-MM-DD`)에 그 도구가 연 봉인 회차들."""
    return [r for r in _rows(path) if _of(r, tool) and str(r.get("at", ""))[:10] == date]


def append(stamp: dict[str, Any], *, tool: str, path: pathlib.Path = SEALED_LOG) -> int:
    """한 줄을 남기고 **그 도구의** 이 기기 누적 횟수를 낸다. 🔴 기록을 못 쓰면 멈춘다(조용히 넘기지 않는다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "commit": git_head(),
        "worktree": worktree_state(),
    } | stamp
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    return sum(1 for r in _rows(path) if _of(r, tool))
