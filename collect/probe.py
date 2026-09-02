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

import json
import re
import re as _re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from collect import http, registry

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/03_데이터"
# 🚨 누적 결과. **단일 소스 탐침이 전체 리포트를 덮어쓰던 것**을 막는다 (2026-09-02).
#    `probe mfds_hf_ingredient` 한 번에 32건 결과가 사라졌다 — 리포트가 그 실행의
#    rows 만으로 렌더링됐기 때문이다. 여기에 소스별로 쌓고 리포트는 전체에서 그린다.
#    🚨 build/ 다. data/ 가 아니다 — 탐침은 등급 디렉터리에 쓰지 않는다 (게이트 23).
CACHE = ROOT / "build" / "probe_results.json"

# 🚨 본문에서 이용조건을 말하는 자리. 검토 확인 항목 1·3·5 가 찾는 문구다.
# 🚨 data.go.kr 의 「API 유형」. LINK 면 실제 호출과 **신청처가 원 기관**이다 (2026-09-02).
#    이걸 못 보면 활용신청 버튼을 찾다가 시간을 버린다 — 15058359 가 그랬다.
PORTAL_HINTS = ("API 유형", "심의유형", "이용허락범위", "End Point", "엔드포인트", "요청주소")
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


def _portal_lines(text: str) -> list[str]:
    """포털 메타 — 「API 유형 : LINK」처럼 **신청·호출 경로를 가르는 한 줄**을 잡는다."""
    out: list[str] = []
    for hint in PORTAL_HINTS:
        i = text.find(hint)
        if i < 0:
            continue
        out.append(f"**{hint}** … {text[i : i + 70].strip()}")
    return out


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


# 🚨 규모를 말하는 자리. 「568건」·「166,339문장」처럼 **숫자 + 단위**로 나타난다.
SCALE_UNITS = "건|문장|문서|개|명|가구|세트|쌍|어절|이미지|행|레코드"
_SCALE = _re.compile(rf"[\d,]{{2,}}\s*(?:{SCALE_UNITS})")


def _scale_lines(text: str) -> list[str]:
    """접근 페이지에서 규모로 보이는 조각. 🚨 **판정이 아니라 길잡이**다.

    `caution` 이 「미확인」이라 적은 규모를 사람이 확인하러 갈 때, 어디를 볼지 좁혀 준다.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _SCALE.finditer(text):
        # 🚨 중복은 **맞은 값**으로 거른다. 문맥 조각으로 거르면 가까이 붙은 숫자들이
        #    서로를 삼킨다 — 「166,339문장 / 10,021문서」에서 뒤엣것이 사라졌다.
        val = m.group(0).replace(" ", "")
        if val in seen:
            continue
        seen.add(val)
        out.append(f"**{m.group(0)}** … {text[max(0, m.start() - 45) : m.end() + 25].strip()}")
    return out[:8]


# 🚨 오픈API 의 **요청주소**. 레지스트리에는 포털 소개 페이지만 있고 실제 엔드포인트가 없어서
#    수집기를 쓸 수 없었다 (2026-09-02). 포털 상세 화면이 이 문자열을 노출하면 주워 온다.
_ENDPOINT = _re.compile(
    r"https?://(?:apis\.)?data\.go\.kr/[\w./%-]+|http://apis\.data\.go\.kr/[\w./%-]+"
)


def _endpoints(text: str) -> list[str]:
    """요청주소 후보. 🚨 **추정하지 않는다** — 화면에 실제로 있는 문자열만 낸다."""
    out: list[str] = []
    for m in _ENDPOINT.finditer(text):
        u = m.group(0)
        if "/data/" in u and u.endswith((".do", "openapi.do", "fileData.do")):
            continue  # 포털 소개 페이지는 엔드포인트가 아니다
        if u not in out:
            out.append(u)
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
    row["endpoints"] = _endpoints(text)
    row["portal"] = _portal_lines(text)
    row["robots"] = _robots(url)
    row["result"] = "✅ 열림"

    # 🚨 **근거 페이지와 접근 페이지는 다른 질문에 답한다** (2026-09-02 2회전에서 드러났다).
    #    AI Hub 6종은 `evidenceUrl` 이 이용정책이라, 승인이 나서 탐침이 열렸는데도
    #    **데이터셋 상세를 한 번도 안 봤다** — `aihub_71694` 의 「규모 미확인」이 그대로 남았다.
    #    조건은 근거 페이지가, **규모·필드는 접근 페이지가** 말한다. 둘 다 본다.
    access_url = s.get("url")
    if access_url and access_url != url and str(access_url).startswith("http"):
        row["access_url"] = access_url
        try:
            atext = _text(http.fetch(access_url))
            row["access_bytes"] = len(atext)
            row["scale_hits"] = _scale_lines(atext)
            row["endpoints"] = _endpoints(atext)
        except http.FetchError as e:
            row["scale_hits"] = []
            row["access_error"] = str(e)
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
        if r.get("access_url"):
            L += [
                "",
                f"**접근 페이지** → <{r['access_url']}>"
                + (f"  🚨 {r['access_error']}" if r.get("access_error") else ""),
                "",
                "규모로 보이는 것 — ⚠️ **기계가 긁은 길잡이**입니다",
                "",
            ]
            L += [f"- {x}" for x in (r.get("scale_hits") or [])] or ["- ⬜ 숫자를 못 찾았습니다"]
        if r.get("portal"):
            L += ["", "🔧 **포털 메타** — API 유형이 `LINK` 면 신청·호출이 원 기관이다", ""]
            L += [f"- {x}" for x in r["portal"]]
        if r.get("endpoints"):
            L += ["", "🔧 **요청주소 후보** — `collect/endpoints.yaml` 에 적을 것", ""]
            L += [f"- `{u}`" for u in r["endpoints"]]
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

    # 🚨 이번 실행 결과를 누적본에 **덮어쓰지 않고 갱신**한다.
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict[str, Any]] = {}
    if CACHE.exists():
        try:
            merged = json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            merged = {}
    for r in rows:
        merged[r["id"]] = r
    CACHE.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

    out = OUT / f"실측_{date.today().isoformat()}.md"
    out.write_text(render(list(merged.values())), encoding="utf-8")
    print(f"탐침 {len(rows)}건 · 게이트가 막은 것 {len(skipped)}건 · 리포트 누적 {len(merged)}건")
    for s in skipped:
        print(f"  ⏸ {s}")
    print(f"→ {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
