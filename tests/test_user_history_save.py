"""검수가 이력에 적는 것 — 🆕 2026-10-13 (ksr).

★ 재는 것 — ① 누구 것을 적나(동의한 회원만 · D-96 · D-69) ② 무엇을 적나(판정 대상 아님은 빼고 · 표의 CHECK 와 같은 모양)
  ③ 검수만 적나(칸 조작 · 이력 문구 담기는 안 적는다) ④ 못 적어도 검수 결과는 그린다.
🚨 DB 없이 돈다(CI `gate.yml` 에 Postgres 없음) — 받은 행을 **모아 두기만** 하는 가짜 세션을 끼운다.
   그래서 표의 CHECK 는 DB 가 아니라 여기서 같은 규칙을 글자로 다시 잰다(`_check_row`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import judgment_store as js
from app.api import FIXTURE_ROOT, app
from app.contracts import JudgeResponse
from app.db import get_session
from app.models import CopySentence, Judgment, WorkDoc
from app.routers import user as user_router

_ME = uuid.uuid4()
_FIXTURES = sorted(p.stem for p in (FIXTURE_ROOT / "judge").glob("*.json"))


def _fixture(name: str) -> JudgeResponse:
    return JudgeResponse.model_validate(
        json.loads((FIXTURE_ROOT / "judge" / f"{name}.json").read_text(encoding="utf-8"))
    )


class _Keeper:
    """받은 행을 모아 두기만 하는 세션. `fail=True` 면 커밋에서 연결이 끊긴다."""

    def __init__(self, *, fail: bool = False) -> None:
        self.rows: list[object] = []
        self.committed = False
        self.rolled_back = False
        self._fail = fail

    def add(self, row: object) -> None:
        self.rows.append(row)
        self.rows.extend(getattr(row, "sentences", []))

    def add_all(self, rows: list[object]) -> None:
        self.rows.extend(rows)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        if self._fail:
            raise OperationalError("insert", {}, Exception("연결 끊김"))
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None

    def of(self, kind: type) -> list:
        return [r for r in self.rows if isinstance(r, kind)]


def _user(*, history: bool = True, improve: bool = False) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=_ME,
        name="테스트",
        consent_history_at=now if history else None,
        consent_improve_at=now if improve else None,
    )


def _check_row(j: Judgment) -> None:
    """`app/models.py` 의 `judgment` CHECK 와 같은 규칙 — DB 가 거부할 행을 여기서 먼저 잡는다."""
    assert j.subject_type == "copy_sentence"
    assert (j.verdict == "hold") == (j.hold_reason is not None)
    assert (j.product_category is None) == (j.product_category_source is None)
    if j.verdict == "confirmed" and j.risk_final is not None:
        assert (j.violation_type is None) == (j.risk_final == 0)
    if j.risk_final is not None:
        # 🔄 2026-10-16 (D-348 보충 2 · 0026) — 하한은 사전 또는 인코더 · 인코더 하한은 R1 이하 · 보류에만
        lows = [r for r in (j.risk_floor, j.risk_encoder) if r is not None]
        assert lows and all(j.risk_final >= r for r in lows)
        assert j.risk_final <= max(lows) or j.evidence_span is not None
    if j.risk_encoder is not None:
        assert j.risk_encoder <= 1 and j.verdict == "hold" and j.risk_final is not None
        assert (j.evidence or {}).get("encoder_refs"), (
            "🔴 ck_judgment_encoder_has_basis — 인코더 하한의 근거 호가 없다"
        )
    assert j.hold_reason is None or len(j.hold_reason) <= 16
    assert len(j.law_version) <= 40 and len(j.judged_by) <= 80


@pytest.mark.gate
@pytest.mark.parametrize("name", _FIXTURES)
def test_픽스처의_판정이_표의_규칙에_맞게_적힌다(name: str) -> None:
    res = _fixture(name)
    keeper = _Keeper()
    kept = js.save_review(keeper, _user(), [res])  # type: ignore[arg-type]

    judged = [s for s in res.sentences if not s.not_claim]
    rows = keeper.of(Judgment)
    assert kept == (js.SAVED if judged else None), "🔴 적은 것과 알리는 상태가 다르다"
    assert len(rows) == len(judged), "🔴 판정 대상 문장 수와 적힌 판정 수가 다르다"
    assert len(keeper.of(CopySentence)) == len(judged)
    assert len(keeper.of(WorkDoc)) == (1 if judged else 0), "🔴 적을 판정이 없는데 문서를 만들었다"
    sent_ids = {s.id for s in keeper.of(CopySentence)}
    for j, s in zip(rows, judged, strict=True):
        _check_row(j)
        assert j.subject_id in sent_ids, "🔴 판정이 가리키는 문장이 없다 — 이력 조인에서 빠진다"
        assert j.doc_id == keeper.of(WorkDoc)[0].id
        assert j.verdict == s.verdict.value
        # 🔄 2026-10-14 (ssm 과 합침) — 위반도 근거도 없는 문장은 `evidence` 를 비운다(None) — 빈 JSON 을 적지 않는다
        ev = j.evidence or {}
        assert (j.evidence is None) == (not s.violations and not s.evidence)
        assert ev.get("violations", []) == [v.value for v in s.violations]
        assert len(ev.get("articles", [])) == len(s.evidence)
    for doc in keeper.of(WorkDoc):
        assert doc.owner_id == _ME and doc.consent_store is True
        assert doc.session_id is None, "🔴 회원 이력에 세션 키를 섞었다 (D-129)"


@pytest.mark.gate
def test_판정_대상_아님은_이력에_적지_않는다() -> None:
    """표에 「판정 대상 아님」 칸이 없다 — 적으면 「특이사항 없음」으로 읽힌다 (D-63 · D-275)."""
    res = _fixture("16_pass_not_claim")
    skipped = [s.text for s in res.sentences if s.not_claim]
    assert skipped, "🔴 픽스처에 판정 대상 아님 문장이 없다 — 재는 대상이 없다"
    keeper = _Keeper()
    js.save_review(keeper, _user(), [res])  # type: ignore[arg-type]
    assert not {s.raw for s in keeper.of(CopySentence)} & set(skipped)


@pytest.mark.gate
def test_품질_개선_동의는_문서에_그대로_실린다() -> None:
    """`consent_train` 은 NOTRAIN 의 유일한 해제다 (D-128) — 동의하지 않은 사람의 문서에 켜지면 안 된다."""
    res = _fixture("05_certificate_a")
    for improve in (False, True):
        keeper = _Keeper()
        js.save_review(keeper, _user(improve=improve), [res])  # type: ignore[arg-type]
        assert keeper.of(WorkDoc)[0].consent_train is improve


@pytest.fixture
def judged(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Keeper]:
    """코어 판정을 픽스처로 바꿔 끼우고, 가짜 세션을 단 `/u/judge`."""
    monkeypatch.setattr(
        user_router, "_core_judge", lambda *_a, **_k: ("ok", _fixture("05_certificate_a"))
    )
    keeper = _Keeper()

    def _dep() -> Iterator[_Keeper]:
        yield keeper

    app.dependency_overrides[get_session] = _dep
    try:
        yield keeper
    finally:
        app.dependency_overrides.pop(get_session, None)


def _post(op: str = "all") -> str:
    r = TestClient(app).post("/u/judge", data={"text": "혈압을 낮춰 줍니다", "op": op})
    assert r.status_code == 200, f"🔴 {r.status_code}"
    return r.text


@pytest.mark.gate
def test_동의한_회원의_검수는_이력에_적힌다(
    judged: _Keeper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(user_router, "current_user", lambda *_a: _user())
    _post()
    assert judged.of(Judgment) and judged.committed, "🔴 검수했는데 이력에 적지 않았다"


@pytest.mark.gate
def test_비회원_검수는_적지_않는다(judged: _Keeper) -> None:
    """D-69 — 비회원 문서를 만들지 않는다. 로그인해도 그 전 것은 안 따라온다."""
    text = _post()
    assert not judged.rows, "🔴 비회원 검수를 적었다"
    assert "이력에 저장됐어요" not in text


@pytest.mark.gate
def test_이력_보관에_동의하지_않으면_적지_않고_알린다(
    judged: _Keeper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-96 — 기본값은 미보관이다. 검수는 그대로 된다 — 동의는 기능의 대가가 아니다."""
    monkeypatch.setattr(user_router, "current_user", lambda *_a: _user(history=False))
    text = _post()
    assert not judged.rows, "🔴 동의 없이 검수 문구를 적었다"
    assert "위험도" in text, "🔴 동의가 없다고 검수 결과를 안 그렸다"
    assert "이력에 저장됐어요" not in text


@pytest.mark.gate
@pytest.mark.parametrize("op", ["add", "sample:1", "load"])
def test_판정하지_않는_동작은_적지_않는다(
    judged: _Keeper, monkeypatch: pytest.MonkeyPatch, op: str
) -> None:
    """칸 추가 · 예시 넣기 · 이력 문구 담기는 검수가 아니다 — 「이 문구로 다시 검수하기」가 누를 때마다 행을 늘리면 안 된다."""
    monkeypatch.setattr(user_router, "current_user", lambda *_a: _user())
    _post(op)
    assert not judged.rows, f"🔴 {op} 가 이력에 적었다"


@pytest.mark.gate
def test_적지_못해도_검수_결과는_그리고_저장됐다고_말하지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        user_router, "_core_judge", lambda *_a, **_k: ("ok", _fixture("05_certificate_a"))
    )
    monkeypatch.setattr(user_router, "current_user", lambda *_a: _user())
    keeper = _Keeper(fail=True)

    def _dep() -> Iterator[_Keeper]:
        yield keeper

    app.dependency_overrides[get_session] = _dep
    try:
        text = _post()
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert keeper.rolled_back, "🔴 실패한 세션을 되돌리지 않았다"
    assert "위험도" in text, "🔴 저장 실패가 검수 결과를 가렸다"
    assert "이력에 저장됐어요" not in text, "🔴 못 적었는데 저장됐다고 했다 (D-147)"


@pytest.mark.gate
def test_이력의_배지는_검수_화면과_같은_말을_한다() -> None:
    """불가 사유는 표에 칸이 없어 `evidence` 에 싣는다 — 빠지면 A/B/C 가 전부 「위반 확정」으로 뭉친다."""
    now = datetime.now(UTC)

    def _view(**kw: object) -> SimpleNamespace:
        base = {
            "id": uuid.uuid4(),
            "judged_at": now,
            "verdict": "confirmed",
            "hold_reason": None,
            "violation_type": None,
            "risk_final": None,
            "product_category": None,
            "evidence": None,
            "law_version": "v",
        }
        return user_router._hist_view(SimpleNamespace(**{**base, **kw}), "문구")

    hit = {"violation_type": "거짓_과장", "risk_final": 1}
    assert _view(risk_final=0).label == "특이사항 없음"
    assert _view(**hit, evidence={"infeasibility": "A"}).label == "인정받은 제품만 가능"
    assert _view(**hit, evidence={"infeasibility": "B"}).label == "객관적인 근거 자료 필요"
    assert _view(**hit, evidence={"infeasibility": "C"}).label == "사용 불가"
    assert _view(**hit).label == "위반 확정"
    held = _view(verdict="hold", hold_reason="low_conf", risk_final=2)
    assert held.label == "보류" and held.hold_reason == "확신 부족"
    assert held.risk is None, "🔴 확정이 아닌 문장에 위험도를 그렸다 (D-280)"
    assert _view(verdict="unjudged").tone != "ok", "🔴 미판정을 통과 색으로 그렸다 (D-127)"
