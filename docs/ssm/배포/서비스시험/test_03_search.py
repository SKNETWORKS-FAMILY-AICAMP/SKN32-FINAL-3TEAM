"""3. 조문 검색 API (`POST /search`) — 근거 검색의 두 갈래(벡터 · 어휘)가 살아 있는가."""

from __future__ import annotations

import pytest
from conftest import Client, assert_no_server_error, note

case = pytest.mark.case
AREA = "검색 API"


@case(id="SRC-01", area=AREA, title="조문 검색 — 질병 효능 표방", expect="200 · 결과 1건 이상 · 벡터 갈래 ok")
def test_search_basic(http: Client) -> None:
    r = http.post("/search", json={"q": "질병의 예방 및 치료에 효능이 있는 것으로 표방하는 광고"})
    assert r.status_code == 200, f"상태 {r.status_code}"
    body = r.json()
    hits = body.get("hits", [])
    assert hits, "검색 결과가 0건이다"
    assert body.get("vector") == "ok", f"벡터 갈래가 안 돌았다: vector={body.get('vector')!r}"
    for h in hits:
        assert h.get("chunk_id"), "결과에 chunk_id 가 없다"
    note(f"결과 {len(hits)}건 · lexical={body.get('lexical')} · counts={body.get('counts')}")


@case(id="SRC-02", area=AREA, title="조문 검색 — 결과 수 지정(limit=3)", expect="200 · 3건 이하")
def test_search_limit(http: Client) -> None:
    r = http.post("/search", json={"q": "체중 감량 다이어트 효과", "limit": 3})
    assert r.status_code == 200, f"상태 {r.status_code}"
    assert len(r.json().get("hits", [])) <= 3, "limit 보다 많이 돌려줬다"


@pytest.mark.parametrize(
    ("body", "why"),
    [
        pytest.param({"q": ""}, "빈 검색어", id="SRC-03", marks=case(id="SRC-03", area=AREA, title="빈 검색어", expect="422")),
        pytest.param({"q": "효능", "limit": 0}, "limit 0", id="SRC-04", marks=case(id="SRC-04", area=AREA, title="limit 0", expect="422")),
        pytest.param({"q": "효능", "limit": 51}, "limit 51", id="SRC-05", marks=case(id="SRC-05", area=AREA, title="limit 51 (상한 50)", expect="422")),
        pytest.param({"q": "효능", "law": ["없는법"]}, "모르는 법", id="SRC-06", marks=case(id="SRC-06", area=AREA, title="모르는 법 이름으로 거르기", expect="422 (조용히 0건이 아니라 거부)")),
    ],
)
def test_search_rejects(http: Client, body: dict, why: str) -> None:
    r = http.post("/search", json=body)
    assert r.status_code == 422, f"{why} → 상태 {r.status_code}"
    assert_no_server_error(r)


@case(id="SRC-07", area=AREA, title="GET 으로 검색 (문구를 주소에 싣기)", expect="405 (POST 만 받는다)")
def test_search_get(http: Client) -> None:
    r = http.get("/search?q=효능")
    assert r.status_code == 405, f"상태 {r.status_code}"
