#!/usr/bin/env python3
"""scripts/casebook2021_sheet.py — 사례집 2021판 **라벨 시트** (쪽 전사 → 행 · 2026-10-03 다시 씀).

  uv run python scripts/casebook2021_sheet.py           # 무엇이 들어가는지 본다
  uv run python scripts/casebook2021_sheet.py --dump    # data/derived/casebook2021_labelsheet.jsonl

──────────────────────────────────────────────────────────────
🔄 2026-10-03 — **전사를 다시 했다.** 09-17 판은 사람이 눈으로 옮긴 278행을 이 파일 안에 적었는데
   원본 대조(10-03)에서 글자가 다른 행이 나왔고, 행을 자른 기준이 일정하지 않았다(빨간 상자 하나 ·
   떨어진 해시태그를 골라 붙인 것 · 상자 밖 글이 섞임). 원장 10-03 ④.

★ 지금 꼴 — 두 층이다.
  ① **쪽 전사** `data/derived/labels/casebook_2021/pages.json` — 원본 쪽을 보이는 그대로 옮긴 것(법령 쪽 제외 61쪽).
     🔴 **git 에 두지 않는다** — 광고 화면의 글(광고주 문구)이 들어 있고 이 저장소는 공개다 (D-249 ⑥).
        부류는 「원천」(판독 원자료 — 다시 돌려도 같은 판독이 아니다)이고 팀 공유 저장소가 옮긴다(`data-publish` / `data-sync`).
        ⛔ 2026-10-03 에 `scripts/` 아래에 두고 커밋했다가 옮겼다 — 09-17 판이 문구 278 개를 이 파일 안에 적어 git 에
           올린 것도 같은 문제였다(D-249 보다 사흘 앞). 이 파일에는 이제 광고 문구가 한 줄도 없다.
     서로 못 보는 판독 둘이 따로 읽고, 어긋난 줄은 셋째 판독이 그 자리만 잘라 정했다.
     줄마다 `합의`(일치 · 판정) · `확신` · `메모` 가 남아 있다. 못 읽은 글자는 `□`, 가린 자리는 `[가림]`,
     식약처가 표시한 범위는 `⟦ ⟧`. 🚨 **모델 판독이다 — 사람 감사는 없다** (D-188). 검수 대상이다.
  ② **행** — 이 파일이 ① 에서 규칙으로 뽑는다. 손으로 고른 행이 없다.
     · 위반사례: 식약처 요약 문장 하나가 한 행
     · 광고사례: **광고 화면 하나가 한 행** (팀장 판정 2026-10-03 (나)) — `문구` 는 식약처가 표시한 조각을
       ` / ` 로 이은 것, `화면글` 은 그 화면에서 읽힌 글 전부(문맥)
       ⛔ 표시 조각 하나를 한 행으로 하지 않는다 — 「불면증」 같은 낱말 조각이 문맥 없이 행이 된다.
          화장품 쪽(72~76쪽)은 표시가 거의 없어 그 규칙이 서지 않는다 (D-192)

🚨 **원본의 오타를 고치지 않는다** — 9쪽 「관절언골」 · 「‘치내’」, 33쪽 「‘수먼부족’」은 인쇄가 그렇다.
   게이트 `tests/test_casebook2021_sheet.py` 가 지킨다.

🚨 **자율심의 결과 칸(52~54쪽 왼쪽 열)** — 53쪽에는 심의기구가 빨간 취소선 · 가는 빨간 네모로 고친 자리가 있다.
   그 쪽에서 고친 자리가 든 줄은 `적법글` 에서 뺀다 — 심의가 지우라고 한 글자는 심의를 통과한 글이 아니다
   (팀장 판정 2026-10-03). 지운 글자는 `심의삭제` 에 따로 둔다.
   ⛔ `심의삭제` 를 위반 라벨로 쓰지 않는다 — 덧쓴 빨간 글자를 한 자도 못 읽어 무엇으로 고쳤는지 모르고,
      지운 주체는 식약처가 아니라 심의기구다. 「통과하지 못한 표현」까지만 말할 수 있다.
   취소선이 없는 쪽(52 · 54)의 빨간 상자는 식약처가 위반 광고와 견주려고 친 표시다 — `표시문구` 로 간다.

🔴 **마스킹** — 모든 글이 `mask.apply_policy(…, "mfds_casebook_2021")` 를 지난다(정책이 없으면 멈춘다 · D-72).
   ① 규칙 축(업체 · 상표 · 주소 · 대표자)은 이 원천에서 **거의 안 걸린다** — 법인격 표기도 주소도 없다(실측 2026-10-03:
      글 1,241 개 중 치환 1 · 그것도 오탐). 그래서 ② 가 실제 방어다.
   ② 원천이 흰 상자로 안 가린 판매자 · 상표 · 제품 이름과 바코드는 **쪽 전사에서 이미 가려 둔다**(`[업체]` · `[상표]` ·
      `[바코드]` — 레지스트리 「즉시 마스킹 · 원문 미보관」 · D-17). 수는 `EXPECTED_REDACTED` 가 지킨다 — 전사를 다시 해
      이름이 되살아나면 수가 줄어 멈춘다. ⛔ 가릴 이름의 목록을 이 파일에 적지 않는다 — 공개 저장소에 그 이름을 싣는 일이다.
   🚨 남긴 것 — 55쪽 「그 밖의 사항」의 제품 이름(그 이름이 곧 위반 표시다) · 9호 화면의 「매직」(식약처 제목이 적었다) ·
      플랫폼 이름 · 광고가 든 연구기관 이름. 검토요청 `검토요청_2026-10-03_마스킹정책_식품사례_3종.md` §1-2.
   🚨 사람 축 오탐 1 — 47쪽 식약처 설명문의 「○○」 앞 글자가 `[대표]` 가 된다. 문언(「대표자명 … 마스킹」)이 서명된 그대로라
      지금은 켜 둔다. 끄려면 문언을 고치고 2인 확인을 받는다(같은 검토요청 (나)).

🚨 후보유형은 **원천이 적은 호**에서만 온다. 책 Ⅱ부(약사법 · 화장품법 제13조①4호)는 유형을 붙이지 않는다 —
   09-17 판은 전사자가 식품 유형 이름을 Ⅱ부 행에 골라 붙였다. 조문은 판독 판에서 붙인다.

🔴 **확정유형은 비어 있다. 사람이 채운다** (D-66). 여기서 채우지 않는다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.settings import PARAMS  # noqa: E402
from collect import registry  # noqa: E402
from preprocess import mask  # noqa: E402

SOURCE_ID = "mfds_casebook_2021"
PAGES = pathlib.Path("data/derived/labels/casebook_2021/pages.json")
OUT = pathlib.Path("data/derived/casebook2021_labelsheet.jsonl")

F = "식품 등의 표시·광고에 관한 법률 제8조 제1항"
W = "식품위생법 제7조 제4항"
D_AK = "약사법 제68조"  # 의약외품 광고
C = "화장품법 제13조 제1항"

# 🔗 1~7호는 `collect/statute.py` 와 같아야 한다 — 게이트 `tests/test_statute.py` 가 소스로 대조한다 (D-99 · D-282).
#    8~10호 이름은 계약 열거형에 없다(statute 는 None) — 시트 표시용이고 적재되지 않는다.
TYPE = {
    1: ["질병_예방치료_표방"],
    2: ["의약품_오인"],
    3: ["건강기능식품_오인"],
    4: ["거짓_과장"],
    5: ["소비자_기만"],
    6: ["비방광고"],
    7: ["부당_비교광고"],
    8: ["사행심_음란"],
    9: ["상호상표_오인"],
    10: ["심의_미이행"],
}

#: 책의 구간 — 쪽은 인쇄 쪽. 법령을 옮겨 적은 쪽(6~7 · 60~62 · 69~71)은 전사하지 않았다(정본은 법령 원천).
#: [관행] 책 차례를 그대로 옮긴 것이다. 쪽 전사에 이 밖의 쪽이 생기면 `_part()` 가 멈춘다.
PARTS = (
    # (첫 쪽, 끝 쪽, 부, 근거법)
    (8, 55, "Ⅰ", F),
    (63, 68, "Ⅱ", D_AK),
    (72, 76, "Ⅱ", C),
)
#: 행을 만들지 않는 쪽 — 「개요」 표(보도자료 목록). 쪽 전사에는 있다
OUTLINE_PAGES = (5, 59)

#: 식약처가 문구를 짚은 표시. 형광 · 색글자는 광고 자체의 꾸밈일 수 있어 넣지 않는다 —
#: 화장품 쪽 판독 둘이 모두 「식약처 표시인지 확신 없음」으로 적었다. 그 줄은 `화면글` 에 `⟦ ⟧` 째 남는다.
MARKS = ("빨간상자", "빨간밑줄", "물결밑줄")
#: 심의기구가 지운 자리. 이 표시가 있는 쪽의 자율심의 칸에서는 빨간 상자도 교정 표시로 읽는다(`_edited_pages`)
STRUCK = "취소선"
#: 표시 조각이 이것뿐이면 문구가 아니다
MASK = "[가림]"

LAYER_1 = "1층 판정라벨"
LAYER_2 = "2층 적법라벨"
APPROVED = "자율심의 결과"
VIOLATED = "위반 광고 내용"

_HO = re.compile(r"^(\d+)\.\s")
_DATE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")
_BLOCK_DATE = re.compile(r"[’'](\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})일자 보도")
_QUOTE = re.compile(r"‘([^‘’]+)’|“([^“”]+)”")
_ITEM = re.compile(r"△\s*([^△]+)")
_ORDER = ("높음", "중간", "낮음")


class SheetError(RuntimeError):
    """쪽 전사가 이 파일의 규칙에 안 맞는다 — 고르지 않고 멈춘다 (D-220)."""


#: 마스킹이 바꾼 자리 — `rows()` 가 채운다(규칙 · 쪽). `verify` 가 기대 수와 견준다
MASKED: list[dict] = []


def masked(text: str, page: int) -> str:
    """레지스트리가 이 원천에 정한 축을 건다. 🔴 정책이 없으면 `MaskPolicyError` 로 멈춘다 (D-72)."""
    log: list[dict] = []
    out = mask.apply_policy(text, "", SOURCE_ID, log)
    if out != text:
        MASKED.append(
            {"쪽": page, "앞": len(text), "뒤": len(out), "규칙": [x.get("rule") for x in log]}
        )
    return out


def pages() -> list[dict]:
    """쪽 전사를 읽고 **글자 칸마다 마스킹을 건 것**을 낸다 — 뒤의 모든 계산이 가린 글 위에서 돈다."""
    got = _load()
    MASKED.clear()
    for p in got:
        n = p["쪽"]
        for e in p["요소"]:
            for key in ("글", "왼칸"):
                if e.get(key):
                    e[key] = masked(e[key], n)
            for key in ("사례", "참고"):
                if e.get(key):
                    e[key] = [masked(x, n) for x in e[key]]
            for ln in e.get("줄") or []:
                ln["글"] = masked(ln["글"], n)
    return got


def _load() -> list[dict]:
    if not PAGES.exists():
        raise SheetError(
            f"쪽 전사가 없다: {PAGES.as_posix()} — git 이 나르지 않는다(D-249). `data-sync` 로 받는다"
        )
    return json.loads(PAGES.read_text(encoding="utf-8"))


def _part(page: int) -> tuple[str, str]:
    for lo, hi, part, law in PARTS:
        if lo <= page <= hi:
            return part, law
    raise SheetError(f"{page}쪽은 책의 어느 구간에도 없다 — PARTS 를 고친다")


def spans(text: str) -> list[str]:
    """`⟦ ⟧` 로 감싼 조각 — 겹친 표시는 바깥 것 하나로 센다(안쪽 기호는 뗀다)."""
    out, depth, buf = [], 0, []
    for ch in text:
        if ch == "⟦":
            depth += 1
            if depth == 1:
                buf = []
            continue
        if ch == "⟧":
            if depth == 0:
                raise SheetError(f"⟧ 가 짝이 없다: {text!r}")
            depth -= 1
            if depth == 0:
                s = "".join(buf).strip()
                if s:
                    out.append(s)
            continue
        if depth:
            buf.append(ch)
    if depth:
        raise SheetError(f"⟦ 가 닫히지 않았다: {text!r}")
    return out


def _has(line: dict, kinds: tuple[str, ...]) -> bool:
    return any(k in (line.get("표시") or "") for k in kinds)


def _edited_pages(all_pages: list[dict]) -> set[int]:
    """자율심의 결과 칸에 취소선이 있는 쪽 — 그 쪽의 왼쪽 열은 심의 교정본이다(53쪽 · 한 칸에 그림 둘)."""
    return {
        p["쪽"]
        for p in all_pages
        for e in p["요소"]
        if e["종류"] == "칸" and APPROVED in (e.get("열머리") or "")
        for ln in e.get("줄") or []
        if STRUCK in (ln.get("표시") or "")
    }


def _dates(text: str) -> str:
    """요약 문장 끝 괄호의 보도일 — 여럿이면 `, ` 로 잇는다. 없으면 빈 글."""
    tail = text[text.rfind("(") :] if "(" in text and "보도" in text[text.rfind("(") :] else ""
    return ", ".join(f"{y}.{int(m):02d}.{int(d):02d}" for y, m, d in _DATE.findall(tail))


def quoted(text: str, examples: list[str]) -> list[str]:
    """요약 문장과 딸린 `* (사례)` 줄에서 식약처가 따옴표 · △ 로 든 표현 — 순서대로, 겹치면 한 번.

    ⛔ 따옴표도 △ 도 없는 사례 줄(「365잠솔솔, 굿잠 …」 같은 나열)은 쪼개지 않는다 — 쉼표가 문구 안에도 있다.
    """
    out: list[str] = []
    for src in (text, *examples):
        got = ["".join(m) for m in _QUOTE.findall(src)]
        got += [x.strip() for x in _ITEM.findall(src)]
        for q in got:
            q = q.strip()
            if q and q not in out:
                out.append(q)
    return out


def _row(**kw: object) -> dict:
    base = dict(
        쪽=0,
        부="",
        호=None,
        호제목="",
        블록="",
        소제목="",
        칸=None,
        열머리="",
        대분류="",
        글="",
        사례=[],
        참고=[],
        문구="",
        표시문구=[],
        길이=0,
        화면글=[],
        식약처설명=[],
        인용표현=[],
        확정유형=[],
        후보유형=[],
        원천=SOURCE_ID,
        연도=2021,
        근거법="",
        보도일="",
        붙인이="",
        붙인날="",
        층=LAYER_1,
        확신="",
        가림=0,
        미판독=0,
        비고="",
    )
    extra = set(kw) - set(base) - {"적법글", "심의삭제"}
    if extra:
        raise SheetError(f"모르는 칸: {sorted(extra)}")
    return {**base, **kw}


def rows() -> list[dict]:
    out: list[dict] = []
    all_pages = pages()
    edited = _edited_pages(all_pages)
    section: tuple[str, str] | None = None
    ho: int | None = None
    ho_title = block = ""
    for p in all_pages:
        page = p["쪽"]
        if page in OUTLINE_PAGES:
            continue
        part, law = _part(page)
        # 🚨 호 제목 · 블록은 쪽을 넘어 이어진다 — 책의 구간(법)이 바뀔 때만 지운다
        if section != (part, law):
            section, ho, ho_title, block = (part, law), None, "", ""
        sub = prev_left = ""
        for e in p["요소"]:
            kind = e["종류"]
            if kind == "제목":
                m = _HO.match(e["글"])
                if m and _same_band(p, e):
                    ho_title += " / " + e["글"]  # 63쪽 — 띠 하나에 호 1 · 2. 호는 앞의 것
                elif m:
                    ho, ho_title = int(m.group(1)), e["글"]
                else:
                    ho, ho_title = None, e["글"]  # 55쪽 「※ 그 밖의 사항」
                block = sub = prev_left = ""
            elif kind == "블록":
                block, sub = e["글"], ""
            elif kind == "소제목":
                sub, prev_left = e["글"], ""
            elif kind == "위반사례":
                out.append(_case(page, part, law, ho, ho_title, block, sub, e))
            elif kind == "칸":
                left = e.get("왼칸") or ""
                inherited = not left and bool(prev_left)
                out.append(
                    _ad(
                        page,
                        part,
                        law,
                        ho,
                        ho_title,
                        block,
                        sub,
                        e,
                        left or prev_left,
                        inherited,
                        page in edited,
                    )
                )
                prev_left = left or prev_left
            elif kind in ("법령상자", "주", "표"):
                continue
            else:
                raise SheetError(f"{page}쪽: 모르는 요소 {kind!r}")
    return out


def _same_band(page: dict, title: dict) -> bool:
    """이 제목 바로 앞 요소도 제목인가 — 63쪽은 회색 띠 하나에 호 1 · 2 가 함께 적혀 있다."""
    els = page["요소"]
    i = els.index(title)
    return i > 0 and els[i - 1]["종류"] == "제목"


def _case(
    page: int, part: str, law: str, ho: int | None, ho_title: str, block: str, sub: str, e: dict
) -> dict:
    kinds = list(TYPE.get(ho, [])) if law == F else []
    note = ""
    if ho is None:  # 55쪽 「※ 그 밖의 사항」 — 광고가 아니다 (D-192)
        if "기준" in sub:
            kinds, law = ["기준규격_위반"], W
            note = "🚨 광고 유형이 아니라 미허용 식품원료 사용이다 — 범위 밖 (D-192)"
        else:
            kinds = ["표시_위반"]
            note = "🚨 광고가 아니라 제품명 표시 위반이다 — 문장 판정기 범위 밖일 수 있다 (D-192)"
    text = e["글"]
    return _row(
        쪽=page,
        부=part,
        호=ho,
        호제목=ho_title,
        블록="위반사례" if ho is not None else "그 밖의 사항",
        소제목=sub,
        글=text,
        사례=list(e.get("사례") or []),
        참고=list(e.get("참고") or []),
        인용표현=quoted(text, e.get("사례") or []),
        후보유형=kinds,
        근거법=law,
        보도일=_dates(text),
        확신="높음",
        비고=" · ".join(x for x in (note, e.get("메모", "")) if x),
    )


def _ad(
    page: int,
    part: str,
    law: str,
    ho: int | None,
    ho_title: str,
    block: str,
    sub: str,
    e: dict,
    left: str,
    inherited: bool,
    edited: bool,
) -> dict:
    lines = e.get("줄") or []
    head = (e.get("열머리") or "").strip("<>〈〉 ")
    approved = head == APPROVED
    screen = [ln for ln in lines if "식약처설명" not in (ln.get("표시") or "")]
    corrected = approved and edited  # 심의 교정본 — 이 칸의 표시는 식약처 것이 아니다
    marked = (
        []
        if corrected
        else [s for ln in screen if _has(ln, MARKS) for s in spans(ln["글"]) if s != MASK]
    )
    conf = max((_ORDER.index(ln.get("확신", "중간")) for ln in lines), default=0)
    m = _BLOCK_DATE.search(block)
    notes = []
    if inherited:
        notes.append("왼칸이 위 칸과 합쳐진 칸 — 대분류는 위 칸의 것")
    if e.get("비고"):
        notes.append(e["비고"])
    if approved:
        kinds: list[str] = []
    elif head == VIOLATED:
        kinds = ["심의_미이행"]
    elif law == F:
        kinds = list(TYPE.get(ho, []))
    elif law == C and ho == 1:
        kinds = ["의약품_오인"]  # 화장품법 §13①1 — `collect/statute.py` 와 같은 대응
    else:
        kinds = []  # 약사법 · 화장품법 §13①4 — 호만으로 유형이 서지 않는다
    row = _row(
        쪽=page,
        부=part,
        호=ho,
        호제목=ho_title,
        블록="광고사례",
        소제목=sub or block,
        칸=e["번호"],
        열머리=head,
        대분류=left,
        문구=" / ".join(marked),
        표시문구=marked,
        길이=max((len(s) for s in marked), default=0),  # 가장 긴 표시 조각 — 상한은 조각마다 본다
        화면글=[{"글": ln["글"], "표시": ln.get("표시", "없음")} for ln in screen],
        식약처설명=[ln["글"] for ln in lines if "식약처설명" in (ln.get("표시") or "")],
        후보유형=kinds,
        근거법=law,
        보도일=f"20{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}" if m else "",
        층=LAYER_2 if approved else LAYER_1,
        확신=_ORDER[conf],
        가림=int(e.get("가림") or 0),
        미판독=sum(ln["글"].count("□") for ln in lines),
        비고=" · ".join(notes),
    )
    if approved:
        fixed = [ln for ln in screen if corrected and _has(ln, (STRUCK, *MARKS))]
        row["적법글"] = [
            ln["글"].replace("⟦", "").replace("⟧", "") for ln in screen if ln not in fixed
        ]
        row["심의삭제"] = [s for ln in fixed for s in spans(ln["글"])]
    return row


#: 🔴 쪽 전사에서 우리가 가린 자리의 수 — [측정] 2026-10-03 화면 글 전부를 읽어 가린 것(모델 판독 · 사람 확인 전).
#:    줄면 이름이 되살아난 것이고 늘면 새로 가린 것이다 — 어느 쪽이든 멈추고 본다
EXPECTED_REDACTED = {"[업체]": 3, "[상표]": 12, "[바코드]": 1}
#: 🔴 규칙 축이 바꾼 자리의 수 — [측정] 2026-10-03: 1(47쪽 식약처 설명문 · 사람 축 오탐) → 🔄 2026-10-04 검토요청 (나) 로
#:    사람 축을 꺼 0 이다(판정 오한빈 · 2인 확인 권소라). 다시 생기면 멈추고 본다
EXPECTED_MASKED = 0

#: 🔴 기대 수 — 쪽 전사가 바뀌면 여기서 멈춘다. [측정] 2026-10-03 쪽 전사(61쪽)에서 센 값
EXPECTED = {"행": 183, "위반사례": 47, "그 밖의 사항": 4, "광고사례": 132, LAYER_2: 5}


def verify(got: list[dict]) -> None:
    c = collections.Counter(r["블록"] for r in got)
    seen = {"행": len(got), **{k: c[k] for k in ("위반사례", "그 밖의 사항", "광고사례")}}
    seen[LAYER_2] = sum(1 for r in got if r["층"] == LAYER_2)
    if seen != EXPECTED:
        raise SheetError(f"행 수가 기대와 다르다: {seen} ≠ {EXPECTED}")
    blob = PAGES.read_text(encoding="utf-8")
    redacted = {k: blob.count(k) for k in EXPECTED_REDACTED}
    if redacted != EXPECTED_REDACTED:
        raise SheetError(f"우리 쪽 가림 수가 기대와 다르다: {redacted} ≠ {EXPECTED_REDACTED}")
    if len(MASKED) != EXPECTED_MASKED:
        raise SheetError(
            f"규칙 축이 바꾼 자리가 기대와 다르다: {len(MASKED)} ≠ {EXPECTED_MASKED} · {MASKED}"
        )
    if any(r["확정유형"] for r in got):
        raise SheetError("확정유형이 채워져 있다 — 사람이 채운다 (D-66)")
    pair = collections.Counter(
        (r["쪽"], r["열머리"]) for r in got if r["열머리"] in (APPROVED, VIOLATED)
    )
    for (page, head), n in pair.items():
        other = VIOLATED if head == APPROVED else APPROVED
        if pair[(page, other)] != n:
            raise SheetError(f"{page}쪽: 자율심의 결과와 위반 광고 내용의 칸 수가 다르다")
    # 🔴 인용 문구의 보관 상한(D-249 ③ · `PARAMS.quote_max_chars`) — 넘는 조각이 생기면 자르지 않고 멈춘다.
    #    화면 하나의 글을 통째로 한 문구로 다루지 않는다 — 상한은 **표시 조각 · 화면 글 한 줄**마다 건다.
    cap = PARAMS.quote_max_chars
    for r in got:
        long = [s for s in r["표시문구"] if len(s) > cap]
        long += [x["글"] for x in r["화면글"] if len(x["글"]) > cap]
        if long:
            raise SheetError(f"{r['쪽']}쪽 칸 {r['칸']}: 인용 상한 {cap}자를 넘는 줄 {len(long)}")
    for r in got:
        if r["블록"] == "광고사례" and not r["화면글"] and not r["식약처설명"]:
            raise SheetError(f"{r['쪽']}쪽 칸 {r['칸']}: 읽힌 글이 없다")
        if r["층"] == LAYER_2 and any("⟦" in t for t in r.get("적법글", [])):
            raise SheetError(f"{r['쪽']}쪽 칸 {r['칸']}: 적법글에 표시 기호가 남았다")


def main() -> int:
    ap = argparse.ArgumentParser(description="사례집 2021판 라벨 시트 (쪽 전사 → 행 · 검수 대상)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    a = ap.parse_args()

    got = rows()
    verify(got)
    # 🔴 변경금지(ND) 게이트 — 전사도 파생 데이터셋이다 (2026-09-25 · `registry.assert_derivable`)
    registry.assert_derivable(got, who="casebook2021_sheet")
    print(f"행 {len(got)}")
    for field in ("부", "블록", "근거법", "층", "확신"):
        c = collections.Counter(str(r.get(field, "")) for r in got)
        print(f"  {field:6} {dict(c.most_common())}")
    adv = [r for r in got if r["블록"] == "광고사례"]
    t: collections.Counter = collections.Counter(x for r in adv for x in r["후보유형"])
    print(f"  후보유형(광고사례 {len(adv)}행) — {dict(t.most_common())}")
    print(
        f"  표시 문구가 없는 광고사례 {sum(1 for r in adv if not r['표시문구'])}행 — 화면글로 읽는다"
    )
    print(
        f"  마스킹 — 쪽 전사에서 가린 자리 {EXPECTED_REDACTED} · 규칙 축이 바꾼 자리 {len(MASKED)}"
    )
    print(f"  못 읽은 글자(□)가 있는 행 {sum(1 for r in got if r['미판독'])}")
    filled = sum(1 for r in got if r.get("확정유형"))
    print(f"  🔴 확정유형이 채워진 행 {filled} — 사람이 채운다 (D-66)")
    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in got) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\n→ {OUT.as_posix()}")
    else:
        print("\n🚨 쓰지 않았다 — `--dump` 를 붙인다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
