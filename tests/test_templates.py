"""화면이 **XSS 를 못 만들게** 막는다 (2026-09-12 밤 · 보안점검 P2-9 · D-208).

⛔ **무엇이 있었나** — `app/templates/` 가 비어 있었고, 자동 이스케이프를 보는 검사도
   `|safe` 를 막는 검사도 **하나도 없었다.** 유일한 HTML 라우트는 손으로 쓴 문자열이었고,
   팀원 4명이 화면을 붙일 때 **그것을 본으로 복사한다** — `f"<li>{hit.text}</li>"` 한 줄이면
   P2-9 다.

🚨 **규칙보다 검사가 먼저다** (D-117). 병렬작업 계약 §8 ③ 은 `templates/` 공유 파일의
   **소유자도 아직 미정**인데, 소유자가 누구든 첫 커밋이 `|safe` 면 결과는 같다.
   ⛔ 그래서 소유자 판정보다 이 게이트가 앞선다.

★ 여기서 보는 것은 **화면이 그리는 방식**이지 화면의 내용이 아니다. 내용은 팀원 몫이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"

#: 🔴 문자열을 HTML 로 흘려보내는 모양들. **찾는 모양을 글자로 적지 않고 정규식으로 본다** —
#:    글자로 적으면 이 파일이 자기를 잡는다 (D-206 곁가지 ②에서 하루에 세 번 밟았다).
_UNSAFE = (
    (re.compile(r"\|\s*safe\b"), "자동 이스케이프를 끄는 필터"),
    (re.compile(r"\{\{\s*.*\|\s*e\s*\(\s*false", re.IGNORECASE), "이스케이프 해제"),
    (re.compile(r"\bautoescape\s+false\b", re.IGNORECASE), "블록 단위 이스케이프 해제"),
    (re.compile(r"\binnerHTML\b"), "DOM 에 문자열을 그대로 넣는 자리"),
    (re.compile(r"\bhx-swap-oob\s*=\s*[\"']?true.*<"), "HTMX 조각을 문자열로 조립"),
)


#: Jinja 주석 `{# … #}`. 🚨 **주석은 렌더되지 않으므로 검사 대상이 아니다.**
#:    ⛔ 주석을 안 빼면 「`|safe` 를 쓰지 않는다」라고 적은 주석이 자기를 잡는다 —
#:       실제로 이 게이트를 붙인 첫 실행에서 `base.html:6` 이 그렇게 걸렸다 (D-206 곁가지 ②).
_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)


def _templates() -> list[Path]:
    return sorted(TEMPLATES.rglob("*.html"))


def _rendered(f: Path) -> str:
    """주석을 지운 본문. 🚨 **줄 번호를 지키려고 개행은 남긴다.**"""
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), f.read_text(encoding="utf-8"))


@pytest.mark.gate
def test_템플릿이_비어_있지_않다() -> None:
    """🚨 골격이 없으면 팀원이 **손으로 쓴 HTML 문자열**을 본으로 삼는다 (D-124)."""
    assert _templates(), (
        "🔴 app/templates/ 에 템플릿이 없다.\n"
        "   화면이 붙기 전에 base.html 과 진입점 둘이 서 있어야 한다 (병렬작업 계약 §8 ⑥)"
    )


@pytest.mark.gate
def test_템플릿에_이스케이프를_끄는_모양이_없다() -> None:
    """🔴 **이것이 P2-9 를 막는 실물이다.** 규칙이 아니라 검사다 (D-117)."""
    bad: list[str] = []
    for f in _templates():
        text = _rendered(f)
        for pat, why in _UNSAFE:
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                bad.append(f"{f.relative_to(ROOT).as_posix()}:{line} — {why}")
    assert not bad, (
        "🔴 화면이 사용자 입력을 그대로 그릴 수 있다 (보안점검 P2-9):\n  "
        + "\n  ".join(bad)
        + "\n  고치는 법 — 하이라이트는 HTML 문자열이 아니라 (offset, length, type) 로 넘기고\n"
        "  템플릿이 그린다. 문자열로 조립하는 순간 이스케이프가 무의미해진다"
    )


@pytest.mark.gate
def test_자동_이스케이프가_켜져_있다() -> None:
    """⛔ Jinja2 의 기본값에 기대지 않고 **실제 환경에서** 확인한다."""
    from app.templating import templates

    assert templates.env.autoescape, "🔴 자동 이스케이프가 꺼져 있다 — 보안점검 P2-9"


@pytest.mark.gate
def test_만드는_자리가_하나다() -> None:
    """🚨 `Jinja2Templates(...)` 를 라우터마다 만들면 **설정이 사람마다 갈린다** (D-99).

    ⛔ 한 사람이 `autoescape=False` 를 주면 그 화면만 조용히 열린다.
    """
    me = Path(__file__).resolve()
    pat = re.compile(r"Jinja2Templates\s*\(")
    found = [
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*.py")
        if p.resolve() != me
        and not ({".venv", "build", "dist", "__pycache__"} & set(p.relative_to(ROOT).parts))
        and pat.search(p.read_text(encoding="utf-8"))
    ]
    assert found == ["app/templating.py"], (
        f"🔴 템플릿 엔진을 만드는 자리가 하나가 아니다: {found}\n"
        "   고치는 법 — app/templating.py 의 `templates` 를 import 한다 (D-99)"
    )


@pytest.mark.gate
def test_템플릿이_CSP_를_따로_들지_않는다() -> None:
    """🔄 **CSP 는 `app/api.py` 의 미들웨어 한 곳이 든다** (D-99 · D-212).

    ⛔ 종전에는 `base.html` 의 `<meta>` 에 있었다. 그러면 **이 템플릿을 쓰는 페이지에만**
       붙고, 손으로 쓴 HTML(`/`)과 JSON·오류 응답은 그 밖이었다.
    🚨 정책이 두 곳에 있으면 갈린다 — 여기서는 **없는지**를 보고, 실제로 붙는지는
       `tests/test_auth_boundary.py` 가 **응답 헤더를 받아** 본다.
    """
    for f in _templates():
        text = _rendered(f)
        assert "Content-Security-Policy" not in text, (
            f"🔴 {f.name} 이 CSP 를 따로 든다 — 정책의 단일 출처는 `app/api.py` 의 `_CSP_PAGE` 다"
        )


@pytest.mark.gate
def test_화면_폴더가_사람별로_갈려_있다() -> None:
    """🚨 §5 의 「같은 파일 두 사람 금지」를 **지킬 자리**가 있는지 본다 (D-208).

    ⛔ 폴더가 없으면 규칙이 지켜질 수 없다 — 규칙보다 구조가 먼저다.
    """
    for d in ("user", "admin"):
        assert (TEMPLATES / d).is_dir(), (
            f"🔴 app/templates/{d}/ 가 없다 — 화면을 사람별로 가를 자리가 없다 (§5)"
        )


def test_음성_픽스처_이스케이프_검사가_실제로_잡는다(tmp_path: Path) -> None:
    """🚨 게이트가 아니다 — **게이트가 잡는다는 것을 잰다** (D-203).

    ⛔ 통과만 하는 검사는 검사가 아니다. 위 규칙이 실제로 `|safe` 를 잡는지 여기서 본다.
    """
    f = tmp_path / "bad.html"
    f.write_text("<p>{{ user_input | safe }}</p>", encoding="utf-8")
    text = f.read_text(encoding="utf-8")
    assert any(pat.search(text) for pat, _ in _UNSAFE), "🔴 검사가 `|safe` 를 못 잡는다"
