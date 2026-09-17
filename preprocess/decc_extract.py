"""preprocess/decc_extract.py — 행정심판 재결례 → 광고 문구 + 근거 조문 (5판).

  uv run python -m preprocess.decc_extract            # 센다
  uv run python -m preprocess.decc_extract --dump     # data/derived/decc_phrases.jsonl

왜 있는가 — `data/derived/law_decc.jsonl` 이 2026-09-08 부터 있었는데
**아무도 안 읽고 있었다** (2026-09-17 확인). 「이유」에 광고 문구가 인용부호로 들어 있고,
「관계법령」 절에 근거 조문이 붙어 있다.

실측은 **사실원장 「2026-09-17 오후」 절 ③** 에 있다 — 여기 숫자를 박지 않는다.
원천이 시계열이라 돌릴 때마다 바뀌고, 박아 두면 원장과 갈린다 (D-54).

🚨 ftc 와 구조가 다르다 — D-99 로 합치지 않고 **호출만 빌린다.**
     ftc  : 주문 → 유형 · 이유 → 문구
     decc : 「4. 관계법령」 → 조문 · 「5. 인정사실」·「3. 피청구인 주장」 → 문구
   재결서는 **같은 문구를 3개 절에 반복**한다(사건개요·피청구인 주장·인정사실).
   절을 안 가르고 세면 문구 수가 3배로 부풀어 D-40 판정이 틀린다.

🚨 **원천이 이미 마스킹했다** — `●`(상호) `◆△`(주소) `□`(제품명) `★☆`(원료).
   우리 자국(`[업체]`)과 모양이 다르므로 `content_len` 이 이것도 자국으로 세야
   「□□□□□는」 같은 알맹이 0 인용이 문구로 들어온다 (D-157 · ftc_extract 2026-09-08 교훈).
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import pathlib
import re

#: 절 머리 — 「1. 사건개요」 …  🚨 줄머리에서만 본다. 본문 안 「1.」에 걸리면 절이 쪼개진다.
SECTION = re.compile(r"^\s*(\d)\.\s*([^\n]{2,40})$", re.M)

#: 문구를 찾을 절. 🚨 「2. 청구인 주장」은 뺀다 — 변명이지 광고가 아니다.
PHRASE_SECTIONS = ("사건개요", "피청구인", "인정사실")
#: 조문을 회수할 절.
LAW_SECTION = "관계법령"

#: 원천이 박은 각주 마커. 문구 한가운데 들어온다.
FOOTNOTE = re.compile(r"\[\[\[FOOTNOTE\]\]\]\d*\[\[\[FOOTNOTE\]\]\]")

#: 🚨 원천 마스킹 자국. 우리 `mask.MARK_RE` 와 **다른 물건**이라 여기서 따로 든다 —
#:    합치면 우리 자국 표기를 바꿀 때 원천 자국까지 끌려간다 (D-166 의 반대 방향).
SRC_MARK = re.compile(r"[●◆△□★☆○▲▼■◇]{1,}")

QUOTES = "“”‘’「」" + chr(39) + chr(34)
QUOTE = re.compile("[" + QUOTES + "]([^" + QUOTES + r"\n]{4,120})[" + QUOTES + "]")

#: 재결서 전용 잡음 — 지시어·당사자·절차어. ftc 의 NOISE 가 안 덮는다.
DECC_NOISE = re.compile(
    r"^이 사건|^해당 |^위 |^동 |청구인|피청구인|재결|처분청|행정심판|취소청구"
    r"|이라 한다|이하 |약칭|별지|가이드라인|안내서|심사지침"
    # 🔄 1판 실측 — 법령·규정·조례명이 인용부호에 싸여 문구로 잡혔다 (40건 중 4건)
    r"|법$|법률$|규정$|조례$|기준$|고시$|지침$|시행령$|시행규칙$|조항$"
    r"|flDownload|https?:|\.do\?|조례|관리법"
    r"|display\s*:|font-|margin|padding|<[a-z]"  # 🔴 원천에 CSS·HTML 조각이 섞여 있다
)

#: 조문 회수 — 「법률명 제N조제M항제K호」
#: 🔄 1판은 앞 글자를 먹었다 — 「제65조 식품위생법 시행령」이 「조 식품위생법 시행령」이 됐다.
#:    법령명을 **토큰 단위**로 잡고 조사·접속어를 앞에서 떼어 낸다.
#: 🔴 2판 — 1판은 「법」만 봤다. 「식품 등의 표시·광고에 관한 **법률** 제8조」가 통째로
#:    안 잡혀 **식품표시광고법·표시광고법 재결례가 0 건으로 보였다.** 화장품법(「법」으로
#:    끝난다)만 잡혀서 「재결례는 화장품뿐」이라는 틀린 그림이 나왔다 (D-191).
#: 🔴 3판 — 2판은 가운뎃점을 못 넘었다. 「식품 등의 표시**·**광고에 관한 법률」이
#:    「광고에 관한 법률」로 잘려 나가 **식품표시광고법 건이 이름 없이 셌다.**
#:    원천이 `·`·`ㆍ` 를 섞어 쓰므로 둘 다 이름의 일부로 본다 (D-117 과 같은 자리).
#: 🔴 **5판 — 3판은 중첩 수량자라 전문에 걸면 폭주했다** (2026-09-17 실측).
#:    `(?:[가-힣]+[\s·ㆍ]?){1,10}?` 가 역추적을 지수로 만든다 — 190KB 표본에서
#:    **111초**였고 392건 전문이면 못 끝난다. 문자 클래스 하나로 바꿔 **0.05초**가 됐다.
#:    ★ 덤으로 앞글자 잔재가 사라졌다 — 첫 글자를 `[가-힣]` 로 고정하니
#:    「조 화장품법 시행령」이 안 나온다. `_ART_HEAD` 는 그물로만 남긴다.
#:    ⛔ `\s` 대신 **공백만** 쓴다. 줄바꿈을 넣으면 법령명이 줄을 넘어 붙는다.
ART = re.compile(
    r"([가-힣][가-힣 ·ㆍ]{1,30}?법(?:률)?(?:\s*시행령|\s*시행규칙)?)\s*"
    r"((?:제\d+조)(?:의\d+)?(?:제\d+항)?(?:제\d+호)?)"
)
_ART_HEAD = re.compile(r"^(?:조|항|호|및|또는|같은|위|의|이|그|제)\s*")
ANNEX = re.compile(r"별표\s*(\d+)")

#: 🔴 **법령명이 아닌 것** — 전문 경로를 열자마자 상위를 이것들이 채웠다 (2026-09-17 실측).
#:    「법 시행규칙」179 · 「및 같은 법 시행규칙」142 · 「부터 법」130 · 「까지 및 법」130.
#:    재결서가 「…제4조부터 제6조까지 및 같은 법 시행규칙…」처럼 쓰기 때문이다.
#:    ⛔ `ours()` 판정에는 영향이 없다(이름에 우리 법 어구가 없다) — **망가진 것은 분포 표**다.
#:    🚨 그래서 「수가 안 틀렸으니 괜찮다」로 넘기지 않는다. 원장에 옮기는 것이 이 표다 (D-54).
#:    🔄 2차 — 걸러도 「법 시행규칙」179 가 남았다. 「같은」을 뗀 자리다. 그리고
#:    「동할 수 있는 내용을 표시ㆍ광고하여 건강기능식품에 관한 법률」처럼 **문장을 통째로**
#:    이름으로 무는 것이 있다. 이름이 **법령명 꼴**인지로 거른다 — 용언·조사가 들어가면 아니다.
#:    ⛔ 「관한」은 살린다 — 「식품 등의 표시·광고에 **관한** 법률」이 그 꼴이다.
_BAD_NAME = re.compile(
    r"부터|까지|및|또는"
    r"|하여|하고|있는|있고|위반|따라|따른|대하여|으로|에서|한다|된다|같이|경우"
    r"|^같은|^해당|^이 |^그 |^위 |^동 |^법"
)

#: 🚨 **아는 법령명** — 뭉치에서 이것만 잘라낸다 (`_canon`). 우리 법 넷 + 자주 같이 나오는 것들.
#:    ⛔ 목록을 늘릴 때는 **긴 것을 앞에** 둔다 — `|` 는 첫 매치를 쓴다.
_CANON = re.compile(
    r"(?:식품\s*등의\s*표시[·ㆍ]광고에\s*관한\s*법률"
    r"|표시[·ㆍ]광고의\s*공정화에\s*관한\s*법률"
    r"|건강기능식품에\s*관한\s*법률"
    r"|수입식품안전관리\s*특별법"
    r"|식품위생법|화장품법|약사법|행정심판법|행정절차법|축산물\s*위생관리법)"
    r"(?:\s*시행령|\s*시행규칙)?"
)

#: 우리 판정 축의 법령. 🚨 원천이 `·`·`ㆍ` 를 섞어 쓰므로 **정규화한 뒤** 비교한다 (D-117).
OUR_LAWS: tuple[str, ...] = (
    "표시·광고에 관한 법",  # 식품 등의 표시·광고에 관한 법률 (+시행령·시행규칙)
    "표시·광고의 공정화",  # 표시·광고의 공정화에 관한 법률
    "화장품법",
    "건강기능식품에 관한 법",
)


def sep_norm(s: str) -> str:
    """가운뎃점을 한 쪽으로 모은다. 비교 직전에만 부른다 (D-117)."""
    return s.replace("\u318d", "\u00b7")


def ours(statutes: list[str]) -> list[str]:
    """회수한 조문 중 우리 법인 것만."""
    return [x for x in statutes if any(k in sep_norm(x) for k in OUR_LAWS)]


def sections(text: str) -> dict[str, str]:
    """「1. 사건개요」 … 로 가른다.

    🚨 못 가르면 전문을 `본문` 하나로 준다 — 없음이 성공으로 집계되지 않게 (D-72).
    """
    marks = list(SECTION.finditer(text))
    if not marks:
        return {"본문": text}
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(2).strip()] = text[m.end() : end]
    return out


def content_len(q: str) -> int:
    """원천 마스킹 자국과 뒤 조사를 걷어낸 알맹이 길이. 「□□□□□는」은 1 이 아니라 0 이다."""
    rest = SRC_MARK.sub("", q)
    rest = re.sub(r"^(?:은|는|이|가|을|를|의|와|과|에|로|도|만)\s*", "", rest.strip())
    return len(rest.strip())


def phrases(sec: dict[str, str]) -> list[str]:
    out: list[str] = []
    for name, body in sec.items():
        if not any(k in name for k in PHRASE_SECTIONS):
            continue
        for q in QUOTE.findall(FOOTNOTE.sub("", html.unescape(body))):
            q = " ".join(q.split())
            if len(q) < 8 or q.isdigit():
                continue
            if DECC_NOISE.search(q):
                continue
            if content_len(q) < 6:
                continue
            if q not in out:
                out.append(q)
    return out


def _canon(name: str) -> str | None:
    """법령명 뭉치에서 **아는 이름만 잘라낸다.** 못 자르면 이름 꼴인지 본다.

    🔴 **버리면 진짜가 같이 죽는다** (2026-09-17 실측). `_BAD_NAME` 으로 통째로 버리니
    「…표시ㆍ광고하여 **건강기능식품에 관한 법률** 제18조」처럼 **앞에 문장이 붙었을 뿐
    진짜인 건**이 4건 사라졌다(19 → 15). 이름을 버릴 게 아니라 **잘라내야** 맞다.
    """
    m = _CANON.search(name)
    if m:
        return " ".join(m.group(0).split())
    name = _ART_HEAD.sub("", name).strip()
    # 🔴 3판 — 2판은 `h.split()[0]` 만 봤다. 「**식품** 등의 표시·광고에 관한 법률
    #    제8조」의 첫 토큰이 2자라 **우리 법 중 가장 중요한 것이 버려졌다.** 이름 전체로 센다.
    if len(name.replace(" ", "")) < 3 or _BAD_NAME.search(name):
        return None
    return name


def _scan(body: str) -> list[str]:
    hits: list[str] = []
    for a, b in ART.findall(body):
        name = _canon(" ".join(a.split()))
        if name:
            hits.append(f"{name} {b}")
    hits += [f"별표 {n}" for n in ANNEX.findall(body)]
    return list(dict.fromkeys(hits))


def statutes(sec: dict[str, str]) -> tuple[list[str], str]:
    """회수한 조문과 **어디서 캤는지**를 함께 돌려준다.

    🔴 **5판 — 4판은 「관계법령」 절만 봤고, 그 절이 없는 건을 통째로 놓쳤다**
    (2026-09-17 실측). 사건명에 「광고」가 든 32건 중 **25건이 회수 실패**였는데
    그중 **22건은 「관계법령」 절이 아예 없었다.** 재결서가 그 대신
    **조문 제목을 절 이름으로** 쓴다 — 「식품등을 의약품으로 인식할…」·
    「거짓ㆍ과장된 표시 또는 광고」·「소비자를 기만하는 표시 또는 광고」.

    ★ 그래서 절이 없으면 **전문으로 물러난다.** 🚨 대신 출처를 함께 돌려준다 —
    전문 경로는 「판단 절이 스쳐 인용한 법」까지 걷어 오므로 **같은 신뢰도로 세면 안 된다** (D-178).
    """
    body = next((v for k, v in sec.items() if LAW_SECTION in k), None)
    if body is not None:
        return _scan(body), "관계법령"
    return _scan("\n".join(sec.values())), "전문"


def main(path: str = "data/derived/law_decc.jsonl") -> int:
    ap = argparse.ArgumentParser(description="재결례 → 광고 문구 + 근거 조문")
    ap.add_argument("--path", default=path)
    ap.add_argument("--dump", action="store_true", help="라벨시트를 낸다")
    ap.add_argument("--peek", type=int, default=0, help="우리 법 건을 N 개까지 찍는다")
    args = ap.parse_args()

    text = pathlib.Path(args.path).read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    recs = []
    for d in rows:
        sec = sections(html.unescape(d.get("이유") or ""))
        ps, (st, src) = phrases(sec), statutes(sec)
        recs.append(
            {
                "사건명": d.get("사건명", ""),
                "사건번호": d.get("사건번호", ""),
                "주문": (d.get("주문") or "").strip(),
                "의결일자": d.get("의결일자", ""),
                "문구": ps,
                "조문": st,
                "우리법조문": ours(st),
                "조문출처": src,
            }
        )

    n = len(recs)
    with_p = sum(1 for r in recs if r["문구"])
    with_s = sum(1 for r in recs if r["조문"])
    both = [r for r in recs if r["문구"] and r["우리법조문"]]
    print(f"  재결례 {n:,} · 문구 {sum(len(r['문구']) for r in recs):,} · 문구 있는 건 {with_p:,}")
    both_any = sum(1 for r in recs if r["문구"] and r["조문"])
    print(f"  조문 회수된 건 {with_s:,} · 문구+조문 {both_any:,}")
    print(f"  🔴 문구+우리법 조문 {len(both):,}건 · 문구 {sum(len(r['문구']) for r in both):,}")

    # 🚨 주문 분포 — 5층 반례는 「뒤집힌 것」이 값이다
    ord_c = collections.Counter(
        "인용/취소"
        if ("취소" in r["주문"] or "변경" in r["주문"])
        else ("기각" if "기각" in r["주문"] else ("각하" if "각하" in r["주문"] else "기타"))
        for r in both
    )
    print(f"  우리법 건의 주문 — {dict(ord_c)}")

    law_c = collections.Counter()
    for r in recs:
        for x in r["조문"]:
            if not x.startswith("별표"):
                law_c[sep_norm(x).split(" 제")[0]] += 1
    print("  회수 법령 상위 —")
    for k, v in law_c.most_common(8):
        print(f"    {v:>4} {k}")

    for r in both[: args.peek]:
        print(f"  * {r['사건명'][:40]} | 문구 {len(r['문구'])} | {', '.join(r['우리법조문'][:3])}")

    if args.dump:
        out = pathlib.Path("data/derived/decc_phrases.jsonl")
        with out.open("w", encoding="utf-8") as f:
            for r in both:
                for q in r["문구"]:
                    f.write(
                        json.dumps(
                            {
                                "사건번호": r["사건번호"],
                                "사건명": r["사건명"],
                                "의결일자": r["의결일자"],
                                "주문": r["주문"][:40],
                                "문구": q,
                                "길이": len(q),
                                "초과40": len(q) > 40,
                                "근거조문": r["우리법조문"],
                                "조문출처": r["조문출처"],
                                "확정유형": [],
                                "후보유형": [],
                                "원천": "law_go_kr",
                                "층": "5층 반례",
                                "붙인이": "",
                                "붙인날": "",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
        print(f"  💾 {sum(len(r['문구']) for r in both):,}행 → {out}")
        print("  🚨 확정유형·후보유형은 비어 있다 — 사람이 채운다 (D-66 · D-172).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
