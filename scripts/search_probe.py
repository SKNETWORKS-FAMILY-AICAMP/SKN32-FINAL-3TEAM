"""search_probe.py — 검색 순위를 재는 탐침. **원장에 올릴 수를 만드는 자리다** (D-204).

  uv run python -m scripts.search_probe                      # 기본 질의 파일
  uv run python -m scripts.search_probe --queries <경로>
  uv run python -m scripts.search_probe --pool 200           # ⚠️ 기본값 밖 — 분모를 같이 적는다

왜 있는가 — 2026-09-12 오후에 이 표를 만든 스크립트가 **커밋되지 않았다.**
원장 §3-1 의 순위 셋(RRF 1위·15위·3위)이 D-198 의 근거이고 남은 것의 우선순위를
두 번 뒤집었는데, **그 수를 다시 낼 방법이 저장소에 없었다** (D-176 — 재현의 근거).
⛔ 게다가 이름이 `collect/probe.py`(소스 탐침 · D-109)와 겹쳐, 찾으러 온 사람이
   전혀 다른 물건을 연다. 그래서 이름을 `search_probe` 로 가른다 (D-167 — 뜻으로 가른다).

🚨 **후보 폭의 정본은 `app/retrieve.py` 의 `POOL` 이다.** 여기서 기본값을 다시 적지 않는다 (D-99).
   ★ **폭을 바꾸는 것은 막지 않는다 — 탐색은 자유롭게다** (D-205). 다만 바꾸면 **분모가
   달라졌다고 찍는다**: 09-12 오후 실측이 200 으로 잰 것을 아무 데도 안 적어서, 오전(50)과
   오후(200)의 순위를 나란히 비교할 뻔했다 (D-178 — 수에는 분모와 조건이 붙는다).
   🔴 **그 표로 `POOL` 을 바꾸지는 않는다** — 여는 조건 둘은 원장 「판정 경로의 출처 태그」에 있다.

🔴 **정확도를 말하지 않는다.** 30건 미만이면 D-40 으로 「측정 불가」를 찍고 순위표만 낸다.
   ⛔ 3건으로 「개선됐다」고 말한 것이 09-12 오후에 실제로 있었다 (D-190 · D-198).

질의 파일 — JSONL 한 줄에 하나. `data/` 는 커밋되지 않으므로 **기기마다 다르다**(D-19).

    {"q": "이 제품은 암 예방에 좋습니다", "want": ["013094:제8조제1항제1호", "013453:[별표 1]제1호*"]}

`want` 는 `retrieve.citation()` 이 내는 모양 그대로이고, 🔄 2026-09-24 부터 **법 ID 를 앞에 붙이고(`법ID:`)
목록으로 여럿**을 줄 수 있다 — 법률 조문과 그 세부 기준([별표 1] 항목)을 둘 다 정답으로 둔다(팀장 판정).
끝의 `*` 는 하위 항목까지 맞힌다. 법 ID 없는 옛 모양(인용만)도 받지만 **다른 법의 같은 인용까지 맞힌 것으로 센다.**
🔄 별표 인용은 0015 부터 조립된다 — 종전 「별표는 `citation()` 이 조립하지 않는다」는 낡은 문장이다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from app import retrieve as rt
from app.settings import PARAMS, dsn
from collect.law_map import LAWS

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUERIES = ROOT / "data" / "derived" / "search_golden.jsonl"

#: **전체 + 법 넷을 다 돈다.** 🚨 09-12 오후에 `건기식` 을 박고 돌렸는데 정답은 `식품` 에 있었다.
#:    ⛔ 사람이 헷갈리지 않게 하는 대신 **틀릴 수 있는 자리를 없앤다** (D-51).
#: 🔄 2026-09-24 (W6 · D-271 ③ ⑦) — 종전 범주 넷(일반 · 식품 · 건기식 · 화장품)을 **법 축**으로 바꿨다.
#:    「전체」(필터 없음)가 판정 그래프가 실제로 도는 모양이다 — 넓게 한 번 찾는다(D-267).
#:    🚨 W6 전에 잰 수(원장 09-12 · 09-16)는 **범주 필터 상태의 수**다 — 이 표와 나란히 놓을 때 조건을 붙인다 (D-178).
SCOPES: tuple[tuple[str, tuple[str, ...]], ...] = (("전체", ()),) + tuple(
    (law, (law,)) for law in LAWS
)

#: D-40 — 이 아래면 「측정 불가」다. 순위는 찍되 **비율을 말하지 않는다.**
MIN_MEASURABLE = PARAMS.min_measurable


def _matches(h: rt.Hit, want: str) -> bool:
    """정답 한 개와 맞는가. 🆕 2026-09-24 (W6 재측정) — **법 ID 를 같이 본다** · 끝이 `*` 면 하위 항목까지.

        "제8조제1항제1호"                  인용만 (옛 모양 — 🚨 다른 법의 같은 「제8조제1항제1호」도 맞힌 것으로 센다)
        "013094:제8조제1항제1호"           법 ID + 인용
        "013453:[별표 1]제1호*"            [별표 1]제1호 와 그 아래(제1호가목 · 제1호다목 …)

    ⛔ 종전에는 인용 글자만 댔다. 「[별표 1]제1호가목」은 식품표시광고법 시행령에도(질병 예방 표방) 시행규칙에도(「제품명」)
       있다 — 법 ID 없이 대면 **목록 청크를 정답으로 셀 수 있다**(2026-09-24 실측 상위 10 에 둘 다 있었다).
    """
    law_id, _, cite = want.rpartition(":")
    if law_id and h.law_id != law_id:
        return False
    if cite.endswith("*"):
        base, got = cite[:-1], h.citation or ""
        # 🚨 「제1호*」가 「제10호」를 맞히지 않게 — 바로 뒤가 숫자면 다른 항목이다
        return got.startswith(base) and not got[len(base) : len(base) + 1].isdigit()
    return h.citation == cite


def rank_of(hits: list[rt.Hit], want: str | list[str]) -> int | None:
    """정답 조문이 몇 위인가 — 정답이 여럿이면 **가장 앞선 것**. 🔴 **없으면 `None` 이다 — 후보 폭+1 이 아니다** (D-188).

    ⛔ 「51위」라고 적으면 「후보 밖」이 「간신히 밖」처럼 읽힌다. 모르는 것은 모른다.
    🆕 2026-09-24 — `want` 가 목록일 수 있다. 법률 조문과 그 세부 기준([별표 1] 항목)을 **둘 다 정답**으로 둔다
       (팀장 판정 2026-09-24 — 세부 기준 우선 · 법률 조문도 인정). W6 전에는 [별표 1] 이 「일반」에 있어 법률 조문만 보였다.
    """
    wants = [want] if isinstance(want, str) else list(want)
    for i, h in enumerate(hits, start=1):
        if any(_matches(h, w) for w in wants):
            return i
    return None


def probe_one(cur, q: str, want: str, pool: int) -> dict:  # noqa: ANN001
    """질의 하나를 전체 + 법 넷에 다 넣고, 갈래별 순위와 RRF 순위를 낸다."""
    out: dict = {"q": q, "want": want, "by_scope": {}}
    for name, laws in SCOPES:
        try:
            vec = rt.by_vector(cur, q, laws, pool)
            vector_state = "ok"
        except rt.RetrieveError as e:
            vec, vector_state = [], f"{type(e).__name__}: {e}"
        lex = rt.by_lexical(cur, q, laws, pool)
        fused = rt.fuse(vec, lex, limit=pool)
        out["by_scope"][name] = {
            "vector_state": vector_state,
            "pool_vector": len(vec),
            "pool_lexical": len(lex),
            "rank_vector": rank_of(vec, want),
            "rank_lexical": rank_of(lex, want),
            "rank_rrf": rank_of(fused, want),
        }
    return out


def _fmt(v: int | None) -> str:
    return "—" if v is None else str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="검색 순위 탐침 — 원장에 올릴 수를 만든다")
    ap.add_argument("--queries", default=str(QUERIES), help="JSONL {q, want}")
    ap.add_argument(
        "--pool",
        type=int,
        default=rt.POOL,
        help=f"후보 폭 (기본 {rt.POOL} — 기획서 5-6 이 고정한 수)",
    )
    ap.add_argument("--json", action="store_true", help="원시 결과를 JSON 으로도 찍는다")
    args = ap.parse_args()

    p = pathlib.Path(args.queries)
    if not p.exists():
        print(
            f"🔴 질의 파일이 없다 — {p}\n"
            '   JSONL 한 줄에 하나: {"q": "…", "want": "제8조제1항제1호"}\n'
            "   🚨 `want` 는 retrieve.citation() 이 내는 모양 그대로다 (별표는 넣지 않는다).",
            file=sys.stderr,
        )
        return 1
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print(f"🔴 질의가 0건이다 — {p}", file=sys.stderr)
        return 1

    # 🚨 **잰 조건을 먼저 찍는다** — 표만 옮겨 적으면 분모가 떨어져 나간다 (D-178).
    print(f"  질의 {len(rows)}건 · 후보 폭 {args.pool} · 전체 + 법 {len(LAWS)}개를 다 돈다")
    if args.pool != rt.POOL:
        print(
            f"  ⚠️ **후보 폭 {args.pool} — 기본값 {rt.POOL} 밖이다.** 분모가 다르므로 "
            "다른 폭에서 잰 표와 나란히 놓지 않는다 (D-178). 이 표로 POOL 을 바꾸지도 않는다 (D-205)"
        )
    if len(rows) < MIN_MEASURABLE:
        print(
            f"  🔴 **{len(rows)}건은 측정 불가다** (D-40 — {MIN_MEASURABLE}건 미만).\n"
            "     순위는 찍지만 **비율·개선 여부를 말하지 않는다.** 「가설」이라고 적는다."
        )

    import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다

    results = []
    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        for r in rows:
            results.append(probe_one(cur, r["q"], r["want"], args.pool))

    print(f"\n  {'질의':<28} {'범위':<8} {'후보(어휘)':>9} {'벡터':>5} {'어휘':>5} {'RRF':>5}")
    for res in results:
        for cat, m in res["by_scope"].items():
            # 🚨 어느 갈래도 못 찾은 범위는 **찍지 않는다** — 다 찍으면 표가 다섯 배가 되고
            #    「정답이 있는 법」이 안 보인다. 다만 전부 못 찾으면 아래에서 따로 알린다.
            if m["rank_vector"] is m["rank_lexical"] is m["rank_rrf"] is None:
                continue
            print(
                f"  {res['q'][:26]:<28} {cat:<8} {m['pool_lexical']:>9} "
                f"{_fmt(m['rank_vector']):>5} {_fmt(m['rank_lexical']):>5} {_fmt(m['rank_rrf']):>5}"
            )
    lost = [r["q"] for r in results if all(m["rank_rrf"] is None for m in r["by_scope"].values())]
    if lost:
        print(f"\n  🔴 후보 {args.pool} 안에서 **어느 범위에서도 못 찾은 질의 {len(lost)}건**")
        for q in lost[:5]:
            print(f"     {q}")
        print("     🚨 이것이 리랭커로 못 고치는 몫이다 — 후보에 없는 것은 순서를 못 바꾼다")

    states = {
        m["vector_state"]
        for r in results
        for m in r["by_scope"].values()
        if m["vector_state"] != "ok"
    }
    if states:
        print(f"\n  ⛔ 벡터 갈래가 안 돈 범위가 있다 — {sorted(states)}")
        print("     🚨 그 줄의 「—」는 「후보에 없다」가 아니라 **「못 쟀다」**다 (D-188)")

    if args.json:
        print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
