"""app/routers/admin_board.py — 게시판관리(공지사항·FAQ) 화면 (뼈대) · 소유자 **psj**
   (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. 화면의 "새 공지 작성"·"새 FAQ 작성" 버튼은
   전부 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **`notice`·`faq` 테이블은 아직 없다** — DB 승인 요청조차 안 한 상태다. 그래서 DB 조회를
   시도하지 않고 **더미로만** 그린다 (admin_errors.py 의 dummy_no_table 분기보다 한 단계
   이른 상태 — 테이블 존재 여부를 물을 대상 자체가 없다).
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `_notices`/`_faqs` 배열 구조를 그대로 따른다 —
   나중에 실데이터 붙을 때 필드명이 어긋나지 않게.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/board` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/board/notices`, `/admin/board/faq` 가 된다.
router = APIRouter(prefix="/board")

PAGE_SIZE = 20

# ─────────────────────────────────────────────────────────────
# 더미 — notice·faq 테이블 자체가 아직 없다. ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 _notices/_faqs 배열을 그대로 옮겨온 것 — 실제 운영
# 문구가 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────

_DUMMY_NOTICES: list[dict] = [
    {
        "id": 1,
        "title": "[중요] 건강기능식품 광고 심사 기준 변경 안내",
        "category": "규정 변경",
        "author": "박수진",
        "date": "08.28",
        "period": "08.28 ~ 상시",
        "status": "게시중",
        "pinned": True,
        "content": (
            "건강기능식품에 관한 법률 제18조 개정에 따라 광고 심사 기준이 "
            "아래와 같이 변경됩니다.\n\n1. 기능성 표현 범위 확대\n"
            "2. 인체적용시험 결과 인용 기준 강화\n3. 비교광고 허용 범위 조정\n\n"
            "변경된 기준은 2026년 9월 1일부터 적용됩니다."
        ),
    },
    {
        "id": 2,
        "title": "8월 시스템 정기점검 안내 (08.30 02:00~06:00)",
        "category": "시스템",
        "author": "김민수",
        "date": "08.27",
        "period": "08.27 ~ 08.31",
        "status": "게시중",
        "pinned": False,
        "content": (
            "안녕하세요, CopyLane 운영팀입니다.\n\n"
            "아래와 같이 시스템 정기점검을 실시합니다.\n\n"
            "- 일시: 2026.08.30 (토) 02:00 ~ 06:00 (4시간)\n"
            "- 영향: 서비스 전체 이용 불가\n- 사유: DB 마이그레이션 및 보안 패치"
        ),
    },
    {
        "id": 3,
        "title": "Enterprise 플랜 신규 기능 출시",
        "category": "업데이트",
        "author": "이서은",
        "date": "08.25",
        "period": "08.25 ~ 09.25",
        "status": "게시중",
        "pinned": False,
        "content": (
            "Enterprise 플랜에 새로운 기능이 추가되었습니다.\n\n"
            "1. 팀 공동 작업 기능\n2. 고급 분석 대시보드\n"
            "3. API 호출 한도 확대 (월 10,000회)"
        ),
    },
    {
        "id": 4,
        "title": "AI 판정 모델 v2.5 업데이트 안내",
        "category": "업데이트",
        "author": "김민수",
        "date": "08.15",
        "period": "08.15 ~ 상시",
        "status": "게시중",
        "pinned": False,
        "content": (
            "AI 판정 모델이 v2.5로 업데이트되었습니다.\n\n주요 개선사항:\n"
            "- 건기식 카테고리 정확도 3.2%p 향상\n- 신규 규정 반영 속도 개선\n"
            "- 오판정 자동 학습 파이프라인 도입"
        ),
    },
    {
        "id": 5,
        "title": "개인정보처리방침 개정 안내",
        "category": "규정 변경",
        "author": "박수진",
        "date": "08.10",
        "period": "08.10 ~ 상시",
        "status": "게시중",
        "pinned": False,
        "content": (
            "개인정보처리방침이 일부 개정되었습니다.\n\n주요 변경사항:\n"
            "- 마케팅 수신동의 항목 세분화\n- 제3자 제공 동의 절차 강화\n"
            "- 개인정보 보유기간 명확화"
        ),
    },
]

_FAQ_CATEGORIES = ("검수 이용", "결제·플랜", "카피 생성", "기업 회원", "가입·로그인")

_DUMMY_FAQS: list[dict] = [
    {
        "id": 1,
        "order": 1,
        "q": "검수 결과에 이의를 제기하려면 어떻게 하나요?",
        "category": "검수 이용",
        "views": 342,
        "date": "08.25",
        "a": (
            '검수 결과 상세 화면에서 "이의제기" 버튼을 클릭하세요. 이의제기 시 사유를 '
            "작성하시면 담당자 검토 후 3영업일 이내에 결과를 안내드립니다."
        ),
    },
    {
        "id": 2,
        "order": 2,
        "q": "Enterprise 플랜은 무엇이 다른가요?",
        "category": "결제·플랜",
        "views": 289,
        "date": "08.20",
        "a": (
            "Enterprise 플랜은 팀 단위 이용에 최적화된 플랜입니다.\n"
            "- 월 500건 검수/생성\n- 팀원 관리 및 권한 설정\n"
            "- 전담 매니저 배정\n- API 우선 호출 및 SLA 보장"
        ),
    },
    {
        "id": 3,
        "order": 3,
        "q": "카피 생성 시 참고하는 법률 기준은?",
        "category": "카피 생성",
        "views": 256,
        "date": "08.18",
        "a": (
            "CopyLane AI는 다음 법률을 참고합니다:\n- 식품표시광고법\n"
            "- 건강기능식품에 관한 법률\n- 화장품법\n- 의료기기법\n"
            "- 공정거래위원회 심사지침"
        ),
    },
    {
        "id": 4,
        "order": 4,
        "q": "기업 회원 가입 시 필요한 서류는?",
        "category": "기업 회원",
        "views": 198,
        "date": "08.15",
        "a": (
            "기업 회원 가입 시 필요 서류:\n1. 사업자등록증 사본\n"
            "2. 담당자 신분증 사본\n3. (선택) 광고심의확인서\n"
            "4. (선택) 제조·수입 허가증"
        ),
    },
    {
        "id": 5,
        "order": 5,
        "q": "비밀번호를 잊어버렸어요",
        "category": "가입·로그인",
        "views": 187,
        "date": "08.10",
        "a": (
            '로그인 페이지에서 "비밀번호 찾기"를 클릭하세요. 가입 시 등록한 이메일로 '
            "재설정 링크가 발송됩니다. 링크는 24시간 유효합니다."
        ),
    },
    {
        "id": 6,
        "order": 6,
        "q": "검수 결과는 얼마나 정확한가요?",
        "category": "검수 이용",
        "views": 165,
        "date": "08.08",
        "a": (
            "현재 AI 판정 정확도는 평균 94.2%입니다. 식품(96.1%), 일반(97.3%)이 "
            "높고 의약외품(89.5%)이 상대적으로 낮습니다."
        ),
    },
    {
        "id": 7,
        "order": 7,
        "q": "플랜을 변경하려면 어떻게 하나요?",
        "category": "결제·플랜",
        "views": 154,
        "date": "08.05",
        "a": "마이페이지 > 구독 관리에서 변경 가능합니다. 상위 플랜 변경 시 차액이 즉시 결제됩니다.",
    },
    {
        "id": 8,
        "order": 8,
        "q": "API 연동은 어떻게 하나요?",
        "category": "검수 이용",
        "views": 143,
        "date": "08.01",
        "a": "Pro 이상 플랜에서 API 연동이 가능합니다. 마이페이지 > API 설정에서 키를 발급받으세요.",
    },
]


def _clean_page(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1


def _paginate(rows: list[dict], page: int) -> tuple[list[dict], int]:
    total = len(rows)
    start = (page - 1) * PAGE_SIZE
    return rows[start : start + PAGE_SIZE], total


@router.get("/notices", response_class=HTMLResponse)
def notice_list(request: Request) -> HTMLResponse:
    """공지사항 목록 — 읽기 전용. `notice` 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    category = (qp.get("category") or "").strip() or None
    page = _clean_page(qp.get("page"))

    rows = _DUMMY_NOTICES
    if category:
        rows = [r for r in rows if r["category"] == category]
    # 고정(pinned) 공지를 앞으로
    rows = sorted(rows, key=lambda r: (not r["pinned"], -r["id"]))

    page_rows, total = _paginate(rows, page)
    pages = max(1, -(-total // PAGE_SIZE))
    categories = sorted({r["category"] for r in _DUMMY_NOTICES})
    return templates.TemplateResponse(
        request,
        "admin/board/notices.html",
        {
            "actor": actor,
            "rows": page_rows,
            "total": total,
            "page": page,
            "pages": pages,
            "category": category or "",
            "categories": categories,
        },
    )


@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: int) -> HTMLResponse:
    """공지사항 상세 — 읽기 전용. 수정·삭제 버튼은 뼈대만."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_NOTICES if r["id"] == notice_id), None)
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "admin/board/notice_detail.html", {"actor": actor, "row": row}
    )


@router.get("/faq", response_class=HTMLResponse)
def faq_list(request: Request) -> HTMLResponse:
    """FAQ 목록 — 읽기 전용. `faq` 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    qp = request.query_params
    category = (qp.get("category") or "").strip() or None
    page = _clean_page(qp.get("page"))

    rows = _DUMMY_FAQS
    if category:
        rows = [r for r in rows if r["category"] == category]
    rows = sorted(rows, key=lambda r: r["order"])

    page_rows, total = _paginate(rows, page)
    pages = max(1, -(-total // PAGE_SIZE))
    return templates.TemplateResponse(
        request,
        "admin/board/faq.html",
        {
            "actor": actor,
            "rows": page_rows,
            "total": total,
            "page": page,
            "pages": pages,
            "category": category or "",
            "categories": _FAQ_CATEGORIES,
        },
    )


@router.get("/faq/{faq_id}", response_class=HTMLResponse)
def faq_detail(request: Request, faq_id: int) -> HTMLResponse:
    """FAQ 상세 — 읽기 전용. 수정·삭제 버튼은 뼈대만."""
    actor = require_governor(request)
    row = next((r for r in _DUMMY_FAQS if r["id"] == faq_id), None)
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "admin/board/faq_detail.html", {"actor": actor, "row": row}
    )
