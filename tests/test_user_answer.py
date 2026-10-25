"""조건부 위반에 답하기 BFF (`POST /u/review/answer` · 🆕 2026-10-16 · D-348 보충 4 결정 2 · 3 · 4 · 6).

★ 판정 코어는 가짜로 바꿔 끼운다 — DB · 모델 없이 돈다. 🔄 2026-10-18 (D-348 보충 20) 조건부 위반 문장은 **직접 만든다**(그래프에 지금 생성처가 없다 ·
   사전 쪽 경로를 걷었다) · 답으로 다시 판정하는 흐름은 인코더 쪽 판정(`wired_enc`)으로 본다.
🔴 지키는 것
   - 조건부 위반 문장 아래에 질문이 그려진다 · 확신 부족 보류에는 질문이 없다
   - 답은 **그 문장에만** 묶이고 문장 글자는 서버가 판정한 결과에서 읽는다(폼의 글자를 믿지 않는다)
   - 앞서 한 답(`prev`)을 함께 보내 이어 묻는다 · 답으로 다시 판정한 결과에 「답한 내용」이 보인다
   - 꼴이 틀린 답 · 모르는 문장은 거부한다(422 · D-220)
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from app.contracts import Answer

pytestmark = pytest.mark.gate

TEXT = "국내 판매 1위 그래놀라"


def _cond_response(product=None):  # noqa: ANN001, ANN202
    from app import graph as g  # noqa: PLC0415
    from app.contracts import (  # noqa: PLC0415
        EvidenceArticle,
        HoldReason,
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

    # 🔄 2026-10-18 (D-348 보충 20) — 종전에는 사전 확정 문장을 `doc_rules` 에 넣어 조건부 위반을 만들었다 · 그 경로를 걷어 직접 만든다
    sub = g.rs.subst_branch([Violation.거짓_과장], {"표시광고법"})
    got = SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.premise_unknown,
        violations=[Violation.거짓_과장],
        infeasibility=Infeasibility.B,
        evidence=[EvidenceArticle(law_id="002011", article="제3조", item="제1항제1호", basis=True)],
        risk=RiskAssessment(floor=Risk.R2, final=Risk.R2),
        substantiation=sub,
    )
    _ = product or ProductContext()
    return JudgeResponse(outcome=Outcome.hold, sentences=[got], category=None)


def _enc_response(product=None):  # noqa: ANN001, ANN202
    """🆕 2026-10-16 (D-348 보충 5) — 인코더만 잡은 문장(사전 근거 없음 · 인코더 하한 R1 · 식품 전제 근거)."""
    from app import graph as g  # noqa: PLC0415
    from app.contracts import (  # noqa: PLC0415
        EncoderBasis,
        EvidenceArticle,
        HoldReason,
        JudgeResponse,
        Outcome,
        Premise,
        ProductContext,
        Risk,
        RiskAssessment,
        SentenceJudgment,
        Verdict,
        Violation,
    )

    ref = EvidenceArticle(law_id="013094", article="제8조제1항제4호")
    s = SentenceJudgment(
        sent_id="s0",
        text=TEXT,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        risk=RiskAssessment(
            encoder=Risk.R1,
            final=Risk.R1,
            encoder_basis=[
                EncoderBasis(
                    premise=Premise.식품,
                    violation=Violation.거짓_과장,
                    floor=Risk.R1,
                    articles=[ref],
                )
            ],
        ),
    )
    # 원문 · 문장을 함께 준다 — 「아니오」 확정에는 문장 전체 구간이 선다(1-b · `_sentence_spans`)
    out = g.doc_rules(
        {"text": TEXT, "sents": [TEXT], "sentences": [s], "product": product or ProductContext()}
    )
    got = (out.get("sentences") or [s])[0]
    done = got.verdict is Verdict.confirmed
    outcome = (
        Outcome.guidance if done and got.violations else Outcome.passed if done else Outcome.hold
    )
    return JudgeResponse(outcome=outcome, sentences=[got], category=None)


@pytest.fixture
def wired_enc(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    from app.api import app  # noqa: PLC0415
    from app.db import get_session  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    st = SimpleNamespace(products=[])

    def fake_judge(text: str, product=None):  # noqa: ANN001, ANN202
        st.products.append(product)
        return "ok", _enc_response(product)

    monkeypatch.setattr(user_router, "_core_judge", fake_judge)
    app.dependency_overrides[get_session] = lambda: SimpleNamespace()
    yield st
    app.dependency_overrides.pop(get_session, None)


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
    assert 'value="subst:na"' in html, "해당 없음 버튼이 함께 그려진다(D-348 보충 5)"
    assert 'action="/u/review/answer"' in html


def test_답하면_그_문장에_묶어_다시_판정하고_답한_내용을_보인다(wired_enc) -> None:  # noqa: ANN001
    # 🔄 2026-10-18 (보충 20) — 답으로 다시 판정하는 쪽은 인코더 쪽 판정이다
    wired = wired_enc
    html = _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("answer", "subst:yes")],
    )
    sent = [p for p in wired.products if p is not None]
    assert sent and sent[-1].substs[0].text == TEXT and sent[-1].substs[0].answer is Answer.예
    assert "답한 내용으로 다시 판정했어요" in html and "실증 자료 있음" in html
    assert "이 표현을 실증할 자료가 있나요?" not in html, (
        "답한 문장에 같은 질문을 다시 그리지 않는다"
    )


def test_앞서_한_답을_함께_보낸다(wired) -> None:  # noqa: ANN001
    # 🔄 2026-10-24 (D-348 보충 42 결정 1) 같은 문장 · 같은 유형의 답 — 유형을 싣는다(유형 없는 둘째 실증 답은 422 · 아래)
    _post(
        "/u/review/answer",
        [
            ("text", TEXT),
            ("target", "1:s0"),
            ("prev", "s0|subst:no:거짓_과장"),
            ("answer", "subst:yes:거짓_과장"),
        ],
    )
    p = [x for x in wired.products if x is not None][-1]
    assert [u.answer for u in p.substs] == [Answer.예], "같은 문장의 앞선 답은 새 답으로 바뀐다"


def test_품목_없는_답은_계약이_받지_않는다() -> None:
    """🆕 2026-10-25 (D-348 보충 44 결정 5) — 품목을 모르면 답을 받지 않는다(그래프가 품목 보류 기록에 답을 실으려다 멈췄다 · 원장 10-24(B) ④)."""
    from pydantic import ValidationError  # noqa: PLC0415

    from app.contracts import Category, JudgeRequest, ProductContext, UserSubst  # noqa: PLC0415

    sub = UserSubst(text=TEXT, answer=Answer.예)
    with pytest.raises(ValidationError, match="품목 없이 답"):
        JudgeRequest(text=TEXT, product=ProductContext(substs=[sub]))
    assert JudgeRequest(text=TEXT, product=ProductContext(category=Category.식품, substs=[sub]))
    assert JudgeRequest(text=TEXT), "답이 없으면 품목이 없어도 받는다(첫 검수 · D-82)"


@pytest.mark.parametrize("prev", ["s0|subst:no", "s0|subst:no:거짓_과장"])
def test_같은_문장의_둘째_실증_답이_유형_없이_오면_422(wired, prev) -> None:  # noqa: ANN001
    """🆕 2026-10-24 (D-348 보충 42 결정 1) — 첫 유형의 답으로 잘못 읽히는 꼴이다 · 다시 판정해 유형을 찾지 않는다(D-220)."""
    _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("prev", prev), ("answer", "subst:yes")],
        status=422,
    )
    assert all(p is None for p in wired.products), "막은 요청으로 답 재판정을 하지 않는다"


def test_유형이_있는_답에는_미리_판정이_없다(wired_enc) -> None:  # noqa: ANN001
    """🆕 2026-10-24 (D-348 보충 42 결정 1) — 종전 `_tag_subst` 의 미리 판정(앞선 답만 넣은 판정)이 유형이 있는 답에도 돌았다 · 걷었다."""
    _post(
        "/u/review/answer",
        [
            ("text", TEXT),
            ("target", "1:s0"),
            ("prev", "s0|fact:인증:true"),
            ("answer", "subst:yes:거짓_과장"),
        ],
    )
    with_answers = [p for p in wired_enc.products if p is not None]
    assert len(with_answers) == 1, f"답을 넣은 판정은 한 번이어야 한다 — {len(with_answers)} 번"
    assert [u.violation.value for u in with_answers[0].substs] == ["거짓_과장"]


def test_인코더만_잡은_문장에도_질문이_그려지고_AI_추정으로_보인다(wired_enc) -> None:  # noqa: ANN001
    """🆕 2026-10-16 (D-348 보충 5) — 답 없이 확정하지 않는다 — 결론은 「AI 추정 · 판정 아님」, 질문 칸은 그린다."""
    html = _post("/u/judge", [("text", TEXT), ("op", "judge:1")])
    assert "AI 추정 · 판정 아님" in html and "조건부 위반 · 실증 자료가 있으면" not in html
    assert "이 표현을 실증할 자료가 있나요?" in html
    # 🔄 2026-10-22 (ksr · 보충 39 결정 6) 인코더 쪽 질문은 유형을 싣는다 — 답 값 끝에 그 유형(`subst:na:거짓_과장`)
    assert re.search(r'value="subst:na(:[^"]+)?"', html)


def test_인코더만_잡은_문장에_있음으로_답하면_특이사항_없음(wired_enc) -> None:  # noqa: ANN001
    html = _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("answer", "subst:yes")],
    )
    assert "답한 내용으로 다시 판정했어요" in html and "실증 자료 있음" in html


def test_해당_없음_답을_받는다(wired_enc) -> None:  # noqa: ANN001
    """🆕 2026-10-16 (D-348 보충 5) — `na` = 「이 문장은 그런 주장이 아니에요」 · 답 셋의 셋째. 🔄 10-18 (보충 20) 인코더 쪽 판정으로."""
    wired = wired_enc
    html = _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("answer", "subst:na")],
    )
    p = [x for x in wired.products if x is not None][-1]
    assert [u.answer for u in p.substs] == [Answer.해당없음]
    assert "답한 내용으로 다시 판정했어요" in html and "실증 자료 해당 없음" in html


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


def test_인코더만_잡은_문장에_없음으로_답하면_확정_위반_지시(wired_enc) -> None:  # noqa: ANN001
    """🆕 2026-10-17 (D-348 보충 5 결정 4 · 1-b) — 「아니오」 → 확정 위반(문장 전체 구간) · 실증 문안의 할 일."""
    html = _post(
        "/u/review/answer",
        [("text", TEXT), ("target", "1:s0"), ("answer", "subst:no")],
    )
    assert "답한 내용으로 다시 판정했어요" in html and "실증 자료 없음" in html
    assert "근거 자료가 있으면 쓸 수 있어요" in html, "확정 위반(B)의 결론 — 보류 표지가 아니다"


def test_고쳐_쓰기도_앞서_한_답으로_다시_판정한_결과를_쓴다(
    wired, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    """🆕 2026-10-19 (lse · 한빈 요청) — 사용자의 답이 판정을 바꾸므로 고쳐 쓰기도 답과 함께 판정한 결과로 고쳐 쓴다.
    ⛔ 종전에는 답 없이 다시 판정해 답하기 전 판정으로 고쳐 썼고, 다시 그린 화면에서 답이 사라졌다."""
    from app.routers import user as user_router  # noqa: PLC0415

    seen = []

    def fake_rewrite(sent, *_a, **_k):  # noqa: ANN001, ANN202 — 🔄 10-22 앞선 답(facts · substs)을 키워드로 받는다
        seen.append(sent)
        return {"no_violation": True}

    monkeypatch.setattr(user_router, "_rewrite_sentence", fake_rewrite)
    html = _post(
        "/u/review/rewrite",
        [("text", TEXT), ("target", "1:s0"), ("prev", "s0|subst:yes")],
    )
    p = [x for x in wired.products if x is not None]
    assert p and [u.answer for u in p[-1].substs] == [Answer.예], "고쳐 쓰기도 답을 판정에 넘긴다"
    assert 'name="prev" value="s0|subst:yes"' in html, "다시 그린 화면의 폼이 답을 이어 싣는다"


def test_고쳐_쓰기는_꼴이_틀린_답을_거부한다(wired) -> None:  # noqa: ANN001
    _post("/u/review/rewrite", [("text", TEXT), ("target", "1:s0"), ("prev", "s0|xx")], status=422)
