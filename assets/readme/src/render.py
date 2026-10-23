import pathlib
import sys

from playwright.sync_api import sync_playwright

SRC = pathlib.Path(__file__).parent
OUT = SRC.parent  # assets/readme/ — 결과 PNG 는 이 폴더의 부모에 쓴다 (글꼴: Pretendard 설치 필요)
names = sys.argv[1:] or ["how-it-works", "one-core", "principles", "results"]
with sync_playwright() as p:
    b = p.chromium.launch()
    for theme in ("light", "dark"):
        pg = b.new_page(viewport={"width": 1200, "height": 800}, device_scale_factor=2)
        for n in names:
            pg.goto((SRC / f"{n}.html").as_uri())
            pg.evaluate(f"document.documentElement.dataset.theme='{theme}'")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(150)
            pg.locator(".frame").screenshot(path=str(OUT / f"{n}-{theme}.png"))
            print(n, theme)
    b.close()
