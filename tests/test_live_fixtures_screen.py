"""실제 응답 픽스처가 검수 화면에 빠짐없이 그려지는가 (🆕 2026-10-19 · E2E 의 오프라인 짝).

★ 픽스처 `tests/fixtures/judge/3x_live_*.json` 은 `scripts/e2e_review.py --save-fixtures` 가 실제 DB · 잠금 채택 인코더(D4-20)로
   받은 **화면이 받는 응답**(품목 모름)이다 — 질문(`fact_check`) · 분기 여섯이 든 꼴을 화면 담당이 DB 없이 보고 고칠 수 있게 한다.
   문구는 우리가 지은 문장이다(재배포 제한 원천 문구가 아니다).
🔴 지키는 것 — 응답에 있는 것이 화면 HTML 에 있다: 분기마다 기준 줄 · 답 칸을 그려야 하는 문장(`reasons.question_text`)의
   질문 글자 · 답 버튼 셋. 검사는 E2E 도구와 **같은 함수**다(`scripts/e2e_review.py` `_html_checks` · D-99).
일반식품_기능성 분기도 식품의 두 번째 선택에 표시한다(D-348 보충 31).
"""

from __future__ import annotations

import pathlib

import pytest

from app.contracts import JudgeResponse

pytestmark = pytest.mark.gate

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE = sorted((ROOT / "tests" / "fixtures" / "judge").glob("3*_live_*.json"))
GFF = "일반식품_기능성"


def _page_and_checks(path: pathlib.Path):  # noqa: ANN202
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from scripts import e2e_review as e2e  # noqa: PLC0415

    res = JudgeResponse.model_validate_json(path.read_text(encoding="utf-8"))
    r = TestClient(app).get(f"/u/preview/{path.stem}")
    assert r.status_code == 200, r.text[:300]
    return res, e2e._html_checks(res, r.text)


def test_실제_응답_픽스처가_있다() -> None:
    assert len(LIVE) >= 10, (
        "E2E 로 받은 실제 응답 픽스처가 없다 — `scripts/e2e_review.py --save-fixtures`"
    )
    kinds = set()
    for p in LIVE:
        res = JudgeResponse.model_validate_json(p.read_text(encoding="utf-8"))
        kinds |= {
            s.fact_check.kind.value for b in res.branches for s in b.sentences if s.fact_check
        }
    assert {"인증", "특허", "비교_기준"} <= kinds, "질문이 달린 꼴이 픽스처에 있다"


@pytest.mark.parametrize("path", LIVE, ids=lambda p: p.stem)
def test_응답에_있는_것이_화면에_있다(path: pathlib.Path) -> None:
    _, checks = _page_and_checks(path)
    bad = [c.name for c in checks if not c.ok and GFF not in c.name]
    assert not bad, bad


def test_일반식품_기능성_분기가_화면에_있다() -> None:
    bad = [c.name for p in LIVE for c in _page_and_checks(p)[1] if not c.ok and GFF in c.name]
    assert not bad, bad
