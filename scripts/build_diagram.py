"""scripts/build_diagram.py — 도면 원천(HTML) → PNG (2026-09-12 · D-217).

  uv run python launcher.py diagram            # 원천이 있는 것 전부
  uv run python launcher.py diagram --only p-01-competition

⛔ **PNG 는 생성물이다** — 손으로 고치지 않는다. `assets/diagrams/src/<이름>.html` 을 고치고
   이 명령으로 다시 뽑는다 (D-90). 2026-09-12 에 A-04 가 어긋난 이유가 정확히 이것이었다:
   **원천은 고쳐졌는데 다시 그린 사람이 없었다.**

🚨 **21장 중 원천이 있는 것만 뽑는다.** 나머지는 원천이 저장소 밖에 있거나 없다 —
   `assets/diagrams/README.md` 가 어느 것이 어느 쪽인지 든다. **없는 것을 있다고 하지 않는다** (D-188).

🚨 렌더러는 `scripts/build_pdf.py` 와 **같은 playwright chromium** 을 쓴다 — 스택이 안 는다.
   `uv sync --group docs && uv run playwright install chromium` 이 선행이다.
   🔴 글꼴 검사도 **같은 한 벌**을 쓴다 — `scripts/fontcheck.py` (2026-09-13 · D-220 · D-99).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fontcheck  # noqa: E402  — 글꼴 검사는 PDF 와 한 벌이다 (D-99)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "diagrams" / "src"
OUT = ROOT / "assets" / "diagrams"

#: 🚨 2배율. 기존 21장이 폭 2024px 이라 원천 폭 1012px × 2 로 맞춘다 — 섞이면 발표에서 티 난다.
SCALE = 2
WIDTH = 1012


def build(only: str | None = None) -> int:
    if not SRC.is_dir():
        print(f"🔴 원천 폴더가 없다 — {SRC}")
        return 1
    srcs = sorted(p for p in SRC.glob("*.html") if only is None or p.stem == only)
    if not srcs:
        print(f"🔴 뽑을 원천이 없다 (--only {only!r})" if only else f"🔴 {SRC} 가 비어 있다")
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("🔴 playwright 가 없다 — uv sync --group docs && uv run playwright install chromium")
        return 1

    #: 🔴 **한 벌만 적는다** — 글꼴 이름의 정본은 `plate.css` 다 (D-99).
    css = (SRC / "plate.css").read_text(encoding="utf-8")
    want = {"도면 본문": fontcheck.declared(css, "body")}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # 🚨 뷰포트 높이를 작게 잡는다 — `full_page` 는 max(내용, 뷰포트) 라
        #    800 으로 두면 내용이 짧은 장에 **빈 여백이 붙는다** (A-04 에서 밟았다).
        page = browser.new_page(viewport={"width": WIDTH, "height": 100}, device_scale_factor=SCALE)
        # 🔴 뽑기 전에 잰다 — 한 장이라도 나가면 되돌리기가 비싸다 (2026-09-13 실측: 13장)
        fontcheck.require(page, want, source="assets/diagrams/src/plate.css")
        for s in srcs:
            page.goto(s.as_uri(), wait_until="networkidle")
            target = OUT / f"{s.stem}.png"
            page.screenshot(path=str(target), full_page=True)
            print(
                f"✅ {s.name} → {target.relative_to(ROOT).as_posix()}  ({target.stat().st_size:,}B)"
            )
        browser.close()
    print(f"\n🚨 원천이 있는 것만 뽑았다 — {len(srcs)}장. 나머지는 원천이 없다 (D-188).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="도면 원천(HTML) → PNG (D-217)")
    ap.add_argument("--only", help="원천 파일 이름(확장자 없이)")
    return build(ap.parse_args().only)


if __name__ == "__main__":
    sys.exit(main())
