"""scripts/decision_map.py — 결정 ↔ 코드 대응표 (2026-09-13 · D-90 · D-54).

  uv run python launcher.py dmap             # build/decision_map.md 를 뽑는다
  uv run python launcher.py dmap --open      # ⬜ 열린 항목만 표준출력으로

★ **무엇을 답하나** — `docs/00_설계결정기록.md` 의 결정 하나하나가
  ① **코드의 어디에 살아 있나**(D 번호가 인용된 파일·줄)
  ② **아직 무엇이 안 됐나**(본문의 `⬜`·「미착수」 줄)

⛔ **판정을 대신하지 않는다** (작업 지침). 이 도구가 내는 것은 **기계가 셀 수 있는 사실**뿐이다 —
   *「인용 0건」* 은 **「미구현」이 아니다.** 셋이 섞여 있고 가르는 것은 사람이다:
     ① 코드가 아직 없다   ② 코드에는 있는데 **D 번호를 안 적었다**   ③ 코드로 갈 결정이 아니다
   ★ 그래서 표의 마지막 칸은 **비워서 낸다** — `docs/02_설계/구현계획.md` 가 그 칸을 채운다.

🚨 **생성물이다** — `build/` 아래로 나가고 손으로 고치지 않는다 (D-90 · 집행계약 §6).
   원장을 고치고 이 명령을 다시 돈다.

⬜ **여기서 안 보는 것** (D-188) —
   ① **의미상 구현 여부.** `D-72` 를 인용한 줄이 그 결정을 *지키는* 코드인지 *어기면서 언급하는*
      주석인지 구별하지 않는다. 세는 것은 **인용**이지 준수가 아니다.
   ② **D 번호 없이 구현된 것.** 코드가 결정을 지키면서 번호를 안 적었으면 여기서는 0건으로 보인다.
      ★ 그것이 위 ②번 갈래이고, **이 도구가 만들어진 이유 중 하나**다 — 번호를 붙이라고 드러낸다.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "00_설계결정기록.md"
OUT = ROOT / "build" / "decision_map.md"

#: 훑는 확장자. ⛔ `docs/` 는 뺀다 — 문서가 문서를 인용하는 것은 「코드에 산다」가 아니다.
_SUFFIX = (".py", ".sql", ".yaml", ".yml", ".html", ".toml", ".css", ".cfg", ".ini", ".md")
_SKIP_DIRS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "data",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    "docs",
    "발표자료",
}

#: 🚨 「아직 안 됐다」의 신호. ⛔ 「미정」·「예정」은 뺀다 — 역사 서술에 너무 자주 걸려 오탐이 는다.
#:    오탐이 늘면 목록을 아무도 안 읽고, 그러면 진짜 ⬜ 까지 같이 안 읽힌다 (D-167).
_OPEN = re.compile(r"⬜|미착수|미구현|아직 없다|아직 아니|안 만들었|스텁|미실행|남았다|남는 것")

#: 🚨 **폐기·대체된 결정이 인용 0건인 것은 정상이다.** 섞어 세면 「안 쓰이는 결정」 수가 부풀고,
#:    부푼 수는 아무도 안 본다 (D-167). 색인 표의 **상태** 칸으로 가른다.
#:    ⛔ 제목의 취소선(`~~`)으로 가르지 않는다 — 실측: 상태가 「대체됨」인 7건 중 **2건은 취소선이 없다**.
_DEAD = re.compile(r"폐기|대체됨")

_DREF = re.compile(r"\bD-(\d{1,3})\b")
_HEAD = re.compile(r"^### (D-\d+) · (.+?)$", re.M)
_INDEX = re.compile(r"^\|\s*(D-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", re.M)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\*+|🔴|🔄|★|🚨", "", s)).strip()


def load_ledger() -> tuple[dict[str, dict], list[str]]:
    """색인 표에서 분류·상태를, 본문에서 제목과 ⬜ 줄을 읽는다."""
    if not LEDGER.exists():
        raise SystemExit(f"🔴 원장이 없다 — {LEDGER}")
    text = LEDGER.read_text(encoding="utf-8")

    index = {m.group(1): (_clean(m.group(3)), _clean(m.group(4))) for m in _INDEX.finditer(text)}

    # 본문 블록 — 제목 사이를 잘라 쓴다
    heads = list(_HEAD.finditer(text))
    decisions: dict[str, dict] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end() : end]
        cat, status = index.get(h.group(1), ("", ""))
        decisions[h.group(1)] = {
            "title": _clean(h.group(2)),
            "cat": cat,
            "status": status,
            "open": [_clean(ln) for ln in body.splitlines() if _OPEN.search(ln) and ln.strip()],
            # 🆕 본문 원문 — 다른 축으로 원장을 훑는 쪽이 파서를 두 번 쓰지 않게 (D-99).
            #    ⛔ 이 파일은 본문을 안 쓴다. `scripts/data_status.py` 가 소스 이름으로 훑는다.
            "body": body,
        }

    # 🚨 색인에만 있고 본문이 없는 것 — 인용하면 안 되는 자리다 (D-100)
    orphan = sorted(set(index) - set(decisions), key=lambda d: int(d[2:]))
    return decisions, orphan


def scan_code() -> dict[str, list[str]]:
    """D 번호가 인용된 자리. 값은 `경로:줄` 목록."""
    where: dict[str, list[str]] = collections.defaultdict(list)
    for p in sorted(ROOT.rglob("*")):
        if p.suffix.lower() not in _SUFFIX or not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if _SKIP_DIRS & set(rel.parts):
            continue
        for lineno, line in enumerate(
            p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for n in set(_DREF.findall(line)):
                where[f"D-{int(n):02d}"].append(f"{rel.as_posix()}:{lineno}")
    return where


def render(decisions: dict[str, dict], where: dict[str, list[str]], orphan: list[str]) -> str:
    def key(d: str) -> int:
        return int(d[2:])

    dead = {d for d in decisions if _DEAD.search(decisions[d]["status"])}
    live = {d for d in decisions if d not in dead}
    cited = {d for d in live if where.get(f"D-{key(d):02d}")}
    opened = {d for d in decisions if decisions[d]["open"]}
    L: list[str] = []
    a = L.append

    a("# 결정 ↔ 코드 대응표 <sub>(생성물 — 손으로 고치지 않는다 · D-90)</sub>\n")
    a("> `uv run python launcher.py dmap` 이 `docs/00_설계결정기록.md` 와 저장소를 읽어 뽑습니다.")
    a("> 🚨 **수의 정본은 원장입니다** (D-54). 이 표는 **어디에 있나**만 답합니다.\n")
    a("> ⛔ **「인용 0건」은 「미구현」이 아닙니다.** 셋이 섞여 있습니다 —")
    a("> ① 코드가 아직 없다 ② 코드에는 있는데 **D 번호를 안 적었다** ③ 코드로 갈 결정이 아니다.")
    a(
        "> **가르는 것은 사람이고**, 그 판정은 [`docs/02_설계/구현계획.md`](../docs/02_설계/구현계획.md) 에 있습니다.\n"
    )

    a("## 0. 한 장\n")
    a("| | |")
    a("|---|---:|")
    a(f"| 결정 본문 | **{len(decisions)}** |")
    a(f"| 그중 **폐기·대체됨** — 안 쓰이는 것이 정상 | **{len(dead)}** |")
    a(f"| **살아 있는 결정** | **{len(live)}** |")
    a(f"| 코드·설정·테스트에 D 번호가 인용된 것 | **{len(cited)}** |")
    a(f"| 🔴 **살아 있는데 인용 0건** | **{len(live) - len(cited)}** |")
    a(f"| 본문에 ⬜ 열린 항목이 있는 것 | **{len(opened)}** |")
    a(f"| ⬜ 줄 총량 | **{sum(len(decisions[d]['open']) for d in opened)}** |")
    if orphan:
        a(f"| 🔴 색인에만 있고 본문이 없는 것 | **{len(orphan)}** — {' '.join(orphan)} |")
    a("")

    a("## 1. ⬜ 열린 항목 — 원장이 스스로 「아직」이라 적은 것\n")
    a("🚨 **여기 있는 문장은 전부 원장 본문에서 그대로 가져온 것입니다.** 지어낸 것이 없습니다.\n")
    by_cat: dict[str, list[str]] = collections.defaultdict(list)
    for d in sorted(opened, key=key):
        by_cat[decisions[d]["cat"] or "(분류 없음)"].append(d)
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        a(f"### [{cat}] — {len(by_cat[cat])}건\n")
        for d in by_cat[cat]:
            v = decisions[d]
            mark = "" if where.get(f"D-{key(d):02d}") else " · 🔴 코드 인용 0건"
            a(f"**{d}** {v['title']}{mark}")
            for ln in v["open"]:
                a(f"- {ln}")
            a("")

    a("## 2. 결정별 사는 자리\n")
    a("| D | 분류 | 제목 | 인용 | 대표 자리 | ⬜ | 폐기 |")
    a("|---|:-:|---|---:|---|:-:|:-:|")
    for d in sorted(decisions, key=key):
        v = decisions[d]
        hits = where.get(f"D-{key(d):02d}", [])
        top = ""
        if hits:
            common = collections.Counter(h.split(":")[0] for h in hits).most_common(2)
            top = " · ".join(f"`{f}`×{c}" if c > 1 else f"`{f}`" for f, c in common)
        a(
            f"| {d} | {v['cat']} | {v['title'][:52]} | {len(hits)} | {top} | "
            f"{'⬜' if v['open'] else ''} | {'🪦' if d in dead else ''} |"
        )
    a("")
    a("---")
    a("🚨 **훑지 않은 자리** — `docs/` · `data/` · `build/` · `dist/` · `발표자료/` (D-188).")
    a("문서가 문서를 인용하는 것은 「코드에 산다」가 아니므로 뺐습니다.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="결정 ↔ 코드 대응표 (D-90)")
    ap.add_argument("--open", action="store_true", help="⬜ 열린 항목만 표준출력으로")
    args = ap.parse_args()

    decisions, orphan = load_ledger()
    where = scan_code()
    dead = [d for d in decisions if _DEAD.search(decisions[d]["status"])]
    live = [d for d in decisions if d not in dead]
    cited = sum(1 for d in live if where.get(f"D-{int(d[2:]):02d}"))
    opened = [d for d in decisions if decisions[d]["open"]]

    if args.open:
        for d in sorted(opened, key=lambda x: int(x[2:])):
            v = decisions[d]
            print(f"\n{d} [{v['cat']}] {v['title']}")
            for ln in v["open"]:
                print(f"   - {ln}")
        print(f"\n⬜ {len(opened)}건 · {sum(len(decisions[d]['open']) for d in opened)}줄")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(decisions, where, orphan), encoding="utf-8")
    print(
        f"✅ {OUT.relative_to(ROOT).as_posix()}  "
        f"({OUT.stat().st_size:,}B)\n"
        f"   결정 {len(decisions)} (폐기·대체 {len(dead)}) · 살아 있는 것 {len(live)} · "
        f"인용된 것 {cited} · 🔴 인용 0건 {len(live) - cited} · ⬜ 열린 결정 {len(opened)}"
    )
    if orphan:
        print(f"🔴 색인에만 있고 본문이 없는 결정: {' '.join(orphan)} — 인용하면 안 된다 (D-100)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
