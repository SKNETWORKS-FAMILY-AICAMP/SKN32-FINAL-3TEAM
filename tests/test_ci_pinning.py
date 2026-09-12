"""CI 가 **남의 태그를 믿지 않게** 막는다 (2026-09-12 밤 · D-215).

⛔ **무엇이 있었나** — 워크플로 둘의 `uses:` 넷이 전부 태그 핀이었다
   (`actions/checkout@v4` · `astral-sh/setup-uv@v5` · `actions/cache@v4`).
   🚨 **태그는 옮길 수 있다.** 액션 소유자 계정이 털리면 `v4` 가 다른 커밋을 가리키고
   그 코드가 **우리 runner 안에서** 돈다. 저장소를 체크아웃한 채로.

★ 지금 등급은 낮다 — 잰 결과 `${{ secrets.* }}` 참조가 **0개**이고
  `permissions: contents: read` 라 훔칠 것이 없다.
  🔴 **등급이 올라가는 시점이 정해져 있다** — 배포를 CI 에 붙이면(D-208 · ssm) 이 파일이
  배포 자격증명을 만지는 파일이 된다. 그때 태그 핀은 **키의 주인을 태그 주인에게 넘기는 것**이다.
  ⛔ 그날 고치면 늦다. 팀원 코드가 0줄인 지금이 가장 싼 순간이다 (D-213 의 lock 논거와 같은 모양).

🚨 **규칙보다 검사가 먼저다** (D-117). 「SHA 로 핀한다」를 문서에만 적으면, 다음에 액션을
   하나 더 붙이는 사람은 공식 문서의 `@v4` 를 복사해 온다. 그게 정상이다 — **막아야 한다.**

★ **컨테이너 이미지도 같이 본다.** 처음에는 ⬜(사유만 적혀 있나)로 뒀다가 같은 밤에
  다이제스트를 재서 **「있나」로 올렸다** — 사유 검사는 다 박고 나면 **영원히 초록**이다 (D-170).

⬜ **여기서 안 보는 것** (D-188) — 액션 SHA 가 *어느 판을 가리키는지*. 옆의 `# vX.Y.Z` 주석이
   맞는지는 **아무도 안 검사한다.** 주석이 틀려도 CI 는 옳게 돈다(SHA 가 뜻을 정한다) —
   틀리는 것은 **사람이 읽는 쪽**이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: 🔴 `uses: owner/repo@<40자리 16진수>` 만 통과. 🚨 **찾는 모양을 글자로 안 적는다** —
#:    `@v4` 를 글자로 적으면 이 파일이 자기를 잡는다 (D-206 곁가지 ②에서 하루에 세 번 밟았다).
_USES = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)")
_SHA_PIN = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w.-]+)*@[0-9a-f]{40}$")

#: 로컬 액션(`./.github/actions/…`)은 우리 저장소 안이라 SHA 가 뜻이 없다.
_LOCAL = re.compile(r"^\./")

#: 🚨 `pull_request_target` 은 **fork 의 코드가 우리 secrets 를 쥐고** 도는 트리거다.
#:    쓸 이유가 지금 없고, 생기면 그때 판정한다 — 조용히 들어오는 길을 막는다.
_FORBIDDEN_TRIGGER = re.compile(r"^\s*pull_request_target\s*:", re.MULTILINE)

#: 🔴 `run:` 안에서 `${{ github.event.… }}` 를 펼치면 **셸 주입**이다 — PR 제목에
#:    백틱을 넣으면 runner 에서 돈다. `env:` 를 거치면 안전하다.
_RUN_INJECTION = re.compile(r"run:.*\$\{\{\s*github\.(event|head_ref)\b")

#: 🔴 컨테이너 이미지 참조. `uses:` 와 **같은 이유로** 다이제스트를 박는다 —
#:    태그는 옮길 수 있고, 이 이미지는 **우리 저장소 이력 전체를 읽는다.**
#:    🚨 태그를 지우지 않는다 — `.pre-commit-config.yaml` 의 `rev` 와 대조하는 데 쓴다 (D-99).
_IMAGE_REF = re.compile(
    r"(?P<img>(?:ghcr\.io|docker\.io|quay\.io)/[\w./-]+)"
    r"(?P<tag>:[\w.-]+)?"
    r"(?P<digest>@sha256:[0-9a-f]{64})?"
)


def _workflows() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))


@pytest.mark.gate
def test_워크플로가_적어도_하나는_있다() -> None:
    """🚨 없는데 통과하면 아래 전부가 **무탐으로 초록**이다 (D-170)."""
    assert _workflows(), f"🔴 {WORKFLOWS} 에 워크플로가 없다 — 아래 게이트가 아무것도 안 본다"


@pytest.mark.gate
def test_uses_는_전부_커밋_SHA_로_못박혀_있다() -> None:
    """태그는 옮길 수 있다. **뜻을 정하는 것은 SHA 다.**"""
    bad: list[str] = []
    for wf in _workflows():
        for i, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = _USES.match(line)
            if not m:
                continue
            ref = m.group("ref")
            if _LOCAL.match(ref) or _SHA_PIN.match(ref):
                continue
            bad.append(f"{wf.name}:{i} — {ref}")
    assert not bad, (
        "🔴 태그로 핀된 액션이 있다 — 태그는 옮길 수 있다 (D-215).\n  "
        + "\n  ".join(bad)
        + "\n\n  재는 법:  git ls-remote --tags https://github.com/<owner>/<repo>"
        + "\n  `refs/tags/vX^{}` 줄이 있으면 **그쪽**이 커밋이다 (annotated tag)."
        + "\n  적는 법:  uses: owner/repo@<40자리 SHA>  # vX.Y.Z"
    )


@pytest.mark.gate
def test_SHA_옆에_사람이_읽을_판번호가_있다() -> None:
    """SHA 만 있으면 **무엇을 고정했는지 사람이 모른다** — 올릴 때 무엇이 바뀌는지도 모른다."""
    naked: list[str] = []
    for wf in _workflows():
        for i, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = _USES.match(line)
            if m and _SHA_PIN.match(m.group("ref")) and "#" not in line.split("uses:", 1)[1]:
                naked.append(f"{wf.name}:{i}")
    assert not naked, "🔴 SHA 옆에 `# vX.Y.Z` 주석이 없다 — 사람이 판을 못 읽는다: " + ", ".join(
        naked
    )


@pytest.mark.gate
def test_fork_가_secrets_를_쥐는_트리거가_없다() -> None:
    """`pull_request_target` — fork 의 코드를 **우리 권한으로** 돌리는 트리거."""
    hit = [
        wf.name for wf in _workflows() if _FORBIDDEN_TRIGGER.search(wf.read_text(encoding="utf-8"))
    ]
    assert not hit, (
        "🔴 `pull_request_target` 이 있다 — fork PR 이 저장소 secrets 를 쥔다 (D-215). "
        f"쓸 이유가 있으면 D 로 판정하고 이 게이트를 고친다: {hit}"
    )


@pytest.mark.gate
def test_run_안에서_PR_문자열을_펼치지_않는다() -> None:
    """PR 제목·브랜치명은 **남이 쓴 문자열**이다. `run:` 에 펼치면 셸 주입이다."""
    bad: list[str] = []
    for wf in _workflows():
        for i, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            if _RUN_INJECTION.search(line):
                bad.append(f"{wf.name}:{i}")
    assert not bad, (
        "🔴 `run:` 안에 `${{ github.event.* }}` 가 펼쳐진다 — 스크립트 주입 (D-215). "
        f'`env:` 로 넘기고 `"$VAR"` 로 받는다: {bad}'
    )


@pytest.mark.gate
def test_권한을_명시하지_않은_워크플로가_없다() -> None:
    """`permissions` 를 안 적으면 **저장소 기본값**이 붙는다 — 기본이 write 인 저장소가 있다."""
    missing = [
        wf.name
        for wf in _workflows()
        if not re.search(r"^permissions\s*:", wf.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert not missing, (
        f"🔴 `permissions:` 가 없다 — 최소 권한을 워크플로가 스스로 적는다: {missing}"
    )


@pytest.mark.gate
def test_컨테이너_이미지도_다이제스트로_못박혀_있다() -> None:
    """`uses:` 와 **같은 이유**다 — 태그는 옮길 수 있다.

    🚨 이 이미지(gitleaks)는 **저장소 이력 전체**를 읽는다. 바꿔치기당하면 「no leaks」를
       내는 이미지가 우리 이력을 훑고 초록을 준다 — **무탐이 안심시킨다** (D-188).
    ★ 2026-09-12 밤에 닫았다. 그 전까지는 사유만 적힌 ⬜ 였다.
    """
    bad: list[str] = []
    for wf in _workflows():
        text = wf.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):  # 주석 속 예시는 대상이 아니다
                continue
            for m in _IMAGE_REF.finditer(line):
                if not m.group("digest"):
                    bad.append(f"{wf.name}:{line_no} — {m.group(0)}")
    assert not bad, (
        "🔴 다이제스트 없는 컨테이너 이미지가 있다 (D-215).\n  "
        + "\n  ".join(bad)
        + "\n\n  재는 법:  docker buildx imagetools inspect <이미지>:<태그>"
        + "\n  맨 위 `Digest:` 줄을 쓴다 — Manifests 아래의 플랫폼별 것이 아니다."
        + "\n  적는 법:  <이미지>:<태그>@sha256:…  ← **태그를 지우지 않는다** (D-99 비교가 읽는다)"
    )


def test_음성_픽스처_태그_핀을_실제로_잡는다() -> None:
    """🚨 게이트가 아니다 — **게이트가 잡는다는 것을 잰다** (D-203).

    ⛔ 위의 검사들은 **지금 저장소가 깨끗해서** 통과한다. 그 초록이 「검사가 일한다」는
       뜻인지는 별개다 — 정규식 하나만 틀려도 영원히 초록이다 (D-170).
    """
    leaky = "      - uses: actions/checkout@v4\n"
    m = _USES.match(leaky)
    assert m, "🔴 음성 픽스처를 정규식이 아예 못 읽는다 — 검사가 무의미하다"
    assert not _SHA_PIN.match(m.group("ref")), "🔴 태그 핀을 SHA 핀으로 읽는다 — 검사가 무의미하다"

    ok = "      - uses: actions/checkout@" + "0" * 40 + " # v4.4.0\n"
    m2 = _USES.match(ok)
    assert m2 and _SHA_PIN.match(m2.group("ref")), "🔴 정상 SHA 핀을 거부한다 — 게이트가 못 쓰인다"

    inj = '        run: echo "${{ github.event.pull_request.title }}"\n'
    assert _RUN_INJECTION.search(inj), "🔴 주입 모양을 못 잡는다 — 검사가 무의미하다"

    naked_img = _IMAGE_REF.search("ghcr.io/gitleaks/gitleaks:v8.30.0 git /repo")
    assert naked_img and not naked_img.group("digest"), "🔴 태그뿐인 이미지를 못 잡는다"
    pinned = _IMAGE_REF.search("ghcr.io/gitleaks/gitleaks:v8.30.0@sha256:" + "0" * 64)
    assert pinned and pinned.group("digest"), "🔴 다이제스트 핀을 거부한다 — 게이트가 못 쓰인다"
