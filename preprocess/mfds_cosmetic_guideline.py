"""preprocess/mfds_cosmetic_guideline.py — 「화장품 표시·광고 관리 지침」 PDF → **금지표현 · 실증대상 항목** (2026-10-03).

  uv run python -m preprocess.mfds_cosmetic_guideline            # 센다
  uv run python -m preprocess.mfds_cosmetic_guideline --verify   # 문서가 스스로 밝힌 구조와 대조한다
  uv run python -m preprocess.mfds_cosmetic_guideline --dump     # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_cosmetic_ad_guideline` (식약처 민원인안내서-0086-07 · 2025-08-14 · 17쪽)

──────────────────────────────────────────────────────────────
★ **레코드 = 항목 하나** — 표의 가운뎃점(·) 한 줄이 항목이다

  [별표 1] 화장품 표시·광고의 표현 범위 및 기준 — 「□ 화장품법 제13조 제1항 제N호 관련」 절마다 표가 하나씩이다
           (제1호 의약품 오인 · 제2호 기능성화장품 오인 · 제4호 그 밖에 사실과 다르게). 칸은 구분 · 금지표현 · 비고.
  [별표 2] 화장품 표시·광고 주요 실증대상 — 칸은 구분 · 실증 대상 · 비고(무엇으로 입증하나).

  실측(2026-10-03 · 클론 B 원문 · 작업공간) — [별표 1] **85** 항목(제1호 54 · 제2호 6 · 제4호 25) · [별표 2] **20** 항목 ·
  단서 있는 금지표현 25 · 줄을 넘은 항목 34 · 쪽을 넘어 이은 자리 2(14 · 16쪽) · 줄넘김 164.
  🚨 **셀이 쪽을 넘는다** — 13쪽 끝 항목이 14쪽 첫 행으로, 15쪽 끝 비고가 16쪽 첫 행으로 이어진다.
     쪽 첫 행의 구분 칸이 비어 있고 글이 가운뎃점으로 시작하지 않으면 앞 항목에 잇는다(`parse`).
  🚨 **줄넘김이 낱말 한가운데에 있다** — 「코스/메슈티컬」 · 「않았/다는」. 글자와 좌표만으로는 띄어쓰기를 못 되살린다.
     줄넘김 전부를 읽고 **붙일 자리를 표(`JOINS`)로 적었다** — 그 밖은 빈칸이다. 표는 이 판의 것이다:
     줄넘김 수가 달라지거나 안 쓰인 이음이 생기면 `--verify` 가 멈춘다(`check_edition`). `줄넘김: True` 는 줄을 넘은 항목의 표시다.

★ **라벨도 사전도 만들지 않는다** — 문서가 적은 것을 항목 단위로 옮길 뿐이다.
  · `근거` 는 절 제목이 밝힌 호의 인용이다(`collect/statute.py` 꼴 · D-282). 🚨 화장품법 제13조①4호는 호만으로 유형을 못 가른다
    — `statute.type_of` 가 None 을 낸다(D-220).
  · `단서` 는 **같은 행의 비고**다. 한 행에 항목이 여럿이면 그 비고가 어느 항목의 것인지 표는 말하지 않는다 —
    `단서_공유: True` 로 표시한다. 🚨 금지표현을 「단, …는 제외」에서 떼어 쓰지 않는다 — 조건부다(레지스트리 fragment_note · D-290 ④).
  · [별표 2] 의 항목은 금지가 아니라 **실증하면 쓸 수 있는 표현**이다(조건 B 의 재료 — 실증 분기).

★ **구속력은 「해설」이다** (D-290 ②) — 검색 · 설명 · 예외 조건의 출처로 쓰고 **근거 조문으로 인용하지 않는다.**
  판정 근거는 화장품법 제13조 · 시행규칙 [별표 5] · 고시(law_go_kr)로 소급한다. 그래서 이 항목들은 **하한 재료가 아니다**
  (D-313 ③ — 하한 재료는 법령 · 고시가 열거한 용어뿐) — 사전의 유형 후보 재료다.
  🚨 제·개정이 잦다(2024-05 · 2025-01 · 2025-08) — 판본(안내서 번호 · 발행일)을 레코드마다 싣는다. 새 판이 오면 옛 판을 남기지 않는다(D-290 ③).

★ **담지 않는 것** (D-159 — 담지 않기가 먼저다)
  · 2쪽 점검표(담당자 · 부서장 실명) · 3쪽 · 17쪽 판권면(발행인 · 편집위원 실명 · 부서 전화) — 판정 재료가 아니다.
    레지스트리 masking 의 「성명 · 전화 · 팩스」는 **여기서 담지 않아** 지킨다 — 별표 쪽만 읽는다(`_APPENDIX_1` 부터 `_COLOPHON` 앞까지).
  · 본문 Ⅰ~Ⅲ(목적 · 적용 범위 · 주의사항) — 주의사항 8 의 ISO 지수 병기 문안은 [별표 2] 3. 항목의 조건이나, 문단이라 항목으로 못 옮긴다 ⬜

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

SOURCE_ID = "mfds_cosmetic_ad_guideline"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_cosmetic_ad_guideline.jsonl")

#: 판본 · 구속력 — 레코드마다 싣는다. 🚨 `구속력` 값은 D-290 ② 의 둘(법령 | 해설)
REGIME = {
    "문서": "안내서-0086-07",
    "발행일": "2025-08-14",
    "기준시점": "2025-08",
    "구속력": "해설",
}

_APPENDIX_1 = re.compile(r"^\[별표\s*1\]")
_APPENDIX_2 = re.compile(r"^\[별표\s*2\]")
#: 판권면 — 여기서 멈춘다. 그 뒤는 담지 않는다(발행인 · 편집위원 실명)
_COLOPHON = re.compile(r"^발\s*행\s*일")
#: 절 제목 「□ 화장품법 제13조 제1항 제1호 관련」
_SECTION = re.compile(r"^□\s*화장품법\s*제\s*(\d+)\s*조\s*제\s*(\d+)\s*항\s*제\s*(\d+)\s*호\s*관련")
#: 쪽 바닥글 「- 9 -」
_FOOT = re.compile(r"^-\s*(\d{1,3})\s*-$")
#: 표 머리 — 둘째 칸 이름으로 별표를 가른다(공백을 접어 댄다)
_HEAD = {"금지표현": 1, "실증대상": 2}
#: 항목의 시작 — 가운뎃점. 🚨 원천이 `·`(U+00B7) 와 `․`(U+2024) 를 섞어 쓴다
_BULLET = re.compile(r"^[·․]\s*")
_EXAMPLE = re.compile(r"^<\s*예시\s*>\s*")
_SUB = re.compile(r"^-\s*")
#: 각주 표지 — 「표현1)」 · 「지수2)」. 글자 뒤에 붙은 숫자 + 닫는 괄호
_NOTE_MARK = re.compile(r"(?<=[가-힣'’])(\d)\)")

#: [별표 1] 이 다루는 호 — 문서가 스스로 밝힌 구조다(레지스트리 scale · 제3호 절은 없다 — 2025-01-31 삭제)
EXPECTED_HO = (1, 2, 4)
#: [별표 2] 의 구분 수
EXPECTED_GROUPS_2 = 3

#: 줄 끝이 가운뎃점이면 다음 줄과 붙인다 — 「표시·/광고」 · 「진단·/치료」
_GLUE_TAIL = "·"
#: 붙일 자리 (앞 줄의 끝 토막, 뒷 줄의 첫 토막) — 줄넘김 167 쌍을 읽고 적었다 `[측정]` 2026-10-03.
#: 🚨 양쪽 다 쓰이는 말(들어 있는 · 자외선 차단 · 인체 외)은 띄운 채 둔다 — 띄운 쪽이 맞춤법 원칙이다
JOINS: frozenset[tuple[str, str]] = frozenset(
    {
        ("뛰어", "나다’,"),
        ("활성화시", "킨다."),
        ("억제", "한다."),
        ("유전자", "(DNA)"),
        ("정보제", "공을"),
        ("코스", "메슈티컬,"),
        ("의약", "품"),
        ("화이트닝", "(whitening),"),
        ("기능성", "화장품"),
        ("피부", "과시술용,"),
        ("않았", "다는"),
        ("無", "(무)"),
        ("규", "정｣"),
        ("사", "용한"),
        ("경우", "에는"),
        ("엑소", "좀"),
        ("특정성분(엑소", "좀,"),
        ("것으", "로"),
        ("다르거", "나"),
        ("‘이너", "케어’,"),
        ("사용", "하려면"),
        ("유기농화", "장품"),
        ("안내서」(대한화장", "품협회)에"),
        ("안내서」(대한화장품", "협회)에"),
        ("피부", "노화"),
        ("기능성", "화장품으로서"),
        ("심사", "받은"),
        ("불가", "능한"),
        ("제조", "관리기록서나"),
        ("원료시험성", "적서"),
        ("16128(가이드", "라인)에"),
        ("방지", "하기"),
    }
)
#: 예시가 갈리는 자리 — 줄마다 예시 하나인 묶음. 그 밖의 예시 줄넘김은 한 예시가 줄을 넘은 것이다
EXAMPLE_BREAKS: frozenset[tuple[str, str]] = frozenset(
    {("효과", "피부결"), ("개선", "2주"), ("완료", "oo시험검사기관의")}
)
#: 이음 표를 적은 판의 줄넘김 수 `[측정]` 2026-10-03 — 한 글 안의 줄넘김(167 쌍 가운데 예시가 갈리는 3 은 줄넘김이 아니다)
EXPECTED_BREAKS = 164


def _n(s: str) -> str:
    return " ".join(s.split())


def pages() -> list[dict]:
    """쪽별 `{쪽, 줄, 표}` — 별표 쪽만. 🚨 pdfplumber 의 표 추출을 쓴다(칸이 줄마다 섞이지 않는다)."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("pdfplumber 가 없다 — 고치는 법:  uv sync") from e

    got = store.current_files(RAW_DIR, "*.pdf")
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 pdf 가 없다 —\n  먼저: uv run python launcher.py collect {SOURCE_ID}"
        )
    out: list[dict] = []
    with pdfplumber.open(got[0]) as d:
        for pg in d.pages:
            lines = [s for s in (_n(x) for x in (pg.extract_text() or "").split("\n")) if s]
            out.append({"줄": lines, "표": pg.extract_tables()})
    return out


def printed(lines: list[str]) -> int | None:
    """인쇄 쪽 번호 — 바닥글 「- 9 -」."""
    for s in reversed(lines):
        m = _FOOT.match(s)
        if m:
            return int(m.group(1))
    return None


class _Glue:
    """줄을 잇는다 — **붙일 자리는 표(`JOINS`)가 정한다.** 그 밖의 줄넘김은 빈칸이다.

    🚨 PDF 는 칸 너비에서 글자 단위로 줄을 바꾼다 — 「코스/메슈티컬」처럼 낱말 한가운데서도 넘고, 줄 끝의 빈칸은
       글자로 남지 않는다(2026-10-03 글자 좌표 실측 — 낱말 사이에서 넘은 줄도 낱말 안에서 넘은 줄도 칸 오른쪽 끝에서 끝난다).
       그래서 글자와 좌표만으로는 띄어쓰기를 못 되살린다 — 줄넘김 전부를 읽고 붙일 자리를 표로 적었다.
    """

    def __init__(self) -> None:
        self.count = 0
        self.used: set[tuple[str, str]] = set()

    def text(self, lines: list[str]) -> str:
        out = ""
        for s in (x for x in lines if x):
            if not out:
                out = s
                continue
            self.count += 1
            pair = (out.split()[-1], s.split()[0])
            if pair in JOINS:
                self.used.add(pair)
                out += s
            elif out.endswith(_GLUE_TAIL):
                out += s
            else:
                out += " " + s
        return out

    def examples(self, lines: list[str]) -> list[str]:
        """예시 줄 → 예시 목록. 「- …」 줄과 `EXAMPLE_BREAKS` 의 자리에서 새 예시가 시작한다."""
        groups: list[list[str]] = []
        for x in lines:
            sub = bool(_SUB.match(x))
            x = _SUB.sub("", x)
            starts = (
                sub or not groups or (groups[-1][-1].split()[-1], x.split()[0]) in EXAMPLE_BREAKS
            )
            if starts:
                groups.append([x])
            else:
                groups[-1].append(x)
        return [self.text(g) for g in groups]


def _cell_lines(cell: str | None) -> list[str]:
    return [s for s in (_n(x) for x in (cell or "").split("\n")) if s]


def _split_cell(cell: str | None) -> tuple[list[str], list[dict]]:
    """칸 글 → (앞 항목에 이을 머리 줄, 항목들).

    항목 = `{줄: [표현의 줄…], 하위: [[줄…], …], 예시: [줄…]}`. 가운뎃점 앞에 온 줄은 **앞 쪽에서 넘어온 글**이다.
    """
    head: list[str] = []
    items: list[dict] = []
    mode = "head"
    for s in _cell_lines(cell):
        if _BULLET.match(s):
            items.append({"줄": [_BULLET.sub("", s)], "하위": [], "예시": []})
            mode = "줄"
        elif not items:
            head.append(s)
        elif _EXAMPLE.match(s):
            rest = _EXAMPLE.sub("", s)
            if rest:
                items[-1]["예시"].append(rest)
            mode = "예시"
        elif mode == "예시":
            items[-1]["예시"].append(s)
        elif _SUB.match(s):
            items[-1]["하위"].append([_SUB.sub("", s)])
            mode = "하위"
        elif mode == "하위":
            items[-1]["하위"][-1].append(s)
        else:
            items[-1]["줄"].append(s)
    return head, items


def parse(pgs: list[dict]) -> tuple[list[dict], dict]:
    """항목 레코드와 계측."""
    rows: list[dict] = []
    glue = _Glue()
    stat: dict = {
        "쪽번호_없음": [],
        "모르는_표": [],
        "절_없는_표": [],
        "머리_없는_이음": [],
        "빈_항목": [],
        "이은_쪽": [],
    }
    annex = 0  # 0 = 아직 별표 앞
    ho: tuple[int, int, int] | None = None
    group = ""
    for pg in pgs:
        lines = pg["줄"]
        if any(_COLOPHON.match(s) for s in lines):
            break  # 🔴 판권면부터는 담지 않는다
        if any(_APPENDIX_1.match(s) for s in lines):
            annex = 1
        if any(_APPENDIX_2.match(s) for s in lines):
            annex, ho, group = 2, None, ""
        if not annex:
            continue
        page = printed(lines)
        if page is None:
            stat["쪽번호_없음"].append(len(rows))
        for s in lines:
            m = _SECTION.match(s)
            if m:
                ho = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                group = ""
        for tb in pg["표"]:
            if not tb or len(tb[0]) != 3:  # noqa: PLR2004 — 칸 셋(구분 · 표현 · 비고)
                stat["모르는_표"].append(page)
                continue
            kind = _HEAD.get("".join((tb[0][1] or "").split()))
            if kind is None:
                stat["모르는_표"].append(page)
                continue
            if kind != annex or (kind == 1 and ho is None):
                stat["절_없는_표"].append(page)
                continue
            for r, row in enumerate(tb[1:]):
                g = glue.text(_cell_lines(row[0]))
                head, items = _split_cell(row[1])
                note_lines = _cell_lines(row[2])
                carried = r == 0 and not g and (head or (not items and note_lines))
                if carried:
                    # 🚨 앞 쪽 마지막 항목이 넘어온 것이다 — 표현(머리)과 비고를 앞 항목에 잇는다
                    if not rows:
                        stat["머리_없는_이음"].append(page)
                    else:
                        prev = rows[-1]
                        key = _NOTE_KEY[kind]
                        if head:
                            _carry_head(prev, head, glue)
                        if note_lines:
                            prev[key] = glue.text([prev.get(key) or "", *note_lines])
                        stat["이은_쪽"].append(page)
                    note = ""
                else:
                    if head:
                        stat["머리_없는_이음"].append(page)
                    note = glue.text(note_lines)
                if g:
                    group = g
                for it in items:
                    text = _NOTE_MARK.sub("", glue.text(it["줄"]))
                    if not text:
                        stat["빈_항목"].append(page)
                        continue
                    rec = {
                        "별표": kind,
                        "근거": statute.cite(str(statute.COSM[0]), *ho)
                        if kind == 1 and ho
                        else None,
                        "구분": group,
                        "표현": text,
                        "하위": [glue.text(x) for x in it["하위"]],
                        "예시": glue.examples(it["예시"]),
                        _NOTE_KEY[kind]: note or None,
                        "단서_공유": len(items) > 1 and bool(note),
                        "줄넘김": len(it["줄"]) > 1,
                        "쪽": page,
                        "원천": SOURCE_ID,
                        "층": "3층 판단규범",
                        **REGIME,
                    }
                    rows.append(rec)
    stat["줄넘김_수"] = glue.count
    stat["안_쓴_이음"] = sorted(JOINS - glue.used)
    return rows, stat


#: 비고 칸의 이름 — [별표 1] 은 예외 조건(단서) · [별표 2] 는 입증 방법
_NOTE_KEY = {1: "단서", 2: "입증"}


def _carry_head(prev: dict, head: list[str], glue: _Glue) -> None:
    """쪽을 넘어온 머리 줄을 앞 항목에 잇는다 — 「<예시>」 줄부터는 예시 칸으로 간다."""
    cut = next((i for i, s in enumerate(head) if _EXAMPLE.match(s)), len(head))
    prev["표현"] = _NOTE_MARK.sub("", glue.text([prev["표현"], *head[:cut]]))
    prev["줄넘김"] = True
    if cut < len(head):
        first = _EXAMPLE.sub("", head[cut])
        prev["예시"] = [*prev["예시"], *glue.examples([x for x in (first, *head[cut + 1 :]) if x])]


def check_edition(stat: dict) -> list[str]:
    """🔴 **판본 대조** — 이음 표는 이 판(안내서-0086-07)의 줄넘김을 읽고 적은 것이다.

    줄넘김 수가 다르거나 안 쓴 이음이 있으면 판이 바뀐 것이다 — 줄넘김을 다시 읽는다. 합성 글(테스트)에는 걸지 않는다.
    """
    bad: list[str] = []
    if stat["줄넘김_수"] != EXPECTED_BREAKS:
        bad.append(
            f"줄넘김 {stat['줄넘김_수']} · 이음 표를 적은 판은 {EXPECTED_BREAKS} — 판이 바뀌었다"
        )
    if stat["안_쓴_이음"]:
        bad.append(f"쓰이지 않은 이음 {stat['안_쓴_이음']} — 판이 바뀌었다")
    return bad


def verify(pgs: list[dict]) -> list[str]:
    """🔴 문서가 스스로 밝힌 구조와 대조한다 — 호 절 셋 · [별표 2] 구분 셋 · 빈 구분 · 모르는 표."""
    rows, stat = parse(pgs)
    bad: list[str] = []
    for k in ("쪽번호_없음", "모르는_표", "절_없는_표", "머리_없는_이음", "빈_항목"):
        if stat[k]:
            bad.append(f"{k} — {stat[k]}")
    one = [r for r in rows if r["별표"] == 1]
    two = [r for r in rows if r["별표"] == 2]  # noqa: PLR2004
    hos = sorted({statute.parse(r["근거"])[3] for r in one if r["근거"]})
    if tuple(hos) != EXPECTED_HO:
        bad.append(f"[별표 1] 의 호 — {hos} (기대 {list(EXPECTED_HO)})")
    if any(not r["근거"] for r in one):
        bad.append("[별표 1] 항목에 근거 호가 없다")
    groups = list(dict.fromkeys(r["구분"] for r in two))
    if len(groups) != EXPECTED_GROUPS_2:
        bad.append(f"[별표 2] 의 구분 — {len(groups)} (기대 {EXPECTED_GROUPS_2})")
    if any(not r["구분"] for r in rows):
        bad.append("구분이 빈 항목이 있다")
    if not one or not two:
        bad.append(f"별표가 비었다 — [별표 1] {len(one)} · [별표 2] {len(two)}")
    return bad


#: 마스킹을 거는 자리 — 문서가 적은 글 전부. 🚨 실명 · 전화는 별표에 없다(담지 않은 쪽에 있다)
MASK_FIELDS = ("표현", "단서", "입증")


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
        out.append(rec)
    return out, changed, log


def _report(rows: list[dict], stat: dict) -> None:
    one = [r for r in rows if r["별표"] == 1]
    two = [r for r in rows if r["별표"] == 2]  # noqa: PLR2004
    print(f"항목 {len(rows):,} — [별표 1] 금지표현 {len(one)} · [별표 2] 실증대상 {len(two)}")
    print("\n  [별표 1] 근거 호 (절 제목이 밝힌 것 · 🚨 유형은 호만으로 못 가르는 것이 있다)")
    for c, v in sorted(collections.Counter(r["근거"] for r in one).items()):
        print(f"    · {v:>3}  {c}  유형 {statute.type_of(c)}")
    print(
        f"\n  단서 있는 금지표현 {sum(1 for r in one if r['단서'])} — 그중 행을 함께 쓰는 것 "
        f"{sum(1 for r in one if r['단서_공유'])} · 🚨 단서를 떼어 쓰지 않는다 (D-290 ④)"
    )
    print(
        f"  예시 있는 항목 {sum(1 for r in rows if r['예시'])} · 하위 항목 있는 것 {sum(1 for r in rows if r['하위'])}"
    )
    print(
        f"  줄을 넘은 항목 {sum(1 for r in rows if r['줄넘김'])} · 줄넘김 {stat['줄넘김_수']} — 붙인 자리 {len(JOINS) - len(stat['안_쓴_이음'])}/{len(JOINS)}"
    )
    if stat["이은_쪽"]:
        print(f"  쪽을 넘어 이은 자리 {stat['이은_쪽']}")
    for k, v in stat.items():
        if v and k not in ("이은_쪽", "줄넘김_수"):
            print(f"  🚨 {k} {v}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="화장품 표시·광고 관리 지침 PDF → 금지표현 · 실증대상 항목"
    )
    ap.add_argument("--verify", action="store_true", help="문서가 밝힌 구조와 대조한다")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    a = ap.parse_args()

    pgs = pages()
    bad = verify(pgs) + check_edition(parse(pgs)[1])
    if a.verify:
        if bad:
            print("🔴 문서 구조와 어긋난다 — 파싱 결과를 믿지 않는다:", file=sys.stderr)
            for b in bad:
                print(f"  · {b}", file=sys.stderr)
            return 1
        print("★ 구조 대조 통과 — 호 절 셋 · [별표 2] 구분 셋 · 빈 구분 없음 · 이음 표의 판과 같다")

    rows, stat = parse(pgs)
    _report(rows, stat)

    if a.dump:
        if bad:  # 🔴 대조가 깨진 파싱은 파생물로 내보내지 않는다 (D-72)
            print(
                f"\n🔴 구조 대조 실패 {len(bad)}건 — 쓰지 않았다. `--verify` 로 본다",
                file=sys.stderr,
            )
            return 1
        out, changed, log = masked(rows)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'} · 치환 {len(log)}건")
        print(f"  → {OUT}  ({len(out):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
