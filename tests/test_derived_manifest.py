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
import shutil
import subprocess

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

    🔄 2026-09-19 (D-247) — **기기 역할의 표(`dm.NEED`)대로** 대조한다.
       ⛔ 종전에는 모든 기기에 151개를 요구해 **CI 에서 원리적으로 통과할 수 없었다** —
          git 이 옮기는 5개 때문에 `data/derived` 가 생겨 skip 이 안 걸리고 146개를 「없다」로 잡았다.
       ★ CI(역할 없음)는 git 이 옮기는 원천·표본만 요구하고, 생성물은 있는 것만 본다.
    """
    if not dm.OUT.exists():
        pytest.skip("파생물 원장이 이 기기에 없다")
    who = dm.role()
    d = dm.diff(who)
    assert not dm.failed(who, d), (
        f"파생물 원장이 디스크와 다르다 (역할 {who or '없음'}) — "
        f"없음 {d['missing']} · sha256 다름 {d['changed']} · 원장에 없음 {d['added']}\n"
        "  정본이면 `launcher.py derived-manifest --write` · 사본이면 `launcher.py data-sync`"
    )


@pytest.mark.gate
@pytest.mark.parametrize(
    ("who", "kind", "rule"),
    [
        (None, "생성물", "있으면"),  # CI — 5개만 요구한다
        (None, "원문캐시", "무시"),
        ("replica", "생성물", "필수"),  # 사본은 받은 뒤 전부 같아야 한다
        ("replica", "원문캐시", "무시"),  # 🔴 옮기지 않는 부류를 요구하면 사본이 영원히 빨강이다
        ("canonical", "원문캐시", "필수"),
        ("canonical", "원천", "필수"),
    ],
)
def test_역할의_표가_검토대로다(who: str | None, kind: str, rule: str) -> None:
    """🔴 표가 바뀌면 CI · 사본 · 정본의 초록불이 **다른 뜻**이 된다 (검토 2026-09-19 §11-1)."""
    assert dm.NEED[who][kind] == rule


@pytest.mark.gate
def test_모르는_역할이면_멈춘다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 오타가 조용히 「역할 없음」이 되면 클론 B 가 사본처럼 군다 (D-220)."""
    monkeypatch.setenv("DATA_ROLE", "canonnical")
    with pytest.raises(SystemExit, match="DATA_ROLE"):
        dm.role()
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert dm.role() == "replica"


# ══════════════════════════════════════════════════════════
# 수집 원장의 병합 규칙 (검토 2026-09-19 §3-a)
# ══════════════════════════════════════════════════════════
#  🚨 `data/manifest.jsonl` 은 git 이 따라가는 **append 전용** 원장이다. 클론 A·B 와 팀원이
#     pull 사이에 각자 수집하면 셋 다 파일 끝에 줄을 붙이고, git 의 기본 병합은 그것을 충돌로 본다.
#  ★ `merge=union` 은 양쪽 줄을 둘 다 남긴다. 원장 행은 서로 독립이라(한 행 = 한 파일 한 번) 순서가
#     섞여도 뜻이 안 바뀐다. ⛔ 통째로 다시 쓰는 `derived_manifest.jsonl` 에 걸면 두 판이 섞인다.


def _git() -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git 이 없다 — 병합 속성을 확인할 수 없다")
    return git


def _merge_attr(path: str) -> str:
    out = subprocess.run(
        [_git(), "-C", str(ROOT), "check-attr", "merge", "--", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if out.returncode != 0:
        pytest.skip(f"이 폴더가 git 저장소가 아니다 — {out.stderr.strip()}")
    return out.stdout.strip().rsplit(":", 1)[-1].strip()


@pytest.mark.gate
def test_수집_원장은_union_으로_병합된다() -> None:
    """🔴 git 이 **실제로 읽는 값**을 본다 — `.gitattributes` 의 글자가 아니라 (D-117).

    ⛔ 글자만 보면 경로 오타·순서 덮어쓰기(뒤 줄이 앞 줄을 이긴다)를 못 잡는다.
    """
    assert _merge_attr("data/manifest.jsonl") == "union", (
        "수집 원장에 merge=union 이 안 걸려 있다 — 두 기기가 pull 사이에 각자 수집하면 "
        "git 이 충돌로 멈춘다 (검토 2026-09-19 §3-a)"
    )
    assert _merge_attr("data/derived_manifest.jsonl") != "union", (
        "파생물 원장에 union 이 걸렸다 — 통째로 다시 쓰는 파일이라 두 판의 줄이 섞인다"
    )


def test_반대_대조_union_이_없으면_충돌하고_있으면_둘_다_남는다(tmp_path: pathlib.Path) -> None:
    """🚨 **게이트가 아니다** — 임시 저장소를 만들고 병합해 본다 (D-170 · 반대 대조).

    위 게이트가 지키는 속성이 **정말로 그 일을 하는지**를 보인다. 속성이 없으면 충돌,
    있으면 두 기기의 줄이 둘 다 남는다.
    """
    git = _git()

    def g(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [git, "-C", str(tmp_path), *args], capture_output=True, text=True, encoding="utf-8"
        )

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    g("config", "commit.gpgsign", "false")  # 전역 서명 설정이 있는 기기에서도 돈다
    g("config", "core.autocrlf", "false")
    ledger = tmp_path / "m.jsonl"
    ledger.write_text('{"r":1}\n', encoding="utf-8", newline="\n")
    g("add", ".")
    g("commit", "-qm", "base")
    g("checkout", "-qb", "clone_a")
    with ledger.open("a", encoding="utf-8", newline="\n") as f:
        f.write('{"r":"A"}\n')
    g("commit", "-qam", "A")
    g("checkout", "-q", "main")
    with ledger.open("a", encoding="utf-8", newline="\n") as f:
        f.write('{"r":"B"}\n')
    g("commit", "-qam", "B")

    assert g("merge", "-q", "clone_a", "-m", "m").returncode != 0, "속성 없이도 병합됐다"
    g("merge", "--abort")

    (tmp_path / ".gitattributes").write_text("m.jsonl merge=union\n", encoding="utf-8")
    g("add", ".gitattributes")
    g("commit", "-qm", "attr")
    assert g("merge", "-q", "clone_a", "-m", "m").returncode == 0, "union 인데 충돌했다"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert '{"r":"A"}' in lines and '{"r":"B"}' in lines, f"한쪽 줄이 사라졌다: {lines}"
