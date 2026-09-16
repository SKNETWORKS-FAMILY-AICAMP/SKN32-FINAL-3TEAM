"""app/routers/admin.py — 관리자 화면 + BFF · 소유자 **ssm · psj** (D-208 · 병렬작업 계약 §5).

✅ **로그인이 섰다** (D-66 구현 · D-213). `require_governor` 를 지나지 않으면 화면이 안 뜬다 —
   **읽기도 막는다.** 이 화면이 내는 것은 등급 판정 근거와 **2인 확인 서명(사람 이름)** 이다.
🔴 **클라우드 에디션에서는 이 라우터가 아예 안 붙는다** (D-213) — 라우트가 없으면 404 다.
   배포 그림에 제품 관리자 화면의 자리가 없었고, 그것을 에디션(compose 프로파일)으로 갈랐다.
⬜ **쓰기 경로는 아직 없다.** 게이트가 막고 있고, 여는 것은 별도 판정이다 (§8 ⑬ 의 남은 절반).

★ **거버넌스 운영 화면이 여기 붙는다** — 소스 레지스트리 2인 확인 · 판정매트릭스 열람.
  🚨 **생성물은 화면이 만들지 않는다** — 보여 주기만 한다 (D-90 · 집행계약 §6).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import auth
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])
_log = logging.getLogger("copylane.admin")

#: 🚨 `app/api.py` 의 `/health` 와 **같은 목록**이라야 한다. ⬜ 두 벌이다 (D-99) —
#:    합치는 것은 `/health` 를 함수로 빼는 일이고, 그건 팀장 파일이라 PR 로 올린다.
_TABLES = (
    "source",
    "fragment",
    "document",
    "chunk",
    "chunk_embedding",
    "dict_entry",
    "product_fact",
    "golden_sample",
)


def require_governor(request: Request) -> str:
    """로그인한 이니셜. 없으면 로그인 화면으로 보낸다 (D-66 · D-213).

    🔴 **읽기도 막는다.** 이 화면이 내는 것은 등급 판정 근거와 **2인 확인 서명(사람 이름)** 이다 —
       읽기 전용이어도 공개 표면에 놓일 것이 아니다 (D-76 · P2-10).
    """
    initials = auth.read_session(request.cookies.get(auth.SESSION_COOKIE))
    if not initials:
        # 🚨 401 이 아니라 **303 리다이렉트**다 — 사람이 보는 화면이라 로그인 폼으로 보낸다.
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return initials


def _table_counts() -> dict[str, int]:
    """`_TABLES` 각각의 행 수. DB 가 없으면 **빈 dict** — 예외를 삼킨다 (D-51).

    🚨 `index()` 와 `/api/counts` 가 **같은 함수**를 쓴다 — 로직을 두 벌 두지 않는다 (D-99).
    """
    counts: dict[str, int] = {}
    try:
        import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            for table in _TABLES:
                cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — 고정 목록이다
                counts[table] = cur.fetchone()[0]
    except Exception as e:  # noqa: BLE001
        # 🔴 원인 문자열을 화면에 담지 않는다 — 호스트·포트·사용자명이 그 안에 있다.
        _log.warning("admin: DB 접속 실패 — %s", type(e).__name__)
    return counts


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """관리자 첫 화면. 🚨 **DB 가 없어도 뜬다** — 빈 표를 그리고 고치는 법을 낸다 (D-51)."""
    actor = require_governor(request)
    return templates.TemplateResponse(
        request, "admin/index.html", {"counts": _table_counts(), "actor": actor}
    )


_SOURCE_GRADES = ("G0", "G1", "G2", "G3")
_SOURCE_SORTS = {
    "grade_decided_at_desc": "grade_decided_at DESC",
    "grade_decided_at_asc": "grade_decided_at ASC",
    "name_asc": "name ASC",
    "grade_asc": "grade ASC",
}
_PAGE_SIZE = 20


def _list_sources(
    *,
    grade: str | None = None,
    verified: bool | None = None,
    sort: str = "grade_decided_at_desc",
    page: int = 1,
) -> tuple[list[dict] | None, int]:
    """`source` 테이블 목록 — 목업 `sources` 화면 컬럼에 맞춰 낸다.

    🚨 읽기 전용이다 — D-66 2인 확인 절차가 쓰기 경로를 아직 안 열었다.
    ⬜ DB 접속 실패 시 **(None, 0)** 을 낸다 (`_table_counts()` 의 빈 dict 와 같은 정신 —
       화면이 죽지 않고 "DB 없음" 상태를 그린다, D-51).
    🆕 등급·검증여부 필터, 정렬, 페이지네이션 — 전부 쿼리 파라미터다. DB 스키마는
       안 건드린다 (병렬작업 계약 §5 `db/**` 등급 1 승인 필요 없음).
    """
    order_by = _SOURCE_SORTS.get(sort, _SOURCE_SORTS["grade_decided_at_desc"])
    where = []
    params: dict = {}
    if grade in _SOURCE_GRADES:
        where.append("grade = %(grade)s")
        params["grade"] = grade
    if verified is not None:
        where.append("verified = %(verified)s")
        params["verified"] = verified
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    offset = max(page - 1, 0) * _PAGE_SIZE
    params["limit"] = _PAGE_SIZE
    params["offset"] = offset

    try:
        import psycopg  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn(), row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM source {where_sql}", params)  # noqa: S608
            total = cur.fetchone()["n"]

            cur.execute(
                f"""
                SELECT source_id, name, publisher, grade, layer, verified,
                       grade_decided_at, grade_decided_by, grade_reviewed_by
                FROM source
                {where_sql}
                ORDER BY {order_by}
                LIMIT %(limit)s OFFSET %(offset)s
                """,  # noqa: S608 — order_by 는 화이트리스트(_SOURCE_SORTS)에서만 온다
                params,
            )
            return cur.fetchall(), total
    except Exception as e:  # noqa: BLE001
        _log.warning("admin: source 조회 실패 — %s", type(e).__name__)
        return None, 0


@router.get("/sources", response_class=HTMLResponse)
def sources(
    request: Request,
    grade: str | None = None,
    verified: str | None = None,
    sort: str = "grade_decided_at_desc",
    page: int = 1,
) -> HTMLResponse:
    """판정 근거(소스 레지스트리) 목록 — 읽기 전용.

    🚨 목업 `sources` 화면의 백엔드다. 쓰기(등급 판정·2인 확인)는 아직 안 연다 —
       그 절차(§8 ⑬)가 정해지기 전까지 이 화면은 **보여 주기만** 한다 (D-90).
    🆕 `?grade=G1&verified=true&sort=name_asc&page=2` — 필터·정렬·페이지네이션.
    """
    actor = require_governor(request)
    verified_bool = {"true": True, "false": False}.get(verified) if verified else None
    page = max(page, 1)
    rows, total = _list_sources(grade=grade, verified=verified_bool, sort=sort, page=page)
    total_pages = max((total + _PAGE_SIZE - 1) // _PAGE_SIZE, 1)
    return templates.TemplateResponse(
        request,
        "admin/sources.html",
        {
            "sources": rows,
            "actor": actor,
            "grade": grade,
            "verified": verified,
            "sort": sort,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "grades": _SOURCE_GRADES,
        },
    )


_DICT_SORTS = {
    "dict_kind_term": "dict_kind, term",
    "term_asc": "term ASC",
    "confidence_desc": "confidence DESC NULLS LAST",
}


def _list_dict_kinds() -> list[str]:
    """`dict_entry.dict_kind` 실제 값 목록 — ENUM 이 아니라 TEXT 라 화이트리스트 대신
    DB 에 실제로 있는 값으로 드롭다운을 채운다 (D-99 주석 참고 — 표기가 갈릴 수 있음).
    DB 접속 실패 시 빈 리스트.
    """
    try:
        import psycopg  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT dict_kind FROM dict_entry ORDER BY dict_kind")
            return [r[0] for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        _log.warning("admin: dict_kind 조회 실패 — %s", type(e).__name__)
        return []


def _list_dict_entries(
    *,
    dict_kind: str | None = None,
    q: str | None = None,
    sort: str = "dict_kind_term",
    page: int = 1,
) -> tuple[list[dict] | None, int]:
    """`dict_entry` 목록 — 금지표현·적법표현 등 판정용 사전. 읽기 전용.

    🚨 `_list_sources()` 와 같은 패턴 — DB 접속 실패 시 (None, 0) (D-51).
    🆕 종류 필터, 용어 검색(ILIKE), 정렬, 페이지네이션.
    """
    order_by = _DICT_SORTS.get(sort, _DICT_SORTS["dict_kind_term"])
    where = []
    params: dict = {}
    if dict_kind:
        where.append("dict_kind = %(dict_kind)s")
        params["dict_kind"] = dict_kind
    if q:
        where.append("term ILIKE %(q)s")
        params["q"] = f"%{q}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    offset = max(page - 1, 0) * _PAGE_SIZE
    params["limit"] = _PAGE_SIZE
    params["offset"] = offset

    try:
        import psycopg  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn(), row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM dict_entry {where_sql}", params)  # noqa: S608
            total = cur.fetchone()["n"]

            cur.execute(
                f"""
                SELECT term, dict_kind, violation_type, law_ref, exact_match, confidence
                FROM dict_entry
                {where_sql}
                ORDER BY {order_by}
                LIMIT %(limit)s OFFSET %(offset)s
                """,  # noqa: S608 — order_by 는 화이트리스트(_DICT_SORTS)에서만 온다
                params,
            )
            return cur.fetchall(), total
    except Exception as e:  # noqa: BLE001
        _log.warning("admin: dict_entry 조회 실패 — %s", type(e).__name__)
        return None, 0


@router.get("/dict-entries", response_class=HTMLResponse)
def dict_entries(
    request: Request,
    dict_kind: str | None = None,
    q: str | None = None,
    sort: str = "dict_kind_term",
    page: int = 1,
) -> HTMLResponse:
    """표현 사전(판정 근거) 목록 — 읽기 전용.

    🚨 `dict_entry` 는 원문(source/fragment)에서 뽑아낸 판정용 사전이다 — 목업의
       "판정 근거 관리"(법률·고시 원문)와는 다른 개념이라 라우트를 분리했다.
    🆕 `?dict_kind=금지표현&q=효능&sort=term_asc&page=2` — 필터·검색·정렬·페이지네이션.
    """
    actor = require_governor(request)
    page = max(page, 1)
    rows, total = _list_dict_entries(dict_kind=dict_kind, q=q, sort=sort, page=page)
    total_pages = max((total + _PAGE_SIZE - 1) // _PAGE_SIZE, 1)
    return templates.TemplateResponse(
        request,
        "admin/dict_entries.html",
        {
            "entries": rows,
            "actor": actor,
            "dict_kind": dict_kind,
            "q": q or "",
            "sort": sort,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "dict_kinds": _list_dict_kinds(),
        },
    )


def _list_admin_accounts() -> list[dict] | None:
    """`app_account` 목록 — 이니셜·이름·마지막 로그인·활성 상태만. 읽기 전용.

    ⛔ **해시는 절대 안 뽑는다** — `scripts/admin_account.py show()` 와 같은 이유
       (해시가 곧 지문이다). 🚨 계정 추가는 이 화면에 없다 — D-66 이 "온프레미스는
       회원가입 화면을 만들지 않는다"고 명시한다. `launcher.py admin-add` 로만 만든다.
    """
    try:
        import psycopg  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn(), row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT initials, display_name, last_login_at, disabled_at
                FROM app_account
                ORDER BY initials
                """
            )
            return cur.fetchall()
    except Exception as e:  # noqa: BLE001
        _log.warning("admin: app_account 조회 실패 — %s", type(e).__name__)
        return None


@router.get("/admins", response_class=HTMLResponse)
def admins(request: Request) -> HTMLResponse:
    """관리자 계정 목록 — 읽기 전용, 끝까지 읽기 전용.

    🚨 목업엔 계정 CRUD 화면이 있었지만 D-66("온프레미스는 회원가입 화면을 만들지
       않는다")과 충돌해 스코프에서 뺐다 — 계정은 `launcher.py admin-add` 로만 만든다.
    """
    actor = require_governor(request)
    rows = _list_admin_accounts()
    return templates.TemplateResponse(
        request, "admin/admins.html", {"accounts": rows, "actor": actor}
    )


def _get_source(source_id: str) -> dict | None:
    """`source` 단건 조회 — 상세(등급 판정 제안) 화면용. 읽기 전용.

    🚨 `_list_sources()` 와 같은 패턴 — DB 접속 실패·행 없음 모두 None (D-51).
       (있음/없음/DB 없음을 구분하지 않는다 — 화면이 "찾을 수 없다"로 셋 다 받는다.)
    """
    try:
        import psycopg  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn(), row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_id, name, publisher, url, layer, grade, cost, value,
                       access, license, attribution, collector, refresh,
                       grade_decided_by, grade_reviewed_by, grade_decided_at,
                       grade_evidence_url, supersedes, verified, note
                FROM source
                WHERE source_id = %s
                """,
                (source_id,),
            )
            return cur.fetchone()
    except Exception as e:  # noqa: BLE001
        _log.warning("admin: source 단건 조회 실패 — %s", type(e).__name__)
        return None


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def source_detail(request: Request, source_id: str) -> HTMLResponse:
    """소스 상세 — 등급 판정 제안 · 2인 확인 화면.

    ⬜ **쓰기는 아직 안 연다.** 제안·확인 버튼은 화면엔 있지만 비활성(disabled) 이다 —
       `source_grade_proposal`/`source_grade_history` 테이블 팀장 승인이 먼저다
       (docs/psj/소스등급_판정흐름_스키마초안.md, 병렬작업 계약 §5 `db/**` 등급 1).
       승인 나오면 이 화면에 POST 라우트만 붙이면 된다 — 뼈대는 미리 만들어 둔다.
    """
    actor = require_governor(request)
    row = _get_source(source_id)
    return templates.TemplateResponse(
        request, "admin/source_detail.html", {"source": row, "actor": actor}
    )


@router.get("/api/counts")
def api_counts(request: Request) -> dict[str, int]:
    """🔌 **목업 프론트 연결 배관 테스트용** (2026-09-14).

    ⬜ **진짜 대시보드 지표(검수 건수·생성 건수·매출)가 아니다.** 그건 사용자 행동 로그·매출
       테이블이 따로 있어야 하고, 지금 DB 엔 없다 — 스키마 추가는 팀장 승인이 먼저다
       (병렬작업 계약 §5 · `db/**` 등급 1).
    🚨 이 라우트는 **"Postgres → FastAPI → 목업 화면" 배관이 실제로 뚫리는가**만 증명한다.
       읽기도 로그인을 요구한다 — `index()` 와 같은 이유다 (D-76 · P2-10).
    """
    require_governor(request)
    return _table_counts()
