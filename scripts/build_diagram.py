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
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "diagrams" / "src"
OUT = ROOT / "assets" / "diagrams"

#: 🚨 2배율. 기존 21장이 폭 2024px 이라 원천 폭 1012px × 2 로 맞춘다 — 섞이면 발표에서 티 난다.
SCALE = 2
WIDTH = 1012

#: 🔴 **한 벌만 적는다** — 폰트 이름은 `plate.css` 가 정본이다 (D-99).
#:    여기 이름을 또 적으면 css 를 고쳐도 검사가 옛 이름을 본다.
_FONT_RE = re.compile(r"font-family:\s*\"([^\"]+)\"")

#: 폭 대조용 글자. 🚨 한글이라야 한다 — 라틴 글자는 대체 폰트도 폭이 비슷하다.
_PROBE = "가나다라마바사"

#: ⛔ `document.fonts.check()` 를 쓰지 않는다 — **없는 폰트에도 `True` 를 낸다**(2026-09-13 실측).
#:    「존재하지않는폰트XYZ」도 `True` 였다. 그것이 D-170 이 말한 **통과만 하는 게이트**다.
#:    ★ 대신 **monospace 와 폭을 견준다** — 대체되면 두 폭이 같아진다.
_MEASURE = """(args) => {
  const c = document.createElement('canvas').getContext('2d');
  c.font = '40px "' + args.f + '", monospace';
  const a = c.measureText(args.s).width;
  c.font = '40px monospace';
  return [a, c.measureText(args.s).width];
}"""


def _require_font(page) -> None:
    """🔴 도면 글꼴이 없으면 **멈춘다.** 조용히 다른 글꼴로 뽑히면 21장이 두 얼굴이 된다.

    ⛔ 2026-09-13 에 실물로 겪었다 — 기기(Windows)에서 뽑았더니 `caBX` 는 사라졌지만
       **글꼴이 대체돼 줄바꿈이 늘고 범례가 박스를 뚫고 나왔다.** 파일 크기가 18% 줄어
       *「뭔가 달라졌다」*는 신호는 있었는데 **멈추는 코드가 없었다** (D-147 과 같은 모양).
    🚨 D-206 이 적어 둔 자리다 — *「리눅스에서 돈 것이 Windows 에서 통과한다는 뜻이 아니다」*.
    """
    css = (SRC / "plate.css").read_text(encoding="utf-8")
    m = _FONT_RE.search(css)
    if not m:
        print(f"🔴 plate.css 에서 font-family 를 못 찾았다 — {SRC / 'plate.css'}")
        raise SystemExit(1)
    want = m.group(1)
    page.set_content("<p>가</p>")
    a, b = page.evaluate(_MEASURE, {"f": want, "s": _PROBE})
    if abs(a - b) < 0.5:
        raise SystemExit(
            f"🔴 도면 글꼴 「{want}」 이 이 기기에 없다 — 대체 글꼴로 뽑히면 **레이아웃이 달라진다.**\n"
            f"   실측: 「{_PROBE}」 폭 {a:.1f}px = monospace {b:.1f}px (대체됐다는 뜻)\n"
            "\n"
            "✅ 고치는 법 — 둘 중 하나\n"
            "   ① 글꼴을 깐다:  https://fonts.google.com/noto/specimen/Noto+Sans+KR\n"
            "      ⚠️ 이름이 정확히 일치해야 한다 — `Noto Sans KR` 은 `Noto Sans CJK KR` 과 다른 이름이다\n"
            "   ② 이 기기에서 안 뽑고, 글꼴이 있는 환경에서 뽑은 PNG 를 받는다\n"
            "\n"
            "🚨 억지로 뽑지 않는다 — 21장 중 몇 장만 글꼴이 다르면 발표에서 티 난다."
        )


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

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # 🚨 뷰포트 높이를 작게 잡는다 — `full_page` 는 max(내용, 뷰포트) 라
        #    800 으로 두면 내용이 짧은 장에 **빈 여백이 붙는다** (A-04 에서 밟았다).
        page = browser.new_page(viewport={"width": WIDTH, "height": 100}, device_scale_factor=SCALE)
        _require_font(page)  # 🔴 뽑기 전에 — 한 장이라도 나가면 되돌리기가 비싸다
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
