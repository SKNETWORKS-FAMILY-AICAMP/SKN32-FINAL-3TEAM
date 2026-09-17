"""preprocess/guide_label.py — 해설서 위반문구 → 평가셋 (2판 · D-240 초안).

  uv run python -m preprocess.guide_label            # 센다
  uv run python -m preprocess.guide_label --dump     # data/derived/evalset_by_statute.jsonl
  uv run python -m preprocess.guide_label --anchors  # data/derived/guide_anchor_candidates.jsonl

🔴 **1판은 축이 틀렸다** (2026-09-17 정정).
   1판은 **내가 쓴 별표1 앵커**를 정본 축으로 삼았다. 결과가 라벨률 **127/1,834 = 6.9%** 이고
   나머지 1,707 행이 「애매(무근거)」로 떨어졌다. 그런데 원천은 **1,834 행 전부에 라벨을 갖고 있다**
   (`원천라벨` 결측 0 · 실측). 떨어진 것은 원천의 한계가 아니라 **내 앵커의 한계**였다.
   ★ 그래서 정본 축을 **원천라벨 3분류**로 되돌린다 — 라벨률 100%, 권위는 심의기구다.
   ⛔ 앵커는 `--anchors` 로 **갈라 낸다.** 평가셋이 아니다 (D-160 — 두 계수기를 섞지 않는다).
   ⛔ 앵커 오탐이 실측됐다 — `의약품_오인` 3건 중 **2건**이 오탐이다
      (「무**농약**」·「시간**절약**」이 `[가-힣]{2,}약(?![가-힣])` 에 걸린다).

🔴 **「폐지된 제도라 못 쓴다」는 철회한다** (2026-09-17 · D-240 초안).
   제도는 폐지되지 않았다 — **주체만 바뀌었다.** 우리 코퍼스 원문으로 확인한 것:
     · 시행규칙 제10조 심의 대상 1호 **특수영양식품**·2호 **특수의료용도식품** — 해설서의 품목 그대로
     · 법 제10조제1항 *「… **미리** 심의를 받아야 한다」* — 여전히 사전·여전히 의무
     · 법 제10조제2항제2호 **한국식품산업협회** — 해설서 시절 식약처가 위탁하던 그 기관
     · 법 제10조제3항 심의 기준은 *「제4조, 제4조의2, 제5조부터 **제8조**까지」* — 현행 8유형 그 자체
   🚨 헌재 2018.6.28. 2016헌가8·2017헌바476 의 위헌 대상은 **건강기능식품법 제18조제1항제6호**다.
      해설서의 근거인 구 **식품위생법 제12조의3** 은 위헌 대상이 아니라 **입법으로 이관**됐다.

★ 그래도 **배제 논거 하나가 남는다 — 판정 지위** (D-240 초안 · D-237).
   해설서 판정은 **심의 단계의 지적**이지 행정처분·판결로 확정된 위반이 아니다.
   그래서 레코드마다 `판정지위` 를 남긴다. 없으면 다음 사람이 확정 위반으로 읽는다.
   ⛔ 사례집·재결례·의결서(행정처분·재결·판결)와 **같은 통에 넣지 않는다** (D-160 · D-155).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

from preprocess.mfds_guide import CANDIDATES, REGIME

ROOT = pathlib.Path(__file__).resolve().parents[1]
NORM = ROOT / "data/derived/law_norm/013453_0001.jsonl"
SRC = ROOT / "data/derived/mfds_guide_labels.jsonl"
DST = ROOT / "data/derived/evalset_by_statute.jsonl"
DST_ANCHOR = ROOT / "data/derived/guide_anchor_candidates.jsonl"

#: 해설서 3분류 → 현행 **식품표시광고법 제8조제1항 각 호**. 출처 `[문헌]`.
#:   좌변은 해설서가 쓴 라벨 문자열, 우변은 `law_article.jsonl` 의 제8조 본문 어구다.
#: 🚨 이것은 「구법 조문 → 현행 조문」 대조가 **아니다.** 구 식품위생법 제13조 원문을 아직 못 읽었다
#:    (보유 법령 20종에 식품위생법이 없다 · law.go.kr / lawnb / bigcase 가 403·robots 로 막혔다).
#:    **「어구 대조」와 「조문 승계 확인」을 가른다** (D-188 — 안 본 것과 없는 것은 다르다).
LABEL_TO_ARTICLE8: dict[str, tuple[str, ...]] = {
    "질병의 예방 치료, 의약품 혼동, 건강기능식품 혼동": ("1", "2", "3"),
    "거짓ㆍ과장ㆍ기만": ("4", "5"),
    "부당한 비교ㆍ비방": ("6", "7"),
}

#: 제8조제1항 각 호 — 조문 본문 그대로. 별표1(제3조제1항 관련)이 덮는 것은 **제1~8호**다.
#: 🚨 제8호는 해설서에 **대응이 없다** — 식품표시광고법 제정 때 신설된 유형이다.
ARTICLE8_NAME: dict[str, str] = {
    "1": "질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려",
    "2": "식품등을 의약품으로 인식할 우려",
    "3": "건강기능식품이 아닌 것을 건강기능식품으로 인식할 우려",
    "4": "거짓ㆍ과장된 표시 또는 광고",
    "5": "소비자를 기만하는 표시 또는 광고",
    "6": "다른 업체나 다른 업체의 제품을 비방",
    "7": "객관적인 근거 없이 부당하게 비교",
    "8": "사행심 조장ㆍ음란한 표현",
}

#: 🚨 `[임의]` — 값 이름은 내가 지었다. **판정 경로에 있다** (평가셋 편입 여부를 가른다).
#:    제도의 성격 자체는 `[문헌]`(법 제10조 본문·식품저널 2019 칼럼)이고, 이름만 임의다.
#: 🚨 D-99 — 두 번째 원천이 이 값을 쓰게 되면 **여기서 공통 자리로 옮긴다.**
#:    지금은 해설서 하나뿐이라 여기 둔다. 옮길 때 `decc_extract.py`·`mfds_casebook.py` 를 같이 본다.
JUDGMENT_STATUS = "심의지적"

#: 🚨 「다만 … 제외한다」 — 이 단서를 든 노드의 **하위 목**이 적용 제외다 (D-238).
EXC = re.compile(r"다만[,\s].{0,80}?제외한다")

# ──────────────────────────────────────────────────────────────
# 아래는 **참고 앵커**다. `--anchors` 로만 나가고 평가셋에 들어가지 않는다.
# ⛔ 판정 근거로 인용하지 않는다 (D-240 초안 · D-100). 오탐이 실측됐다 — 위 docstring.
# ⛔ 제외 경로(`1.가.1` `1.가.2` `1.라.1` `1.라.2` `3.가`~`3.라`)는 **여기 없다** (D-238 · D-19).
# ──────────────────────────────────────────────────────────────

#: 조문 목 → 앵커 정규식. 출처는 전부 `[문헌]`(별표1 본문 어구).
#: 🔴 1판은 한 글자 앵커(`약`·`탕`)를 써서 의약품_오인 **69건이 전부 오탐**이었다
#:    (「약**사**」·「연**약**한」·「식**약**청」·「설**탕** 무첨가」). 2판은 `제` 접미어를 열어 둬
#:    「방부**제**」·「무항생**제**」 19건이 걸렸다. 3판도 「무농약」·「시간절약」을 잡는다.
#:    ★ 수는 매번 그럴듯했다 — 열어 보기 전에는 안 보인다 (D-191).
ANCHORS: dict[str, re.Pattern[str]] = {
    "1.가": re.compile(r"예방|방지"),
    "1.나": re.compile(r"치료|완치|낫게|고쳐|고친다"),
    "1.다": re.compile(r"증상|징후|통증|염증|가려움|붓기|설사|변비|불면"),
    "2.가": re.compile(
        r"[가-힣]{2,}약(?![가-힣])"
        r"|[가-힣]{2,}(?:유도제|억제제|안정제|개선제|소화제|이뇨제|진통제|해열제|수면제|치료제)"
        r"|경옥고|총명탕|공진단|쌍화탕|우황청심"
        r"|처방명|한약 ?처방"
    ),
    "2.나": re.compile(r"의약품에 ?포함|의약품 ?성분"),
    "2.다": re.compile(r"의약품을 ?대체|약을 ?대신|약 ?대신"),
    "2.라": re.compile(r"효능을 ?증대|약효를 ?높|치료 ?효과를 ?증대"),
    "3": re.compile(r"기능성|건강기능식품|인정받|도움을 ?줄 ?수 ?있|개선에 ?도움"),
    "4.나": re.compile(r"인정받지 ?않은 ?기능성|미인정 ?기능성"),
    "4.다": re.compile(r"사실과 ?다른|허위"),
    "4.라": re.compile(r"신체조직|기능[ㆍ·]작용|효능[ㆍ·]효과"),
    "4.마": re.compile(r"수상\(|인증|보증|선정되|특허"),
    "5.나": re.compile(r"원재료|성분의 ?효능|사료|첨가한 ?성분"),
    "5.다": re.compile(r"감사장|체험기|후기|한방\(|한방 ?요법|특수제법|주문쇄도|단체추천"),
    "5.마": re.compile(r"외국어|기술 ?제휴|외국 ?제품"),
    "5.바": re.compile(r"조제유류"),
    "5.사": re.compile(r"모유와 ?같|모유보다"),
    "5.차": re.compile(r"이온수|생명수|약수(?![가-힣])"),
    "5.카": re.compile(r"첨가물이 ?함유되지 ?않|무첨가"),
    "6": re.compile(r"비방|타사|다른 ?업체"),
    "7.가": re.compile(r"비교대상|비교기준"),
    "7.나": re.compile(r"사용하지 ?않은 ?성분|직접적인 ?관련이 ?적"),
    "8.가": re.compile(r"경품|사례품|사행심"),
    "8.나": re.compile(r"저속|음란|미풍양속"),
}

#: 🔴 **면책·의무 표기는 위반 근거가 아니다.** 「… 의약품이 **아닙니다**」는 법정 의무 표기다.
#:    🚨 이 목록은 `[임의]` 이고 **앵커 경로에만** 걸린다 — 평가셋 판정에는 안 닿는다.
_DISCLAIM = re.compile(
    r"아닙니다|아닌 |아니며|아니고|아니라|해당하지 ?않|목적이 ?아"
    r"|상담하|상담하여|전문의와|의사와 ?상담|섭취를 ?피|주의하|과민반응"
    r"|복용 ?중이|치료 ?중이|치료중인"
)

#: 목 번호 → 우리 유형 8종. 🚨 **앵커 경로 전용**이다.
#: 🚨 D-99 — `scripts/label_sheet.py` 의 `TYPES` 와 **집합이 다르다.**
#:    여기는 `사행심_음란`, 저기는 `후기_체험기_기만` 이 8번째다. 어느 쪽이 정본인지는 **미판정**이고
#:    `CANDIDATES`(원천 축)는 `후기_체험기_기만` 쪽을 쓴다. 합치는 것은 유형 체계 판정이라 사람 몫이다.
TYPE_OF = {
    "1": "질병_예방치료_표방",
    "2": "의약품_오인",
    "3": "건강기능식품_오인",
    "4": "거짓_과장",
    "5": "소비자_기만",
    "6": "비방광고",
    "7": "부당_비교광고",
    "8": "사행심_음란",
}


def excluded_paths(nodes: list[dict]) -> set[str]:
    """「다만 … 제외한다」를 든 노드의 하위 목. 🚨 손으로 적지 않는다 (D-238)."""
    body = [d for d in nodes if d["section"] == "본문"]
    parents = {d["path"] for d in body if EXC.search(d["text"].replace("\n", ""))}
    return {d["path"] for d in body if any(d["path"].startswith(p + ".") for p in parents)}


def anchor_label(text: str) -> list[tuple[str, str]]:
    """(근거조문 path, 앵커유형). ⛔ 참고용 — 평가셋 판정에 쓰지 않는다."""
    out: list[tuple[str, str]] = []
    disclaim = bool(_DISCLAIM.search(text))
    for path, rx in ANCHORS.items():
        if not rx.search(text):
            continue
        if disclaim and path[0] in ("1", "2"):
            continue
        out.append((path, TYPE_OF[path.split(".")[0]]))
    return out


def _gate_tables() -> None:
    """두 표가 갈리면 판정이 갈린다 — 먼저 멈춘다 (D-99)."""
    a, b = set(CANDIDATES), set(LABEL_TO_ARTICLE8)
    if a != b:
        raise SystemExit(
            f"🔴 `CANDIDATES`(preprocess/mfds_guide.py)와 `LABEL_TO_ARTICLE8` 의 키가 다르다.\n"
            f"  CANDIDATES 에만: {sorted(a - b)}\n"
            f"  LABEL_TO_ARTICLE8 에만: {sorted(b - a)}"
        )
    bad = sorted({h for hs in LABEL_TO_ARTICLE8.values() for h in hs} - set(ARTICLE8_NAME))
    if bad:
        raise SystemExit(f"🔴 `ARTICLE8_NAME` 에 없는 호를 가리킨다 — {bad}")


def build(viol: list[dict]) -> list[dict]:
    """위반문구 → 평가셋 행. 🚨 원천라벨이 없으면 **멈춘다** (fail-closed · D-72)."""
    missing = [r["문구"] for r in viol if not r.get("원천라벨")]
    if missing:
        raise SystemExit(
            f"🔴 `원천라벨` 이 없는 위반문구 {len(missing)}행 — 없음을 성공으로 세지 않는다 (D-72).\n"
            f"  첫 셋: {missing[:3]}"
        )
    unknown = sorted({r["원천라벨"] for r in viol} - set(LABEL_TO_ARTICLE8))
    if unknown:
        raise SystemExit(f"🔴 매핑에 없는 원천라벨 — {unknown} (D-139)")

    out = []
    for r in viol:
        lab = r["원천라벨"]
        out.append(
            {
                "문구": r["문구"],
                "원천라벨": lab,
                "제8조_호": list(LABEL_TO_ARTICLE8[lab]),
                # 🚨 `후보유형` 은 원천 축이다. 이름을 바꾸지 않는다 —
                #    `scripts/label_sheet.py` 가 이 칸을 읽어 사람 시트를 뽑는다 (D-99).
                "후보유형": list(CANDIDATES[lab]),
                "확정유형": [],  # 🔴 사람만 채운다 (D-66 · D-172)
                "판정": "원천3분류",
                "판정지위": JUDGMENT_STATUS,
                **REGIME,
                "표": r.get("표"),
                # 🚨 제1호 가목 단서(특수의료용도식품이면 제외)를 사람이 보려면 **제품유형이 있어야 한다**.
                #    옛 `mfds_guide_labels.jsonl` 에는 없다 — 추출기를 다시 돌리면 채워진다.
                "제품유형": r.get("제품유형") or "미상",
                "원천": r["원천"],
                "붙인이": "",
                "붙인날": "",
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="해설서 위반문구 → 평가셋(원천라벨 축)")
    ap.add_argument("--dump", action="store_true", help="evalset_by_statute.jsonl 을 쓴다")
    ap.add_argument(
        "--anchors",
        action="store_true",
        help="참고 앵커를 guide_anchor_candidates.jsonl 로 따로 쓴다 — 평가셋이 아니다",
    )
    args = ap.parse_args()

    _gate_tables()

    rows = [json.loads(x) for x in SRC.read_text(encoding="utf-8").splitlines() if x.strip()]
    viol = [r for r in rows if r.get("블록") == "삭제"]
    out = build(viol)

    print(f"  위반문구 {len(viol):,}행 · 원천라벨 결측 0 (fail-closed 통과)")
    by = collections.Counter(r["원천라벨"] for r in out)
    print("  원천라벨별 — 🚨 확정유형은 비어 있다 (D-66 · D-172)")
    for k, v in by.most_common():
        hos = "·".join(f"제{h}호" for h in LABEL_TO_ARTICLE8[k])
        print(f"    {v:>5,}  {k}  → {hos}")
    covered = {h for hs in LABEL_TO_ARTICLE8.values() for h in hs}
    rest = sorted(set(ARTICLE8_NAME) - covered)
    print(f"  제8조 덮은 호 {len(covered)}/8 — 미포함 {rest}: {[ARTICLE8_NAME[h] for h in rest]}")
    print(f"  🚨 판정지위 = {JUDGMENT_STATUS!r} — 행정처분·판결 확정이 아니다 (D-240 초안)")
    unknown = sum(1 for r in out if r["제품유형"] == "미상")
    if unknown:
        print(
            f"  🔴 제품유형이 「미상」인 행 {unknown:,} — 제1호 가목 단서(특수의료용도식품 제외)를 볼 수 없다.\n"
            "     고치는 법: uv run python launcher.py extract mfds_special_use_guide --dump\n"
            "     ⛔ `--sheet` 는 주지 않는다 — 라벨링 중에 표본이 갈린다 (지시서 09-10 §5)."
        )
    else:
        by = collections.Counter(r["제품유형"] for r in out)
        print("  제품유형별 —")
        for k, v in by.most_common():
            print(f"    {v:>5,}  {k}")

    if args.dump:
        with DST.open("w", encoding="utf-8", newline="\n") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  💾 {len(out):,}행 → {DST.relative_to(ROOT)}")

    if args.anchors:
        nodes = [json.loads(x) for x in NORM.read_text(encoding="utf-8").splitlines() if x.strip()]
        exc = excluded_paths(nodes)
        bad = sorted(exc & set(ANCHORS))
        if bad:
            raise SystemExit(f"🔴 적용 제외 경로가 앵커 표에 있다 — {bad} (D-238 ①)")
        anc, stat = [], collections.Counter()
        for r in viol:
            hits = anchor_label(r["문구"])
            types = sorted({t for _, t in hits})
            cand = set(r.get("후보유형") or [])
            stat["앵커걸림" if hits else "앵커없음"] += 1
            anc.append(
                {
                    "문구": r["문구"],
                    "근거조문": [p for p, _ in hits],
                    "앵커유형": types,
                    "후보유형": sorted(cand),
                    "후보밖": sorted(set(types) - cand) if cand else [],
                }
            )
        with DST_ANCHOR.open("w", encoding="utf-8", newline="\n") as f:
            for r in anc:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        t = collections.Counter(x for r in anc for x in r["앵커유형"])
        print(f"\n  ⛔ 참고 앵커 — 평가셋이 아니다 (D-160). 적용 제외 경로 {len(exc)}개 제외 확인")
        for k, v in stat.most_common():
            print(f"    {k:10} {v:>5,}")
        for k, v in t.most_common():
            print(f"    {k:22} {v:>5,}")
        print(f"  💾 {len(anc):,}행 → {DST_ANCHOR.relative_to(ROOT)}")
        print("  🚨 `의약품_오인` 은 3건 중 2건이 오탐이다 — 수를 그대로 인용하지 않는다 (D-191).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
