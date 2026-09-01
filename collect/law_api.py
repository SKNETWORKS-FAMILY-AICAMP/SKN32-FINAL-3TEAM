"""collect/law_api.py — 법제처 OPEN API 수집기 (S1-01 · S1-02 · D-92).

  uv run python -m collect.law_api --target law      # 법령 6종
  uv run python -m collect.law_api --target admrul   # 고시·행정규칙 2종
  uv run python -m collect.law_api --dry-run         # 저장하지 않고 무엇을 받을지만

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1). 게이트를 우회하는 경로를 만들지 않는다.
   원본은 data/raw/law/ 에 무손상 저장하고 덮어쓰지 않는다 (규약 2 · D-92).

산출: data/raw/law/{target}_{id}_{eff}.xml  + data/manifest.jsonl 1행
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import xml.etree.ElementTree as ET

from collect import env, http, registry, store

SOURCE_ID = "law_go_kr"
FAMILY = "law"

BASE_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
BASE_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

# 수집리스트 S1-01 · S1-02. 🚨 목록을 여기서 늘리지 않는다 —
#    새 소스는 레지스트리에 먼저 등재하고 그다음 여기에 온다 (D-15).
TARGETS: dict[str, list[tuple[str, str]]] = {
    "law": [
        ("표시·광고의 공정화에 관한 법률", "S1-01"),
        ("식품 등의 표시·광고에 관한 법률", "S1-01"),
        ("화장품법", "S1-01"),
        ("표시·광고의 공정화에 관한 법률 시행령", "S1-01"),
        ("식품 등의 표시·광고에 관한 법률 시행규칙", "S1-01"),
        ("화장품법 시행규칙", "S1-01"),
    ],
    "admrul": [
        ("식품등의 부당한 표시 또는 광고의 내용 기준", "S1-02"),
        ("부당한 표시·광고로 보지 아니하는 식품등의 기능성 표시·광고에 관한 규정", "S1-02"),
    ],
}

ID_FIELDS = ("법령ID", "행정규칙ID", "법령일련번호", "행정규칙일련번호")
NAME_FIELDS = ("법령명한글", "행정규칙명")
EFF_FIELDS = ("시행일자", "발령일자")


def _text(node: ET.Element, *names: str) -> str:
    for n in names:
        el = node.find(n)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def _call(base: str, oc: str, **params: str) -> bytes:
    params["OC"] = oc
    params.setdefault("type", "XML")
    url = f"{base}?{urllib.parse.urlencode(params, encoding='utf-8')}"
    return http.fetch(url)


def _parse(body: bytes) -> ET.Element | None:
    """XML 이면 root, 아니면 None. 🚨 인증 실패 시 HTML 이 온다."""
    try:
        return ET.fromstring(body.decode("utf-8", "replace"))
    except ET.ParseError:
        return None


def search(oc: str, target: str, query: str) -> tuple[str, str, str] | None:
    """검색해서 (ID, 이름, 시행일) 을 돌려준다. 못 찾으면 None."""
    root = _parse(_call(BASE_SEARCH, oc, target=target, query=query, display="3"))
    if root is None:
        raise SystemExit(
            "🚨 XML 이 아닌 응답이다 — OC 가 승인되지 않았거나 값이 틀렸다.\n"
            "   scripts/law_api_smoke.py 를 먼저 돌려 확인하라 (S0-01)."
        )
    hits = root.findall(".//law") + root.findall(".//admrul")
    if not hits:
        return None
    first = hits[0]
    return _text(first, *ID_FIELDS), _text(first, *NAME_FIELDS) or query, _text(first, *EFF_FIELDS)


def collect(target: str, *, dry_run: bool = False) -> int:
    """대상 하나를 수집한다. 돌려주는 값은 새로 저장한 건수."""
    # ── 규약 1 — 게이트가 첫 줄이다 ──────────────────────────
    registry.require(SOURCE_ID, use="U1")
    oc = env.get("LAW_OC_KEY")

    saved = 0
    for query, sid in TARGETS[target]:
        hit = search(oc, target, query)
        if hit is None:
            print(f"  ❌ [{sid}] {query} — 검색어를 바꿔 재시도 필요")
            continue

        law_id, name, eff = hit
        print(f"  ✅ [{sid}] {name}  ID={law_id}  시행일={eff or '미상'}")
        if dry_run:
            continue

        body = _call(BASE_SERVICE, oc, target=target, ID=law_id)
        if _parse(body) is None:
            print(f"     ⚠️  본문이 XML 이 아니다 — 건너뛴다 ({law_id})")
            continue

        # 🚨 파일명에 시행일을 넣는다. 개정되면 새 파일이 되고 원본은 남는다 (규약 2)
        filename = f"{target}_{law_id}_{eff or 'unknown'}.xml"
        path = store.save_raw(
            SOURCE_ID,
            FAMILY,
            filename,
            body,
            url=f"{BASE_SERVICE}?target={target}&ID={law_id}",
        )
        if path is None:
            print(f"     ⏭  동일본 스킵 (sha256 일치) — {filename}")
        else:
            print(f"     💾 {path.relative_to(store.ROOT)}  ({len(body):,} bytes)")
            saved += 1

    return saved


def main() -> int:
    ap = argparse.ArgumentParser(description="법제처 OPEN API 수집기 (S1-01 · S1-02)")
    ap.add_argument("--target", choices=sorted(TARGETS), default="law")
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않고 조회만")
    args = ap.parse_args()

    try:
        saved = collect(args.target, dry_run=args.dry_run)
    except (registry.RegistryError, env.MissingKey) as e:
        # 🚨 게이트와 키 부재는 「고치는 법」을 그대로 보여준다 (D-51)
        print(f"\n수집을 시작할 수 없다 —\n{e}\n", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\n(dry-run — 저장하지 않았다)")
        return 0

    print(f"\n새로 저장 {saved}건")
    if saved:
        registry.mark_collected(SOURCE_ID)
        print("collected_at 을 원장에 기록하고 data_sources.yaml 을 재생성했다.")
    print("🚨 이어서 반드시:  uv run pytest -m gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
