"""LLM 카피 생성 — 실험 실행기.

    uv run python docs/ksr/llm_copy/run.py --fake --judge off             # 키 · DB 없이 흐름만
    uv run python docs/ksr/llm_copy/run.py --case cos_no_1 --judge off    # GPT + 코드 필터
    uv run python docs/ksr/llm_copy/run.py --case cos_no_1                # GPT + 코드 필터 + 판정엔진
    uv run python docs/ksr/llm_copy/run.py --model gpt-4o --more 1        # 모델 바꿔서 · 「더 탐색하기」 1번

결과는 `build/llm_copy/` 에 JSON 으로 남는다(git 무시 폴더). 탈락 문구 원문은 이 로그에만 있다.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import io
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import llm as llm_mod  # noqa: E402
import pipeline  # noqa: E402
from branches import BRANCHES  # noqa: E402
from filters import REASONS, Inputs  # noqa: E402
from judge import GraphJudge, NoJudge  # noqa: E402


def show(case_id: str, res: pipeline.Result, sec: float, judged: bool) -> None:
    b = BRANCHES[res.branch]
    print(f"\n━━ {case_id} · {b.label} ━━")
    if res.notice:
        print(f"  안내: {res.notice}")
    for i, r in enumerate(res.rounds):
        drops = " · ".join(f"{REASONS[k]} {v}" for k, v in r.items() if k in REASONS)
        print(
            f"  라운드 {i + 1}: 생성 {r.get('generated', 0)} → 보관 {r.get('kept', 0)}"
            + (f"  (탈락 — {drops})" if drops else "")
        )
    label = "후보" if judged else "후보 (판정엔진 안 거침)"
    if res.status == "ok":
        print(f"  ▶ {label} {len(res.picked)}개 · 보관 {len(res.kept)}개 · {sec:.1f}초")
    else:
        print(
            f"  ▶ 탐색 실패 — 3개 중 {len(res.picked)}개를 찾았습니다  [더 탐색하기] [이대로 쓰기] [입력 고치기]"
        )
        if not res.picked:
            top = " · ".join(f"{REASONS[k]} {v}건" for k, v in res.reasons().most_common(3))
            print(f"    입력을 고쳐 보세요 — 주된 탈락 사유: {top}")
    for k in res.picked:
        print(f"    [{k.angle}{' · ' + k.model if k.model else ''}] {k.text}")


def make_llm(spec: str, temperature: float | None):  # noqa: ANN201
    """`--model a,b` 처럼 쉼표로 주면 섞는다."""
    names = [m.strip() for m in spec.split(",") if m.strip()]
    llms = [llm_mod.OpenAIChat(m, temperature) for m in names]
    return llms[0] if len(llms) == 1 else llm_mod.MixLLM(llms)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument(
        "--case", action="append", help="돌릴 시험 입력 id (여러 번 줄 수 있다 · 비우면 전부)"
    )
    ap.add_argument("--model", default=llm_mod.DEFAULT_MODEL)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument(
        "--judge",
        choices=("reject", "graph", "off"),
        default="reject",
        help="reject: 엔진이 위반·유형 후보를 찾으면 탈락(지금 기본) · graph: 종착 pass 만 통과 · off: 판정 안 함",
    )
    ap.add_argument("--fake", action="store_true", help="GPT 대신 대역 — 키 없이 흐름만 본다")
    ap.add_argument(
        "--rounds",
        type=int,
        default=pipeline.MAX_ROUNDS,
        help="자동 반복 상한 (GPT 호출 횟수 상한)",
    )
    ap.add_argument(
        "--more", type=int, default=0, help="탐색 실패 때 「더 탐색하기」를 누르는 횟수"
    )
    ap.add_argument("--show-dropped", action="store_true", help="탈락 문구와 사유를 화면에 찍는다")
    args = ap.parse_args()

    cases = json.loads(pathlib.Path(args.cases).read_text("utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    if not cases:
        raise SystemExit("돌릴 시험 입력이 없다")

    judge = NoJudge() if args.judge == "off" else GraphJudge(reject_only=args.judge == "reject")
    out_dir = ROOT / "build" / "llm_copy"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log = []
    try:
        for case in cases:
            branch = BRANCHES[case["branch"]]
            inputs = Inputs.from_dict(case["inputs"])
            if branch.needs_fixed and not inputs.fixed:
                raise SystemExit(f"{case['id']}: 이 분기는 고정 문구(fixed)가 있어야 한다")
            gen = llm_mod.FakeLLM() if args.fake else make_llm(args.model, args.temperature)
            t0 = time.time()
            res = pipeline.run(inputs, branch, gen, judge, rounds=args.rounds)
            for _ in range(args.more):
                if res.status == "ok":
                    break
                res = pipeline.run(inputs, branch, gen, judge, carry=res)
            sec = time.time() - t0
            show(case["id"], res, sec, judged=args.judge != "off")
            if args.show_dropped:
                for d in res.dropped:
                    print(f"      ✗ [{REASONS[d['reason']]}] {d['text']}  ← {d['hit']}")
            log.append(
                {
                    "case": case["id"],
                    "model": gen.model,
                    "judge": judge.name,
                    "seconds": round(sec, 1),
                    "status": res.status,
                    "usage": dict(gen.usage),
                    **dataclasses.asdict(res),
                }
            )
    finally:
        judge.close()

    path = (
        out_dir
        / f"{stamp}_{'fake' if args.fake else args.model.replace(',', '+')}_{judge.name}.json"
    )
    path.write_text(json.dumps(log, ensure_ascii=False, indent=1), "utf-8")
    ok = sum(1 for x in log if x["status"] == "ok")
    gen_n = sum(r.get("generated", 0) for x in log for r in x["rounds"])
    kept_n = sum(len(x["kept"]) for x in log)
    print(
        f"\n합계 — 입력 {len(log)}개 중 3개 채움 {ok} · 후보 {gen_n} → 보관 {kept_n} · 로그 {path.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
