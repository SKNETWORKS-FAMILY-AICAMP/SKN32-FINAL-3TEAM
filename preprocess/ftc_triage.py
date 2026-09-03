"""preprocess/ftc_triage.py — 공정위 결정문 1,087건을 **1층 라벨 모수로 선별**하고
회피 표기 실사례를 센다 (전처리 사양 2-5 · 미해결 #3 · D-40).

  uv run python -m preprocess.ftc_triage
  uv run python -m preprocess.ftc_triage --dump      # 분류표를 파일로도 낸다

수집이 아니라 **읽기만 한다** — data/raw/ftc/*.xml 을 건드리지 않는다.
그래서 registry.require() 를 부르지 않는다 (수집기 공통 규약 1의 대상이 아니다).

🚨 **`scripts/` 가 아니라 `preprocess/` 다.** 처음에 `scripts/ftc_triage.py` 로 두었다가
   게이트 `test_raw_는_수집_전처리_밖에서_참조되지_않는다` 에 걸렸다. 게이트가 옳다 —
   `RAW_READERS` 는 `{"collect", "preprocess"}` 이고, `scripts/` 에 raw 읽기를 한 번
   허용하면 학습 스크립트가 raw 를 글롭해도 막을 수 없다 (D-19 · D-92 · D-116).

──────────────────────────────────────────────────────────────
🚨 왜 사건명으로 가르는가 — 법률명으로 가르면 본건을 놓친다 (2026-09-03 실측)

  「파인콜의 부당한 광고행위에 대한 건」은 표시광고법 본건인데
  결정문이 법률명을 풀어쓰지 않고 **「법 제3조」로 약칭**해서
  `표시·광고의 공정화에 관한 법률` 매칭에 걸리지 않는다.
  법률명으로 세면 270건, 사건명 행위유형으로 세면 660건이다.

🚨 가운뎃점이 두 종류다 — 원천이 `ㆍ`(U+318D 아래아)와 `·`(U+00B7)를 섞어 쓴다.
   정규화하지 않으면 「중요한 표시ㆍ광고사항 고시 위반」 13건이 통째로 샌다.
   law_annex.SEPARATORS 에서 이미 겪은 것과 같은 함정이다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import xml.etree.ElementTree as ET

RAW = pathlib.Path("data/raw/ftc")
OUT = pathlib.Path("data/derived/ftc_layer1_triage.json")

#: 🚨 가운뎃점 이형 정규화. 이것을 빼면 사건명 매칭이 조용히 13건을 흘린다.
SEP_NORM = str.maketrans({"ㆍ": "·", "․": "·", "‧": "·", "･": "·"})

#: A — 표시광고법 본건. 사건명의 **행위유형**이 곧 적용 법률이다.
RE_AD = re.compile(
    r"부당한\s*(?:표시·광고|표시|광고)행위"
    r"|표시·광고행위"
    r"|중요한\s*표시·광고사항"
    r"|기만적인\s*(?:표시|광고)"
    r"|거짓·과장"
)
#: B — 광고 문구가 쟁점이지만 적용 법조가 공정거래법인 것. 경계 사례다.
RE_LURE = re.compile(r"부당한\s*고객유인|위계에\s*의한")
#: C — 전자상거래법. 「거짓·과장 광고」가 섞여 있어 버리지 않고 가른다.
RE_ECOM = re.compile(r"전자상거래|통신판매|임시중지명령")
#: 법률명이 실제로 적힌 경우. 사건명이 애매할 때만 쓰는 보조 기준이다.
RE_LAWNAME = re.compile(r"표시\s*·?\s*광고의?\s*공정화|표시광고법")

BUCKETS = [
    ("A", "표시광고 본건 (사건명)"),
    ("A'", "표시광고 (주문·결정요지)"),
    ("B", "고객유인·위계"),
    ("C", "전상법 + 표시광고법"),
    ("C'", "전상법만"),
    ("D", "법률명만 언급"),
    ("E", "무관"),
]
#: A·A'·B·C 가 1층 학습 라벨 후보다. C'·D·E 는 후보에서 뺀다.
CORE = {"A", "A'", "B", "C"}

# ── 회피 표기 (전처리 사양 [P11] SURFACE_VARIANTS) ────────────
#: 🚨 사전([P6])이 아직 없다. 그때까지 **판정 대상 어휘의 최소 집합**으로 센다 —
#:    여기서 나온 수는 하한이지 전량이 아니다. 사전이 서면 다시 센다.
LEX = ["치료", "효과", "완치", "부작용", "다이어트", "미백", "주름", "개선", "예방", "특효"]
_ZW = re.compile(r"[​-‏﻿⁠]")

#: S2 구분자 삽입 — `치·료` `치.료` `치+료`.
#: 🚨 **공백을 구분자로 넣으면 안 된다** (2026-09-03 오탐으로 확인).
#:    「45**개 선**불식 할부거래업자」가 `개선` 의 회피 표기로 잡혔다. 한국어는 어절을
#:    공백으로 가르므로, 공백 하나만 허용해도 인접 두 어절의 끝·첫 글자가 늘 걸린다.
#:    회피 표기의 실제 모양은 눈에 보이는 기호(`·` `.` `+` `~`)다 — 그것만 센다.
#: 🚨 앞뒤를 어절 경계로 묶는다. 묶지 않으면 더 긴 낱말의 일부가 걸린다.
#: 🚨 구분자는 **글자마다 선택**이다 — 「다·이어트」처럼 한 곳만 쪼개는 것이 실제 모양이다.
#:    모든 자리에 요구하면(`다·이·어·트`) 실사례를 놓친다. 대신 선택으로 두면 원형
#:    「다이어트」까지 걸리므로, **매칭 문자열에 구분자가 실제로 있는지 뒤에서 확인한다.**
_SEP_CHARS = "·.-+~*^/|,_"
_SEPS = r"[" + re.escape(_SEP_CHARS) + r"]{0,2}"
_S2 = [
    (w, re.compile(r"(?<![가-힣A-Za-z0-9])" + _SEPS.join(w) + r"(?![가-힣A-Za-z0-9])")) for w in LEX
]

#: S3 자모 분리 — `ㅊl료` `다ㅇㅣ어트`. 낱자 자모가 단어 안에 끼어든 형태.
#: 🚨 **`ㅇ` 은 세지 않는다.** 의결서는 개인정보를 `대표이사 이ㅇㅇ` · `소갑 제ㅇ호증`
#:    처럼 **`ㅇ` 자리표시자로 가려서** 보낸다 (원천 마스킹 · D-17 검토요청서에서 확인).
#:    이것을 회피 표기로 세면 16건이 전부 오탐이 된다 — 실제로 그렇게 나왔다.
#:    자음은 `ㅇ` 을 뺀 나머지만, 모음은 전부 본다.
_S3 = re.compile(r"[가-힣][ㄱ-ㅆㅈ-ㅎㅏ-ㅣ][가-힣]|[ㄱ-ㅆㅈ-ㅎ][a-zA-Z][가-힣]")


def _text(node: ET.Element, path: str) -> str:
    el = node.find(path)
    return (el.text or "").strip() if el is not None and el.text else ""


def classify(name: str, order: str, gist: str, reason: str) -> str:
    """사건명 → 버킷. 앞선 규칙이 이긴다."""
    law = bool(RE_LAWNAME.search(name + order + gist + reason[:60_000]))
    if RE_AD.search(name):
        return "A"
    if RE_AD.search(order) or RE_AD.search(gist):
        return "A'"
    if RE_LURE.search(name):
        return "B"
    if RE_ECOM.search(name):
        return "C" if law else "C'"
    return "D" if law else "E"


def evasion(text: str) -> list[str]:
    """이 결정문에 실재하는 회피 표기 종류. 사양 2-5 의 `evasion_observed`."""
    flags = []
    if _ZW.search(text):
        flags.append("S4")
    # 🚨 구분자가 실제로 들어간 매칭만 센다 — 원형 낱말은 회피 표기가 아니다.
    if any(any(c in _SEP_CHARS for c in m.group(0)) for _, p in _S2 for m in p.finditer(text)):
        flags.append("S2")
    if _S3.search(text):
        flags.append("S3")
    return flags


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 결정문 1층 선별 + 회피 표기 실사례")
    ap.add_argument("--dump", action="store_true", help=f"분류표를 {OUT} 로 쓴다")
    a = ap.parse_args()

    if not RAW.exists():
        print(f"🚨 {RAW} 가 없다 — 먼저 uv run python -m collect.ftc_body --query 표시광고")
        return 1

    rows, buck = [], collections.Counter()
    ev_cnt, ev_core = collections.Counter(), collections.Counter()
    for p in sorted(RAW.glob("*.xml")):
        r = ET.parse(p).getroot()
        name, order, gist, reason = (
            _text(r, f).translate(SEP_NORM) for f in ("사건명", "주문", "결정요지", "이유")
        )
        k = classify(name, order, gist, reason)
        # 🚨 회피 표기는 **인용된 광고 원문**에 있다. 「이유」가 그것을 담는 자리다.
        flags = evasion(reason)
        buck[k] += 1
        for f in flags:
            ev_cnt[f] += 1
            if k in CORE:
                ev_core[f] += 1
        rows.append(
            {
                "seq": _text(r, "결정문일련번호"),
                "사건명": name,
                "결정일자": _text(r, "결정일자"),
                "분류": k,
                "1층후보": k in CORE,
                "회피표기": flags,
                "이유길이": len(reason),
            }
        )

    n = len(rows)
    core = [x for x in rows if x["1층후보"]]
    print(f"결정문 {n:,}건 — 1층 선별\n")
    for key, label in BUCKETS:
        mark = "★" if key in CORE else " "
        print(f"  {mark} {key:3}{label:24}{buck[key]:>5}건 {buck[key] * 100 // n:>3}%")
    print(f"\n★ 1층 학습 라벨 후보 = {len(core):,}건 / {n:,}건 ({len(core) * 100 // n}%)")

    year = collections.Counter(x["결정일자"][:4] for x in core if x["결정일자"])
    recent = sum(v for k, v in year.items() if k >= "2020")
    undated = sum(1 for x in core if not x["결정일자"])
    print(f"  2020년 이후 {recent}건 · 결정일자 없음 {undated}건")

    print("\n회피 표기 실사례 (전처리 사양 2-5 · [P11])")
    any_ev = sum(1 for x in rows if x["회피표기"])
    for f, label in [("S2", "구분자 삽입"), ("S3", "자모 분리"), ("S4", "zero-width")]:
        # 🚨 D-40 — 30건 미만이면 「측정 불가」다. 합성 변형만으로 낸 수를
        #    실사례 성능처럼 말하지 않는다. 그 판정을 여기서 바로 찍는다.
        verdict = "측정 가능" if ev_core[f] >= 30 else "🚨 측정 불가 (D-40)"
        print(f"  {f} {label:12}전체 {ev_cnt[f]:>4}건 · 1층후보 {ev_core[f]:>4}건  ← {verdict}")
    print(f"  하나라도 있는 결정문 {any_ev:,}건 / {n:,}건")
    print("  🚨 사전([P6])이 아직 없어 어휘 10개로만 셌다 — 이 수는 하한이다.")

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n→ {OUT} ({n:,}행)")
        print("  🚨 data/ 는 .gitignore 대상이다 (D-19) — 커밋되지 않는다. 이 스크립트가 원본이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
