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
from collections import Counter
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
    # 🔄 2026-09-09 신규 — 「무엇을 쓰기로 했고 무엇을 안 쓰기로 했나」의 단일 출처.
    #    🚨 생성물이라 낡지 않는다 (D-54). 2026-09-03 판 현황판이 손으로 쓴 것이었다.
    "docs/03_데이터/데이터현황판.md": "claude/CopyLane_데이터현황판.md",
    "docs/03_데이터/S0-14_2인확인_검토표.md": "claude/CopyLane_S0-14_2인확인_검토표.md",
    "docs/03_데이터/판정매트릭스.html": "claude/CopyLane_데이터거버넌스_판정매트릭스.html",
    "docs/04_보안/보안점검.md": "claude/CopyLane_보안점검.md",
    "docs/05_배포/배포계획.md": "claude/CopyLane_배포계획.md",
}

# 🚨 프로젝트에만 있는 것 — 레포에서 덮어쓰지 않는다.
#    CopyLane_기획문서_v3.5.md  : 역사 기록. 소급 수정하지 않는다.
#    CopyLane_인계_2026-08-31.md: 세션 인계 메모. 원본이 레포에 없다.
#    CopyLane_설계스키마_3종.md : docs/02_설계/{DB,청크,LangGraph} 합본 — 손으로 만든다.
#    🔄 CopyLane_소스레지스트리.md 는 아래 registry_snapshot() 이 만든다 — 더는 손으로 안 쓴다.
#       손으로 쓰던 동안 세 군데가 낡았다 (not_adopted 10→9 · D-106 으로 철회된 문장 · 게이트 19).


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


REGISTRY_SNAPSHOT = "claude/CopyLane_소스레지스트리.md"


def registry_snapshot() -> str:
    """`data_sources.yaml` 에 머리말을 얹은 프로젝트 사본.

    🚨 **손으로 쓰지 않는다.** 손으로 쓰던 동안 `not_adopted` 건수·D-106 으로 철회된 문장·
    게이트 수 셋이 각각 다른 시점에 낡았다. 숫자는 전부 yaml 에서 센다 — 머리말 산문만 고정이다.
    """
    import yaml  # noqa: PLC0415 — 이 함수에서만 쓴다

    text = (ROOT / "data_sources.yaml").read_text(encoding="utf-8")
    d = yaml.safe_load(text)
    S = {k: v for k, v in d["sources"].items() if isinstance(v, dict)}
    n = Counter(v.get("status") for v in S.values())
    ev_real = sum(
        1 for v in S.values() if v.get("evidence_url") and not v.get("evidence_is_access")
    )
    ev_fb = sum(1 for v in S.values() if v.get("evidence_is_access"))
    ev_no = sum(1 for v in S.values() if not v.get("evidence_url"))
    head = f"""## 축이 넷이다 — 섞으면 안 된다

| 축 | 묻는 것 | 필드 |
|---|---|---|
| **등급** | 원문을 어디까지 다룰 수 있는가 | `grade` G0~G3 |
| **용도** | 가져온 것을 무엇에 쓸 수 있는가 | `use` U1~U4 |
| **재배포** | **우리가 만든 파생 데이터셋**을 공개 배포할 수 있는가 | `redistributable` · `NOREDIST` (D-71) |
| **수집** | 가져오는가 — 용도와 다른 축이다 | `status` (D-108) |

### 등급이 허용하는 용도 상한 — 게이트가 검사한다

| 등급 | U1 학습 | U2 원문색인 | U3 화면인용 | U4 배포 |
|:-:|:-:|:-:|:-:|:-:|
| G3 | 가능 | 가능 | 가능 | 가능 |
| **G2** | 가능 | 🚨 **deny 고정** | 🚨 **deny 고정** | 가능 |
| G1 | deny | deny | deny | deny |
| **G0** | deny | deny | deny | deny |

G2 에 U2·U3 가 닫히는 것은 정책이 아니라 **정의**다 — 원문을 보관하지 않기로 한 등급에
원문 색인과 원문 인용을 열어 두면 등급 표기가 거짓이 된다.

### `status` — 「수집기가 이 소스를 실행하는가」 하나만 뜻한다 (D-108)

| 값 | 뜻 | `use` 와의 관계 |
|---|---|---|
| `collect` | 자동 수집기가 실행한다 | 🚨 **최소 하나 `allow`** (게이트 22) |
| `manual` | 🚨 사람이 수기로만 — 자동 수집은 약관 위반이라 수집기가 거부한다 | 제약 없음 |
| `hold` | 이번 범위 밖 — 착수 전 또는 선결 조건 대기 | 제약 없음 (열려 있어도 정상) |

아무 용도도 열리지 않은 소스를 자동으로 가져오는 것은 **판정 없이 원문을 손에 쥐는 일**이다 —
G0 를 fail-closed 로 닫아 둔 이유(D-72)가 **수집 단계에서 우회된다.**
🚨 **역은 성립하지 않는다.** `hold` + 용도 열림은 「판정 끝, 착수만 남음」이며 정상이다.
🚨 `blocked` · `not_adopted` 는 `status` 값이 **아니라 별도 섹션**이다 — 스키마부터 다르다.

**전파 규칙** — 두 축은 다르다 (D-71).

```
배포 모델 학습  = {{ f | f.U1 AND f.U4 }}
데이터셋 공개   = {{ f | NOREDIST 없음 }}
```

🚨 **AI Hub 6종은 U2·U3 가 닫혀 있다** — 이용정책 제4항 「학습모델의 학습용으로만」 ·
제5항 「제3자 열람 금지」 (D-102). 등급은 G3 이고 U1·U4 는 열려 있다.
**등급과 용도는 다른 축**이라는 것이 여기서 가장 잘 보인다.

## 현황

| | 값 |
|---|:-:|
| 등재 소스 | **{len(S)}** — 수집 {n["collect"]} · 수기 {n["manual"]} · 보류 {n["hold"]} |
| `law_go_kr` covers | **{len(S["law_go_kr"].get("covers") or [])}종** |
| 편입 금지 `blocked` | {len(d["sources"]["blocked"])} |
| 판정 완료·미채택 `not_adopted` | {len(d["not_adopted"])} |
| `redistributable: false` | {sum(1 for v in S.values() if not v.get("redistributable"))} — AI Hub 전량 |
| 등재 모델 | {len(d["models"])} |
| 근거 URL | 실물 **{ev_real}** · ⚠️ 접근 URL 폴백 {ev_fb} · 없음 {ev_no} |

🚨 **근거 URL 과 접근 URL 은 다르다** (역검토 v1.3 §2). `evidenceUrl` 이 없으면 `url` 로
폴백하되 **폴백했다고 표시한다** — 추정한 URL 은 빈 칸보다 나쁘다. 빈 칸은 「미확인」이라
말하지만 추정값은 「확인됨」이라고 거짓말한다.

🚨 **`reviewed_by` 가 채워지지 않으면 수집이 한 건도 못 나간다** (S0-14 · D-66 · D-90).

---

## 전문

```yaml
{text.rstrip()}
```
"""
    return head


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

    # 🔄 레지스트리 스냅샷 — MAP 과 달리 원본 파일이 아니라 **생성물**이다.
    #    rows 에 넣어야 아래 stale 정리가 이것을 낡은 사본으로 지우지 않는다.
    snap = Path(REGISTRY_SNAPSHOT).name
    sha, date = last_commit("data_sources.yaml")
    (OUT / snap).write_text(
        f"# CopyLane 소스 레지스트리 (`data_sources.yaml`) — 스냅샷\n\n"
        f"> 📌 **레포 사본** · 갱신 {date} · 커밋 `{sha}` · 원본 `data_sources.yaml`  \n"
        f"> 🚨 여기서 고치지 마십시오 — `_matrix/data.js` 가 원본이고 그것조차 생성물입니다.\n\n"
        + registry_snapshot(),
        encoding="utf-8",
    )
    rows.append((snap, "생성물", sha, date))

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
