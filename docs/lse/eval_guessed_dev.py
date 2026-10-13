"""사전이 조용한 문장을 AI 추정 유형으로 고쳐 쓰면 후보가 얼마나 나오나 — dev 511 행 (2026-10-14 · 팀장 요청 · D-323 보충).

앱이 하는 그대로 한다 — 원문을 판정 코어에 넣고(`_core_judge` · 전제 층은 그 전제의 분기), 사전 유형이 없는 문장의
**인코더 추정 유형**(`reasons.guessed_types`)을 생성 서버에 넘기고, 고친 문장을 다시 판정한다(`_rewrite_sentence` 와 같은 규칙).

    uv run python docs/lse/eval_guessed_dev.py pick                              # ① 앱 venv — 사전이 조용한 문장 · 추정 유형
    .venv-sllm\\Scripts\\python.exe docs\\lse\\eval_guessed_dev.py gen            # ② GPU venv — 고쳐 쓰기(1단계 · 2단계 다듬기는 앱과 같이)
    uv run python docs/lse/eval_guessed_dev.py score                             # ③ 앱 venv — 재판정 · 비율

🚨 dev 만 쓴다(D-322 C). 이 결과로 관문 · 후처리 · 프롬프트 · 판정 규칙을 고르지 않는다 — 잴 뿐이다.
⛔ 출력에는 광고 문구가 든다 — `build/` 밖에 쓰지 않는다(D-249). 화면 · 문서에는 개수만 낸다.
"""

from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT)]

IN = ROOT / "build" / "eval" / "gen_inputs_dev.jsonl"
PICK = ROOT / "build" / "eval" / "guessed_pick_dev.jsonl"
OUT = ROOT / "build" / "eval" / "guessed_out_dev.jsonl"
SCORE = ROOT / "build" / "eval" / "guessed_score_dev.jsonl"


def _judge_branch(text: str, r: dict):  # noqa: ANN202 — Branch | JudgeResponse | None
    """원문 판정 — 전제 층은 품목 없이 판정해 그 전제의 분기 · 품목 층은 품목을 넘긴다 · 참고 층은 제품 정보 없이(앱과 같다)."""
    from app.contracts import Category, ProductContext  # noqa: PLC0415
    from app.routers import user as u  # noqa: PLC0415

    premise = r.get("전제") or ""
    category = None if premise else (r.get("품목") or None)
    st, jr = u._core_judge(text, ProductContext(category=Category(category)) if category else None)
    if st != "ok":
        return None
    return (u._branch_of(jr, premise) or jr) if premise else jr


def pick() -> None:
    from app import reasons  # noqa: PLC0415
    from eval_gen_dev import _sllm_category  # noqa: PLC0415

    rows = [json.loads(line) for line in IN.open(encoding="utf-8") if line.strip()]
    c = collections.Counter()
    with PICK.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            br = _judge_branch(r["text"], r)
            if br is None:
                c["판정 못 함"] += 1
                continue
            c["행"] += 1
            for s in br.sentences:
                if getattr(s, "not_claim", False):
                    continue
                c["문장"] += 1
                if s.violations:
                    continue
                c["사전 조용"] += 1
                g = reasons.guessed_types(s)
                if not g:
                    continue
                c["추정 유형 있음"] += 1
                f.write(json.dumps({"id": r["id"], "sid": getattr(s, "sent_id", None), "text": s.text, "guessed": g,
                                    "정답_유형": r["정답_유형"], "층": r["층"], "전제": r.get("전제"), "품목": r.get("품목"),
                                    "불가_사유": r.get("불가_사유"), "sllm_category": _sllm_category(r)},
                                   ensure_ascii=False) + "\n")
    print(dict(c), "→", PICK)


def gen() -> None:
    import persona_pipeline_e2e as pe  # noqa: PLC0415
    import sllm_meta  # noqa: PLC0415
    from sllm_service import _META, load  # noqa: PLC0415

    sllm_meta.permit_unlocked()  # 평가 도구 — 표지에 잠금 상태가 남는다(D-333)
    model, tok, ver = load()
    rows = [json.loads(line) for line in PICK.open(encoding="utf-8") if line.strip()]
    t0 = time.time()
    with OUT.open("w", encoding="utf-8", newline="\n") as fo:
        for i, r in enumerate(rows, 1):
            cat = r["sllm_category"]
            t = time.time()
            # 앱과 같다 — 다듬기는 식품 · 건기식 · 화장품에서만(`POLISH_CATEGORIES` · run_one 이 가른다)
            res = pe.run_one(model, tok, r["text"], r["guessed"], category=cat, polish=bool(_META.get("stage2")))
            fo.write(json.dumps({**r, "model": ver, "lock_stage1": _META.get("lock_stage1"),
                                 "ms": round((time.time() - t) * 1000), "res": res}, ensure_ascii=False) + "\n")
            fo.flush()
            if i % 10 == 0:
                print(f"{i}/{len(rows)} · {time.time() - t0:.0f}s", flush=True)
    print(f"끝 — {OUT} · {time.time() - t0:.0f}s", flush=True)


def score() -> None:
    from app.routers import user as u  # noqa: PLC0415

    rows = [json.loads(line) for line in OUT.open(encoding="utf-8") if line.strip()]
    out = []
    for x in rows:
        res = x["res"]
        premise = x.get("전제") or ""
        category = None if premise else (x.get("품목") or None)
        y = {k: x[k] for k in ("id", "층", "전제", "품목", "불가_사유", "정답_유형", "guessed", "model")}
        y["outcome"] = res["outcome"]
        y["guess_hits_gold"] = bool(set(x["guessed"]) & set(x["정답_유형"]))
        final = res.get("final")
        if res["outcome"] == "candidate" and final:
            rj = u._rejudge(final, premise, category)
            y["rejudge"] = rj["status"]
            y["enc_left"] = bool(rj.get("enc_types"))
            y["note_conflict"] = u._note_conflict(res.get("note"), premise, category)
            plain = res.get("stage1_final")
            if plain and plain != final and (rj["status"] == "rejected" or y["enc_left"]):
                pj = u._rejudge(plain, premise, category)  # 앱 — 다듬은 안이 떨어지면 담백한 안을 올린다
                if pj["status"] != "rejected" and not (y["enc_left"] and pj.get("enc_types")):
                    y["rejudge"], y["enc_left"], y["plain_used"] = pj["status"], bool(pj.get("enc_types")), True
        out.append(y)
    with SCORE.open("w", encoding="utf-8", newline="\n") as f:
        for y in out:
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    report(out)


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "0/0"


def report(out: list[dict]) -> None:
    n = len(out)
    oc = collections.Counter(y["outcome"] for y in out)
    print(f"\n추정 유형으로 고쳐 쓴 문장 {n} 개 · 모델 {out[0]['model'] if out else '?'}")
    print(f"  생성 — 후보 {_pct(oc['candidate'], n)} · 보류 {_pct(oc['hold'], n)} · 「만들지 못했어요」 {_pct(oc['infeasible'], n)}")
    cands = [y for y in out if y["outcome"] == "candidate"]
    rc = collections.Counter(y.get("rejudge") for y in cands)
    print(f"  재판정 — 탈락 {rc['rejected']} · 위반 못 찾음 {rc['no_violation']} · 판정 못 함 {rc['unjudged']} · 통과 {rc['passed']}")
    shown = [y for y in cands if y.get("rejudge") in ("no_violation", "passed") and not y.get("note_conflict")]
    left = [y for y in shown if y.get("enc_left")]
    print(f"  → 화면에 후보로 나가는 것 {_pct(len(shown), n)} · 그중 「AI 추정 유형 남음」 표시 {_pct(len(left), len(shown))}")
    print(f"  참고 — 추정 유형이 정답 유형과 하나라도 겹친 문장 {_pct(sum(y['guess_hits_gold'] for y in out), n)}")
    by = collections.defaultdict(collections.Counter)
    for y in out:
        k = y["전제"] or y["품목"] or "제품 정보 없음"
        by[k]["n"] += 1
        by[k]["shown"] += y in shown
    for k in sorted(by):
        print(f"    {k:<10} {by[k]['shown']}/{by[k]['n']}")


if __name__ == "__main__":
    {"pick": pick, "gen": gen, "score": score}[sys.argv[1]]()
