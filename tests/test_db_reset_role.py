"""`scripts/db_reset.py --data` — 역할을 **지우기 전에** 본다 (2026-09-20 · D-254 · 감사 §1-5).

⛔ 종전에는 볼륨을 먼저 지우고 추출 모듈을 직접 불렀다 — 사본은 빈 DB, 원문 있는 사본은 반쪽 DB,
   정본은 낡은 파생물 원장이 남았다.
🔴 docker·DB·자식 프로세스 없이 돈다 — `_run` 을 기록기로 바꿔 **무엇이 어떤 순서로 불렸는지**만 본다.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from scripts import db_reset, raw_inbox


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    events: list[tuple[str, ...]] = []
    state = {"role": "replica", "pending": 0}

    def role() -> str | None:
        events.append(("role",))
        return state["role"]

    def run(*args: str) -> int:
        events.append(tuple(args))
        return 0

    def pending() -> int:
        events.append(("pending",))
        return state["pending"]

    monkeypatch.setattr(db_reset.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(db_reset, "accounts", lambda: [])
    monkeypatch.setattr(db_reset.dm, "role", role)
    monkeypatch.setattr(db_reset, "_run", run)
    monkeypatch.setattr(raw_inbox, "check_pending", pending)
    monkeypatch.setattr(db_reset, "DERIVED", tmp_path)

    def main(*argv: str) -> int:
        monkeypatch.setattr(sys, "argv", ["db_reset", *argv])
        return db_reset.main()

    def derived(*names: str) -> None:
        for n in names:
            if n == "law_norm":
                (tmp_path / n).mkdir(exist_ok=True)
                (tmp_path / n / "a.jsonl").write_text("{}\n", encoding="utf-8")
            else:
                (tmp_path / n).write_text("{}\n", encoding="utf-8")

    return main, derived, events, state


def _destroyed(events: list[tuple[str, ...]]) -> bool:
    return any(e[:4] == ("docker", "compose", "down", "-v") for e in events)


def _launcher_cmds(events: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    return [e[2:] for e in events if len(e) > 2 and e[1].endswith("launcher.py")]


@pytest.mark.gate
def test_역할을_지우기_전에_본다(world) -> None:
    main, derived, events, _ = world
    derived("law_article.jsonl", "law_norm", "chunks.jsonl")
    assert main("--yes", "--data") == 0
    first_docker = next(i for i, e in enumerate(events) if e[0] == "docker")
    assert ("role",) in events[:first_docker], "🔴 역할을 지운 뒤에 봤다"


@pytest.mark.gate
def test_사본에_받은_파생물이_없으면_지우기_전에_멈춘다(world) -> None:
    main, derived, events, _ = world
    derived("law_article.jsonl", "law_norm")  # 청크가 없다
    assert main("--yes", "--data") == 1
    assert not _destroyed(events), "🔴 멈춘다고 했는데 볼륨을 지웠다"


@pytest.mark.gate
def test_사본은_재추출_청킹_없이_load_embed_만(world) -> None:
    main, derived, events, _ = world
    derived("law_article.jsonl", "law_norm", "chunks.jsonl")
    assert main("--yes", "--data") == 0
    assert not any("preprocess.law_article" in e or "preprocess.law_norm" in e for e in events)
    assert ("load",) in _launcher_cmds(events)
    assert ("embed",) in _launcher_cmds(events)
    assert ("chunk", "--dump") not in _launcher_cmds(events)
    assert ("pending",) not in events


@pytest.mark.gate
def test_정본은_팀원_원문이_남아_있으면_지우기_전에_멈춘다(world) -> None:
    main, _derived, events, state = world
    state.update(role="canonical", pending=1)
    assert main("--yes", "--data") == 1
    assert ("pending",) in events
    assert not _destroyed(events)


def test_정본은_재추출_뒤_원장까지_같은_단계표를_탄다(world) -> None:
    main, derived, events, state = world
    state["role"] = "canonical"
    derived("law_article.jsonl", "law_norm")
    assert main("--yes", "--data") == 0
    cmds = _launcher_cmds(events)
    assert cmds[-1] == ("data-refresh", "--no-golden"), "🔴 파생물 원장을 다시 쓰지 않았다"
    assert ("chunk", "--dump") in cmds
    i_pending = events.index(("pending",))
    first_docker = next(i for i, e in enumerate(events) if e[0] == "docker")
    assert i_pending < first_docker


@pytest.mark.gate
def test_역할이_없으면_data_를_거부한다(world) -> None:
    main, derived, events, state = world
    state["role"] = None
    derived("law_article.jsonl", "law_norm", "chunks.jsonl")
    assert main("--yes", "--data") == 1
    assert not _destroyed(events)


def test_미리보기도_역할_선결을_본다(world) -> None:
    main, _derived, events, _ = world
    assert main("--data") == 1  # 사본 · 파생물 없음 — 미리보기에서도 같은 답
    assert ("role",) in events
    assert not any(e[0] == "docker" for e in events)


def test_data_없이_스키마만이면_역할과_무관하게_돈다(world) -> None:
    main, _derived, events, state = world
    state["role"] = None
    assert main("--yes") == 0
    assert _destroyed(events)
