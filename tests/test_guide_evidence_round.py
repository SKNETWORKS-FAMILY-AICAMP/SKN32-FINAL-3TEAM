"""해설서 근거자료 제출 판 — 단위의 원천 대조 (2026-10-05 · 원장 10-03 ㊿-15).

🔴 무엇을 막나
   ① 근거자료 블록이 아닌 행(위반문구 · 수정쌍)이 이 판의 단위로 드는 것 — 원천의 뜻이 다르다
   ② 같은 행을 원천에 실린 수보다 많이 세는 것 (D-220)
"""

from __future__ import annotations

import json

import pytest

from scripts import guide_statute_round as g

K1, K2, K3 = "ge:aaaaaaaaaaaa", "ge:bbbbbbbbbbbb", "ge:cccccccccccc"


def _row(block: str, text: str, kind: str = "표시내용") -> dict:
    return {
        "표": "34",
        "블록": block,
        "제품유형": "1. 영아용 조제식",
        "원천": g.GF_SOURCE,
        "종류": kind,
        "문구": text,
    }


@pytest.fixture
def ge(tmp_path, monkeypatch):
    rows = [
        _row("근거자료", "유기농 원료 사용"),
        _row("근거자료", "유기농 원료 사용"),  # 같은 행이 두 번 실렸다
        _row("삭제", "면역력 강화", "위반문구"),
    ]
    p = tmp_path / "guide.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(g, "GF_GUIDE", p)
    monkeypatch.setattr(g.registry, "assert_derivable", lambda rows, who: None)

    def unit(k: str, text: str, kind: str = "표시내용") -> dict:
        return {"지문": k, "표": "34", "제품유형": "1. 영아용 조제식", "종류": kind, "문구": text}

    return unit


@pytest.mark.gate
def test_원천에_실린_수만큼만_단위가_된다(ge) -> None:
    src = g.ge_units([ge(K1, "유기농 원료 사용"), ge(K2, "유기농 원료 사용")])
    assert list(src) == [K1, K2] and src[K1]["원천"] == g.GF_SOURCE
    with pytest.raises(SystemExit, match="근거자료"):
        g.ge_units(
            [ge(K1, "유기농 원료 사용"), ge(K2, "유기농 원료 사용"), ge(K3, "유기농 원료 사용")]
        )


@pytest.mark.gate
def test_다른_블록의_행은_단위가_못_된다(ge) -> None:
    with pytest.raises(SystemExit, match="근거자료"):
        g.ge_units([ge(K1, "면역력 강화", "위반문구")])
    with pytest.raises(SystemExit, match="근거자료"):
        g.ge_units([ge(K1, "원천에 없는 문구")])
