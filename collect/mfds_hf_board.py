"""collect/mfds_hf_board.py — 식품안전나라 「건강기능식품 원료별 정보」 게시판 수집기.

  uv run python -m collect.mfds_hf_board --probe          # ① 구조 확인 (저장 없음)
  uv run python -m collect.mfds_hf_board --limit 5        # 🚨 첫 실행은 5 로
  uv run python -m collect.mfds_hf_board                  # 전량 655건

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1).

★ **2층 적법라벨의 실체가 여기 있다.** 상세 본문이 「○ 키 : 값」으로 구조화돼 있고
  그중 **「○ 기능성내용 : 체지방 감소에 도움을 줄 수 있음」이 곧 승인된 표시 문구**다 —
  2층이 찾던 「어떤 표현이 승인되나」의 답이다 (2026-09-02 오한빈 실물 확인 · 09-07 재확인).

🚨 **규약 2 — 파싱하지 않는다.** 상세 HTML 을 그대로 저장하고, 「○ 키 : 값」 해체는
   전처리가 한다. 수집기가 파싱하면 원본이 사라져 되돌릴 수 없다.

──────────────────────────────────────────────────────────────
🚨 왜 `http.fetch`(GET)로 되는가 — 화면은 POST 인데

  게시판 화면은 `document.baseForm.submit()` 으로 **POST** 를 보낸다. 그대로 따라가면
  `collect/http.py` 에 POST 를 더해야 하고, 그것은 간격·재시도·키 가리기(D-111)를
  짊어진 공용 모듈을 건드리는 일이다.
  🔄 **2026-09-07 실측 — 두 엔드포인트 모두 GET 을 받는다.** 그래서 공용 모듈을
     그대로 두고 쿼리스트링으로 부른다. 확인하지 않고 POST 부터 만들었으면
     `http.py` 를 고쳤을 것이다.

🚨🚨 **이 소스는 sha 기반 멱등성이 성립하지 않는다** (2026-09-07 `--limit 5` 가 잡았다)

  같은 URL 을 2분 뒤에 다시 받았더니 **5건 전부 「새 판」**이 떴다. diff 를 내 보니 원인이 둘이다.

      - <span class="con">392</span>
      + <span class="con">393</span>          ← 🔴 **조회수**. 우리가 열 때마다 +1 된다
      - …boardDetail.do?menu_no=2660&menu_grp=…  ← copyUrl·SNS 공유 링크에 **요청 URL 이 박힌다**

  뒤엣것은 `ctgry_type_cd` 를 더하면서 생긴 일회성이지만, **앞엣것은 구조적이다.**
  읽는 행위가 문서를 바꾸므로 **재수집은 반드시 새 판을 만든다.** 655건 × 90KB 가
  받을 때마다 쌓이고, 팀원 5인이 각자 받으면 그만큼 곱해진다.

  🚨 **정규화해서 비교하지 않는다** — 조회수를 지우고 sha 를 내는 것은 수집기가 원본을
     고치는 일이라 규약 2 위반이다. 대신 **받기 전에 디스크를 본다**(아래 `collect`).
  ⬜ **갱신 감지는 미해결이다.** 목록의 `last_updt_dtm` 을 이전 색인과 대조하면 되지만,
     그것은 수집 정책이라 팀장 결정이 필요하다. 지금은 `--refetch` 로 사람이 정한다.

🚨 **`start_idx` 는 레코드 오프셋이 아니라 페이지 번호다** (2026-09-07 실측).
   `start_idx=653` 을 넣으면 **0건**이 온다. 오프셋으로 착각하고 100씩 더하면
   7페이지 중 1페이지만 받고 「다 받았다」가 된다.
   확인 — `show_cnt=100` 일 때 1~6페이지 100건 · 7페이지 55건 · 8페이지 0건 = 655.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import urllib.parse

from collect import http, registry, store

SOURCE_ID = "mfds_hf_ingredient_board"
USE = "U1"
FAMILY = "mfds_hf_board"

BASE = "https://www.foodsafetykorea.go.kr/portal/board"
LIST_URL = f"{BASE}/boardList.do"
DETAIL_URL = f"{BASE}/boardDetail.do"

#: 🚨 화면 폼은 필드가 40개가 넘는다. 실측으로 **없어도 같은 응답이 오는 것**을 다 뺐다.
#:    앞 셋이 게시판을 특정한다 — 메뉴·메뉴그룹·게시판번호.
#:
#: 🚨 **`ctgry_type_cd` 는 빼면 안 된다** (2026-09-07 `--probe` 가 잡았다).
#:    없어도 목록은 정상으로 오는데 **`ctgrynm` 만 빈 문자열이 된다** — 응답이 실패하지
#:    않고 필드 하나가 조용히 비므로, 첫 실행에서 눈으로 안 봤으면 655장을 다 받은 뒤에
#:    「카테고리가 없네」를 알게 됐을 것이다. `ctgry_no`(1207)는 그대로 오기 때문에
#:    **번호는 있는데 이름만 없는** 모양이라 더 안 보인다.
#:    카테고리는 「영양성분 / 기능성 원료 / 개별인정원료」를 가르고, 그것이 2층 라벨을
#:    고시형과 개별인정형으로 나누는 축이다 (레지스트리 caution — API 15074311 과의 겹침 확인).
KEYS = {
    "menu_no": "2660",
    "menu_grp": "MENU_NEW01",
    "bbs_no": "bbs987",
    "ctgry_type_cd": "CTG_TYPE01",
}

PAGE_SIZE = 100


def _url(base: str, **extra: str) -> str:
    return f"{base}?{urllib.parse.urlencode({**KEYS, **extra})}"


def list_page(page: int) -> tuple[bytes, list[dict], int]:
    """목록 한 장. (원문, 행, 전체건수)"""
    raw = http.fetch(_url(LIST_URL, show_cnt=str(PAGE_SIZE), start_idx=str(page)))
    doc = json.loads(raw.decode("utf-8"))
    total = int(doc.get("total_cnt") or 0)
    return raw, list(doc.get("list") or []), total


def build_index(*, dry_run: bool = False) -> tuple[list[dict], int]:
    """전량 목록을 훑어 `ntctxt_no` 를 모은다.

    🚨 빈 장이 나올 때까지 돈다 — `total_cnt` 만 믿고 나누면 마지막 장을 놓친다.
       원천이 수집 중에 늘어날 수 있다(650 → 655, 2026-09-02 → 09-07).
    """
    rows: list[dict] = []
    total = 0
    page = 1
    while True:
        raw, got, total = list_page(page)
        if not got:
            break
        rows.extend(got)
        # 🚨 목록도 raw 에 남긴다 — **카테고리(`ctgrynm`)가 목록에만 있다.**
        #    2026-09-07 실측: 상세 HTML 에 「개별인정원료」가 없다. 목록을 버리면
        #    「이 원료가 개별인정형이었나」를 되물을 자리가 사라진다 (규약 3).
        #    반대로 「○ 기능성내용」은 상세에만 있다 — **둘 다 있어야 2층이 선다.**
        #
        # 🚨 **한 번만 쓴다.** 목록은 갱신 감지를 위해 실행할 때마다 받아야 하는데,
        #    `inqry_cnt`(조회수)가 행마다 박혀 있어 받을 때마다 sha 가 달라진다.
        #    ⛔ 첫 판은 무조건 저장해서 재실행 한 번에 index 6장이 「새 판」으로 늘었다.
        #    실측 — 두 판의 길이는 **같고**(234,176) 다른 필드는 `inqry_cnt` **하나뿐**,
        #    100행 중 8행. 🚨 그 8행은 **우리가 안 읽은 것도 포함**이다. 목록 조회로는
        #    조회수가 오르지 않으므로 **남들이 보면서 오른 것**이다 — 「덜 읽기」로는 못 막는다.
        #    ★ 그래서 갈라 둔다: raw 는 **수집 시점의 증언 1벌**, 재조회는 **받되 저장 안 함**.
        #      `probe` 가 `build/` 에 쓰고 `data/` 에 안 쓰는 것과 같은 구분이다 (게이트 23).
        idx_path = store.raw_dir(FAMILY) / f"hf_board_index_{page:02d}.json"
        if not dry_run and not idx_path.exists():
            store.save_raw(
                SOURCE_ID,
                FAMILY,
                idx_path.name,
                raw,
                url=_url(LIST_URL, show_cnt=str(PAGE_SIZE), start_idx=str(page)),
                rows=len(got),
            )
        print(f"  목록 {page}장 — {len(got)}건 (누적 {len(rows)} / {total})")
        page += 1
    return rows, total


def probe() -> int:
    """① 저장하지 않고 구조만 본다."""
    _raw, got, total = list_page(1)
    print(f"전체 {total}건 · 1장에 {len(got)}건")
    if not got:
        print("🚨 0건이다 — 파라미터가 바뀌었는지 화면을 열어 확인할 것")
        return 1
    r = got[0]
    for k in ("no", "ntctxt_no", "ctgrynm", "titl", "cret_dtm"):
        print(f"  {k:12s} {r.get(k)!r}")
    print("\n🚨 목록의 `cn`(본문)은 비어 있다 — 본문은 상세에서 받는다")
    detail = http.fetch(_url(DETAIL_URL, ntctxt_no=str(r["ntctxt_no"])))
    text = detail.decode("utf-8", errors="replace")
    print(f"  상세 {len(detail):,} bytes")
    for key in ("원료명", "인정번호", "업체명", "기능성내용", "일일섭취량"):
        print(f"    ○ {key} : {'있음' if key in text else '🚨 없음'}")
    return 0


def collect(*, limit: int | None, dry_run: bool, refetch: bool) -> int:
    registry.require(SOURCE_ID, use=USE)

    rows, total = build_index(dry_run=dry_run)
    print(f"목록 {len(rows)}건 (원천 신고 {total})")
    if len(rows) != total:
        print(f"  🚨 목록 수와 원천 신고가 다르다 ({len(rows)} ≠ {total}) — 그대로 기록한다")

    todo = rows[:limit] if limit else rows
    saved = skipped = 0
    if refetch:
        print("🚨 --refetch — 이미 있는 것도 다시 받는다. 조회수 때문에 **전 건이 새 판**이 된다")
    for i, r in enumerate(todo, 1):
        no = str(r.get("ntctxt_no") or "")
        if not no:
            print(f"  🚨 {i}번째 행에 ntctxt_no 가 없다 — 건너뛴다")
            continue
        dest = store.raw_dir(FAMILY) / f"hf_board_{no}.html"
        # 🚨 **받기 전에 디스크를 본다.** 조회수가 매 요청마다 오르므로 다시 받으면
        #    내용이 반드시 달라지고 `save_raw` 가 새 판을 만든다. 규약 4(같으면 스킵)가
        #    이 소스에서는 작동하지 않는다 — 그래서 요청 자체를 막는다.
        #    ★ 공공기관 서버를 덜 두드리는 효과도 같이 온다 (규약 6 의 정신).
        if store.already_have(dest) and not refetch:  # 🔄 09-21 — 원장(다른 기기)도 본다
            skipped += 1
            continue
        url = _url(DETAIL_URL, ntctxt_no=no)
        body = http.fetch(url)
        if dry_run:
            print(f"  [{i}/{len(todo)}] {no} — {len(body):,} bytes (저장 안 함)")
            continue
        path = store.save_raw(SOURCE_ID, FAMILY, f"hf_board_{no}.html", body, url=url)
        if path is None:
            skipped += 1
        else:
            saved += 1
        if i % 50 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] 저장 {saved} · 이미 있음 {skipped}")

    if dry_run:
        print("\n--dry-run — 저장하지 않았다")
        return 0

    print(f"\n저장 {saved} · 이미 있어 건너뜀 {skipped}")
    # 🔴 2026-09-12 — 저장 0 이면 안 찍는다(09-12 655건 전량 스킵에 날짜가 올라갔다) · `--limit` 이면 안 찍는다.
    #    🔄 2026-09-21 — 그 규칙을 `registry.mark_if_complete` 한 곳으로 옮겼다 (D-99). 이 수집기만 지키고 있었다.
    registry.mark_if_complete(SOURCE_ID, saved=saved, partial=bool(limit))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="식품안전나라 건강기능식품 원료별 정보 수집기")
    ap.add_argument("--probe", action="store_true", help="① 구조를 실물로 확인한다 (저장 없음)")
    ap.add_argument("--limit", type=int, default=None, help="🚨 첫 실행은 5 로")
    ap.add_argument("--dry-run", action="store_true", help="받아 보되 저장하지 않는다")
    ap.add_argument(
        "--refetch",
        action="store_true",
        help="🚨 이미 받은 것도 다시 받는다 — 조회수 때문에 전 건이 새 판이 된다",
    )
    a = ap.parse_args()
    if a.probe:
        return probe()
    return collect(limit=a.limit, dry_run=a.dry_run, refetch=a.refetch)


if __name__ == "__main__":
    raise SystemExit(main())
