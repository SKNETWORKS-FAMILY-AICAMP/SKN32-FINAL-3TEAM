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


# 조문 형식이 아닌 행정규칙의 마커 — 「Ⅰ.」 아래는 별표와 **같은 표**를 쓴다(`law_norm.LEVELS` · D-99)
#: 🔄 2026-09-27 — 종전에는 「Ⅰ. → 1. → 가. → (1)」 넷만 알았다. 식품등의 표시기준(36814)은
#:    「가. 조미식품 → 1) 유형 → 가) 식초류 · 2) 표시사항 → (1) 제품명」 으로 `1)` `가)` 를 쓴다 —
#:    그 둘을 몰라 **계층이 납작해졌고**(본문에 `1)` `가)` 가 묻힌 청크 103), 표시사항 목록 「(1) 제품명」 이
#:    식품 유형마다 부모 없이 되풀이되어 **본문이 같은 청크가 91**(「(1) 부정ㆍ불량식품신고표시」 22)이 됐다 —
#:    짧고 같은 청크가 벡터 상위를 차지했다(사실원장 ㉟ · D-195 와 같은 병). 별표 파서가 09-26 에 겪고 고친 병이다.
_ROMAN = re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\.\s*(.*)$")
#: 장(Ⅰ.)의 순위 — `law_norm.RANK` 의 어느 모양보다 얕다
_TOP = -1


def _prose(text: str) -> list[dict]:
    """마커로 절을 자른다. 고정폭이 아니라 `\n` 으로 접힌 산문이다.

    🔄 2026-09-27 — 「Ⅰ.」 아래 계층은 `law_norm` 의 모양 표 · 순위 · 역순 규칙을 그대로 쓴다(`reverse_child` —
       고시는 번호 순서를 거꾸로 쓴다 · 09-26 전수 6곳이 모두 자식이었다). 뒤집은 노드는 `역순` 을 단다.
    🆕 각 행에 **상위 항목의 본문**(`상위`)을 싣는다 — 「(1) 제품명」 은 「파. 조미식품 › 2) 표시사항」 이 있어야 읽힌다.
       `chunk._context` 가 문맥으로 쓴다(별표 `_annex_context` 와 같은 처방 · 검색이 보고 화면이 보여 주는 한 값 · D-99).
       ⛔ 종전 문맥은 「제목 = 자기 본문 앞 40자」라 **자기 본문을 되풀이**했다(36814 107청크).
    """
    # law_norm 이 이 모듈을 늦게 부른다(순환 회피)
    from preprocess import law_norm as ln  # noqa: PLC0415

    rows: list[dict] = []
    stack: list[tuple[int, str, int]] = []  # (순위, 마커, rows 의 자리) — 바깥에서 안으로
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
        m = _ROMAN.match(s)
        if m:
            rank, mark, reversed_ = _TOP, m.group(1), False
            if mark in seen_top:
                section += 1
            seen_top.add(mark)
            stack = []
        else:
            hit = ln._marker(s)  # noqa: SLF001 — 모양 표의 정본은 law_norm 하나다 (D-99)
            if hit is None:
                if cur is not None:
                    cur["본문"] += " " + s
                continue
            level, mark = hit
            rank, reversed_ = ln.RANK[level], False
            ranks = [x[0] for x in stack]
            if rank in ranks:  # 같은 모양 — 그 자리의 형제
                stack = stack[: ranks.index(rank)]
            elif stack and rank < stack[-1][0]:
                reversed_ = True  # 거꾸로 쓴 순서 — 자식으로 둔다 (`law_norm.parse(reverse_child=True)` 와 같다)
        parents = [rows[i] for _, _, i in stack]
        stack.append((rank, mark, len(rows)))
        top = parents[0] if parents and stack[0][0] == _TOP else None
        cur = {
            "키": f"prose-{len(rows)}",
            "조": stack[0][1] if stack[0][0] == _TOP else "",
            "가지": "",
            # 🔄 제목은 **장(Ⅰ.) 머리 줄**이다 — 종전 「자기 본문 앞 40자」는 문맥에서 자기를 되풀이했다
            "제목": (top["본문"] if top else "")[:40],
            "항": (f"{section}:" if section > 1 else "") + ".".join(x[1] for x in stack),
            "본문": s,
            "_상위": [i for _, _, i in stack[:-1] if rows[i] is not top],
        }
        if reversed_:
            cur["역순"] = True
        rows.append(cur)
    for r in rows:
        # 상위 항목 본문 — 장 머리 줄은 `제목` 이 이미 들고 있다
        r["항본문"] = "\n".join(rows[i]["본문"] for i in r.pop("_상위"))
    return rows


def _ho_number(ho: ET.Element) -> str:
    """호 번호 — 「3.」 · 가지번호가 있으면 「3의2.」 (🆕 2026-09-28 · 사실원장 ㊴).

    ⛔ 종전에는 `<호번호>` 만 읽었다. 법제처 XML 은 「3의2」를 `<호번호>3.</호번호>` + `<호가지번호>2</호가지번호>` 로
       준다 — 가지번호를 버리면 **「3의2. 맞춤형화장품」이 「제3호」로 인용된다**(화장품법 제2조 · 4의2 등 법령 4건 63곳).
       키는 원천의 `조문키` + 순번이라 겹치지 않았고, 그래서 아무 게이트에도 안 걸렸다.
    """
    no = _text(ho.find("호번호"))
    branch = _text(ho.find("호가지번호"))
    if not branch:
        return no
    return f"{no.rstrip('.')}의{branch}."


def _ho_body(ho: ET.Element) -> str:
    """호 본문 + **그 아래 목 전부** (🆕 2026-09-28 · 사실원장 ㊴).

    ⛔ 종전에는 `<호내용>` 만 읽어 `<목>` 이 **통째로 빠졌다** — 법령 9건 목 159개가 청크 어디에도 없었다
       (화장품법 제2조제2호 기능성화장품의 범위 가~목 · 식품표시광고법 21 · 시행규칙 83 …).
       「다음 각 목의 화장품을 말한다」만 남고 각 목이 없는 호는 **근거가 되지 못한다.**
    ★ 목은 **호 본문에 잇는다** — 따로 청크로 두지 않는다. 목은 대개 짧은 목록이라 따로 두면 짧은 청크(D-195)가 되고,
       인용은 호까지 선다(목 좌표를 세우려면 `chunk` 칸과 `citation()` 을 같이 넓혀야 한다 — 이번에 안 했다).
    🚨 호가 「삭제」면 목도 잇지 않는다 — 삭제 표지는 청킹에서 빠진다(`chunk.skip_reason`).
    """
    body = _text(ho.find("호내용"))
    moks = [_text(m.find("목내용")) for m in ho.iter("목")]
    moks = [m for m in moks if m]
    if not body or not moks:
        return body
    return "\n".join([body, *moks])


#: 🆕 2026-09-28 — 조문형식 행정규칙의 조 본문 안 마커(사실원장 ㊴). 줄 머리만 본다 — 줄 중간의 「1.」은 인용 글이다
_ADM_HANG = re.compile(r"^([①-⑳])\s*")
_ADM_HO = re.compile(r"^([0-9]+)(?:의([0-9]+))?\.\s")


def _adm_article(body: str, base: dict, key: str) -> list[dict]:
    """조문형식 행정규칙의 조 하나 → 조 · 항 · 호 행 (🆕 2026-09-28 · 사실원장 ㊴).

    ⛔ 종전에는 조 본문 **통째로 한 행**이었다. 69549 「식품등의 부당한 표시 또는 광고의 내용 기준」 제2조(호 6 · 목 25 ·
       예시)는 700자로 잘려 11조각이 되고 **11조각 모두 「제2조」로 인용됐다** — 「무보존료」 광고의 근거가 제2조제3호나목인지
       알 수 없다. 법령은 XML 이 항 · 호를 주지만 행정규칙은 조 본문 한 덩이로 준다.
    ★ 법령 갈래와 **같은 모양의 행**을 낸다 — 항(`항` · `항서수`) · 호(`호` · `항본문`) · 목과 (예시) 줄은 **호 본문에 잇는다**
       (법령 갈래의 `_ho_body` 와 같은 판단). 인용은 `retrieve.citation()` 이 그대로 조립한다.
    🚨 줄 머리의 마커만 본다 — 원문에 줄바꿈이 없으면 나누지 않는다(종전과 같은 한 행). 조 행의 키는 종전 그대로(`adm-N`).
    🚨 호가 항 없이 조 바로 아래에 오면 **항서수 1** 이다 — 법령 갈래와 같은 규칙(항이 하나뿐인 조 · `retrieve.citation`).
    """
    lines = [x.strip() for x in body.split("\n")]
    first = lines[0] if lines else ""
    # 머리 줄 안의 「①」 — 「제2조(정의) ① 이 고시에서 …」
    mt = re.match(r"(제[0-9]+조(?:의[0-9]+)?\s*\([^)]*\))\s*([①-⑳].*)$", first)
    head = [mt[1]] if mt else [first]
    rest = ([mt[2]] if mt else []) + lines[1:]
    hangs: list[dict] = []  # {"항": 마커, "lines": [...], "호": [{"호": 번호, "lines": [...]}]}
    for ln in rest:
        if not ln:
            continue
        mh = _ADM_HANG.match(ln)
        mo = _ADM_HO.match(ln)
        if mh:
            hangs.append({"항": mh[1], "lines": [ln], "호": []})
        elif mo:
            if not hangs:
                hangs.append({"항": "", "lines": [], "호": []})  # 번호 없는 제1항 — 본문은 머리 줄
            no = f"{mo[1]}의{mo[2]}." if mo[2] else f"{mo[1]}."
            hangs[-1]["호"].append({"호": no, "lines": [ln]})
        elif hangs and hangs[-1]["호"]:
            hangs[-1]["호"][-1]["lines"].append(ln)
        elif hangs:
            hangs[-1]["lines"].append(ln)
        else:
            head.append(ln)
    if not hangs:  # 나눌 마커가 없다 — 종전과 같은 한 행
        return [{"키": key, **base, "항": "", "본문": body}]
    out = [{"키": key, **base, "항": "", "본문": "\n".join(head)}]
    for hi, h in enumerate(hangs):
        hbody = "\n".join(h["lines"]) if h["lines"] else "\n".join(head)
        if h["lines"]:
            out.append(
                {"키": f"{key}-{hi}", **base, "항": h["항"], "항서수": hi + 1, "본문": hbody}
            )
        for oi, ho in enumerate(h["호"]):
            out.append(
                {
                    "키": f"{key}-{hi}-{oi}",
                    **base,
                    "항": h["항"],
                    "호": ho["호"],
                    "항서수": hi + 1,
                    "항본문": hbody,
                    "본문": "\n".join(ho["lines"]),
                }
            )
    return out


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
                    hono = _ho_number(ho)
                    hobody = _ho_body(ho)
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
            ai = 0  # 조 행의 순번 — 🚨 키가 이것이다. 항 · 호 행을 더해도 조 행의 키가 밀리지 않게 따로 센다
            for body in chunks:
                # 🔴 **편장절 제목은 조문이 아니다** (2026-09-09 실측).
                #    「제1장  총칙」이 조문 정규식에 안 맞아 조 번호가 빈 문자열이 되고,
                #    청크 키가 `제조` 로 뭉쳐 **한 법령에서 6건이 한 키로 겹쳤다.**
                if re.match(r"^제\s*\d+\s*[장절관편]\s", body):
                    continue
                m = re.match(r"제(\d+)조(?:의(\d+))?\s*\(([^)]*)\)", body)
                base = {
                    "조": m.group(1) if m else "",
                    "가지": m.group(2) if m and m.group(2) else "",
                    "제목": m.group(3) if m else "",
                }
                rows += _adm_article(body, base, f"adm-{ai}")
                ai += 1

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

#: 🆕 2026-09-25 팀장 판정 (나) — **시행 전 판인데 싣는 파일**. 사람이 부칙 · 제개정이유를 읽고 적는다.
#:    `근거` — 왜 실어도 되는가 · `시행예정` — 시행 전인 조항을 찾는 원문 글귀(그 조항 노드에 표시를 붙인다)
#:    🔴 글귀가 어느 노드에도 없으면 **멈춘다** — 판이 바뀌어 표시가 조용히 빠지는 것을 막는다 (D-220).
#:    ⬜ D 번호 없음 — 초안 `docs/ohb/D초안_2026-09-25_시행_전_판.md`. ⛔ D-290 ③ 이 아니다(③ 은 옛 판이다).
PENDING_ALLOWED: dict[str, dict] = {
    "admrul_36814_20280101.xml": {
        "근거": (
            "식품등의 표시기준 제2026-37호(2026-05-12 발령) — 부칙 제1조 2028-01-01 시행 · 제2조 미리 적용 가능 · "
            "제개정이유 주요내용 2(커피 탈카페인 · 주류협업제품) — 그 밖 조항은 종전과 같은 글"
        ),
        "표시": (
            "2028-01-01 시행 예정(식품등의 표시기준 제2026-37호) · 부칙 제2조로 미리 적용할 수 있고, "
            "그 전에 종전 기준으로 만든 제품은 소비기한까지 판매할 수 있다(부칙 제3조)"
        ),
        "시행예정": (
            "카페인을 제거한 커피원두를 원료로 사용하고",  # Ⅲ. 1. 자. 2) 거) (2) (나)
            "주류를 주류가 아닌 식품의 상호",  # Ⅲ. 1. 거. 2) 하) (16)
        ),
    },
}


def mark_pending(rows: list[dict], name: str) -> int:
    """허용된 시행 전 판의 노드 중 시행 전 조항이 든 것에 `시행예정` 표시를 붙인다. 붙인 노드 수를 돌려준다."""
    spec = PENDING_ALLOWED[name]
    n = 0
    for needle in spec["시행예정"]:
        hit = [r for r in rows if needle in (r.get("본문") or "")]
        if not hit:
            raise SystemExit(
                f"🔴 {name}: 시행 전 조항 글귀 {needle!r} 가 어느 노드에도 없다 — 판이 바뀌었다. "
                "PENDING_ALLOWED 를 사람이 다시 본다 (D-220)"
            )
        for r in hit:
            r["시행예정"] = spec["표시"]
            n += 1
    return n


def split_in_force(
    files: list[pathlib.Path], today: str
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """파일명의 시행일(`{target}_{ID}_{시행일}.xml`)로 (시행 중, 시행 전) 을 가른다.

    🔴 2026-09-25 — 법제처 본문 조회가 「식품등의 표시기준」(36814)에 **시행 전 판(20280101)** 을 줬다.
       부칙을 읽지 않은 시행 전 판은 **싣지 않고 이름을 찍는다** (D-220 — 조용히 넣지도 조용히 버리지도 않는다).
       사람이 부칙을 읽고 `PENDING_ALLOWED` 에 적은 파일만 시행 중 쪽으로 간다(팀장 판정 (나)). 원문은 그대로 남는다(규약 2).
       🔄 같은 날 정정 — 종전 이 자리는 「D-290 ③」을 적었다. ③ 은 **옛 판**(제도가 바뀐 뒤)이고 시행 전 판을 다룬 D 는 없다.
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
        future = m.group(1) > today
        (later if future and p.name not in PENDING_ALLOWED else now).append(p)
    return now, later


def main() -> int:
    ap = argparse.ArgumentParser(description="법령·행정규칙 조문 본문 → 3층")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    files = [p for p in store.current_files(LAW, "*.xml") if p.name.startswith(PREFIX)]
    files, later = split_in_force(files, date.today().strftime("%Y%m%d"))
    for p in later:
        print(
            f"  🚨 시행 전 판 — 싣지 않는다: {p.name} (사람이 부칙을 보고 `PENDING_ALLOWED` 에 적는다)"
        )
    if not files:
        print("조문 원문이 없다 — collect.law_api 를 먼저 돌린다")
        return 1

    all_rows: list[dict] = []
    for p in files:
        rows = parse(p)
        if p.name in PENDING_ALLOWED:
            k = mark_pending(rows, p.name)
            print(
                f"  ⚠ 시행 전 판을 싣는다 — {p.name} · 시행 전 조항 노드 {k}개에 표시 (팀장 판정 (나))"
            )
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
