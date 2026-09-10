"""preprocess/inject.py — [P10] **결함 주입** · 규칙이 곧 라벨 (D-74).

  uv run python -m preprocess.inject            # 무엇이 만들어지는지 본다
  uv run python -m preprocess.inject --dump     # data/derived/injected_golden.jsonl

──────────────────────────────────────────────────────────────
★ **라벨을 사람도 모델도 붙이지 않는다 — 규칙이 붙인다.**

    적법 「스트레스로 인한 긴장완화에 도움을 줄 수 있음」   (2층 · 인정받은 문구)
      ↓ T1 완화구 삭제
    위법 「스트레스로 인한 긴장완화」                      라벨 = T1 → 거짓_과장

**변형을 만든 규칙이 곧 정답이다.** 라벨 오류가 0 이고 사람 시간이 0 이다.
🚨 그래서 **규칙이 법과 맞는지**가 이 파일의 전부다 — 규칙이 틀리면 라벨이 조용히 전부 틀린다.

──────────────────────────────────────────────────────────────
🔴 **주입본은 `test_holdout` 에 넣지 않는다** ([P10] 규약 5 · `split.py` 게이트)

합성으로 평가하면 「규칙을 배웠는가」를 재게 된다. 평가는 **실사례**로만 한다.
모든 행에 `split: "train"` 을 박는다.

🚨 **원본도 함께 넣는다** ([P10] 규약 3). 안 넣으면 골든셋이 전부 위법이라
   「전부 위법」이라고 답해도 100% 가 된다 (기획서 5-3 클래스 불균형).

🔴 **분할을 먼저 읽는다** (2026-09-09 저녁). 승인 문구 일부가 **음성 평가 표본**으로
   봉인돼 있다. 그것으로 주입을 만들면 **시험지 문장이 학습에 들어간다.**
   🚨 `split_manifest.json` 이 없으면 멈춘다 — 「없으면 전량으로」는 누수로 가는 길이다.

★ **이것이 지금 평가가 비어 있는 유형의 유일한 학습 경로다** —
  `후기_체험기_기만`(평가 0) · `부당_비교광고`(3) · `비방광고`(6) 는
  실사례가 없어서 라벨링으로 못 채운다. T6·T7 이 그 자리를 만든다.
  ⛔ **학습만 채운다. 평가는 여전히 비어 있다** — 그것을 메우는 척하지 않는다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import re

from preprocess import split as split_mod
from preprocess.split import approved_docs as split_approved

HF = pathlib.Path("data/derived/mfds_hf_labels.jsonl")
SPLIT = pathlib.Path("data/derived/golden/split_manifest.json")
OUT = pathlib.Path("data/derived/injected_golden.jsonl")

#: 완곡 표현 — 적법과 위법을 가르는 바로 그 조각이다 (D-156 실측).
HEDGE = re.compile(r"\s*에?\s*도움을\s*줄\s*수\s*있음\s*")
#: 인정 시기 꼬리표 — 문구가 아니라 메타다. 변형 전에 뗀다.
TAIL = re.compile(r"\s*\(\s*'?\d{2,4}\s*년\s*\d{1,2}\s*월\s*인정\s*\)\s*")

#: T4 의약품 어휘 · T5 최상급 — 🚨 **삽입 어휘는 실측 원천에서 가져온다.**
#:    내가 지어낸 낱말로 만들면 모델이 「내 말버릇」을 배운다.
DRUG_WORDS = ("치료제", "특효", "처방", "의약품 대체")
SUPERLATIVE = ("100%", "완치", "유일한", "국내 최초", "부작용 없는")
#: 🔴 **핵심 주장은 언제나 명사구다** — 「갱년기 남성의 건강」·「긴장완화」.
#:    ⛔ 처음에 동사 틀(「먹고 {}았어요」)에 넣었더니 **「갱년기 남성의 건강았어요」**가 나왔다.
#:       비문으로 학습시키면 모델이 「위반 = 비문」이라고 배운다 — 없느니만 못하다.
#:    ★ 그래서 모든 틀에서 핵심 주장을 **명사 자리에만** 넣는다.
#: T6 후기·체험기 — 대가성 표시가 없는 형태 (식품표시광고법 제8조제1항제5호)
REVIEW_FRAMES = (
    "{핵}, 3개월 먹고 확실히 느꼈어요",
    "{핵} 후기 폭발 — 저도 효과 봤습니다",
    "{핵}에 반신반의했는데 지금은 매일 챙겨 먹어요",
    "직접 써 보니 {핵}은 확실합니다, 강력 추천드려요",
    "{핵} 때문에 인생이 바뀌었다는 체험 후기가 이어집니다",
)
#: T7a 부당 비교 — 제3호. 🚨 비교 대상과 근거 없이 우위를 말하는 형태.
COMPARE_FRAMES = (
    "타사 제품보다 2배 빠른 {핵}",
    "경쟁 제품과 비교 불가한 {핵}",
    "동종 제품 중 {핵} 1위",
)
#: T7b 비방 — 제4호. 🚨 경쟁 제품을 깎아 자기 우위를 만드는 형태.
SLANDER_FRAMES = (
    "경쟁사 제품에는 없는 {핵}",
    "시중 제품은 {핵} 효과가 전혀 없습니다",
    "다른 브랜드에 속지 마세요 — 진짜 {핵}은 여기뿐입니다",
)


def core(text: str) -> str:
    """완곡구를 뗀 **핵심 주장**. 「긴장완화에 도움을 줄 수 있음」 → 「긴장완화」."""
    return HEDGE.sub("", text).strip(" ,.")


#: 규칙표. 🚨 **(id, 설명, 라벨, 근거조문)** 이 한 줄에 있어야 규칙과 법이 안 갈린다.
#: T1 단정 — 🚨 완화구를 **떼기만 하면** 명사구가 남아 광고 문장이 아니다.
#:    ⛔ 「갱년기 남성의 건강」은 위반이라기보다 조각이다. 법이 겨냥하는 것은
#:       **단정적으로 말하는 것**이므로 단정 서술을 붙여 문장으로 만든다.
ASSERT_FRAMES = (
    "{핵}에 확실한 효과가 있습니다",
    "{핵}을 개선해 줍니다",
    "{핵}, 먹으면 바로 좋아집니다",
)

RULES: tuple[tuple[str, str, str, str], ...] = (
    ("T1", "완화구 삭제 — 단정 표현으로", "거짓_과장", "식품표시광고법 제8조제1항제4호"),
    ("T2", "기능성 → 질병명 치환", "질병_예방치료_표방", "식품표시광고법 제8조제1항제1호"),
    ("T4", "의약품 어휘 삽입", "의약품_오인", "식품표시광고법 제8조제1항제2호"),
    ("T5", "최상급·절대 표현 삽입", "거짓_과장", "식품표시광고법 제8조제1항제4호"),
    (
        "T6",
        "후기·체험기 형식 + 대가성 미표시",
        "후기_체험기_기만",
        "식품표시광고법 제8조제1항제5호",
    ),
    ("T7a", "경쟁사 부당 비교", "부당_비교광고", "표시광고법 제3조제1항제3호"),
    ("T7b", "경쟁사 비방", "비방광고", "표시광고법 제3조제1항제4호"),
)


def disease_terms() -> list[str]:
    """T2 가 넣을 질병어. 🚨 **사전에서 가져온다 — 내가 고르지 않는다** ([P6] · D-158)."""
    p = pathlib.Path("data/derived/banned_terms.jsonl")
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 가 없다 —\n  먼저: uv run python -m preprocess.dictionary --dump"
        )
    got = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["유형"] == ["질병_예방치료_표방"] and 2 <= len(r["term"]) <= 8:
            # ⛔ 사전 항목이 이미 「소아비만예방」처럼 **동작어를 달고** 온다.
            #    그대로 틀에 넣으면 「소아비만예방 예방·치료에」가 된다 — 떼고 넣는다.
            got.append(re.sub(r"(예방|치료|개선|방지|관리|완화)+$", "", r["term"]))
    return sorted({x for x in got if len(x) >= 2})


def transform(text: str, rnd: random.Random, diseases: list[str]) -> list[dict]:
    """한 적법 문구에서 나오는 위법 변형들. 🚨 **1문장당 1규칙** ([P10] 규약 1)."""
    out: list[dict] = []
    c = core(text)
    if not c or c == text:
        return out  # 완화구가 없으면 이 원천의 적법 문구가 아니다

    def add(rule: str, made: str) -> None:
        rid = {r[0]: r for r in RULES}[rule]
        out.append(
            {
                "문구": made,
                "라벨": [rid[2]],
                "rule_id": rule,
                "규칙": rid[1],
                "근거": rid[3],
                "원본": text,
                # 🚨 변형 전/후 오프셋 대신 **핵심 주장**을 남긴다 ([P10] 규약 2 의 취지) —
                #    주장 스팬을 나중에 이걸로 되짚는다.
                "핵심주장": c,
                "origin": "injected",
                "split": "train",  # 🔴 규약 5 — 평가에 넣지 않는다
                "provenance": "mfds_hf_ingredient_board",
                "redistributable": True,
            }
        )

    add("T1", rnd.choice(ASSERT_FRAMES).format(핵=c))
    add("T5", f"{rnd.choice(SUPERLATIVE)} {c}")
    add("T4", f"{c}, {rnd.choice(DRUG_WORDS)} 수준의 효과")
    add("T6", rnd.choice(REVIEW_FRAMES).format(핵=c))
    add("T7a", rnd.choice(COMPARE_FRAMES).format(핵=c))
    add("T7b", rnd.choice(SLANDER_FRAMES).format(핵=c))
    if diseases:
        add("T2", f"{rnd.choice(diseases)} 예방·치료에 효과적인 {c}")
    return out


def build(seed: int = 20260909) -> tuple[list[dict], dict]:
    if not HF.exists():
        raise FileNotFoundError(
            f"{HF} 가 없다 —\n  먼저: uv run python launcher.py extract mfds_hf_ingredient_board --dump"
        )
    if not SPLIT.exists():
        raise FileNotFoundError(
            f"{SPLIT} 가 없다 — **분할이 먼저다** (D-171).\n"
            "  먼저: uv run python -m preprocess.split --write\n"
            "  🚨 봉인된 음성 평가 표본으로 주입을 만들면 시험지가 학습에 들어간다."
        )
    _m = json.loads(SPLIT.read_text(encoding="utf-8"))
    split_mod.verify_inputs(_m, who="주입[P10]")  # 🔴 D-176
    assign = _m["assign"]
    rnd = random.Random(seed)
    diseases = disease_terms()
    rows: list[dict] = []
    stat: dict = {"원본": 0, "적법": 0, "규칙별": collections.Counter(), "봉인제외": 0}

    # 🔴 **`doc_id` 를 만드는 곳은 한 곳뿐이다** (D-99). 처음에 여기서 따로 만들었더니
    #    `split` 은 원본 줄 번호로, 여기는 **거른 뒤의 번호**로 매겨져 어긋났다 —
    #    봉인 60개를 빼려다 449개를 뺐다. 바로 위 주석에 「같은 규칙이어야 한다」고
    #    적어 놓고 그 줄에서 어겼다. 이제 `split.approved_docs()` 를 그대로 쓴다.
    for d in split_approved():
        text = d["문구"][0]
        if assign.get(d["doc_id"]) != "train":
            stat["봉인제외"] += 1
            continue
        stat["원본"] += 1
        # 🚨 규약 3 — 원본을 **적법(V0)** 으로 함께 넣는다
        rows.append(
            {
                # 🔴 **어느 원본에서 나왔는지 실어 보낸다** (2026-09-10).
                #    ⛔ 없으면 물질화가 id 를 문구로 만들 수밖에 없는데, 정규화하면
                #       「피부 보습에…」와 「피부보습에…」가 같은 문자열이 돼 **56쌍이 겹쳤다**.
                #    ★ 원본 doc_id 는 분할과 같은 키이므로 추적도 된다 (D-99).
                "src": d["doc_id"],
                "문구": text,
                "라벨": [],
                "rule_id": "V0",
                "규칙": "원본 — 인정받은 적법 문구",
                "근거": "건강기능식품 기능성 원료 인정",
                "원본": text,
                "핵심주장": core(text),
                "origin": "approved",
                "split": "train",
                "provenance": "mfds_hf_ingredient_board",
                "redistributable": True,
            }
        )
        stat["적법"] += 1
        for made in transform(text, rnd, diseases):
            made["src"] = d["doc_id"]
            rows.append(made)
            stat["규칙별"][made["rule_id"]] += 1
    return rows, stat


def main() -> int:
    ap = argparse.ArgumentParser(description="[P10] 결함 주입 — 규칙이 곧 라벨")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    ap.add_argument("--seed", type=int, default=20260909, help="재현 조건 (D-54)")
    a = ap.parse_args()

    rows, stat = build(a.seed)
    inj = sum(stat["규칙별"].values())
    print(f"주입 골든셋 **{len(rows):,}건** — 적법 {stat['적법']:,} · 위법 {inj:,}")
    print(f"  원본 적법 문구 {stat['원본']:,}종에서 나왔다 (중복 제거 후)")
    print(
        f"  🔴 음성 평가로 **봉인돼 제외한 문구 {stat['봉인제외']}개** — 시험지가 학습에 안 들어가게"
    )

    print("\n  규칙별 —")
    for rid, desc, lab, _art in RULES:
        n = stat["규칙별"].get(rid, 0)
        mark = "✅" if n >= 30 else "🔴 30 미만"
        print(f"    {rid:4} {n:>5}  {lab:16} {desc}   {mark}")

    by = collections.Counter(t for r in rows for t in r["라벨"])
    print("\n  라벨별 (D-40 · 유형당 30) —")
    for k, v in by.most_common():
        print(f"    {v:>5}  {k}  {'✅' if v >= 30 else '🔴'}")
    print(f"    {stat['적법']:>5}  (적법 · V0)")

    # 🔴 **틀 다양성** — 합성의 가장 큰 함정이다. 틀이 적으면 모델이 위반이 아니라
    #    **틀을 배운다.** 그러면 골든셋 F1 은 높은데 실사례에서 무너진다.
    print("\n  🔴 **틀 다양성** — 낮으면 모델이 위반이 아니라 틀을 배운다")
    frames = collections.defaultdict(set)
    for r in rows:
        if r["rule_id"] == "V0":
            continue
        # 핵심 주장을 빼면 남는 것이 틀이다
        frames[r["rule_id"]].add(r["문구"].replace(r["핵심주장"], "{}"))
    for rid, _d, _l, _a in RULES:
        n, f = stat["규칙별"].get(rid, 0), len(frames.get(rid, ()))
        ratio = f * 100 // n if n else 0
        mark = "✅" if ratio >= 50 else ("🟡" if f > 3 else "🔴 틀에 갇혔다")
        print(f"    {rid:4} {n:>5}건 / 고유 틀 {f:>4}종 ({ratio:>3}%)   {mark}")
    print("     🚨 T6·T7 은 고정 문장이라 **한 자릿수 틀**이다. 이대로 학습에 넣으면")
    print("        「타사 제품보다」라는 말버릇을 배우지 위반을 배우지 않는다.")
    print("     ⬜ **틀을 늘리는 것이 다음 작업이다** — 실사례(ftc 의결서 근거절)에서")
    print("        표현을 뽑아 채운다. 지금은 그 한계를 적어 두고 쓴다.")

    print("\n  ⬜ **T3(제품유형 오인)은 아직 없다** — `건강기능식품_오인` 이 주입에서 0 이다.")
    print("     일반식품 문구가 있어야 만드는데 2층은 인정 원료뿐이다. 실사례로만 채운다.")

    print("\n  표본 —")
    for rid in ("T1", "T2", "T4", "T5", "T6", "T7a", "T7b"):
        s = next((r for r in rows if r["rule_id"] == rid), None)
        if s:
            print(f"    [{rid} → {s['라벨'][0]}] {s['문구'][:70]}")

    print("\n  🔴 **전부 `split: train` 이다** — 평가에 넣지 않는다 ([P10] 규약 5).")
    print("     합성으로 평가하면 「규칙을 배웠는가」를 재게 된다.")
    print("  🚨 학습만 채운다 — `후기_체험기_기만`·`부당_비교광고`·`비방광고` 의")
    print("     **평가는 여전히 비어 있다.** 메우는 척하지 않는다.")

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n  → {OUT}  ({len(rows):,}줄)")
    else:
        print(f"\n  ⬜ 쓰지 않았다 — `--dump` 를 붙이면 {OUT} 에 쓴다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
