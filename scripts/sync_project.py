"""sync_project.py — 레포 문서를 claude.ai 프로젝트 사본으로 내보낸다.

🚨 레포가 원본이고 프로젝트는 사본이다. 사본은 레포에서 덮어쓰며 반대로는 고치지 않는다.

🚨 버전은 **문서 머리말 한 곳**에만 둔다 — 파일명에는 붙이지 않는다.
   파일명에 붙이면 갱신할 때 두 곳을 손대야 하고, 실제로 어긋났다
   (`수집전처리_기획_v1.2.md` 의 내용이 v1.3 이었다). 두 벌이 된 사실은 갈라진다 (D-99).

🚨 그리고 버전 번호만으로는 「사본이 최신인가」에 답할 수 없다 —
   **어제의 v1.3 과 오늘의 v1.3 을 구분하지 못한다.** 커밋 해시가 그것을 한다.
   그래서 사본 첫 줄에 「버전 · 갱신일 · 그 문서를 마지막으로 바꾼 커밋」을 찍는다.
   스탬프는 **사본에만** 붙는다. 레포 원본은 건드리지 않으므로 커밋이 또 생기지 않는다.

    uv run python scripts/sync_project.py
    → build/project_sync/ 에 스탬프가 찍힌 사본이 생긴다. 업로드는 Claude 가 한다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docmeta import version_of  # noqa: E402  — 버전을 읽는 방법은 한 곳뿐이다

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "project_sync"

# 레포 원본 → 프로젝트 사본 경로. 🚨 이 표가 대응의 단일 출처다.
MAP: dict[str, str] = {
    "docs/00_설계결정기록.md": "claude/CopyLane_설계결정기록.md",
    "docs/00_사실원장.md": "claude/CopyLane_사실원장_FACTS.md",
    "docs/00_산출물현황.md": "claude/CopyLane_산출물현황.md",
    "docs/00_거버넌스_집행계약.md": "claude/CopyLane_거버넌스_집행계약.md",
    "docs/01_기획/01_주제확정_및_실행일정.md": "claude/CopyLane_주제확정_및_실행일정.md",
    "docs/01_기획/02_프로젝트기획서.md": "claude/CopyLane_기획문서.md",
    "docs/01_기획/03_작업일정.md": "claude/CopyLane_작업일정.md",
    "docs/01_기획/경제성_근거.md": "claude/CopyLane_경제성_근거.md",
    "docs/02_설계/거버넌스데이터층_DDL.md": "claude/CopyLane_거버넌스데이터층_DDL.md",
    "docs/03_데이터/소스분석.md": "claude/CopyLane_소스분석.md",
    "docs/03_데이터/수집리스트.md": "claude/CopyLane_수집리스트.md",
    "docs/03_데이터/수집전처리_기획.md": "claude/CopyLane_수집전처리_기획.md",
    "docs/03_데이터/전처리_사양.md": "claude/CopyLane_전처리_사양.md",
    "docs/03_데이터/S0-14_2인확인_검토표.md": "claude/CopyLane_S0-14_2인확인_검토표.md",
    "docs/03_데이터/판정매트릭스.html": "claude/CopyLane_데이터거버넌스_판정매트릭스.html",
    "docs/04_보안/보안점검.md": "claude/CopyLane_보안점검.md",
    "docs/05_배포/배포계획.md": "claude/CopyLane_배포계획.md",
}

# 🚨 프로젝트에만 있는 것 — 레포에서 덮어쓰지 않는다.
#    CopyLane_기획문서_v3.5.md  : 역사 기록. 소급 수정하지 않는다.
#    CopyLane_인계_2026-08-31.md: 세션 인계 메모. 원본이 레포에 없다.
#    CopyLane_설계스키마_3종.md : docs/02_설계/{DB,청크,LangGraph} 합본 — 손으로 만든다.
#    CopyLane_소스레지스트리.md : data_sources.yaml 에 머리말을 붙인 사본 — 손으로 만든다.


def last_commit(rel: str) -> tuple[str, str]:
    """그 문서를 **마지막으로 바꾼** 커밋. HEAD 가 아니다 —
    안 바뀐 문서의 스탬프가 매번 흔들리면 비교의 뜻이 없다."""
    out = subprocess.run(
        ["git", "--no-optional-locks", "log", "-1", "--format=%h|%cs", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    return tuple(out.split("|", 1)) if "|" in out else ("미커밋", "—")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    before = {f.name for f in OUT.iterdir() if f.is_file()}

    rows, missing = [], []
    for rel, dst in MAP.items():
        src = ROOT / rel
        if not src.exists():
            missing.append(rel)
            continue
        text = src.read_text(encoding="utf-8")
        ver = version_of(text) or "판 없음"
        sha, date = last_commit(rel)
        stamp = (
            f"> 📌 **레포 사본** · {ver} · 갱신 {date} · 커밋 `{sha}` · 원본 `{rel}`  \n"
            f"> 🚨 여기서 고치지 마십시오 — 레포가 원본입니다. "
            f"최신 여부는 `git log -1 --format=%h -- {rel}` 와 위 해시를 비교합니다.\n\n"
        )
        if src.suffix == ".html":
            stamp = (
                f"<!-- 레포 사본 · {ver} · 갱신 {date} · 커밋 {sha} · 원본 {rel} "
                f"- 여기서 고치지 마십시오 -->\n"
            )
        (OUT / Path(dst).name).write_text(stamp + text, encoding="utf-8")
        rows.append((Path(dst).name, ver, sha, date))

    # 🚨 MAP 에서 빠진 사본이 남아 있으면 낡은 것을 올리게 된다. 지우거나, 못 지우면 알린다.
    stale = sorted(before - {r[0] for r in rows})
    left = []
    for name in stale:
        try:
            (OUT / name).unlink()
        except OSError:
            left.append(name)

    w = max(len(r[0]) for r in rows)
    for name, ver, sha, date in rows:
        print(f"  {name:<{w}}  {ver:>5}  {sha:>8}  {date}")
    print(f"\n{len(rows)}건 → {OUT.relative_to(ROOT)}/")
    if missing:
        print(f"🚨 원본 없음 {len(missing)}건: {', '.join(missing)}")
    if stale:
        print(f"🧹 MAP 에 없는 낡은 사본 {len(stale)}건 정리: {', '.join(stale)}")
    if left:
        print(f"🚨 지우지 못한 사본 {len(left)}건 — 손으로 지우십시오: {', '.join(left)}")


if __name__ == "__main__":
    main()
