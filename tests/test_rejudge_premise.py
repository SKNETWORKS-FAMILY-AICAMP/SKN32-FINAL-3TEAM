"""고쳐 쓰기 재판정에 고른 전제 · 답을 넘긴다 (🆕 2026-10-21 · D-348 보충 37 결정 5 · 보충 34 결정 1).

지키는 것 — `app/routers/user.py` `_rejudge`
  ① 고른 전제가 있으면 그 전제를 입력으로(`pm.product_of` · 품목은 전제의 품목) · 없으면 원문 판정의 품목 · 둘 다 없으면 None
  ② 앞서 한 답(사실 · 실증)을 같이 넘긴다 · 답만 있고 품목이 없어도 넘긴다
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts import (
    Answer,
    Category,
    JudgeResponse,
    Premise,
    ProductContext,
    UserSubst,
)
from app.routers import user as u

pytestmark = pytest.mark.gate

_FIX = Path(__file__).parent / "fixtures/judge/02_hold_low_conf.json"


def _capture(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    res = JudgeResponse.model_validate(json.loads(_FIX.read_text(encoding="utf-8")))

    def fake(body: str, product: ProductContext | None = None):  # noqa: ANN202
        seen.append(product)
        return "ok", res

    monkeypatch.setattr(u, "_core_judge", fake)
    return seen


def test_고른_전제를_입력으로_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch)
    u._rejudge("고친 문구", "건기식_인정", "건기식")  # noqa: SLF001
    (p,) = seen
    assert p.premise is Premise.건기식_인정 and p.category is Category.건기식


def test_전제가_없으면_품목_둘_다_없으면_None(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch)
    u._rejudge("고친 문구", "", "화장품")  # noqa: SLF001
    u._rejudge("고친 문구")  # noqa: SLF001
    assert seen[0].category is Category.화장품 and seen[0].premise is None
    assert seen[1] is None


def test_앞서_한_답을_같이_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch)
    ans = [UserSubst(text="고친 문구", answer=Answer.예)]
    u._rejudge("고친 문구", "식품", "식품", substs=ans)  # noqa: SLF001
    u._rejudge("고친 문구", substs=ans)  # noqa: SLF001
    assert seen[0].premise is Premise.식품 and seen[0].substs == ans
    assert seen[1].category is None and seen[1].substs == ans
