"""`preprocess/split.py --write` — 봉인 평가셋이 줄면 멈춘다 (2026-09-20 · D-254 · 감사 §2 golden).

⛔ 종전에는 옛 `split_manifest.json` 과 비교하지 않고 덮었다 — 봉인 문서가 조용히 빠지면
   옛 판과 새 판의 지표가 **다른 시험지**로 잰 수가 된다.
🔴 실데이터 없이 돈다 — `plan()` 을 가짜로 바꾼다.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

from preprocess import split


def _manifest(test_ids: list[str], train_ids: list[str] = ()) -> dict:  # type: ignore[assignment]
    assign = {k: "train" for k in train_ids} | {k: "test_sentence" for k in test_ids}
    return {
        "seed": 1,
        "split_key": "doc_id",
        "eval_target": 40,
        "sizes": {
            "train": {"문서": 0, "문구": 0},
            "test_sentence": {"문서": len(test_ids), "문구": 0},
            "사전(사례집)": {"문서": 0, "문구": 0},
        },
        "negatives": {"test_sentence": 0, "train": 0},
        "excluded_from_eval": {"다중라벨_문서": 0},
        "unit": {"test_sentence": "문장"},
        "counts": {"test_sentence": {}},
        "unmeasurable": {"test_sentence": []},
        "no_eval_at_all": [],
        "assign": assign,
    }


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "golden" / "split_manifest.json"
    monkeypatch.setattr(split, "OUT", out)

    def run(new: dict, *argv: str) -> int:
        monkeypatch.setattr(split, "plan", lambda _seed=0: new)
        monkeypatch.setattr(sys, "argv", ["split", *argv])
        return split.main()

    def seed(m: dict) -> pathlib.Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        return out

    return run, seed


@pytest.mark.gate
def test_봉인이_빠지면_쓰지_않고_멈춘다(world) -> None:
    run, seed = world
    out = seed(_manifest(["a", "b", "c"]))
    before = out.read_bytes()
    assert run(_manifest(["a", "b"]), "--write") == 1
    assert out.read_bytes() == before


@pytest.mark.gate
def test_수가_같아도_봉인_id_가_바뀌면_멈춘다(world) -> None:
    """🚨 하나 빠지고 하나 들어오면 수는 같아도 시험지가 바뀐다."""
    run, seed = world
    seed(_manifest(["a", "b", "c"]))
    assert run(_manifest(["a", "b", "d"]), "--write") == 1


def test_봉인에서_train_으로_넘어가도_빠진_것이다(world) -> None:
    run, seed = world
    seed(_manifest(["a", "b"]))
    assert run(_manifest(["a"], ["b"]), "--write") == 1


def test_더해지는_것은_막지_않는다(world) -> None:
    run, seed = world
    out = seed(_manifest(["a", "b"]))
    assert run(_manifest(["a", "b", "c"]), "--write") == 0
    assert json.loads(out.read_text(encoding="utf-8"))["assign"]["c"] == "test_sentence"


def test_allow_shrink_면_쓴다(world) -> None:
    run, seed = world
    out = seed(_manifest(["a", "b", "c"]))
    assert run(_manifest(["a"]), "--write", "--allow-shrink") == 0
    assert "b" not in json.loads(out.read_text(encoding="utf-8"))["assign"]


def test_이전_판이_없으면_쓴다(world) -> None:
    run, _seed = world
    assert run(_manifest(["a"]), "--write") == 0
