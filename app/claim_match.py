"""인정 · 고시 기능성 문구 대조 — 이용자가 적은 「인정 · 심사받은 문구」가 공식 문구와 같은가 (🆕 2026-10-14 ksr · D-341 결정 4).

★ 묻는 것은 **글자**다 — 「이 문구가 식약처가 인정 · 고시한 문구 그대로인가」. 「이 제품이 그 인정을 받았는가」는 묻지 않는다
  (인정서 없이는 누구도 확인할 수 없다 · 화면이 그렇게 적는다).
★ 결과 넷 — `same`(목록의 문구와 같음) · `near`(비슷하지만 다름 · 가장 가까운 공식 문구와 다른 점) · `none`(목록에 없음) ·
  `unchecked`(목록이 없어 대조 못 함). 🔴 `unchecked` 를 「문제없음」으로 돌려주지 않는다 (D-220).
★ 목록(정본만) — 고시형 `hf_gosi_claims.jsonl`(「건강기능식품의 기준 및 규격」) · 개별인정형 `hf_api_labels.jsonl`(I-0050) ·
  `mfds_hf_labels.jsonl`(원료별 정보 게시판). ⛔ `hf_display_claims.jsonl`(I-0040)은 **넣지 않는다** — 업체가 신고한
  표시 문구(관측 축)라 정본과 같은 것이 65% 뿐이다(`preprocess/hf_api.py` · D-185). 넣으면 「다른 문구」가 「같음」이 된다.
★ 매칭은 정규화문, 보관은 원문 (D-117) — 화면에는 원문을 보인다.
⬜ 기능성화장품 심사 문구 목록은 없다 — 화장품 분기는 `unchecked`.
"""

from __future__ import annotations

import difflib
import functools
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DERIVED = ROOT / "data" / "derived"
#: (파일, 문구 칸, 출처 이름, 번호 칸) — 문구 칸이 목록이면 그대로, 글이면 나눈다
SOURCES = (
    ("hf_gosi_claims.jsonl", "기능성문구", "고시형", "번호"),
    ("hf_api_labels.jsonl", "PRIMARY_FNCLTY", "개별인정형", "인정번호"),
    ("mfds_hf_labels.jsonl", "기능성문구", "개별인정형", "인정번호"),
)
#: 이만큼 닮으면 「비슷함」 — 핵심부(끝 · 강조어를 뗀 것) 글자 닮음. 10-14 측정 — 무관한 문장 10/10 「없음」 · 변형 대부분 「비슷함」
NEAR = 0.8

_ENG = re.compile(r"\(\s*영문\s*\).*$", re.S)
_KOR = re.compile(r"\(\s*국문\s*\)")
#: 문구 뒤에 붙는 분류 · 등급 · 인정 시기 꼬리표 — 「(기타기능Ⅱ)」 「(생리활성기능 2등급)」 「('20년 2월 인정)」
_TAG = re.compile(r"\(\s*(?:기타|생리활성|질병발생|영양소|'?\d{2}\s*년)[^()]*\)")
_QUOTE = re.compile(r"[\"'“”‘’「」『』]")
#: 문구 끝(「줌」 · 「있음」 · 「필요」) 뒤에 붙은 괄호 — 분류 꼬리표다 「…도움을 줌(치아건강)」 (10-15 · 고친 것)
_TAIL_TAG = re.compile(r"(줌|있음|있습니다|필요)\s*\([^()]*\)\s*$")
_ENDING = (
    ("있습니다", "있음"),
    ("있어요", "있음"),
    ("있다", "있음"),
    ("필요합니다", "필요"),
    ("필요함", "필요"),
)
#: 한 칸에 문구가 여럿일 때 가르는 자리 — 줄 · 번호(①, 1)) · 글머리(-, ·) · 「있음」 뒤
#: 🔄 측정(10-14) — 「· 」 글머리와 「1) 2)」 번호를 안 갈라 원문 7 · 업체 표시 문구 11건이 「같음」을 놓쳤다
_SPLIT = re.compile(
    r"\n|[/;]|[①-⑩]|(?:^|\s)(?:[-◆•·]|\d{1,2}[).])\s*(?=\S)|(?<=있음)[,.·]?\s*|(?<=있습니다)[,.·]?\s*|(?<=필요)[,.]\s*"
)
#: 🚨 NFKC 가 반각 「･」(U+FF65)를 「・」(U+30FB)로 바꾼다 — 둘 다 넣는다
DOT = "･・·‧․ㆍ"
TAIL = "에도움을줄수있음"
#: 공식 문구에는 없는데 붙으면 안 되는 말 — 화면에 「강조하는 말」로 알린다
EMPHASIS = (
    "확실",
    "탁월",
    "획기적",
    "놀라운",
    "강력",
    "완벽",
    "최고",
    "최상",
    "100%",
    "즉시",
    "즉각",
    "빠르게",
    "단숨에",
    "반드시",
    "무조건",
    "특효",
    "만능",
    "기적",
)


def norm(s: str) -> str:
    """매칭용 정규화 — 꼬리표 · 따옴표 · 어미 차이 · 띄어쓰기를 없앤다. 낱말은 바꾸지 않는다."""
    s = unicodedata.normalize("NFKC", s)
    s = _QUOTE.sub("", _TAG.sub("", _KOR.sub("", _ENG.sub("", s))))
    s = _TAIL_TAG.sub(lambda m: m.group(1), s.strip())
    s = re.sub(r"\s+", "", s).rstrip(".,;")
    for a, b in _ENDING:
        if s.endswith(a):
            s = s[: -len(a)] + b
    return s


def _display(seg: str) -> str:
    """화면용 원문 조각 — 꼬리표 · 따옴표만 걷고 띄어쓰기는 남긴다."""
    seg = _TAIL_TAG.sub(
        lambda m: m.group(1), _QUOTE.sub("", _TAG.sub("", _KOR.sub("", seg))).strip(" ,.;-◆•")
    )
    return re.sub(r"\s+", " ", seg).strip(" ,.;-◆•")


def _split_dots(seg: str) -> list[str]:
    """「A･B에 도움을 줄 수 있음」 → [「A에 도움을 줄 수 있음」, 「B에 …」]. 괄호 안 가운뎃점(「기침·가래 등」)은 두고 가른다."""
    m = re.search(r"\s*에\s*도움을\s*줄\s*수\s*있(?:음|습니다|어요)\s*$", seg)
    if not m:
        return [seg]
    head, depth, parts, cur = seg[: m.start()], 0, [], ""
    for ch in head:
        depth += ch in "([" and 1 or 0
        depth -= ch in ")]" and 1 or 0
        if ch in DOT and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    if len(parts) < 2:
        return [seg]
    return [p.strip() + "에 도움을 줄 수 있음" for p in parts if p.strip()]


def split_display(text: str, *, dots: bool = True) -> list[tuple[str, str]]:
    """한 칸의 글 → [(정규화문, 화면용 원문)] — 문구 하나씩. 4글자 미만 조각은 버린다.

    `dots=False` — 가운뎃점으로는 가르지 않는다. 🚨 개별인정형 문구는 가운뎃점이 **낱말 안**에 있기도 하다
    (「기관·기관지 상태(기침·가래 등) 개선에…」를 가르면 「기관에 도움을 줄 수 있음」이라는 없는 문구가 생긴다).
    고시형은 전처리(`preprocess/hf_gosi.py`)가 이미 갈랐다.
    """
    text = _ENG.sub("", unicodedata.normalize("NFKC", text))
    out: list[tuple[str, str]] = []
    for part in _SPLIT.split(text):
        # 「있음.」 뒤에서 가르면 다음 조각이 「2) …」로 시작한다 — 앞의 번호 · 글머리를 뗀다
        part = re.sub(r"^\s*(?:\d{1,2}[).]|[-◆•·])\s*", "", part or "").strip(" ,.;-◆•")
        if not part or not re.search(r"[가-힣]", part):
            continue
        for seg in _split_dots(part) if dots else [part]:
            n = norm(seg)
            if len(n) >= 4:
                out.append((n, _display(seg)))
    return out


def pieces(text: str) -> list[str]:
    """정규화문만."""
    return [n for n, _ in split_display(text)]


@dataclass(frozen=True)
class Official:
    norm: str
    text: str  # 원문 그대로(화면에 보인다)
    source: str  # 고시형 · 개별인정형
    ref: str  # 고시 번호 「2-10」 · 인정번호
    name: str  # 원료명


@functools.cache
def _rows() -> tuple[Official, ...]:
    """목록의 모든 행(같은 문구가 원료마다 한 줄씩) — 「이 문구가 어느 원료의 것인가」를 답한다."""
    out: dict[tuple[str, str, str, str], Official] = {}
    for fname, col, label, ref_col in SOURCES:
        p = DERIVED / fname
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row.get("시행", "현행") != "현행":
                    continue  # 아직 시행 전인 개정 문구 — 시행일에 다시 만든다
                raw = row.get(col) or ""
                texts = raw if isinstance(raw, list) else [raw]
                name = _short_name(row.get("원료명") or row.get("RAWMTRL_NM") or "")
                ref = str(row.get(ref_col) or "")
                for t in texts:
                    for n, shown in split_display(t, dots=False):
                        out.setdefault((n, label, ref, name), Official(n, shown, label, ref, name))
    return tuple(out.values())


def _short_name(name: str) -> str:
    """원료명에서 인정번호 · 괄호 꼬리를 뗀다 — 「두충우슬추출복합물(KGC08EA)(제2023-40호)」 → 「두충우슬추출복합물」."""
    return re.sub(r"\s*\(.*$", "", unicodedata.normalize("NFKC", name)).strip() or name


@functools.cache
def owners() -> dict[str, tuple[Official, ...]]:
    """정규화문 → 그 문구를 가진 원료들(고시형 먼저)."""
    by: dict[str, list[Official]] = {}
    for o in _rows():
        by.setdefault(o.norm, []).append(o)
    return {k: tuple(sorted(v, key=lambda o: o.source != "고시형")) for k, v in by.items()}


@functools.cache
def catalog() -> tuple[Official, ...]:
    """공식 문구 목록(문구마다 한 줄 · 대표 원료). 파일이 하나도 없으면 빈 튜플 — 부르는 쪽이 `unchecked` 로 그린다."""
    return tuple(os_[0] for os_ in owners().values())


#: 원료 이름에 흔한 꼬리 — 이름을 견줄 때 뗀다(「추출물」끼리 같다고 보지 않게)
_GENERIC = re.compile(
    r"(?:열수|주정|효소)?(?:추출물|추출분말|추출오일|분말|복합물|농축액|농축분말|발효물|가수분해물|등)"
)


def _name_key(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", unicodedata.normalize("NFKC", s)).lower()
    return s.replace("펩티드", "펩타이드")


def _common(a: str, b: str) -> int:
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size


def fits_name(name: str, ingredients: list[str]) -> bool:
    """원료 이름 하나가 적힌 원재료 중 하나와 같은가.

    ★ 서로 품거나, 흔한 꼬리(추출물 · 분말 …)를 뗀 뒤 **네 글자 이상** 겹치면 같다고 본다 —
       「리프리놀-초록입홍합추출오일」 ↔ 「초록입홍합추출오일복합물」(10-14 측정 · 같음 232 중 엇갈림 2 → 0).
    """
    n = _name_key(name)
    if len(n) < 2:
        return False
    for g in (_name_key(x) for x in ingredients):
        if len(g) < 2:
            continue
        if g in n or n in g or _common(_GENERIC.sub("", g), _GENERIC.sub("", n)) >= 4:
            return True
    return False


def fits(official_norm: str, ingredients: list[str]) -> bool | None:
    """적힌 원재료 중 하나가 그 문구의 원료인가 — 원재료를 안 적었으면 `None`(모른다)."""
    if not any(len(_name_key(g)) >= 2 for g in ingredients):
        return None
    return any(fits_name(o.name, ingredients) for o in owners().get(official_norm, ()))


@dataclass
class PieceResult:
    text: str
    state: str  # same · near · none
    official: Official | None = None
    score: float = 0.0
    why: list[str] = field(default_factory=list)
    shown: str = ""  # 이용자가 적은 그 조각(띄어쓰기 그대로) — 화면용


@dataclass
class MatchResult:
    state: str  # same · near · none · unchecked
    pieces: list[PieceResult] = field(default_factory=list)
    reason: str = ""  # unchecked 의 까닭


#: 문구 끝 — 「…에 도움을 줄 수 있음」 · 「…에 도움을 줌」 · 「…하는데 도움을 줍니다」 · 「…에 필요」. 핵심부를 견줄 때 뗀다
_END = re.compile(
    r"(?:에|데|에서)?(?:도움(?:을|이)?(?:줄수있음|될수있음|줌|준다|줍니다|줘요|드림|드립니다|됨|된다|됩니다|돼요)?|필요)$"
)
#: 핵심부 포함으로 「비슷함」을 낼 때의 최소 길이 — 「간건강」(3)처럼 짧은 핵심부는 아무 데나 들어 있다
_MIN_CORE = 4


def _plain(n: str) -> str:
    for w in EMPHASIS:
        n = n.replace(w, "")
    return re.sub(r"(?:하게|히|이)(?=도움)", "", n)


def core(n: str) -> str:
    """정규화문의 핵심부 — 강조어와 끝(「도움을 줄 수 있음」 등)을 뗀 것."""
    return _END.sub("", _plain(n))


def _why(given: str, official: str) -> list[str]:
    """가장 가까운 공식 문구와 다른 점(코드) — 화면이 앞의 한두 개만 적는다."""
    out: list[str] = []
    if official.endswith("수있음") and "수있" not in given:
        out.append("assertive")  # 「줄 수 있음」 → 「줌 · 줍니다」
    if any(w in given and w not in official for w in EMPHASIS):
        out.append("emphasis")
    cg, co = core(given), core(official)
    if cg != co:
        if cg in co:
            out.append("narrowed")  # 공식 문구의 대상 · 조건 한정이 빠졌다 → 범위가 넓어진다
        elif co in cg:
            out.append("added")  # 공식 문구에 말이 덧붙었다
        else:
            out.append("changed")
    return out or ["changed"]


@functools.cache
def _cores() -> dict[str, tuple[Official, ...]]:
    by: dict[str, list[Official]] = {}
    for o in catalog():
        by.setdefault(core(o.norm), []).append(o)
    return {k: tuple(v) for k, v in by.items()}


def _nearest(n: str) -> tuple[Official | None, float]:
    """가장 가까운 공식 문구 — ① 핵심부가 같다 ② 핵심부가 서로를 품는다 ③ 핵심부 글자 닮음."""
    c = core(n)
    cores = _cores()
    if c in cores:
        return cores[c][0], 1.0
    inside = [k for k in cores if len(k) >= _MIN_CORE and k in c]  # 공식 문구 + 덧붙임
    if inside:
        return cores[max(inside, key=len)][0], 0.95
    outside = [k for k in cores if len(c) >= _MIN_CORE and c in k]  # 공식 문구에서 한정이 빠짐
    if outside:
        return cores[min(outside, key=len)][0], 0.9
    best, score = None, 0.0
    for k, os_ in cores.items():
        sm = difflib.SequenceMatcher(None, c, k, autojunk=False)
        if sm.real_quick_ratio() <= score or sm.quick_ratio() <= score:
            continue
        r = sm.ratio()
        if r > score:
            best, score = os_[0], r
    return best, score


def clear_cache() -> None:
    """목록 캐시를 비운다 — 파생물을 다시 만든 뒤 · 테스트."""
    for f in (_rows, owners, catalog, _cores):
        f.cache_clear()


def match(text: str, category: str) -> MatchResult:
    """`category` — 분기의 품목(「건기식」 · 「화장품」). 건기식만 목록이 있다."""
    if category != "건기식":
        return MatchResult("unchecked", reason="no_list")
    cat = catalog()
    if not cat:
        return MatchResult("unchecked", reason="no_data")
    index = {o.norm: o for o in cat}
    whole = norm(text)
    if whole in index:
        return MatchResult(
            "same", [PieceResult(whole, "same", index[whole], 1.0, shown=text.strip())]
        )
    results: list[PieceResult] = []
    for n, shown in split_display(text) or [(whole, text.strip())]:
        if n in index:
            results.append(PieceResult(n, "same", index[n], 1.0, shown=shown))
            continue
        o, s = _nearest(n)
        if o is not None and s >= NEAR:
            results.append(PieceResult(n, "near", o, s, _why(n, o.norm), shown))
        else:
            results.append(PieceResult(n, "none", o, s, shown=shown))
    states = {r.state for r in results}
    state = "same" if states == {"same"} else "near" if "near" in states else "none"
    return MatchResult(state, results)
