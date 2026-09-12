"""app/routers/user.py — 사용자 화면 + BFF · 소유자 **ksr · lse** (D-208 · 병렬작업 계약 §5).

★ **여기서 하는 일** — 화면을 그리고, 코어(`/judge`·`/search`)나 픽스처를 불러 화면 모양으로
  바꾼다. ⛔ **판정 로직을 여기 쓰지 않는다** (D-119 — 판정 코어는 하나).

🚨 **DB 없이도 화면이 떠야 한다** (D-124). 엔진이 없는 지금 화면은 **골든 픽스처**로 모든
   분기를 그린다. 그래서 이 라우터는 DB 에 안 붙는다.

⬜ **2W 산출물의 화면 4종을 여기로 옮기는 것이 남은 일**이다 (계약 §8 ⑥).
"""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.settings import PARAMS
from app.templating import templates

router = APIRouter(prefix="/u", tags=["user"])

#: 🚨 본문 상한 — 없으면 무제한이다 (보안점검 P2-11).
#:    ⛔ 한글은 퍼센트 인코딩으로 **글자당 9바이트**다. 여유를 좁게 잡으면 길이 초과가
#:       413(본문)으로 먼저 걸려 「문구가 너무 길다」라는 **정확한 이유가 안 나온다.**
_MAX_BODY = PARAMS.max_text_len * 16


async def _form_field(request: Request, name: str) -> str:
    """`application/x-www-form-urlencoded` 본문에서 필드 하나. **의존성을 안 늘린다.**

    ⛔ 상한을 **자르지 않고 거부한다** — 자르면 사용자는 자기 문구가 잘린 줄 모른다 (D-72).
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
