#!/usr/bin/env python3
"""law_annex_probe.py — [별표]가 「참조」인가 「내용」인가 (S2-04 경로 판정).

🚨 스모크 테스트의 `"별표" in body` 는 **문자열 포함 검사**라,
   조문에 *"별표 1에 따른다"* 라는 **참조**만 있어도 통과한다.
   4층 위험도 전체가 여기 걸려 있으므로 한 번 더 본다.

  uv run python scripts/law_annex_probe.py

표준 라이브러리만 쓴다 — uv 환경이 서기 전에도 돌아야 한다.
"""

import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.law.go.kr/DRF/lawService.do"
UA = {"User-Agent": "CopyLane-probe/1.0 (SKN final project)"}

# 화장품법 시행규칙 — 스모크에서 확인한 ID
TARGET_ID = "008741"
TARGET_NAME = "화장품법 시행규칙"


def read_oc():
    for name in ("LAW_OC_KEY", "LAW_OC"):
        v = (os.environ.get(name) or "").strip()
        if v:
            return v
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8-sig") as f:
            for line in f:
                if line.strip().startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() in ("LAW_OC_KEY", "LAW_OC"):
                    return v.split("#")[0].strip()
    return ""


def main():
    oc = read_oc()
    if not oc:
        sys.exit("LAW_OC_KEY 가 비어 있습니다 — .env 를 확인하십시오.")

    url = f"{BASE}?{urllib.parse.urlencode({'OC': oc, 'target': 'law', 'ID': TARGET_ID, 'type': 'XML'})}"
    body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
    text = body.decode("utf-8", "replace")

    print(f"{TARGET_NAME} (ID={TARGET_ID})  응답 {len(body):,} bytes")
    print("=" * 72)

    total = text.count("별표")
    print(f"[1] '별표' 등장 {total}회\n")

    # ── 참조 패턴: "별표 1에 따른다" / "[별표 3]" 같은 것
    refs = re.findall(r"별표\s*\d+[^<]{0,20}", text)
    print(f"[2] 참조로 보이는 것 {len(refs)}건 (앞 8개)")
    for r in refs[:8]:
        print(f"    · {r.strip()[:60]}")
    print()

    # ── 내용 신호: 별표 제목 노드 · 표 구조 · 별표 서식 링크
    signals = {
        "별표단위 노드(<별표...>)": len(re.findall(r"<별표[^>]*>", text)),
        "별표제목/별표명 필드": len(re.findall(r"별표(제목|명|번호|단위)", text)),
        "별표서식 링크(licbyl)": text.count("licbyl") + text.count("flDownload"),
        "표 마크업(<table|<TR|<TD)": len(re.findall(r"<(table|TR|TD)\b", text, re.I)),
    }
    print("[3] 「내용」이 실려 왔다는 신호")
    for k, v in signals.items():
        print(f"    {'✅' if v else '❌'} {k:28} {v}")
    print()

    # ── [4] 🚨 노드를 실제로 열어본다 — 신호만으로 닫지 않는다
    print("[4] 별표 노드 실물 — 제목과 내용 앞부분")
    print("-" * 72)
    # 🚨 `<별표[^>]*>` 는 <별표번호> 같은 **짧은 태그에 먼저 매칭**된다.
    #    그래서 빈 블록을 잡고 「내용 없음」으로 오판했다 (2026-08-31 · D-98).
    #    내용은 <별표내용> 태그에 CDATA 로 실려 온다. 그것만 본다.
    nodes = re.findall(r"<별표내용>(.*?)</별표내용>", text, re.S)
    titles = re.findall(
        r"<별표(?:제목|명)[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</별표(?:제목|명)[^>]*>",
        text,
        re.S,
    )
    print(f"    별표 블록 {len(nodes)}개 · 제목 {len(titles)}개")
    for t in titles[:10]:
        print(f"      · {t.strip()[:70]}")

    # 행정처분 기준을 우선 찾는다 — 4층 위험도가 쓰는 것
    pick = next((n for n in nodes if "행정처분" in n), nodes[0] if nodes else "")
    # 🚨 태그를 `<[^>]+>` 로 지우면 안 된다 — CDATA 안에 `>` 가 없으면
    #    `[^>]+` 가 블록을 넘어 계속 먹어치워 **내용이 통째로 사라진다.**
    #    (2026-08-31 · probe 가 두 번째로 낸 오판. 측정기를 먼저 의심한다 — D-97)
    #    CDATA 를 먼저 뽑고, 줄바꿈은 보존한다. 표는 고정폭이라 줄이 곧 행이다.
    inner = "".join(re.findall(r"<!\[CDATA\[(.*?)\]\]>", pick, re.S))
    print(f"\n    [샘플 블록] 텍스트 길이 {len(inner):,}자")
    for line in [ln for ln in inner.splitlines() if ln.strip()][:12]:
        print("      " + line.rstrip()[:104])
    print()

    # ── [5] 🚨 첨부 형식이 비용을 가른다 — HWP 인가 PDF 인가
    print("[5] 별표 첨부 링크 실물 — 형식이 파싱 비용을 가른다")
    print("-" * 72)
    raw_block = pick if pick else ""
    if raw_block:
        # 행정처분 기준 블록의 원본 XML 을 그대로 보여준다 (필드명을 상상하지 않기 위해)
        m = re.search(r"<별표[^>]*>.{0,1200}?행정처분.{0,1200}?</별표[^>]*>", text, re.S)
        sample = m.group(0) if m else raw_block[:1200]
        print("    [원본 XML 발췌]")
        for line in sample[:1400].splitlines()[:24]:
            if line.strip():
                print("      " + line.strip()[:110])
    print()

    exts = {}
    for ext in ("hwp", "hwpx", "pdf", "docx", "jpg", "png", "xlsx"):
        n = len(re.findall(rf"\.{ext}\b", text, re.I)) + len(
            re.findall(rf"fileType=\w*{ext}", text, re.I)
        )
        if n:
            exts[ext] = n
    print(f"    파일 확장자 흔적: {exts or '(응답에 확장자 문자열 없음 — 링크 파라미터로만 제공)'}")
    # 🚨 다운로드 경로는 licbyl 이 아니라 flDownload 다 (2026-08-31 실측)
    print("    [별표단위 블록 전문 — 수집기가 쓸 필드명]")
    m2 = re.search(
        r"<별표단위[^>]*>(?:(?!</별표단위>).)*?행정처분(?:(?!</별표단위>).)*?</별표단위>",
        text,
        re.S,
    )
    if m2:
        for line in m2.group(0).splitlines():
            if line.strip():
                print("      " + line.strip()[:150])
    else:
        print("      (행정처분 블록을 못 찾음)")
    print()

    # 표는 고정폭 ASCII 괘선으로 그려져 온다 — 이것이 파싱 대상이다
    rule_chars = sum(inner.count(c) for c in "┌┬┐├┼┤└┴┘─│")
    print(f"    괘선 문자 {rule_chars:,}개 — {'표 구조 있음 ✅' if rule_chars > 50 else '표 아님'}")
    print()

    body_has_table_text = len(inner) > 300
    has_content = any(v for k, v in signals.items() if k != "별표서식 링크(licbyl)")
    print("=" * 72)
    if has_content and body_has_table_text:
        print("판정: ✅ 별표 노드에 실제 텍스트가 실려 있다.")
        print("      → S2-04 를 API 경로로 진행한다.")
        print("      🚨 다만 [4] 샘플이 「표의 행/열」로 읽히는지 눈으로 확인하라 —")
        print("        표가 줄글로 뭉개져 오면 위반 횟수별 처분 일수를 파싱할 수 없다.")
    elif has_content:
        print("판정: ⚠️ 별표 노드는 오지만 **내용이 비어 있다**.")
        print("      → 표 데이터는 별표서식 첨부(licbyl)로만 제공된다는 뜻이다.")
        print("      → 첨부 다운로드 + 파싱 수집기가 하나 더 필요하다. S2-04 재산정.")
    elif signals["별표서식 링크(licbyl)"]:
        print("판정: ⚠️ 본문에는 참조만 있고, 별표는 **별도 API/링크**로 제공된다.")
        print("      → 별표서식 API(target=licbyl 계열) 로 수집기를 하나 더 만든다.")
    else:
        print("판정: ❌ 참조만 있고 내용이 없다.")
        print("      → 법령 HTML 페이지 파싱으로 우회한다. 🚨 수집기가 하나 늘어난다.")
    print("\n🚨 이 판정을 설계결정기록에 D 번호로 남길 것 (S2-04 경로가 여기서 갈린다).")


if __name__ == "__main__":
    main()
