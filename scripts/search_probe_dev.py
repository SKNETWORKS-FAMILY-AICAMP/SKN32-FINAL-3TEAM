"""search_probe_dev.py — **실제 문구**로 재는 검색 탐침: dev 문장의 금지 조항이 그 법의 근거 상위에 드는가 (🆕 2026-10-12).

  uv run python -m scripts.search_probe_dev                    # dev 근거 행 전부
  uv run python -m scripts.search_probe_dev --limit 50         # 앞 50 행만(시범)
  uv run python -m scripts.search_probe_dev --pool 200         # ⚠️ 기본값 밖 — 분모를 같이 적는다

왜 있는가 — `scripts/search_probe.py` 의 질의 31건은 **지어낸 문구**이고 30건 남짓이라 비율을 말할 수 없다(D-40).
   「검색이 금지 조항을 못 올린다」가 실제 문구에서도 그런지, 얼마나 그런지를 dev 의 근거 행(수백)으로 잰다.
   정답은 골든 `근거` 칸의 **호 좌표**다 — 검색은 정답표의 근거 조문으로 잰다(D-322 결정 E).

재는 것 — 문구마다 넓은 검색(`rt.wide`)을 한 번 돌리고, 정답 좌표의 법으로 거른 순서(`rt.law_view` · 판정 그래프 설계 D-267)에서
   · **탐침 순위** — 거른 순서 그대로의 자리(`search_probe.rank_of` 와 같은 채점 · 좌표 없는 줄도 자리를 먹는다)
   · **화면 순위** — 좌표를 못 세운 줄을 건너뛰고 같은 좌표를 한 번만 센 자리. 판정 그래프의 법별 노드가 근거를 고르는
     규칙이다(`app/graph.py` `_pick` · D-224). 🚨 그 규칙을 여기 다시 적었다 — `_pick` 은 상위 몇 개만 돌려주어 순위를 못 낸다.
     `_pick` 이 바뀌면 `screen_rank` 도 같이 바꾼다 (D-99 — 서로를 가리키는 주석)
   · 목 좌표(`…제4호|다목`)가 있으면 그 세부 기준(시행령 [별표 1])의 자리도 따로 — 식품표시광고법만

🔴 **정확도를 말하는 도구가 아니다.** 정답은 금지 조항(호)뿐이다 — 고시 · 지침 같은 참고 조문의 품질은 이 수로 알 수 없다.
🔴 **dev 다** — 판 · 규칙을 고르는 자리(D-175). 봉인 평가셋 행은 읽지 않는다.
🚨 **문구를 찍지 않는다** — 화면 출력도 결과 파일도 행 id 와 순위뿐이다(D-249 · 실제 광고 문구다). 결과 파일은 `build/` 아래(git 무시).
🚨 질의는 **행의 문구 전체**다. 판정 그래프는 문장으로 갈라 문장마다 찾는다 — 여러 문장 행에서는 조건이 다르다(dev 근거 행
   640 중 600 이 한 문장이다 · 2026-10-12 결과 파일로 셈).
🆕 2026-10-12 — 갈래별 자리(벡터 · 어휘)와 시행일이 뒤인 현행 청크 수도 낸다 — 어느 갈래가 정답을 넣는지 · 시행 전 조항이 섞일 수 있는지.
⬜ 좌표 없는 줄이 상위를 얼마나 차지하는지도 센다(`uncited_top`) — D-293(좌표를 원문 번호로 넓힌다)은 집행 전이다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import time
from typing import Any

from app import retrieve as rt
from app.settings import PARAMS, dsn
from collect import statute
from collect.law_map import LAW_OF_ID
from scripts import eval_graph as eg
from scripts import search_probe as sp

OUT = pathlib.Path("build/eval/search_probe_dev.json")

#: 식품표시광고법 §8① 의 세부 기준 — 시행령 [별표 1]. 🚨 법 ID 는 `collect/law_map.LAW_OF_ID` 에 있는 값이다(시행령 줄).
FOOD_ANNEX = "013453:[별표 1]"

#: 판정 그래프가 법마다 화면에 싣는 근거 수 — `app/graph.py` `LAW_TOP_K` 와 같은 설정값을 읽는다 (D-99)
TOP_K = PARAMS.top_k


def targets(row: dict) -> list[dict[str, str]]:
    """행의 근거 좌표 → 찾을 것들. 🔴 꼴이 틀린 좌표는 건너뛰지 않고 멈춘다 — 조용히 분모가 준다 (D-220)."""
    out = []
    for c in row.get("근거") or []:
        law_id, _jo, _hang, ho, mok = statute.parse(c)
        law = LAW_OF_ID.get(law_id)
        if law is None:
            raise SystemExit(f"🔴 법을 못 정한 근거 좌표 — {c!r} (행 {row.get('id')})")
        t = {"cite": c, "law": law, "ho": statute.ho_key(c), "mok": ""}
        if mok and law_id == statute.FOOD[0]:
            t["mok"] = f"{FOOD_ANNEX}제{ho}호{mok}목"
        out.append(t)
    return out


def screen_rank(view: list[Any], want: str) -> int | None:
    """화면 순위 — 좌표를 못 세운 줄은 건너뛰고 같은 좌표는 한 번만 센 자리. 없으면 `None` (D-188).

    🚨 `app/graph.py` `_pick` 의 규칙이다(좌표 없음 → 버림 · `(법 ID, 위반 근거 좌표)` 가 같으면 한 줄). 그쪽이 바뀌면 여기도 바꾼다.
    """
    seen: set[tuple[str, str]] = set()
    for h in view:
        if not h.basis_citation or not h.law_id:
            continue
        key = (h.law_id, h.basis_citation)
        if key in seen:
            continue
        seen.add(key)
        if sp._matches(h, want):
            return len(seen)
    return None


def probe_row(cur: Any, row: dict, pool: int) -> list[dict[str, Any]]:
    """행 하나 — 넓은 검색 한 번 · 근거 좌표마다 한 줄. 🔴 벡터 갈래가 못 돌면 삼키지 않는다(`rt.RetrieveError` 그대로)."""
    wvec, wlex, _st = rt.wide(cur, row["text"], pool)
    out = []
    for t in targets(row):
        view = rt.law_view(wvec, wlex, t["law"])
        rec: dict[str, Any] = {
            "id": row["id"],
            "law": t["law"],
            "cite": t["ho"],
            "pool": len(view),
            "rank": sp.rank_of(view, t["ho"]),
            # 🆕 2026-10-12 — 갈래별 자리(그 법의 후보 안에서). 어느 갈래가 정답을 넣는지 가른다 — 섞은 순위만 보면 안 보인다
            "rank_vec": sp.rank_of([h for h in wvec if h.law == t["law"]], t["ho"]),
            "rank_lex": sp.rank_of([h for h in wlex if h.law == t["law"]], t["ho"]),
            "screen": screen_rank(view, t["ho"]),
            "uncited_top": sum(1 for h in view[:TOP_K] if not h.basis_citation),
        }
        if t["mok"]:
            rec["mok"] = t["cite"]
            rec["mok_rank"] = sp.rank_of(view, t["mok"])
            rec["mok_screen"] = screen_rank(view, t["mok"])
        out.append(rec)
    return out


def tally(recs: list[dict[str, Any]], key: str, rank: str = "rank", scr: str = "screen") -> dict:
    """묶음별 집계 — n · 후보 안 · 탐침 상위 K · 화면 상위 K · 화면 1위 · 화면 MRR. 🔴 없는 순위는 0 점이다 — 빼지 않는다 (D-220)."""
    acc: dict[str, list[float]] = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0.0])
    for r in recs:
        a = acc[r[key]]
        a[0] += 1
        a[1] += r[rank] is not None
        a[2] += r[rank] is not None and r[rank] <= TOP_K
        a[3] += r[scr] is not None and r[scr] <= TOP_K
        a[4] += r[scr] == 1
        a[5] += 1 / r[scr] if r[scr] else 0.0
    return {
        k: {"n": int(v[0]), "in_pool": int(v[1]), "top": int(v[2]), "screen_top": int(v[3]),
            "screen_first": int(v[4]), "mrr": v[5] / v[0]}
        for k, v in sorted(acc.items())
    }  # fmt: skip


def by_branch(recs: list[dict[str, Any]], key: str = "law") -> dict[str, dict[str, int]]:
    """갈래별 「후보 안」 — n · 벡터만 · 어휘만 · 둘 다 · 어느 쪽도 아님. 🔴 넷의 합은 n 이다 — 못 찾은 줄도 센다 (D-220)."""
    acc: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"n": 0, "vec_only": 0, "lex_only": 0, "both": 0, "neither": 0}
    )
    for r in recs:
        v, x = r["rank_vec"] is not None, r["rank_lex"] is not None
        a = acc[r[key]]
        a["n"] += 1
        a["both" if v and x else "vec_only" if v else "lex_only" if x else "neither"] += 1
    return dict(sorted(acc.items()))


#: 🆕 2026-10-12 — 시행일이 **오늘보다 뒤**인 현행 청크 · 시행일을 모르는 현행 청크. 검색 조건은 시행일을 보지 않는다
#:    (`app/retrieve.py` `SQL_VECTOR` · `SQL_LEXICAL`) — 시행 전 조항이 참고 조문에 섞일 수 있는지 수로 본다 (D-239 · D-293 ⬜)
SQL_NOT_YET = """SELECT count(*) FILTER (WHERE effective_date > CURRENT_DATE),
       count(*) FILTER (WHERE effective_date IS NULL), count(*)
FROM v_current_chunk"""


def _table(title: str, tab: dict[str, dict[str, Any]]) -> None:
    k = TOP_K
    print(
        f"\n  {title:34} {'n':>5} {'후보 안':>8} {f'탐침 상위 {k}':>10} {f'화면 상위 {k}':>10} {'화면 1위':>8} {'MRR':>6}"
    )
    for name, v in tab.items():
        n = v["n"]
        mark = "  🔴 측정 불가 (D-40)" if n < sp.MIN_MEASURABLE else ""
        print(
            f"  {name:34} {n:>5} {v['in_pool'] / n:>8.1%} {v['top'] / n:>10.1%} "
            f"{v['screen_top'] / n:>10.1%} {v['screen_first'] / n:>8.1%} {v['mrr']:>6.3f}{mark}"
        )  # fmt: skip


def report(
    recs: list[dict[str, Any]],
    rows: int,
    pool: int,
    secs: float,
    dates: tuple[int, int, int] | None = None,
) -> None:
    print(
        f"\n검색 탐침(dev 문구) — 행 {rows} · 근거 좌표 {len(recs)} · 후보 폭 {pool} · 상위 {TOP_K} · {secs:.0f}초"
        f" · 행당 {secs / max(rows, 1) * 1000:.0f} ms"
    )
    print(
        "  🚨 정답은 금지 조항(호)이다 — 참고 조문 전반의 품질이 아니다 · dev 다(D-175) · 문구는 찍지 않는다(D-249)"
    )
    if pool != rt.POOL:
        print(
            f"  ⚠️ 후보 폭 {pool} — 기본값 {rt.POOL} 밖이다. 다른 폭의 표와 나란히 놓지 않는다 (D-178 · D-205)"
        )
    _table("법", tally(recs, "law"))
    _table("금지 조항(호)", tally(recs, "cite"))
    mok = [r for r in recs if "mok" in r]
    if mok:
        _table("세부 기준(목) — 식품표시광고법", tally(mok, "law", "mok_rank", "mok_screen"))
        _table("세부 기준(목) — 목별", tally(mok, "mok", "mok_rank", "mok_screen"))
    print(
        f"\n  {'갈래별 후보 안 (호)':30} {'n':>5} {'벡터만':>7} {'어휘만':>7} {'둘 다':>7} {'없음':>7}"
    )
    for name, v in by_branch(recs).items():
        print(
            f"  {name:34} {v['n']:>5} {v['vec_only']:>7} {v['lex_only']:>7} {v['both']:>7} {v['neither']:>7}"
        )
    slots = len(recs) * TOP_K
    unc = sum(r["uncited_top"] for r in recs)
    print(
        f"\n  거른 순서의 상위 {TOP_K} 자리 {slots} 중 좌표 없는 줄 {unc} ({unc / max(slots, 1):.1%}) — 화면은 이 줄을 건너뛴다"
        " (D-224 · D-293 집행 전)"
    )
    if dates is not None:
        later, unknown, total = dates
        print(
            f"  현행 청크 {total:,} 중 시행일이 오늘보다 뒤 {later:,} · 시행일을 모름 {unknown:,} — 검색 조건은 시행일을 보지 않는다"
            " (D-239 · 🚨 「모름」은 「시행 중」이 아니다)"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="dev 문구로 재는 검색 탐침 — 금지 조항이 근거 상위에 드는가"
    )
    ap.add_argument("--pool", type=int, default=rt.POOL, help=f"후보 폭 (기본 {rt.POOL})")
    ap.add_argument("--limit", type=int, default=0, help="앞 N 행만 (시범 · 0 이면 전부)")
    ap.add_argument("--out", default=str(OUT), help="결과 파일 — 행 id 와 순위만(문구 없음)")
    a = ap.parse_args(argv)

    rows = [r for r in eg.load_rows(dev=True) if r.get("근거")]
    if not rows:
        print("🔴 dev 에 근거가 붙은 행이 0 이다 — 재지 않는다 (D-220)", file=sys.stderr)
        return 1
    if a.limit:
        rows = rows[: a.limit]

    import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다

    recs: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        cur.execute(sp.SQL_UNMARKED)
        unmarked = cur.fetchone()[0]
        if unmarked:
            print(
                f"🔴 적용 제외 표시(`exempt_of`)가 안 실린 청크 {unmarked:,}개 — 재지 않는다 (0021 · D-220)",
                file=sys.stderr,
            )
            return 1
        cur.execute(SQL_NOT_YET)
        dates = tuple(int(x) for x in cur.fetchone())
        for i, r in enumerate(rows, start=1):
            recs += probe_row(cur, r, a.pool)
            if i % 100 == 0:
                print(f"  … {i}행 · {time.perf_counter() - t0:.0f}초", flush=True)
    secs = time.perf_counter() - t0
    report(recs, len(rows), a.pool, secs, dates)

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "rows": len(rows),
                "pool": a.pool,
                "top_k": TOP_K,
                "limit": a.limit,
                "chunk_dates": dict(zip(("not_yet", "unknown", "total"), dates, strict=True)),
                "records": recs,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
