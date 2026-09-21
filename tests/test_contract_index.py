"""게이트 파일 ↔ `docs/00_거버넌스_집행계약.md` §1-3 색인 대조 (2026-09-21).

⛔ 집행계약이 이름을 댄 게이트 파일은 여섯이었고, `@pytest.mark.gate` 가 붙은 파일은 마흔셋이었다(2026-09-21 `grep -l`).
   「어디에 박혀 있는가」의 지도가 지도 노릇을 못 했다 — 사본(문서)이 정본(코드)을 안 따라갔다 (D-54).
★ **이름만** 본다. 설명 문구는 각 파일 머리말이 정본이다 — 산문을 검사하면 사람이 산문을 지운다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.gate

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "00_거버넌스_집행계약.md"
_NAMED = re.compile(r"tests/(test_[a-z0-9_]+\.py)")
_GATE = re.compile(r"pytest\.mark\.gate")


def gate_files(tests: pathlib.Path = ROOT / "tests") -> set[str]:
    return {p.name for p in tests.glob("test_*.py") if _GATE.search(p.read_text(encoding="utf-8"))}


def named(text: str) -> set[str]:
    return set(_NAMED.findall(text))


def test_게이트_파일은_전부_집행계약에_있다() -> None:
    missing = sorted(gate_files() - named(CONTRACT.read_text(encoding="utf-8")))
    assert not missing, (
        f"🔴 집행계약 §1-3 에 없는 게이트 파일: {missing} — 같은 커밋에 한 줄 보탠다"
    )


def test_집행계약이_대는_파일은_전부_있다() -> None:
    gone = sorted(
        n for n in named(CONTRACT.read_text(encoding="utf-8")) if not (ROOT / "tests" / n).exists()
    )
    assert not gone, f"🔴 집행계약이 대는데 없는 테스트 파일: {gone}"


def test_반대_대조_색인에서_빠진_파일을_잡는다(tmp_path: pathlib.Path) -> None:
    (tmp_path / "test_a.py").write_text("import pytest\npytestmark = pytest.mark.gate\n", "utf-8")
    (tmp_path / "test_b.py").write_text("def test_x():\n    pass\n", "utf-8")
    assert gate_files(tmp_path) == {"test_a.py"}
    assert gate_files(tmp_path) - named("`tests/test_b.py`") == {"test_a.py"}
