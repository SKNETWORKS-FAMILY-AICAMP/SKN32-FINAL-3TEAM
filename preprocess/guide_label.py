"""preprocess/guide_label.py — 위반문구 → 별표1 근거 조문 (초안 1판 · D-238).

  uv run python -m preprocess.guide_label            # 센다
  uv run python -m preprocess.guide_label --dump     # data/derived/evalset_by_statute.jsonl

🔴 **왜 있는가 — 「다만 … 제외한다」를 위반 근거로 55건 인용했다** (2026-09-17).
   제3호는 본문이 위반이고 가~라목은 **적용 제외**다. 가~라목에 해당하면 **위반이 아니다.**
   그런데 라벨에 「제3호 나목」처럼 적혀 있으면 **조문 번호가 정확해서 그럴듯하다.**
   틀린 것은 번호가 아니라 그 번호가 **위반을 뜻하는지 제외를 뜻하는지**다.

★ 그래서 **제외 경로는 앵커 표에 아예 넣지 않는다.** 없는 것은 인용할 수 없다 (D-19 「위치가 곧 게이트」).
🚨 제외 경로는 `law_norm` 에서 **기계가 뽑는다** — 손으로 적지 않는다 (D-238).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
NORM = ROOT / "data/derived/law_norm/013453_0001.jsonl"
SRC = ROOT / "data/derived/mfds_guide_labels.jsonl"

#: 🚨 「다만 … 제외한다」 — 이 단서를 든 노드의 **하위 목**이 적용 제외다.
EXC = re.compile(r"다만[,\s].{0,80}?제외한다")

#: 조문 목 → 앵커 **정규식**. 🚨 출처는 전부 **[문헌]** (별표1 본문 어구)이고 `[임의]` 가 없다.
#: ⛔ 제외 경로(`1.가.1` `1.가.2` `1.라.1` `1.라.2` `3.가`~`3.라`)는 **여기 없다.**
#:
#: 🔴 **1판은 한 글자 앵커를 썼다가 통째로 틀렸다** (2026-09-17 실측).
#:    `2.가` 를 `("약", "탕", "환", "고", …)` 로 두니 **69건이 전부 오탐**이었다 —
#:      「소아과 전문의, 약**사**」 · 「**연약**한 아기 장에」 · 「미국 식**약**청 FDA」
#:      · 「설**탕** 무첨가」  ← 설탕이 한약 처방명으로 세어졌다
#:    ★ **수는 그럴듯했다**(의약품_오인 69 → D-40 통과로 보였다). 열어 보기 전에는 안 보인다 (D-191).
#: ★ 그래서 **경계를 요구하는 정규식**으로 바꾼다 — 낱말 끝이 한글이면 앵커가 아니다.
ANCHORS: dict[str, re.Pattern[str]] = {
    # 1호 질병 예방·치료
    "1.가": re.compile(r"예방|방지"),
    "1.나": re.compile(r"치료|완치|낫게|고쳐|고친다"),
    "1.다": re.compile(r"증상|징후|통증|염증|가려움|붓기|설사|변비|불면"),
    # 2호 의약품 오인 — 🔴 **낱말 끝을 요구한다.** 「약사」·「연약한」·「식약청」이 안 걸린다
    # 🔴 **2판도 틀렸다** — `제` 접미어를 열어 두니 「방부**제** 무첨가」·「무항생**제**」·
    #    「항생**제** 3중 관리」가 걸렸다(19건). 그건 **식품첨가물·원료** 얘기지 의약품 명칭이 아니다.
    #    ★ 3판은 **의약품 제형 접미어를 명시**한다. 열어 두지 않는다.
    "2.가": re.compile(
        r"[가-힣]{2,}약(?![가-힣])"  # 탈모약 · 다이어트약 · 변비약
        r"|[가-힣]{2,}(?:유도제|억제제|안정제|개선제|소화제|이뇨제|진통제|해열제|수면제|치료제)"
        r"|경옥고|총명탕|공진단|쌍화탕|우황청심"  # 한약 처방명 (고유명사)
        r"|처방명|한약 ?처방"
    ),
    "2.나": re.compile(r"의약품에 ?포함|의약품 ?성분"),
    "2.다": re.compile(r"의약품을 ?대체|약을 ?대신|약 ?대신"),
    "2.라": re.compile(r"효능을 ?증대|약효를 ?높|치료 ?효과를 ?증대"),
    # 3호 건기식 오인 — 🔴 **본문뿐이다.** 가~라목은 전부 적용 제외다
    "3": re.compile(r"기능성|건강기능식품|인정받|도움을 ?줄 ?수 ?있|개선에 ?도움"),
    # 4호 거짓·과장
    "4.나": re.compile(r"인정받지 ?않은 ?기능성|미인정 ?기능성"),
    "4.다": re.compile(r"사실과 ?다른|허위"),
    "4.라": re.compile(r"신체조직|기능[ㆍ·]작용|효능[ㆍ·]효과"),
    "4.마": re.compile(r"수상\(|인증|보증|선정되|특허"),
    # 5호 소비자 기만
    "5.나": re.compile(r"원재료|성분의 ?효능|사료|첨가한 ?성분"),
    "5.다": re.compile(r"감사장|체험기|후기|한방\(|한방 ?요법|특수제법|주문쇄도|단체추천"),
    "5.마": re.compile(r"외국어|기술 ?제휴|외국 ?제품"),
    "5.바": re.compile(r"조제유류"),
    "5.사": re.compile(r"모유와 ?같|모유보다"),
    "5.차": re.compile(r"이온수|생명수|약수(?![가-힣])"),
    "5.카": re.compile(r"첨가물이 ?함유되지 ?않|무첨가"),
    # 6·7·8호
    "6": re.compile(r"비방|타사|다른 ?업체"),
    "7.가": re.compile(r"비교대상|비교기준"),
    "7.나": re.compile(r"사용하지 ?않은 ?성분|직접적인 ?관련이 ?적"),
    "8.가": re.compile(r"경품|사례품|사행심"),
    "8.나": re.compile(r"저속|음란|미풍양속"),
}

#: 🔴 **면책·의무 표기는 위반 근거가 아니다** (2026-09-17 실측).
#:    「본 제품은 질병의 예방과 치료를 위한 **의약품이 아닙니다**」가 1호 나목(치료)으로 걸렸다.
#:    이건 건강기능식품이 **법으로 달아야 하는 문구**다 — 위반의 정반대다.
#:    ⛔ 부정을 안 보면 **적법 의무 표기가 위반 표본으로 들어간다.** 평가셋이 통째로 오염된다.
#:    🚨 1호·2호(질병·의약품)에만 건다 — 다른 호는 부정문이 위반일 수 있다.
#:    🔄 2차 — 「치료중인 분은 **전문의와 상담**하여 주십시오」·「과민반응이 나타날 수 있으므로」도
#:    같은 자리다. **주의·상담 안내**는 위반이 아니라 오히려 달아야 하는 문구다.
_DISCLAIM = re.compile(
    r"아닙니다|아닌 |아니며|아니고|아니라|해당하지 ?않|목적이 ?아"
    r"|상담하|상담하여|전문의와|의사와 ?상담|섭취를 ?피|주의하|과민반응"
    r"|복용 ?중이|치료 ?중이|치료중인"
)

#: 목 → 우리 유형 8종
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


def label(text: str) -> list[tuple[str, str]]:
    """(근거조문 path, 제안유형). 🚨 하나가 아니다 — 한 문구가 여러 목에 걸린다."""
    out: list[tuple[str, str]] = []
    disclaim = bool(_DISCLAIM.search(text))
    for path, rx in ANCHORS.items():
        if not rx.search(text):
            continue
        # 🔴 면책·의무 표기를 질병·의약품 위반으로 세지 않는다
        if disclaim and path[0] in ("1", "2"):
            continue
        out.append((path, TYPE_OF[path.split(".")[0]]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="위반문구 → 별표1 근거 조문")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    nodes = [json.loads(x) for x in NORM.read_text(encoding="utf-8").splitlines() if x.strip()]
    exc = excluded_paths(nodes)

    # 🔴 게이트 ① — 제외 경로가 앵커 표에 있으면 멈춘다. 없는 것은 인용할 수 없다.
    bad = sorted(exc & set(ANCHORS))
    if bad:
        raise SystemExit(f"🔴 적용 제외 경로가 앵커 표에 있다 — {bad} (D-238 ①)")

    rows = [json.loads(x) for x in SRC.read_text(encoding="utf-8").splitlines() if x.strip()]
    viol = [r for r in rows if r.get("블록") == "삭제"]

    out, stat = [], collections.Counter()
    for r in viol:
        hits = label(r["문구"])
        paths = [p for p, _ in hits]
        types = sorted({t for _, t in hits})
        cand = set(r.get("후보유형") or [])
        # 🚨 게이트 ③ — 후보 밖이면 조용히 통과시키지 않는다
        outside = sorted(set(types) - cand) if cand else []
        kind = "애매(무근거)" if not hits else "명확(단일)" if len(types) == 1 else "명확(복수)"
        stat[kind] += 1
        if outside:
            stat["후보밖"] += 1
        out.append(
            {
                "문구": r["문구"],
                "근거조문": paths,
                "제안유형": types,
                "후보유형": sorted(cand),
                "후보밖": outside,
                "판정": kind,
                "확정유형": [],
                "원천": r["원천"],
                "연도": r.get("연도"),
                "붙인이": "",
                "붙인날": "",
            }
        )

    print(f"  위반문구 {len(viol):,}행")
    print(f"  적용 제외 경로 {len(exc)} — {sorted(exc)}")
    for k, v in stat.most_common():
        print(f"    {k:14} {v:>5,}")
    t = collections.Counter()
    for r in out:
        for x in r["제안유형"]:
            t[x] += 1
    print("  제안유형별 —")
    for k, v in t.most_common():
        print(f"    {k:22} {v:>5,}  {'✅' if v >= 30 else '❌'}")

    if args.dump:
        dst = ROOT / "data/derived/evalset_by_statute.jsonl"
        with dst.open("w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  💾 {len(out):,}행 → {dst.relative_to(ROOT)}")
        print("  🚨 확정유형은 비어 있다 — 사람이 채운다 (D-66 · D-172).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
