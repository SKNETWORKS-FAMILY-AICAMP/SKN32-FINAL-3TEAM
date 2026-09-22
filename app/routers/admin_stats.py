"""app/routers/admin_stats.py — 통계 화면(대시보드·이용자·매출·품질·판정·생성) (뼈대) ·
   소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** CSV 다운로드 버튼은 전부 `disabled` 뼈대다(목업은 `mockDownload()`).
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔴 **관련 테이블(회원 통계·매출·판정 통계·생성 통계)이 전부 없다** — `db/schema.sql` 에
   흔적이 없다. DB 승인 요청조차 안 한 상태라 **더미로만** 그린다
   (admin_board.py 와 같은 이유 — admin_errors.py 의 dummy_no_table 분기보다 한 단계 이르다).
   ⬜ 스키마가 생기면 admin_errors.py 패턴(우선 DB, 실패 시 더미)으로 바꾼다.

🚨 목업(`app/static/mockup.html`)의 `VIEWS['member-stats']`/`VIEWS['revenue']`/
   `VIEWS['quality']`(=`qualityCombinedViewV2()` 원본, `qp-judge`/`qp-gen` 패널로 슬라이스됨)
   구조를 그대로 따른다 — 항상 **파일 뒤쪽(마지막) 재정의**가 최종본이다.

🔴 **일/주/월 토글은 목업에서 JS(`switchMemberStatsPeriodV2`/`switchQualPeriod`)로 전환하지만,
   여기는 CSP `script-src 'self'` 라 스크립트를 못 쓴다 — GET 쿼리 파라미터
   (`?period=daily|weekly|monthly`)로 서버사이드 전환한다 (2026-09-16 psj·사용자 합의).**

✅ **매출 통계(`/admin/stats/revenue`)는 목업에서 `role:'super'` 전용이었지만, 팀 결정으로
   관리자 등급 구분 자체를 없앴다 — 로그인한 관리자는 전부 동일 권한이다 (2026-09-16 결정).
   그래서 다른 화면과 똑같이 `require_governor`만 건다.

🚨 **품질 통계는 3개 라우트로 나눈다** — `/admin/stats/quality`(전체 요약),
   `/admin/stats/quality/judge`(판정 통계), `/admin/stats/quality/generation`(생성 통계).
   목업은 하나의 `qualityCombinedViewV2()` 를 패널로 슬라이스해 재사용하는데, 여기서도
   같은 더미 데이터 원본에서 함수만 나눠 각 화면을 그린다 — 데이터 구조 자체는 공유한다.

🚨 **`/admin/stats/dashboard` — 목업 `VIEWS['dashboard']`(app/static/mockup.html 11670번 줄,
   최종본) 구조.** KPI 3개(검수·생성 건수·매출) + 일/주/월 토글 + 시간대별 검수·생성 추이 +
   월별 매출. `/admin/`(기존 거버넌스 대시보드 — 데이터 층 표)과는 다른 화면이다 —
   운영 현황은 사이드바 "통계" 카테고리 안 별도 대시보드로 둔다 (2026-09-16 사용자 결정).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/stats` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/stats/member`, `/admin/stats/revenue`, `/admin/stats/quality`(+`/judge`,`/generation`) 가 된다.
router = APIRouter(prefix="/stats")

_PERIODS = ("daily", "weekly", "monthly")
_PERIOD_LABEL = {"daily": "일간", "weekly": "주간", "monthly": "월간"}


def _clean_period(value: str | None) -> str:
    return value if value in _PERIODS else "daily"


# ─────────────────────────────────────────────────────────────
# 더미 — member_stat·revenue·judge_stat·generation_stat 테이블 자체가 아직 없다.
# ⬜ 테이블 승인·적재 뒤 DB 조회로 바꾼다.
# 목업 app/static/mockup.html 의 VIEWS['member-stats']/VIEWS['revenue']/qualityCombinedViewV2()
# 데이터를 그대로 옮겨온 것 — 실제 운영 수치가 아니라 화면 구조 확인용이다.
# ─────────────────────────────────────────────────────────────

_MEMBER_KPI = {
    "total": 12483,
    "general": 10921,
    "influencer": 1327,
    "enterprise": 235,
}

_PAID_PLAN_DIST = [
    {"label": "Basic", "value": 892, "max": 1500},
    {"label": "Pro", "value": 341, "max": 1500},
    {"label": "Enterprise", "value": 235, "max": 1500},
]

_MEMBER_TYPE_CARDS = [
    {"type": "일반 회원", "desc": "개인 크리에이터 · 무료/Basic 플랜 중심", "count": 10921},
    {"type": "인플루언서 회원", "desc": "채널 연동 · 팔로워 인증 완료 계정", "count": 1327},
    {"type": "기업 회원", "desc": "사업자 인증 · 팀 단위 이용", "count": 235},
]

# 가입·탈퇴 추이 — period 별 막대(간이 트렌드). 실제 값은 예시 수치.
_JOIN_LEAVE_TREND = {
    "daily": [
        {"label": f"{d}일", "join": j, "leave": lv}
        for d, j, lv in [
            ("09/10", 42, 6), ("09/11", 38, 5), ("09/12", 51, 9),
            ("09/13", 47, 7), ("09/14", 55, 4), ("09/15", 49, 8), ("09/16", 44, 6),
        ]
    ],
    "weekly": [
        {"label": f"{w}주차", "join": j, "leave": lv}
        for w, j, lv in [
            ("8월 3주", 289, 41), ("8월 4주", 312, 38), ("9월 1주", 334, 45),
            ("9월 2주", 326, 40),
        ]
    ],
    "monthly": [
        {"label": m, "join": j, "leave": lv}
        for m, j, lv in [
            ("5월", 1102, 154), ("6월", 1245, 167), ("7월", 1389, 172),
            ("8월", 1421, 189), ("9월", 660, 85),
        ]
    ],
}

_REVENUE_KPI = {
    "period_revenue": "₩284,920,000",
    "mrr": "₩198,340,000",
    "arpu": "₩22,830",
    "receivable": "₩6,120,000",
}

_REVENUE_TREND = {
    "daily": [
        {"label": f"{d}일", "value": v}
        for d, v in [
            ("09/10", 8_420_000), ("09/11", 7_890_000), ("09/12", 9_210_000),
            ("09/13", 8_760_000), ("09/14", 10_340_000), ("09/15", 9_580_000), ("09/16", 8_990_000),
        ]
    ],
    "weekly": [
        {"label": f"{w}주차", "value": v}
        for w, v in [
            ("8월 3주", 58_200_000), ("8월 4주", 61_400_000),
            ("9월 1주", 64_900_000), ("9월 2주", 63_100_000),
        ]
    ],
    "monthly": [
        {"label": m, "value": v}
        for m, v in [
            ("5월", 231_000_000), ("6월", 248_500_000), ("7월", 262_100_000),
            ("8월", 271_800_000), ("9월", 284_920_000),
        ]
    ],
}

_REVENUE_BY_PLAN = [
    {"label": "Basic", "value": 89_200_000, "max": 300_000_000},
    {"label": "Pro", "value": 112_400_000, "max": 300_000_000},
    {"label": "Enterprise", "value": 83_320_000, "max": 300_000_000},
]

# 품질 통계 — 카테고리별 정확도/품질(전체 요약용)
_QUALITY_BY_CATEGORY = [
    {"label": "식품", "value": 96.1, "max": 100},
    {"label": "건기식", "value": 91.4, "max": 100},
    {"label": "화장품", "value": 93.8, "max": 100},
    {"label": "의료기기", "value": 88.2, "max": 100},
    {"label": "일반", "value": 97.3, "max": 100},
]

_QUALITY_KPI = {
    "avg_accuracy": "94.2%",
    "total_cases": "48,921건",
    "avg_review_time": "1.8초",
    "low_quality_rate": "2.4%",
}

_ENGINE_MIX = [
    {"label": "코드기반", "pct": 38},
    {"label": "인코더기반", "pct": 27},
    {"label": "sLLM기반", "pct": 35},
]

_JUDGE_KPI = {
    "accuracy": "94.2%",
    "total_cases": "48,921건",
    "avg_time": "1.8초",
    "appeal_approval_rate": "12.6%",
}

_JUDGE_MISCASES = [
    {"id": "JC-2291", "category": "건기식", "predicted": "부적합", "actual": "적합", "date": "09.14"},
    {"id": "JC-2288", "category": "의료기기", "predicted": "적합", "actual": "부적합", "date": "09.13"},
    {"id": "JC-2279", "category": "화장품", "predicted": "부적합", "actual": "적합", "date": "09.12"},
    {"id": "JC-2261", "category": "식품", "predicted": "적합", "actual": "부적합", "date": "09.10"},
]

_GEN_KPI = {
    "quality_score": "88.4점",
    "total_cases": "31,204건",
    "avg_time": "2.6초",
    "regen_rate": "7.1%",
}

_GEN_MODEL_MIX = [
    {"label": "GPT-4o", "pct": 45},
    {"label": "Claude", "pct": 35},
    {"label": "자체 Fine-tuned", "pct": 20},
]

_GEN_REASONS = [
    {"reason": "톤·스타일 불일치", "count": 412, "pct": 38.2},
    {"reason": "법률 근거 누락", "count": 289, "pct": 26.8},
    {"reason": "과장 표현 잔존", "count": 201, "pct": 18.6},
    {"reason": "글자 수 초과", "count": 176, "pct": 16.4},
]


@router.get("/member", response_class=HTMLResponse)
def member_stats(request: Request) -> HTMLResponse:
    """이용자 통계 — 읽기 전용. `member_stat` 테이블이 아직 없어 더미로만 그린다."""
    actor = require_governor(request)
    period = _clean_period(request.query_params.get("period"))
    return templates.TemplateResponse(
        request,
        "admin/stats/member.html",
        {
            "actor": actor,
            "kpi": _MEMBER_KPI,
            "paid_plans": _PAID_PLAN_DIST,
            "type_cards": _MEMBER_TYPE_CARDS,
            "period": period,
            "periods": _PERIODS,
            "period_label": _PERIOD_LABEL,
            "trend": _JOIN_LEAVE_TREND[period],
        },
    )


@router.get("/revenue", response_class=HTMLResponse)
def revenue_stats(request: Request) -> HTMLResponse:
    """매출 통계 — 읽기 전용. 목업에서 `role:'super'` 전용이었지만 관리자 등급 구분을
    없앤 팀 결정에 따라 다른 화면과 동일하게 `require_governor`만 건다.
    `revenue` 테이블이 아직 없어 더미로만 그린다.
    """
    actor = require_governor(request)
    period = _clean_period(request.query_params.get("period"))
    return templates.TemplateResponse(
        request,
        "admin/stats/revenue.html",
        {
            "actor": actor,
            "kpi": _REVENUE_KPI,
            "by_plan": _REVENUE_BY_PLAN,
            "period": period,
            "periods": _PERIODS,
            "period_label": _PERIOD_LABEL,
            "trend": _REVENUE_TREND[period],
            "max_trend": max(r["value"] for r in _REVENUE_TREND[period]),
        },
    )


@router.get("/quality", response_class=HTMLResponse)
def quality_stats(request: Request) -> HTMLResponse:
    """품질 통계(전체 요약) — 읽기 전용. `judge_stat`/`generation_stat` 테이블이 아직
    없어 더미로만 그린다. 판정/생성 상세는 별도 라우트(`/quality/judge`, `/quality/generation`).
    """
    actor = require_governor(request)
    return templates.TemplateResponse(
        request,
        "admin/stats/quality.html",
        {
            "actor": actor,
            "kpi": _QUALITY_KPI,
            "by_category": _QUALITY_BY_CATEGORY,
            "engine_mix": _ENGINE_MIX,
        },
    )


@router.get("/quality/judge", response_class=HTMLResponse)
def judge_stats(request: Request) -> HTMLResponse:
    """판정 통계 — 읽기 전용. 품질 통계 원본(목업 `qualityCombinedViewV2()`)의
    `qp-judge` 패널에 해당. `judge_stat` 테이블이 아직 없어 더미로만 그린다.
    """
    actor = require_governor(request)
    return templates.TemplateResponse(
        request,
        "admin/stats/judge.html",
        {
            "actor": actor,
            "kpi": _JUDGE_KPI,
            "engine_mix": _ENGINE_MIX,
            "miscases": _JUDGE_MISCASES,
        },
    )


@router.get("/quality/generation", response_class=HTMLResponse)
def generation_stats(request: Request) -> HTMLResponse:
    """생성 통계 — 읽기 전용. 품질 통계 원본(목업 `qualityCombinedViewV2()`)의
    `qp-gen` 패널에 해당. `generation_stat` 테이블이 아직 없어 더미로만 그린다.
    """
    actor = require_governor(request)
    return templates.TemplateResponse(
        request,
        "admin/stats/generation.html",
        {
            "actor": actor,
            "kpi": _GEN_KPI,
            "model_mix": _GEN_MODEL_MIX,
            "reasons": _GEN_REASONS,
        },
    )


# ─────────────────────────────────────────────────────────────
# 대시보드 — 목업 VIEWS['dashboard'] 구조. service_log·revenue 류 테이블이 없어 더미다.
# ─────────────────────────────────────────────────────────────

_DASH_DATA = {
    "daily": {
        "kpi": {"judge": "143", "gen": "86", "sales": "₩1.8M"},
        "delta": {"judge": "▲ 12% 전일 대비", "gen": "▲ 9% 전일 대비", "sales": "▲ 6.4% 전일 대비"},
        "trend_title": "시간대별 서비스 이용",
        "labels": ["09시", "11시", "13시", "15시", "17시", "19시", "21시"],
        "judge_series": [11, 18, 23, 19, 28, 22, 22],
        "gen_series": [7, 10, 15, 12, 18, 13, 11],
    },
    "weekly": {
        "kpi": {"judge": "892", "gen": "534", "sales": "₩12.1M"},
        "delta": {"judge": "▲ 8% 전주 대비", "gen": "▲ 11% 전주 대비", "sales": "▲ 5.3% 전주 대비"},
        "trend_title": "요일별 서비스 이용",
        "labels": ["월", "화", "수", "목", "금", "토", "일"],
        "judge_series": [95, 112, 108, 132, 151, 139, 155],
        "gen_series": [56, 64, 61, 79, 91, 84, 99],
    },
    "monthly": {
        "kpi": {"judge": "3,842", "gen": "2,318", "sales": "₩48.2M"},
        "delta": {"judge": "▲ 15% 전월 대비", "gen": "▲ 12% 전월 대비", "sales": "▲ 8.7% 전월 대비"},
        "trend_title": "월별 서비스 이용",
        "labels": ["2월", "3월", "4월", "5월", "6월", "7월", "8월"],
        "judge_series": [2100, 2450, 2680, 2920, 3180, 3540, 3842],
        "gen_series": [1260, 1480, 1610, 1770, 1910, 2140, 2318],
    },
}

_DASH_MONTHLY_SALES = [
    {"label": "2월", "value": "32.1"},
    {"label": "3월", "value": "34.5"},
    {"label": "4월", "value": "36.8"},
    {"label": "5월", "value": "39.4"},
    {"label": "6월", "value": "42.0"},
    {"label": "7월", "value": "44.3"},
    {"label": "8월", "value": "48.2"},
]


@router.get("/dashboard", response_class=HTMLResponse)
def stats_dashboard(request: Request) -> HTMLResponse:
    """통계 대시보드 — 읽기 전용. 목업 `VIEWS['dashboard']` 구조(KPI·시간대별 추이·월별 매출).
    `/admin/`(거버넌스 대시보드)과는 별개 화면이다. 집계 테이블이 없어 더미로만 그린다.
    """
    actor = require_governor(request)
    period = _clean_period(request.query_params.get("period"))
    d = _DASH_DATA[period]
    dash_max = max(d["judge_series"] + d["gen_series"])
    return templates.TemplateResponse(
        request,
        "admin/stats/dashboard.html",
        {
            "actor": actor,
            "period": period,
            "periods": _PERIODS,
            "period_label": _PERIOD_LABEL,
            "dash": d,
            "dash_max": dash_max,
            "monthly_sales": _DASH_MONTHLY_SALES,
        },
    )
