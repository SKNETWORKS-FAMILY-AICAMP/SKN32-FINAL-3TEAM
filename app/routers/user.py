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

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contracts import PASS_RISK_MAX, Risk
from app.db import get_session, reachable
from app.formbody import read_capped
from app.models import CopySentence, Judgment
from app.settings import PARAMS
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
    path = _screen_path(request.url.path)
    section = _SCREEN_SECTION.get(path)
    ctx.setdefault("active_section", section)
    ctx.setdefault("section_label", _SECTION_LABELS.get(section) if section else None)
    ctx.setdefault("section_subs", _SECTION_SUBS.get(section) if section else None)
    ctx.setdefault(
        "active_sub", active_sub if active_sub is not None else _SECTION_ACTIVE_SUB.get(path)
    )
    return templates.TemplateResponse(request, template, ctx)


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
      (D-125 통과 조건의 위험도 문턱 = R1 · D-227)을 그대로 쓴다 — 문턱을 여기서 따로 두지 않는다.
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


@router.get("/review", response_class=HTMLResponse)
def review(request: Request) -> HTMLResponse:
    """문구 검수 입력 화면 (SCR-A, ksr 2026-09-13)."""
    return _render(
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
    return _render(
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
    return _render(
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


@router.get("/cs", response_class=HTMLResponse)
def cs(request: Request) -> HTMLResponse:
    """고객센터 문의 — ★ **골격만**. 각 구역 사이드바 하단 버튼으로만 들어온다 (구역 밖)."""
    return _render(request, "user/cs.html")


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


#: 마이페이지 가로 탭 (key, label). 프로토타입의 포트폴리오 · 구성원 관리 · 결제 탭은
#: 매칭/과금 범위라 뺐다. ⛔ 탭 전환을 스크립트로 하지 않는다 (CSP) — `?tab=` 으로 고른다.
_MYPAGE_TABS: tuple[tuple[str, str], ...] = (
    ("profile", "프로필"),
    ("defaults", "광고 기본값"),
    ("account", "계정"),
)
_MYPAGE_SECTION_TAB = {"profile": "profile", "adprefs": "defaults"}


@router.get("/mypage", response_class=HTMLResponse)
def mypage(request: Request, tab: str = "profile") -> HTMLResponse:
    """마이페이지 — 프로필 · 광고 기본값 · 계정 탭 (ksr 2026-09-13).

    ⛔ 저장할 테이블이 없다 — 폼만 세운다. 상단 오른쪽 아바타 버튼으로 들어온다 (구역 밖).
    """
    if tab not in dict(_MYPAGE_TABS):
        tab = "profile"
    return _render(
        request,
        "user/mypage.html",
        {"picked": _MYPAGE_BLANK, "tab": tab, "tabs": _MYPAGE_TABS},
    )


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
    return _render(
        request,
        "user/mypage.html",
        {
            "picked": picked,
            "saved_attempt": True,
            "tab": _MYPAGE_SECTION_TAB.get(_one(form, "section", 16), "profile"),
            "tabs": _MYPAGE_TABS,
        },
    )


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


@router.get("/reset", response_class=HTMLResponse)
def user_reset(request: Request) -> HTMLResponse:
    """비밀번호 재설정 — ★ **골격만, 제출 버튼 없음**. login.html과 같은 이유로
    계정 테이블이 없어 재설정 링크를 보낼 대상이 없다 — 입력만 보여준다.
    """
    return templates.TemplateResponse(request, "user/reset.html", {})
