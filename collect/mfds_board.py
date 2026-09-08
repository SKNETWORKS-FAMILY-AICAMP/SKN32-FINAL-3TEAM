"""collect/mfds_board.py — 식약처 게시물 **첨부 수집기** (자료실·안내서·사례집 공용).

  uv run python -m collect.mfds_board mfds_casebook --use U3 --dry-run
  uv run python -m collect.mfds_board mfds_casebook --use U3

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1).
   원본은 data/raw/<소스id>/ 에 무손상 저장하고 덮어쓰지 않는다 (규약 2 · D-92).

──────────────────────────────────────────────────────────────
🚨 **한 게시물에서 첨부만 받는다.** 목록을 훑지 않는다 — 레지스트리의 `url` 이
   이미 그 게시물을 가리키고 있고, 그것이 2인 확인이 덮은 화면이다.
   목록 순회가 필요한 소스(`mfds_press`)는 자기 수집기를 따로 갖는다.

🔄 **PDF 를 우선하고, PDF 가 없으면 hwp 를 받는다** (2026-09-08 · D-148).

   원래는 「PDF 만」이었다. 같은 자료가 `.hwpx` 와 `.pdf` 로 두 벌 붙고 내용이 같기 때문이다.
   🚨 그런데 `mfds_special_use_guide`(특수용도식품 표시·광고 해설서)는 **hwp 단독**이라
      이 수집기로는 아예 못 받았다 — 값 A 인 1층 자료가 규칙 한 줄 때문에 막혀 있었다.
   ★ 「PDF 만」이 막으려던 것은 **중복**이지 hwp 가 아니다. 목적으로 돌아가면
     「PDF 가 있으면 그것만, 없으면 hwp」가 같은 목적을 이루면서 자료를 잃지 않는다.
     **플래그로 사람에게 묻지 않는다** — 판단이 필요한 자리가 아니다.

   🚨 뷰어 변환본(`/common/convertDocViewer.do` 의 xhtml)을 받지 **않는다.**
      텍스트는 나오지만 **표 셀이 줄로 흩어져 「유형 │ 내용」 대응이 무너진다**(D-138 실측).
      원본을 받아 두면 나중에 표를 살려 파싱할 수 있지만, 변환본으로 받으면 되돌릴 수 없다.
      규약 2 — 수집기는 파싱하지 않는다.

🚨 **링크를 조립하지 않는다** — 게시물 HTML 이 준 `down.do?…&file_seq=N` 을 그대로 쓴다.
   번호만 뽑아 URL 을 다시 만들었다가 오류 페이지 5건을 본문으로 셌다 (D-118 ①).

🚨 **이미지는 뽑지 않는다.** 사례집의 적발 광고 캡처는 **광고주 저작물**이라
   D-132(제24조의2)의 대상이 아니고 D-18 에서 G1(미추출)이다.
   PDF 를 원본으로 보관하는 것과 캡처를 뽑아 쓰는 것은 다르고, 그 경계가 전처리에 있다.
   → 문구만 취하고 그 조각은 **G2 · 40자 상한 · NOREDIST** 로 다룬다 (D-133).

🚨 **use 를 인자로 받는다.** 소스마다 열린 용도가 다르다 — `mfds_casebook` 은
   **U1(학습) deny** 이고 U3·U4 만 열려 있다. 기본값을 두지 않는 이유는
   「무엇으로 쓰려고 받는가」를 부르는 사람이 매번 밝히게 하기 위해서다 (D-15).
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from urllib.parse import urljoin

from collect import http, registry, store

#: 첨부 파일명 ↔ `down.do` 링크 쌍. `mfds_press` 와 같은 모양이다.
_ATTACH = re.compile(
    r"<strong>([^<]{5,200}\.(?:hwpx?|pdf|zip|xlsx?|pptx?))</strong>\s*"
    r'<a\s+href="([^"]*down\.do[^"]*)"',
    re.I | re.S,
)
_PDF = re.compile(r"\.pdf$", re.I)
_HWP = re.compile(r"\.hwpx?$", re.I)

#: 확장자별 **매직바이트와 최소 크기**. 🚨 크기만 보면 오류 페이지가 통과한다 (D-118 ②).
#:    hwp 5.x 는 OLE2 복합문서, hwpx 는 ZIP(OOXML 계열)이다.
KIND = {
    "pdf": (b"%PDF", 20_000),
    "hwp": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 20_000),
    "hwpx": (b"PK\x03\x04", 20_000),
}
#: 파서가 빗나갔을 때 **실물을 보여 주기 위한** 그물. 판정에는 쓰지 않는다.
_RAW_DOWN = re.compile(r"""[^"']*down\.do[^"']*""", re.I)
_TAG = re.compile(r"<[^>]+>")
#: 오류 페이지·빈 파일 그물 (D-118 ②). 🚨 크기 **와** 매직바이트 둘 다 본다.
MIN_PDF = 20_000


def _slug(name: str) -> str:
    """파일명을 안전하게. 🚨 원본 이름을 버리지 않는다 — manifest 가 URL 을 들고 있지만
    사람이 디렉터리를 열었을 때 무엇인지 알아볼 수 있어야 한다."""
    s = _TAG.sub("", html.unescape(name)).strip()
    s = re.sub(r"[\\/:*?\"<>|]+", "_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:120]


def attachments(page_html: str) -> list[tuple[str, str]]:
    """게시물 HTML 에서 [(파일명, 상대 URL)].

    🔄 **PDF 가 하나라도 있으면 PDF 만, 없으면 hwp/hwpx** (D-148).
       둘을 섞어 받지 않는다 — 같은 자료를 두 벌 보관하는 것이 원래 막으려던 것이다.
    """
    pdf: list[tuple[str, str]] = []
    hwp: list[tuple[str, str]] = []
    for name, href in _ATTACH.findall(page_html):
        name = html.unescape(name).strip()
        href = html.unescape(href).strip()
        if _PDF.search(name):
            pdf.append((name, href))
        elif _HWP.search(name):
            hwp.append((name, href))
    return pdf or hwp


def collect(source_id: str, *, use: str, dry_run: bool) -> tuple[int, int, int]:
    """돌려주는 값은 (새로 저장, 건너뜀, 실패)."""
    # ── 규약 1 — 게이트가 첫 줄이다 ──────────────────────────
    spec = registry.require(source_id, use=use)

    url = (spec.get("url") or "").strip()
    if not url.startswith("http"):
        raise ValueError(
            f"{source_id!r} 의 url 이 게시물 주소가 아니다 ({url!r}).\n"
            "   🚨 이 수집기는 **레지스트리의 url 이 가리키는 게시물 하나**에서 첨부를 받는다 —\n"
            "      그 화면이 2인 확인이 덮은 자리다. 주소를 손으로 넘기는 인자는 두지 않는다."
        )

    print(f"  게시물: {url}\n")
    page = http.fetch(http.encode(url)).decode("utf-8", errors="replace")
    links = attachments(page)
    if links:
        kind = "PDF" if _PDF.search(links[0][0]) else "hwp — 🚨 PDF 가 없어 원본으로 받는다"
        print(f"  첨부 {len(links)}개 · {kind}")
    if not links:
        # 🚨 「못 찾았다」로 끝내지 않는다 — 응답에 실제로 들어 있는 링크를 보여 준다.
        #    없는 것인지 파서가 틀린 것인지 그것으로 갈린다 (D-118).
        found = [m.group(0)[:90] for m in _RAW_DOWN.finditer(page)][:3]
        raise FileNotFoundError(
            "PDF·hwp 첨부를 하나도 못 찾았다.\n"
            "   ① 게시물에 첨부가 없다 (본문만 있을 수 있다)\n"
            "   ② 게시판 스킨이 달라 파일명·링크 구조가 다르다\n"
            "   응답에 실제로 있는 down.do 링크 앞 3개:\n"
            + ("\n".join(f"     {x}" for x in found) if found else "     (하나도 없다)")
        )

    saved = skipped = failed = 0
    out_dir = store.raw_dir(source_id)
    for idx, (name, href) in enumerate(links, 1):
        dest = f"{idx:02d}_{_slug(name)}"
        if (out_dir / dest).exists():
            skipped += 1
            continue

        full = urljoin(url, href)
        try:
            body = http.fetch(http.encode(full))
        except http.FetchError as e:
            print(f"  ❌ {name[:56]} — {e}")
            failed += 1
            continue
        ext = name.rsplit(".", 1)[-1].lower()
        magic, floor = KIND.get(ext, (b"", MIN_PDF))
        if len(body) < floor or (magic and not body.startswith(magic)):
            head = body[:16].decode("latin-1", "replace")
            print(f"  ❌ {name[:46]} — {ext} 가 아니다 ({len(body):,} B · {head!r})")
            failed += 1
            continue

        print(f"  ✅ {name[:60]}  ({len(body):,} B)")
        if dry_run:
            continue
        if store.save_raw(source_id, source_id, dest, body, url=full) is None:
            skipped += 1
            continue
        saved += 1
        time.sleep(0.5)  # 규약 5

    if dry_run:
        print("\n  (dry-run — 저장하지 않았다)")
    return saved, skipped, failed


def main() -> int:
    ap = argparse.ArgumentParser(description="식약처 게시물 첨부 수집기 (자료실·안내서·사례집)")
    ap.add_argument("source_id", help="레지스트리 소스 id (예: mfds_casebook)")
    ap.add_argument(
        "--use",
        required=True,
        choices=("U1", "U2", "U3", "U4"),
        help="🚨 무엇으로 쓰려고 받는가. 소스마다 열린 용도가 다르다 (mfds_casebook 은 U1 deny)",
    )
    ap.add_argument("--dry-run", action="store_true", help="받아 보되 저장하지 않는다")
    a = ap.parse_args()

    try:
        saved, skipped, failed = collect(a.source_id, use=a.use, dry_run=a.dry_run)
    except (registry.RegistryError, FileNotFoundError, ValueError) as e:
        print(f"\n수집을 시작할 수 없다 —\n{e}\n", file=sys.stderr)
        return 1
    except http.FetchError as e:
        print(f"\n🚨 받아오지 못했다 — {e}", file=sys.stderr)
        return 1

    print(
        f"\n새로 저장 {saved}건 · 건너뜀 {skipped}건" + (f" · 🚨 실패 {failed}건" if failed else "")
    )
    if saved and not a.dry_run:
        registry.mark_collected(a.source_id)
        print("collected_at 을 원장에 기록하고 data_sources.yaml 을 재생성했다.")
        print(
            "🚨 **캡처는 뽑지 않는다** — 적발 광고 이미지는 광고주 저작물이라 G1 이다.\n"
            "   문구만 취하고 그 조각은 G2 · 40자 상한 · NOREDIST 로 다룬다 (D-133 · D-18)."
        )
    print("🚨 이어서 반드시:  python launcher.py check")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
