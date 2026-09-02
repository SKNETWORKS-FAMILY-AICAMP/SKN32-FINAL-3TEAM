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
# 처분 종류 — 별표 값에서 뽑아야 하는 것 (4층 위험도)
#
#  🚨 **법마다 처분 용어가 다르다** (2026-09-02 실측). 처음 목록은 화장품법 용어뿐이라
#     식품표시광고법 [별표 7]의 처분 칸 197개 중 **160개를 못 잡았다** — 「영업정지」가
#     목록에 없었기 때문이다. 식품 4층이 기간만 남고 처분 종류 없이 비어 있었다.
#
#     화장품법 : 제조업무정지 · 판매업무정지 · 등록취소 · 영업소 폐쇄 · 시정명령
#     식품표시광고법 : **영업정지** · **품목 제조정지** · 품목류 제조정지 ·
#                      영업허가ㆍ등록 취소 · 영업소 폐쇄 · 시정명령
#
#  🚨 **순서가 곧 우선순위다** — `next()` 가 첫 매치를 쓴다. 긴 것·구체적인 것을 앞에 둔다.
#     「품목 제조정지」가 「제조정지」보다, 「영업허가등록취소」가 「등록취소」보다 앞이어야 한다.
#
#  🚨 비교는 **공백을 지운 뒤** 한다(`extract_sanction`). 그래서 여기 항목도 공백 없이 적는다 —
#     「등록취소」와 「등록 취소」를 둘 다 적던 것은 같은 값의 중복이었다.
ACTIONS = [
    # 품목 한정 — 영업 전체보다 먼저 본다
    "품목류제조정지",
    "품목제조정지",
    "품목판매정지",
    "품목업무정지",
    # 업무 종류별 정지 (화장품법)
    "수입대행업무정지",
    "제조업무정지",
    "판매업무정지",
    "광고업무정지",
    # 취소·폐쇄 — 「영업허가ㆍ등록 취소」가 「등록취소」보다 앞이다
    "영업허가등록취소",
    "영업허가취소",
    "영업소폐쇄",
    "등록취소",
    # 영업 전체 정지 (식품표시광고법)
    "영업정지",
    "업무정지",
    # 정지를 수반하지 않는 처분
    "개수명령",
    "시정명령",
    "경고",
]

#: 🚨 처분 어휘 안의 구분자가 **한 문서 안에서도 갈린다** — 실측에서 넷이 나왔다:
#:  `영업허가ㆍ등록취소`(U+318D) · `영업허가·등록취소`(U+00B7) · `영업허가?등록취소`(깨짐) ·
#:  `영업허가등록취소`. 앞의 셋을 지워 하나로 만든 뒤 비교한다 (D-114 의 N1·N2 와 같은 자리).
SEPARATORS = "ㆍ·?？"

#: 부가 처분 — 「영업정지 1개월**과 해당 제품 폐기**」처럼 정지에 딸려 온다.
#: 🚨 `action` 은 하나만 뽑으므로 이것을 종류로 넣으면 주 처분을 덮는다. **별도 축**으로 둔다.
DISPOSAL = ("제품폐기", "음식물폐기", "제품(표시된제품만해당한다)폐기")
DURATION = re.compile(r"(\d+)\s*(일|개월)")

#: 🚨 **논리 행이 `├──┼──┤` 로 갈리지 않는 표가 있다** (2026-09-02 실측).
#:
#:  화장품법 시행규칙 [별표 7] 「행정처분의 기준」은 41,927자 · 셀 줄 480개인데
#:  `├` 가 **머리글 아래 하나뿐**이다. 구분선만 보면 표 전체가 한 덩어리가 되고,
#:  실제로 **2행**으로 잘렸다 — 4층 위험도 라벨의 원천이 통째로 비어 있었다.
#:  (같은 파일의 [별표 9] 수수료는 `├` 가 9개라 정상 동작했다. 그래서 안 보였다.)
#:
#:  이런 표는 **첫 칸의 항목 마커**가 행 경계다:  `가.` `나.` … / `1)` `2)` … / `(1)` …
#:
#:  🚨 오탐이 걱정되는 자리는 하나다 — 접힌 문장이 「…처분한 / 다. 다만,」 처럼
#:     마커처럼 보이는 조각으로 시작하는 경우. 실측으로 확인했다:
#:     [별표 7]에서 잡힌 한글 마커 23개가 **가나다라마바사아자차카타파하거너더러머버서어저**로
#:     정확히 순서다. 순서가 깨진 항목이 하나도 없다 = 오탐이 없다.
#:
#:  🚨 그래도 **완전 복원은 하지 않는다**(D-98). 마커로 자른 행에는 `marker` 를 남겨,
#:     S2-04 의 2인 수동 대조가 어느 행이 휴리스틱으로 잘렸는지 볼 수 있게 한다.
ROW_START = re.compile(r"^(?:[가-힣]\.|\(\d{1,2}\)|\d{1,2}\))\s")

#: 🚨 **`별표번호` 는 유일하지 않다** (2026-09-02 실측). 파일명을 그것 하나로 지으면
#:  덮어쓰기 거부(규약 2)에 걸려 수집이 중간에 죽는다 — 실제로 죽었다.
#:
#:  화장품법 시행규칙(008741) 44건 기준:
#:    · `별표 0001`(품질관리기준)과 `서식 0001`(화장품제조업 등록신청서)이 **번호가 같다**
#:    · 같은 구분 안에서도 겹친다 — `서식 0006` 7건 · `서식 0010` 7건 · `별표 0005` 4건.
#:      이때 갈리는 것이 **`별표가지번호`** 다 (00 · 02 · 03 …)
#:
#:  → 유일 키는 **구분 + 번호 + 가지번호** 다 (44건 중복 0). 파일명이 이 셋을 진다.
#:  🚨 구분은 ASCII 로 적는다. 이 파일명이 manifest 와 derived 경로로 흘러가고,
#:     팀원 5인의 OS 가 갈린다.
KIND_SLUG = {"별표": "annex", "서식": "form"}


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
    marker: str | None = None  # 이 행을 연 항목 마커 (구분선으로 열렸으면 None)

    def flush() -> None:
        nonlocal marker
        if not buf:
            marker = None
            return
        width = max(len(r) for r in buf)
        cols: list[list[str]] = [[] for _ in range(width)]
        for line in buf:
            for i, cell in enumerate(line):
                if cell.strip():
                    cols[i].append(cell.strip())
        if any(cols):
            rows.append(
                {
                    "fragments": cols,
                    "cells": ["".join(c) for c in cols],
                    # 🚨 마커로 잘린 행임을 남긴다 — S2-04 2인 대조가 볼 표시다
                    "marker": marker,
                }
            )
        buf.clear()
        marker = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        head = line.lstrip()[:1]
        if head in BORDER_TOP or head in BORDER_BOT:
            flush()
            continue
        if head in BORDER_MID:
            flush()  # 논리 행 경계 — 구분선이 있는 표
            continue
        if CELL in line:
            parts = line.split(CELL)
            cells = parts[1:-1] if len(parts) > 2 else parts
            # 🚨 구분선이 없는 표의 행 경계 — 첫 칸이 항목 마커로 시작하면 새 행이다
            m = ROW_START.match(cells[0].strip()) if cells else None
            if m:
                flush()
                marker = m.group(0).strip()
            buf.append(cells)

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
    for sep in SEPARATORS:  # 🚨 구분자가 문서 안에서도 갈린다 — 지우고 비교한다
        flat = flat.replace(sep, "")
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
        # 🚨 「영업정지 1개월과 해당 제품 폐기」의 뒷부분. 주 처분을 덮지 않도록 별도 축이다
        "disposal": any(d in flat for d in DISPOSAL),
    }


#: 표 머리글의 첫 칸에 오는 말. 법마다 다르다 — 화장품은 「위반 내용」, 식품은
#: 「위반사항」·「위반행위」다. 공백을 지우고 **정확히 일치**할 때만 머리글로 본다.
HEADER_FIRST = frozenset({"위반내용", "위반사항", "위반행위"})


def _is_header(cells: list[str]) -> bool:
    """머리글 행인가.

    🚨 처음에는 `idx == 0` 인 행만 봤는데, **머리글은 표마다 다시 나온다** —
       식품표시광고법 [별표 7] 하나에 표가 둘이고 머리글이 둘이다
       (「위반사항 · 근거」와 「위반행위 · 근거 법조문」). 둘째가 그대로 데이터 행이 되어
       `article_at` 에 「근거」라는 가짜 조문을 심었다. 위치가 아니라 **내용**으로 본다.

    🚨 「차 위반」·「처분기준」이 들어간 칸을 넓게 잡으면 진짜 위반내용 행이 함께 걸린다
       (실제로 12행이 잡혔고 그중 10행이 데이터였다). 첫 칸 **완전 일치**로 좁힌다.
    """
    if not cells:
        return False
    return cells[0].replace(" ", "") in HEADER_FIRST


def _marker_level(marker: str | None) -> int:
    """항목 마커의 깊이. 조문 상속이 「어디에서 물려받는가」를 이걸로 정한다.

        1  `가.` `나.` `다.` …      상위 항목 — **관련법조문이 여기 붙는다**
        2  `1)` `2)` `10)` …        하위 항목 — **처분값이 여기 붙는다**
        3  `(1)` `(2)` …            더 하위

    🚨 마커 없이 구분선(`├`)으로 잘린 행은 **1** 로 본다. 식품 [별표 7]에 5행 있고
       다섯 다 조문을 스스로 들고 있다 — 상위 항목과 같은 자리다.
    """
    if not marker:
        return 1
    if marker.startswith("("):
        return 3
    return 2 if marker[0].isdigit() else 1


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
        branch = field("별표가지번호") or "00"
        kind = field("별표구분")
        title = field("별표제목")
        content = field("별표내용")
        if not content or title.startswith("삭제"):
            continue

        table = parse_table(content)
        record = {
            "law_id": law_id,
            "annex_no": no,
            "annex_branch": branch,  # 🚨 번호만으로는 유일하지 않다 — 아래 참조
            "kind": kind,
            "title": title,
            "pdf_link": field("별표서식PDF파일링크"),
            "content": content,  # 🚨 원문 보존 (D-84 ①)
            "table_rows": len(table),
        }

        print(f"  [{kind} {no}-{branch}] {title[:38]}  · {len(content):,}자 · 표 {len(table)}행")

        if dry_run:
            continue

        path = store.save_raw(
            SOURCE_ID,
            "law/annex",
            f"{law_id}_{KIND_SLUG.get(kind, 'etc')}_{no}_{branch}.json",
            json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"),
            url=f"{law_api.BASE_SERVICE}?target=law&ID={law_id}",
            rows=len(table),
        )
        if path is not None:
            saved += 1

        # 🚨 관련법조문은 **상위 항목에만 붙는다** (2026-09-02 실측).
        #    `가.` 행이 「법 제24조제1항제1호」를 들고, 처분값을 실제로 가진 `1)` 하위 행은
        #    그 칸이 비어 있다. 화장품 23/23 · 식품 33/33 이 상위에 있고 하위는 0 이다.
        #    그대로 두면 **처분값 47행이 조문과 이어지지 않는다** — 4층 라벨이 근거를 잃는다.
        #    그래서 가장 가까운 상위 레벨에서 물려받되, **물려받았다는 사실을 남긴다.**
        article_at: dict[int, str] = {}

        for row in table:
            cells = row["cells"]
            if _is_header(cells):
                continue
            sanctions = [extract_sanction(c) for c in cells[2:]] if len(cells) > 2 else []

            article = cells[1] if len(cells) > 1 else ""
            level = _marker_level(row.get("marker"))
            inherited = False
            if article.strip():
                article_at[level] = article
                # 아래 레벨의 기억은 버린다 — 새 상위 항목이 시작됐다
                for deeper in [k for k in article_at if k > level]:
                    del article_at[deeper]
            else:
                parent = max((k for k in article_at if k < level), default=None)
                if parent is not None:
                    article, inherited = article_at[parent], True
            parsed_rows.append(
                store.stamp(
                    {
                        "law_id": law_id,
                        # 🚨 셋이 함께 있어야 어느 별표의 행인지 정해진다 (KIND_SLUG 참조).
                        #    `annex_no` 하나만 쓰면 **별표 0007(행정처분 72행)과
                        #    서식 0007(심사의뢰서 12행)이 한 덩어리가 된다** — 실제로 됐다.
                        #    4층 라벨을 뽑을 때 신청서 행이 처분 행에 섞인다.
                        "kind": kind,
                        "annex_no": no,
                        "annex_branch": branch,
                        "title": title,
                        "violation": cells[0] if cells else "",
                        "article": article,
                        # 🚨 상위 항목에서 물려받은 조문인지 — 2인 대조가 볼 표시다
                        "article_inherited": inherited,
                        "sanctions": [s for s in sanctions if s],
                        "marker": row.get("marker"),  # 🚨 마커로 잘린 행인지 (2인 대조용)
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
