"""preprocess/claim_nouns.py — **동작 · 상태 명사 목록** (🆕 2026-10-24 · D-348 보충 41 결정 2 · 3 · (가) 코퍼스).

  uv run python -m preprocess.claim_nouns --verify     # 세기만 한다
  uv run python -m preprocess.claim_nouns --dump       # → data/derived/claim_nouns.jsonl

★ 왜 — 인코더 하한(R1 층)의 하한 가드(`app/claimscope.py` `floor_guard`)가 「~ 예방」 · 「~ 차단」 · 「~ 설계」처럼 **동작 · 상태 명사로 끝나는
  명사구 주장**을 개조식 서술(「~함」의 줄임)로 본다. 어떤 명사가 「-하다 · -되다」를 받는지는 사람이 고르지 않고 코퍼스에서 센다.
★ 정의 — 낱말 머리(앞이 한글이 아님)에서 시작하는 한글 2 ~ 4 자 X 뒤에 「하 · 되 · 시키 · 해 · 돼 · 했 · 됐 · 한 · 된 · 할 · 될 · 함 · 됨 · 하여 · 되어」가
  붙은 꼴이 코퍼스에 `MIN_COUNT` 회 이상 나오면 X 를 싣는다.
  · `MIN_COUNT` = 2 `[임의]`(1 회는 오탈자 · 고유명사를 들인다 · 5 회는 dev 위반 하한이 줄었다 — 원장 10-23(B) ③ 은 코퍼스가 이 판과 다르다)
★ 코퍼스(보충 41 (가) — **파생물 원장 안의 것만**) — 법령 청크 `data/derived/chunks.jsonl` + 학습 골든(`golden.jsonl` 중 학습 분할에서 dev 를 뺀 행 ·
  재분할 학습 칸) · 🔴 dev · 봉인 평가셋 · 데이터 밖 묶음은 쓰지 않는다(D-175) · 정상 카피 900 은 쓰지 않는다 — 원장 밖 입력이라 다른 기기에서 다시 만들 수 없다(D-90 · D-72)
🚨 입력이 없으면 멈춘다 — 빈 목록을 쓰지 않는다(D-220). 목록이 없을 때의 동작(하한 가드 = 지금 주장 가드)은 읽는 쪽(`claimscope.claim_nouns`)이 정한다.
🔗 같은 정의의 측정판 — `docs/ohb/측정도구_2026-10-23/probe_guard_b1022.py` `_vn_words`(900 을 넣은 판 · 탐색용) · 판정 경로의 정의는 이 파일 하나다(D-99)
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from collections.abc import Iterable

from collect import store
from preprocess import devsplit, golden
from preprocess import encoder_resplit as rsp

#: 출력 — 읽는 쪽 `app/claimscope.py` `CLAIM_NOUNS` 와 같은 이름이다(🔗 바꾸면 둘 다)
OUT = "claim_nouns.jsonl"
CHUNKS = "chunks.jsonl"
MIN_COUNT = 2
#: 명사 뒤에 붙는 「하다 · 되다 · 시키다」의 꼴 — 어간 · 활용
SUFFIX = r"(하|되|시키|해|돼|했|됐|한|된|할|될|함|됨|하여|되어)"
STEM = re.compile(r"(?<![가-힣])([가-힣]{2,4})" + SUFFIX)


def count(texts: Iterable[str]) -> collections.Counter[str]:
    """글 묶음에서 X(동작 · 상태 명사 후보)마다 나온 횟수."""
    c: collections.Counter[str] = collections.Counter()
    for t in texts:
        for m in STEM.finditer(t or ""):
            c[m.group(1)] += 1
    return c


def nouns(texts: Iterable[str], min_count: int = MIN_COUNT) -> dict[str, int]:
    """`min_count` 회 이상인 X → 횟수 (가나다순)."""
    return dict(sorted((w, n) for w, n in count(texts).items() if n >= min_count))


def design_golden(rows: list[dict]) -> list[str]:
    """학습 골든 — 학습 분할에서 dev 를 뺀 행 + 재분할 학습 칸(인코더 학습과 같은 쪽 · D-347). 봉인 · dev 는 넣지 않는다."""
    dev = set(devsplit.dev_ids(rows))
    plan = rsp.plan(rows)
    return [
        r["text"]
        for r in rows
        if r["id"] not in dev and (r.get("split") == "train" or plan.get(r["id"]) == rsp.TRAIN)
    ]


def corpus() -> list[str]:
    """코퍼스 글 — 🔴 입력이 하나라도 없으면 멈춘다(D-220)."""
    paths = {"법령 청크": store.DERIVED / CHUNKS, "골든": golden.OUT}
    missing = [f"{k} {p}" for k, p in paths.items() if not p.exists()]
    if missing:
        raise SystemExit(
            f"🔴 코퍼스가 없다 — {missing} · 정본은 `chunk` · `golden --write` · 사본은 `data-sync`"
        )
    chunks = [
        json.loads(x)["text"]
        for x in paths["법령 청크"].read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    gold = [
        json.loads(x) for x in paths["골든"].read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    return chunks + design_golden(gold)


def main() -> int:
    ap = argparse.ArgumentParser(description=f"동작 · 상태 명사 목록 → {OUT}")
    ap.add_argument("--dump", action="store_true", help=f"data/derived/{OUT} 로 쓴다")
    ap.add_argument("--verify", action="store_true", help="세기만 한다")
    args = ap.parse_args()

    texts = corpus()
    got = nouns(texts)
    print(f"  코퍼스 {len(texts):,} 글 · 동작 · 상태 명사 {len(got):,} 낱말(최소 {MIN_COUNT} 회)")
    if not got:
        print("  🚨 목록이 비었다 — 쓰지 않는다 (D-220)", file=sys.stderr)
        return 1
    if args.verify or not args.dump:
        return 0
    out = store.derived_dir(".") / OUT
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for w, n in got.items():
            f.write(json.dumps({"낱말": w, "횟수": n}, ensure_ascii=False) + "\n")
    print(f"  💾 {len(got)}행 → data/derived/{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
