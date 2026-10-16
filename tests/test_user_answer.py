"""조건부 위반에 답하기 BFF (`POST /u/review/answer` · 🆕 2026-10-16 · D-348 보충 4 결정 2 · 3 · 4 · 6).

★ 판정 코어는 가짜로 바꿔 끼운다 — DB · 모델 없이 돈다. 조건부 위반 문장은 실제 조건부 판정(`graph.doc_rules`)으로 만든다.
🔴 지키는 것
   - 조건부 위반 문장 아래에 질문이 그려진다 · 확신 부족 보류에는 질문이 없다
   - 답은 **그 문장에만** 묶이고 문장 글자는 서버가 판정한 결과에서 읽는다(폼의 글자를 믿지 않는다)
   - 앞서 한 답(`prev`)을 함께 보내 이어 묻는다 · 답으로 다시 판정한 결과에 「답한 내용」이 보인다
   - 꼴이 틀린 답 · 모르는 문장은 거부한다(422 · D-220)
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

pytestmark = pytest.mark.gate

TEXT = "국내 판매 1위 그래놀라"


def _cond_response(product=None):  # noqa: ANN001, ANN202
    from app import graph as g  # noqa: PLC0415
    from app.contracts import (  # noqa: PLC0415
        EvidenceArticle,
        Infeasibility,
        JudgeResponse,
        Outcome,
        ProductContext,
        Risk,
        RiskAssessment,
        SentenceJudgment,
        Verdict,
        Violation,
    )

    s = SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.confirmed,
        violations=[Violation.거짓_과장],
        infeasibility=Infeasibility.B,
        evidence=[EvidenceArticle(law_id="002011", article="제3조", item="제1항제1호", basis=True)],
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
    )
    out = g.doc_rules({"sentences": [s], "product": product or ProductContext()})
    got = (out.get("sentences") or [s])[0]
    outcome = (
        Outcome.passed if got.verdict is Verdict.confirmed and not got.violations else Outcome.hold
    )
    return JudgeResponse(outcome=outcome, sentences=[got], category=None)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    from app.api import app  # noqa: PLC0415
    from app.db import get_session  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    st = SimpleNamespace(products=[])

    def fake_judge(text: str, product=None):  # noqa: ANN001, ANN202
        st.products.append(product)
        return "ok", _cond_response(product)

    monkeypatch.setattr(user_router, "_core_judge", fake_judge)
    app.dependency_overrides[get_session] = lambda: SimpleNamespace()
    yield st
    app.dependency_overrides.pop(get_session, None)


def _post(path: str, pairs: list[tuple[str, str]], status: int = 200) -> str:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    r = TestClient(app).post(
        path,
        content=urlencode(pairs).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == status, r.text[:300]
    return r.text


def test_조건부_위반_문장에_질문이_그려진다(wired) -> None:  # noqa: ANN001
    html = _post("/u/judge", [("text", TEXT), ("op", "judge:1")])
    assert "조건부 위반 · 실증 자료가 있으면 쓸 수 있어요" in html
    assert "이 표현을 실증할 자료가 있나요?" in html and 'value="subst:yes"' in html
    assert 'action="/u/review/answer"' in html


def test_답하면_그_문장에_묶어_다시_판정하고_답한_내용을_보인다(wired) -> None:  # noqa: ANN001
    html = _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("answer", "subst:yes")],
    )
    sent = [p for p in wired.products if p is not None]
    assert sent and sent[-1].substs[0].text == TEXT and sent[-1].substs[0].has_evidence
    assert "답한 내용으로 다시 판정했어요" in html and "실증 자료 있음" in html
    assert "이 표현을 실증할 자료가 있나요?" not in html, (
        "답한 문장에 같은 질문을 다시 그리지 않는다"
    )


def test_앞서_한_답을_함께_보낸다(wired) -> None:  # noqa: ANN001
    _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("prev", "s0|subst:no"), ("answer", "subst:yes")],
    )
    p = [x for x in wired.products if x is not None][-1]
    assert [u.has_evidence for u in p.substs] == [True], "같은 문장의 앞선 답은 새 답으로 바뀐다"


@pytest.mark.parametrize(
    "pairs",
    [
        [("text", TEXT), ("target", "1:s0"), ("answer", "subst:maybe")],
        [("text", TEXT), ("target", "1:s9"), ("answer", "subst:yes")],
        [("text", TEXT), ("target", "1:s0"), ("answer", "fact:없는종류:true")],
        [("text", TEXT), ("target", "1:s0"), ("prev", "꼴틀림"), ("answer", "subst:yes")],
    ],
)
def test_꼴이_틀린_답은_거부한다(wired, pairs) -> None:  # noqa: ANN001
    _post("/u/review/answer", pairs, status=422)
