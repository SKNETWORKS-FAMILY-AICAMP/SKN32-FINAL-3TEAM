"""진단용 재판정 — e2e 결과의 **원문**과 **1단계 문장**을 모두 팀 판정 코어에 넣어 lse 판단과 맞대 본다 (2026-10-02).

e2e 의 `--rejudge` 는 후보(candidate)만 다시 판정한다 — 후보가 0 이면 재판정은 한 번도 안 돈다.
여기서는 종착과 상관없이 넣어서 두 가지를 센다:
  ① 원문 — 판정 코어가 원문을 위반 확정하는가. 1단계가 「합법화 불가」를 냈는데 코어가 원문에서 위반을 못 찾으면
     지나친 거절이거나 코어의 사전 구멍이다(어느 쪽인지는 사람이 본다).
  ② 1단계 문장 — 관문(`stage_gate.py`)이 통과·보류시킨 문장을 코어도 같은 쪽으로 보는가.

🚨 원문은 재배포 불가(식약처 사례집) — 결과는 `_private/` 에만 쓰고 화면에는 개수만 낸다.

실행 (repo 루트 · DB 필요):
    .venv-sllm/Scripts/python.exe docs/lse/rejudge_diag.py [e2e 결과 jsonl]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rejudge import RejudgeUnavailable, rejudge  # noqa: E402

SRC = HERE / "_private" / "persona_pipeline_e2e_none.jsonl"


def _rj(text: str) -> dict:
    try:
        r = rejudge(text)
    except RejudgeUnavailable as e:
        return {"status": "unavailable", "why": str(e)}
    return {"status": r.status, "violations": list(r.violations), "basis": list(r.basis)}


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    rows = [json.loads(line) for line in src.open(encoding="utf-8") if line.strip()]
    out = src.with_name(src.stem + "_diag.jsonl")
    res = []
    for i, r in enumerate(rows, 1):
        d = {"no": i, "outcome": r["outcome"], "input_rejudge": _rj(r["input"])}
        if r.get("stage1"):
            d["stage1_rejudge"] = _rj(r["stage1"])
        res.append(d)
        print(f"{i:>2}  {r['outcome']:<10}  원문 {d['input_rejudge']['status']:<12}"
              f"  1단계 {d.get('stage1_rejudge', {}).get('status', '-')}", flush=True)
    with out.open("w", encoding="utf-8") as f:
        for r, d in zip(rows, res, strict=True):
            f.write(json.dumps({**r, **d}, ensure_ascii=False) + "\n")

    print("\n=== ① 원문을 코어가 어떻게 보나 (lse 종착별) ===")
    for k, n in sorted(Counter((d["outcome"], d["input_rejudge"]["status"]) for d in res).items()):
        print(f"  {k[0]:<10} × 코어 {k[1]:<12} {n}")
    s1 = [d for d in res if "stage1_rejudge" in d]
    print(f"\n=== ② 1단계 문장 {len(s1)}개 — 관문 종착 × 코어 ===")
    for k, n in sorted(Counter((d["outcome"], d["stage1_rejudge"]["status"]) for d in s1).items()):
        print(f"  {k[0]:<10} × 코어 {k[1]:<12} {n}")
    print(f"\n결과: {out}  (재배포 불가 문구 포함 — _private)")


if __name__ == "__main__":
    main()
