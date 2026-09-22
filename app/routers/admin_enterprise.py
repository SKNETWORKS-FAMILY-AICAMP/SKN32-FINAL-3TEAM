"""app/routers/admin_enterprise.py — 회원관리(기업 회원) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_members.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **기업 회원을 담는 테이블 자체가 없다** — 회원 목록(admin_members.py)과 같은 이유다.
   서비스 쪽 기업 가입 기능(ksr·lse 담당)이 스키마와 함께 먼저 생겨야 한다. 그래서 DB
   조회를 시도하지 않고 **더미로만** 그린다.
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `ENTERPRISES_V22` 배열·`enterprise`/`enterprise-detail`
   뷰 구조를 그대로 따른다. 목업 상세 화면은 탭(구성원·사용량 분석·결제 이력)을 JS 로
   전환하지만, 여기는 스크립트 없이(CSP `script-src 'self'`) 세 섹션을 순서대로 모두
   펼쳐서 보여준다 — admin/members/detail.html 과 같은 방식.
   이용량 추이·기능별 사용량·구성원 명단·결제 내역은 목업에서도 하드코딩된 예시라
   그대로 옮긴다 (담는 집계·결제 테이블이 아직 없다).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/enterprise` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/enterprise`, `/admin/enterprise/{id}` 가 된다.
router = APIRouter(prefix="/enterprise")

ENTERPRISE_PLANS = ("Basic", "Pro", "Enterprise")

# ─────────────────────────────────────────────────────────────
# 더미 — 기업 회원 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 ENTERPRISES_V22 배열을 그대로 옮겨온 것 — 실제 기업
# 정보가 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────
_DUMMY_ENTERPRISES: list[dict] = [
    {
        "id": "e1",
        "name": "(주)미래광고",
        "biz": "120-88-12345",
        "rep": "김민아",
        "members": 24,
        "plan": "Enterprise",
        "joined": "2025.11.05",
        "status": "활성",
    },
    {
        "id": "e2",
        "name": "브랜드원",
        "biz": "211-09-45678",
        "rep": "윤하람",
        "members": 12,
        "plan": "Enterprise",
        "joined": "2026.01.20",
        "status": "활성",
    },
    {
        "id": "e3",
        "name": "푸드마켓",
        "biz": "314-81-90876",
        "rep": "장우진",
        "members": 8,
        "plan": "Pro",
        "joined": "2026.03.17",
        "status": "활성",
    },
    {
        "id": "e4",
        "name": "헬스뷰티랩",
        "biz": "501-22-33445",
        "rep": "서민지",
        "members": 5,
        "plan": "Basic",
        "joined": "2026.06.02",
        "status": "검토중",
    },
]

# 목업 enterprise-detail 에 하드코딩된 예시 수치 — 담는 집계·결제 테이블이 아직 없다.
_USAGE_TREND = [("4월", 820), ("5월", 940), ("6월", 1010), ("7월", 1130), ("8월", 1248)]
_FEATURE_USAGE = [
    ("문구 판정", "1,248건"),
    ("카피 생성", "864건"),
    ("문서 저장", "326건"),
    ("API 호출", "2,410회"),
]


def _clean_choice(value: str | None, allowed: tuple[str, ...]) -> str | None:
    return value if value in allowed else None


@router.get("", response_class=HTMLResponse)
def enterprise_list(request: Request) -> HTMLResponse:
    """기업 회원 목록 — 읽기 전용. 기업 회원 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    plan = _clean_choice(qp.get("plan"), ENTERPRISE_PLANS)

    rows = _DUMMY_ENTERPRISES
    if plan:
        rows = [r for r in rows if r["plan"] == plan]

    return templates.TemplateResponse(
        request,
        "admin/members/enterprise_list.html",
        {
            "actor": actor,
            "rows": rows,
            "plan": plan or "",
            "plans": ENTERPRISE_PLANS,
            "total": len(_DUMMY_ENTERPRISES),
        },
    )


@router.get("/{enterprise_id}", response_class=HTMLResponse)
def enterprise_detail(request: Request, enterprise_id: str) -> HTMLResponse:
    """기업 회원 상세 — 읽기 전용. 구성원·사용량 분석·결제 이력을 한 화면에 순서대로."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_ENTERPRISES if r["id"] == enterprise_id), None)
    if row is None:
        raise HTTPException(status_code=404)

    max_usage = max(v for _, v in _USAGE_TREND)

    return templates.TemplateResponse(
        request,
        "admin/members/enterprise_detail.html",
        {
            "actor": actor,
            "row": row,
            "usage_trend": _USAGE_TREND,
            "max_usage": max_usage,
            "feature_usage": _FEATURE_USAGE,
        },
    )
