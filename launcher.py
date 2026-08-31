"""launcher.py — CopyLane 진입점 (D-51).

🚨 launcher 는 얇은 껍데기다. 로직은 전부 밖에 있다 (기획서 7-5).

    O  launcher -> subprocess -> `uv run pytest`
    X  launcher 안에 테스트·수집·학습 로직 직접 구현

로직이 여기 들어가면 CI·재현 스크립트·개별 실행에서 쓸 수 없다.
메뉴는 진입점이지 진실의 원천이 아니다.

이중 인터페이스 (Typer):
    uv run python launcher.py            # 대화형 메뉴
    uv run python launcher.py doctor     # 직접 실행 (CI·자동화)
    uv run python launcher.py test -k gate
"""

from __future__ import annotations

import contextlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

ROOT = Path(__file__).resolve().parent
console = Console()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="CopyLane 작업 진입점 — 인자 없이 실행하면 대화형 메뉴가 뜬다.",
)


# ══════════════════════════════════════════════════════════
# 공통 — 바깥 명령을 부르는 것이 이 파일의 전부다
# ══════════════════════════════════════════════════════════
def run(*args: str) -> int:
    """subprocess 로 위임한다. 여기서 로직을 처리하지 않는다."""
    console.print(f"[dim]$ {' '.join(args)}[/dim]")
    return subprocess.run(args, cwd=ROOT).returncode


def planned(name: str, when: str, needs: str) -> None:
    """아직 대상 스크립트가 없는 메뉴. 눌러도 에러 대신 현황을 보여준다."""
    console.print(
        Panel(
            f"[yellow]{name}[/yellow] 은(는) 아직 구현되지 않았다.\n\n"
            f"  예정   {when}\n"
            f"  선행   {needs}",
            title="미구현",
            border_style="yellow",
        )
    )


def _git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "?"


def _docker_state() -> str:
    if shutil.which("docker") is None:
        return "[red]없음[/red]"
    probe = subprocess.run(["docker", "info"], capture_output=True)
    return "[green]실행중[/green]" if probe.returncode == 0 else "[yellow]설치됨·미기동[/yellow]"


def _env_line() -> str:
    py = platform.python_version()
    env = (
        "[green]py" + py + "[/green]" if py.startswith("3.11") else f"[red]py{py} (3.11 아님)[/red]"
    )
    return f"branch: {_git_branch()}  ·  {env}  ·  docker: {_docker_state()}"


# ══════════════════════════════════════════════════════════
# 동작하는 명령
# ══════════════════════════════════════════════════════════
@app.command()
def setup() -> None:
    """환경 설정 — uv sync · pre-commit 훅 · .env 생성."""
    run("uv", "sync")
    run("uv", "run", "pre-commit", "install")

    env = ROOT / ".env"
    if env.exists():
        console.print("  [green]OK[/green]   .env 이미 있음")
    else:
        env.write_bytes((ROOT / ".env.example").read_bytes())
        console.print("  [green]생성[/green] .env  — [bold]LAW_OC_KEY 를 채워야 한다[/bold]")


@app.command()
def doctor() -> None:
    """환경·거버넌스 진단 — 무엇이 틀렸나가 아니라 어떻게 고치나를 낸다."""
    raise typer.Exit(run("uv", "run", "python", "scripts/doctor.py"))


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def test(ctx: typer.Context) -> None:
    """pytest 실행. 추가 인자는 그대로 넘어간다 (예: test -k gate)."""
    raise typer.Exit(run("uv", "run", "pytest", *ctx.args))


@app.command()
def gate() -> None:
    """거버넌스 게이트만 실행 — 실패하면 다음 단계로 가지 않는다 (D-51)."""
    raise typer.Exit(run("uv", "run", "pytest", "-m", "gate", "-v"))


@app.command()
def fmt() -> None:
    """포맷·린트 — ruff format + ruff check --fix."""
    run("uv", "run", "ruff", "format", ".")
    raise typer.Exit(run("uv", "run", "ruff", "check", "--fix", "."))


@app.command(name="db-up")
def db_up() -> None:
    """postgres + pgvector 컨테이너 기동 (127.0.0.1:5432)."""
    if run("docker", "compose", "up", "-d") != 0:
        console.print(
            Panel(
                "docker compose 가 실패했다.\n\n"
                "  1. Docker Desktop 이 켜져 있는가\n"
                "  2. 없다면 setup.bat 을 다시 실행하면 켜준다",
                title="DB 기동 실패",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    # 🚨 init 스크립트는 볼륨이 비어 있을 때만 돈다. 기존 볼륨에는 여기서 붙인다.
    run(
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "copylane",
        "-d",
        "copylane",
        "-c",
        "CREATE EXTENSION IF NOT EXISTS vector;",
    )
    console.print("  [green]DB 준비 완료[/green]  127.0.0.1:5432  (pgvector 확장 포함)")


@app.command(name="db-down")
def db_down() -> None:
    """컨테이너 중지 — 데이터는 볼륨에 남는다."""
    raise typer.Exit(run("docker", "compose", "stop"))


# ══════════════════════════════════════════════════════════
# 아직 대상이 없는 명령 — 메뉴에는 보이되 눌러도 안전하다
# ══════════════════════════════════════════════════════════
@app.command()
def migrate() -> None:
    """DB 마이그레이션 (Alembic)."""
    planned("migrate", "W2", "alembic/ 초기화 + postgres 기동")


@app.command()
def collect() -> None:
    """데이터 수집 — 게이트 통과분만 (D-15)."""
    planned("collect", "W2", "scripts/collect.py 수집 로직 구현")


@app.command()
def golden() -> None:
    """골든셋 생성 (결함 주입)."""
    planned("golden", "W3", "수집 코퍼스 확보")


@app.command()
def train() -> None:
    """학습 — 인코더 / sLLM."""
    planned("train", "W4~", "골든셋 · GPU 경로 확정")


@app.command(name="eval")
def eval_() -> None:
    """평가 — 전체 / 지표 선택."""
    planned("eval", "W4~", "학습 산출물")


@app.command()
def serve() -> None:
    """API 서버 실행 (FastAPI)."""
    planned("serve", "W2", "walking skeleton")


@app.command()
def demo() -> None:
    """데모 모드 (오프라인 GGUF)."""
    planned("demo", "W8~", "GGUF 변환 · 오프라인 경로")


# ══════════════════════════════════════════════════════════
# 대화형 메뉴
# ══════════════════════════════════════════════════════════
MENU: list[tuple[str, str, str, bool]] = [
    ("1", "환경 설정", "setup", True),
    ("2", "환경 진단", "doctor", True),
    ("-", "", "", True),
    ("d", "DB 기동", "db-up", True),
    ("x", "DB 중지", "db-down", True),
    ("3", "DB 마이그레이션", "migrate", False),
    ("4", "데이터 수집", "collect", False),
    ("5", "골든셋 생성", "golden", False),
    ("-", "", "", True),
    ("6", "학습", "train", False),
    ("7", "평가", "eval", False),
    ("g", "Phase 게이트 판정", "gate", True),
    ("-", "", "", True),
    ("8", "서버 실행", "serve", False),
    ("9", "데모 모드", "demo", False),
    ("-", "", "", True),
    ("t", "테스트", "test", True),
    ("f", "포맷·린트", "fmt", True),
    ("q", "종료", "", True),
]

ACTIONS = {
    "setup": setup,
    "db-up": db_up,
    "db-down": db_down,
    "doctor": doctor,
    "gate": gate,
    "fmt": fmt,
    "migrate": migrate,
    "collect": collect,
    "golden": golden,
    "train": train,
    "eval": eval_,
    "serve": serve,
    "demo": demo,
}


def _draw() -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=3, justify="right")
    table.add_column(width=20)
    table.add_column(style="dim")

    for key, label, cmd, ready in MENU:
        if key == "-":
            table.add_row("", "", "")
            continue
        note = cmd if ready else f"{cmd}  (미구현)"
        # 🚨 Rich 는 대괄호를 마크업으로 읽는다. [g]·[t] 같은 한 글자 키가 통째로 사라진다.
        #    escape 로 리터럴 대괄호를 만든다.
        table.add_row(
            escape(f"[{key}]"),
            f"[dim]{label}[/dim]" if not ready else label,
            note,
        )

    console.print(Panel(table, title="CopyLane Launcher", subtitle=_env_line()))


def menu() -> None:
    while True:
        _draw()
        choice = console.input("  선택 > ").strip().lower()

        if not choice:
            continue
        if choice in {"q", "quit", "exit"}:
            return
        if choice == "t":
            run("uv", "run", "pytest")
            continue

        entry = next((m for m in MENU if m[0] == choice and m[0] != "-"), None)
        if entry is None:
            console.print("  [red]없는 항목이다[/red]")
            continue

        action = ACTIONS.get(entry[2])
        if action is None:
            continue
        # 각 명령은 종료 코드를 typer.Exit 로 던진다. 메뉴에서는 그걸로 끝내면 안 된다.
        with contextlib.suppress(typer.Exit):
            action()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """인자가 없으면 대화형 메뉴, 있으면 해당 명령을 직접 실행한다."""
    if ctx.invoked_subcommand is None:
        menu()


if __name__ == "__main__":
    sys.exit(app())
