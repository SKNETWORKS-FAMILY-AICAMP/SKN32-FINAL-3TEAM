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


def doc_names(body: str) -> list[str]:
    """이 보도자료가 법인격 표기와 함께 적은 상호들 — 긴 것부터(같은 길이는 글자 순 · D-176)."""
    from preprocess.mask import doc_org_names  # noqa: PLC0415

    names = set(doc_org_names(body)) | set(_ABBR_AFTER.findall(body))
    return sorted(names, key=lambda n: (-len(n), n))


def _mask_text(text: str, names: list[str], log: list[dict] | None = None) -> str:
    """정책대로 지운 뒤, 이 문서가 밝힌 상호의 **맨몸 언급**까지 지운다."""
    from preprocess.mask import MASK_ORG, apply_policy, mask_org_bare  # noqa: PLC0415

    text = mask_org_bare(apply_policy(text, "", SOURCE_ID, log), names, log)[0]
    for n in (
        names
    ):  # 줄넘김으로 갈린 이름(「○○ ○사는」) — 옛 보도자료의 괘선 칸은 낱말 안에서 줄이 바뀐다
        text = _spaced(n).sub(MASK_ORG, text)
    return text


def _spaced(name: str) -> re.Pattern:
    """글자 사이의 공백을 허용한 이름 꼴 — 지울 때와 남았는지 볼 때 같은 꼴을 쓴다."""
    return re.compile(r"\s*".join(re.escape(c) for c in name))


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter, list[dict]]:
    log: list[dict] = []
    changed: collections.Counter = collections.Counter()
    out = []
    for r in rows:
        rec = dict(r)
        names = doc_names(
            rec["본문"]
        )  # 🚨 제목도 본문의 이름으로 지운다 — 제목에만 맨몸으로 나올 수 있다
        for f in MASK_FIELDS:
            m = _mask_text(rec[f], names, log)
            changed[f] += m != rec[f]
            rec[f] = m
        out.append(rec)
    return out, changed, log


#: 🆕 마스킹된 문구 단위 — `guide_statute_round fp-merge --units` 가 읽는다
OUT_UNITS = pathlib.Path("data/derived/ftc_press_old_units.jsonl")
#: 문구 단위에서 문구 말고 **원문의 글이 든 칸** — 마스킹을 같이 건다(🚨 칸을 더하면 여기에도 더한다)
UNIT_TEXT_FIELDS = ("원천판단",)
#: 문구 자리 표시 — 마스킹을 **본문 안에서** 건 뒤 이 사이를 꺼낸다(사용자 영역 글자 · 원문에 나오지 않는다)
_OPEN, _CLOSE = "\ue000", "\ue001"
_WS = re.compile(r"\s+")


def mask_units(rows: list[dict], units: list[dict]) -> tuple[list[dict], list[str]]:
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
        got = _mask_text(marked, names)
        seg = re.search(re.escape(_OPEN) + "(.*?)" + re.escape(_CLOSE), got, re.S)
        if not seg:
            bad.append(f"{u['지문']} 마스킹이 문구 경계를 먹었다 {u['문구'][:30]!r}")
            continue
        rec = {**u, "문구": re.sub(r"\s+", " ", seg.group(1)).strip(), "마스킹": True}
        # 🆕 2026-10-04 — **문구 말고 글이 든 칸도 같은 이름으로 지운다**. 종전에는 `{**u}` 로 그대로 실려
        #    `원천판단`(본문에서 옮긴 판단 문장)의 상호가 파생물에 남았다(실측 10 / 119 · 원장 10-03 ㊸).
        for f in UNIT_TEXT_FIELDS:
            if isinstance(rec.get(f), str):
                rec[f] = _mask_text(rec[f], names)
        left = [
            n
            for n in names
            if any(_spaced(n).search(str(rec.get(f, ""))) for f in ("문구", *UNIT_TEXT_FIELDS))
        ]
        if left:  # 🔴 지운 뒤에도 남으면 쓰지 않는다 (D-220) — 이름은 내지 않고 수만 낸다
            bad.append(
                f"{u['지문']} 사건 {u['사건']} 마스킹 뒤에도 문서가 밝힌 상호가 {len(left)}개 남았다"
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
    a = ap.parse_args()
    rows = extract()
    unread = [x for r in rows for x in r["첨부_못읽음"]]
    print(f"보도자료 {len(rows)}건 (등록 ~{UNTIL})")
    if unread:
        print(
            f"  🚨 읽지 못한 첨부 {len(unread)} — {unread[:5]} (LibreOffice 가 없으면 한글 3.0 을 못 읽는다)"
        )
    if a.dump:
        registry.assert_derivable(rows, who="preprocess.ftc_press_old")
        out, changed, log = masked(rows)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  🔴 마스킹 — 바뀐 필드 {dict(changed)} · 치환 {len(log)}건")
        print(f"  → {OUT}  ({len(out)}줄)")
        if a.units:
            got, bad = mask_units(rows, json.loads(a.units.read_text(encoding="utf-8")))
            if bad:
                print(
                    f"🔴 문구 단위 {len(bad)}개를 원문에서 못 찾았다 — 쓰지 않았다", file=sys.stderr
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
