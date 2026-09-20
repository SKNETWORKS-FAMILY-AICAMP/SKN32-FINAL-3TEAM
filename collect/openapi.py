"""오픈API 수집기 — 여러 포털 공용.

🚨 처음 이름은 `data_go_kr.py` 였으나 **틀린 이름이 됐다** — data.go.kr 의 API 유형이
   `LINK` 인 소스는 실제 호출이 **원 기관 포털**로 간다(식품안전나라). 이름이 거짓이 되면
   다음 사람이 그 이름을 믿고 판단한다. 오늘 갈아 둔다.

🚨 **첫 줄이 `registry.require()` 다** (수집기 공통 규약 1). 게이트를 우회하는 경로를 만들지 않는다.

여섯이 한 파일인 이유 — **키가 하나(`DATA_GO_KR_KEY`)이고 호출 규약이 같다.** 소스마다 파일을
만들면 규약 2·3·5·7 을 여섯 번 다시 쓰게 되고, 그중 하나가 빠지는 것이 실제로 일어난다.
다른 것은 **요청주소와 응답 모양뿐**이고 그것은 `collect/endpoints.yaml` 이 진다 (D-89).

    uv run python -m collect.openapi mfds_hf_ingredient --use U1
    uv run python -m collect.openapi mfds_hf_ingredient --use U1 --pages 1   # 첫 장만
    uv run python -m collect.openapi A B C --use U1 --measure               # 규모만 잰다

🚨 첫 실행은 `--pages 1` 로 한다. 응답 모양을 눈으로 보고 나서 전량을 받는다 —
   5,000건을 받아 놓고 필드가 기대와 다른 것을 아는 것이 가장 비싸다.

🔴 **그런데 `--pages 1` 에서 멈춘 채 잊히는 일이 실제로 일어났다** (2026-09-06 전수조사).
   다섯 소스가 `page_0001.json` **한 장씩만** 있었다 — 26~60 KB.
   2026-09-02 에 검문소를 통과시키고 2단계(전량)로 넘어가지 않은 것이다.

   🚨 나쁜 것은 멈춘 것이 아니라 **멈춘 자리가 아무 데도 안 남은 것**이다.
      이 수집기는 1장을 받을 때 「전체 건수」를 **화면에 찍는다.** 그 숫자가 그때
      터미널에 있었고, 원장에도 코드에도 남지 않았다. 나흘 뒤엔 아무도 모른다.
      `ftc` 664건이 나흘간 드러나지 않은 것과 **같은 모양**이다 (§3⑥).

   그래서 `--measure` 를 뒀다 — **규모만 재고 저장하지 않는다.** 재는 일과 받는 일을
   갈라 두면 「재기만 하고 안 받았다」가 원장의 빈 칸으로 남아 눈에 띈다.
   🚨 잰 값은 반드시 `docs/00_사실원장.md` 에 적는다 (D-54). 화면은 증언이 아니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml

from collect import env, http, registry, store

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = Path(__file__).resolve().parent / "endpoints.yaml"
ROWS = 100  # 한 장에 받을 건수. 🚨 크게 잡지 않는다 — 실패 시 재시도 비용이 커진다


def spec_of(source_id: str) -> dict[str, Any]:
    """요청주소를 읽는다. 🚨 비어 있으면 **추정하지 않고 거부**한다."""
    table = yaml.safe_load(ENDPOINTS.read_text(encoding="utf-8")) or {}
    ep = table.get(source_id)
    if not ep or not ep.get("url"):
        portal = registry.spec(source_id).get("url", "(포털 URL 미기재)")
        raise registry.RegistryError(
            f"{source_id!r} 의 요청주소가 collect/endpoints.yaml 에 없다.\n"
            f"  🚨 추정하지 않는다 — 틀린 주소는 빈 칸보다 나쁘다.\n"
            f"  포털 상세기능에서 요청주소를 확인해 적는다: {portal}\n"
            f"  `python launcher.py probe {source_id}` 가 화면에서 후보를 주워 준다."
        )
    return ep


def fetch_page(ep: dict[str, Any], key: str, page: int) -> bytes:
    """🚨 포털마다 호출 규약이 다르다 — 같은 「오픈API」가 같은 모양을 뜻하지 않는다.

    query : data.go.kr      ?serviceKey=..&pageNo=..&numOfRows=..
    path  : 식품안전나라     /{keyId}/{serviceId}/{dataType}/{startIdx}/{endIdx}
    """
    fmt = ep.get("fmt") or "json"
    if (ep.get("style") or "query") == "path":
        sid = ep.get("service_id")
        if not sid:
            raise registry.RegistryError(
                "style: path 인데 service_id 가 없다. 🚨 하이픈까지 화면 그대로 적는다 (예: I-0040)"
            )
        start = (page - 1) * ROWS + 1  # 🚨 1-based 포함 구간이다
        return http.fetch(f"{ep['url']}/{key}/{sid}/{fmt}/{start}/{start + ROWS - 1}")

    params = {"serviceKey": key, "pageNo": page, "numOfRows": ROWS, **(ep.get("params") or {})}
    if fmt == "json":
        params.setdefault("type", "json")
    return http.fetch(f"{ep['url']}?{urlencode(params, safe='')}")


def total_of(payload: bytes) -> int | None:
    """전체 건수. 🚨 못 읽으면 None 을 내고 **추정하지 않는다** — 페이징은 빈 장에서 멈춘다."""
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    def walk(o: Any) -> int | None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in {"totalcount", "total_count", "totalcnt"}:
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        pass
                found = walk(v)
                if found is not None:
                    return found
        elif isinstance(o, list):
            for v in o:
                found = walk(v)
                if found is not None:
                    return found
        return None

    return walk(obj)


def measure(source_ids: list[str], use: str) -> int:
    """전량 규모만 잰다 — 소스당 호출 **1번**, 저장 **없음** (§3⑥).

    🚨 저장하지 않는 것이 이 함수의 요점이다.
       ① 원장은 「raw 에 무엇이 들어왔는가」의 증언이다 (규약 3). 안 받았으면 줄을 쓰지 않는다.
       ② 그래야 「규모는 알지만 아직 안 받았다」가 원장의 **빈 칸**으로 남는다.
          받아 버리면 그 상태가 안 보이고, 안 보이면 넉 달 뒤에도 1장짜리로 남는다.

    🚨 `registry.require()` 는 그대로 부른다 — 규약 6 은 수집이 아니라 **접근**의 조건이다.
       재는 것도 남의 서버를 두드리는 일이다.

    🚨 한 소스가 실패해도 멈추지 않는다. 다섯을 재려고 부른 사람에게 첫 실패로
       나머지 넷을 안 보여주면, 그 사람은 다시 네 번 부른다 — 서버를 네 번 더 두드린다.
    """
    env.load()
    print(f"\n  {'source_id':26}{'전체 건수':>12}{'장':>8}   {'예상 소요':>10}")
    worst = 0
    for source_id in source_ids:
        try:
            registry.require(source_id, use=use)  # 🚨 규약 1 — 재는 것도 접근이다
            ep = spec_of(source_id)
            key = env.get(
                "FOODSAFETY_KEY" if (ep.get("style") or "query") == "path" else "DATA_GO_KR_KEY"
            )
            total = total_of(fetch_page(ep, key, 1))
        except Exception as e:  # noqa: BLE001 — 실패 사유가 곧 결과다
            worst = 1
            print(f"  {source_id:26}{'🔴 실패':>12}   {type(e).__name__}: {e}")
            continue
        if total is None:
            worst = 1
            print(f"  {source_id:26}{'🔴 못 읽음':>12}        응답에 전체 건수가 없다")
            continue
        pages = -(-total // ROWS)  # 올림
        # 규약 5 — 공공기관 서버 간격 0.5초. 재는 사람이 각오할 시간이 여기서 나온다.
        secs = pages * 0.5
        span = f"{secs / 60:.0f}분" if secs >= 60 else f"{secs:.0f}초"
        print(f"  {source_id:26}{total:>12,}{pages:>8,}   {span:>10}")

    print("\n  🚨 저장하지 않았다. 잰 값을 docs/00_사실원장.md 에 적고 나서 받는다 (D-54).")
    return worst


#: 🔴 **응답이 데이터인지 오류인지 본다** (2026-09-08 · D-147).
#:
#: ⛔ 식품안전나라가 이렇게 답한 것을 **그대로 raw 에 저장했다** —
#:      {"I-0050":{"total_count":"0","RESULT":{
#:        "MSG":"09시~19시에는 서비스가 제한됩니다·","CODE":"ERROR-503"}}}
#:    146바이트짜리 오류 본문이 `page_0001.json` 이 되고 원장에 「저장」으로 적혔다.
#:    `mfds_hf_individual` 은 원래 파일이 없던 자리라 **doctor 가 다음부터 「있다」고 본다** —
#:    **없는 것보다 나쁘다. 쓰레기가 정상으로 보인다.**
#:
#: ★ 화면에는 「전체 건수: 0」이 찍혔다. **신호는 있었는데 아무도 안 멈췄다.**
def result_code(payload: bytes) -> tuple[str, str] | None:
    """응답의 결과 코드와 메시지. 🚨 못 읽으면 None — **추정하지 않는다.**"""
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    def walk(o: Any) -> tuple[str, str] | None:
        if isinstance(o, dict):
            if "CODE" in o and isinstance(o.get("CODE"), str):
                return str(o["CODE"]), str(o.get("MSG") or "")
            if "resultCode" in o:
                return str(o["resultCode"]), str(o.get("resultMsg") or "")
            for v in o.values():
                got = walk(v)
                if got:
                    return got
        elif isinstance(o, list):
            for v in o:
                got = walk(v)
                if got:
                    return got
        return None

    return walk(obj)


#: 🔴 **행 수가 맞아도 전량이 아니다** (2026-09-08 · D-149).
#:
#:    `mfds_sanctions` 54장을 받으니 행 합계가 **5,381 = 원천 신고 5,381** 로 딱 맞았다.
#:    **맞아서 아무도 안 볼 뻔했다.** 서로 다른 행을 세니 **5,122** 였다 —
#:    236종이 완전히 같은 행으로 두 번 이상 왔다.
#:
#: ★ offset 페이징인데 **정렬 키가 유일하지 않으면** 페이지 경계에서 같은 행이 두 번 나오고,
#:   그만큼 다른 행이 **빠진다.** 즉 259행이 중복인 만큼 **못 받은 행이 있을 수 있다.**
#:   합계가 맞는 것은 「다 받았다」의 근거가 아니다.
#:
#: 🚨 여기서 하는 것은 **세는 것뿐이다.** 파싱해서 저장하지 않는다 (규약 2) —
#:    `total_of` 가 이미 같은 이유로 payload 를 읽는다.
def rows_of(payload: bytes) -> list[dict[str, Any]]:
    """응답 안의 레코드 목록. 🚨 키 이름을 모르는 채로 찾는다 — 원천마다 다르다."""
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    def walk(o: Any) -> list[dict[str, Any]]:
        if isinstance(o, list):
            return [x for x in o if isinstance(x, dict)] if o else []
        if isinstance(o, dict):
            for v in o.values():
                got = walk(v)
                if got:
                    return got
        return []

    return walk(obj)


#: 성공으로 보는 코드. 🚨 **화이트리스트다** — 모르는 코드는 오류로 본다 (D-220 fail-closed).
OK_CODES = frozenset({"INFO-000", "00", "0"})


def collect(source_id: str, use: str, max_pages: int | None) -> int:
    registry.require(source_id, use=use)  # 🚨 규약 1 — 첫 줄
    ep = spec_of(source_id)
    # 쓰는 폴더 — 첫 계열 (store.raw_dir_of 와 같다 · 만들기는 save_raw 가)
    dest = store.family_path(source_id)
    env.load()
    # 🚨 포털마다 키가 다르다. LINK 유형은 원 기관에서 따로 발급받는다 (2026-09-02).
    key = env.get("FOODSAFETY_KEY" if (ep.get("style") or "query") == "path" else "DATA_GO_KR_KEY")

    page, saved, total = 1, 0, None
    n_rows, seen = 0, set()  # 🔴 D-149 — 행 수와 **서로 다른 행 수**를 따로 센다
    while True:
        payload = fetch_page(ep, key, page)
        if total is None:
            total = total_of(payload)
            print(f"  전체 건수: {total if total is not None else '읽지 못함 — 빈 장까지 받는다'}")
        # 🔴 **저장하기 전에 오류인지 본다.** 저장한 뒤엔 쓰레기가 데이터로 보인다.
        rc = result_code(payload)
        if rc and rc[0] not in OK_CODES:
            print(f"\n  🔴 원천이 오류를 돌려줬다 — {rc[0]}")
            print(f"     {rc[1]}")
            print("     🚨 **저장하지 않고 멈춘다.** 오류 본문을 raw 에 넣으면")
            print("        다음부터 doctor 가 「파일 있음」으로 보아 **없는 것보다 나빠진다.**")
            print("     🚨 mark_collected 도 찍지 않는다 — 「받았다」가 거짓이 된다.")
            return 1
        if page == 1 and total == 0:
            print("\n  🔴 첫 장부터 전체 건수가 0 이다 — 저장하지 않고 멈춘다")
            print("     오류 코드가 없어도 받을 것이 없다. 빈 장을 원장에 적을 이유가 없다.")
            return 1
        path = store.save_raw(
            source_id,
            # 🆕 D-254 — 폴더는 소스 id 가 아니라 계열이다(store.FAMILY_OF). ⛔ 종전에는 소스 id 를
            #    그대로 넘겨 `ftc_decisions_api` 가 표(`ftc`)와 다른 `ftc_decisions_api/` 에 썼다 (감사 §1-7).
            dest.name,
            f"page_{page:04d}.json",
            payload,
            url=ep["url"],
        )
        for row in rows_of(payload):
            n_rows += 1
            seen.add(hash(json.dumps(row, sort_keys=True, ensure_ascii=False)))
        if path:
            saved += 1
        print(f"  page {page:>4} · {len(payload):>9,} bytes {'저장' if path else '동일 — 스킵'}")

        if max_pages and page >= max_pages:
            print(f"  ⏸ --pages {max_pages} 에서 멈춘다. 응답을 눈으로 보고 전량을 받는다")
            break
        if total is not None and page * ROWS >= total:
            break
        if total is None and len(payload) < 200:  # 🚨 빈 장으로 본다
            break
        page += 1

    # 🔴 **2026-09-08 — `--pages` 로 일부만 받고 「수집 완료」를 찍고 있었다.**
    #    `--pages 1` 은 **탐침**이다. 54장 중 1장을 받고 `collected_at` 이 찍히면
    #    원장이 「다 받았다」고 거짓말한다 — 그리고 아무도 다시 안 본다.
    #    🚨 `mfds_hf_board.py` 는 같은 상황에서 안 찍는 규약을 지키고 있었다.
    #       **한쪽 수집기만 고쳐 둔 규약은 규약이 아니다** (오늘 `_ONLY_PARTICLE` 과 같은 자리).
    if max_pages:
        print(f"  🚨 --pages {max_pages} 로 일부만 받았다 — mark_collected 를 찍지 않는다")
    elif saved:
        registry.mark_collected(source_id)  # 규약 3 · 게이트 15
    print(f"\n{source_id} — {saved}장 저장 → {dest.relative_to(store.ROOT)}/")
    if n_rows:
        dup = n_rows - len(seen)
        print(
            f"  받은 행 {n_rows:,} · 서로 다른 행 {len(seen):,}"
            + (f" · 🚨 중복 {dup:,}" if dup else "")
        )
        if total is not None and n_rows == total and dup:
            print(
                "  🔴 **합계는 원천 신고와 맞는데 중복이 있다 — 그만큼 못 받은 행이 있을 수 있다.**"
            )
            print(
                "     offset 페이징인데 정렬 키가 유일하지 않으면 경계에서 같은 행이 두 번 나오고"
            )
            print(
                "     그만큼 다른 행이 빠진다. **합계가 맞는 것은 「다 받았다」의 근거가 아니다** (D-149)."
            )
    if registry.is_g2(source_id):
        print("🚨 G2 다 — 사실 추출 후 원본을 지운다 (D-17 · store.drop_raw_for_g2)")
    return 0


def main(argv: list[str]) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(prog="collect.openapi")
    # 🚨 여럿을 받는다 — `--measure` 는 나란히 놓고 봐야 「어느 것부터」가 정해진다.
    ap.add_argument("source_id", nargs="+")
    ap.add_argument("--use", required=True, choices=sorted(registry.VALID_USES))
    ap.add_argument("--pages", type=int, default=None, help="🚨 첫 실행은 1 로 한다")
    ap.add_argument(
        "--measure",
        action="store_true",
        help="전량 규모만 잰다 — 소스당 호출 1번, 저장 없음 (§3⑥)",
    )
    a = ap.parse_args(argv[1:])

    if a.measure:
        if a.pages is not None:
            # 🚨 둘을 같이 주면 무엇을 기대한 것인지 알 수 없다. 조용히 한쪽을 이기지 않는다.
            ap.error("--measure 와 --pages 는 같이 쓰지 않는다 — 재는 일과 받는 일은 다르다")
        return measure(a.source_id, a.use)

    worst = 0
    for source_id in a.source_id:
        worst = collect(source_id, a.use, a.pages) or worst
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
