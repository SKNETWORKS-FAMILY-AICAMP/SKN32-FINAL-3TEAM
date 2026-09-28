"""사용자 화면이 DB 없이 뜨는가 · 프론티어 축 — 🆕 2026-09-22 (ksr 병합 흡수).

★ 병합(843de72) 뒤 `/u/`(홈)·`/u/history` 가 `app.db.get_session` 에 붙었다. DB 없는 기기에서
  `test_모든_응답에_보안_헤더가_붙는다` 가 `OperationalError` 로 🔴 였다(재현 — 컨테이너, Postgres 없음).
  CI(`gate.yml`)에도 Postgres 가 없다.
🚨 A 기기처럼 DB 가 **떠 있는** 곳에서도 「DB 없음」 길을 재야 한다 — 그래서 세션을 갈아 끼운다.
   닿지 않는 주소(`127.0.0.1:1`)의 **진짜 엔진**을 쓴다 — psycopg 오류가 SQLAlchemy `OperationalError` 로
   감싸여 오는지까지 본다. 가짜 예외로 재면 그 포장을 못 본다 (D-170).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.api import app
from app.contracts import Candidate, Risk
from app.db import get_session

_UNREACHABLE = "postgresql+psycopg://x:x@127.0.0.1:1/x"


def _down_session() -> Iterator[Session]:
    engine = create_engine(_UNREACHABLE, connect_args={"connect_timeout": 1})
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class _QueryBreaks:
    """연결은 되는데 **쿼리가 틀린** 세션 — `reachable()` 이 이것까지 삼키면 안 된다 (D-162)."""

    def connection(self) -> None:
        return None

    def scalar(self, *_a: object, **_k: object) -> None:
        raise ProgrammingError("SELECT …", {}, Exception("relation does not exist"))

    def close(self) -> None:
        return None


@pytest.fixture
def down_client() -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = _down_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.gate
def test_DB_가_없어도_홈이_뜨고_수를_0건으로_적지_않는다(down_client: TestClient) -> None:
    r = down_client.get("/u/")
    assert r.status_code == 200, f"🔴 DB 없이 /u/ 가 안 뜬다 — {r.status_code}"
    assert "DB 에 붙지 못해" in r.text, "🔴 못 붙었다는 안내가 없다"
    # 🚨 셀 수 없는 것을 0 으로 적으면 없음이 사실로 둔갑한다 (D-72)
    assert '<div class="hm-v">0건</div>' not in r.text, "🔴 DB 없음을 0건으로 그렸다"
    assert r.text.count('<div class="hm-v">—</div>') == 3, "🔴 통계 셋이 「—」(모름)로 안 그려졌다"


@pytest.mark.gate
def test_DB_가_없어도_이력이_뜨고_기록없음으로_적지_않는다(down_client: TestClient) -> None:
    r = down_client.get("/u/history?verdict=hold&page=2")
    assert r.status_code == 200, f"🔴 DB 없이 /u/history 가 안 뜬다 — {r.status_code}"
    assert "DB 에 붙지 못해" in r.text, "🔴 못 붙었다는 안내가 없다"
    assert "아직 판정 기록이 없다" not in r.text, "🔴 못 읽은 것을 「기록 없음」으로 그렸다"


@pytest.mark.gate
def test_쿼리_오류는_DB_없음으로_삼키지_않는다() -> None:
    """🚨 음성 대조 — 「연결 실패만 받아 준다」가 참인지 잰다. 넓게 잡으면 이 테스트가 🔴 다."""

    def _breaks() -> Iterator[_QueryBreaks]:
        yield _QueryBreaks()

    app.dependency_overrides[get_session] = _breaks
    try:
        with pytest.raises(ProgrammingError):
            TestClient(app).get("/u/")
    finally:
        app.dependency_overrides.pop(get_session, None)


def _cand(risk: Risk) -> Candidate:
    return Candidate.model_validate(
        {
            "label": risk.value,
            "rewrite": {"body": "x"},
            "residual_risk": risk,
            "appeal_retention": 0.5,
        }
    )


@pytest.mark.gate
def test_프론티어_축은_R3_에서_끝난다() -> None:
    """🔴 종전 `/ 4.0` 은 R3 를 축의 3/4 지점에 찍었다 (D-227 — 척도는 R0~R3)."""
    from app.routers.user import _PLOT, _frontier  # noqa: PLC0415

    pts = {p["risk"]: p["cx"] for p in _frontier([_cand(Risk.R0), _cand(Risk.R3)])}
    assert pts["R0"] == _PLOT["x0"], "🔴 R0 가 축 왼쪽 끝이 아니다"
    assert pts["R3"] == _PLOT["x1"], f"🔴 R3 가 축 오른쪽 끝이 아니다 — {pts['R3']}"


@pytest.mark.gate
def test_프론티어는_도달불가_R4_를_축_끝에_눌러_그리지_않는다() -> None:
    from app.routers.user import _frontier  # noqa: PLC0415

    with pytest.raises(ValueError, match="축 밖"):
        _frontier([_cand(Risk.R4)])
