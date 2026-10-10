"""고쳐 쓰기(생성) 평가 — dev 511 행 · D-322 B 지표 (2026-10-11 · 팀장 전달 10-10 §3).

두 단계로 돈다 — 생성은 GPU venv, 재판정은 앱 venv(앱의 `_rejudge` · `_note_conflict` 를 그대로 부른다 · D-99).

    uv run python scripts/gen_eval_inputs.py --out build/eval/gen_inputs_dev.jsonl          # 입력(팀 정의)
    .venv-sllm\\Scripts\\python.exe docs\\lse\\eval_gen_dev.py gen                             # ① 생성 → build/eval/gen_out_dev.jsonl
    uv run python docs/lse/eval_gen_dev.py score                                             # ② 재판정 · 지표 → build/eval/gen_score_dev.*

★ 입력 한 행 = (문구 · 전제 또는 품목 · 정답 유형 · 불가 사유). 앱과 같은 규칙으로 넘긴다:
   · 전제 층 — 생성 서버에 그 전제의 품목(`pm.PREMISE_CATEGORY`) · 재판정은 그 전제의 분기로 읽는다(품목은 안 넘긴다 — 앱의 분기 경로)
   · 품목 층 — 생성 · 재판정 모두 품목 · 참고 층 — 제품 정보 없이
   · 위반 유형은 **골든 정답 유형**을 넘긴다 — 판정기의 오탐 · 미탐과 생성기의 몫을 가르려고(앱은 판정 결과를 넘긴다)
🚨 dev 만 쓴다(D-322 C). 봉인 평가셋을 넣지 않는다. 이 결과로 판정 규칙을 고르지 않는다(D-322 원칙).
🚨 이 결과로 관문 · 후처리 · 프롬프트를 고치지 않는다 — 고칠 때는 직접 만든 문제로 고르고 이것으로는 잰다(팀장 전달 10-05 §3 과 같은 뜻).
⛔ 출력에는 광고 문구가 든다 — `build/` 밖에 쓰지 않는다(D-249). 화면에는 개수만 낸다.
"""

from __future__ import annotations

import collections
import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT)]

IN = ROOT / "build" / "eval" / "gen_inputs_dev.jsonl"
OUT = ROOT / "build" / "eval" / "gen_out_dev.jsonl"
SCORE = ROOT / "build" / "eval" / "gen_score_dev.jsonl"
REVIEW = ROOT / "build" / "eval" / "gen_blindspot_review_dev.csv"


def _sllm_category(r: dict) -> str | None:
    """생성 서버에 넘기는 품목 — 앱의 `_sllm_category` 와 같은 규칙(전제 → 품목 · 없으면 품목 칸)."""
    from app import premise as pm  # noqa: PLC0415
    from app.contracts import Premise  # noqa: PLC0415

    if r.get("전제"):
        return pm.PREMISE_CATEGORY[Premise(r["전제"])].value
    return r.get("품목") or None


def gen() -> None:
    import persona_pipeline_e2e as pe  # noqa: PLC0415
    from sllm_service import _META, load  # noqa: PLC0415

    model, tok, ver = load()
    rows = [json.loads(line) for line in IN.open(encoding="utf-8") if line.strip()]
    done = set()
    if OUT.exists():  # 끊겼다 다시 돌리면 이어서 — 같은 판일 때만
        for line in OUT.open(encoding="utf-8"):
            x = json.loads(line)
            if x.get("model") == ver:
                done.add(x["id"])
    t0 = time.time()
    with OUT.open("a", encoding="utf-8", newline="\n") as fo:
        for i, r in enumerate(rows, 1):
            if r["id"] in done:
                continue
            cat = _sllm_category(r)
            t = time.time()
            res = pe.run_one(model, tok, r["text"], r["정답_유형"], category=cat)
            fo.write(json.dumps({**r, "sllm_category": cat, "model": ver, "adapter_sha": _META.get("adapter_sha"),
                                 "ms": round((time.time() - t) * 1000), "res": res}, ensure_ascii=False) + "\n")
            fo.flush()
            if i % 25 == 0:
                print(f"{i}/{len(rows)} · {time.time() - t0:.0f}s", flush=True)
    print(f"끝 — {OUT} · {time.time() - t0:.0f}s", flush=True)


# ── ② 재판정 · 지표 ────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")


def _content_tokens(text: str) -> list[str]:
    """원문의 내용 낱말(조사 뗀 두 글자 이상) — 사실 보존율의 분모."""
    from stage_gate import _PARTICLE  # noqa: PLC0415

    out = []
    for w in _TOKEN.findall(text):
        s = _PARTICLE.sub("", w) if len(w) > 2 else w
        if len(s) >= 2:
            out.append(s)
    return out


def _violation_tokens(text: str) -> set[str]:
    """위반 표현에 든 낱말 — 지워야 맞는 것이라 보존율에서 뺀다(사전 전 항목 · 관문의 질병 · 의약품 표현)."""
    from stage_gate import DISEASE, DRUG, dm  # noqa: PLC0415

    spans = [h.span for h in dm.find(text, _all_entries()) if h.span]
    spans += [m.span() for p in (DISEASE, DRUG) for m in p.finditer(text)]
    toks = list(_TOKEN.finditer(text))
    bad = set()
    for i, m in enumerate(toks):
        if any(a < m.end() and m.start() < b for a, b in spans):
            bad.add(m.group())
            # 위반 낱말 바로 뒤 한 낱말은 그 주장의 동사다(「고혈압 낮추는」 · 「암을 이기는」) — 지워야 맞다
            if i + 1 < len(toks):
                bad.add(toks[i + 1].group())
    return {t for w in bad for t in _content_tokens(w)}


def _all_entries() -> tuple:
    """사전 **전 항목**(단독판정 자격과 무관) — 보존율에서 「지워야 맞는 낱말」을 빼는 데만 쓴다."""
    global _ALL
    if _ALL is None:
        from stage_gate import DICT, dm  # noqa: PLC0415

        _ALL = tuple(dm.Entry(term=json.loads(line)["term"], violation_type=None) for line in DICT.open(encoding="utf-8") if line.strip())
    return _ALL


_ALL: tuple | None = None


def fact_retention(original: str, out: str) -> float | None:
    """사실 문구 보존율(대리 지표) — 위반 낱말을 뺀 원문 내용 낱말 중 출력에 남은 비율. 분모가 0 이면 None."""
    from stage_gate import dm  # noqa: PLC0415

    bad = _violation_tokens(original)
    toks = [t for t in dict.fromkeys(_content_tokens(original)) if t not in bad]
    if not toks:
        return None
    o = dm.norm(out)
    return sum(dm.norm(t) in o for t in toks) / len(toks)


def score() -> None:
    from app.routers import sllm_client  # noqa: PLC0415
    from app.routers import user as u  # noqa: PLC0415
    from stage_gate import _claim_word, new_words  # noqa: PLC0415

    rows = [json.loads(line) for line in OUT.open(encoding="utf-8") if line.strip()]
    scored = []
    for x in rows:
        res = x["res"]
        premise = x.get("전제") or ""
        category = None if premise else (x.get("품목") or None)  # 앱 — 분기 경로는 재판정에 품목을 안 넘긴다
        raw = res.get("stage1")
        final = res.get("final")
        note = res.get("note")
        y = {k: x[k] for k in ("id", "층", "전제", "품목", "불가_사유", "정답_유형", "model")}
        y["outcome"] = res["outcome"]
        y["ms"] = x["ms"]
        # 관문 전 · 후 낱말 삽입 — 「도움」 문장의 인정 문구 낱말은 뺀다(관문과 같은 규칙)
        def ins(s: str | None) -> bool:
            if not s:
                return False
            nw = new_words(x["text"], s)
            if "도움" in s:
                nw = [w for w in nw if not _claim_word(w)]
            return bool(nw)
        y["insert_raw"] = ins(raw)
        y["insert_final"] = ins(final)
        y["note"] = note
        if final:
            rj = u._rejudge(final, premise, category)
            y["rejudge"] = rj["status"]
            y["rejudge_violations"] = rj.get("violations", [])
            y["new_type"] = bool(set(rj.get("violations", [])) - set(x["정답_유형"]))
            y["note_conflict"] = u._note_conflict(note, premise, category)
            y["fact_keep"] = fact_retention(x["text"], final)
            # 인코더 후보 — 사각지대 검수의 참고(판정은 사전 근거로만 · D-323)
            st, jr = u._core_judge(final, None)
            if st == "ok":
                br = (u._branch_of(jr, premise) if premise else None) or jr
                y["encoder_types"] = sorted({c.violation.value for s in br.sentences for c in (getattr(s, "encoder_candidates", None) or [])})
                y["judged_by"] = getattr(jr, "judged_by", None)
        scored.append(y)
    with SCORE.open("w", encoding="utf-8", newline="\n") as f:
        for y in scored:
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    report(scored, rows, sllm_client.NOTE_RECOGNIZED_HF)


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "0/0"


def report(scored: list[dict], rows: list[dict], note_hf: str) -> None:
    n = len(scored)
    print(f"\n고쳐 쓰기 dev 평가 — {n} 행 · 모델 {scored[0]['model'] if scored else '?'}")
    print("\n[1] 생성 결과 (층 · 불가 사유별)")
    by = collections.defaultdict(collections.Counter)
    for y in scored:
        key = f"{y['층']} · {y['전제'] or y['품목'] or '제품 정보 없음'} · {y['불가_사유']}"
        by[key][y["outcome"]] += 1
    for k in sorted(by):
        c = by[k]
        print(f"  {k:<28} 후보 {c['candidate']:>3} · 보류 {c['hold']:>3} · 불가 {c['infeasible']:>3}")
    tot = collections.Counter(y["outcome"] for y in scored)
    print(f"  {'합':<28} 후보 {tot['candidate']:>3} · 보류 {tot['hold']:>3} · 불가 {tot['infeasible']:>3}")

    cands = [y for y in scored if y["outcome"] == "candidate"]
    print(f"\n[2] 재판정 분포 — 후보 {len(cands)} 개 (D-322 B · 통과는 D-323 으로 닫혀 있다)")
    rc = collections.Counter(y.get("rejudge") for y in cands)
    for k, lab in (("rejected", "탈락"), ("no_violation", "위반 못 찾음"), ("unjudged", "판정 못 함"), ("passed", "통과"), ("unavailable", "판정기 없음")):
        print(f"  {lab:<8} {_pct(rc[k], len(cands))}")
    nc = [y for y in cands if y.get("note_conflict")]
    print(f"  조건이 전제에서 채워질 수 없음(앱이 후보로 안 냄 · _note_conflict) {_pct(len(nc), len(cands))}")
    shown = [y for y in cands if y.get("rejudge") in ("no_violation", "passed") and not y.get("note_conflict")]
    print(f"  → 화면에 후보로 나가는 것 {_pct(len(shown), n)} (입력 대비)")

    fk = [y["fact_keep"] for y in cands if y.get("fact_keep") is not None]
    print(f"\n[3] 사실 문구 보존율(대리 · 위반 낱말을 뺀 원문 낱말 중 남은 비율) — 후보 {len(fk)} · 평균 {statistics.mean(fk):.2f} · 중앙 {statistics.median(fk):.2f}" if fk else "\n[3] 사실 보존 — 후보 없음")

    raws = [y for y in scored if y["outcome"] != "infeasible"]
    print("\n[4] 낱말 삽입률 — 원문에 없는 낱말(인정 문구 낱말 제외)")
    print(f"  관문 전(모델 출력) {_pct(sum(y['insert_raw'] for y in raws), len(raws))} · 관문 후(후보) {_pct(sum(y['insert_final'] for y in cands), len(cands))}")
    rej = [y for y in cands if y.get("rejudge") == "rejected"]
    print(f"[5] 새 위반 유형 비율 — 후보 중 재판정이 정답에 없던 유형을 낸 것 {_pct(sum(y.get('new_type', False) for y in cands), len(cands))} (탈락 {len(rej)} 중 {sum(y.get('new_type', False) for y in rej)})")

    food = [y for y in scored if y["층"] == "전제" and y["전제"] == "식품"]
    fh = [y for y in food if y["outcome"] == "candidate" and y.get("note") == note_hf]
    print(f"\n[6] 🔴 식품 전제 {len(food)} 행 중 「{note_hf}」 조건을 단 후보 {_pct(len(fh), len(food))}"
          f" — 그중 앱이 거른 것(_note_conflict) {sum(bool(y.get('note_conflict')) for y in fh)}")
    other = collections.Counter((y["전제"] or y["품목"] or "없음") for y in scored if y["outcome"] == "candidate" and y.get("note") == note_hf)
    print(f"  같은 조건 — 층별 {dict(other)}")

    nv = [y for y in cands if y.get("rejudge") == "no_violation" and not y.get("note_conflict")]
    enc = sum(bool(y.get("encoder_types")) for y in nv)
    print(f"\n[7] 사각지대(D-38) — 「위반 못 찾음」 후보 {len(nv)} 개는 사람이 검수해야 잰다 → {REVIEW.name}")
    print(f"  참고 — 그중 인코더 후보가 걸린 것 {_pct(enc, len(nv))} (판정 아님 · D-323)")
    ms = [y["ms"] for y in scored]
    print(f"\n[8] 지연 — 문장당 중앙 {statistics.median(ms) / 1000:.1f}초 · 최대 {max(ms) / 1000:.1f}초")
    src = {r["id"]: r for r in rows}
    with REVIEW.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "층", "전제/품목", "정답_유형", "원문", "고친 문구", "조건", "인코더 후보(참고)", "사람 판정(적법/위법/애매)", "메모"])
        for y in nv:
            r = src[y["id"]]
            w.writerow([y["id"], y["층"], y["전제"] or y["품목"] or "", ",".join(y["정답_유형"]), r["text"],
                        r["res"].get("final"), r["res"].get("note") or "", ",".join(y.get("encoder_types") or []), "", ""])


if __name__ == "__main__":
    {"gen": gen, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "score"]()
