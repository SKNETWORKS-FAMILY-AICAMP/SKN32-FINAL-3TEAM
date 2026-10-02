"""preprocess/mfds_cosmetic_faq_2020.py — 「화장품 분야 자주하는 질문집」(2020) PDF → **질의회신 레코드** (2026-10-03).

  uv run python -m preprocess.mfds_cosmetic_faq_2020            # 센다
  uv run python -m preprocess.mfds_cosmetic_faq_2020 --verify   # 목차(편 · 절 · 쪽) · 번호 연속과 대조한다
  uv run python -m preprocess.mfds_cosmetic_faq_2020 --dump     # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_cosmetic_faq_2020` (식약처 민원인안내서-1079-01 · 2020-12-10 · 147쪽 · 국민신문고 질의 선별)

──────────────────────────────────────────────────────────────
★ **레코드 = 문항 하나** — 「Qn」 한 줄 · 질의 · 「¡」로 시작하는 답변

  편(Ⅰ~Ⅹ)은 **목차의 쪽**으로 정한다 — 본문의 편 제목은 텍스트 층에 일부만 있다(Ⅲ · Ⅳ · Ⅸ · Ⅹ만 · 2026-10-03 실측).
  절(「1. 질병 및 의학적 효능·효과 관련」)은 목차 순서대로, **목차가 말한 쪽에서 그 번호로 시작하는 줄**을 만나면 넘긴다.
  🚨 절 앞에 문항이 올 수 있다 — Ⅳ 광고의 Q106~108 은 첫 절(58쪽) 앞의 총론이다. `절` 이 None 이다.
  「□ …」 줄은 절 안의 소제목이다 — 다음 소제목이나 절이 올 때까지 뒤 문항에 붙는다.
  실측(작업공간) — 문항 **235** · 광고 범위 **30**(Ⅳ 광고 Q106~132 27 · Ⅸ-3 천연·유기농 표시·광고 Q223~225 3).
  범위 밖인데 답변이 광고 금지 조문을 드는 문항 **10**(Q59 · 64 · 67 · 70 · 77 · 104 · 199 · 200 · 212 · 216) — `광고조문`.
  🚨 원장 09-30 ② 는 「Ⅳ 광고 Q106~131 26」이라 적었다 — Q132(72쪽 · 실증자료)도 Ⅳ 다(Ⅴ 는 73쪽부터). Ⅸ-3 의 3 은 이번에 더했다.

★ **문항을 다 싣고 `광고범위` 로 가른다** — 영업 등록 · 기재사항 · 수입통관은 광고 판단 범위 밖이다(레지스트리 caution).
  🚨 `광고범위` 는 **절 제목**으로 정한다(`AD_SECTIONS`) — 품목 분류(Ⅴ) · 기능성(Ⅶ) 문항에도 광고 문구가 나오나 절 단위로는 못 가른다.
     그래서 `광고조문` 을 따로 싣는다 — **답변이 화장품법 제13조 · 시행규칙 제22조 · [별표 5] · 실증 규정을 드는가**(기계 판정).
     범위 밖인데 `광고조문` 인 문항이 판독 판의 추가 후보다(제품명 · 기술제휴원 · 판매원 표시가 제13조로 판단된 문항들).

★ **라벨을 만들지 않는다** — `인용표현` 은 라벨 판의 후보다(`mfds_cosmetic_qa` 머리말과 같은 이유).
  답변은 조문을 글 속에 든다(「화장품법」 제13조1항1호) — 문항 단위 `관련규정` 칸이 없어 인용을 만들지 않는다.

★ **담지 않는 것** (D-159)
  · 점검표 · 머리말(부서 전화 · 팩스) · 제·개정 이력 · 목차 — 첫 문항 앞은 읽지 않는다.
  · 편 · 절 머리의 「& 관련 조항」 줄과 법령 전재 상자 — 문항 앞의 글이다(코퍼스 law_go_kr 에 있다). 줄 수를 센다.
  · [참고 문헌] — 여기서 멈춘다.
  · 전화번호는 여기서 `[전화]` 로 바꾼다(실측 1 — 답변 속 협회 대표 전화 · 레지스트리 masking 「전화번호」) — 마스킹 축에 전화가 없다.

★ **기준 시점 · 판정 지위** — 2020-12 기준 · `질의회신`(D-240). 2025 질문집 · 2025 지침이 우선한다(D-290 ③).
  🚨 화장품법 제13조제1항제3호(천연 · 유기농 오인)는 2025-01-31 삭제됐다 — 이 문서는 그 호를 현행으로 적는다.
  ★ 줄넘김은 **글자 좌표로 되살린다**(`preprocess.pdf_lines`) — 낱말 한가운데서 넘은 줄(「광\\n고」)은 붙이고
    빈칸에서 넘은 줄은 띄운다. 대조 어긋남 1.5%(1,152 쌍 중 17) — 모르면 띄운다.
  ★ 겹치는 문항(레지스트리 fragment_note) — 질의 4글자 조각 포함도로 쟀다(2026-10-03 · 작업공간):
    광고 범위 30 · 광고조문 10 가운데 2021 질의응답집 · 2025 질문집과 0.5 이상 겹치는 문항 **0**. 뺄 문항이 없다.
    2025 질문집과 같은 문항 7(Q1 · 3 · 16 · 22 · 25 · 31 · 74)은 전부 업 등록 · 표시기재 — 광고 범위 밖이다.
    ⬜ 문구 단위 중복(같은 인용 문구)은 판독 판을 골든에 넣을 때 거른다.

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

SOURCE_ID = "mfds_cosmetic_faq_2020"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_cosmetic_faq_2020.jsonl")

REGIME = {
    "문서": "안내서-1079-01",
    "발행일": "2020-12-10",
    "기준시점": "2020-12",
    "판정지위": "질의회신",
}

_ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
#: 쪽 바닥글 「- 56 -」
_FOOT = re.compile(r"^-\s*(\d{1,3})\s*-$")
_Q = re.compile(r"^Q(\d{1,3})$")
#: 답변의 시작 — 원천의 글머리표(¡ 로 뜬다)
_ANSWER = "¡"
_TOPIC = re.compile(r"^□\s*(.+)$")
#: 목차 — 「Ⅳ. 광고 ····56」 · 「1. 질병 및 의학적 효능·효과 관련 ····58」
_TOC_PART = re.compile(rf"^([{_ROMAN}])\.\s*(.+?)\s*·{{2,}}\s*(\d{{1,3}})$")
_TOC_SECTION = re.compile(r"^(\d)\.\s*(.+?)\s*·{2,}\s*(\d{1,3})$")
_SECTION_LINE = re.compile(r"^(\d)\.\s*(.+)$")
#: 본문의 편 제목 줄 「Ⅳ 광고」 — 글에 섞이지 않게 뺀다
_PART_LINE = re.compile(rf"^[{_ROMAN}]\.?\s+\S")
_REFERENCES = re.compile(r"^\[\s*참고\s*문헌\s*\]")
_PHONE = re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")
MASK_PHONE = "[전화]"

#: 광고 범위 — (편 번호, 절 번호 | None = 편 전체). 절 제목이 「광고」를 말하는 자리다 `[측정]` 2026-10-03 목차
AD_SECTIONS = frozenset({("Ⅳ", None), ("Ⅸ", 3)})
#: 답변이 표시·광고 금지 조문을 드는가 — 화장품법 제13조 · 시행규칙 제22조 · [별표 5] · 실증 규정.
#: 🚨 「기능성화장품 심사에 관한 규정 제13조」는 아니다 — 법 이름과 함께 볼 때만 센다
_AD_LAW = re.compile(
    r"화장품법[」｣]?\s*제\s*13\s*조|시행규칙[」｣]?\s*제\s*22\s*조|\[?\s*별표\s*5\s*\]|표시\s*[·ㆍ･‧]?\s*광고\s*실증"
)


def _n(s: str) -> str:
    return " ".join(s.split())


def _key(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s)


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


def printed(lines: list[str]) -> int | None:
    for s in reversed(lines):
        m = _FOOT.match(s)
        if m:
            return int(m.group(1))
    return None


def toc(pgs: list) -> list[dict]:
    """목차 → `[{편, 편제목, 쪽, 절: [{번호, 제목, 쪽}, …]}, …]`. 첫 문항 앞까지만 읽는다."""
    parts: list[dict] = []
    for p in pgs:
        ls = _lines(p)
        if any(_Q.match(s) for s in ls):
            break
        for s in ls:
            m = _TOC_PART.match(s)
            if m:
                parts.append(
                    {"편": m.group(1), "편제목": m.group(2), "쪽": int(m.group(3)), "절": []}
                )
                continue
            m = _TOC_SECTION.match(s)
            if m and parts:
                parts[-1]["절"].append(
                    {"번호": int(m.group(1)), "제목": m.group(2), "쪽": int(m.group(3))}
                )
    return parts


def _same(a: str, b: str) -> bool:
    """절 제목이 같은가 — 🚨 본문이 줄여 적는다(목차 「우수화장품 제조 및 품질관리기준(CGMP) 인증」 · 본문 「CGMP 인증」)."""
    x, y = _key(a), _key(b)
    return bool(x and y) and (x in y or y in x)


def parse(pgs: list) -> tuple[list[dict], dict]:
    """쪽 텍스트 → (문항 레코드, 계측). 🚨 마스킹은 여기서 하지 않는다 — 전화번호만 바꾼다."""
    parts = toc(pgs)
    #: 절을 목차 순서대로 편 — (편 색인, 절)
    order = [(i, s) for i, p in enumerate(parts) for s in p["절"]]
    rows: list[dict] = []
    stat: dict = {
        "쪽번호_없음": [],
        "편_없는_문항": [],
        "못_찾은_절": [],
        "답변_없음": [],
        "질의_물음표_없음": [],
        "문항_앞_줄": 0,
        "전화": 0,
    }
    nxt = 0  # 다음에 올 절
    section: dict | None = None
    section_part = -1
    topic: str | None = None
    cur: dict | None = None
    started = done = False
    for page in pgs:
        ls = _lines(page)
        if done:
            break
        if not started and not any(_Q.match(s) for s in ls):
            continue  # 🔴 첫 문항 앞(점검표 · 머리말 · 목차)은 담지 않는다
        started = True
        pg = printed(ls)
        if pg is None:
            stat["쪽번호_없음"].append(len(rows))
        pi = max((i for i, p in enumerate(parts) if pg is not None and p["쪽"] <= pg), default=-1)
        if pi != section_part and (section is None or pi > section_part):
            # 편이 바뀌었다 — 절 · 소제목이 끊긴다
            section, section_part, topic, cur = None, pi, None, None
        for s in ls:
            if _FOOT.match(s):
                continue
            if _REFERENCES.match(s):
                done = True
                break
            m = _SECTION_LINE.match(s)
            if (
                m
                and nxt < len(order)
                and order[nxt][0] == pi
                and order[nxt][1]["쪽"] == pg
                and int(m.group(1)) == order[nxt][1]["번호"]
                and _same(m.group(2), order[nxt][1]["제목"])
            ):
                section, topic, cur = order[nxt][1], None, None
                nxt += 1
                continue
            t = _TOPIC.match(s)
            if t:
                topic, cur = t.group(1), None
                continue
            q = _Q.match(s)
            if q:
                if pi < 0:
                    stat["편_없는_문항"].append(int(q.group(1)))
                cur = {
                    "편": f"{parts[pi]['편']}. {parts[pi]['편제목']}" if pi >= 0 else None,
                    "절": f"{section['번호']}. {section['제목']}" if section else None,
                    "소제목": topic,
                    "문항": int(q.group(1)),
                    "쪽": pg,
                    "광고범위": pi >= 0
                    and (
                        (parts[pi]["편"], None) in AD_SECTIONS
                        or (parts[pi]["편"], section["번호"] if section else None) in AD_SECTIONS
                    ),
                    "_글": [],
                }
                rows.append(cur)
                continue
            if cur is None:
                if not _PART_LINE.match(s):
                    stat["문항_앞_줄"] += 1  # 「& 관련 조항」 · 법령 전재 상자
                continue
            cur["_글"].append(s)
    stat["못_찾은_절"] = [f"{parts[i]['편']}-{s['번호']}" for i, s in order[nxt:]]

    for r in rows:
        body = r.pop("_글")
        a = next((i for i, s in enumerate(body) if s.startswith(_ANSWER)), None)
        if a is None:
            stat["답변_없음"].append(r["문항"])
            a = len(body)
        ask = join(body[:a])
        if (
            "?" not in ask
        ):  # 🚨 물음 뒤에 「(예) …」 · 「* …」 덧글이 붙는 문항이 있다(Q82 · Q137) — 끝이 아니라 있는지를 본다
            stat["질의_물음표_없음"].append(r["문항"])
        r["질의"] = _phone(ask, stat)
        r["답변"] = _phone(join(body[a:], clean=lambda x: x.removeprefix(_ANSWER)), stat)
        r["광고조문"] = bool(_AD_LAW.search(r["답변"]))
        r["인용표현"] = quotes(r)
        r["원천"] = SOURCE_ID
        r.update(REGIME)
    return rows, stat


def _phone(text: str, stat: dict) -> str:
    out, n = _PHONE.subn(MASK_PHONE, text)
    stat["전화"] += n
    return out


def verify(pgs: list) -> list[str]:
    """🔴 목차와 대조한다 — 절을 다 찾았나 · 번호가 1 부터 이어지나 · 편마다 문항이 있나 · 답변이 있나."""
    parts = toc(pgs)
    rows, stat = parse(pgs)
    bad: list[str] = []
    if not parts:
        return ["목차를 못 읽었다"]
    for k in ("쪽번호_없음", "편_없는_문항", "못_찾은_절", "답변_없음"):
        if stat[k]:
            bad.append(f"{k} — {stat[k][:8]}")
    qs = [r["문항"] for r in rows]
    if qs != list(range(1, len(qs) + 1)):
        bad.append("문항 번호가 1 부터 이어지지 않는다")
    have = {r["편"] for r in rows}
    for p in parts:
        if f"{p['편']}. {p['편제목']}" not in have:
            bad.append(f"문항이 없는 편 — {p['편']}. {p['편제목']}")
    if not any(r["광고범위"] for r in rows):
        bad.append("광고 범위 문항이 0 이다")
    return bad


MASK_FIELDS = ("질의", "답변")


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
    ad = [r for r in rows if r["광고범위"]]
    more = [r["문항"] for r in rows if r["광고조문"] and not r["광고범위"]]
    print(
        f"문항 {len(rows):,} — 광고 범위 {len(ad)} · 범위 밖인데 광고 조문을 드는 문항 {len(more)}"
    )
    print(f"    범위 밖 후보 Q{more}")
    for part, v in collections.Counter(r["편"] for r in rows).items():
        print(f"    {v:>3}  {part}")
    print("\n  광고 범위의 절")
    for (part, sec), v in collections.Counter((r["편"], r["절"]) for r in ad).items():
        print(f"    {v:>3}  {part} / {sec}")
    print(
        f"\n  인용표현 {sum(len(r['인용표현']) for r in rows):,}건 — 광고 범위 {sum(len(r['인용표현']) for r in ad):,}건"
    )
    print(
        f"  문항 앞의 줄 {stat['문항_앞_줄']}(관련 조항 · 법령 전재 — 담지 않았다) · 전화번호 {stat['전화']}곳을 {MASK_PHONE} 로 바꿨다"
    )
    for k, v in stat.items():
        if v and k not in ("문항_앞_줄", "전화"):
            print(f"  🚨 {k} {v}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="화장품 분야 자주하는 질문집(2020) PDF → 질의회신 레코드"
    )
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
        print("★ 목차 대조 통과 — 절을 다 찾았다 · 번호가 이어진다 · 편마다 문항이 있다")

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
