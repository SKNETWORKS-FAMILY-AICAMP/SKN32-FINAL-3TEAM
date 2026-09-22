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
import logging
import pathlib
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
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
from app.logging_conf import mask, setup_logging
from app.routers import admin_router, auth_router, user_router
from app.settings import DEFAULT_CATEGORY, PARAMS, admin_is_mounted, dsn
from app.templating import STATIC_ROOT

# 🔴 **로거를 여기서 세운다** (보안점검 P1-4). import 시점이라 잊을 자리가 없다 —
#    `uvicorn app.api:app` 이든 `TestClient` 든 이 모듈을 지나야 앱이 생긴다.
#    ⛔ 「띄울 때 부르세요」로 두면 아무도 안 부른다 (D-117 — 코드로만 막힌다).
setup_logging()
_log = logging.getLogger("copylane.api")

# 🔴 **검색 로직은 이 파일에 없다** — `app/retrieve.py` 하나가 든다 (D-99 · D-51).
#    ⛔ `app/graph.py` 의 `retrieve` 노드가 **같은 검색**을 부를 자리다(🔜 W4~).
#       여기서 고치면 그때 두 벌이 된다. 이 파일은 **두 갈래를 불러 한 응답에 담는 껍데기**다.

app = FastAPI(
    title="CopyLane",
    description="광고 문구 준법 검수·생성 — 판정 근거를 조문으로 돌려준다",
    version="0.1.0",
)

#: 🔴 **모든 응답에 붙는 보안 헤더** (2026-09-12 밤 · 보안점검 P2-9 · D-212).
#: ⛔ `base.html` 의 CSP 는 **HTML 에만** 붙는다. JSON·오류 응답·`/docs` 는 그 밖이었다.
#:    🚨 `nosniff` 가 없으면 브라우저가 JSON 을 HTML 로 추측해 그릴 수 있고, 그 순간
#:       「데이터인데 실행됐다」가 된다. 헤더는 **한 곳에서 전부에** 붙여야 뜻이 있다 (D-99).
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # 🚨 CSP 의 frame-ancestors 와 같은 뜻인데, 구형 브라우저는 이쪽만 본다
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # ⛔ 우리는 이 셋을 안 쓴다 — 안 쓰는 것을 **명시적으로 끈다**
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

#: 🔴 **HTML 이 아닌 응답**(JSON·오류)의 CSP — 아무것도 안 부른다.
_CSP_DATA = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

#: 🔴 **화면의 CSP — 여기가 단일 출처다** (D-99). 종전에는 `base.html` 의 `<meta>` 에만 있었고
#:    그러면 **템플릿을 안 쓰는 응답에는 안 붙는다.** 헤더는 전부에 붙고 meta 는 그 페이지에만 붙는다.
#: 🚨 `style-src` 에만 `unsafe-inline` 을 둔다 — HTMX 가 `style` 을 건드린다. ⬜ 좁힐 자리다.
#:    ⛔ `script-src` 에는 **절대 열지 않는다** — 열면 P2-9 의 피해 범위가 그대로 커진다.
_CSP_PAGE = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "form-action 'self'; base-uri 'none'"
)

#: ⬜ **Swagger·ReDoc 은 CDN 에서 스크립트를 받는다** — 엄격한 CSP 를 걸면 `/docs` 가 안 뜨고,
#:    그건 팀원이 계약을 보는 창구다. **면제하되 면제 사실을 여기 남긴다** (D-192).
#:    🚨 배포 때는 `/docs` 자체를 닫는 판정이 필요하다 — 지금은 로컬뿐이라 연다.
#: 🔄 2026-09-14 (psj) — `/static/mockup.html` 추가. 프론트 목업(Tailwind CDN + 인라인
#:    스크립트)을 FastAPI 배관 테스트용으로 같은 origin 에서 열려고 면제했다. 같은 이유,
#:    같은 패턴(D-192). ⬜ 목업이 실제 화면으로 전환되면 이 예외는 지운다 — 그때는 CSP
#:    안에서 동작하게 다시 짜야 한다. 팀장 파일이라 여기 남기고 디코에도 알린다.
_CSP_EXEMPT = ("/docs", "/redoc", "/openapi.json", "/static/mockup.html")


@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Response:
    """🚨 **미들웨어 하나가 전부를 덮는다** — 라우트마다 붙이면 새 라우트가 빠진다 (D-117).

    ★ CSP 는 **여기 한 곳**에서 정한다 (D-99). `base.html` 의 `<meta>` 는 그 페이지에만
      붙지만 헤더는 **전부에** 붙는다 — 손으로 쓴 HTML(`/`)과 오류 응답까지.
    ⬜ `/docs`·`/redoc` 만 면제한다 — Swagger 가 CDN 스크립트를 받는다.
    """
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if not request.url.path.startswith(_CSP_EXEMPT):
        html = response.headers.get("content-type", "").startswith("text/html")
        response.headers.setdefault("Content-Security-Policy", _CSP_PAGE if html else _CSP_DATA)
    return response


# 🔴 **화면·BFF 는 여기 안 쓴다** (D-208 · 병렬작업 계약 §5). 팀원 4명이 같은 파일을
#    고치지 않도록 `app/routers/` 로 갈랐다 — `user.py`(ksr·lse) · `admin.py`(ssm·psj).
#    ⛔ 이 파일은 **판정 코어 API 와 조립부**다. 새 화면 라우트를 여기 더하지 않는다.
app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")
app.include_router(user_router)

# 🔴 **관리자와 로그인은 에디션이 정한다** (D-213 · 배포계획 §1).
#    ⛔ 배포 그림에 **제품 관리자 화면의 자리가 없었다** — `api:8000`(Caddy 뒤 · 공개)과
#       `admin:8001 SQLAdmin`(터널) 둘뿐이었다. 공개 쪽에 두면 배포하는 순간
#       **등급 판정 근거와 2인 확인 서명(사람 이름)이 인터넷에 선다.** 읽기 전용이어도 같다.
#    ★ 배포계획이 이미 「에디션 = compose 프로파일」을 채택했다 — 그 손잡이를 쓴다.
#    🚨 **닫는다 = 안 붙인다.** 라우트가 없으면 404 다 — 인증 실패(401)와 다른 답이고,
#       **없는 것과 막힌 것은 다르다.**
if admin_is_mounted():
    app.include_router(admin_router)
    app.include_router(auth_router)


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
    #: 🔴 **이 근거가 조문의 일부인가** (0011 · D-199). `part_total > 1` 이면 조각이다.
    #:    ⛔ `citation` 은 좌표로 맞지만 **전문이 아니다** — 화면은 「제18조 (1/3)」처럼 적고,
    #:       인용 검증은 조문 집합 대조에 이 사실을 함께 넣는다 (기획서 5-6).
    #:    🚨 `null` 은 「아직 재적재 안 됨」이지 「안 쪼갰다」가 아니다. 안 쪼갰으면 1/1 이다.
    part_no: int | None = None
    part_total: int | None = None
    #: 「제8조제1항제1호」 또는 「[별표 1]제2호가목1)」. 🚨 `null` 이면 **조립을 못 한 것**이지
    #:    근거가 없는 게 아니다. 그때는 `article`·`paragraph`·`doc_title` 을 쓴다.
    #:    🔴 값이 있다고 「조문 전문」이 아니다 — `part_total` 을 **같이** 본다 (D-199).
    #:    🔄 2026-09-14 (0015) — 종전 주석은 *「별표는 조립하지 않는다」* 였다. 이제 조립한다.
    citation: str | None = None
    doc_type: str | None = None
    #: 🆕 별표 번호 (0015) — **원문 머리글에서 읽은 값만.** `null` 이면 인용이 안 선다.
    #:    ⛔ 파일명 일련번호가 아니다 — 짐작해 채우면 다른 별표를 가리킬 수 있다 (D-224).
    annex_no: int | None = None
    #: 🆕 문서 이름 — 「부당한 표시 또는 광고의 내용(제3조제1항 관련)」. 🚨 **좌표가 아니다.**
    #:    화면이 무슨 별표인지 말할 때 쓴다. 좌표는 `citation` 이다.
    doc_title: str | None = None
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
    #: `ok` 이거나, 벡터가 **안 된 이유**가 그대로 들어온다.
    vector: str
    #: 🔴 2026-09-12 밤 (D-202) — 어휘 갈래도 같은 칸을 갖는다. `ok` 이거나 `no_terms: …`.
    #:    ⛔ 종전에는 벡터만 있었다. 「질의에 검색어가 없다」와 「겹치는 조문이 없다」가
    #:       둘 다 0건으로 나와 **부르는 쪽에서 구별이 없었다.**
    lexical: str
    #: 후보 폭 — `counts` 의 `*_pool` 이 이 수를 분모로 한다 (기획서 5-6 의 「상위 50」).
    pool: int = 0
    #: 🔴 **분모가 둘이다** (D-178 · D-202).
    #:    `vector_pool`·`lexical_pool`  — 후보 `pool` 안에서 각 갈래가 잡은 수
    #:    `vector_top`·`lexical_top`    — 돌려준 `limit` 안에서 각 갈래가 올린 수
    #:    ⛔ 종전에는 뒤엣것 둘만 있었고 이름에 분모가 없었다. 그러면 「후보에는 있었는데
    #:       상위에 못 들었다」가 「후보가 없었다」와 같은 0 으로 보인다.
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
  <li class=yes><code>POST /search</code> (<a href="/docs#/default/search_search_post">/docs 에서 눌러 본다</a>)
      — 조문 검색. 🔴 <b>GET 이 아니다</b> — 문구를 URL 에 실으면 접근 로그·히스토리·Referer 가
      전부 나른다 (보안점검 P1-4). <b>뜻(벡터)과 어휘를 RRF 로 섞은 한 순위</b> —
      각 줄의 <code>rank_vector</code>·<code>rank_lexical</code> 이
      <b>어느 갈래가 몇 위로 올렸는지</b> 말한다.
      갈래가 안 되면 <code>vector</code>·<code>lexical</code> 칸에 이유가 적히고,
      <code>counts</code> 는 <b>후보(<code>_pool</code>)와 응답(<code>_top</code>)을 갈라</b> 센다.
      <code>part_total</code> 이 1보다 크면 <b>그 근거는 조문의 일부</b>다</li>
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
  <li class=no><b>리랭커</b> — D-77 예산표의 다음 층이고 <b>지금 가장 급한 층</b>이다.
      어휘+벡터가 후보 50개(기획서 5-6)를 만들고, 그 안의 순서를 리랭커가 고친다.
      <b>「면역력이 쑥쑥」류가 이 층을 기다린다</b> — 2026-09-12 오후 실측에서
      <b>어휘 후보 0건</b>이라 어휘가 못 돕고 벡터 15위였다. 후보 안에는 있으니
      순서를 고칠 층이 리랭커뿐이다.
      🚨 모델 미선정 — 기획서 7-3 이 v2-m3(0.6B)와 base(0.3B)를 <b>나란히 재라</b>고 했다.</li>
  <li class=no><b>규칙 매칭 사전</b>(536행) — 어휘도 벡터도 못 잡는 유형을 맡는다.
      ⚠️ <b>2026-09-12 오후에 근거가 뒤집혔다</b>: 종전 이 자리에 「타사보다 3배」류가
      예로 적혀 있었는데, 실측에서 <b>어휘가 3위로 잡았다</b>
      (조문 제8조제1항제6호의 「제품」이 겹친다). 그 예는 틀렸다.
      <b>어느 유형이 이 층을 필요로 하는지는 골든셋 30건 뒤에 정한다</b> (D-40 · D-198).</li>
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
        # 🔴 **원인 문자열을 응답에 담지 않는다** — 호스트·포트·사용자명이 그 안에 있다.
        #    ⛔ 게다가 이 응답은 **200 으로 나간다** — 모니터링에도 안 걸리면서 정보만 샌다.
        _log.warning("health: DB 접속 실패 — %s", type(e).__name__)
        return Health(ok=False, db=f"down: {type(e).__name__}")


class SearchRequest(BaseModel):
    """조문 검색 요청. 🔴 **GET 이 아니라 POST 다** (보안점검 P1-4 · 2026-09-12 밤).

    ⛔ **무엇이 있었나** — `GET /search?q=<문구>` 였다. P1-4 의 조치가
       *"문구는 절대 URL 에 싣지 않는다 (POST 본문만)"* 라고 못박은 바로 그 형태다.
       uvicorn 접근 로그·브라우저 히스토리·Referer·배포 후 ALB 로그가 전부 문구를 나른다.
       D-76 이 관리자 화면에서 막은 원문이 로그로 다 보인다.
    🚨 **화면이 붙기 전이 이 결정의 마지막 기회였다** — 팀원이 `hx-get="/search?q=…"` 를
       쓰기 시작하면 고칠 곳이 네 사람의 템플릿이 된다.
    ★ 상한 셋은 **없으면 무제한**이다 (보안점검 P2-11 — 자원 고갈).
    """

    q: str = Field(..., min_length=1, max_length=PARAMS.max_text_len)
    category: str = DEFAULT_CATEGORY
    limit: int = Field(PARAMS.top_k, ge=1, le=PARAMS.max_limit)


@app.post("/search", response_model=SearchResult)
def search(req: SearchRequest) -> SearchResult:
    """조문 검색 — **어휘와 벡터를 RRF 로 섞은 한 순위** (2026-09-12 오후 · D-193).

        vector    뜻이 가까운 것.  「면역력 쑥!」 → 「질병의 예방 및 치료에 효능이…」
        lexical   어휘가 겹치는 것. 조사를 깎고 접두어로 맞춘다
        ↓
        fused     `Σ 1/(k + 순위)` — 점수가 아니라 **순위만** 쓴다 (`k` 는 `rt.RRF_K`)

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
            # 🚨 합치는 것도 상태를 짓는 것도 코어가 한다 — 여기는 얇다 (D-51 · D-99).
            hits, state = rt.search(cur, req.q, req.category, req.limit)
    except psycopg.Error as e:
        # 🔴 **원인을 응답에 담지 않는다** (2026-09-12 밤). psycopg 의 OperationalError 는
        #    호스트·포트·사용자명을 문자열에 담고, 배포 후에는 RDS 엔드포인트가 여기서 샌다.
        #    ⛔ 대신 **로그에 남긴다** — 질의는 `mask()` 를 지난다 (P1-4).
        _log.warning("DB 접속 실패 · 질의=%s · 원인=%s", mask(req.q), type(e).__name__)
        raise HTTPException(503, "DB 에 못 붙었다 — 서버 로그를 본다") from e

    # 🔴 **분모를 이름에 박는다** (D-178 · D-202). `*_pool` 은 후보 폭 안, `*_top` 은 응답 안이다.
    #    ⛔ 이름에 분모가 없으면 「후보에 없었다」와 「상위에 못 들었다」가 같은 0 으로 읽힌다.
    counts = {
        f"{rt.MATCH_VECTOR}_pool": state.pool_vector,
        f"{rt.MATCH_LEXICAL}_pool": state.pool_lexical,
        f"{rt.MATCH_VECTOR}_top": sum(1 for h in hits if h.rank_vector is not None),
        f"{rt.MATCH_LEXICAL}_top": sum(1 for h in hits if h.rank_lexical is not None),
    }
    return SearchResult(
        hits=[SearchHit(**dataclasses.asdict(h)) for h in hits],
        vector=state.vector,
        lexical=state.lexical,
        pool=state.pool,
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


#: 🔴 픽스처 이름은 **이 모양만** 받는다 — 영숫자·밑줄·붙임표. 점도 슬래시도 백슬래시도 없다.
_FIXTURE_NAME = re.compile(r"[A-Za-z0-9_\-]{1,64}")


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
    # 🔴 **이름을 화이트리스트로 막는다** (2026-09-12 밤 · 경로 순회).
    #    ⛔ `kind` 는 `FIXTURE_KINDS` 로 검증됐는데 `name` 은 검증이 없었다.
    #       `%5C`(백슬래시)는 Starlette 의 `[^/]+` 를 통과하고 **Windows 의 `pathlib` 는
    #       그것을 경로 구분자로 읽는다.** 팀 5인과 CI 가 전부 Windows 다.
    #       내용이 나가려면 계약을 통과해야 해서 지금은 좁지만, **임의 `.json` 존재 오라클**이고
    #       팀원이 업로드·다운로드 라우트를 이 패턴으로 복사하면 그대로 커진다.
    #    ★ 「막는다」가 아니라 「받을 것만 받는다」로 적는다 — 부정 목록은 반드시 빠뜨린다.
    if not _FIXTURE_NAME.fullmatch(name):
        raise HTTPException(404, "그런 픽스처가 없다 — 목록은 GET /fixtures")
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
