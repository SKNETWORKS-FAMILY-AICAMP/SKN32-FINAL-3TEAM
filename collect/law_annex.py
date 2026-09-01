"""collect/law_annex.py — [별표] 수집·파싱 (S2-04 · D-98).

  uv run python -m collect.law_annex --law 008741            # 화장품법 시행규칙
  uv run python -m collect.law_annex --law 008741 --dry-run

🚨 XML 파서로 짠다. 정규식으로 구조를 다루지 않는다 (D-98 교훈) —
   `<별표[^>]*>` 는 `<별표번호>` 에 매칭되고, `<[^>]+>` 는 CDATA 를 통째로 삼킨다.
   `xml.etree` 로 `<별표내용>` 을 `.text` 로 꺼내면 두 오류가 정의상 발생하지 않는다.

산출
  data/raw/law/annex/{law_id}_{번호}.json      원문 보존 (별표 메타 + 내용 전문)
  data/derived/law_annex/{law_id}.jsonl        파싱된 행
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

from collect import env, law_api, registry, store

SOURCE_ID = "law_go_kr"

# 괘선 문자 — 표의 구조를 이것으로만 판단한다
BORDER_TOP = "┌┬┐"
BORDER_MID = "├┼┤"
BORDER_BOT = "└┴┘"
CELL = "│"

# 처분 종류 — 별표 값에서 뽑아야 하는 것 (4층 위험도)
ACTIONS = [
    "등록취소",
    "등록 취소",
    "영업소 폐쇄",
    "영업소폐쇄",
    "시정명령",
    "개수명령",
    "경고",
    "수입대행업무정지",
    "품목업무정지",
    "제조업무정지",
    "판매업무정지",
    "광고업무정지",
    "업무정지",
]
DURATION = re.compile(r"(\d+)\s*(일|개월)")


def parse_table(text: str) -> list[dict]:
    """고정폭 ASCII 괘선 표를 논리 행으로 자른다.

    🚨 열 경계를 「문자 위치」로 잡지 않는다. 한글은 폭 2, 문자 수 1 이라
       줄마다 문자 인덱스가 어긋난다. **`│` 로 쪼갠다.**

    🚨 셀이 여러 물리 줄에 걸치고 **단어 중간에서 끊긴다** —
       「제조업무정 / 지 1개월」. 공백으로 이으면 값이 깨지므로 **공백 없이** 잇는다.
       다만 「제조 또는 / 판매업무」처럼 공백이 필요한 경우와 구분할 수 없다.
       ★ 그래서 조각(fragments)을 그대로 남기고, 필요한 값은 정규식으로 뽑는다.
         완전 복원은 하지 않는다 — S2-04 의 「2인 수동 대조」가 그 자리다.
    """
    rows: list[dict] = []
    buf: list[list[str]] = []

    def flush() -> None:
        if not buf:
            return
        width = max(len(r) for r in buf)
        cols: list[list[str]] = [[] for _ in range(width)]
        for line in buf:
            for i, cell in enumerate(line):
                if cell.strip():
                    cols[i].append(cell.strip())
        if any(cols):
            rows.append({"fragments": cols, "cells": ["".join(c) for c in cols]})
        buf.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        head = line.lstrip()[:1]
        if head in BORDER_TOP or head in BORDER_BOT:
            flush()
            continue
        if head in BORDER_MID:
            flush()  # 논리 행 경계
            continue
        if CELL in line:
            parts = line.split(CELL)
            buf.append(parts[1:-1] if len(parts) > 2 else parts)

    flush()
    return rows


def extract_sanction(cell: str) -> dict | None:
    """처분 셀에서 「범위 + 종류 + 기간」을 뽑는다. 공백 복원과 무관하게 동작한다.

    ★ 이것이 공백 모호성을 우회하는 지점이다 — 우리가 필요한 것은
      문장 복원이 아니라 **구조화된 값**이다.

    🚨 `scope` 를 빠뜨리면 안 된다. 「해당 품목 판매업무정지」와 「판매업무정지」는
       **범위가 다르다** — 앞은 품목 하나, 뒤는 영업 전체다. 4층 위험도가 이 둘을
       같게 보면 예상 제재 수준이 통째로 어긋난다.
    """
    if not cell:
        return None
    flat = cell.replace(" ", "")
    action = next((a for a in ACTIONS if a.replace(" ", "") in flat), None)
    m = DURATION.search(cell)
    if not action and not m:
        return None

    days = None
    if m:
        n, unit = int(m.group(1)), m.group(2)
        # 🚨 근사다. 법령의 「개월」은 역월이지만 여기서는 30일로 환산한다.
        #    비교·정렬 용도이며, 실제 처분일 계산에 쓰지 않는다.
        days = n if unit == "일" else n * 30

    # 「해당 품목 판매업무정지」 · 「품목업무정지」 는 품목 한정,
    # 그냥 「판매업무정지」 는 영업 전체다. 공백이 뭉개져도 「품목」 유무로 갈린다.
    scope = "품목" if "품목" in flat else "영업"

    return {
        "scope": scope,  # 품목 한정 / 영업 전체
        "action": action,
        "duration_raw": m.group(0) if m else None,
        "duration_days": days,
        "duration_is_approx": bool(m and m.group(2) == "개월"),
    }


def collect_annex(law_id: str, *, dry_run: bool = False) -> int:
    registry.require(SOURCE_ID, use="U1")
    oc = env.get("LAW_OC_KEY")

    body = law_api._call(law_api.BASE_SERVICE, oc, target="law", ID=law_id)
    try:
        root = ET.fromstring(body.decode("utf-8", "replace"))
    except ET.ParseError as e:
        raise SystemExit(f"🚨 XML 파싱 실패 — OC 를 확인하라: {e}") from e

    units = root.iter("별표단위")
    saved = 0
    parsed_rows: list[dict] = []

    for unit in units:

        def field(name: str, u: ET.Element = unit) -> str:
            el = u.find(name)
            return (el.text or "").strip() if el is not None and el.text else ""

        no = field("별표번호")
        title = field("별표제목")
        content = field("별표내용")
        if not content or title.startswith("삭제"):
            continue

        table = parse_table(content)
        record = {
            "law_id": law_id,
            "annex_no": no,
            "kind": field("별표구분"),
            "title": title,
            "pdf_link": field("별표서식PDF파일링크"),
            "content": content,  # 🚨 원문 보존 (D-84 ①)
            "table_rows": len(table),
        }

        print(f"  [별표 {no}] {title[:40]}  · {len(content):,}자 · 표 {len(table)}행")

        if dry_run:
            continue

        path = store.save_raw(
            SOURCE_ID,
            "law/annex",
            f"{law_id}_{no}.json",
            json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"),
            url=f"{law_api.BASE_SERVICE}?target=law&ID={law_id}",
            rows=len(table),
        )
        if path is not None:
            saved += 1

        for idx, row in enumerate(table):
            cells = row["cells"]
            # 🚨 첫 행은 헤더다. 병합 셀 때문에 「처분기준1차 위반」처럼 뭉쳐 나온다.
            if idx == 0 and any("위반 내용" in c or "처분기준" in c for c in cells):
                continue
            sanctions = [extract_sanction(c) for c in cells[2:]] if len(cells) > 2 else []
            parsed_rows.append(
                store.stamp(
                    {
                        "law_id": law_id,
                        "annex_no": no,
                        "violation": cells[0] if cells else "",
                        "article": cells[1] if len(cells) > 1 else "",
                        "sanctions": [s for s in sanctions if s],
                        "fragments": row["fragments"],  # 🚨 조각 보존 — 2인 대조용
                        "needs_review": True,  # S2-04
                    },
                    SOURCE_ID,
                )
            )

    if parsed_rows and not dry_run:
        out = store.derived_dir("law_annex") / f"{law_id}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for r in parsed_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n  💾 파싱 {len(parsed_rows)}행 → {out.relative_to(store.ROOT)}")

    return saved


def main() -> int:
    ap = argparse.ArgumentParser(description="[별표] 수집·파싱 (S2-04 · D-98)")
    ap.add_argument("--law", default="008741", help="법령 ID (기본: 화장품법 시행규칙)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        saved = collect_annex(args.law, dry_run=args.dry_run)
    except (registry.RegistryError, env.MissingKey) as e:
        print(f"\n수집을 시작할 수 없다 —\n{e}\n", file=sys.stderr)
        return 1

    print(f"\n새로 저장 {saved}건")
    print("🚨 S2-04 는 2인 수동 대조가 필수다 — needs_review 가 그 표시다 (D-98).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
