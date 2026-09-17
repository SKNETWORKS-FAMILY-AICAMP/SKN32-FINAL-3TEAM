"""preprocess/mfds_casebook.py — 사례집 PDF → **1층 판정라벨** (D-151 · D-158).

  uv run python -m preprocess.mfds_casebook                # 센다
  uv run python -m preprocess.mfds_casebook --verify       # 목차 쪽번호와 대조한다
  uv run python -m preprocess.mfds_casebook --dump         # 🔴 마스킹 정책이 있어야 한다
  uv run python -m preprocess.mfds_casebook --sheet 30     # 사람이 붙일 검증셋을 만든다

원천: `mfds_casebook` (식약처 「식품 등 온라인 부당광고 사례집」 · 사이버조사팀 · 2026-04)

──────────────────────────────────────────────────────────────
★ **해설서와 정반대다 — 여기서는 조문이 확정이다** (D-151 과 짝)

  해설서(2017)는 자기 3분류로 우리 6종을 **뭉쳐** 놓아서 확정할 수 없었다.
  사례집은 **식품표시광고법 제8조 제1항의 호를 그대로 적어 준다.** 호는 원천의 선언이고,
  우리가 추측한 것이 아니다. 그래서 옮겨 적는 것이지 라벨을 만드는 것이 아니다.

  🚨 **딱 하나 5호만 뭉친다** — 「소비자를 기만하는 표시 또는 광고」 안에
     `소비자_기만` 과 `후기_체험기_기만` 이 같이 산다(시행령 [별표 1] 5. 다목).
     그래서 5호는 `후보유형` 으로만 적고 `확정유형` 은 비운다. D-151 과 같은 규칙이다:
     **없는 확신을 만들지 않는다.**

  ⛔ 「다목이면 체험기니까 확정」으로 가려다 말았다. 다목은 체험기 **말고도**
     「한방」·「특수제법」·「주문쇄도」·「단체추천」을 함께 담는다. 좁혀 보이지만 안 좁다.

★ **제도 시점이 해설서와 다르다** (D-138). 사례집은 2026-04 발간이고 현행 자율심의
  체계의 자료다. 해설서(2017 · 사전심의)와 **섞으면 안 된다** — 레코드마다 남긴다.

──────────────────────────────────────────────────────────────
🚨 **원천이 같은 블록을 다섯 가지 이름으로 부른다**

    [부당광고 사례] · [부당광고사례] · [광고사례] · [위반사례]   ← 사례 블록
    [점검 현황]                                                ← 점검 현황 블록

  ⛔ 처음에 「[부당광고 사례]」로 하드코딩했더니 **5개 중 2개만** 잡혔다. 그런데
     예외가 안 났다 — 3·4·5호의 사례가 통째로 「점검현황」에 붙어 버릴 뿐이었다.
  ★ 그래서 이름을 나열하지 않고 **모양으로 판별**하고, 끝에 **다섯 쌍이 맞는지 센다.**

🔴 **광고 캡처 이미지는 추출하지 않는다** (D-18 · G1 미추출). 적발된 광고는 광고주
   저작물이다. 우리가 취하는 것은 식약처가 **직접 쓴 캡션과 조문**이다.
   🚨 그래서 이 원천의 「문구」는 대개 **캡션 속 인용부호 안**에 있다 — 원문 그대로가
      아니라 식약처가 인용한 만큼이다. 레코드에 `인용표현` 으로 따로 적는다.

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed).
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import re
import sys

from collect import store
from preprocess.text import SheetOverwriteError, quoted, sheet_lengths, write_sheet

SOURCE_ID = "mfds_casebook"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_casebook_labels.jsonl")
SHEET = pathlib.Path("data/derived/mfds_casebook_labelsheet.jsonl")

#: 제도 시점 — D-138. **레코드마다 남긴다.** 해설서(2017 사전심의)와 섞으면 안 된다.
REGIME = {
    "심의제도": "자율심의(식품표시광고법 제10조)",
    "연도": 2026,
    "근거법": "식품 등의 표시·광고에 관한 법률 제8조 제1항",
}

#: 식품표시광고법 §8① 각 호 → 우리 유형. **원천이 호를 적어 주므로 옮겨 적는 것이다.**
#: 🚨 5호만 둘이다 — 뭉친 것은 `확정유형` 에 넣지 않는다 (D-151 과 같은 규칙).
HO_TYPES: dict[int, tuple[str, ...]] = {
    1: ("질병_예방치료_표방",),
    2: ("의약품_오인",),
    3: ("건강기능식품_오인",),
    4: ("거짓_과장",),
    5: ("소비자_기만", "후기_체험기_기만"),
    6: ("비방광고",),
    7: ("부당_비교광고",),
}

#: Ⅱ부의 호 제목 머리말. 🚨 Ⅰ부(법령 전재)에도 같은 번호가 있어 **말끝으로 가른다** —
#: Ⅰ부는 「…있는 **다음 각 목의** 표시 또는 광고」, Ⅱ부는 「…있는 표시 또는 광고」.
_HO_HEAD = re.compile(
    r"^([1-7])\.\s*(질병의 예방|식품등을 의약품|건강기능식품이 아닌|거짓|소비자를 기만)"
)
_BLOCK = re.compile(r"^\[([^\]]{2,12})\]$")
_FOOT = re.compile(r"^-\s*(\d+)\s*-$")
_MARK = ("○", "▶", "◦", "-")
_PRESS = re.compile(r"\((\d{4})[.\s]*(\d{1,2})[.\s]*(\d{1,2})[.\s]*보도\)")
#: 플랫폼부(Ⅲ)
_GROUP = re.compile(r"^부당광고 유형 및 사례\s*\((\d+)\)$")
_ITEM = re.compile(r"^(\d+)\.\s*(.+)$")
_HO_CITE = re.compile(r"제8조\s*제1항\s*제(\d)호")
_MOK = re.compile(r"\[별표\s*1\]\s*(\d)\.\s*.*?\s([가-힣])\.\s")


def _n(s: str) -> str:
    return " ".join(s.split())


def pages() -> list[str]:
    """쪽별 텍스트. 🚨 `pdftotext -layout` 은 이 문서에서 글자를 깨뜨린다(「또는」→「또…」)."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ModuleNotFoundError as e:  # 🚨 무엇을 하라는지까지 말한다 (D-72 의 어조)
        raise ModuleNotFoundError(
            "pdfplumber 가 없다 — 사례집 파싱은 이것으로 읽는다 (D-158).\n"
            "  고치는 법:  uv sync\n"
            "  🚨 2026-09-08 까지 docs 그룹에 있었다. 지금은 런타임 의존성이다."
        ) from e

    got = store.current_files(RAW_DIR, "*.pdf")
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 pdf 가 없다 —\n  먼저: 자료실에서 사례집을 내려받아 둔다 (레지스트리 access:)"
        )
    with pdfplumber.open(got[0]) as d:
        return [(pg.extract_text() or "") for pg in d.pages]


def printed(page: str) -> int | None:
    """인쇄 쪽번호(`- 13 -`). 목차와 대조할 **독립된 선언**이다."""
    for ln in page.split("\n"):
        m = _FOOT.match(ln.strip())
        if m:
            return int(m.group(1))
    return None


def toc(pgs: list[str]) -> tuple[int, list[tuple[str, int]]]:
    """목차 → (목차 쪽 index, [(제목, 인쇄쪽), …]).

    ★ 이 문서에는 `hwp.PrvText` 같은 **독립 렌더링**이 없다. 대신 목차가 있다 —
      본문과 다른 경로로 만들어진 선언이라 대조에 쓸 수 있다.
    """
    for i, t in enumerate(pgs):
        if t.strip().startswith("목차"):
            out = []
            for ln in t.split("\n")[1:]:
                m = re.match(r"^(.*?)[·\s]{3,}(\d+)$", _n(ln))
                if m and m.group(1).strip():
                    out.append((_n(m.group(1)), int(m.group(2))))
            return i, out
    raise ValueError("목차를 못 찾았다 — 원천의 구조가 바뀌었다면 이 모듈을 다시 본다")


def locate(pgs: list[str], tocpage: int, entries: list[tuple[str, int]]) -> dict[str, int]:
    """목차 제목 → 그 제목이 처음 나오는 쪽 index. **목차 순서대로 앞으로만 찾는다.**

    ⛔ 순서를 안 지키고 매번 처음부터 찾았더니 호 제목 다섯 개가 전부 **1쪽**에서 잡혔다.
       Ⅰ부가 법 제8조 제1항을 통째로 전재하는데, 각 호의 문장이 목차 제목과 **글자까지
       같기 때문**이다. 목차 대조가 「어긋난다」고 외쳐 준 덕에 알았다 —
       🚨 대조기가 없었으면 Ⅱ부 대신 **법령 전재를 파싱하고** 조용히 끝났을 것이다.
    """
    out: dict[str, int] = {}
    cursor = tocpage + 1
    for label, _ in entries:
        key = re.sub(r"[\s.]", "", label)
        for i in range(cursor, len(pgs)):
            if key in re.sub(r"[\s.]", "", pgs[i]):
                out[label] = i
                cursor = i
                break
    return out


def verify() -> list[str]:
    """🔴 목차가 말한 쪽에 그 제목이 정말 있는가. 어긋나면 파싱 결과를 믿지 않는다."""
    pgs = pages()
    tocpage, entries = toc(pgs)
    found = locate(pgs, tocpage, entries)
    bad = []
    for label, want in entries:
        if label not in found:
            bad.append(f"목차 {label!r} 가 본문에 없다 (목차 순서대로 찾았다)")
            continue
        got = printed(pgs[found[label]])
        if got != want:
            bad.append(f"목차 {label!r} 는 {want}쪽인데 실제로는 {got}쪽에서 나온다")
    return bad


def _types(hos: list[int]) -> tuple[list[str], list[str]]:
    """호 목록 → (확정유형, 후보유형). 🚨 뭉친 호(5호)는 확정에 넣지 않는다."""
    fixed: list[str] = []
    cand: list[str] = []
    for h in hos:
        ts = HO_TYPES.get(h, ())
        (fixed if len(ts) == 1 else cand).extend(ts)
    return sorted(set(fixed)), sorted(set(cand))


def quotes(text: str) -> list[str]:
    """인용부호 안의 표현. **이것이 이 원천의 「광고 문구」다** — 캡처 이미지는 안 쓴다.

    🚨 계수기는 `preprocess.text.quoted` **하나뿐이다** (D-160). 여기서는 종수만 쓰므로
       중복을 접는다 — `evasion_scan` 은 회수도 쓰기 때문에 접지 않는다.
    ★ 가족을 전부 열어 둬도 결과가 같다는 것을 재 봤다 (2026-09-08 · 250종 == 250종) —
      Ⅱ·Ⅲ부 레코드 글에는 `「」`·`""` 인용이 없다. 그래서 기본값을 그대로 쓴다.
    """
    return list(dict.fromkeys(quoted(text)))


def own_text(rec: dict) -> str:
    """레코드 **자기 글**. 🚨 `대분류` 는 뺀다 — 여러 ▶ 가 같은 ○ 를 공유하므로,
    넣으면 같은 표현이 형제 레코드마다 복제돼 표본 수가 부풀어 오른다.

    ⛔ `--dump` 에서만 `대분류` 를 섞어 세었다가 「사라진 인용표현 **-213건**」이 찍혔다.
       마이너스라서 눈에 띄었지 부호가 반대였으면 그냥 넘어갔을 계측 오류다 —
       **세는 쪽과 하는 쪽이 어긋난 자리**, 오늘 하루 종일 나온 그 모양이다.
    """
    return rec.get("글") or rec.get("문구") or ""


def extract() -> tuple[list[dict], dict]:
    """레코드들과 계측. 🚨 마스킹은 여기서 하지 않는다 — 부르는 쪽이 정책을 지고 건다."""
    pgs = pages()
    tocpage, entries = toc(pgs)
    label_page = locate(pgs, tocpage, entries)
    part2 = next(i for lab, i in label_page.items() if lab.startswith("Ⅱ"))
    part3 = next(i for lab, i in label_page.items() if lab.startswith("Ⅲ"))
    part4 = next(i for lab, i in label_page.items() if lab.startswith("Ⅳ"))

    rows: list[dict] = []
    stat: dict = {"블록": collections.Counter(), "호없음": 0, "블록없음": 0, "인용": 0}

    # ── Ⅱ. 부당광고 사례 ────────────────────────────────────────────────
    ho: int | None = None
    blk: str | None = None
    lead: str = ""  # 사례 블록의 ○ 는 ▶ 들의 **대분류**다
    cur: dict | None = None
    for i in range(part2, part3):
        pg = printed(pgs[i])
        for raw in pgs[i].split("\n"):
            s = _n(raw)
            if not s or _FOOT.match(s):
                continue
            m = _HO_HEAD.match(s)
            if m and "다음 각 목의" not in s:
                ho, blk, lead, cur = int(m.group(1)), None, "", None
                continue
            m = _BLOCK.match(s)
            if m:
                blk = "점검현황" if "점검" in m.group(1) else "사례"
                stat["블록"][f"{blk}:{m.group(1)}"] += 1
                lead, cur = "", None
                continue
            if s[0] in _MARK and not s.startswith("- "):
                fixed, cand = _types([ho] if ho else [])
                if blk == "사례" and s[0] == "○":
                    lead, cur = s[1:].strip(), None  # 대분류만 갱신 — 레코드가 아니다
                    continue
                cur = {
                    "쪽": pg,
                    "부": "Ⅱ",
                    "호": ho,
                    "블록": blk,
                    "대분류": lead,
                    "글": s[1:].strip(),
                    "확정유형": fixed,
                    "후보유형": cand,
                    "원천": SOURCE_ID,
                    **REGIME,
                }
                rows.append(cur)
                if ho is None:
                    stat["호없음"] += 1
                if blk is None:
                    stat["블록없음"] += 1
            elif cur is not None:
                cur["글"] = _n(cur["글"] + " " + s.lstrip("- "))
            elif blk == "사례" and lead:
                lead = _n(lead + " " + s.lstrip("- "))

    for r in rows:
        m = _PRESS.search(r["글"])
        if m:
            r["보도일"] = f"{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"
            r["글"] = _n(_PRESS.sub("", r["글"]))
        r["인용표현"] = quotes(own_text(r))
        stat["인용"] += len(r["인용표현"])

    # ── Ⅲ. 주요 플랫폼별 부당광고 유형 ──────────────────────────────────
    grp = 0
    item: dict | None = None
    tail: str | None = None  # 이어지는 줄이 어디로 붙는지
    for i in range(part3, part4):
        pg = printed(pgs[i])
        for raw in pgs[i].split("\n"):
            s = _n(raw)
            if not s or _FOOT.match(s):
                continue
            m = _GROUP.match(s)
            if m:
                grp, item, tail = int(m.group(1)), None, None
                continue
            if not grp:
                continue
            m = _ITEM.match(s)
            if m and not s.startswith("☞"):
                pos, _, txt = m.group(2).partition(":")
                item = {
                    "쪽": pg,
                    "부": "Ⅲ",
                    "사례": grp,
                    "항목번호": int(m.group(1)),
                    "위치": _n(pos),
                    "문구": _n(txt),
                    "호": [],
                    "별표목": [],
                    "원천": SOURCE_ID,
                    **REGIME,
                }
                rows.append(item)
                tail = "문구" if txt else None
                continue
            if item is None:
                continue
            if s.startswith("☞"):
                item["호"] += [int(x) for x in _HO_CITE.findall(s)]
                tail = None
            elif s.startswith("○"):
                item["별표목"] += [f"{a}-{b}" for a, b in _MOK.findall(s)]
                tail = None
            elif tail == "문구":
                item["문구"] = _n(item["문구"] + " " + s)
    for r in rows:
        if r["부"] != "Ⅲ":
            continue
        r["확정유형"], r["후보유형"] = _types(r["호"])
        r["인용표현"] = quotes(own_text(r))
        stat["인용"] += len(r["인용표현"])
    return rows, stat


#: 마스킹을 거는 자리. `대분류` 도 건다 — ▶ 의 우산 문장에도 상호가 올 수 있다.
MASK_FIELDS = ("글", "대분류", "문구")


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter, list[dict]]:
    """마스킹을 건 사본과 계측. **산출물로 나가는 모든 길이 여기를 지난다.**

    🔴 `--sheet` 도 여기를 지난다. 검증셋은 사람이 읽는 파일이라 무심코 원문을 쓰기 쉽지만,
       `data/derived/` 에 떨어지는 순간 다른 파생물과 똑같이 D-17 대상이다.
       ⛔ 실제로 처음엔 `--sheet` 만 원문을 썼다 — 표본에 상호가 없어서 **깨끗해 보였다.**
          오늘 깨끗한 것은 표본 운이지 규칙이 아니다.
    """
    from preprocess.mask import apply_policy  # noqa: PLC0415

    log: list[dict] = []
    changed: collections.Counter = collections.Counter()
    out: list[dict] = []
    for r in rows:
        rec = dict(r)
        for f in MASK_FIELDS:
            if rec.get(f):
                m = apply_policy(rec[f], "", SOURCE_ID, log)
                if m != rec[f]:
                    changed[f] += 1
                rec[f] = m
        # 🔴 인용표현은 **마스킹된 본문에서 다시 뜬다.** 원문에서 뜬 것을 그대로 두면
        #    가려 놓은 이름이 인용표현 안에 그대로 남는다 — 같은 사고의 다른 문이다.
        #    🚨 뜨는 자리는 `extract` 와 **같아야 한다** (`own_text`).
        rec["인용표현"] = quotes(own_text(rec))
        out.append(rec)
    return out, changed, log


def _report(rows: list[dict], stat: dict) -> None:
    print(f"레코드 {len(rows):,}")
    kinds = collections.Counter((r["부"], r.get("블록") or "플랫폼") for r in rows)
    for k, v in sorted(kinds.items()):
        print(f"    {k[0]} {k[1]:8} {v:>5,}")
    print(f"\n  인용표현 {stat['인용']:,}건 — 🔴 캡처 이미지는 안 쓴다 (D-18 · G1 미추출)")
    print("\n  블록 머리 — 🚨 원천이 같은 것을 여러 이름으로 부른다")
    for k, v in sorted(stat["블록"].items()):
        print(f"    {v:>3}  [{k.split(':', 1)[1]}]  → {k.split(':', 1)[0]}")
    n_case = sum(v for k, v in stat["블록"].items() if k.startswith("사례"))
    n_chk = sum(v for k, v in stat["블록"].items() if k.startswith("점검"))
    mark = "★" if n_case == n_chk == 5 else "🔴"
    print(f"    {mark} 점검현황 {n_chk} · 사례 {n_case}  (호가 5개니 5쌍이어야 한다)")
    if stat["호없음"] or stat["블록없음"]:
        print(f"    🔴 호 없는 레코드 {stat['호없음']} · 블록 없는 레코드 {stat['블록없음']}")

    print("\n  호별 — 🚨 5호는 `확정유형` 이 비어 있다 (뭉쳤다)")
    by: dict[int, int] = collections.Counter(r["호"] for r in rows if isinstance(r.get("호"), int))
    for h in sorted(by):
        f, c = _types([h])
        print(f"    · {by[h]:>4}  {h}호  확정{f or '없음'} 후보{c or '없음'}")
    # ⛔ 예전에는 여기서 30건(D-40)과 견주어 ★/🚨 를 찍었다. **그게 틀렸다.**
    #    D-40 은 **유형별** 표본을 말하는데 이 수는 **이 원천 안에서의** 수다.
    #    실제로 「4호 28건은 2건 모자라다」고 문서에 적었다가 정정했다 —
    #    `거짓_과장` 은 `ftc` 에만 211건이다 (D-161).
    #    🚨 계측기가 매번 그렇게 읽으라고 부추기고 있었다. 부추기지 않게 고친다.
    print("     🚨 D-40 의 30건은 **유형별** 표본이다 — 이 표는 **이 원천 안에서의** 수다.")
    print("        유형이 서는지는 원천을 합쳐서 본다 (사실원장 ②).")
    plat = [r for r in rows if r["부"] == "Ⅲ"]
    if plat:
        ho = collections.Counter(h for r in plat for h in r["호"])
        print(
            f"\n  Ⅲ 플랫폼 {len(plat)}건 — 조문 인용 {sum(ho.values())}회 {dict(sorted(ho.items()))}"
        )
        multi = [r for r in plat if len(set(r["호"])) > 1]
        print(f"    ★ 한 항목에 호가 둘 이상인 것 {len(multi)}건 — **다중 라벨이 원천에 있다**")
        print(f"    🚨 문구가 있는 것 {sum(1 for r in plat if r['문구'])}건 — 나머지는 캡처뿐이다")


def main() -> int:
    ap = argparse.ArgumentParser(description="사례집 PDF → 1층 판정라벨 (D-158)")
    ap.add_argument("--verify", action="store_true", help="목차 쪽번호와 대조한다")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    ap.add_argument("--sheet", type=int, default=0, help="5호 확정을 사람이 붙일 검증셋")
    ap.add_argument("--seed", type=int, default=20260908, help="표본 추출 seed — 재현 조건 (D-54)")
    ap.add_argument(
        "--min-len",
        type=int,
        default=0,
        dest="min_len",
        help="판단 재료(글) 길이 하한 — 낱말만 있는 항목을 뺀다 (0 = 안 건다)",
    )
    a = ap.parse_args()

    if a.verify:
        bad = verify()
        if bad:
            print("🔴 목차와 본문이 어긋난다 — 파싱 결과를 믿지 않는다:", file=sys.stderr)
            for b in bad:
                print(f"  · {b}", file=sys.stderr)
            return 1
        print("★ 목차 대조 통과 — 목차의 모든 항목이 선언한 쪽에서 나온다")

    rows, stat = extract()
    _report(rows, stat)

    if a.sheet:
        rnd = random.Random(a.seed)
        safe, _, _ = masked(rows)  # 🔴 검증셋도 마스킹을 지난다
        pool = [r for r in safe if r["후보유형"] and r.get("인용표현")]
        # 🔴 사람이 5호를 「소비자_기만 / 후기_체험기_기만」으로 가르려면 **맥락**이 필요하다.
        #    인용표현은 낱말이라(중앙 4자) 그것만으로는 못 가른다 — 재료는 `글` 쪽이다.
        if a.min_len:
            pool = [r for r in pool if len(" ".join((r.get("글") or "").split())) >= a.min_len]
        pick = rnd.sample(pool, min(a.sheet, len(pool)))
        try:
            carried, had = write_sheet(SHEET, pick, ("쪽", "호", "글"))
        except SheetOverwriteError as e:
            print(f"\n{e}", file=sys.stderr)
            return 1
        if had:
            print(f"\n     ★ 사람이 채워 둔 {had}건 중 {carried}건을 **이어받았다**")
        print(
            f"\n  ⓒ 검증셋 {len(pick):,}건 → {SHEET}"
            f"  (seed={a.seed} · 후보가 둘인 5호만 · 길이하한 {a.min_len})"
        )
        sheet_lengths(pick, "글", a.min_len)
        print(
            "     🚨 `확정유형` 은 **사람이** 채운다 — 추출기가 채우면 홀드아웃이 자기 채점이 된다."
        )

    if a.dump:
        out, changed, log = masked(rows)
        lost = sum(len(x["인용표현"]) for x in rows) - sum(len(x["인용표현"]) for x in out)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'} · 치환 {len(log)}건")
        print(f"  {'🚨' if lost else '★'} 마스킹으로 사라진 인용표현 {lost}건")
        print(
            "     🚨 광고 문구가 줄면 학습 입력이 줄어든 것이다 — 0 이 아니면 무엇이 지워졌는지 본다."
        )
        print(f"  → {OUT}  ({len(out):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
