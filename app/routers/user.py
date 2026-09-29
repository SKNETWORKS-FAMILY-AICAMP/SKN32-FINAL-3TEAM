"""app/routers/user.py — 사용자 화면 + BFF · 소유자 **ksr · lse** (D-208 · 병렬작업 계약 §5).

★ **여기서 하는 일** — 화면을 그리고, 코어(`/judge`·`/search`)나 픽스처를 불러 화면 모양으로
  바꾼다. ⛔ **판정 로직을 여기 쓰지 않는다** (D-119 — 판정 코어는 하나).

🚨 **엔진이 필요한 화면은 DB 없이도 떠야 한다** (D-124) — `review`·`generate`·`compose` 는
   골든 픽스처로 모든 분기를 그린다. ⬜ **`history`·`/`(홈) 은 예외다** — 실제 DB(`app/db.py`,
   `Judgment`)에 붙는다. 판정 엔진이 아직 없어 지금은 빈 목록/0 건으로 뜬다.
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
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.contracts import PASS_RISK_MAX, Risk
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
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month = select(Judgment).where(Judgment.judged_at >= month_start)
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

    recent = (
        session.execute(select(Judgment).order_by(Judgment.judged_at.desc()).limit(3))
        .scalars()
        .all()
    )
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


def _core_judge(text: str):  # noqa: ANN202
    """코어 판정을 부른다 — `POST /judge` 와 **같은 함수**다 (D-119 · 판정 코어는 하나).

    ★ 반환 `(상태, 응답)` — `ok` 는 `JudgeResponse`, `pending` 은 엔진 미착수(501).
    ⛔ 501 을 결과처럼 꾸미지 않는다 (D-147). 다른 오류는 삼키지 않고 올린다.
    """
    from app.api import judge as core_judge  # noqa: PLC0415 — 순환 import 를 피한다
    from app.contracts import JudgeRequest  # noqa: PLC0415

    try:
        return "ok", core_judge(JudgeRequest(text=text))
    except HTTPException as e:
        if e.status_code == 501:
            return "pending", None
        raise


def _flagged(result) -> set[str]:  # noqa: ANN001
    """지적 문장 id — **확정이면서 통과 문턱 이하**가 아닌 문장은 전부 든다.

    🚨 미판정·보류도 든다 — 통과로 집계하지 않는다 (D-127). 문턱은 `PASS_RISK_MAX` 한 곳 (D-273) —
       템플릿에 R0 을 따로 적지 않으려고 여기서 계산해 넘긴다 (D-99).
    """
    out: set[str] = set()
    for s in result.sentences:
        ok = s.verdict.value == "confirmed" and (
            s.risk.final is None or s.risk.final.level <= PASS_RISK_MAX.level
        )
        if not ok and not s.not_claim:
            out.add(s.sent_id)
    return out


def _review_ctx(copies: list[str], results: list[dict] | None = None, **extra) -> dict:
    ctx = {
        "fixtures": _fixture_names("judge"),
        "max_text_len": PARAMS.max_text_len,
        "max_copies": _MAX_COPIES,
        "copies": copies,
        "results": results or [],
    }
    for r in results or []:
        r["flagged"] = _flagged(r["result"])
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
        if state == "pending":
            return _render(request, "user/review.html", _review_ctx(copies, engine_pending=True))
        results.append({"n": n, "result": res})
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


@router.get("/generate", response_class=HTMLResponse)
def generate_page(request: Request) -> HTMLResponse:
    """카피 생성 입력 화면 (`gen-input`, ksr 2026-09-13).

    `review`/`index` 와 같은 패턴이다: DB·엔진 없이 골든 픽스처(`GenerateResponse`,
    D-181)로 뜬다. `POST /generate` 코어는 아직 501 이다 — 여기서 부르지 않는다.
    """
    return _render(
        request,
        "user/generate.html",
        {"fixtures": _fixture_names("generate"), "max_text_len": PARAMS.max_text_len},
    )


@router.post("/generate", response_class=HTMLResponse)
async def generate(request: Request) -> HTMLResponse:
    """카피 생성 — ⛔ **코어가 아직 501 이다** (D-181). 가짜 결과를 그리지 않는다 (D-147).

    🚨 `GenerateRequest` 는 `segment` 가 필수라 필드가 여럿이다. 그래도
       `python-multipart` 는 필요 없다 — `parse_qs` 가 여러 필드를 그대로 준다.
    ★ 고른 값은 되돌려 그린다. **템플릿이 이스케이프한다** (P2-9).
    """
    form = await _form(request)
    keywords = [k for k in form.get("keyword", []) if len(k) <= 64][:32]
    return _render(
        request,
        "user/generate.html",
        {
            "fixtures": _fixture_names("generate"),
            "max_text_len": PARAMS.max_text_len,
            "picked": {
                "product": _one(form, "product", 128),
                "segment": _one(form, "segment", 128),
                "keywords": keywords,
            },
            "engine_pending": True,
        },
    )


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
        {
            "fixtures": _fixture_names("generate"),
            "max_text_len": PARAMS.max_text_len,
            "result": result,
            "points": _frontier(result.candidates),
            "risk_axis_max": _RISK_AXIS_MAX.value,
            "fixture_name": name,
        },
    )


@router.get("/segments", response_class=HTMLResponse)
def segments(request: Request) -> HTMLResponse:
    """대상고객 탐색 — ★ **골격만**. `/u/generate` 카드에서만 들어온다 (사이드바 밖)."""
    return _render(request, "user/segments.html")


# ══════════════════════════════════════════════════════════════════════
#  C · 광고 생성 (SCR-AD) — 진입점 C
# ══════════════════════════════════════════════════════════════════════


@router.get("/compose", response_class=HTMLResponse)
def compose_page(request: Request) -> HTMLResponse:
    """광고 초안 입력 화면 (`draft-setup`, ksr 2026-09-13). 구 `/u/draft-setup`·`/u/draft-editor`
    (빈 골격)를 대체한다.

    ⬜ 프로토타입 `draft-editor` 의 아트보드·인스펙터·줌은 **전부 스크립트**라 만들지 않았다.
       섹션 골격은 `ComposeResponse.sections` 를 서버가 순서대로 그린다.
    """
    return _render(
        request,
        "user/compose.html",
        {"fixtures": _fixture_names("compose"), "max_text_len": PARAMS.max_text_len},
    )


@router.post("/compose", response_class=HTMLResponse)
async def compose(request: Request) -> HTMLResponse:
    """광고 생성 — ⛔ **코어가 아직 없다.** 가짜 결과를 그리지 않는다 (D-147).

    🚨 `ComposeRequest` 는 두 경로 중 **하나로만** 들어온다 (계약 `_one_of_two_paths`) —
       B 의 각색본(`source_copy`) 또는 직접 입력(`prompt`). 이 화면은 후자다.
    """
    form = await _form(request)
    return _render(
        request,
        "user/compose.html",
        {
            "fixtures": _fixture_names("compose"),
            "max_text_len": PARAMS.max_text_len,
            "picked": {
                "ad_format": _one(form, "ad_format", 32),
                "prompt": _one(form, "prompt", PARAMS.max_text_len),
            },
            "engine_pending": True,
        },
    )


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
        {
            "fixtures": _fixture_names("compose"),
            "max_text_len": PARAMS.max_text_len,
            "result": ComposeResponse.model_validate_json(raw),
            "fixture_name": name,
        },
    )


# ══════════════════════════════════════════════════════════════════════
#  이력 · 사용설명 · 나머지
# ══════════════════════════════════════════════════════════════════════

#: D-127 — 판정 상태 4종. history 필터가 받는 값은 이 넷뿐이다.
_VERDICTS = ("confirmed", "hold", "no_basis", "unjudged")
_PAGE_SIZE = 20


def _history_rows(session: Session, verdict: str | None, page: int) -> tuple[list, int]:
    """이력 한 쪽의 행과 전체 건수. `judgment` × `copy_sentence` 조인 (ksr 원문 조인 · lse 필터·페이지)."""
    stmt = (
        select(Judgment, CopySentence.raw)
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
    ⬜ 판정 엔진이 아직 없어 `judgment` 표는 비어 있다 — 그래서 지금은 빈 목록으로 뜬다.
       가짜 행을 만들어 채우지 않는다 (D-147 의 정신과 같다).
    ⛔ **`page`·`verdict` 는 사용자가 URL 을 손으로 바꿀 수 있다** — 잘못된 값으로
       500 을 내지 않고 조용히 안전한 기본값(1 페이지·전체)으로 되돌린다.
    ⬜ 근거(evidence)·질의응답은 디자인엔 있지만 이번엔 뺐다 — QnA 를 저장할 테이블이
       아직 없다. 원문·결론·위험도·법령 버전만 보여준다.
    """
    page = max(page, 1)
    if verdict not in (None, *_VERDICTS):
        verdict = None
    db_down = not reachable(session)
    rows, total = ([], 0) if db_down else _history_rows(session, verdict, page)
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
    request: Request, tab: str = "profile", session: Session = Depends(get_session)
) -> HTMLResponse:  # noqa: B008
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
async def mypage_save(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:  # noqa: B008
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
            _mypage_ctx(user, tab, error="화면이 오래돼서 다시 불러왔어요. 한 번 더 저장해 주세요."),
            403,
        )

    if section == "profile":
        name = _one(form, "name", _MYPAGE_FIELDS["name"]).strip()
        org = _one(form, "org", _MYPAGE_FIELDS["org"]).strip()
        if not name:
            return _render_form(
                request,
                "user/mypage.html",
                {**_mypage_ctx(user, tab), "picked": {**_mypage_picked(user), "name": name, "org": org}, "error": "이름을 입력해 주세요."},
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
        request, "user/mypage.html", {**_mypage_ctx(user, tab), "picked": picked, "saved_attempt": True}
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
            _mypage_ctx(user, "account", error="화면이 오래돼서 다시 불러왔어요. 한 번 더 해 주세요."),
            403,
        )
    confirm = _one(form, "confirm", 20)
    if confirm != _MYPAGE_DISABLE_CONFIRM:
        return _render_form(
            request,
            "user/mypage.html",
            _mypage_ctx(
                user, "account", error=f"확인 문구가 맞지 않아요. 「{_MYPAGE_DISABLE_CONFIRM}」라고 정확히 입력해 주세요."
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
