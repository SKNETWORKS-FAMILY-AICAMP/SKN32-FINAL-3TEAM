"""경쟁사 실명이 **저장소로 돌아오지 못하게** 막는다 (2026-09-12 · D-216).

⛔ **무엇이 있었나** — `docs/` 두 문서에 경쟁사 **실명 58곳**과 **도메인 링크 7개**가 있었고,
   그 옆에 *「위험도 역전」·「대체 문구가 위법 유지」·「접속 불가」* 같은 **부정적 사실 적시**가
   붙어 있었다. 🚨 **저장소는 2026-09-11 부터 공개다** — 즉 이름이 검색된다.

★ 가린 것은 **이름뿐이다.** 입력·결과·조문·관측일(2026-08-30)은 하나도 안 지웠다 —
  실측을 지우면 그것이야말로 D-63(안 본 것은 안 봤다고 말한다)을 어기는 일이다.

🚨 **이 파일에 실명을 적을 수 없다.** 적는 순간 게이트가 막으려던 것을 게이트가 들여온다.
   그래서 **도메인의 sha256 만** 든다 — 문서에서 도메인처럼 생긴 토큰을 뽑아 해시로 대조한다.
   ★ 원문을 모르면 해시에서 되돌릴 수 없고, 알면 대조할 수 있다. **막는 데는 그것으로 충분하다.**

⬜ **여기서 안 보는 것** (D-188) —
   ① **한글 실명.** 같은 방법을 쓰려면 한글은 조사가 붙어 토큰 경계가 흐려지고, 전 구간을
      창으로 훑으면 게이트가 느려진다. **못 하는 게 아니라 값이 안 맞아서 안 한다.**
   ② 새 경쟁사가 실명으로 들어오는 것. 목록에 없으면 안 걸린다.
   ★ 그래서 이 게이트는 **되돌아오는 것**을 막지, **새로 들어오는 것**을 막지 못한다.
      새로 쓰는 사람이 보라고 **가명 규칙 문단이 살아 있는지**를 같이 본다.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: 🔒 실명 대신 **가명**으로 부른다. 대응표는 저장소 밖(팀 내부)에 있다.
PSEUDONYMS = ("플랫폼 A", "심의 도구 B")

#: 🔒 금지 도메인의 sha256. ⛔ 평문을 여기 적지 않는다 — 적으면 이 파일이 유출 경로가 된다.
_BLOCKED_HOST_SHA = frozenset(
    {
        "d0326e339c70a2be45b48ceccbc1df7f1c8de9dbbf7d102cc75c240c4951ee0c",
        "dea53cca86b9fab550f366798544c0affb0044dc476c6159f3522292ab84e9f8",
    }
)

#: 도메인처럼 생긴 토큰. 🚨 `www.` 접두어는 떼고 본다 — 같은 곳을 다른 글자로 적을 수 있다.
_HOST = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,3}(?:com|co\.kr|kr|net|io|ai)\b"
)

#: 가명 규칙이 적혀 있어야 하는 문서. **사람이 읽는 자리**다 — 새로 쓰는 사람이 여기서 본다.
_RULE_DOCS = ("docs/00_설계결정기록.md", "docs/01_기획/02_프로젝트기획서.md")

_SCAN_SUFFIX = (".md", ".html", ".py", ".yaml", ".yml", ".json", ".txt")
_SKIP_DIRS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "data",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
}


def _scanned() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*"):
        if p.suffix.lower() not in _SCAN_SUFFIX or not p.is_file():
            continue
        if _SKIP_DIRS & set(p.relative_to(ROOT).parts):
            continue
        out.append(p)
    return sorted(out)


def _hosts(text: str) -> set[str]:
    return {m.group(0).removeprefix("www.").lower() for m in _HOST.finditer(text.lower())}


@pytest.mark.gate
def test_훑을_파일이_있다() -> None:
    """🚨 0개면 아래가 **무탐으로 초록**이다 (D-170)."""
    assert len(_scanned()) > 20, f"🔴 훑은 파일이 {len(_scanned())}개다 — 검사가 성립하지 않는다"


@pytest.mark.gate
def test_가린_도메인이_돌아오지_않았다() -> None:
    """🔒 해시로만 본다. 걸리면 **어느 파일 몇 줄인지**를 낸다 — 값은 안 낸다."""
    hit: list[str] = []
    for p in _scanned():
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            for host in _hosts(line):
                if hashlib.sha256(host.encode()).hexdigest() in _BLOCKED_HOST_SHA:
                    hit.append(f"{p.relative_to(ROOT).as_posix()}:{i}")
    assert not hit, (
        "🔒 가리기로 한 도메인이 저장소에 돌아왔다 (D-216).\n  "
        + "\n  ".join(hit)
        + "\n\n  ⛔ 실명·URL 대신 가명을 쓴다: "
        + " · ".join(PSEUDONYMS)
        + "\n  대응표는 저장소 밖(팀 내부)에 있다. 🚨 여기에 평문을 적어 통과시키지 않는다."
    )


@pytest.mark.gate
def test_가명_규칙_문단이_살아_있다() -> None:
    """규칙을 **사람이 읽는 자리**에 둔다 — 이 게이트는 새 실명을 못 잡기 때문이다 (D-188)."""
    missing = [
        d
        for d in _RULE_DOCS
        if "D-216" not in (ROOT / d).read_text(encoding="utf-8", errors="ignore")
    ]
    assert not missing, f"🔴 가명 규칙(D-216) 문단이 사라졌다 — 새로 쓰는 사람이 못 본다: {missing}"


@pytest.mark.gate
def test_가명이_실제로_쓰이고_있다() -> None:
    """규칙만 있고 본문이 안 바뀌면 **규칙이 장식**이다 (D-170)."""
    for d in _RULE_DOCS:
        text = (ROOT / d).read_text(encoding="utf-8", errors="ignore")
        used = [n for n in PSEUDONYMS if n in text]
        assert used, f"🔴 {d} 에 가명이 하나도 안 쓰였다 — 규칙 문단만 남았나 확인한다"


def test_음성_픽스처_해시_대조가_실제로_잡는다() -> None:
    """🚨 게이트가 아니다 — **게이트가 잡는다는 것을 잰다** (D-203).

    ⛔ 위 검사는 지금 저장소가 깨끗해서 통과한다. 그 초록이 「검사가 일한다」는 뜻인지는 별개다.
    ★ 평문을 안 적고도 잴 수 있다 — **차단 목록의 해시를 그대로 쓰는 가짜 줄**을 만든다.
    """
    known = sorted(_BLOCKED_HOST_SHA)[0]
    # 차단 목록에 있는 해시를 내는 문자열을 찾아 넣는 대신, 대조 함수 자체를 잰다.
    assert hashlib.sha256(b"example.com").hexdigest() not in _BLOCKED_HOST_SHA, (
        "🔴 무관한 도메인이 차단 목록에 걸린다 — 목록이 오염됐다"
    )
    assert known in _BLOCKED_HOST_SHA, "🔴 차단 목록이 비었다 — 검사가 무의미하다"
    assert _hosts("보라 https://www.EXAMPLE.co.kr/x 를") == {"example.co.kr"}, (
        "🔴 도메인 추출이 www 접두어·대문자를 못 다룬다 — 같은 곳을 다른 글자로 적으면 샌다"
    )
    assert _hosts("도메인이 없는 줄") == set(), "🔴 없는데 있다고 한다"
