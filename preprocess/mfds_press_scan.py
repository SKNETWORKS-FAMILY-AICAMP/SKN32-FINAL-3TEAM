"""preprocess/mfds_press_scan.py — 식약처 보도자료 PDF 에서 **회피 표기 실사례를 센다**.

  uv run python -m preprocess.mfds_press_scan
  uv run python -m preprocess.mfds_press_scan --dump    # 문서별 결과를 파일로

전처리 사양 2-5 미해결 #3 의 답을 내는 자리다 — **실사례 30건 미만이면 「측정 불가」** (D-40).

──────────────────────────────────────────────────────────────
🚨 **왜 HTML 이 아니라 PDF 인가** (2026-09-04 실측)

  게시물 HTML 에는 **본문이 없다.** 제목·등록일·조회수·첨부 파일명뿐이고,
  40자 넘는 줄은 전부 검색 도움말이다. 광고 문구는 **첨부 PDF 에만 있다.**
  D-118 ⑤ 가 「미확인」으로 남긴 자리다.

🚨 **텍스트만 뽑는다 — 이미지는 건드리지 않는다.**
  보도자료의 적발 광고 캡처는 **광고주 저작물**이라 D-132(제24조의2)의 대상이 아니고
  D-18 에서 **G1(미추출)** 이다. PDF 를 원본으로 보관하는 것과 이미지를 뽑아 쓰는 것은
  다르고, 그 경계가 여기다. `pdfplumber` 의 `extract_text()` 만 부른다.

🚨 **공정위와 같은 계수기를 쓴다** (`preprocess.text.evasion` · D-117).
  따로 두면 두 소스의 수를 비교할 수 없다 — 「공정위 0건 · 식약처 N건」이 결론인데
  계수기가 다르면 그 비교가 성립하지 않는다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

from preprocess.text import LEX, evasion

RAW = pathlib.Path("data/raw/mfds_press_pdf")
OUT = pathlib.Path("data/derived/mfds_press/evasion_scan.json")
QUOTES = pathlib.Path("data/derived/mfds_press/quotes.json")
#: 🚨 [P1] 파싱 산출물. **PDF 를 매번 다시 열지 않는다** — 107건에 2분 넘게 걸리고,
#:    그러면 어휘를 하나 고칠 때마다 2분을 낸다. 되돌리기 싼 구조가 실제로 되돌리게 한다
#:    (색인을 본문과 나눈 것과 같은 이유 · D-118 ④).
CACHE = pathlib.Path("data/derived/mfds_press/text")

#: 🚨 D-40 — 실사례가 이 수에 못 미치면 **「측정 불가」로 보고한다.**
#:    합성 변형만으로 낸 수를 실사례 성능처럼 말하지 않는다.
MIN_CASES = 30

#: 광고 문구가 실린 자리를 알아보는 말. 🚨 이것은 **계수 기준이 아니라 길잡이**다 —
#:    본문에 광고 문구가 실제로 실리는지 눈으로 확인하려고 뽑는다.
_QUOTE = re.compile(r"[「『\"'“‘]([^」』\"'”’\n]{6,80})[」』\"'”’]")


def pdf_text(path: pathlib.Path, *, refresh: bool = False) -> str:
    """PDF 한 건의 텍스트. 🚨 이미지는 추출하지 않는다 (위 머리말).

    캐시가 있으면 그것을 쓴다 — `--refresh` 로 강제한다.
    """
    cached = CACHE / f"{path.stem}.txt"
    if not refresh and cached.exists():
        return cached.read_text(encoding="utf-8")

    import pdfplumber  # noqa: PLC0415 — docs 그룹 의존성이라 지연 import

    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="식약처 보도자료 PDF — 회피 표기 실사례 계수")
    ap.add_argument("--dump", action="store_true", help=f"문서별 결과를 {OUT} 로 쓴다")
    ap.add_argument("--limit", type=int, default=None, help="앞 N건만")
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 PDF 를 다시 연다")
    a = ap.parse_args()

    files = sorted(RAW.glob("*.pdf"))[: a.limit]
    if not files:
        print(f"🚨 {RAW} 가 비었다 — 먼저 uv run python -m collect.mfds_press --attach")
        return 1

    rows, flag_docs = [], collections.Counter()
    lex_hits = collections.Counter()
    quotes: list[tuple[str, str]] = []
    empty = 0
    for p in files:
        try:
            text = pdf_text(p, refresh=a.refresh)
        except Exception as e:  # noqa: BLE001 — 어떤 PDF 가 깨졌는지 알아야 한다
            print(f"  ❌ {p.name} — 텍스트 추출 실패: {type(e).__name__}: {e}")
            rows.append({"file": p.name, "chars": 0, "flags": [], "error": str(e)[:120]})
            continue
        # 🚨 **원문을 넘긴다** — sep_norm 을 거치면 정상 마침표가 구분자로 둔갑한다 (D-117 ②)
        flags = evasion(text)
        for f in flags:
            flag_docs[f] += 1
        for w in LEX:
            if w in text:
                lex_hits[w] += 1
        # 🚨 **광고 문구가 실제로 실리는지** 눈으로 본다 — 이 소스를 받는 이유가 그것이다.
        #    판정 어휘를 품은 인용만 모은다 (기관 명칭·법령 인용을 걸러내는 값싼 그물).
        for m in _QUOTE.finditer(text):
            q = " ".join(m.group(1).split())
            if any(w in q for w in LEX):
                quotes.append((p.stem, q))
        # 🚨 텍스트가 비면 **스캔 PDF**다 — 0건이 「없다」인지 「못 읽었다」인지 갈린다
        if len(text) < 200:
            empty += 1
        rows.append({"file": p.name, "chars": len(text), "flags": flags})

    n = len(rows)
    ok = [r for r in rows if r["chars"] >= 200]
    print(f"PDF {n}건 — 텍스트 추출 {len(ok)}건 · 🚨 비었거나 짧음 {empty}건")
    if ok:
        chars = sorted(r["chars"] for r in ok)
        print(f"  글자 수 중앙 {chars[len(chars) // 2]:,} · 최소 {chars[0]:,} · 최대 {chars[-1]:,}")
    if empty:
        print(
            "  🚨 빈 건은 **스캔 이미지 PDF** 일 수 있다 — 0건이 「없다」인지 「못 읽었다」인지 갈린다."
        )

    print("\n회피 표기 실사례 (사양 2-5 · [P11])")
    for f, label in [("S2", "구분자 삽입"), ("S3", "자모 분리"), ("S4", "zero-width")]:
        verdict = (
            "✅ 측정 가능" if flag_docs[f] >= MIN_CASES else f"🚨 측정 불가 (D-40 · {MIN_CASES}건)"
        )
        print(f"  {f} {label:12}{flag_docs[f]:>4}건 / {len(ok)}건  ← {verdict}")
    any_doc = sum(1 for r in rows if r["flags"])
    print(f"  하나라도 있는 문서 {any_doc}건")

    print("\n판정 대상 어휘가 실린 문서 (계수 기준이 아니라 길잡이)")
    for w, c in lex_hits.most_common():
        print(f"  {w:8}{c:>4}건")
    if not lex_hits:
        print("  ⬜ 하나도 없다 — 🚨 본문이 안 읽혔거나 어휘 목록이 이 원천과 안 맞는다.")

    # 🚨 **고유 종수를 센다.** 같은 문구가 여러 번 인용되는데(「기억력 개선」이 한 문서에
    #    세 번), 연·건수를 그대로 쓰면 실사례 규모를 부풀린다 — D-40 의 30건은 종수여야 한다.
    uniq = collections.Counter(q for _, q in quotes)
    print(f"\n인용된 광고 문구 — 총 {len(quotes)}회 · **고유 {len(uniq)}종**")
    verdict = "✅ 측정 가능" if len(uniq) >= MIN_CASES else f"🚨 측정 불가 (D-40 · {MIN_CASES}종)"
    print(f"  위법 문구 실사례로서: {verdict}")
    for q, c in uniq.most_common(15):
        print(f"    {c:>3}회  {q[:66]}")
    if not quotes:
        print("  ⬜ 없다 — 🚨 보도자료가 적발 문구를 **인용하지 않고 요약만** 할 수 있다.")
        print("     그러면 이 소스는 회피 표기 출처로도 쓸 수 없다 — 사양 2-5 를 다시 봐야 한다.")

    print("\n🚨 사전([P6])이 아직 없어 어휘 10개로만 셌다 — 이 수는 하한이다.")

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        QUOTES.write_text(
            json.dumps([{"doc": d, "quote": q} for d, q in quotes], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"\n→ {OUT} ({n}건)\n→ {QUOTES} ({len(quotes)}회 · 고유 {len(uniq)}종)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
