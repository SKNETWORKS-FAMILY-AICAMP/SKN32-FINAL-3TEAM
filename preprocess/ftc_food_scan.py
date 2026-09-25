"""preprocess/ftc_food_scan.py — 공정위 의결서 중 **식품·건강기능식품 광고에 표시광고법을 적용한 사건**을 센다 (D-272 ⬜ · 2026-09-25).

  uv run python -m preprocess.ftc_food_scan
  uv run python -m preprocess.ftc_food_scan --show 60

★ 무엇을 재나 — 식품표시광고법 제3조(「다른 법률에 우선하여」)가 표시광고법을 **배제**하는지.
   공정위가 식품 광고에 표시광고법으로 시정명령·과징금을 낸 의결이 있으면 「공존」 해석의 실증 근거다.
   🚨 **판정이 아니다** — 의결이 있어도 식품표시광고법이 먼저 걸리지 않은 사안일 수 있다. 법률 확인 질문을 좁힌다.

🔴 이 모듈은 라벨을 만들지 않는다 — 계측이다. 읽기만 한다(`ftc_triage` 와 같은 자리 · 수집 규약 1 의 대상이 아니다).
🚨 `scripts/` 가 아니라 `preprocess/` 다 — `data/raw` 를 읽는 것은 수집·전처리뿐이다 (D-92 · 게이트
   `test_raw_는_수집_전처리_밖에서_참조되지_않는다`). `ftc_triage` 가 같은 자리에서 같은 교훈을 남겼다.

셈의 정의 — 🔴 낱말로 찾은 **근사**다 [임의]
  표시광고  `ftc_triage.classify` 의 A · A' · B · C (사건명 행위유형 · D-99 — 분류를 두 곳에 두지 않는다).
            법률명으로만 세면 「법 제3조」로 약칭한 본건을 놓친다(`ftc_triage` 머리말 · 270 vs 660)
  식품      사건명·주문에 `FOOD` 낱말. 🚨 「식품」이 든 회사명은 **마스킹 전 원문**으로 찾는다 — 오탐이 섞인다 → 행을 눈으로 본다
  식품법    본문에 식품표시광고법 · 식품위생법 · 건강기능식품법 이름 — 공정위가 두 법의 관계를 말했는지 보는 자리
🔴 `build/` 로 나가는 사건명은 **마스킹을 지난다** (D-17 · `apply_policy` · `interp_scan` 과 같은 규칙).
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re
import xml.etree.ElementTree as ET

from collect import store
from preprocess.ftc_triage import CORE, RAW, classify
from preprocess.mask import anchor_ftc, apply_policy
from preprocess.text import sep_norm

OUT = pathlib.Path("build/ftc_food_scan.csv")

#: [임의] — 식품·건기식 광고로 볼 낱말. 회사명에 걸리는 행은 눈으로 거른다
FOOD = (
    "건강기능식품",
    "건강식품",
    "건강보조식품",
    "식품",
    "다이어트",
    "유산균",
    "프로바이오틱스",
    "홍삼",
    "영양제",
    "비타민",
    "음료",
    "생수",
    "먹는샘물",
    "우유",
    "분유",
    "과자",
    "라면",
    "커피",
    "녹즙",
    "효소",
    "콜라겐",
)
FOOD_LAW = re.compile(
    r"식품\s*등의\s*표시\s*·?\s*광고에\s*관한\s*법률|식품표시광고법|식품위생법"
    r"|건강기능식품에\s*관한\s*법률|건강기능식품법"
)
SANCTION = re.compile(r"시정명령|과징금|고발|경고")
COLS = ["seq", "결정일자", "분류", "식품낱말", "식품법언급", "제재", "사건명"]
#: 🚨 B(고객유인·위계)는 **공정거래법** 사건이다 — 표시광고법 적용의 근거로 세지 않는다 (`ftc_triage.BUCKETS`)
FAIR_ACT = {"A", "A'", "C"}
_YMD = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})")
_CONTEXT = re.compile(r"[^.。\n]{0,120}(?:기간|20\d\d\s*년|19\d\d\s*년)[^.。\n]{0,120}")


def _ymd(day: str) -> tuple[int, int, int]:
    """「2021.7.9.」 · 「2021.11.15.」 → 정렬 가능한 수. 🚨 문자열로 정렬하면 7월이 11월 뒤에 온다. 못 읽으면 (0,0,0)"""
    m = _YMD.search(day)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)  # type: ignore[return-value]


def _text(node: ET.Element, path: str) -> str:
    el = node.find(path)
    return (el.text or "").strip() if el is not None and el.text else ""


def scan(show: int) -> int:
    files = store.current_files(RAW, "*.xml") if RAW.exists() else []
    if not files:
        # 🔴 없음이 「식품 사건 0」으로 읽히면 안 된다 (D-220)
        print(
            f"🔴 {RAW} 에 의결서 XML 이 없다 — 이 기기에는 수집본이 없다. 0 이 아니라 **미측정**이다."
        )
        return 1
    bad, rows = 0, []
    for p in files:
        try:
            r = ET.parse(p).getroot()
        except ET.ParseError:
            bad += 1
            continue
        raw = {f: _text(r, f) for f in ("사건명", "주문", "결정요지", "이유")}
        name, order, gist, reason = (sep_norm(raw[f]) for f in raw)
        k = classify(name, order, gist, reason)
        if k not in CORE:
            continue
        hits = [w for w in FOOD if w in raw["사건명"] + " " + raw["주문"]]
        if not hits:
            rows.append({"분류": k, "식품낱말": "", "결정일자": _text(r, "결정일자")})
            continue
        _, bare = anchor_ftc(r)
        rows.append(
            {
                "seq": _text(r, "결정문일련번호"),
                "결정일자": _text(r, "결정일자"),
                "분류": k,
                "식품낱말": "·".join(hits),
                "식품법언급": "·".join(
                    sorted({m.group(0) for m in FOOD_LAW.finditer(order + gist + reason)})
                ),
                "제재": "·".join(sorted({m.group(0) for m in SANCTION.finditer(order)})),
                "사건명": apply_policy(name, bare, "ftc"),  # 🔴 마스킹 뒤 (D-17)
            }
        )
    food = [x for x in rows if x["식품낱말"]]
    fair = [x for x in rows if x["분류"] in FAIR_ACT]
    fair_food = [x for x in food if x["분류"] in FAIR_ACT]
    both = [x for x in food if x["식품법언급"]]
    print(
        f"의결서 {len(files):,} · 못 읽음 {bad} · 표시광고 사건(A·A'·B·C) {len(rows):,}"
        f" · 그중 식품 낱말 {len(food):,} · 그중 본문에 식품법 이름 {len(both):,}"
    )
    if bad:
        print(f"🚨 못 읽은 XML {bad} — 셈에서 빠졌다")
    c = collections.Counter(w for x in food for w in x["식품낱말"].split("·"))
    print(
        "식품 낱말별 (한 사건이 여럿에 걸린다):", ", ".join(f"{w} {n}" for w, n in c.most_common())
    )
    print(
        "제재 (주문 기준):", dict(collections.Counter(x["제재"] or "(주문에 없음)" for x in food))
    )
    print(
        "분류:",
        dict(collections.Counter(x["분류"] for x in food)),
        "— B 는 공정거래법(고객유인)이다",
    )
    # ★ 연도별 — 표시광고법 적용 사건(A·A'·C) 전체 대비 식품. 식품표시광고법 시행(2019-03-14) 전후를 가른다
    ya = collections.Counter(_ymd(x["결정일자"])[0] for x in fair)
    yf = collections.Counter(_ymd(x["결정일자"])[0] for x in fair_food)
    print("\n연도별 표시광고법 사건(A·A'·C) — 전체 / 식품 낱말  (0 = 결정일자 못 읽음)")
    print("  " + " · ".join(f"{y} {ya[y]}/{yf[y]}" for y in sorted(ya)))
    cut = (2019, 3, 14)
    after_all = sum(1 for x in fair if _ymd(x["결정일자"]) >= cut)
    after = [x for x in fair_food if _ymd(x["결정일자"]) >= cut]
    print(
        f"  식품표시광고법 시행(2019-03-14) 이후 결정 — 전체 {after_all} · 식품 낱말 {len(after)}"
    )
    print(
        "  🚨 결정일이 뒤라도 **행위 시점**이 시행 전이면 제3조와 무관하다 — `--seq` 로 본문의 기간을 본다"
    )
    food.sort(key=lambda x: _ymd(x["결정일자"]), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(food)
    print(f"\n식품 낱말 사건 전부 → {OUT} (사건명 마스킹 뒤 · build/ 는 커밋하지 않는다)")
    print(
        f"\n최근 {min(show, len(food))}건 — 일련번호 · 결정일자 · 분류 · 식품 낱말 · 식품법 언급 · 제재 · 사건명"
    )
    for x in food[:show]:
        print(
            f"  {x['seq']:>7} | {x['결정일자'] or '--------':11} | {x['분류']:2} | {x['식품낱말'][:18]:18}"
            f" | {x['식품법언급'][:22]:22} | {x['제재'][:10]:10} | {x['사건명'][:50]}"
        )
    return 0


def _mask(bare: str, text: str) -> str:
    return apply_policy(sep_norm(text), bare, "ftc")


def detail(seqs: list[str]) -> int:
    """사건 몇 건의 주문 앞부분과 **기간·연도가 적힌 문장** — 마스킹 뒤에만 보인다 (D-17)."""
    want, seen = set(seqs), set()
    for p in store.current_files(RAW, "*.xml") if RAW.exists() else []:
        r = ET.parse(p).getroot()
        seq = _text(r, "결정문일련번호")
        if seq not in want:
            continue
        seen.add(seq)
        _, bare = anchor_ftc(r)
        reason = _text(r, "이유")
        print(f"\n━━ {seq} · {_text(r, '결정일자')} · {_mask(bare, _text(r, '사건명'))}")
        print("주문 |", _mask(bare, _text(r, "주문"))[:500])
        for m in list(_CONTEXT.finditer(reason))[:8]:
            print("  기간 |", _mask(bare, m.group(0)).strip())
        for m in list(FOOD_LAW.finditer(sep_norm(reason)))[:4]:
            t = sep_norm(reason)
            print("  식품법 |", _mask(bare, t[max(0, m.start() - 150) : m.end() + 150]).strip())
    miss = want - seen
    if miss:
        print(f"\n🚨 못 찾은 일련번호 {sorted(miss)}")
    return 0 if not miss else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="공정위 의결서 중 식품 광고에 표시광고법을 적용한 사건 (D-272 ⬜)"
    )
    ap.add_argument("--show", type=int, default=30)
    ap.add_argument("--seq", nargs="+", help="이 일련번호들의 주문·기간 문장을 본다 (마스킹 뒤)")
    a = ap.parse_args()
    return detail(a.seq) if a.seq else scan(a.show)


if __name__ == "__main__":
    raise SystemExit(main())
