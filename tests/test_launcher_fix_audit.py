"""런처 전수 감사(2026-09-20) 고침 — D-254.

★ 명령은 **실제로 돌리지 않는다** — `launcher.run` 을 기록기로 바꿔 무엇을 어떤 순서로 부르려 했는지만 본다.
🔗 고정물(`role`·`calls`)은 `tests/test_launcher_automation.py` 와 같은 모양이다 — 픽스처를 모듈 사이에 못 나눠 둘이다.
"""

from __future__ import annotations

import re

import pytest
from rich.console import Console
from typer.testing import CliRunner

import launcher
from collect import env

pytestmark = pytest.mark.gate


@pytest.fixture(autouse=True)
def _wide(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 좁은 폭이면 Rich 가 줄을 접어 부분 문자열 대조가 흔들린다."""
    monkeypatch.setattr(launcher, "console", Console(width=400))


@pytest.fixture
def role(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(env, "_loaded", True)

    def set_(value: str) -> None:
        monkeypatch.setenv("DATA_ROLE", value)

    set_("")
    return set_


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    got: list[tuple[str, ...]] = []
    monkeypatch.setattr(launcher, "run", lambda *a: got.append(a) or 0)
    return got


def _cli(*args: str):
    return CliRunner().invoke(launcher.app, list(args))


def _inputs(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    it = iter(answers)
    monkeypatch.setattr(launcher.console, "input", lambda *_a, **_k: next(it))


SECRET = "sk-이것은-키-값이다-0123456789"


# ── 1. setkey — 비밀이 명령 줄로 찍히지 않는다 ─────────────────────────
def test_setkey_보기는_키_이름의_정본에서_온다() -> None:
    assert [k for k, _ in launcher._choices("key")] == list(env.KEYS)


def test_setkey_메뉴는_보기_밖_입력을_받지도_되비추지도_않는다(monkeypatch, capsys) -> None:
    _inputs(monkeypatch, SECRET, "1")
    assert launcher._ask(launcher.setkey) == [next(iter(env.KEYS))]
    assert SECRET not in capsys.readouterr().out


def test_자유_입력_보기는_그대로다(monkeypatch) -> None:
    """⬜ `free` 기본값은 종전과 같다 — 소스 id 를 그냥 치는 사람은 그대로 친다."""
    _inputs(monkeypatch, "mfds_casebook")
    got = launcher._pick("?", [("a", "")], required=True)
    assert got == "mfds_casebook"


def test_setkey_CLI_는_모르는_이름을_run_앞에서_멈춘다(calls) -> None:
    r = _cli("setkey", SECRET)
    assert r.exit_code == 1 and not calls, r.output
    assert SECRET not in r.output


# ── 2·3. gate · check · fmt — 명령 구성 ────────────────────────────────
def test_gate_는_건너뛴_사유를_낸다(calls) -> None:
    assert _cli("gate").exit_code == 0
    assert calls == [launcher.GATE_CMD]
    assert "-rs" in calls[0] and "-v" not in calls[0]


def test_check_는_pre_commit_순서로_ruff_를_돌고_게이트를_부른다(calls) -> None:
    assert _cli("check").exit_code == 0
    flat = [" ".join(c) for c in calls]
    assert flat[0].endswith("ruff check --fix .") and flat[1].endswith("ruff format ."), flat
    assert calls[2] == launcher.GATE_CMD


@pytest.mark.parametrize("fails", ["check", "format"])
def test_ruff_어느_단계든_실패하면_멈춘다(monkeypatch, fails) -> None:
    got: list[tuple[str, ...]] = []

    def fake(*a: str) -> int:
        got.append(a)
        return 1 if a[3] == fails else 0

    monkeypatch.setattr(launcher, "run", fake)
    assert _cli("check").exit_code == 1
    assert launcher.GATE_CMD not in got, "ruff 가 실패했는데 게이트를 돌렸다"
    assert _cli("fmt").exit_code == 1


# ── 4. registry · review — 판정매트릭스 대조가 먼저 ─────────────────────
@pytest.mark.parametrize("cmd", ["registry", "review"])
def test_생성물_하나만_도는_메뉴는_매트릭스_대조부터(calls, cmd) -> None:
    assert _cli(cmd).exit_code == 0
    assert calls[0] == launcher.MATRIX_CHECK and len(calls) > 1


@pytest.mark.parametrize("cmd", ["registry", "review"])
def test_매트릭스가_어긋나면_아무것도_안_만든다(monkeypatch, cmd) -> None:
    got: list[tuple[str, ...]] = []
    monkeypatch.setattr(launcher, "run", lambda *a: got.append(a) or 1)
    r = _cli(cmd)
    assert r.exit_code == 1 and got == [launcher.MATRIX_CHECK], r.output
    assert "rebuild" in r.output


# ── 5. 묻는 표 ↔ 명령 시그니처 ─────────────────────────────────────────
def test_메뉴가_묻는_것과_명령이_받는_것이_같다() -> None:
    assert launcher._ask_drift() == []
    launcher._check_menu()


@pytest.mark.parametrize(
    ("table", "entry", "expect"),
    [
        ("ASK_ARG", {"diagram": [("어느 도면인가", False, "text")]}, "위치 인자"),
        ("ASK_FLAG", {"serve": [("주소", "--host", "a", "b")]}, "여부 플래그"),
        ("ASK_VALUE", {"register": [("용도", "--usage", [("U1", "")])]}, "옵션이 명령에 없다"),
        ("ASK_ARG", {"register": [("소스", False, "manual"), ("경로", True, "path")]}, "필수"),
    ],
)
def test_어긋나면_게이트가_잡는다(monkeypatch, table, entry, expect) -> None:
    monkeypatch.setattr(launcher, table, {**getattr(launcher, table), **entry})
    assert any(expect in d for d in launcher._ask_drift())
    with pytest.raises(SystemExit):
        launcher._check_menu()


def test_diagram_메뉴_입력은_only_로_간다(monkeypatch) -> None:
    _inputs(monkeypatch, "p-01-competition", "2")  # 도면 이름 · 위험 확인 「실행한다」
    assert launcher._ask(launcher.diagram) == ["--only", "p-01-competition"]


# ── 6. 메뉴가 자식의 종료코드를 보인다 ──────────────────────────────────
def test_메뉴는_실패한_종료코드를_빨갛게_찍는다(monkeypatch, capsys) -> None:
    monkeypatch.setattr(launcher, "run", lambda *a: 2)
    assert launcher._invoke(launcher.gate) == 2
    assert "종료코드 2" in capsys.readouterr().out


# ── 7. 미구현 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("fn", [launcher.train, launcher.eval_, launcher.demo])
def test_미구현은_0_으로_끝나지_않는다(fn) -> None:
    name = launcher.cli_name(fn)
    assert _cli(name).exit_code == launcher.STUB_EXIT != 0
    assert launcher.STUB_TAG in _cli(name, "--help").output
    assert not launcher.summary(fn).startswith(launcher.STUB_TAG), "메뉴 설명은 표를 뗀다"


# ── 8. serve ───────────────────────────────────────────────────────────
def test_serve_는_밖으로_열려면_명시해야_한다(calls) -> None:
    r = _cli("serve", "--host", "0.0.0.0", "--no-reload")
    assert r.exit_code == 1 and not calls, r.output
    assert _cli("serve", "--host", "0.0.0.0", "--no-reload", "--allow-remote").exit_code == 0
    assert calls and "uvicorn" in calls[0]
    calls.clear()
    assert _cli("serve", "--no-reload").exit_code == 0 and calls


# ── 10. scan — 원문을 읽는 갈래만 팀원 원문을 본다 ─────────────────────
def test_scan_은_원천을_고를_때만_합치지_않은_원문을_본다(calls) -> None:
    assert _cli("scan").exit_code == 0 and not calls
    assert _cli("scan", "mfds_casebook").exit_code == 0
    assert calls[0][-2:] == ("scripts.raw_inbox", "pending")
    assert "preprocess.evasion_scan" in calls[1]


# ── 11. onboard — 역할마다 다른 안내 ────────────────────────────────────
@pytest.mark.parametrize("who", ["replica", ""])
def test_사본의_onboard_는_원문_수집과_db_reset_data_를_권하지_않는다(role, capsys, who) -> None:
    role(who)
    launcher._onboard_data_steps()
    out = capsys.readouterr().out
    assert "data-sync" in out and "--use U1" not in out and "db-reset --yes --data" not in out


def test_정본의_onboard_는_재추출_경로를_낸다(role, capsys) -> None:
    role("canonical")
    launcher._onboard_data_steps()
    assert "db-reset --yes --data" in capsys.readouterr().out


# ── 12·13. 메뉴 첫 줄 ──────────────────────────────────────────────────
def test_메뉴_첫_줄에는_D_번호가_없다() -> None:
    bad = {
        launcher.cli_name(fn): launcher.summary(fn)
        for _, _, fn in launcher.MENU
        if fn is not None and re.search(r"D-\d", launcher.summary(fn))
    }
    assert not bad, bad


def test_golden_첫_줄의_순서는_GOLDEN_STEPS_와_같다() -> None:
    names = {"split": "분할", "dictionary": "사전", "inject": "주입", "golden": "물질화"}
    want = " → ".join(names[m[-1].rsplit(".", 1)[1]] for m, _ in launcher.GOLDEN_STEPS)
    assert want in launcher.summary(launcher.golden)
