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
        console.print(
            "  [green]OK[/green]   .env 이미 있음 — 키 현황은 "
            "[bold]launcher.py keys[/bold], 안내 주석 복원은 [bold]keys --repair[/bold]"
        )
    else:
        env.write_bytes((ROOT / ".env.example").read_bytes())
        console.print("  [green]생성[/green] .env  — [bold]LAW_OC_KEY 를 채워야 한다[/bold]")


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
    args = ["uv", "run", "python", "scripts/doctor.py", "--data"]
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
    """사람이 받아 온 파일을 원장에 올린다 — 🚨 2인 확인이 끝나야 통과한다.

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
    args = ["uv", "run", "python", "-m", "collect.openapi", source, "--use", use]
    if pages:
        args += ["--pages", str(pages)]
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
#
# 🔴 **키가 겹치면 뒤엣것은 영영 안 눌린다** (2026-09-08 · D-162).
#    `g` 가 「받은 파일 등록」과 「Phase 게이트 판정」에, `c` 가 「오픈API 수집」과
#    「커밋 전 점검」에 둘씩 있었다. 조회가 `next(...)` 라 **앞엣것만** 걸린다 —
#    메뉴에는 네 줄이 다 보이는데 두 줄은 눌러도 다른 것이 돈다.
#    ⛔ 그런데 **에러가 안 난다.** `g` 를 누르면 `register` 가 인자 없이 돌아
#       「인자가 부족하다」는 그럴듯한 메시지를 낸다 — 게이트 판정이 안 돌았다는 말은 없다.
#    ★ 등록을 `i`, 커밋 전 점검을 `l` 로 옮겼다. `g`·`c` 는 **표에 적힌 대로** 돌게 뒀다.


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
    ("p", "소스 실측 (저장 없음)", probe),
    ("n", "받은 파일 세기", count),
    ("i", "받은 파일 등록", register),
    ("c", "오픈API 수집", collect),
    ("e", "전처리 추출", extract),
    ("o", "원천 계측", scan),
    ("s", "프로젝트 사본", sync),
    SEP,
    ("4", "데이터 수집", collect),
    ("5", "골든셋 생성", golden),
    ("6", "학습", train),
    ("7", "평가", eval_),
    ("8", "서버 실행", serve),
    ("9", "데모 모드", demo),
    SEP,
    ("k", "API 키 현황", keys),
    ("g", "Phase 게이트 판정", gate),
    ("l", "커밋 전 점검", check),
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
