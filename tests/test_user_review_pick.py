"""D-348 supplement 31: selected product reaches the core.

🔄 2026-10-22 (ksr 흡수 · D-348 보충 36 결정 2 · 보충 34 결정 4) — 비회원은 적지 않는다(D-307) · 회원은 고른 품목의 판정과
   고른 뒤 답한 판정을 **새 행**으로 적는다(`save_review` · 앞 기록을 지우지 않는다). 게이트로 올렸다 — 이력은 출처 · 책임이 남는 자리다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import premise as pm
from app.contracts import JudgeResponse, Premise
from app.db import get_session
from app.routers import user

pytestmark = pytest.mark.gate


@pytest.fixture
def flow(monkeypatch):
    baseline = JudgeResponse.model_validate_json(
        (Path(__file__).parent / "fixtures/judge/35_live_cos_function.json").read_text(
            encoding="utf-8"
        )
    )
    state = SimpleNamespace(calls=[], saved=[], baseline=baseline, conditional=baseline)

    def judge(text, product=None):
        state.calls.append((text, product))
        return "ok", state.baseline if product is None else state.conditional

    monkeypatch.setattr(user, "_core_judge", judge)
    monkeypatch.setattr(user, "current_user", lambda *_: None)
    # 실제 `save_review` 처럼 비회원(`user is None`)이면 아무것도 적지 않는다 — 회원이면 (사용자, 판정들)을 남긴다
    monkeypatch.setattr(
        user.judgment_store,
        "save_review",
        lambda session, member, results: (
            state.saved.append((member, list(results))) if member is not None else None
        ),
    )
    app = FastAPI()
    app.include_router(user.router)
    app.dependency_overrides[get_session] = lambda: SimpleNamespace()
    state.client = TestClient(app)
    state.text = " ".join(s.text for s in baseline.sentences)
    return state


def post(flow, op, extra=(), path="/u/review"):
    return flow.client.post(
        path,
        content=urlencode([("text", flow.text), ("op", op), *extra]),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


@pytest.mark.parametrize("premise", list(Premise))
def test_pick_sends_selected_product_and_preserves_round_without_saving(flow, premise):
    response = post(flow, f"pick:1:{premise.value}", [("round", "2")])
    assert response.status_code == 200
    assert flow.calls[0][1] is None  # sentence id mapping remains product-free
    product = flow.calls[1][1]
    assert product == pm.product_of(premise)
    assert 'data-ui-stage="result" data-round="2"' in response.text
    assert not flow.saved


def test_collapsed_branch_displays_actual_recorded_result(flow):
    branch = next(b for b in flow.baseline.branches if b.premise is Premise.화장품)
    sent = branch.sentences[0].model_copy(update={"text": "고른 품목으로 판정한 실제 결과"})
    flow.conditional = flow.baseline.model_copy(
        update={
            "category": pm.PREMISE_CATEGORY[Premise.화장품],
            "branches": [],
            "sentences": [sent],
        }
    )
    response = post(flow, "pick:1:화장품")
    assert response.status_code == 200
    selected = response.text.split('class="rv-res rv-res-cos is-shown"', 1)[1].split(
        'class="rv-redo"', 1
    )[0]
    assert "고른 품목으로 판정한 실제 결과" in selected


def test_selected_branch_overrides_record_and_precomputed_branch(flow):
    branch = next(b for b in flow.baseline.branches if b.premise is Premise.화장품)
    chosen = branch.model_copy(
        update={
            "sentences": [branch.sentences[0].model_copy(update={"text": "서버 재판정 분기 결과"})],
            "criteria": "서버가 반환한 선택 전제의 기준",
        }
    )
    flow.conditional = flow.baseline.model_copy(update={"branches": [chosen]})
    response = post(flow, "pick:1:화장품")
    assert response.status_code == 200
    selected = response.text.split('class="rv-res rv-res-cos is-shown"', 1)[1].split(
        'class="rv-redo"', 1
    )[0]
    assert "서버 재판정 분기 결과" in selected
    assert "서버가 반환한 선택 전제의 기준" in selected


@pytest.mark.parametrize("state", ["pending", "down"])
def test_product_rejudge_failure_keeps_input_without_inventing_result(flow, monkeypatch, state):
    monkeypatch.setattr(
        user,
        "_core_judge",
        lambda text, product=None: ("ok", flow.baseline) if product is None else (state, None),
    )
    response = post(flow, "pick:1:식품")
    assert response.status_code == 200
    assert flow.text in response.text
    assert "입력한 문구는 유지돼요" in response.text
    assert 'class="rv-res rv-res-food is-shown"' not in response.text
    assert not flow.saved


@pytest.mark.parametrize("kind,stage", [("food", "food"), ("hf", "cert")])
def test_first_choice_posts_to_second_question_before_product_judgment(flow, kind, stage):
    response = post(flow, "choose:1", [("kind", kind)])
    assert response.status_code == 200
    assert f'data-ui-stage="{stage}"' in response.text
    assert len(flow.calls) == 1 and flow.calls[0][1] is None
    assert 'value="pick:1:일반식품_기능성"' in response.text


def test_missing_functional_food_branch_is_disabled(flow):
    flow.baseline = flow.baseline.model_copy(
        update={
            "branches": [
                b for b in flow.baseline.branches if b.premise is not Premise.일반식품_기능성
            ]
        }
    )
    response = post(flow, "choose:1", [("kind", "food")])
    assert response.status_code == 200
    assert 'value="pick:1:일반식품_기능성"' not in response.text
    assert 'aria-disabled="true">기능성표시식품' in response.text


def test_pick_carries_previous_answers(flow):
    sid = flow.baseline.sentences[0].sent_id
    response = post(flow, "pick:1:식품", [("prev", f"{sid}|subst:yes")])
    assert response.status_code == 200
    assert flow.calls[1][1].substs[0].text == flow.baseline.sentences[0].text
    assert f'name="prev" value="{sid}|subst:yes"' in response.text


def test_server_advances_redo_round_and_stops_at_five(flow):
    response = post(flow, "redo:1", [("round", "4")])
    assert response.status_code == 200
    assert 'data-ui-stage="type" data-round="5"' in response.text
    assert post(flow, "redo:1", [("round", "5")]).status_code == 422
    assert not flow.saved


@pytest.mark.parametrize(
    "op,extra",
    [
        ("pick:1:없는전제", []),
        ("pick:0:식품", []),
        ("pick:2:식품", []),
        ("pick:1:식품", [("round", "6")]),
        ("pick:1:식품", [("round", "²")]),
        ("choose:1", [("kind", "unknown")]),
        ("pick:1:식품", [("prev", "bad")]),
    ],
)
def test_invalid_pick_is_422(flow, op, extra):
    assert post(flow, op, extra).status_code == 422


@pytest.mark.parametrize("premise", ["", *[p.value for p in Premise]])
def test_answer_uses_selected_product_or_no_category(flow, premise):
    sid = flow.baseline.sentences[0].sent_id
    response = post(
        flow,
        "all",
        [("target", f"1:{sid}"), ("answer", "subst:yes"), ("premise", premise)],
        path="/u/review/answer",
    )
    assert response.status_code == 200
    assert flow.calls[0][1] is None
    product = flow.calls[1][1]
    assert product.category == (pm.PREMISE_CATEGORY[Premise(premise)] if premise else None)
    assert product.substs[0].text == flow.baseline.sentences[0].text
    assert not flow.saved  # 비회원


def _member_session():
    yield SimpleNamespace()


def test_member_pick_saves_selected_judgment_as_new_row(flow, monkeypatch):
    member = SimpleNamespace(id="m")
    monkeypatch.setattr(user, "current_user", lambda *_: member)
    monkeypatch.setattr(user, "get_session", _member_session)
    response = post(flow, "pick:1:화장품")
    assert response.status_code == 200
    assert len(flow.saved) == 1 and flow.saved[0][0] is member
    assert flow.saved[0][1] == [flow.conditional], "고른 품목의 판정을 그대로 적는다(새 행)"


def test_member_answer_after_pick_is_saved(flow, monkeypatch):
    member = SimpleNamespace(id="m")
    monkeypatch.setattr(user, "current_user", lambda *_: member)
    sid = flow.baseline.sentences[0].sent_id
    response = post(
        flow,
        "all",
        [("target", f"1:{sid}"), ("answer", "subst:yes"), ("premise", "화장품")],
        path="/u/review/answer",
    )
    assert response.status_code == 200
    assert len(flow.saved) == 1 and flow.saved[0][0] is member, (
        "고른 뒤 답한 판정도 적는다(보충 34 결정 4 · 종전 ksr 판은 적지 않았다)"
    )
