"""사람이 붙인 라벨이 **골든셋까지 닿는가** (2026-09-17 · D-172 · D-99).

⛔ 실측 사고. `data/derived/labels/오한빈.jsonl` 248행(유형 163)을 이틀에 걸쳐 붙였는데
   파이프라인에 **들어갈 문이 없었다** —

       preprocess/split.py 의 입력   ftc_layer1_phrases · mfds_casebook_labels · mfds_hf_labels
       golden.jsonl 의 provenance    ftc 5,233 · hf_board 1,080 · casebook 313 · 해설서 **0**

   `label_merge --merge` 로 뽑아도 그 산출물을 **읽는 코드가 없었다.** 붙인 사람은
   「했다」고 보고했고 수치는 하나도 움직이지 않았다 — 「남은것」 ①의 실체다.

🚨 그래서 검사한다. **라벨이 늘었는데 평가셋이 그대로면 여기서 걸린다.**
   골든셋이 없는 기기에서는 건너뛴다 — 기기 축이다 (D-19).
"""

from __future__ import annotations

import collections
import json
import pathlib

import pytest

from app.settings import PARAMS
from preprocess import labels as label_store

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "data" / "derived" / "golden" / "golden.jsonl"
GUIDE_SRC = "mfds_special_use_guide"


def _golden() -> list[dict]:
    return [json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.gate
def test_분할과_물질화가_라벨을_입력으로_든다() -> None:
    """🔴 **문이 있는가** — 파일이 없는 기기에서도 도는 검사다 (코드만 본다).

    ⛔ 이것이 없으면 「라벨을 읽는 코드를 실수로 떼어 냈다」가 조용히 지나간다.
    """
    from preprocess import golden as golden_mod
    from preprocess import split as split_mod

    assert hasattr(split_mod, "guide_docs"), (
        "split.py 에 guide_docs() 가 없다 — 라벨이 들어갈 문이 없다"
    )
    src = pathlib.Path(golden_mod.__file__).read_text(encoding="utf-8")
    assert "guide_docs()" in src, (
        "golden.build() 가 guide_docs() 를 부르지 않는다 — 분할은 배정하는데 물질화가 버린다"
    )
    names = {p.as_posix() for p in split_mod.inputs()}
    assert any("/labels/" in n for n in names) or not label_store.files(), (
        "라벨 파일이 있는데 분할의 입력 지문에 없다 — D-176 이 그 갈림을 못 잡는다"
    )


@pytest.mark.gate
def test_붙인_라벨이_골든셋_평가에_들어가_있다() -> None:
    """🔴 붙인 수와 골든셋의 수가 맞는가. **다르면 어딘가에서 조용히 버려진 것이다.**"""
    if not GOLDEN.exists():
        pytest.skip("이 기기에 골든셋이 없다 — 기기 축이다 (D-19)")
    docs = label_store.docs()
    if not docs:
        pytest.skip("아직 붙인 라벨이 없다")
    rows = [r for r in _golden() if r["provenance"] == GUIDE_SRC]
    assert rows, (
        f"붙인 라벨 {len(docs)}건이 골든셋에 **한 행도 없다** — "
        "uv run python launcher.py golden --write 로 다시 꾸린다"
    )
    assert len(rows) == len(docs), (
        f"붙인 라벨 {len(docs)}건 중 골든셋에 {len(rows)}행만 있다 — 나머지가 버려졌다"
    )
    bad = sorted({r["split"] for r in rows} - {"test_sentence"})
    assert not bad, (
        f"사람이 붙인 라벨이 평가가 아닌 곳에 있다: {bad} — "
        "평가 라벨은 사람이나 조문이 붙인다 (D-172). 학습으로 보내면 평가할 것이 0 이 된다"
    )


@pytest.mark.gate
def test_평가_문장이_학습에_그대로_있지_않다() -> None:
    """🔴 누수. 문서 단위로 갈라도 **문구는 겹친다** — golden.build() 의 2차 필터가 그 자리다."""
    if not GOLDEN.exists():
        pytest.skip("이 기기에 골든셋이 없다")
    rows = _golden()
    train = {r["text"] for r in rows if r["split"] == "train"}
    leak = [
        r["id"]
        for r in rows
        if r["split"] == "test_sentence" and r["labels"] and r["text"] in train
    ]
    assert not leak, f"평가 문장이 학습에 그대로 있다 {len(leak)}건 — 외운 것을 맞힌다: {leak[:5]}"


@pytest.mark.gate
def test_측정_가능한_유형이_줄지_않았다() -> None:
    """🚨 **되돌아가는 것**을 막는다 — 2026-09-17 에 2종에서 4종이 됐다.

    ⛔ 「종전보다 나아졌다」를 코드로 못 박지 않으면 다음 갱신에서 조용히 되돌아간다.
    ★ 수를 박지 않고 **목록**을 박는다 — 어느 유형이 섰는지가 사실이고, 수는 바뀐다.
    """
    if not GOLDEN.exists():
        pytest.skip("이 기기에 골든셋이 없다")
    # 2026-09-17 실측으로 선 넷. 여기서 빠지면 퇴행이다.
    stood = {"거짓_과장", "소비자_기만", "건강기능식품_오인", "부당_비교광고"}
    rows = [r for r in _golden() if r["split"] == "test_sentence"]
    by: collections.Counter = collections.Counter(t for r in rows for t in r["labels"])
    lost = sorted(t for t in stood if by.get(t, 0) < PARAMS.min_measurable)
    assert not lost, (
        f"측정 가능했던 유형이 {PARAMS.min_measurable}건 미만으로 떨어졌다: "
        f"{ {t: by.get(t, 0) for t in lost} } (D-40). 라벨이 빠졌거나 분할이 갈렸다"
    )
