"""README 가 말하는 것과 저장소가 실제로 가진 것이 같은가 (D-99 · D-170).

README 는 **공개 저장소의 첫 화면**이고, 명령 이름과 폴더 구조를 글자로 든다.
글자는 코드를 따라오지 않는다 — 명령을 지우거나 폴더를 옮기면 README 만 남는다.

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89 · `test_launcher_menu.py` 와 같은 자리).
   CI `tests` 잡이 `pytest -m gate` 뒤에 **전체**를 돌리므로 PR 에서는 걸린다.
   ⚠️ `launcher.py check` 는 gate 만 돌리므로 **로컬 커밋 전에는 안 걸린다** — 그 사실을 여기 적어 둔다.

⛔ 여기에 명령 이름이나 폴더 이름을 **적지 않는다.** 정본은 `launcher.app`(명령)과 디스크(구조)다.
   이 파일이 이름을 들면 세 번째 벌이 된다.
"""

from __future__ import annotations

import re
from pathlib import Path

import launcher

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def _registered_commands() -> set[str]:
    """Typer 에 등록된 CLI 명령 이름 — `name=` 이 있으면 그것, 없으면 함수명에서 (`db_up` → `db-up`)."""
    return {
        info.name or launcher.cli_name(info.callback) for info in launcher.app.registered_commands
    }


def _readme_commands() -> list[tuple[int, str]]:
    """README 본문에서 `launcher.py <명령>` 꼴을 전부 줍는다 — 코드 블록·본문·표 가리지 않는다.

    `launcher.py` 뒤에 아무것도 없거나 옵션(`-`)이 오면 「메뉴 실행」이므로 명령이 아니다.
    """
    found: list[tuple[int, str]] = []
    for no, line in enumerate(README.read_text(encoding="utf-8").splitlines(), 1):
        for m in re.finditer(r"launcher\.py\s+([A-Za-z][\w-]*)", line):
            found.append((no, m.group(1)))
    return found


def test_readme_의_명령은_전부_런처에_있다() -> None:
    """🔴 README 가 든 `launcher.py <명령>` 이 등록돼 있지 않으면 첫 화면이 거짓말을 한다."""
    registered = _registered_commands()
    missing = [(no, cmd) for no, cmd in _readme_commands() if cmd not in registered]
    assert not missing, "README 가 든 명령이 launcher 에 없다: " + ", ".join(
        f"L{no} `{cmd}`" for no, cmd in missing
    )


def test_readme_가_명령을_하나_이상_든다() -> None:
    """🚨 위 검사는 README 에 명령이 하나도 없으면 **통과**한다 — 실패할 수 없는 단언이 된다 (D-170).
    README 에서 명령 블록이 통째로 사라지면 여기서 걸린다."""
    assert _readme_commands(), "README 에 `launcher.py <명령>` 이 하나도 없다"


def _readme_tree_paths() -> list[tuple[int, str]]:
    """「저장소 구조」 트리의 **최상위** 항목만 줍는다 (`├── ` · `└── ` 로 시작하는 줄).

    한 줄에 `setup.bat / setup.ps1` 처럼 둘이 오면 둘 다 본다.
    깊은 항목(`data/raw/` 등)은 보지 않는다 — `data/**` 는 커밋되지 않아 클론마다 답이 다르다 (D-19).
    """
    text = README.read_text(encoding="utf-8")
    m = re.search(r"^## 저장소 구조\s*$(.*?)^## ", text, re.S | re.M)
    assert m, "README 에 「## 저장소 구조」 절이 없다"
    paths: list[tuple[int, str]] = []
    start = text[: m.start(1)].count("\n") + 1
    for offset, line in enumerate(m.group(1).splitlines()):
        if not line.startswith(("├── ", "└── ")):
            continue
        label = line[4:].split("  ", 1)[0]  # 두 칸 공백 앞까지가 경로 칸
        for token in label.split(" / "):
            token = token.strip().rstrip("/")
            if token:
                paths.append((start + offset, token))
    return paths


def test_readme_구조_트리의_최상위_항목이_디스크에_있다() -> None:
    """🔴 폴더를 옮기거나 지우면 트리가 낡는다. 트리에 적힌 것은 실제로 있어야 한다."""
    missing = [(no, p) for no, p in _readme_tree_paths() if not (ROOT / p).exists()]
    assert not missing, "README 구조 트리에 있는데 디스크에 없다: " + ", ".join(
        f"L{no} `{p}`" for no, p in missing
    )


def test_readme_구조_트리가_비어_있지_않다() -> None:
    """🚨 절 제목만 남고 트리가 사라져도 위 검사는 통과한다 (D-170)."""
    assert len(_readme_tree_paths()) >= 5, "README 구조 트리가 비었거나 형식이 바뀌었다"
