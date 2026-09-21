"""collect/ftc_body.py — 공정위 결정문 **본문** 수집기 (1층 판정라벨 · D-15).

  uv run python -m collect.ftc_body --query 표시광고 --limit 5 --dry-run
  uv run python -m collect.ftc_body --query 표시광고            # 본문검색 1,087건
  uv run python -m collect.ftc_body                              # 전체 8,255건 (약 70분)

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1). 게이트를 우회하는 경로를 만들지 않는다.
   원본은 data/raw/ftc/ 에 무손상 저장하고 덮어쓰지 않는다 (규약 2 · D-92).
   🚨 **마스킹은 여기서 하지 않는다.** 업체명·피심인 주소가 그대로 들어온다 —
      원본은 무손상이 원칙이고 D-17 마스킹은 전처리의 몫이다.

두 단이다 — **목록에서 일련번호를 얻고, 그 번호로 본문을 부른다.**

    목록  lawSearch.do?target=ftc&type=XML&display=100&page=N   → <결정문일련번호>
    본문  lawService.do?target=ftc&ID=<일련번호>&type=XML       → <FtcService>

🚨 data.go.kr **15103247** 이 이 API 인데 **API 유형이 LINK** 라 실제 호출처는 공정위가
   아니라 **법제처**다. 인증이 `serviceKey` 가 아니라 **`OC`** 이고 `LAW_OC_KEY` 를 쓴다 —
   `law_go_kr` · `ftc_decisions_api` 와 같은 포털·같은 키다 (D-113).

🚨 **파일데이터(15103301)를 대신하는 경로다.** 그쪽은 제공형태가 「기관자체에서
   다운로드」라 data.go.kr 에 파일이 없고, 실물 PDF 5,870개가 case.ftc.go.kr 에 있으며
   일괄 다운로드가 없다. 여기는 같은 결정문을 XML 로 준다 — OCR 이 필요 없고,
   대표자명이 원천에서 이미 가려져 오며, `<그림 N>` 광고 캡처가 들어오지 않는다
   (그것은 광고주 이미지 저작물이라 G1 미추출 대상이었다 · D-18).

산출: data/raw/ftc/{일련번호}_{결정일자}.xml + data/manifest.jsonl 1행
      (결정일자가 원천에 없는 12건은 `{일련번호}.xml`)
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET

from collect import env, law_api, registry, store

SOURCE_ID = "ftc_decisions_body"
FAMILY = "ftc"

ROWS = 100  # 목록 한 장에 받을 건수 (API 상한)

#: 🚨 본문 응답의 최소 크기. 실측에서 가장 짧은 약식 의결서가 5.5KB 였다.
#:    `law_api.MIN_BODY`(1000) 보다 넉넉히 잡아도 되지만, **잘못 잡으면 진짜 짧은 건을
#:    버린다.** 자식 요소 검사가 주 방어이고 이것은 그물이므로 낮게 둔다 (D-115).
MIN_BODY = 1000

#: 결정일자가 `2016.9.27.` 로 온다 — 파일명에 점을 넣지 않고 8자리로 편다.
_DATE = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")


def _norm_date(raw: str) -> str:
    """`2016.9.27.` → `20160927`. 못 읽으면 빈 문자열.

    🚨 빈 문자열은 **정상이다.** 1,087건 중 12건이 원천에 결정일자가 없다.
       그때는 `{일련번호}.xml` 로 저장한다 — 일련번호가 유일하니 충돌하지 않는다.
       `unknown` 같은 **고정 문자열**을 쓰면 충돌하고, 충돌은 규약 2(덮어쓰기 거부)에
       걸려 수집이 중간에 죽는다 — D-115 ③ 이 경계했던 것이 그것이다.
    """
    m = _DATE.search(raw or "")
    return f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}" if m else ""


def _text(node: ET.Element, name: str) -> str:
    el = node.find(name)
    return (el.text or "").strip() if el is not None and el.text else ""


def list_page(
    oc: str, page: int, query: str, search: int, sort: str
) -> tuple[int, list[tuple[str, str, str]]]:
    """목록 한 장. 돌려주는 값은 (전체 건수, [(일련번호, 사건명, 결정일자)]).

    🚨 목록의 실패는 본문의 실패와 **모양이 다르다** (2026-09-02 실측).
       본문은 조회에 실패하면 **HTML 오류 페이지**(1,798 B)가 오는데,
       목록은 결과가 0건이어도 **정상 XML** 에 `<totalCnt>0</totalCnt>` 로 온다.
       그래서 목록은 자식 요소 유무가 아니라 **`<ftc>` 항목의 유무**로 본다.
    """
    params = {"target": "ftc", "display": str(ROWS), "page": str(page), "sort": sort}
    if query:
        params["query"] = query
        params["search"] = str(search)
    root = law_api._parse(law_api._call(law_api.BASE_SEARCH, oc, **params))
    if root is None:
        raise SystemExit(
            "🚨 목록이 XML 이 아니다 — OC 가 승인되지 않았거나 값이 틀렸다.\n"
            "   uv run python scripts/law_api_smoke.py 로 먼저 확인하라 (S0-01)."
        )
    # 🔴 2026-09-21 (전수 재검토 · 페이지 가드) — ⛔ `totalCnt` 가 없으면 0 으로 읽어 「받을 것 없음」으로 끝났다.
    #    0 건(정상 XML 에 `<totalCnt>0`)과 **못 읽음**은 다르다 — 못 읽으면 멈춘다 (D-220 fail-closed).
    raw_total = _text(root, "totalCnt")
    if not raw_total.isdigit():
        raise SystemExit(
            f"🚨 목록에 전체 건수(totalCnt)가 없다 — 응답 구조가 바뀌었다 ({raw_total!r})"
        )
    total = int(raw_total)
    rows = [
        (_text(e, "결정문일련번호"), _text(e, "사건명"), _text(e, "결정일자"))
        for e in root.findall("ftc")
    ]
    return total, [r for r in rows if r[0]]


def fetch_body(oc: str, seq: str) -> tuple[bytes | None, str, str, str]:
    """본문 하나. 돌려주는 값은 (payload, 사건명, 결정일자8, 거절사유).

    거절사유가 비어 있으면 성공이다.
    """
    body = law_api._call(law_api.BASE_SERVICE, oc, target="ftc", ID=seq)
    root = law_api._parse(body)
    if root is None:
        # 🚨 본문 조회 실패는 XML 이 아니라 **HTML 오류 페이지**로 온다.
        #    OC 문제와 「없는 일련번호」가 같은 모양이라 둘 다 말해 준다 (D-51).
        return None, "", "", "XML 이 아니다 — 없는 일련번호이거나 OC 가 틀렸다"
    if len(root) == 0:
        return (
            None,
            "",
            "",
            f"본문이 비었다 — 서버 응답: {(root.text or root.tag).strip()[:80]}",
        )
    if len(body) < MIN_BODY:
        return None, "", "", f"본문이 너무 짧다 ({len(body):,} bytes)"

    name = _text(root, "사건명")
    # 🚨 **결정일자가 없어도 거절하지 않는다.** 1,087건 실측에서 12건이 비어 있었고
    #    (임시중지명령·전자상거래 위반 등) 응답 구조가 바뀐 게 아니라 **원천에 그 값이
    #    없다.** 사건명은 전건에 있으므로 이것만 본다.
    #    D-115 ③ 은 `unknown` 파일명 충돌 이야기였는데, 일련번호가 유일하므로
    #    `{일련번호}.xml` 은 충돌하지 않는다 — 날짜 없는 건은 번호만으로 저장한다.
    day = _norm_date(_text(root, "결정일자"))
    if not name:
        return None, name, day, "사건명을 못 읽었다 — 응답 구조를 확인하라"
    return body, name, day, ""


def collect(
    *,
    query: str,
    search: int,
    sort: str,
    limit: int | None,
    dry_run: bool,
    refetch: bool,
) -> tuple[int, int, int, int, int]:
    """돌려주는 값은 (새로 저장, 건너뜀, 실패, 날짜없음, 목록이 안 준 건수).

    🚨 「날짜없음」은 실패가 아니다 — 저장은 됐고 **연도 분포에서 빠질 뿐이다.**
       S0-17 연도 집계를 할 때 이 수를 모수에서 빼야 한다.
    """
    # ── 규약 1 — 게이트가 첫 줄이다 ──────────────────────────
    registry.require(SOURCE_ID, use="U1")
    oc = env.get("LAW_OC_KEY")

    saved = skipped = failed = undated = seen = listed = 0
    page, total = 1, None
    out_dir = store.raw_dir(FAMILY)

    while True:
        got, rows = list_page(oc, page, query, search, sort)
        if total is None:
            total = got
            label = f"본문검색 「{query}」" if query else "전체"
            print(f"  목록: {label} — {total:,}건 (한 장 {ROWS}건)\n")
            if total == 0:
                return 0, 0, 0, 0, 0
        if not rows:
            break
        listed += len(rows)

        for seq, list_name, list_day in rows:
            if limit and seen >= limit:
                print(f"\n  ⏸ --limit {limit} 에서 멈춘다.")
                return saved, skipped, failed, undated, 0
            seen += 1

            # 🚨 이어받기 — 8,255건이면 호출 간격 0.5초만으로 70분이다.
            #    목록이 이미 일련번호와 결정일자를 주므로 **부르기 전에** 건너뛸 수 있다.
            #    ⚠️ 대신 같은 번호·같은 날짜로 내용이 바뀐 개정본은 못 본다 — `--refetch` 로 강제한다.
            day = _norm_date(list_day)
            if not refetch and (
                # 🔄 09-21 — 원장(다른 기기가 받은 것)도 본다 (`store.already_have`)
                (day and store.already_have(out_dir / f"{seq}_{day}.xml"))
                or store.already_have(out_dir / f"{seq}.xml")
            ):
                skipped += 1
                continue

            payload, name, day2, reason = fetch_body(oc, seq)
            if reason:
                print(f"  ❌ {seq}  {list_name[:36]} — {reason}")
                failed += 1
                continue

            # 🚨 날짜 없는 건은 눈에 띄게 — 연도 분포를 셀 때 빠지는 것들이다
            mark = "✅" if day2 else "⚠️"
            print(f"  {mark} {seq}  {day2 or '········'}  {name[:40]}  ({len(payload):,} B)")
            # 🚨 dry-run 은 **받아 보되 저장하지 않는다.** 응답 모양을 눈으로 보는 것이
            #    목적이므로 호출은 하고, store 는 부르지 않는다 (law_api --dry-run 과 같다).
            if dry_run:
                continue

            path = store.save_raw(
                SOURCE_ID,
                FAMILY,
                f"{seq}_{day2}.xml" if day2 else f"{seq}.xml",
                payload,
                url=f"{law_api.BASE_SERVICE}?target=ftc&ID={seq}",
            )
            if path is None:
                skipped += 1  # 규약 4 — sha256 동일
                continue
            saved += 1
            if not day2:
                undated += 1

        if dry_run:
            print("\n  (dry-run — 첫 장만 훑었다. 저장은 하지 않았다)")
            break
        if page * ROWS >= total:
            break
        page += 1

    # 🔴 2026-09-21 (전수 재검토 · 페이지 가드) — ⛔ 중간에 빈 장이 오면 `break` 로 **조용히** 끝났다.
    #    목록이 준 행이 신고보다 적으면 그 차이를 돌려준다 — 일부 장만 받은 것이라 완료로 찍지 않는다(main).
    unlisted = total - listed if not dry_run and listed < total else 0
    if unlisted:
        print(
            f"\n  🔴 목록이 준 행 {listed:,} < 원천 신고 {total:,} — {unlisted:,}건을 못 봤다 (빈 장에서 멈춤)"
        )
    return saved, skipped, failed, undated, unlisted


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 결정문 본문 수집기 (1층)")
    ap.add_argument(
        "--query",
        default="",
        help="검색어. 비우면 전체 8,255건. 🚨 1층 학습 라벨은 「표시광고」 본문검색 1,087건이다",
    )
    ap.add_argument(
        "--search", type=int, default=2, choices=(1, 2), help="1=사건명 2=본문 (기본 2)"
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="🚨 첫 실행은 5 로 — 응답을 보고 전량을 받는다",
    )
    ap.add_argument(
        "--sort",
        default="ddes",
        choices=("ddes", "dasc", "lasc", "ldes", "nasc", "ndes"),
        help="정렬. 기본 ddes(결정일자 내림차순 = 최근 건부터). "
        "🚨 API 기본값은 lasc(사건명 가나다)라 --limit 이 알파벳 슬라이스가 된다 — "
        "「2개…」「3개…」로 시작하는 담합 건이 앞에 몰려 표본을 오해하게 만든다 (2026-09-02 실제로 겪음)",
    )
    ap.add_argument("--dry-run", action="store_true", help="첫 장만 훑고 저장하지 않는다")
    ap.add_argument("--refetch", action="store_true", help="이미 받은 파일도 다시 부른다")
    a = ap.parse_args()

    try:
        saved, skipped, failed, undated, unlisted = collect(
            query=a.query,
            search=a.search,
            sort=a.sort,
            limit=a.limit,
            dry_run=a.dry_run,
            refetch=a.refetch,
        )
    except (registry.RegistryError, env.MissingKey) as e:
        # 🚨 게이트와 키 부재는 「고치는 법」을 그대로 보여준다 (D-51)
        print(f"\n수집을 시작할 수 없다 —\n{e}\n", file=sys.stderr)
        return 1

    print(
        f"\n새로 저장 {saved}건 · 건너뜀 {skipped}건" + (f" · 🚨 실패 {failed}건" if failed else "")
    )
    if undated:
        # 🚨 실패가 아니다 — 저장은 됐다. 연도 분포의 모수에서만 빼면 된다.
        print(f"⚠️ 그중 {undated}건은 원천에 결정일자가 없다 — 파일명이 번호뿐이다.")
    if not a.dry_run:
        # 🔄 2026-09-21 — 목록이 덜 줬으면 일부 장만 받은 것이다 (본문 실패는 종전대로 — 찍고 종료코드 1 · law_api 와 같다)
        registry.mark_if_complete(
            SOURCE_ID, saved=saved, partial=a.limit is not None or bool(unlisted)
        )
    if failed:
        # 🚨 일부 실패를 0 으로 끝내지 않는다 (D-115).
        print(
            "🚨 실패한 항목이 있다 — 위 사유를 먼저 해결하고 다시 돌린다.",
            file=sys.stderr,
        )
    print("🚨 업체명·피심인 주소가 원본에 그대로 있다. 마스킹은 전처리에서 한다 (D-17).")
    print("🚨 이어서 반드시:  uv run pytest -m gate")
    return 1 if failed or unlisted else 0


if __name__ == "__main__":
    raise SystemExit(main())
