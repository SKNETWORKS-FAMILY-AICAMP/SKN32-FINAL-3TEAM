"""preprocess/ftc_press_old.py — 공정위 보도자료 1997~2007 → **사건 레코드** (2026-09-30 · 동결 전 판정 ⑤-1·3 (나)).

  uv run python -m preprocess.ftc_press_old            # 센다 (쓰지 않는다)
  uv run python -m preprocess.ftc_press_old --dump     # 🔴 마스킹 정책이 있어야 한다

원천: `ftc_press` (공정거래위원회 보도자료 게시판 · 본문 HTML + 첨부 hwp)

──────────────────────────────────────────────────────────────
★ **레코드 = 보도자료 하나** — 사건 번호(nttSn) · 등록일 · 제목 · 본문(HTML + 첨부 글)

  🚨 **여기서는 라벨도 문구도 만들지 않는다.** 문구 단위(광고에 실린 표현)는 사람 · 판독자가 뽑고
     (`build/labels/ftc_press_old/단위.json`), 조문 · 조건은 판 두 개가 붙인다(`scripts/guide_statute_round.py fp-*`).
     이 파일은 그 문구가 **원천에 그대로 있는지** 대조하는 바닥이다(`fp_units` — D-220).
     ⛔ 보도자료는 따옴표를 거의 안 쓴다(1997~2004 본문 실측) — 인용부호로 문구를 뜨면 거의 안 나온다.

★ **범위 — 등록 2007-12-31 까지.** 비교 · 비방 결정문(`ftc_decisions_body`)은 2008 년 이후만 있어(원장 09-30 ④)
  그 뒤 보도자료는 결정문과 같은 사건이다 → 평가에 쓰면 학습 누수다(레지스트리 caution).

★ **첨부**
  · 한글 5.x — `preprocess.hwp` 로 문단 글자를 읽는다
  · 🔴 한글 3.0(`HWP Document File` 머리 · 2001~2004 12 개) — `preprocess.hwp3` 가 조합형 글자를 훑는다.
    ⛔ 처음에는 LibreOffice 로 바꿨다 — 본문을 거의 다 잃었다(34743 · 34745 의 광고 문구 0 · 2026-09-30 실측).
    🚨 훑기라 못 읽는 자리가 남는다(34811 · 35185 법 위반 내용) — 글이 안 나온 첨부는 **읽지 못한 첨부로 적는다**
  · 🆕 괘선 표(1997~2000 본문) — 칸 글을 이어 붙여 본문 끝에 싣는다(`box_cells`)
  · PDF 첨부는 이 범위에 없다(2008 년부터)

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed · `preprocess.mask.apply_policy`).
   🚨 2026-09-30 현재 `ftc_press` 의 마스킹 정책이 **없다** — 레지스트리 caution 은 「대표이사 성명 … 전처리 마스킹(D-17)」
      만 적었고 `masking:` 칸이 없다. `--dump` 는 정책이 등재될 때까지 멈춘다(판정 대기).
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import html
import json
import pathlib
import re
import sys

from collect import registry

SOURCE_ID = "ftc_press"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/ftc_press_old.jsonl")
#: 범위 끝 — 이 날짜까지 등록된 보도자료만 (머리말 「범위」 · 원장 09-30 ④)
UNTIL = "2007-12-31"
_DATE = re.compile(r"<em>등록</em>\s*:\s*(\d{4}-\d{2}-\d{2})")
_TITLE = re.compile(r'class="p-table__subject_text">\s*(.*?)\s*(?:<!--|</div>)', re.S)


def html_text(raw: bytes) -> str:
    """게시물 HTML → 글. 🚨 인코딩은 utf-8 을 먼저 · 안 되면 cp949(옛 게시물)."""
    for enc in ("utf-8", "cp949"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("인코딩을 모른다")
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?is)<!--.*?-->", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def _hwp5(path: pathlib.Path) -> str:
    from preprocess import hwp  # noqa: PLC0415

    out = []
    for sec in hwp.sections(path):
        for tag, _lvl, data in hwp.records(sec):
            if tag == 67:  # HWPTAG_PARA_TEXT
                out.append(hwp.para_text(data))
    return "\n".join(out)


#: 표 괘선 — 세로선과 가로 구분선. 🚨 옛 보도자료(1997~2000)는 표를 괘선 글자로 그렸다 — 칸 글이 줄마다 다른 칸과 섞인다
_VBAR = re.compile(r"[│┃]")
_RULE = re.compile(r"[─━]{3,}")


def box_cells(text: str) -> list[str]:
    """괘선 표 → **칸마다 이어 붙인 글**. 줄마다 세로선으로 칸을 나누고, 같은 열의 조각을 가로 구분선까지 잇는다.

    ★ 칸 안의 글이 여러 줄에 걸치면 원문에서는 다른 칸과 번갈아 나온다(34128 「어떠한 조건에서도 │ … 환경 │ … 호르몬이」) —
       이것이 없으면 그 문구가 원천에 「없는」 것으로 보인다. 🚨 줄바꿈 자리에 공백이 하나 들어간다(대조는 공백을 보지 않는다).
    """
    out: list[str] = []
    cols: dict[int, list[str]] = {}

    def flush() -> None:
        for k in sorted(cols):
            cell = re.sub(r"\s+", " ", " ".join(cols[k])).strip()
            if cell:
                out.append(cell)
        cols.clear()

    for line in text.splitlines():
        if _RULE.search(line) or not _VBAR.search(line):
            flush()
            continue
        for i, part in enumerate(_VBAR.split(line)):
            if part.strip():
                cols.setdefault(i, []).append(part.strip())
    flush()
    return out


def attachments(nid: str) -> tuple[list[str], list[str]]:
    """사건의 첨부 글 · 읽지 못한 첨부 이름."""
    texts, unread = [], []
    for p in sorted(RAW_DIR.glob(f"ftc_press_{nid}_*")):
        if p.suffix.lower() != ".hwp":
            unread.append(p.name)
            continue
        from preprocess import hwp3  # noqa: PLC0415

        t = hwp3.text(p) if hwp3.is_hwp3(p) else _hwp5(p)
        if t.strip():
            texts.append(t)
        else:
            unread.append(p.name)
    return texts, unread


def extract() -> list[dict]:
    if not RAW_DIR.exists():
        raise SystemExit(f"🔴 {RAW_DIR} 가 없다 — 먼저: uv run python launcher.py raw-import")
    rows = []
    for p in sorted(RAW_DIR.glob("ftc_press_*.html")):
        raw = p.read_bytes()
        s = raw.decode("utf-8", errors="ignore")
        m = _DATE.search(s)
        if not m:
            raise ValueError(f"{p.name}: 등록일을 못 읽는다 — 게시물 꼴이 바뀌었나")
        if m.group(1) > UNTIL:
            continue
        nid = p.stem.split("_")[2]
        t = _TITLE.search(s)
        att, unread = attachments(nid)
        body = html_text(raw)
        # 🆕 괘선 표의 칸 글 — 본문 뒤에 붙인다(원문 줄은 그대로 두고 · 대조가 둘 다 본다)
        cells = box_cells(body)
        rows.append(
            {
                "사건": nid,
                "등록": m.group(1),
                "제목": re.sub(r"\s+", " ", t.group(1)).strip() if t else "",
                "본문": "\n\n".join(
                    [body, *att, *(["[괘선 표 칸]\n" + "\n".join(cells)] if cells else [])]
                ),
                "첨부_못읽음": unread,
                "원천": SOURCE_ID,
            }
        )
    return rows


#: 마스킹을 거는 자리 — 🚨 문구 대조(`fp_units`)는 **마스킹된 본문**에서 한다
MASK_FIELDS = ("제목", "본문")


#: 🆕 2026-10-04 — **법인격 약칭이 뒤에 붙은 상호**(「○○맥주(주)의 부당한 광고행위」). 보도자료는 이 꼴로 피심인을 적는다.
#:    `mask.doc_org_names` 는 앞붙이(「(주)○○」)와 풀어 쓴 뒷붙이(「○○ 주식회사」)만 캔다 — 「A는 (주)B」에서 A 를
#:    상호로 잡지 않으려는 것이다. 그래서 여기서는 **붙여 쓴 약칭 뒤에 조사·구두점이 오는 자리만** 받는다.
#:    ⛔ 이것이 없으면 「○○(주)」는 자리 치환으로 지워지는데 같은 문서의 맨몸 「○○는 …」은 남는다
#:       (실측 2026-10-04 · 원장 10-03 ㊸ — 정책 초안을 걸었을 때 문구 119 중 19 에 상호가 남았다).
#:    🔗 공통화하지 못한 까닭 — `mask.py` 를 넓히면 결정문(`ftc`) 파생물이 바뀐다(재측정 전). 넓힐 때는 그쪽으로 옮긴다 (D-99).
_ABBR_AFTER = re.compile(
    r"([가-힣A-Za-z0-9]{3,12})(?:㈜|\(주\)|（주）)"
    r"(?=(?:에게|에서|[의은는이가을를에와과도])?(?:[\s,.·)」』]|$))"
)


_LEGAL_MARK = r"(?:㈜|\(주\)|（주）)"


def _suffix_artifact(body: str, name: str) -> bool:
    """「○○(주)의 부당한 …」의 뒷말을 앞붙이 상호로 잘못 든 것인가.

    🔴 `mask.doc_org_names` 는 「(주)X」를 앞붙이로 읽는다 — 보도자료는 「X(주)의 부당한 광고행위」로 적으므로
       「(주)」 **앞에 글자가 붙어 있으면** 그 「(주)」는 앞 낱말의 뒷붙이이고 뒤에 온 말은 상호가 아니다.
       ⛔ 종전에는 「부당한」 · 「의부당한」이 상호로 들어 그 낱말이 `[업체]` 가 됐다(원장 10-03 ㊽ · 2 사건).
    ★ 같은 말이 풀어 쓴 법인격(「X 주식회사」)이나 띄어 쓴 앞붙이로도 나오면 상호로 둔다.
    """
    pat = _spaced(name).pattern
    hits = list(re.finditer(_LEGAL_MARK + r"\s*" + pat, body))
    if not hits:
        return False
    if re.search(pat + r"\s*(?:주식회사|유한회사|" + _LEGAL_MARK + ")", body):
        return False
    return all(m.start() > 0 and re.match(r"[가-힣A-Za-z0-9]", body[m.start() - 1]) for m in hits)


def doc_names(body: str) -> list[str]:
    """이 보도자료가 법인격 표기와 함께 적은 상호들 — 긴 것부터(같은 길이는 글자 순 · D-176)."""
    from preprocess.mask import doc_org_names  # noqa: PLC0415

    names = set(doc_org_names(body)) | set(_ABBR_AFTER.findall(body))
    return sorted((n for n in names if not _suffix_artifact(body, n)), key=lambda n: (-len(n), n))


# ──────────────────────────────────────────────────────────────
# 🆕 2026-10-04 — **사건별 이름 목록** (원장 10-03 ㊺~㊾ · 검토요청 §3-6 (ㅁ′))
#
#   규칙만으로는 약칭 · 한자 표기 · 「상호와 같은 글자의 상표」 · 괄호 속 대표자 이름이 남는다
#   (정책 초안을 건 뒤에도 문구 33 / 119 · 본문 28 / 33 건). 이 원천은 33 건이라 **사람이 확인한 목록**으로 닫는다.
#   · 싣는 것 — **회사 · 사람 이름과 연락처만**. 피심인 · 상대 · 제3자를 가르지 않는다(역할 분류는 무르다 · ㊽).
#     상표는 싣지 않는다 — 다만 회사 이름과 글자가 같은 상표는 회사 이름이다.
#   · 🔴 목록은 **저장소 밖**(`build/` · 실명)이고 저장소에는 사건마다 **수와 지문**만 둔다(`NAMES_LOCK`).
#     목록이 없거나 지문이 다르면 `--dump` 는 멈춘다 (D-220).
#   · ⛔ 이 마스킹은 이름 글자를 싣지 않는 데까지다 — **광고주를 숨기지 않는다**(문구만으로 광고주가 맞혀지는 것이
#     어느 수준으로 지워도 약 80 / 119 · ㊾).
#   · D-233 과의 관계 — 「법인격 표기 없이 쓰인 이름을 **추측으로** 지우는 치환」은 여전히 두지 않는다.
#     이것은 추측이 아니라 사건마다 사람이 확인한 표기다.
# ──────────────────────────────────────────────────────────────
NAMES = pathlib.Path("build/labels/ftc_press_old/이름목록.csv")
NAMES_LOCK = pathlib.Path(__file__).with_name("ftc_press_names.lock.json")
#: 목록의 `갈래` → 자국. 🚨 연락처는 따로 자국이 없어 주소 자국을 쓴다
_KIND_MARK = {"회사": "[업체]", "사람": "[대표]", "연락처": "[주소]"}
#: 목록 표기의 최소 글자 수(공백 뺀) `[임의]` — 한 글자는 다른 낱말을 깬다. 두 글자는 실측 17 자리에서 낱말 속 0(㊾)
MIN_LISTED = 2


def read_names(path: pathlib.Path | None = None) -> dict[str, list[tuple[str, str]]]:
    """이름 목록 CSV → `{사건: [(표기, 갈래), …]}` — `처리` 가 「뺌」인 줄은 싣지 않는다. 긴 표기부터."""
    path = path or NAMES
    out: dict[str, list[tuple[str, str]]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh), 2):
            if (row.get("처리") or "").strip() == "뺌":
                continue
            case, name, kind = (row.get(k, "").strip() for k in ("사건", "표기", "갈래"))
            if kind not in _KIND_MARK:
                raise ValueError(
                    f"{path.name} {i}행: 갈래 {kind!r} — {sorted(_KIND_MARK)} 중 하나여야 한다"
                )
            if len(_WS.sub("", name)) < MIN_LISTED or not case:
                raise ValueError(f"{path.name} {i}행: 표기가 너무 짧거나 사건이 비었다")
            out.setdefault(case, []).append((name, kind))
    return {c: sorted(set(v), key=lambda x: (-len(x[0]), x[0])) for c, v in out.items()}


def names_lock(listed: dict[str, list[tuple[str, str]]]) -> dict[str, dict]:
    """사건마다 표기 수와 지문 — 표기 자체는 싣지 않는다."""
    return {
        c: {
            "수": len(v),
            "지문": hashlib.sha256(
                "\n".join(f"{k}\t{_WS.sub('', n)}" for n, k in sorted(v)).encode()
            ).hexdigest()[:12],
        }
        for c, v in sorted(listed.items())
    }


def load_names() -> dict[str, list[tuple[str, str]]]:
    """목록을 읽고 저장소의 지문과 맞춘다 — 없거나 다르면 멈춘다 (D-220)."""
    if not NAMES_LOCK.exists():
        raise SystemExit(f"🔴 {NAMES_LOCK} 가 없다 — 이름 목록의 지문이 저장소에 있어야 한다")
    if not NAMES.exists():
        raise SystemExit(
            f"🔴 {NAMES} 가 없다 — 사건별 이름 목록 없이는 약칭 · 대표자 이름이 파생물에 남는다. "
            "목록은 저장소 밖에 있다(실명) — 다른 기기에서 옮겨 온다"
        )
    listed = read_names()
    want = json.loads(NAMES_LOCK.read_text(encoding="utf-8"))["사건"]
    got = names_lock(listed)
    if got != want:
        diff = sorted(c for c in set(got) | set(want) if got.get(c) != want.get(c))
        raise SystemExit(
            f"🔴 이름 목록이 저장소의 지문과 다르다 — 사건 {diff[:8]} · "
            "목록을 고쳤으면 `--lock` 으로 지문을 다시 쓰고 2인 확인을 거친다"
        )
    return listed


def _listed_pat(name: str) -> re.Pattern:
    """목록 표기 꼴 — 글자 사이 공백 · 괘선을 허용한다(`_spaced` 와 같은 꼴 · 공백은 표기에서 뺀다)."""
    return _spaced(_WS.sub("", name))


def mask_listed(text: str, listed: list[tuple[str, str]], log: list[dict] | None = None) -> str:
    """사건의 목록 표기를 지운다 — 🚨 정책 마스킹 **뒤에** 건다.

    ⛔ 앞에 걸어 봤다 — 목록의 짧은 표기가 긴 상호의 앞머리를 먼저 먹어 「[업체]건설(주)」 꼴이 되고
       자리 치환이 깨졌다(2026-10-04 작업공간). 목록은 **정책을 건 뒤에 남은 표기**를 사람이 확인한 것이다.
    """
    for name, kind in listed:
        mark = _KIND_MARK[kind]
        pat = _listed_pat(name)
        if log is not None:
            log.extend({"규칙": "이름목록", "갈래": kind} for _ in pat.finditer(text))
        text = pat.sub(mark, text)
    return text


def listed_left(text: str, listed: list[tuple[str, str]]) -> int:
    """지운 뒤에도 남은 목록 표기 수 — 이름은 내지 않는다."""
    return sum(1 for name, _ in listed if _listed_pat(name).search(text))


#: 🆕 괄호 · 대괄호 속 「대표 ○○○」 — 보도자료가 피심인을 「○○(주)(대표 ○○○)」 · 「[代表理事 ○○○]」로 적는다.
#:    `mask._TITLES` 에는 「대표」 단독과 한자 직함이 없고 성씨 목록 밖 이름이 있다(실측 4 사건 · ㊾).
#:    ⛔ 괄호가 열린 자리에서 닫히거나 줄이 끝나는 데까지만 본다 — 「대표 상품」 같은 보통 말을 건드리지 않으려는 것이다.
#:    🚨 한글(hwp) 글의 한자는 호환 한자(U+F900~)로 올 때가 있다(「理」 U+F9E4) — 직함과 이름 양쪽에 넣었다.
#:    🔗 `mask.py` 로 못 옮긴 까닭은 `_ABBR_AFTER` 와 같다(결정문 파생물 재측정 전 · D-99).
_PAREN_CEO = re.compile(
    r"([(（\[]\s*(?:대표이사|대표자|대표|代表[理\uf9e4]\s*事|代表)\s*[:：]?\s*)"
    r"([가-힣一-龥\uf900-\ufaff]{2,4})(?=[ \t]*(?:[)）\]]|\r?$))",
    re.M,
)


def mask_paren_ceo(text: str, log: list[dict] | None = None) -> str:
    def sub(m: re.Match[str]) -> str:
        if log is not None:
            log.append({"규칙": "괄호대표"})
        return m.group(1) + "[대표]"

    return _PAREN_CEO.sub(sub, text)


def _mask_split(text: str, names: list[str], log: list[dict] | None = None) -> str:
    """줄넘김 · 괘선으로 **갈린** 상호를 정책보다 먼저 지운다 — 붙은 법인격 약칭까지.

    ⛔ 뒤에 걸면 늦다 — 「○○ │⏎│ ○○개발(주)」에서 자리 치환이 뒷조각만 `[업체]` 로 바꿔 앞조각 「○○」가 남았다(실측 · ㊾).
    🚨 갈리지 않은 자리는 건드리지 않는다 — 그 자리는 정책(자리 치환)이 법인격 표기와 함께 지운다.
    """
    from preprocess.mask import MASK_ORG  # noqa: PLC0415

    for n in names:
        pat = re.compile(rf"({_spaced(n).pattern})(\s*{_LEGAL_MARK})?")

        def sub(m: re.Match[str], n: str = n) -> str:
            if m.group(1) == n:
                return m.group(0)
            if log is not None:
                log.append({"규칙": "갈린상호"})
            return MASK_ORG

        text = pat.sub(sub, text)
    return text


def _mask_text(
    text: str,
    names: list[str],
    log: list[dict] | None = None,
    listed: list[tuple[str, str]] | None = None,
) -> str:
    """갈린 상호 → 괄호 속 대표 → 정책 → 이 문서가 밝힌 상호의 **맨몸 언급** → 사건의 목록 표기 순으로 지운다."""
    from preprocess.mask import MASK_ORG, apply_policy, mask_org_bare  # noqa: PLC0415

    text = mask_paren_ceo(_mask_split(text, names, log), log)
    text = mask_org_bare(apply_policy(text, "", SOURCE_ID, log), names, log)[0]
    for n in (
        names
    ):  # 줄넘김으로 갈린 이름(「○○ ○사는」) — 옛 보도자료의 괘선 칸은 낱말 안에서 줄이 바뀐다
        text = _spaced(n).sub(MASK_ORG, text)
    return mask_listed(text, listed or [], log)


def _spaced(name: str) -> re.Pattern:
    """글자 사이의 공백 · 괘선을 허용한 이름 꼴 — 지울 때와 남았는지 볼 때 같은 꼴을 쓴다.

    🔄 2026-10-04 — 괘선(│)을 더했다. 괘선 표 안에서 줄이 바뀐 상호는 「○○○ │⏎│ ○(주)」로 갈려 남았다(실측 3 · ㊾).
    """
    return re.compile(r"[\s│┃]*".join(re.escape(c) for c in name))


def masked(
    rows: list[dict], listed: dict[str, list[tuple[str, str]]] | None = None
) -> tuple[list[dict], collections.Counter, list[dict]]:
    """사건 레코드 마스킹. 🚨 `listed`(사건별 이름 목록)를 안 주면 규칙만 건다 — 파생을 쓰는 `main` 은 반드시 준다."""
    log: list[dict] = []
    changed: collections.Counter = collections.Counter()
    out = []
    for r in rows:
        rec = dict(r)
        names = doc_names(
            rec["본문"]
        )  # 🚨 제목도 본문의 이름으로 지운다 — 제목에만 맨몸으로 나올 수 있다
        mine = (listed or {}).get(str(rec["사건"]), [])
        for f in MASK_FIELDS:
            m = _mask_text(rec[f], names, log, mine)
            changed[f] += m != rec[f]
            rec[f] = m
        out.append(rec)
    return out, changed, log


def records_left(out: list[dict], listed: dict[str, list[tuple[str, str]]]) -> list[str]:
    """마스킹된 레코드에 목록 표기가 남은 사건 — 🔴 남으면 부르는 쪽이 멈춘다 (D-220)."""
    bad = []
    for rec in out:
        n = sum(listed_left(rec[f], listed.get(str(rec["사건"]), [])) for f in MASK_FIELDS)
        if n:
            bad.append(f"사건 {rec['사건']} 목록 표기 {n}개가 남았다")
    return bad


#: 🆕 마스킹된 문구 단위 — `guide_statute_round fp-merge --units` 가 읽는다
OUT_UNITS = pathlib.Path("data/derived/ftc_press_old_units.jsonl")
#: 문구 단위에서 문구 말고 **원문의 글이 든 칸** — 마스킹을 같이 건다(🚨 칸을 더하면 여기에도 더한다)
UNIT_TEXT_FIELDS = ("원천판단",)
#: 문구 자리 표시 — 마스킹을 **본문 안에서** 건 뒤 이 사이를 꺼낸다(사용자 영역 글자 · 원문에 나오지 않는다)
_OPEN, _CLOSE = "\ue000", "\ue001"
_WS = re.compile(r"\s+")


def mask_units(
    rows: list[dict], units: list[dict], listed: dict[str, list[tuple[str, str]]] | None = None
) -> tuple[list[dict], list[str]]:
    """문구 단위(마스킹 전 · 사람 · 판독자가 뽑은 것) → **본문 안에서 마스킹한** 문구.

    🔴 문구만 따로 마스킹하면 안 된다 — 마스킹은 문서가 스스로 밝힌 상호를 문서 전체에서 지운다(`mask.doc_org_names`).
       따로 걸면 본문에서는 `[업체]` 인 이름이 문구에는 그대로 남는다(34657 「… 대한항공이 더욱 편리합니다」 · 2026-09-30 실측).
       ★ 그래서 원문 본문에서 문구 자리를 찾아 표시를 끼우고 **본문 전체를 마스킹한 뒤** 표시 사이를 꺼낸다.
    🔴 원문에서 못 찾은 문구 · 표시가 깨진 문구는 돌려주지 않고 `bad` 로 모은다 — 부르는 쪽이 멈춘다 (D-220).
    """
    by = {r["사건"]: r for r in rows}
    out, bad = [], []
    for u in units:
        r = by.get(str(u["사건"]))
        pat = r"\s*".join(re.escape(c) for c in re.sub(r"\s+", "", u["문구"]))
        m = re.search(pat, r["본문"]) if r else None
        if not m:
            bad.append(f"{u['지문']} 사건 {u['사건']} 원문에 없는 문구 {u['문구'][:30]!r}")
            continue
        body = r["본문"]
        marked = body[: m.start()] + _OPEN + body[m.start() : m.end()] + _CLOSE + body[m.end() :]
        names = doc_names(body)
        mine = (listed or {}).get(str(u["사건"]), [])
        got = _mask_text(marked, names, None, mine)
        seg = re.search(re.escape(_OPEN) + "(.*?)" + re.escape(_CLOSE), got, re.S)
        if not seg:
            bad.append(f"{u['지문']} 마스킹이 문구 경계를 먹었다 {u['문구'][:30]!r}")
            continue
        rec = {**u, "문구": re.sub(r"\s+", " ", seg.group(1)).strip(), "마스킹": True}
        # 🆕 2026-10-04 — **문구 말고 글이 든 칸도 같은 이름으로 지운다**. 종전에는 `{**u}` 로 그대로 실려
        #    `원천판단`(본문에서 옮긴 판단 문장)의 상호가 파생물에 남았다(실측 10 / 119 · 원장 10-03 ㊸).
        for f in UNIT_TEXT_FIELDS:
            if isinstance(rec.get(f), str):
                rec[f] = _mask_text(rec[f], names, None, mine)
        cells = [str(rec.get(f, "")) for f in ("문구", *UNIT_TEXT_FIELDS)]
        left = sum(1 for n in names if any(_spaced(n).search(c) for c in cells))
        left += sum(listed_left(c, mine) for c in cells)
        if left:  # 🔴 지운 뒤에도 남으면 쓰지 않는다 (D-220) — 이름은 내지 않고 수만 낸다
            bad.append(
                f"{u['지문']} 사건 {u['사건']} 마스킹 뒤에도 상호 · 목록 표기가 {left}개 남았다"
            )
            continue
        out.append(rec)
    return out, bad


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 보도자료 1997~2007 → 사건 레코드")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    ap.add_argument(
        "--units",
        type=pathlib.Path,
        help=f"문구 단위 JSON(마스킹 전) — `--dump` 와 함께 주면 본문 안에서 마스킹해 {OUT_UNITS} 로 쓴다",
    )
    ap.add_argument(
        "--lock", action="store_true", help=f"{NAMES} 의 지문을 {NAMES_LOCK.name} 에 다시 쓴다"
    )
    a = ap.parse_args()
    if a.lock:
        listed = read_names()
        lock = {"뜻": "사건별 이름 목록의 수와 지문 — 표기는 저장소 밖", "사건": names_lock(listed)}
        NAMES_LOCK.write_text(
            json.dumps(lock, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            f"  → {NAMES_LOCK}  (사건 {len(listed)} · 표기 {sum(len(v) for v in listed.values())})"
        )
        return 0
    rows = extract()
    unread = [x for r in rows for x in r["첨부_못읽음"]]
    print(f"보도자료 {len(rows)}건 (등록 ~{UNTIL})")
    if unread:
        print(
            f"  🚨 읽지 못한 첨부 {len(unread)} — {unread[:5]} (LibreOffice 가 없으면 한글 3.0 을 못 읽는다)"
        )
    if a.dump:
        registry.assert_derivable(rows, who="preprocess.ftc_press_old")
        listed = load_names()
        out, changed, log = masked(rows, listed)
        left = records_left(out, listed)
        if left:
            print(
                f"🔴 마스킹 뒤에도 목록 표기가 남았다 — 쓰지 않았다 ({len(left)} 사건)",
                file=sys.stderr,
            )
            for b in left[:10]:
                print(f"  · {b}", file=sys.stderr)
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  🔴 마스킹 — 바뀐 필드 {dict(changed)} · 치환 {len(log)}건")
        print(f"  → {OUT}  ({len(out)}줄)")
        if a.units:
            got, bad = mask_units(rows, json.loads(a.units.read_text(encoding="utf-8")), listed)
            if bad:
                print(
                    f"🔴 문구 단위 {len(bad)}개가 걸렸다(원문에 없거나 이름이 남았다) — 쓰지 않았다",
                    file=sys.stderr,
                )
                for b in bad[:10]:
                    print(f"  · {b}", file=sys.stderr)
                return 1
            with OUT_UNITS.open("w", encoding="utf-8", newline="\n") as fh:
                for u in got:
                    fh.write(json.dumps(u, ensure_ascii=False) + "\n")
            before = {
                x["지문"]: _WS.sub("", x["문구"])
                for x in json.loads(a.units.read_text(encoding="utf-8"))
            }
            # 공백은 원문 자리의 것으로 바뀐다 — 마스킹으로 **글자가** 바뀐 것만 센다
            moved = sum(1 for u in got if before[u["지문"]] != _WS.sub("", u["문구"]))
            print(f"  → {OUT_UNITS}  (문구 {len(got)} · 마스킹으로 바뀐 것 {moved})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
