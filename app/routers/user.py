"""app/routers/user.py — 사용자 화면 + BFF · 소유자 **ksr · lse** (D-208 · 병렬작업 계약 §5).

★ **여기서 하는 일** — 화면을 그리고, 코어(`/judge`·`/search`)나 픽스처를 불러 화면 모양으로
  바꾼다. ⛔ **판정 로직을 여기 쓰지 않는다** (D-119 — 판정 코어는 하나).

🚨 **DB 없이도 화면이 떠야 한다** (D-124). 엔진이 없는 지금 화면은 **골든 픽스처**로 모든
   분기를 그린다. 그래서 이 라우터는 DB 에 안 붙는다.

⛔ **`Form(...)` 도 `request.form()` 도 안 쓴다** — 둘 다 `python-multipart` 를 요구하고
   그것은 **새 의존성**이다. `uv.lock` 은 팀장 단독이다 (D-87 · §5). 본문을 직접 판다.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import CopySentence, Judgment
from app.settings import PARAMS
from app.templating import templates

router = APIRouter(prefix="/u", tags=["user"])

#: 🚨 본문 상한 — 없으면 무제한이다 (보안점검 P2-11).
#:    ⛔ 한글은 퍼센트 인코딩으로 **글자당 9바이트**다. 여유를 좁게 잡으면 길이 초과가
#:       413(본문)으로 먼저 걸려 「문구가 너무 길다」라는 **정확한 이유가 안 나온다.**
_MAX_BODY = PARAMS.max_text_len * 16

#: 🔴 픽스처 이름 **화이트리스트**. `app/api.py` 가 밟은 경로 순회(`%5C` + Windows
#:    `pathlib`)와 같은 이유다 — 이름을 경로로 쓰기 전에 모양을 고정한다.
_FIXTURE_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

#: 마이페이지가 받는 필드와 글자 상한. 🚨 **상한을 자르지 않고 거부한다** (D-72).
_MYPAGE_FIELDS = {
    "name": 40,
    "email": 120,
    "org": 60,
    "age": 16,
    "sex": 8,
    "channel": 16,
    "category": 16,
}
_MYPAGE_BLANK = dict.fromkeys(_MYPAGE_FIELDS, "")


async def _form(request: Request) -> dict[str, list[str]]:
    """`application/x-www-form-urlencoded` 본문을 표준 라이브러리로 판다.

    ★ HTML 폼은 `enctype` 없이 보내면 이 형식이고, `urllib.parse.parse_qs` 로 끝난다.
      필드가 여럿이어도 마찬가지다 — `python-multipart` 가 필요한 것은
      **파일 업로드(`multipart/form-data`)** 뿐이다.
    ⬜ 업로드를 붙일 때는 lock 을 만지는 판정이다 (§5). 그 판정 전까지 만들지 않는다.
    """
    body = await request.body()
    if len(body) > _MAX_BODY:
        raise HTTPException(413, f"본문이 너무 크다 — {_MAX_BODY} 바이트까지 받는다")
    return parse_qs(body.decode("utf-8", "replace"))


def _one(form: dict[str, list[str]], name: str, limit: int) -> str:
    """필드 하나. ⛔ 상한을 **자르지 않고 거부한다** — 자르면 사용자는 잘린 줄 모른다 (D-72)."""
    value = form.get(name, [""])[0]
    if len(value) > limit:
        raise HTTPException(422, f"{name} 이 너무 길다 — {limit}자까지 받는다")
    return value


def _fixture_names(kind: str) -> list[str]:
    from app.api import FIXTURE_ROOT  # noqa: PLC0415 — 순환 import 를 피한다

    return sorted(p.stem for p in (FIXTURE_ROOT / kind).glob("*.json"))


def _fixture_path(kind: str, name: str):
    from app.api import FIXTURE_ROOT  # noqa: PLC0415

    if not _FIXTURE_NAME.match(name):
        raise HTTPException(404, "그런 픽스처가 없다")
    path = FIXTURE_ROOT / kind / f"{name}.json"
    if not path.is_file():
        raise HTTPException(404, "그런 픽스처가 없다")
    return path


# ══════════════════════════════════════════════════════════════════════
#  A · 문구 검수 (SCR-A)
# ══════════════════════════════════════════════════════════════════════


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """사용자 첫 화면 = **홈**. 🚨 **DB 없이 뜬다** — 팀원이 클론 첫날 여는 자리다.

    🔄 종전에는 여기가 문구 검수였다. 화면이 늘면서 **첫 화면을 홈이 든다** —
       검수는 `/u/review` 로 옮겼다.
    ⛔ 집계(이번 달 검수·위법 소지·통과율)와 최근 이력은 **판정 이력**에서 나온다.
       엔진도 DB 연결도 없으니 **숫자를 지어내지 않는다** (D-147) — 자리만 둔다.
    """
    return templates.TemplateResponse(request, "user/index.html", {})


@router.get("/review", response_class=HTMLResponse)
def review(request: Request) -> HTMLResponse:
    """문구 검수 입력 화면 (SCR-A)."""
    return templates.TemplateResponse(
        request,
        "user/review.html",
        {"fixtures": _fixture_names("judge"), "max_text_len": PARAMS.max_text_len},
    )


@router.post("/judge", response_class=HTMLResponse)
async def judge(request: Request) -> HTMLResponse:
    """문구 검수 — 🚨 **엔진이 없다.** 가짜 결과를 그리지 않는다 (D-147).

    🔴 **POST 다** — 문구를 URL 에 싣지 않는다 (보안점검 P1-4).
    ★ 넣은 문구는 되돌려 그린다. **템플릿이 이스케이프한다** (P2-9) — 문자열 조립 금지.
    ⬜ 엔진이 서면 `POST /judge` 를 부르고 응답을 `result` 로 넘긴다. 지금은 배너만 든다.
    """
    text = _one(await _form(request), "text", PARAMS.max_text_len)
    return templates.TemplateResponse(
        request,
        "user/review.html",
        {
            "fixtures": _fixture_names("judge"),
            "max_text_len": PARAMS.max_text_len,
            "text": text,
            "engine_pending": True,
        },
    )


@router.get("/preview/{name}", response_class=HTMLResponse)
def judge_preview(request: Request, name: str) -> HTMLResponse:
    """골든 픽스처 하나를 **결과 화면으로** 그린다 (D-124 ③).

    ⛔ 파일을 그대로 흘리지 않는다 — `JudgeResponse` **계약을 통과시켜** 낸다.
       계약이 깨지면 화면이 아니라 여기서 먼저 터져야 한다.
    """
    from app.contracts import JudgeResponse  # noqa: PLC0415

    raw = _fixture_path("judge", name).read_text(encoding="utf-8")
    return templates.TemplateResponse(
        request,
        "user/review.html",
        {
            "fixtures": _fixture_names("judge"),
            "max_text_len": PARAMS.max_text_len,
            "result": JudgeResponse.model_validate_json(raw),
            "fixture_name": name,
        },
    )


# ══════════════════════════════════════════════════════════════════════
#  B · 카피 생성 (SCR-GN)
# ══════════════════════════════════════════════════════════════════════

#: 프론티어 산점도의 그리기 영역. 🚨 **좌표는 파이썬이 계산한다** —
#:    CSP 가 스크립트를 막아 차트 라이브러리를 못 쓰고, 템플릿은 인라인 SVG 로 점만 찍는다.
_PLOT = {"x0": 40.0, "x1": 326.0, "y0": 216.0, "y1": 14.0}


def _frontier(candidates: list) -> list[dict]:
    """후보를 산점도 좌표로 옮긴다.

    x = 잔여 위험도(R0~R4 를 0~1 로), y = 소구력 보존율(원문 대비 정보량 보존율).
    🚨 y 축은 **전환율·판매 성과가 아니다** (contracts.py `Candidate` docstring).
    """
    points: list[dict] = []
    for c in candidates:
        rx = c.residual_risk.level / 4.0
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
    """카피 생성 입력 화면 (`gen-input`).

    `judge`/`index` 와 같은 패턴이다: DB·엔진 없이 골든 픽스처(`GenerateResponse`,
    D-181)로 뜬다. `POST /generate` 코어는 아직 501 이다 — 여기서 부르지 않는다.
    """
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
        request,
        "user/generate.html",
        {
            "fixtures": _fixture_names("generate"),
            "max_text_len": PARAMS.max_text_len,
            "result": result,
            "points": _frontier(result.candidates),
            "fixture_name": name,
        },
    )


# ══════════════════════════════════════════════════════════════════════
#  C · 광고 생성 (SCR-AD) — 진입점 C
# ══════════════════════════════════════════════════════════════════════


@router.get("/compose", response_class=HTMLResponse)
def compose_page(request: Request) -> HTMLResponse:
    """광고 초안 입력 화면 (`draft-setup`).

    ⬜ 프로토타입 `draft-editor` 의 아트보드·인스펙터·줌은 **전부 스크립트**라 만들지 않았다.
       섹션 골격은 `ComposeResponse.sections` 를 서버가 순서대로 그린다.
    """
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
#  사용설명 — 데이터가 없어도 서는 화면
# ══════════════════════════════════════════════════════════════════════


@router.get("/landing", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    """랜딩 — 로그인 전 첫 화면.

    🚨 nav 를 넣지 않는다. 로그인 전이라 사용자 메뉴가 없다.
    ⛔ 프로토타입의 사용량 수치(「240개 팀 · 12,000건」)는 **지어낸 값**이라 옮기지 않았다 (D-147).
    """
    return templates.TemplateResponse(request, "user/landing.html", {})


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request, tab: str = "guide") -> HTMLResponse:
    """copylane 소개 — 하위가 둘이다 (`SECTIONS.about`): 사용방법 / 자주 묻는 질문.

    ⛔ 탭 전환을 스크립트로 하지 않는다 (CSP) — **쿼리스트링으로 서버가 고른다.**
    ⛔ 아직 없는 화면의 사용법은 「아직 없는 것」으로 따로 묶는다 (D-147).
    """
    return templates.TemplateResponse(
        request, "user/help.html", {"tab": "faq" if tab == "faq" else "guide"}
    )


@router.get("/history", response_class=HTMLResponse)
def history(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:  # noqa: B008
    """검수 이력 — DB 에 직접 붙는다 (judgment × copy_sentence join).

    ★ 쿼리는 **lse** 가 준 것이다 (`app/db.py` + `Judgment` 모델). 화면(`user/history.html`)은
      ksr 것이고, 넘기는 이름 셋(`rows`·`pattern`·`fixtures`)만 맞췄다 —
      같은 화면을 둘이 만든 것을 이렇게 합쳤다 (§5).
    ⬜ 판정 엔진이 아직 없어 지금은 항상 빈 목록이다 — **정상이다** (D-147).
       🚨 빈 목록을 채우려고 가짜 행을 넣지 않는다. 엔진이 붙으면 여기에 쌓인다.
    ⬜ `pattern`(반복 지적 패턴)은 집계 로직이 없어 아직 `None` 으로 넘긴다.
       화면은 `None` 이면 그 카드를 아예 그리지 않는다.
    🚨 이 라우트만 DB 를 본다 — 나머지 화면은 여전히 DB 없이 뜬다 (D-124).
    """
    rows = session.execute(
        select(Judgment.judged_at, Judgment.verdict, CopySentence.raw)
        .join(CopySentence, CopySentence.id == Judgment.subject_id)
        .where(Judgment.subject_type == "copy_sentence")
        .order_by(Judgment.judged_at.desc())
        .limit(50)
    ).all()
    history_rows = [
        SimpleNamespace(text=raw, outcome=verdict, judged_at=judged_at)
        for judged_at, verdict, raw in rows
    ]
    return templates.TemplateResponse(
        request,
        "user/history.html",
        {"rows": history_rows, "pattern": None, "fixtures": _fixture_names("judge")},
    )


@router.get("/mypage", response_class=HTMLResponse)
def mypage(request: Request) -> HTMLResponse:
    """마이페이지 — 프로필 · 광고 기본값.

    ⛔ 저장할 테이블이 없다 (사용자UI 정리 4-7 — 「추가해야 할 스키마」). 폼만 세운다.
    """
    return templates.TemplateResponse(request, "user/mypage.html", {"picked": _MYPAGE_BLANK})


@router.post("/mypage", response_class=HTMLResponse)
async def mypage_save(request: Request) -> HTMLResponse:
    """마이페이지 저장 — 🚨 **저장하지 않는다.**

    ⛔ 사용자 계정·광고 기본값 테이블이 스키마에 없다. `app_account` 는 거버넌스
       운영자용이라 여기에 쓰지 않는다. **가짜 성공을 그리지 않는다** (D-147) —
       받은 값을 되돌려 그리고 저장되지 않았다고 화면이 말한다.
    ⬜ 스키마가 서면 여기서 쓰고 「저장했습니다」로 바꾼다.
    """
    form = await _form(request)
    picked = {k: _one(form, k, limit) for k, limit in _MYPAGE_FIELDS.items()}
    return templates.TemplateResponse(
        request,
        "user/mypage.html",
        {"picked": picked, "saved_attempt": True},
    )
