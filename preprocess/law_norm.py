"""law_norm.py — [별표] **산문**을 규범 노드로 자른다 (3층 판단규범).

  uv run python -m preprocess.law_norm --dump
  uv run python -m preprocess.law_norm --annex 013453_0001

왜 따로인가 — `collect/law_annex.py` 는 **괘선 표**를 자른다. 그런데 표 0행인 별표가 12건이고,
그중 **3층의 본체가 둘 있다**(2026-09-09 실측) —

    013453 [별표 1] 부당한 표시 또는 광고의 내용(제3조제1항 관련)   8,161자
    008741 [별표 5] 화장품 표시ㆍ광고의 범위 및 준수사항(제22조 관련) 2,734자

앞의 것이 **우리 위법 유형 8종의 법령상 정의 그 자체**다. 표가 아니라 `1. → 가. → 1)` 계층
산문이라 표 파서로는 0행이 나온다. 같은 수집으로 4층은 채워지고 3층은 원문만 쌓여 있었다.

🚨 **줄을 이어붙이는 것은 되돌릴 수 없이 애매하다.** 원문이 고정폭으로 접혀 있는데
   패딩이 공백을 먹어서, 「단어 사이에서 접혔는가」와 「음절 사이에서 접혔는가」가
   구분되지 않는다. 실측 —

       '…등(이하 이'  + '목에서'  → 원문은 「이 목에서」   (공백 있었음)
       '…각 목의 표'  + '시 또는' → 원문은 「표시 또는」   (공백 없었음)

   폭으로도 안 갈린다. 접힘 열이 76~78 사이에서 흔들리고, 한글이 폭 2 라 마지막 칸을
   정확히 채우지 못한다. **그래서 복원하지 않는다** (D-98 「완전 복원은 하지 않는다」).

✅ **그런데 이 애매함은 매칭에 영향을 주지 않는다.** D-117 이 「매칭은 정규화문, 보관은 원문」
   이고 `norm()` 이 공백을 **전부 지운다** — 「이목에서」와 「이 목에서」가 같은 문자열이 된다.
   그래서 이 모듈은 둘 다 남긴다:
     `lines`  물리 줄 원본 — 화면에 보일 때 쓴다. 재구성하지 않는다
     `text`   공백 없이 이어붙인 것 — 매칭용. `norm()` 을 지나면 애매함이 사라진다
   🚨 `text` 를 화면에 그대로 찍으면 안 된다. 그건 복원한 척하는 것이다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from collect import store

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANNEX = ROOT / "data" / "raw" / "law" / "annex"

# 계층 — 마커의 **모양**이 깊이를 정한다. 들여쓰기로 정하지 않는다:
# 이어지는 줄의 들여쓰기가 마커 줄과 같아서 둘을 못 가른다 (실측).
JO = "가나다라마바사아자차카타파하"
LEVELS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (1, re.compile(r"^(\d{1,2})\.\s")),
    (2, re.compile(rf"^([{JO}])\.\s")),
    (3, re.compile(r"^(\d{1,2})\)\s")),
    (4, re.compile(rf"^([{JO}])\)\s")),
    (5, re.compile(r"^([①-⑳])\s?")),
)
# 「■ 화장품법 시행규칙 [별표 5] <개정 …>」 — 머리글
HEAD = re.compile(r"^■")
# 제목의 「(제22조 관련)」 — 이 별표를 위임한 조문
ARTICLE = re.compile(r"\(([^)]*제\d+조[^)]*)\s*관련\)")


def _marker(line: str) -> tuple[int, str] | None:
    s = line.strip()
    for level, pat in LEVELS:
        m = pat.match(s)
        if m:
            return level, m.group(1)
    return None


def parse(content: str) -> list[dict]:
    """`1. → 가. → 1)` 계층을 노드로 자른다. 노드는 마커 줄에서 시작한다.

    🔴 **구역을 갈라야 한다** (2026-09-09 실측). 013453 [별표 1] 은 8호까지가 위법 유형이고
       그 뒤에 「비고」가 붙어 **「부당한 표시·광고로 보지 않는다」는 적용 제외 2호**가 온다.
       번호가 1 부터 다시 시작하므로, 구역을 안 가르면 **적용 제외가 위법 유형 1·2호로 읽힌다** —
       「식품접객업 영업소의 표시·광고」가 위법 유형이 되는 것이다. D-153·D-156 의 자리다.

    🚨 구역 전환은 **낱말이 아니라 구조**로 잡는다 — 이미 1호가 나온 뒤에 다시 1호가 오면
       그 자리가 새 구역이다. 「비고」라는 낱말은 **이름을 붙이는 데만** 쓴다 (없으면 번호로 부른다).
    """
    nodes: list[dict] = []
    stack: dict[int, str] = {}
    cur: dict | None = None
    section, section_no, seen_l1 = "본문", 1, False
    label: str | None = None  # 직전에 지나간 마커 없는 짧은 줄 — 구역 이름 후보

    for raw in content.split("\n"):
        if not raw.strip() or HEAD.match(raw.strip()):
            continue
        hit = _marker(raw)
        if hit is None:
            if cur is not None:
                cur["lines"].append(raw.rstrip())
            s = raw.strip()
            # 🚨 「고」를 거르면 안 된다 — **「비고」가 걸린다**(2026-09-09에 실제로 걸렸다).
            #    「…표시ㆍ광고」로 끝나는 줄을 거르려던 것인데 구역 이름을 먹었다.
            if len(s) <= 12 and not s.endswith((".", "다")):
                label = s
            continue
        level, mark = hit
        if level == 1:
            if mark == "1" and seen_l1:
                section_no += 1
                section = label or f"구역{section_no}"
                stack.clear()
                cur = None
            seen_l1 = True
            label = None
        stack[level] = mark
        for deeper in [k for k in stack if k > level]:
            del stack[deeper]
        cur = {
            "section": section,
            "level": level,
            "marker": mark,
            "path": ".".join(stack[k] for k in sorted(stack)),
            "lines": [raw.rstrip()],
        }
        nodes.append(cur)
    return nodes


def build(path: pathlib.Path) -> tuple[dict, list[dict]]:
    d = json.loads(path.read_text(encoding="utf-8"))
    art = ARTICLE.search(d["title"])
    nodes = parse(d["content"])
    rows = []
    for n in nodes:
        joined = "".join(x.strip() for x in n["lines"])
        # 마커를 본문에서 뗀다 — 「1. 질병의…」의 「1. 」
        body = re.sub(r"^[\dA-Za-z①-⑳" + JO + r"]{1,2}[.)]\s*", "", joined, count=1)
        rows.append(
            store.stamp(
                {
                    "law_id": d["law_id"],
                    "annex_no": d["annex_no"],
                    "section": n["section"],
                    "annex_title": d["title"],
                    "article": art.group(1).strip() if art else "",
                    "path": n["path"],
                    "level": n["level"],
                    "text": body,  # 🚨 매칭용. 화면에 그대로 찍지 않는다
                    "lines": n["lines"],  # 🚨 원문 — 화면은 이쪽을 쓴다
                    "chars": len(body),
                },
                "law_go_kr",
            )
        )
    return d, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="[별표] 산문 → 규범 노드 (3층)")
    ap.add_argument("--annex", default=None, help="예: 013453_0001 (생략하면 표 0행 전부)")
    ap.add_argument("--dump", action="store_true", help="노드를 사람이 읽게 찍는다")
    ap.add_argument("--write", action="store_true", help="data/derived/law_norm/ 에 쓴다")
    args = ap.parse_args()

    if not ANNEX.exists():
        print("별표가 없다 — collect.law_annex 를 먼저 돌린다", file=sys.stderr)
        return 1

    total = 0
    for p in sorted(ANNEX.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d["table_rows"]:  # 표는 law_annex 가 맡는다
            continue
        key = f"{d['law_id']}_{d['annex_no']}"
        if args.annex and args.annex != key:
            continue
        _, rows = build(p)
        by_level = {lv: sum(1 for r in rows if r["level"] == lv) for lv in (1, 2, 3, 4, 5)}
        lv = " ".join(f"L{k}:{v}" for k, v in by_level.items() if v)
        print(f"  [{key}] {d['title'][:38]:40} 노드 {len(rows):>3}  {lv}")
        total += len(rows)

        if args.dump:
            for r in rows[:12]:
                print(f"       {r['path']:>10}  {r['text'][:64]}")
        if args.write and rows:
            out = store.derived_dir("law_norm") / f"{key}.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n노드 {total}개")
    print("🚨 `text` 는 매칭용이다 — 화면에는 `lines` 를 쓴다 (D-98 · D-117).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
