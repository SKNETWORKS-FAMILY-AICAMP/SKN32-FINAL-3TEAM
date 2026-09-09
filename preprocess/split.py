"""preprocess/split.py — 골든셋 분할 [P12] · 🚨 **출처 분리** (D-15 · D-40).

  uv run python -m preprocess.split --dry-run   # 무엇이 어디로 가는지만 본다
  uv run python -m preprocess.split --write     # split_manifest.json 을 쓴다

──────────────────────────────────────────────────────────────
★ **라벨의 출처는 셋이고, 이 파일은 ① 만 다룬다** (2026-09-09)

    ① 조문   감독기관이 법으로 붙였다 — 사례집(D-158) · 공정위 의결서
    ② 구성   규칙이 곧 라벨 — 결함 주입 [P10]. 🚨 test 에 넣지 않는다
    ③ 판단   사람 또는 모델 — 뭉친 라벨을 가르는 자리에만

🔴 **평가셋은 ① 로만 만든다.** 시험지를 시험 대상이 만들면 안 된다.

──────────────────────────────────────────────────────────────
🚨 **왜 `ftc` 를 갈라야 하는가**

레지스트리에서 `ftc_decisions_body` 는 `U1: allow` 라 **학습 원천**이고,
`mfds_casebook`·`mfds_press` 는 `U1: deny` 라 **평가 전용**이다. 그런데 평가 전용
원천만으로는 축이 안 선다 — 실측 (2026-09-09) —

                          casebook(낱말)   ftc(문장)
    질병_예방치료_표방            41            0
    의약품_오인                 38            0
    건강기능식품_오인             32            0
    거짓_과장                   32          168
    소비자_기만                   0           40   ← ftc 에만 있다
    후기_체험기_기만               0            0   🔴
    부당_비교광고                 0            2   🔴
    비방광고                     0            1   🔴

**`소비자_기만` 은 `ftc` 없이는 0 이다.** 그래서 `ftc` 의 일부를 **문서 단위로 봉인**해
학습에서 빼고 평가로 돌린다. 무작위 분할이 아니라 `seq`(의결서 번호) 단위다 —
같은 의결서의 문구가 train 과 eval 에 섞이면 F1 이 부풀려진다 ([P12] 규칙 1).

⛔ **같은 기관이라는 한계는 남는다.** `ftc` 평가 슬라이스는 학습과 **같은 원천**이라
「다른 기관에서도 되는가」를 재지 못한다. 그래서 산출에 `same_source: true` 를 박고
**두 지표를 나란히 보고한다** — 감추는 것이 아니라 적는 것이 이 설계의 값이다.

🚨 **30 미만 유형은 `unmeasurable` 에 적는다** (D-40). 「측정 불가」를 말할 수 있게
만드는 것은 슬라이드가 아니라 이 JSON 한 줄이다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random

FTC_PHRASES = pathlib.Path("data/derived/ftc_layer1_phrases.json")
CASEBOOK = pathlib.Path("data/derived/mfds_casebook_labels.jsonl")
OUT = pathlib.Path("data/derived/golden/split_manifest.json")

#: 🚨 유형별 평가 목표. D-40 의 30 이 **하한**이고, 신뢰구간을 감안해 40 을 목표로 둔다.
#:    40건에서 Recall 0.85 면 95% CI 가 ±11%p 다 (기획문서 6-3) — 30 은 아슬아슬하다.
EVAL_TARGET = 40

#: 🔴 가용이 목표 이하면 **전량을 평가로** 돌린다. 학습은 주입본([P10])으로 채울 수 있지만
#:    평가는 실사례로만 채울 수 있다 — **못 만드는 쪽에 먼저 준다.**
#:    ⛔ 처음에 이 값을 `EVAL_TARGET * 2` 로 뒀더니 `소비자_기만` 79건을 **통째로** 봉인해
#:       학습 몫이 0 이 됐다. 40 이면 서는 것을 79 로 가져가는 것은 평가의 이득이 아니라
#:       **학습의 손실**이다. 목표를 넘으면 목표만 가져간다.
SCARCE = EVAL_TARGET

MIN_MEASURABLE = 30  # D-40


def _load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        raise FileNotFoundError(f"{p} 가 없다 — 먼저 추출기를 돌린다")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def ftc_docs() -> list[dict]:
    """공정위 의결서 — **문서 하나가 한 줄**. 조문에서 읽은 유형이 붙어 있다."""
    if not FTC_PHRASES.exists():
        raise FileNotFoundError(
            f"{FTC_PHRASES} 가 없다 —\n  먼저: uv run python -m preprocess.ftc_extract --stage --dump"
        )
    got = []
    for r in json.loads(FTC_PHRASES.read_text(encoding="utf-8")):
        labels = sorted({u["label"] for u in (r.get("유형") or [])})
        if not labels or not r.get("문구"):
            continue  # 🚨 라벨이나 문구가 없으면 어느 쪽에도 못 쓴다
        got.append(
            {
                "doc_id": f"ftc:{r['seq']}",
                "원천": "ftc_decisions_body",
                "유형": labels,
                "문구수": len(r["문구"]),
                "결정일자": r.get("결정일자"),
            }
        )
    return got


def casebook_docs() -> list[dict]:
    """사례집 — `U1: deny` 라 **통째로 평가**다. 가르지 않는다."""
    got = []
    for i, r in enumerate(_load_jsonl(CASEBOOK)):
        labels = sorted(r.get("확정유형") or [])
        if not labels or not r.get("인용표현"):
            continue
        got.append(
            {
                "doc_id": f"casebook:{r.get('쪽')}:{i}",
                "원천": "mfds_casebook",
                "유형": labels,
                "문구수": len(r["인용표현"]),
                "단위": "낱말",  # 🔴 문장이 아니다 (D-155)
            }
        )
    return got


def plan(seed: int = 20260909) -> dict:
    """🚨 **희소한 유형부터 채운다.** 흔한 유형이 먼저 가져가면 희소한 것이 못 선다."""
    ftc = ftc_docs()
    have = collections.Counter(t for d in ftc for t in d["유형"])
    # 희소한 유형이 앞에 오도록 — 그 유형을 가진 문서를 먼저 평가로 봉인한다
    order = sorted(have, key=lambda t: have[t])
    need = {t: (have[t] if have[t] <= SCARCE else EVAL_TARGET) for t in have}

    rnd = random.Random(seed)
    pool = sorted(ftc, key=lambda d: d["doc_id"])
    rnd.shuffle(pool)

    sealed: dict[str, dict] = {}
    got: collections.Counter = collections.Counter()
    for t in order:
        for d in pool:
            if d["doc_id"] in sealed or t not in d["유형"]:
                continue
            if got[t] >= need[t]:
                break
            sealed[d["doc_id"]] = d
            for x in d["유형"]:
                got[x] += 1  # 🚨 다중 라벨 문서는 여러 유형을 동시에 채운다

    train = [d for d in pool if d["doc_id"] not in sealed]
    evals = list(sealed.values()) + casebook_docs()

    def tally(rows: list[dict]) -> dict[str, int]:
        c: collections.Counter = collections.Counter()
        for d in rows:
            for t in d["유형"]:
                c[t] += 1
        return dict(sorted(c.items(), key=lambda x: -x[1]))

    ev = tally(evals)
    return {
        "seed": seed,
        "eval_target": EVAL_TARGET,
        "min_measurable": MIN_MEASURABLE,
        "split_key": "doc_id",
        "note": (
            "평가셋은 조문 라벨 원천으로만 만든다 — 사람도 모델도 붙이지 않는다. "
            "ftc 슬라이스는 학습과 같은 기관이라 원천 편향을 재지 못한다 (same_source)."
        ),
        "counts": {"train": tally(train), "test_holdout": ev},
        "sizes": {"train": len(train), "test_holdout": len(evals)},
        "unmeasurable": sorted(t for t, n in ev.items() if n < MIN_MEASURABLE),
        "absent": sorted(
            t
            for t in (
                "질병_예방치료_표방",
                "의약품_오인",
                "건강기능식품_오인",
                "거짓_과장",
                "소비자_기만",
                "후기_체험기_기만",
                "부당_비교광고",
                "비방광고",
            )
            if t not in ev
        ),
        "source_sets": {
            "train": ["ftc_decisions_body(비봉인)", "mfds_special_use_guide", "주입본[P10]"],
            "test_holdout": ["ftc_decisions_body(봉인)", "mfds_casebook"],
        },
        "same_source": ["ftc_decisions_body"],
        "sealed_doc_ids": sorted(sealed),
        "train_doc_ids": sorted(d["doc_id"] for d in train),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="골든셋 분할 [P12] — 출처 분리")
    ap.add_argument("--write", action="store_true", help=f"{OUT} 로 쓴다")
    ap.add_argument("--seed", type=int, default=20260909, help="재현 조건 (D-54)")
    a = ap.parse_args()

    m = plan(a.seed)
    print(f"분할 seed={m['seed']} · 키={m['split_key']} · 평가 목표 유형당 {m['eval_target']}")
    print(f"  train {m['sizes']['train']}문서 · test_holdout {m['sizes']['test_holdout']}문서\n")
    print(f"  {'유형':22} {'train':>6} {'eval':>6}")
    keys = sorted(set(m["counts"]["train"]) | set(m["counts"]["test_holdout"]))
    for t in sorted(keys, key=lambda x: -m["counts"]["test_holdout"].get(x, 0)):
        ev = m["counts"]["test_holdout"].get(t, 0)
        mark = "✅" if ev >= MIN_MEASURABLE else "🔴 측정 불가"
        print(f"  {t:22} {m['counts']['train'].get(t, 0):>6} {ev:>6}   {mark}")

    if m["unmeasurable"]:
        print(f"\n  🔴 **측정 불가** {len(m['unmeasurable'])}종 — {m['unmeasurable']}")
        print("     🚨 이 유형들은 지표를 내지 않는다. 「측정 불가」로 **보고한다** (D-40).")
    if m["absent"]:
        print(f"  🔴 **평가 데이터가 아예 없는 유형** — {m['absent']}")
        print("     🚨 라벨링으로 안 풀린다. 원천에 사건 자체가 없다.")
    print("\n  🚨 ftc 슬라이스는 학습과 **같은 기관**이다 — 원천 편향은 못 잰다.")
    print("     `same_source: true` 를 박고 두 지표를 나란히 보고한다 (기획문서 6-2).")

    if a.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  → {OUT}")
    else:
        print(f"\n  ⬜ 쓰지 않았다 — `--write` 를 붙이면 {OUT} 에 고정된다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
