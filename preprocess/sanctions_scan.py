"""preprocess/sanctions_scan.py — 행정처분 대장, **받은 것이 전부인가** (D-161).

  uv run python -m preprocess.sanctions_scan mfds_sanctions

🔴 이 모듈은 라벨을 만들지 않는다. **두 가지만 묻는다.**

  ① 원천이 말한 수만큼 **서로 다른 행**을 받았는가
  ② 이 원천이 정말 **광고 문구**를 주는가

──────────────────────────────────────────────────────────────
🚨 **수가 맞는 것은 다 받았다는 뜻이 아니다** (D-149 가 걱정한 자리)

  실측 (2026-09-08 · `mfds_sanctions`)

      원천 선언            5,381
      받은 행              5,381   ← **수가 맞는다**
      서로 다른 행         5,122   ← 🔴 **259 행이 중복이다**

  ⛔ 「전체 건수 = 받은 건수」만 보고 넘어가면 여기서 끝난다. 실제로 그렇게 넘어갔었다.

  ★ 중복이 **어디에** 있는지가 원인을 가른다.

      한 페이지 안에서 중복    → 원천에 정말 같은 행이 둘 있다 (우리 잘못 아님)
      페이지를 걸쳐 중복       → 🔴 **페이지마다 순서가 달라진다** (offset 페이징의 고전)

    실측은 **한 페이지 안 0종 · 페이지 걸침 236종**이었다. 후자다.
    🚨 정렬 키가 유일하지 않으면 요청할 때마다 순서가 흔들려 **중복과 누락이 함께** 난다.
       받은 5,381 중 259 가 중복이면, **못 받은 259 가 어딘가에 있다.**
    ⛔ 같은 축으로 다시 받아도 안 낫는다 — 다른 축(처분일자 구간 등)으로 나눠 받아
       **합집합**을 취해야 한다. 그 전까지 이 원천은 「전량 확보」가 아니다.

──────────────────────────────────────────────────────────────
🔴 **그리고 이 원천은 광고 문구 출처가 아니다**

  실측 — 조문명에 「표시」나 「광고」가 든 행 **57 / 5,122**, 그중 부당광고 금지 조문
  (식품표시광고법 제8조)은 **28행**. 그 28행마저 대부분 **라벨 표시 위반**이다 —
  「소비기한 변조」·「표시사항을 거짓으로 표시」. 광고 **문구**가 인용된 것은 극소수다.

  🚨 **원장의 R8 전제를 다시 봐야 한다.** 「유형별 30건은 `mfds_sanctions` 전량과 합쳐야
     선다」고 적혀 있는데, 전량을 받아도 광고 문구는 여기서 거의 안 나온다.
     ★ 이 원천의 값어치는 다른 데 있다 — **처분 실적**(D-75 경제성 ①)이다. 그쪽으로 쓴다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

from collect import store
from preprocess.text import quoted

#: 조문명에 이것이 들어 있으면 표시·광고 관련으로 본다. 🚨 **판정이 아니라 그물**이다.
AD_LAW = ("표시", "광고")
#: 부당광고 금지 조문. 식품표시광고법 제8조 제1항.
AD_ARTICLE = "제8조"

#: 🚨 문구를 셀 때는 **낫표를 빼고** 센다 — 「축산물 위생관리법 시행령」처럼 **법령명**이
#:    낫표로 인용된다. 넣어 두면 「문구가 인용된 행」이 법령 인용만으로 부풀어 오른다.
#:    ★ 범위 차이는 정규식이 아니라 이렇게 **선언된 파라미터**로 둔다 (D-160).
QUOTE_FAMILIES_AD = ("‘’", "“”")


def _rows(raw: pathlib.Path) -> tuple[list[dict], set[int], dict[str, list[dict]]]:
    """페이지 파일들 → (행 전부, 원천이 선언한 전체 수, 파일별 행)."""
    per: dict[str, list[dict]] = {}
    rows: list[dict] = []
    total: set[int] = set()
    for f in store.current_files(raw, "page_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        body = d[next(iter(d))]
        if body.get("total_count"):
            total.add(int(body["total_count"]))
        got = body.get("row") or []
        per[f.name] = got
        rows += got
    return rows, total, per


def _key(r: dict) -> str:
    return json.dumps(r, sort_keys=True, ensure_ascii=False)


def raw_of(source: str) -> pathlib.Path:
    """원문 폴더 — 🆕 D-254 폴더 이름은 store.FAMILY_OF 에서 꺼낸다 (D-99).

    🚨 **작업 폴더 기준 상대 경로**로 둔다 — 종전(`pathlib.Path("data/raw") / source`)과 같다.
       절대 경로로 바꾸면 tmp 폴더에서 도는 계측 테스트가 저장소의 data/ 를 읽는다.
    """
    return store.family_path(source).relative_to(store.ROOT)


def scan(source: str) -> dict:
    """계측만 한다. 🚨 판정 문구는 `main` 이 찍는다 — 세는 곳과 말하는 곳을 나눈다."""
    raw = raw_of(source)
    rows, total, per = _rows(raw)
    if not rows:
        raise FileNotFoundError(f"{raw} 에 page_*.json 이 없다 — 먼저 수집기를 돌린다")

    where: dict[str, list[str]] = collections.defaultdict(list)
    for name, got in per.items():
        for r in got:
            where[_key(r)].append(name)
    dups = {k: v for k, v in where.items() if len(v) > 1}
    in_one_page = sum(1 for v in dups.values() if len(set(v)) == 1)

    ad_law = [r for r in where if AD_LAW_HIT(json.loads(r))]
    ad_art = [r for r in ad_law if AD_ARTICLE in (json.loads(r).get("LAWORD_CD_NM") or "")]
    with_quote = [
        r
        for r in ad_art
        if quoted(json.loads(r).get("VILTCN") or "", min_len=2, families=QUOTE_FAMILIES_AD)
    ]
    return {
        "선언": sorted(total),
        "받은행": len(rows),
        "유일행": len(where),
        "중복종": len(dups),
        "중복초과": sum(len(v) - 1 for v in dups.values()),
        "한페이지안": in_one_page,
        "페이지걸침": len(dups) - in_one_page,
        "표시광고조문": len(ad_law),
        "부당광고조문": len(ad_art),
        "문구인용": len(with_quote),
        "예시": [json.loads(r).get("VILTCN", "")[:100] for r in with_quote[:5]],
    }


def AD_LAW_HIT(r: dict) -> bool:  # noqa: N802 — 그물의 이름을 그대로 쓴다
    name = r.get("LAWORD_CD_NM") or ""
    return any(w in name for w in AD_LAW)


def main() -> int:
    ap = argparse.ArgumentParser(description="행정처분 대장 — 받은 것이 전부인가 (D-161)")
    ap.add_argument("source", nargs="?", default="mfds_sanctions", help="data/raw 아래 이름")
    a = ap.parse_args()
    s = scan(a.source)

    declared = s["선언"][0] if len(s["선언"]) == 1 else None
    print(f"{a.source} — 원천 선언 {s['선언']} · 받은 행 {s['받은행']:,}")
    mark = "★" if declared == s["유일행"] else "🔴"
    print(
        f"  {mark} 서로 다른 행 {s['유일행']:,}  (중복 {s['중복종']:,}종 · 초과 {s['중복초과']:,}건)"
    )
    if declared is not None and declared != s["유일행"]:
        print(
            f"     🔴 **못 받은 행이 {declared - s['유일행']:,} 있다.** 수가 맞는 것은 다 받았다는 뜻이 아니다."
        )

    if s["중복종"]:
        print(
            f"\n  중복이 있는 자리 — 한 페이지 안 {s['한페이지안']}종 · 페이지 걸침 {s['페이지걸침']}종"
        )
        if s["페이지걸침"] > s["한페이지안"]:
            print(
                "     🔴 **페이지마다 순서가 달라진다** — 정렬 키가 유일하지 않은 offset 페이징이다."
            )
            print(
                "        🚨 같은 축으로 다시 받아도 안 낫는다. 다른 축으로 나눠 받아 합집합을 취한다."
            )
        else:
            print("     ★ 원천에 정말 같은 행이 둘 있다 — 우리 잘못이 아니다.")

    print(
        f"\n  광고 문구 출처로서 — 조문명에 표시/광고 {s['표시광고조문']:,}행"
        f" · 그중 {AD_ARTICLE} {s['부당광고조문']:,}행 · 문구가 인용된 것 {s['문구인용']:,}행"
    )
    print(
        "     🚨 **이 원천은 처분 대장이지 광고 문구 원장이 아니다** — 값어치는 처분 실적 쪽이다."
    )
    for e in s["예시"]:
        print(f"       · {e}")
    return 0 if declared == s["유일행"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
