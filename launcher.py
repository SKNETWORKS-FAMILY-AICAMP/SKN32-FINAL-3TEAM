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
    """처음 한 번. 필요한 것을 전부 설치하고 준비한다.

    파이썬 패키지(`uv sync`) · 커밋 훅(pre-commit) · 설정 파일(`.env`).
    """
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
    """내 PC 설정이 팀과 같은지 검사한다.

    틀린 것을 알리는 데서 끝내지 않고 **어떻게 고치는지**까지 낸다 (D-51 · D-89).
    """


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def test(ctx: typer.Context) -> None:
    """pytest 실행. 추가 인자는 그대로 넘어간다 (예: test -k gate)."""
    raise typer.Exit(run("uv", "run", "pytest", *ctx.args))


@app.command()
def gate() -> None:
    """다음 단계로 가도 되는지 검사한다.

    거버넌스 게이트만 골라 실행한다. **실패하면 진행하지 않는다** (D-51).
    """
    raise typer.Exit(run("uv", "run", "pytest", "-m", "gate", "-v"))


@app.command()
def fmt() -> None:
    """코드 서식과 import 순서를 자동으로 맞춘다."""
    run("uv", "run", "ruff", "format", ".")
    raise typer.Exit(run("uv", "run", "ruff", "check", "--fix", "."))


@app.command()
def check() -> None:
    """커밋 전에 한 번. 코드 정리 + 게이트 검사.

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
    """어떤 데이터를 수집해도 되는지 목록을 다시 만든다.

    🚨 `data_sources.yaml` 을 손으로 고치지 않는다. 생성물이다.
       판정·검토 기록은 `scripts/registry_review.yaml` 에 적는다.
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/gen_registry.py"))


@app.command()
def review() -> None:
    """다른 사람이 등급 판정을 재확인할 표를 뽑는다.

    판정 근거를 매트릭스에서 다시 뽑고 검토표를 낸다. 검토자는 A 구간을 자세히,
    B 를 확인, C 를 훑는다. 결과는 `scripts/registry_review.yaml` 에 적는다.
    """
    if run("uv", "run", "python", "scripts/extract_rationale.py") != 0:
        raise typer.Exit(1)
    raise typer.Exit(run("uv", "run", "python", "scripts/review_sheet.py"))


@app.command()
def matrix() -> None:
    """소스별 등급 근거 페이지를 다시 만든다.

    소스마다 왜 그 등급인지를 정리한 HTML 이다.
    `_matrix/data.js` -> `sources.json` + `판정매트릭스.html` (D-87 · D-90).
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/build_matrix.py"))


@app.command()
def sync() -> None:
    """문서를 claude.ai 프로젝트에 올릴 사본으로 복사한다.

    🚨 레포가 원본이고 claude.ai 프로젝트는 사본이다. 업로드 자체는 사람이 한다.
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/sync_project.py"))


@app.command()
@stub("W8", "제출 문서 목록 확정 — 지금은 `pdf <문서경로>` 로 한 건씩 뽑는다")
def package() -> None:
    """제출용 PDF 를 한꺼번에 만든다.

    `00_산출물현황.md` 의 목록을 읽어 `dist/` 에 낸다 (D-53).
    """


@app.command()
def pdf(src: str) -> None:
    """문서 하나를 제출용 PDF 로 만든다. 파일 이름에 버전이 붙는다.

    예:  python launcher.py pdf docs/01_기획/03_작업일정.md
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/build_pdf.py", src))


@app.command(name="db-up")
def db_up() -> None:
    """로컬 데이터베이스를 켠다 (Docker Desktop 필요).

    postgres + pgvector 컨테이너. `127.0.0.1` 에만 열린다 (P3-14).
    """
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
    """데이터베이스를 끈다. 저장된 데이터는 그대로 남는다."""
    raise typer.Exit(run("docker", "compose", "stop"))


# ══════════════════════════════════════════════════════════
# 아직 대상이 없는 명령 — 메뉴에는 보이되 눌러도 안전하다
# ══════════════════════════════════════════════════════════
@app.command()
def migrate() -> None:
    """데이터베이스 테이블을 최신 상태로 맞춘다.

    Alembic 으로 스키마 변경을 코드로 남긴다. DB 가 떠 있어야 한다 (`db-up`).
    """
    raise typer.Exit(run("uv", "run", "alembic", "upgrade", "head"))


@app.command(name="migrate-new")
def migrate_new(message: str) -> None:
    """모델 변경분으로 새 마이그레이션을 뽑는다 (autogenerate).

    🚨 뽑은 파일을 **눈으로 확인**한 뒤 커밋한다. autogenerate 는 초안이지 정답이 아니다.
    """
    raise typer.Exit(run("uv", "run", "alembic", "revision", "--autogenerate", "-m", message))


@app.command()
@stub("W2", "scripts/collect.py 수집 로직 구현")
def collect() -> None:
    """허가가 끝난 소스만 골라 내려받는다.

    2인 확인이 안 끝난 소스는 게이트가 거부한다 (D-15).
    """


@app.command()
@stub("W3", "수집 코퍼스 확보")
def golden() -> None:
    """일부러 틀린 문장을 만들어 채점용 정답셋을 꾸린다."""


@app.command()
@stub("W4~", "골든셋 · GPU 경로 확정")
def train() -> None:
    """모델을 학습시킨다.

    인코더 파인튜닝과 sLLM 학습. 트랙별로 나눠 돌린다 (D-94).
    """


@app.command(name="eval")
@stub("W4~", "학습 산출물")
def eval_() -> None:
    """학습한 모델이 얼마나 맞히는지 잰다.

    4층 지표 — L1 품질 · L2 통합 · L3 운영 · L4 거버넌스 (D-77).
    """


@app.command()
@stub("W2", "walking skeleton")
def serve() -> None:
    """웹 API 를 띄운다. 판정·생성을 호출할 수 있다."""


@app.command()
@stub("W8~", "GGUF 변환 · 오프라인 경로")
def demo() -> None:
    """인터넷 없이 도는 발표용 모드로 띄운다."""


# ══════════════════════════════════════════════════════════
# 대화형 메뉴
# ══════════════════════════════════════════════════════════
# 🚨 메뉴는 **함수를 직접 든다.** 예전에는 명령 이름 문자열을 든 MENU 와
#    이름->함수 표(ACTIONS)가 따로 있었고, 그 둘이 이미 어긋나 있었다
#    (`test` 가 MENU 에만 있고 ACTIONS 에는 없었다). 같은 사실을 두 곳에 두면
#    갈라진다 — D-99 와 같은 형태다.
#    「미구현」 표기도 여기 적지 않는다. @stub 이 붙었는지로 판정한다.


def _menu_test() -> None:
    """테스트를 전부 돌린다."""
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


def summary(fn) -> str:
    """메뉴 설명문. **docstring 첫 줄에서 나온다.**

    🚨 설명을 메뉴 표에 따로 적지 않는다. 그러면 docstring(=`--help` 가 쓰는 것)과
       메뉴가 두 벌이 되고, 한쪽만 갱신된다 — `ACTIONS` 에서 본 그대로다.

    🚨 **첫 줄에는 「눌렀을 때 무슨 일이 일어나는지」만 쓴다.**
       런처를 여는 사람은 이 저장소를 만들지 않은 팀원이다. 파일 이름·내부 용어·
       D 번호는 첫 줄에 넣지 않는다 — 필요하면 docstring 본문에 적는다.
       `"data.js 에서 HTML 을 만든다 (D-87)"` 는 만든 사람만 아는 말이다.
    """
    lines = (fn.__doc__ or "").strip().splitlines()
    return (lines[0].strip() if lines else "").rstrip(".")


def _draw() -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=3, justify="right")
    table.add_column(width=20)
    table.add_column(width=50, style="dim", no_wrap=True, overflow="ellipsis")
    table.add_column(width=10, style="dim")

    for key, label, fn in MENU:
        if key == "-":
            table.add_row("", "", "", "")
            continue
        ready = fn is None or not getattr(fn, "_planned", False)
        # 🚨 Rich 는 대괄호를 마크업으로 읽는다. [g]·[t] 같은 한 글자 키가 통째로 사라진다.
        #    escape 로 리터럴 대괄호를 만든다.
        table.add_row(
            escape(f"[{key}]"),
            label if ready else f"[dim]{label}[/dim]",
            "" if fn is None else summary(fn),
            "" if fn is None else (cli_name(fn) if ready else "[yellow]미구현[/yellow]"),
        )

    console.print(Panel(table, title="CopyLane Launcher", subtitle=_env_line(), width=96))


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
