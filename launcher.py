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
import functools
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


def stub(when: str, needs: str):
    """아직 대상이 없는 명령을 감싼다.

    🚨 「미구현」이라는 사실을 **한 곳에만** 적기 위한 것이다.
       예전에는 함수 본문과 메뉴 표(`ready` 플래그)에 따로 적었고, 그래서
       `doctor` 가 메뉴에서는 정상으로 보이면서 실행하면 죽는 상태가 됐다.
       이제 메뉴의 표기는 이 표시에서 나온다.
    """

    def deco(fn):
        @functools.wraps(fn)
        def wrapper() -> None:
            planned(cli_name(fn), when, needs)

        wrapper._planned = True
        return wrapper

    return deco


def cli_name(fn) -> str:
    """함수 이름 -> CLI 명령 이름. `db_up` -> `db-up`, `eval_` -> `eval`."""
    return getattr(fn, "_cli", fn.__name__.rstrip("_").replace("_", "-"))


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
@stub("W1", "scripts/doctor.py 본문 구현 — 지금은 검사 목록만 있는 자리표시자다")
def doctor() -> None:
    """환경·거버넌스 진단 — 무엇이 틀렸나가 아니라 어떻게 고치나를 낸다."""


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


@app.command()
def check() -> None:
    """커밋 직전 점검 — 포맷·린트 후 게이트.

    🚨 순서가 핵심이다. `ruff check` 만 돌리고 커밋하면 `ruff-format` 훅이
       커밋 시점에 파일을 고치고 커밋이 중단된다. 고칠 것을 **먼저** 고친다.
    """
    run("uv", "run", "ruff", "format", ".")
    if run("uv", "run", "ruff", "check", "--fix", ".") != 0:
        raise typer.Exit(1)
    raise typer.Exit(run("uv", "run", "pytest", "-m", "gate"))


# ══════════════════════════════════════════════════════════
# 데이터 거버넌스 — 레지스트리·검토표·매트릭스는 전부 생성물이다
# ══════════════════════════════════════════════════════════
@app.command()
def registry() -> None:
    """레지스트리 재생성 — registry_head/review/tail -> data_sources.yaml.

    🚨 `data_sources.yaml` 을 손으로 고치지 않는다. 생성물이다.
       판정·검토 기록은 `scripts/registry_review.yaml` 에 적는다.
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/gen_registry.py"))


@app.command()
def review() -> None:
    """S0-14 2인 확인 검토표 생성 (D-66 · D-99).

    판정 근거를 매트릭스에서 다시 뽑고 검토표를 낸다. 검토자는 A 구간을 자세히,
    B 를 확인, C 를 훑는다. 결과는 `scripts/registry_review.yaml` 에 적는다.
    """
    if run("uv", "run", "python", "scripts/extract_rationale.py") != 0:
        raise typer.Exit(1)
    raise typer.Exit(run("uv", "run", "python", "scripts/review_sheet.py"))


@app.command()
def matrix() -> None:
    """판정매트릭스 HTML 빌드 (D-87 · D-90)."""
    raise typer.Exit(run("uv", "run", "python", "scripts/build_matrix.py"))


@app.command()
def sync() -> None:
    """프로젝트 사본 생성 — build/project_sync/ 에 스탬프를 찍어 낸다.

    🚨 레포가 원본이고 claude.ai 프로젝트는 사본이다. 업로드 자체는 사람이 한다.
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/sync_project.py"))


@app.command()
@stub("W8", "제출 문서 목록 확정 — 지금은 `pdf <문서경로>` 로 한 건씩 뽑는다")
def package() -> None:
    """제출본 일괄 빌드 — 00_산출물현황.md 를 읽어 dist/ 를 만든다 (D-53)."""


@app.command()
def pdf(src: str) -> None:
    """제출용 PDF 빌드 (D-53) — 발행물 이름에는 버전이 붙는다.

    예:  python launcher.py pdf docs/01_기획/03_작업일정.md
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/build_pdf.py", src))


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
@stub("W2", "alembic/ 초기화 + postgres 기동")
def migrate() -> None:
    """DB 마이그레이션 (Alembic)."""


@app.command()
@stub("W2", "scripts/collect.py 수집 로직 구현")
def collect() -> None:
    """데이터 수집 — 게이트 통과분만 (D-15)."""


@app.command()
@stub("W3", "수집 코퍼스 확보")
def golden() -> None:
    """골든셋 생성 (결함 주입)."""


@app.command()
@stub("W4~", "골든셋 · GPU 경로 확정")
def train() -> None:
    """학습 — 인코더 / sLLM."""


@app.command(name="eval")
@stub("W4~", "학습 산출물")
def eval_() -> None:
    """평가 — 전체 / 지표 선택."""


@app.command()
@stub("W2", "walking skeleton")
def serve() -> None:
    """API 서버 실행 (FastAPI)."""


@app.command()
@stub("W8~", "GGUF 변환 · 오프라인 경로")
def demo() -> None:
    """데모 모드 (오프라인 GGUF)."""


# ══════════════════════════════════════════════════════════
# 대화형 메뉴
# ══════════════════════════════════════════════════════════
# 🚨 메뉴는 **함수를 직접 든다.** 예전에는 명령 이름 문자열을 든 MENU 와
#    이름->함수 표(ACTIONS)가 따로 있었고, 그 둘이 이미 어긋나 있었다
#    (`test` 가 MENU 에만 있고 ACTIONS 에는 없었다). 같은 사실을 두 곳에 두면
#    갈라진다 — D-99 와 같은 형태다.
#    「미구현」 표기도 여기 적지 않는다. @stub 이 붙었는지로 판정한다.


def _menu_test() -> None:
    run("uv", "run", "pytest")


_menu_test._cli = "test"

SEP = ("-", "", None)

MENU: list[tuple[str, str, object]] = [
    ("1", "환경 설정", setup),
    ("2", "환경 진단", doctor),
    SEP,
    ("d", "DB 기동", db_up),
    ("x", "DB 중지", db_down),
    ("3", "DB 마이그레이션", migrate),
    SEP,
    ("r", "레지스트리 재생성", registry),
    ("v", "S0-14 검토표", review),
    ("m", "판정매트릭스 빌드", matrix),
    ("s", "프로젝트 사본", sync),
    SEP,
    ("4", "데이터 수집", collect),
    ("5", "골든셋 생성", golden),
    ("6", "학습", train),
    ("7", "평가", eval_),
    ("8", "서버 실행", serve),
    ("9", "데모 모드", demo),
    SEP,
    ("g", "Phase 게이트 판정", gate),
    ("c", "커밋 전 점검", check),
    ("t", "테스트", _menu_test),
    ("f", "포맷·린트", fmt),
    ("q", "종료", None),
]


def _draw() -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=3, justify="right")
    table.add_column(width=20)
    table.add_column(style="dim")

    for key, label, fn in MENU:
        if key == "-":
            table.add_row("", "", "")
            continue
        ready = fn is None or not getattr(fn, "_planned", False)
        note = "" if fn is None else cli_name(fn) + ("" if ready else "  (미구현)")
        # 🚨 Rich 는 대괄호를 마크업으로 읽는다. [g]·[t] 같은 한 글자 키가 통째로 사라진다.
        #    escape 로 리터럴 대괄호를 만든다.
        table.add_row(
            escape(f"[{key}]"),
            label if ready else f"[dim]{label}[/dim]",
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

        entry = next((m for m in MENU if m[0] == choice and m[0] != "-"), None)
        if entry is None or entry[2] is None:
            console.print("  [red]없는 항목이다[/red]")
            continue

        # 각 명령은 종료 코드를 typer.Exit 로 던진다. 메뉴에서는 그걸로 끝내면 안 된다.
        with contextlib.suppress(typer.Exit):
            entry[2]()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """인자가 없으면 대화형 메뉴, 있으면 해당 명령을 직접 실행한다."""
    if ctx.invoked_subcommand is None:
        menu()


if __name__ == "__main__":
    sys.exit(app())
