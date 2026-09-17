"""build_pdf.py — 마크다운 문서를 제출용 PDF로 빌드한다 (D-53).

제출본은 저장소가 아니라 빌드 결과물이므로, 레포에는 이 스크립트만 두고
PDF는 dist/ 에 생성한다(.gitignore 대상).

  python scripts/build_pdf.py docs/01_기획/02_프로젝트기획서.md

동작
  1) 마크다운 -> HTML (표·코드펜스 확장)
  2) h2/h3에서 목차 생성
  3) 1차 렌더 -> 각 항목이 몇 쪽인지 실측 -> 목차에 페이지 번호 주입
  4) 2차 렌더 -> 최종 PDF

의존성:  markdown, playwright(chromium), pdfplumber
폰트   :  Noto Sans CJK KR + Noto Color Emoji 가 설치돼 있어야 한다
         🔴 **없으면 멈춘다** (2026-09-13 · D-220) — `scripts/fontcheck.py` 가 렌더 직전에 잰다.
            ⛔ 종전에는 검사가 없었다. 09-13 에 뽑은 114쪽에 박힌 글꼴을 재 봤더니
               `MalgunGothic`·`GulimChe` 였다 — **선언한 글꼴이 하나도 안 들어갔는데**
               「114쪽 · 목차 미매칭 0건」이 찍혔다. 내용은 맞고 **판형만 조용히 갈렸다.**
            🚨 기존 제출본은 `NotoSansCJKkr` 로 뽑혔다 — 섞으면 발표에서 서체가 튄다.
"""

import argparse
import base64
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import re

import fontcheck  # noqa: E402  — 글꼴 검사는 도면과 한 벌이다 (D-99)
from docmeta import versioned_stem  # noqa: E402  — 버전을 읽는 방법은 한 곳뿐이다

BRAND_INK = "#0C1A2B"
BRAND_BLUE = "#2B5BD7"


#: 🔴 `docs` 그룹은 기본 설치에 없다 (`pyproject.toml` 주석이 그렇게 적어 뒀다) —
#:    5인이 매일 쓰는 것이 아니고 playwright 는 브라우저 바이너리까지 받는다.
#:    ⛔ 그런데 **에러가 그 사실을 안 알려 줬다.** 날 `ModuleNotFoundError` 트레이스백만 나왔고
#:       같은 자리를 두 번 밟았다 — D-51 이 *「에러가 고치는 법을 보여 준다」*고 적은 그 자리다.
_DOCS_GROUP = (
    "🔴 문서 빌드 의존성이 없다 — `docs` 그룹은 기본 설치에 안 들어간다.\n"
    "   uv sync --group docs\n"
    "   uv run playwright install chromium\n"
    "🚨 두 줄을 다 돌린다. 첫 줄은 파이썬 패키지, 둘째 줄은 브라우저 바이너리다."
)


def _need(mod: str):
    """`docs` 그룹 모듈을 부르되, 없으면 **고치는 법을 낸다** (D-51).

    ⛔ 예외를 삼키지 않는다 — 사유를 붙여 다시 낸다 (D-162). 조용히 넘어가면
       PDF 가 안 나온 채 「완료」로 읽힌다.
    """
    import importlib

    try:
        return importlib.import_module(mod)
    except ImportError as e:
        raise SystemExit(f"{_DOCS_GROUP}\n\n   없는 것: {mod}  ({e})") from e


def md_to_html(md_text):
    markdown = _need("markdown")

    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "attr_list", "sane_lists", "def_list", "md_in_html"],
    )


#: 🔴 **문서 안의 그림** — 상대 경로를 data URI 로 박는다 (2026-09-17).
#:    ⛔ 임시 HTML 은 `dist/` 에 쓰고 원본은 `docs/**` 에 있다. 상대 경로를 그대로 두면
#:       브라우저가 `dist/` 기준으로 찾아 **그림이 조용히 빈칸으로 나온다** — 에러도 안 난다.
#:       ★ 도면이 든 첫 문서(`docs/03_데이터/전처리_결과서.md` · 2026-09-17)에서 드러났다.
#:    🚨 `assets/brand` 로고와 **같은 방법**이다(base64 인라인) — 두 번째라 함수로 올렸다 (D-99).
_IMG_SRC = re.compile(r'<img([^>]*?)src="(?!data:|https?:)([^"]+)"')
_IMG_MIME = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def inline_images(html: str, src: str) -> str:
    """상대 경로 그림을 문서 위치 기준으로 찾아 data URI 로 바꾼다.

    🔴 **없으면 멈춘다** (D-72 fail-closed). 빠진 그림을 「완료」로 찍지 않는다 —
       조용히 빈칸이 되는 실패가 이 함수를 만든 이유다.
    """
    base = pathlib.Path(src).resolve().parent

    def sub(m: re.Match) -> str:
        rel = m.group(2)
        path = (base / rel).resolve()
        if not path.exists():
            raise FileNotFoundError(f"🔴 그림이 없다 — {rel}  (문서 기준 {path})")
        mime = _IMG_MIME.get(path.suffix.lower())
        if mime is None:
            raise ValueError(f"🔴 넣을 줄 모르는 그림 형식 — {path.suffix} ({rel})")
        data = base64.b64encode(path.read_bytes()).decode()
        return f'<img{m.group(1)}src="data:{mime};base64,{data}"'

    return _IMG_SRC.sub(sub, html)


def build_html(src, logo_png, title, subtitle, meta_html, footer, cover_skip_lines=4):
    md_text = pathlib.Path(src).read_text(encoding="utf-8")
    body_md = "\n".join(md_text.split("\n")[cover_skip_lines:])
    html_body = md_to_html(body_md)
    html_body = inline_images(html_body, src)

    toc = []

    def anchor(m):
        lvl, txt = int(m.group(1)), m.group(2)
        hid = f"s{len(toc)}"
        if lvl in (2, 3):
            toc.append((lvl, re.sub(r"<[^>]+>", "", txt), hid))
        return f'<h{lvl} id="{hid}">{txt}</h{lvl}>'

    html_body = re.sub(r"<h([234])>(.*?)</h\1>", anchor, html_body, flags=re.S)

    toc_html = "\n".join(
        f'<div class="toc-{lvl}"><a href="#{i}"><span class="t">{t}</span>'
        f'<span class="d"></span><span class="pn">@@PN:{i}@@</span></a></div>'
        for lvl, t, i in toc
    )

    logo = base64.b64encode(pathlib.Path(logo_png).read_bytes()).decode()
    css = CSS.replace("__INK__", BRAND_INK).replace("__BLUE__", BRAND_BLUE)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{title}</title><style>{css}</style></head><body>
<div class="cover"><div class="in">
<img src="data:image/png;base64,{logo}">
<h1>{title}</h1><div class="sub">{subtitle}</div>
<div class="meta">{meta_html}</div></div>
<div class="foot">{footer}</div></div>
<div class="tocpage"><h1 class="toch">목차</h1>{toc_html}</div>
<div style="font-size:1pt;color:#fff">BODYSTARTMARK</div>
{html_body}</body></html>"""


CSS = """
@page { size:A4; margin:20mm 16mm 18mm 16mm; } @page :first { margin:0; }
*{box-sizing:border-box}
body{font-family:'Noto Sans CJK KR','Noto Color Emoji',sans-serif;font-size:9.6pt;
 line-height:1.72;color:#16212E;margin:0}
.cover{height:297mm;width:210mm;page-break-after:always;position:relative;background:__INK__;
 color:#fff;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}
.cover .in{padding:0 26mm}
.cover img{width:78mm;margin-bottom:26mm}
.cover h1{font-size:30pt;margin:0 0 6mm;letter-spacing:-.02em;font-weight:800;line-height:1.25}
.cover .sub{font-size:13pt;color:#9DB3D0;margin:0 0 22mm}
.cover .meta{font-size:10pt;color:#8FA6C4;line-height:2.0;border-top:1px solid #24384F;padding-top:8mm}
.cover .meta b{color:#fff;font-weight:600}
.cover .foot{position:absolute;bottom:22mm;left:26mm;font-size:9pt;color:#5E7591}
.tocpage{page-break-after:always}
h1.toch{font-size:16pt;margin:0 0 8mm;color:__INK__}
.toc-2 a,.toc-3 a{display:flex;text-decoration:none;color:#16212E;align-items:baseline}
.toc-2{font-size:10pt;font-weight:700;margin:3.4mm 0 1mm}
.toc-3{font-size:9pt;margin:1.1mm 0 1.1mm 7mm;color:#42566E;font-weight:400}
.toc-2 .d,.toc-3 .d{flex:1;border-bottom:1px dotted #C6D2E0;margin:0 2mm 1.2mm}
.pn{font-variant-numeric:tabular-nums;color:#6A7C92;font-size:8.6pt;min-width:7mm;text-align:right}
h1{font-size:19pt;margin:0 0 6mm}
h2{font-size:15pt;margin:0 0 5mm;padding:0 0 3mm;border-bottom:2.5px solid __BLUE__;
 color:__INK__;break-before:page;break-after:avoid;letter-spacing:-.01em}
h3{font-size:11.6pt;margin:8mm 0 3mm;color:#12345E;break-after:avoid}
h4{font-size:10.2pt;margin:6mm 0 2.5mm;color:__BLUE__;break-after:avoid}
h5,h6{font-size:9.6pt;margin:5mm 0 2mm;color:#42566E;break-after:avoid}
p{margin:0 0 3.2mm} ul,ol{margin:0 0 3.2mm;padding-left:6mm} li{margin:.9mm 0}
strong{font-weight:700;color:#08111C}
table{width:100%;border-collapse:collapse;margin:3mm 0 5mm;font-size:8.3pt;line-height:1.55}
th,td{border:.5px solid #CFDAE7;padding:1.6mm 2mm;text-align:left;vertical-align:top;word-break:break-word}
th{background:#EDF2F9;font-weight:700;color:__INK__}
tr{break-inside:avoid} thead{display:table-header-group}
code{font-family:'Noto Sans Mono CJK KR','DejaVu Sans Mono',monospace;font-size:8.4pt;
 background:#F1F4F9;padding:.3mm 1mm;border-radius:2px}
pre{background:#F7F9FC;border:.5px solid #DCE5F0;border-left:2.5px solid __BLUE__;
 padding:3mm 3.5mm;margin:3mm 0 5mm;overflow:hidden;break-inside:avoid}
pre code{background:none;padding:0;font-size:7.7pt;line-height:1.5;white-space:pre-wrap;word-break:break-all}
blockquote{margin:3mm 0 4mm;padding:2.5mm 4mm;background:#F6F9FD;border-left:3px solid #A6B8D1;
 color:#2B3B4E;break-inside:avoid}
blockquote p:last-child{margin-bottom:0}
hr{border:0;border-top:.5px solid #DCE5F0;margin:6mm 0}
a{color:__BLUE__;text-decoration:none;word-break:break-all}
img{max-width:100%}
"""

HEADER = (
    '<div style="font-size:7pt;color:#9AA8B8;width:100%;padding:0 16mm;font-family:sans-serif;'
    'display:flex;justify-content:space-between;"><span>{doc}</span><span>{org}</span></div>'
)
FOOTER = (
    '<div style="font-size:7.5pt;color:#9AA8B8;width:100%;padding:0 16mm;font-family:sans-serif;'
    'text-align:center;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'
)


def _fonts():
    """검사할 글꼴. 🔴 **이름의 정본은 위 `CSS` 다** — 여기 또 적지 않는다 (D-99)."""
    return {
        "본문": fontcheck.declared(CSS, "body"),
        "코드": fontcheck.declared(CSS, "code"),
    }


def render(src_html, out_pdf, doc_title, org):
    sync_playwright = _need("playwright.sync_api").sync_playwright

    url = "file://" + str(pathlib.Path(src_html).resolve())
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        # 🔴 렌더 전에 잰다 — 대체돼도 PDF 는 **오류 없이 나온다.** 그것이 09-13 의 사고였다.
        #    ⬜ 이모지 글꼴(`Noto Color Emoji`)은 안 본다 — 폭 대조가 안 통한다 (D-188).
        fontcheck.require(pg, _fonts(), source="scripts/build_pdf.py · CSS")
        pg.goto(url, wait_until="networkidle")
        pg.pdf(
            path=out_pdf,
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template=HEADER.format(doc=doc_title, org=org),
            footer_template=FOOTER,
            margin={"top": "18mm", "bottom": "16mm", "left": "16mm", "right": "16mm"},
        )
        b.close()


DECO = "★🚨✅❌⚠️♦●·—–-()[]「」『』:：,.'\"／/"


def norm(t):
    return "".join(c for c in re.sub(r"\s+", "", t) if c not in DECO)


def inject_page_numbers(html, pdf_path):
    """1차 렌더 결과에서 각 목차 항목의 실제 쪽수를 찾아 주입한다."""
    pdfplumber = _need("pdfplumber")

    with pdfplumber.open(pdf_path) as pdf:
        pages = [norm(p.extract_text() or "") for p in pdf.pages]
    body = next((i for i in range(1, len(pages)) if "BODYSTARTMARK" in pages[i]), 1)
    items = re.findall(
        r'<div class="toc-([23])"><a href="#s?(\d+)"><span class="t">(.*?)</span>', html
    )
    found, cur, prev = {}, body, 0
    for _, idx, txt in items:
        key = norm(re.sub(r"<[^>]+>", "", txt))
        hit = next((i + 1 for i in range(cur, len(pages)) if key and key in pages[i]), None)
        if hit is None:
            hit = next((i + 1 for i in range(body, len(pages)) if key and key in pages[i]), None)
        if hit:
            cur = max(body, hit - 1)
            if hit < prev:
                hit = prev
            prev = hit
        found[idx] = hit or ""
    out = re.sub(r"@@PN:s?(\d+)@@", lambda m: str(found.get(m.group(1), "")), html)
    return (
        out.replace('<div style="font-size:1pt;color:#fff">BODYSTARTMARK</div>', ""),
        sum(1 for v in found.values() if not v),
        len(pages),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--logo", default="assets/brand/png/lockup-horizontal-reverse.png")
    ap.add_argument("--title", default="다중 에이전트 기반<br>광고 문구 준법 검수·생성 플랫폼")
    ap.add_argument("--subtitle", default="SKN Final Project 기획문서 — CopyLane v3.8")
    ap.add_argument("--doc-title", default="CopyLane 기획문서 v3.8")
    ap.add_argument("--org", default="SKN Final Project")
    ap.add_argument("--footer", default="팀 공유용")
    ap.add_argument("--meta", default=None, help="표지 메타 HTML — 생략하면 기본 크레딧")
    a = ap.parse_args()

    # 🚨 발행물 파일명에는 버전을 붙인다 — 원본은 계속 고쳐지므로 경로가 고정돼야 하고,
    #    PDF 는 그 시점에서 얼어붙은 것이라 이름이 바뀔 일이 없다.
    #    「PDF 발행이 버전을 고정하는 사건」이라는 개정 규칙이 여기에 산다.
    src_text = pathlib.Path(a.src).read_text(encoding="utf-8")
    out = a.out or "dist/" + versioned_stem(pathlib.Path(a.src).stem, src_text) + ".pdf"
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    meta = a.meta or (
        "팀장 &nbsp;<b>오한빈</b><br>"
        "팀원 &nbsp;<b>박수진 · 권소라 · 소성민 · 이서은</b><br>"
        "작성자 &nbsp;<b>오한빈</b> (팀장)<br>"
        "도메인 제안 &nbsp;<b>권소라</b>"
    )

    html = build_html(a.src, a.logo, a.title, a.subtitle, meta, a.footer)
    tmp = pathlib.Path(out).with_suffix(".pass1.html")
    tmp.write_text(html, encoding="utf-8")
    p1 = str(pathlib.Path(out).with_suffix(".pass1.pdf"))
    render(str(tmp), p1, a.doc_title, a.org)

    html2, miss, npages = inject_page_numbers(html, p1)
    tmp2 = pathlib.Path(out).with_suffix(".pass2.html")
    tmp2.write_text(html2, encoding="utf-8")
    render(str(tmp2), out, a.doc_title, a.org)

    for f in (tmp, tmp2, pathlib.Path(p1)):
        f.unlink(missing_ok=True)
    print(f"O {out}  ({npages}쪽, 목차 미매칭 {miss}건)")


if __name__ == "__main__":
    main()
