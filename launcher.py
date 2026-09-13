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


def _table(title: str, rows: dict[str, str]) -> Table:
    """원천 id → 모듈 표. 🚨 **표는 `preprocess/__init__.py` 에 있다** — 여기서 만들지 않는다."""
    t = Table(title=title, box=None, padding=(0, 2))
    t.add_column("원천 id")
    t.add_column("모듈", style="dim")
    for k, v in sorted(rows.items()):
        t.add_row(k, v)
    return t


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


@functools.lru_cache(maxsize=1)
def _docker_state() -> str:
    """🚨 메뉴를 그릴 때마다 `docker info` 를 부르면 안 된다 (2026-09-11).
    도커가 안 떠 있으면 그릴 때마다 타임아웃을 기다린다. 한 번만 잰다."""
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
        console.print(
            "  [green]OK[/green]   .env 이미 있음 — 키 현황은 "
            "[bold]launcher.py keys[/bold], 안내 주석 복원은 [bold]keys --repair[/bold]"
        )
    else:
        env.write_bytes((ROOT / ".env.example").read_bytes())
        console.print("  [green]생성[/green] .env  — [bold]LAW_OC_KEY 를 채워야 한다[/bold]")


@app.command()
def onboard() -> None:
    """새 기기에서 이어 붙일 때 — 무엇이 되고 무엇이 안 되는지 순서대로 냅니다.

    🚨 **런처가 다 해 줄 수 없습니다.** 셋은 구조상 안 됩니다 —
       ① `.env` 키 — `.gitignore` 라 안 따라옵니다. 사람이 다시 넣습니다 (D-111)
       ② `data/raw` 원문 — `.gitignore` 라 안 따라옵니다 (D-19). **다시 받습니다**
       ③ `git` — 팀 규칙상 사람이 직접 돕니다

    그래서 이 명령은 **되는 것을 하고, 안 되는 자리를 이름으로 냅니다** (D-51).
    """
    import shutil  # noqa: PLC0415

    console.print("\n[bold]1. 코드·문서·원장[/bold] — 🚨 사람이 돌립니다")
    console.print("     [bold]git pull[/bold]")
    console.print(
        "     ★ 원장(`data/manifest.jsonl`)은 git 으로 따라옵니다 — 팀 축은 여기서 맞습니다"
    )

    console.print("\n[bold]2. 파이썬 패키지·커밋 훅·.env 틀[/bold]")
    run("uv", "sync")
    run("uv", "run", "pre-commit", "install")
    envf = ROOT / ".env"
    if not envf.exists():
        envf.write_bytes((ROOT / ".env.example").read_bytes())
        console.print("  [yellow]생성[/yellow] .env — 비어 있습니다")

    console.print("\n[bold]3. API 키[/bold] — 🔴 git 에 없습니다. 사람이 다시 넣습니다")
    console.print("     [bold]uv run python launcher.py keys[/bold]        현황")
    console.print("     [bold]uv run python launcher.py setkey LAW_OC_KEY[/bold]")
    console.print("     [bold]uv run python launcher.py setkey FOODSAFETY_KEY[/bold]")
    console.print("     🚨 값을 인자로 주지 않습니다 — PowerShell 기록에 남습니다 (D-111)")

    console.print("\n[bold]4. DB[/bold]")
    if shutil.which("docker") is None:
        console.print("  [red]docker 가 없습니다[/red] — Docker Desktop 을 먼저 켭니다")
    else:
        console.print("     [bold]uv run python launcher.py db-up[/bold]")
        console.print(
            "     [bold]uv run python launcher.py migrate[/bold]   거버넌스 18 + 런타임 6"
        )

    console.print("\n[bold]5. 이 기기에 무엇이 없는지[/bold]")
    console.print("     [bold]uv run python launcher.py inventory[/bold]")
    console.print(
        "     🚨 「원장에 있다」는 「이 기기에 있다」가 아닙니다 — 없는 것을 이름으로 냅니다"
    )
    console.print(
        "     그 목록대로 [bold]launcher.py collect <소스id> --use U1[/bold] 로 다시 받습니다"
    )
    console.print("     🔴 AI Hub 계열은 사람이 받아 [bold]launcher.py register[/bold] 로 올립니다")

    console.print("\n[bold]6. 파생물 → DB → 벡터[/bold]  (원문을 받은 뒤)")
    console.print("     [bold]uv run python launcher.py load[/bold]")
    console.print("     [bold]uv run python launcher.py chunk --dump[/bold]")
    console.print(
        "     [bold]uv run python launcher.py embed --check[/bold]  🚨 먼저 차원을 잽니다"
    )
    console.print("     [bold]uv run python launcher.py embed[/bold]")
    console.print("     ⚠️ KURE-v1 모델 2.27GB 를 처음 한 번 내려받습니다")

    console.print("\n[bold]7. 확인[/bold]")
    console.print("     [bold]uv run python launcher.py check[/bold]      게이트 전체")
    console.print("     [bold]uv run python launcher.py status[/bold]     팀 축 — 쓴다/안 쓴다")
    console.print("     [bold]uv run python launcher.py doctor[/bold]     원장 ↔ 디스크")
    console.print("     [bold]uv run python launcher.py serve[/bold]      /health 로 층별 행 수")

    console.print("\n[dim]무엇을 하던 중이었는지는 docs/ohb/ 의 최신 인계 문서에 있습니다.[/dim]\n")


@app.command()
def setkey(name: str = typer.Argument(..., help="키 이름 (예: FOODSAFETY_KEY)")) -> None:
    """API 키를 화면에 뜨지 않게 입력해 설정 파일에 넣는다.

    🚨 값을 **인자로 주지 않는다.** 이름만 주면 물어보고, 입력은 화면에 표시되지 않는다.
       인자로 주면 PowerShell 기록 파일(`ConsoleHost_history.txt`)에 그대로 남는다 —
       터미널을 닫아도 남고, 지운 줄 알아도 남아 있다.
       확인은 값이 아니라 **지문**으로 낸다. 지문은 붙여 넣어도 안전하다.
    """
    raise typer.Exit(run("uv", "run", "python", "-m", "collect.setkey", name))


@app.command()
def keys(
    repair: bool = typer.Option(False, "--repair", help="설정 파일의 안내 주석을 되살린다"),
) -> None:
    """어떤 키가 채워졌는지 본다 — 값은 화면에 올리지 않는다.

    지금까지 확인하는 방법이 `.env` 를 편집기로 여는 것뿐이었다. 확인하려고 열면
    화면에 뜬다 — **확인 행위 자체가 유출 경로**였다. 그 자리를 이 명령이 대신한다.
    `--repair` 는 손으로 만든 `.env` 에 발급 안내를 되살리고 BOM 을 벗긴다 (값은 보존).
    """
    args = ["uv", "run", "python", "-m", "collect.setkey"]
    raise typer.Exit(run(*args, "--repair") if repair else run(*args))


@app.command()
def doctor(
    hash_check: bool = typer.Option(False, "--hash", help="전 파일 해시를 다시 계산한다 (느리다)"),
    env: bool = typer.Option(False, "--env", help="환경·git 신원·DB — 데이터 없이 돈다"),
) -> None:
    """내 PC 의 데이터가 원장과 맞는지 검사한다 — 원장 ↔ 디스크 대조.

    틀린 것을 알리는 데서 끝내지 않고 **어떻게 고치는지**까지 낸다 (D-51 · D-89).

    🔄 **2026-09-08 — `@stub` 을 뗀다. 검사는 있는데 부르는 길이 없었다.**

       `scripts/doctor.py --data` 는 09-06 부터 돌아가고 있었는데 이 명령이
       자리표시자여서 **메뉴에서 부를 수 없었다.** 그래서 아무도 안 돌렸고,
       「원장에 있는데 이 기기에 없는 파일 73개」가 그동안 보이지 않았다.
       그중 `mfds_sanctions` 는 **54개 전부**가 없는데 `collected_at` 은 찍혀 있다.

    ★ **만들어 두고 부르지 않는 검사는 없는 검사다.** 오늘 마스킹에서 배운 것과
      같은 자리다 — 세는 쪽만 있고 그것을 보는 길이 없으면 조용히 틀린다.

    🚨 게이트가 아니다 (D-89). 답이 **기기마다 다르므로** `check` 에 넣지 않는다.
       🟡(내 기기에 없음)로는 실패하지 않고, 🔴(출처 불명·해시 불일치)만 실패한다.
    """
    args = ["uv", "run", "python", "scripts/doctor.py"]
    if env:
        # 🆕 2026-09-12 밤 — **데이터 없이 도는 검사.** 새 클론에서 제일 먼저 부르는 자리다.
        #    ⛔ 종전에는 「환경 진단」이 원장↔디스크 대조 **하나만** 봤다. 팀원이 초록을 보고도
        #       파이썬 버전·git 신원·DB 리비전은 **아무도 안 본 상태**였다 (D-170).
        args.append("--env")
    else:
        args.append("--data")
        if hash_check:
            args.append("--hash")
    raise typer.Exit(run(*args))


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
def rebuild() -> None:
    """등급 판정을 고친 뒤 — 생성물 넷을 한 벌로 다시 만든다.

    🔴 **넷은 한 벌이다.** `_matrix/data.js`(사람이 쓴 판정) 하나에서 갈라진다 —

        gen_registry.py      -> data_sources.yaml            집행 (게이트가 읽는다)
        build_matrix.py      -> sources.json + 판정매트릭스   근거 (사람이 읽는다)
        extract_rationale.py -> registry_rationale.yaml      판정 근거
        review_sheet.py      -> S0-14 검토표                  2인 확인

    🔄 **2026-09-13 — 이 docstring 이 「셋」이라 적고 있었다.** 아래 `steps` 는 넷이고
       끝 줄과 `DANGER` 표도 「넷」이다 — **한 파일 안에서 두 벌이었다** (D-99 · D-167).
       ⛔ 도면(`diagram`)은 **여기 안 넣는다** — 원천이 13/21 뿐이라 「한 벌로 다시」가
          성립하지 않고, 글꼴 없는 기기에서 레지스트리 rebuild 까지 막힌다 (D-217 은 다른 축이다).

    ⛔ 하나만 돌리면 그 순간 **두 벌**이 된다. D-90 이 적은 그 자리다 —
       *"손으로 양쪽을 고치면 반드시 갈린다."* 사람이 셋을 기억하게 두지 않는다.

    🚨 첫 실패에서 멈춘다. 중간이 실패했는데 끝까지 돈 것처럼 보이면 안 된다.
    """
    steps = (
        (["scripts/gen_registry.py"], "레지스트리"),
        (["scripts/build_matrix.py"], "판정매트릭스"),
        (["scripts/extract_rationale.py"], "판정 근거"),
        (["scripts/review_sheet.py"], "S0-14 검토표"),
    )
    for i, (script, label) in enumerate(steps, 1):
        console.print(f"\n[bold]{i}/{len(steps)}  {label}[/bold]")
        if run("uv", "run", "python", *script) != 0:
            console.print(f"  [red]{label} 에서 멈췄다[/red] — 나머지는 돌리지 않는다")
            raise typer.Exit(1)
    console.print("\n  [green]생성물 넷이 같은 판정에서 다시 만들어졌다[/green]")
    raise typer.Exit(0)


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


@app.command()
def diagram(only: str = typer.Option("", "--only", help="원천 파일 이름(확장자 없이)")) -> None:
    """도면 원천(HTML) → PNG. ⛔ PNG 는 손으로 고치지 않는다 (D-90 · D-217).

    🔴 원천이 있는 것만 뽑는다 — 21장 중 나머지는 원천이 저장소 밖에 있거나 없다 (D-188).
    🚨 `build_pdf.py` 와 **같은** playwright chromium 을 쓴다 — 스택이 안 는다.
    """
    args = ["uv", "run", "python", "-m", "scripts.build_diagram"]
    if only:
        args += ["--only", only]
    raise typer.Exit(run(*args))


@app.command()
def dmap(
    open_only: bool = typer.Option(False, "--open", help="⬜ 열린 항목만 화면으로"),
) -> None:
    """결정이 코드의 어디에 사는지 표로 뽑는다 — `build/decision_map.md` (D-90).

    ⛔ **「인용 0건」이 「미구현」은 아니다.** 세 갈래가 섞여 있고 **가르는 것은 사람이다** —
       ① 코드가 아직 없다 ② 코드에는 있는데 D 번호를 안 적었다 ③ 코드로 갈 결정이 아니다.
    ★ 그 판정은 `docs/02_설계/구현계획.md` 가 든다. 이 명령은 **셀 수 있는 것만** 낸다.
    """
    args = ["uv", "run", "python", "-m", "scripts.decision_map"]
    if open_only:
        args.append("--open")
    raise typer.Exit(run(*args))


@app.command(name="admin-add")
def admin_add(initials: str = typer.Argument(..., help="docs/<이니셜>/ 과 같은 철자")) -> None:
    """거버넌스 콘솔 계정을 만든다 — 가입 화면은 없다 (D-66 · D-213).

    🚨 **비밀번호는 화면에 안 뜨고 셸 인자로도 안 받는다** (`getpass`). `setkey` 와 같은
       이유다 — PowerShell 기록 파일에 값이 그대로 남는다 (D-111).
    🔴 명단의 정본은 **디스크**다 — `docs/<이니셜>/` 이 없으면 거부한다 (D-99).
    """
    raise typer.Exit(run("uv", "run", "python", "-m", "scripts.admin_account", "add", initials))


@app.command(name="admin-list")
def admin_list() -> None:
    """거버넌스 콘솔 계정 목록 — ⛔ 해시는 안 찍는다."""
    raise typer.Exit(run("uv", "run", "python", "-m", "scripts.admin_account", "list"))


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


@app.command(name="db-fresh")
def db_fresh(keep: bool = typer.Option(False, "--keep", help="임시 DB 를 안 지운다")) -> None:
    """빈 DB 에서 `migrate` 가 끝까지 도는가 — **새로 클론한 사람이 밟는 자리** (D-221).

    🔴 2026-09-13 에 팀원이 새 기기에서 막혔다. 다들 쓰던 DB 에 이어 붙이기만 해서
       **빈 DB 에서 처음부터 돌린 적이 없었다** (D-146).
    🚨 **옆에 임시 DB 를 만들어** 거기에만 적용하고 지운다 — 진짜 DB 는 안 건드린다.
    """
    args = ["uv", "run", "python", "-m", "scripts.db_fresh_check"]
    if keep:
        args.append("--keep")
    raise typer.Exit(run(*args))


# ══════════════════════════════════════════════════════════
# 아직 대상이 없는 명령 — 메뉴에는 보이되 눌러도 안전하다
# ══════════════════════════════════════════════════════════
@app.command()
def migrate() -> None:
    """데이터베이스 테이블을 최신 상태로 맞춘다.

    Alembic 으로 스키마 변경을 코드로 남긴다. DB 가 떠 있어야 한다 (`db-up`).

    🔴 **층이 둘이고 관리 방식이 다르다** (2026-09-09) —

        거버넌스·데이터 층 18테이블   `db/schema.sql`   손으로 쓴 DDL · 0001 이 읽어 실행
        런타임 층 6테이블            `app/models.py`   ORM · `migrate-new` 로 autogenerate

    🚨 거버넌스 층은 `--autogenerate` 대상이 아니다. `alembic/env.py` 의 `include_object`
       가 시야에서 뺀다 — 안 그러면 **DROP 을 생성한다.**
    """
    raise typer.Exit(run("uv", "run", "alembic", "upgrade", "head"))


@app.command(name="migrate-new")
def migrate_new(message: str) -> None:
    """모델 변경분으로 새 마이그레이션을 뽑는다 (autogenerate).

    🚨 뽑은 파일을 **눈으로 확인**한 뒤 커밋한다. autogenerate 는 초안이지 정답이 아니다.
    """
    raise typer.Exit(run("uv", "run", "alembic", "revision", "--autogenerate", "-m", message))


@app.command()
def probe(source: str = typer.Argument("", help="소스 id 하나만 (비우면 전체)")) -> None:
    """소스를 열어보고 이용조건 문구를 긁는다 — 🚨 저장은 하지 않는다.

    2인 확인 전에도 돈다. 확인하려면 열어봐야 하고, 열어보는 것은 수집이 아니다 (D-109).
    산출은 `docs/03_데이터/실측_<날짜>.md` 한 장이고 그것이 검토자가 서명할 근거다.
    G1·수기 소스·승인 선행(GATED)·robots 미확인 크롤링형은 그대로 막힌다.
    """
    args = ["uv", "run", "python", "-m", "collect.probe"]
    raise typer.Exit(run(*args, source) if source else run(*args))


@app.command(name="search-probe")
def search_probe(
    queries: str = typer.Option("", help="질의 JSONL 경로 (비우면 기본 경로)"),
    pool: int = typer.Option(0, help="후보 폭 (0 이면 기획서 5-6 의 50)"),
) -> None:
    """검색 순위를 잰다 — 🚨 **원장에 올릴 수를 만드는 자리**다 (D-204).

    범주 넷을 다 돌고 갈래별 순위와 RRF 순위를 낸다. 30건 미만이면 D-40 으로
    「측정 불가」를 찍고 **비율을 말하지 않는다.**
    ⛔ `collect.probe`(소스 탐침 · D-109)와 다른 물건이다 — 이름을 가른 이유가 그것이다.
    """
    a = ["uv", "run", "python", "-m", "scripts.search_probe"]
    if queries:
        a += ["--queries", queries]
    if pool:
        a += ["--pool", str(pool)]
    raise typer.Exit(run(*a))


@app.command()
def count(path: str = typer.Argument(..., help="받아 온 파일이나 폴더")) -> None:
    """받아 온 파일을 세어 본다 — 옮기지도 등록하지도 않는다.

    파일 수·줄 수·크기·sha256 만 냅니다. 2인 확인 전에도 돌고, 레지스트리의
    `scale` 이 실제와 맞는지 확인하는 자리입니다 (D-109).
    """
    raise typer.Exit(run("uv", "run", "python", "-m", "collect.ingest", "count", path))


@app.command()
def register(
    source: str = typer.Argument(..., help="레지스트리 소스 id"),
    path: str = typer.Argument(..., help="받아 온 파일이나 폴더"),
    use: str = typer.Option(..., "--use", help="U1~U4 중 하나"),
) -> None:
    """사람이 받아 온 파일을 원장에 올린다.

    🚨 **2인 확인이 끝나야 통과한다.**

    AI Hub 처럼 신청·승인을 거쳐 사람이 내려받는 소스는 수집기가 가져오지 않습니다.
    그래서 원장에 안 남고, provenance 는 나중에 못 붙입니다 (D-71). 이 명령이 그 자리입니다.
    data/raw/<소스id>/ 로 복사하고 manifest 에 1행 남깁니다 — 등급 디렉터리가 아닙니다 (D-92).
    """
    raise typer.Exit(
        run("uv", "run", "python", "-m", "collect.ingest", "register", source, path, "--use", use)
    )


@app.command()
def collect(
    source: str = typer.Argument(..., help="레지스트리 소스 id"),
    use: str = typer.Option("U1", "--use", help="U1~U4"),
    pages: int = typer.Option(0, "--pages", help="🚨 첫 실행은 1 로 — 응답을 보고 전량을 받는다"),
) -> None:
    """공공데이터포털 오픈API 를 내려받는다 — 6개 소스 공용.

    2인 확인이 안 끝난 소스는 게이트가 첫 줄에서 거부합니다 (D-15 · D-66).
    요청주소는 `collect/endpoints.yaml` 에 있고, 비어 있으면 어디를 볼지 알려줍니다.
    """
    from collect import COLLECTORS, MANUAL_SOURCES  # noqa: PLC0415 — 표는 collect 가 든다

    if source in MANUAL_SOURCES:
        typer.echo(
            f"⬜ `{source}` 는 **사람이 받는 소스**입니다 — 신청·회원가입이 필요합니다.\n"
            f"   받은 뒤: uv run python launcher.py register {source} <경로> --use {use}"
        )
        raise typer.Exit(1)
    spec = COLLECTORS.get(source)
    if spec is None:
        typer.echo(
            f"🔴 `{source}` 의 수집기가 표에 없습니다.\n"
            "   표를 봅니다 — collect/__init__.py 의 COLLECTORS · MANUAL_SOURCES\n"
            "   🚨 **추정하지 않습니다.** 오픈API 가 아닌 소스를 openapi 로 보내면"
            " 엉뚱한 오류가 납니다 (D-179)."
        )
        raise typer.Exit(1)
    module, shape = spec
    args = ["uv", "run", "python", "-m", module]
    if shape == "arg":
        args += [source, "--use", use]
    elif shape == "target":
        args += ["--target", "law"]
    if pages and module == "collect.openapi":
        args += ["--pages", str(pages)]
    raise typer.Exit(run(*args))


@app.command(
    name="labelsheet",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def labelsheet(ctx: typer.Context) -> None:
    """라벨 시트 ↔ 엑셀(CSV) — 🚨 **사람은 번호만 채웁니다**.

        labelsheet export <시트.jsonl> --who 권소라 --part 1-50
        labelsheet import  build/labels/권소라.csv --sheet <시트.jsonl>

    ⛔ 종전에는 JSONL 을 손으로 고치게 했습니다 — 대괄호를 빠뜨려 그 줄이 JSON 이 아니게 되거나,
       유형 이름을 한 글자 틀려 **조용히 다른 라벨**이 되던 자리입니다.
    ★ 번호는 지시서 §3 의 **판정 순서 그대로**입니다. 두 곳이 갈리면 게이트가 잡습니다 (D-99).
    """
    raise typer.Exit(run("uv", "run", "python", "scripts/label_sheet.py", *ctx.args))


@app.command()
def inventory() -> None:
    """**이 기기**에 무엇이 있나 — 원장(팀 축)과 대조합니다.

    🚨 축이 둘입니다. 원장은 git 으로 공유되지만 원문은 `.gitignore` 라 기기마다 다릅니다 (D-19).
       「원장에 있다」는 「이 기기에 있다」가 아닙니다.
    """
    raise typer.Exit(run("uv", "run", "python", "-m", "preprocess.inventory"))


@app.command()
def status() -> None:
    """데이터 현황판을 다시 만듭니다 — 무엇을 쓰기로 했고 무엇을 안 쓰기로 했나.

    🚨 **생성물입니다.** 손으로 적으면 갈립니다 (D-54). 2026-09-03 판이 그렇게 낡았습니다.
    """
    raise typer.Exit(run("uv", "run", "python", "-m", "scripts.data_status", "--write"))


@app.command()
def load(
    allow_missing: bool = typer.Option(
        False,
        "--allow-missing",
        help="🚨 파생물이 없어도 0행으로 적재합니다 — **일부러** 비운 채 돌릴 때만",
    ),
) -> None:
    """파생물을 거버넌스 DB 에 적재한다 (D-95).

    🚨 CHECK 둘을 못 지나는 소스는 **넣지 않고 이름을 냅니다** —
       2인 확인 미완 · attribution 없음. 조용히 건너뛰면 「다 들어갔다」로 읽힙니다.
    🔴 **입력이 없으면 멈춥니다** (2026-09-10 · D-72). 종전에는 빈 리스트로 삼켜서
       `document 0 · product_fact 0` 이 오류도 경고도 없이 「정상 완료」로 찍혔습니다.
    🔴 골든셋은 아직 못 넣습니다 — `split_t` 에 `test_sentence` 가 없고
       `violation_t`(V0~V8) 대응표가 미판정입니다 (결정요청 ⑤).
    """
    args = ["uv", "run", "python", "-m", "scripts.load_db"]
    if allow_missing:
        args.append("--allow-missing")
    raise typer.Exit(run(*args))


@app.command()
def chunk(dump: bool = typer.Option(False, "--dump", help="chunks.jsonl 을 쓴다")) -> None:
    """[P5] 조문·별표를 RAG 청크로 자릅니다 — 🚨 조문 단위입니다."""
    args = ["uv", "run", "python", "-m", "preprocess.chunk"]
    if dump:
        args.append("--dump")
    raise typer.Exit(run(*args))


@app.command()
def embed(
    check: bool = typer.Option(False, "--check", help="모델 차원만 잽니다 (DB 불필요)"),
) -> None:
    """청크를 KURE-v1 로 임베딩해 pgvector 에 넣습니다.

    🚨 `--check` 를 먼저 돌리십시오 — `vector(1024)` 가 모델과 맞는지 아무도 안 재 봤습니다.
    """
    args = ["uv", "run", "python", "-m", "scripts.embed"]
    if check:
        args.append("--check")
    raise typer.Exit(run(*args))


@app.command()
def serve(
    reload: bool = typer.Option(True, "--reload/--no-reload"),
    host: str = typer.Option("127.0.0.1", "--host", help="🚨 0.0.0.0 은 사내망에 연다"),
    port: int = typer.Option(8000, "--port", help="4명이 동시에 띄우면 겹친다"),
) -> None:
    """FastAPI 를 띄웁니다 (D-42 · D-135 — Django 를 쓰지 않습니다).

    🔄 2026-09-09 — `@stub("W2", "walking skeleton")` 자리를 대신합니다.
       ⛔ 새 명령을 더하면서 **같은 이름의 스텁이 이미 있는지 안 봤습니다.**
          `ruff F811` 이 잡았습니다 — 안 잡혔으면 뒤에 정의된 스텁이 이겨
          `serve` 가 「아직 없다」를 찍고 서버는 안 떴을 것입니다.
    """
    # 🚨 없는 것을 「없다」고 말한다 (D-51 — 오류는 고치는 법을 보여준다).
    #    ⛔ 2026-09-09 — `uv run uvicorn` 이 `program not found` 로 죽었다.
    #       D-42·D-135 가 FastAPI 를 확정해 뒀는데 `pyproject.toml` 에는 없었다.
    #       `sentence-transformers` 와 같은 부류다 — **코드가 0줄이면 의존성도 없다.**
    #       스택은 결정돼 있었고 아무도 그것을 설치한 적이 없었다.
    import importlib.util

    missing = [m for m in ("fastapi", "uvicorn", "jinja2") if importlib.util.find_spec(m) is None]
    if missing:
        console.print(f"[red]없는 것 — {', '.join(missing)}[/red]")
        console.print('  고치는 법 — [bold]uv add fastapi "uvicorn[standard]" jinja2[/bold]')
        console.print("  🚨 D-42·D-135 가 FastAPI 를 확정해 뒀지만 의존성은 없었습니다.")
        raise typer.Exit(1)

    # 🔴 **`127.0.0.1` 이 기본이다** (보안점검 P2-10 · P1-7). 종전에는 `--host` 가 없어
    #    uvicorn 기본값에 기대고 있었고, **그것이 판정이라고 적힌 데가 없었다.**
    #    ⛔ 인증이 아직 0줄이라, `--host 0.0.0.0` 하나면 `/admin`·`/docs` 가 사내망에 열린다.
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(f"[red]🚨 --host {host} — 인증이 아직 없습니다 (보안점검 P1-5 · P1-7).[/red]")
        console.print("  관리자 화면과 /docs 가 그대로 열립니다. 배포는 SSH 터널로만 (P2-10).")
    args = ["uv", "run", "uvicorn", "app.api:app", "--host", host, "--port", str(port)]
    if reload:
        args.append("--reload")
    raise typer.Exit(run(*args))


@app.command()
def extract(
    source: str = typer.Argument("", help="원천 id (비우면 표를 보여준다)"),
    dump: bool = typer.Option(False, "--dump", help="파생물을 쓴다 — 🔴 마스킹 정책이 있어야 한다"),
    sheet: int = typer.Option(0, "--sheet", help="사람이 채울 검증셋을 N건씩 만든다"),
    min_len: int = typer.Option(
        0, "--min-len", help="검증셋 문구 길이 하한 — 낱말을 빼고 문장만 (0 = 안 건다)"
    ),
    verify: bool = typer.Option(False, "--verify", help="원천의 선언과 대조만 한다"),
) -> None:
    """받아 둔 원문에서 라벨을 뽑는다 — 원천별 전처리 모듈로 위임한다.

    🔴 `--dump` 는 마스킹 정책이 선언된 원천에서만 돕니다 (D-72 fail-closed).
    🚨 `--verify` 를 먼저 돌립니다 — 원천이 스스로 밝힌 수(목차 쪽번호·전체 건수)와 맞춰 봅니다.
    ⛔ 원천마다 받는 옵션이 다릅니다. 없는 옵션을 주면 그 모듈이 알려 줍니다.
    """
    from preprocess import EXTRACTORS  # noqa: PLC0415 — 표는 로직 쪽에 있다 (D-99)

    if not source:
        console.print(_table("전처리 추출", EXTRACTORS))
        raise typer.Exit(0)
    module = EXTRACTORS.get(source)
    if module is None:
        console.print(
            f"  [red]{source} 의 전처리 모듈이 없다[/red] — preprocess/__init__.py 의 표를 본다"
        )
        raise typer.Exit(1)
    args = ["uv", "run", "python", "-m", module]
    if verify:
        args.append("--verify")
    if dump:
        args.append("--dump")
    if sheet:
        args += ["--sheet", str(sheet)]
    if min_len:
        args += ["--min-len", str(min_len)]
    raise typer.Exit(run(*args))


@app.command()
def scan(source: str = typer.Argument("", help="원천 id (비우면 표를 보여준다)")) -> None:
    """원천을 세어 본다 — 🚨 라벨을 만들지 않는다. 산출물이 없다.

    두 가지를 묻습니다 — **받은 것이 전부인가**(D-161) · **광고 문구가 실제로 실리는가**(D-40).
    🔴 유일 행이 원천 선언에 못 미치면 종료코드 1 로 끝납니다. 지금 `mfds_sanctions` 가 그렇습니다.
    """
    from preprocess import SCANNERS  # noqa: PLC0415

    if not source:
        console.print(_table("원천 계측", SCANNERS))
        raise typer.Exit(0)
    module = SCANNERS.get(source)
    if module is None:
        console.print(
            f"  [red]{source} 의 계측 모듈이 없다[/red] — preprocess/__init__.py 의 표를 본다"
        )
        raise typer.Exit(1)
    raise typer.Exit(run("uv", "run", "python", "-m", module, source))


@app.command()
def golden(
    write: bool = typer.Option(False, "--write", help="파생물을 실제로 쓴다 (기본은 보기만)"),
) -> None:
    """골든셋을 꾸린다 — **사전 → 주입 → 분할** 세 단계 (2026-09-09).

    🚨 **라벨을 사람도 모델도 붙이지 않는다.** 조문이 붙이거나(사전) 규칙이 붙인다(주입).

        [P12] 분할  🔴 **먼저다** — 출처 분리 · 문서 단위 봉인   preprocess.split
        [P6] 사전   조문이 묶어 준 표현을 모은다 (train 만)     preprocess.dictionary
        [P10] 주입  적법 문구를 규칙으로 위법화한다 (train 만)   preprocess.inject
        물질화      문장·라벨을 한 파일로 (D-143)              preprocess.golden

    🔴 **분할이 맨 앞이다.** 종전에는 사전이 먼저였는데, 그러면 사전이 **평가 문구로**
       만들어진다 — 실측: 봉인된 평가 문구 118개 중 **118개**가 사전에 있었다.
       그 사전으로 매칭기를 재면 외운 것을 맞힌다.

    🔴 **주입본은 평가에 들어가지 않는다** ([P10] 규약 5). 합성으로 평가하면
       「규칙을 배웠는가」를 재게 된다. 분할 게이트가 그것을 막는다.
    """
    steps = (
        (["-m", "preprocess.split"], ["--write"]),
        (["-m", "preprocess.dictionary"], ["--dump"]),
        (["-m", "preprocess.inject"], ["--dump"]),
        (["-m", "preprocess.golden"], ["--dump"]),
    )
    for mod, extra in steps:
        args = ["uv", "run", "python", *mod] + (extra if write else [])
        if run(*args) != 0:
            raise typer.Exit(1)
    if not write:
        console.print("\n  [yellow]⬜ 아무것도 쓰지 않았다[/yellow] — `--write` 를 붙인다.")
    raise typer.Exit(0)


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
#
# 🔴 **그런데 그 함수를 파이썬에서 「직접 호출」하면 안 된다** (2026-09-11).
#    Typer 로 등록된 함수를 그냥 부르면 인자가 기본값이 아니라
#    `OptionInfo`·`ArgumentInfo` **객체**로 들어온다. 그리고 객체는 언제나 참이다.
#    ⛔ 실측 — 메뉴 「골든셋 생성」이 `write=<OptionInfo>` 로 돌아 **dry-run 이 아니라
#       실제 쓰기**를 했다. *"기본은 보기만"* 이라 적힌 버튼이 분할 매니페스트를 덮어썼다.
#       `keys` 는 늘 `--repair`(설정 파일을 고친다), `doctor` 는 늘 `--hash`(느리다)로 돌았고,
#       인자를 받는 여섯(collect·register·count·probe·extract·scan)은 소스 id 자리에
#       객체가 들어가 「표에 없습니다」로 끝났다 — **에러처럼 보이지 않는 에러**다.
#    ★ 원인은 **호출 경로가 둘**이라는 것이다 (CLI / 메뉴). 이 파일의 원칙이 이미
#      *"launcher 는 얇은 껍데기다 — 밖으로 위임한다"* 인데 메뉴만 그 밖에 있었다.
#      그래서 **메뉴도 CLI 를 부른다.** 경로가 하나면 갈릴 수 없다.
#
# 🔴 **키가 겹치면 뒤엣것은 영영 안 눌린다** (2026-09-08 · D-162).
#    그래서 번호는 `_check_menu()` 가 중복을 검사한다 — 표를 손으로 고쳐도 안 어긋난다.


def _invoke(fn, *extra: str) -> None:
    """🔴 메뉴도 **CLI 를 거쳐** 부른다 — 경로를 하나로 (D-51 · D-99).

    `sys.executable` 을 쓰므로 이미 venv 안이고 `uv run` 을 한 번 더 타지 않는다.
    """
    run(sys.executable, str(ROOT / "launcher.py"), cli_name(fn), *extra)


#: 눌렀을 때 **위치 인자를 묻는다** — (물음, 필수인가, 보기 종류)
#: 🚨 `register` 처럼 **둘 이상**을 받는 명령이 있다. 하나만 물으면 CLI 가 거부한다.
#: 🔴 보기 종류가 있으면 **번호로 고르게 한다** — 소스 id 를 외워서 칠 이유가 없다.
ASK_ARG: dict[str, list[tuple[str, bool, str]]] = {
    "setkey": [("어떤 키를 넣을까", True, "key")],
    "admin-add": [("누구의 계정인가 (이니셜)", True, "text")],
    "diagram": [("어느 도면인가 (엔터 = 전부)", False, "text")],
    "probe": [("어떤 소스를 열어 볼까", False, "collect")],
    "collect": [("어떤 소스를 받을까", True, "collect")],
    "count": [("받아 온 파일이나 폴더 경로", True, "path")],
    "register": [("어떤 소스인가", True, "manual"), ("받아 온 파일이나 폴더 경로", True, "path")],
    "extract": [("어떤 원천을 추출할까", False, "extract")],
    "scan": [("어떤 원천을 셀까", False, "scan")],
}

#: 값을 받는 옵션 중 **필수**인 것 — (물음, 플래그, 보기)
ASK_VALUE: dict[str, list[tuple[str, str, list[tuple[str, str]]]]] = {
    "register": [
        (
            "무슨 용도로 쓸 것인가",
            "--use",
            [
                ("U1", "학습"),
                ("U2", "RAG 검색"),
                ("U3", "인용 표시"),
                ("U4", "배포"),
            ],
        )
    ],
}

#: 눌렀을 때 **여부를 묻는** 플래그 — (물음, 플래그, 1번 설명, 2번 설명)
#: 🚨 **1번이 언제나 「안 하는 쪽」**이고 기본이다. 엔터만 치면 안 붙는다.
#:    ⛔ 종전에는 메뉴가 이 플래그들을 **늘 켠 채로** 돌렸다 (Typer 인자 객체가 참이라).
ASK_FLAG: dict[str, list[tuple[str, str, str, str]]] = {
    "doctor": [
        (
            "무엇을 볼까",
            "--env",
            "데이터 — 원장 ↔ 디스크 대조",
            "환경 — 파이썬·git 신원·DB (데이터 불필요)",
        ),
        ("해시 검사", "--hash", "빠르게 — 있는지만 본다", "느리게 — 전 파일 해시를 다시 잰다"),
    ],
    "keys": [("설정 파일", "--repair", "보기만 한다", ".env 의 안내 주석을 되살린다")],
    "golden": [("파생물", "--write", "보기만 한다", "실제로 쓴다 — 기존 분할이 덮어쓰인다")],
    "load": [("원본이 없는 행", "--allow-missing", "있으면 멈춘다", "허용하고 적재한다")],
    "chunk": [("chunks.jsonl", "--dump", "보기만 한다", "파일로 쓴다")],
    "embed": [("범위", "--check", "전부 임베딩한다 (DB 필요)", "모델 차원만 잰다 (DB 불필요)")],
    "extract": [("파생물", "--dump", "보기만 한다", "쓴다 — 🚨 마스킹 정책이 있어야 한다")],
}

#: 확인을 한 번 더 받는 동작 — **값은 이유다** (2026-09-11).
#:    🚨 종전에는 다섯 곳이 전부 *"되돌리기 어렵다"* 라고 떴다. 그런데 `db-down` 은
#:       볼륨이 남아 되돌리기 어렵지 않고, `setup` 은 멱등이다. **사실이 아닌 경고는
#:       곧 안 읽힌다** — D-167 이 오탐에 대해 적은 것과 같은 자리다.
#:    ★ 그래서 성질을 둘로 갈라 적는다 — 「되돌리기 어렵다」와 「무겁거나 끊는다」.
DANGER: dict[str, str] = {
    "db-down": "돌고 있는 작업이 끊긴다 — 저장된 데이터는 남는다",
    "setup": "환경을 다시 세운다 — 몇 분 걸린다. 결과는 여러 번 돌려도 같다",
    "load": "DB 내용이 바뀐다",
    # 🆕 2026-09-12 밤 — **덮어쓰거나 지우는데 확인이 없었다.**
    "status": "데이터 현황판을 덮어쓴다 — 보기만 하는 경로가 없다",
    "sync": "사본을 다시 만들고 **MAP 에 없는 낡은 사본은 지운다**",
    "embed": "DB 를 쓰고 **선언 밖 청크를 지운다** (D-187) · 모델 2.27GB 를 받는다",
    "rebuild": "생성물 넷을 덮어쓴다 — 하나만 돌리면 두 벌이 된다",
    "diagram": "도면 PNG 를 덮어쓴다 — 원천이 있는 것만 (D-217)",
    "dmap": "build/decision_map.md 를 덮어쓴다 — 생성물이다 (D-90)",
    "db-fresh": "임시 DB `copylane_freshcheck` 를 만들었다 지운다 — 진짜 DB 는 안 건드린다",
}

#: 🔴 **플래그가 붙었을 때만** 위험한 것 — (플래그, 이유)
#:    안전한 경로에서 두 번 묻지 않는다. `golden` 은 보기만 할 때는 아무것도 안 쓴다.
#:    **확인이 습관이 되면, 습관이 된 확인은 안 읽힌다.**
DANGER_IF: dict[str, tuple[str, str]] = {
    "golden": ("--write", "기존 분할이 덮어쓰인다 — 되돌릴 수 없다"),
    "extract": ("--dump", "파생물이 덮어쓰인다"),
}

#: 경로를 물을 때 보여 줄 예시
PATH_HINT = r"예: C:\Users\<이름>\Downloads\aihub_558  ·  data\raw\mfds_casebook"


GROUP = "#"  # 그룹 제목 줄
MENU: list[tuple[str, str, object]] = [
    (GROUP, "환경", None),
    ("1", "환경 설정", setup),
    ("2", "새 기기 안내", onboard),
    ("3", "환경 진단", doctor),
    ("4", "이 기기 재고", inventory),
    ("5", "API 키 현황", keys),
    ("6", "API 키 입력", setkey),
    # 🚨 번호는 뒤에서 받는다 — 28~34 를 밀면 손에 익은 번호가 전부 바뀐다 (D-162)
    ("35", "콘솔 계정 만들기", admin_add),
    ("36", "콘솔 계정 목록", admin_list),
    (GROUP, "DB", None),
    ("7", "DB 기동", db_up),
    ("8", "DB 중지", db_down),
    ("9", "DB 마이그레이션", migrate),
    ("39", "빈 DB 에서 마이그레이션 검사", db_fresh),
    (GROUP, "거버넌스", None),
    ("10", "생성물 한 벌 다시", rebuild),
    ("11", "레지스트리만", registry),
    ("12", "판정매트릭스만", matrix),
    ("13", "S0-14 검토표만", review),
    ("14", "데이터 현황판", status),
    (GROUP, "수집", None),
    ("15", "소스 실측", probe),
    ("16", "오픈API 수집", collect),
    ("17", "받은 파일 세기", count),
    ("18", "받은 파일 등록", register),
    (GROUP, "전처리 · 적재", None),
    ("19", "전처리 추출", extract),
    ("20", "원천 계측", scan),
    ("21", "골든셋 생성", golden),
    ("22", "DB 적재", load),
    ("23", "청킹", chunk),
    ("24", "임베딩", embed),
    (GROUP, "학습 · 서비스", None),
    ("25", "학습", train),
    ("26", "평가", eval_),
    ("27", "서버 실행 (127.0.0.1)", serve),
    # 🚨 번호가 순서대로가 아니다 — 28~33 을 밀면 손에 익은 번호가 전부 바뀐다.
    #    `_check_menu()` 는 **중복만** 본다 (D-162). 새 명령은 뒤 번호를 받는다.
    ("34", "검색 실측", search_probe),
    ("28", "데모 모드", demo),
    (GROUP, "개발", None),
    ("29", "테스트", test),
    ("30", "포맷·린트", fmt),
    ("31", "커밋 전 점검", check),
    ("32", "Phase 게이트 판정", gate),
    ("33", "프로젝트 사본", sync),
    ("37", "도면 다시 그리기", diagram),
    ("38", "결정 ↔ 코드 대응표", dmap),
    (GROUP, "", None),
    ("0", "종료", None),
]


def summary(fn) -> str:
    """메뉴 설명문. **docstring 첫 줄에서 나온다.**

    🚨 설명을 메뉴 표에 따로 적지 않는다. 그러면 docstring(=`--help` 가 쓰는 것)과
       메뉴가 두 벌이 되고, 한쪽만 갱신된다 — `ACTIONS` 에서 본 그대로다.

    🚨 **첫 줄에는 「눌렀을 때 무슨 일이 일어나는지」만 쓴다.**
       런처를 여는 사람은 이 저장소를 만들지 않은 팀원이다. 파일 이름·내부 용어·
       D 번호는 첫 줄에 넣지 않는다 — 필요하면 docstring 본문에 적는다.
    """
    lines = (fn.__doc__ or "").strip().splitlines()
    first = (lines[0].strip() if lines else "").rstrip(".")
    # 🚨 docstring 은 마크다운으로도 읽힌다(`--help`·문서). 화면에서는 `**` 가 글자로 보인다.
    return first.replace("**", "")


def _check_menu() -> None:
    """🔴 **표가 스스로를 검사한다** (D-162 · D-170).

    번호가 겹치면 뒤엣것은 영영 안 눌린다. 종전에는 그것을 사람이 눈으로 봤다.
    🚨 실패할 수 있는 단언이다 — 표를 손으로 고치다 겹치면 **여기서 죽는다.**
    """
    nums = [k for k, _, _ in MENU if k != GROUP]
    dup = {n for n in nums if nums.count(n) > 1}
    if dup:
        raise SystemExit(f"🔴 메뉴 번호가 겹친다: {sorted(dup)}")
    names = {cli_name(fn) for _, _, fn in MENU if fn is not None}
    asked = sorted(set(ASK_ARG) | set(ASK_VALUE) | set(ASK_FLAG) | set(DANGER) | set(DANGER_IF))
    missing = [n for n in asked if n not in names]
    if missing:
        raise SystemExit(f"🔴 메뉴에 없는 명령을 묻고 있다: {missing}")


def _draw() -> None:
    """🔴 **터미널 폭에 맞춘다** (2026-09-11).

    ⛔ 종전에는 설명 칸이 46칸 고정이었다. 한글은 한 글자가 **두 칸**을 쓰므로 23자뿐이고,
       29개 중 **17개가 잘려** `…` 로 끝났다 — 가장 긴 것이 67칸이었다.
    ★ 좁은 창에서는 맨 오른쪽 **명령어 칸을 접는다.** 그 이름은 아래 안내 줄과 `--help`
      에도 있으니 둘 중 하나를 접어야 한다면 설명이 아니라 이름 쪽이다.
    """
    width = min(console.width, 120)
    show_name = width >= 112
    lead_w, label_w, name_w = 4, 22, (12 if show_name else 0)
    cols = 3 + (1 if show_name else 0)
    desc_w = max(28, width - 4 - lead_w - label_w - name_w - 2 * cols)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=lead_w, justify="right")
    table.add_column(width=label_w)
    table.add_column(width=desc_w, style="dim", no_wrap=True, overflow="ellipsis")
    if show_name:
        table.add_column(width=name_w, style="dim")

    for key, label, fn in MENU:
        if key == GROUP:
            table.add_row(
                *(["", f"[bold]{label}[/bold]" if label else "", ""] + ([""] if show_name else []))
            )
            continue
        ready = fn is None or not getattr(fn, "_planned", False)
        name = "" if fn is None else cli_name(fn)
        mark = ""
        if name in DANGER or name in DANGER_IF:
            mark = " [yellow]⚠[/yellow]"
        elif name in ASK_ARG:
            mark = " [dim]→[/dim]"
        if not ready:
            mark += " [yellow]미구현[/yellow]"
        # 🚨 Rich 는 대괄호를 마크업으로 읽는다. escape 로 리터럴 대괄호를 만든다.
        cells = [
            escape(f"{key}."),
            (label if ready else f"[dim]{label}[/dim]") + mark,
            "" if fn is None else summary(fn),
        ]
        if show_name:
            cells.append("" if fn is None else name)
        table.add_row(*cells)

    console.print(Panel(table, title="CopyLane Launcher", subtitle=_env_line(), width=width))
    # 🔴 **「다음에 뭘 눌러야 하지」에 답한다** (2026-09-11).
    #    메뉴는 무엇이 있는지를 보여 주지만 **순서**는 안 보여 준다. 항목이 33개가 되면
    #    「무엇이 중요한가」가 사라진다 — 매일 쓰는 것과 기기당 한 번이 같은 무게로 놓인다.
    #    🚨 정적인 한 줄이다. 상태를 재지 않는다 — 재려면 DB·파일을 봐야 하고,
    #       그건 껍데기가 할 일이 아니다 (D-51). 상태 축은 `doctor` 가 든다.
    console.print(
        "  [dim]흐름[/dim]  [cyan]1[/cyan] 설치 → [cyan]7[/cyan] DB → [cyan]16[/cyan] 수집 → "
        "[cyan]19[/cyan] 추출 → [cyan]21[/cyan] 골든셋 → [cyan]22[/cyan] 적재 → "
        "[cyan]23[/cyan] 청킹 → [cyan]24[/cyan] 임베딩 → [cyan]32[/cyan] 게이트"
    )
    console.print(
        "  [dim]처음이면[/dim] [cyan]2[/cyan] 새 기기 안내    "
        "[dim]번호나 명령 이름을 넣는다 — 예: 3 · doctor · 16 · collect[/dim]"
    )


def _choices(kind: str) -> list[tuple[str, str]]:
    """보기를 **표에서** 가져온다 — 여기서 만들지 않는다 (D-99).

    🚨 런처가 목록을 따로 들면 표와 갈라진다. 수집기 표·전처리 표·`.env.example` 이 원본이다.
    """
    if kind == "collect":
        from collect import COLLECTORS  # noqa: PLC0415 — 표는 collect 가 든다

        return [(k, v[0].replace("collect.", "")) for k, v in COLLECTORS.items()]
    if kind == "manual":
        from collect import MANUAL_SOURCES  # noqa: PLC0415

        return [(k, "사람이 받는 소스") for k in sorted(MANUAL_SOURCES)]
    if kind in {"extract", "scan"}:
        import preprocess  # noqa: PLC0415

        table = preprocess.EXTRACTORS if kind == "extract" else preprocess.SCANNERS
        return [(k, v.replace("preprocess.", "")) for k, v in table.items()]
    if kind == "key":
        import re  # noqa: PLC0415

        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        # 🚨 `DATABASE_URL`·`MLFLOW_TRACKING_URI` 같은 **설정값**은 키가 아니다.
        #    이름이 `_KEY` 로 끝나는 것만 고른다 — `setkey` 는 비밀을 넣는 자리다.
        return [(m.group(1), "") for m in re.finditer(r"^([A-Z][A-Z0-9_]*_KEY)=", text, re.M)]
    return []


#: 🔴 **`0` 은 어디서나 「뒤로」다** (2026-09-11).
#:    첫 단계에서 누르면 메뉴로, 그 뒤에서는 **이전 단계로** 돌아간다.
#:    ⛔ 종전에는 되돌아갈 길이 없었다 — `_confirm` 에서 엔터를 치면 「안 함」으로
#:       **진행**했고, 3단계짜리 `register` 는 두 번째에서 틀리면 처음부터 다시였다.
#:    ★ 개념 하나에 키 하나다. 「0 직접 입력」을 따로 두지 않는다 —
#:      번호 대신 **값을 그대로 치면** 그것이 값으로 들어간다.
BACK = object()


def _foot(required: bool, skip_note: str = "") -> None:
    console.print("    [cyan] 0[/cyan]  [dim]← 뒤로[/dim]")
    if not required and skip_note:
        console.print(f"    [dim] ⏎  {skip_note}[/dim]")


def _pick(question: str, options: list[tuple[str, str]], *, required: bool, skip_note: str = ""):
    """번호로 고르게 한다. `0` 또는 (필수일 때) 빈 입력은 **뒤로**.

    🚨 Rich 는 대괄호를 마크업으로 읽는다 — 물음 줄에 `[y/N]` 같은 것을 쓰면 통째로 사라진다.
       실제로 2026-09-11 에 그렇게 사라져서 무엇을 쳐야 할지 안 보였다. 여기서는 대괄호를 안 쓴다.
    """
    console.print(f"\n  [bold]{question}[/bold]")
    for i, (value, note) in enumerate(options, 1):
        tail = f"  [dim]{note}[/dim]" if note else ""
        console.print(f"    [cyan]{i:>2}[/cyan]  {value}{tail}")
    _foot(required, skip_note)

    raw = console.input("  번호, 또는 값을 그대로 > ").strip()
    if raw == "0":
        return BACK
    if not raw:
        return BACK if required else ""
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1][0]
    # 번호가 아니면 값으로 받는다 — 익숙해진 사람은 그냥 친다
    return raw


def _ask_path(question: str):
    """경로는 보기를 줄 수 없다 — 예시를 보여 주고 받는다."""
    console.print(f"\n  [bold]{question}[/bold]")
    console.print(f"    [dim]{PATH_HINT}[/dim]")
    _foot(required=True)
    raw = console.input("  경로 > ").strip().strip('"')
    return BACK if raw in {"", "0"} else raw


def _confirm(title: str, no_label: str, yes_label: str, reason: str = ""):
    """1=안 함(기본) · 2=함 · 0=뒤로. 🚨 **1번이 언제나 안전한 쪽**이다."""
    console.print(f"\n  [bold]{title}[/bold]")
    if reason:
        console.print(f"    [yellow]이유[/yellow]  [dim]{reason}[/dim]")
    console.print(f"    [cyan] 1[/cyan]  {no_label}  [dim](기본 · ⏎)[/dim]")
    console.print(f"    [cyan] 2[/cyan]  {yes_label}")
    console.print("    [cyan] 0[/cyan]  [dim]← 뒤로[/dim]")
    raw = console.input("  번호 > ").strip()
    if raw == "0":
        return BACK
    if raw in {"", "1", "n", "no"}:
        return False
    if raw in {"2", "y", "yes"}:
        return True
    console.print("  [yellow]못 알아들었다 — 다시 고른다[/yellow]")
    return _confirm(title, no_label, yes_label, reason)


def _steps(name: str) -> list[tuple[str, tuple]]:
    """물어볼 것을 **한 줄로 편다** — 순서가 곧 단계다.

    🚨 순서가 있다 — **위치 인자 → 값 옵션 → 플래그**.
       위치 인자를 옵션 뒤에 붙이면 CLI 가 다르게 읽는다.
    """
    out: list[tuple[str, tuple]] = []
    out += [("arg", s) for s in ASK_ARG.get(name, [])]
    out += [("val", s) for s in ASK_VALUE.get(name, [])]
    out += [("flag", s) for s in ASK_FLAG.get(name, [])]
    return out


def _ask(fn) -> list[str] | None:
    """인자·옵션·플래그를 단계별로 묻는다. 메뉴로 돌아가면 None.

    🔴 `0` 을 누르면 **이전 단계로** 간다. 첫 단계면 메뉴로 나간다.
    """
    name = cli_name(fn)
    steps = _steps(name)
    got: list[list[str]] = []
    i = 0
    try:
        while i < len(steps):
            kind, spec = steps[i]
            if kind == "arg":
                question, required, source = spec
                if source == "path":
                    value = _ask_path(question)
                else:
                    skip = "건너뛴다 — 전체를 보거나 표를 본다"
                    value = _pick(question, _choices(source), required=required, skip_note=skip)
                out = [value] if value and value is not BACK else ([] if value == "" else value)
            elif kind == "val":
                question, flag, options = spec
                value = _pick(question, options, required=True)
                out = [flag, value] if value is not BACK else BACK
            else:
                title, flag, no_label, yes_label = spec
                answer = _confirm(title, no_label, yes_label)
                out = ([flag] if answer else []) if answer is not BACK else BACK

            if out is BACK:
                if i == 0:
                    return None  # 첫 단계에서 뒤로 = 메뉴로
                i -= 1
                got.pop()
                continue
            got.append(out)
            i += 1

        extra = [x for part in got for x in part]
        reason = DANGER.get(name, "")
        if name in DANGER_IF:
            flag, why = DANGER_IF[name]
            reason = why if flag in extra else reason
        if reason:
            answer = _confirm(
                f"{name} 를 실행할까?", "실행하지 않는다", f"{name} 를 실행한다", reason
            )
            if answer is not True:
                console.print("  [yellow]메뉴로 돌아간다[/yellow]")
                return None
        return extra
    except (KeyboardInterrupt, EOFError):
        console.print("\n  [yellow]메뉴로 돌아간다[/yellow]")
        return None


def menu() -> None:
    _check_menu()
    by_num = {k: fn for k, _, fn in MENU if k != GROUP}
    by_name = {cli_name(fn): fn for _, _, fn in MENU if fn is not None}

    while True:
        _draw()
        try:
            choice = console.input("  선택 > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return

        if not choice:
            continue
        if choice in {"0", "q", "quit", "exit"}:
            return
        if choice in by_num and by_num[choice] is None:
            return

        fn = by_num.get(choice) or by_name.get(choice)
        if fn is None:
            console.print("  [red]없는 항목이다[/red] — 번호나 명령 이름을 넣는다")
            continue

        extra = _ask(fn)
        if extra is None:
            continue
        _invoke(fn, *extra)
        # 🚨 결과를 읽기 전에 메뉴가 다시 그려지면 안 된다.
        with contextlib.suppress(KeyboardInterrupt, EOFError):
            console.input("\n  [dim]⏎ 계속[/dim]")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """인자가 없으면 대화형 메뉴, 있으면 해당 명령을 직접 실행한다."""
    if ctx.invoked_subcommand is None:
        menu()


if __name__ == "__main__":
    sys.exit(app())
