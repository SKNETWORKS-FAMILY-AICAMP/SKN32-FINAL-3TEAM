"""런처 자동화 검토 (2026-09-20) — 정본 전용 · 원문캐시 · `data-refresh` · 수집 뒤 안내 · 병합 전 요약.

팀장 — *「문제를 해결하고 자동화를 진행하되 … 사용하는 사람이 이해하고 쓰기 편하도록하되 보안문제가 생기지 않도록」*.

★ 명령은 **실제로 돌리지 않는다** — `launcher.run` 을 기록기로 바꿔 **무엇을 어떤 순서로 부르려 했는지**만 본다.
🚨 `.env` 를 읽지 않는다(`env._loaded`) — 클론 B 의 진짜 역할(canonical)이 끼면 사본 경로를 못 잰다.
"""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

import launcher
from collect import env
from scripts import derived_manifest as dm
from scripts import raw_inbox as ri

pytestmark = pytest.mark.gate


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


# ══════════════════════════════════════════════════════════
# ① 정본 전용 — D-226 1항을 코드로
# ══════════════════════════════════════════════════════════
@pytest.mark.parametrize("who", ["replica", ""])
@pytest.mark.parametrize(
    "argv",
    [
        ["golden", "--write"],
        ["extract", "mfds_casebook", "--dump"],
        ["chunk", "--dump"],
        ["adopt", "law_go_kr", "x"],
        ["data-refresh"],
    ],
)
def test_사본은_파생물을_만드는_명령에서_멈춘다(role, calls, who, argv) -> None:
    """🔴 작업공간 재현 — 사본에서 `derived-manifest --write` 가 거부 없이 원장을 썼다."""
    role(who)
    r = _cli(*argv)
    assert r.exit_code == 1, r.output
    assert "정본(클론 B)에서만" in r.output and "data-sync" in r.output, r.output
    made = [c for c in calls if "scripts.raw_inbox" not in c and "scripts.data_store" not in c]
    assert not made, f"멈췄는데 무엇을 돌렸다: {made}"


def test_보기만_하는_옵션은_사본에서도_돈다(role, calls) -> None:
    role("replica")
    assert _cli("golden").exit_code == 0
    assert any("preprocess.split" in c for c in calls)


def test_원장_쓰기는_스크립트를_직접_불러도_막힌다(role, monkeypatch, tmp_path) -> None:
    role("replica")
    out = tmp_path / "derived_manifest.jsonl"
    out.write_text("원래\n", encoding="utf-8")
    monkeypatch.setattr(dm, "OUT", out)
    monkeypatch.setattr(sys, "argv", ["dm", "--write"])
    assert dm.main() == 1
    assert out.read_text(encoding="utf-8") == "원래\n"


def test_라벨_가져오기는_정본만(role, monkeypatch) -> None:
    from scripts import label_sheet as ls

    role("replica")
    monkeypatch.setattr(sys, "argv", ["ls", "import", "x.csv", "--sheet", "y.jsonl"])
    monkeypatch.setattr(ls, "import_", lambda *a: pytest.fail("사본에서 라벨을 썼다"))
    assert ls.main() == 1


def test_정본이면_통과한다(role) -> None:
    role("canonical")
    assert dm.not_canonical("x") is None


# ══════════════════════════════════════════════════════════
# ② 원문캐시 — 마스킹 전 PDF 전문이 저장소로 나가지 않는다 (D-17 · D-78 ③)
# ══════════════════════════════════════════════════════════
def test_PDF_전문_캐시는_원문캐시다() -> None:
    """🔗 `evasion_scan.paths()` 의 캐시 폴더와 `KIND_RULES` 를 잇는다 — 한쪽만 바꾸면 여기서 걸린다 (D-99)."""
    from preprocess import evasion_scan

    text_dir = evasion_scan.paths("mfds_casebook")[3]
    rel = (text_dir / "a.txt").relative_to("data/derived").as_posix()
    assert dm.kind_of(rel)[0] == "원문캐시", rel
    assert not dm.moved(rel, "원문캐시")


def test_검사가_못_읽는_형식은_올리지_않는다() -> None:
    rows = [
        {"경로": "x/a.jsonl", "부류": "생성물"},
        {"경로": "x/b.txt", "부류": "생성물"},  # 규칙에 안 걸린 새 캐시가 생겼다고 치자
        {"경로": "x/text/c.txt", "부류": "원문캐시"},  # 옮기지 않으니 상관없다
    ]
    assert dm.unscanned(rows) == ["x/b.txt"]


# ══════════════════════════════════════════════════════════
# ③ data-refresh — 순서를 사람이 외우지 않는다
# ══════════════════════════════════════════════════════════
def test_모르는_원천이면_아무것도_안_돌린다(role, calls) -> None:
    role("canonical")
    r = _cli("data-refresh", "없는_원천")
    assert r.exit_code == 1 and not calls, r.output


def test_미리보기는_단계만_보여준다(role, calls) -> None:
    role("canonical")
    r = _cli("data-refresh", "mfds_casebook", "--dry-run")
    assert r.exit_code == 0 and not calls, r.output
    assert "mfds_casebook" in r.output and "derived_manifest.py --write" in r.output


def test_순서대로_돌고_올리기_전에_멈춘다(role, calls) -> None:
    role("canonical")
    r = _cli("data-refresh", "mfds_casebook")
    assert r.exit_code == 0, r.output
    flat = [" ".join(c) for c in calls]
    order = [
        "scripts.raw_inbox pending",
        "--dump",  # 추출
        "preprocess.split --write",
        "preprocess.golden --dump",
        "derived_manifest.py --write",
        "data_store publish --dry-run",
    ]
    pos = [next(i for i, f in enumerate(flat) if key in f) for key in order]
    assert pos == sorted(pos), flat
    assert not any("publish" in f and "--dry-run" not in f for f in flat), "실제로 올렸다"
    assert not any(f.startswith("git") for f in flat), "git 을 돌렸다"
    out = r.output
    assert out.index("data-publish") < out.index("git add"), "올리기가 먼저여야 한다"


def test_중간에_실패하면_몇_번째인지_말하고_멈춘다(role, monkeypatch) -> None:
    role("canonical")
    got: list[tuple[str, ...]] = []

    def fake(*a: str) -> int:
        got.append(a)
        return 1 if "preprocess.split" in a else 0

    monkeypatch.setattr(launcher, "run", fake)
    r = _cli("data-refresh")
    assert r.exit_code == 1 and "2번째 단계" in r.output, r.output
    assert not any("derived_manifest.py" in " ".join(c) for c in got)


def test_골든셋을_건너뛸_수_있다(role, calls) -> None:
    role("canonical")
    assert _cli("data-refresh", "--no-golden").exit_code == 0
    assert not any("preprocess.split" in c for c in calls)


# ══════════════════════════════════════════════════════════
# ⑤ 수집 뒤 안내 · 병합 전 요약
# ══════════════════════════════════════════════════════════
def test_수집이_끝나면_역할에_맞는_다음_단계를_보여준다(role, calls, monkeypatch) -> None:
    from collect import store

    monkeypatch.setenv("DATA_DEVICE", "collector-1")
    monkeypatch.setattr(store, "recent_by_others", lambda s, **k: {})
    role("replica")
    r = _cli("collect", "law_go_kr")
    assert r.exit_code == 0 and "raw-publish" in r.output and "자기 브랜치" in r.output, r.output
    role("canonical")
    r = _cli("collect", "law_go_kr")
    assert "data-refresh" in r.output and "raw-publish" not in r.output, r.output


def test_병합_전_요약은_원천_기기별로_센다() -> None:
    rows = [
        {"source_id": "law_go_kr", "device": "c1", "path": "src/law/a.xml", "bytes": 1024},
        {
            "source_id": "law_go_kr",
            "device": "c1",
            "path": "src/law/b__c20260920.xml",
            "bytes": 1024,
        },
        {"source_id": "mfds_press", "device": "c2", "path": "src/p/c.json", "bytes": 0},
    ]
    got = ri.summary(rows)
    assert len(got) == 2
    assert "law_go_kr" in got[0] and "2개" in got[0] and "새 판    1" in got[0], got
    assert all("a.xml" not in x for x in got), "파일 이름·내용은 요약에 안 낸다"


def test_메뉴에서_부를_수_있다() -> None:
    names = {launcher.cli_name(f) for _, _, f in launcher.MENU if f}
    assert "data-refresh" in names
    assert "data-refresh" in launcher.ASK_ARG and "data-refresh" in launcher.ASK_FLAG
