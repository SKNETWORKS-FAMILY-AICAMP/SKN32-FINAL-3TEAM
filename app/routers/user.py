"""app/routers/user.py — 사용자 화면 + BFF · 소유자 **ksr · lse** (D-208 · 병렬작업 계약 §5).

★ **여기서 하는 일** — 화면을 그리고, 코어(`/judge`·`/search`)나 픽스처를 불러 화면 모양으로
  바꾼다. ⛔ **판정 로직을 여기 쓰지 않는다** (D-119 — 판정 코어는 하나).

🚨 **엔진이 필요한 화면은 DB 없이도 떠야 한다** (D-124) — `review`·`generate`·`compose` 는
   골든 픽스처로 모든 분기를 그린다. ⬜ **`history`·`/`(홈) 은 예외다** — 실제 DB(`app/db.py`,
   `Judgment`)에 붙는다. 🔄 판정은 돌지만(코어 `/judge`) 결과를 `judgment` 표에 **저장하는 코드가 아직 없어**
   지금은 빈 목록/0 건으로 뜬다.
   🔄 2026-09-22 (ohb 흡수) — **DB 가 없어도 뜬다.** 붙지 못하면 「DB 없음」을 그리고 수를 0 으로 적지 않는다
      (`app.db.reachable` · D-72). 게이트가 `/u/` 200 을 요구하고 CI 에는 Postgres 가 없다.

🔄 2026-09-16 — ksr(`skn32/ksr`, 2026-09-13~14)와 lse 가 독립적으로 만든 사용자 화면
   구현을 합쳤다 (`docs/lse/ksr_lse_화면중복_비교_2026-09-16.md` 참고). `review`·`generate`·
   `compose`(구 draft-setup/editor)·`mypage`·`landing` 은 ksr 것을 이식했고, `history` 는
   ksr 의 원문 조인 + lse 의 필터·페이지네이션·상세 토글을 합쳤다. nav 구조(4-pill+사이드바)는
   두 사람이 독립적으로 같은 결론에 도달해, 이미 테스트가 붙은 lse `_render()` 를 베이스로 뒀다.

⛔ **`Form(...)` 도 `request.form()` 도 안 쓴다** — 둘 다 `python-multipart` 를 요구하고
   그것은 **새 의존성**이다. `uv.lock` 은 팀장 단독이다 (D-87 · §5). 본문을 직접 판다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import auth, reasons, sentsplit
from app import premise as pm
from app.contracts import (
    PASS_RISK_MAX,
    Category,
    HoldReason,
    Premise,
    Risk,
    Verdict,
    Violation,
    is_pass,
)
from app.db import get_session, reachable
from app.formbody import read_capped
from app.models import (
    NOTICE_CATEGORIES,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    CopySentence,
    Judgment,
    Notice,
    Terms,
    Ticket,
    UserAccount,
    WorkDoc,
)
from app.settings import PARAMS, TICKET_RETENTION_DAYS, TICKET_TEXT_MAX
from app.templating import templates

router = APIRouter(prefix="/u", tags=["user"])

#: 🚨 본문 상한 — 없으면 무제한이다 (보안점검 P2-11).
#:    ⛔ 한글은 퍼센트 인코딩으로 **글자당 9바이트**다. 여유를 좁게 잡으면 길이 초과가
#:       413(본문)으로 먼저 걸려 「문구가 너무 길다」라는 **정확한 이유가 안 나온다.**
_MAX_BODY = PARAMS.max_text_len * 16

#: 🔴 픽스처 이름 **화이트리스트**. `app/api.py` 가 밟은 경로 순회와 같은 이유다 —
#:    이름을 경로로 쓰기 전에 모양을 고정한다.
_FIXTURE_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

# ══════════════════════════════════════════════════════════════════════
#  상단 nav — 구역 넷 + 사이드바 (2026-09-16, 발표자료 v7.2 SECTIONS 를 서버 렌더로)
# ══════════════════════════════════════════════════════════════════════
#: 🚨 **경로 → 구역.** 여기 없는 경로(홈·마이페이지·고객센터·랜딩)는 구역이 없다 —
#:    상단 pill 이 안 켜지고 사이드바도 안 뜬다. 디자인의 `SCREEN_SECTION` 그대로다.
_SCREEN_SECTION: dict[str, str] = {
    "/u/review": "work",
    "/u/generate": "work",
    "/u/segments": "work",
    "/u/history": "work",
    "/u/compose": "adgen",
    "/u/help": "about",
    "/u/matching": "matching",
}

_SECTION_LABELS: dict[str, str] = {
    "about": "copylane 소개",
    "work": "검수 및 카피생성",
    "adgen": "AI 광고 생성",
    "matching": "매칭",
}

#: 🔴 구역별 사이드바 항목 (key, label, href). **matching 은 없다** — 하위 화면 넷이
#:    홀딩이라 있지도 않은 화면에 링크를 걸지 않는다 (2026-09-16 판단).
_SECTION_SUBS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "work": (
        ("review", "검수", "/u/review"),
        ("gen", "카피생성", "/u/generate"),
        ("history", "이력", "/u/history"),
    ),
    "about": (
        ("guide", "사용방법", "/u/help?tab=guide"),
        ("faq", "자주 묻는 질문", "/u/help?tab=faq"),
    ),
    "adgen": (("make", "광고 만들기", "/u/compose"),),
}

#: 경로 → 사이드바 활성 항목 key. `/u/help` 는 tab 쿼리로 갈리니 라우터에서 직접 넘긴다.
_SECTION_ACTIVE_SUB: dict[str, str] = {
    "/u/review": "review",
    "/u/generate": "gen",
    "/u/segments": "gen",
    "/u/history": "history",
    "/u/compose": "make",
}


#: 🔴 **결과 경로 → 그 화면의 입력 경로.** 검수 버튼(`POST /u/judge`)이나 픽스처 미리보기는
#:    경로가 입력 화면과 달라서, 이게 없으면 구역을 못 찾아 **사이드바가 사라진다**
#:    (2026-09-17 발견). 결과는 입력 화면과 같은 구역·같은 사이드바 항목에 속한다.
_SCREEN_ALIAS: tuple[tuple[str, str], ...] = (
    ("/u/judge", "/u/review"),
    ("/u/preview/", "/u/review"),
    ("/u/generate/preview/", "/u/generate"),
    ("/u/review/rewrite", "/u/review"),  # 지적 문장 고쳐 쓰기 결과는 검수 화면에 그린다 (lse 10-06)
    ("/u/compose/preview/", "/u/compose"),
)


def _screen_path(path: str) -> str:
    for prefix, target in _SCREEN_ALIAS:
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            return target
    return path


def _render(
    request: Request, template: str, ctx: dict | None = None, *, active_sub: str | None = None
) -> HTMLResponse:
    """모든 사용자 화면이 여기를 거친다 — 구역·사이드바 계산을 **한 곳에만** 둔다.

    ⛔ 화면마다 `active_section` 을 손으로 채우면, 화면이 늘 때마다 빠뜨리는 자리가
       생긴다 (D-147 의 정신과 같다 — 계산이 갈리면 둘 다 못 믿는다).
    """
    ctx = dict(ctx or {})
    # 🆕 2026-09-29 — 상단바는 **로그인한 사람의 실제 정보**로 그린다(이름 · 소속 · 이니셜). 테마는 쿠키 하나.
    ctx.setdefault("me", _nav_user(request))
    ctx.setdefault("theme", _theme(request))
    ctx.setdefault("here", request.url.path)
    ctx.setdefault("today", _today_label())
    path = _screen_path(request.url.path)
    section = _SCREEN_SECTION.get(path)
    ctx.setdefault("active_section", section)
    ctx.setdefault("section_label", _SECTION_LABELS.get(section) if section else None)
    ctx.setdefault("section_subs", _SECTION_SUBS.get(section) if section else None)
    ctx.setdefault(
        "active_sub", active_sub if active_sub is not None else _SECTION_ACTIVE_SUB.get(path)
    )
    return templates.TemplateResponse(request, template, ctx)


#: 테마 쿠키 — 🚨 값은 둘뿐이다. 없으면 운영체제 설정(`prefers-color-scheme`)을 따른다.
_THEME_COOKIE = "copylane_theme"
_THEMES = ("light", "dark")


#: 한국 시간 — 🚨 `zoneinfo` 는 Windows 에서 `tzdata` 패키지를 요구한다(새 의존성 · §5). 서머타임이 없어 고정 +9 로 충분하다.
_KST = timezone(timedelta(hours=9))
_WEEKDAYS = "월화수목금토일"


def _today_label() -> str:
    """홈 오른쪽 날짜 — 프로토타입 `today-date` 모양(「2026.09.29 (화)」)."""
    now = datetime.now(_KST)
    return f"{now:%Y.%m.%d} ({_WEEKDAYS[now.weekday()]})"


def _theme(request: Request) -> str | None:
    value = request.cookies.get(_THEME_COOKIE)
    return value if value in _THEMES else None


def _nav_user(request: Request) -> SimpleNamespace | None:
    """상단바에 그릴 로그인 사용자 — 이름 · 소속 · 이니셜(아바타). 로그아웃이면 `None`.

    🚨 사용자 쿠키가 **있을 때만** DB 를 연다 — 로그아웃 화면은 DB 없이 뜬다(게이트 `/u/` 200 · D-124).
    ★ 판별은 `current_user` 한 곳(서명 · 만료 · 꺼진 계정 · DB 없음) — 여기서 따로 판단하지 않는다 (D-99).
    """
    if not request.cookies.get(auth.USER_SESSION_COOKIE):
        return None
    gen = get_session()
    session = next(gen)
    try:
        user = current_user(request, session)
        if user is None:
            return None
        notifs = _notifications(request, session, user)
        return SimpleNamespace(
            name=user.name,
            org=user.org,
            initials=user.name.strip()[:2],
            verified=user.email_verified_at is not None,
            notifs=notifs,
            unread=sum(1 for n in notifs if n.unread),
            cs_unread=any(n.unread and n.kind == "alert" for n in notifs),
        )
    finally:
        gen.close()


# ── 알림 · 공지사항 (프로토타입 v7.2 벨 팝업 · ksr 2026-09-29) ─────────────────────────
#: 🚨 **새 표 없이 계산한다** — 공지(`notice` 게시 중) + 내 문의 알림(`ticket` 답변 · 완료). 2026-09-29 권소라 결정.
#:    ⛔ 프로토타입의 재판정 완료 · 카피 생성 완료 · 팀원 공유 · 초안 임시저장 알림은 **없다** — 만들 데이터가 없다
#:       (엔진 없음 · 팀 없음 D-260 ④). 지어내지 않는다 (D-147).
#: 🚨 읽음은 **쿠키**에 둔다 — 기기마다 따로다. 공유하려면 알림 표가 필요하다(팀장 승인 요청 6번).
#:    - `copylane_notif_seen` = 「모두 읽음」 누른 시각(유닉스 초) → 그보다 뒤에 올라온 공지만 안 읽음
#:    - `copylane_seen_tk` = 읽은 문의 알림 `<id 앞 8자리><r|c>`(답변 · 완료) — 🚨 `ticket` 에 답변 시각 칸이 없어 시각으로 못 가른다
_NOTIF_SEEN_COOKIE = "copylane_notif_seen"
_SEEN_TK_COOKIE = "copylane_seen_tk"
_SEEN_TK_MAX = 60  # 쿠키 길이 상한 — 오래된 것부터 버린다
_NOTICE_MAX = 20


def _seen_keys(request: Request) -> list[str]:
    raw = request.cookies.get(_SEEN_TK_COOKIE, "")
    return [k for k in raw.split(".") if re.fullmatch(r"[0-9a-f]{8}[rc]", k)]


def _ticket_alert_key(t: Ticket) -> str | None:
    """문의 알림의 상태 열쇠 — 완료(c)가 답변(r)보다 앞선다. 알릴 것이 없으면 `None`."""
    if t.status == _CS_DONE:
        return f"{t.id.hex[:8]}c"
    if t.reply is not None:
        return f"{t.id.hex[:8]}r"
    return None


def _when(at: datetime | None) -> str:
    if at is None:
        return ""
    delta = datetime.now(UTC) - at
    if delta < timedelta(hours=1):
        return f"{max(1, int(delta.total_seconds() // 60))}분 전"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)}시간 전"
    return at.astimezone(_KST).strftime("%m.%d")


def _notifications(request: Request, session: Session, user: UserAccount) -> list[SimpleNamespace]:
    """벨 팝업에 그릴 항목 — 안 읽은 것이 위로. 🚨 공지는 **게시 중**인 것만(숨김 아님 · 게시 기간 안)."""
    try:
        seen_at = datetime.fromtimestamp(int(request.cookies.get(_NOTIF_SEEN_COOKIE, "0")), UTC)
    except (ValueError, OverflowError, OSError):
        seen_at = datetime.fromtimestamp(0, UTC)
    seen_tk = set(_seen_keys(request))
    today = datetime.now(_KST).date()
    items: list[SimpleNamespace] = []

    notices = (
        session.execute(
            select(Notice)
            .where(
                Notice.hidden_at.is_(None),
                (Notice.starts_on.is_(None)) | (Notice.starts_on <= today),
                (Notice.ends_on.is_(None)) | (Notice.ends_on >= today),
            )
            .order_by(Notice.pinned.desc(), Notice.created_at.desc())
            .limit(_NOTICE_MAX)
        )
        .scalars()
        .all()
    )
    for n in notices:
        posted = max(n.created_at, n.updated_at)
        items.append(
            SimpleNamespace(
                kind="notice",
                title=n.title,
                body=NOTICE_CATEGORIES.get(n.category, n.category)
                + (" · 고정" if n.pinned else ""),
                when=_when(posted),
                unread=posted > seen_at,
                href=None,
            )
        )

    tickets = session.execute(
        select(Ticket).where(
            Ticket.requester_id == user.id,
            (Ticket.reply.is_not(None)) | (Ticket.status == _CS_DONE),
        )
    ).scalars()
    for t in tickets:
        key = _ticket_alert_key(t)
        if key is None:
            continue
        done = key.endswith("c")
        items.append(
            SimpleNamespace(
                kind="alert",
                title="문의가 완료됐어요" if done else "문의에 답변이 달렸어요",
                body=t.title,
                # 🚨 답변 시각 칸이 없다 — 완료는 완료 시각, 답변은 접수 시각으로 적는다(승인 요청)
                when=_when(t.closed_at if done else t.created_at),
                unread=key not in seen_tk,
                href=f"/u/cs/{t.id}",
                key=key,
            )
        )
    items.sort(key=lambda i: not i.unread)
    return items


def _remember_seen(
    resp: HTMLResponse | RedirectResponse, request: Request, keys: list[str]
) -> None:
    """읽은 문의 알림 열쇠를 쿠키에 더한다(오래된 것부터 버린다)."""
    merged = [k for k in _seen_keys(request) if k not in keys] + keys
    resp.set_cookie(
        _SEEN_TK_COOKIE,
        ".".join(merged[-_SEEN_TK_MAX:]),
        max_age=365 * 24 * 3600,
        **_cookie_kwargs(request),  # type: ignore[arg-type]
    )


async def _form(request: Request) -> dict[str, list[str]]:
    """`application/x-www-form-urlencoded` 본문을 표준 라이브러리로 판다.

    ★ HTML 폼은 `enctype` 없이 보내면 이 형식이고, `urllib.parse.parse_qs` 로 끝난다.
      필드가 여럿이어도 마찬가지다 — `python-multipart` 가 필요한 것은
      **파일 업로드(`multipart/form-data`)** 뿐이다.
    ⬜ 업로드를 붙일 때는 lock 을 만지는 판정이다 (§5). 그 판정 전까지 만들지 않는다.
    """
    # 🔄 09-21 — 다 읽고 재지 않는다. 넘는 순간 멈춘다 (app/formbody.py · P2-11)
    body = await read_capped(
        request, _MAX_BODY, f"본문이 너무 크다 — {_MAX_BODY} 바이트까지 받는다"
    )
    return parse_qs(body.decode("utf-8", "replace"))


def _one(form: dict[str, list[str]], name: str, limit: int) -> str:
    """필드 하나. ⛔ 상한을 **자르지 않고 거부한다** — 자르면 사용자는 잘린 줄 모른다 (D-220)."""
    value = form.get(name, [""])[0]
    if len(value) > limit:
        raise HTTPException(422, f"{name} 이 너무 길다 — {limit}자까지 받는다")
    return value


def _fixture_names(kind: str) -> list[str]:
    from app.api import FIXTURE_ROOT  # noqa: PLC0415 — 순환 import 를 피한다

    return sorted(p.stem for p in (FIXTURE_ROOT / kind).glob("*.json"))


def _fixture_path(kind: str, name: str):  # noqa: ANN201
    from app.api import FIXTURE_ROOT  # noqa: PLC0415

    if not _FIXTURE_NAME.match(name):
        raise HTTPException(404, "그런 픽스처가 없다")
    path = FIXTURE_ROOT / kind / f"{name}.json"
    if not path.is_file():
        raise HTTPException(404, "그런 픽스처가 없다")
    return path


# ══════════════════════════════════════════════════════════════════════
#  홈 — 구역 밖, 진짜 DB 집계
# ══════════════════════════════════════════════════════════════════════


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:  # noqa: B008
    """사용자 첫 화면 = 홈. 🚨 **history 와 같은 요령으로 진짜 DB 집계다.**

    🔄 종전에는 여기가 문구 검수였다 — 검수는 `/u/review` 로 옮겼다 (2026-09-16, ksr 안).
    ⬜ 판정 엔진이 없어 지금은 통계가 0/— 로 뜬다 — 정상이다 (D-147, 가짜 수치를 안 그린다).
    ★ "위법 소지 발견"·"재검수 통과율"은 `app.contracts.PASS_RISK_MAX`
      (D-125 통과 조건의 위험도 문턱 = 🔄 **R0** · D-273)을 그대로 쓴다 — 문턱을 여기서 따로 두지 않는다.
    """
    if not reachable(session):
        # 🚨 수를 **None** 으로 넘긴다 — 템플릿이 0건이 아니라 「—」와 안내를 그린다 (D-72).
        return _render(
            request,
            "user/index.html",
            {
                "db_down": True,
                "total_month": None,
                "violation_count": None,
                "pass_rate": None,
                "recent": [],
            },
        )
    # 🔴 2026-09-29 — 통계·최근 이력은 **내 판정만** 센다 (P1-5 · `_owned_judgments`). 로그아웃이면 셀 대상이 없다.
    user = current_user(request, session)
    if user is None:
        # 🔄 2026-10-14 (lse · 사용자 요청) — 로그인 전에 들어오면 **랜딩이 첫 화면**이다. 홈(통계)은 로그인한 사람의 것이다.
        #    🚨 넘기지(303) 않고 이 주소에서 랜딩을 그린다 — 로그인 벽이 아니다(D-66 · 200 · 로그인 안내 · 「이력에 남지 않아요」 D-69).
        #    「copylane 소개」 메뉴는 랜딩이 아니라 사용방법으로 간다(종전대로). DB 가 없을 때는 위에서 홈의 안내를 그린다
        return templates.TemplateResponse(request, "user/landing.html", {})
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mine = _owned_judgments(user.id)
    month = mine.where(Judgment.judged_at >= month_start)
    pass_level = PASS_RISK_MAX.level

    total_month = session.scalar(select(func.count()).select_from(month.subquery())) or 0
    violation_count = (
        session.scalar(
            select(func.count()).select_from(
                month.where(
                    Judgment.verdict == "confirmed", Judgment.risk_final > pass_level
                ).subquery()
            )
        )
        or 0
    )
    pass_count = (
        session.scalar(
            select(func.count()).select_from(
                month.where(
                    Judgment.verdict == "confirmed", Judgment.risk_final <= pass_level
                ).subquery()
            )
        )
        or 0
    )
    pass_rate = round(pass_count / total_month * 100) if total_month else None

    recent = session.execute(mine.order_by(Judgment.judged_at.desc()).limit(3)).scalars().all()
    return _render(
        request,
        "user/index.html",
        {
            "total_month": total_month,
            "violation_count": violation_count,
            "pass_rate": pass_rate,
            "recent": recent,
        },
    )


@router.get("/landing", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    """랜딩 — 로그인 전 첫 화면 (ksr, 2026-09-13).

    🚨 nav 를 넣지 않는다 — 로그인 전이라 사용자 메뉴가 없다.
    ⛔ 프로토타입의 사용량 수치(「240개 팀 · 12,000건」)는 **지어낸 값**이라 옮기지 않았다 (D-147).
    🔄 2026-09-16 — `/login`(governor 전용) 대신 오늘 생긴 `/u/login`·`/u/signup` 으로 잇는다.
    """
    return templates.TemplateResponse(request, "user/landing.html", {})


# ══════════════════════════════════════════════════════════════════════
#  A · 문구 검수 (SCR-A)
# ══════════════════════════════════════════════════════════════════════


#: 한 번에 검수하는 문구 수 상한 — 프로토타입 v7.2 `addReviewCopy` 의 5건 그대로 (ksr 2026-09-29).
_MAX_COPIES = 5

#: 품목 분기를 고른 뒤 「다시 선택」할 수 있는 횟수 (팀장 2026-10-01). 화면이 회차만큼 미리 그려 두고 넘긴다.
#: 🔄 2026-10-06 — 3 → 5. 분기별 판정 결과를 바꿔 보는 횟수다 — 엔진을 다시 돌리지 않는다.
_MAX_REDO = 5

#: 「예시 넣기」 문구 — 프로토타입 `SAMPLE_COPY` 그대로. 🚨 실제 광고 인용이 아니라 화면용 예시다.
_SAMPLE_COPY = (
    "이 영양제는 매일 섭취 시 눈 피로 회복에 탁월한 효과가 있습니다. "
    "간편하게 하루 한 알로 건강을 챙기세요. 누적 판매 10만 개, 후기 평점 4.9점의 인기 제품입니다."
)

#: 🔴 버튼 하나 = 폼 제출 하나 (`op`). CSP 가 스크립트를 막아 문구 추가·삭제도 서버가 다시 그린다.
_OP = re.compile(r"^(add|all|del:\d|sample:\d|judge:\d)$")


def _copies(form: dict[str, list[str]]) -> list[str]:
    """문구 칸들. ⛔ 상한을 넘으면 자르지 않고 거부한다 (D-220 · `_one` 과 같은 규칙)."""
    texts = form.get("text", [""])
    if len(texts) > _MAX_COPIES:
        raise HTTPException(422, f"문구는 한 번에 {_MAX_COPIES}건까지 받는다")
    for t in texts:
        if len(t) > PARAMS.max_text_len:
            raise HTTPException(422, f"text 가 너무 길다 — {PARAMS.max_text_len}자까지 받는다")
    return texts or [""]


def _core_judge(text: str, product=None):  # noqa: ANN001, ANN202
    """코어 판정을 부른다 — `POST /judge` 와 **같은 함수**다 (D-119 · 판정 코어는 하나).

    ★ 반환 `(상태, 응답)` — `ok` 는 `JudgeResponse`, `pending` 은 엔진 미착수(501), `down` 은 엔진 연결 실패(503).
    ⛔ 501 · 503 을 결과처럼 꾸미지 않는다 (D-147). 다른 오류는 삼키지 않고 올린다.
    🔄 2026-09-29 (ohb · ksr 병합) — `POST /judge` 가 501 대신 그래프를 부르고, DB · 그래프 의존성이 없으면 **503** 을 낸다.
       종전에는 501 만 받아서 503 이 화면 오류로 떨어졌다. 🚨 화면 문구는 화면 담당(ksr · lse)이 정한다 — 지금은
       `engine_pending` 그림을 같이 쓰고 `engine_down` 을 넘겨 둔다.
    """
    from app.api import judge as core_judge  # noqa: PLC0415 — 순환 import 를 피한다
    from app.contracts import JudgeRequest  # noqa: PLC0415

    try:
        # 🆕 10-06 (lse) — 고쳐 쓴 문구의 재판정은 원문 판정의 품목을 넘긴다(D-319). 검수는 종전대로 품목 없이
        req = (
            JudgeRequest(text=text) if product is None else JudgeRequest(text=text, product=product)
        )
        return "ok", core_judge(req)
    except HTTPException as e:
        # 🔄 2026-10-01 (ksr 병합) — ksr 도 같은 503 수정을 따로 했다(`in (501, 503)` → pending). ohb 의 갈래를 둔다:
        #    501 = 엔진 미착수 · 503 = 연결 실패 — 둘을 합치면 아래 `down` 이 닿지 않는 줄이 된다(자동 병합이 그렇게 만들었다)
        if e.status_code == 501:
            return "pending", None
        if e.status_code == 503:
            return "down", None
        raise


def _flagged(result) -> set[str]:  # noqa: ANN001
    """지적 문장 id — **확정이면서 통과 문턱 이하**가 아닌 문장은 전부 든다.

    🚨 미판정·보류도 든다 — 통과로 집계하지 않는다 (D-127). 문턱은 `PASS_RISK_MAX` 한 곳 (D-273) —
       템플릿에 R0 을 따로 적지 않으려고 여기서 계산해 넘긴다 (D-99).
    🔄 2026-10-01 — ⛔ 종전에는 위험도가 없는 확정(`final is None`)을 통과로 봤다. 판정 노드 1판은 **확정 위반을
       위험도 없이** 낸다(하한 W5 전) — 그 문장이 지적에서 빠지고 보류 문장만 세어졌다. 계약의 `is_pass` 를 쓴다 (D-72 · D-99).
    """
    return {s.sent_id for s in result.sentences if not is_pass(s) and not s.not_claim}


def _marks(text: str | None, result) -> dict[str, list[tuple[str, bool]]]:  # noqa: ANN001
    """문장마다 **뺄 구간**을 칠할 조각 `(글자, 구간인가)` — 엔진의 `spans` 는 원문 좌표다 (D-278).

    ★ 응답에는 문장의 원문 시작 자리가 없다 — 넣은 문구에서 되찾는다(`sentsplit.offsets` · 엔진과 같은 함수 · D-99).
    🚨 원문을 모르거나(픽스처 미리보기) 좌표를 못 되찾으면 **칠하지 않는다** — 엉뚱한 글자를 칠하지 않는다 (D-224).
    ★ 겹친 구간은 합쳐 한 번 칠한다. 조각은 템플릿이 이스케이프한다 (P2-9).
    """
    if not text:
        return {}
    try:
        starts = sentsplit.offsets(text, [s.text for s in result.sentences])
    except ValueError:
        return {}
    out: dict[str, list[tuple[str, bool]]] = {}
    for s, at in zip(result.sentences, starts, strict=True):
        n = len(s.text)
        cuts = sorted(
            (max(sp.start - at, 0), min(sp.end - at, n))
            for sp in s.spans
            if sp.start < at + n and sp.end > at
        )
        if not cuts:
            continue
        merged = [cuts[0]]
        for a, b in cuts[1:]:
            if a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        pieces: list[tuple[str, bool]] = []
        pos = 0
        for a, b in merged:
            pieces += [(s.text[pos:a], False), (s.text[a:b], True)]
            pos = b
        pieces.append((s.text[pos:], False))
        out[s.sent_id] = [p for p in pieces if p[0]]
    return out


def _sllm_enabled() -> bool:
    from app.routers import sllm_client  # noqa: PLC0415

    return sllm_client.enabled()


def _review_ctx(copies: list[str], results: list[dict] | None = None, **extra) -> dict:
    ctx = {
        "fixtures": _fixture_names("judge"),
        "max_text_len": PARAMS.max_text_len,
        "max_copies": _MAX_COPIES,
        "max_redo": _MAX_REDO,
        "copies": copies,
        "results": results or [],
        # 🆕 2026-10-08 — 고쳐 쓰기를 꺼 둔 환경이면 버튼 대신 안내를 그린다(`sllm_client.enabled()`)
        "rewrite_enabled": _sllm_enabled(),
    }
    for r in results or []:
        r["flagged"] = _flagged(r["result"])
        r["marks"] = _marks(r.get("text"), r["result"])
        # 분기마다의 지적 문장 — 화면이 고른 분기 기준으로 지적 건수를 센다 (2026-10-01)
        r["branch_flagged"] = {b.premise.value: _flagged(b) for b in r["result"].branches}
    if results:
        ctx["flagged"] = sum(len(r["flagged"]) for r in results)
    ctx.update(extra)
    return ctx


@router.get("/review", response_class=HTMLResponse)
def review(request: Request) -> HTMLResponse:
    """문구 검수 입력 화면 (SCR-A, ksr 2026-09-13)."""
    return _render(request, "user/review.html", _review_ctx([""]))


@router.post("/judge", response_class=HTMLResponse)
async def judge(request: Request) -> HTMLResponse:
    """문구 검수 BFF — 문구 칸 조작과 판정 호출 (ksr 2026-09-29 · 프로토타입 v7.2 `goReview`).

    🔴 **POST 다** — 문구를 URL 에 싣지 않는다 (보안점검 P1-4).
    ★ `op` — `add`(칸 추가) · `del:N` · `sample:N`(예시 넣기) · `judge:N`(그 문구만) · `all`(전체 검수).
    ★ 판정은 코어(`app.api.judge`)를 부른다 — 여기서 판정하지 않는다 (D-119).
       엔진이 501 이면 「엔진 준비 중」을 그린다. **가짜 결과를 만들지 않는다** (D-147).
    ★ 넣은 문구는 되돌려 그린다. **템플릿이 이스케이프한다** (P2-9) — 문자열 조립 금지.
    """
    form = await _form(request)
    copies = _copies(form)
    op = form.get("op", ["all"])[0]
    if not _OP.match(op):
        raise HTTPException(422, "모르는 동작")
    kind, _, arg = op.partition(":")
    idx = int(arg) - 1 if arg else -1
    if arg and not 0 <= idx < len(copies):
        raise HTTPException(422, "그런 문구 칸이 없다")

    if kind == "add":
        if len(copies) >= _MAX_COPIES:
            return _render(
                request,
                "user/review.html",
                _review_ctx(copies, notice=f"한 번에 최대 {_MAX_COPIES}건까지 검수할 수 있어요"),
            )
        return _render(request, "user/review.html", _review_ctx([*copies, ""]))
    if kind == "del":
        rest = copies[:idx] + copies[idx + 1 :]
        return _render(request, "user/review.html", _review_ctx(rest or [""]))
    if kind == "sample":
        copies[idx] = _SAMPLE_COPY
        return _render(request, "user/review.html", _review_ctx(copies))

    targets = [(idx + 1, copies[idx])] if kind == "judge" else list(enumerate(copies, 1))
    targets = [(n, t.strip()) for n, t in targets if t.strip()]
    if not targets:
        return _render(
            request, "user/review.html", _review_ctx(copies, notice="검수할 문구를 입력해주세요")
        )
    results: list[dict] = []
    for n, text in targets:
        state, res = _core_judge(text)
        if state in ("pending", "down"):
            return _render(
                request,
                "user/review.html",
                _review_ctx(copies, engine_pending=True, engine_down=state == "down"),
            )
        results.append({"n": n, "result": res, "text": text})
    return _render(request, "user/review.html", _review_ctx(copies, results))


# ── 검수 → 지적 문장 고쳐 쓰기 (sLLM 재생성) — lse 2026-10-06 · 팀장 승인 ─────────────
#: ★ 검수 결과의 지적 문장 아래 「이 문장 고쳐 쓰기」 → 그 문장을 sLLM 서버(`sllm_client`)가 고쳐 쓰고,
#:   고친 문구를 **앱의 판정 코어로 재판정**(D-119)해 **같은 검수 화면**의 그 문장 아래에 그린다.
#: 🔴 검수 판정(`JudgeResponse`)에는 대체 문구를 넣지 않는다 — `candidates` 는 비운 채다(D-265 계약).
#:    고쳐 쓰기는 판정과 따로 부르는 **재생성 호출**이고, 화면이 판정 결과 옆에 붙여 보일 뿐이다.
#: ⛔ 사유 A(자격형)는 고쳐 쓰지 않는다 — 같은 위반을 되풀이한다(D-59).
#: ⛔ sLLM 서버가 없으면 후보를 그리지 않는다(D-146 · D-147). 모델이 지어낸 불가 사유는 그리지 않는다.

_VIOLATIONS = frozenset(v.value for v in Violation)
_PREMISES = frozenset(p.value for p in Premise)
_TARGET = re.compile(r"^(\d{1,2}):([A-Za-z0-9_\-]{1,32})$")


def _violations_of(result) -> list[str]:  # noqa: ANN001 — JudgeResponse · Branch
    """판정 결과(또는 분기 하나)의 위반 유형(문장 순서대로 · 중복 없이)."""
    out: list[str] = []
    for s in result.sentences:
        for v in s.violations or []:
            if v.value not in out:
                out.append(v.value)
    return out


def _branch_of(result, premise: str):  # noqa: ANN001, ANN202 — JudgeResponse → Branch | None
    """고른 전제의 분기. 없으면 `None` — 없는 전제의 판정을 지어내지 않는다 (D-147)."""
    return next((b for b in result.branches if b.premise.value == premise), None)


def _sllm_category(category: str | None, premise: str) -> str | None:
    """생성 서버에 넘길 품목 (🆕 2026-10-10 · 인계 10-08 §2 「함께」 · D-319).

    원문 판정에 품목이 있으면 그 품목 · 없고 분기를 골랐으면 **고른 전제의 품목**(`pm.PREMISE_CATEGORY` — 판정이 쓰는 표 · D-99) ·
    둘 다 없으면 `None`(서버가 문구에서 추측한다). ⛔ 종전에는 분기를 고른 문구가 늘 `None` 이었다 — 사용자가 화장품을 골랐는데
    서버는 문구로 식품이라 추측할 수 있었다.
    🚨 재판정에는 이 값을 넘기지 않는다 — 재판정은 종전대로 품목 없이 판정하고 고른 전제의 분기를 읽는다(`_rejudge`).
       품목을 넘기면 전제가 줄어 그 분기가 생략될 수 있다(전제마다 판정이 같으면 분기를 내지 않는다).
    ⬜ 건강기능식품의 **인정 여부**(전제 `건기식_인정` · `건기식_비인정`)는 넘어가지 않는다 — 서버에 받는 칸이 없다(이서은 확인 대기).
    """
    if category or not premise:
        return category
    return pm.PREMISE_CATEGORY[Premise(premise)].value


def _rejudge(body: str, premise: str = "", category: str | None = None) -> dict:
    """고친 문구를 판정 코어에 다시 넣는다(D-119). 🚨 `no_violation` 은 「위반을 못 찾음」이지 통과가 아니다.

    🆕 2026-10-06 (ksr) — 분기를 고르고 고쳐 썼으면 재판정도 **같은 전제의 분기**로 읽는다. 재판정에 그 분기가
       없으면(전제마다 판정이 같아 분기가 생략됨) 기록되는 판정을 읽는다.
    🆕 2026-10-06 (lse) — 원문 판정에 품목이 있으면 재판정에도 그 품목을 넘긴다(D-319). 분기를 고른 문구는 원문 판정의
       품목이 비어 있다 — 그때는 종전대로 품목 없이 판정하고 고른 전제의 분기를 읽는다.
    """
    from app.contracts import Category, ProductContext  # noqa: PLC0415

    state, res = _core_judge(
        body, ProductContext(category=Category(category)) if category else None
    )
    if state != "ok":
        return {"status": "unavailable"}
    res = (_branch_of(res, premise) if premise else None) or res
    violations = _violations_of(res)
    hold = sorted({s.hold_reason.value for s in res.sentences if s.hold_reason})
    if violations or any(s.verdict.value == "no_basis" for s in res.sentences):
        return {"status": "rejected", "violations": violations, "hold_reasons": hold}
    if any(s.verdict.value == "unjudged" for s in res.sentences):
        # 🆕 2026-10-08 (D-127) — 미판정은 「안 봤다」다. ⛔ 「위반 못 찾음」으로 내면 안 본 문장을 본 것처럼 말한다.
        #    🚨 같은 규칙이 `docs/lse/rejudge.py` 에도 있다(이서은 폴더 · 서버 쪽 재판정) — 바꾸면 양쪽을 같이 (D-99)
        return {"status": "unjudged", "violations": [], "hold_reasons": hold}
    status = "passed" if res.outcome.value == "pass" else "no_violation"
    # 🆕 2026-10-14 (D-323 결정 4 집행 · D-323 보충) — 사전은 지났는데 인코더가 유형 후보를 내면 「위반 못 찾음 + AI 추정 유형 남음」.
    #    판정이 아니다 — 상태는 그대로 두고 칸 하나로 싣는다. 후보가 없으면 빈 목록(「문제없음」이 아니다 · D-220)
    enc = sorted(
        {
            c.violation.value
            for s in res.sentences
            for c in getattr(s, "encoder_candidates", None) or ()
        }
    )
    return {"status": status, "violations": [], "hold_reasons": hold, "enc_types": enc}


def _note_conflict(note: str | None, premise: str, category: str | None) -> bool:
    """후보의 조건이 **이 제품 전제에서 채워질 수 없는가** (🆕 2026-10-10 · D-326 · 원장 10-10 ⑪).

    서버 후처리는 공식 기능성 문구에 「기능성 인정 건강기능식품에 한해 표시」를 붙인다(`sllm_client.NOTE_RECOGNIZED_HF`).
    그 문구는 일반식품 · 인정 없는 건강기능식품에서는 쓸 수 없는데(3호 · [별표 1] 4.나), 재판정은 그것을 거부하지 못한다 —
    공식 기능성 문구는 식품 분기에서 확신 부족 보류로 나온다(dev 승인 문구 19 행 중 거부 0). 서버는 전제를 모른다.
    ★ 보는 전제 — 고른 분기가 있으면 그 전제 하나 · 없고 품목을 알면 그 품목의 전제 전부(`pm.PREMISES_OF`).
       **그 전부가 `건기식_인정` 이 아닐 때만** 참이다.
    🔴 값이 없을 때 (D-220) — 조건이 없거나 다른 조건이면 거짓(이 검사의 대상이 아니다) · 전제도 품목도 모르면 거짓이다.
       모르는 것을 「쓸 수 없음」으로도 「쓸 수 있음」으로도 적지 않는다 — 재판정 표시가 그대로 나간다.
    """
    from app.routers import sllm_client  # noqa: PLC0415

    if (note or "").strip() != sllm_client.NOTE_RECOGNIZED_HF:
        return False
    if premise:
        premises: tuple[Premise, ...] = (Premise(premise),)
    elif category:
        premises = pm.PREMISES_OF.get(Category(category), ())
    else:
        premises = ()
    return bool(premises) and Premise.건기식_인정 not in premises


def _rewrite_sentence(  # noqa: ANN001 — SentenceJudgment
    sentence, premise: str = "", category: str | None = None, sllm_category: str | None = None
) -> dict:
    """지적 문장 하나를 고쳐 쓰고 재판정한다. 화면용 dict(`rw`).

    `category` 는 원문 판정의 품목(재판정에 넘긴다) · `sllm_category` 는 생성 서버에 넘기는 품목이다 — 둘이 다른 것은
    분기를 고른 문구뿐이다(원문 판정의 품목은 비어 있고, 고른 전제가 품목을 말한다 · `_sllm_category`).
    """
    from app.routers import sllm_client  # noqa: PLC0415

    violations = [v.value for v in sentence.violations or []]
    # 🆕 2026-10-14 (D-323 보충) — 사전 유형이 없으면 인코더 추정 유형으로 부른다(`reasons.guessed_types` · 화면 버튼과 같은 함수).
    #    생성은 기록되는 판정이 아니다 — D-332 보충 ① 과 같은 판단. 서버 계약은 그대로(`violation_types` 칸)
    guessed = [] if violations else reasons.guessed_types(sentence)
    violations = violations or guessed
    rw: dict = {"violations": violations, "guessed": bool(guessed)}
    # 🆕 10-06 (팀장 전달 §2 #3) — 품목을 넘긴다. 미확정이면 None — 서버가 문구에서 추측한다
    # 🔄 2026-10-10 — 분기를 고른 문구는 고른 전제의 품목을 넘긴다(인계 10-08 §2 「함께」). 서버가 추측하지 않는다
    s_state, out = sllm_client.rewrite(sentence.text, violations, sllm_category or category)
    if out and out.get("infeasible") and out["infeasible"] not in _VIOLATIONS:
        # 위반 유형 없이 보내면 모델이 사유를 제 말로 지어 쓴다(10-06 실측) — 그 말을 사유로 그리지 않는다
        out = {**out, "infeasible": None}
    # 🆕 2026-10-08 — 이 환경에는 서버를 두지 않았다(`sllm_client.enabled()`) — 「연결 실패」와 가른다
    rw["off"] = s_state == "off"
    rw["down"] = s_state != "ok"
    rw["out"] = out
    if out and out.get("outcome") == "infeasible":
        # 🔄 2026-10-14 (D-323 보충 개정) — 생성 서버의 「고칠 수 없음」은 유형 출처와 무관하게 「만들지 못했어요」다.
        #    ⛔ 「합법화 불가」는 코드의 불가 사유만 말한다 (D-59 · D-10) — 같은 카드에서 코드(실증 B)와 말이 갈리던 자리
        rw["infeasible_note"] = reasons.REWRITE_INFEASIBLE_TEXT
    if out and out["outcome"] == "candidate" and out.get("rewrite"):
        rw["rejudge"] = _rejudge(out["rewrite"]["body"], premise, category)
        # 🆕 2026-10-10 — 후보의 조건이 이 전제에서 채워질 수 없으면 후보로 내지 않는다(재판정이 못 거르는 자리)
        rw["note_conflict"] = _note_conflict(
            out["rewrite"].get("mandatory_note"), premise, category
        )
        # 🆕 2026-10-12 — 서버가 다듬은 문장(2단계)과 담백한 문장(1단계)을 같이 주면 담백한 안도 재판정한다.
        #    다듬은 안이 재판정에서 떨어지면 담백한 안을 후보로 올린다 · 둘 다 살면 담백한 안을 두 번째 안으로 보인다
        plain = out.get("plain")
        if plain:
            p_rejudge = _rejudge(plain, premise, category)
            if p_rejudge.get("status") != "rejected":
                # 🆕 2026-10-14 — 다듬은 안에만 AI 추정 유형이 남으면 담백한 안을 올린다(사전 탈락과 같은 자리 · 더 보수적인 쪽)
                enc_only_polished = bool(rw["rejudge"].get("enc_types")) and not p_rejudge.get(
                    "enc_types"
                )
                if rw["rejudge"].get("status") == "rejected" or enc_only_polished:
                    rw["out"] = {**out, "rewrite": {**out["rewrite"], "body": plain}, "plain": None}
                    rw["rejudge"] = p_rejudge
                else:
                    rw["plain"] = {"body": plain, "rejudge": p_rejudge}
    # 🆕 2026-10-13 — 「조건 확인 필요」 보류의 문장(인정 · 심사 제품에서만 쓸 수 있는 공식 문구)을 「조건부 후보」로 보인다.
    #    🚨 후보가 아니다 — 재판정을 받고, 고른 전제에서 조건이 채워질 수 없으면(`_note_conflict`) 보이지 않는다.
    #    사람이 제품의 인정 · 심사 여부를 확인한 뒤 쓰는 문장이다
    cond = out.get("conditional") if out and out["outcome"] == "hold" else None
    if cond and not _note_conflict(cond.get("mandatory_note"), premise, category):
        c_rejudge = _rejudge(cond["body"], premise, category)
        if c_rejudge.get("status") != "rejected":
            rw["conditional"] = {**cond, "rejudge": c_rejudge}
    return rw


@router.post("/review/rewrite", response_class=HTMLResponse)
async def review_rewrite(request: Request) -> HTMLResponse:
    """지적 문장 고쳐 쓰기 BFF (lse 2026-10-06).

    🔴 **POST 다** — 문구를 URL 에 싣지 않는다(P1-4). 화면에 상태를 두지 않으므로 문구 칸을 다시 받아 **다시 판정**하고,
       `target`(`문구번호:문장id`) 문장을 고쳐 써 그 아래에 붙인다. 위반 유형은 **서버의 판정 결과**에서 읽는다(폼을 믿지 않는다).
    🆕 2026-10-06 (ksr · 병합) — 품목 분기가 있는 문구는 **분기를 고른 뒤에만** 고쳐 쓴다. 폼이 고른 전제(`premise`)와
       회차(`round`)를 싣고, 위반 유형은 **그 전제의 분기 문장**에서 읽는다 — 품목을 모를 때의 기록 판정(가장 보수적인
       전제)으로 고쳐 쓰지 않는다. 다시 그릴 때 고른 분기를 펼쳐 둔다(`picked`) — 화면에 상태가 없어서다.
    """
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

    form = await _form(request)
    copies = _copies(form)
    m = _TARGET.match(form.get("target", [""])[0])
    if not m:
        raise HTTPException(422, "고쳐 쓸 문장을 모른다")
    want_n, want_sid = int(m.group(1)), m.group(2)
    premise = _one(form, "premise", 32)
    if premise and premise not in _PREMISES:
        raise HTTPException(422, "모르는 전제")
    redo = _one(form, "round", 2) or "0"
    if not redo.isdigit() or int(redo) > _MAX_REDO:
        raise HTTPException(422, "모르는 회차")

    targets = [(n, t.strip()) for n, t in enumerate(copies, 1) if t.strip()]
    results: list[dict] = []
    for n, text in targets:
        state, res = await run_in_threadpool(_core_judge, text)
        if state in ("pending", "down"):
            return _render(
                request,
                "user/review.html",
                _review_ctx(copies, engine_pending=True, engine_down=state == "down"),
            )
        results.append({"n": n, "result": res, "text": text, "rewrites": {}})

    item = next((r for r in results if r["n"] == want_n), None)
    source = item and item["result"]
    if source is not None and source.branches:
        source = _branch_of(source, premise)
        if source is None:
            return _render(
                request,
                "user/review.html",
                _review_ctx(
                    copies,
                    results,
                    notice="제품 유형을 먼저 골라 주세요 — 고른 유형의 판정으로 고쳐 써요",
                ),
            )
        item["picked"] = {"premise": premise, "round": int(redo)}
    else:
        premise = ""
    sent = source and next((s for s in source.sentences if s.sent_id == want_sid), None)
    if sent is None:
        return _render(
            request,
            "user/review.html",
            _review_ctx(copies, results, notice="고쳐 쓸 문장을 찾지 못했어요"),
        )
    if sent.infeasibility and sent.infeasibility.value == "A":
        rw = {"qualification": True}
    elif not sent.violations and not reasons.guessed_types(sent):
        # 확신 부족 보류만 있고 위반 유형이 없다 — 고칠 것이 없다. 유형 없이 보내면 모델이 엉뚱한 불가를 낸다(10-06 실측)
        # 🔄 2026-10-14 (D-323 보충) — 인코더 추정 유형이 있으면 그 유형으로 고쳐 쓴다(`_rewrite_sentence`)
        rw = {"no_violation": True}
    else:
        cat = item["result"].category.value if item["result"].category else None
        rw = await run_in_threadpool(
            _rewrite_sentence, sent, premise, cat, _sllm_category(cat, premise)
        )
    # 열쇠는 (전제, 문장) — 분기 없는 문구의 전제는 빈 글자다. 다른 분기의 같은 문장에 붙지 않는다
    item["rewrites"][premise] = {want_sid: rw}
    return _render(request, "user/review.html", _review_ctx(copies, results))


@router.get("/preview/{name}", response_class=HTMLResponse)
def judge_preview(request: Request, name: str) -> HTMLResponse:
    """골든 픽스처 하나를 **결과 화면으로** 그린다 (D-124 ③).

    ⛔ 파일을 그대로 흘리지 않는다 — `JudgeResponse` **계약을 통과시켜** 낸다.
       계약이 깨지면 화면이 아니라 여기서 먼저 터져야 한다.
    """
    from app.contracts import JudgeResponse  # noqa: PLC0415

    raw = _fixture_path("judge", name).read_text(encoding="utf-8")
    result = JudgeResponse.model_validate_json(raw)
    return _render(
        request,
        "user/review.html",
        _review_ctx(
            [" ".join(s.text for s in result.sentences)],
            [{"n": 1, "result": result}],
            fixture_name=name,
        ),
    )


# ══════════════════════════════════════════════════════════════════════
#  B · 카피 생성 (SCR-GN)
# ══════════════════════════════════════════════════════════════════════

#: 프론티어 산점도의 그리기 영역. 🚨 **좌표는 파이썬이 계산한다** —
#:    CSP 가 스크립트를 막아 차트 라이브러리를 못 쓰고, 템플릿은 인라인 SVG 로 점만 찍는다.
_PLOT = {"x0": 40.0, "x1": 326.0, "y0": 216.0, "y1": 14.0}

#: 🔴 프론티어 가로축의 **오른쪽 끝** — 도달할 수 있는 가장 높은 위험도. 척도는 R0~R3 네 단계다 (D-227).
#: 🔄 2026-09-22 (ohb 흡수) — ⛔ 종전 `level / 4.0` 은 R4 까지 있는 척도로 그렸다. R4 는 ENUM 에 남아 있으나
#:    도달 불가다 (D-182 · `contracts.Risk`). 그래서 가장 높은 R3 가 축의 **3/4 지점**에 찍혔다.
#:    ★ 템플릿의 오른쪽 눈금도 이 값을 받는다 — 좌표와 눈금이 한 벌이다 (D-99).
_RISK_AXIS_MAX = Risk.R3


def _frontier(candidates: list) -> list[dict]:  # noqa: ANN401
    """후보를 산점도 좌표로 옮긴다.

    x = 잔여 위험도(R0~R3 를 0~1 로 · `_RISK_AXIS_MAX`), y = 소구력 보존율(원문 대비 정보량 보존율).
    🚨 축 밖의 위험도(R4)는 **축 끝에 눌러 그리지 않고 멈춘다** — 도달 불가 값이 왔다는 것은
       코어 쪽 사고이고, 끝에 찍으면 R3 로 보인다 (D-72).
    🚨 y 축은 **전환율·판매 성과가 아니다** (contracts.py `Candidate` docstring).
    """
    points: list[dict] = []
    for c in candidates:
        if c.residual_risk.level > _RISK_AXIS_MAX.level:
            raise ValueError(
                f"프론티어 축 밖의 위험도 {c.residual_risk.value} — 척도는 R0~{_RISK_AXIS_MAX.value} (D-227 · D-182)"
            )
        rx = c.residual_risk.level / _RISK_AXIS_MAX.level
        ry = float(c.appeal_retention)
        points.append(
            {
                "label": c.label,
                "cx": round(_PLOT["x0"] + rx * (_PLOT["x1"] - _PLOT["x0"]), 1),
                "cy": round(_PLOT["y0"] - ry * (_PLOT["y0"] - _PLOT["y1"]), 1),
                "risk": c.residual_risk.value,
                "retention": round(ry * 100),
            }
        )
    #: 🚨 프론티어 선은 **왼쪽에서 오른쪽으로** 잇는다 — 후보 순서에 기대지 않는다.
    return sorted(points, key=lambda p: p["cx"])


#: 🆕 2026-10-08 — 생성 입력의 **분기 6종**(품목 × 인증 여부 · LLM 카피 생성 기획서 §3).
#:    시험 코드(`docs/ksr/llm_copy/branches.py`)와 같은 표다 — ⛔ 앱이 시험 폴더를 import 하지 않는다.
#:    화면이 쓰는 것(이름 · 안내 · 그 분기에서만 읽는 칸)만 여기 둔다. 프롬프트 · 금지 낱말은 엔진의 것이다.
_GEN_CATEGORIES = (("cos", "화장품"), ("food", "식품"), ("hf", "건강기능식품"))
_GEN_HF_NO_NOTICE = (
    "기능성 인정이 없으면 건강기능식품으로 광고할 수 없습니다. 일반식품으로 생성합니다."
)
#: 🆕 2026-10-10 — `premise` = 이 분기로 만든 문구를 **어느 전제로 판정하는가** (D-276 결정 1 · `app/premise.py`).
#:    생성의 분기(품목 × 인증 여부)와 판정의 전제는 축이 다르다 — 대응을 여기 한 곳에 적는다. 생성 평가도 이 표로 잰다.
#:    · 식품의 「인증 예」는 HACCP 같은 인증이다 — ⛔ `일반식품_기능성`(고시의 기능성 표시 요건)이 아니다. 전제는 `식품`
#:    · 건강기능식품의 「인증 아니오」는 일반식품으로 생성한다(위 안내) — 전제는 `식품`. ⛔ `건기식_비인정` 이 아니다
#:    · ⬜ 화장품의 「인증 예」(기능성화장품 심사 · 보고)에 맞는 전제가 없다 — 화장품의 전제는 `화장품` 하나다.
#:      심사받은 효능 범위 안의 문구가 그 전제에서 어떻게 판정되는지는 정해지지 않았다 (판정 대기)
#:    시험 코드 `docs/ksr/llm_copy/branches.py` 의 `category` 와 맞는지는 `tests/test_user_screens.py` 가 본다
_GEN_BRANCHES: dict[str, dict] = {
    "food_no": {"label": "식품 · 인증 아니오", "premise": Premise.식품},
    "food_yes": {
        "label": "식품 · 인증 예 (HACCP 등)",
        "needs": "certs",
        "premise": Premise.식품,
    },
    "hf_yes": {
        "label": "건강기능식품 · 인증 예 (기능성 인정)",
        "needs": "fixed",
        "premise": Premise.건기식_인정,
    },
    "hf_no": {
        "label": "건강기능식품 · 인증 아니오",
        "notice": _GEN_HF_NO_NOTICE,
        "premise": Premise.식품,
    },
    "cos_no": {"label": "화장품 · 인증 아니오 (일반)", "premise": Premise.화장품},
    "cos_yes": {
        "label": "화장품 · 인증 예 (기능성 심사·보고)",
        "needs": "fixed",
        "premise": Premise.화장품,
    },
}
#: 대상 고객 — 나이대 × 성별. 🚨 축은 **둘까지만** 겹친다(셋을 겹치면 20명 미만 칸이 생긴다 · `k_anon_min`).
#:    ⛔ 건강 고민 · 증상은 축으로 두지 않는다 (D-27). 나이대 구간은 페르소나 정리 2판(10-01)의 1층과 같다
_GEN_AGES = (
    ("all", "전체 나이대"),
    ("20", "20대"),
    ("30", "30대"),
    ("40", "40대"),
    ("50", "50대"),
    ("60", "60대 이상"),
)
_GEN_SEXES = (("all", "성별 전체"), ("f", "여성"), ("m", "남성"))
#: 칸마다 받는 길이. 여러 개를 적는 칸(특징 · 원재료 · 인증)은 항목 하나의 길이(`line`)와 개수다
_GEN_MAX_LINES = 12
_GEN_LIMITS = {"name": 128, "kind": 64, "phrase": 200, "target": 128, "fixed": 300, "line": 64}
_GEN_LIMITS["list"] = (_GEN_LIMITS["line"] + 2) * _GEN_MAX_LINES


def _gen_ctx(extra: dict | None = None) -> dict:
    """생성 화면이 늘 받는 것 — 세 경로(입력 · 제출 · 픽스처)가 같은 폼을 그린다."""
    return {
        "fixtures": _fixture_names("generate"),
        "gen_categories": _GEN_CATEGORIES,
        "gen_ages": _GEN_AGES,
        "gen_sexes": _GEN_SEXES,
        "gen_limits": _GEN_LIMITS,
        "gen_hf_no_notice": _GEN_HF_NO_NOTICE,
        "gen_want": PARAMS.candidate_n,
        # 🆕 2026-10-13 — 생성 엔진이 켜져 있으면 「제품 정보가 밖(GPT)으로 나간다」를 입력 칸 옆에 적는다
        "gen_external": _copygen_off() is None,
        **(extra or {}),
    }


#: 🆕 2026-10-13 (권소라) — 「더 탐색하기」는 **세 번까지**다. 누를 때마다 생성 모델을 다시 부른다 — 끝없이 해 줄 수 없다.
#:    🚨 횟수는 폼이 들고 다닌다(로그인 · 서버 저장이 없다) — 화면의 약속이지 비용의 방벽이 아니다.
#:       새로 「카피 생성」을 누르면 처음부터다. 비용을 막는 것은 호출 제한의 일이다(변경 기록 10-13 §4-2 10번)
_GEN_MORE_MAX = 3
#: 이미 보여 준 문구의 상한 — 첫 결과 + 더 탐색 세 번 = 넷 묶음
_GEN_SHOWN_MAX = PARAMS.candidate_n * (_GEN_MORE_MAX + 1)


def _gen_more(form: dict[str, list[str]]) -> tuple[int, list[str]]:
    """「더 탐색하기」가 넘긴 (몇 번째인가 · 이미 보여 준 문구). 처음 생성이면 `(0, [])`.

    ★ 문구는 자리표시자가 든 글자로 들고 다닌다 — 인정 · 심사 문구를 폼에 여러 벌 싣지 않는다.
    ⛔ 넘치는 것 · 긴 것 · 모르는 횟수는 자르지 않고 거부한다 (D-220).
    """
    raw = _one(form, "more", 4)
    if not raw:
        return 0, []
    if not raw.isdigit() or not 1 <= int(raw) <= _GEN_MORE_MAX:
        raise HTTPException(422, f"더 탐색하기는 {_GEN_MORE_MAX}번까지다")
    shown = [s.strip() for s in form.get("shown", []) if s.strip()]
    if len(shown) > _GEN_SHOWN_MAX or any(len(s) > _GEN_LIMITS["phrase"] for s in shown):
        raise HTTPException(422, "이미 보여 준 문구가 너무 많거나 길다")
    return int(raw), shown


def _copygen_off() -> str | None:
    """카피 생성 엔진을 못 쓰는 까닭(쓸 수 있으면 `None`) — 판단은 `copygen.off_reason` 한 곳이다 (D-99)."""
    from app.routers import copygen  # noqa: PLC0415 — 엔진을 안 쓰는 화면이 import 값을 치르지 않게

    return copygen.off_reason()


def _gen_lines(form: dict[str, list[str]], name: str) -> list[str]:
    """여러 개를 적는 칸 — 쉼표나 줄바꿈으로 나눈다. ⛔ 넘치는 것 · 긴 것을 자르지 않고 거부한다 (D-220)."""
    raw = _one(form, name, _GEN_LIMITS["list"])
    lines = [ln.strip() for ln in re.split(r"[,\n]", raw) if ln.strip()]
    if len(lines) > _GEN_MAX_LINES or any(len(ln) > _GEN_LIMITS["line"] for ln in lines):
        raise HTTPException(
            422, f"{name} 은 {_GEN_MAX_LINES}개 · 하나에 {_GEN_LIMITS['line']}자까지 받는다"
        )
    return lines


def _gen_picked(form: dict[str, list[str]]) -> tuple[dict, dict, list[str]]:
    """폼에서 (적은 값 · 분기 · 고칠 곳)을 읽는다.

    🚨 분기에 안 맞는 칸은 화면에서 숨길 뿐이라 **값이 같이 넘어온다** — 인증 · 고정 문구는
       그 분기일 때만 읽는다. 「아니오」로 바꿨는데 예전 인증이 입력 사실로 남으면 안 된다.
    """
    category, cert = _one(form, "category", 8), _one(form, "cert", 8)
    branch = _GEN_BRANCHES.get(f"{category}_{cert}")
    if branch is None:
        raise HTTPException(422, "그런 분기가 없다 — 품목과 인증 여부를 다시 고른다")
    needs = branch.get("needs")
    age, sex = _one(form, "age", 8), _one(form, "sex", 8)
    ages, sexes = dict(_GEN_AGES), dict(_GEN_SEXES)
    if age not in ages or sex not in sexes:
        raise HTTPException(422, "그런 대상 고객이 없다 — 나이대와 성별을 다시 고른다")
    picked = {
        "category": category,
        "cert": cert,
        "age": age,
        "sex": sex,
        #: 화면 · 엔진에 넘길 이름 — 「30대 여성」 · 「남성」 · 「전체」
        "audience": " ".join(v for k, v in ((age, ages[age]), (sex, sexes[sex])) if k != "all")
        or "전체",
        "name": _one(form, "name", _GEN_LIMITS["name"]).strip(),
        "kind": _one(form, "kind", _GEN_LIMITS["kind"]).strip(),
        "phrase": _one(form, "phrase", _GEN_LIMITS["phrase"]).strip(),
        "target": _one(form, "target", _GEN_LIMITS["target"]).strip(),
        "features": _gen_lines(form, "features"),
        "ingredients": _gen_lines(form, "ingredients"),
        "certs": _gen_lines(form, "certs") if needs == "certs" else [],
        "fixed": _one(form, "fixed", _GEN_LIMITS["fixed"]).strip() if needs == "fixed" else "",
    }
    errors: list[str] = []
    if not any(picked[k] for k in ("name", "kind", "phrase", "features")):
        errors.append("제품명 · 제품 종류 · 간단한 문구 · 특징 중 하나는 적어 주세요.")
    if needs == "certs" and not picked["certs"]:
        errors.append("인증 「예」를 골랐어요 — 받은 인증의 이름을 적어 주세요.")
    if needs == "fixed" and not picked["fixed"]:
        errors.append(
            "인증 「예」를 골랐어요 — 인정 · 심사받은 기능성 문구를 원문 그대로 적어 주세요."
        )
    return picked, branch, errors


@router.get("/generate", response_class=HTMLResponse)
def generate_page(request: Request) -> HTMLResponse:
    """카피 생성 입력 화면 (`gen-input`, ksr 2026-09-13).

    `review`/`index` 와 같은 패턴이다: DB·엔진 없이 골든 픽스처(`GenerateResponse`,
    D-181)로 뜬다. `POST /generate` 코어는 아직 501 이다 — 여기서 부르지 않는다.
    """
    return _render(request, "user/generate.html", _gen_ctx())


@router.post("/generate", response_class=HTMLResponse)
async def generate(request: Request) -> HTMLResponse:
    """카피 생성 — GPT 가 후보를 쓰고 · 코드 필터가 거르고 · 판정 인코더가 본다 (`app/routers/copygen` · ksr 2026-10-13).

    🚨 코어 `POST /generate`(계약 `GenerateResponse`)는 여전히 501 이다 — 부르지 않는다. 여기 붙은 것은 화면의 엔진이고,
       잔여 리스크 · 소구력 보존 같은 계약의 수치는 채우지 않는다(재는 노드가 없다 · D-147).
    ★ 엔진을 쓸 수 없으면(스위치 · 키 · 인코더) 「준비 안 됨」과 그 까닭을, 호출이 실패하면 「실패」를 그린다. 가짜 후보를 만들지 않는다.
    ★ 수십 초 걸린다 — 스레드로 돌려 그동안 다른 요청이 멈추지 않게 한다.
    ★ 적은 값은 되돌려 그린다. **템플릿이 이스케이프한다** (P2-9).
    """
    from app.routers import copygen  # noqa: PLC0415

    form = await _form(request)
    picked, branch, errors = _gen_picked(form)
    more, shown = _gen_more(form)
    ctx: dict = {"picked": picked, "branch": branch, "errors": errors}
    if errors:
        return _render(request, "user/generate.html", _gen_ctx(ctx))
    if why := copygen.off_reason():
        ctx |= {"engine_pending": True, "engine_why": why}
        return _render(request, "user/generate.html", _gen_ctx(ctx))
    fields = {
        **{k: picked[k] for k in ("name", "kind", "phrase", "features", "ingredients", "certs")},
        "fixed": picked["fixed"],
        # 대상 — 고른 나이대 · 성별과 적은 말을 한 줄로. 「전체」는 대상이 아니다
        "target": " · ".join(
            v
            for v in (picked["audience"] if picked["audience"] != "전체" else "", picked["target"])
            if v
        ),
    }
    try:
        live = await run_in_threadpool(
            copygen.generate, f"{picked['category']}_{picked['cert']}", fields, tuple(shown)
        )
    except copygen.CopyGenOff as e:
        ctx |= {"engine_pending": True, "engine_why": str(e)}
    except copygen.CopyGenError:
        # 🚨 까닭은 서버 로그에만 — 화면에는 「실패했다」만 그린다 (P1-4)
        logging.getLogger(__name__).warning("카피 생성 실패", exc_info=True)
        ctx |= {"engine_pending": True, "engine_failed": True}
    else:
        ctx |= {
            "live": live,
            "live_reasons": [(copygen.REASONS[k], n) for k, n in live.reasons().most_common()],
            "live_strip": _gen_strip(live),
            # 「더 탐색하기」 — 지금까지 보여 준 것(이번 것 포함)과 다음 횟수를 폼에 실어 둔다
            "more": more,
            "more_max": _GEN_MORE_MAX,
            "more_shown": [*shown, *(k.raw or k.text for k in live.picked)],
        }
    return _render(request, "user/generate.html", _gen_ctx(ctx))


#: 띠 그래프의 그릴 자리 — 가로 한 줄. 왼쪽 = 문턱에서 멀다 · 오른쪽 끝 = 문턱
_STRIP = {"x0": 24, "x1": 316, "y": 46}


def _gen_strip(live) -> list[dict]:  # noqa: ANN001
    """통과한 후보 전부를 「문턱까지의 거리」 한 축에 찍을 좌표 (🆕 2026-10-13 · 픽스처의 프론티어 그림 자리).

    🚨 세로축이 없다 — 소구력 보존을 재는 노드가 없다. 지어내지 않고 한 축만 그린다 (D-147).
    ★ 고른 셋은 이름(보수 · 균형 · 공격)을 달고, 겹친 점은 위아래로 조금씩 벌린다.
    """
    span = _STRIP["x1"] - _STRIP["x0"]
    points: list[dict] = []
    stack: dict[int, int] = {}
    for k in sorted(live.kept, key=lambda k: (not k.tier, k.closeness)):
        cx = round(_STRIP["x0"] + min(max(k.closeness, 0.0), 1.0) * span)
        n = stack.get(cx // 8, 0)
        stack[cx // 8] = n + 1
        points.append(
            {
                "cx": cx,
                "cy": _STRIP["y"] - (0 if k.tier else 14 + 9 * (n % 3)),
                "tier": k.tier,
                "pct": round(k.closeness * 100),
            }
        )
    return points


@router.get("/generate/preview/{name}", response_class=HTMLResponse)
def generate_preview(request: Request, name: str) -> HTMLResponse:
    """생성 골든 픽스처 하나를 **결과 화면으로** 그린다 (D-124 ③).

    ⛔ 파일을 그대로 흘리지 않는다 — `GenerateResponse` **계약을 통과시켜** 낸다.
    """
    from app.contracts import GenerateResponse  # noqa: PLC0415

    raw = _fixture_path("generate", name).read_text(encoding="utf-8")
    result = GenerateResponse.model_validate_json(raw)
    return _render(
        request,
        "user/generate.html",
        _gen_ctx(
            {
                "result": result,
                "points": _frontier(result.candidates),
                "risk_axis_max": _RISK_AXIS_MAX.value,
                "fixture_name": name,
            }
        ),
    )


@router.get("/segments", response_class=HTMLResponse)
def segments(request: Request) -> HTMLResponse:
    """대상고객 탐색 — ★ **골격만**. `/u/generate` 카드에서만 들어온다 (사이드바 밖)."""
    return _render(request, "user/segments.html")


# ══════════════════════════════════════════════════════════════════════
#  C · 광고 생성 (SCR-AD) — 진입점 C
# ══════════════════════════════════════════════════════════════════════


#: 🆕 2026-10-12 — 광고 종류 **셋**(프로토타입 v7.2 `DRAFT_FORMATS` 일곱 중 SNS 피드 · 상세페이지 · 배너 300×250).
#:    🚨 화면의 표다 — 코어 계약 `AdFormat`(상세페이지 · 카드뉴스 · 배너)은 그대로 둔다. 코어 `/compose` 가 서면 그때 맞춘다.
#:    `h` 가 없으면 세로 가변이다. `disclose` = 「광고」 표시를 어디에 두는가 (D-93 · D-164)
_AD_FORMATS: dict[str, dict] = {
    "SNS 피드": {
        "key": "sns",
        "w": 1080,
        "h": 1080,
        "spec": "1080 × 1080 · 1:1",
        "disclose": "캡션 첫 줄 · 더보기 컷오프 전",
    },
    "상세페이지": {
        "key": "detail",
        "w": 860,
        "h": None,
        "spec": "860 × 세로 가변",
        "disclose": "페이지 하단 필수 표기 영역 (고정)",
    },
    "배너": {
        "key": "banner",
        "w": 300,
        "h": 250,
        "spec": "300 × 250",
        "disclose": "면적 부족 · 랜딩 페이지 고지 필수",
    },
}


def _compose_ctx(extra: dict | None = None) -> dict:
    """광고 생성 화면이 늘 받는 것 — 입력 · 제출 · 편집기 · 픽스처가 같은 폼을 그린다."""
    return {
        "fixtures": _fixture_names("compose"),
        "max_text_len": PARAMS.max_text_len,
        "ad_formats": _AD_FORMATS,
        **(extra or {}),
    }


def _lands(s) -> str:  # noqa: ANN001
    """이 문장을 지면에 얹어도 되는가 — `ok`(통과) · `unsure`(확인 필요 표시를 달고 얹는다) · `ng`(얹지 않는다).

    🚨 **얹는 기준은 여기 한 곳이다** (D-99). 판정은 코어가 한다 — 여기서는 그 결과를 읽기만 한다 (D-119).
    ⚠️ 2026-10-12 (ksr · 권소라 결정) — 코어 1판은 사전이 침묵하면 통과가 아니라 **보류(확신 부족)** 를 낸다 (D-269).
       「확정이 아니면 얹지 않는다」(D-63)를 그대로 걸면 어떤 문구도 편집기에 못 들어간다. 그래서 **유형 후보가 없는
       확신 부족 보류**만 `unsure` 로 얹고 화면이 「확인 필요」를 단다. 엄격하게 되돌리려면 그 가지를 `ng` 로 바꾼다.
    """
    if is_pass(s) or s.not_claim:
        return "ok"
    if s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf and not s.violations:
        return "unsure"
    return "ng"


#: 얹지 못하는 까닭 — 🚨 검수 화면(review.html)과 **같은 말**을 쓴다 (2026-10-01 판정 문구 확정)
_INFEASIBLE_WHY = {"A": "인정받은 제품만 가능", "B": "객관적인 근거 자료 필요", "C": "사용 불가"}
_HOLD_WHY = {
    "low_conf": "확신 부족",
    "gap2": "코드·모델 2등급 차",
    "cat_unknown": "품목 선택 필요",
    "rd1": "공존 규칙 발동",
    "premise_unknown": "전제 선택 필요 — 인정 여부",
    "law_uncovered": "전용법 미검수",
}


def _why_blocked(s) -> str:  # noqa: ANN001
    types = " · ".join(v.value.replace("_", " ") for v in s.violations)
    if s.verdict is Verdict.confirmed:
        head = _INFEASIBLE_WHY.get(s.infeasibility.value if s.infeasibility else "", "위반 확정")
    elif s.verdict is Verdict.hold:
        head = "보류 — " + _HOLD_WHY.get(s.hold_reason.value if s.hold_reason else "", "사유 없음")
    elif s.verdict is Verdict.no_basis:
        head = "근거 없음"
    else:
        head = "미판정"
    return f"{head} ({types})" if types else head


def _compose_origin(form: dict[str, list[str]]) -> dict:
    """카피 생성에서 넘어온 **분기**와 **인정 · 심사 문구** (🆕 2026-10-13). 없거나 모르는 값이면 빈 것이다.

    ★ 분기를 알면 판정에 품목을 넘긴다(식품 · 건강기능식품 · 화장품 · 인정 여부) — 품목 없이 뭉뚱그려 판정하지 않는다.
    ★ 인정 · 심사 문구는 **판정에서 뺀다** — 생성 단계와 같은 규칙이다(`copygen.pipeline`). 그 문구는 인정받은 글자 그대로라
       유형 후보로 걸리면 인정 제품의 광고가 전부 막힌다(10-03 실측 · 10-13 화면에서 재현).
    🚨 인정 문구는 **이용자가 적은 값이고 확인되지 않았다** — 화면이 그렇게 적는다 (D-263 ③ 「사업자가 선택한 값」).
       ⛔ 인정 문구가 필요 없는 분기에서는 읽지 않는다 — 아무 문구나 「인정 문구」라며 판정에서 빼지 못하게.
    """
    from app.routers.copygen import BRANCHES  # noqa: PLC0415

    key = _one(form, "branch", 16)
    fixed = _one(form, "fixed", _GEN_LIMITS["fixed"]).strip()
    branch = BRANCHES.get(key)
    if branch is None:
        return {"branch": "", "fixed": "", "label": "", "product": None}
    from app.contracts import ProductContext  # noqa: PLC0415

    return {
        "branch": key,
        "fixed": fixed if branch.needs_fixed else "",
        "label": branch.label,
        "product": ProductContext(
            category=Category(branch.category), has_recognized_function=branch.recognized
        ),
    }


def _judged_part(text: str, fixed: str) -> str:
    """판정에 넣을 글자 — 인정 · 심사 문구를 뺀 나머지."""
    return text.replace(fixed, " ").strip() if fixed else text


@router.get("/compose", response_class=HTMLResponse)
def compose_page(request: Request) -> HTMLResponse:
    """광고 초안 입력 화면 (`draft-setup`, ksr 2026-09-13). 구 `/u/draft-setup`·`/u/draft-editor`
    (빈 골격)를 대체한다.
    """
    return _render(request, "user/compose.html", _compose_ctx())


@router.post("/compose", response_class=HTMLResponse)
async def compose(request: Request) -> HTMLResponse:
    """광고 생성 — 적은 문구를 **판정 코어에 먼저 통과시키고**, 얹을 수 있으면 섹션 편집기를 그린다 (ksr 2026-10-12).

    🚨 코어 `POST /compose`(템플릿 엔진)는 아직 501 이다 — 부르지 않는다. 섹션 골격은 화면(`user_compose.js`)이 깔고,
       **문구 판정만 코어 `/judge` 와 같은 함수**를 부른다 (`_core_judge` · D-119). 가짜 판정을 만들지 않는다 (D-147).
    ★ 후보 카드(「AI 광고 생성 →」)는 `carry` 를 달고 온다. 그때는 제출이 아니라 **문구를 채운 입력 화면**을 그린다.
    ★ 얹지 못하는 문장이 있으면 편집기를 열지 않고 그 판정을 그린다 (`_lands`). 엔진이 없으면 「준비 중」을 그린다.
    """
    form = await _form(request)
    prompt = _one(form, "prompt", PARAMS.max_text_len)
    note = _one(form, "note", PARAMS.max_text_len)
    origin = _compose_origin(form)
    if form.get("carry"):
        return _render(
            request,
            "user/compose.html",
            _compose_ctx({"carried": {"prompt": prompt, "note": note}, "origin": origin}),
        )
    ad_format = _one(form, "ad_format", 32)
    if ad_format not in _AD_FORMATS:
        raise HTTPException(
            422, "그런 광고 종류가 없다 — SNS 피드 · 상세페이지 · 배너 중에서 고른다"
        )
    picked = {"ad_format": ad_format, "prompt": prompt, "note": note}
    base = {"picked": picked, "origin": origin}
    if not prompt.strip():
        return _render(
            request,
            "user/compose.html",
            _compose_ctx({**base, "errors": ["광고에 담을 문구를 적어 주세요."]}),
        )
    # 🆕 2026-10-13 — 인정 · 심사 문구가 그 문구에 그대로 들어 있을 때만 뺀다. 문구를 고쳐 인정 문구가 깨졌으면 전부 판정한다
    fixed = origin["fixed"] if origin["fixed"] and origin["fixed"] in prompt else ""
    part = _judged_part(prompt, fixed)
    if not part:
        return _render(
            request,
            "user/compose.html",
            _compose_ctx(
                {**base, "errors": ["인정 · 심사 문구 말고 광고에 담을 문구를 더 적어 주세요."]}
            ),
        )
    status, result = _core_judge(part, origin["product"])
    if status != "ok":
        return _render(
            request,
            "user/compose.html",
            _compose_ctx({**base, "engine_pending": True, "engine_down": status == "down"}),
        )
    lands = [_lands(s) for s in result.sentences]
    if "ng" in lands:
        return _render(
            request,
            "user/compose.html",
            _compose_ctx(
                {
                    **base,
                    "screening": result.sentences,
                    "blocked": lands.count("ng"),
                    #: 얹을 수 있는 문장(확인 필요) — 화면이 「배치되지 않아요」를 이 문장에는 적지 않는다
                    "unsure_ids": {
                        s.sent_id
                        for s, how in zip(result.sentences, lands, strict=True)
                        if how == "unsure"
                    },
                }
            ),
        )
    if fixed:
        # 인정 문구가 든 문구는 **통째로** 얹는다 — 문장으로 쪼개면 인정 문구가 빠진다. 표시는 나머지 글자의 판정을 따른다
        # 🔄 2026-10-13 (ohb 흡수) — 인정 문구는 **이용자가 적은 값이고 판정하지 않은 글자**다. 그 문구를 뺀 나머지가 통과해도
        #    「판정 통과」로 그리지 않는다 — 늘 「확인 필요」다. 아무 글자나 「인정 문구」라며 판정에서 빼 통과를 얻지 못하게 (D-147 · D-220)
        copy = [{"text": prompt.strip(), "unsure": True}]
    else:
        copy = [
            {"text": s.text, "unsure": how == "unsure"}
            for s, how in zip(result.sentences, lands, strict=True)
        ]
    draft = {
        **_AD_FORMATS[ad_format],
        "label": ad_format,
        #: 판정을 지난 문장들 — 화면이 첫 문장을 헤드라인에, 나머지를 보조 문구에 얹는다
        "copy": copy,
        "note": note.strip(),
        "max_text_len": PARAMS.max_text_len,
        #: 편집기의 칸 판정이 같은 품목 · 같은 인정 문구로 돌게 넘긴다 (`/u/compose/judge`)
        "branch": origin["branch"],
        "fixed": origin["fixed"],
    }
    return _render(request, "user/compose.html", _compose_ctx({**base, "draft": draft}))


@router.post("/compose/judge")
async def compose_judge(request: Request) -> JSONResponse:
    """편집기의 문구 한 칸을 판정한다 — 고친 문구는 판정을 지나야 지면에 얹힌다 (D-63 · D-119).

    ★ 본문은 JSON `{"text": …}` 이다. 🔴 **POST 다** — 문구를 주소에 싣지 않는다 (P1-4).
       🆕 2026-10-13 — `branch` · `fixed` 를 같이 받으면 그 품목으로 판정하고 인정 · 심사 문구는 뺀다 (`_compose_origin`).
    ★ 응답 `state` — `ok` · `unsure`(확인 필요) · `ng`(얹지 않는다) · `pending`(엔진 미착수) · `down`(엔진 연결 실패).
       `ng` 면 `notes` 에 걸린 문장과 까닭을 싣는다. 화면이 글자로 그린다(문자열 조립 금지 · P2-9).
    """
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "JSON 본문만 받는다")
    body = await read_capped(
        request, _MAX_BODY, f"본문이 너무 크다 — {_MAX_BODY} 바이트까지 받는다"
    )
    try:
        data = json.loads(body.decode("utf-8"))
        text = data["text"]
        origin = _compose_origin(
            {k: [data[k]] for k in ("branch", "fixed") if isinstance(data.get(k), str)}
        )
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, "본문은 text 칸 하나를 가진 JSON 이다") from e
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(422, "text 가 비었다")
    if len(text) > PARAMS.max_text_len:
        raise HTTPException(422, f"text 가 너무 길다 — {PARAMS.max_text_len}자까지 받는다")
    fixed = origin["fixed"] if origin["fixed"] and origin["fixed"] in text else ""
    part = _judged_part(text, fixed)
    if not part:
        # 인정 문구뿐이다 — 판정할 글자가 없다. 이용자가 적은 값이라 「확인 필요」로 얹는다
        return JSONResponse({"state": "unsure", "notes": []})
    status, result = _core_judge(part, origin["product"])
    if status != "ok":
        return JSONResponse({"state": status, "notes": []})
    lands = [_lands(s) for s in result.sentences]
    notes = [
        {"text": s.text, "why": _why_blocked(s)}
        for s, how in zip(result.sentences, lands, strict=True)
        if how == "ng"
    ]
    # 🔄 2026-10-13 (ohb 흡수) — 인정 문구를 뺐으면 「통과」가 아니라 「확인 필요」다 (위 `compose` 와 같은 규칙 · D-147)
    state = "ng" if notes else ("unsure" if fixed or "unsure" in lands else "ok")
    return JSONResponse({"state": state, "notes": notes})


@router.get("/compose/preview/{name}", response_class=HTMLResponse)
def compose_preview(request: Request, name: str) -> HTMLResponse:
    """광고 골든 픽스처 하나를 **결과 화면으로** 그린다 (D-124 ③).

    ⛔ 파일을 그대로 흘리지 않는다 — `ComposeResponse` **계약을 통과시켜** 낸다.
       🚨 그 계약이 「광고」 표시 섹션이 없는 응답을 **거부한다** (D-93 · D-164) —
          화면이 아니라 여기서 먼저 걸린다.
    """
    from app.contracts import ComposeResponse  # noqa: PLC0415

    raw = _fixture_path("compose", name).read_text(encoding="utf-8")
    return _render(
        request,
        "user/compose.html",
        _compose_ctx({"result": ComposeResponse.model_validate_json(raw), "fixture_name": name}),
    )


# ══════════════════════════════════════════════════════════════════════
#  이력 · 사용설명 · 나머지
# ══════════════════════════════════════════════════════════════════════

#: D-127 — 판정 상태 4종. history 필터가 받는 값은 이 넷뿐이다.
_VERDICTS = ("confirmed", "hold", "no_basis", "unjudged")
_PAGE_SIZE = 20


def _owned_judgments(owner_id: uuid.UUID) -> Select:
    """🔴 **내 판정만** (P1-5) — `judgment.doc_id` → `work_doc.owner_id` 로 거른다.

    홈 집계·최근 이력·이력 목록이 모두 이것에서 출발한다 — 소유자 조건을 화면마다 따로 적지 않는다.
    🔴 2026-10-01 — **비회원 검수는 이력에 쌓이지 않는다** (D-69 「비회원 … 이력 없음」 · 권소라 결정).
       비회원 문서(`owner_id` NULL · `session_id` + `expires_at`, D-129)는 여기 안 걸린다 — 그 키는 **지울 키**이지 이력 키가 아니다.
    ⛔ `session_id` 로 이력을 읽거나, 로그인·가입할 때 그 세션의 문서에 `owner_id` 를 채워 넣지 않는다 — 이력은 로그인한 뒤 검수한 것부터다.
    """
    return (
        select(Judgment)
        .join(WorkDoc, WorkDoc.id == Judgment.doc_id)
        .where(WorkDoc.owner_id == owner_id)
    )


def _history_rows(
    session: Session, owner_id: uuid.UUID, verdict: str | None, page: int
) -> tuple[list, int]:
    """이력 한 쪽의 행과 전체 건수. `judgment` × `copy_sentence` 조인 (ksr 원문 조인 · lse 필터·페이지)."""
    stmt = (
        _owned_judgments(owner_id)
        .add_columns(CopySentence.raw)
        .join(CopySentence, CopySentence.id == Judgment.subject_id)
        .where(Judgment.subject_type == "copy_sentence")
    )
    if verdict:
        stmt = stmt.where(Judgment.verdict == verdict)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    raw_rows = session.execute(
        stmt.order_by(Judgment.judged_at.desc()).limit(_PAGE_SIZE).offset((page - 1) * _PAGE_SIZE)
    ).all()
    rows = [
        SimpleNamespace(
            id=j.id,
            judged_at=j.judged_at,
            verdict=j.verdict,
            hold_reason=j.hold_reason,
            risk_final=j.risk_final,
            law_version=j.law_version,
            text=raw,
        )
        for j, raw in raw_rows
    ]
    return rows, total


@router.get("/history", response_class=HTMLResponse)
def history(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
    verdict: str | None = None,
    page: int = 1,
    open_id: str | None = None,
) -> HTMLResponse:
    """검수 이력 — 🚨 **DB 에 직접 붙는 첫 화면**이다 (2026-09-13 한빈님 확인).

    🔄 2026-09-16 — `Judgment` × `CopySentence` 조인(ksr)으로 **판정 원문**까지 보여준다.
       필터(`verdict`)·페이지네이션(`page`)·상세 토글(`?open_id=`)은 lse 것을 그대로 쓴다.
    ⬜ 판정 결과를 `judgment` 표에 저장하는 코드가 아직 없어 표는 비어 있다 — 그래서 지금은 빈 목록으로 뜬다.
       (판정 자체는 돈다 — `/u/judge` 가 코어를 부른다. 그 결과를 적는 자리가 없다.)
       가짜 행을 만들어 채우지 않는다 (D-147 의 정신과 같다).
    ⛔ **`page`·`verdict` 는 사용자가 URL 을 손으로 바꿀 수 있다** — 잘못된 값으로
       500 을 내지 않고 조용히 안전한 기본값(1 페이지·전체)으로 되돌린다.
    ⬜ 근거(evidence)·질의응답은 디자인엔 있지만 이번엔 뺐다 — QnA 를 저장할 테이블이
       아직 없다. 원문·결론·위험도·법령 버전만 보여준다.
    🔴 2026-09-29 — **로그인한 사람 것만** 보여 준다 (보안점검 P1-5 · `_owned_judgments`).
       로그아웃이면 리다이렉트하지 않고 로그인 안내를 그린다(200) — `/u/cs` 와 같다(D-66).
       DB 가 없으면 로그인 여부를 알 수 없으니 「DB 없음」 안내가 먼저다 (D-72).
    """
    page = max(page, 1)
    if verdict not in (None, *_VERDICTS):
        verdict = None
    db_down = not reachable(session)
    user = None if db_down else current_user(request, session)
    if not db_down and user is None:
        return _render(request, "user/history.html", {"need_login": True})
    rows, total = ([], 0) if user is None else _history_rows(session, user.id, verdict, page)
    opened = next((r for r in rows if str(r.id) == open_id), None) if open_id else None
    return _render(
        request,
        "user/history.html",
        {
            # 🚨 못 붙었으면 빈 목록을 「기록 없음」으로 그리지 않는다 — 못 읽은 것이다 (D-72).
            "db_down": db_down,
            "judgments": rows,
            "verdicts": _VERDICTS,
            "verdict": verdict,
            "page": page,
            "has_prev": page > 1,
            "has_next": page * _PAGE_SIZE < total,
            "base_qs": f"&verdict={verdict}" if verdict else "",
            "opened": opened,
        },
    )


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request, tab: str = "guide") -> HTMLResponse:
    """copylane 소개 (ksr 2026-09-13) — `tab`(guide·faq)이 "사용방법"·"자주 묻는 질문"
    사이드바 두 항목을 가른다. ⛔ 탭 전환을 스크립트로 하지 않는다 (CSP) — 쿼리스트링으로
    서버가 고른다.
    """
    if tab not in ("guide", "faq"):
        tab = "guide"
    return _render(request, "user/help.html", {"tab": tab}, active_sub=tab)


@router.get("/matching", response_class=HTMLResponse)
def matching(request: Request) -> HTMLResponse:
    """매칭 — ★ **골격만**. 하위 화면 넷은 홀딩이라 이 구역은 아직 사이드바가 없다."""
    return _render(request, "user/matching.html")


# ══════════════════════════════════════════════════════════════════════
#  고객센터 — 문의 접수 · 내 문의 목록 · 상세 (D-260 ③ · ksr 2026-09-29 · 프로토타입 v7.2 cs · cs-detail)
# ══════════════════════════════════════════════════════════════════════
#: 🚨 로그인한 사용자만 접수한다(`ticket.requester_id` NOT NULL — 비회원 문의는 범위 밖 · 설계초안 09-22 §4).
#: 🔴 **내 문의만** 본다 — 조회 조건에 `requester_id = 나` 를 건다. 남의 것은 없는 것과 같은 404 (보안점검 P1-5).
#: ⛔ 판정 원문을 붙이거나 판정 id 를 링크하는 칸이 없다 — 화면은 「광고 문구 원문을 붙여 넣지 마세요」를 안내한다 (D-76 · D-260 ③).
#: ⬜ 스키마에 없는 프로토타입 요소는 비활성 + 사유 — 우선순위 선택(관리자가 매긴다) · 첨부 · 추가 문의(스레드) ·
#:    사용자 「문의 종료하기」(팀장 승인 요청 5번). 2026-09-29 권소라 결정.

_CS_BODY = (
    TICKET_TEXT_MAX * 16
)  # 한글은 퍼센트 인코딩으로 글자당 9바이트 — `_MAX_BODY` 와 같은 여유
_CS_TITLE_MAX = 100  # `ticket.title` String(100)
#: 목록 상태 묶음 — 프로토타입 통계 「처리 중」은 아직 안 닫힌 것 전부다(미처리 + 처리중)
_CS_DONE = "closed"


def _ticket_no(session: Session, t: Ticket) -> str:
    """표시 번호 `TK-YYMMDD-NN` — 🚨 **저장하지 않고 보여 줄 때 만든다** (설계초안 09-22 §4 · `Ticket` docstring).

    ★ 접수일(한국 시간) + 그날 몇 번째 문의인지. 같은 날의 순번은 전체 문의 기준이라 관리자 화면과 같은 번호를 쓸 수 있다.
    """
    local = t.created_at.astimezone(_KST)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    n = session.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.created_at >= start, Ticket.created_at <= t.created_at)
    )
    return f"TK-{local:%y%m%d}-{n or 1:02d}"


def _render_form(
    request: Request, template: str, ctx: dict, status_code: int = 200
) -> HTMLResponse:
    """구역 셸 화면 + CSRF 이중 제출(쿠키와 폼 양쪽). 로그인 뒤 쓰기 화면이 쓴다 (P1-7)."""
    token = auth.new_csrf()
    resp = _render(request, template, {**ctx, "csrf_token": token, "csrf_field": auth.CSRF_FIELD})
    resp.status_code = status_code
    resp.set_cookie(auth.CSRF_COOKIE, token, **_cookie_kwargs(request))  # type: ignore[arg-type]
    return resp


def _cs_list_ctx(session: Session, user: UserAccount) -> dict:
    rows = (
        session.execute(
            select(Ticket).where(Ticket.requester_id == user.id).order_by(Ticket.created_at.desc())
        )
        .scalars()
        .all()
    )
    tickets = [
        SimpleNamespace(
            id=t.id,
            no=_ticket_no(session, t),
            title=t.title,
            category=TICKET_CATEGORIES.get(t.category, t.category),
            priority=t.priority,
            priority_label=TICKET_PRIORITIES.get(t.priority, t.priority),
            status=t.status,
            status_label=TICKET_STATUSES.get(t.status, t.status),
            at=t.created_at.astimezone(_KST).strftime("%m.%d"),
            replied=t.reply is not None,
        )
        for t in rows
    ]
    return {
        "tickets": tickets,
        "stat_total": len(tickets),
        "stat_open": sum(1 for t in tickets if t.status != _CS_DONE),
        "stat_done": sum(1 for t in tickets if t.status == _CS_DONE),
        "categories": TICKET_CATEGORIES,
        "body_max": TICKET_TEXT_MAX,
        "title_max": _CS_TITLE_MAX,
    }


@router.get("/cs", response_class=HTMLResponse)
def cs(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:  # noqa: B008
    """고객센터 문의 — 각 구역 사이드바 하단 「CS 문의」 버튼으로 들어온다 (구역 밖).

    ⛔ 로그아웃 상태면 리다이렉트하지 않고 로그인 안내를 그린다(200) — 로그인 벽을 세우지 않는다(D-66).
    """
    user = current_user(request, session)
    if user is None:
        return _render(request, "user/cs.html", {"need_login": True})
    return _render_form(request, "user/cs.html", {**_cs_list_ctx(session, user), "form": {}})


@router.post("/cs")
async def cs_post(request: Request, session: Session = Depends(get_session)):  # noqa: B008
    """문의 접수 → 그 문의 상세로 (PRG). 🚨 본문 상한은 **자르지 않고 거부**한다 (`TICKET_TEXT_MAX` · D-220)."""
    user = current_user(request, session)
    if user is None:
        return RedirectResponse("/u/login", status_code=303)
    body_raw = await read_capped(request, _CS_BODY, "본문이 너무 크다")
    form = parse_qs(body_raw.decode("utf-8", "replace"), keep_blank_values=True)
    category = form.get("category", [""])[0]
    title = (form.get("title", [""])[0] or "").strip()
    body = (form.get("body", [""])[0] or "").strip()
    kept = {"category": category, "title": title, "body": body}

    def again(msg: str, code: int = 422) -> HTMLResponse:
        ctx = {**_cs_list_ctx(session, user), "form": kept, "error": msg, "open_form": True}
        return _render_form(request, "user/cs.html", ctx, code)

    if not auth.csrf_ok(request.cookies.get(auth.CSRF_COOKIE), form.get(auth.CSRF_FIELD, [""])[0]):
        return again("화면이 오래돼서 다시 불러왔어요. 한 번 더 접수해 주세요.", 403)
    if category not in TICKET_CATEGORIES:
        return again("문의 유형을 골라 주세요.")
    if not title or len(title) > _CS_TITLE_MAX:
        return again(f"제목을 1~{_CS_TITLE_MAX}자로 적어 주세요.")
    if not body or len(body) > TICKET_TEXT_MAX:
        return again(f"문의 내용을 1~{TICKET_TEXT_MAX:,}자로 적어 주세요.")

    ticket = Ticket(requester_id=user.id, category=category, title=title, body=body)
    session.add(ticket)
    session.commit()
    auth.audit("user_ticket", _actor(user.id), ok=True)
    return RedirectResponse(f"/u/cs/{ticket.id}", status_code=303)


@router.get("/cs/{ticket_id}", response_class=HTMLResponse)
def cs_detail(request: Request, ticket_id: str, session: Session = Depends(get_session)):  # noqa: B008
    """문의 상세 (프로토타입 `cs-detail`). 🔴 **내 문의가 아니면 없는 것과 같은 404** (P1-5)."""
    user = current_user(request, session)
    if user is None:
        return RedirectResponse("/u/login", status_code=303)
    try:
        tid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(404, "그런 문의가 없다") from None
    t = session.scalar(select(Ticket).where(Ticket.id == tid, Ticket.requester_id == user.id))
    if t is None:
        raise HTTPException(404, "그런 문의가 없다")
    # 🆕 알림 — 상세를 열면 이 문의의 알림(답변 · 완료)은 읽은 것이다. 이 화면의 벨부터 꺼져 있게 먼저 반영한다.
    key = _ticket_alert_key(t)
    me = _nav_user(request)
    if me is not None and key is not None:
        for n in me.notifs:
            if n.kind == "alert" and n.key == key:
                n.unread = False
        me.unread = sum(1 for n in me.notifs if n.unread)
        me.cs_unread = any(n.unread and n.kind == "alert" for n in me.notifs)
    resp = _render(
        request,
        "user/cs_detail.html",
        {
            "me": me,
            "t": t,
            "no": _ticket_no(session, t),
            "category": TICKET_CATEGORIES.get(t.category, t.category),
            "priority_label": TICKET_PRIORITIES.get(t.priority, t.priority),
            "status_label": TICKET_STATUSES.get(t.status, t.status),
            "at": t.created_at.astimezone(_KST).strftime("%Y.%m.%d %H:%M"),
            "closed_at": t.closed_at.astimezone(_KST).strftime("%Y.%m.%d") if t.closed_at else None,
            "requester": user.name,
            "retention_days": TICKET_RETENTION_DAYS,
        },
    )
    if key is not None:
        _remember_seen(resp, request, [key])
    return resp


#: 마이페이지가 받는 필드와 글자 상한. 🚨 **상한을 자르지 않고 거부한다** (D-72).
#: 🚨 이메일은 여기 없다 — 계정 이메일 변경은 범위 밖이다(설계초안 09-22 · 권소라).
_MYPAGE_FIELDS = {
    "name": 40,
    "org": 60,
    "age": 16,
    "sex": 8,
    "channel": 16,
    "category": 16,
}
_MYPAGE_BLANK = dict.fromkeys(_MYPAGE_FIELDS, "")


#: 마이페이지 가로 탭 (key, label). 프로토타입의 포트폴리오 · 구성원 관리 · 결제 탭은
#: 매칭/과금 범위라 뺐다. ⛔ 탭 전환을 스크립트로 하지 않는다 (CSP) — `?tab=` 으로 고른다.
_MYPAGE_TABS: tuple[tuple[str, str], ...] = (
    ("profile", "프로필"),
    ("defaults", "광고 기본값"),
    ("account", "계정"),
)
_MYPAGE_SECTION_TAB = {"profile": "profile", "adprefs": "defaults", "consent": "account"}
#: 계정을 끌 때 정확히 이렇게 입력해야 한다 — 실수로 끄는 것을 막는 확인 문구다.
_MYPAGE_DISABLE_CONFIRM = "끄기"


def _mypage_picked(user: UserAccount) -> dict[str, str]:
    return {**_MYPAGE_BLANK, "name": user.name, "org": user.org or ""}


def _mypage_ctx(user: UserAccount, tab: str, **extra: object) -> dict[str, object]:
    return {
        "tab": tab,
        "tabs": _MYPAGE_TABS,
        "picked": _mypage_picked(user),
        "email": user.email,
        "consent_history": user.consent_history_at is not None,
        "consent_improve": user.consent_improve_at is not None,
        **extra,
    }


@router.get("/mypage", response_class=HTMLResponse)
def mypage(
    request: Request,
    tab: str = "profile",
    session: Session = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    """마이페이지 — 프로필 · 광고 기본값 · 계정 탭 (ksr 2026-09-13 · lse 2026-09-29 저장 배선).

    🔴 로그인해야 들어온다 — 채울 계정이 없으면 프로필도 없다 (cs_detail 과 같은 문).
    ⛔ 광고 기본값(나이·성별·매체·물품)은 아직 저장하지 않는다 — `user_ad_preference` 표가
       없다 (팀장 승인 요청 #7, 2026-09-29). 프로필 · 동의 · 계정 끄기는 `user_account`
       에 이미 있는 칸(D-96 · disabled_at)이라 바로 저장한다.
    """
    user = current_user(request, session)
    if user is None:
        return RedirectResponse("/u/login", status_code=303)
    if tab not in dict(_MYPAGE_TABS):
        tab = "profile"
    return _render_form(request, "user/mypage.html", _mypage_ctx(user, tab))


@router.post("/mypage", response_class=HTMLResponse)
async def mypage_save(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:  # noqa: B008
    """마이페이지 저장 — 섹션마다 갈린다 (2026-09-29).

    🔴 `profile` · `consent` 는 `user_account` 에 실제로 쓴다. `adprefs`(광고 기본값)는
       아직 **저장하지 않는다** — 담을 표가 없다(팀장 승인 요청 #7). 가짜 성공을 그리지
       않는다(D-147) — 그 섹션만 「아직 저장되지 않았어요」로 되돌린다.
    """
    user = current_user(request, session)
    if user is None:
        return RedirectResponse("/u/login", status_code=303)
    form = await _form(request)
    section = _one(form, "section", 16) or "profile"
    tab = _MYPAGE_SECTION_TAB.get(section, "profile")

    if not auth.csrf_ok(request.cookies.get(auth.CSRF_COOKIE), form.get(auth.CSRF_FIELD, [""])[0]):
        return _render_form(
            request,
            "user/mypage.html",
            _mypage_ctx(
                user, tab, error="화면이 오래돼서 다시 불러왔어요. 한 번 더 저장해 주세요."
            ),
            403,
        )

    if section == "profile":
        name = _one(form, "name", _MYPAGE_FIELDS["name"]).strip()
        org = _one(form, "org", _MYPAGE_FIELDS["org"]).strip()
        if not name:
            return _render_form(
                request,
                "user/mypage.html",
                {
                    **_mypage_ctx(user, tab),
                    "picked": {**_mypage_picked(user), "name": name, "org": org},
                    "error": "이름을 입력해 주세요.",
                },
                422,
            )
        user.name = name
        user.org = org or None
        session.commit()
        auth.audit("user_profile_save", _actor(user.id), ok=True)
        return _render_form(request, "user/mypage.html", _mypage_ctx(user, tab, saved=True))

    if section == "consent":
        c1 = bool(_one(form, "consent_history", 8))
        c2 = bool(_one(form, "consent_improve", 8))
        if c2 and not c1:
            return _render_form(
                request,
                "user/mypage.html",
                _mypage_ctx(user, tab, error="②는 ①에 동의해야 고를 수 있어요."),
                422,
            )
        now = datetime.now(UTC)
        user.consent_history_at = now if c1 else None
        user.consent_improve_at = now if c2 else None
        session.commit()
        auth.audit("user_consent_save", _actor(user.id), ok=True)
        return _render_form(request, "user/mypage.html", _mypage_ctx(user, tab, saved=True))

    # adprefs — 나머지는 아직 담을 표가 없다 (승인 요청 #7)
    picked = {**_mypage_picked(user)}
    for k in ("age", "sex", "channel", "category"):
        picked[k] = _one(form, k, _MYPAGE_FIELDS[k])
    return _render_form(
        request,
        "user/mypage.html",
        {**_mypage_ctx(user, tab), "picked": picked, "saved_attempt": True},
    )


@router.post("/mypage/disable", response_class=HTMLResponse)
async def mypage_disable(request: Request, session: Session = Depends(get_session)):  # noqa: B008
    """계정 끄기 — 지우지 않고 켠다/끈다(`disabled_at`, D-260). 확인 문구를 정확히 입력해야 한다.

    🔴 삭제가 아니다 — `work_doc.owner_id` 등 이 계정을 가리키는 행이 남아야 한다(모델 docstring).
       끈 뒤에는 로그아웃도 같이 한다 — 쿠키만 지운다(D-213), 서버 세션은 원래 없다.
    """
    user = current_user(request, session)
    if user is None:
        return RedirectResponse("/u/login", status_code=303)
    form = await _form(request)
    if not auth.csrf_ok(request.cookies.get(auth.CSRF_COOKIE), form.get(auth.CSRF_FIELD, [""])[0]):
        return _render_form(
            request,
            "user/mypage.html",
            _mypage_ctx(
                user, "account", error="화면이 오래돼서 다시 불러왔어요. 한 번 더 해 주세요."
            ),
            403,
        )
    confirm = _one(form, "confirm", 20)
    if confirm != _MYPAGE_DISABLE_CONFIRM:
        return _render_form(
            request,
            "user/mypage.html",
            _mypage_ctx(
                user,
                "account",
                error=f"확인 문구가 맞지 않아요. 「{_MYPAGE_DISABLE_CONFIRM}」라고 정확히 입력해 주세요.",
            ),
            422,
        )
    user.disabled_at = datetime.now(UTC)
    session.commit()
    auth.audit("user_account_disable", _actor(user.id), ok=True)
    resp = RedirectResponse("/u/landing", status_code=303)
    resp.delete_cookie(auth.USER_SESSION_COOKIE, path="/")
    return resp


# ══════════════════════════════════════════════════════════════════════
#  계정 — 가입 · 로그인 · 로그아웃 (D-260 ② ⑧ · D-66 · D-213 · ksr 2026-09-29)
# ══════════════════════════════════════════════════════════════════════
#: 🔴 논리는 `app/auth.py` 가 든다(해시 · 세션 서명 · 시도 제한 · CSRF · 접속기록) — 여기는 껍데기다 (D-99).
#:    관리자 로그인(`app/routers/auth.py`)과 **같은 순서**로 막는다: 본문 상한 → CSRF → 시도 제한 → 해시.
#: 🚨 사용자 세션은 **쿠키가 따로다** — `copylane_user` · 값 `u:<id>` (D-260 세션 (가)). 관리자 쿠키를 안 만진다.
#: ⛔ 로그인 벽을 세우지 않는다 — 검수(진입점 A)는 가입 없이 쓴다 (D-66). 홈·이력은 로그아웃 상태로도 200 이다(게이트).

#: 본문 상한 — 이름 · 이메일 · 비밀번호 둘 · 체크박스 · 토큰뿐이다 (P2-11)
_ACCOUNT_BODY = 4096
_NAME_MAX = 40  # `user_account.name` String(40)
_EMAIL_MAX = 120  # `user_account.email` String(120)
#: 🚨 비밀번호 길이 — 하한은 프로토타입 「8자 이상」. 상한은 Argon2 에 긴 입력을 먹이는 자원 고갈을 막는다 (P2-11).
_PW_MIN = 8
_PW_MAX = 128
#: 약관이 아직 한 건도 없을 때 `terms_version` 에 적는 값 — 🚨 **지어낸 버전이 아니라 사실**이다.
#:    2026-09-29 권소라 판단(약관 표가 비어 있는 동안 팀·시험 계정을 받는다). 팀장 승인 요청에 올렸다.
_TERMS_UNREGISTERED = "미등록"
#: 🚨 `terms_version` 칸은 하나인데 약관은 세 종류다 — 어느 것을 적는지 정한 문서가 없어 **서비스 이용약관**으로 둔다(승인 요청).
_TERMS_KIND_RECORDED = "service"
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _cookie_kwargs(request: Request) -> dict[str, object]:
    """쿠키 옵션 — 관리자 쪽(`app/routers/auth.py`)과 같은 값이다 (보안점검 P1-7).

    🚨 `Secure` 는 HTTPS 일 때만 — 로컬 http 에서 무조건 켜면 쿠키가 안 실려 로그인이 조용히 안 된다.
    ⛔ 그 모듈을 import 하지 않는다 — 클라우드 에디션에서는 관리자 로그인이 안 붙는다 (D-213).
    """
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": request.url.scheme == "https",
        "path": "/",
    }


def _actor(user_id: object | None = None, email: str = "") -> str:
    """접속기록의 「누가」. 🚨 **이메일 원문을 로그에 남기지 않는다** — 로그 가림(`logging_conf`)에 email 키가 없다.

    성공은 계정 id, 실패는 이메일 해시 앞 10자리(같은 이메일의 반복 실패를 묶어 볼 수 있다).
    """
    if user_id is not None:
        return f"u:{user_id}"
    if not email:
        return "u?-"
    return "u?" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:10]


def _auth_page(
    request: Request, template: str, ctx: dict | None = None, status_code: int = 200
) -> HTMLResponse:
    """로그인·가입 화면. 🚨 CSRF 토큰을 **쿠키와 폼 양쪽에** 심는다 (이중 제출 · P1-7)."""
    token = auth.new_csrf()
    ctx = {**(ctx or {}), "csrf_token": token, "csrf_field": auth.CSRF_FIELD}
    resp = templates.TemplateResponse(request, template, ctx, status_code=status_code)
    resp.set_cookie(auth.CSRF_COOKIE, token, **_cookie_kwargs(request))  # type: ignore[arg-type]
    return resp


async def _account_form(request: Request) -> dict[str, list[str]]:
    body = await read_capped(request, _ACCOUNT_BODY, "본문이 너무 크다")
    return parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)


def current_user(request: Request, session: Session) -> UserAccount | None:
    """로그인한 사용자. 없거나 · 서명이 틀리거나 · 만료거나 · **꺼진 계정**이면 `None`.

    🚨 세션은 서버에 없는 서명 쿠키라 계정을 꺼도(`disabled_at`) 만료까지 들어온다 — 그래서 **요청마다 DB 를 본다**
       (관리자 쪽 `account_active` 와 같은 이유). ⛔ DB 가 없으면 로그인 안 된 것으로 본다 — 통과가 아니다 (D-220).
    """
    uid = auth.read_user_session(request.cookies.get(auth.USER_SESSION_COOKIE))
    if uid is None or not reachable(session):
        return None
    user = session.get(UserAccount, uid)
    if user is None or user.disabled_at is not None:
        auth.audit("user_session_disabled", _actor(uid), ok=False)
        return None
    return user


def _terms_version(session: Session) -> str:
    """지금 시행 중인 서비스 이용약관 버전. 없으면 「미등록」(지어내지 않는다 · D-220)."""
    today = datetime.now(UTC).date()
    row = session.scalar(
        select(Terms.version)
        .where(Terms.kind == _TERMS_KIND_RECORDED, Terms.effective_on <= today)
        .order_by(Terms.effective_on.desc(), Terms.created_at.desc())
        .limit(1)
    )
    return row or _TERMS_UNREGISTERED


def _login_cookie(resp: RedirectResponse, request: Request, user: UserAccount) -> RedirectResponse:
    resp.set_cookie(
        auth.USER_SESSION_COOKIE,
        auth.issue_user_session(user.id),
        **_cookie_kwargs(request),  # type: ignore[arg-type]
    )
    return resp


@router.get("/login", response_class=HTMLResponse)
def user_login(request: Request, session: Session = Depends(get_session)):  # noqa: B008
    """일반 회원 로그인. `/login`(팀장 소유 · governor 전용)과 **다른 화면 · 다른 쿠키**다 (D-260 세션 (가))."""
    if current_user(request, session) is not None:
        return RedirectResponse("/u/", status_code=303)
    return _auth_page(request, "user/login.html", {"email": ""})


@router.post("/login")
async def user_login_post(request: Request, session: Session = Depends(get_session)):  # noqa: B008
    """로그인. ⛔ **없는 계정 · 틀린 비밀번호 · 꺼진 계정을 같은 답으로** 낸다 — 존재 여부가 정보다 (P1-5).

    🚨 시도 제한이 해시보다 먼저다 (P2-11). 키는 `u:<이메일>` — 관리자 이니셜과 섞이지 않게 접두어를 단다.
    """
    form = await _account_form(request)
    email = (form.get("email", [""])[0] or "").strip().lower()[:_EMAIL_MAX]
    password = form.get("password", [""])[0] or ""

    def again(msg: str, code: int) -> HTMLResponse:
        return _auth_page(request, "user/login.html", {"email": email, "error": msg}, code)

    if not auth.csrf_ok(request.cookies.get(auth.CSRF_COOKIE), form.get(auth.CSRF_FIELD, [""])[0]):
        auth.audit("user_login", _actor(email=email), ok=False)
        return again("화면이 오래돼서 다시 불러왔어요. 한 번 더 로그인해 주세요.", 403)
    key = f"u:{email}"
    if auth.throttle.blocked(key):
        auth.audit("user_login_blocked", _actor(email=email), ok=False)
        return again(f"시도가 너무 많아요. {auth.LOCKOUT_SEC // 60}분 뒤에 다시 해 주세요.", 429)
    if not reachable(session):
        return again("지금은 로그인할 수 없어요 — 데이터베이스에 연결되지 않았어요.", 503)

    user = session.scalar(
        select(UserAccount).where(UserAccount.email == email, UserAccount.disabled_at.is_(None))
    )
    # 🚨 없는 계정도 해시를 한 번 돈다 — 걸린 시간이 존재를 알리지 않게 (P1-5 · `verify_account`)
    stored = user.pw_hash if user else None
    if len(password) > _PW_MAX or not auth.verify_account(stored, password):
        auth.throttle.fail(key)
        auth.audit("user_login", _actor(email=email), ok=False)
        return again("이메일이나 비밀번호가 맞지 않아요.", 401)

    auth.throttle.clear(key)
    if auth.needs_rehash(user.pw_hash):
        user.pw_hash = auth.hash_password(password)
    user.last_login_at = datetime.now(UTC)
    session.commit()
    auth.audit("user_login", _actor(user.id), ok=True)
    return _login_cookie(RedirectResponse("/u/", status_code=303), request, user)


@router.post("/logout")
def user_logout(request: Request) -> RedirectResponse:
    """로그아웃 → 랜딩(로그인 전 첫 화면 · 2026-09-29 권소라). 🚨 쿠키를 지우는 것으로 끝난다 — 세션은 서버에 없다 (D-213). 관리자 쿠키는 건드리지 않는다."""
    uid = auth.read_user_session(request.cookies.get(auth.USER_SESSION_COOKIE))
    auth.audit("user_logout", _actor(uid), ok=True)
    resp = RedirectResponse("/u/landing", status_code=303)
    resp.delete_cookie(auth.USER_SESSION_COOKIE, path="/")
    return resp


#: 테마를 바꾼 뒤 돌아갈 곳 — 🔴 **사용자 화면 안의 경로만** 받는다(열린 리다이렉트 방지).
_BACK_PATH = re.compile(r"^/u(/[A-Za-z0-9_\-/]*)?$")


@router.post("/theme")
async def user_theme(request: Request) -> RedirectResponse:
    """다크모드 전환 — 상단바 달 버튼 (프로토타입 v7.2). ⛔ 스크립트 없이 폼 제출로 쿠키만 바꾼다(CSP).

    🚨 CSRF 토큰을 받지 않는다 — 바꾸는 것이 **화면 색 하나**뿐이고 계정 · 데이터를 건드리지 않는다.
       교차 사이트 POST 에는 `SameSite=Lax` 가 우리 쿠키를 싣지 않는다.
    """
    form = await _form(request)
    value = form.get("theme", [""])[0]
    back = form.get("next", ["/u/"])[0]
    resp = RedirectResponse(back if _BACK_PATH.match(back) else "/u/", status_code=303)
    if value in _THEMES:
        resp.set_cookie(_THEME_COOKIE, value, max_age=365 * 24 * 3600, **_cookie_kwargs(request))  # type: ignore[arg-type]
    return resp


@router.post("/notifications/read")
async def notifications_read(request: Request, session: Session = Depends(get_session)):  # noqa: B008
    """알림 「모두 읽음」 — 공지는 지금 시각까지, 문의 알림은 지금 있는 것 전부를 읽음으로 쿠키에 적는다.

    🚨 CSRF 토큰을 받지 않는다 — 테마와 같은 이유(바꾸는 것이 **이 브라우저의 읽음 표시**뿐 · 데이터를 안 건드린다).
    """
    form = await _form(request)
    back = form.get("next", ["/u/"])[0]
    resp = RedirectResponse(back if _BACK_PATH.match(back) else "/u/", status_code=303)
    user = current_user(request, session)
    if user is None:
        return resp
    resp.set_cookie(
        _NOTIF_SEEN_COOKIE,
        str(int(datetime.now(UTC).timestamp())),
        max_age=365 * 24 * 3600,
        **_cookie_kwargs(request),  # type: ignore[arg-type]
    )
    keys = [n.key for n in _notifications(request, session, user) if n.kind == "alert"]
    _remember_seen(resp, request, keys)
    return resp


@router.get("/signup", response_class=HTMLResponse)
def user_signup(request: Request) -> HTMLResponse:
    """일반 회원 가입 (D-260 ② ⑧). 🚨 역할을 묻지 않는다 (D-66). 선택 동의 ①② 는 여기 없다 — 마이페이지에서만 (D-96)."""
    return _auth_page(request, "user/signup.html", {"form": {}})


@router.post("/signup")
async def user_signup_post(request: Request, session: Session = Depends(get_session)):  # noqa: B008
    """가입. 필수 동의 둘(약관 · 진단 면책)을 **시각으로** 남긴다. 🚨 인증 메일은 보내지 않는다 (D-260 ⑧).

    ⛔ 상한을 자르지 않고 거부한다 (D-220). ⛔ 계정을 시드하지 않는다 — 데모 계정도 이 화면으로 만든다 (D-213 · D-260).
    """
    form = await _account_form(request)
    name = (form.get("name", [""])[0] or "").strip()
    email = (form.get("email", [""])[0] or "").strip().lower()
    pw = form.get("password", [""])[0] or ""
    pw2 = form.get("password2", [""])[0] or ""
    agree_terms = form.get("agree_terms", [""])[0] == "on"
    agree_disclaimer = form.get("agree_disclaimer", [""])[0] == "on"
    kept = {
        "name": name,
        "email": email,
        "agree_terms": agree_terms,
        "agree_disclaimer": agree_disclaimer,
    }

    def again(msg: str, code: int = 422) -> HTMLResponse:
        return _auth_page(request, "user/signup.html", {"form": kept, "error": msg}, code)

    if not auth.csrf_ok(request.cookies.get(auth.CSRF_COOKIE), form.get(auth.CSRF_FIELD, [""])[0]):
        return again("화면이 오래돼서 다시 불러왔어요. 한 번 더 가입해 주세요.", 403)
    if not name or len(name) > _NAME_MAX:
        return again(f"이름을 1~{_NAME_MAX}자로 적어 주세요.")
    if len(email) > _EMAIL_MAX or not _EMAIL_SHAPE.match(email):
        return again("이메일 형식을 확인해 주세요.")
    if not _PW_MIN <= len(pw) <= _PW_MAX:
        return again(f"비밀번호는 {_PW_MIN}~{_PW_MAX}자로 정해 주세요.")
    if pw != pw2:
        return again("비밀번호 확인이 맞지 않아요.")
    if not (agree_terms and agree_disclaimer):
        return again("필수 동의 두 가지에 체크해 주세요.")
    if not reachable(session):
        return again("지금은 가입할 수 없어요 — 데이터베이스에 연결되지 않았어요.", 503)
    # 2026-09-29 권소라 판단 — 이미 있는 이메일은 **직접 안내**한다(계정 존재가 드러난다 · P1-5 · 승인 요청에 적었다)
    if session.scalar(select(UserAccount.id).where(UserAccount.email == email)) is not None:
        return again("이미 가입된 이메일이에요. 로그인해 주세요.", 409)

    now = datetime.now(UTC)
    user = UserAccount(
        email=email,
        pw_hash=auth.hash_password(pw),
        name=name,
        terms_version=_terms_version(session),
        terms_agreed_at=now,
        disclaimer_agreed_at=now,
        last_login_at=now,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:  # 같은 이메일이 동시에 들어왔다 — 유일 제약이 막는다
        session.rollback()
        return again("이미 가입된 이메일이에요. 로그인해 주세요.", 409)
    auth.audit("user_signup", _actor(user.id), ok=True)
    return _login_cookie(RedirectResponse("/u/", status_code=303), request, user)


@router.get("/reset", response_class=HTMLResponse)
def user_reset(request: Request) -> HTMLResponse:
    """비밀번호 재설정 — 🚨 **메일을 보내지 않는다** (D-260 ⑧ · D-66). 입력 없이 안내만 둔다 (D-107 · D-147).

    ⛔ 보내는 척하는 POST 를 만들지 않는다 — 「보냈어요」는 지키지 못할 약속이다.
    """
    return templates.TemplateResponse(request, "user/reset.html", {})
