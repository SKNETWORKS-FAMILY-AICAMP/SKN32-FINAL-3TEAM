"""scripts/eval_rule.py — **판정기 B** (룰 기반 사전 매칭) 와 그 실측 (기획문서 6-2).

  uv run python scripts/eval_rule.py

──────────────────────────────────────────────────────────────
★ **왜 룰 판정기가 따로 필요한가** — 상관 오류 방어다.

    [판정기 A] 인코더   — 골든셋으로 학습됨
    [판정기 B] 룰 매칭  — 고시·조문에서 직접 나옴. **학습 데이터를 공유하지 않는다**

둘이 같은 데이터로 배우면 오류가 **상관**된다. B 는 학습이 없으므로 오류가 독립이고,
**불일치가 곧 위험 신호**가 된다. 새로 만들 것은 매칭기 하나뿐이었다 — 사전은 이미 있다.

🔴 **사전은 `train` 문서에서만 만들어졌다** (`dictionary.train_only`). 그래서 이 점수는
   「외운 것을 맞힌 수」가 아니다. 그 봉인이 없으면 이 스크립트의 출력은 전부 착시다.

──────────────────────────────────────────────────────────────
🚨 **점수가 낮게 나오는 것이 정상이다.** D-156 이 「사전만으로는 틀린다」를 이미 적었다.
   ★ 이 낮은 숫자가 **「그래서 모델이 필요하다」의 근거**다. 높게 나오면 오히려
     누수를 의심해야 한다.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import sys
import unicodedata

from app.settings import PARAMS

DICT = pathlib.Path("data/derived/banned_terms.jsonl")
GOLDEN = pathlib.Path("data/derived/golden/golden.jsonl")
MIN_MEASURABLE = PARAMS.min_measurable  # D-40

#: 🆕 D-255 — **보고용 묶음 지표.** 클래스·라벨은 그대로 두고 **평가 보고에서만** 함께 잰다.
#:    식품표시광고법 §8①**5호**(소비자를 기만하는 표시·광고) 안에 `소비자_기만` 과 `후기_체험기_기만` 이
#:    같이 산다(시행령 [별표 1] 5호 · 체험기는 다목의 한 요소). 후기 단독은 실사례가 30건에 못 미쳐
#:    「측정 불가」(D-40)로 남으므로, 조문이 묶은 단위로 **함께** 낸다 — D-231 이 열어 둔 (다)의 보고판.
#:    ⛔ 라벨을 합치지 않는다(D-231 (라) 기각) — 묶음은 **보조 지표**이고 유형별 표를 대신하지 않는다.
REPORT_GROUPS: dict[str, tuple[str, ...]] = {
    "5호 묶음(소비자_기만∪후기)": ("소비자_기만", "후기_체험기_기만"),
}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s)))


def load_rules() -> dict[str, str]:
    """`단독판정` 자격이 있는 항목만. 🔴 적법중첩·모호는 **단독으로 쓰지 않는다** (D-156)."""
    if not DICT.exists():
        raise FileNotFoundError(f"{DICT} 가 없다 — 먼저: uv run python launcher.py golden --write")
    got = {}
    for line in DICT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["단독판정"]:
            got[r["term"]] = r["유형"][0]
    return got


def judge(text: str, rules: dict[str, str]) -> set[str]:
    """사전 항목이 **정규화문에 부분문자열로** 들어 있으면 그 유형으로 본다.

    ⛔ 종전 docstring 은 「정확 매칭만 한다」였는데 코드는 `term in n` 이다 —
       **문서가 코드를 잘못 적고 있었다** (2026-09-10 정정).
    🚨 부분문자열이라 짧은 낱말이 위험하다. 그래서 앞에서 `단독판정` 자격
       (적법중첩·모호 제외)이 거른다 — 자격 심사가 이 매칭의 안전장치다 (D-156).
    """
    n = norm(text)
    return {lab for term, lab in rules.items() if term in n}


def group_scores(
    pairs: list[tuple[set[str], set[str]]], groups: dict[str, tuple[str, ...]] = REPORT_GROUPS
) -> dict[str, tuple[int, int, int, int]]:
    """(예측, 정답) 쌍 → 묶음마다 `(정답 행, TP, FP, FN)`. 🚨 행 단위다 — 묶음 안 어느 유형이든 맞으면 적중.

    묶음 안에서 유형을 잘못 골라도(후기를 소비자_기만으로) 적중으로 센다 — 그것이 묶음 지표의 뜻이다.
    유형을 가르는 능력은 위의 유형별 표가 잰다.
    """
    out = {}
    for name, members in groups.items():
        m = set(members)
        g = tp = fp = fn = 0
        for pred, true in pairs:
            t, p = bool(true & m), bool(pred & m)
            g += t
            tp += t and p
            fp += p and not t
            fn += t and not p
        out[name] = (g, tp, fp, fn)
    return out


def main() -> int:
    rules = load_rules()
    if not GOLDEN.exists():
        print(f"🔴 {GOLDEN} 가 없다 — uv run python launcher.py golden --write", file=sys.stderr)
        return 1
    rows = [
        json.loads(x)
        for x in GOLDEN.read_text(encoding="utf-8").splitlines()
        if x.strip() and json.loads(x)["split"] == "test_sentence"
    ]
    print(f"판정기 B — 사전 {len(rules):,}종(단독판정) · 시험지 {len(rows)}행 (문장 단위)")

    tp: collections.Counter = collections.Counter()
    fp: collections.Counter = collections.Counter()
    fn: collections.Counter = collections.Counter()
    gold: collections.Counter = collections.Counter()
    neg_fired = 0
    neg_total = 0
    pairs: list[tuple[set[str], set[str]]] = []
    for r in rows:
        pred, true = judge(r["text"], rules), set(r["labels"])
        pairs.append((pred, true))
        if not true:
            neg_total += 1
            neg_fired += bool(pred)
        for t in true:
            gold[t] += 1
        for t in pred & true:
            tp[t] += 1
        for t in pred - true:
            fp[t] += 1
        for t in true - pred:
            fn[t] += 1

    # 🚨 **정답에 없는 유형의 오탐도 표에 낸다** (2026-09-10).
    #    ⛔ 종전에는 `sorted(gold, ...)` 라 `gold[t] == 0` 인 유형이 표에서 **사라졌다.**
    #       실측에서 `질병_예방치료_표방` 에 오탐 1건이 있었는데 한 줄도 안 보였다.
    #       Precision 을 재려고 만든 표에서 오탐이 숨는 것은 표를 착시로 만든다.
    seen = sorted(set(gold) | set(tp) | set(fp), key=lambda x: (-gold[x], x))
    print(f"\n  {'유형':22} {'정답':>5} {'P':>7} {'R':>7} {'F1':>7}")
    for t in seen:
        p = tp[t] / (tp[t] + fp[t]) if tp[t] + fp[t] else 0.0
        rc = tp[t] / gold[t] if gold[t] else 0.0
        f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
        if gold[t] == 0:
            mark = f"  🚨 정답 0인데 오탐 {fp[t]}건 — 시험지에 없는 유형이다"
        elif gold[t] < MIN_MEASURABLE:
            mark = "  🔴 측정 불가 (D-40)"
        else:
            mark = ""
        print(f"  {t:22} {gold[t]:>5} {p:>7.3f} {rc:>7.3f} {f1:>7.3f}{mark}")

    # 🆕 D-255 — 보고용 묶음 지표 (유형별 표를 대신하지 않는다)
    print(f"\n  {'묶음 (보조 지표 · D-255)':22} {'정답':>5} {'P':>7} {'R':>7} {'F1':>7}")
    for name, (g, t_, f_, _fn) in group_scores(pairs).items():
        p = t_ / (t_ + f_) if t_ + f_ else 0.0
        rc = t_ / g if g else 0.0
        f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
        mark = "  🔴 측정 불가 (D-40)" if g < MIN_MEASURABLE else ""
        print(f"  {name:22} {g:>5} {p:>7.3f} {rc:>7.3f} {f1:>7.3f}{mark}")

    print(f"\n  🔴 **적법 {neg_total}행 중 {neg_fired}행에서 사전이 울렸다**", end="")
    print(f" (오탐률 {neg_fired / neg_total:.1%})" if neg_total else "")
    print("     🚨 적법 문구가 위반으로 잡히는 비율이다 — 이것이 없으면 Precision 은 착시다.")

    print("\n  🚨 **이 점수를 제품 성능으로 읽지 않는다.** 판정기 B 는 인코더의 **대조군**이다.")
    print("     둘이 갈리는 지점이 보류·재생성 신호가 된다 (기획문서 6-2 ①).")
    print("  ★ 낮은 것이 정상이다 — 사전만으로는 못 푼다 (D-156). 높으면 누수를 의심한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
