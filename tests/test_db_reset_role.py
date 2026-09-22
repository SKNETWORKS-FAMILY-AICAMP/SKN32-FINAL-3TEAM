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
    # 🔄 2026-09-21 — 사본은 지우기 전에 **원장과 같은지**도 본다(`data_store.plan`). 기본은 같다
    from scripts import data_store

    monkeypatch.setattr(data_store, "ledger_missing", lambda: state.get("no_ledger"))
    monkeypatch.setattr(data_store, "plan", lambda: state.get("todo", []))

    def main(*argv: str) -> int:
        monkeypatch.setattr(sys, "argv", ["db_reset", *argv])
        return db_reset.main()

    def derived(*names: str) -> None:
        for n in names:
            if n == "law_norm":
                (tmp_path / n).mkdir(exist_ok=True)
                (tmp_path / n / "a.jsonl").write_text("{}\n", encoding="utf-8")
            else:
                (tmp_path / n).parent.mkdir(parents=True, exist_ok=True)
                (tmp_path / n).write_text("{}\n", encoding="utf-8")

    return main, derived, events, state


#: 🔄 2026-09-21 — 적재가 읽는 입력 전부 (`load_db.LOAD_INPUTS`) · 사본은 청크까지.
#:    재추출 대상(조문·별표)은 정본 테스트에서 뺀다.
LOAD = (
    "law_article.jsonl",
    "law_norm",
    "banned_terms.jsonl",
    "hf_api_labels.jsonl",
    "golden/golden.jsonl",
)
NOT_REEXTRACTED = ("banned_terms.jsonl", "hf_api_labels.jsonl", "golden/golden.jsonl")


def _destroyed(events: list[tuple[str, ...]]) -> bool:
    return any(e[:4] == ("docker", "compose", "down", "-v") for e in events)


def _launcher_cmds(events: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    return [e[2:] for e in events if len(e) > 2 and e[1].endswith("launcher.py")]


@pytest.mark.gate
def test_역할을_지우기_전에_본다(world) -> None:
    main, derived, events, _ = world
    derived(*LOAD, "chunks.jsonl")
    assert main("--yes", "--data") == 0
    first_docker = next(i for i, e in enumerate(events) if e[0] == "docker")
    assert ("role",) in events[:first_docker], "🔴 역할을 지운 뒤에 봤다"


@pytest.mark.gate
def test_사본에_받은_파생물이_없으면_지우기_전에_멈춘다(world) -> None:
    main, derived, events, _ = world
    derived(*LOAD)  # 청크가 없다
    assert main("--yes", "--data") == 1
    assert not _destroyed(events), "🔴 멈춘다고 했는데 볼륨을 지웠다"


@pytest.mark.gate
@pytest.mark.parametrize(
    "gap", [{"todo": [{"경로": "data/derived/x.jsonl"}]}, {"no_ledger": "원장 없음"}]
)
def test_사본의_파생물이_원장과_다르면_지우기_전에_멈춘다(world, gap) -> None:
    """🔴 2026-09-21 (전수 재검토) — ⛔ 비어 있지 않은지만 봐서, 옛 판이 남고 저장소에 못 닿으면 볼륨을 지운 뒤
    받기가 실패해 **빈 DB** 가 남았다. 원장과 같아야 저장소 없이도 다시 적재된다."""
    main, derived, events, state = world
    derived(*LOAD, "chunks.jsonl")
    state.update(gap)
    assert main("--yes", "--data") == 1
    assert not _destroyed(events)


@pytest.mark.gate
def test_사본은_재추출_청킹_없이_load_embed_만(world) -> None:
    main, derived, events, _ = world
    derived(*LOAD, "chunks.jsonl")
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
    derived("law_article.jsonl", "law_norm", *NOT_REEXTRACTED)
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
    derived(*LOAD, "chunks.jsonl")
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


@pytest.mark.gate
@pytest.mark.parametrize("gone", NOT_REEXTRACTED)
def test_사본은_적재_입력이_하나라도_없으면_지우기_전에_멈춘다(world, gone) -> None:
    """🔴 2026-09-21 — ⛔ 종전 사전검사는 조문·별표·청크만 봤다. `banned_terms.jsonl` 이 없으면
    볼륨을 지운 **뒤에** `load` 가 멈춰 빈 DB 가 남았다."""
    main, derived, events, _ = world
    derived(*(n for n in LOAD if n != gone), "chunks.jsonl")
    assert main("--yes", "--data") == 1
    assert not _destroyed(events), f"🔴 {gone} 가 없는데 볼륨을 지웠다"


@pytest.mark.gate
@pytest.mark.parametrize("gone", NOT_REEXTRACTED)
def test_정본도_재추출_밖의_적재_입력이_없으면_지우기_전에_멈춘다(world, gone) -> None:
    main, derived, events, state = world
    state["role"] = "canonical"
    derived("law_article.jsonl", "law_norm", *(n for n in NOT_REEXTRACTED if n != gone))
    assert main("--yes", "--data") == 1
    assert not _destroyed(events)


@pytest.mark.gate
def test_적재가_읽는_파일은_전부_사전검사_표에_있다() -> None:
    """🚨 `load_db.py` 가 새 입력을 읽게 되면 `LOAD_INPUTS` 에 오르지 않은 채 빠지지 않게 (D-99 · D-220)."""
    import re

    from scripts import load_db

    src = pathlib.Path(load_db.__file__).read_text(encoding="utf-8")
    read = set(
        re.findall(r'_jsonl\(\s*"([\w./]+\.jsonl)"', src)
    )  # 설명문의 `_jsonl("…")` 은 거른다
    read |= {"/".join(m) for m in re.findall(r'DERIVED\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"', src)}
    read |= set(re.findall(r'DERIVED\s*/\s*"([^"/]+)"\s*$', src, re.M))
    listed = {n for _, n, _ in load_db.LOAD_INPUTS}
    assert read, "🔴 대조할 입력을 못 찾았다 — 정규식이 낡았다 (반대 대조)"
    assert read <= listed, f"🔴 LOAD_INPUTS 에 없는 적재 입력: {sorted(read - listed)}"
    assert set(db_reset.REPLICA_CHECKS) >= set(db_reset.LOAD_CHECKS)
