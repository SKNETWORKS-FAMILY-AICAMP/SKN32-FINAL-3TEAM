#!/usr/bin/env python3
"""
법제처 OPEN API 스모크 테스트  —  S0-01 승인 직후 5분 안에 돌리는 것

목적 세 가지
  1. OC 값이 실제로 통하는지 (승인 메일만 믿지 않는다)
  2. CopyLane이 필요로 하는 법령·고시 6+2종이 이 API로 실제로 잡히는지
  3. 🚨 [별표] 조회가 되는지  ← 4층 위험도 전체가 여기에 달려 있다

사용법
    export LAW_OC="발급받은ID"
    python law_api_smoke.py
"""

import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def _read_oc() -> str:
    """🚨 .env 의 LAW_OC_KEY 를 읽는다.

    이전 판은 `LAW_OC` 를 봤는데 `.env` 에는 `LAW_OC_KEY` 로 적혀 있어
    **키를 채워도 못 찾았다** (2026-08-31 수정).
    이 스크립트는 uv 환경이 서기 전에도 돌아야 하므로 표준 라이브러리로 직접 읽는다.
    """
    for name in ("LAW_OC_KEY", "LAW_OC"):
        v = (os.environ.get(name) or "").strip()
        if v:
            return v
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() in ("LAW_OC_KEY", "LAW_OC"):
                    return v.split("#")[0].strip()
    return ""


OC = _read_oc()
BASE_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
BASE_SERVICE = "https://www.law.go.kr/DRF/lawService.do"
UA = {"User-Agent": "CopyLane-smoke/1.0 (SKN final project)"}
SLEEP = 0.6  # 공공 API 예의. 수집기 공통 규약 5번

# CopyLane이 1W에 반드시 잡아야 하는 것 (수집 리스트 S1-01 · S1-02)
TARGETS = [
    ("law", "표시·광고의 공정화에 관한 법률", "S1-01"),
    ("law", "식품 등의 표시·광고에 관한 법률", "S1-01"),
    ("law", "화장품법", "S1-01"),
    ("admrul", "식품등의 부당한 표시 또는 광고의 내용 기준", "S1-02"),
    ("admrul", "부당한 표시·광고로 보지 아니하는 식품등의 기능성 표시·광고에 관한 규정", "S1-02"),
    ("admrul", "건강기능식품의 기준 및 규격", "S1-04 원출처"),
]


def call(base, **params):
    params["OC"] = OC
    params.setdefault("type", "XML")
    url = f"{base}?{urllib.parse.urlencode(params, encoding='utf-8')}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace"), url


def parse(body):
    """XML이면 root 반환, 아니면 None (인증 실패 시 HTML이 온다)."""
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        return None


def text(node, *names):
    for n in names:
        el = node.find(n)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def main():
    if not OC:
        sys.exit("LAW_OC_KEY 가 비어 있습니다 — .env 에 값을 넣으십시오 (S0-01).")

    print(f"OC = {OC!r}\n" + "=" * 72)

    # ── 0. 인증 확인 ────────────────────────────────────────────────
    body, url = call(BASE_SEARCH, target="law", query="화장품법", display="1")
    root = parse(body)
    if root is None:
        print("🚨 XML이 아닙니다 — OC가 아직 승인되지 않았거나 값이 틀렸습니다.")
        print("   응답 앞부분:", body[:300].replace("\n", " "))
        print("\n   확인할 것")
        print("   · 마이페이지 > OPEN API 신청현황 에서 상태가 '승인'인지")
        print("   · OC에 이메일 @ 앞부분만 넣었는지 (전체 주소가 아니라)")
        sys.exit(1)
    print("✅ 인증 OK — XML 응답 정상\n")

    # ── 1. 필요한 법령·고시가 실제로 잡히는가 ────────────────────────
    print("[1] CopyLane 1W 수집 대상 조회")
    print("-" * 72)
    found = {}
    for tgt, name, sid in TARGETS:
        time.sleep(SLEEP)
        body, _ = call(BASE_SEARCH, target=tgt, query=name, display="3")
        root = parse(body)
        hits = [] if root is None else root.findall(".//law") + root.findall(".//admrul")
        if hits:
            first = hits[0]
            lid = text(first, "법령ID", "행정규칙ID", "법령일련번호", "행정규칙일련번호")
            nm = text(first, "법령명한글", "행정규칙명")
            eff = text(first, "시행일자", "발령일자")
            found[name] = (tgt, lid, eff)
            print(f"  ✅ [{sid}] {nm or name}")
            print(f"        target={tgt}  ID={lid}  시행일={eff}")
        else:
            print(f"  ❌ [{sid}] {name}  — 검색어를 바꿔 재시도 필요")
    print()

    # ── 2. 🚨 [별표] 조회 — 4층 전체가 여기 달려 있다 ────────────────
    print("[2] 🚨 [별표] 조회 가능 여부  (4층 위험도의 전제)")
    print("-" * 72)
    cosmetic = found.get("화장품법")
    if not cosmetic:
        print("  ⏭  화장품법을 못 찾아 건너뜁니다.")
    else:
        # 시행규칙 본문을 받아 별표 노드가 실려 오는지 본다
        time.sleep(SLEEP)
        body, _ = call(BASE_SEARCH, target="law", query="화장품법 시행규칙", display="1")
        root = parse(body)
        node = None if root is None else root.find(".//law")
        if node is None:
            print("  ❌ 화장품법 시행규칙을 찾지 못했습니다.")
        else:
            lid = text(node, "법령ID")
            time.sleep(SLEEP)
            body, url = call(BASE_SERVICE, target="law", ID=lid)
            has_annex = "별표" in body
            print(f"  시행규칙 ID={lid}")
            print(f"  본문 응답에 '별표' 문자열 {'있음 ✅' if has_annex else '없음 ❌'}")
            print(f"  응답 크기 {len(body):,} bytes")
            if not has_annex:
                print("\n  🚨 별표가 본문에 실려 오지 않습니다.")
                print("     → 별도 별표 조회 API가 있는지 가이드에서 확인하십시오:")
                print("       open.law.go.kr > OPEN API > 활용가이드 > '별표서식'")
                print("     → 그래도 안 되면 4층은 법령 HTML 페이지 파싱으로 우회합니다.")
                print("     ⚠️ 이 판정을 1W 안에 내려야 S2-04가 밀리지 않습니다.")

    # ── 3. 응답 필드 실물 확인 ──────────────────────────────────────
    print("\n[3] 응답 필드 실물  (스키마를 상상으로 짜지 않기 위해)")
    print("-" * 72)
    time.sleep(SLEEP)
    body, _ = call(
        BASE_SEARCH,
        target="admrul",
        query="식품등의 부당한 표시 또는 광고의 내용 기준",
        display="1",
    )
    root = parse(body)
    node = None if root is None else root.find(".//admrul")
    if node is None:
        print("  (샘플 없음)")
    else:
        for child in node:
            val = (child.text or "").strip()
            print(f"  {child.tag:<24} {val[:60]}")

    print("\n" + "=" * 72)
    print("다음 할 일")
    print("  · 위 target / ID / 시행일을 data_sources.yaml 의 law_acts 항목에 기록")
    print("  · [2]의 별표 판정 결과를 설계결정기록에 D 번호로 남길 것")
    print("  · collect/law_api.py 작성 — registry.require() 로 시작, manifest.jsonl append")


if __name__ == "__main__":
    main()
