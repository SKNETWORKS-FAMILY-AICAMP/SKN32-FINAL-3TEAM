from __future__ import annotations

from fastapi.testclient import TestClient

from app import graph
from app.api import app
from app.contracts import HoldReason, Outcome, SentenceJudgment, Verdict, Violation


def test_judge_calls_build_review_and_wraps_response(monkeypatch) -> None:
    """POST /judge — 코어(`build_review`)를 불러 응답을 계약(`JudgeResponse`)으로 감싼다.

    🔄 2026-09-29 — main 병합(D-266)으로 `build_graph`가 `build_review`로 갈렸다.
       `encoder_enabled` 상태 칸과 `judged_by="kcbert-encoder-…"` 조건부는 이제 없다 —
       인코더 연결은 `encode()` 노드(현재 스텁)로 옮겨갔다.
    """
    seen: dict[str, object] = {}

    class FakeGraph:
        def invoke(self, state):  # noqa: ANN001
            seen.update(state)
            return {
                "outcome": Outcome.hold,
                "sentences": [
                    SentenceJudgment(
                        sent_id="s0",
                        text=state["text"],
                        verdict=Verdict.hold,
                        hold_reason=HoldReason.low_conf,
                        violations=[Violation.거짓_과장],
                    )
                ],
                "timings": [],
            }

    monkeypatch.setattr(graph, "build_review", lambda: FakeGraph())

    response = TestClient(app).post("/judge", json={"text": "근거 없는 과장 문구"})

    assert response.status_code == 200
    assert seen["text"] == "근거 없는 과장 문구"
    assert response.json()["outcome"] == "hold"
    assert response.json()["sentences"][0]["hold_reason"] == "low_conf"
    assert response.json()["sentences"][0]["violations"] == ["거짓_과장"]
    assert response.json()["judged_by"] == "stub-0.2.0"
