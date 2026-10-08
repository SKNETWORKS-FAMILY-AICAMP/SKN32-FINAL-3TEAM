"""1단계 프롬프트 실험 (2026-10-08 · 멘토링 「프롬프팅으로도 조절해 보라」).

같은 어댑터(v12)에 **추론 때 시스템 프롬프트만 바꿔** 넣고, 직접 만든 연습 문제로 잰다.
🚨 정답표 v2(사례집 2021 · 화장품 Q&A) 문구는 쓰지 않는다 (팀장 전달 §3) — 살리기 40 · 원료명 14 · 뜻 보존 15 만.
🚨 어댑터는 SYSTEM_V6 으로 학습했다 — 프롬프트를 바꾸면 학습 때 본 꼴과 달라진다. 그 영향도 함께 잰다.

    .venv-sllm\\Scripts\\python.exe docs\\lse\\prompt_experiment.py            # 전부
    .venv-sllm\\Scripts\\python.exe docs\\lse\\prompt_experiment.py P0 P1      # 고른 판만
결과: `docs/lse/prompt_experiment_out.jsonl`(행) · 표준 출력에 요약표. 끝나면 프로세스가 내려가 GPU 를 돌려준다.
"""

from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent)]

import persona_pipeline_e2e as pe  # noqa: E402
from sllm_service import load  # noqa: E402
from train_stage1_v5 import SYSTEM_V6  # noqa: E402

KEEP_RULE = (
    "\n추가: 원산지 · 원료명 · 제조 방법 · 용량 같은 사실은 원문 낱말 그대로 쓴다. "
    "「대신 · 없이 · 무첨가 · 넣지 않고」처럼 앞말과의 관계를 바꾸는 말은 빼지 않는다 — 빼면 뜻이 뒤집힌다."
)
#: 🚨 예시 문구는 연습 문제(뜻 보존 15)와 겹치지 않게 다른 제품 · 다른 원료로 썼다
FEW_SHOT = (
    "\n예시) 위반 문구: 골다공증 걱정 끝 라떼, 우유 대신 국산 귀리 음료로 만들어요 · 위반 유형: 질병_예방치료_표방\n"
    "핵심 주장: 우유 대신 국산 귀리 음료로 만든 라떼\n"
    '{"body": "우유 대신 국산 귀리 음료로 만든 라떼", "mandatory_note": null, "placement": null}\n'
    "예시) 위반 문구: 비염 싹 낫는 유자청, 합성향료 없이 고흥 유자만 썰어 담금 · 위반 유형: 질병_예방치료_표방\n"
    "핵심 주장: 합성향료 없이 고흥 유자만 썰어 담근 유자청\n"
    '{"body": "합성향료 없이 고흥 유자만 썰어 담근 유자청", "mandatory_note": null, "placement": null}'
)
SHORT = (
    "광고 문구의 위반 표현만 지우고 사실(원산지 · 원료 · 제조 · 용량)은 원문 그대로 살린다. "
    "살릴 사실이 없으면(질병 치료 · 의약품 표방 · 체험기 · 신체 변화) 고치지 않는다.\n"
    "출력: 「핵심 주장: ...」 한 줄, 그다음 줄에 JSON 하나.\n"
    '고칠 수 있으면 {"body": "본문", "mandatory_note": null, "placement": null} · 고칠 수 없으면 {"infeasible": "위반 유형"}'
)
VARIANTS = {
    "P0": ("학습 때 프롬프트 그대로(기준)", SYSTEM_V6),
    "P1": ("+ 사실 · 관계어 보존 규칙", SYSTEM_V6 + KEEP_RULE),
    "P2": ("+ 보존 규칙 + 예시 2개(few-shot)", SYSTEM_V6 + KEEP_RULE + FEW_SHOT),
    "P3": ("짧은 새 프롬프트(학습과 다른 꼴)", SHORT),
}
SETS = {"살리기": "stage1_salvage_eval.jsonl", "원료명": "stage1_ingredient_eval.jsonl", "뜻보존": "stage1_meaning_eval.jsonl"}


def rows() -> list[dict]:
    out = []
    for name, f in SETS.items():
        for line in (HERE / f).open(encoding="utf-8"):
            if line.strip():
                out.append({**json.loads(line), "set": name})
    return out


def score(r: dict, res: dict) -> dict:
    final = res.get("final") or ""
    keep_ok = all(k in final for k in r.get("keep", [])) if final else False
    gate = res.get("gate1") or []
    if r["expect"] == "salvage":
        verdict = "살림" if res["outcome"] == "candidate" and keep_ok else (
            "살림(사실 일부 잃음)" if res["outcome"] == "candidate" else ("버림" if res["outcome"] == "infeasible" else "보류"))
    else:
        verdict = "막음" if res["outcome"] != "candidate" else "포장"  # 🔴 고칠 수 없는 것을 후보로 냈다
    return {"verdict": verdict, "flip": any(g.startswith("뜻 바뀜") for g in gate), "gate": gate}


def main(names: list[str]) -> None:
    model, tok, ver = load()
    data = rows()
    out_path = HERE / "prompt_experiment_out.jsonl"
    summary: dict[str, collections.Counter] = {}
    with out_path.open("w", encoding="utf-8", newline="\n") as fo:
        for v in names:
            pe.STAGE1_SYSTEM = VARIANTS[v][1]  # `_run_one` 이 모듈 전역을 읽는다
            c: collections.Counter = collections.Counter()
            t0 = time.time()
            for r in data:
                res = pe.run_one(model, tok, r["input"], r["violation_types"])
                s = score(r, res)
                c[f"{r['set']}:{s['verdict']}"] += 1
                c["뜻 바뀜(관문이 막음)"] += s["flip"]
                fo.write(json.dumps({"variant": v, "set": r["set"], "no": r["no"], "input": r["input"], "raw": res.get("stage1"),
                                     "final": res.get("final"), "outcome": res["outcome"], **s}, ensure_ascii=False) + "\n")
                fo.flush()
            c["초"] = round(time.time() - t0)
            summary[v] = c
            print(f"[{v}] {VARIANTS[v][0]} — {dict(c)}", flush=True)
    print(f"\n모델 {ver} · 문항 {len(data)} (살리기 40 · 원료명 14 · 뜻 보존 15)")
    for v, c in summary.items():
        sal = sum(n for k, n in c.items() if k.endswith(":살림"))
        want = sum(1 for r in data if r["expect"] == "salvage")
        print(f"{v} {VARIANTS[v][0]:<28} 살림 {sal}/{want} · 포장 {sum(n for k, n in c.items() if k.endswith(':포장'))} · "
              f"막음 {c['살리기:막음']}/12 · 뜻 바뀜 {c['뜻 바뀜(관문이 막음)']} · {c['초']}초")


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
