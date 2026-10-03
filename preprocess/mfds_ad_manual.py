"""preprocess/mfds_ad_manual.py — 「허위·과대광고 판별 매뉴얼」(2015-03) PDF → **적발 사례 레코드** (2026-10-03).

  uv run python -m preprocess.mfds_ad_manual                # 센다
  uv run python -m preprocess.mfds_ad_manual --verify       # 목차(구역 · 쪽 범위)와 대조한다
  uv run python -m preprocess.mfds_ad_manual --people       # 가린 자리 · 남은 이름 후보를 화면에만 낸다(사람 확인용)
  uv run python -m preprocess.mfds_ad_manual --dump         # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_ad_judge_manual_2015` (식약처 「허위·과대광고 판별 매뉴얼」 · 2015-03 · 67쪽)

──────────────────────────────────────────────────────────────
★ **레코드 = 사례 하나** — 원천이 사례마다 다섯 칸을 적는다

    ▶ 위반 구분 · ▶ 위반 내용 · ▶ 광고 매체 · ▶ 과대광고 문구 · ▶ 처분내용(근거)

  실측(2026-10-03 · 클론 B 원문 · 작업공간) — 사례 **80**(식품 37 · 건강기능식품 28 · 축산물 15) · 처분 칸 65
  (축산물 15 건에는 처분 칸이 없다) · 목차 대조 통과 · 사람 가림 21 곳 · 남은 이름 후보 0(기기 실행 2026-10-03 — 사례 수 · 가림 수 같음).
  🚨 **PDF 한 쪽이 책의 두 쪽(펼침)이다** — 통째로 읽으면 왼쪽 사례와 오른쪽 사례의 줄이 섞인다.
     쪽을 좌우 반으로 잘라 따로 읽는다(`pages`). 반쪽 하나에 사례는 하나뿐이다(실측 80/80 · `verify` 가 본다).
  🚨 글자 간격 허용값을 좁힌다(`X_TOLERANCE`) — 기본값으로는 「수면장애등이사라집니다」처럼 띄어쓰기가 사라진다.

★ **라벨을 만들지 않는다** — `위반구분` · `처분근거` 는 원천의 선언을 옮긴 것이다.
  · 근거가 **구법**이다(식품위생법 시행규칙 제8조 — 식품표시광고법 2019 시행 전). 현행 호는 라벨 판(지시서)이 붙인다.
  · 🚨 기준 시점이 지난 자료다 — 판단 사례로만 쓰고 근거 조문으로 인용하지 않는다(D-290 ③ · 레지스트리 caution).
  · 문구 한 덩어리에 문장이 여럿이다. 어느 문장이 위반인지는 원천이 적지 않았다 — 문장 분할 · 판독은 라벨 판의 일이다.

★ **담지 않는 것** (D-159 — 담지 않기가 먼저다)
  · 광고 캡처 이미지(약 1,080 개) — 광고주 저작물이다(D-18 · D-133). 문서가 글자로 적은 문구만 사실로 취한다
  · 「범위」 절(10~20쪽) — 조문 해설이다. 조문은 코퍼스(law_go_kr)에 있다
  · 떴다방 절(111쪽~) — 다섯 칸 꼴의 사례가 없다(요약 서술 · 단속 보도 인용)
  · 붙임(관련 법령)

★ **사람이 특정될 수 있는 자리는 여기서 가린다** — `redact_people`
  `preprocess.mask` 의 사람 축은 「대표이사 홍길동」 꼴을 보는 규칙이라 이 문서에서는 좁게 0 · 넓게도 1 곳만 걸린다.
  그래서 이 문서의 꼴에 맞춘 가림을 **마스킹 앞에** 건다.
  · 체험자 「이름 (남, 63세)」 → 「[대표] (남, 60대)」 — 나이는 10 년 단위(D-133 ④)
  · 체험자 「(대구, 이름)」 → 「(대구, [대표])」 — 지역은 광역 단위라 둔다(D-133 ④)
  · 체험자 「(이름, 39세, 사는 곳)」 → 「([대표], 30대, [주소])」 — 사는 곳이 시 · 동네 단위다
  · 체험자 「이름(34세 …」 · 「이름씨」 → 이름만 가린다(성씨로 시작하는 세 글자)
  · 「전문의 이름(」 · 「이름 박사는」 · 「[외국인 이름 박사]」 → 이름만 가린다. 직함은 남긴다(자국을 남긴다 — `mask.mask_person` 과 같다)
  🚨 **규칙은 본 꼴만 잡는다** — 그래서 `--people` 이 가린 자리와 **남은 이름 후보**를 함께 낸다. 사람이 확인한다.
  🚨 자국은 `mask.MASK_CEO` 를 쓴다 — 원천이 제품명을 가린 `○○○` 와 섞이지 않게(D-166).

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed · `preprocess.mask.apply_policy`).
   2026-10-03 현재 `POLICY` 에 이 원천이 없다 — `--dump` 는 멈춘다(검토요청 2026-10-03 식품사례 3종 · 2인 확인 대기).
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
from preprocess.mask import _SURNAMES, MASK_ADDR, MASK_CEO

SOURCE_ID = "mfds_ad_judge_manual_2015"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_ad_judge_manual_2015.jsonl")

#: 문서 시점 — 레코드마다 싣는다. 없으면 다음 사람이 현행 기준으로 읽는다 (D-290 ③)
REGIME = {
    "문서": "허위·과대광고 판별 매뉴얼",
    "발행일": "2015-03",
    "기준시점": "2015-03",
}
#: 처분 칸이 있는 사례의 판정 지위. 🚨 값 이름은 `[임의]` 이고 판정 경로에 있다 (D-240 의 값 목록)
STATUS_SANCTION = "행정처분"

#: pdfplumber 글자 간격 허용값 `[측정]` — 3(기본)은 낱말이 붙고 2 이하는 같다(공백 비 0.178 → 0.204 · 2026-10-03)
X_TOLERANCE = 2

#: 다섯 칸의 표지. 🚨 원천이 띄어쓰기를 섞어 쓴다 — 「위반구분」 · 「위반 구분」 · 「과대광고문구」 · 「과대광고 문구」
FIELDS = {
    "위반구분": r"위반\s*구분",
    "위반내용": r"위반\s*내용",
    "광고매체": r"광고\s*매체",
    "문구": r"과대\s*광고\s*문구",
    "처분": r"처분\s*내용\s*\(근거\)",
}
_LABEL = re.compile(
    r"▶\s*(?:" + "|".join(f"(?P<{k}>{v})" for k, v in FIELDS.items()) + r")\s*[:：]\s*"
)
#: 처분 칸 없이도 사례인 것 — 앞 네 칸은 늘 있어야 한다 (D-220)
REQUIRED = ("위반구분", "위반내용", "광고매체", "문구")

#: 쪽 바닥글 — 왼쪽 「26 MINISTRY …」 · 오른쪽 「MINISTRY … 27」. 인쇄 쪽 번호는 목차와 대조할 **독립된 선언**이다
_FOOT = re.compile(
    r"^(?:(\d{1,3})\s+MINISTRY OF FOOD AND DRUG SAFETY|MINISTRY OF FOOD AND DRUG SAFETY\s+(\d{1,3}))$"
)
#: 쪽 머리글 — 사례 글에 섞이면 안 된다
_RUNNING = re.compile(r"^●+\s*허위[•·]과대광고\s*판별\s*매뉴얼$")
#: 처분 칸 「영업정지[식품위생법 시행규칙 제8조(…)①항2호]」 → (처분, 근거)
_SANCTION = re.compile(r"^(?P<처분>[^\[]*)\[(?P<근거>.*)\]\s*$", re.S)

#: 목차의 사례 구역 — 「위반 사례 및 적발 사례」 아래 세 줄. 떴다방(111쪽~)에는 다섯 칸 사례가 없다
SECTIONS = ("식품", "건강기능식품", "축산물")
_TOC_HEAD = re.compile(r"^위반\s*사례\s*및\s*적발\s*사례\s+(\d{1,3})$")
_TOC_ROW = re.compile(r"^([1-9])\.\s*(\S+)\s+(\d{1,3})$")
_TOC_END = re.compile(r"^노인\s*대상.*?(\d{1,3})$")

# ── 사람 가림 ────────────────────────────────────────────────────────────────
#: 광역 시·도 `[문헌]` 행정구역 — 「(지역, 이름)」 의 앞 칸. 🚨 「(허위, 과장)」 같은 나열을 사람으로 읽지 않게 지역으로 좁힌다
_REGION = (
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
)
_NAME = r"[가-힣]{2,4}"
#: 성씨로 시작하는 세 글자 이름 — 성씨 표는 `preprocess.mask` 의 것이다 (D-99 · 사본을 두지 않는다)
_NAME3 = rf"[{_SURNAMES}][가-힣]{{2}}"
#: 체험자 「이름 (남, 63세)」
_P_SEX_AGE = re.compile(rf"({_NAME})(\s*\(\s*[남여]\s*,\s*)(\d{{2}})세(\s*\))")
#: 체험자 「(대구, 이름)」
_P_REGION = re.compile(rf"(\(\s*{_REGION}\s*,\s*)({_NAME})(\s*\))")
#: 체험자 「(이름, 39세, 사는 곳)」 — 🚨 PDF 가 이름 한가운데서 띄기도 한다(「장 ○○」) · 사는 곳은 시 · 동네 단위라 통째로 가린다
_P_TRIPLE = re.compile(
    r"(\(\s*)([가-힣]{1,2}\s?[가-힣]{1,3})(\s*,\s*)(\d{2})세(\s*,\s*)([^(),]{2,12}?)(\s*\))"
)
#: 체험자 「이름(34세 가명/서울)」 · 「이름,(48세 …」
_P_NAME_AGE = re.compile(rf"(?<![가-힣])({_NAME3})(,?\s*\(\s*)(\d{{2}})세")
#: 「이름씨」 — 세 글자 · 성씨로 시작할 때만(「홍화씨」 · 「포도씨」는 두 글자 + 씨라 걸리지 않는다)
_P_NAME_SSI = re.compile(rf"(?<![가-힣])({_NAME3})(씨)(?![가-힣])")
#: 「전문의 이름(」 — 직함이 앞에 온다
_P_TITLE_NAME = re.compile(rf"((?:전문의|한의사|약사)\s+)({_NAME})(?=\s*\()")
#: 「이름 박사는」 — 🚨 이름은 세 글자로 좁힌다(「대학교수」 · 「의대교수」의 앞 두 글자를 이름으로 읽지 않게)
_P_NAME_TITLE = re.compile(r"(?<![가-힣])([가-힣]{3})(\s*(?:박사|교수|원장)(?=[는은이가의,\s]))")
#: 「[N.W 워커박사]」 — 대괄호 안 외국인 이름
_P_FOREIGN = re.compile(r"(\[\s*)([A-Z]\.(?:[A-Z]\.?)?\s*[가-힣]{2,8})(\s*박사\s*\])")
#: 이름 자리에 오지만 이름이 아닌 말 `[임의]` — 성씨 글자로 시작하는 보통명사 · 직함 앞의 기관 낱말
_NOT_NAME = frozenset(
    {
        "대학교",
        "연구소",
        "한의대",
        "의과대",
        "노인들",
        "여성들",
        "남성들",
        "주부들",
        "고객님",
        "임산부",
        "어린이",
        "청소년",
    }
)
#: 사람이 확인할 **남은 후보** — 나이 표기 · 직함이나 호칭 곁의 한글. 🚨 판정이 아니다 — 눈으로 볼 목록이다
#:    🔄 2026-10-03 (기기 실행 · 팀장 지적) — 「볶은 홍화씨 500g」이 후보로 떴다. 씨앗 이름이다.
#:       「씨」 · 「님」 은 **성씨로 시작하고 뒤에 조사나 문장 부호가 올 때만** 후보다(「김씨는」 · 「박씨.」) —
#:       씨앗 이름 뒤에는 무게 · 수량이 온다
_CANDIDATE = re.compile(
    rf".{{0,8}}(?:\d{{2}}세|{_NAME}\s*(?:박사|교수|원장)(?![가-힣])"
    rf"|(?<![가-힣])[{_SURNAMES}][가-힣]{{0,3}}(?:씨|님)(?=[는은이가의도와과,.(]|$)"
    rf"|(?:전문의|한의사|약사)\s+{_NAME}).{{0,6}}"
)


def _n(s: str) -> str:
    return " ".join(s.split())


def pages() -> list[tuple[int, str, str]]:
    """반쪽별 텍스트 `[(PDF 쪽, 면 L/R, 글), …]`. 🚨 pdfplumber — 반으로 자르지 않으면 좌우 사례의 줄이 섞인다."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("pdfplumber 가 없다 — 고치는 법:  uv sync") from e

    got = store.current_files(RAW_DIR, "*.pdf")
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 pdf 가 없다 —\n  먼저: uv run python launcher.py collect {SOURCE_ID}"
        )
    out: list[tuple[int, str, str]] = []
    with pdfplumber.open(got[0]) as d:
        for i, pg in enumerate(d.pages, 1):
            w, h = pg.width, pg.height
            for side, box in (("L", (0, 0, w / 2, h)), ("R", (w / 2, 0, w, h))):
                out.append((i, side, pg.crop(box).extract_text(x_tolerance=X_TOLERANCE) or ""))
    return out


def _lines(text: str) -> list[str]:
    return [s for s in (_n(x) for x in text.split("\n")) if s]


def _undouble(line: str) -> str:
    """글자가 **겹쳐 찍힌** 바닥글을 편다 — 「2222 MMIINNIISSTTRRYY …」 → 「22 MINISTRY …」.

    🚨 실측(PDF 12쪽 · 인쇄 22 · 23쪽) — 바닥글 글자가 두 번씩 나온다. 숫자 토막은 **네 자리일 때만** 편다 —
       인쇄 쪽은 세 자리를 넘지 않으므로 「2233」은 겹친 23 이고, 「22」는 그대로 22 다.
    """
    out = []
    for tok in line.split():
        doubled = len(tok) % 2 == 0 and tok[0::2] == tok[1::2]
        if doubled and (not tok.isdigit() or len(tok) == 4):
            out.append(tok[0::2])
        else:
            out.append(tok)
    return " ".join(out)


def _foot(line: str) -> int | None:
    """바닥글이면 인쇄 쪽 번호, 아니면 None."""
    m = _FOOT.match(line) or _FOOT.match(_undouble(line))
    return int(m.group(1) or m.group(2)) if m else None


def printed(text: str) -> int | None:
    """인쇄 쪽 번호 — 바닥글에서 읽는다. 없으면 None(표지 · 간지)."""
    for s in reversed(_lines(text)):
        n = _foot(s)
        if n is not None:
            return n
    return None


def toc(halves: list[tuple[int, str, str]]) -> dict[str, tuple[int, int]]:
    """목차 → `{구역: (첫 쪽, 끝 쪽)}` — 사례 절의 세 구역. 못 찾으면 멈춘다 (D-220).

    끝 쪽은 다음 구역의 첫 쪽 − 1 이고, 마지막 구역(축산물)은 「노인 대상 …」 절의 첫 쪽 − 1 이다.
    """
    for _, _, text in halves:
        ls = _lines(text)
        for k, s in enumerate(ls):
            if not _TOC_HEAD.match(s):
                continue
            starts: list[tuple[str, int]] = []
            end: int | None = None
            for t in ls[k + 1 :]:
                m = _TOC_ROW.match(t)
                if m and len(starts) < len(SECTIONS):
                    starts.append((m.group(2), int(m.group(3))))
                    continue
                e = _TOC_END.match(t)
                if e:
                    end = int(e.group(1))
                break
            names = tuple(n for n, _ in starts)
            if names != SECTIONS or end is None:
                raise ValueError(
                    f"목차의 사례 구역을 못 읽었다 — 구역 {names} · 다음 절 {end} (기대 {SECTIONS})"
                )
            bounds = [p for _, p in starts] + [end]
            return {n: (bounds[i], bounds[i + 1] - 1) for i, n in enumerate(SECTIONS)}
    raise ValueError("목차에서 「위반 사례 및 적발 사례」 줄을 못 찾았다")


def _section(page: int, ranges: dict[str, tuple[int, int]]) -> str | None:
    for name, (a, b) in ranges.items():
        if a <= page <= b:
            return name
    return None


def parse(halves: list[tuple[int, str, str]]) -> tuple[list[dict], dict]:
    """사례 레코드와 계측. 🚨 라벨을 만들지 않는다(머리말).

    반쪽 하나에서 표지(▶ …)로 글을 가른다 — 표지 뒤부터 다음 표지 앞까지가 그 칸이다.
    바닥글 · 머리글은 칸에 넣지 않는다.
    """
    ranges = toc(halves)
    rows: list[dict] = []
    stat: dict = {
        "쪽번호_없음": [],
        "구역_밖": [],
        "칸_빠짐": [],
        "한_면에_여럿": [],
        "처분_꼴_다름": [],
    }
    for pdf_page, side, text in halves:
        body = "\n".join(s for s in _lines(text) if _foot(s) is None and not _RUNNING.match(s))
        marks = list(_LABEL.finditer(body))
        if not marks:
            continue
        where = f"{pdf_page}{side}"
        rec: dict = {}
        dup = False
        for k, m in enumerate(marks):
            name = m.lastgroup or ""
            end = marks[k + 1].start() if k + 1 < len(marks) else len(body)
            val = _n(body[m.end() : end])
            if name in rec:
                dup = True
                continue
            rec[name] = val
        if dup:
            stat["한_면에_여럿"].append(where)
        missing = [f for f in REQUIRED if not rec.get(f)]
        if missing:
            stat["칸_빠짐"].append(f"{where}: {missing}")
            continue  # 🔴 칸이 빠진 사례는 레코드로 내지 않는다 — `verify` 가 멈춘다
        page = printed(text)
        if page is None:
            stat["쪽번호_없음"].append(where)
        section = _section(page, ranges) if page is not None else None
        if section is None:
            stat["구역_밖"].append(f"{where}: 인쇄 {page}쪽")
        sanction = basis = None
        if rec.get("처분"):
            m2 = _SANCTION.match(rec["처분"])
            if m2:
                sanction, basis = _n(m2.group("처분")), _n(m2.group("근거"))
            else:
                sanction = rec["처분"]
                stat["처분_꼴_다름"].append(where)
        rows.append(
            {
                "구역": section,
                "쪽": page,
                "면": side,
                "위반구분": rec["위반구분"],
                "위반내용": rec["위반내용"],
                "광고매체": rec["광고매체"],
                "문구": rec["문구"],
                "처분": sanction,
                "처분근거": basis,
                "원천": SOURCE_ID,
                "층": "1층 판정라벨",
                **REGIME,
                # 🚨 처분 칸이 없으면 지위를 지어내지 않는다 (D-220) — 축산물 사례가 그렇다
                "판정지위": STATUS_SANCTION if sanction else None,
            }
        )
    return rows, stat


def verify(halves: list[tuple[int, str, str]]) -> list[str]:
    """🔴 목차와 대조한다 — 사례가 목차의 구역 안에 있는가 · 칸이 다 있는가 · 한 면에 하나인가."""
    rows, stat = parse(halves)
    bad: list[str] = []
    for k in ("쪽번호_없음", "구역_밖", "칸_빠짐", "한_면에_여럿"):
        if stat[k]:
            bad.append(f"{k} — {stat[k]}")
    marks = sum(len(re.findall(r"▶\s*" + FIELDS["위반구분"], t)) for _, _, t in halves)
    if marks != len(rows):
        bad.append(f"「위반 구분」 표지 {marks} · 레코드 {len(rows)}")
    seen = collections.Counter((r["쪽"], r["면"]) for r in rows)
    twice = [k for k, v in seen.items() if v > 1]
    if twice:
        bad.append(f"같은 쪽 · 면의 레코드가 둘 이상 — {twice}")
    if not rows:
        bad.append("사례가 하나도 없다")
    return bad


def redact_people(text: str, log: list[dict] | None = None) -> str:
    """사람이 특정될 수 있는 자리를 가린다 — 이름은 자국으로 · 나이는 10 년 단위로 (머리말 · D-133 ④).

    🚨 본 꼴만 잡는다. 못 잡은 자리는 `candidates` 가 사람에게 보인다.
    """

    def note(rule: str) -> None:
        if log is not None:
            log.append({"규칙": rule, "자리": MASK_CEO})

    def decade(age: str) -> str:
        return f"{int(age) // 10 * 10}대"

    def sex_age(m: re.Match[str]) -> str:
        note("체험자_성별나이")
        return f"{MASK_CEO}{m.group(2)}{decade(m.group(3))}{m.group(4)}"

    def region(m: re.Match[str]) -> str:
        note("체험자_지역")
        return f"{m.group(1)}{MASK_CEO}{m.group(3)}"

    def triple(m: re.Match[str]) -> str:
        note("체험자_이름나이사는곳")
        return f"{m.group(1)}{MASK_CEO}{m.group(3)}{decade(m.group(4))}{m.group(5)}{MASK_ADDR}{m.group(7)}"

    def name_age(m: re.Match[str]) -> str:
        if m.group(1) in _NOT_NAME:
            return m.group(0)
        note("체험자_이름나이")
        return f"{MASK_CEO}{m.group(2)}{decade(m.group(3))}"

    def name_ssi(m: re.Match[str]) -> str:
        if m.group(1) in _NOT_NAME:
            return m.group(0)
        note("이름+씨")
        return f"{MASK_CEO}{m.group(2)}"

    def title_name(m: re.Match[str]) -> str:
        note("직함+이름")
        return f"{m.group(1)}{MASK_CEO}"

    def name_title(m: re.Match[str]) -> str:
        if m.group(1) in _NOT_NAME:
            return m.group(0)
        note("이름+직함")
        return f"{MASK_CEO}{m.group(2)}"

    def foreign(m: re.Match[str]) -> str:
        note("외국인_이름")
        return f"{m.group(1)}{MASK_CEO}{m.group(3)}"

    # 🚨 순서 — 꼴이 **좁은 것부터**. 「(이름, 나이, 사는 곳)」을 먼저 먹어야 뒤 규칙이 그 안을 다시 훑지 않는다
    text = _P_TRIPLE.sub(triple, text)
    text = _P_SEX_AGE.sub(sex_age, text)
    text = _P_REGION.sub(region, text)
    text = _P_NAME_AGE.sub(name_age, text)
    text = _P_NAME_SSI.sub(name_ssi, text)
    text = _P_TITLE_NAME.sub(title_name, text)
    text = _P_FOREIGN.sub(foreign, text)
    return _P_NAME_TITLE.sub(name_title, text)


def candidates(text: str) -> list[str]:
    """가린 뒤에도 남은 **이름 후보** — 사람이 볼 목록이다. 🚨 화면에만 낸다(원값이 들어 있다)."""
    return [m.group(0) for m in _CANDIDATE.finditer(text) if MASK_CEO not in m.group(0)]


#: 마스킹을 거는 자리 — 광고 문구와 그 요약. 다른 칸은 원천의 분류어 · 조문이다
MASK_FIELDS = ("위반내용", "문구")


def redacted(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """사람 가림만 건 사본과 기록 — `masked` 와 `--people` 이 같은 길을 쓴다 (D-99)."""
    log: list[dict] = []
    out: list[dict] = []
    for r in rows:
        rec = dict(r)
        for f in MASK_FIELDS:
            if rec.get(f):
                rec[f] = redact_people(rec[f], log)
        out.append(rec)
    return out, log


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter, list[dict]]:
    """사람 가림 → 원천 정책 마스킹. **산출물로 나가는 모든 길이 여기를 지난다.**"""
    from preprocess.mask import apply_policy  # noqa: PLC0415

    red, log = redacted(rows)
    changed: collections.Counter = collections.Counter()
    out: list[dict] = []
    for before, r in zip(rows, red, strict=True):
        rec = dict(r)
        for f in MASK_FIELDS:
            if rec.get(f):
                rec[f] = apply_policy(rec[f], "", SOURCE_ID, log)
                if rec[f] != before[f]:
                    changed[f] += 1
        out.append(rec)
    return out, changed, log


def _report(rows: list[dict], stat: dict) -> None:
    print(f"사례 {len(rows):,}")
    for name, v in collections.Counter(str(r["구역"]) for r in rows).most_common():
        print(f"    {name:8} {v:>3}")
    print(
        f"\n  처분 칸 있음 {sum(1 for r in rows if r['처분'])} · 없음 {sum(1 for r in rows if not r['처분'])}"
    )
    print("  위반 구분 (원천의 분류어 · 🚨 현행 호가 아니다)")
    for name, v in collections.Counter(r["위반구분"] for r in rows).most_common(8):
        print(f"    · {v:>3}  {name}")
    n = sum(len(r["문구"]) for r in rows)
    print(
        f"\n  문구 글자 {n:,} · 사례당 평균 {n // max(len(rows), 1)} — 문장 분할 · 판독은 라벨 판의 일이다"
    )
    for k, v in stat.items():
        if v:
            print(f"  🚨 {k} {v}")


def _people(rows: list[dict]) -> None:
    red, log = redacted(rows)
    print(f"가린 자리 {len(log)} — {dict(collections.Counter(x['규칙'] for x in log))}")
    left = [(r["쪽"], r["면"], c) for r in red for f in MASK_FIELDS for c in candidates(r[f])]
    print(f"남은 이름 후보 {len(left)} — 🚨 사람이 확인한다(원값 · 이 출력을 문서에 붙이지 않는다)")
    for page, side, c in left:
        print(f"    {page}쪽 {side}  {c}")


def main() -> int:
    ap = argparse.ArgumentParser(description="판별 매뉴얼 PDF → 적발 사례 레코드")
    ap.add_argument("--verify", action="store_true", help="목차와 대조한다")
    ap.add_argument("--people", action="store_true", help="가린 자리 · 남은 이름 후보(화면에만)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    a = ap.parse_args()

    halves = pages()
    bad = verify(halves)
    if a.verify:
        if bad:
            print("🔴 목차와 본문이 어긋난다 — 파싱 결과를 믿지 않는다:", file=sys.stderr)
            for b in bad:
                print(f"  · {b}", file=sys.stderr)
            return 1
        print("★ 목차 대조 통과 — 사례가 모두 목차의 구역 안에 있고 칸이 다 있다")

    rows, stat = parse(halves)
    _report(rows, stat)
    if a.people:
        _people(rows)

    if a.dump:
        if bad:  # 🔴 대조가 깨진 파싱은 파생물로 내보내지 않는다 (D-72)
            print(
                f"\n🔴 목차 대조 실패 {len(bad)}건 — 쓰지 않았다. `--verify` 로 본다",
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
