"""app/routers/admin_stats.py — 통계 화면(대시보드·이용자·매출·품질·판정·생성) (뼈대) ·
   소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** CSV 다운로드 버튼은 전부 `disabled` 뼈대다(목업은 `mockDownload()`).
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **검수(판정) 통계(`/quality/judge`)는 `judgment` 표를 읽는다** (아래 `_load_judge`).
🔄 2026-10-20 — **생성 통계(`/quality/generation`)는 엔진 상태와 생성 실패(`app_error_log`)만 그린다** (아래 `_load_generation` ·
   생성 결과 · 요청을 저장하지 않아 그 밖의 수는 셀 근거가 없다 · D-147).
🔄 2026-10-20 — **이용자 통계(`/member`)는 `user_account` 를, 대시보드(`/dashboard` · `/admin/`)는 `judgment` 를 센다**
   (아래 `_load_members` · `_load_usage`). 예시 수치는 모두 지웠다 — 못 읽으면 「-」 + 안내 (D-72 · D-147).
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

from datetime import datetime

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
# 🔄 2026-10-20 — 이용자 통계 · 대시보드의 이용 추이는 **운영 표를 읽는다** (`admin_dbread` · D-72 · D-147).
#    ⛔ 종전 더미(회원 12,483명 · 인플루언서 · 기업 · Basic/Pro 플랜 · 가입 추이 · 검수 143건 …)는 지웠다.
#    🔴 회원 유형 · 요금제 칸은 표에 없다(D-66 · D-69 · `UserAccount` docstring) — 그 분포는 그리지 않는다.
#    ★ 회원 상태는 회원 목록(`admin_members._STATUS_SQL`)과 같은 식이다 — 비활성 > 휴면(마지막 접속 365일 전) > 활성 (D-99).
#    ★ 검수 이용은 `judgment` 에서 센다 — 이력 보관에 동의한 검수만 저장된다(D-96). 생성 결과는 저장하지 않는다.
#    🚨 시각은 KST 고정 +9 (`admin_dbread.KST`) — 칸(시 · 일 · 주 · 월)은 KST 로 자른다.
# ─────────────────────────────────────────────────────────────

_UNIT_SQL = {"hour": "hour", "day": "day", "week": "week", "month": "month"}


def _month_add(d, months: int):  # noqa: ANN001, ANN202
    y, m = divmod(d.month - 1 + months, 12)
    return d.replace(year=d.year + y, month=m + 1, day=1)


def _axis(unit: str, count: int, now):  # noqa: ANN001, ANN202
    """(시작 시각 · 칸 키 목록 · 칸 이름 목록). 키는 KST 기준 naive datetime — SQL `date_trunc(… AT TIME ZONE)` 결과와 맞댄다."""
    from datetime import timedelta  # noqa: PLC0415

    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == "hour":
        keys = [day0 + timedelta(hours=h) for h in range(now.hour + 1)]
        labels = [f"{k.hour:02d}시" for k in keys]
    elif unit == "day":
        keys = [day0 - timedelta(days=i) for i in range(count - 1, -1, -1)]
        labels = [k.strftime("%m.%d") for k in keys]
    elif unit == "week":
        monday = day0 - timedelta(days=day0.weekday())
        keys = [monday - timedelta(weeks=i) for i in range(count - 1, -1, -1)]
        labels = [k.strftime("%m.%d") + "~" for k in keys]
    else:
        first = day0.replace(day=1)
        keys = [_month_add(first, -i) for i in range(count - 1, -1, -1)]
        labels = [f"{k.month}월" for k in keys]
    return keys[0], [k.replace(tzinfo=None) for k in keys], labels


def _series(keys: list, rows: list[dict]) -> list[int]:
    got = {r["b"].replace(tzinfo=None): r["n"] for r in rows}
    return [got.get(k, 0) for k in keys]


def _bucket_sql(table: str, col: str) -> str:
    return (
        f"SELECT date_trunc(%s, {col} AT TIME ZONE 'Asia/Seoul') AS b, count(*) AS n "  # noqa: S608 — 고정 조각만
        f"FROM {table} WHERE {col} >= %s GROUP BY 1"
    )


#: 회원 추이 — 기간별 (칸 단위, 칸 수)
_MEMBER_AXIS = {"daily": ("day", 7), "weekly": ("week", 8), "monthly": ("month", 6)}
_MEMBER_AXIS_LABEL = {"daily": "최근 7일", "weekly": "최근 8주", "monthly": "최근 6개월"}


def _load_members(period: str) -> dict:
    from app.routers import admin_dbread as db  # noqa: PLC0415
    from app.routers.admin_members import DORMANT_DAYS  # noqa: PLC0415

    unit, count = _MEMBER_AXIS[period]
    start, keys, labels = _axis(unit, count, datetime.now(db.KST))
    source, out = db.run(
        [
            (
                "SELECT count(*) FILTER (WHERE disabled_at IS NULL) AS live, "
                "count(*) FILTER (WHERE disabled_at IS NULL AND coalesce(last_login_at, created_at) "
                "< now() - make_interval(days => %s)) AS dormant, "
                "count(*) FILTER (WHERE disabled_at IS NOT NULL) AS disabled, "
                "count(*) FILTER (WHERE disabled_at IS NULL AND email_verified_at IS NOT NULL) AS verified, "
                "count(*) FILTER (WHERE disabled_at IS NULL AND consent_history_at IS NOT NULL) AS history, "
                "count(*) FILTER (WHERE disabled_at IS NULL AND consent_improve_at IS NOT NULL) AS improve, "
                "count(*) FILTER (WHERE disabled_at IS NULL AND coalesce(org, '') <> '') AS with_org, "
                "max(created_at) AS last_join FROM user_account",
                [DORMANT_DAYS],
            ),
            (_bucket_sql("user_account", "created_at"), [_UNIT_SQL[unit], start]),
            (_bucket_sql("user_account", "disabled_at"), [_UNIT_SQL[unit], start]),
        ],
        what="stats.members",
    )
    if source != "db":
        return {"source": source}
    k = out[0][0]
    live = k["live"]

    def share(n: int) -> float:
        return round(n * 100 / live, 1) if live else 0.0

    joins, leaves = _series(keys, out[1]), _series(keys, out[2])
    return {
        "source": source,
        "kpi": {
            "live": live,
            "active": live - k["dormant"],
            "dormant": k["dormant"],
            "disabled": k["disabled"],
            "last_join": db.fmt_dt(k["last_join"]) if k["last_join"] else "가입 기록 없음",
        },
        "consents": [
            {"label": label, "n": k[key], "pct": share(k[key])}
            for label, key in (
                ("검수 이력 보관 동의", "history"),
                ("서비스 개선 활용 동의", "improve"),
                ("이메일 인증 완료", "verified"),
                ("소속 기재", "with_org"),
            )
        ],
        "trend": [
            {"label": lb, "join": j, "leave": lv}
            for lb, j, lv in zip(labels, joins, leaves, strict=True)
        ],
        "trend_scope": _MEMBER_AXIS_LABEL[period],
        "dormant_days": DORMANT_DAYS,
    }


@router.get("/member", response_class=HTMLResponse)
def member_stats(request: Request) -> HTMLResponse:
    """이용자 통계 — `user_account` 에서 센다. 회원 유형 · 요금제 칸은 표에 없어 그리지 않는다."""
    actor = require_governor(request)
    period = _clean_period(request.query_params.get("period"))
    return templates.TemplateResponse(
        request,
        "admin/stats/member.html",
        {
            "actor": actor,
            "period": period,
            "periods": _PERIODS,
            "period_label": _PERIOD_LABEL,
            **_load_members(period),
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


#: 판정 상태 — 「확정」을 위반 / 무위반으로 가른다(`violation_type` 유무). 🚨 미판정은 통과가 아니다 (D-127)
_VERDICT_SPLIT_SQL = (
    "CASE WHEN verdict = 'confirmed' AND violation_type IS NOT NULL THEN 'confirmed_viol' "
    "WHEN verdict = 'confirmed' THEN 'confirmed_pass' ELSE verdict END"
)
_VERDICT_SPLIT_LABEL = {
    "confirmed_viol": "확정 위반",
    "confirmed_pass": "확정 무위반",
    "hold": "보류",
    "no_basis": "근거 없음",
    "unjudged": "미판정 (오류 · 시간 초과)",
}
_CATEGORY_SOURCE_LABEL = {
    "classified": "자동 판별",
    "user_selected": "사용자가 고름",
    "none": "품목 미확정",
}
#: 위험도 하한 — 사전(`risk_floor`) vs 인코더(`risk_encoder` · D-348 보충 2)
_RISK_SOURCE_SQL = (
    "CASE WHEN risk_encoder IS NULL THEN 'dict_only' "
    "WHEN risk_encoder > coalesce(risk_floor, 0) THEN 'enc_up' ELSE 'enc_same' END"
)
_RISK_SOURCE_LABEL = {
    "dict_only": "사전 하한만",
    "enc_up": "인코더가 위험도를 올림",
    "enc_same": "인코더 하한 ≤ 사전 하한",
}


def _load_judge(days: int) -> dict:
    from app.routers import admin_dbread as db  # noqa: PLC0415

    where = "WHERE judged_at >= now() - make_interval(days => %s)" if days else ""
    p: list[object] = [days] if days else []
    trend_days = min(days or _TREND_MAX_DAYS, _TREND_MAX_DAYS)
    group = "SELECT {k} AS k, count(*) AS n FROM judgment {w} {extra} GROUP BY 1 ORDER BY 2 DESC"
    source, out = db.run(
        [
            (
                "SELECT count(*) AS n, count(DISTINCT doc_id) AS docs, "
                "count(*) FILTER (WHERE verdict = 'unjudged') AS unjudged, "
                "count(*) FILTER (WHERE verdict = 'no_basis') AS no_basis, "
                "count(*) FILTER (WHERE verdict = 'confirmed' AND violation_type IS NOT NULL) AS viol, "
                "min(judged_at) AS first_at, max(judged_at) AS last_at "
                f"FROM judgment {where}",
                p,
            ),
            (group.format(k=_VERDICT_SPLIT_SQL, w=where, extra=""), p),
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
            (group.format(k="coalesce(product_category_source, 'none')", w=where, extra=""), p),
            (group.format(k="judged_by", w=where, extra="") + " LIMIT 10", p),
            (
                group.format(
                    k=_RISK_SOURCE_SQL,
                    w=where or "WHERE TRUE",
                    extra="AND (risk_floor IS NOT NULL OR risk_encoder IS NOT NULL)",
                ),
                p,
            ),
        ],
        what="stats.judge",
    )
    if source != "db":
        return {"source": source}
    from app.routers.user import _HOLD_LABELS  # noqa: PLC0415

    k = out[0][0]
    trend = [{"label": db.fmt_dt(r["d"], "%m.%d"), "n": r["n"]} for r in out[6]]
    return {
        "source": source,
        "kpi": {
            "sentences": k["n"],
            "docs": k["docs"],
            "viol": k["viol"],
            "unjudged": k["unjudged"],
            "no_basis": k["no_basis"],
            "first_at": db.fmt_dt(k["first_at"], "%Y.%m.%d"),
            "last_at": db.fmt_dt(k["last_at"]),
        },
        "by_verdict": _bars(out[1], lambda v: _VERDICT_SPLIT_LABEL.get(v, v)),
        "by_hold": _bars(out[2], lambda v: _HOLD_LABELS.get(v, v or "사유 없음")),
        "by_category": _bars(out[3]),
        "by_risk": _bars(
            sorted(out[4], key=lambda r: r["k"]), lambda v: _RISK_LABEL.get(v, f"R{v}")
        ),
        "by_type": _bars(out[5], lambda v: str(v).replace("_", " ")),
        "by_source": _bars(out[7], lambda v: _CATEGORY_SOURCE_LABEL.get(v, v)),
        "by_version": _bars(out[8]),
        "by_risk_source": _bars(out[9], lambda v: _RISK_SOURCE_LABEL.get(v, v)),
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
# 🔄 2026-10-20 — 생성 통계는 **셀 수 있는 것만** 그린다 (D-147).
#    🚨 생성 결과도 생성 요청도 저장하지 않는다 — `copy_sentence` 의 `generated` 는 늘 0 이라 지웠다(종전 KPI · 추이 · 출처 분포).
#    ★ 그리는 것 ① 엔진 상태 — `copygen.off_reason()`(스위치 · 키 · 판정 인코더) 를 그대로
#               ② 생성 실패 — 생성 처리부(`user.py` `generate`)가 남기는 WARNING `카피 생성 실패` 를 `app_error_log` 에서 센다.
#                  예외는 **클래스 이름만** 저장된다(`app/error_log.py` `to_row`) — 사용자 입력은 없다 (D-76).
#                  🔴 오류 로그를 DB 에 쌓지 않는 환경(`settings.error_log_enabled()` 거짓 — local 등)에서는 0 이 아니라 「기록 안 함」
#                  ⚠️ 보관은 `ERROR_LOG_RETENTION_DAYS` 일 — 「전체」도 그만큼이다
#               ③ 집계를 열려면 필요한 결정 (D-96 · D-129 · D-307)
#    ⛔ 성공 건수 · 성공률은 그리지 않는다 — 분모(요청 수)가 없다.
# ─────────────────────────────────────────────────────────────

#: 생성 실패 로그의 자리 — `app/routers/user.py` 의 `logging.getLogger(__name__).warning("카피 생성 실패", …)`.
#: 🚨 글자가 바뀌면 0 건으로 보인다 — `tests/test_admin_dbread_screens.py` 가 user.py 소스와 맞댄다.
GEN_FAIL_LOGGER = "app.routers.user"
GEN_FAIL_MESSAGE = "카피 생성 실패"

_GEN_NEEDS = [
    (
        "생성 요청 수 · 성공률",
        "원문 없이 건수만 남기는 기록 표 — 스키마 판정 (팀장 · D-129 보관 기한)",
    ),
    ("생성 문구 · 승인 · 검수로 넘긴 수", "생성 결과 저장과 동의 범위 (D-96 · D-307)"),
    ("품목 · 분기별 생성 분포", "위 기록 표에 품목 칸 (D-263)"),
]


def _engine_state() -> dict:
    """생성 엔진을 지금 쓸 수 있는가 — 생성 화면이 보는 것과 같은 판단(`copygen.off_reason`) (D-99)."""
    try:
        from app.routers import copygen  # noqa: PLC0415

        why = copygen.off_reason()
    except Exception as e:  # noqa: BLE001 — 상태 화면이 생성 모듈 오류로 죽지 않게
        return {"on": False, "why": f"엔진 상태를 확인하지 못했어요 ({type(e).__name__})"}
    return {"on": why is None, "why": why}


def _load_generation(days: int) -> dict:
    from app.routers import admin_dbread as db  # noqa: PLC0415
    from app.settings import ERROR_LOG_RETENTION_DAYS, error_log_enabled  # noqa: PLC0415

    base = {
        "engine": _engine_state(),
        "needs": _GEN_NEEDS,
        "retention_days": ERROR_LOG_RETENTION_DAYS,
        "log_on": error_log_enabled(),
    }
    span = days or ERROR_LOG_RETENTION_DAYS
    trend_days = min(span, _TREND_MAX_DAYS)
    cond = "logger_name = %s AND message = %s AND occurred_at >= now() - make_interval(days => %s)"
    p: list[object] = [GEN_FAIL_LOGGER, GEN_FAIL_MESSAGE, span]
    source, out = db.run(
        [
            (
                f"SELECT count(*) AS n, max(occurred_at) AS last_at FROM app_error_log WHERE {cond}",
                p,
            ),  # noqa: S608
            (
                "SELECT coalesce(exc_type, '알 수 없음') AS k, count(*) AS n FROM app_error_log "  # noqa: S608
                f"WHERE {cond} GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
                p,
            ),
            (
                "SELECT (occurred_at AT TIME ZONE 'Asia/Seoul')::date AS d, count(*) AS n FROM app_error_log "  # noqa: S608
                f"WHERE {cond} GROUP BY 1 ORDER BY 1",
                [GEN_FAIL_LOGGER, GEN_FAIL_MESSAGE, trend_days],
            ),
        ],
        what="stats.generation",
    )
    if source != "db":
        return {**base, "source": source}
    k = out[0][0]
    trend = [{"label": db.fmt_dt(r["d"], "%m.%d"), "n": r["n"]} for r in out[2]]
    return {
        **base,
        "source": source,
        "fail": {"n": k["n"], "last_at": db.fmt_dt(k["last_at"]) if k["last_at"] else "없음"},
        "by_exc": _bars(out[1]),
        "trend": trend,
        "trend_max": max((r["n"] for r in trend), default=0),
        "trend_days": trend_days,
        "span_days": span,
    }


@router.get("/quality/generation", response_class=HTMLResponse)
def generation_stats(request: Request) -> HTMLResponse:
    """생성 통계 — 엔진 상태 · 생성 실패(`app_error_log`) · 집계를 열 조건. 기간: 최근 7 · 30 · 90일 · 전체(= 로그 보관 기간)."""
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
# 🔄 2026-10-20 — 대시보드(통계 · 운영 `/admin/` 둘 다)의 검수 이용은 **`judgment` 를 센다** — 매출은 닫힘 라벨만.
#    ★ 검수 요청 = 판정이 담긴 작업 문서 수(`doc_id`) · 문장 = 판정 행 수. 이력 보관 동의분만 저장된다 (D-96).
#    🔴 생성은 저장 경로가 없다 — 0 건을 「안 썼다」로 읽히게 그리지 않고 「저장하지 않아요」로 적는다 (D-147).
#    기간 — 일간: 오늘 0시부터 · 시간대별 (비교: 어제 같은 시각까지)
#           주간: 최근 7일 · 일별 (비교: 그 전 7일)
#           월간: 이번 달 1일부터 (비교: 지난달 같은 날수까지) · 추이는 최근 6개월 월별
# ─────────────────────────────────────────────────────────────

_USAGE = {
    "daily": {"title": "오늘 시간대별 검수", "axis": ("hour", 24), "vs": "어제 같은 시각까지"},
    "weekly": {"title": "최근 7일 일별 검수", "axis": ("day", 7), "vs": "그 전 7일"},
    "monthly": {"title": "최근 6개월 월별 검수", "axis": ("month", 6), "vs": "지난달 같은 기간"},
}
_GEN_NOTE = "생성 결과는 저장하지 않아요"


def _usage_windows(period: str, now):  # noqa: ANN001, ANN202
    """(이번 기간 시작, 비교 기간 시작, 비교 기간 끝)."""
    from datetime import timedelta  # noqa: PLC0415

    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "daily":
        return day0, day0 - timedelta(days=1), now - timedelta(days=1)
    if period == "weekly":
        start = day0 - timedelta(days=6)
        return start, start - timedelta(days=7), start
    start = day0.replace(day=1)
    prev = _month_add(start, -1)
    return start, prev, min(prev + (now - start), start)


def _load_usage(period: str) -> dict:
    """대시보드 이용 현황. 템플릿 키(`kpi` · `delta` · `labels` · `judge_series`)는 종전 예시와 같은 모양이다."""
    from app.routers import admin_dbread as db  # noqa: PLC0415

    conf = _USAGE[period]
    now = datetime.now(db.KST)
    cur, prev_from, prev_to = _usage_windows(period, now)
    unit, count = conf["axis"]
    chart_from, keys, labels = _axis(unit, count, now)
    window = (
        "SELECT count(DISTINCT doc_id) AS docs, count(*) AS n FROM judgment "
        "WHERE judged_at >= %s AND judged_at < %s"
    )
    source, out = db.run(
        [
            (window, [cur, now]),
            (window, [prev_from, prev_to]),
            (_bucket_sql("judgment", "judged_at"), [_UNIT_SQL[unit], chart_from]),
        ],
        what="stats.usage",
    )
    base = {"source": source, "trend_title": conf["title"], "labels": labels, "gen_note": _GEN_NOTE}
    if source != "db":
        return {
            **base,
            "kpi": {"judge": "-", "gen": "-", "sentences": None},
            "delta": {"judge": "기록을 읽지 못했어요", "gen": _GEN_NOTE},
            "judge_series": [],
            "max": 0,
        }
    now_k, prev_k = out[0][0], out[1][0]
    series = _series(keys, out[2])
    return {
        **base,
        "kpi": {"judge": f"{now_k['docs']:,}", "gen": "저장 안 함", "sentences": now_k["n"]},
        "delta": {"judge": f"{conf['vs']} {prev_k['docs']:,}건", "gen": _GEN_NOTE},
        "judge_series": series,
        "max": max(series, default=0),
    }


@router.get("/dashboard", response_class=HTMLResponse)
def stats_dashboard(request: Request) -> HTMLResponse:
    """통계 대시보드 — 검수 이용(`judgment`) · 생성은 저장 안 함 안내 · 매출 닫힘 라벨.
    `/admin/`(운영 대시보드)과는 별개 화면이다 — 같은 집계(`_load_usage`)를 쓴다 (D-99).
    """
    actor = require_governor(request)
    period = _clean_period(request.query_params.get("period"))
    d = _load_usage(period)
    return templates.TemplateResponse(
        request,
        "admin/stats/dashboard.html",
        {
            "actor": actor,
            "period": period,
            "periods": _PERIODS,
            "period_label": _PERIOD_LABEL,
            "dash": d,
            "dash_max": d["max"],
            "revenue_label": LABEL,
        },
    )
