"""preprocess/evasion_scan.py — 수집한 PDF 에서 **회피 표기 실사례를 센다** (소스 공용).

  uv run python -m preprocess.evasion_scan mfds_press_pdf --dump
  uv run python -m preprocess.evasion_scan mfds_casebook --dump

🚨 **소스마다 따로 만들지 않는다.** 계수기가 다르면 「A 는 0건 · B 는 N건」이라는
   비교 자체가 성립하지 않는다 — 같은 함정을 D-117 에서 세 번 밟았다.

전처리 사양 2-5 미해결 #3 의 답을 내는 자리다 — **실사례 30건 미만이면 「측정 불가」** (D-40).

──────────────────────────────────────────────────────────────
🚨 **왜 HTML 이 아니라 PDF 인가** (2026-09-04 실측 · `mfds_press`)

  게시물 HTML 에는 **본문이 없다.** 제목·등록일·조회수·첨부 파일명뿐이고,
  40자 넘는 줄은 전부 검색 도움말이다. 광고 문구는 **첨부 PDF 에만 있다.**
  D-118 ⑤ 가 「미확인」으로 남긴 자리다.

🚨 **텍스트만 뽑는다 — 이미지는 건드리지 않는다.**
  보도자료의 적발 광고 캡처는 **광고주 저작물**이라 D-132(제24조의2)의 대상이 아니고
  D-18 에서 **G1(미추출)** 이다. PDF 를 원본으로 보관하는 것과 이미지를 뽑아 쓰는 것은
  다르고, 그 경계가 여기다. `pdfplumber` 의 `extract_text()` 만 부른다.

🔴 **무엇을 쓰는가 — 「산출물이 없다」가 아니다** (2026-09-20 · D-254 · 감사 §2 scan).
   ⛔ 런처 `scan` 과 `preprocess.SCANNERS` 주석은 「라벨을 만들지 않는다 · 산출물이 없다」라 적는다.
      **라벨은 안 만들지만 파일은 쓴다** —
        늘      `data/derived/<폴더>/text/*.txt`  🚨 **마스킹 전** PDF 전문 캐시 (`pdf_text`).
                원문캐시 부류라 저장소로 안 옮긴다 (`derived_manifest.KIND_RULES` · D-251)
        --dump  `data/derived/<폴더>/evasion_scan.json` · `quotes.json` — 인용은 마스킹을 지난다
   🚨 `--dump` 없이 돌려도 캐시는 생긴다 — 「세기만 한다」를 「아무것도 안 남는다」로 읽지 않는다.

🔴 **인자는 원문 폴더 이름이고 마스킹 정책은 원천 id 로 찾는다** (2026-09-20 · D-254).
   ⛔ 종전에는 폴더 이름(`mfds_press_pdf`)을 그대로 정책 키로 넘겨 `MaskPolicyError` 로 멈췄다 —
      정책은 원천 id(`mfds_press`)에 걸려 있다. 폴더 → 원천은 `collect.store.FAMILY_OF` 가 정본이다
      (`policy_source()`). ⛔ POLICY 에 폴더 이름을 더해 막지 않는다 — 판정 단위가 둘로 갈린다.

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

from collect import store
from preprocess.mask import apply_policy
from preprocess.text import LEX, evasion, quoted


#: 🚨 소스 이름이 곧 경로다 — `data/raw/<이름>/` 을 읽고 `data/derived/<이름>/` 에 쓴다.
#:    수집기가 그렇게 저장하므로(store.raw_dir) 여기서 규칙을 다시 만들지 않는다.
#: 🔗 넷째 값 `text/` 는 **마스킹 전 PDF 전문 캐시**다 — `scripts/derived_manifest.py` `KIND_RULES` 가 이 폴더 이름으로
#:    원문캐시(저장소로 안 옮긴다)를 가른다. 이름을 바꾸면 양쪽을 같이 (D-99 · D-251).
def paths(source: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    raw = pathlib.Path("data/raw") / source
    der = pathlib.Path("data/derived") / source
    return raw, der / "evasion_scan.json", der / "quotes.json", der / "text"


def policy_source(folder: str) -> str:
    """원문 폴더 이름 → 마스킹 정책을 찾을 **원천 id** (D-254). 🔗 표는 `collect.store.FAMILY_OF` 한 곳 (D-99).

        mfds_press_pdf  →  mfds_press      (부속 폴더 — FAMILY_OF 가 가리킨다)
        mfds_casebook   →  mfds_casebook   (표에 없으면 폴더 = 원천)

    🔴 **두 원천 이상이 같은 폴더를 쓰면 멈춘다** (예: `ftc`) — 어느 원천의 정책인지 고르는 것은 판정이다.
       ⛔ 첫 번째를 조용히 고르지 않는다 (D-220).
    """
    owners = sorted(sid for sid, fams in store.FAMILY_OF.items() if folder in fams)
    if not owners or folder in owners:
        return folder
    if len(owners) == 1:
        return owners[0]
    raise SystemExit(
        f"🔴 원문 폴더 {folder!r} 를 원천 {owners} 가 함께 쓴다 — 어느 원천의 마스킹 정책인지 못 고른다.\n"
        "  `collect/store.py` 의 FAMILY_OF 를 보고 원천을 하나로 정한다 (D-220)."
    )


#: 🚨 [P1] 파싱 산출물을 캐시한다. **PDF 를 매번 다시 열지 않는다** — 107건에 2분 넘게
#:    걸리고, 그러면 어휘를 하나 고칠 때마다 2분을 낸다. 되돌리기 싼 구조가 실제로
#:    되돌리게 한다 (색인을 본문과 나눈 것과 같은 이유 · D-118 ④).

#: 🚨 D-40 — 실사례가 이 수에 못 미치면 **「측정 불가」로 보고한다.**
#:    합성 변형만으로 낸 수를 실사례 성능처럼 말하지 않는다.
MIN_CASES = 30

#: 광고 문구가 실린 자리를 알아보는 말. 🚨 이것은 **계수 기준이 아니라 길잡이**다 —
#:    본문에 광고 문구가 실제로 실리는지 눈으로 확인하려고 뽑는다.
#: 🔄 2026-09-08 — 자체 정규식을 버리고 `preprocess.text.quoted` 로 옮겼다 (D-160).
#:    ⛔ 옛 정규식은 닫는 자리에 여는 따옴표를 안 두어, 원천이 「‘난임예방‘」처럼 적으면
#:       **멈추지 못하고 다음 따옴표까지 물었다.** 버려진 게 아니라 **틀린 종이 만들어졌다** —
#:       「피로개선‘, ‘뇌건강」은 두 표현인데 한 종으로 세어졌다.
#:    🚨 범위 차이는 정규식이 아니라 **선언된 파라미터**로 둔다 — 아래 두 값이 전부다.
QUOTE_MIN, QUOTE_MAX = 6, 80


def pdf_text(path: pathlib.Path, cache: pathlib.Path, *, refresh: bool = False) -> str:
    """PDF 한 건의 텍스트. 🚨 이미지는 추출하지 않는다 (위 머리말).

    캐시가 있으면 그것을 쓴다 — `--refresh` 로 강제한다.
    """
    cached = cache / f"{path.stem}.txt"
    if not refresh and cached.exists():
        return cached.read_text(encoding="utf-8")

    import pdfplumber  # noqa: PLC0415 — docs 그룹 의존성이라 지연 import

    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8", newline="\n")
    return text


def image_stats(files: list[pathlib.Path]) -> None:
    """🚨 **캡처가 실려 있는가**를 쪽 면적 대비 크기로 가른다.

    보도자료 실측(2026-09-04)에서는 이미지 110개 중 **106개(96%)가 89×31pt 급 로고·머리글**
    이었고 캡처는 4개뿐이었다 — 「이미지가 있다」와 「캡처가 있다」는 다르다.
    회피 표기가 이미지 안에 살아 있을 수 있는지는 이 분포가 답한다 (D-133 ②).
    """
    import pdfplumber  # noqa: PLC0415

    buckets: collections.Counter[str] = collections.Counter()
    sample: dict[str, str] = {}
    pages = 0
    for f in files:
        try:
            with pdfplumber.open(f) as pdf:
                for pg in pdf.pages:
                    pages += 1
                    pw, ph = pg.width, pg.height
                    for im in pg.images:
                        w = im["x1"] - im["x0"]
                        h = im["bottom"] - im["top"]
                        frac = (w * h) / (pw * ph) if pw and ph else 0
                        k = (
                            "① 아주 작음 (로고·아이콘)"
                            if frac < 0.01
                            else "② 작음 (표·도장)"
                            if frac < 0.06
                            else "③ 중간 (캡처 후보)"
                            if frac < 0.25
                            else "④ 큼 (전면 캡처)"
                        )
                        buckets[k] += 1
                        sample.setdefault(k, f"{f.stem} {w:.0f}×{h:.0f}pt ({frac * 100:.1f}%)")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {f.name} — {type(e).__name__}")
    total = sum(buckets.values())
    print(f"\n이미지 {total}개 / {pages}쪽 — 쪽 면적 대비 크기")
    if not total:
        print("  ⬜ 이미지가 없다 — 순수 텍스트 문서다.")
        return
    for k in sorted(buckets):
        pct = buckets[k] * 100 // total
        print(f"  {k:22}{buckets[k]:>5}개 {pct:>3}%   {sample.get(k, '')}")
    big = buckets["③ 중간 (캡처 후보)"] + buckets["④ 큼 (전면 캡처)"]
    if big:
        print(f"\n  ★ 캡처 후보 {big}개 — 회피 표기가 **이미지 안에** 있을 수 있다.")
        print(
            "     🚨 그러나 캡처는 광고주 저작물이라 G1(미추출)이다 — **문구만** 취한다 (D-133 · D-18)."
        )
        print("     🚨 OCR 은 「기ㆍ억력」을 「기억력」으로 교정한다 — 검증 없이 낸 수는 못 쓴다.")
    else:
        print("\n  이미지가 전부 장식이다 — 캡처가 없다. 텍스트 계수 결과가 곧 결론이다.")


def main() -> int:
    ap = argparse.ArgumentParser(description="수집 PDF — 회피 표기 실사례 계수 (소스 공용)")
    ap.add_argument("source", help="data/raw/ 아래 디렉터리 이름 (예: mfds_casebook)")
    ap.add_argument(
        "--dump", action="store_true", help="문서별 결과·인용문을 data/derived/<소스>/ 로 쓴다"
    )
    ap.add_argument("--limit", type=int, default=None, help="앞 N건만")
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 PDF 를 다시 연다")
    ap.add_argument(
        "--images",
        action="store_true",
        help="🚨 캡처가 실려 있는지 크기 분포로 가른다 (PDF 를 다시 연다)",
    )
    a = ap.parse_args()

    RAW, OUT, QUOTES, CACHE = paths(a.source)
    # 🔴 **파일을 열기 전에** 정책 원천을 정한다 — 모르면 PDF 를 다 연 뒤가 아니라 여기서 멈춘다.
    policy = policy_source(a.source)
    files = store.current_files(RAW, "*.pdf")[: a.limit]
    if not files:
        print(f"🚨 {RAW} 에 PDF 가 없다 — 먼저 수집기를 돌린다.")
        return 1

    rows, flag_docs = [], collections.Counter()
    lex_hits = collections.Counter()
    quotes: list[tuple[str, str]] = []
    empty = 0
    for p in files:
        try:
            text = pdf_text(p, CACHE, refresh=a.refresh)
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
        for q in quoted(text, min_len=QUOTE_MIN, max_len=QUOTE_MAX):
            if any(w in q for w in LEX):
                # 🔴 **derived 로 나가는 것은 마스킹을 지난다** (D-17 · 2026-09-06).
                #    인용된 광고 문구에는 업체명·제품명이 섞여 들어온다.
                #    🚨 이 원천에 masking: 선언이 없으면 여기서 **멈춘다** (D-72 fail-closed).
                #       조용히 통과시키면 「선언이 없다」와 「불필요하다」가 구분되지 않는다.
                quotes.append((p.stem, apply_policy(q, "", policy)))
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

    if a.images:
        image_stats(files)

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        QUOTES.write_text(
            json.dumps([{"doc": d, "quote": q} for d, q in quotes], ensure_ascii=False, indent=1),
            encoding="utf-8",
            newline="\n",
        )
        print(f"\n→ {OUT} ({n}건)\n→ {QUOTES} ({len(quotes)}회 · 고유 {len(uniq)}종)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
