"""탐침 — 열어보고 세되 **저장하지 않는다** (D-109).

🚨 **이것은 수집기가 아니다.** `collect/store.py` 를 import 하지 않고, `data/` 아래에
   아무것도 쓰지 않으며, `mark_collected()` 를 부르지 않는다. **게이트 23 이 그것을 강제한다.**

왜 필요한가 — D-72 는 *"확인 후 2인 판정으로 승격한다"* 고 말한다. 그런데 확인 수단이
수집기뿐이면 **확인이 판정 뒤로 밀리고**, 그 판정은 확인 없이 내려진다. 자기모순이다.
레지스트리의 `caution` 7건이 *"1W 실측"* · *"직접 열어 확인할 것"* · *"셋을 대조해"* 라고
적고 있는데, 그 문장들이 요구하는 것이 정확히 이 경로다.

무엇을 내놓는가 — `docs/03_데이터/실측_<날짜>.md` 한 장. 그것이 **검토자가 서명할 근거**다.

    uv run python -m collect.probe            # 전체
    uv run python -m collect.probe kosis      # 하나만

🚨 **저장이 필요해지는 순간 이 파일이 아니라 수집기를 만든다.** 여기에 쓰기를 더하는 것은
   규약 1 이 경고한 「일단 받아두고 나중에 판정한다」는 경로를 만드는 일이다.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from collect import http, registry

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/03_데이터"

# 🚨 본문에서 이용조건을 말하는 자리. 검토 확인 항목 1·3·5 가 찾는 문구다.
LICENSE_HINTS = (
    "이용허락범위",
    "공공누리",
    "제1유형",
    "제2유형",
    "제3유형",
    "제4유형",
    "저작권",
    "출처표시",
    "상업적",
    "영리",
    "라이선스",
    "licence",
    "license",
    "CC BY",
)
SNIPPET = 90  # 문구 앞뒤로 보여줄 길이


def _text(raw: bytes) -> str:
    """HTML 을 사람이 읽는 문자열로. 🚨 파싱이 목적이 아니라 **문구 찾기**가 목적이다."""
    s = raw.decode("utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _license_lines(text: str) -> list[str]:
    out: list[str] = []
    for hint in LICENSE_HINTS:
        i = text.find(hint)
        if i < 0:
            continue
        frag = text[max(0, i - SNIPPET) : i + SNIPPET].strip()
        if not any(frag in o for o in out):
            out.append(f"**{hint}** … {frag}")
    return out[:6]


def _robots(url: str) -> str:
    """robots.txt 를 그대로 읽어 온다. 🚨 판단은 사람이 한다 — 요약해서 넘기지 않는다."""
    p = urlsplit(url)
    if not p.scheme.startswith("http"):
        return "— (외부 URL 이 아니다)"
    try:
        body = _text(http.fetch(f"{p.scheme}://{p.netloc}/robots.txt", timeout=15))
    except http.FetchError as e:
        return f"⬜ 못 읽음 — {e}"
    return body[:400] + ("…" if len(body) > 400 else "")


def probe_one(source_id: str) -> dict[str, Any]:
    """한 소스를 열어본다. 🚨 예외를 삼키지 않는다 — 실패도 실측 결과다."""
    s = registry.probe(source_id)
    row: dict[str, Any] = {
        "id": source_id,
        "grade": s.get("grade"),
        "value": s.get("value"),
        "status": s.get("status"),
        "url": s.get("evidence_url") or s.get("url"),
        "fallback": bool(s.get("evidence_is_access")),
        "caution": s.get("caution") or "",
    }
    url = row["url"]
    if not url or not str(url).startswith("http"):
        row["result"] = "⬜ 외부 URL 이 없다 (자체 산출물이거나 미기재)"
        return row
    try:
        raw = http.fetch(url)
    except http.FetchError as e:
        row["result"] = f"🚨 접근 실패 — {e}"
        return row
    text = _text(raw)
    row["bytes"] = len(raw)
    row["license"] = _license_lines(text)
    row["robots"] = _robots(url)
    row["result"] = "✅ 열림"
    return row


def render(rows: list[dict[str, Any]]) -> str:
    today = date.today().isoformat()
    ok = [r for r in rows if r.get("result", "").startswith("✅")]
    L = [
        f"# 소스 실측 — {today}",
        "",
        "> 🚨 **생성물입니다.** `uv run python -m collect.probe` 가 만듭니다.",
        "> **탐침은 수집이 아닙니다** (D-109) — 아무것도 저장하지 않았고 "
        "`collected_at` 도 찍지 않았습니다. 이 문서는 **검토자가 서명할 근거**입니다.",
        "",
        f"| 대상 | {len(rows)}건 · 열림 {len(ok)} · 실패 {len(rows) - len(ok)} |",
        "|---|---|",
        "| 제외 | G1(배제) · `manual`(약관) · `GATED`(승인 선행) · robots 미확인 크롤링형 |",
        "",
        "> ⚠️ **여기 실린 문구는 기계가 긁은 것입니다.** 판정 근거가 아니라 "
        "**검토자가 원문을 열 때의 길잡이**입니다 — 서명은 원문을 보고 하십시오.",
        "",
        "---",
        "",
    ]
    for r in rows:
        L += [
            f"## `{r['id']}` — {r['grade']} · 가치 {r['value']} · {r['result']}",
            "",
            f"- URL: <{r['url']}>" + ("  ⚠️ **접근 URL 로 대체됨**" if r["fallback"] else ""),
        ]
        if r.get("bytes"):
            L.append(f"- 응답: {r['bytes']:,} bytes")
        lic = r.get("license") or []
        L += ["", "**이용조건 문구**", ""]
        L += [f"- {x}" for x in lic] or [
            "- ⬜ **찾지 못했습니다.** 🚨 이 페이지는 근거가 아닐 수 있습니다"
        ]
        if r.get("robots"):
            L += [
                "",
                "<details><summary>robots.txt</summary>",
                "",
                f"```\n{r['robots']}\n```",
                "",
                "</details>",
            ]
        if r["caution"]:
            L += ["", f"> ⚠️ 활용 주의 — {r['caution'][:300]}"]
        L += ["", "---", ""]
    return "\n".join(L)


def main(argv: list[str]) -> int:
    from collect.registry import RegistryError, _load  # noqa: PLC0415

    ids = argv[1:] or [k for k, v in (_load().get("sources") or {}).items() if isinstance(v, dict)]
    rows, skipped = [], []
    for sid in ids:
        try:
            rows.append(probe_one(sid))
        except RegistryError as e:
            skipped.append(f"{sid}: {e}")
        except Exception as e:  # noqa: BLE001 — 실패도 결과다. 한 건이 전체를 죽이지 않는다
            rows.append(
                {
                    "id": sid,
                    "grade": "?",
                    "value": "?",
                    "url": "",
                    "fallback": False,
                    "caution": "",
                    "result": f"🚨 예외 — {type(e).__name__}: {e}",
                }
            )

    out = OUT / f"실측_{date.today().isoformat()}.md"
    out.write_text(render(rows), encoding="utf-8")
    print(f"탐침 {len(rows)}건 · 게이트가 막은 것 {len(skipped)}건")
    for s in skipped:
        print(f"  ⏸ {s}")
    print(f"→ {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
