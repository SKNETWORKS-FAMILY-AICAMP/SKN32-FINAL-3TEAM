"""app/routers/admin_terms.py — 문서관리(약관 버전) 화면 · 소유자 **psj** (병렬작업 계약 §5)

★ `admin.py` 와 파일을 가른다 (D-208 · admin_errors.py 와 같은 패턴). 붙이는 자리는
   `app/routers/__init__.py` 한 줄 — `admin_router` 아래에 매단다.

✅ **읽기 전용이다.** 이 파일에 POST 는 없다. "새 버전 등록" 은 `disabled` 뼈대다.
✅ `require_governor` 를 지나야 뜬다 — `admin.py` 와 같은 함수를 쓴다 (D-99 · 두 벌 금지).

🔄 2026-10-20 — **`terms` 표를 읽는다** (alembic `0017_ops_tables` · `app/models.py` `Terms` · D-260 ①).
   가입 화면이 동의 버전을 읽는 것과 같은 표다. 종전 더미(목업 terms 뷰 — SLA · 기업 계약서)는 지웠다.
   ★ 못 읽으면 빈 화면 + 안내다 — 0건이라 말하지 않는다 (`admin_dbread` · D-72).
   🚨 종류 이름은 `app/models.py` `TERMS_KINDS` 한 벌이다 (D-99).
   🚨 상태 · 이전 버전은 저장하지 않는다(`Terms` docstring) — 같은 종류의 시행일 순서에서 계산한다:
      시행일이 오늘 이후 = 예정 · 오늘 이전 중 가장 늦은 것 = 시행 중 · 그보다 앞선 것 = 지난 버전.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.models import TERMS_KINDS
from app.routers import admin_dbread as db
from app.routers.admin import require_governor
from app.templating import templates

#: 🚨 prefix 는 `/terms` 다 — `admin_router`(prefix `/admin`) 아래에 매달려
#:    `/admin/terms`, `/admin/terms/{term_id}` 가 된다.
router = APIRouter(prefix="/terms")

#: 버전이 아주 많아질 일은 없다 — 화면 상한만 둔다
_LIMIT = 500

_SELECT = """
SELECT t.id::text AS id, t.kind, t.version, t.effective_on, t.body, t.change_reason,
       t.created_at, a.display_name AS created_by
FROM terms t
LEFT JOIN app_account a ON a.id = t.created_by
"""


def _views(rows: list[dict]) -> list[dict]:
    """같은 종류끼리 시행일 순으로 세워 상태 · 이전 버전을 계산한다. 결과는 종류 순 · 최신 시행일 먼저."""
    today = db.today_kst()
    by_kind: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: (r["kind"], r["effective_on"], r["created_at"])):
        by_kind.setdefault(r["kind"], []).append(r)
    out: list[dict] = []
    for kind in sorted(
        by_kind, key=lambda k: list(TERMS_KINDS).index(k) if k in TERMS_KINDS else 99
    ):
        seq = by_kind[kind]
        current = max((i for i, r in enumerate(seq) if r["effective_on"] <= today), default=None)
        views = []
        for i, r in enumerate(seq):
            if r["effective_on"] > today:
                status = "예정"
            elif i == current:
                status = "시행 중"
            else:
                status = "지난 버전"
            views.append(
                {
                    "id": r["id"],
                    "kind": kind,
                    "name": TERMS_KINDS.get(kind, kind),
                    "version": r["version"],
                    "effective_date": db.fmt_dt(r["effective_on"], "%Y.%m.%d"),
                    "prev_version": seq[i - 1]["version"] if i > 0 else "-",
                    "reason": r["change_reason"],
                    "status": status,
                    "body": r["body"],
                    "created_by": r["created_by"] or "-",
                    "created_at": db.fmt_dt(r["created_at"]),
                }
            )
        out.extend(reversed(views))
    return out


@router.get("", response_class=HTMLResponse)
def terms_list(request: Request) -> HTMLResponse:
    """약관 버전 목록 — 읽기 전용. 종류별로 최신 시행일 먼저."""
    actor = require_governor(request)
    source, out = db.run([(f"{_SELECT} LIMIT %s", [_LIMIT])], what="terms.list")  # noqa: S608
    rows = _views(out[0]) if source == "db" else []
    return templates.TemplateResponse(
        request,
        "admin/docs/terms_list.html",
        {"actor": actor, "source": source, "rows": rows},
    )


@router.get("/{term_id}", response_class=HTMLResponse)
def terms_detail(request: Request, term_id: str) -> HTMLResponse:
    """약관 버전 상세 — 본문 + 같은 종류의 버전 이력. 읽기 전용."""
    actor = require_governor(request)
    source, out = db.run(
        [
            (
                f"{_SELECT} WHERE t.kind = (SELECT kind FROM terms WHERE id::text = %s) LIMIT %s",  # noqa: S608
                [term_id[:64], _LIMIT],
            )
        ],
        what="terms.detail",
    )
    history = _views(out[0]) if source == "db" else []
    row = next((v for v in history if v["id"] == term_id), None)
    if source == "db" and row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/docs/terms_detail.html",
        {"actor": actor, "source": source, "row": row, "history": history},
    )
