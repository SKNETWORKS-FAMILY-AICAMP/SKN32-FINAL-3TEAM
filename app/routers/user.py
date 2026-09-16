"""app/routers/user.py — 사용자 화면 + BFF · 소유자 **ksr · lse** (D-208 · 병렬작업 계약 §5).

★ **여기서 하는 일** — 화면을 그리고, 코어(`/judge`·`/search`)나 픽스처를 불러 화면 모양으로
  바꾼다. ⛔ **판정 로직을 여기 쓰지 않는다** (D-119 — 판정 코어는 하나).

🚨 **엔진이 필요한 화면은 DB 없이도 떠야 한다** (D-124) — `judge`·`generate_page` 는
   골든 픽스처로 모든 분기를 그린다. ⬜ **`history` 는 예외다** — 한빈님 확인 후
   (2026-09-13) 처음으로 실제 DB(`app/db.py`, `Judgment`)에 붙었다. 판정 엔진이
   아직 없어 지금은 빈 목록으로 뜬다.

⬜ **2W 산출물의 화면 4종을 여기로 옮기는 것이 남은 일**이다 (계약 §8 ⑥).
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contracts import PASS_RISK_MAX_PROVISIONAL
from app.db import get_session
from app.models import Judgment
from app.settings import PARAMS
from app.templating import templates

router = APIRouter(prefix="/u", tags=["user"])

#: 🚨 본문 상한 — 없으면 무제한이다 (보안점검 P2-11).
#:    ⛔ 한글은 퍼센트 인코딩으로 **글자당 9바이트**다. 여유를 좁게 잡으면 길이 초과가
#:       413(본문)으로 먼저 걸려 「문구가 너무 길다」라는 **정확한 이유가 안 나온다.**
_MAX_BODY = PARAMS.max_text_len * 16

# ══════════════════════════════════════════════════════════════════════
#  상단 nav — 구역 넷 + 사이드바 (2026-09-16, 발표자료 v7.2 SECTIONS 를 서버 렌더로)
# ══════════════════════════════════════════════════════════════════════
#: 🚨 **경로 → 구역.** 여기 없는 경로(홈·마이페이지·고객센터)는 구역이 없다 —
#:    상단 pill 이 안 켜지고 사이드바도 안 뜬다. 디자인의 `SCREEN_SECTION` 그대로다.
_SCREEN_SECTION: dict[str, str] = {
    "/u/": "work",
    "/u/generate": "work",
    "/u/segments": "work",
    "/u/history": "work",
    "/u/draft-setup": "adgen",
    "/u/draft-editor": "adgen",
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
        ("review", "검수", "/u/"),
        ("gen", "카피생성", "/u/generate"),
        ("history", "이력", "/u/history"),
    ),
    "about": (
        ("guide", "사용방법", "/u/help?tab=guide"),
        ("faq", "자주 묻는 질문", "/u/help?tab=faq"),
    ),
    "adgen": (("make", "광고 만들기", "/u/draft-setup"),),
}

#: 경로 → 사이드바 활성 항목 key. `/u/help` 는 tab 쿼리로 갈리니 라우터에서 직접 넘긴다.
_SECTION_ACTIVE_SUB: dict[str, str] = {
    "/u/": "review",
    "/u/generate": "gen",
    "/u/segments": "gen",
    "/u/history": "history",
    "/u/draft-setup": "make",
    "/u/draft-editor": "make",
}


def _render(
    request: Request, template: str, ctx: dict | None = None, *, active_sub: str | None = None
) -> HTMLResponse:
    """모든 사용자 화면이 여기를 거친다 — 구역·사이드바 계산을 **한 곳에만** 둔다.

    ⛔ 화면마다 `active_section` 을 손으로 채우면, 화면이 늘 때마다 빠뜨리는 자리가
       생긴다 (D-147 의 정신과 같다 — 계산이 갈리면 둘 다 못 믿는다).
    """
    ctx = dict(ctx or {})
    path = request.url.path
    section = _SCREEN_SECTION.get(path)
    ctx.setdefault("active_section", section)
    ctx.setdefault("section_label", _SECTION_LABELS.get(section) if section else None)
    ctx.setdefault("section_subs", _SECTION_SUBS.get(section) if section else None)
    ctx.setdefault("active_sub", active_sub if active_sub is not None else _SECTION_ACTIVE_SUB.get(path))
    return templates.TemplateResponse(request, template, ctx)


async def _form_field(request: Request, name: str) -> str:
    """`application/x-www-form-urlencoded` 본문에서 필드 하나. **의존성을 안 늘린다.**

    ⛔ 상한을 **자르지 않고 거부한다** — 자르면 사용자는 자기 문구가 잘린 줄 모른다 (D-220).
    """
    body = await request.body()
    if len(body) > _MAX_BODY:
        raise HTTPException(413, f"본문이 너무 크다 — {_MAX_BODY} 바이트까지 받는다")
    value = parse_qs(body.decode("utf-8", "replace")).get(name, [""])[0]
    if len(value) > PARAMS.max_text_len:
        raise HTTPException(422, f"문구가 너무 길다 — {PARAMS.max_text_len}자까지 받는다")
    return value


@router.get("/home", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:  # noqa: B008
    """대시보드 — 🚨 history 와 같은 요령으로 **진짜 DB 집계**다. 판정 엔진이 없어 지금은
    통계가 전부 0/— 로 뜬다 — 정상이다 (D-147 의 정신과 같다. 가짜 수치를 안 그린다).

    ★ "위법 소지 발견"·"재검수 통과율"은 `app.contracts.PASS_RISK_MAX_PROVISIONAL`
      (D-125 통과 조건의 잠정 위험도 임계값)을 그대로 쓴다 — 그 상수 자체가 주석에
      "⛔ 화면 표기에만 쓴다"고 허가해 둔 값이라 여기 쓰는 게 정확히 그 용도다.
      R2·R3 순서가 검증 ②로 확정되면 이 화면도 자동으로 따라간다.
    """
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month = select(Judgment).where(Judgment.judged_at >= month_start)
    pass_level = PASS_RISK_MAX_PROVISIONAL.level

    total_month = session.scalar(select(func.count()).select_from(month.subquery())) or 0
    violation_count = (
        session.scalar(
            select(func.count()).select_from(
                month.where(Judgment.verdict == "confirmed", Judgment.risk_final > pass_level)
                .subquery()
            )
        )
        or 0
    )
    pass_count = (
        session.scalar(
            select(func.count()).select_from(
                month.where(Judgment.verdict == "confirmed", Judgment.risk_final <= pass_level)
                .subquery()
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
        "user/home.html",
        {
            "total_month": total_month,
            "violation_count": violation_count,
            "pass_rate": pass_rate,
            "recent": recent,
        },
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """사용자 첫 화면. 🚨 **DB 없이 뜬다** — 팀원이 클론 첫날 여는 자리다."""
    from app.api import FIXTURE_ROOT  # noqa: PLC0415 — 순환 import 를 피한다

    names = sorted(p.stem for p in (FIXTURE_ROOT / "judge").glob("*.json"))
    return _render(
        request,
        "user/index.html",
        {"fixtures": names, "max_text_len": PARAMS.max_text_len},
    )


@router.post("/judge", response_class=HTMLResponse)
async def judge(request: Request) -> HTMLResponse:
    """문구 검수 — 🚨 **엔진이 없다.** 가짜 결과를 그리지 않는다 (D-147).

    🔴 **POST 다** — 문구를 URL 에 싣지 않는다 (보안점검 P1-4).

    ⛔ **`Form(...)` 도 `request.form()` 도 안 쓴다** (2026-09-12 밤 · **실패로 두 번 배웠다**).
       둘 다 `python-multipart` 를 요구한다 — `Form` 은 **라우트를 정의하는 순간**,
       `request.form()` 은 **본문을 팔 때**. 그것은 **새 의존성**이고 `uv.lock` 은 팀장
       단독이며 충돌이 팀 전체로 번진다 (D-87 · 병렬작업 계약 §5).
    ★ 필드가 하나라서 **본문을 직접 판다.** HTML 폼은 `enctype` 없이 보내면
      `application/x-www-form-urlencoded` 이고 그것은 표준 라이브러리로 파싱된다.
    ⬜ **파일 업로드를 붙일 때는 얘기가 다르다** — 그때는 `multipart/form-data` 라
       `python-multipart` 가 필요하고, **lock 을 만지는 판정**이다 (§5). 그 판정 전까지
       업로드 라우트를 만들지 않는다.
    ⬜ 엔진이 서면 `POST /judge` 를 부르고 응답을 템플릿에 넘긴다. 지금은 픽스처로 그린다.
    """
    from app.api import FIXTURE_ROOT  # noqa: PLC0415

    _text = await _form_field(request, "text")

    names = sorted(p.stem for p in (FIXTURE_ROOT / "judge").glob("*.json"))
    return _render(
        request,
        "user/index.html",
        # ⛔ `text` 를 되돌려 그리지 않는다 — 지금은 그릴 자리가 없고,
        #    되돌려 그릴 때는 **템플릿이 이스케이프한다** (P2-9). 문자열 조립 금지.
        {"fixtures": names, "max_text_len": PARAMS.max_text_len},
    )


@router.get("/generate", response_class=HTMLResponse)
def generate_page(request: Request) -> HTMLResponse:
    """카피 생성 화면 자리. ★ **골격만** — 세그먼트·키워드 폼은 세부 화면 담당이 채운다.

    `judge`/`index` 와 같은 패턴이다: DB·엔진 없이 골든 픽스처(`GenerateResponse`,
    D-181)로 뜬다. `POST /generate` 코어는 아직 501 이다 — 여기서 부르지 않는다.
    """
    from app.api import FIXTURE_ROOT  # noqa: PLC0415

    names = sorted(p.stem for p in (FIXTURE_ROOT / "generate").glob("*.json"))
    return _render(request, "user/generate.html", {"fixtures": names})


#: D-127 — 판정 상태 4종. history 필터가 받는 값은 이 넷뿐이다.
_VERDICTS = ("confirmed", "hold", "no_basis", "unjudged")
_PAGE_SIZE = 20


@router.get("/history", response_class=HTMLResponse)
def history(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
    verdict: str | None = None,
    page: int = 1,
    open_id: str | None = None,
) -> HTMLResponse:
    """검수 이력 — 🚨 **DB 에 직접 붙는 첫 화면**이다 (2026-09-13 한빈님 확인).

    ⬜ 판정 엔진이 아직 없어 `judgment` 표는 비어 있다 — 그래서 지금은 빈 목록으로 뜬다.
       가짜 행을 만들어 채우지 않는다 (D-147 의 정신과 같다).

    ★ 필터(`verdict`)·페이지네이션(`page`)은 목록 화면 공통 패턴이다 — segments 등
      다음 목록 화면이 생기면 `user/_pagination.html` 을 그대로 include 한다.
    ⛔ **`page`·`verdict` 는 사용자가 URL 을 손으로 바꿀 수 있다** — 잘못된 값으로
       500 을 내지 않고 조용히 안전한 기본값(1 페이지·전체)으로 되돌린다.

    🔄 **상세는 서버 렌더 토글이다** (2026-09-16 판단) — 디자인 프로토타입(v7.2)은
       클릭하면 옆에 드로어가 JS 로 열리는데, 이 프로젝트는 CSP 가 인라인 스크립트를
       막고 HTMX 도 아직 안 붙었다 (`base.html` 참고). `?open_id=<judgment.id>` 링크로
       같은 효과(항목 클릭 → 상세 펼침)를 서버 렌더만으로 낸다.
    ⬜ 근거(evidence)·질의응답은 디자인엔 있지만 이번엔 뺐다 — QnA 를 저장할 테이블이
       아직 없다. 결론·위험도·법령 버전만 보여준다.
    """
    page = max(page, 1)
    if verdict not in (None, *_VERDICTS):
        verdict = None

    stmt = select(Judgment)
    if verdict:
        stmt = stmt.where(Judgment.verdict == verdict)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(
            stmt.order_by(Judgment.judged_at.desc())
            .limit(_PAGE_SIZE)
            .offset((page - 1) * _PAGE_SIZE)
        )
        .scalars()
        .all()
    )
    opened = next((j for j in rows if str(j.id) == open_id), None) if open_id else None
    return _render(
        request,
        "user/history.html",
        {
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


@router.get("/segments", response_class=HTMLResponse)
def segments(request: Request) -> HTMLResponse:
    """대상고객 탐색 — ★ **골격만**. `/u/generate` 카드에서만 들어온다 (사이드바 밖)."""
    return _render(request, "user/segments.html")


@router.get("/draft-setup", response_class=HTMLResponse)
def draft_setup(request: Request) -> HTMLResponse:
    """AI 광고 생성 · 포맷 선택 — ★ **골격만**. 남은 화면 4종(계약 §8 ⑥) 중 하나."""
    return _render(request, "user/draft-setup.html")


@router.get("/draft-editor", response_class=HTMLResponse)
def draft_editor(request: Request) -> HTMLResponse:
    """AI 광고 생성 · 섹션 에디터 — ★ **골격만**. `draft-setup` 에서만 들어온다 (사이드바 밖)."""
    return _render(request, "user/draft-editor.html")


@router.get("/mypage", response_class=HTMLResponse)
def mypage(request: Request) -> HTMLResponse:
    """마이페이지 — ★ **골격만**. 상단 오른쪽 아바타 버튼으로 들어온다 (구역 밖)."""
    return _render(request, "user/mypage.html")


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request, tab: str = "guide") -> HTMLResponse:
    """copylane 소개 — ★ **골격만**. `tab`(guide·faq)이 "사용방법"·"자주 묻는 질문"
    사이드바 두 항목을 가른다 — 디자인은 이 둘을 같은 화면의 JS 탭으로 뒀다.
    """
    if tab not in ("guide", "faq"):
        tab = "guide"
    return _render(request, "user/help.html", {"tab": tab}, active_sub=tab)


@router.get("/matching", response_class=HTMLResponse)
def matching(request: Request) -> HTMLResponse:
    """매칭 — ★ **골격만**. 하위 화면 넷은 홀딩이라 이 구역은 아직 사이드바가 없다."""
    return _render(request, "user/matching.html")


@router.get("/cs", response_class=HTMLResponse)
def cs(request: Request) -> HTMLResponse:
    """고객센터 문의 — ★ **골격만**. 각 구역 사이드바 하단 버튼으로만 들어온다 (구역 밖)."""
    return _render(request, "user/cs.html")


@router.get("/login", response_class=HTMLResponse)
def user_login(request: Request) -> HTMLResponse:
    """일반 회원 로그인 — ★ **골격만, 제출 버튼 없음**. `/login`(팀장 소유, governor 전용)과
    다른 화면이다 — 계정 테이블이 없어 입력만 보여준다 (2026-09-16 판단).
    """
    return templates.TemplateResponse(request, "user/login.html", {})


@router.get("/signup", response_class=HTMLResponse)
def user_signup(request: Request) -> HTMLResponse:
    """일반 회원 가입 — ★ **골격만, 제출 버튼 없음**. D-66이 클라우드 에디션에 열어 둔
    가입 화면이지만, 계정 테이블이 진입점 B 엔진과 함께 오기 전까지는 폼만 보여준다.
    """
    return templates.TemplateResponse(request, "user/signup.html", {})
