"""preprocess/law_article.py — 법령·행정규칙 **조문 본문** → 3층 판단규범.

  uv run python -m preprocess.law_article            # 센다
  uv run python -m preprocess.law_article --dump     # data/derived/law_article.jsonl

왜 있는가 — `data/raw/law/` 에 법령 9 · 행정규칙 11 이 2026-09-02 부터 있었는데
**아무도 안 읽고 있었다**(2026-09-09 확인). 3층에 실제로 들어간 것은 같은 날 만든
`law_norm.py` 의 별표 노드 300개가 전부였다. 위임의 근거인 **조문 본문이 없었다.**

🚨 별표와 다르다 — `<조문내용>` 은 CDATA 산문이고 **고정폭으로 접혀 있지 않다.**
   그래서 `law_norm.py` 의 줄 이어붙이기 문제가 여기에는 없다.

구조 — `<조문단위>` 안에 `<조문번호>` `<조문제목>` `<조문내용>`, 그 아래 `<항> <호> <목>`.
행정규칙(`AdmRulService`)은 `<조문내용>` 만 평평하게 온다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import xml.etree.ElementTree as ET
from datetime import date

from collect import store

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = "law_go_kr"
# 🆕 D-254 — 폴더 이름은 store.FAMILY_OF 에서만 꺼낸다 (D-99 · 감사 §1-7)
LAW = store.family_path(SOURCE)
# 🚨 판례·재결례는 다른 모듈이 맡는다 — 여기서 섞으면 「조문」과 「사건」이 한 파일에 섞인다
PREFIX = ("law_", "admrul_")


# 조문 형식이 아닌 행정규칙의 마커 — 「Ⅰ. → 1. → 가. → (1)」
_JO = "가나다라마바사아자차카타파하"
_PROSE = (
    ("장", re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\.\s*(.*)$")),
    ("절", re.compile(r"^(\d{1,2})\.\s*(.*)$")),
    ("목", re.compile(rf"^([{_JO}])\.\s*(.*)$")),
    ("세목", re.compile(r"^\((\d{1,2})\)\s*(.*)$")),
)


def _prose(text: str) -> list[dict]:
    """마커로 절을 자른다. 고정폭이 아니라 `\n` 으로 접힌 산문이다."""
    rows: list[dict] = []
    stack: dict[str, str] = {}
    cur: dict | None = None
    # 🔴 **최상위 마커가 문서 안에서 다시 쓰인다** (2026-09-09 실측).
    #    「부당한 표시·광고행위의 유형 및 기준 지정고시」는 본문이 Ⅰ~Ⅲ 으로 가고
    #    그 뒤 부칙 쪽이 다시 Ⅲ 부터 시작한다 — 「Ⅲ. 표시·광고에 관한 일반지침」과
    #    「Ⅲ. 재검토기한」이 **같은 키**가 됐다.
    #    law_norm.py 의 「비고」와 같은 부류다. 같은 규칙으로 구역을 가른다.
    seen_top: set[str] = set()
    section = 1
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        hit = next(((k, p.match(s)) for k, p in _PROSE if p.match(s)), None)
        if hit is None:
            if cur is not None:
                cur["본문"] += " " + s
            continue
        kind, m = hit
        order = ["장", "절", "목", "세목"]
        if kind == "장":
            if m.group(1) in seen_top:
                section += 1
                stack.clear()
            seen_top.add(m.group(1))
        stack[kind] = m.group(1)
        for deeper in order[order.index(kind) + 1 :]:
            stack.pop(deeper, None)
        cur = {
            "키": f"prose-{len(rows)}",
            "조": stack.get("장", ""),
            "가지": "",
            "제목": m.group(2)[:40],
            "항": (f"{section}:" if section > 1 else "")
            + ".".join(stack[k] for k in order if k in stack),
            "본문": s,
        }
        rows.append(cur)
    return rows


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None and el.text else ""


def _title(root: ET.Element) -> str:
    for tag in ("법령명_한글", "행정규칙명", "법령명한글"):
        v = _text(root.find(f".//{tag}"))
        if v:
            return v
    return ""


def parse(path: pathlib.Path) -> list[dict]:
    root = ET.parse(path).getroot()
    name = _title(root)
    rows: list[dict] = []

    units = list(root.iter("조문단위"))
    if units:
        # 🚨 **키는 조립하지 않고 원천이 주는 것을 쓴다** (2026-09-09).
        #    ⛔ 조·가지·항·호를 이어붙여 키를 만들다가 **네 번 겹쳤다** —
        #       ① 「제1장 총칙」이 조문으로 들어와 `제조` 로 뭉침
        #       ② 행정규칙 최상위 마커 Ⅲ 가 본문과 부칙에서 두 번
        #       ③ 제7조 와 제7조의2 (가지번호를 항·호에 안 넘김)
        #       ④ 호번호 「2」와 「2의2」가 둘 다 `2.` 로 옴
        #    고칠 때마다 다음 것이 나왔다. `<조문단위 조문키="0007021">` 이 이미 유일하다.
        #    **원천이 유일 키를 주면 그것을 쓴다.**
        for u in units:
            unit_key = u.attrib.get("조문키", "")
            no = _text(u.find("조문번호"))
            # 🔴 **가지번호를 항·호에도 넣어야 한다** (2026-09-09 실측).
            #    ⛔ 조문 행에만 넣고 항·호는 비워 뒀더니 **제7조①과 제7조의2① 이 같은 키**가 됐다.
            #       청크 게이트가 잡았다 — 안 잡았으면 조용히 덮였다 (D-149).
            branch = _text(u.find("조문가지번호"))
            body = _text(u.find("조문내용"))
            head = _text(u.find("조문제목"))
            if _text(u.find("조문여부")) == "전문":  # 편·장·절 제목 줄
                continue
            rows.append(
                {
                    "조": no,
                    "가지": _text(u.find("조문가지번호")),
                    "제목": head,
                    "항": "",
                    "본문": body,
                }
            )
            for hi, hang in enumerate(u.iter("항")):
                hno = _text(hang.find("항번호"))
                hbody = _text(hang.find("항내용"))
                if hbody:
                    rows.append(
                        {
                            "조": no,
                            "가지": branch,
                            "제목": head,
                            "항": hno,
                            # 🔴 **원문에 항번호가 없어도 항은 있다** (2026-09-12).
                            #    법제처 XML 은 항이 하나뿐인 조에 `<항번호>` 를 주지 않는다.
                            #    「①」를 지어내지 않고 **우리가 센 서수를 옆 칸에** 둔다 (D-117).
                            "항서수": hi + 1,
                            "본문": hbody,
                            "키": f"{unit_key}-{hi}",
                        }
                    )
                for oi, ho in enumerate(hang.iter("호")):
                    hono = _text(ho.find("호번호"))
                    hobody = _text(ho.find("호내용"))
                    if hobody:
                        rows.append(
                            {
                                "조": no,
                                "가지": branch,
                                "제목": head,
                                # 🔴 **항과 호를 한 칸에 뭉치지 않는다** (2026-09-12).
                                #    ⛔ 종전에는 `f"{hno}{hono}"` 로 「①1.」을 만들었다.
                                #       그러면 `chunk.paragraph` 에 두 층이 들어가고
                                #       **「제8조제1항제1호」로 조립할 수 없다** — D-224 이
                                #       요구하는 근거 인용이 데이터에서 나오지 않는다.
                                #    🚨 뭉친 라벨은 뭉친 채로 굳는다 (D-151 · D-167).
                                "항": hno,
                                "호": hono,
                                "항서수": hi + 1,
                                # 🔴 **호는 항 없이 뜻이 없다** — 「1. 마약」은 앞의
                                #    「① …제조·수입하여서는 아니 된다」가 있어야 읽힌다.
                                #    ⛔ `chunk.py` 가 부모를 되찾게 두지 않는다 — 여기서는
                                #       `hbody` 가 손에 있고, 되찾는 규칙은 별표와 달라
                                #       **두 벌이 된다** (D-99).
                                "항본문": hbody,
                                "본문": hobody,
                                "키": f"{unit_key}-{hi}-{oi}",
                            }
                        )
    else:  # 행정규칙
        chunks = [(el.text or "").strip() for el in root.iter("조문내용")]
        chunks = [c for c in chunks if c]
        # 🔴 **조문 형식이 아닌 행정규칙이 있다** (2026-09-09 실측).
        #    `조문형식여부: N` 인 것은 `<조문내용>` **하나에 전문이 통째로** 온다 —
        #    「비교표시·광고 심사지침」10,229자 · 「부당한 표시·광고행위의 유형 및 기준
        #    지정고시」23,120자. 조문 정규식으로 받으면 **1행**이 나오고, 그 1행이
        #    3층의 핵심 여섯 건이었다.
        #    🚨 「없는 것」과 「못 뽑은 것」을 같은 1 로 적지 않는다 (mfds_hf.py 의 교훈).
        if _text(root.find(".//조문형식여부")) != "Y" and len(chunks) <= 2:
            for c in chunks:
                rows += _prose(c)
        else:
            for body in chunks:
                # 🔴 **편장절 제목은 조문이 아니다** (2026-09-09 실측).
                #    「제1장  총칙」이 조문 정규식에 안 맞아 조 번호가 빈 문자열이 되고,
                #    청크 키가 `제조` 로 뭉쳐 **한 법령에서 6건이 한 키로 겹쳤다.**
                if re.match(r"^제\s*\d+\s*[장절관편]\s", body):
                    continue
                m = re.match(r"제(\d+)조(?:의(\d+))?\s*\(([^)]*)\)", body)
                rows.append(
                    {
                        "키": f"adm-{len(rows)}",
                        "조": m.group(1) if m else "",
                        "가지": m.group(2) if m and m.group(2) else "",
                        "제목": m.group(3) if m else "",
                        "항": "",
                        "본문": body,
                    }
                )

    # 🔴 **원천이 본문을 안 주는 것이 있다** (2026-09-09 실측).
    #    `admrul_34650` 「건강기능식품의 기준 및 규격」의 `<조문내용>` 은 73자다 —
    #    「자세한 내용은 상단 메뉴 … 버튼을 이용하십시오」 + 첨부 ZIP.
    #    🚨 **없는 것과 못 뽑은 것을 같은 1 로 적지 않는다.** 여기서 표시하지 않으면
    #       「1행 뽑혔다」로 지나가고, 2층 적법라벨의 근거 고시가 빈 채로 남는다.
    if len(rows) == 1 and re.search(r"자세한 내용은|버튼을 이용", rows[0]["본문"]):
        rows[0]["본문없음"] = "원천이 본문 대신 첨부를 준다 — 별도 확보가 필요하다"

    out = []
    for r in rows:
        r["법령"] = name
        r["파일"] = path.name
        r["층"] = "3층 판단규범"
        out.append(store.stamp(r, SOURCE))
    return out


_EFF = re.compile(r"_(\d{8})$")


def split_in_force(
    files: list[pathlib.Path], today: str
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """파일명의 시행일(`{target}_{ID}_{시행일}.xml`)로 (시행 중, 시행 전) 을 가른다.

    🔴 2026-09-25 — 법제처 본문 조회가 「식품등의 표시기준」(36814)에 **시행 전 판(20280101)** 을 줬다.
       조문 노드로 풀면 2028 기준이 지금 기준으로 검색·판정에 들어간다 → 시행 전 판은 **싣지 않고 이름을 찍는다**
       (D-290 ③ 기준 시점 · D-220 — 조용히 넣지도 조용히 버리지도 않는다). 원문은 그대로 남는다(규약 2).
    🔴 시행일을 못 읽는 이름은 **멈춘다** — `collect.law_api` 는 시행일 없는 응답을 저장하지 않으므로(09-25 원장
       실측 20건 전부 날짜가 있다) 그런 이름은 손으로 넣은 파일이다. 시행 중으로 치면 fail-open 이다 (D-220).
    """
    now: list[pathlib.Path] = []
    later: list[pathlib.Path] = []
    for p in files:
        m = _EFF.search(p.stem)
        if m is None:
            raise SystemExit(
                f"🔴 파일명에서 시행일을 못 읽었다: {p.name} — `{{target}}_{{ID}}_{{시행일}}.xml` 이어야 한다"
            )
        (later if m.group(1) > today else now).append(p)
    return now, later


def main() -> int:
    ap = argparse.ArgumentParser(description="법령·행정규칙 조문 본문 → 3층")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    files = [p for p in store.current_files(LAW, "*.xml") if p.name.startswith(PREFIX)]
    files, later = split_in_force(files, date.today().strftime("%Y%m%d"))
    for p in later:
        print(f"  🚨 시행 전 판 — 싣지 않는다: {p.name} (사람이 부칙을 보고 정한다 · D-290 ③)")
    if not files:
        print("조문 원문이 없다 — collect.law_api 를 먼저 돌린다")
        return 1

    all_rows: list[dict] = []
    for p in files:
        rows = parse(p)
        all_rows += rows
        flag = " 🔴 원천에 본문이 없다(첨부만)" if rows and rows[0].get("본문없음") else ""
        print(f"  {p.name:32} {len(rows):>4}행  {rows[0]['법령'][:34] if rows else ''}{flag}")

    print(f"\n조문 노드 {len(all_rows)}개 · 법령 {len(files)}건")
    if args.dump:
        out = store.derived_dir(".") / "law_article.jsonl"
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for r in all_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"💾 → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
