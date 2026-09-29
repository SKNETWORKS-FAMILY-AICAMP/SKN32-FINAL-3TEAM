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
  · 🔴 한글 3.0(`HWP Document File` 머리 · 2002~2004 12 개) — `soffice`(LibreOffice)가 있으면 텍스트로 바꾼다.
    🚨 글상자 안 글은 빠진다(원장 09-30 ④). LibreOffice 가 없으면 **읽지 못한 첨부로 적고** 본문만 둔다 —
       그 첨부에서 뽑은 문구는 `fp_units` 대조에서 멈춘다(조용히 빠지지 않는다 · D-220)
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
import shutil
import subprocess
import sys
import tempfile

from collect import registry

SOURCE_ID = "ftc_press"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/ftc_press_old.jsonl")
#: 범위 끝 — 이 날짜까지 등록된 보도자료만 (머리말 「범위」 · 원장 09-30 ④)
UNTIL = "2007-12-31"
_DATE = re.compile(r"<em>등록</em>\s*:\s*(\d{4}-\d{2}-\d{2})")
_TITLE = re.compile(r'class="p-table__subject_text">\s*(.*?)\s*(?:<!--|</div>)', re.S)
_HWP3 = b"HWP Document File"


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


def _hwp3(path: pathlib.Path) -> str | None:
    """한글 3.0 → 글(LibreOffice). 없거나 실패하면 None — 읽지 못한 것으로 적는다."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(
            [
                exe,
                "--headless",
                "--convert-to",
                "txt:Text (encoded):UTF8",
                "--outdir",
                d,
                str(path),
            ],
            capture_output=True,
            timeout=180,
            check=False,
        )
        got = pathlib.Path(d) / (path.stem + ".txt")
        return got.read_text(encoding="utf-8", errors="ignore") if got.exists() else None


def attachments(nid: str) -> tuple[list[str], list[str]]:
    """사건의 첨부 글 · 읽지 못한 첨부 이름."""
    texts, unread = [], []
    for p in sorted(RAW_DIR.glob(f"ftc_press_{nid}_*")):
        if p.suffix.lower() != ".hwp":
            unread.append(p.name)
            continue
        t = _hwp3(p) if p.read_bytes()[: len(_HWP3)] == _HWP3 else _hwp5(p)
        if t is None:
            unread.append(p.name)
        else:
            texts.append(t)
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
        rows.append(
            {
                "사건": nid,
                "등록": m.group(1),
                "제목": re.sub(r"\s+", " ", t.group(1)).strip() if t else "",
                "본문": "\n\n".join([body, *att]),
                "첨부_못읽음": unread,
                "원천": SOURCE_ID,
            }
        )
    return rows


#: 마스킹을 거는 자리 — 🚨 문구 대조(`fp_units`)는 **마스킹된 본문**에서 한다
MASK_FIELDS = ("제목", "본문")


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter, list[dict]]:
    from preprocess.mask import apply_policy  # noqa: PLC0415

    log: list[dict] = []
    changed: collections.Counter = collections.Counter()
    out = []
    for r in rows:
        rec = dict(r)
        for f in MASK_FIELDS:
            m = apply_policy(rec[f], "", SOURCE_ID, log)
            changed[f] += m != rec[f]
            rec[f] = m
        out.append(rec)
    return out, changed, log


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 보도자료 1997~2007 → 사건 레코드")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
