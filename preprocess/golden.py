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
import re

from app.settings import PARAMS
from preprocess import split as split_mod
from preprocess.dictionary import norm
from preprocess.split import approved_docs, casebook_docs, ftc_docs

SPLIT = pathlib.Path("data/derived/golden/split_manifest.json")
INJECTED = pathlib.Path("data/derived/injected_golden.jsonl")
OUT = pathlib.Path("data/derived/golden/golden.jsonl")

# ══ 「이유」 행 전용 필터 (2026-09-17 · D-234) ═══════════════════════════════
#
# 🚨 **`ftc_extract.NOISE` 와 합치지 않는다.** 그쪽은 **주문**용이고 이쪽은 **이유**용이다.
#    합치면 주문 문구가 움직이고, D-143 의 판 대조가 증명한 **「문구 627 불변」이 깨진다.**
#    ⛔ D-99(두 번째면 공통화)에 걸리는 것처럼 보이지만, **같은 로직이 아니라 같은 모양**이다 —
#       거는 대상이 다르고, 합치는 순간 한쪽을 고칠 때마다 다른 쪽이 조용히 따라 움직인다.
#
# **왜 이유에만 거는가** — 이유의 인용 중 광고 카피는 **39.7%**(전수)다. 나머지는 법령 이름·
# 문서 지시어·용어다. 라벨을 붙인 채 넣으면 모델이 「`정부조직법` = 거짓_과장」을 배운다.
#
# ★ **다섯 다 무엇을 버리는지 눈으로 확인하고 넣었다** (D-142 — 지나친 쪽 실패는 조용하다).
_TAG = re.compile(r"<[^>]{1,24}>")
#: ⛔ **ㄱ 은 버리지 않고 벗긴다.** 「던힐 파인 컷 1MG 멘톨<각주>3</각주>」은 담배 제품명
#:    광고다 — 태그가 붙었다고 버리면 카피를 버린다.
_REASON_DROP = (
    # ㄴ 약칭 정의가 잘려 들어온 것 — 「라 한다)」·「…공정경쟁규약(이하」
    re.compile(r"라\s*한다|\(이하\s*$"),
    # ㄷ 중첩 인용부호에서 두 문구가 이어붙은 것 — 「숭인 한양 LEEPS(이하 "이 사건 분양물」
    re.compile(r"[‘’“”「」『』]"),
    # ㄹ 법령 약칭 — 🔴 **「방·요·용·수·기·주」를 제외한다.** 안 하면 「43℃의 **온열요법**」
    #   「황토도포시트의 **제조방법**」 같은 **광고 카피를 먹는다**(실측 29건).
    #   ⬜ 대가로 「목재**이용법**」 한 건을 놓친다 — 카피를 버리는 쪽이 더 나쁘다 (D-157).
    re.compile(r"(?<![방요용수기주])법$|법\)|과태료|공정경쟁규약|규약$|시행규칙|부과기준"),
    # ㅁ 문서 내부 지시어·서증 — 「이 사건 광고」·「소갑 제○호증」. 어느 광고인지도 안 알려 준다
    re.compile(r"^이 ?사건|^본 ?건|^행위 ?\d|^소갑|심사보고서|^별지|호증$|^표 ?\d|^그림 ?\d"),
)
#: 태그를 벗기고 남은 알맹이가 이보다 짧으면 버린다 — `ftc_extract.phrases_in` 과 같은 하한
_REASON_MIN = 4


def reason_keep(text: str) -> tuple[str, str | None]:
    """이유 문구를 학습에 넣을지. 돌려주는 값은 `(쓸 문자열, 버린 사유 or None)`.

    ★ **버린 사유를 함께 돌려준다** — 세는 쪽과 거르는 쪽이 같은 함수를 봐야
      「몇 개를 왜 버렸나」가 산출물 옆에 남는다 (D-142 · D-110).
    """
    s = _TAG.sub("", text).strip()  # ㄱ — 벗긴다
    if len(s) < _REASON_MIN:
        return s, "태그뿐"
    for i, pat in enumerate(_REASON_DROP):
        if pat.search(s):
            return s, "ㄴㄷㄹㅁ"[i]
    return s, None


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
                    "구역": "주문",  # 🆕 D-234 — 어디서 왔는지 남긴다
                    "redistributable": True,
                    "split": split,
                }
            )
            stat[split] += 1

        # 🆕 **「이유」 문구 — 학습에만 넣는다** (2026-09-17 · D-232 (A) · D-234).
        #
        # 🔴 **봉인 문서의 이유는 버린다.** 넣을 자리가 없다 —
        #      · train 에 넣으면 **같은 문서가 양쪽에 서서** 문서 단위 분할이 무너진다
        #      · test 에 넣으면 **채택률 39.7%짜리 라벨로 평가**하게 된다 (D-172)
        #    ★ 143문서분을 버리는 대신 분할이 성립한다. 버리는 것도 적어 둔다 (D-110).
        #
        # 🚨 id 를 `#r{k}` 로 가른다 — 주문과 같은 번호대를 쓰면 대조가 무너진다.
        # 🚨 `구역` 을 남긴다. 안 남기면 **나중에 주문분과 이유분을 못 가른다** —
        #    그러면 「한 숫자가 두 과제를 평균한 수」가 되고, 그것이 D-172 가 경고한 자리다.
        if split == "train":
            for k, text in enumerate(d.get("문구_이유") or []):
                text, why = reason_keep(text)
                if why:
                    stat[f"이유버림_{why}"] += 1
                    continue
                rows.append(
                    {
                        "id": f"{d['doc_id']}#r{k}",
                        "text": text,
                        "labels": d["유형"],
                        "unit": d["단위"],
                        "origin": "approved" if not d["유형"] else "real",
                        "provenance": d["원천"],
                        "구역": "이유",
                        "redistributable": True,
                        "split": split,
                    }
                )
                stat["train(이유)"] += 1
        elif d.get("문구_이유"):
            stat["봉인문서_이유_버림"] += len(d["문구_이유"])

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
            mark = "✅" if s == "train" or v >= PARAMS.min_measurable else "🔴"
            print(f"     {v:>5}  {k}  {mark}")
        units = collections.Counter(r["unit"] for r in sub)
        print(f"     단위 — {dict(units)}")
    # 🆕 **「이유」 회수 계측** (2026-09-17 · D-234). 🚨 **버린 수가 안 보이면 계측이 반쪽이다** —
    #    무엇을 왜 버렸는지가 산출물 옆에 없으면, 필터를 고쳤을 때 무엇이 달라졌는지 못 본다 (D-142).
    drops = {k[len("이유버림_") :]: v for k, v in stat.items() if k.startswith("이유버림_")}
    if stat.get("train(이유)") or drops:
        kept = stat.get("train(이유)", 0)
        tot = kept + sum(drops.values())
        print("\n  🆕 **「이유」 행 (D-232 (A) · D-234)** — 학습에만 넣는다")
        print(f"     담은 것  {kept:>5} / {tot:,}  ({kept / max(tot, 1):.1%})")
        _why = {
            "ㄴ": "약칭 정의가 잘려 들어온 것",
            "ㄷ": "중첩 인용부호로 이어붙은 것",
            "ㄹ": "법령 약칭",
            "ㅁ": "문서 내부 지시어·서증",
            "태그뿐": "태그를 벗기니 알맹이가 없는 것",
        }
        for k, v in sorted(drops.items(), key=lambda x: -x[1]):
            print(f"     버림 {k:<5} {v:>5}  {_why.get(k, '')}")
        if stat.get("봉인문서_이유_버림"):
            print(
                f"     🔴 봉인 문서의 이유 {stat['봉인문서_이유_버림']:,}개는 **버렸다** — "
                "train 에 넣으면 같은 문서가 양쪽에 선다"
            )
        print("     🚨 이유 인용 중 광고 카피는 전수 39.7% 다 — 남은 것에도 잡음이 있다 (⬜ D-234)")

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
