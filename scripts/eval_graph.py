"""scripts/eval_graph.py — **그래프 평가 도구 (W1)**. 판정 그래프를 봉인 평가셋(`test_sentence`)에 돌려 잰다.

    uv run python scripts/eval_graph.py                          # 정본 기기 · 실제 DB · 전부
    uv run python scripts/eval_graph.py --limit 200              # 앞 200행만(실행 시간을 먼저 잰다)
    uv run python scripts/eval_graph.py --provenance ftc_decisions_body
    uv run python scripts/eval_graph.py --stub                   # DB 없이 — 배선만(전부 미판정 · 수는 0 이 정상)
    uv run python scripts/eval_graph.py --out build/eval/graph.json

★ **무엇을 답하나** (설계초안 09-23 W1 · D-269 · D-275 · D-301) —
  ① 응답 분포 — 문장 판정 상태 · 종착 · **보류율을 사유별로** (D-269 「게이트 수는 보류율을 사유별로 함께」)
  ② 유형 · 호 P/R/F1 — 예측 = **확정 문장의 위반만**(보류 · 근거없음 · 미판정은 예측이 아니다 · D-127). 30 미만은 측정 불가 (D-40)
  ③ selective risk — 판정을 내린 행(전 문장 확정) 중 틀린 비율 · coverage 와 쌍으로 (D-77 L1 #8)
  ④ 조건별 대응표 — 라벨 조건(C/A/B/M/D/L) × 응답 (D-275 가 W1 몫으로 넘긴 표)
  ⑤ 적법 문장 오탐률 — 내역(주장 있음 · 주장 없음)과 함께만 (D-301)
🔴 **채점 규칙은 판정기 B 와 한 곳이다** — `scored` · `truth_types` · `truth_ho` · `lawful_report` · D-40 문턱을
   `scripts/eval_rule.py` 에서 가져온다 (D-99). 판정기 B 와 그래프의 수가 같은 자로 재진다.
🚨 **봉인 평가셋으로 규칙을 고르지 않는다** (D-175) — 이 수는 보고용이다. 규칙 · 문턱을 이 수에 맞춰 고치면 누수다.
🚨 조건부 평가(품목을 아는 경우)는 **측정 불가** — 골든셋에 품목 칸이 없다(판정 대기). 무조건부(품목 미확정 · 세 법)만 잰다.
🚨 게이트가 아니다 — 답이 기기마다 다르다(`data/**` 미커밋 · D-19). 수는 원장에 기기 · 커밋 · 골든 sha 와 함께 적는다 (D-178).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import graph as g  # noqa: E402
from app.contracts import ProductContext, SentenceJudgment, Verdict  # noqa: E402
from collect import statute  # noqa: E402
from preprocess.golden import lawful_kind  # noqa: E402
from scripts.eval_rule import (  # noqa: E402 — 채점 규칙은 한 곳 (D-99)
    MIN_MEASURABLE,
    lawful_report,
    print_lawful,
    scored,
    truth_ho,
    truth_types,
)

GOLDEN = pathlib.Path("data/derived/golden/golden.jsonl")
#: DB 사전 대조의 기준 — 적재기(`scripts/load_db.py` `load_dict`)가 읽는 바로 그 파일
DICT_FILE = pathlib.Path("data/derived/banned_terms.jsonl")

#: 행 하나의 응답 갈래 — 조건별 대응표(D-275)와 selective risk 가 같이 쓴다.
#: 🔴 「확정 위반」은 **전 문장 확정 ∧ 위반 있음**이 아니라 **위반을 확정한 문장이 하나라도** — 예측의 정의와 같다.
CLASSES = ("확정위반", "확정무위반", "보류", "근거없음", "미판정")


def load_rows(path: pathlib.Path = GOLDEN, provenance: str | None = None) -> list[dict]:
    """봉인 평가셋 행. 🔴 파일이 없으면 멈춘다 — 빈 목록으로 0 을 내지 않는다 (D-220)."""
    if not path.exists():
        raise SystemExit(
            f"🔴 {path} 가 없다 — 정본은 `launcher.py golden --write` · 사본은 `data-sync`"
        )
    rows = [
        r
        for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())
        if r["split"] == "test_sentence"
    ]
    if provenance:
        rows = [r for r in rows if r.get("provenance") == provenance]
    return rows


# ── 한 행 → 예측 ────────────────────────────────────────────────────────


def _ho(sent: SentenceJudgment) -> set[str]:
    """확정 문장의 근거 중 **인용 꼴로 되돌릴 수 있는 것**의 호. 검색 근거(「[별표 1]…」)는 호로 못 돌린다 — 세지 않는다."""
    out = set()
    for a in sent.evidence:
        try:
            out.add(statute.ho_key(f"{a.law_id}:{a.article}{a.item}"))
        except ValueError:
            continue
    return out


def predict(state: dict[str, Any]) -> dict[str, Any]:
    """그래프 상태 → 행 예측. 예측 유형 · 호는 **확정 문장의 위반만**이다 (D-127 · 보류는 예측이 아니다)."""
    sents: list[SentenceJudgment] = list(state.get("sentences", []))
    conf = [s for s in sents if s.verdict is Verdict.confirmed]
    types = sorted({v.value for s in conf for v in s.violations})
    ho = sorted({h for s in conf if s.violations for h in _ho(s)})
    verdicts = [s.verdict.value for s in sents]
    if any(s.violations for s in conf):
        cls = "확정위반"
    elif sents and len(conf) == len(sents):
        cls = "확정무위반"
    elif any(s.verdict is Verdict.unjudged for s in sents) or not sents:
        cls = "미판정"
    elif any(s.verdict is Verdict.hold for s in sents):
        cls = "보류"
    else:
        cls = "근거없음"
    outcome = state.get("outcome")
    return {
        "outcome": getattr(outcome, "value", outcome),
        "verdicts": verdicts,
        "hold_reasons": sorted({s.hold_reason.value for s in sents if s.hold_reason is not None}),
        "types": types,
        "ho": ho,
        "class": cls,
        #: 판정을 내린 행 — **전 문장이 확정**이다(selective risk 의 분모 · D-77 L1 #8)
        "committed": bool(sents) and len(conf) == len(sents),
        "n_sents": len(sents),
    }


# ── 집계 ────────────────────────────────────────────────────────────────


def _prf(gold: int, tp: int, fp: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / gold if gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def summarize(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """행 · 예측 → 수. 🔴 순수 함수 — 게이트가 대역 예측으로 잰다."""
    assert len(rows) == len(preds)
    n = len(rows)
    out: dict[str, Any] = {"rows": n}
    out["outcome"] = dict(collections.Counter(p["outcome"] for p in preds))
    out["verdict"] = dict(collections.Counter(v for p in preds for v in p["verdicts"]))
    out["class"] = dict(collections.Counter(p["class"] for p in preds))
    # 보류율 — 사유별(행 단위 · 한 행에 사유가 여럿이면 각각 센다) · 「위험도 없음」은 문장이 전부 확정인데 종착이 보류인 행
    held = [p for p in preds if p["outcome"] == "hold"]
    reasons: collections.Counter = collections.Counter()
    for p in held:
        if p["hold_reasons"]:
            reasons.update(p["hold_reasons"])
        elif p["committed"]:
            reasons["하한없음(W5)"] += 1
        elif "unjudged" in p["verdicts"]:
            reasons["미판정"] += 1
        else:
            reasons["근거없음"] += 1
    out["hold_rate"] = len(held) / n if n else 0.0
    out["hold_reasons"] = dict(reasons)
    # 조건별 대응표 (D-275)
    table: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r, p in zip(rows, preds, strict=True):
        table[r.get("조건") or "-"][p["class"]] += 1
    out["by_condition"] = {k: dict(v) for k, v in sorted(table.items())}
    # 유형 · 호 — 채점 행만 (M · D 는 빼고 뺀 수를 보인다 · eval_rule 과 같다)
    gold_t, tp_t, fp_t = collections.Counter(), collections.Counter(), collections.Counter()
    gold_h, tp_h, fp_h = collections.Counter(), collections.Counter(), collections.Counter()
    committed = errors = 0
    sc = [(r, p) for r, p in zip(rows, preds, strict=True) if scored(r)]
    for r, p in sc:
        pt, ph = set(p["types"]), set(p["ho"])
        tt, th = truth_types(r, pt), truth_ho(r, ph)
        for t in tt:
            gold_t[t] += 1
            tp_t[t] += t in pt
        for t in pt - tt:
            fp_t[t] += 1
        laws = {statute.parse(c)[0] for c in th}
        for c in th:
            gold_h[c] += 1
            tp_h[c] += c in ph
        for c in ph - th:
            if (
                not th or statute.parse(c)[0] in laws
            ):  # 오탐은 정답의 법 안에서만 (eval_rule.ho_scores 와 같다)
                fp_h[c] += 1
        if p["committed"]:
            committed += 1
            wrong = (not tt and pt) or (tt and not (pt & tt))
            errors += bool(wrong)
    out["scored_rows"] = len(sc)
    out["unscored_rows"] = n - len(sc)
    out["types"] = {t: (gold_t[t], tp_t[t], fp_t[t]) for t in sorted(set(gold_t) | set(fp_t))}
    out["ho"] = {c: (gold_h[c], tp_h[c], fp_h[c]) for c in sorted(set(gold_h) | set(fp_h))}
    out["coverage"] = committed / len(sc) if sc else 0.0
    out["selective_risk"] = errors / committed if committed else None
    out["committed"] = committed
    # 적법 문장 (D-301) — 「울림」= 위반을 확정한 문장이 있다
    flag = {id(r): p["class"] == "확정위반" for r, p in zip(rows, preds, strict=True)}
    by_text: dict[str, bool] = {}
    for r in rows:
        by_text[r["text"]] = by_text.get(r["text"], False) or flag[id(r)]
    out["lawful"] = lawful_report(rows, lambda t: by_text.get(t, False))
    out["lawful_rows_seen"] = sum(1 for r in rows if lawful_kind(r))
    return out


def report(s: dict[str, Any]) -> None:
    print(
        f"그래프 평가 — 평가셋 {s['rows']}행 (채점 {s['scored_rows']} · 채점 밖 M · D {s['unscored_rows']})"
    )
    print(f"  종착   {s['outcome']}")
    print(f"  문장   {s['verdict']}")
    print(f"  행     {s['class']}")
    print(f"  보류율 {s['hold_rate']:.1%} — 사유별 {s['hold_reasons']}")
    print("\n  조건별 대응표 (D-275 · 행 수)")
    for k, v in s["by_condition"].items():
        print(f"    {k:>2}  " + "  ".join(f"{c} {v.get(c, 0)}" for c in CLASSES))
    for name, tab in (("유형", s["types"]), ("호 (정본 · D-282)", s["ho"])):
        print(f"\n  {name:26} {'정답':>5} {'P':>7} {'R':>7} {'F1':>7}")
        for k, (gold, tp, fp) in tab.items():
            p, r, f = _prf(gold, tp, fp)
            mark = "  🔴 측정 불가 (D-40)" if gold < MIN_MEASURABLE else ""
            if gold == 0:
                mark = f"  🚨 정답 0인데 오탐 {fp}건"
            print(f"  {k:26} {gold:>5} {p:>7.3f} {r:>7.3f} {f:>7.3f}{mark}")
    sr = s["selective_risk"]
    print(
        f"\n  selective risk {('-' if sr is None else f'{sr:.1%}')} · coverage {s['coverage']:.1%} "
        f"(판정을 내린 행 {s['committed']} / 채점 {s['scored_rows']})"
    )
    print_lawful(s["lawful"])
    print("\n  🔴 조건부 평가(품목을 아는 경우)는 측정 불가 — 골든셋에 품목 칸이 없다")
    print("  🚨 봉인 평가셋이다 — 이 수에 맞춰 규칙 · 문턱을 고르지 않는다 (D-175)")


# ── 실행 ────────────────────────────────────────────────────────────────


def _sha12(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _key(e: Any) -> tuple[str, str | None, tuple[str, ...]]:
    return (e.term, e.violation_type, tuple(e.basis))


def dict_drift(db: Iterable[Any], file_rows: Iterable[dict]) -> dict[str, int]:
    """DB 의 단독판정 사전(`graph.load_dict_entries`) ↔ 사전 파일 — 어긋난 **수**만 (용어는 싣지 않는다 · ND 면제 조건).

    🆕 2026-10-01 (원장 10-01 ⑦) — A 기기 DB 에 동결 09-30 이전 사전이 남아 **봉인 평가 문서의 문구**가 걸렸다.
       ⛔ 평가 도구가 DB 사전의 판을 몰라 그 수가 정본처럼 찍혔다 — 없음 · 낡음이 성공으로 집계됐다 (D-220 · D-174).
    🔴 파일 쪽 변환은 적재기와 **한 함수**(`load_db.dict_row`)다 (D-99) — 「단독판정 항목만」도 그래프의 `SQL_DICT` 와 같은 거름.
    """
    from scripts.load_db import dict_row  # noqa: PLC0415 — 적재기의 변환을 그대로 (D-99)

    want = {}
    for term, law_ref, exact, vt in map(dict_row, file_rows):
        if exact:
            want[term] = (term, vt, tuple(b.strip() for b in law_ref.split(";") if b.strip()))
    have = {e.term: _key(e) for e in db}
    return {
        "db_only": len(have.keys() - want.keys()),
        "file_only": len(want.keys() - have.keys()),
        "changed": sum(have[t] != want[t] for t in have.keys() & want.keys()),
        "file": len(want),
        "db": len(have),
    }


def check_dict(cur: Any, path: pathlib.Path = DICT_FILE) -> dict[str, Any]:
    """DB 사전이 파일과 같아야 돈다 — 🔴 다르면 **멈춘다** (D-220). 같으면 판 표지(sha · 수)를 돌려준다(D-178)."""
    if not path.exists():
        raise SystemExit(f"🔴 {path} 가 없다 — DB 사전과 대조할 기준이 없다 (D-220)")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    d = dict_drift(g.load_dict_entries(cur), rows)
    if d["db_only"] or d["file_only"] or d["changed"]:
        raise SystemExit(
            f"🔴 DB 사전이 {path} 와 다르다 — DB 에만 {d['db_only']} · 파일에만 {d['file_only']} · "
            f"값이 다름 {d['changed']} (단독판정 · 파일 {d['file']} · DB {d['db']})\n"
            "  이대로 재면 다른 판 사전의 수가 정본처럼 찍힌다(봉인 문서 문구가 걸릴 수 있다 · D-174).\n"
            "  먼저: uv run python launcher.py load"
        )
    return {"dict_sha": _sha12(path), "dict_entries": d["file"]}


def stub_runner() -> Callable[[str], dict[str, Any]]:
    """DB 없이 — 스텁 한 바퀴(`run_review_stub`). 사전을 못 훑어 전부 미판정이다 — 배선만 본다."""
    return lambda text: g.run_review_stub(text)[0]


def run(
    rows: Iterable[dict], runner: Callable[[str], dict[str, Any]], every: int = 100
) -> list[dict]:
    preds = []
    t0 = time.perf_counter()
    for k, r in enumerate(rows, 1):
        preds.append(predict(runner(r["text"])))
        if every and k % every == 0:
            print(f"  … {k}행 · {time.perf_counter() - t0:.0f}초", file=sys.stderr)
    return preds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--provenance")
    ap.add_argument("--stub", action="store_true", help="DB 없이 배선만")
    ap.add_argument("--out", type=pathlib.Path, help="수 · 행 예측을 JSON 으로")
    a = ap.parse_args(argv)
    rows = load_rows(provenance=a.provenance)
    if a.limit:
        rows = rows[: a.limit]
    #: 판 표지 — 원장에 수와 함께 적는다 (D-178). 🔴 실제 실행은 DB 사전이 파일과 같을 때만 돈다(`check_dict`)
    stamp: dict[str, Any] = {"golden_sha": _sha12(GOLDEN)}
    t0 = time.perf_counter()
    if a.stub:
        preds = run(rows, stub_runner())
    else:
        from app.db import pg_connect  # noqa: PLC0415 — DB 가 없어도 --stub 은 돈다

        review = g.build_review()
        with pg_connect() as conn, conn.cursor() as cur:
            stamp |= check_dict(cur)
            cfg = {"configurable": {"conn": cur}}
            preds = run(
                rows, lambda t: review.invoke({"text": t, "product": ProductContext()}, config=cfg)
            )
    secs = time.perf_counter() - t0
    s = summarize(rows, preds)
    report(s)
    print(
        f"\n  실행 {secs:.0f}초 · 행당 {secs / max(len(rows), 1) * 1000:.0f} ms · judged_by {g.JUDGED_BY}"
        f" · " + " · ".join(f"{k} {v}" for k, v in stamp.items())
    )
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(
            json.dumps(
                {
                    "summary": s,
                    "judged_by": g.JUDGED_BY,
                    "stub": a.stub,
                    **stamp,
                    "rows": [{"id": r["id"], **p} for r, p in zip(rows, preds, strict=True)],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
