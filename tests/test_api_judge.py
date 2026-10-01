from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app import api
from app.contracts import HoldReason, Outcome, SentenceJudgment, Verdict, Violation


@contextmanager
def _conn():  # noqa: ANN202
    """DB 대역 — 라우트는 커서를 열어 그래프 `config` 로만 넘긴다."""

    class _Conn:
        def cursor(self):  # noqa: ANN202
            @contextmanager
            def cm():  # noqa: ANN202
                yield object()

            return cm()

    yield _Conn()


def test_judge_calls_build_review_and_wraps_response(monkeypatch) -> None:
    """POST /judge — 검수 그래프를 불러 응답을 계약(`JudgeResponse`)으로 감싼다.

    🔄 2026-09-29 — main 병합(D-266)으로 `build_graph`가 `build_review`로 갈렸다.
       `encoder_enabled` 상태 칸과 `judged_by="kcbert-encoder-…"` 조건부는 이제 없다 —
       인코더 연결은 `encode()` 노드(현재 스텁)로 옮겨갔다.
    🔄 2026-09-29 (ohb · ksr 병합) — 라우트는 `api._review_graph()` 로 컴파일본을 얻고 DB 커서를 `config` 로 넘긴다
       (`tests/test_judge_route.py` 가 배선을 잰다). 여기서는 **보류 문장의 사유 · 위반이 응답까지 가는지**만 본다.
       대역을 `graph.build_review` 에서 `api._review_graph` · `app.db.pg_connect` 로 옮겼다 — 종전 대역은 DB 가 없으면 503 이었다.
    """
    import app.db  # noqa: PLC0415

    seen: dict[str, object] = {}

    class FakeGraph:
        def invoke(self, state, config=None):  # noqa: ANN001
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

    monkeypatch.setattr(api, "_review_graph", lambda: FakeGraph())
    monkeypatch.setattr(app.db, "pg_connect", _conn)

    response = TestClient(api.app).post("/judge", json={"text": "근거 없는 과장 문구"})

    assert response.status_code == 200, response.text
    assert seen["text"] == "근거 없는 과장 문구"
    assert response.json()["outcome"] == "hold"
    assert response.json()["sentences"][0]["hold_reason"] == "low_conf"
    assert response.json()["sentences"][0]["violations"] == ["거짓_과장"]
    assert response.json()["judged_by"].startswith(
        "rule-"
    )  # 🔄 2026-10-01 — 인코더 전 규칙 판정(D-269)
