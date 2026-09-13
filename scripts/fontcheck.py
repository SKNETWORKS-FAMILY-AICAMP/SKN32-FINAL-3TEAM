"""scripts/fontcheck.py — 뽑기 전에 **이 기기에 글꼴이 있는지** 본다 (2026-09-13 · D-220 · D-206).

🔴 **왜 있나 — 2026-09-13 에 같은 사고를 두 번 봤다.**
   ① **도면** — 기기(Windows)에서 `diagram` 을 돌렸더니 `Noto Sans CJK KR` 이 없어
      **맑은 고딕으로 대체**됐다. 13장이 −18% 로 줄고 범례가 상자를 뚫고 나왔는데
      **멈추는 코드가 없었다.**
   ② **PDF** — 같은 날 뽑은 114쪽에 박힌 글꼴을 재 봤더니 `MalgunGothic`·`GulimChe` 였다.
      기존 제출본은 `NotoSansCJKkr`. **선언한 글꼴이 하나도 안 들어갔는데 조용히 나왔다.**

★ 둘이 같은 모양이라 **한 벌로 올린다** (D-99). `build_diagram.py` 와 `build_pdf.py` 가
  같은 playwright chromium 을 쓰므로 검사도 하나면 된다.
🚨 **기기가 둘이면 이 검사가 유일한 방벽이다** — 같은 명령이 기기마다 다른 산출물을 내는데
   git 은 그것을 「수정됨」으로만 보여 준다. 어느 쪽이 옳은지는 안 알려 준다.

⛔ `document.fonts.check()` 를 쓰지 않는다 — **없는 글꼴에도 `True` 를 낸다**(2026-09-13 실측).
   「존재하지않는폰트XYZ」도 `True` 였다. 그것이 D-170 이 말한 **통과만 하는 게이트**다.

★ 대신 **폭을 견준다** — 글꼴이 없으면 대체되고, 대체되면 generic 과 폭이 같아진다.
   🚨 generic 하나로는 부족하다: 원하는 글꼴이 그 기기의 **monospace 한글 대체본**이면
      깔려 있는데도 폭이 같다. 그래서 **셋(monospace·serif·sans-serif)을 다 보고
      하나라도 다르면 있다**로 친다.

★ **묻는 것은 「깔려 있나」가 아니라 「이 기기에서 한글을 그리나」다.** [실측 2026-09-13]
     Noto Sans CJK KR       → 있다   폭 257.6 vs generic 280.0
     Noto Sans Mono CJK KR  → 있다   폭 257.6 vs generic 280.0
     존재하지않는폰트XYZ    → 없다   폭 280.0 = 280.0   ← 음성 확인 (D-170)
     DejaVu Sans            → 없다   폭 280.0 = 280.0   ← **깔려 있는데 「없다」**
  🚨 마지막 줄이 오탐이 아니다 — DejaVu Sans 에는 **한글 글리프가 없어서** 어차피 대체된다.
     우리가 알고 싶은 것이 정확히 그것이다.

⬜ **여기서 못 보는 것** (D-188) —
   ① 원하는 글꼴이 **세 generic 전부의 한글 대체본**인 기기에서는 「없다」로 잡는다.
      그런 기기에서는 있으나 없으나 렌더 결과가 같으므로 **막아도 그림이 틀리지는 않는다** —
      다만 사람이 한 번 막힌다.
   ② **글꼴 판(version)은 안 본다.** 같은 이름의 다른 판이면 폭이 미세하게 다를 수 있다.
   ③ **이모지 글꼴은 안 본다** — 폭 대조가 안 통한다. 없으면 네모로 나오고, 그건 눈에 띈다.
   ④ **굵기·기울임은 안 본다.** Regular 만 잰다.
"""

from __future__ import annotations

import re

#: 폭 대조용 글자. 🚨 **한글이라야 한다** — 라틴 글자는 대체 글꼴도 폭이 비슷하다.
PROBE = "가나다라마바사"

#: 🔴 셋을 다 본다. 하나만 보면 그 generic 의 대체본인 글꼴을 「없다」로 오판한다.
GENERICS = ("monospace", "serif", "sans-serif")

#: 폭이 이만큼도 안 다르면 **같은 글꼴로 그려진 것**이다.
_EPS = 0.5

_MEASURE = """(args) => {
  const c = document.createElement('canvas').getContext('2d');
  const out = [];
  for (const g of args.g) {
    c.font = '40px "' + args.f + '", ' + g;
    const a = c.measureText(args.s).width;
    c.font = '40px ' + g;
    out.push([a, c.measureText(args.s).width]);
  }
  return out;
}"""


def declared(css: str, selector: str) -> str:
    """`<selector>{ … font-family:X, … }` 의 **첫 글꼴 이름**.

    🔴 **이름을 코드에 또 적지 않는다** (D-99) — 정본은 CSS 다. 여기 이름을 적으면
       CSS 를 고쳐도 검사가 옛 이름을 본다.
    ⛔ 앞에 낱말이 붙은 규칙(`pre code{…`)은 안 잡는다 — `code{` 와 다른 규칙이다.
    """
    m = re.search(r"(?:^|[\n;}])\s*" + re.escape(selector) + r"\s*\{(.*?)\}", css, re.S)
    if not m:
        raise SystemExit(f"🔴 CSS 에서 `{selector}{{…}}` 규칙을 못 찾았다 — 검사할 글꼴이 없다")
    f = re.search(r"font-family:\s*['\"]?([^'\",;}]+)", m.group(1))
    if not f:
        raise SystemExit(f"🔴 `{selector}{{…}}` 에 font-family 가 없다")
    return f.group(1).strip()


def present(page, want: str) -> tuple[bool, list[tuple[float, float]]]:
    """이 기기에 `want` 가 있는가. 되돌리는 둘째 값은 **실측 폭 쌍**이다 (근거를 같이 낸다)."""
    if want.lower() in GENERICS:
        # generic 을 견줄 대상이 없다 — 늘 「없다」가 되므로 검사에서 뺀다.
        return True, []
    page.set_content("<p>가</p>")
    pairs = [
        (float(a), float(b))
        for a, b in page.evaluate(_MEASURE, {"f": want, "s": PROBE, "g": list(GENERICS)})
    ]
    return any(abs(a - b) >= _EPS for a, b in pairs), pairs


def require(page, wants: dict[str, str], *, source: str) -> None:
    """🔴 하나라도 없으면 **멈춘다.** `wants` 는 `{쓰임: 글꼴이름}`.

    ⛔ 억지로 뽑지 않는다 — 대체된 산출물은 *「뭔가 달라졌다」*는 신호만 남기고
       **무엇이 왜 달라졌는지는 안 남긴다.** 그 상태로 다른 기기의 것과 섞이면
       발표에서 서체가 튄다 (2026-09-13 실측 — 제출본 Noto vs 새 PDF 맑은고딕).
    🚨 D-206 이 적어 둔 자리다 — *「리눅스에서 돈 것이 Windows 에서 통과한다는 뜻이 아니다」*.
    """
    missing: list[tuple[str, str, list[tuple[float, float]]]] = []
    for use, want in wants.items():
        ok, pairs = present(page, want)
        if not ok:
            missing.append((use, want, pairs))
    if not missing:
        return

    lines = [
        f"🔴 이 기기에 없는 글꼴이 있다 — 대체 글꼴로 뽑히면 **판형이 달라진다.** ({source})",
        "",
    ]
    for use, want, pairs in missing:
        lines.append(f"   ✗ {use} — 「{want}」")
        for g, (a, b) in zip(GENERICS, pairs, strict=False):
            lines.append(f"       「{PROBE}」 폭 {a:.1f}px = {g} {b:.1f}px  (대체됐다는 뜻)")
    lines += [
        "",
        "✅ 고치는 법 — 둘 중 하나",
        "   ① 글꼴을 깐다.  ⚠️ **이름이 정확히 일치해야 한다** —",
        "      `Noto Sans KR`(Google Fonts 웹폰트)은 `Noto Sans CJK KR` 과 **다른 이름**이다.",
        "      Noto CJK 원본: https://github.com/notofonts/noto-cjk/releases",
        "   ② 이 기기에서 안 뽑고, 글꼴이 있는 기기에서 뽑은 것을 받는다.",
        "",
        "🚨 넘기는 플래그를 만들지 않는다 — 넘기는 길이 있으면 결국 늘 켜진다 (D-170).",
    ]
    raise SystemExit("\n".join(lines))
