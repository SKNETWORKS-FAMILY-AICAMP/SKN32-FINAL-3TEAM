"""preprocess/interp_scan.py — 식약처 1차 법령해석(`mfds_cgm_expc`)이 **평가 라벨의 원천**이 되는가.

  uv run python -m preprocess.interp_scan mfds_cgm_expc              # 세기만 한다 (화면에 수만)
  uv run python -m preprocess.interp_scan mfds_cgm_expc --candidates # + 후보를 build/ 에 쓴다 (마스킹 뒤)

🔴 이 모듈은 라벨을 만들지 않는다 — 계측(`SCANNERS`)이다. **셋만 묻는다.**

  ① 5,129건 중 **부당 표시·광고 조항**을 다룬 해석이 몇 건인가 (관련법령 · 안건명의 그물)
  ② 그중 **특정 문구**를 두고 물은 것이 몇 건인가 (질의요지의 인용부호)
  ③ 기관이 **어느 호(號)로** 봤는가 — 「제8조제1항제N호」가 적혀 있으면 우리 유형과 1:1 이다

팀장 — *「기관 판단 원천 후보 등을 충분히 탐색해보고 분석한 뒤 진행해보자」* (2026-09-20).
평가셋 4유형(비방 12 · 의약품 8 · 질병 6 · 후기 1)이 D-40 의 30 밑이다. 사람 라벨 전에
**기관이 이미 판단해 둔 문장**이 어디에 있는지를 먼저 잰다.

🚨 **표본 45건 실측 (2026-09-20 · 컨테이너)** — 부당광고 조항(식품표시광고법 제8조)을 다룬 것 **2/45**.
   대부분은 수입신고 · 품목허가 · 시설기준 같은 **절차 질의**다. 5,129건 전체에서 얼마인지가 이 모듈의 질문이다.
🚨 **회답은 「민원 답변」이다** — 스스로 「이후 개정 법규·사실관계에 따라 달리 적용될 수 있다」고 적는다.
   의결서·심의 지적보다 **구속력이 약하다.** 라벨 지위는 사람이 정한다 (D-151 ② 검증셋 흐름).
🔴 **후보 파일은 마스킹을 지난 뒤에만 쓴다** (`mask.apply_policy` · 원천 정책 org·person · D-248).
   쓰는 자리는 `build/` 다 — 커밋되지 않고 공유 저장소로도 안 간다(파생물이 아니다).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import xml.etree.ElementTree as ET

from collect import store
from preprocess.text import quoted

#: 부당 표시·광고 **조항**의 그물 — 관련법령 문자열에 이것이 있으면 센다. 🚨 판정이 아니다.
#: 식품표시광고법 제8조 · 건강기능식품법 제18조 · 화장품법 제13조 · 약사법 제68조 · 의료기기법 제24조
AD_ARTICLES: tuple[tuple[str, str], ...] = (
    ("식품표시광고법 제8조", r"표시\s*[ㆍ·]?\s*광고에\s*관한\s*법률.{0,20}제8조"),
    ("건강기능식품법 제18조", r"건강기능식품에\s*관한\s*법률.{0,20}제18조"),
    ("화장품법 제13조", r"화장품법.{0,20}제13조"),
    ("약사법 제68조", r"약사법.{0,20}제68조"),
    ("의료기기법 제24조", r"의료기기법.{0,20}제24조"),
)
#: 관련법령이 비었거나 다른 조를 달았어도 **질의가 광고 문구를 묻는** 경우를 줍는 둘째 그물
AD_WORDS = re.compile(r"광고|표시\s*[ㆍ·]?\s*광고|문구|표현|문안")

#: 식품표시광고법 제8조제1항 각 호 → 우리 유형 (D-155 표와 같다 · 1:1)
HO_TYPE: dict[str, str] = {
    "1": "질병_예방치료_표방",
    "2": "의약품_오인",
    "3": "건강기능식품_오인",
    "4": "거짓_과장",
    "5": "소비자_기만",
    "6": "비방광고",
    "7": "부당_비교광고",
}
HO = re.compile(r"제8조\s*제1항\s*제(\d)호")

#: 유형 **단서**(판정 아님) — 호가 안 적힌 해석을 사람이 볼 때 순서를 정하는 데만 쓴다
CUES: dict[str, re.Pattern[str]] = {
    "질병_예방치료_표방": re.compile(r"질병.{0,10}(예방|치료|완화)|예방\s*[ㆍ·]?\s*치료"),
    "의약품_오인": re.compile(r"의약품(으로|과)\s*(오인|혼동|인식)|약효|처방"),
    "건강기능식품_오인": re.compile(r"건강기능식품(으로|과)\s*(오인|혼동|인식)"),
    "후기_체험기_기만": re.compile(r"체험기|체험\s*사례|후기|사용\s*후기|소비자\s*리뷰"),
    "비방광고": re.compile(r"비방"),
    "부당_비교광고": re.compile(r"비교\s*(표시|광고)|타사|다른\s*업체"),
}

#: 회답의 결론 단서 — 🚨 **판정이 아니다.** 「~할 수 없을 것으로 판단」과 「~에 해당하지 않을 것」이 섞인다
NEG = re.compile(
    r"(표시|광고|사용)\s*(하)?(할|하실)\s*수\s*없|해당(할|될)\s*(수\s*있|것으로)|부당한\s*표시|위반"
)
POS = re.compile(r"(표시|광고|사용)\s*(하)?(할|하실)\s*수\s*있|해당하지\s*않")

#: 🔴 낫표는 **법령명**을 인용한다(「식품 등의 표시·광고에 관한 법률」) — 문구로 세지 않는다 (sanctions_scan 과 같은 이유)
QUOTE_FAMILIES_AD = ("‘’", "“”", '"', "'")


def _fields(path: pathlib.Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    return {ch.tag: (ch.text or "").strip() for ch in root}


def _articles(law: str) -> list[str]:
    return [name for name, pat in AD_ARTICLES if re.search(pat, law)]


def classify(f: dict[str, str]) -> dict:
    """한 해석 → 계측 칸. 🚨 원문을 담지 않는다(후보 쓰기는 `candidates` 가 마스킹해서)."""
    law = f.get("관련법령", "")
    q, a, why = f.get("질의요지", ""), f.get("회답", ""), f.get("이유", "")
    arts = _articles(law)
    ad_word = bool(AD_WORDS.search(f.get("안건명", "") + " " + q))
    phrases = quoted(q, min_len=2, max_len=120, families=QUOTE_FAMILIES_AD)
    hos = sorted(set(HO.findall(a + "\n" + why)))
    cues = sorted(t for t, p in CUES.items() if p.search(q + "\n" + a))
    neg, pos = bool(NEG.search(a)), bool(POS.search(a))
    return {
        "조항": arts,
        "광고어": ad_word,
        "문구수": len(phrases),
        "호": hos,
        "호유형": sorted({HO_TYPE[h] for h in hos if h in HO_TYPE}),
        "단서": cues,
        "결론": "불가"
        if neg and not pos
        else "가능"
        if pos and not neg
        else "섞임"
        if neg
        else "없음",
    }


def scan(source: str) -> tuple[dict, list[tuple[pathlib.Path, dict, dict]]]:
    raw = store.raw_dir_of(source)
    files = store.current_files(raw, "*.xml")
    if not files:
        raise FileNotFoundError(f"{raw} 에 *.xml 이 없다 — 먼저 수집기를 돌린다")
    rows = []
    for p in files:
        f = _fields(p)
        rows.append((p, f, classify(f)))
    ad = [r for r in rows if r[2]["조항"] or r[2]["광고어"]]
    art = [r for r in rows if r[2]["조항"]]
    phr = [r for r in ad if r[2]["문구수"]]
    count = collections.Counter
    return {
        "해석": len(rows),
        "부당광고_조항": len(art),
        "조항별": dict(count(a for r in art for a in r[2]["조항"]).most_common()),
        "광고_그물(조항∪광고어)": len(ad),
        "그중_문구를_물은_것": len(phr),
        "문구_수": sum(r[2]["문구수"] for r in phr),
        "호가_적힌_것": sum(1 for r in ad if r[2]["호"]),
        "호유형": dict(count(t for r in ad for t in r[2]["호유형"]).most_common()),
        "단서(문구를_물은_것)": dict(count(t for r in phr for t in r[2]["단서"]).most_common()),
        "결론(문구를_물은_것)": dict(count(r[2]["결론"] for r in phr).most_common()),
        "연도(문구를_물은_것)": dict(
            sorted(count(r[1].get("해석일자", "")[:4] for r in phr).items())
        ),
    }, ad


def candidates(phr: list[tuple[pathlib.Path, dict, dict]], out: pathlib.Path) -> int:
    """🔴 사람이 볼 후보 — **마스킹을 지난 글만** 쓴다. 쓰는 곳은 `build/`(커밋·공유 밖)."""
    from preprocess.mask import apply_policy  # noqa: PLC0415 — 쓸 때만 무겁게

    out.parent.mkdir(parents=True, exist_ok=True)
    src = "mfds_cgm_expc"
    with out.open("w", encoding="utf-8", newline="\n") as w:
        for p, f, c in phr:
            q = apply_policy(f.get("질의요지", ""), "", src)
            a = apply_policy(f.get("회답", ""), "", src)
            rec = {
                "id": p.stem,
                "해석일자": f.get("해석일자", ""),
                "안건명": apply_policy(f.get("안건명", ""), "", src),
                "관련법령": f.get("관련법령", ""),
                "문구": quoted(q, min_len=2, max_len=120, families=QUOTE_FAMILIES_AD),
                "질의요지": q[:600],
                "회답": a[:800],
                **c,
            }
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(phr)


def main() -> int:
    ap = argparse.ArgumentParser(description="1차 법령해석 — 평가 라벨의 원천이 되는가")
    ap.add_argument("source", nargs="?", default="mfds_cgm_expc")
    ap.add_argument(
        "--candidates",
        action="store_true",
        help="후보를 build/interp_candidates.jsonl 에 쓴다 (마스킹 뒤 · 커밋 안 됨)",
    )
    a = ap.parse_args()
    got, ad = scan(a.source)
    for k, v in got.items():
        print(f"  {k:<28} {v}")
    print(
        "\n  🚨 그물이다 — 판정이 아니다. 「호가 적힌 것」만 기관이 유형을 말한 것이고,"
        " 나머지 유형은 단서(사람이 볼 순서)다."
    )
    if a.candidates:
        out = pathlib.Path("build") / "interp_candidates.jsonl"
        n = candidates(ad, out)  # 문구를 안 물은 것도 — 회답 본문에 문구가 있을 수 있다
        print(f"\n  → {out} {n}행 (마스킹 뒤 · build/ 는 커밋되지 않는다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
