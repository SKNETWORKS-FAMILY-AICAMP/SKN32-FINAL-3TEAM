"""preprocess/mfds_cosmetic_qa.py — 허위과대광고 질의응답집 PDF → **질의회신 레코드** (2026-09-25).

  uv run python -m preprocess.mfds_cosmetic_qa                # 센다
  uv run python -m preprocess.mfds_cosmetic_qa --verify       # 목차(문항 번호 · 쪽)와 대조한다
  uv run python -m preprocess.mfds_cosmetic_qa --dump         # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_cosmetic_ad_qa` (식약처 「화장품·의료기기·의약외품 허위과대광고 질의응답집」 · 안내서-1009-02 · 2020-12-30)

──────────────────────────────────────────────────────────────
★ **레코드 = 문항 하나** — 질의 · 답변 · 원천이 적은 `관련규정`

  문항마다 원천이 「관련규정」을 적는다(123문항 전부 · 2026-09-25 실측 · 반각 괄호 ｣ 를 받은 뒤).
  🚨 **그 규정은 문항 단위다 — 문구 단위가 아니다.** 한 문항에 위반 · 조건부 · 적법 문구가 섞이고
     (Q14 「여드름성 피부에 사용 적합」은 실증 시 가능 · 「면포 개수의 감소율」은 오인), 관련규정은
     그 전부를 덮는다. 그래서 여기서는 **라벨을 만들지 않는다** — `관련규정_인용` 은 원천의 선언을 옮긴 것이고,
     문구별 조문·조건은 라벨 판(지시서)이 붙인다. 추출기가 붙이면 원천 선언이 문구 판정으로 승격된다.

★ **담지 않는 것** (D-159 — 담지 않기가 먼저다)
  · [참고 1] 법령 전재 — 코퍼스(law_go_kr)에 있다. 🔴 화장품 [참고 1] 끝(63~66쪽)에 **2015 「화장품 표시·광고 관리
    가이드라인」 금지표현 표**가 통째로 있다 — 2020-08 시행규칙 개정 전 기준이라 정답으로 쓰지 않는다(사실원장 ⑳)
  · [참고 2] 적발 사례 — 광고 캡처 이미지뿐이다(D-18 · 광고주 저작물). 문구는 사람이 옮겨 적을 때만 받는다(D-133 ③)
  · 판권면(발행인 · 편집위원 실명) — 판정 재료가 아니다. 레지스트리 masking 의 「담당 공무원 성명」은 여기서 담지 않아 지킨다
    (`POLICY` 에 사람 축이 없다 — 문언이 「대표자명」이 아니라서다 · `tests/test_mask.py` 대조)

★ **기준 시점 · 판정 지위를 레코드마다 남긴다** — 없으면 다음 사람이 현행 · 확정 위반으로 읽는다
  · 기준 시점 2020-12 — 현행 판단은 「화장품 표시·광고 관리 지침」(`mfds_cosmetic_ad_guideline` · 0086-07 · 2025-08)이 우선한다
  · 판정 지위 `질의회신` — 민원 질의에 대한 소관부처 답이다(행정처분 · 판결 아님). 🚨 값 이름은 `[임의]` —
    D-240(초안)의 값 목록(심의지적 · 행정처분 · 재결 · 판결)에 없다. D-240 이 확정될 때 함께 정한다
  · 🚨 화장품법 제13조제1항제3호(천연 · 유기농 오인)는 2025-01-31 삭제됐다(`collect/statute.py`) — 원천은 2020 기준이라
    그 호를 인용한다. 인용은 그대로 옮기고 유형은 None 이다(`statute.type_of`)

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

from collect import statute, store
from collect.law_map import law_of_basis
from preprocess.text import quoted, sep_norm

SOURCE_ID = "mfds_cosmetic_ad_qa"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_cosmetic_ad_qa.jsonl")

#: 문서 시점 · 지위 — 레코드마다 싣는다. 🚨 `판정지위` 값 이름은 `[임의]` (D-240 초안 · 머리말)
REGIME = {
    "문서": "안내서-1009-02",
    "발행일": "2020-12-30",
    "기준시점": "2020-12",
    "판정지위": "질의회신",
}

#: 분야 표지 쪽 — 그 한 줄만 있는 쪽이 분야의 시작이다. 🚨 같은 줄이 **모든 쪽 머리글**에도 있다 — 한 줄뿐일 때만 표지다
FIELD_TITLES = {
    "Ⅰ. 화장품 분야": "화장품",
    "Ⅱ. 의료기기 분야": "의료기기",
    "Ⅲ. 의약외품 분야": "의약외품",
}
#: 쪽 머리글 — 문항 글에 섞이면 안 된다
RUNNING = {"화장품･의료기기･의약외품 허위･과대광고 질의응답집", *FIELD_TITLES}
_FOOT = re.compile(r"^\d{2,3}$")
#: 문항 표지 — 「Q1 질의…」 또는 「Q2」 한 줄(질의가 표지 **앞뒤로** 흩어진다 — 레이아웃이 표지를 가운데 둔다)
_Q = re.compile(r"^Q(\d{1,3})(?:\s+(.*))?$")
_CHAPTER = re.compile(r"^([1-9])\.\s*(.+)$")
#: 관련규정 한 줄 — 「법령명」으로 시작한다. 🚨 닫는 괄호가 둘이다(」 U+300D · ｣ U+FF63) — Q53 이 반각이다
_CITE_LINE = re.compile(r"^「[^」｣]+[」｣]")
#: 목차 한 줄 — 「Q12. 제목 7」. 제목이 줄을 넘으면 다음 줄에 이어지고 쪽 번호는 끝줄에 있다
_TOC_Q = re.compile(r"^Q(\d{1,3})\.\s*(.+)$")
_TOC_Q_ANY = re.compile(r"Q\d{1,3}\.")
_TOC_END = re.compile(r"^(.*?)\s+(\d{1,3})$")
#: 「부록」 시작 — 여기서 그 분야의 문항이 끝난다
_APPENDIX = re.compile(r"^참고\s*[12]\b")

#: 관련규정 → 인용. 법률 **조문 호**만 인용으로 만든다(`collect/statute.py` 꼴) — 나머지는 원문 그대로 남긴다.
#: 법 이름은 `collect.law_map.law_of_basis` 가 정한다 (D-99 — 법 이름을 두 곳에서 읽지 않는다)
_LAW_SEG = re.compile(r"「([^」｣]+)[」｣]([^「]*)")
#: 🚨 「제13조1항제4호」처럼 항 앞의 「제」가 빠진 줄이 있다(Q 실측 1) — 받는다
_JO_HANG_HO = re.compile(r"제(\d+)조(?:제?(\d+)항)?(?:제(\d+)호)?")
_MORE_HO = re.compile(r"^\s*,\s*제(\d+)호")
#: 위반 근거가 되는 (법 ID, 조, 항) — `collect/statute.py` 의 셋이다 (D-99 · 사본을 두지 않는다)
_VIOLATION = frozenset({statute.FOOD, statute.FAIR, statute.COSM})


def _n(s: str) -> str:
    return " ".join(s.split())


def pages() -> list[str]:
    """쪽별 텍스트. 🚨 pdfplumber — `pdftotext -layout` 은 이 계열 문서에서 줄을 흩뜨린다(`mfds_casebook` 과 같다)."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("pdfplumber 가 없다 — 고치는 법:  uv sync") from e

    got = store.current_files(RAW_DIR, "*.pdf")
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 pdf 가 없다 —\n  먼저: uv run python launcher.py collect {SOURCE_ID}"
        )
    with pdfplumber.open(got[0]) as d:
        return [(pg.extract_text() or "") for pg in d.pages]


def _lines(page: str) -> list[str]:
    return [s for s in (_n(x) for x in page.split("\n")) if s]


def _field_of(page: str) -> str | None:
    ls = _lines(page)
    return FIELD_TITLES.get(ls[0]) if len(ls) == 1 else None


def printed(page: str) -> int | None:
    """인쇄 쪽 번호 — 쪽 끝의 숫자 한 줄. 목차와 대조할 **독립된 선언**이다."""
    for s in reversed(_lines(page)):
        if _FOOT.match(s):
            return int(s)
    return None


def toc(pgs: list[str]) -> tuple[list[tuple[str, int, str, int]], list[str]]:
    """목차 → ([(분야, 문항 번호, 제목, 인쇄 쪽), …], [장 제목, …]).

    🚨 목차의 분야는 **문항 번호가 1 로 돌아가는 자리**로 가른다 — 목차 쪽의 「화장품 / 분 야」 글자는 줄 순서가 흩어져 있다.
    """
    first = next(i for i, p in enumerate(pgs) if _field_of(p))
    fields = list(FIELD_TITLES.values())
    got: list[tuple[str, int, str, int]] = []
    chapters: list[str] = []
    buf: list[str] = []
    k = -1
    for p in pgs[:first]:
        for s in _lines(p):
            # 🚨 목차 쪽 옆 칸 글자가 줄 앞에 붙는다 — 「분 야 Q73. 진피 관련 효능 광고 33」(실측). 표지 앞을 떼어 낸다
            lead = _TOC_Q_ANY.search(s)
            if buf:
                buf.append(s)
            elif lead:
                buf = [s[lead.start() :]]
            elif _CHAPTER.match(s):
                chapters.append(s)
                continue
            else:
                continue
            m = _TOC_END.match(" ".join(buf))
            if not m:
                continue
            q = _TOC_Q.match(m.group(1))
            if q is None:  # 🔴 조용히 버리지 않는다 (D-220)
                raise ValueError(f"목차 줄을 못 읽는다: {' '.join(buf)!r}")
            if int(q.group(1)) == 1:
                k += 1
            got.append((fields[k], int(q.group(1)), _n(q.group(2)), int(m.group(2))))
            buf = []
    return got, chapters


def _same_chapter(line: str, chapters: list[str]) -> bool:
    """본문의 장 제목인가 — **목차의 장 제목과 앞부분이 같을 때만**. 🚨 목차 「… 광고」 · 본문 「… 광고 등」처럼 꼬리가 다르다."""
    key = re.sub(r"\s", "", line)
    return any(
        key.startswith(c) or c.startswith(key) for c in (re.sub(r"\s", "", x) for x in chapters)
    )


def parse(pgs: list[str]) -> tuple[list[dict], dict]:
    """쪽 텍스트 → (문항 레코드, 계측). 🚨 마스킹은 여기서 하지 않는다 — 부르는 쪽이 정책을 지고 건다.

    한 문항의 끝은 **관련규정 줄**이다. 그 뒤에 오는 글은 다음 문항의 질의 앞부분이다(표지가 가운데 온다).
    """
    entries, chapters = toc(pgs)
    rows: list[dict] = []
    stat: dict = {"부록에서_멈춘_쪽": [], "관련규정_없음": [], "질의_물음표_없음": []}
    field: str | None = None
    chapter: str | None = None
    cur: dict | None = None
    pending: list[str] = []
    in_appendix = False
    for page in pgs:
        f = _field_of(page)
        if f:
            _no_orphan(pending)
            field, chapter, cur, pending, in_appendix = f, None, None, [], False
            continue
        if field is None or in_appendix:
            continue
        pg = printed(page)
        for s in _lines(page):
            if s in RUNNING or _FOOT.match(s):
                continue
            if _APPENDIX.match(s):
                _no_orphan(pending)
                in_appendix = True
                stat["부록에서_멈춘_쪽"].append(pg)
                break
            if _CHAPTER.match(s) and _same_chapter(s, chapters):
                chapter = s
                continue
            m = _Q.match(s)
            if m:
                cur = {
                    "분야": field,
                    "장": chapter,
                    "문항": int(m.group(1)),
                    "쪽": pg,
                    "_글": [*pending, *([m.group(2)] if m.group(2) else [])],
                    "_규정": [],
                    "_상태": "글",
                }
                pending = []
                rows.append(cur)
                continue
            if cur is not None and s == "관련규정":
                cur["_상태"] = "규정"
                continue
            if cur is not None and cur["_상태"] == "규정":
                if _CITE_LINE.match(s):
                    cur["_규정"].append(s)
                    continue
                cur["_상태"] = "끝"
            if cur is None or cur["_상태"] == "끝":
                pending.append(s)
                continue
            cur["_글"].append(s)
    _no_orphan(pending)

    titles = {(f, q): t for f, q, t, _ in entries}
    for r in rows:
        body = r.pop("_글")
        r.pop("_상태")
        # 질의 = 처음으로 물음표로 끝나는 줄까지. 🚨 없으면 질의를 비우지 않고 멈추지도 않는다 — 계측에 올린다
        k = next((i for i, x in enumerate(body) if x.rstrip().endswith("?")), None)
        if k is None:
            stat["질의_물음표_없음"].append((r["분야"], r["문항"]))
            k = 0
        r["제목"] = titles.get((r["분야"], r["문항"]))
        r["질의"] = _n(" ".join(body[: k + 1]))
        r["답변"] = _n(" ".join(body[k + 1 :]))
        r["관련규정"] = _n(" ".join(r.pop("_규정")))
        r["관련규정_인용"], r["관련규정_기타"] = cites(r["관련규정"])
        if not r["관련규정"]:
            stat["관련규정_없음"].append((r["분야"], r["문항"]))
        r["인용표현"] = quotes(r)
        r["원천"] = SOURCE_ID
        r.update(REGIME)
    return rows, stat


def _no_orphan(pending: list[str]) -> None:
    """🔴 문항에 붙지 않은 글은 **버리지 않고 멈춘다** — 분야가 바뀌거나 부록이 시작될 때 · 끝에서 (D-220)."""
    if pending:
        raise ValueError(f"문항에 붙지 않은 글이 남았다 — 구조가 바뀌었다: {pending[:2]!r}")


def cites(basis: str) -> tuple[list[str], list[str]]:
    """관련규정 → (인용, 기타). 🚨 **화장품법 · 표시광고법의 「조 · 항 · 호」만** 인용으로 만든다 —
    그 밖(제14조 실증 · 제2조 정의 · 시행규칙 [별표5] 목 · 약사법 · 의료기기법 · 고시)은 원문 조각을 `기타` 에 둔다.
    ⛔ 호가 없는 조문을 억지로 가까운 호에 넣지 않는다 (지시서 §1 과 같은 원칙).

        「화장품법」 제13조제1항제1호, 제4호 및 제14조제1항 → ['002015:제13조제1항제1호', '002015:제13조제1항제4호'] · ['「화장품법」 제14조제1항']
    """
    got: list[str] = []
    other: list[str] = []
    for law, rest in _LAW_SEG.findall(basis):
        parts = [p.strip(" ,") for p in re.split(r"\s및\s", rest) if p.strip(" ,")]
        if not parts:
            other.append(f"「{law}」")
            continue
        for part in parts:
            m = _JO_HANG_HO.match(part.replace(" ", ""))
            # 🚨 가운뎃점 변이(･ U+FF65)는 `sep_norm` 으로 편다 — 「표시･광고의 공정화에 관한 법률」
            key = law_of_basis(f"{sep_norm(law)} {part}")
            lid = statute.STATUTE_ID.get(key) if key else None
            jo, hang = (int(m.group(1)), int(m.group(2) or 1)) if m else (0, 0)
            # 🔴 **위반 근거 조항만** 인용이 된다 — 제2조(정의)의 「제9호」 같은 호를 위반 호로 읽지 않는다 (D-220)
            if lid and m and m.group(3) and (lid, jo, hang) in _VIOLATION:
                got.append(statute.cite(lid, jo, hang, int(m.group(3))))
                tail = part.replace(" ", "")[m.end() :]
                while (mm := _MORE_HO.match(tail)) is not None:
                    got.append(statute.cite(lid, jo, hang, int(mm.group(1))))
                    tail = tail[mm.end() :]
                if tail.strip(" ,"):
                    other.append(f"「{law}」 {tail.strip(' ,')}")
            else:
                other.append(f"「{law}」 {part}")
    return list(dict.fromkeys(got)), other


def quotes(rec: dict) -> list[str]:
    """질의 · 답변의 인용부호 안 표현 — **라벨 판의 후보**다. 계수기는 `preprocess.text.quoted` 하나다 (D-160).

    🚨 줄을 이어 붙인 글에서 뜬다 — PDF 는 인용 한복판에서 줄을 바꾼다. 이 문서는 표가 아니라 문단이라
       옆 칸을 무는 사고(`quoted` 의 `same_line` 이 막으려던 것)가 없다.
    """
    return list(dict.fromkeys(quoted(f"{rec.get('질의', '')}\n{rec.get('답변', '')}")))


def verify(pgs: list[str]) -> list[str]:
    """🔴 목차와 대조한다 — 분야별 문항 수 · 번호 연속 · 문항이 목차가 말한 쪽에서 시작하는가."""
    entries, _ = toc(pgs)
    rows, _ = parse(pgs)
    bad: list[str] = []
    want = collections.Counter(f for f, *_ in entries)
    have = collections.Counter(r["분야"] for r in rows)
    if want != have:
        bad.append(f"분야별 문항 수 — 목차 {dict(want)} · 본문 {dict(have)}")
    for f in want:
        qs = [r["문항"] for r in rows if r["분야"] == f]
        if qs != list(range(1, len(qs) + 1)):
            bad.append(f"{f} 문항 번호가 이어지지 않는다")
    page_of = {(f, q): p for f, q, _, p in entries}
    for r in rows:
        p = page_of.get((r["분야"], r["문항"]))
        # 🚨 표지(Q) 줄이 있는 쪽을 쓴다 — 질의가 앞 쪽에서 시작해도 목차는 표지 쪽을 적는다(실측 · 어긋나면 여기서 보인다)
        if p is not None and r["쪽"] != p:
            bad.append(f"{r['분야']} Q{r['문항']} — 목차 {p}쪽 · 본문 {r['쪽']}쪽")
    return bad


#: 마스킹을 거는 자리 — 🚨 인용표현은 **마스킹된 본문에서 다시 뜬다**(`mfds_casebook.masked` 와 같은 이유)
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
    print(f"문항 {len(rows):,}")
    for (f, ch), v in sorted(
        collections.Counter((r["분야"], r["장"]) for r in rows).items(), key=str
    ):
        print(f"    {f:5} {v:>3}  {ch}")
    print(
        f"\n  인용표현 {sum(len(r['인용표현']) for r in rows):,}건 — 🔴 [참고 2] 적발 사례(캡처)는 담지 않는다 (D-18)"
    )
    print(
        f"  부록에서 멈춘 쪽 {stat['부록에서_멈춘_쪽']} — [참고 1] 법령 전재 · 2015 가이드라인 표를 담지 않는다"
    )
    ho = collections.Counter(c for r in rows for c in r["관련규정_인용"])
    print("\n  관련규정 인용 (문항 단위 · 🚨 문구 판정이 아니다)")
    for c, v in sorted(ho.items()):
        print(f"    · {v:>3}  {c}  유형 {statute.type_of(c)}")
    print(
        f"    · 기타 조각 {sum(len(r['관련규정_기타']) for r in rows)}  (제14조 · 제2조 · [별표5] 목 · 다른 법)"
    )
    for k in ("관련규정_없음", "질의_물음표_없음"):
        if stat[k]:
            print(f"  🚨 {k} {stat[k]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="질의응답집 PDF → 질의회신 레코드")
    ap.add_argument("--verify", action="store_true", help="목차와 대조한다")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    a = ap.parse_args()

    pgs = pages()
    if a.verify:
        bad = verify(pgs)
        if bad:
            print("🔴 목차와 본문이 어긋난다 — 파싱 결과를 믿지 않는다:", file=sys.stderr)
            for b in bad:
                print(f"  · {b}", file=sys.stderr)
            return 1
        print("★ 목차 대조 통과 — 분야별 문항 수 · 번호 · 쪽이 목차와 같다")

    rows, stat = parse(pgs)
    _report(rows, stat)

    if a.dump:
        bad = verify(pgs)
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
