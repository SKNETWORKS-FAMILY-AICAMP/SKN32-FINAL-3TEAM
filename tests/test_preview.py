"""추출 미리보기 — 임시 폴더에 돌려 지금 파생물과 맞댄다 (2026-09-21 · D-256 · `preprocess/preview.py`).

★ 가짜 추출기 모듈과 임시 레포로 돈다. 진짜 원문·파생물은 안 본다.
🚨 여기서 막는 것 —
   ① 미리보기가 **저장소 파생물을 덮는 것** — 사본에서 파생물을 만드는 것과 같다 (D-226)
   ② 추출기가 경로 상수를 안 거치고 쓰는데 조용히 지나가는 것
   ③ 실제 추출기가 상수 밖(함수 안 문자열)으로 파생물을 쓰게 바뀌는 것 — 모양으로 지킨다
"""

from __future__ import annotations

import ast
import pathlib
import sys
import types

import pytest

from preprocess import preview

pytestmark = pytest.mark.gate


def _fake(monkeypatch, tmp_path: pathlib.Path, body) -> pathlib.Path:
    """가짜 레포 + `preprocess._fake_ext` 모듈 (OUT 은 상대 경로 상수 — 실제 추출기와 같은 모양)."""
    root = tmp_path / "repo"
    (root / "data" / "derived").mkdir(parents=True)
    (root / "data" / "derived" / "x.jsonl").write_text("a\nb\nc\n", encoding="utf-8")
    mod = types.ModuleType("preprocess._fake_ext")
    mod.OUT = pathlib.Path("data/derived/x.jsonl")
    mod.main = lambda: body(mod, root)
    monkeypatch.setitem(sys.modules, "preprocess._fake_ext", mod)
    monkeypatch.setattr("preprocess.EXTRACTORS", {"fake": "preprocess._fake_ext"})
    monkeypatch.setattr(preview, "ROOT", root)
    monkeypatch.chdir(
        root
    )  # 🚨 상대 경로 상수가 돌려지지 않으면 **이 임시 레포**에 떨어진다 — 진짜 레포를 안 더럽힌다
    return root


def _writes_via_constant(mod, _root) -> int:
    assert "--dump" in sys.argv
    mod.OUT.parent.mkdir(parents=True, exist_ok=True)
    mod.OUT.write_text("a\nb\nd\ne\n", encoding="utf-8")
    return 0


def test_미리보기는_저장소_파생물을_안_바꾸고_차이를_센다(tmp_path, monkeypatch, capsys) -> None:
    root = _fake(monkeypatch, tmp_path, _writes_via_constant)
    before = (root / "data/derived/x.jsonl").read_bytes()
    assert preview.run("fake") == 0
    assert (root / "data/derived/x.jsonl").read_bytes() == before, "🔴 저장소 파생물을 덮었다"
    out = capsys.readouterr().out
    assert "3 → 4줄 · 더해진 줄 2 · 빠진 줄 1" in out, out
    assert pathlib.Path("data/derived/x.jsonl") == sys.modules["preprocess._fake_ext"].OUT, (
        "상수를 되돌리지 않았다"
    )


def test_상수를_안_거치고_저장소에_쓰면_멈춘다(tmp_path, monkeypatch, capsys) -> None:
    """🔴 반대 대조 — 추출기가 경로를 함수 안에서 조립해 저장소에 쓰면 미리보기가 그것을 잡아야 한다."""

    def sneaky(_mod, root) -> int:
        (root / "data/derived/x.jsonl").write_text("overwritten\n", encoding="utf-8")
        return 0

    _fake(monkeypatch, tmp_path, sneaky)
    assert preview.run("fake") == 1
    assert "저장소 파생물을 건드렸다" in capsys.readouterr().out


def test_실제_추출기는_파생물을_상수로만_쓴다() -> None:
    """🚨 미리보기의 전제 — 모든 추출기가 `data/derived/…` 를 **모듈 수준 상수**로만 가리킨다.
    함수 안에 그 문자열이 생기면 미리보기가 저장소에 쓸 수 있다(위 반대 대조가 잡지만 먼저 여기서 막는다)."""
    from preprocess import EXTRACTORS

    root = pathlib.Path(__file__).resolve().parents[1]
    bad = []
    for mod in EXTRACTORS.values():
        tree = ast.parse((root / (mod.replace(".", "/") + ".py")).read_text(encoding="utf-8"))
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            doc = ast.get_docstring(fn, clean=False)
            for n in ast.walk(fn):
                if (
                    isinstance(n, ast.Constant)
                    and isinstance(n.value, str)
                    and "data/derived" in n.value
                    and n.value != doc
                ):
                    bad.append(f"{mod}.{fn.name}:{n.lineno}")
    assert not bad, f"🔴 함수 안에서 파생물 경로를 쓴다 — 모듈 상수로 옮긴다: {bad}"
    for mod in EXTRACTORS.values():
        m = __import__(mod, fromlist=["_"])
        assert any(
            isinstance(v, pathlib.PurePath) and preview._derived_rel(v) is not None  # noqa: SLF001
            for v in vars(m).values()
        ), f"🔴 {mod} 에 파생물 경로 상수가 없다 — 미리보기가 못 돌린다"
