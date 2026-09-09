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
    assign = json.loads(SPLIT.read_text(encoding="utf-8"))["assign"]
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

    if INJECTED.exists():
        for line in INJECTED.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rows.append(
                {
                    "id": f"inj:{r['rule_id']}:{len(rows)}",
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
