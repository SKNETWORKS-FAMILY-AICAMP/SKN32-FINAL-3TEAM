"""새 판독 판의 배치 — 학습 · 평가 · 문항 단위 (2026-10-05 · 판정기록 10-04 ① · D-316 · 원장 10-03 ㊿-18 · ㊿-19).

🔴 무엇을 막나
   ① 대기가 남은 판이 골든에 드는 것 · 평가로 갈 문항이 학습에 드는 것(문항 단위 · 화장품 지시서 §7)
   ② 평가 행 목록 없이 「문항」 판이 전량 학습으로 드는 것 · 목록이 채점 행이 아닌 것을 가리키는 것 (D-220)
   ③ 근거자료 판의 조건 L 이 적법 음성으로 드는 것 (D-301 · D-316)
   ④ 새 학습 행 때문에 봉인 평가 행이 줄어드는 것 — 겹치면 학습 쪽을 뺀다 (D-254)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from preprocess import golden, split

pytestmark = pytest.mark.gate


def _row(key: str, cond: str = "C", **more) -> dict:
    return {
        "지문": key,
        "원천": "mfds_cosmetic_faq_2020",
        "대상": "Y",
        "조건": cond,
        "labels": [],
        "근거": ["002015:제13조제1항제2호"] if cond in ("C", "A", "B") else [],
        "근거_후보": [],
        "판독": "독립판독_합의",
        "원천결손": False,
        "별표5목": "",
        "문구": f"문구 {key}",
        "문항": "Q1",
        "품목": "식품",
        "구역": "식품",
        **more,
    }


def _put(root: pathlib.Path, name: str, rows: list[dict], *, wait: int = 0, evals=None) -> None:
    d = root / name
    d.mkdir(parents=True)
    extra = [{"지문": f"wait:{i}"} for i in range(wait)]
    lines = [{"지문": r["지문"]} for r in rows] + extra
    (d / "readings.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8"
    )
    (d / "adopted.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8"
    )
    if evals is not None:
        (d / "eval_rows.jsonl").write_text(
            "".join(json.dumps({"지문": k}, ensure_ascii=False) + "\n" for k in evals),
            encoding="utf-8",
        )


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(split, "PLACED_DIR", tmp_path)
    return tmp_path


def test_자리대로_학습과_평가로_간다(root) -> None:
    _put(root, "daegu_2013", [_row("dg:a"), _row("dg:n", 대상="N")])
    _put(root, "casebook_2021_food", [_row("cb:a")])
    train, test, stat = split.placed_docs()
    assert [d["doc_id"] for d in train] == ["dg:a"] and [d["doc_id"] for d in test] == ["cb:a"]
    assert train[0]["판"] == "daegu_2013" and train[0]["품목"] == "식품"
    assert stat == {"daegu_2013": {"학습": 1}, "casebook_2021_food": {"평가": 1}}


def test_대기가_남은_판은_들지_않는다(root) -> None:
    _put(root, "daegu_2013", [_row("dg:a")], wait=1)
    assert split.placed_docs() == ([], [], {})
    assert not [p for p in split.inputs() if "daegu_2013" in p.as_posix()]


def test_문항_판은_목록의_행만_평가로_가고_그_문항의_다른_행은_버린다(root) -> None:
    rows = [
        _row("ic:e", "A"),
        _row("ic:o", "C"),  # 같은 문항의 다른 행
        _row("ic:t", "B", 문항="Q2"),  # 다른 문항
    ]
    _put(root, "interp_ad_cosmetic", rows, evals=["ic:e"])
    train, test, stat = split.placed_docs()
    assert [d["doc_id"] for d in test] == ["ic:e"] and [d["doc_id"] for d in train] == ["ic:t"]
    assert stat["interp_ad_cosmetic"] == {"평가": 1, "뺌_평가문항의_다른행": 1, "학습": 1}
    names = [p.name for p in split.inputs() if "interp_ad_cosmetic" in p.as_posix()]
    assert names == ["adopted.jsonl", "eval_rows.jsonl"]  # 목록도 분할의 입력이다 (D-176)


def test_문항_판은_목록이_없거나_채점_행이_아니면_멈춘다(root) -> None:
    _put(root, "cosmetic_qa_old", [_row("cf:m", "M")])
    with pytest.raises(SystemExit, match="eval_rows"):
        split.placed_docs()
    (root / "cosmetic_qa_old" / "eval_rows.jsonl").write_text(
        json.dumps({"지문": "cf:m"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="채점 행이 아니다"):
        split.placed_docs()


def test_근거자료_판의_조건_L_은_들지_않는다(root) -> None:
    _put(root, "guide_evidence", [_row("ge:l", "L"), _row("ge:b", "B")])
    train, _test, stat = split.placed_docs()
    assert [d["doc_id"] for d in train] == ["ge:b"]
    assert stat["guide_evidence"] == {"뺌_조건L": 1, "학습": 1}


def test_새_학습_행이_평가와_겹치면_학습_쪽을_뺀다() -> None:
    def r(i: str, text: str, sp: str) -> dict:
        return {"id": f"{i}#0", "text": text, "split": sp}

    rows = [
        r("ftc:1", "면역력을 높여 주는 발효 홍삼", "test_sentence"),
        r("ge:same", "면역력을 높여 주는 발효 홍삼", "train"),
        r("ge:in", "면역력을 높여 주는", "train"),  # 평가 문구에 품긴다(6 자 이상)
        r("ge:short", "홍삼", "train"),  # 짧아서 포함 관계로 보지 않는다
        r("ftc:2", "면역력을 높여 주는 발효 홍삼", "train"),  # 새 판이 아니다 — 건드리지 않는다
    ]
    kept, same, inside = golden.drop_placed_overlap(rows, {"ge:same", "ge:in", "ge:short"})
    assert [x["id"] for x in kept] == ["ftc:1#0", "ge:short#0", "ftc:2#0"]
    assert (same, inside) == (1, 1)


def test_사례집_식품편은_채택본의_품목을_읽는다(root) -> None:
    """🔴 2026-10-10 (D-326) — 판 상수 「식품」이 아니다. 품목 칸이 없는 옛 채택본이면 멈춘다 (D-220)."""
    _put(root, "casebook_2021_food", [_row("cb:a"), _row("cb:b", 품목="건기식")])
    _train, test, _stat = split.placed_docs()
    assert {d["doc_id"]: d["품목"] for d in test} == {"cb:a": "식품", "cb:b": "건기식"}


@pytest.mark.parametrize("bad", [None, "", "화장품"])
def test_사례집_식품편_채택본에_품목이_없으면_멈춘다(root, bad) -> None:
    _put(root, "casebook_2021_food", [_row("cb:a", 품목=bad)])
    with pytest.raises(SystemExit, match="cbf-rebuild"):
        split.placed_docs()
