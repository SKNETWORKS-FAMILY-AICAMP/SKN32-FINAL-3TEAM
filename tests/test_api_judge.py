from __future__ import annotations

from fastapi.testclient import TestClient

from app import graph
from app.api import app
from app.contracts import HoldReason, Outcome, SentenceJudgment, Verdict, Violation


def test_judge_runs_encoder_enabled_graph(monkeypatch) -> None:
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
                "encoder_used": True,
                "attempt": 0,
                "timings": [],
            }

    monkeypatch.setattr(graph, "build_graph", lambda: FakeGraph())

    response = TestClient(app).post("/judge", json={"text": "근거 없는 과장 문구"})

    assert response.status_code == 200
    assert seen["encoder_enabled"] is True
    assert response.json()["outcome"] == "hold"
    assert response.json()["sentences"][0]["hold_reason"] == "low_conf"
    assert response.json()["sentences"][0]["violations"] == ["거짓_과장"]
    assert response.json()["judged_by"] == "kcbert-encoder-2026-09-22"
