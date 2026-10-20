"""app/routers/admin_stats.py — 통계 화면(대시보드·이용자·매출·품질·판정·생성) (뼈대) ·
   소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** CSV 다운로드 버튼은 전부 `disabled` 뼈대다(목업은 `mockDownload()`).
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **검수(판정) 통계(`/quality/judge`)는 `judgment` 표를 읽는다** (아래 `_load_judge`).
🔄 2026-10-20 — **생성 통계(`/quality/generation`)는 `copy_sentence` 출처별 건수를 읽는다** (아래 `_load_generation` ·
   생성 결과를 저장하는 경로가 아직 없어 `generated` 는 0 건이 정상이다).
🔴 **이용자 통계 전용 테이블은 없다** — `db/schema.sql` 에
   흔적이 없다. DB 승인 요청조차 안 한 상태라 **더미로만** 그린다
   (admin_board.py 와 같은 이유 — admin_errors.py 의 dummy_no_table 분기보다 한 단계 이르다).
   ⬜ 스키마가 생기면 실제 집계를 읽고, 못 읽었을 때 예시로 채우지 않는다.
🔄 매출 통계는 D-260 ⑥ · D-69 · D-107에 따라 닫힘 사유만 표시한다.

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
   최종본) 구조.** 검수·생성 KPI + 매출 닫힘 라벨 + 일/주/월 토글 + 검수·생성 추이. `/admin/`(기존 거버넌스 대시보드 — 데이터 층 표)과는 다른 화면이다 —
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

# D-260 ⑥: revenue stays closed. The label is the single edit point pending schedule review.
LABEL = "Phase 4 이후"
CLOSED = {
    "page_title": "매출 통계",
    "label": LABEL,
    "decision": "D-260 ⑥ · D-69 · D-107",
    "why": [
        "결제(PG) 연동은 프로젝트 범위 밖이에요 (D-69).",
        "요금제·결제 테이블이 없어요 (D-69).",
        "실제 사용 데이터가 없어 매출을 집계할 수 없어요 (D-96).",
    ],
    "needs": [
        "과금 정책 확정",
        "PG 연동 판정",
        "payment / subscription 테이블 스키마 (팀장)",
    ],
    "alt": [],
}


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
            ("09/10", 42, 6),
            ("09/11", 38, 5),
            ("09/12", 51, 9),
            ("09/13", 47, 7),
            ("09/14", 55, 4),
            ("09/15", 49, 8),
            ("09/16", 44, 6),
        ]
    ],
    "weekly": [
        {"label": f"{w}주차", "join": j, "leave": lv}
        for w, j, lv in [
            ("8월 3주", 289, 41),
            ("8월 4주", 312, 38),
            ("9월 1주", 334, 45),
            ("9월 2주", 326, 40),
        ]
    ],
    "monthly": [
        {"label": m, "join": j, "leave": lv}
        for m, j, lv in [
            ("5월", 1102, 154),
            ("6월", 1245, 167),
            ("7월", 1389, 172),
            ("8월", 1421, 189),
            ("9월", 660, 85),
        ]
    ],
}

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
    """매출은 비활성 사유만 표시한다. 예시 금액·입력·쓰기 기능을 제공하지 않는다."""
    actor = require_governor(request)
    return templates.TemplateResponse(request, "admin/_closed.html", {"actor": actor, **CLOSED})


@router.get("/revenue/{revenue_id}", response_class=HTMLResponse)
def revenue_detail(request: Request, revenue_id: str) -> HTMLResponse:  # noqa: ARG001
    """상세 경로도 동일한 닫힘 안내를 제공한다."""
    return revenue_stats(request)


@router.get("/quality", response_class=HTMLResponse)
def quality_stats(request: Request) -> HTMLResponse:
    """메뉴의 검수 통계도 기존 운영 집계를 사용한다. 인증·기간 정규화는 같은 경로다."""
    return judge_stats(request)


# ─────────────────────────────────────────────────────────────
# 🔄 2026-10-20 — 검수(판정) 통계는 **`judgment` 표를 읽는다** (`admin_dbread` · D-72).
#    ⛔ 종전 더미(정확도 94.2% · 이의제기 승인율 · 오판정 사례)는 지웠다 — 운영 판정에는 정답 라벨이 없어
#       정확도를 셀 수 없다. 셀 수 없는 수를 그리면 없는 사실을 만든다 (D-147).
#    ★ 세는 것: 문장 판정 수 · 검수 요청(문서) 수 · 판정 상태 · 보류 사유 · 품목 · 위험도 · 위반 유형 · 인코더 사용률 · 일별 추이.
#    🔴 원문은 읽지 않는다 — 건수만 (D-76 열람 경계). 이력 보관에 동의한 검수만 저장된다 (D-96).
#    🚨 상태 · 보류 사유 글자는 사용자 화면(`user.py` `_VERDICT_LABELS` · `_HOLD_LABELS`)과 같은 한 벌 (D-99).
# ─────────────────────────────────────────────────────────────
_JUDGE_DAYS = (7, 30, 90)
_RISK_LABEL = {
    0: "R0 특이사항 없음",
    1: "R1 시정명령 위험",
    2: "R2 업무정지 위험",
    3: "R3 영업 상실 위험",
}
#: 일별 추이를 그리는 최대 일수 — 「전체」 기간도 최근 이만큼만 막대로 그린다
_TREND_MAX_DAYS = 30


def _bars(rows: list[dict], label_of=lambda k: k) -> list[dict]:  # noqa: ANN001
    total = sum(r["n"] for r in rows) or 1
    return [
        {"label": label_of(r["k"]), "n": r["n"], "pct": round(r["n"] * 100 / total, 1)}
        for r in rows
    ]


def _load_judge(days: int) -> dict:
    from app.encoder import JUDGED_BY_MARK  # noqa: PLC0415
    from app.routers import admin_dbread as db  # noqa: PLC0415

    where = "WHERE judged_at >= now() - make_interval(days => %s)" if days else ""
    p: list[object] = [days] if days else []
    trend_days = min(days or _TREND_MAX_DAYS, _TREND_MAX_DAYS)
    group = "SELECT {k} AS k, count(*) AS n FROM judgment {w} {extra} GROUP BY 1 ORDER BY 2 DESC"
    source, out = db.run(
        [
            (
                "SELECT count(*) AS n, count(DISTINCT doc_id) AS docs, "
                "count(*) FILTER (WHERE judged_by LIKE %s ESCAPE '\\') AS enc, "
                "min(judged_at) AS first_at, max(judged_at) AS last_at "
                f"FROM judgment {where}",
                [db.like_param(JUDGED_BY_MARK), *p],
            ),
            (group.format(k="verdict", w=where, extra=""), p),
            (
                group.format(
                    k="hold_reason", w=where or "WHERE TRUE", extra="AND verdict = 'hold'"
                ),
                p,
            ),
            (group.format(k="coalesce(product_category, '미확정')", w=where, extra=""), p),
            (
                group.format(
                    k="risk_final", w=where or "WHERE TRUE", extra="AND risk_final IS NOT NULL"
                ),
                p,
            ),
            (
                group.format(
                    k="violation_type",
                    w=where or "WHERE TRUE",
                    extra="AND violation_type IS NOT NULL",
                )
                + " LIMIT 10",
                p,
            ),
            (
                "SELECT (judged_at AT TIME ZONE 'Asia/Seoul')::date AS d, count(*) AS n FROM judgment "
                "WHERE judged_at >= now() - make_interval(days => %s) GROUP BY 1 ORDER BY 1",
                [trend_days],
            ),
        ],
        what="stats.judge",
    )
    if source != "db":
        return {"source": source}
    from app.routers.user import _HOLD_LABELS, _VERDICT_LABELS  # noqa: PLC0415

    k = out[0][0]
    n = k["n"]
    trend = [{"label": db.fmt_dt(r["d"], "%m.%d"), "n": r["n"]} for r in out[6]]
    return {
        "source": source,
        "kpi": {
            "sentences": n,
            "docs": k["docs"],
            "enc_pct": round(k["enc"] * 100 / n, 1) if n else None,
            "first_at": db.fmt_dt(k["first_at"], "%Y.%m.%d"),
            "last_at": db.fmt_dt(k["last_at"]),
        },
        "by_verdict": _bars(out[1], lambda v: _VERDICT_LABELS.get(v, v)),
        "by_hold": _bars(out[2], lambda v: _HOLD_LABELS.get(v, v or "사유 없음")),
        "by_category": _bars(out[3]),
        "by_risk": _bars(
            sorted(out[4], key=lambda r: r["k"]), lambda v: _RISK_LABEL.get(v, f"R{v}")
        ),
        "by_type": _bars(out[5], lambda v: str(v).replace("_", " ")),
        "trend": trend,
        "trend_max": max((r["n"] for r in trend), default=0),
        "trend_days": trend_days,
    }


@router.get("/quality/judge", response_class=HTMLResponse)
def judge_stats(request: Request) -> HTMLResponse:
    """검수(판정) 통계 — 읽기 전용 · `judgment` 표에서 센다. 기간: 최근 7 · 30 · 90일 · 전체."""
    actor = require_governor(request)
    raw = request.query_params.get("days", "30")
    days = int(raw) if raw.isdigit() and int(raw) in _JUDGE_DAYS else (0 if raw == "all" else 30)
    return templates.TemplateResponse(
        request,
        "admin/stats/judge.html",
        {
            "actor": actor,
            "days": days,
            "day_options": _JUDGE_DAYS,
            **_load_judge(days),
        },
    )


# ─────────────────────────────────────────────────────────────
# 🔄 2026-10-20 — 생성 통계는 **`copy_sentence` 를 출처(`origin`)별로 센다** (`admin_dbread` · D-72).
#    ⛔ 종전 더미(품질 88.4점 · GPT-4o 45% · 재생성 사유)는 지웠다 — 실제 구성과도 달랐고 셀 근거가 없다 (D-147).
#    🚨 **지금은 생성 결과를 저장하는 경로가 없다** — `copy_sentence` 에 쓰는 곳은 검수 이력(`judgment_store.save_review`,
#       `origin='user'`)뿐이다. 그래서 `generated` 는 0 건이 정상이고, 화면은 「사용이 없다」가 아니라 「저장하지 않는다」로 적는다.
#       생성 저장을 열려면 동의 · 보관 기한 판정이 먼저다 (D-96 · D-129 · D-307).
#    🔴 원문은 읽지 않는다 — 건수만 (D-76).
# ─────────────────────────────────────────────────────────────
_ORIGIN_LABEL = {
    "user": "직접 입력 · 검수",
    "generated": "카피 생성",
    "batch": "일괄 검수",
    "crawl": "URL 수집 (설계만)",
}


def _load_generation(days: int) -> dict:
    from app.routers import admin_dbread as db  # noqa: PLC0415

    where = "WHERE created_at >= now() - make_interval(days => %s)" if days else ""
    gen_where = (where + " AND " if where else "WHERE ") + "origin = 'generated'"
    p: list[object] = [days] if days else []
    trend_days = min(days or _TREND_MAX_DAYS, _TREND_MAX_DAYS)
    source, out = db.run(
        [
            (
                f"SELECT origin AS k, count(*) AS n FROM copy_sentence {where} GROUP BY 1 ORDER BY 2 DESC",
                p,
            ),  # noqa: S608
            (
                "SELECT count(*) AS n, count(DISTINCT doc_id) AS docs, "
                "count(*) FILTER (WHERE approved_at IS NOT NULL) AS approved, max(created_at) AS last_at "
                f"FROM copy_sentence {gen_where}",  # noqa: S608
                p,
            ),
            (
                "SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS d, count(*) AS n FROM copy_sentence "
                "WHERE origin = 'generated' AND created_at >= now() - make_interval(days => %s) "
                "GROUP BY 1 ORDER BY 1",
                [trend_days],
            ),
        ],
        what="stats.generation",
    )
    if source != "db":
        return {"source": source}
    by_origin = _bars(out[0], lambda v: _ORIGIN_LABEL.get(v, v))
    g = out[1][0]
    total = sum(r["n"] for r in out[0])
    trend = [{"label": db.fmt_dt(r["d"], "%m.%d"), "n": r["n"]} for r in out[2]]
    return {
        "source": source,
        "kpi": {
            "generated": g["n"],
            "docs": g["docs"],
            "approved": g["approved"],
            "share": round(g["n"] * 100 / total, 1) if total else None,
            "last_at": db.fmt_dt(g["last_at"]),
            "stored_total": total,
        },
        "by_origin": by_origin,
        "trend": trend,
        "trend_max": max((r["n"] for r in trend), default=0),
        "trend_days": trend_days,
    }


@router.get("/quality/generation", response_class=HTMLResponse)
def generation_stats(request: Request) -> HTMLResponse:
    """생성 통계 — 읽기 전용 · `copy_sentence` 출처별 건수. 기간: 최근 7 · 30 · 90일 · 전체."""
    actor = require_governor(request)
    raw = request.query_params.get("days", "30")
    days = int(raw) if raw.isdigit() and int(raw) in _JUDGE_DAYS else (0 if raw == "all" else 30)
    return templates.TemplateResponse(
        request,
        "admin/stats/generation.html",
        {
            "actor": actor,
            "days": days,
            "day_options": _JUDGE_DAYS,
            **_load_generation(days),
        },
    )


# ─────────────────────────────────────────────────────────────
# 대시보드 — 검수·생성은 기존 예시, 매출은 닫힘 라벨만 표시한다.
# ─────────────────────────────────────────────────────────────

_DASH_DATA = {
    "daily": {
        "kpi": {"judge": "143", "gen": "86"},
        "delta": {"judge": "▲ 12% 전일 대비", "gen": "▲ 9% 전일 대비"},
        "trend_title": "시간대별 서비스 이용",
        "labels": ["09시", "11시", "13시", "15시", "17시", "19시", "21시"],
        "judge_series": [11, 18, 23, 19, 28, 22, 22],
        "gen_series": [7, 10, 15, 12, 18, 13, 11],
    },
    "weekly": {
        "kpi": {"judge": "892", "gen": "534"},
        "delta": {"judge": "▲ 8% 전주 대비", "gen": "▲ 11% 전주 대비"},
        "trend_title": "요일별 서비스 이용",
        "labels": ["월", "화", "수", "목", "금", "토", "일"],
        "judge_series": [95, 112, 108, 132, 151, 139, 155],
        "gen_series": [56, 64, 61, 79, 91, 84, 99],
    },
    "monthly": {
        "kpi": {"judge": "3,842", "gen": "2,318"},
        "delta": {
            "judge": "▲ 15% 전월 대비",
            "gen": "▲ 12% 전월 대비",
        },
        "trend_title": "월별 서비스 이용",
        "labels": ["2월", "3월", "4월", "5월", "6월", "7월", "8월"],
        "judge_series": [2100, 2450, 2680, 2920, 3180, 3540, 3842],
        "gen_series": [1260, 1480, 1610, 1770, 1910, 2140, 2318],
    },
}


@router.get("/dashboard", response_class=HTMLResponse)
def stats_dashboard(request: Request) -> HTMLResponse:
    """통계 대시보드 — 검수·생성 예시 집계와 매출 닫힘 상태를 표시한다.
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
            "revenue_label": LABEL,
        },
    )
