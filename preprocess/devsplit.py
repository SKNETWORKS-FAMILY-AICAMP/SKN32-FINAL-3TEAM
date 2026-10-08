"""dev 분리 — 인코더 학습 노트북이 떼는 **검증 묶음(dev)** 과 같은 행을 저장소에서 다시 낸다 (🆕 2026-10-07).

왜 여기 있나
  · 판정 그래프를 인코더와 함께 잴 때 봉인 평가셋을 볼 때마다 보는 횟수가 쌓인다 (D-175). 규칙 · 문턱 · 판을 고르는
    자리는 dev 다 — 그런데 dev 를 떼는 코드가 학습 노트북에만 있었다(소성민 v11 섹션 3 · 박수진 v10 「dev 분리」).
  · 🔴 **그 노트북의 코드를 그대로 옮긴 것이다** — 줄을 바꾸면 다른 행이 나온다. 같은 행인지는 지문(`sha`)으로
    확인한다: 모델 폴더 `label_scheme.json` 의 `dev_sha` · `dev_rows` 와 다르면 평가 도구가 멈춘다(`scripts/eval_graph.py --dev`).
    ⛔ 노트북과 두 벌이다 (D-99) — 합치지 못해 지문 대조로 묶어 둔다. 노트북의 규칙이 바뀌면 여기도 바꾸고 지문이 그것을 잡는다.

규칙 (v11 규칙 · 10-07 에 박수진 v10 이 같은 규칙으로 맞췄다)
  · 학습 분할만 본다. 대상은 `unit` 이 「문장」이고 합성(`origin == "injected"`)이 아닌 행
  · 묶음 = 행 id 의 `#` 앞(합성 행은 원본 승인 문구) — 같은 문서의 문장이 학습과 dev 로 갈리지 않게
  · 원천마다 묶음의 15% (묶음 단위 · 시드 42) + 선택 6종의 dev 양성이 10건(또는 15%)보다 적으면 묶음을 더 넣는다
  · 조건 M · D · L 은 라벨이 적혀 있어도 양성으로 세지 않는다 (D-296 개정 2)

🚨 dev 는 **학습 분할에서 뗀 것**이다 — 금지 표현 사전은 학습 분할 전체로 만든다. dev 문장에는 사전이 평가셋보다 잘 울린다.
   dev 의 사전 쪽 수치를 평가셋 수치처럼 읽지 않는다. 그리고 dev 에는 해설서 수정문구류(적법 · 주장 없음)가 없다.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable

#: 모델을 고르는 6종 (D-321 결정 4) — dev 양성을 채우는 기준이다. 순서가 결과를 바꾼다(난수를 유형 순서대로 쓴다)
SEL = (
    "질병_예방치료_표방",
    "건강기능식품_오인",
    "의약품_오인",
    "거짓_과장",
    "소비자_기만",
    "후기_체험기_기만",
)
#: `[관행]` — 노트북의 값 그대로다 (v11 · v10)
DEV_SEED = 42
DEV_FRAC = 0.15
#: 유형마다 채우는 dev 양성의 하한 `[관행]` — 노트북의 `min(10, ceil(15% × 전체))`
MIN_POS = 10


def _group(rid: str) -> str:
    if rid.startswith("inj:"):  # 'inj:T1:hf:0:0' → 원본 승인 문구 'hf:0:0'
        return rid.split(":", 2)[2]
    return rid.split("#")[0]


def _eligible(r: dict) -> bool:
    return r.get("unit") == "문장" and r.get("origin") != "injected"


def _target(r: dict) -> list[str]:
    return [] if r.get("조건") in ("M", "D", "L") else list(r.get("labels") or [])


def dev_ids(golden: Iterable[dict]) -> list[str]:
    """dev 행의 id — 노트북과 같은 순서(묶음 이름 순 · 묶음 안은 파일 순)."""
    train = [r for r in golden if r.get("split") == "train"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in train:
        groups[_group(r["id"])].append(r)

    by_prov: dict[str, list[str]] = defaultdict(list)
    for g in sorted(groups):
        elig = [r for r in groups[g] if _eligible(r)]
        if elig:
            by_prov[Counter(r.get("provenance") for r in elig).most_common(1)[0][0]].append(g)
    rng = random.Random(DEV_SEED)
    dev: set[str] = set()
    for prov in sorted(by_prov, key=str):
        gs = by_prov[prov][:]
        rng.shuffle(gs)
        dev.update(gs[: max(1, math.ceil(DEV_FRAC * len(gs)))])

    def pos(rows: list[dict], label: str) -> int:
        return sum(1 for r in rows if _eligible(r) and label in _target(r))

    rest = [g for g in sorted(groups) if g not in dev]
    rng.shuffle(rest)
    for label in SEL:
        want = min(MIN_POS, math.ceil(DEV_FRAC * pos(train, label)))
        have = sum(pos(groups[g], label) for g in dev)
        for g in rest:
            if have >= want:
                break
            k = pos(groups[g], label)
            if k and g not in dev:
                dev.add(g)
                have += k
    ids = [r["id"] for g in sorted(dev) for r in groups[g] if _eligible(r)]
    if len(set(ids)) != len(ids):
        raise ValueError("dev 에 같은 id 가 둘 이상이다")
    return ids


def sha(ids: Iterable[str]) -> str:
    """dev 지문 — 노트북의 `DEV_SHA` 와 같은 식(정렬한 id 를 `|` 로 이은 것의 sha256 앞 16자)."""
    return hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:16]
