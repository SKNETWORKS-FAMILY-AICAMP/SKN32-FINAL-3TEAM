"""app/api.py — FastAPI 골격 (D-42 · D-135 · D-56).

  uv run uvicorn app.api:app --reload

🚨 **FastAPI 단독이다.** Django 를 쓰지 않는다 (D-135 확정 · D-134 되돌림).
   화면은 Jinja2 + HTMX 로 같은 앱이 낸다 (D-56) — 별도 프론트를 두지 않는다.

🚨 **이 파일은 계약이지 구현이 아니다.** 판정 엔진(LangGraph)은 아직 없다.
   그래서 판정 라우트는 **`501 Not Implemented` 를 낸다** — 200 에 가짜 응답을 넣지 않는다.
   가짜 응답을 넣으면 프론트가 그 모양에 맞춰 붙고, 진짜가 오면 두 번 고친다.
   D-147 이 같은 말을 데이터 쪽에서 한다 — **오류 응답은 데이터가 아니다.**

🔴 **거버넌스가 API 에도 걸린다** — `/search` 는 `source_use.allowed` 가 `U2_rag` 인
   프래그먼트만 돌려준다. 화면 인용은 `U3_cite`. 게이트가 아니라 **질의**로 건다.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="CopyLane",
    description="광고 문구 준법 검수·생성 — 판정 근거를 조문으로 돌려준다",
    version="0.1.0",
)


def dsn() -> str:
    return os.environ.get("DATABASE_URL") or (
        "postgresql://copylane:copylane@localhost:5432/copylane"
    )


class Health(BaseModel):
    ok: bool
    db: str
    counts: dict[str, int] = Field(default_factory=dict)


class SearchHit(BaseModel):
    chunk_id: str
    law_id: str
    article: str
    doc_type: str
    category: list[str]
    text: str
    # 🚨 출처표시는 조립해서 낸다 — `attribution` 은 기관명·자료명뿐이고
    #    URL·게시일은 `source`·`document` 가 들고 있다 (D-132 · 결정요청 ③)
    attribution: str | None = None
    source_url: str | None = None


class JudgeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    category: str = Field("일반", pattern="^(일반|식품|건기식|화장품)$")


@app.get("/health", response_model=Health)
def health() -> Health:
    """DB 가 붙는지와 층별 행 수를 낸다. 팀원이 처음 여는 자리다."""
    try:
        import psycopg

        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            counts: dict[str, int] = {}
            for table in (
                "source",
                "fragment",
                "document",
                "chunk",
                "chunk_embedding",
                "dict_entry",
                "product_fact",
                "golden_sample",
            ):
                cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — 고정 목록이다
                counts[table] = cur.fetchone()[0]
        return Health(ok=True, db="up", counts=counts)
    except Exception as e:  # noqa: BLE001
        return Health(ok=False, db=f"down: {e}")


@app.get("/search", response_model=list[SearchHit])
def search(q: str, category: str = "일반", limit: int = 5) -> list[SearchHit]:
    """조문 검색 — 🚨 **아직 벡터 검색이 아니다.** 텍스트 부분일치다.

    `chunk_embedding` 이 채워지면 `embedding <=> %s::vector` 로 바꾼다.
    🔴 지금 상태를 감추지 않는다 — 「검색이 된다」와 「의미 검색이 된다」는 다르다.
    """
    import psycopg

    try:
        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.chunk_id, c.law_id, c.article, c.doc_type, c.category, c.text,
                       s.attribution, s.url
                FROM chunk c
                JOIN fragment f ON f.fragment_id = c.fragment_id
                JOIN source   s ON s.source_id   = f.source_id
                JOIN source_use u ON u.source_id = s.source_id AND u.use_code = 'U2_rag'
                WHERE u.allowed AND c.text ILIKE %s AND %s = ANY(c.category)
                LIMIT %s
                """,
                (f"%{q}%", category, limit),
            )
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"DB 에 못 붙었다 — {e}") from e
    return [
        SearchHit(
            chunk_id=r[0],
            law_id=r[1],
            article=r[2],
            doc_type=r[3],
            category=r[4],
            text=r[5],
            attribution=r[6],
            source_url=r[7],
        )
        for r in rows
    ]


@app.post("/judge")
def judge(req: JudgeRequest) -> dict[str, Any]:
    """판정 — 🚨 **아직 없다.** 가짜 200 을 내지 않는다.

    엔진(LangGraph · 판정기 A/B)이 붙는 자리다. 계약만 여기 적어 둔다:
      입력  text · category
      출력  violations[] · evidence[](조문 인용) · risk · rewrite 후보
    """
    raise HTTPException(
        501,
        "판정 엔진이 아직 없다. 계약만 정해져 있다 — "
        "violations[] · evidence[](조문) · risk · rewrite. "
        "가짜 응답을 내면 프론트가 그 모양에 맞춰 붙고 진짜가 오면 두 번 고친다.",
    )
