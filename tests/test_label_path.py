"""해설서 행이 **어떤 라벨로** 골든셋에 닿는가 (2026-09-17 · D-172 → 🔄 2026-09-24 D-283).

⛔ 09-17 실측 사고 — 사람이 붙인 라벨 248행이 파이프라인에 **들어갈 문이 없었다.** 그래서 문을 냈고(D-243),
   이 파일은 「붙인 라벨이 평가셋까지 닿는가」를 지켰다.
🔄 **2026-09-24 (D-283) — 그 라벨은 이제 평가에 쓰지 않는다.** 라벨링 지시서의 자체 8유형으로 붙인 것이라 조문 근거가
   없다(지시서 6·7번이 법 제8조①6·7호와 반대 · 사람끼리 α 0.32). 유형의 정본은 조문이다 (D-237 · D-282).
★ 문(`guide_docs()`)은 남긴다 — 해설서 호를 조문 원문 기준으로 붙이면 이 문으로 들어온다. 이 파일은 이제
   「조문 근거 없이 해설서 행이 평가에 들어오지 않는가」를 지킨다.
   골든셋이 없는 기기에서는 건너뛴다 — 기기 축이다 (D-19).
"""

from __future__ import annotations

import collections
import json
import pathlib

import pytest

from app.settings import PARAMS
from collect import statute
from scripts import derived_manifest as dm

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "data" / "derived" / "golden" / "golden.jsonl"
GUIDE_SRC = "mfds_special_use_guide"


def _golden() -> list[dict]:
    return [json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.gate
def test_해설서가_들어올_문은_남아_있다() -> None:
    """🔴 **문이 있는가** — 코드만 본다. 호가 붙은 해설서 행이 생기면 이 문으로 골든셋에 닿는다.

    ⛔ 문을 떼면 09-17 사고(붙인 것이 어디에도 안 닿는다)가 다시 난다.
    """
    from preprocess import golden as golden_mod
    from preprocess import split as split_mod

    assert hasattr(split_mod, "guide_docs"), (
        "split.py 에 guide_docs() 가 없다 — 해설서가 들어갈 문이 없다"
    )
    src = pathlib.Path(golden_mod.__file__).read_text(encoding="utf-8")
    assert "guide_docs()" in src, "golden.build() 가 guide_docs() 를 부르지 않는다"


@pytest.mark.gate
def test_해설서_행은_조문_근거_없이_평가에_없다() -> None:
    """🔴 해설서 행이 골든셋에 있다면 **근거 조문이 있고** 평가(test_sentence)에만 있다 (D-283 · D-172)."""
    dm.gate_guard(GOLDEN)  # 🔄 2026-09-19 — 역할대로 fail/skip · 옛 판 위에서 돌지 않는다 (F1)
    rows = [r for r in _golden() if r["provenance"] == GUIDE_SRC]
    no_basis = [r["id"] for r in rows if r["labels"] and not r.get("근거")]
    assert not no_basis, (
        f"근거 조문 없는 해설서 라벨 {len(no_basis)}행 — 사람 8유형 라벨이 새어 들었다: {no_basis[:5]}"
    )
    bad = sorted({r["split"] for r in rows} - {"test_sentence"})
    assert not bad, (
        f"해설서 행이 평가가 아닌 곳에 있다: {bad} — 평가 라벨은 사람이나 조문이 붙인다 (D-172)"
    )


@pytest.mark.gate
def test_평가_문장이_학습에_그대로_있지_않다() -> None:
    """🔴 누수. 문서 단위로 갈라도 **문구는 겹친다** — golden.build() 의 2차 필터가 그 자리다."""
    dm.gate_guard(GOLDEN)
    rows = _golden()
    train = {r["text"] for r in rows if r["split"] == "train"}
    leak = [
        r["id"]
        for r in rows
        if r["split"] == "test_sentence" and r["labels"] and r["text"] in train
    ]
    assert not leak, f"평가 문장이 학습에 그대로 있다 {len(leak)}건 — 외운 것을 맞힌다: {leak[:5]}"


@pytest.mark.gate
def test_측정_가능한_호가_줄지_않았다() -> None:
    """🚨 **되돌아가는 것**을 막는다 — 🔄 2026-09-24 (D-282) 셈 단위가 **호**다.

    ⛔ 「종전보다 나아졌다」를 코드로 못 박지 않으면 다음 갱신에서 조용히 되돌아간다.
    ★ 수를 박지 않고 **목록**을 박는다 — 어느 호가 섰는지가 사실이고, 수는 바뀐다.
    🔄 09-17 목록(거짓_과장 · 소비자_기만 · 건강기능식품_오인 · 부당_비교광고)에서 **건기식·부당비교 둘은 일부러 뺐다** —
       둘을 세운 것은 조문 근거 없는 사람 8유형 라벨이었다(D-283). 조문 근거로 선 것만 박는다.
    """
    dm.gate_guard(GOLDEN)
    stood = {
        statute.fair(1),
        statute.fair(2),
    }  # 표시광고법 제3조①1 거짓·과장 · 2 기만 — 공정위 의결서 봉인
    rows = [r for r in _golden() if r["split"] == "test_sentence"]
    by: collections.Counter = collections.Counter(
        k for r in rows for k in {statute.ho_key(c) for c in r.get("근거") or []}
    )
    lost = sorted(c for c in stood if by.get(c, 0) < PARAMS.min_measurable)
    assert not lost, (
        f"측정 가능했던 호가 {PARAMS.min_measurable}건 미만으로 떨어졌다: "
        f"{ {c: by.get(c, 0) for c in lost} } (D-40 · D-282). 라벨이 빠졌거나 분할이 갈렸다"
    )
