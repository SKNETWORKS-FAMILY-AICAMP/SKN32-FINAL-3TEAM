"""검색 탐침 질의 파일 — 자리 · 출처 (🆕 2026-09-27 · 사실원장 ㉞).

🔴 막는 것
   ① 사람이 정답을 정한 질의 파일이 **원장 밖**(`build/`)에 한 기기만 갖고 사는 것 — 09-24 W6 가 그랬다
   ② 그 파일이 `labels/*.jsonl` 로 들어가 **사람 라벨로 읽히는 것**(`preprocess/labels.py`)
   ③ 출처를 모르는 줄 · 변경금지(ND) · 재배포 제약 원천의 줄이 평가셋에 들어가 공유 저장소로 나가는 것 (D-110 · D-71)
⬜ 실명 · 실제 광고 문구는 못 잡는다 — 사람이 본다 (D-216 · D-249).
"""

from __future__ import annotations

import json

import pytest

from collect import registry
from preprocess import labels
from scripts import derived_manifest as dm
from scripts import search_probe as sp

pytestmark = pytest.mark.gate

FAKE = {
    "sources": {
        "nd_src": {"grade": "G3", "constraints": ["BY", "ND"], "redistributable": True},
        "closed": {"grade": "G3", "constraints": ["BY"], "redistributable": False},
        "open": {"grade": "G3", "constraints": ["BY"], "redistributable": True},
    }
}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_load", lambda: FAKE)


def _row(src: str | None) -> dict:
    r = {"q": "면역력이 쑥쑥", "want": ["013094:제8조제1항제1호"]}
    if src is not None:
        r["provenance"] = src
    return r


def test_기본_경로는_원천이고_사람_라벨로_읽히지_않는다() -> None:
    rel = sp.QUERIES.relative_to(dm.DERIVED).as_posix()
    assert dm.kind_of(rel)[0] == "원천", rel
    assert sp.QUERIES.parent.resolve() != (dm.ROOT / labels.DIR).resolve(), (
        "🔴 `labels/` 바로 아래면 `preprocess/labels.py` 가 사람 라벨로 읽는다 — 하위 폴더에 둔다"
    )
    assert f"data/derived/{rel}" not in dm.GIT_CARRIES  # 공개 git 이 나르지 않는다


def test_자작과_재배포_가능한_원천은_통과한다(fake: None) -> None:
    assert sp.check_rows([_row("자작"), _row("open")]) == []


@pytest.mark.parametrize(
    ("src", "why"),
    [
        (None, "provenance 가 없다"),
        ("nd_src", "변경금지"),
        ("closed", "재배포 제약"),
        ("모름", "모름"),
    ],
)
def test_출처가_없거나_막힌_원천이면_막는다(fake: None, src: str | None, why: str) -> None:
    bad = sp.check_rows([_row(src)])
    assert len(bad) == 1 and why in bad[0], bad


def test_기기의_질의_파일이_있으면_검사를_지난다() -> None:
    """🚨 파일이 없는 기기(CI · 받기 전 사본)는 건너뛴다 — 있는 기기에서만 본다."""
    if not sp.QUERIES.exists():
        pytest.skip(f"질의 파일 없음 — {sp.QUERIES} (사본은 `data-sync`)")
    rows = [json.loads(x) for x in sp.QUERIES.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows and sp.check_rows(rows) == []
