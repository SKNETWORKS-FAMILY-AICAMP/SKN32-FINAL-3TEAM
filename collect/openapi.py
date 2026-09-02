"""오픈API 수집기 — 여러 포털 공용.

🚨 처음 이름은 `data_go_kr.py` 였으나 **틀린 이름이 됐다** — data.go.kr 의 API 유형이
   `LINK` 인 소스는 실제 호출이 **원 기관 포털**로 간다(식품안전나라). 이름이 거짓이 되면
   다음 사람이 그 이름을 믿고 판단한다. 오늘 갈아 둔다.

🚨 **첫 줄이 `registry.require()` 다** (수집기 공통 규약 1). 게이트를 우회하는 경로를 만들지 않는다.

여섯이 한 파일인 이유 — **키가 하나(`DATA_GO_KR_KEY`)이고 호출 규약이 같다.** 소스마다 파일을
만들면 규약 2·3·5·7 을 여섯 번 다시 쓰게 되고, 그중 하나가 빠지는 것이 실제로 일어난다.
다른 것은 **요청주소와 응답 모양뿐**이고 그것은 `collect/endpoints.yaml` 이 진다 (D-89).

    uv run python -m collect.openapi mfds_hf_ingredient --use U1
    uv run python -m collect.openapi mfds_hf_ingredient --use U1 --pages 1   # 첫 장만

🚨 첫 실행은 `--pages 1` 로 한다. 응답 모양을 눈으로 보고 나서 전량을 받는다 —
   5,000건을 받아 놓고 필드가 기대와 다른 것을 아는 것이 가장 비싸다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml

from collect import env, http, registry, store

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = Path(__file__).resolve().parent / "endpoints.yaml"
ROWS = 100  # 한 장에 받을 건수. 🚨 크게 잡지 않는다 — 실패 시 재시도 비용이 커진다


def spec_of(source_id: str) -> dict[str, Any]:
    """요청주소를 읽는다. 🚨 비어 있으면 **추정하지 않고 거부**한다."""
    table = yaml.safe_load(ENDPOINTS.read_text(encoding="utf-8")) or {}
    ep = table.get(source_id)
    if not ep or not ep.get("url"):
        portal = registry.spec(source_id).get("url", "(포털 URL 미기재)")
        raise registry.RegistryError(
            f"{source_id!r} 의 요청주소가 collect/endpoints.yaml 에 없다.\n"
            f"  🚨 추정하지 않는다 — 틀린 주소는 빈 칸보다 나쁘다.\n"
            f"  포털 상세기능에서 요청주소를 확인해 적는다: {portal}\n"
            f"  `python launcher.py probe {source_id}` 가 화면에서 후보를 주워 준다."
        )
    return ep


def fetch_page(ep: dict[str, Any], key: str, page: int) -> bytes:
    """🚨 포털마다 호출 규약이 다르다 — 같은 「오픈API」가 같은 모양을 뜻하지 않는다.

    query : data.go.kr      ?serviceKey=..&pageNo=..&numOfRows=..
    path  : 식품안전나라     /{keyId}/{serviceId}/{dataType}/{startIdx}/{endIdx}
    """
    fmt = ep.get("fmt") or "json"
    if (ep.get("style") or "query") == "path":
        sid = ep.get("service_id")
        if not sid:
            raise registry.RegistryError(
                "style: path 인데 service_id 가 없다. 🚨 하이픈까지 화면 그대로 적는다 (예: I-0040)"
            )
        start = (page - 1) * ROWS + 1  # 🚨 1-based 포함 구간이다
        return http.fetch(f"{ep['url']}/{key}/{sid}/{fmt}/{start}/{start + ROWS - 1}")

    params = {"serviceKey": key, "pageNo": page, "numOfRows": ROWS, **(ep.get("params") or {})}
    if fmt == "json":
        params.setdefault("type", "json")
    return http.fetch(f"{ep['url']}?{urlencode(params, safe='')}")


def total_of(payload: bytes) -> int | None:
    """전체 건수. 🚨 못 읽으면 None 을 내고 **추정하지 않는다** — 페이징은 빈 장에서 멈춘다."""
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    def walk(o: Any) -> int | None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in {"totalcount", "total_count", "totalcnt"}:
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        pass
                found = walk(v)
                if found is not None:
                    return found
        elif isinstance(o, list):
            for v in o:
                found = walk(v)
                if found is not None:
                    return found
        return None

    return walk(obj)


def collect(source_id: str, use: str, max_pages: int | None) -> int:
    registry.require(source_id, use=use)  # 🚨 규약 1 — 첫 줄
    ep = spec_of(source_id)
    env.load()
    # 🚨 포털마다 키가 다르다. LINK 유형은 원 기관에서 따로 발급받는다 (2026-09-02).
    key = env.get("FOODSAFETY_KEY" if (ep.get("style") or "query") == "path" else "DATA_GO_KR_KEY")

    page, saved, total = 1, 0, None
    while True:
        payload = fetch_page(ep, key, page)
        if total is None:
            total = total_of(payload)
            print(f"  전체 건수: {total if total is not None else '읽지 못함 — 빈 장까지 받는다'}")
        path = store.save_raw(
            source_id,
            source_id,
            f"page_{page:04d}.json",
            payload,
            url=ep["url"],
        )
        if path:
            saved += 1
        print(f"  page {page:>4} · {len(payload):>9,} bytes {'저장' if path else '동일 — 스킵'}")

        if max_pages and page >= max_pages:
            print(f"  ⏸ --pages {max_pages} 에서 멈춘다. 응답을 눈으로 보고 전량을 받는다")
            break
        if total is not None and page * ROWS >= total:
            break
        if total is None and len(payload) < 200:  # 🚨 빈 장으로 본다
            break
        page += 1

    if saved:
        registry.mark_collected(source_id)  # 규약 3 · 게이트 15
    print(f"\n{source_id} — {saved}장 저장 → data/raw/{source_id}/")
    if registry.is_g2(source_id):
        print("🚨 G2 다 — 사실 추출 후 원본을 지운다 (D-17 · store.drop_raw_for_g2)")
    return 0


def main(argv: list[str]) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(prog="collect.openapi")
    ap.add_argument("source_id")
    ap.add_argument("--use", required=True, choices=sorted(registry.VALID_USES))
    ap.add_argument("--pages", type=int, default=None, help="🚨 첫 실행은 1 로 한다")
    a = ap.parse_args(argv[1:])
    return collect(a.source_id, a.use, a.pages)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
