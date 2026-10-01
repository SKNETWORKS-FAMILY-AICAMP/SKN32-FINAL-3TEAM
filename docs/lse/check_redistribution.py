"""lse 공개 파일에 재배포 불가 문구가 들어가는 것을 커밋 전에 막는다 (2026-10-01).

광고주가 쓴 광고 문구를 인용한 행은 재배포 불가다(골든 `redistributable: false`).
2026-10-01 에 학습쌍 · 노트북 · 결과서에 공정위 의결서 인용 문구가 실려 공개 저장소에
올라간 것을 발견해 걷어냈다 — 같은 일이 다시 생기지 않게 하는 문지기다.

기준 문구:
  - `docs/lse/_private/ftc_pairs.jsonl` 의 입력 · 교정문 · 핵심주장 (공정위 원천)
  - `data/derived/golden/golden.jsonl` 의 `redistributable: false` 문장
둘 다 없는 기기(팀 비공개 데이터를 안 받은 기기)에서는 경고만 하고 통과한다.

pre-commit 이 바뀐 파일 경로를 넘긴다. 손으로:
    python docs/lse/check_redistribution.py docs/lse/train_pairs.jsonl ...
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "docs" / "lse" / "_private" / "ftc_pairs.jsonl"
GOLDEN = ROOT / "data" / "derived" / "golden" / "golden.jsonl"
#: 재배포 가능한 원천 — 식약처 기능성 원료 게시판(고시 문구)과 그걸로 만든 주입 데이터
OPEN_SOURCES = (
    ROOT / "data" / "derived" / "hf_display_claims.jsonl",
    ROOT / "data" / "derived" / "injected_golden.jsonl",
)
#: 줄 끝에 `redistribution: ok` 를 단 줄은 검사에서 뺀다(일반어 우연 일치용).
#: 이보다 짧은 골든 문장은 따옴표로 감싸 인용했을 때만 잡는다 — 「해독」 같은 일반어 오탐을 막는다
MIN_FREE = 8


def restricted() -> tuple[set[str], set[str]]:
    """(어디서든 잡을 문구, 따옴표 안에서만 잡을 짧은 문구)."""
    free: set[str] = set()
    quoted: set[str] = set()

    def add(s: str | None) -> None:
        s = (s or "").strip()
        if len(s) >= MIN_FREE:
            free.add(s)
        elif len(s) >= 3:
            quoted.add(s)

    if PRIVATE.exists():
        for line in PRIVATE.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                add(r.get("input"))
                add((r.get("output") or {}).get("body"))
    open_texts: set[str] = set()
    if GOLDEN.exists():
        for line in GOLDEN.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("redistributable") is False:
                add(r.get("text"))
            else:
                open_texts.add((r.get("text") or "").strip())
    # 재배포 가능한 원천에도 같은 문장이 있으면(예: 고시 기능성 문구 「피부건강에 도움」) 인용이 아니다
    open_blob = "\n".join(
        p.read_text(encoding="utf-8") for p in OPEN_SOURCES if p.exists()
    )
    free = {s for s in free - open_texts if s not in open_blob}
    quoted = {s for s in quoted - open_texts if s not in open_blob}
    return free, quoted


def read_text(path: Path) -> str | None:
    if path.suffix == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        return re.sub(r"<[^>]+>", "", xml).replace("&quot;", '"')
    if path.suffix in {".md", ".ipynb", ".jsonl", ".json", ".py", ".txt", ".csv"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    return None


def main(argv: list[str]) -> int:
    free, quoted = restricted()
    if not free and not quoted:
        print("⚠️ 재배포 불가 기준 문구가 없다(_private · golden 없음) — 검사를 건너뛴다")
        return 0
    bad = 0
    for arg in argv:
        path = Path(arg)
        if "_private" in path.parts or not path.is_file() or path.resolve() == Path(__file__).resolve():
            continue
        text = read_text(path)
        if text is None:
            continue
        # 일반어가 우연히 겹친 줄은 끝에 표시를 달아 뺀다 — 광고 문구 인용에는 쓰지 않는다
        text = "\n".join(ln for ln in text.splitlines() if "redistribution: ok" not in ln)
        hits = [s for s in free if s in text]
        hits += [s for s in quoted if re.search(rf"[\"'“‘「]{re.escape(s)}[\"'”’」]", text)]
        if hits:
            bad += 1
            print(f"✖ {arg}: 재배포 불가 문구 {len(hits)}개 — 예: {hits[:3]}")
    if bad:
        print("광고주 문구 인용은 docs/lse/_private/ 에만 둔다. 공개 파일에는 출처 번호(source_id)만 남긴다.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
