"""collect/mfds_press.py — 식약처 부당광고 점검 보도자료 수집기 (1층 · 평가 홀드아웃).

  uv run python -m collect.mfds_press --probe     # ① 목록 구조·파라미터를 실물로 확인
  uv run python -m collect.mfds_press --index     # ② 435장 훑어 제목 전량 색인 (약 4분)
  uv run python -m collect.mfds_press --limit 5 --dry-run
  uv run python -m collect.mfds_press            # ③ 색인에서 주제어 걸린 것만 본문 수집

🚨 **세 단이다.** ftc_body 와 같은 「목록 → 본문」인데 여기엔 색인 단계가 하나 더 있다.
   게시판 검색(`srchWord`)이 **무시되기 때문**이다 (2026-09-03 실측 · 아래 참조).
   그래서 4,348건의 제목을 먼저 전량 확보하고, 그 위에서 주제어를 고른다.
   ★ 색인을 따로 두면 **TOPIC 정규식을 바꿔도 다시 훑지 않는다** — 제목이 이미 손에 있다.

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1).
   원본은 data/raw/mfds_press/ 에 무손상 저장하고 덮어쓰지 않는다 (규약 2 · D-92).

──────────────────────────────────────────────────────────────
🚨 **use 가 U1 이 아니라 U3 다.** 레지스트리가 이 소스의 U1(학습)·U2(색인)를 닫아 뒀다.
   등급은 G3(상한 전부 허용)이므로 이것은 **라이선스 제약이 아니라 우리 결정**이다 —
   caution: 「test_holdout 출처로 쓰고 train에는 넣지 않는다」.
   학습 출처(공정위 의결서)와 **기관이 다르므로 편향이 독립적**이고, 그래서 평가용으로
   값이 크다. require(use="U1") 로 부르면 거부되는 것이 정상이다.

🚨 **robots 가 열린 것과 저작물을 써도 되는 것은 다르다.**
   robots.txt 는 `User-agent: *` 에 Disallow 가 없다 (2026-09-03 확인 · 규약 6).
   그러나 식약처 저작권정책은 **공공누리 미부착 게시물은 등록 부서와 사전 협의**를 요구한다.
   → `nuri` 필드를 게시물마다 기록하고, **미부착 건은 격리 디렉터리로 보낸다** (D-18).
      격리는 「받지 않는다」가 아니라 「받되 쓰지 않는다」이다 — 부착 여부 자체가 실측 결과다.

🚨 **살아 있는 게시판이다.** 총량이 2026-09-02 에 4,347 → 09-03 에 4,348 이었다.
   페이지 번호는 시간이 지나면 다른 글을 가리킨다. 그래서 **manifest 의 기준은 페이지가
   아니라 게시물 번호(`ntctxtNo`)** 이고, 조회 시각을 원장에 남긴다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time

from collect import http, registry, store
from preprocess.text import sep_norm

SOURCE_ID = "mfds_press"
FAMILY = "mfds_press"
USE = "U3"  # 🚨 U1 이 아니다 — 위 머리말 참조

LIST_URL = "https://www.mfds.go.kr/brd/m_99/list.do"
VIEW_URL = "https://www.mfds.go.kr/brd/m_99/view.do"

#: ✅ 2026-09-03 실측 — `page` 는 먹는다 (1장·2장이 한 건도 겹치지 않았다).
PAGE_PARAM = "page"
#: 🚨 2026-09-03 실측 — `srchWord` 는 **무시된다.** 「부당광고」로 부른 결과가 1장과
#:    완전히 같았다. 서버가 오류를 내지 않고 **1페이지를 조용히 다시 준다** —
#:    검증 없이 썼다면 4,348건을 검색으로 좁힌 줄 알고 같은 10건만 받았을 것이다.
#:
#:    이름 자체는 맞다 — 폼이 실제로 `srchWord` 를 보낸다(입력 11개: headerQuery ·
#:    detailCollection · necQuery · stopQuery · chkbox · multi_itm_seq · **board_id** ·
#:    seq · **srchWord** · returnType · returnUrl). GET 한 줄로는 안 먹고 `board_id`
#:    같은 짝을 함께 보내야 하는 구조로 보인다.
#:
#:    🚨 **더 파고들지 않았다.** `--index` 가 435장을 4분에 훑고, 색인은 검색보다 낫다 —
#:       제목 전량이 손에 남아 TOPIC 을 고쳐도 다시 훑지 않는다. 검색을 되살리는 것은
#:       **이미 해결된 문제를 다시 푸는 일**이라 하지 않는다.
QUERY_PARAM = "srchWord"

#: 색인 — 제목 전량. 🚨 본문(raw)이 아니라 파생물이다. 목록 페이지 435장 × 216KB 를
#:    통째로 보관하는 것은 낭비이고, 우리가 쓰는 것은 (번호·제목)뿐이다.
INDEX_NAME = "mfds_press_index.jsonl"

#: 🚨 **링크의 쿼리스트링을 통째로 딴다 — 파라미터 이름을 짐작하지 않는다.**
#:    첫 판은 번호만 뽑아 `view.do?ntctxtNo=<번호>` 로 다시 조립했는데, 그 이름이 틀려서
#:    **5건이 전부 정확히 1,455 B 오류 페이지**로 왔다 (2026-09-03 · D-118).
#:    목록이 이미 올바른 링크를 주고 있었다 — 그것을 버리고 짐작으로 다시 만든 것이 잘못이다.
_HREF = re.compile(
    r"""<a[^>]+href=["'][^"']*?view\.do\?([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S
)
#: 파일명에 쓸 번호. 🚨 조회에는 쓰지 않는다 — 조회는 위 쿼리스트링 그대로 한다.
_NO = re.compile(r"(?:ntctxtNo|seq|bbsNo|nttId|no)=(\d+)", re.I)
_TAG = re.compile(r"<[^>]+>")
#: 🚨 태그를 걷어낸 **뒤에** 찾는다. 화면에는 「전체 4348 건」으로 보이지만 원본은
#:    `전체 <span>4348</span> 건` 이라 태그가 낀 채로는 안 잡힌다 (2026-09-03 실측).
_TOTAL = re.compile(r"전체\s*([\d,]+)\s*건")

#: 공공누리 부착 표시. 🚨 없으면 **없다고 기록한다** — 있다고 가정하지 않는다.
#: 🚨 이 패턴도 **짐작이다.** `--diag <번호>` 로 실물에서 확인하고 고친다 —
#:    짐작한 파라미터 이름이 D-118 이었고, 여기서 같은 실수를 반복하지 않는다.
#:    판정이 틀리면 107건이 전부 격리로 가고, 격리는 「사전 협의 전에는 쓰지 않는다」다.
_NURI = re.compile(r"공공누리|kogl|OPEN\s*\d|제\s*\d\s*유형", re.I)

#: `--diag` 가 세어 보는 후보들. 어느 것이 실제로 있는지 눈으로 고른다.
_NURI_CANDIDATES = ["공공누리", "누리", "kogl", "OPEN", "유형", "저작권", "이용허락", "출처표시"]

#: 부당광고 점검 회차를 고르는 말. 🚨 사건명이 아니라 보도자료 제목이라 표현이 흔들린다 —
#:    넓게 잡고 사람이 좁힌다. 좁게 잡으면 무엇을 놓쳤는지 알 수 없다.
#:
#: 🚨 **`sep_norm` 을 거친 제목에 맞춘다** — 구분자를 `·` 로 편 뒤라 여기서는 `·` 만 쓴다.
#:    첫 판은 `허위·?과대` 처럼 가운뎃점만 optional 로 뒀다가 **「표시.광고」·「불법.부당」·
#:    「거짓.과대」 22건을 놓쳤다.** 식약처 보도자료는 마침표로 나열한다 (2026-09-03 · D-117).
TOPIC = re.compile(
    r"부당\s*광고|허위·?과대|과대\s*광고|거짓·?과대|불법·?부당|불법\s*광고"
    r"|온라인\s*광고|광고\s*점검|표시·?광고|의약품\s*둔갑|둔갑한\s*화장품"
)


def is_topic(title: str) -> bool:
    """제목이 부당광고 점검 회차인가. 🚨 **매칭은 정규화문, 보관은 원문**이다."""
    return bool(TOPIC.search(sep_norm(title)))


def _strip(s: str) -> str:
    return html.unescape(_TAG.sub("", s)).strip()


def list_page(page: int, query: str) -> tuple[bytes, list[tuple[str, str, str]]]:
    """목록 한 장. 돌려주는 값은 (원본 바이트, [(번호, 제목, 쿼리스트링)])."""
    url = f"{LIST_URL}?{PAGE_PARAM}={page}"
    if query:
        url += f"&{QUERY_PARAM}={query}"
    body = http.fetch(http.encode(url))
    text = body.decode("utf-8", errors="replace")
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for m in _HREF.finditer(text):
        qs = html.unescape(m.group(1))
        num = _NO.search(qs)
        # 🚨 번호를 못 읽으면 파일명을 만들 수 없다. 조용히 넘기지 않고 건너뛰되,
        #    --probe 가 그런 링크를 세어 보여준다.
        if not num:
            continue
        no = num.group(1)
        if no in seen:
            continue
        seen.add(no)
        rows.append((no, _strip(m.group(2)), qs))
    return body, rows


def probe() -> int:
    """🚨 수집 전에 **한 번은 반드시** 돈다. 값을 추정하지 않기 위한 자리다.

    목록 1장을 받아 ① 총량 ② 뽑힌 게시물 수 ③ 제목 표본 ④ 주제어에 걸리는 비율을 낸다.
    여기서 0건이 나오면 `PAGE_PARAM` · `_LINK` 가 실물과 다른 것이다 — 고치고 다시 돈다.
    """
    body, rows = list_page(1, "")
    total = _TOTAL.search(_strip(body.decode("utf-8", errors="replace")))
    text = body.decode("utf-8", errors="replace")
    print(f"목록 1장 — {len(body):,} bytes")
    print(f"  총량   : {total.group(1) if total else '⬜ 못 읽음'} 건")
    print(f"  뽑힌 글: {len(rows)}건")
    if not rows:
        print(
            "\n🚨 0건이다 — 추정한 값이 실물과 다르다.\n"
            f"   지금 부른 곳: {LIST_URL}?{PAGE_PARAM}=1\n"
            "   ① 목록 링크가 view.do 가 아닐 수 있다 (_LINK)\n"
            "   ② 페이지 파라미터 이름이 다를 수 있다 (PAGE_PARAM)\n"
            "   ③ 목록이 JS 로 채워질 수 있다 — 그러면 이 경로로는 못 받는다\n"
            "   응답에 실제로 들어 있는 view.do 링크 앞 3개:"
        )
        for m in list(re.finditer(r"[^\"']*view\.do[^\"']{0,120}", text))[:3]:
            print(f"     {m.group(0)[:160]}")
        return 1
    hit = [t for _, t, _ in rows if is_topic(t)]
    print(f"  주제어 : {len(hit)}/{len(rows)}건")
    # 🚨 **조회에 실제로 쓸 링크를 눈으로 보여준다.** 이것을 안 보여줘서 파라미터 이름을
    #    짐작으로 조립했고, 오류 페이지 5건을 본문으로 셌다 (D-118).
    print(f"  조회링크: {VIEW_URL}?{rows[0][2][:96]}\n")
    for no, title, _ in rows[:10]:
        mark = "★" if is_topic(title) else " "
        print(f"  {mark} {no:>9}  {title[:60]}")

    # ── 🚨 파라미터가 **실제로 먹는지** 본다. 여기가 이 함수의 핵심이다 ──────
    #    파라미터 이름이 틀리면 서버는 오류를 내지 않고 **1페이지를 조용히 다시 준다.**
    #    그대로 수집을 돌리면 435장을 받아도 같은 10건이고, 로그는 성공으로 보인다.
    #    「되는 것 옆에 안 되는 것이 있으면 안 보인다」와 같은 형태다 (D-115).
    print("\n── 파라미터 검증 — 값을 믿지 않고 **두 번 불러 비교**한다 ──")
    ok = True
    _, p2 = list_page(2, "")
    overlap = {n for n, *_ in rows} & {n for n, *_ in p2}
    if overlap:
        ok = False
        print(f"  🚨 {PAGE_PARAM}  : 1장과 2장이 {len(overlap)}건 겹친다 — 파라미터가 무시된다.")
        print(f"     2장 첫 글: {p2[0][1][:50] if p2 else '(없음)'}")
    else:
        print(f"  ✅ {PAGE_PARAM}  : 1장·2장이 겹치지 않는다 ({len(p2)}건). 페이징이 먹는다.")

    probe_word = "부당광고"
    _, q = list_page(1, probe_word)
    same = {n for n, *_ in rows} == {n for n, *_ in q}
    if same:
        ok = False
        print(f"  🚨 {QUERY_PARAM}: 「{probe_word}」 검색이 1장과 **완전히 같다** — 무시된다.")
        print("     → --index 로 전량을 훑는다. 435장 · 약 4분이면 검색이 없어도 된다.")
        # 🚨 이름을 **추정하지 않는다** — 검색 폼이 실제로 무엇을 보내는지 읽어서 보여준다.
        names = [
            n
            for n in dict.fromkeys(re.findall(r'<input[^>]+name=["\']([^"\']+)', text, re.I))
            if not n.lower().startswith(("_csrf", "csrf"))
        ]
        if names:
            print(f"     실제 폼이 보내는 입력 이름 {len(names)}개: {', '.join(names[:14])}")
            print("     → 이 중 검색어 칸을 찾아 QUERY_PARAM 을 고치면 색인 없이도 좁힐 수 있다.")
    else:
        qhit = sum(1 for _, t, _ in q if is_topic(t))
        print(f"  ✅ {QUERY_PARAM}: 「{probe_word}」 {len(q)}건 · 주제어 {qhit}건. 검색이 먹는다.")
        for no, title, _ in q[:5]:
            print(f"       {no:>9}  {title[:56]}")

    print(
        "\n🚨 제목을 눈으로 보고 TOPIC 정규식이 맞는지 판단하라. 넓게 잡고 좁히는 것이 순서다."
        if ok
        else "\n🚨 위 🚨 를 먼저 고친다. 파라미터가 무시되는 채로 수집을 돌리면 조용히 틀린다."
    )
    return 0 if ok else 1


def _index_rows() -> list[dict[str, str]]:
    """색인 파일을 있는 그대로. 없으면 빈 목록."""
    path = store.derived_dir(FAMILY) / INDEX_NAME
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def build_index(*, restart: bool = False) -> int:
    """435장을 훑어 (번호, 제목, 쿼리스트링)을 전량 색인한다. 본문은 받지 않는다.

    🚨 **본문을 여기서 받지 않는 이유** — 색인은 「무엇이 있는가」이고 수집은 「무엇을
       가져올 것인가」다. 섞으면 TOPIC 정규식을 고칠 때마다 4,348건을 다시 훑게 된다.

    🚨 **한 장마다 파일에 붙인다 — 끝에 한 번 쓰지 않는다** (2026-09-03 · D-118).
       첫 판은 4,348건을 메모리에 모아 마지막에 썼다. 120장에서 `IncompleteRead` 로
       죽자 **1분치가 통째로 사라졌고 남은 것이 한 줄도 없었다.**
       오래 도는 일은 중간에 죽는다 — 죽는 것을 막는 것보다 **죽어도 이어받는** 것이 싸다.
    """
    path = store.derived_dir(FAMILY) / INDEX_NAME
    if restart and path.exists():
        path.unlink()

    prev = [] if restart else _index_rows()
    seen: set[str] = {r["no"] for r in prev}
    # 🚨 옛 판 색인(쿼리스트링 없음)에 이어붙이면 절반만 쓸 수 있는 파일이 된다.
    if prev and any(not r.get("qs") for r in prev):
        print("🚨 기존 색인이 옛 판이다 (쿼리스트링 없음) — 처음부터 다시 만든다.")
        path.unlink()
        prev, seen = [], set()

    added, page = 0, 1
    if seen:
        print(f"  이어받기 — 이미 {len(seen):,}건이 있다.\n")
    fh = path.open("a", encoding="utf-8")
    try:
        while True:
            _, got = list_page(page, "")
            if not got:
                break
            fresh = [(n, t, q) for n, t, q in got if n not in seen]
            # 🚨 겹치면 페이징이 끝났거나 무시된 것이다. 여기서 멈추지 않으면 무한히 돈다.
            if not fresh:
                print(f"\n  ⏸ {page}장에서 새 글이 없다 — 여기가 끝이다.")
                break
            for n, t, q in fresh:
                seen.add(n)
                fh.write(
                    json.dumps(
                        {"no": n, "title": t, "qs": q, "topic": is_topic(t)}, ensure_ascii=False
                    )
                    + "\n"
                )
            fh.flush()  # 🚨 죽어도 여기까지는 남는다
            added += len(fresh)
            if page % 20 == 0 or page == 1:
                print(f"  {page:>3}장 · 누적 {len(seen):,}건")
            page += 1
            time.sleep(0.5)  # 규약 5
    except (http.FetchError, KeyboardInterrupt) as e:
        # 🚨 여기서 삼키지 않는다 — 다만 **어디까지 됐는지**를 먼저 말하고 죽는다.
        fh.close()
        print(
            f"\n🚨 {page}장에서 멈췄다 — {e}\n"
            f"   지금까지 {len(seen):,}건이 {path} 에 남아 있다.\n"
            "   같은 명령을 다시 돌리면 **이어받는다**:"
            "  uv run python -m collect.mfds_press --index",
            file=sys.stderr,
        )
        return 1
    finally:
        if not fh.closed:
            fh.close()

    rows = _index_rows()
    hit = [(r["no"], r["title"]) for r in rows if is_topic(r["title"])]
    print(
        f"\n색인 {len(rows):,}건 (이번에 {added:,}건 추가) · "
        f"주제어 {len(hit):,}건 ({len(hit) * 100 // max(len(rows), 1)}%)"
    )
    print(f"→ {path}")
    print("\n주제어에 걸린 제목 앞 15개 — 🚨 눈으로 보고 TOPIC 을 확정하라:")
    for n, t in hit[:15]:
        print(f"  {n:>9}  {t[:64]}")
    print(
        "\n🚨 **놓친 것**을 보려면 주제어에 안 걸린 제목도 훑어라 — 색인이 있으니 공짜다.\n"
        "   TOPIC 을 고치면 --index 를 다시 돌릴 필요 없이 수집만 다시 돌린다."
    )
    return 0


def read_index() -> list[tuple[str, str, str]]:
    """색인에서 주제어에 걸린 것만. 없으면 빈 목록."""
    out = []
    for r in _index_rows():
        # 🚨 저장된 topic 값이 아니라 **지금의 TOPIC** 으로 다시 본다 —
        #    정규식을 고친 뒤 색인을 다시 훑지 않아도 되게 하는 것이 이 구조의 목적이다.
        if is_topic(r["title"]):
            out.append((r["no"], r["title"], r.get("qs", "")))
    return out


#: 🚨 본문의 최소 크기. 실측에서 오류 페이지가 **1,455 B** 였고 본문은 그보다 훨씬 크다.
#:    law_api.MIN_BODY 와 같은 그물이다 — 이것이 없어서 오류 페이지 5건을
#:    「공공누리 미부착」으로 셌다 (D-118).
MIN_BODY = 4000


def fetch_view(qs: str) -> tuple[bytes | None, bool, str]:
    """게시물 하나. 돌려주는 값은 (원본, 공공누리 부착, 거절사유).

    🚨 **목록이 준 쿼리스트링을 그대로 쓴다.** URL 을 다시 조립하지 않는다 —
       조립하려면 파라미터 이름을 알아야 하고, 그 짐작이 D-118 의 원인이었다.
    """
    body = http.fetch(http.encode(f"{VIEW_URL}?{qs}"))
    if len(body) < MIN_BODY:
        # 🚨 공공누리 판정을 하기 **전에** 거절한다. 오류 페이지에는 공공누리 표시가
        #    없으므로, 크기를 안 보면 전부 「미부착」으로 세어 격리 디렉터리에 쌓인다.
        return None, False, f"본문이 너무 짧다 ({len(body):,} B) — 오류 페이지일 수 있다"
    return body, bool(_NURI.search(body.decode("utf-8", errors="replace"))), ""


def diag(no: str) -> int:
    """게시물 하나를 받아 **공공누리 표시가 실제로 어떻게 들어 있는지** 보여준다.

    🚨 `_NURI` 정규식은 짐작이다. 짐작이 틀리면 전부 「미부착」이 되어 격리되고,
       격리된 것은 사전 협의 전까지 못 쓴다 — 그래서 눈으로 한 번 확인한다.
    """
    targets = {n: qs for n, _, qs in read_index()}
    qs = targets.get(no)
    if not qs:
        print(f"🚨 색인에 {no} 이 없다. --index 를 먼저 돌리거나 다른 번호를 고르라.")
        return 1
    body, nuri, reason = fetch_view(qs)
    if reason:
        print(f"🚨 {reason}")
        return 1
    text = body.decode("utf-8", errors="replace")
    print(f"게시물 {no} — {len(body):,} B · 현행 판정: {'✅ 부착' if nuri else '🚨 미부착'}\n")
    print("── 후보 낱말이 실제로 몇 번 나오나 ──")
    for word in _NURI_CANDIDATES:
        cnt = len(re.findall(re.escape(word), text, re.I))
        print(f"  {word:8} {cnt:>4}회")
    # 🚨 **낱말별로** 보여준다. 한 덩어리로 앞 몇 개만 찍으면 흔한 낱말(「누리집」·
    #    `window.open`)이 자리를 다 먹고 정작 드문 낱말을 못 본다 — 실제로 그랬다.
    print("\n── 낱말별 문맥 (각 2개) ──")
    for word in _NURI_CANDIDATES:
        hits = list(re.finditer(re.escape(word), text, re.I))
        if not hits:
            continue
        print(f"\n  [{word}]")
        for m in hits[:2]:
            chunk = _strip(text[max(0, m.start() - 110) : m.end() + 110])
            print(f"    …{chunk[:170]}…")

    # 🚨 보도자료 본문은 **첨부(HWP·PDF)에 있는 경우가 많다.** 광고 문구 예시가 거기
    #    실리면 HTML 만 받아서는 회피 표기를 셀 수 없다 — 무엇이 붙어 있는지 본다.
    print("\n── 첨부 링크 ──")
    files = [
        html.unescape(m.group(0))
        for m in re.finditer(r"""[^"']*(?:fileDown|download|/board/file)[^"']*""", text, re.I)
    ]
    for f in dict.fromkeys(files[:6]):
        print(f"    {f[:130]}")
    if not files:
        print("    ⬜ 없다 — 본문이 HTML 안에 있다는 뜻이다.")

    body_text = _strip(re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text))
    print(f"\n── 태그·스크립트를 걷어낸 텍스트: {len(body_text):,}자 (원본 {len(text):,}자) ──")
    print("\n🚨 위를 보고 `_NURI` 를 실물에 맞춘다. 맞춘 뒤 --limit 5 --dry-run 으로 다시 본다.")
    return 0


def collect(
    *, query: str, limit: int | None, dry_run: bool, topic_only: bool
) -> tuple[int, int, int, int]:
    """돌려주는 값은 (새로 저장, 건너뜀, 🚨 공공누리 미부착, 실패)."""
    # ── 규약 1 — 게이트가 첫 줄이다 ──────────────────────────
    # 🚨 use=U3. U1 로 부르면 레지스트리가 거부하고, 그것이 옳은 동작이다.
    registry.require(SOURCE_ID, use=USE)

    saved = skipped = nonuri = failed = seen = 0
    sizes: list[int] = []
    out_dir = store.raw_dir(FAMILY)
    quarantine = store.raw_dir(f"{FAMILY}_격리")

    # 🚨 색인이 먼저다. 없으면 무엇을 받을지 모른다 — 게시판 검색이 무시되기 때문이다.
    targets = read_index()
    if not targets:
        raise FileNotFoundError(
            "색인이 없다 (또는 주제어에 걸린 글이 없다).\n"
            "   먼저:  uv run python -m collect.mfds_press --index\n"
            "   🚨 게시판 검색(srchWord)이 무시되므로 색인 없이는 4,348건에서 고를 수 없다."
        )
    if any(not qs for _, _, qs in targets):
        raise FileNotFoundError(
            "색인이 옛 판이다 — 링크 쿼리스트링이 없다.\n"
            "   다시:  uv run python -m collect.mfds_press --index\n"
            "   🚨 번호만으로 URL 을 조립하면 파라미터 이름을 짐작하게 되고, 그것이 D-118 이었다."
        )
    print(f"  색인 {len(targets):,}건이 주제어에 걸렸다 (전체 4,348건 중)\n")

    for no, title, qs in targets:
        if limit and seen >= limit:
            print(f"\n  ⏸ --limit {limit} 에서 멈춘다.")
            break
        seen += 1

        # 규약 4 — 격리 쪽도 함께 본다. 안 그러면 미부착 건을 매번 다시 받는다.
        if (out_dir / f"{no}.html").exists() or (quarantine / f"{no}.html").exists():
            skipped += 1
            continue

        body, nuri, reason = fetch_view(qs)
        if reason:
            print(f"  ❌ {no:>9}  {title[:46]} — {reason}")
            failed += 1
            continue
        sizes.append(len(body))
        mark = "✅" if nuri else "🚨"
        print(f"  {mark} {no:>9}  {title[:52]}  ({len(body):,} B)")
        if not nuri:
            nonuri += 1
        if dry_run:
            continue

        # 🚨 미부착 건도 **받아서 격리**한다. 안 받으면 「몇 건이 미부착인지」를
        #    영영 못 세고, 그 수가 없으면 사전 협의를 요청할 근거도 없다.
        path = store.save_raw(
            SOURCE_ID,
            FAMILY if nuri else f"{FAMILY}_격리",
            f"{no}.html",
            body,
            url=f"{VIEW_URL}?ntctxtNo={no}",
        )
        if path is None:
            skipped += 1  # 규약 4 — sha256 동일
            continue
        saved += 1
        time.sleep(0.5)  # 규약 5

    if dry_run:
        print("\n  (dry-run — 저장하지 않았다)")
    # 🚨 **크기가 전부 같으면 본문이 아니다.** 1,455 B 오류 페이지 5건이 그렇게 왔고,
    #    그때는 개별 크기를 눈으로 보고서야 알았다. 이제는 코드가 먼저 말한다 (D-118).
    if len(sizes) >= 3 and len(set(sizes)) == 1:
        print(
            f"\n🚨 받은 {len(sizes)}건이 **전부 {sizes[0]:,} B 로 같다** — 본문이 아니라"
            " 같은 페이지를 반복해서 받고 있을 수 있다. 하나를 열어 눈으로 확인하라."
        )
    return saved, skipped, nonuri, failed


def main() -> int:
    ap = argparse.ArgumentParser(description="식약처 부당광고 점검 보도자료 수집기")
    ap.add_argument("--probe", action="store_true", help="① 목록 구조·파라미터를 실물로 확인한다")
    ap.add_argument("--index", action="store_true", help="② 435장 훑어 제목 전량 색인 (약 4분)")
    ap.add_argument(
        "--restart", action="store_true", help="--index 를 처음부터 다시 (기본은 이어받기)"
    )
    ap.add_argument("--diag", metavar="번호", help="한 건을 받아 공공누리 표시를 실물로 확인한다")
    ap.add_argument("--limit", type=int, default=None, help="🚨 첫 실행은 5 로")
    ap.add_argument("--dry-run", action="store_true", help="받아 보되 저장하지 않는다")
    a = ap.parse_args()

    if a.probe:
        return probe()
    if a.index:
        return build_index(restart=a.restart)
    if a.diag:
        return diag(a.diag)

    try:
        saved, skipped, nonuri, failed = collect(
            query="", limit=a.limit, dry_run=a.dry_run, topic_only=True
        )
    except registry.RegistryError as e:
        print(f"\n수집을 시작할 수 없다 —\n{e}\n", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 1
    except http.FetchError as e:
        print(
            f"\n🚨 받아오지 못했다 — {e}\n   --probe 로 목록이 열리는지 먼저 본다.", file=sys.stderr
        )
        return 1

    print(
        f"\n새로 저장 {saved}건 · 건너뜀 {skipped}건" + (f" · 🚨 실패 {failed}건" if failed else "")
    )
    if nonuri:
        # 🚨 이것은 실패가 아니라 **실측 결과**다. 수를 알아야 협의를 요청할 수 있다.
        print(
            f"🚨 공공누리 미부착 {nonuri}건 — data/raw/{FAMILY}_격리/ 로 보냈다.\n"
            "   식약처 저작권정책상 등록 부서와 **사전 협의** 전에는 쓰지 않는다 (D-18)."
        )
    if saved and not a.dry_run:
        registry.mark_collected(SOURCE_ID)
        print("collected_at 을 원장에 기록하고 data_sources.yaml 을 재생성했다.")
    if failed:
        print("🚨 실패한 항목이 있다 — 위 사유를 먼저 해결하고 다시 돌린다.", file=sys.stderr)
    print("🚨 이 소스는 U1(학습) deny 다 — **test_holdout 전용**이다. train 에 넣지 않는다.")
    print("🚨 이어서 반드시:  uv run pytest -m gate")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
