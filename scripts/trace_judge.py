"""scripts/trace_judge.py — 문구 하나를 검수 엔진에 넣고 **노드마다 무엇을 냈는지** 콘솔에 찍는다 · 🆕 2026-10-15 (ksr).

  uv run python -m scripts.trace_judge "면역력 증진에 도움을 줄 수 있습니다."
  uv run python -m scripts.trace_judge "비만방지에 효과적입니다" --category 식품

★ 사전 · 인코더 · 판정 로직 중 어디서 결과가 갈렸는지 보려고 쓴다. 서버 없이 돈다(DB 는 떠 있어야 한다).
  `--category` 를 비우면 검수 화면과 같은 조건(품목 모름 → 분기 여섯)이다.
🚨 추적 줄(`copylane.trace`)은 문구를 가린다(`app/trace.py`). 맨 위 문장 표만 원문이다 — 이 터미널에만 나간다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="검수 엔진 노드별 추적")
    ap.add_argument("text", help="검수할 문구")
    ap.add_argument("--category", choices=["식품", "건기식", "화장품", "일반상품"], default=None)
    args = ap.parse_args()

    # 🚨 설정을 읽기 전에 켠다 — `settings()` 는 프로세스당 한 번만 읽는다
    os.environ["COPYLANE_TRACE"] = "on"
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    for noisy in ("httpx", "sentence_transformers", "transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from app import sentsplit  # noqa: PLC0415 — 위에서 스위치를 켠 뒤에 import 한다
    from app.api import judge  # noqa: PLC0415
    from app.contracts import Category, JudgeRequest, ProductContext  # noqa: PLC0415

    print("═" * 70)
    print("문장 표 (원문 · 이 터미널에만)")
    for i, s in enumerate(sentsplit.split(args.text)):
        print(f"  s{i}  {s}")
    print("═" * 70)

    product = (
        ProductContext(category=Category(args.category)) if args.category else ProductContext()
    )
    r = judge(JudgeRequest(text=args.text, product=product))

    print("═" * 70)
    print(f"결과 outcome={r.outcome.value}  judged_by={r.judged_by}")
    for s in r.sentences:
        enc = (
            ", ".join(f"{c.violation.value} {c.confidence:.2f}" for c in s.encoder_candidates)
            or "-"
        )
        print(
            f"  {s.sent_id} 판정={s.verdict.value}"
            + (f"({s.hold_reason.value})" if s.hold_reason else "")
            + f"  위반(사전 근거)={[v.value for v in s.violations] or '-'}  인코더 후보={enc}"
        )
    print(
        f"  분기 {len(r.branches)}개: "
        + " · ".join(f"{b.premise.value}→{b.outcome.value}" for b in r.branches)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
