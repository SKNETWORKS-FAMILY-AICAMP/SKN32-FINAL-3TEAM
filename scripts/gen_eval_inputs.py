"""생성 평가 입력 목록 — dev 의 위반 행을 (문구 · 전제 · 정답 유형 · 불가 사유)로 낸다 (D-322 결정 C · 🆕 2026-10-10).

고쳐 쓰기(생성)를 잴 때 **어떤 문구를 어떤 제품 전제로 넣는가**를 한 곳에서 정한다. 이 목록이 없어 사람마다 다른 묶음으로 쟀고,
D-322 가 적어 둔 층별 수(98 · 71 · 43 → 103 · 71 · 42)가 두 번 재현되지 않았다. 이 스크립트가 낸 수가 정의다.

    uv run python scripts/gen_eval_inputs.py                       # 수만 본다
    uv run python scripts/gen_eval_inputs.py --out build/eval/gen_inputs_dev.jsonl

★ 정답은 문구가 아니라 (문구 · 전제)의 짝에 붙는다. 제품 정보는 **아는 만큼만** 넘긴다 — 판정 평가(`scripts/eval_graph.py`
   `product_of`)와 같은 규칙이다.
     · `전제` 층 — 골든 `전제` 칸이 있는 행. 그 전제로 고쳐 쓰고 그 전제의 분기로 재판정한다
     · `품목` 층 — 전제는 모르고 품목만 아는 행(건강기능식품의 인정 여부). 품목으로 고쳐 쓰고 기록되는 판정으로 재판정한다
     · `참고` 층 — 둘 다 모르는 행(공정위 의결서). 제품 정보 없이 넣는다. D-322 C 의 「의결서 · 참고 층」이다
🔴 행의 조건이 A · B · C 이고 **유형이 있는** 행만 든다 — 채점 밖(M · D)과 적법(L)은 고칠 것이 없다.
   근거는 있는데 8유형이 없는 행(화장품법 제13조① 4호 등)은 뺀다 — 판정 평가가 채점에서 빼는 행이고(D-321), 고쳐 쓰기
   서버에 넘길 위반 유형이 없다. 뺀 수는 출력에 찍는다.
   불가 사유는 골든 `조건` 칸 그대로다(A 자격 · B 실증 · C 절대). 🚨 조건 라벨은 대부분 모델 판독의 합의다(원장 10-03 ㊿-36).
🚨 **dev 만 쓴다.** 봉인 평가셋의 문구를 생성기에 넣으면 그 출력으로 판정 규칙을 고르게 된다 (D-175 · D-322 원칙).
⛔ 출력에는 광고 문구가 든다 — `build/` 밖(공개 저장소)에 쓰지 않는다 (D-249).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.contracts import Infeasibility  # noqa: E402
from collect import registry  # noqa: E402
from scripts import eval_graph as eg  # noqa: E402

#: 골든 `조건` 칸 → 불가 사유 (계약 `Infeasibility`). 이 셋만 고쳐 쓸 대상이다
REASON_OF_COND = {"A": Infeasibility.A, "B": Infeasibility.B, "C": Infeasibility.C}
#: 사유의 이름 — 표의 머리말에만 쓴다(계약 `Infeasibility` 의 주석과 같은 말)
REASON_NAME = {"B": "실증", "C": "절대", "A": "자격"}
LAYERS = ("전제", "품목", "참고")


def layer_of(r: dict) -> str:
    """행에 대해 아는 만큼 — 전제 · 품목 · 둘 다 모름. 승인 문구 규칙 행은 `전제`(식품)로만 든다(`eg.conditional_rows`)."""
    if r.get("전제"):
        return "전제"
    return "품목" if eg.conditional_rows([r]) else "참고"


def gen_inputs(rows: list[dict]) -> list[dict[str, Any]]:
    """dev 행 → 생성 평가 입력. 🔴 `전제` 칸이 없는 판(재동결 전)이면 멈춘다 — 품목만으로 조용히 만들지 않는다 (D-220)."""
    if rows and not all("전제" in r for r in rows):
        raise SystemExit(
            "🔴 골든에 `전제` 칸이 없다 — 2026-10-10 재동결 전 판이다. 생성 평가 입력을 못 만든다\n"
            "  먼저(정본): uv run python launcher.py golden --write · (사본): data-sync"
        )
    out = []
    for r in rows:
        reason = REASON_OF_COND.get(r.get("조건"))
        if reason is None or not r.get("labels"):
            continue
        layer = layer_of(r)
        product = eg.product_of(r, layer != "참고")
        out.append(
            {
                "id": r["id"],
                "text": r["text"],
                "층": layer,
                "전제": r["전제"],
                "품목": product.category.value if product.category else None,
                "인정": product.has_recognized_function if r["전제"] else None,
                "정답_유형": list(r["labels"]),
                "정답_근거": list(r["근거"]),
                "불가_사유": reason.value,
            }
        )
    return out


def counts(items: list[dict]) -> dict[str, dict[str, int]]:
    """층 · 전제(없으면 품목) → 사유별 수."""
    table: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for it in items:
        table[f"{it['층']} · {it['전제'] or it['품목'] or '제품 정보 없음'}"][it["불가_사유"]] += 1
    by_layer = sorted(table.items(), key=lambda kv: (LAYERS.index(kv[0].split(" · ")[0]), kv[0]))
    return {k: dict(v) for k, v in by_layer}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=pathlib.Path, help="목록을 JSONL 로 (build/ 아래에만)")
    a = ap.parse_args(argv)
    if a.out and not a.out.resolve().is_relative_to(ROOT / "build"):
        raise SystemExit("🔴 출력에는 광고 문구가 든다 — `build/` 아래에만 쓴다 (D-249)")
    rows = eg.load_rows(dev=True)
    items = gen_inputs(rows)
    # 🔴 변경금지(ND) 게이트 — 문구가 든 파생물이다. 골든이 만들 때 막았지만 여기서도 부른다 (`tests/test_nd_gate.py`)
    picked = {it["id"] for it in items}
    registry.assert_derivable([r for r in rows if r["id"] in picked], who="scripts.gen_eval_inputs")
    untyped = sum(
        1 for r in rows if r.get("조건") in REASON_OF_COND and r.get("근거") and not r.get("labels")
    )
    order = list(REASON_NAME)
    print(
        f"생성 평가 입력 — dev {len(rows)}행 중 {len(items)}행 (조건 A · B · C ∧ 유형 있음)"
        f" · 근거는 있는데 유형이 없어 뺀 행 {untyped} · 골든 {eg._sha12(eg.GOLDEN)}"
    )
    head = "".join(f"{REASON_NAME[x]:>8}" for x in order)
    print(f"\n  {'층 · 전제(없으면 품목)':<28}{head}{'합':>8}")
    total: collections.Counter = collections.Counter()
    for name, c in counts(items).items():
        total.update(c)
        print(
            f"  {name:<28}" + "".join(f"{c.get(x, 0):>8}" for x in order) + f"{sum(c.values()):>8}"
        )
    print(
        f"  {'합':<28}"
        + "".join(f"{total.get(x, 0):>8}" for x in order)
        + f"{sum(total.values()):>8}"
    )
    print(
        "\n  🚨 사유는 골든 `조건` 칸이다(대부분 모델 판독의 합의) · 「참고」 층은 제품 정보 없이 넣는다 (D-322 C)"
    )
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8", newline="\n") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        print(f"  → {a.out}  ({len(items)}줄)")
    else:
        print("  ⬜ 쓰지 않았다 — `--out build/eval/…jsonl` 을 붙인다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
