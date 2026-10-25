"""검수 화면 「답한 주장은 풀렸지만 … (추정)」 줄이 서버 판정과 어긋나는 문장 수 세기 (2026-10-22 · 박수진).

  uv run python docs\\psj\\e2e_prototype\\count_left_claims.py
  uv run python docs\\psj\\e2e_prototype\\count_left_claims.py --limit 100    # 빠른 확인

★ 왜 — 전달받은 검토: 그 줄의 「남은 주장」을 화면(`app/templates/user/review.html` · `left`)이 서버와 다른 규칙으로 계산한다(D-99).
   코드만 읽은 지적이라 실제 문장으로 몇 건인지 센다.
★ 어떻게 — `scripts/eval_graph.py` 의 답 경로(`--answers` · 보충 35)와 같은 방식: 확장 dev 조건부 행을 판정하고, 선 질문에 모두 같은 답
   (예 · 아니오 · 해당없음)을 하고 다시 판정(최대 3회). 마지막 응답의 문장(기록 문장 + 보이는 분기 문장)마다 화면과 같은 조건을 본다.
     화면 줄이 뜸   = 보류 · hold_kind 「unconfirmed」 · 실증 답(user_substs)이 있음 · left(인코더 추정 − 답한 유형)가 비지 않음
     ⑤ 빈 유형 답  = 답의 유형이 비어 있음 → 방금 답한 유형까지 「남은 주장」으로 나옴
     ③ 「예」인데 보류 = 화면은 「풀렸지만」이라 쓰지만 서버는 풀지 않음
     ② 「해당없음」 = 서버는 풀림이 아니라고 봄 · 화면은 풀린 것으로 침
     ① 판정 밖 유형 = left 에 근거 유형(risk.encoder_basis)에 없는 추정 유형이 섞임
🔴 문장 원문은 결과에 싣지 않는다 — 수와 골든 id 만. 판정을 바꾸지 않는다(읽기만).
결과 — `build/eval/left_claims_<날짜>.json` (git 밖)
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.contracts import Answer, HoldKind, UserFact, UserSubst, Verdict, Violation  # noqa: E402
from scripts import eval_graph as eg  # noqa: E402

ROUNDS = eg.ANSWER_ROUNDS


def _sentences(st: dict) -> list:
    return list(st.get("sentences", [])) + [x for b in st.get("branches", []) for x in b.sentences]


def _answer_until_done(runner, text: str, product, first: dict, answer: Answer) -> dict:
    """eval_graph.answer_path 와 같은 돌림 — 마지막 상태를 돌려준다(그쪽은 요약만 낸다)."""
    from app.contracts import FactKind  # noqa: PLC0415

    facts, substs = list(product.facts), list(product.substs)
    asked: set = set()
    st = first
    for _ in range(ROUNDS):
        new = [q for q in eg._open_questions(st) if q not in asked]  # noqa: SLF001
        if not new:
            break
        for t, kind, fk in new:
            asked.add((t, kind, fk))
            if kind == "fact":
                facts.append(UserFact(text=t, kind=FactKind(fk), answer=answer))
            else:
                substs.append(UserSubst(text=t, answer=answer, violation=Violation(fk) if fk else None))
        st = runner(text, product.model_copy(update={"facts": facts, "substs": substs}))
    return st


def _screen_left(x) -> list:
    """화면(review.html 459 ~ 463행)과 같은 계산 — 보류 · unconfirmed · 실증 답 있음일 때 left."""
    if x.verdict is not Verdict.hold or x.hold_kind is not HoldKind.unconfirmed or not x.user_substs:
        return []
    answered = {u.violation for u in x.user_substs}
    return [c for c in x.encoder_candidates if c.violation not in answered]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    rows = eg.conditional_rows(eg.load_rows(dev=True, guide_dev=True))
    rows = rows[: a.limit] if a.limit else rows
    stamp = {"golden_sha": eg._sha12(eg.GOLDEN), "rows": len(rows)}  # noqa: SLF001
    stamp |= eg.use_encoder(None)
    from app import graph as g  # noqa: PLC0415
    from app.db import pg_connect  # noqa: PLC0415

    review = g.build_review()
    count: dict[str, collections.Counter] = {}
    ids: dict[str, dict[str, list[str]]] = {}
    with pg_connect() as conn, conn.cursor() as cur:
        stamp |= eg.check_dict(cur)
        cfg = {"configurable": {"conn": cur}}

        def runner(t, p):  # noqa: ANN001, ANN202
            return eg._checked(review.invoke({"text": t, "product": p}, config=cfg))  # noqa: SLF001

        asked_rows = 0
        for k, r in enumerate(rows, 1):
            product = eg.product_of(r, True)
            first = runner(r["text"], product)
            if not eg._open_questions(first):  # noqa: SLF001
                continue
            asked_rows += 1
            for ans in (Answer.예, Answer.아니오, Answer.해당없음):
                c = count.setdefault(ans.value, collections.Counter())
                bucket = ids.setdefault(ans.value, collections.defaultdict(list))
                st = _answer_until_done(runner, r["text"], product, first, ans)
                seen = set()
                for x in _sentences(st):
                    key = (x.text, x.verdict.value)
                    if key in seen:
                        continue
                    seen.add(key)
                    left = _screen_left(x)
                    if not left:
                        continue
                    c["화면 줄이 뜸"] += 1
                    bucket["화면 줄이 뜸"].append(r["id"])
                    if any(u.violation is None for u in x.user_substs):
                        c["⑤ 빈 유형 답(방금 답한 유형도 남은 주장)"] += 1
                        bucket["⑤"].append(r["id"])
                    if ans is Answer.예:
                        c["③ 「예」인데 보류(서버는 안 풀림)"] += 1
                        bucket["③"].append(r["id"])
                    if ans is Answer.해당없음:
                        c["② 「해당없음」(서버는 풀림 아님)"] += 1
                        bucket["②"].append(r["id"])
                    basis = {b.violation for b in x.risk.encoder_basis}
                    if any(lv.violation not in basis for lv in left):
                        c["① 판정 밖 추정 유형이 섞임"] += 1
                        bucket["①"].append(r["id"])
            if k % 100 == 0:
                print(f"  … {k}/{len(rows)}행 · 질문 선 행 {asked_rows}")
    stamp["asked_rows"] = asked_rows
    print(f"\n골든 {stamp['golden_sha']} · 조건부 확장 dev {len(rows)}행 · 질문이 선 행 {asked_rows}")
    for ans, c in count.items():
        print(f"\n[모두 「{ans}」로 답했을 때]")
        if not c:
            print("  화면 줄이 뜨는 문장 없음")
        for name, n in c.items():
            print(f"  {name}: {n}")
    out = ROOT / "build" / "eval" / f"left_claims_{dt.date.today():%Y%m%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"stamp": stamp, "counts": {k: dict(v) for k, v in count.items()},
             "ids": {k: {n: sorted(set(v)) for n, v in b.items()} for k, b in ids.items()}},
            ensure_ascii=False, indent=2, default=str,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"\n✅ {out.relative_to(ROOT)} (문장 원문 없음 · 골든 id 만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
