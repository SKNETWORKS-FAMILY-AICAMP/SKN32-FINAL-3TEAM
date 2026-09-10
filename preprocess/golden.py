"""preprocess/golden.py — 골든셋 **물질화** (D-143 · 수집전처리_기획 4-6).

  uv run python -m preprocess.golden            # 무엇이 들어가는지 본다
  uv run python -m preprocess.golden --dump     # data/derived/golden/golden.jsonl

──────────────────────────────────────────────────────────────
🚨 **분할은 「어느 문서가 어디로」만 정한다.** 실제 문장과 라벨이 한 파일에 없으면
   학습도 평가도 못 돌린다. 단계가 물질화되지 않으면 다음 단계가 그것을 못 쓴다 (D-143).

스키마 (수집전처리_기획 4-6)

    {"id":…, "text":…, "labels":[…], "unit":"문장|낱말",
     "origin":"real|injected|approved", "provenance":…, "redistributable":…,
     "split":"train|test_sentence"}

🔴 **`labels` 가 빈 리스트인 행은 적법이다** — 없는 것이 라벨이다. 지우지 않는다.
   그것이 없으면 「전부 위반」이라 답해도 Recall 100% 가 된다.

🚨 **문서 라벨을 문구에 전파한다.** 의결서 한 건에 문구가 여럿이면 모두 같은 라벨을 받는다.
   다중 라벨 문서는 `split.py` 가 평가에서 이미 뺐다 — 학습에만 이 잡음이 남는다.

🔴 **문서를 갈라도 문구는 겹친다** (2026-09-09 실측 8건).
   「글루코사민 100%」·「1+1 행사」 같은 표현이 **서로 다른 의결서에 각각 인용**된다.
   문서 단위 분할은 그것을 못 막는다 — 그래서 여기서 **문구 단위로 한 겹 더 거른다.**
   ★ **평가는 안 본 것이어야 한다.** train 에 같은 문구가 있으면 평가에서 뺀다.
   ⛔ 반대로 하지 않는다 — train 에서 빼면 학습이 줄고, 그 문구는 어차피 평가에서
      무의미하다(외운 것을 맞힌다).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

from preprocess import split as split_mod
from preprocess.dictionary import norm
from preprocess.split import approved_docs, casebook_docs, ftc_docs

SPLIT = pathlib.Path("data/derived/golden/split_manifest.json")
INJECTED = pathlib.Path("data/derived/injected_golden.jsonl")
OUT = pathlib.Path("data/derived/golden/golden.jsonl")


def build() -> tuple[list[dict], dict]:
    if not SPLIT.exists():
        raise FileNotFoundError(
            f"{SPLIT} 가 없다 —\n  먼저: uv run python -m preprocess.split --write"
        )
    _m = json.loads(SPLIT.read_text(encoding="utf-8"))
    split_mod.verify_inputs(_m, who="물질화")  # 🔴 D-176
    assign = _m["assign"]
    rows: list[dict] = []
    stat: dict = collections.Counter()

    for d in ftc_docs() + casebook_docs() + approved_docs():
        split = assign.get(d["doc_id"])
        if not split:
            stat["미배정"] += 1
            continue
        for k, text in enumerate(d["문구"]):
            rows.append(
                {
                    "id": f"{d['doc_id']}#{k}",
                    "text": text,
                    "labels": d["유형"],
                    "unit": d["단위"],
                    "origin": "approved" if not d["유형"] else "real",
                    "provenance": d["원천"],
                    "redistributable": True,
                    "split": split,
                }
            )
            stat[split] += 1

    # 🔴 **주입본이 없으면 멈춘다** (2026-09-10 · D-72 fail-closed).
    #    ⛔ 종전에는 `if INJECTED.exists():` 라 없으면 아무 말 없이 건너뛰고
    #       1,015행짜리 골든셋을 **성공으로 찍고 파일까지 썼다.** `stat["주입"]` 이 0 이라
    #       출력에도 안 나온다 — 「행이 줄었는데 초록불」의 전형이다 (D-149).
    if not INJECTED.exists():
        raise SystemExit(
            f"🔴 {INJECTED} 가 없다 — 주입 없이 물질화하면 학습 라벨이 통째로 빠진다.\n"
            "  먼저: uv run python -m preprocess.inject --dump\n"
            "  (순서 전체는 uv run python launcher.py golden --write)"
        )
    for line in INJECTED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        # 🚨 id 를 **앞 단계 행 수**에 매달지 않는다 (2026-09-10).
        #    ⛔ `len(rows)` 였다 — 실사례가 한 줄만 늘어도 주입 행 id 가 전부 밀려
        #       다른 배치와 대조가 불가능해진다.
        #    ⛔ 그래서 문구로 만들었더니, 정규화가 「피부 보습에…」와 「피부보습에…」를
        #       접어 **56쌍이 겹쳤다** — 게이트가 그 자리에서 잡았다.
        #    ★ 원본 doc_id 로 만든다. 분할과 같은 키라 추적도 된다 (D-99).
        if "src" not in r:
            raise SystemExit(
                "🔴 주입본에 `src`(원본 doc_id)가 없다 — 낡은 산출물이다.\n"
                "  먼저: uv run python -m preprocess.inject --dump"
            )
        rows.append(
            {
                "id": f"inj:{r['rule_id']}:{r['src']}",
                "text": r["문구"],
                "labels": r["라벨"],
                "unit": "문장",
                "origin": r["origin"],
                "provenance": r["provenance"],
                "redistributable": r["redistributable"],
                "split": "train",  # 🔴 [P10] 규약 5 — 주입본은 평가에 안 넣는다
                "rule_id": r["rule_id"],
            }
        )
        stat["train"] += 1
        stat["주입"] += 1

    # 🔴 문구 단위 2차 필터 — 평가는 **안 본 것**이어야 한다
    train_text = {norm(r["text"]) for r in rows if r["split"] == "train"}
    kept, dropped = [], 0
    for r in rows:
        if r["split"] == "test_sentence" and r["labels"] and norm(r["text"]) in train_text:
            dropped += 1
            continue
        kept.append(r)
    stat["문구겹침제외"] = dropped

    # 🔴 **id 유일성 게이트** — `chunk.py:165` 와 같은 이유다 (D-149).
    #    ⛔ 겹치면 뒤엣것이 앞엣것을 조용히 덮고, 행 수만 보면 아무 일도 없어 보인다.
    dup = [k for k, v in collections.Counter(r["id"] for r in kept).items() if v > 1]
    if dup:
        raise SystemExit(
            f"🔴 골든셋 id 가 {len(dup)}개 겹친다 — 같은 행이 두 번 들어갔거나 id 규칙이 약하다.\n"
            f"   예: {dup[:5]}"
        )

    # 🟡 **정규화하면 같은 문장** — id 는 달라도 학습에는 같은 표본이다 (D-117).
    #    치명적이지 않으므로 멈추지 않고 **수로 낸다.** ⛔ 안 세면 「행이 많다」로만 보인다.
    ntxt = collections.Counter(norm(r["text"]) for r in kept if r["split"] == "train")
    stat["정규화중복"] = sum(v - 1 for v in ntxt.values() if v > 1)
    return kept, stat


def main() -> int:
    ap = argparse.ArgumentParser(description="골든셋 물질화 (D-143)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    a = ap.parse_args()

    rows, stat = build()
    print(f"골든셋 **{len(rows):,}행**")
    for s in ("train", "test_sentence"):
        sub = [r for r in rows if r["split"] == s]
        pos = [r for r in sub if r["labels"]]
        print(f"\n  ── {s} — {len(sub):,}행 (위반 {len(pos):,} · 적법 {len(sub) - len(pos):,})")
        c: collections.Counter = collections.Counter()
        for r in pos:
            for t in r["labels"]:
                c[t] += 1
        for k, v in c.most_common():
            mark = "✅" if s == "train" or v >= 30 else "🔴"
            print(f"     {v:>5}  {k}  {mark}")
        units = collections.Counter(r["unit"] for r in sub)
        print(f"     단위 — {dict(units)}")
    if stat.get("문구겹침제외"):
        print(
            f"\n  🔴 **문구가 train 과 겹쳐 평가에서 뺀 행 {stat['문구겹침제외']}개** — "
            "문서를 갈라도 문구는 겹친다"
        )
        print("     「글루코사민 100%」처럼 서로 다른 의결서에 각각 인용된 표현이다.")
    if stat.get("정규화중복"):
        print(
            f"\n  🟡 **정규화하면 같은 문장인 학습 행 {stat['정규화중복']}개** — "
            "「피부 보습에…」와 「피부보습에…」가 접힌다 (D-117)"
        )
        print("     id 는 다르지만 학습에는 같은 표본이다. 행 수를 표본 수로 읽지 않는다.")
    if stat.get("미배정"):
        print(f"\n  🚨 분할에 없는 문서 {stat['미배정']}개 — 조용히 빠졌다. 분할부터 다시 본다.")

    print("\n  🔴 적법 행(`labels` 빈 리스트)이 없으면 「전부 위반」이라 답해도 100% 다.")
    print("  🚨 평가 행은 **문장 단위뿐**이다 — 사례집은 사전 쪽이다 (D-155).")

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
