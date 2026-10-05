"""preprocess/mfds_cosmetic_qa_2012.py — 「2012년 화장품·의약외품 표시·광고 등 질의·응답집」 PDF → **질의회신 레코드** (2026-10-03).

  uv run python -m preprocess.mfds_cosmetic_qa_2012            # 센다
  uv run python -m preprocess.mfds_cosmetic_qa_2012 --verify   # 목차(제목 · 쪽 · 장별 수)와 대조한다
  uv run python -m preprocess.mfds_cosmetic_qa_2012 --dump     # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_cosmetic_ad_qa_2012` (식약청 바이오생약국 · 2012-02 · 166쪽 · '10.7~'12.1 민원회신 모음)

──────────────────────────────────────────────────────────────
★ **레코드 = 문항 하나** — 제목 · 질의 · 회신일 · 답변

  쪽 머리글 「화장품의약외품 표시광고 등 질의응답집 N」 · 제목 줄 · 「문 N」 · 날짜 줄 · 「회신」 · 답변. 문항은 **새 쪽에서 시작한다**.
  문항 번호는 편(화장품 · 의약외품)마다 1 부터 다시 센다. 장은 표지 쪽(세 줄뿐인 쪽)이 넘긴다 — 목차의 장 순서대로다.
  실측(2026-10-03 · 클론 B 원문 · 작업공간) — 문항 **130**: 화장품 94(표시광고 일반 46 · 기능성 3 · 유기농 4 · 품목분류 41) ·
  의약외품 36(품목분류 17 · 표시광고 9 · 기타 10) → **표시광고 장 62**(화장품 53 · 의약외품 9). 원장 09-30 ② 의 목차 셈과 같다.

★ **라벨을 만들지 않는다** — 한 문항에 위반 · 조건부 · 적법 문구가 섞인다(`mfds_cosmetic_qa` 머리말과 같은 이유).
  `인용표현` 은 라벨 판의 후보다. 🚨 답변이 드는 조문은 **2010 화장품법**(제12조 · 시행규칙 제15조 [별표3])이다 —
  지금의 제13조가 아니다. 그래서 `관련규정_인용` 을 만들지 않는다: 옛 조문 번호를 지금 번호로 읽으면 틀린다 (D-220).

★ **담지 않는 것** (D-159)
  · 일러두기 · 목차 · 표지 쪽 · 판권면(발행인 · 편집위원 실명) — 「●」로 시작하는 줄에서 멈춘다.
    레지스트리 masking 의 「판권면의 담당 공무원 성명」은 여기서 담지 않아 지킨다.
  · 전화번호는 여기서 `[전화]` 로 바꾼다(실측 1 — 답변 속 기관 대표 전화) — 마스킹 축에 전화가 없다.
  · 광고 캡처 · 예시 이미지는 텍스트 층에 없다 (D-18 · D-133).

★ **기준 시점 · 판정 지위를 레코드마다 남긴다** — 2012-02 기준 · `질의회신`(D-240). 판단 사례로만 쓴다(D-290 ③):
  2021 질의응답집(`mfds_cosmetic_ad_qa`) · 2025 지침(`mfds_cosmetic_ad_guideline`)이 우선한다.
  ★ 줄넘김은 **글자 좌표로 되살린다**(`preprocess.pdf_lines`) — 낱말 한가운데서 넘은 줄(「거칠거\\n칠한」)은 붙이고
    빈칸에서 넘은 줄은 띄운다. 대조 어긋남 1.3%(742 쌍 중 10) — 모르면 띄운다.
  ★ 겹치는 문항(레지스트리 fragment_note) — 표시광고 장 62 가운데 2021 질의응답집과 질의 4글자 조각 포함도 0.4 이상 **0**
    (최대 0.3 · 2026-10-03 · 작업공간). 뺄 문항이 없다. ⬜ 문구 단위 중복은 판독 판을 골든에 넣을 때 거른다.
  ★ 상호 · 상표는 **원천이 가려서 준다**(△△ 54 · ★★★ 9 · ▲▲ 5) — 「제품명 :」 뒤 35곳이 전부 가림 표기다.
    남은 로마자 고유명은 제3자다(광고 문구 속 순위 사이트 · 인증 협회 · 국제 기구) — 광고주가 아니다.

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed · `preprocess.mask.apply_policy`).
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

from collect import store
from preprocess.mfds_cosmetic_qa import quotes
from preprocess.pdf_lines import Line, as_lines, document, join

SOURCE_ID = "mfds_cosmetic_ad_qa_2012"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_cosmetic_ad_qa_2012.jsonl")

#: 문서 시점 · 지위 — 레코드마다 싣는다. `판정지위` 값은 D-240 의 목록
REGIME = {
    "문서": "화장품·의약외품 표시·광고 등 질의·응답집(2012)",
    "발행일": "2012-02",
    "기준시점": "2012-02",
    "판정지위": "질의회신",
}

#: 쪽 머리글 — 끝의 숫자가 인쇄 쪽 번호다(목차와 대조할 독립된 선언)
_RUNNING = re.compile(r"^화장품의약외품 표시광고 등 질의응답집\s*(\d{1,3})$")
#: 문항 표지 — 「문 1 …」 · 「문45 …」
_Q = re.compile(r"^문\s*(\d{1,3})(?:\s+(.*))?$")
#: 회신일 — 🚨 「2010/4/15」처럼 한 자리 달 · 날이 있다(실측 1)
_DATE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_ANSWER = "회신"
#: 목차 — 편 「Ⅰ. 화장품」 · 장 「1. 화장품 표시광고 : 일반사항」 · 항목 「○ 제목····쪽」
_TOC_PART = re.compile(r"^[ⅠⅡ]\.\s*(.+)$")
_TOC_CHAPTER = re.compile(r"^(\d)\.\s*(.+?)\s*:\s*(.+)$")
_TOC_ITEM = re.compile(r"^○\s*(.+?)·{2,}\s*(\d{1,3})$")
#: 본문의 편 표지 쪽 — 「Ⅰ. 화 장 품」
_PART_PAGE = re.compile(r"^[ⅠⅡ]\.\s*\S")
#: 판권면 — 여기서 멈춘다
_COLOPHON = "●"
#: 전화번호 — 지역번호-국-번호. 마스킹 축에 없어 여기서 바꾼다
_PHONE = re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")
MASK_PHONE = "[전화]"
#: 표지 쪽의 줄 수 상한 — 「화장품 / 일반사항 / 표시 광고」 세 줄 `[측정]` 2026-10-03 (표지 9쪽 전부 세 줄)
_COVER_MAX_LINES = 3


def _n(s: str) -> str:
    return " ".join(s.split())


def _key(s: str) -> str:
    """제목 대조용 — 빈칸을 뺀다(목차 「무( )보존제」 · 본문 「무( )보존제」의 빈칸 수가 다르다)."""
    return re.sub(r"\s", "", s)


def pages() -> list[list[Line]]:
    """쪽별 줄 목록 — 줄마다 다음 줄과 붙는지(`glue`)가 실려 있다(`preprocess.pdf_lines`)."""
    got = store.current_files(RAW_DIR, "*.pdf")
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 pdf 가 없다 —\n  먼저: uv run python launcher.py collect {SOURCE_ID}"
        )
    return document(got[0])[0]


def _lines(page: str | list[str]) -> list[Line]:
    return as_lines(page)


def toc(pgs: list) -> list[dict]:
    """목차 → `[{편, 장, 제목, 쪽}, …]`. 본문 첫 쪽(머리글 있는 쪽) 앞까지만 읽는다."""
    got: list[dict] = []
    part = chapter = None
    for p in pgs:
        ls = _lines(p)
        if ls and _RUNNING.match(ls[0]):
            break
        for s in ls:
            m = _TOC_ITEM.match(s)
            if m and part and chapter:
                got.append(
                    {"편": part, "장": chapter, "제목": _n(m.group(1)), "쪽": int(m.group(2))}
                )
            elif _TOC_CHAPTER.match(s):
                chapter = s
            elif _TOC_PART.match(s):
                part, chapter = _TOC_PART.match(s).group(1), None
    return got


def parse(pgs: list) -> tuple[list[dict], dict]:
    """쪽 텍스트 → (문항 레코드, 계측). 🚨 마스킹은 여기서 하지 않는다 — 전화번호만 바꾼다."""
    entries = toc(pgs)
    chapters = list(dict.fromkeys((e["편"], e["장"]) for e in entries))
    rows: list[dict] = []
    stat: dict = {
        "표지_넘침": [],
        "문항_앞_글": [],
        "제목_없음": [],
        "회신_없음": [],
        "날짜_없음": [],
        "전화": 0,
    }
    k = -1  # 지금 장 — 표지 쪽이 넘긴다
    cur: dict | None = None
    started = False
    for page in pgs:
        ls = _lines(page)
        if not ls:
            continue
        if any(s.startswith(_COLOPHON) for s in ls):
            break  # 🔴 판권면부터는 담지 않는다
        head = _RUNNING.match(ls[0])
        if not head:
            if not started and not (entries and _PART_PAGE.match(ls[0]) and len(ls) == 1):
                continue  # 표지 · 목차 · 일러두기
            started = True
            if len(ls) == 1 and _PART_PAGE.match(ls[0]):
                continue  # 편 표지
            if len(ls) <= _COVER_MAX_LINES:
                k += 1
                cur = None
                if k >= len(chapters):
                    stat["표지_넘침"].append(ls)
                continue
            stat["문항_앞_글"].append(ls[0])
            continue
        pg = int(head.group(1))
        body = ls[1:]
        q = next((i for i, s in enumerate(body) if _Q.match(s)), None)
        if q is None:
            if cur is None:
                stat["문항_앞_글"].append(pg)
            else:
                cur["_글"].extend(body)
            continue
        if not 0 <= k < len(chapters):
            stat["표지_넘침"].append(pg)
            continue
        m = _Q.match(body[q])
        title = join(body[:q])
        if not title:
            stat["제목_없음"].append(pg)
        cur = {
            "편": chapters[k][0],
            "장": chapters[k][1],
            "문항": int(m.group(1)),
            "제목": title,
            "쪽": pg,
            "_글": [*([Line(m.group(2), body[q].glue)] if m.group(2) else []), *body[q + 1 :]],
        }
        rows.append(cur)

    for r in rows:
        body = r.pop("_글")
        a = next((i for i, s in enumerate(body) if s == _ANSWER), None)
        if a is None:
            stat["회신_없음"].append((r["편"], r["문항"]))
            a = len(body)
        ask = body[:a]
        date = None
        if ask and (dm := _DATE.match(ask[-1])):
            date, ask = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}", ask[:-1]
        else:
            stat["날짜_없음"].append((r["편"], r["문항"]))
        r["질의"] = _phone(join(ask), stat)
        r["회신일"] = date
        r["답변"] = _phone(join(body[a + 1 :]), stat)
        r["광고장"] = "표시광고" in _key(r["장"])
        r["인용표현"] = quotes(r)
        r["원천"] = SOURCE_ID
        r.update(REGIME)
    return rows, stat


def _phone(text: str, stat: dict) -> str:
    out, n = _PHONE.subn(MASK_PHONE, text)
    stat["전화"] += n
    return out


def verify(pgs: list) -> list[str]:
    """🔴 목차와 대조한다 — 장별 문항 수 · 제목 · 쪽 · 편별 번호 연속 · 회신이 있는가."""
    entries = toc(pgs)
    rows, stat = parse(pgs)
    bad: list[str] = []
    if not entries:
        return ["목차를 못 읽었다"]
    for k in ("표지_넘침", "문항_앞_글", "제목_없음", "회신_없음"):
        if stat[k]:
            bad.append(f"{k} — {stat[k][:5]}")
    want = collections.Counter((e["편"], e["장"]) for e in entries)
    have = collections.Counter((r["편"], r["장"]) for r in rows)
    if want != have:
        bad.append(f"장별 문항 수 — 목차 {dict(want)} · 본문 {dict(have)}")
    for part in dict.fromkeys(e["편"] for e in entries):
        qs = [r["문항"] for r in rows if r["편"] == part]
        if qs != list(range(1, len(qs) + 1)):
            bad.append(f"{part} 문항 번호가 이어지지 않는다")
    if len(entries) == len(rows):
        for e, r in zip(entries, rows, strict=True):
            if _key(e["제목"]) != _key(r["제목"]) or e["쪽"] != r["쪽"]:
                bad.append(
                    f"{r['편']} 문{r['문항']} — 목차 「{e['제목']}」 {e['쪽']}쪽 · 본문 「{r['제목']}」 {r['쪽']}쪽"
                )
    return bad


#: 마스킹을 거는 자리 — 🚨 인용표현은 마스킹된 본문에서 다시 뜬다(`mfds_cosmetic_qa.masked` 와 같다)
MASK_FIELDS = ("제목", "질의", "답변")


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter, list[dict]]:
    """마스킹을 건 사본과 계측. **산출물로 나가는 모든 길이 여기를 지난다.**"""
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
        rec["인용표현"] = quotes(rec)
        out.append(rec)
    return out, changed, log


def _report(rows: list[dict], stat: dict) -> None:
    print(f"문항 {len(rows):,} — 표시광고 장 {sum(1 for r in rows if r['광고장'])}")
    for (part, ch), v in collections.Counter((r["편"], r["장"]) for r in rows).items():
        print(f"    {part:5} {v:>3}  {ch}")
    ad = [r for r in rows if r["광고장"]]
    print(
        f"\n  인용표현 {sum(len(r['인용표현']) for r in rows):,}건 — 표시광고 장 {sum(len(r['인용표현']) for r in ad):,}건"
    )
    days = sorted(r["회신일"] for r in rows if r["회신일"])
    if days:
        print(
            f"  회신일 {days[0]} ~ {days[-1]} · 🚨 2010 화장품법 기준 — 조문 번호를 지금 번호로 읽지 않는다"
        )
    print(f"  전화번호 {stat['전화']}곳을 {MASK_PHONE} 로 바꿨다")
    for k, v in stat.items():
        if v and k != "전화":
            print(f"  🚨 {k} {v}")


def main() -> int:
    ap = argparse.ArgumentParser(description="2012 질의응답집 PDF → 질의회신 레코드")
    ap.add_argument("--verify", action="store_true", help="목차와 대조한다")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    a = ap.parse_args()

    pgs = pages()
    bad = verify(pgs)
    if a.verify:
        if bad:
            print("🔴 목차와 본문이 어긋난다 — 파싱 결과를 믿지 않는다:", file=sys.stderr)
            for b in bad:
                print(f"  · {b}", file=sys.stderr)
            return 1
        print("★ 목차 대조 통과 — 장별 문항 수 · 제목 · 쪽 · 번호가 목차와 같다")

    rows, stat = parse(pgs)
    _report(rows, stat)

    if a.dump:
        if bad:  # 🔴 대조가 깨진 파싱은 파생물로 내보내지 않는다 (D-72)
            print(
                f"\n🔴 목차 대조 실패 {len(bad)}건 — 쓰지 않았다. `--verify` 로 본다",
                file=sys.stderr,
            )
            return 1
        out, changed, log = masked(rows)
        lost = sum(len(x["인용표현"]) for x in rows) - sum(len(x["인용표현"]) for x in out)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'} · 치환 {len(log)}건")
        print(f"  {'🚨' if lost else '★'} 마스킹으로 사라진 인용표현 {lost}건")
        print(f"  → {OUT}  ({len(out):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
