"""scripts/eval_diff.py — **평가 결과 파일 대조** (🆕 2026-10-21 · D-348 보충 35 결정 2 · 인계 10-21 클론B §0-3).

    uv run python scripts/eval_diff.py diff build/eval/<앞>.json build/eval/<뒤>.json          # 행 단위 차이 · 분류 이동
    uv run python scripts/eval_diff.py diff <앞> <뒤> --show 30 --field class --field types    # 보일 칸 · 줄 수
    uv run python scripts/eval_diff.py equiv build/eval/<품목만>.json build/eval/<고른전제>.json  # 경로 동치

★ **무엇을 답하나**
  ① `diff` — 같은 행(`id`)의 칸이 두 판에서 얼마나 바뀌었나 · 분류(`class`)가 어디서 어디로 갔나. 고침마다 원장에 적는
     「바뀐 행 · 바뀐 칸」을 손 셈 대신 이 도구로 낸다(원장 10-21 ④ · ⑤ 의 셈법).
  ② `equiv` — **경로가 달라도 판정이 같은가**(결함 A 꼴의 그물). 짝:
       · 품목만 넘긴 판정(`eval_graph --dev --guide-dev --conditional --category-only`)
       · 전제를 고른 판정(`eval_graph --dev --guide-dev --conditional`)
     골든 `전제` 가 있는 행마다 「전제를 고른 기록」 = 「품목만 넘긴 판정의 그 전제 분기」(분기가 접혔으면 그 기록)를 맞댄다
     (보충 34 결정 1 의 동치 · `tests/test_premise_chosen.py` 를 dev 전 행으로). 어긋난 행이 있으면 1 로 끝난다.
🚨 판정을 하지 않는다 — 결과 파일만 읽는다(DB · 모델 없음). 게이트가 아니다 · 수는 원장에 두 파일의 판 표지와 함께 적는다(D-178).
🔴 칸이 없는 옛 결과 파일(10-21 보충 35 전)로는 `equiv` 를 하지 않는다 — 없는 칸을 「같다」로 세지 않는다(D-220).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

#: 경로 동치에서 맞대는 칸 — 판정 · 사유 · 위반 · 질문(분기 · 기록 모두 있는 칸 · `eval_graph._branch_view` 와 `predict` 의 같은 이름).
#: ⛔ 후보(`candidates` · `enc_candidates`)는 넣지 않는다 — 판정이 아니고(D-311 · D-323) 접힌 기록은 전제들의 합집합이다(`_held_candidates`)
EQUIV_FIELDS = ("verdicts", "hold_reasons", "types", "cond_types", "questions", "committed")
#: 위험도는 분기가 보일 때만 맞댄다 — 접힌 기록의 위험도는 전제 최댓값이다(보충 33 「가장 나쁜 쪽은 위험도에만」 · 고른 전제는 그 전제의 값)
EQUIV_RISK = "risk_max"
#: `diff` 에서 기본으로 세지 않는 칸 — 실행마다 달라지거나(시간 없음) 다른 칸의 요약이다. `--field` 로 고르면 센다
DIFF_SKIP = frozenset({"id"})


def load(path: pathlib.Path) -> dict[str, Any]:
    """결과 파일 하나 — 🔴 행이 없거나 `id` 가 겹치면 멈춘다(짝을 못 지으면 대조가 거짓말이 된다 · D-220)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("rows")
    if not rows:
        raise SystemExit(f"🔴 {path} 에 행이 없다 — `eval_graph --out` 결과 파일인가")
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        dup = [k for k, n in collections.Counter(ids).items() if n > 1][:5]
        raise SystemExit(f"🔴 {path} 에 같은 id 가 둘 이상이다 — {dup}")
    return doc


def stamp(doc: dict[str, Any]) -> str:
    """판 표지 한 줄 — 원장에 옮길 것(D-178)."""
    keys = (
        "judged_by",
        "golden_sha",
        "conditional",
        "category_only",
        "answers",
        "encoder",
        "split",
    )
    return " · ".join(f"{k} {doc[k]}" for k in keys if k in doc)


def diff(a: dict[str, Any], b: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    """두 결과 파일의 행 단위 차이 — 칸마다 바뀐 행 수 · 분류 이동 · 바뀐 행 목록. 🔴 순수 함수(시험이 대역 파일로 잰다)."""
    ra = {r["id"]: r for r in a["rows"]}
    rb = {r["id"]: r for r in b["rows"]}
    both = [k for k in ra if k in rb]
    keys_a = set().union(*(r.keys() for r in a["rows"]))
    keys_b = set().union(*(r.keys() for r in b["rows"]))
    shared = sorted((keys_a & keys_b) - DIFF_SKIP)
    use = [f for f in (fields or shared) if f in shared]
    by_field: collections.Counter = collections.Counter()
    moves: collections.Counter = collections.Counter()
    changed: list[dict[str, Any]] = []
    for k in both:
        x, y = ra[k], rb[k]
        diffs = [f for f in use if x.get(f) != y.get(f)]
        by_field.update(diffs)
        if x.get("class") != y.get("class"):
            moves[(x.get("class"), y.get("class"))] += 1
        if diffs:
            changed.append({"id": k, "fields": diffs})
    return {
        "rows_a": len(ra),
        "rows_b": len(rb),
        "both": len(both),
        "only_a": sorted(set(ra) - set(rb)),
        "only_b": sorted(set(rb) - set(ra)),
        "fields_only_a": sorted(keys_a - keys_b),
        "fields_only_b": sorted(keys_b - keys_a),
        "changed_rows": len(changed),
        "by_field": dict(by_field.most_common()),
        "moves": {f"{s} → {t}": n for (s, t), n in moves.most_common()},
        "changed": changed,
    }


def equiv(cat: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    """경로 동치 — 전제를 고른 기록 = 품목만 넘긴 판정의 그 전제 분기(접혔으면 기록). 🔴 순수 함수.

    ★ 짝 — 같은 `id` · 고른 쪽 `product.premise` 가 있고 품목만 쪽 `product.premise` 가 없고 품목이 같은 행.
    🔴 칸이 없는 결과 파일이면 멈춘다(`product` · 분기의 `questions` — 보충 35 전 파일).
    """
    for name, doc in (("품목만", cat), ("고른 전제", chosen)):
        if not all("product" in r for r in doc["rows"]):
            raise SystemExit(
                f"🔴 {name} 결과 파일에 `product` 칸이 없다 — 보충 35 전 판이다. 같은 커밋으로 두 번 다시 잰다"
            )
    rc = {r["id"]: r for r in cat["rows"]}
    pairs = []
    for r in chosen["rows"]:
        c = rc.get(r["id"])
        p = r["product"]
        if (
            c is None
            or not p.get("premise")
            or c["product"].get("premise")
            or c["product"].get("category") != p.get("category")
        ):
            continue
        pairs.append((c, r))
    if not pairs:
        raise SystemExit(
            "🔴 짝지을 행이 없다 — 앞 파일은 `--category-only`, 뒤 파일은 그것 없이 같은 조건부로 잰 것이어야 한다"
        )
    mism: list[dict[str, Any]] = []
    shown = folded = 0
    for c, r in pairs:
        prem = r["product"]["premise"]
        if c.get("branches"):
            shown += 1
            ref = c["branches"].get(prem)
            fields = (*EQUIV_FIELDS, EQUIV_RISK)
            if ref is None:
                mism.append(
                    {"id": r["id"], "premise": prem, "where": "분기", "fields": ["분기 없음"]}
                )
                continue
            missing = [f for f in fields if f not in ref]
            if missing:
                raise SystemExit(
                    f"🔴 품목만 결과 파일의 분기에 {missing} 칸이 없다 — 보충 35 전 판이다(분기 칸을 「같다」로 세지 않는다)"
                )
            where = "분기"
        else:
            folded += 1
            ref, fields, where = c, EQUIV_FIELDS, "접힘(기록)"
        bad = [f for f in fields if ref.get(f) != r.get(f)]
        if bad:
            mism.append(
                {
                    "id": r["id"],
                    "premise": prem,
                    "where": where,
                    "fields": bad,
                    "want": {f: ref.get(f) for f in bad},
                    "got": {f: r.get(f) for f in bad},
                }
            )
    return {
        "pairs": len(pairs),
        "shown": shown,
        "folded": folded,
        "mismatch": len(mism),
        "by_field": dict(collections.Counter(f for m in mism for f in m["fields"]).most_common()),
        "rows": mism,
        "invariant_cat": sum(1 for r in cat["rows"] if r.get("invariant")),
        "invariant_chosen": sum(1 for r in chosen["rows"] if r.get("invariant")),
    }


def _print_diff(d: dict[str, Any], show: int) -> None:
    print(
        f"  행 앞 {d['rows_a']} · 뒤 {d['rows_b']} · 같은 id {d['both']} · 앞에만 {len(d['only_a'])} · 뒤에만 {len(d['only_b'])}"
    )
    if d["fields_only_a"] or d["fields_only_b"]:
        print(
            f"  ⚠️ 한쪽에만 있는 칸 — 앞 {d['fields_only_a']} · 뒤 {d['fields_only_b']} (세지 않았다 · 판이 다르다)"
        )
    print(f"  바뀐 행 {d['changed_rows']}")
    for f, n in d["by_field"].items():
        print(f"    {f:24} {n}")
    if d["moves"]:
        print("  분류 이동")
        for k, n in d["moves"].items():
            print(f"    {k:28} {n}")
    for row in d["changed"][:show]:
        print(f"    {row['id']}  {', '.join(row['fields'])}")
    if len(d["changed"]) > show:
        print(f"    … {len(d['changed']) - show} 행 더 (`--show`)")


def _print_equiv(e: dict[str, Any], show: int) -> None:
    mark = "✅" if e["mismatch"] == 0 else "🔴"
    print(
        f"  {mark} 경로 동치 — 짝 {e['pairs']}(분기가 보인 행 {e['shown']} · 접힌 행 {e['folded']}) · 어긋난 행 {e['mismatch']}"
    )
    for f, n in e["by_field"].items():
        print(f"    {f:24} {n}")
    for m in e["rows"][:show]:
        print(f"    {m['id']}  {m['premise']} · {m['where']} · {m['fields']}")
        if "want" in m:
            print(f"        품목만 {m['want']}")
            print(f"        고른것 {m['got']}")
    if len(e["rows"]) > show:
        print(f"    … {len(e['rows']) - show} 행 더 (`--show`)")
    if e["invariant_cat"] or e["invariant_chosen"]:
        print(
            f"  🔴 불변식이 깨진 행 — 품목만 {e['invariant_cat']} · 고른 전제 {e['invariant_chosen']} (D-348 보충 35 결정 1)"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="두 결과 파일의 행 단위 차이")
    d.add_argument("a", type=pathlib.Path)
    d.add_argument("b", type=pathlib.Path)
    d.add_argument(
        "--field", action="append", help="셀 칸(여러 번) — 없으면 두 파일에 다 있는 칸 전부"
    )
    d.add_argument("--show", type=int, default=20)
    d.add_argument("--out", type=pathlib.Path, help="결과를 JSON 으로")
    e = sub.add_parser("equiv", help="경로 동치 — 품목만 넘긴 판정 vs 전제를 고른 판정")
    e.add_argument("category_only", type=pathlib.Path)
    e.add_argument("chosen", type=pathlib.Path)
    e.add_argument("--show", type=int, default=20)
    e.add_argument("--out", type=pathlib.Path, help="결과를 JSON 으로")
    a = ap.parse_args(argv)
    if a.cmd == "diff":
        da, db = load(a.a), load(a.b)
        print(f"  앞 {a.a} — {stamp(da)}\n  뒤 {a.b} — {stamp(db)}")
        res = diff(da, db, a.field)
        _print_diff(res, a.show)
        code = 0
    else:
        dc, dd = load(a.category_only), load(a.chosen)
        print(f"  품목만 {a.category_only} — {stamp(dc)}\n  고른 전제 {a.chosen} — {stamp(dd)}")
        res = equiv(dc, dd)
        _print_equiv(res, a.show)
        code = (
            0
            if res["mismatch"] == 0 and not (res["invariant_cat"] or res["invariant_chosen"])
            else 1
        )
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(
            json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        print(f"  → {a.out}")
    return code


if __name__ == "__main__":
    sys.exit(main())
