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

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Judgment
from app.settings import PARAMS
from app.templating import templates

router = APIRouter(prefix="/u", tags=["user"])

#: 🚨 본문 상한 — 없으면 무제한이다 (보안점검 P2-11).
#:    ⛔ 한글은 퍼센트 인코딩으로 **글자당 9바이트**다. 여유를 좁게 잡으면 길이 초과가
#:       413(본문)으로 먼저 걸려 「문구가 너무 길다」라는 **정확한 이유가 안 나온다.**
_MAX_BODY = PARAMS.max_text_len * 16


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


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """사용자 첫 화면. 🚨 **DB 없이 뜬다** — 팀원이 클론 첫날 여는 자리다."""
    from app.api import FIXTURE_ROOT  # noqa: PLC0415 — 순환 import 를 피한다

    names = sorted(p.stem for p in (FIXTURE_ROOT / "judge").glob("*.json"))
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(request, "user/generate.html", {"fixtures": names})


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
    return templates.TemplateResponse(
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
    """대상고객 탐색 — ★ **골격만**. `/u/generate` 카드에서만 들어온다 (nav 밖)."""
    return templates.TemplateResponse(request, "user/segments.html", {})


@router.get("/draft-setup", response_class=HTMLResponse)
def draft_setup(request: Request) -> HTMLResponse:
    """AI 광고 생성 · 포맷 선택 — ★ **골격만**. 남은 화면 4종(계약 §8 ⑥) 중 하나."""
    return templates.TemplateResponse(request, "user/draft-setup.html", {})


@router.get("/draft-editor", response_class=HTMLResponse)
def draft_editor(request: Request) -> HTMLResponse:
    """AI 광고 생성 · 섹션 에디터 — ★ **골격만**. `draft-setup` 에서만 들어온다 (nav 밖)."""
    return templates.TemplateResponse(request, "user/draft-editor.html", {})


@router.get("/mypage", response_class=HTMLResponse)
def mypage(request: Request) -> HTMLResponse:
    """마이페이지 — ★ **골격만**. 남은 화면 4종(계약 §8 ⑥) 중 하나."""
    return templates.TemplateResponse(request, "user/mypage.html", {})


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request) -> HTMLResponse:
    """도움말 — ★ **골격만**. 남은 화면 4종(계약 §8 ⑥) 중 하나."""
    return templates.TemplateResponse(request, "user/help.html", {})


@router.get("/matching", response_class=HTMLResponse)
def matching(request: Request) -> HTMLResponse:
    """매칭 — ★ **골격만**. 남은 화면 4종(계약 §8 ⑥) 중 하나 — 하위 화면 넷은 다음 차례."""
    return templates.TemplateResponse(request, "user/matching.html", {})
