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

질의 파일 — JSONL 한 줄에 하나. 🔄 2026-09-27 — 기본 경로를 `data/derived/labels/search_probe/queries.jsonl` 로 옮겼다.
    ⛔ 09-24 W6 재측정은 `build/search_probe_w6.jsonl`(git · 원장 밖)로 돌았고, 기본 경로(`search_golden.jsonl`)는
       만든 적이 없어 「질의 파일이 없다」로 읽혔다(사실원장 ㉛ · ㉜). 사람이 정답을 정한 파일이 한 기기에만 있었다.
    ★ `labels/` 아래라 원장 부류가 **원천**이다 — 잃으면 `derived-manifest --write` 가 멈추고, `data-publish` 가
       팀 공유 저장소로 옮긴다(D-247 · D-249). 🚨 **공개 git 에 두지 않는다** — 팀 자산인 평가셋이다(2026-09-27 팀장 판정).
    🚨 `labels/` **바로 아래가 아니라 하위 폴더**다 — `preprocess/labels.py` 가 `labels/*.jsonl` 을 사람 라벨로 읽는다.

    {"q": "이 제품은 암 예방에 좋습니다", "want": ["013094:제8조제1항제1호", "013453:[별표 1]제1호*"], "provenance": "자작"}

`provenance` — 🆕 2026-09-27 · **줄마다 필수**. `자작`(팀이 지어낸 문구) 또는 레지스트리 원천 ID.
    원천 ID 는 **재배포 가능 · 변경금지(ND) 아님**이어야 한다 — 이 파일은 제3자 계정 저장소로 나가고(D-78 ③ · D-71),
    평가셋은 파생 데이터셋이다(ND 게이트 · D-110). 어기면 **돌지 않는다**(`check_rows`).
    ⛔ 실제 광고 문구 · 실명을 넣지 않는다(D-216 · D-249) — 이 검사는 실명을 못 잡는다. 사람이 본다.

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
QUERIES = ROOT / "data" / "derived" / "labels" / "search_probe" / "queries.jsonl"
#: 출처 칸의 허용값 — 레지스트리 원천 ID 밖에서 받는 것은 이것뿐이다
SELF_MADE = "자작"

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
    wide: tuple[list[rt.Hit], list[rt.Hit]] = ([], [])
    for name, laws in SCOPES:
        try:
            vec = rt.by_vector(cur, q, laws, pool)
            vector_state = "ok"
        except rt.RetrieveError as e:
            vec, vector_state = [], f"{type(e).__name__}: {e}"
        lex = rt.by_lexical(cur, q, laws, pool)
        fused = rt.fuse(vec, lex, limit=pool)
        if not laws:
            # 🆕 2026-09-28 — 넓은 검색의 **두 갈래 후보 전체**. 법별 노드가 갈래마다 거른 뒤 섞는다 (D-267 · `rt.law_view`)
            wide = (vec, lex)
        view = rt.law_view(*wide, laws[0]) if len(laws) == 1 else None
        out["by_scope"][name] = {
            "vector_state": vector_state,
            "pool_vector": len(vec),
            "pool_lexical": len(lex),
            "rank_vector": rank_of(vec, want),
            "rank_lexical": rank_of(lex, want),
            "rank_rrf": rank_of(fused, want),
            # 🆕 2026-09-27 — 판정 그래프가 실제로 보는 순서(규범당 상한 · `rt.diversify`)
            "rank_rrf_cap": rank_of(rt.diversify(fused), want),
            # 🆕 2026-09-28 — **설계대로의 순위**: 넓게 한 번 찾고 이 법의 근거만 거른 순서(D-267). 분모는 `wide_law`
            "wide_law": None if view is None else len(view),
            "rank_wide_law": None if view is None else rank_of(view, want),
        }
    return out


def check_rows(rows: list[dict]) -> list[str]:
    """질의 줄 검사 — 문제 목록(빈 목록이면 통과). 🆕 2026-09-27.

    🔴 모르는 것은 막는다 (D-220) — 출처가 없거나 레지스트리에 없는 원천이면 문제로 센다.
    """
    from collect import registry  # noqa: PLC0415

    bad: list[str] = []
    for i, r in enumerate(rows, start=1):
        if not str(r.get("q") or "").strip() or not r.get("want"):
            bad.append(f"{i}행: q · want 가 비었다")
        src = str(r.get("provenance") or "").strip()
        if not src:
            bad.append(f"{i}행: provenance 가 없다 — `{SELF_MADE}` 또는 레지스트리 원천 ID")
            continue
        if src == SELF_MADE:
            continue
        try:
            if registry.no_derivatives(src):
                bad.append(f"{i}행: {src} 는 변경금지(ND) — 평가셋에 싣지 않는다 (D-110)")
            elif not registry.redistributable(src):
                bad.append(f"{i}행: {src} 는 재배포 제약 — 공유 저장소로 나갈 수 없다 (D-71)")
        except registry.RegistryError as e:
            bad.append(f"{i}행: {src} — {e}")
    return bad


def _wants_law(want: str | list[str], laws: tuple[str, ...]) -> bool:
    """정답이 이 법 범위에 있는가 — `--top` 이 정답이 없는 법 범위까지 찍지 않게 한다."""
    from collect.law_map import LAW_OF_ID  # noqa: PLC0415

    ids = {w.rpartition(":")[0] for w in ([want] if isinstance(want, str) else want)}
    return any(LAW_OF_ID.get(i) in laws for i in ids if i)


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
    ap.add_argument(
        "--top",
        type=int,
        default=0,
        help="질의 · 범위마다 판정 그래프가 받는 순서(규범당 상한 뒤)로 상위 N 건을 찍는다 — 정답은 ★",
    )
    args = ap.parse_args()

    p = pathlib.Path(args.queries)
    if not p.exists():
        print(
            f"🔴 질의 파일이 없다 — {p}\n"
            '   JSONL 한 줄에 하나: {"q": "…", "want": ["법ID:인용"], "provenance": "자작"}\n'
            "   🚨 `want` 는 retrieve.citation() 이 내는 모양 그대로다. 사본 기기는 `launcher.py data-sync` 로 받는다",
            file=sys.stderr,
        )
        return 1
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print(f"🔴 질의가 0건이다 — {p}", file=sys.stderr)
        return 1
    bad = check_rows(rows)
    if bad:
        print(f"🔴 질의 파일을 쓰지 않는다 — {p}", file=sys.stderr)
        for b in bad[:10]:
            print(f"   {b}", file=sys.stderr)
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

    print(
        f"\n  {'질의':<28} {'범위':<8} {'후보(어휘)':>9} {'벡터':>5} {'어휘':>5} {'RRF':>5} {'상한':>5}"
        f" {'넓게→거름':>9}"
    )
    print(
        "  🚨 「넓게→거름」 이 판정 그래프 설계(D-267)의 순위다 — 법 필터 없이 한 번 찾은 두 갈래 후보에서 갈래마다 이 법 것만"
        " 골라 섞고 규범당 상한을 건 순서 · 괄호는 그 법의 후보 수(분모)\n"
        "     법 범위 줄의 벡터 · 어휘 · RRF · 상한은 **법마다 따로 검색**한 수다 — 설계가 비용 때문에 택하지 않은 모양이다"
    )
    for res in results:
        for cat, m in res["by_scope"].items():
            # 🚨 어느 갈래도 못 찾은 범위는 **찍지 않는다** — 다 찍으면 표가 다섯 배가 되고
            #    「정답이 있는 법」이 안 보인다. 다만 전부 못 찾으면 아래에서 따로 알린다.
            if m["rank_vector"] is m["rank_lexical"] is m["rank_rrf"] is m["rank_wide_law"] is None:
                continue
            wide_col = (
                "·" if m["wide_law"] is None else f"{_fmt(m['rank_wide_law'])}({m['wide_law']})"
            )
            print(
                f"  {res['q'][:26]:<28} {cat:<8} {m['pool_lexical']:>9} "
                f"{_fmt(m['rank_vector']):>5} {_fmt(m['rank_lexical']):>5} {_fmt(m['rank_rrf']):>5} "
                f"{_fmt(m['rank_rrf_cap']):>5} {wide_col:>9}"
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

    if args.top:
        # 🆕 2026-09-27 — 09-24 `build/w6_top.py`(git 밖)가 하던 일을 여기로 옮겼다. 상위가 **무엇인지** 봐야
        #    「잡음이 올라왔나 · 관련 규범이 올라왔나」가 갈린다(사실원장 ㉟). 🚨 `rt.search` 그대로다 — 새 검색을 짓지 않는다
        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            for r in rows:
                own = tuple(x for x in SCOPES[1:] if _wants_law(r["want"], x[1]))
                views = [(name, laws, None) for name, laws in SCOPES[:1] + own]
                # 🆕 2026-09-28 — 설계대로(D-267): 넓게 한 번 찾은 후보 전체에서 이 법 것만
                views += [(f"{name}(넓게→거름)", (), name) for name, _ in own]
                for name, laws, law in views:
                    hits, st = rt.search(cur, r["q"], laws, limit=args.top, pool=args.pool)
                    if law is not None:
                        vec = rt.by_vector(cur, r["q"], (), args.pool)
                        lex = rt.by_lexical(cur, r["q"], (), args.pool)
                        hits = rt.law_view(vec, lex, law)[: args.top]
                    print(f"\n  ■ {r['q'][:30]} · {name} · 벡터 {st.vector}")
                    for i, h in enumerate(hits, 1):
                        mark = "★" if rank_of([h], r["want"]) else " "
                        print(
                            f"   {mark}{i:>2}. {h.law:<8} {h.law_id:<8} {(h.citation or '(인용 없음)'):<22} "
                            f"v{h.rank_vector or '-':>4} l{h.rank_lexical or '-':>4}  "
                            f"{(h.text or '').replace(chr(10), ' ')[:40]}"
                        )

    if args.json:
        print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
