"""파생물 원장 — 기기 사이 동등성의 게이트 (D-19 의 짝 · 2026-09-17).

팀장이 물은 것:
*"집 로컬기기에서 데이터 작업을 하면 다른 기기나 팀원들이 각자 기기에서 작업을 이어갈 수
있도록 하는건데 반드시 원천 데이터가 필요한가? 파생물만 가지고도 가능한가?"*

**된다** — 게이트 `RAW_READERS = {"collect","preprocess"}` 가 이미 그 길을 만들어 두었다.
`scripts/`·`app/`·`db/` 는 전부 파생물만 읽으므로 `golden` 아래 전부가 raw 없이 돈다.
그런데 그 길을 쓰려면 **파생물에도 원장이 있어야** 한다 — `data/manifest.jsonl` 은
raw 전용(20,395행 · derived 0행)이라 「네가 받은 파생물이 내 것과 같은가」를 물을 수 없었다.

🔴 여기서 막는 것은 하나다 — **다시 만들 수 없는 파생물이 `.gitignore` 안에 갇히는 것.**
   `data/derived/labels/오한빈.jsonl`(248행)은 사람의 판정이고 어떤 명령으로도 다시 안 나온다.
   그것이 한 기기에만 있으면 그 기기가 죽는 날 사라진다.
"""

from __future__ import annotations

import pathlib

import pytest

from scripts import derived_manifest as dm

ROOT = pathlib.Path(__file__).resolve().parent.parent
GITIGNORE = ROOT / ".gitignore"


def _ignore_lines() -> list[str]:
    return [x.strip() for x in GITIGNORE.read_text(encoding="utf-8").splitlines()]


@pytest.mark.gate
def test_원장과_사람의_판정은_gitignore_예외에_있다() -> None:
    """🚨 `data/**` 가 통째로 막혀 있어서 **예외를 명시하지 않으면 안 따라온다** (D-19).

    ⛔ 2026-09-17 까지 예외가 `data/manifest.jsonl` 하나였다. 그래서 어제 붙인 라벨 248행이
       git 에도 원장에도 없었다 — 그 기기가 죽으면 되돌릴 방법이 없는 상태였다.
    ★ 여기서 「생성물」은 일부러 요구하지 않는다. 다시 만들 수 있는 것을 커밋하면
      이력이 부풀고 D-90(생성물은 손대지 않는다)과 부딪힌다.
    """
    need = [
        "!data/derived_manifest.jsonl",
        "!data/derived/labels/**",
        "!data/derived/*_labelsheet.jsonl",
        "!data/derived/golden/split_manifest.json",
    ]
    lines = _ignore_lines()
    missing = [p for p in need if p not in lines]
    assert not missing, (
        "다시 만들 수 없는 파생물이 .gitignore 에 갇혀 있다 — 한 기기에만 남는다 (D-19). "
        f"예외를 추가한다: {missing}"
    )


@pytest.mark.gate
def test_생성물은_gitignore_예외에_없다() -> None:
    """🔴 위 검사의 반대쪽 — **예외가 넓어지는 것**을 막는다.

    `!data/derived/**` 한 줄이면 53MB 생성물이 전부 커밋 대상이 된다. 편하지만
    매 재생성이 이력에 쌓이고, 「무엇이 원천인가」가 다시 흐려진다.
    """
    bad = [x for x in _ignore_lines() if x in {"!data/derived/**", "!data/derived/*", "!data/**"}]
    assert not bad, f"예외가 파생물 전체를 열었다 — 생성물까지 커밋 대상이 된다 (D-90): {bad}"


@pytest.mark.gate
def test_모든_파생물이_부류를_가진다() -> None:
    """🔴 분류 없는 파생물이 있으면 **재배포 가부를 모르는 채로 묶음에 섞인다** (D-72).

    부류는 「만드는 코드가 있는가」로 갈린다 — 없으면 다시 만들 수 없으므로 원천이다.
    🚨 예외가 필요하면 `dm.UNWRITTEN` 에 **이름과 사유**를 적는다. 검사를 약하게 두지 않는다
       (게이트의 `RAW_EXCEPTIONS` 와 같은 자리).
    """
    if not dm.DERIVED.exists():
        pytest.skip("이 기기에 data/derived 가 없다 — 기기 축이다 (D-19)")
    rows = dm.rows()  # 미분류가 있으면 SystemExit 으로 멈춘다
    assert rows, "파생물이 0개다 — 원장을 만들 것이 없다"
    # 🔄 2026-09-17 — **부류 이름을 여기 적지 않는다** (D-99). 손으로 박아 두었다가
    #    「원문캐시」를 더하는 순간 이 게이트가 걸렸다 — 같은 사실을 두 곳에 두면 갈린다.
    #    ★ 표에서 끌어오면 부류가 늘어도 안 깨지고, **표에 없는 값**은 그대로 잡는다.
    known = {name for name, _, _ in dm.KIND_RULES} | {dm.DEFAULT_KIND}
    kinds = {str(r["부류"]) for r in rows}
    assert kinds <= known, f"KIND_RULES 에 없는 부류가 있다: {sorted(kinds - known)}"


@pytest.mark.gate
def test_원문캐시는_묶음에_들어가지_않는다() -> None:
    """🔴 **마스킹 전 원문이 묶음에 섞이는 것**을 막는다 (D-17 · D-78 ③ · 2026-09-17).

    ⛔ `data/derived/mfds_press_pdf/tables/` 는 파생물이 아니라 **PDF 표 캐시**다
       (`preprocess/mfds_press.py:165` — 「캐시가 PDF 보다 새로우면 그것을 쓴다」).
       마스킹은 그 **뒤** `--dump` 경로에서 `mfds_press_labels.jsonl` 에 적용되므로
       캐시에는 법인 표기가 그대로 있다 — 실측 105개 중 11개에 76건.
    🚨 그래서 「derived 는 마스킹을 지난 층」이 **캐시에는 참이 아니다.** 그 사실을
       부류로 박고, 캐시가 gitignore 예외에 들어오지 않는 것으로 집행한다.
    """
    cache_pats = [pat for name, pat, _ in dm.KIND_RULES if name == "원문캐시"]
    assert cache_pats, "KIND_RULES 에 원문캐시 규칙이 없다 — 캐시가 생성물로 섞인다"
    lines = _ignore_lines()
    opened = [x for x in lines if x.startswith("!") and any(p in x for p in cache_pats)]
    assert not opened, (
        f"원문캐시가 gitignore 예외로 열려 있다 — 마스킹 전 원문이 커밋된다: {opened}"
    )


@pytest.mark.gate
def test_UNWRITTEN_에_오른_것은_사유가_있다() -> None:
    """이름만 적고 사유가 없으면 다음 사람이 지울지 둘지 판단할 수 없다 (D-110)."""
    thin = [k for k, v in dm.UNWRITTEN.items() if len(v.strip()) < 20]
    assert not thin, f"UNWRITTEN 에 사유가 없다: {thin}"


def test_원장이_디스크와_같다() -> None:
    """🚨 **게이트가 아니다** — `launcher.py check` 는 gate 만 돌리므로 로컬 커밋을 막지 않는다.

    파생물을 다시 뽑으면 sha256 이 바뀌는 것이 정상이고, 그때마다 커밋이 막히면
    `--write` 를 습관적으로 눌러 원장이 뜻을 잃는다. 대신 **CI 전체 실행에서 걸린다** —
    `test_readme_drift.py` 와 같은 자리다 (D-89).
    """
    if not dm.DERIVED.exists() or not dm.OUT.exists():
        pytest.skip("파생물 또는 원장이 이 기기에 없다")
    import json

    old = {
        r["경로"]: r["sha256"]
        for r in (
            json.loads(x) for x in dm.OUT.read_text(encoding="utf-8").splitlines() if x.strip()
        )
    }
    new = {str(r["경로"]): r["sha256"] for r in dm.rows()}
    added = sorted(set(new) - set(old))
    gone = sorted(set(old) - set(new))
    changed = [k for k in sorted(set(old) & set(new)) if old[k] != new[k]]
    assert not (added or gone or changed), (
        "파생물 원장이 디스크와 다르다 — `uv run python launcher.py derived-manifest --write` "
        f"로 갱신한다. 원장에 없음 {added} · 이 기기에 없음 {gone} · sha256 다름 {changed}"
    )
