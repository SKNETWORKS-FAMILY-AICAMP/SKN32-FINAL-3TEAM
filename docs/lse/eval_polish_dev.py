"""dev 511 후보에 2단계 「자연스럽게 다듬기」를 돌려 본다 (🆕 2026-10-13 · lse).

다듬기 시험(직접 만든 제품 72)은 학습 데이터와 같은 결의 문장이다 — 팀 평가 입력(dev · D-322)에서 1단계가 낸 **후보**를
다듬으면 관문 · 규칙 · 재판정을 얼마나 지나는지 잰다. 1단계 출력은 이미 저장된 것(`gen_out_dev_<판>.jsonl`)을 쓰고,
지금 관문을 다시 지난 후보만 다듬는다.

    .venv-sllm\\Scripts\\python.exe docs\\lse\\eval_polish_dev.py gen      # GPU — 다듬기 · 관문 · 규칙
    uv run python docs\\lse\\eval_polish_dev.py score                      # 앱 판정 코어로 재판정(다듬은 안 · 담백한 안)

🔒 출력(`build/eval/polish_dev_<판>.jsonl`)에는 dev 원문이 들어간다 — 저장소에 올리지 않는다(build 는 git 무시).
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT)]

from sllm_meta import stage1_version  # noqa: E402

VER = stage1_version()
IN = ROOT / "build" / "eval" / f"gen_out_dev_{VER}.jsonl"
OUT = ROOT / "build" / "eval" / f"polish_dev_{VER}.jsonl"


def gen() -> None:
    import persona_pipeline_e2e as pe  # noqa: PLC0415
    import sllm_meta  # noqa: PLC0415
    from sllm_service import _META, load  # noqa: PLC0415

    sllm_meta.permit_unlocked()  # 🆕 10-13 평가 도구 — 잠금 밖 판도 잰다(D-333)
    from stage_gate import check  # noqa: PLC0415
    from train_persona_stage2 import rule_check  # noqa: PLC0415

    model, tok, ver = load()
    rows = [json.loads(line) for line in IN.open(encoding="utf-8") if line.strip()]
    cands = [r for r in rows if r["res"].get("outcome") == "candidate" and r["res"].get("final")]
    cands = [r for r in cands if check(r["text"], r["res"]["final"]).passed]  # 지금 관문 기준
    print(f"{IN.name} 후보 {len(cands)} (지금 관문 통과) · 2단계 {_META.get('stage2')}", flush=True)
    model.set_adapter("stage2")
    t0 = time.time()
    with OUT.open("w", encoding="utf-8", newline="\n") as fo:
        for i, r in enumerate(cands, 1):
            s1 = r["res"]["final"]
            t = time.time()
            raw = pe.chat(model, tok, pe.STAGE2_SYSTEM, f"검수 통과 문장: {s1}\n대상 고객: {pe.NEUTRAL_PERSONA}", 160)
            a, b = raw.find("{"), raw.rfind("}")
            try:
                s2 = json.loads(raw[a:b + 1])["body"]
            except Exception:  # noqa: BLE001
                s2 = None
            probs = rule_check({"input": s1, "persona_label": pe.NEUTRAL_PERSONA}, s2)
            g2 = check(s1, s2, persona=True) if s2 else None
            ok = bool(s2) and not probs and g2.passed
            fo.write(json.dumps({"id": r["id"], "text": r["text"], "전제": r.get("전제"), "품목": r.get("품목"), "층": r.get("층"),
                                 "정답_유형": r.get("정답_유형"), "s1": s1, "s2": s2, "ok": ok, "problems": probs,
                                 "gate2": list(g2.reasons) if g2 else None, "ms": round((time.time() - t) * 1000),
                                 "stage2": _META.get("stage2"), "model": ver}, ensure_ascii=False) + "\n")
            if i % 20 == 0:
                print(f"{i}/{len(cands)} · {time.time() - t0:.0f}s", flush=True)
    print(f"끝 — {OUT} · {time.time() - t0:.0f}s", flush=True)


def score() -> None:
    from app.routers import user as u  # noqa: PLC0415

    rows = [json.loads(line) for line in OUT.open(encoding="utf-8") if line.strip()]
    for x in rows:
        premise = x.get("전제") or ""
        category = None if premise else (x.get("품목") or None)
        if x["ok"]:
            x["rejudge2"] = u._rejudge(x["s2"], premise, category)["status"]
    n = len(rows)
    ok = [x for x in rows if x["ok"]]
    why = collections.Counter(p.split(":")[0] for x in rows if not x["ok"] for p in (x["problems"] or []) + (x["gate2"] or []))
    rj = collections.Counter(x["rejudge2"] for x in ok)
    print(f"\n다듬기 dev 평가 — 1단계 {rows[0]['model'] if rows else '?'} 후보 {n} · 2단계 {rows[0]['stage2'] if rows else '?'}")
    print(f"  다듬은 안이 관문 · 규칙 통과 {len(ok)}/{n} ({100 * len(ok) / max(n, 1):.1f}%) — 나머지는 담백한 안만 낸다")
    print(f"  막힌 사유 {dict(why.most_common())}")
    print(f"  통과한 다듬은 안의 재판정 {dict(rj)} — 「위반 못 찾음」은 통과가 아니다(D-323)")
    print(f"  다듬기 시간 중앙 {statistics.median(x['ms'] for x in rows) / 1000:.1f}초" if rows else "")
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    {"gen": gen, "score": score}[sys.argv[1]]()
