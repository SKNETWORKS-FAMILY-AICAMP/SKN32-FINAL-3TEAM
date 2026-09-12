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

import dataclasses
import os
import pathlib
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# 🚨 계약은 `app/contracts.py` 하나가 원본이다 (D-124). 여기서 다시 정의하지 않는다 —
#    두 곳에 있으면 화면이 보는 모양과 우리가 내는 모양이 조용히 갈린다.
from app import retrieve as rt
from app.contracts import (
    ComposeRequest,
    ComposeResponse,
    GenerateRequest,
    GenerateResponse,
    JudgeRequest,
    JudgeResponse,
)

# 🔴 **검색 로직은 이 파일에 없다** — `app/retrieve.py` 하나가 든다 (D-99 · D-51).
#    ⛔ `app/graph.py` 의 `retrieve` 노드가 **같은 검색**을 부를 자리다(🔜 W4~).
#       여기서 고치면 그때 두 벌이 된다. 이 파일은 **두 갈래를 불러 한 응답에 담는 껍데기**다.

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
    # 🔴 **DB 열이 NULL 을 허용한다** (`db/schema.sql` 의 chunk) — 모델도 그래야 한다.
    #    ⛔ 종전에는 전부 필수라 NULL 행이 하나만 걸려도 `ValidationError` → 500 이었다.
    #       별표 청크는 `article` 이 없을 수 있다.
    law_id: str | None = None
    article: str | None = None
    #: 🔴 2026-09-12 신설 — 항(「①」)과 호(「1.」). 종전에는 `paragraph` 에 둘이 뭉쳐 있고
    #:    응답에는 아예 없었다. 그래서 화면이 **어느 호가 걸렸는지 말할 수 없었다.**
    paragraph: str | None = None
    item: str | None = None
    #: 항 서수 (0008) — 원문에 「①」가 없는 호가 31% 다. 인용은 이쪽으로 조립된다.
    paragraph_no: int | None = None
    #: 자립 텍스트 — **임베딩이 본 것과 같은 값**이다. 화면은 이것을 접어서 보여 주고
    #: `text` 를 펼쳐 보여 준다. 🚨 `null` 은 미적재, 빈 문자열은 붙일 문맥 없음이다.
    context: str | None = None
    #: 「제8조제1항제1호」. 🚨 `null` 이면 **조립을 못 한 것**이지 근거가 없는 게 아니다 —
    #:    별표는 계층 표기가 달라 조립하지 않는다. 그때는 `article`·`paragraph` 를 쓴다.
    citation: str | None = None
    doc_type: str | None = None
    category: list[str] = Field(default_factory=list)
    text: str
    # 🚨 출처표시는 조립해서 낸다 — `attribution` 은 기관명·자료명뿐이고
    #    URL·게시일은 `source`·`document` 가 들고 있다 (D-132 · 결정요청 ③)
    attribution: str | None = None
    source_url: str | None = None
    #: 🔴 **어느 갈래로 찾아졌는가** — `fused`(합친 순위) · `vector` · `lexical` · `literal`.
    #:    🔄 2026-09-12 오후 — `/search` 는 이제 `fused` 를 낸다 (D-193). 종전 값 `text` 는
    #:    `literal` 로 이름이 바뀌었다.
    match: str
    #: 코사인 거리 (작을수록 가깝다). 🚨 어휘·기호 갈래는 `null` 이다 —
    #:    0.0 으로 채우면 「완전 일치」라는 뜻이 되어 없는 값이 가장 좋은 값이 된다.
    distance: float | None = None
    #: `ts_rank_cd` 원점수 (클수록 가깝다). 🚨 벡터 갈래는 `null`.
    lexical: float | None = None
    #: 🔴 **합친 뒤에도 어느 갈래가 몇 위로 올렸는지 보인다** (D-185).
    #:    ⛔ 이 둘이 없으면 한 갈래가 죽어도 결과가 그럴듯해서 **안 보인다.**
    #:    🚨 `null` 은 「그 갈래 후보 50개 안에 없었다」이고, 「50위」가 아니다 (D-188).
    rank_vector: int | None = None
    rank_lexical: int | None = None
    #: RRF 점수 (클수록 앞). 🚨 같은 질의 안에서만 뜻이 있다 — 질의끼리 비교하지 않는다.
    rrf: float | None = None


class SearchResult(BaseModel):
    """🔴 목록이 아니라 **봉투**다 — 「왜 못 했는지」를 담을 자리가 있어야 한다.

    ⛔ 벡터 검색이 안 될 때 조용히 텍스트 결과만 내면 「의미 검색을 했는데 0건」과
       「의미 검색을 못 했다」가 구별되지 않는다. 2026-09-12 에 `mark_collected` 가
       같은 모양으로 틀렸다 — **찍혔다 ≠ 받았다**.
    🚨 2026-09-12 응답 모양이 `list[SearchHit]` 에서 이 봉투로 바뀌었다.
       화면이 아직 없어서 지금이 바꿀 수 있는 마지막 때다 (D-147).
    """

    hits: list[SearchHit] = Field(default_factory=list)
    #: `ok` 이거나, **안 된 이유**가 그대로 들어온다.
    vector: str
    #: 갈래별 건수 — 0 이 「못 했다」인지 「없다」인지는 위 `vector` 가 말한다.
    counts: dict[str, int] = Field(default_factory=dict)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """무엇이 있고 무엇이 아직 없는지 한 화면에 낸다.

    ⛔ 2026-09-09 — 서버를 처음 띄우고 브라우저로 열었더니 **404** 였다. 루트가 비어 있었다.
       🚨 **처음 여는 자리를 비워 두면 「안 도는 것」처럼 보인다.** 실제로는 돌고 있었다.
       D-51 — 오류는 고치는 법을 보여준다. 여기서는 **어디를 볼지**를 보여준다.

    🚨 되는 것과 안 되는 것을 같은 화면에 적는다. 안 되는 것을 감추면
       팀원이 「되는 줄 알고」 붙었다가 두 번 고친다 (D-147 의 API 판).
    """
    return """<!doctype html><meta charset="utf-8"><title>CopyLane</title>
<style>body{font-family:system-ui;max-width:44rem;margin:3rem auto;padding:0 1rem;line-height:1.7}
code{background:#f4f4f5;padding:.1rem .35rem;border-radius:.25rem}
.no{color:#b91c1c}.yes{color:#15803d}</style>
<h1>CopyLane</h1>
<p>광고 문구 준법 검수·생성 — 판정 근거를 조문으로 돌려준다.</p>
<h2>지금 되는 것</h2>
<ul>
  <li class=yes><a href="/health">/health</a> — DB 층별 행 수</li>
  <li class=yes><a href="/search?q=%EC%A7%88%EB%B3%91&amp;category=%EC%8B%9D%ED%92%88">/search</a>
      — 조문 검색. <b>뜻(벡터)과 어휘를 RRF 로 섞은 한 순위</b> —
      각 줄의 <code>rank_vector</code>·<code>rank_lexical</code> 이
      <b>어느 갈래가 몇 위로 올렸는지</b> 말한다.
      벡터가 안 되면 <code>vector</code> 칸에 이유가 적힌다</li>
  <li class=yes><a href="/docs">/docs</a> — API 계약 <b>(판정 응답 스키마 포함)</b></li>
  <li class=yes><a href="/fixtures">/fixtures</a>
      — <b>진입점 셋</b>의 고정 응답 14건 (D-124 · D-181):
      judge 9 · generate 2 · compose 3. 화면·BFF 는 이것으로 붙는다.
      <b>실제 판정이 아니다</b></li>
</ul>
<h2>아직 없는 것</h2>
<ul>
  <li class=no><code>POST /judge</code> · <code>/generate</code> · <code>/compose</code>
      — 진입점 셋의 엔진이 없다. <b>501</b> 을 낸다 (D-119 — 판정 코어는 하나).
      가짜 200 을 내면 프론트가 그 모양에 맞춰 붙고 진짜가 오면 두 번 고친다.</li>
  <li class=no>화면(Jinja2 + HTMX) — D-56 이 정해 뒀고 아직 안 지었다.</li>
  <li class=no>벡터 <b>인덱스</b> — 지금 규모(청크 수천)에서는 순차 스캔이 빠르고,
      <code>ivfflat</code> 은 <code>lists</code> 를 잘못 잡으면 재현율이 조용히 떨어진다.
      <b>빠뜨린 것이 아니라 판정이다</b> — 근거는 <code>app/retrieve.py</code> 머리말.</li>
  <li class=no><b>리랭커</b>(bge-reranker-v2-m3) — D-77 예산표의 다음 층이다.
      어휘+벡터가 후보 50개를 만들고, 그 안의 순서를 리랭커가 고친다.
      <b>후보에 없는 것은 리랭커도 못 건진다</b> — 그 몫은 규칙 매칭 사전이 맡는다.</li>
  <li class=no><b>규칙 매칭 사전</b>(536행) — 「타사보다 3배」 같은 비방·부당비교는
      조문과 어휘가 하나도 안 겹쳐 <b>어휘로도 벡터로도 후보에 안 든다</b>
      (2026-09-12 실측: 50위 밖). 이 유형은 사전이 맡아야 한다.</li>
  <li class=no><code>violation_article</code>·<code>sanction_rule</code>
      — 근거 조문 대응표와 제재 수치. 그래서 위험도가 아직 스텁이다.</li>
</ul>
"""


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


@app.get("/search", response_model=SearchResult)
def search(q: str, category: str = "일반", limit: int = 5) -> SearchResult:
    """조문 검색 — **어휘와 벡터를 RRF 로 섞은 한 순위** (2026-09-12 오후 · D-193).

        vector    뜻이 가까운 것.  「면역력 쑥!」 → 「질병의 예방 및 치료에 효능이…」
        lexical   어휘가 겹치는 것. 조사를 깎고 접두어로 맞춘다
        ↓
        fused     `Σ 1/(60 + 순위)` — 점수가 아니라 **순위만** 쓴다

    🔄 종전에는 두 갈래를 **따로** 냈다. 합치지 않은 이유는 「[임의] 가중치를 안 만든다」였고,
       그 판정은 **가중합만 보고 내린 것**이었다. RRF 에는 더할 가중치가 없다 (D-193).
    🚨 각 줄의 `rank_vector`·`rank_lexical` 이 **어느 갈래가 올렸는지**를 말한다.
       한 갈래가 죽어도 결과는 그럴듯하므로, 합친 순위만 보면 안 보인다 (D-185).
    🔴 벡터가 안 되면 **어휘 결과를 내되 `vector` 칸에 이유를 적는다.** 조용히 안 떨어진다.
    ⬜ 기호 검색(「제5호 아목」)은 `rt.by_literal` 이 맡고 **여기 섞지 않는다** (D-167).
       기호는 부분 일치가 아니라 정확한 글자를 원한다 — 섞으면 둘 다 나빠진다.
       🔜 진입점은 따로 낸다. 지금은 코어에만 있다.
    """
    import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다

    try:
        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            # 🚨 합치는 것도 상태 문자열을 짓는 것도 코어가 한다 — 여기는 얇다 (D-51 · D-99).
            hits, vector_state = rt.search(cur, q, category, limit)
    except psycopg.Error as e:
        raise HTTPException(503, f"DB 에 못 붙었다 — {e}") from e

    # 🔴 **갈래별 건수는 합친 뒤에도 센다** — 「어휘만으로 올라온 줄이 몇이냐」가
    #    한 갈래가 죽었는지 보는 가장 싼 신호다. 0 이 「못 했다」인지는 `vector` 가 말한다.
    counts = {
        rt.MATCH_VECTOR: sum(1 for h in hits if h.rank_vector is not None),
        rt.MATCH_LEXICAL: sum(1 for h in hits if h.rank_lexical is not None),
    }
    return SearchResult(
        hits=[SearchHit(**dataclasses.asdict(h)) for h in hits],
        vector=vector_state,
        counts=counts,
    )


@app.post("/judge", response_model=JudgeResponse, responses={501: {"description": "엔진 미착수"}})
def judge(req: JudgeRequest) -> JudgeResponse:
    """판정 — 🚨 **엔진은 아직 없다.** 가짜 200 을 내지 않는다.

    🔄 2026-09-10 (D-124 ②) — `response_model` 을 붙였다. FastAPI 가 `/docs` 와
       `openapi.json` 에 **완전한 응답 스키마**를 싣는다. 팀원은 그것으로 붙는다.
       ★ 껍데기가 곧 목 서버라는 D-124 의 뜻이 이것이다 — **200 을 지어내지 않고도**
         계약이 기계가 읽는 형태로 나간다.
    🚨 고정 응답은 `/judge/fixtures/{name}` 이 낸다. **이 라우트는 501 을 지킨다** —
       임의 입력에 픽스처를 돌려주면 그건 계약이 아니라 거짓말이다.
    """
    raise HTTPException(
        501,
        "판정 엔진이 아직 없다. 계약은 정해져 있다 — GET /judge/fixtures 로 분기별 "
        "고정 응답을 받고, 스키마는 /docs 에서 본다. 가짜 200 을 내면 프론트가 "
        "그 모양에 맞춰 붙고 진짜가 오면 두 번 고친다.",
    )


#: 골든 픽스처 (D-124 ③) — 화면·BFF 가 모든 분기를 그리는 재료
#: 🔄 2026-09-10 — **진입점 셋으로 나눴다** (D-181). 종전에는 판정 하나뿐이었고,
#:    화면은 SCR-GN 3 · SCR-AD 3 으로 이미 서 있는데 응답 모양이 없었다.
FIXTURE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"
FIXTURE_KINDS: dict[str, Any] = {
    "judge": JudgeResponse,  # A 문구 검수
    "generate": GenerateResponse,  # B 카피 생성
    "compose": ComposeResponse,  # C AI 광고 생성
}


@app.get("/fixtures")
def fixtures_index() -> dict[str, list[str]]:
    """진입점별 고정 응답 목록. 🚨 **실제 판정이 아니다** — 계약 확인용이다."""
    return {
        kind: sorted(p.stem for p in (FIXTURE_ROOT / kind).glob("*.json")) for kind in FIXTURE_KINDS
    }


@app.get("/fixtures/{kind}/{name}")
def fixture(kind: str, name: str) -> Any:
    """고정 응답 하나 (D-124 ②③ · D-181).

    ⛔ 파일을 그대로 흘려보내지 않고 **계약을 통과시켜** 낸다. 픽스처가 계약과
       어긋나면 여기서 500 이 난다 — 화면이 어긋난 모양에 붙는 것보다 낫다.
    """
    model = FIXTURE_KINDS.get(kind)
    if model is None:
        raise HTTPException(404, f"진입점은 {list(FIXTURE_KINDS)} 셋이다 — 목록은 GET /fixtures")
    f = FIXTURE_ROOT / kind / f"{name}.json"
    if not f.exists():
        raise HTTPException(404, "그런 픽스처가 없다 — 목록은 GET /fixtures")
    return model.model_validate_json(f.read_text(encoding="utf-8"))


@app.post(
    "/generate", response_model=GenerateResponse, responses={501: {"description": "엔진 미착수"}}
)
def generate(req: GenerateRequest) -> GenerateResponse:
    """진입점 B — 카피 생성 (D-181). 🚨 엔진은 아직 없다. 계약만 나간다."""
    raise HTTPException(501, "생성 엔진이 아직 없다. 고정 응답은 GET /fixtures/generate/… 에 있다.")


@app.post(
    "/compose", response_model=ComposeResponse, responses={501: {"description": "엔진 미착수"}}
)
def compose(req: ComposeRequest) -> ComposeResponse:
    """진입점 C — AI 광고 생성 (D-164 · D-181). 🚨 엔진은 아직 없다."""
    raise HTTPException(
        501, "템플릿 엔진이 아직 없다. 고정 응답은 GET /fixtures/compose/… 에 있다."
    )
