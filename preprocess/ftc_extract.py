"""preprocess/ftc_extract.py — 공정위 결정문 「주문」에서 **1층 라벨 삼요소**를 뽑는다.

  uv run python -m preprocess.ftc_extract              # 세기만 한다
  uv run python -m preprocess.ftc_extract --dump       # data/derived/ftc_layer1_phrases.json

수집이 아니라 **읽기만 한다** — `data/raw/ftc/*.xml` 을 건드리지 않는다 (`preprocess/` 에 있는 이유).

──────────────────────────────────────────────────────────────
★ 왜 「주문」인가 — 한 문장에 입력·라벨·근거가 다 있다 (2026-09-07 실측)

    “초유함량 국내 최대”라고 표시·광고함으로써  자신의 제품에 포함된 초유함량이
    └──── ① 입력: 광고 문구 원문 ────┘          국내 최대가 아님에도  마치 국내 최대인 것처럼
                                                └──── ③ 근거: 왜 부당한가 ────┘
    … 거짓·과장의 광고행위를 다시 하여서는 아니 된다
      └ ② 라벨: 유형 ┘

  D-59 의 A/B/C 형이 그대로다.

🚨 **「이유」가 아니다.** 「이유」에는 인용부호가 훨씬 많지만 대부분 노이즈다 —
   `/LSW/flDownload.do?flSeq=…`(첨부 링크) · 「이유 1번째 이미지」(이미지 alt) ·
   「이라 한다)」(약칭 정의). 실측에서 「이유」는 665문서가 걸렸는데 광고 문구는 거의 없었다.
   **주문 261~308문서**가 실제 자리다.

🚨 **B 버킷(고객유인·위계)에는 광고 문구가 거의 없다 — 105건 중 4건.**
   09-06 인계가 「값은 B 에 있다(17→105, 6배)」고 적은 것은 **모수 증가** 관점이고,
   **광고 문구 관점에서는 A 가 압도적**(280/680)이다. 두 말이 모순이 아니라 축이 다르다.

🚨 **분류는 `sep_norm` 을 지난 문장으로 한다.** 원문으로 `classify` 를 부르면
   A 680 → 599, A′ 67 → 12 로 **135건이 샌다** (2026-09-07 실측 · D-117).
   `ftc_triage.main()` 이 그렇게 하고 있고, 여기도 같아야 두 산출물의 수가 맞는다.

🔴 **derived 로 나가는 것은 마스킹을 지난다** (D-17 · 게이트).
   문구를 뽑기 **전에** `apply_policy` 를 건다 — 뽑은 뒤에 걸면 업체명이 문구 안에 남는다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import xml.etree.ElementTree as ET

from preprocess.ftc_triage import CORE, _text, classify
from preprocess.mask import anchor_ftc, apply_policy
from preprocess.text import sep_norm

RAW = pathlib.Path("data/raw/ftc")
OUT = pathlib.Path("data/derived/ftc_layer1_phrases.json")

#: 인용부호 5종. 원천이 섞어 쓴다.
QUOTE = re.compile(r"[‘'\"“「『]([^’'\"”」』\n]{4,120})[’'\"”」』]")

#: 🚨 인용부호 안이라고 다 광고 문구가 아니다. 실측에서 걸러야 했던 것들 —
#:    법문 재인용(「소비자를 속이거나 오인시킬 우려가 있는 광고행위」) · 처분 방식(「사업장공표 문안」) ·
#:    약칭 정의(「이라 한다)」) · 첨부 링크 · 이미지 alt · 마스킹 자국.
NOISE = re.compile(
    r"법률|법 제|제\s?\d+조|시행령|시행규칙|사건번호|피심인|공정거래위원회|고시|지침|별표|위원회"
    r"|flDownload|번째 이미지|이라 한다|사업장공표|공표 ?문안|광고행위|표시행위"
    r"|\[업체\]|\[대표\]|\[주소\]|\[상표\]"
    # 🔄 2026-09-07 1회전 실측으로 추가한 둘 —
    #   ① 「별지 기재 문안」류 36건. 처분 **방식**이지 광고 문구가 아니다
    #   ② 마스킹이 이름만 지우고 남긴 법인격 표기가 인용부호에 감싸여 문구로 잡혔다 (2건)
    r"|별지|기재 ?문안|^주식회사$|^유한회사$|^㈜$"
)

#: 표시광고법 제3조 제1항 각 호. 주문의 서술어에 그대로 나온다.
#: 🚨 원천이 `·`·`ㆍ`·`.` 를 섞어 써서 `sep_norm` 뒤에 센다 (D-117).
TYPES: list[tuple[str, str, str]] = [
    ("거짓·과장", "거짓_과장", "제3조제1항제1호"),
    ("허위·과장", "거짓_과장", "제3조제1항제1호"),
    ("기만적", "소비자_기만", "제3조제1항제2호"),
    ("부당하게 비교", "부당_비교광고", "제3조제1항제3호"),
    ("비방", "비방광고", "제3조제1항제4호"),
]

#: 「… 아님에도 마치 … 인 것처럼」 — 왜 부당한가가 여기 있다.
GROUND = re.compile(r"([^.。\n]{6,120}?)(?:것처럼|것과 같이)")


def types_in(order: str) -> list[dict[str, str]]:
    """주문에 나타난 위반 유형들. 🚨 **하나가 아니다** — 한 건이 여러 호에 걸린다."""
    seen: list[dict[str, str]] = []
    for word, label, article in TYPES:
        if word in order and all(x["label"] != label for x in seen):
            seen.append({"word": word, "label": label, "article": article})
    return seen


def phrases_in(order: str) -> list[str]:
    """주문에서 광고 문구 원문만. 🚨 이미 마스킹을 지난 문자열을 받는다."""
    out: list[str] = []
    for q in QUOTE.findall(order):
        q = q.strip()
        if len(q) < 4 or q.isdigit() or NOISE.search(q):
            continue
        if q not in out:
            out.append(q)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 결정문 주문 → 1층 라벨 삼요소")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    a = ap.parse_args()

    if not RAW.exists():
        print(f"🚨 {RAW} 가 없다 — 먼저 uv run python -m collect.ftc_body")
        return 1

    rows: list[dict] = []
    buck = collections.Counter()
    lab = collections.Counter()
    docs_with = 0

    for p in sorted(RAW.glob("*.xml")):
        r = ET.parse(p).getroot()
        raw = {f: _text(r, f) for f in ("사건명", "주문", "결정요지", "이유")}
        name, order, gist, reason = (sep_norm(raw[f]) for f in raw)
        k = classify(name, order, gist, reason)
        buck[k] += 1
        if k not in CORE:
            continue

        # 🔴 뽑기 **전에** 마스킹한다. 뽑은 뒤에 걸면 문구 안의 업체명이 남는다.
        _, bare = anchor_ftc(r)
        masked = apply_policy(order, bare, "ftc")

        ps = phrases_in(masked)
        if not ps:
            continue
        docs_with += 1
        ts = types_in(masked)
        for t in ts:
            lab[t["label"]] += 1
        grounds = [m.group(1).strip() for m in GROUND.finditer(masked)][:3]
        rows.append(
            {
                "seq": _text(r, "결정문일련번호"),
                "결정일자": _text(r, "결정일자"),
                "분류": k,
                "사건명": apply_policy(name, bare, "ftc"),
                "문구": ps,
                "유형": ts,
                "근거절": grounds,
            }
        )

    total_core = sum(buck[k] for k in CORE)
    n_ph = sum(len(x["문구"]) for x in rows)
    print(f"결정문 {sum(buck.values()):,}건 · 1층 후보 {total_core:,}건")
    print(f"  주문에 광고 문구가 있는 문서  {docs_with:,}건 ({docs_with * 100 // total_core}%)")
    print(f"  뽑은 문구                    {n_ph:,}개 (문서당 {n_ph / max(docs_with, 1):.1f})")
    print()
    print("  유형별 문서 수 — 🚨 한 건이 여러 호에 걸리므로 합이 문서 수를 넘는다")
    for label, c in lab.most_common():
        mark = "★" if c >= 30 else "🚨"  # D-40 — 30건 미만은 「측정 불가」
        print(f"    {mark} {label:16s} {c:>4}건")
    if any(c < 30 for c in lab.values()):
        print("    🚨 30건 미만 유형은 D-40 상 「측정 불가」다 — 홀드아웃을 세울 수 없다")
    print()
    no_type = [x for x in rows if not x["유형"]]
    print(f"  유형을 못 붙인 문서  {len(no_type):,}건 — 주문에 유형어가 없다")
    if no_type:
        print(f"    예: {no_type[0]['seq']} {no_type[0]['문구'][:2]}")
        print(
            "    🚨 유형은 문구가 아니라 **주문의 서술어**에서 온다. 없으면 「근거절」로 사람이 붙인다"
        )

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n→ {OUT}")
    else:
        print("\n(--dump 를 주면 파일로 쓴다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
