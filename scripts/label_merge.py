"""scripts/label_merge.py — 사람이 붙인 라벨을 합치고 **일치도를 잰다** (D-40 · 기획문서 6-3).

  uv run python scripts/label_merge.py data/derived/labels/*.jsonl
  uv run python scripts/label_merge.py data/derived/labels/*.jsonl --merge out.jsonl

──────────────────────────────────────────────────────────────
★ **일치도가 라벨의 신뢰도다.** 「정답을 누가 붙였습니까」에 답하는 것은 이름이 아니라 κ 다.

    두 사람이 독립으로 붙여 κ = 0.8 이면 → 「우리 라벨은 재현된다」
    κ = 0.4 이면                       → 🔴 **기준이 없는 것이다.** 지시서부터 고친다

🚨 **일치도를 재지 않으면 라벨이 몇 사람의 취향인지 알 수 없다.** 그리고 그것을 모른 채
   학습하면, 모델이 배운 것이 법인지 취향인지도 알 수 없다.

──────────────────────────────────────────────────────────────
🔴 **불일치를 다수결로 덮지 않는다.** 갈린 항목은 목록으로 뽑아 **셋째 사람이 본다** —
   두 사람이 갈렸다는 것은 그 항목이 어렵다는 뜻이고, 어려운 항목이 곧 경계다.
   경계를 다수결로 지우면 지시서가 영영 안 좋아진다.

🚨 이 스크립트는 **라벨을 만들지 않는다.** 세고, 갈린 것을 보여 줄 뿐이다.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib
import sys

# 🔄 **2026-09-17 — 읽기를 `preprocess/labels.py` 로 옮겼다** (D-99).
#    ⛔ `preprocess/split.py` 가 같은 라벨을 읽게 되면서 키 만들기·라벨 꺼내기·파일 읽기가
#       두 벌이 됐다. 두 번째로 쓰게 되면 멈추고 공통화한다 — 갈리면 **같은 라벨이 여기서는
#       합의인데 저기서는 아닌** 상태가 되고, 그것은 수치로 안 보인다.
#    ★ 이 파일은 여전히 **세고 보여 주는 쪽**이다. 라벨을 만들지 않는다.
#    🚨 `python scripts/label_merge.py` 로 직접 돌므로 저장소 뿌리가 `sys.path` 에 없다 —
#       `scripts/db_reset.py`·`schema_drift_check.py` 와 같은 꼴로 세운 뒤에 든다.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from preprocess import labels as store  # noqa: E402 — 위에서 sys.path 를 세운 뒤라야 든다

# 🚨 **바깥에 보이는 이름은 그대로 둔다.** 구현만 옮겼고 이 모듈의 표면은 안 바꾼다 —
#    `tests/test_label_merge.py` 가 `from scripts.label_merge import kappa, load` 로 들고
#    `KEY_FIELDS` 도 본다. 옮기면서 표면을 깨면 「공통화」가 아니라 그냥 파괴다.
#    ⛔ 실제로 한 번 깼다 (2026-09-17 · 클론 B 게이트가 collect 단계에서 죽었다).
KEY_FIELDS = store.KEY_FIELDS
HUMAN = store.HUMAN
load = store.load


def kappa(a: dict[str, str], b: dict[str, str]) -> tuple[float, int, int]:
    """Cohen's κ — **겹치는 항목에서만** 잰다. (κ, 겹친 수, 일치 수)

    🚨 단순 일치율을 쓰지 않는 이유 — 유형이 넷이면 찍어도 25% 는 맞는다.
       κ 는 **우연히 맞을 확률을 뺀 뒤**의 일치도라 그 착시를 없앤다.

    ⛔ 실측으로 확인한 극단 — **일치 51/60(85%) 인데 κ = 0.000** 이 나온다.
       한 사람이 늘 같은 답을 고르면 그 사람은 정보를 주지 않고, 나머지가 그 답을
       자주 맞혀도 「합의」가 아니다. **일치율만 봤으면 85% 라고 적었을 자리다.**
    """
    both = sorted(set(a) & set(b))
    n = len(both)
    if n == 0:
        return float("nan"), 0, 0
    agree = sum(1 for k in both if a[k] == b[k])
    po = agree / n
    ca, cb = collections.Counter(a[k] for k in both), collections.Counter(b[k] for k in both)
    pe = sum(ca[x] * cb.get(x, 0) for x in ca) / (n * n)
    # 🔴 **`pe == 1` 이면 κ 는 정의되지 않는다** (2026-09-10 · D-170).
    #    ⛔ 종전에는 1.0(완전 합의)을 냈다. 그런데 `pe == 1` 은 **두 사람이 전부 같은 한
    #       라벨만 찍었다**는 뜻이고, 그때 정보량은 0 이다. 「우연히 맞을 확률을 뺀다」는
    #       κ 의 취지에서 그 자리는 **뺄 것이 전부**라 답이 없다.
    #    🚨 위 docstring 이 반대편 착시(일치 85%인데 κ=0.000)는 경고해 놓고 이쪽 극단은
    #       열어 뒀다. 1.0 으로 보고하면 **가장 정보 없는 라벨링이 가장 좋아 보인다.**
    k = float("nan") if pe >= 1 else (po - pe) / (1 - pe)
    return k, n, agree


def kappa_by_type(data: dict[str, dict[str, str]]) -> dict[str, tuple[float, int]]:
    """유형마다 「붙었나/안 붙었나」 이진 κ — 모든 사람 쌍을 모아서. 🆕 2026-09-22 (D-262).

    ★ **다중 라벨의 일치도는 유형별로 잰다.** 묶음 κ(`kappa`)는 {8} 과 {5,8} 을 **다른 범주**로 세어
       8 에서 합의한 사실까지 지운다 — 어느 유형의 경계가 흔들리는지도 안 보인다.
    🚨 범위밖이 낀 쌍은 뺀다 — 범위밖은 유형이 없는 게 아니라 **다른 판단**이다(묶음 κ 가 센다).
    반환 — {유형: (κ, 쌍 수)}. κ 가 정의되지 않으면 nan.
    """
    pairs: dict[str, list[tuple[bool, bool]]] = collections.defaultdict(list)
    types = sorted(
        {t for d in data.values() for v in d.values() for t in v.split("|")}
        - {store.OUT_OF_SCOPE, ""}
    )
    for x, y in itertools.combinations(data, 2):
        for k in set(data[x]) & set(data[y]):
            a, b = data[x][k], data[y][k]
            if store.OUT_OF_SCOPE in (a, b):
                continue
            sa, sb = set(a.split("|")), set(b.split("|"))
            for t in types:
                pairs[t].append((t in sa, t in sb))
    got = {}
    for t, pr in pairs.items():
        n = len(pr)
        po = sum(a == b for a, b in pr) / n
        p1, p2 = sum(a for a, _ in pr) / n, sum(b for _, b in pr) / n
        pe = p1 * p2 + (1 - p1) * (1 - p2)
        got[t] = (float("nan") if pe >= 1 else (po - pe) / (1 - pe), n)
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description="라벨 취합 · 일치도 (κ)")
    ap.add_argument("paths", nargs="+", help="사람마다 채운 labelsheet 파일들")
    ap.add_argument("--merge", help="합의된 것만 이 경로로 쓴다 (불일치는 제외)")
    a = ap.parse_args()

    files = [pathlib.Path(x) for x in a.paths]
    missing = [p for p in files if not p.exists()]
    if missing:
        print(f"🔴 없는 파일: {[str(p) for p in missing]}", file=sys.stderr)
        return 1

    # 🔄 2026-09-20 — **사람별**로 묶는다(파일별이 아니다). 한 사람이 시트 둘을 가져오면 파일이 둘이다
    data = store.by_person(files)
    print("채운 건수 —")
    for name, d in data.items():
        print(f"  {name:44} {len(d):>5}건")

    if len(data) < 2:
        print("\n  ⬜ 파일이 하나다 — 일치도를 잴 수 없다.")
        print("     🚨 **한 사람의 라벨은 신뢰도를 모른다.** 최소 두 사람이 겹쳐 붙여야")
        print("        「우리 라벨이 재현되는가」에 답할 수 있다 (기획문서 6-3).")
        return 0

    print("\n일치도 (Cohen's κ) —")
    worst = 1.0
    for x, y in itertools.combinations(data, 2):
        k, n, agree = kappa(data[x], data[y])
        if n == 0:
            print(f"  {x} ↔ {y}: 겹치는 항목이 없다 — 같은 행을 나눠 줘야 잰다")
            continue
        worst = min(worst, k)
        mark = "✅" if k >= 0.8 else ("🟡" if k >= 0.6 else "🔴")
        print(f"  {x} ↔ {y}: κ={k:.3f} {mark}  (겹침 {n} · 일치 {agree})")
    print("     ⚠ 위는 **묶음 κ** 다 — {8} 과 {5,8} 을 다른 범주로 센다(참고).")
    print("\n일치도 — **유형별** 이진 κ (D-262 · 모든 쌍 · 범위밖 쌍 제외) —")
    for t, (k, n) in sorted(
        kappa_by_type(data).items(), key=lambda kv: -(kv[1][0] if kv[1][0] == kv[1][0] else -9)
    ):
        mark = "✅" if k >= 0.8 else ("🟡" if k >= 0.6 else "🔴")
        print(f"  {t:14} κ={k:.2f} {mark}  (쌍 {n})")
    print("     ★ 0.8 이상이면 「우리 라벨은 재현된다」고 말할 수 있다.")
    print("     🔴 0.6 미만이면 라벨이 아니라 **지시서를 고친다** — 사람 탓이 아니다.")

    # 🔴 갈린 항목 — 다수결로 덮지 않고 목록으로 낸다
    allk = set().union(*[set(d) for d in data.values()])
    split_rows = []
    for k in sorted(allk):
        labs = {name: d[k] for name, d in data.items() if k in d}
        if len(set(labs.values())) > 1:
            split_rows.append((k, labs))
    print(f"\n🔴 **갈린 항목 {len(split_rows)}건** — 셋째 사람이 본다 (다수결로 덮지 않는다)")
    for k, labs in split_rows[:8]:
        txt = k.split("\x1f")[2] or k.split("\x1f")[3]
        print(f"  · {txt[:56]}")
        print(f"      {labs}")
    if len(split_rows) > 8:
        print(f"  … 외 {len(split_rows) - 8}건")

    # 🔴 **한 사람만 채운 항목을 「합의」로 넣지 않는다** (2026-09-10 · D-66 2인 확인).
    #    ⛔ 종전 조건은 `len({라벨들}) == 1` 뿐이었다. 한 파일에만 있는 키도 집합 크기가
    #       1 이라 통과한다 — **겹치지 않은 라벨이 전부 「두 사람이 합의한 것」으로**
    #       산출에 들어갔다. 2인 확인이 이 프로젝트의 뼈대인데(D-15 · D-66) 그 자리가 비어 있었다.
    #    ★ 「몇 명이 채웠나」와 「그들이 같은가」는 다른 질문이다. 둘 다 묻는다.
    solo = [k for k in allk if sum(1 for d in data.values() if k in d) == 1]
    if solo:
        print(f"\n🔴 **한 사람만 채운 항목 {len(solo)}건** — 합의가 아니다 (D-66)")
        for k in solo[:5]:
            txt = k.split("\x1f")[2] or k.split("\x1f")[3]
            print(f"  · {txt[:56]}")
        if len(solo) > 5:
            print(f"  … 외 {len(solo) - 5}건")
        print("  🚨 취합에 넣지 않는다. 버린 것이 아니라 **두 번째 사람을 기다리는 것**이다.")

    if a.merge:
        out = pathlib.Path(a.merge)
        agreed = {
            k
            for k in allk
            if sum(1 for d in data.values() if k in d) >= 2
            and len({d[k] for d in data.values() if k in d}) == 1
        }
        # 🔄 2026-09-21 (전수 재검토 I10) — ⛔ 합의 목록은 모두에게서 모으고 **첫 파일의 줄만** 썼다.
        #    첫 파일에 없는 합의(둘째·셋째 사람이 같이 붙인 것)가 경고 없이 빠졌다. 파일 전부를 돌며 키마다 한 줄.
        n = 0
        written: set[str] = set()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for src in files:
                for line in src.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    k = store.key(r)
                    if k in agreed and k not in written and store.verdict(r):
                        f.write(line + "\n")
                        written.add(k)
                        n += 1
        print(f"\n  → {out}  ({n}건 · **2인 이상이 채우고 답이 같은 것만**)")
        print(f"  🚨 갈린 {len(split_rows)}건은 **안 들어갔다.** 버린 것이 아니라 보류다.")
        if solo:
            print(
                f"  🚨 한 사람만 채운 {len(solo)}건도 **안 들어갔다** — 2인 확인이 아니다 (D-66)."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
