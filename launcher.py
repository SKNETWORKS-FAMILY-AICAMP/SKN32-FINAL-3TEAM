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
import time
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
    # 🔄 2026-09-21 (전수 재검토) — ⛔ 인자를 Rich 표기로 해석했다. `docs/[draft]/a.md` 가 `docs//a.md` 로 찍히고
    #    `[/tmp]` 가 든 인자는 **실행 전에** MarkupError 로 죽었다. 명령 줄은 글자 그대로 찍는다.
    console.print(f"$ {' '.join(args)}", style="dim", markup=False)
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


#: 미구현 명령의 종료코드 — 🆕 D-254 · 「미구현」 패널 뒤 0 이면 CI·스크립트가 「돌았다」로 읽는다 (D-220).
#: `[임의]` — 1(실패)·2(click 사용법 오류)와 겹치지 않는 수를 골랐을 뿐이다.
STUB_EXIT = 3
#: `--help` 첫 줄에 붙는 표. 🚨 메뉴 설명(`summary`)은 이것을 떼고 보인다 — 메뉴에는 따로 「미구현」 표가 있다.
STUB_TAG = "[미구현]"


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
            # 🆕 D-254 — ⛔ 종전에는 여기서 0 으로 끝났다. 없는 것은 성공이 아니다 (D-220).
            raise typer.Exit(STUB_EXIT)

        # 🆕 D-254 — `--help` 에서 정상 명령처럼 보이던 것. 표는 docstring 앞에 붙인다(한 곳).
        wrapper.__doc__ = f"{STUB_TAG} {(fn.__doc__ or '').strip()}"
        wrapper._planned = True
        return wrapper

    return deco


def needs_data(fn=None, *, unless: str | None = None):
    """🆕 **파생물을 읽는 명령** — 사본이면 부족분을 먼저 받는다 (2026-09-19 · D-247 · 판정 ③).

    ★ 판정 — 「데이터 명령 앞에서 자동」. 클론 A · 팀원이 `load` 를 누르면 부족한 생성물을
      공유 저장소에서 먼저 받고, **받지 못하면 그 명령을 멈춘다** (D-220 — 옛 판 위에서 돌지 않는다).
    🚨 로직은 여기 없다 — `scripts.data_store ensure` 에 위임한다 (얇은 껍데기 · D-51).
       정본·역할 없음(CI)에서는 아무것도 안 한다.
    🚨 **메뉴에 붙이지 않고 명령에 붙인다** — `launcher.py load` 처럼 메뉴를 안 거치는 호출이 있다.
    🔄 2026-09-21 (소성민 코드 리뷰 #9) — `unless=<옵션 이름>` 이 켜져 있으면 받지 않는다.
       ⛔ `embed --check` 는 모델 차원만 재고 파생물·DB 를 안 읽는데(명령 설명 「DB 불필요」), 명령 전체를 감싸서
          저장소가 없는 기기에서는 동기화 실패로 막혔다.
    """
    if fn is None:
        return lambda f: needs_data(f, unless=unless)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if unless and kwargs.get(unless):
            return fn(*args, **kwargs)  # 파생물을 안 읽는 갈래 — 받지 않는다
        if run(sys.executable, "-m", "scripts.data_store", "ensure") != 0:
            console.print("[red]🔴 파생물을 받지 못해 멈췄다[/red] — 위 메시지를 본다 (D-247)")
            raise typer.Exit(1)
        return fn(*args, **kwargs)

    wrapper._needs_data = True
    return wrapper


def needs_raw(fn):
    """🆕 **원문을 읽어 파생물을 만드는 명령** — 정본에 합치지 않은 팀원 원문이 있으면 멈춘다 (D-250).

    ⛔ 원장은 git 병합으로, 원문은 `raw-import` 로 따로 온다. 그 사이에 추출하면 **경고 없이**
       팀원 원문이 빠진 파생물이 나온다. 로직은 `scripts.raw_inbox pending` 에 있다(얇은 껍데기 · D-51).
       정본이 아니면 아무것도 안 한다.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        _raw_pending_or_exit()
        return fn(*args, **kwargs)

    wrapper._needs_raw = True
    return wrapper


def _raw_pending_or_exit() -> None:
    """`needs_raw` 의 몸통 — 🆕 D-254 · `scan` 처럼 **원문을 읽는 갈래에서만** 부르는 명령이 쓴다 (D-99)."""
    if run(sys.executable, "-m", "scripts.raw_inbox", "pending") != 0:
        raise typer.Exit(1)


def only_canonical(what: str) -> None:
    """🆕 파생물·원문을 **만들거나 바꾸는** 자리에서 부른다 — 정본(클론 B)이 아니면 이유와 할 일을 내고 멈춘다.

    ⛔ D-226 1항이 규약뿐이었다 — 사본에서 원장을 거부 없이 썼다(런처 자동화 검토 2026-09-20 발견 1).
    🚨 판단은 `derived_manifest.not_canonical` 한 곳이다 — 스크립트를 직접 불러도 같은 말이 나온다 (D-99).
    ★ **보기만 하는 옵션**(`--write`·`--dump` 없이)은 막지 않는다 — 사본에서도 미리보기는 된다.
    """
    from scripts import derived_manifest as dm  # noqa: PLC0415

    why = dm.not_canonical(what)
    if why:
        console.print(why, markup=False)
        raise typer.Exit(1)


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
    🔄 **`onboard` 의 1단계와 같은 것을 부른다** (2026-09-13 · D-99) — 종전에는 두 곳에
       같은 세 줄이 적혀 있었고, 한쪽만 고쳐지면 새 사람이 밟는 쪽이 낡는다.
    ★ **새 기기라면 이것 말고 `onboard` 를 쓴다** — DB 까지 세우고 **끝에 판정한다.**
    """
    _install()
    console.print("\n[dim]새 기기라면 launcher.py onboard 가 DB 까지 세우고 판정합니다.[/dim]")


def _install() -> int:
    """패키지 · 커밋 훅 · `.env` 틀. 🔴 되돌리는 값은 **빨간 건수**다 (D-220).

    ⛔ 실패를 삼키지 않는다 — `uv sync` 가 죽었는데 다음 단계로 가면
       「환경이 섰다」가 거짓이 된다 (D-162).
    """
    red = 0
    if run("uv", "sync") != 0:
        console.print("🔴 uv sync 실패 — uv 가 깔려 있는가. https://docs.astral.sh/uv/")
        red += 1
    if run("uv", "run", "pre-commit", "install") != 0:
        console.print("🟡 pre-commit 훅을 못 걸었다 — 커밋은 되지만 검사가 안 돈다")
    env = ROOT / ".env"
    if env.exists():
        console.print(
            "  [green]OK[/green]   .env 이미 있음 — 키 현황은 "
            "[bold]launcher.py keys[/bold], 안내 주석 복원은 [bold]keys --repair[/bold]"
        )
    else:
        env.write_bytes((ROOT / ".env.example").read_bytes())
        console.print("  [green]생성[/green] .env  — [bold]LAW_OC_KEY 를 채워야 한다[/bold]")
    return red


@app.command()
def onboard(
    check: bool = typer.Option(False, "--check", help="아무것도 바꾸지 않고 진단만 한다"),
) -> None:
    """새 기기에서 처음부터 — **세우고, 마지막에 판정한다**.

    근거 — D-51 · D-220.
    🔄 **2026-09-13 — 안내만 하던 것을 실행·판정으로 올렸다.**
       ⛔ 종전에는 DB 를 **화면에 명령어로 찍어 주고 끝**이었고, 종료코드는 **항상 0** 이었다.
          그래서 팀원은 초록을 한 번도 못 본 채 「됐겠지」로 넘어갔다 (D-170 의 친척 —
          **아무것도 판정하지 않는 안내**). 실제로 09-13 에 팀원이 막힌 자리가
          정확히 **런처가 손을 놓는 그 자리**였다 (D-221).

    🚨 **런처가 못 하는 셋은 그대로다** — 지어서 넘어가지 않고 **이름으로 낸다** (D-51) —
       ① `.env` 키: `.gitignore` 라 안 따라온다. 사람이 다시 넣는다 (D-111)
       ② `data/raw` 원문: `.gitignore` 라 안 따라온다 (D-19). **다시 받는다**
       ③ `git`: 팀 규칙상 사람이 직접 돈다

    🔴 **끝에 `doctor --env` 로 판정하고 그 종료코드를 그대로 낸다.** 빨강이면 1 이다.
    """
    import shutil  # noqa: PLC0415

    console.print("\n[bold]1. 코드·문서·원장[/bold] — 🚨 사람이 돌립니다")
    console.print("     [bold]git pull[/bold]")
    console.print("     ★ 원장(`data/manifest.jsonl`)은 git 으로 따라옵니다")

    if check:
        console.print("\n[dim]--check — 2~4 단계는 건너뜁니다. 아래는 진단뿐입니다.[/dim]")
    else:
        console.print("\n[bold]2. 파이썬 패키지·커밋 훅·.env 틀[/bold]")
        if _install():
            console.print("\n🔴 여기서 멈춥니다 — 패키지가 없으면 뒤 단계가 전부 거짓이 됩니다.")
            raise typer.Exit(1)

    console.print("\n[bold]3. API 키[/bold] — 🔴 git 에 없습니다. 사람이 다시 넣습니다")
    console.print("     [bold]uv run python launcher.py keys[/bold]        현황(지문만)")
    console.print("     [bold]uv run python launcher.py setkey LAW_OC_KEY[/bold]")
    console.print("     🚨 값을 인자로 주지 않습니다 — PowerShell 기록에 남습니다 (D-111)")

    # 🆕 2026-09-20 (D-247 · D-249) — 파생물·라벨은 git 에 없다. 공유 저장소에서 받는다.
    console.print(
        "\n[bold]3-1. 파생물·라벨[/bold] — 🔴 git 에 없습니다. 팀 공유 저장소에서 받습니다"
    )
    console.print(
        "     Google Drive for desktop 로그인 → 공유받은 `CopyLane_store` 를 내 드라이브에 바로가기 추가"
    )
    console.print(
        "     [bold]uv run python launcher.py data-setup[/bold]   역할(replica) · 저장소를 적고 바로 받습니다"
    )
    console.print(
        "     그 뒤로는 `load`·`chunk`·`embed`·`search-probe` 가 부족분을 스스로 받습니다"
    )
    console.print(
        "     [dim]수집 팀원(D-250) — `CopyLane_raw_inbox` 도 바로가기 추가 → "
        "`data-setup --device collector-1`(영문 · 실명 금지)[/dim]"
    )
    console.print(
        "     [dim]받은 뒤 `raw-publish` → 원장을 **자기 브랜치**로 push → 팀장에게 알림[/dim]"
    )

    console.print("\n[bold]4. DB[/bold] — 거버넌스 19표 + 런타임 7표")
    if shutil.which("docker") is None:
        console.print("  [red]🔴 docker 가 없습니다[/red] — Docker Desktop 을 켜고 다시 부릅니다.")
        console.print("     ⛔ 여기서 멈춥니다. DB 없이 「환경이 섰다」고 말하지 않습니다.")
        raise typer.Exit(1)
    if not check:
        if run(sys.executable, str(ROOT / "launcher.py"), "db-up") != 0:
            console.print("  [red]🔴 db-up 실패[/red] — Docker Desktop 이 켜져 있는지 봅니다.")
            raise typer.Exit(1)
        # 🔴 여기가 09-13 에 팀원이 막힌 자리다 (D-221). 이제 런처가 돌리고, 죽으면 멈춘다.
        if run("uv", "run", "alembic", "upgrade", "head") != 0:
            # 🔄 **2026-09-14 — 안내가 엉뚱한 곳을 가리켰다.** 종전에는 `db-fresh` 만 가리켰는데
            #    그것은 **빈 DB** 만 잰다. 09-14 에 팀원(psj)이 막힌 원인은 **옛 볼륨**이었고,
            #    안내대로 돌렸으면 **초록이 떴을 것**이다. 같은 증상이 이틀 반복된 이유의 후보다.
            #    ⛔ 두 갈래를 가른다 — 위 출력이 그것을 정한다.
            console.print("  [red]🔴 마이그레이션이 실패했습니다.[/red]")
            console.print("     [bold]① 위 오류 본문 전체를 그대로 팀에 주세요.[/bold]")
            console.print("        🚨 본문 없이는 어느 리비전이 걸렸는지 아무도 못 가릅니다.")
            console.print("     ② 지금 어디까지 왔는지: [bold]uv run alembic current[/bold]")
            console.print("     ③ 갈래가 둘입니다 —")
            console.print(
                "        · [bold]새 DB[/bold](처음 세우는 중) → "
                "[bold]launcher.py db-fresh[/bold] 의 출력을 같이 주세요 (D-221)"
            )
            console.print(
                "        · [bold]쓰던 DB[/bold](예전 상태가 남아 있다) → "
                "[bold]launcher.py db-reset[/bold] 로 **먼저 미리보기**를 봅니다"
            )
            console.print("          🔴 `--yes` 는 볼륨을 지웁니다 — 콘솔 계정이 사라집니다 (D-66)")
            raise typer.Exit(1)

    console.print("\n[bold]5. 판정[/bold] — 여기서 초록을 봅니다")
    code = run("uv", "run", "python", "scripts/doctor.py", "--env")

    _onboard_data_steps()

    console.print("\n[bold]8. 콘솔 계정[/bold] — 가입 화면이 없습니다 (D-66 · D-213)")
    console.print("     [bold]uv run python launcher.py admin-add <이니셜>[/bold]")

    if code:
        console.print("\n[red]🔴 진단에 빨강이 있습니다[/red] — 위 「고치는 법」을 먼저 읽습니다.")
    elif check:
        # 🚨 **한 일과 하는 말을 맞춘다.** `--check` 는 아무것도 안 세웠다 —
        #    여기서 「섰습니다」라고 하면 안내가 판정처럼 읽힌다 (D-170 의 친척).
        console.print(
            "\n[green]✅ 진단에 빨강이 없습니다.[/green] "
            "⬜ **--check 라 아무것도 세우지 않았습니다** — 세우려면 옵션 없이 다시 부릅니다."
        )
    else:
        console.print(
            "\n[green]✅ 환경이 섰습니다.[/green] "
            "⬜ 다만 데이터·모델은 아직입니다 (6·7단계 · D-188)."
        )
    console.print("\n[dim]무엇을 하던 중이었는지는 docs/ohb/ 의 최신 인계 문서에 있습니다.[/dim]\n")
    raise typer.Exit(code)


def _onboard_data_steps() -> None:
    """`onboard` 6·7단계 — 🆕 D-254 · **역할마다 다르다.**

    ⛔ 종전에는 누구에게나 「`collect … --use U1` 로 원문을 다시 받는다」 → 「`db-reset --yes --data`」였다.
       사본은 원문이 필요 없고(파생물을 `data-sync` 로 받는다), `db-reset --data` 는 원문을 다시 추출한다 —
       사본에서 따르면 빈 DB 나 반쪽 DB 가 남는다(감사 2026-09-20 §1-5).
    🚨 역할이 없으면 **사본 쪽 안내**를 낸다 — 정본은 클론 B 한 곳뿐이고, 모르는 것을 정본으로 치지 않는다 (D-220).
    """
    from scripts import derived_manifest as dm  # noqa: PLC0415 — 역할 판단은 한 곳 (D-99)

    who = dm.role()
    if who == "canonical":
        console.print("\n[bold]6. 이 기기에 없는 것[/bold] — 데이터는 git 으로 안 옵니다 (D-19)")
        console.print("     [bold]uv run python launcher.py inventory[/bold]")
        console.print("     🚨 「원장에 있다」는 「이 기기에 있다」가 아닙니다")
        console.print(
            "     그 목록대로 [bold]launcher.py collect <소스id> --use U1[/bold] 로 다시 받습니다"
        )
        console.print(
            "     🔴 AI Hub 계열은 사람이 받아 [bold]launcher.py register[/bold] 로 올립니다"
        )

        console.print("\n[bold]7. 원문을 받은 뒤[/bold]  파생물 → DB → 벡터 (정본)")
        # 🔄 **2026-09-14 — 여기에 「재추출」이 없었다.** 이 순서를 그대로 따른 사람은 **낡은
        #    파생물로 DB 를 세운다.** 실측: `citation()` 커버리지가 38.1% 였고, 코드는 09-12 에
        #    고쳤는데 `data/derived/law_article.jsonl` 이 09-10 판이었다. D-221 과 같은 모양이다.
        # ★ 한 명령으로 묶어 두었다. 절차를 두 벌로 적으면 한쪽만 갱신된다 (D-99).
        console.print(
            "     [bold]uv run python launcher.py db-reset --yes --data[/bold]   ← 이 한 줄입니다"
        )
        console.print(
            "     🚨 **재추출부터** 합니다 — 조문·별표를 다시 뽑고, 적재하고, 임베딩합니다."
        )
        console.print("        ⛔ `load` → `chunk` → `embed` 만 돌리면 **낡은 파생물로 섭니다.**")
        console.print("     🔴 볼륨을 지웁니다 — 쓰던 기기라면")
        console.print(
            "        먼저 [bold]launcher.py db-reset[/bold] (미리보기)으로 무엇이 사라지나 봅니다."
        )
    else:
        console.print("\n[bold]6. 원문[/bold] — 🚨 사본은 원문이 필요 없습니다 (D-247)")
        console.print(
            "     파생물은 3-1 의 공유 저장소에서 받습니다 — 원문을 다시 수집하지 않습니다."
        )
        console.print(
            "     [dim]수집을 맡은 팀원만(D-250) 지정받은 소스를 "
            "`collect <소스id>` → `raw-publish` 로 올립니다[/dim]"
        )
        if who is None:
            console.print(
                "     🟡 이 기기의 역할이 아직 없습니다 — 3-1 의 "
                "[bold]launcher.py data-setup[/bold] 을 먼저 합니다"
            )

        console.print("\n[bold]7. 파생물을 받은 뒤[/bold]  DB → 벡터 (사본)")
        console.print(
            "     [bold]uv run python launcher.py data-sync[/bold]   부족한 파생물을 받습니다"
        )
        console.print("     [bold]uv run python launcher.py load[/bold]        DB 에 적재합니다")
        console.print("     [bold]uv run python launcher.py embed[/bold]       벡터를 넣습니다")
        console.print(
            "     ⛔ `db-reset --data` 는 쓰지 않습니다 — 원문을 다시 추출하는 정본 절차입니다"
        )
    console.print("     ⚠️ KURE-v1 모델 2.27GB 를 처음 한 번 내려받습니다")


@app.command()
def setkey(
    name: str = typer.Argument(..., help="키 이름 (예: FOODSAFETY_KEY)"),
    extra: list[str] = typer.Argument(None, hidden=True, show_default=False),  # noqa: B008
) -> None:
    """API 키를 화면에 뜨지 않게 입력해 설정 파일에 넣는다.

    🚨 값을 **인자로 주지 않는다.** 이름만 주면 물어보고, 입력은 화면에 표시되지 않는다.
       인자로 주면 PowerShell 기록 파일(`ConsoleHost_history.txt`)에 그대로 남는다 —
       터미널을 닫아도 남고, 지운 줄 알아도 남아 있다.
       확인은 값이 아니라 **지문**으로 낸다. 지문은 붙여 넣어도 안전하다.
    🆕 D-254 — **모르는 이름은 `run()` 앞에서 멈추고 되비추지 않는다.** `run()` 은 명령 줄을 화면에 찍는다 —
       이름 자리에 **값**을 붙여 넣었다면 그 줄이 곧 유출이다(감사 2026-09-20 §1-2).
       🔗 이름 목록은 `collect.env.KEYS` 한 곳 — `collect/setkey.py` 도 같은 표로 거부한다 (D-99).
    """
    from collect import env  # noqa: PLC0415 — 키 이름의 정본

    if extra:
        # 🔄 2026-09-21 (전수 재검토) — ⛔ 인자를 더 주면 Click 이 「Got unexpected extra argument(s) (sk-…)」로
        #    **값을 그대로 되비췄다.** 이름 뒤에 키를 붙여 넣는 실수가 정확히 그 모양이다. 받아서 버리고 안 찍는다.
        console.print(
            "[red]🔴 인자를 하나만 준다 — 이름만.[/red] 값은 인자로 받지 않는다(셸 기록에 남는다). "
            "뒤에 준 것은 **읽지도 찍지도 않았다.**"
        )
        console.print(
            "  🚨 값을 붙여 넣었다면 셸 기록에 남았다 — 그 키는 재발급을 검토한다 (팀장 판정)"
        )
        raise typer.Exit(1)
    if name not in env.KEYS:
        console.print("[red]🔴 모르는 키 이름이다[/red] — 입력은 화면에 다시 찍지 않는다.")
        console.print("  아는 이름: " + " · ".join(env.KEYS), markup=False)
        raise typer.Exit(1)
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
        if hash_check:
            # 🔄 2026-09-21 (전수 재검토) — ⛔ `--env --hash` 는 `--hash` 를 **말없이 버렸다**(메뉴가 둘 다 묻고 보냈다).
            #    해시는 데이터 검사의 옵션이다 — 둘 다 줬으면 환경 다음에 데이터까지 본다(`doctor.py` 가 이어서 돈다).
            args += ["--data", "--hash"]
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
    🆕 D-254 — `-rs` 로 **건너뛴 테스트의 이름·사유**를 끝에 낸다. ⛔ 종전 `-v` 는 pyproject 의 `-q` 와
       상쇄돼 skip 이 숫자로만 보였다 — 사본에서 skip 만으로 초록이 떠도 무엇이 안 돌았는지 몰랐다.
       ⬜ skip 은 실패로 치지 않는다 — pytest 의 종료코드를 그대로 낸다.
    """
    raise typer.Exit(run(*GATE_CMD))


#: 게이트 호출 — `gate` 와 `check` 가 **이 한 줄**을 쓴다 (D-99 · D-254).
GATE_CMD = ("uv", "run", "pytest", "-m", "gate", "-rs")

#: ruff 두 단계 — 🔴 **`.pre-commit-config.yaml` 과 같은 순서다** (`ruff --fix` → `ruff-format`) · D-254.
#:    ⛔ 종전에는 거꾸로(format → fix)였다. `--fix` 가 import 를 고치면 서식이 다시 흐트러져
#:       커밋 훅이 파일을 고치고 커밋을 멈춘다. `fmt` 와 `check` 가 이 표 하나를 돈다 (D-99).
RUFF_STEPS = (
    ("uv", "run", "ruff", "check", "--fix", "."),
    ("uv", "run", "ruff", "format", "."),
)


def _ruff() -> int:
    """ruff 두 단계를 다 돌고 **하나라도 실패하면 1** — ⛔ 종전에는 format 의 종료코드를 버렸다 (D-220)."""
    return int(any([run(*cmd) != 0 for cmd in RUFF_STEPS]))


@app.command()
def fmt() -> None:
    """코드 서식과 import 순서를 자동으로 맞춘다."""
    raise typer.Exit(_ruff())


@app.command()
def check() -> None:
    """커밋 전에 한 번. 코드 정리 + 게이트 검사.

    🚨 순서가 핵심이다. `ruff check` 만 돌리고 커밋하면 `ruff-format` 훅이
       커밋 시점에 파일을 고치고 커밋이 중단된다. 고칠 것을 **먼저** 고친다.
    ⬜ gitleaks·개행 훅·비게이트 테스트는 안 돈다 — 커밋 통과를 보장하지 않는다.
    """
    if _ruff():
        raise typer.Exit(1)
    raise typer.Exit(run(*GATE_CMD))


# ══════════════════════════════════════════════════════════
# 데이터 거버넌스 — 레지스트리·검토표·매트릭스는 전부 생성물이다
# ══════════════════════════════════════════════════════════
@app.command()
def registry() -> None:
    """어떤 데이터를 수집해도 되는지 목록을 다시 만든다.

    🚨 `data_sources.yaml` 을 손으로 고치지 않는다. 생성물이다.
       판정·검토 기록은 `scripts/registry_review.yaml` 에 적는다.
    🆕 D-254 — **판정매트릭스가 원본과 맞는지 먼저 본다.** `gen_registry.py` 는 `sources.json` 을 읽으므로
       `data.js` 를 고치고 이것만 누르면 **에러 없이 옛 판정으로** 집행 파일이 나온다. 어긋나면 멈춘다.
    """
    _matrix_fresh_or_exit()
    raise typer.Exit(run("uv", "run", "python", "scripts/gen_registry.py"))


#: 판정매트릭스 대조 — 쓰지 않고 `data.js` ↔ `sources.json`·HTML 이 같은지만 본다 (D-254).
MATRIX_CHECK = ("uv", "run", "python", "scripts/build_matrix.py", "--check")


def _matrix_fresh_or_exit() -> None:
    """🆕 D-254 — 생성물 넷 중 **하나만** 도는 메뉴(11·13) 앞에서 부른다. 한 벌은 `rebuild` 다."""
    if run(*MATRIX_CHECK) != 0:
        console.print(
            "  [red]🔴 판정매트릭스가 원본(data.js)과 어긋나 멈췄다[/red] — "
            "넷을 한 벌로: [bold]launcher.py rebuild[/bold]"
        )
        raise typer.Exit(1)


@app.command()
def review() -> None:
    """다른 사람이 등급 판정을 재확인할 표를 뽑는다.

    판정 근거를 매트릭스에서 다시 뽑고 검토표를 낸다. 검토자는 A 구간을 자세히,
    B 를 확인, C 를 훑는다. 결과는 `scripts/registry_review.yaml` 에 적는다.
    🆕 D-254 — `registry` 와 같이 판정매트릭스 대조를 먼저 한다.
    ⬜ `data_sources.yaml` 이 `sources.json` 보다 낡았는지는 못 본다 — `gen_registry.py` 에 대조 모드가 없다.
    """
    _matrix_fresh_or_exit()
    if run("uv", "run", "python", "scripts/extract_rationale.py") != 0:
        raise typer.Exit(1)
    raise typer.Exit(run("uv", "run", "python", "scripts/review_sheet.py"))


@app.command()
def matrix() -> None:
    """소스별 등급 근거 페이지를 다시 만든다.

    소스마다 왜 그 등급인지를 정리한 HTML 이다.
    `_matrix/data.js` -> `sources.json` + `판정매트릭스.html` (D-87 · D-90).
    🆕 D-254 — 이것만 돌면 레지스트리는 **옛 판정**이다. 끝에 그 사실과 할 일을 낸다.
    """
    rc = run("uv", "run", "python", "scripts/build_matrix.py")
    if rc == 0:
        console.print(
            "  [yellow]🟡 레지스트리·근거·검토표는 아직 옛 판정이다[/yellow] — "
            "[bold]launcher.py rebuild[/bold] 로 한 벌을 맞춘다"
        )
    raise typer.Exit(rc)


@app.command()
def rebuild() -> None:
    """등급 판정을 고친 뒤 — 생성물 넷을 한 벌로 다시 만든다.

    🔴 **넷은 한 벌이다.** `_matrix/data.js`(사람이 쓴 판정) 하나에서 갈라진다 —

        build_matrix.py      -> sources.json + 판정매트릭스   근거 (사람이 읽는다) · 🔴 먼저
        gen_registry.py      -> data_sources.yaml            집행 (게이트가 읽는다) · sources.json 을 읽는다
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
    # 🔴 2026-09-19 — **판정매트릭스가 먼저다** (클론A 인계 09-18 F4). `gen_registry.py` 는 `build_matrix.py` 가 만드는
    #    `sources.json` 을 읽는다. ⛔ 거꾸로면 새 id 는 `KeyError` 이고, **기존 레코드를 고치면 에러 없이 옛 판정으로**
    #    `data_sources.yaml` 을 만든다 — 한 번의 rebuild 가 두 벌을 만든다 (D-90). `_matrix/README.md` 순서와 같다.
    #    ★ 이 날 `mfds_cgm_expc` 를 G0 → G3 로 고치며 그 자리를 밟을 참이었다. 순서 게이트가 지킨다.
    steps = (
        (["scripts/build_matrix.py"], "판정매트릭스"),
        (["scripts/gen_registry.py"], "레지스트리"),
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
    """도면 원천(HTML) → PNG. ⛔ PNG 는 손으로 고치지 않는다.

    근거 — D-90 · D-217.
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
    """결정이 코드의 어디에 사는지 표로 뽑는다.

    산출 — `build/decision_map.md` (생성물 · D-90).

    ⛔ **「인용 0건」이 「미구현」은 아니다.** 세 갈래가 섞여 있고 **가르는 것은 사람이다** —
       ① 코드가 아직 없다 ② 코드에는 있는데 D 번호를 안 적었다 ③ 코드로 갈 결정이 아니다.
    ★ 그 판정은 `docs/02_설계/구현계획.md` 가 든다. 이 명령은 **셀 수 있는 것만** 낸다.
    """
    args = ["uv", "run", "python", "-m", "scripts.decision_map"]
    if open_only:
        args.append("--open")
    raise typer.Exit(run(*args))


@app.command(name="admin-add")
def admin_add(
    initials: str = typer.Argument(..., help="docs/<이니셜>/ 과 같은 철자"),
    extra: list[str] = typer.Argument(None, hidden=True, show_default=False),  # noqa: B008
) -> None:
    """거버넌스 콘솔 계정을 만든다 — 가입 화면은 없다.

    근거 — D-66 · D-213.

    🚨 **비밀번호는 화면에 안 뜨고 셸 인자로도 안 받는다** (`getpass`). `setkey` 와 같은
       이유다 — PowerShell 기록 파일에 값이 그대로 남는다 (D-111).
    🔴 명단의 정본은 **디스크**다 — `docs/<이니셜>/` 이 없으면 거부한다 (D-99).
    """
    if extra:
        # 🔄 2026-09-21 (전수 재검토) — ⛔ 비밀번호를 뒤에 붙이면 Click 이 그대로 되비췄다 (`setkey` 와 같은 자리)
        console.print(
            "[red]🔴 이니셜만 준다.[/red] 비밀번호는 묻는다 — 뒤에 준 것은 읽지도 찍지도 않았다."
        )
        raise typer.Exit(1)
    raise typer.Exit(run("uv", "run", "python", "-m", "scripts.admin_account", "add", initials))


@app.command(name="admin-list")
def admin_list() -> None:
    """거버넌스 콘솔 계정 목록 — ⛔ 해시는 안 찍는다."""
    raise typer.Exit(run("uv", "run", "python", "-m", "scripts.admin_account", "list"))


#: 컨테이너 안에서 psql·pg_isready 에 넘기는 접속 인자.
#: 🚨 두 번째로 쓰게 되어 상수로 뺐다 (D-99) — `_db_ready()` 와 `db_up()` 이 같은 값을 본다.
#: ⛔ `docker-compose.yml` 은 `POSTGRES_USER:-copylane` 로 **덮어쓸 수 있게** 되어 있는데
#:    여기는 고정이다. 종전 psql 호출도 그랬다 — 범위 밖이라 안 고쳤다 (D-192).
_PG_CONN = ("-U", "copylane", "-d", "copylane")

#: 🚨 `docker compose up -d` 는 **컨테이너가 연결을 받기 전에 돌아온다.**
#:    compose 의 healthcheck 는 5초 간격이라 첫 판정 전에는 `starting` 이다.
#: ⛔ **2026-09-16 · 여기서 기다리지 않아 사고가 났다** — `CREATE EXTENSION` 이
#:    「소켓 없음」으로 실패했는데 바로 아래 줄이 **「DB 준비 완료 (pgvector 확장 포함)」**
#:    을 찍었다. 거짓 성공이다 (D-162). 확장이 없었다면 `0001` 이 터지고, 그 사람은
#:    「준비 완료」 화면을 보고 딴 데를 판다 — 09-13·14 에 팀원 둘이 잃은 하루가 그 모양이다.
#: `[임의]` — 로컬 도커 기동 시간을 잰 적이 없다. 🚨 **넘치면 멈춘다**(아래).
#:    값이 틀려도 조용히 지나가지 않는다는 것이 이 값을 `[임의]` 로 둘 수 있는 이유다.
DB_READY_TIMEOUT_S = 60
DB_READY_POLL_S = 1.0


def _db_ready(timeout_s: int = DB_READY_TIMEOUT_S) -> bool:
    """컨테이너의 postgres 가 연결을 받을 때까지 기다린다. 화면은 조용하다.

    🚨 `docker compose ps` 의 상태 문자열을 파싱하지 않는다 — compose 판마다 다르다.
       **실제로 접속이 되는가**를 본다 (`pg_isready`).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        probe = subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres", "pg_isready", *_PG_CONN],
            cwd=ROOT,
            capture_output=True,
        )
        if probe.returncode == 0:
            return True
        time.sleep(DB_READY_POLL_S)
    return False


@app.command(name="db-up")
def db_up() -> None:
    """로컬 데이터베이스를 켠다 (Docker Desktop 필요).

    postgres + pgvector 컨테이너. `127.0.0.1` 에만 열린다 (P3-14).
    🚨 **연결이 서고 확장까지 붙은 뒤에만 「준비 완료」라고 적는다** (D-162).
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

    console.print(f"  [dim]연결을 받을 때까지 기다린다 (최대 {DB_READY_TIMEOUT_S}초) …[/dim]")
    if not _db_ready():
        console.print(
            Panel(
                f"{DB_READY_TIMEOUT_S}초 안에 postgres 가 연결을 받지 않았다.\n\n"
                "  docker compose ps\n"
                "  docker compose logs postgres --tail 50\n\n"
                "⛔ 여기서 멈춘다 — 확장을 못 만든 채 「준비 완료」라고 적지 않는다 (D-162).",
                title="DB 기동 실패 — 기다려도 안 선다",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    # 🚨 init 스크립트는 볼륨이 비어 있을 때만 돈다. 기존 볼륨에는 여기서 붙인다.
    # ⛔ **반환값을 버리지 않는다.** 종전에는 버리고 아래 「준비 완료」를 무조건 찍었다.
    if (
        run(
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            *_PG_CONN,
            "-c",
            "CREATE EXTENSION IF NOT EXISTS vector;",
        )
        != 0
    ):
        console.print(
            Panel(
                "`CREATE EXTENSION vector` 가 실패했다. 위 psql 출력이 원인이다.\n\n"
                "⛔ 이 상태로 `migrate` 를 돌리면 `0001` 이 벡터 열에서 터진다.\n"
                "   증상이 원인과 다른 자리에서 나오므로 여기서 멈춘다 (D-162).",
                title="pgvector 확장 실패",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    console.print("  [green]DB 준비 완료[/green]  127.0.0.1:5432  (pgvector 확장 포함)")


@app.command(name="db-down")
def db_down() -> None:
    """데이터베이스를 끈다. 저장된 데이터는 그대로 남는다."""
    raise typer.Exit(run("docker", "compose", "stop"))


@app.command(name="db-fresh")
def db_fresh(keep: bool = typer.Option(False, "--keep", help="임시 DB 를 안 지운다")) -> None:
    """빈 DB 에서 `migrate` 가 끝까지 도는가 — **새로 클론한 사람이 밟는 자리**.

    근거 — D-221.

    🔴 2026-09-13 에 팀원이 새 기기에서 막혔다. 다들 쓰던 DB 에 이어 붙이기만 해서
       **빈 DB 에서 처음부터 돌린 적이 없었다** (D-146).
    🚨 **옆에 임시 DB 를 만들어** 거기에만 적용하고 지운다 — 진짜 DB 는 안 건드린다.
    """
    args = ["uv", "run", "python", "-m", "scripts.db_fresh_check"]
    if keep:
        args.append("--keep")
    raise typer.Exit(run(*args))


@app.command(name="db-drift")
def db_drift(keep: bool = typer.Option(False, "--keep", help="임시 DB 둘을 안 지운다")) -> None:
    """스키마 선언과 실제 DB 가 같은 모양인가 — **두 벌이 조용히 갈리는 것을 잡는다**.

    🔴 `0001` 은 DDL 을 자기 안에 안 적고 **실행 시점에 `db/schema.sql` 을 읽는다.**
       그 파일이 바뀌면 **「3번 마이그레이션이 도는 DB 의 모양」이 사람마다 달라진다** —
       새로 클론한 사람은 오늘자 모양 위에서, 쓰던 사람은 그때 모양 위에서 돈다 (D-221).
    🚨 **`db-fresh` 와 다른 물건이다** — 저쪽은 *돌았는가*, 이쪽은 *같은가*를 본다.
    ⛔ **`0001` 동결의 선결이다.** 갈려 있는 채로 동결하면 그 차이가 영구히 굳는다.
    """
    args = ["uv", "run", "python", "-m", "scripts.schema_drift_check"]
    if keep:
        args.append("--keep")
    raise typer.Exit(run(*args))


@app.command(name="db-reset")
def db_reset(
    yes: bool = typer.Option(False, "--yes", help="🔴 실제로 지운다 — 없으면 미리보기"),
    data: bool = typer.Option(False, "--data", help="파생물 재추출 → 적재 → 임베딩까지"),
) -> None:
    """데이터베이스를 처음부터 다시 만든다 — **고치지 않고 다시 세운다**.

    🔴 09-13·09-14 에 팀원 둘이 옛 DB 상태 때문에 막혔고, 둘 다 `docker compose down -v` 로
       **자력으로** 풀었다. 처방은 있었는데 **절차가 아니어서 각자 따로 발견했다** (D-221).
    ★ DB 를 **생성물**로 본다 — 원천은 마이그레이션 체인·`data/derived/**`·시드다 (D-90).
    🚨 **콘솔 계정이 사라진다** — DB 에만 있고 파일에 없는 유일한 값이다 (D-66 · D-213).
       지우기 전에 명단을 읽어 두고, 다시 세운 뒤 사람이 칠 명령을 찍는다.
    ⛔ **기본은 미리보기다.** `--yes` 를 줘야 지운다 (D-220 fail-closed).
    """
    args = ["uv", "run", "python", "-m", "scripts.db_reset"]
    if yes:
        args.append("--yes")
    if data:
        args.append("--data")
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
        런타임 층 12테이블           `app/models.py`   ORM · `migrate-new` 로 autogenerate (🔄 09-22 — 0016·0017)

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
@needs_data
def search_probe(
    queries: str = typer.Option("", help="질의 JSONL 경로 (비우면 기본 경로)"),
    pool: int = typer.Option(0, help="후보 폭 (0 이면 기획서 5-6 의 50)"),
) -> None:
    """검색 순위를 잰다 — 🚨 **원장에 올릴 수를 만드는 자리**다.

    근거 — D-204.

    전체(필터 없음) + 법 넷을 다 돌고 갈래별 순위와 RRF 순위를 낸다(🔄 W6 · D-271 ③). 30건 미만이면 D-40 으로
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
    소스의 **원문 폴더**로 복사하고 manifest 에 1행 남깁니다 — 등급 디렉터리가 아닙니다 (D-92).
    🔴 원문 폴더는 소스 id 와 이름이 다를 수 있습니다 (`store.raw_dir_of` · D-245) —
       예전 설명(「소스 id 폴더로 복사」)을 믿고 넣었다가 화장품법 334노드가 사라졌습니다.
    ⛔ 다른 기기에서 받은 raw 를 합치는 데 쓰지 않습니다 — 하위 폴더를 펴고, 첫 폴더로만
       넣고, 원장에 행을 또 붙입니다 (검토 2026-09-19 §3-d).
    """
    raise typer.Exit(
        run("uv", "run", "python", "-m", "collect.ingest", "register", source, path, "--use", use)
    )


@app.command()
def adopt(
    source: str = typer.Argument(..., help="레지스트리 소스 id"),
    stem: str = typer.Argument(..., help="판을 뺀 원본 이름 (확장자 없이)"),
) -> None:
    """판(`__c…`)을 **원본 자리로 올린다** — `collect` 가 만들고 `current_files` 가 멈추는 그 다음 칸.

    🔴 이 자리가 비어 있었습니다 (2026-09-18). 수집기는 원본을 덮지 않고 판으로 저장하고
       (규약 2), 추출기는 판이 있으면 멈춥니다(D-143 — 어느 것을 쓸지는 사람이 정한다).
       **채택하는 명령이 없어서** 손으로 옮기다가 원장이 깨졌습니다.
    🚨 원장에 원본 경로의 새 행을 붙입니다 — 그래야 `doctor --hash` 가 훼손으로 안 봅니다.
    🚨 2인 확인은 요구하지 않습니다 (팀장 판정) — 채택 자체가 사람의 판정입니다.
    🆕 2026-09-20 — **정본에서만** 합니다. 팀원 기기에서 채택하면 원본 경로의 바이트가 정본과 갈리고,
       `raw-import` 는 덮어쓰지 않으므로 **영영 안 맞춰집니다** (D-250). 판은 그대로 올리면 정본이 고릅니다.
    """
    only_canonical(f"adopt {source}")
    raise typer.Exit(run("uv", "run", "python", "-m", "collect.ingest", "adopt", source, stem))


@app.command()
def collect(
    source: str = typer.Argument(..., help="레지스트리 소스 id"),
    use: str | None = typer.Option(
        None,
        "--use",
        help="U1~U4 — 소스 id 를 받는 수집기만(비우면 U1). 안 받는 수집기에 주면 거부",
    ),
    pages: int = typer.Option(0, "--pages", help="🚨 첫 실행은 1 로 — 응답을 보고 전량을 받는다"),
    limit: int = typer.Option(0, "--limit", help="앞 N 건만 — 받는 수집기만 (안 받으면 거부)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="저장하지 않고 무엇을 받을지만 — 받는 수집기만 (안 받으면 거부)"
    ),
    force: bool = typer.Option(
        False, "--force", help="다른 기기가 최근에 받은 소스라도 받는다 (D-250 겹침 경고를 넘긴다)"
    ),
) -> None:
    """원천에서 원문을 내려받는다 — 소스마다 맞는 수집기로 보냅니다.

    2인 확인이 안 끝난 소스는 게이트가 첫 줄에서 거부합니다 (D-15 · D-66).
    어느 수집기로 갈지는 `collect/__init__.py` 의 `COLLECTORS` 표가 정합니다 (D-179).

    🆕 2026-09-18 — 법제처 목록형은 `--dry-run` · `--limit` 을 넘깁니다.
       첫 실행은 `--dry-run` → `--limit 20` → 전량 순서로 봅니다.
    🔄 2026-09-21 — `--dry-run` · `--limit` · `--pages` 는 **그 수집기가 받을 때만** 넘깁니다.
       안 받는 수집기에 주면 받기 전에 멈춥니다 (표 — `collect/__init__.py` 의 `COLLECTOR_OPTIONS`).
    🚨 **파생물은 클론 B 에서만 만듭니다** (D-226).
    🔄 2026-09-20 (D-250) — 수집은 **지정 팀원도** 합니다. 받은 원문은 `raw-publish` 로 올리고
       원장은 자기 브랜치로 올립니다 → 팀장이 검토·병합 → 정본이 `raw-import` 로 합칩니다.
       다른 기기가 최근 7일 안에 받은 소스면 **먼저 멈추고 알립니다** — 알고 받으려면 `--force`.
       (겹쳐 받아도 섞이지는 않습니다 — 원장의 sha 로 같으면 건너뛰고 다르면 새 판입니다.)
    """
    from collect import (  # noqa: PLC0415 — 표는 collect 가 든다
        COLLECTOR_OPTIONS,
        COLLECTORS,
        MANUAL_SOURCES,
    )

    if source in MANUAL_SOURCES:
        typer.echo(
            f"⬜ `{source}` 는 **사람이 받는 소스**입니다 — 신청·회원가입이 필요합니다.\n"
            f"   받은 뒤: uv run python launcher.py register {source} <경로> --use {use or 'U1'}"
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
    # 🆕 2026-09-21 (코드 리뷰 #4) — 안 받는 인자는 **받기 전에** 거부한다. ⛔ 종전에는 말없이 버려서
    #    `--dry-run` 이 실제 수집이 됐다 — 아래 `if not dry_run` 이 별칭·겹침 검사까지 건너뛴 채로.
    offered = COLLECTOR_OPTIONS.get(module, frozenset())
    # 🔄 2026-09-21 (전수 재검토) — `--use` 도 같은 규칙이다. ⛔ 소스 id 를 받는 수집기(`arg`)에만 넘기고 나머지(넷)는
    #    **말없이 버렸다** — 그 수집기들은 용도를 코드에 박아 두어, 사용자가 적은 용도가 레지스트리와 대조되지 않았다.
    if shape == "arg":
        offered = offered | {"--use"}
    asked = {"--dry-run": dry_run, "--limit": limit, "--pages": pages, "--use": use}
    refused = [k for k, v in asked.items() if v and k not in offered]
    if refused:
        typer.echo(
            f"🔴 `{source}` 의 수집기({module})는 {', '.join(refused)} 를 받지 않습니다 — 아무것도 받지 않았습니다.\n"
            f"   받는 것: {', '.join(sorted(offered)) or '없음'}  (표 — collect/__init__.py 의 COLLECTOR_OPTIONS)"
        )
        raise typer.Exit(1)
    if not dry_run:
        from collect import store  # noqa: PLC0415

        try:
            store.device_id()  # 🆕 D-250 — 별칭이 없으면 받기 **전에** 멈춘다
        except store.StoreError as e:
            typer.echo(f"🔴 {e}")
            raise typer.Exit(1) from None
        others = store.recent_by_others(source)
        if others and not force:
            typer.echo(
                f"🟡 `{source}` 는 다른 기기가 최근 {store.OVERLAP_DAYS}일 안에 받았습니다 — "
                + " · ".join(f"{k} {v[:10]}" for k, v in sorted(others.items()))
                + "\n   겹쳐 받는지 팀에 먼저 확인합니다. 원장이 최신인지도 봅니다 (`git pull`).\n"
                f"   알고 받으려면: uv run python launcher.py collect {source} --force"
            )
            raise typer.Exit(1)
    args = ["uv", "run", "python", "-m", module]
    if shape == "arg":
        args += [source, "--use", use or "U1"]
    elif shape.startswith("target"):
        # 🚨 값은 표가 든다 — `target` 만 있으면 법령(`law`)이다. 런처가 target 을 추정하지 않는다.
        args += ["--target", shape.partition("=")[2] or "law"]
    # 여기 오면 위 거부를 지났다 — 준 인자는 그 수집기가 받는 것이다
    if pages:
        args += ["--pages", str(pages)]
    if dry_run:
        args.append("--dry-run")
    if limit:
        args += ["--limit", str(limit)]
    rc = run(*args)
    if rc == 0 and not dry_run:
        _after_collect(source)
    raise typer.Exit(rc)


def _refresh_ids(source: str) -> list[str]:
    """`data-refresh` 가 받는 원천 id 중 **이 소스의 원문을 읽는 것** — 🆕 D-254.

    같은 id 가 추출기 표에 있으면 그것, 없으면 원문 폴더(`store.families`)가 겹치는 추출기 id.
    ⛔ 종전 안내는 어느 소스든 `data-refresh <원천>` 이었고, 15개 중 10개가 「모르는 원천」으로 거부됐다.
    🔗 표는 `preprocess.EXTRACTORS`·`collect.store.FAMILY_OF` 가 든다 — 여기서 만들지 않는다 (D-99).
    """
    from collect import store  # noqa: PLC0415
    from preprocess import EXTRACTORS  # noqa: PLC0415

    if source in EXTRACTORS:
        return [source]
    mine = set(store.families(source))
    return sorted(k for k in EXTRACTORS if mine & set(store.families(k)))


def _after_collect(source: str) -> None:
    """🆕 수집이 끝난 뒤 **다음에 칠 것** — 역할마다 다르다 (런처 자동화 검토 발견 5).

    🚨 올리기는 자동으로 하지 않는다 — 외부 전송이라 사람이 본다(`raw-publish` 가 한 번 묻는다).
    🔄 D-254 — 정본의 안내는 **`data-refresh` 가 실제로 받는 원천일 때만** 그 명령을 낸다.
    """
    from scripts import derived_manifest as dm  # noqa: PLC0415

    if dm.role() == "canonical":
        ids = _refresh_ids(source)
        if ids:
            console.print(
                f"\n  다음 — 파생물: uv run python launcher.py data-refresh {' '.join(ids)}  "
                "(판 `__c…` 이 생겼으면 먼저 `adopt`)",
                markup=False,
            )
            return
        # ⬜ 추출기 표에 없다 — `data-refresh` 는 거부한다. 지어서 안내하지 않는다 (D-220).
        console.print(
            f"\n  다음 — `{source}` 의 추출기는 preprocess/__init__.py EXTRACTORS 표에 없습니다.\n"
            "    `data-refresh` 로는 다시 만들 수 없습니다 (표에 없는 원천은 거부합니다).\n"
            "    법령(law_go_kr)의 조문·별표 추출 명령은 scripts/db_reset.py `reload_data` 의 표에 있습니다\n"
            "    (🚨 `db-reset --yes --data` 는 볼륨을 지웁니다 — 추출만 하려면 그 표의 두 줄을 직접 돌립니다).\n"
            "    그 밖의 원천은 이 원문을 읽는 preprocess 모듈이 있는지부터 봅니다.\n"
            "    판 `__c…` 이 생겼으면 먼저 `adopt`.",
            markup=False,
        )
        return
    console.print(
        "\n  다음 (수집 팀원) —\n"
        "    uv run python launcher.py raw-publish          받은 원문을 받은편지함에 올린다\n"
        "    git add data/manifest.jsonl\n"
        '    git commit -m "수집 — <원천>"\n'
        "    git push origin <내 브랜치>                    🚨 ohb 가 아니라 자기 브랜치\n"
        "  그리고 팀장에게 브랜치 이름을 알린다 (D-250)",
        markup=False,
    )


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
def derived_manifest(
    write: bool = typer.Option(False, "--write", help="data/derived_manifest.jsonl 을 씁니다"),
    check: bool = typer.Option(False, "--check", help="원장 ↔ 디스크 대조. 다르면 종료코드 1"),
) -> None:
    """**파생물 원장** — 기기 사이에 파생물을 옮길 때 같은지 확인합니다.

    🚨 `data/manifest.jsonl` 은 **raw 전용**입니다(20,395행 · derived 0행). 그래서
       「네가 받은 파생물이 내 것과 같은가」를 물을 수 없었습니다 — 이것이 그 짝입니다.
    🔴 부류를 넷으로 가릅니다 — **원천**(다시 안 나온다) · **표본**(다시 뽑으면 갈린다) ·
       **생성물** · **원문캐시**(마스킹 전 원문 — 옮기지 않는다). 앞의 둘만 git 으로
       따라갑니다 (`.gitignore` 예외). 부류 이름의 정본은 `KIND_RULES` 한 곳입니다.
    🔄 `--check` 는 **기기 역할**(`.env` 의 `DATA_ROLE`)대로 봅니다 (D-247) — 정본은 전부,
       사본은 원문캐시를 빼고, 역할이 없으면(CI) git 이 옮기는 것만 요구합니다.
    """
    args = ["uv", "run", "python", "scripts/derived_manifest.py"]
    if write:
        args.append("--write")
    if check:
        args.append("--check")
    raise typer.Exit(run(*args))


@app.command(name="data-sync")
def data_sync(
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 받을지만 보여 준다"),
) -> None:
    """부족하거나 낡은 파생물을 공유 저장소에서 받습니다 — 사본(클론 A · 팀원 · 서버)용.

    🆕 2026-09-19 (D-247). 무엇을 받을지는 **git 의 파생물 원장**이 정합니다 — 지금 체크아웃한
       커밋의 판을 받습니다. 옛 파일은 레포 밖 `CopyLane_backup` 에 복사해 둡니다.
    🚨 `.env` 에 `DATA_ROLE=replica` 와 `DATA_STORE=<폴더>` 가 있어야 합니다. 정본은 받지 않습니다.
    """
    args = [sys.executable, "-m", "scripts.data_store", "sync"]
    if yes:
        args.append("--yes")
    if dry_run:
        args.append("--dry-run")
    raise typer.Exit(run(*args))


@app.command(name="data-setup")
def data_setup(
    role: str = typer.Option("", "--role", help="canonical | replica (비우면 묻는다)"),
    store: str = typer.Option("", "--store", help="저장소 폴더 (비우면 드라이브에서 찾는다)"),
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    inbox: str = typer.Option(
        "", "--inbox", help="원문 받은편지함 폴더 (비우면 찾는다 · 수집 팀원)"
    ),
    device: str = typer.Option(
        "", "--device", help="이 기기 이름 — 영문 (예: collector-1 · 실명 금지)"
    ),
    mirror: str = typer.Option(
        "", "--mirror", help="정본 원문 거울 폴더 (비우면 찾는다 · 팀장 기기 · D-256)"
    ),
) -> None:
    """이 기기의 데이터 역할과 공유 저장소를 설정 파일에 적고, 받는 쪽이면 바로 받습니다.

    🆕 2026-09-20 (D-247 · D-249) — `.env` 를 손으로 열지 않습니다. 저장소 폴더
       `CopyLane_store` 를 Google Drive 가 붙은 드라이브에서 **찾아서** 적습니다.
    🚨 정본(canonical)은 클론 B 한 곳입니다 — 고르면 한 번 더 묻습니다 (D-226).
    🆕 D-250 — 수집 팀원은 `CopyLane_raw_inbox` 도 찾아 적고, `--device` 로 기기 이름을 적습니다.
    """
    args = [sys.executable, "-m", "scripts.data_store", "setup"]
    if role:
        args += ["--role", role]
    if store:
        args += ["--store", store]
    if inbox:
        args += ["--inbox", inbox]
    if device:
        args += ["--device", device]
    if mirror:
        args += ["--mirror", mirror]
    if yes:
        args.append("--yes")
    raise typer.Exit(run(*args))


@app.command(name="data-publish")
def data_publish(
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 올릴지만 보여 준다"),
) -> None:
    """정본의 생성물을 공유 저장소에 올립니다 — 클론 B 전용.

    🆕 2026-09-19 (D-247). 올리기 전에 셋을 봅니다 — 원장 최신 · 마스킹 잔여 0 ·
       재배포 제약 소스 0. **원문캐시는 올리지 않습니다** (D-244 · D-17).
    🚨 외부 전송입니다 (제3자 계정 · D-78 ③) — 한 번 묻습니다.
    🚨 올린 뒤 `data/derived_manifest.jsonl` 을 커밋·push 해야 사본이 받습니다.
    """
    args = [sys.executable, "-m", "scripts.data_store", "publish"]
    if yes:
        args.append("--yes")
    if dry_run:
        args.append("--dry-run")
    raise typer.Exit(run(*args))


@app.command(name="raw-publish")
def raw_publish(
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 올릴지만 보여 준다"),
) -> None:
    """수집 팀원 — 이 기기가 받은 원문을 원문 받은편지함에 올립니다.

    🆕 2026-09-20 (D-250). 올리는 것은 **이 기기 디스크에 있고 원장에 있는 원문** 중 받은편지함에 없는 것입니다.
       (기기 별칭이 바뀌어도 안 올린 원문이 빠지지 않습니다.) 정본은 쓰지 않습니다.
    🚨 막는 것 — 키가 섞인 원문 · 원장과 바이트가 다른 원문 · 재배포 제약 원천 · `data/raw` 밖 경로.
    🚨 올린 뒤 `data/manifest.jsonl` 을 **자기 브랜치에** 커밋·push 하고 팀장에게 알립니다.
    """
    args = [sys.executable, "-m", "scripts.raw_inbox", "publish"]
    if yes:
        args.append("--yes")
    if dry_run:
        args.append("--dry-run")
    raise typer.Exit(run(*args))


@app.command(name="raw-import")
def raw_import(
    branch: str = typer.Option("", "--from", help="병합 **전** — 이 브랜치 원장으로 검사만"),
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 놓을지만 보여 준다"),
) -> None:
    """정본 — 팀원이 받은 원문을 받은편지함에서 꺼내 제자리에 놓습니다.

    🆕 2026-09-20 (D-250). 순서 — ① `git fetch` → `raw-import --from origin/<팀원 브랜치>` (검사)
       ② 검토·병합 ③ `raw-import` (놓기) ④ 파생물 재생성 → `data-publish`.
    🚨 바이트가 원장의 sha 와 안 맞거나 키가 섞였으면 **하나도 놓지 않습니다.** 덮어쓰지 않습니다.
    """
    args = [sys.executable, "-m", "scripts.raw_inbox", "import"]
    if branch:
        args += ["--from", branch]
    if yes:
        args.append("--yes")
    if dry_run:
        args.append("--dry-run")
    raise typer.Exit(run(*args))


@app.command(name="raw-mirror-publish")
def raw_mirror_publish(
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 올릴지만 보여 준다"),
) -> None:
    """정본 — 디스크의 원문을 팀장 전용 원문 거울에 올립니다 (읽기용).

    🆕 2026-09-21 (D-256). 원장 경로 중 **디스크에 실제로 있는 원문**을 sha 이름으로 올리고, 그 순간의 목록을 새로 씁니다.
    🚨 G2 · 재배포 제약(AI Hub 포함) · 레지스트리에 없는 원천은 올리지 않습니다. 키가 섞인 원문이 있으면 하나도 안 올립니다.
    🚨 거울은 **팀장 계정에만** 공유합니다 — 원문은 마스킹 전입니다.
    """
    args = [sys.executable, "-m", "scripts.raw_mirror", "publish"]
    if yes:
        args.append("--yes")
    if dry_run:
        args.append("--dry-run")
    raise typer.Exit(run(*args))


@app.command(name="raw-mirror-sync")
def raw_mirror_sync(
    yes: bool = typer.Option(False, "--yes", help="묻지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 받을지만 보여 준다"),
) -> None:
    """사본(팀장 기기) — 원문 거울을 받아 이 기기의 원문을 정본과 같게 합니다.

    🆕 2026-09-21 (D-256). 파생물은 안 바꿉니다 — 원문은 읽기와 `extract <원천> --preview` 에만 씁니다 (D-226).
    🚨 이 기기의 옛 원문이 정본과 다르면 레포 밖 `CopyLane_backup/raw-<시각>` 에 복사해 두고 바꿉니다.
    """
    args = [sys.executable, "-m", "scripts.raw_mirror", "sync"]
    if yes:
        args.append("--yes")
    if dry_run:
        args.append("--dry-run")
    raise typer.Exit(run(*args))


@app.command(name="data-refresh")
def data_refresh(
    sources: list[str] = typer.Argument(  # noqa: B008 — typer 의 선언 방식
        None, help="다시 추출할 원천 id (여럿 가능 · 비우면 추출 없이 골든셋·원장만)"
    ),
    no_golden: bool = typer.Option(False, "--no-golden", help="골든셋을 다시 만들지 않는다"),
    dry_run: bool = typer.Option(False, "--dry-run", help="무엇을 할지만 보여 준다"),
) -> None:
    """정본 — 원문이 바뀐 뒤 파생물을 **한 번에 순서대로** 다시 만들고, 올리기 직전에서 멈춥니다.

    🆕 2026-09-20 (런처 자동화 검토 발견 3) — 사람이 외우던 순서를 명령 하나로 묶습니다.

        1 합치지 않은 팀원 원문이 없는가     raw_inbox pending   (있으면 `raw-import` 먼저)
        2 원천별 추출                        extract <id> --dump (준 원천만)
        3 골든셋                             분할 → 사전 → 주입 → 물질화
        4 파생물 원장                        derived-manifest --write
        5 올리기 전 검사 (올리지 않는다)     개인 식별 · 마스킹 잔여 · 검사 못 한 형식 · 재배포 제약

    🚨 **외부 전송(`data-publish`)과 git 은 하지 않습니다** — 끝에 칠 명령을 순서대로 보여 줍니다.
    🚨 첫 실패에서 멈추고 **몇 번째 단계인지** 말합니다. 정본(클론 B)에서만 돕니다 (D-226).
    """
    from preprocess import EXTRACTORS  # noqa: PLC0415
    from scripts import derived_manifest as dm  # noqa: PLC0415

    sources = list(sources or [])
    unknown = [s for s in sources if s not in EXTRACTORS]
    if unknown:
        console.print(
            f"  [red]모르는 원천 {unknown}[/red] — 아는 것: {', '.join(sorted(EXTRACTORS))}"
        )
        raise typer.Exit(1)

    py = ["uv", "run", "python"]
    steps: list[tuple[str, list[str]]] = [
        ("합치지 않은 팀원 원문 확인", [*py, "-m", "scripts.raw_inbox", "pending"])
    ]
    steps += [(f"추출 — {s}", [*py, "-m", EXTRACTORS[s], "--dump"]) for s in sources]
    if not no_golden:
        steps += [(f"골든셋 — {m[-1]}", [*py, *m, *extra]) for m, extra in GOLDEN_STEPS]
    steps += [
        ("파생물 원장 쓰기", [*py, "scripts/derived_manifest.py", "--write"]),
        (
            "올리기 전 검사 (올리지 않는다)",
            [*py, "-m", "scripts.data_store", "publish", "--dry-run"],
        ),
    ]
    if dry_run:
        # 🔄 2026-09-21 (전수 재검토) — ⛔ 정본 검사가 이 앞에 있어 **사본에서 미리보기도 거부**했다 —
        #    `only_canonical` 의 docstring(「보기만 하는 옵션은 막지 않는다」)과 반대였다. 미리보기는 아무것도 안 돌린다.
        for i, (label, cmd) in enumerate(steps, 1):
            console.print(f"  {i:>2}. {label}   {' '.join(cmd[3:])}", markup=False)
        console.print("\n  [yellow]⬜ --dry-run — 아무것도 돌리지 않았다[/yellow]")
        raise typer.Exit(0)
    only_canonical("data-refresh")
    for i, (label, cmd) in enumerate(steps, 1):
        console.print(f"\n[bold]{i}/{len(steps)}  {label}[/bold]")
        if run(*cmd) != 0:
            console.print(
                f"  [red]{i}번째 단계({label})에서 멈췄다[/red] — 뒤 단계는 돌리지 않았다. 위 메시지를 본다"
            )
            raise typer.Exit(1)

    carried = " ".join(["data/derived_manifest.jsonl", *dm.GIT_CARRIES])
    console.print(
        "\n  [green]파생물을 다시 만들었고 올리기 전 검사를 통과했다.[/green]\n"
        "  다음은 **사람이** 순서대로 칩니다 (외부 전송·git 은 자동으로 하지 않습니다):\n\n"
        "    uv run python launcher.py data-publish\n"
        f"    git add {carried}\n"
        '    git commit -m "파생물 재생성 — <무엇을 바꿨나>"\n'
        "    git push origin ohb\n"
        "    uv run python launcher.py load\n\n"
        "  🚨 올리기가 먼저입니다 — 원장을 먼저 push 하면 사본이 「저장소에 없음」으로 멈춥니다.\n"
        "  ★ `git status` 로 다른 변경(수집 원장 등)이 섞였는지 봅니다.",
        markup=False,
    )
    raise typer.Exit(0)


@app.command()
def status() -> None:
    """데이터 현황판을 다시 만듭니다 — 무엇을 쓰기로 했고 무엇을 안 쓰기로 했나.

    🚨 **생성물입니다.** 손으로 적으면 갈립니다 (D-54). 2026-09-03 판이 그렇게 낡았습니다.
    """
    raise typer.Exit(run("uv", "run", "python", "-m", "scripts.data_status", "--write"))


@app.command()
@needs_data
def load(
    allow_missing: bool = typer.Option(
        False,
        "--allow-missing",
        help="🚨 파생물이 없어도 0행으로 적재합니다 — **일부러** 비운 채 돌릴 때만",
    ),
) -> None:
    """파생물을 거버넌스 DB 에 적재한다.

    근거 — D-95.

    🚨 CHECK 둘을 못 지나는 소스는 **넣지 않고 이름을 냅니다** —
       2인 확인 미완 · attribution 없음. 조용히 건너뛰면 「다 들어갔다」로 읽힙니다.
    🔴 **입력이 없으면 멈춥니다** (2026-09-10 · D-72). 종전에는 빈 리스트로 삼켜서
       `document 0 · product_fact 0` 이 오류도 경고도 없이 「정상 완료」로 찍혔습니다.
    🔄 D-254 — 골든셋도 넣습니다(`golden_sample` · `scripts/load_db.py` `load_golden`).
       ⛔ 종전 「골든셋은 아직 못 넣습니다」는 옛말이었다. 파일에서 사라진 행은 `sweep_golden` 이 거둡니다.
    """
    args = ["uv", "run", "python", "-m", "scripts.load_db"]
    if allow_missing:
        args.append("--allow-missing")
    raise typer.Exit(run(*args))


@app.command()
@needs_data(
    unless="dump"
)  # 🔄 09-21 — `--dump` 는 정본 전용이라 사본에서 먼저 받을 이유가 없다(받고 나서 거부했다)
def chunk(dump: bool = typer.Option(False, "--dump", help="chunks.jsonl 을 쓴다")) -> None:
    """[P5] 조문·별표를 RAG 청크로 자릅니다 — 🚨 조문 단위입니다."""
    args = ["uv", "run", "python", "-m", "preprocess.chunk"]
    if dump:
        only_canonical("chunk --dump")
        args.append("--dump")
    raise typer.Exit(run(*args))


@app.command()
@needs_data(unless="check")
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


#: 이 기기 안에서만 받는 주소 — 이 밖이면 `serve` 가 `--allow-remote` 를 요구한다 (D-254).
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


@app.command()
def serve(
    reload: bool = typer.Option(True, "--reload/--no-reload"),
    host: str = typer.Option("127.0.0.1", "--host", help="🚨 0.0.0.0 은 사내망에 연다"),
    port: int = typer.Option(8000, "--port", help="4명이 동시에 띄우면 겹친다"),
    allow_remote: bool = typer.Option(
        False, "--allow-remote", help="🔴 인증 없이 이 기기 밖에 연다 — 알고 할 때만"
    ),
) -> None:
    """FastAPI 를 띄웁니다 — Django 를 쓰지 않습니다.

    근거 — D-42 · D-135.

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
    # 🆕 D-254 — ⛔ 종전에는 경고만 하고 열었다. 이제 `--allow-remote` 없이는 **멈춘다** (D-220).
    if host not in LOCAL_HOSTS:
        console.print(f"[red]🚨 --host {host} — 인증이 아직 없습니다 (보안점검 P1-5 · P1-7).[/red]")
        console.print("  관리자 화면과 /docs 가 그대로 열립니다. 배포는 SSH 터널로만 (P2-10).")
        if not allow_remote:
            console.print("  ⛔ 열지 않았습니다 — 알고 열려면 [bold]--allow-remote[/bold]")
            raise typer.Exit(1)
    args = ["uv", "run", "uvicorn", "app.api:app", "--host", host, "--port", str(port)]
    if reload:
        args.append("--reload")
    raise typer.Exit(run(*args))


@app.command()
@needs_raw
def extract(
    source: str = typer.Argument("", help="원천 id (비우면 표를 보여준다)"),
    dump: bool = typer.Option(False, "--dump", help="파생물을 쓴다 — 🔴 마스킹 정책이 있어야 한다"),
    sheet: int = typer.Option(0, "--sheet", help="사람이 채울 검증셋을 N건씩 만든다"),
    min_len: int = typer.Option(
        0, "--min-len", help="검증셋 문구 길이 하한 — 낱말을 빼고 문장만 (0 = 안 건다)"
    ),
    verify: bool = typer.Option(False, "--verify", help="원천의 선언과 대조만 한다"),
    preview: bool = typer.Option(
        False,
        "--preview",
        help="임시 폴더에 뽑아 지금 파생물과 맞댄다 — 파생물은 안 바꾼다 (D-256)",
    ),
) -> None:
    """받아 둔 원문에서 라벨을 뽑는다 — 원천별 전처리 모듈로 위임한다.

    🔴 `--dump` 는 마스킹 정책이 선언된 원천에서만 돕니다 (D-72 fail-closed).
    🚨 `--verify` 를 먼저 돌립니다 — 원천이 스스로 밝힌 수(목차 쪽번호·전체 건수)와 맞춰 봅니다.
    ⛔ 원천마다 받는 옵션이 다릅니다. 없는 옵션을 주면 그 모듈이 알려 줍니다.
    """
    from preprocess import EXTRACTORS  # noqa: PLC0415 — 표는 로직 쪽에 있다 (D-99)

    if not source:
        if dump or sheet or verify or preview or min_len:
            # 🔄 2026-09-21 (전수 재검토) — ⛔ 원천 없이 옵션을 주면 표만 보이고 **0** 으로 끝났다(옵션은 버려졌다)
            console.print("  [red]원천 id 가 없다[/red] — 옵션을 주려면 원천을 적는다. 표:")
            console.print(_table("전처리 추출", EXTRACTORS))
            raise typer.Exit(1)
        console.print(_table("전처리 추출", EXTRACTORS))
        raise typer.Exit(0)
    if preview:
        # 🆕 2026-09-21 (D-256) — 어느 역할에서든 돈다. 파생물은 임시 폴더에만 나온다 — 저장소를 건드리면 🔴 로 멈춘다
        # 🔄 같은 날 (전수 재검토) — `--verify` · `--min-len` 도 **말없이 버렸다** — 같이 주면 거부한다
        if dump or sheet or verify or min_len:
            console.print(
                "  [red]--preview 는 --dump · --sheet · --verify · --min-len 과 같이 쓰지 않는다[/red]"
            )
            raise typer.Exit(1)
        raise typer.Exit(run(sys.executable, "-m", "preprocess.preview", source))
    if dump or sheet:
        only_canonical(f"extract {source} " + ("--dump" if dump else "--sheet"))
    if sheet:
        # 🔴 2026-09-25 — 변경금지(ND) 소스는 라벨 시트를 만들지 않는다. 원문 그대로의 레코드(`--dump`)만 된다.
        #    ⬜ 이 자리는 런처 경로만 막는다 — 모듈을 직접 부르는 길은 파생 쪽 `registry.assert_derivable` 이 받는다.
        from collect import registry as reg  # noqa: PLC0415 — 이 파일에 `registry` 명령이 있다

        if reg.no_derivatives(source):
            console.print(
                f"  [red]{source} 는 변경금지(ND)다[/red] — 라벨 시트는 파생 데이터셋이라 만들지 않는다. "
                "원문 그대로 색인 · 인용만 된다 (D-110 · 2026-09-25 팀장 판정 (가))."
            )
            raise typer.Exit(1)
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
    🆕 D-254 — 원천을 고르면 `extract` 처럼 합치지 않은 팀원 원문부터 봅니다(`needs_raw` 와 같은 검사).
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
    # 🆕 D-254 — 계측기는 전부 `data/raw` 를 읽는다. 합치지 않은 팀원 원문이 있으면 **센 수가 모자란다** (D-250).
    #    ⬜ 표만 볼 때(위 두 갈래)는 원문을 안 읽으므로 묻지 않는다 — 그래서 데코레이터가 아니라 여기다.
    _raw_pending_or_exit()
    raise typer.Exit(run("uv", "run", "python", "-m", module, source))


#: 골든셋 네 단계 — (모듈, 쓸 때 붙이는 플래그). 🚨 `golden` 과 `data-refresh` 가 **이 표 하나**를 돈다 (D-99)
GOLDEN_STEPS: tuple[tuple[list[str], list[str]], ...] = (
    (["-m", "preprocess.split"], ["--write"]),
    (["-m", "preprocess.dictionary"], ["--dump"]),
    (["-m", "preprocess.inject"], ["--dump"]),
    (["-m", "preprocess.golden"], ["--dump"]),
)


@app.command()
def golden(
    write: bool = typer.Option(False, "--write", help="파생물을 실제로 쓴다 (기본은 보기만)"),
) -> None:
    """골든셋을 꾸린다 — **분할 → 사전 → 주입 → 물질화** 네 단계.

    🔄 D-254 — 첫 줄이 「사전 → 주입 → 분할 세 단계」였다(2026-09-09 판). 순서의 정본은 `GOLDEN_STEPS` 다.

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
    if write:
        only_canonical("golden --write")
    for mod, extra in GOLDEN_STEPS:
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


def _invoke(fn, *extra: str) -> int:
    """🔴 메뉴도 **CLI 를 거쳐** 부른다 — 경로를 하나로 (D-51 · D-99).

    `sys.executable` 을 쓰므로 이미 venv 안이고 `uv run` 을 한 번 더 타지 않는다.
    🆕 D-254 — **자식의 종료코드를 버리지 않는다.** ⛔ 종전에는 실패해도 「⏎ 계속」뿐이라
       메뉴에서는 초록과 빨강이 같아 보였다 (D-220). 메뉴로는 그대로 돌아간다.
    ⬜ 미구현 명령은 패널이 이미 말했으므로 한 번 더 빨갛게 찍지 않는다.
    """
    rc = run(sys.executable, str(ROOT / "launcher.py"), cli_name(fn), *extra)
    if rc and not getattr(fn, "_planned", False):
        console.print(
            f"\n  [red]🔴 {cli_name(fn)} 가 실패했다 — 종료코드 {rc}[/red] · 위 메시지를 본다"
        )
    return rc


#: 눌렀을 때 **위치 인자를 묻는다** — (물음, 필수인가, 보기 종류)
#: 🚨 `register` 처럼 **둘 이상**을 받는 명령이 있다. 하나만 물으면 CLI 가 거부한다.
#: 🔴 보기 종류가 있으면 **번호로 고르게 한다** — 소스 id 를 외워서 칠 이유가 없다.
#: 🔴 `_check_menu` 가 이 표를 **명령의 실제 시그니처**와 대조한다 — 위치 인자 수·필수 여부 (D-254).
ASK_ARG: dict[str, list[tuple[str, bool, str]]] = {
    "setkey": [("어떤 키를 넣을까", True, "key")],
    "admin-add": [("누구의 계정인가 (이니셜)", True, "text")],
    "probe": [("어떤 소스를 열어 볼까", False, "collect")],
    "collect": [("어떤 소스를 받을까", True, "collect")],
    "adopt": [("어떤 소스인가", True, "collect"), ("원본 이름 (확장자 없이)", True, "text")],
    "count": [("받아 온 파일이나 폴더 경로", True, "path")],
    "register": [("어떤 소스인가", True, "manual"), ("받아 온 파일이나 폴더 경로", True, "path")],
    "extract": [("어떤 원천을 추출할까", False, "extract")],
    "data-refresh": [
        ("어떤 원천을 다시 추출할까 (엔터 = 추출 없이 골든셋·원장만)", False, "extract")
    ],
    "scan": [("어떤 원천을 셀까", False, "scan")],
}

#: 값을 받는 옵션 중 **골라도 비워도 되는** 것 — (물음, 플래그, 보기 종류). 비우면 옵션을 안 붙인다.
#: 🆕 D-254 — `diagram` 이 도면 이름을 **위치 인자**로 물었는데 명령은 `--only` 만 받는다 → 메뉴에서 넣으면 반드시 실패.
ASK_OPT: dict[str, list[tuple[str, str, str]]] = {
    "diagram": [("어느 도면인가 (엔터 = 전부)", "--only", "text")],
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
    # 🆕 2026-09-21 (전수 재검토) — ⛔ 메뉴의 수집은 미리보기 단계 없이 곧장 네트워크 수집을 돌렸다(명령 설명은
    #    「첫 실행은 --dry-run」). 묻는다 — 1번(기본)은 종전처럼 받는다. 미리보기를 못 하는 수집기는 런처가 거부한다.
    "collect": [
        ("먼저 미리보기로 볼까", "--dry-run", "받는다 — 저장한다", "미리보기 — 저장하지 않는다")
    ],
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
    "data-refresh": [
        ("골든셋", "--no-golden", "다시 만든다 — 분할 포함", "건너뛴다 — 추출·원장만"),
        ("미리보기", "--dry-run", "실제로 돌린다", "무엇을 할지만 본다"),
    ],
    # 🔴 순서가 중요하다 — `--yes` 를 먼저 묻는다. 「미리보기」를 고르면 `--data` 는 뜻이 없다.
    "db-reset": [
        ("실행", "--yes", "미리보기만 — 아무것도 안 지운다", "🔴 볼륨을 지우고 다시 세운다"),
        ("데이터", "--data", "스키마와 시드까지", "파생물 재추출 → 적재 → 임베딩까지"),
    ],
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
    # 🆕 2026-09-20 — 골든셋을 다시 만들면 분할도 다시 쓴다(`golden --write` 와 같은 자리). 미리보기면 안 바뀐다
    "data-refresh": "파생물을 덮어쓴다 — 골든셋을 고르면 분할까지 (미리보기를 골랐으면 아무것도 안 바뀐다)",
    # 🆕 2026-09-12 밤 — **덮어쓰거나 지우는데 확인이 없었다.**
    "status": "데이터 현황판을 덮어쓴다 — 보기만 하는 경로가 없다",
    "sync": "사본을 다시 만들고 **MAP 에 없는 낡은 사본은 지운다**",
    "embed": "DB 를 쓰고 **선언 밖 청크를 지운다** (D-187) · 모델 2.27GB 를 받는다",
    "rebuild": "생성물 넷을 덮어쓴다 — 하나만 돌리면 두 벌이 된다",
    "diagram": "도면 PNG 를 덮어쓴다 — 원천이 있는 것만 (D-217)",
    "dmap": "build/decision_map.md 를 덮어쓴다 — 생성물이다 (D-90)",
    "db-fresh": "임시 DB `copylane_freshcheck` 를 만들었다 지운다 — 진짜 DB 는 안 건드린다",
    "db-drift": "임시 DB **둘**을 만들었다 지운다 — 진짜 DB 는 안 건드린다",
    # 🔴 이 저장소에서 **유일하게 되돌릴 수 없는** 명령이다. 이유를 두 줄로 적는다.
    "db-reset": (
        "🔴 볼륨을 지운다 — **콘솔 계정이 사라지고 비밀번호는 되살릴 수 없다** (D-66). "
        "청크·임베딩은 파생물에서 되세운다 — **이 기기에 원문이 있는 경우만**"
    ),
    "onboard": "패키지를 깔고 DB 컨테이너를 띄우고 마이그레이션을 돌린다 — 새 기기용 (D-221)",
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
    # 🚨 번호는 뒤에서 받는다 (D-162) — 「환경」 무리에 있지만 번호는 42 다
    ("42", "파생물 원장", derived_manifest),
    ("43", "판 채택", adopt),
    # 🆕 2026-09-19 (D-247) — 확인은 **스크립트가 필요할 때만** 묻는다(외부 전송 · raw 있는 기기의 덮어쓰기).
    #    ⛔ DANGER 에 또 올리면 같은 것을 두 번 묻는다 — 습관이 된 확인은 안 읽힌다.
    ("44", "데이터 받기", data_sync),
    ("45", "데이터 올리기", data_publish),
    ("46", "데이터 역할·저장소 설정", data_setup),
    # 🆕 2026-09-20 (D-250) — 팀원 수집 원문. 올리기는 수집 팀원, 합치기는 정본
    ("47", "원문 올리기 (수집 팀원)", raw_publish),
    ("48", "원문 합치기 (정본)", raw_import),
    # 🆕 2026-09-20 — 정본의 재생성 순서를 한 번에 (외부 전송·git 앞에서 멈춘다)
    ("49", "파생물 다시 만들기 (정본)", data_refresh),
    # 🆕 2026-09-21 (D-256) — 정본 원문 거울 (팀장 기기 읽기용)
    ("50", "원문 거울 올리기 (정본)", raw_mirror_publish),
    ("51", "원문 거울 받기 (팀장 사본)", raw_mirror_sync),
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
    ("40", "스키마 선언 ↔ 실제 대조", db_drift),
    ("41", "DB 를 처음부터 다시", db_reset),
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
    # 🆕 D-254 — `--help` 용 미구현 표는 떼어 낸다. 메뉴에는 「미구현」 표가 따로 있다(`_draw`).
    first = first.removeprefix(STUB_TAG).strip()
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
    asked = sorted(
        set(ASK_ARG) | set(ASK_OPT) | set(ASK_VALUE) | set(ASK_FLAG) | set(DANGER) | set(DANGER_IF)
    )
    missing = [n for n in asked if n not in names]
    if missing:
        raise SystemExit(f"🔴 메뉴에 없는 명령을 묻고 있다: {missing}")
    drift = _ask_drift()
    if drift:
        raise SystemExit("🔴 메뉴가 묻는 것과 명령이 받는 것이 다르다:\n  " + "\n  ".join(drift))


def _ask_drift() -> list[str]:
    """🆕 D-254 — 묻는 표(ASK_*)를 **명령의 실제 시그니처**와 대조한다. 어긋난 줄을 돌려준다.

    ⛔ `diagram` 이 도면 이름을 위치 인자로 물었는데 명령은 `--only` 만 받았다 — 메뉴에서 넣으면
       **위험 확인을 받은 뒤에** 반드시 실패했다. 표를 손으로 고쳐도 여기서 걸린다.
    본다 — 위치 인자 수 · 필수 여부(메뉴가 비워도 되는데 명령이 필수면 어긋남) ·
           옵션 이름 · 값을 받는 옵션인가 / 여부 플래그인가.
    """
    # 🚨 시그니처는 명령 객체에서 읽는다 — 여기서 다시 적지 않는다 (D-99).
    #    ⛔ `isinstance(p, click.Argument)` 는 안 된다 — typer 0.27 은 click 을 안에 따로 들고 있다(`typer._click`).
    cmds = typer.main.get_command(app).commands  # type: ignore[attr-defined]
    out: list[str] = []
    for name in sorted(set(ASK_ARG) | set(ASK_OPT) | set(ASK_VALUE) | set(ASK_FLAG)):
        cmd = cmds.get(name)
        if cmd is None:
            out.append(f"{name}: 명령이 없다")
            continue
        args = [p for p in cmd.params if p.param_type_name == "argument"]
        opts = {
            o: p
            for p in cmd.params
            if p.param_type_name == "option"
            for o in (*p.opts, *p.secondary_opts)
        }
        asked = ASK_ARG.get(name, [])
        if len(asked) > len(args):
            out.append(f"{name}: 위치 인자를 {len(asked)}개 묻는데 명령은 {len(args)}개 받는다")
        for (question, required, _kind), p in zip(asked, args, strict=False):
            if p.required and not required:
                out.append(f"{name}: 「{question}」 를 비워도 된다는데 명령은 필수다")
        valued = [(f, False) for _q, f, _k in ASK_OPT.get(name, [])]
        valued += [(f, False) for _q, f, _o in ASK_VALUE.get(name, [])]
        valued += [(f, True) for _t, f, _n, _y in ASK_FLAG.get(name, [])]
        for flag, is_flag in valued:
            p = opts.get(flag)
            if p is None:
                out.append(f"{name}: {flag} 옵션이 명령에 없다")
            elif p.is_flag != is_flag:
                what = "여부 플래그" if is_flag else "값을 받는 옵션"
                out.append(f"{name}: {flag} 를 {what}로 묻는데 명령은 다르다")
    return out


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
        # 🔄 D-254 — `.env.example` 을 정규식으로 긁던 것을 **키 이름의 정본** `collect.env.KEYS` 로 (D-99).
        #    `setkey` 가 받는 이름이 정확히 이 표다 — 메뉴 보기와 명령이 받는 것이 갈리지 않는다.
        from collect import env  # noqa: PLC0415

        return [(name, purpose) for name, (purpose, _where) in env.KEYS.items()]
    return []


#: 🔴 **`0` 은 어디서나 「뒤로」다** (2026-09-11).
#:    첫 단계에서 누르면 메뉴로, 그 뒤에서는 **이전 단계로** 돌아간다.
#:    ⛔ 종전에는 되돌아갈 길이 없었다 — `_confirm` 에서 엔터를 치면 「안 함」으로
#:       **진행**했고, 3단계짜리 `register` 는 두 번째에서 틀리면 처음부터 다시였다.
#:    ★ 개념 하나에 키 하나다. 「0 직접 입력」을 따로 두지 않는다 —
#:      번호 대신 **값을 그대로 치면** 그것이 값으로 들어간다.
BACK = object()

#: 🆕 D-254 — **보기 밖의 입력을 받지 않는** 보기 종류. 입력이 비밀일 수 있는 자리다.
CLOSED_KINDS = frozenset({"key"})


def _foot(required: bool, skip_note: str = "") -> None:
    console.print("    [cyan] 0[/cyan]  [dim]← 뒤로[/dim]")
    if not required and skip_note:
        console.print(f"    [dim] ⏎  {skip_note}[/dim]")


def _pick(
    question: str,
    options: list[tuple[str, str]],
    *,
    required: bool,
    skip_note: str = "",
    free: bool = True,
):
    """번호로 고르게 한다. `0` 또는 (필수일 때) 빈 입력은 **뒤로**.

    🚨 Rich 는 대괄호를 마크업으로 읽는다 — 물음 줄에 `[y/N]` 같은 것을 쓰면 통째로 사라진다.
       실제로 2026-09-11 에 그렇게 사라져서 무엇을 쳐야 할지 안 보였다. 여기서는 대괄호를 안 쓴다.
    🆕 D-254 — `free=False` 면 **보기 번호만** 받는다. 모르는 입력은 **되비추지 않고** 다시 묻는다.
       ⛔ `setkey` 가 「값을 그대로」 받아서, 키 **값**을 붙여 넣으면 명령 줄로 화면에 찍혔다(감사 §1-2).
    """
    console.print(f"\n  [bold]{question}[/bold]")
    for i, (value, note) in enumerate(options, 1):
        tail = f"  [dim]{escape(note)}[/dim]" if note else ""
        console.print(f"    [cyan]{i:>2}[/cyan]  {value}{tail}")
    _foot(required, skip_note)

    while True:
        raw = console.input("  번호, 또는 값을 그대로 > " if free else "  번호 > ").strip()
        if raw == "0":
            return BACK
        if not raw:
            return BACK if required else ""
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        if free:
            # 번호가 아니면 값으로 받는다 — 익숙해진 사람은 그냥 친다
            return raw
        # ⛔ 입력을 찍지 않는다 — 비밀일 수 있다
        console.print(f"  [yellow]보기 번호(1~{len(options)})만 받는다 — 다시 고른다[/yellow]")


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
    out += [("opt", s) for s in ASK_OPT.get(name, [])]
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
                    # 🔴 비밀을 받는 자리(`key`)는 보기에서만 고른다 (D-254)
                    value = _pick(
                        question,
                        _choices(source),
                        required=required,
                        skip_note=skip,
                        free=source not in CLOSED_KINDS,
                    )
                out = [value] if value and value is not BACK else ([] if value == "" else value)
            elif kind == "opt":
                question, flag, source = spec
                value = _pick(question, _choices(source), required=False, skip_note="건너뛴다")
                out = (
                    [flag, value] if value and value is not BACK else ([] if value == "" else value)
                )
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
        _invoke(fn, *extra)  # 🆕 D-254 — 실패면 종료코드를 빨갛게 찍고 메뉴로 돌아온다
        # 🚨 결과를 읽기 전에 메뉴가 다시 그려지면 안 된다.
        with contextlib.suppress(KeyboardInterrupt, EOFError):
            console.input("\n  [dim]⏎ 계속[/dim]")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """인자가 없으면 대화형 메뉴, 있으면 해당 명령을 직접 실행한다."""
    if ctx.invoked_subcommand is None:
        menu()


def _utf8_console() -> None:
    """🆕 2026-09-21 (전수 재검토) — 콘솔이 cp949 여도 죽지 않게 한다.

    ⛔ 이 파일과 스크립트들은 `—`·`🔴`·`🚨` 를 찍는데, cp949 콘솔에서는 `UnicodeEncodeError` 로 **명령이 죽었다**
       (`launcher.py --help` · `setkey 모르는이름` · `build_matrix --check` — 마지막 것은 「판정매트릭스가 어긋났다」는
       엉뚱한 안내로 나왔다). `setup.ps1` 의 `PYTHONUTF8` 가 있는 기기에서만 괜찮았다.
    ★ 이 프로세스는 utf-8 로 다시 열고, 자식 프로세스에는 `PYTHONIOENCODING` 을 물려준다
      (`scripts/gen_registry.py` · `derived_manifest._utf8_out` 과 같은 처방 — 스크립트를 직접 부를 때는 그쪽이 맡는다).
    """
    import os  # noqa: PLC0415 — 이 함수만 쓴다

    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(
                encoding="utf-8"
            )  # utf-8 은 못 찍는 글자가 없다 — 뭉개 감추지 않는다 (D-162)
    if os.environ.get("PYTHONIOENCODING", "").lower().replace("-", "") != "utf8":
        os.environ["PYTHONIOENCODING"] = "utf-8"


if __name__ == "__main__":
    _utf8_console()
    sys.exit(app())
