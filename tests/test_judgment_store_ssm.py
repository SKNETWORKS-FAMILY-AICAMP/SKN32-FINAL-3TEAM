"""검수 판정 저장 — 🆕 2026-10-13 (소성민 · W10 · `app/judgment_store.py`).

★ 지키는 것
  ① 비회원 · 선택 동의 ① 없는 회원은 **아무것도 쓰지 않는다** (D-307 · D-96)
  ② 동의한 회원은 문장마다 `copy_sentence` + `judgment` 한 줄 · 칸이 표의 제약을 지킨다
  ③ 저장이 실패해도 판정 응답은 나가고, 로그에 원문이 남지 않는다
🚨 DB 없이 돈다(CI 에 Postgres 없음) — 받아 적기만 하는 가짜 세션을 끼운다. 실제 DB 대조는 `COPYLANE_DB_IT=1` 일 때만.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import judgment_store as js
from app.api import app
from app.contracts import JudgeResponse
from app.db import get_session
from app.models import CopySentence, Judgment, WorkDoc
from app.routers import user as user_router

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = sorted((ROOT / "tests/fixtures/judge").glob("*.json"))
_HOLD_REASONS = {"low_conf", "gap2", "cat_unknown", "rd1", "premise_unknown", "law_uncovered"}
_SECRET = "출시전비밀문구-테스트"


def _resp(name: str) -> JudgeResponse:
    return JudgeResponse.model_validate(
        json.loads((ROOT / "tests/fixtures/judge" / name).read_text("utf-8"))
    )


def _user(*, history: bool = True, improve: bool = False) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="테스트",
        consent_history_at=now if history else None,
        consent_improve_at=now if improve else None,
    )


class _Writer:
    """쓰기를 받아 적기만 하는 세션. `fail=True` 면 커밋에서 터진다."""

    def __init__(self, *, fail: bool = False) -> None:
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False
        self.fail = fail

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def add_all(self, objs: list[object]) -> None:
        self.added.extend(objs)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        if self.fail:
            raise RuntimeError(f"connection to host=db user=x failed: {_SECRET}")
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None


# ── ① 쓰지 않는 사람 ──────────────────────────────────────────


@pytest.mark.gate
def test_비회원은_아무것도_쓰지_않는다() -> None:
    w = _Writer()
    assert js.save_review(w, None, [_resp("02_hold_low_conf.json")]) is None  # type: ignore[arg-type]
    assert not w.added and not w.committed, f"🔴 써서는 안 되는 판정을 적었다 — {w.added}"


@pytest.mark.gate
def test_이력_보관은_필수라_동의_기록이_없는_회원도_적는다() -> None:
    """🔄 2026-10-20 (lse · 사용자 결정) — 검수 이력 보관은 필수다(종전 D-96 선택 동의 ①). 가입 전 회원(동의 칸 빈 값)도 적는다."""
    w = _Writer()
    assert js.save_review(w, _user(history=False), [_resp("02_hold_low_conf.json")]) == js.SAVED  # type: ignore[arg-type]
    assert w.added and w.committed


# ── ② 적는 칸 ─────────────────────────────────────────────────


@pytest.mark.gate
@pytest.mark.parametrize("fx", FIXTURES, ids=lambda p: p.stem)
def test_픽스처마다_행이_표의_제약을_지킨다(fx: Path) -> None:
    """`app/models.py` 의 CHECK 를 파이썬으로 다시 잰다 — 실제 DB 가 없어도 거절될 행을 먼저 잡는다."""
    res = JudgeResponse.model_validate(json.loads(fx.read_text("utf-8")))
    user = _user()
    docs, sents, judgs = js.build_rows(user, [res])  # type: ignore[arg-type]
    judged = [s for s in res.sentences if not s.not_claim]  # 판정 대상 아님은 적지 않는다 (D-275)
    assert len(docs) == (1 if judged else 0), (
        "🔴 문구 하나 = 문서 하나가 아니다(적을 문장이 없으면 문서도 없다)"
    )
    if not docs:
        return
    doc = docs[0]
    assert doc.owner_id == user.id and doc.consent_store and doc.expires_at is None
    assert doc.kind == "single" and len(doc.title) <= 200
    assert len(sents) == len(judgs) == len(judged), "🔴 판정한 문장마다 한 줄이 아니다"
    for cs, j, s in zip(sents, judgs, judged, strict=True):
        assert cs.doc_id == doc.id and j.doc_id == doc.id
        assert j.subject_type == "copy_sentence" and j.subject_id == cs.id
        assert cs.raw == s.text and cs.origin == "user" and " " not in cs.norm
        assert j.verdict in {"confirmed", "hold", "no_basis", "unjudged"}
        assert (j.verdict == "hold") == (j.hold_reason is not None), "🔴 ck_judgment_hold_reason"
        assert j.hold_reason is None or j.hold_reason in _HOLD_REASONS
        assert (j.product_category is None) == (j.product_category_source is None), (
            "🔴 ck_judgment_category_source_pair"
        )
        assert j.product_category_source in (None, "classified", "user_selected")
        for r in (j.risk_floor, j.risk_final):
            assert r is None or 0 <= r <= 4
        if j.verdict == "confirmed" and j.risk_final is not None:
            assert (j.violation_type is None) == (j.risk_final == 0), (
                "🔴 ck_judgment_confirmed_risk"
            )
        assert len(j.law_version) <= 40 and len(j.judged_by) <= 80
        assert 0 <= j.attempt <= 2
        if s.violations:
            assert j.violation_type == s.violations[0].value
            assert j.evidence["violations"] == [v.value for v in s.violations]
            assert j.evidence["infeasibility"] == (
                s.infeasibility.value if s.infeasibility else None
            )


@pytest.mark.gate
def test_판정_대상_아님은_적지_않는다() -> None:
    """🆕 2026-10-14 (흡수 중 고침) — 표에 `not_claim` 칸이 없다. 적으면 「확정 · 위반 없음 · R0」 으로 남아
    이력 · 통계에서 「특이사항 없음」 으로 읽힌다 — 통과를 닫아 둔 판정(D-275 · D-323 결정 5)이 저장에서 열린다."""
    res = _resp("16_pass_not_claim.json")
    assert res.sentences and all(s.not_claim for s in res.sentences), "픽스처 전제가 바뀌었다"
    w = _Writer()
    assert js.save_review(w, _user(), [res]) is None  # type: ignore[arg-type]
    assert not w.added and not w.committed, f"🔴 판정 대상 아님 문장을 적었다 — {w.added}"
    mixed = js.build_rows(_user(), [res, _resp("02_hold_low_conf.json")])  # type: ignore[arg-type]
    assert all(cs.raw not in {s.text for s in res.sentences} for cs in mixed[1]), (
        "🔴 섞인 검수에서 판정 대상 아님 문장이 들어갔다"
    )


@pytest.mark.gate
def test_동의_둘을_문서에_그대로_옮긴다() -> None:
    res = _resp("02_hold_low_conf.json")
    assert js.build_rows(_user(improve=False), [res])[0][0].consent_train is False  # type: ignore[arg-type]
    assert js.build_rows(_user(improve=True), [res])[0][0].consent_train is True  # type: ignore[arg-type]


@pytest.mark.gate
def test_사용자가_고른_품목은_출처와_함께_적는다() -> None:
    """D-276 — 고른 품목의 결과는 「선택 전제 결과」다. 출처가 빠지면 이력이 둘을 못 가른다."""
    res = _resp("20_pass_user_selected_category.json")
    _, _, judgs = js.build_rows(_user(), [res])  # type: ignore[arg-type]
    assert res.category is not None
    assert {j.product_category_source for j in judgs} == {res.category_source.value}  # type: ignore[union-attr]


@pytest.mark.gate
def test_동의한_회원의_검수는_문구마다_문서_하나다() -> None:
    """🔄 2026-10-14 (ksr 흡수 · 팀장 (다)) — 문구 칸마다 별개의 광고 문구다(`kind='single'`). 종전에는 검수 한 번을 문서 하나로 묶었다.
    문서 제목에 원문을 넣지 않는다 — 원문은 `copy_sentence.raw` 한 곳이다."""
    w = _Writer()
    results = [_resp("02_hold_low_conf.json"), _resp("05_certificate_a.json")]
    status = js.save_review(w, _user(), results)  # type: ignore[arg-type]
    docs = [o for o in w.added if isinstance(o, WorkDoc)]
    sents = [o for o in w.added if isinstance(o, CopySentence)]
    judgs = [o for o in w.added if isinstance(o, Judgment)]
    assert w.committed and status == js.SAVED and len(docs) == len(results)
    assert {j.doc_id for j in judgs} == {d.id for d in docs}
    assert not {s.raw for s in sents} & {d.title for d in docs}, "🔴 문서 제목에 원문이 들어갔다"
    assert (
        len(judgs)
        == len(sents)
        == sum(len([s for s in r.sentences if not s.not_claim]) for r in results)
    )


# ── ③ 실패 ────────────────────────────────────────────────────


@pytest.mark.gate
def test_저장이_실패해도_예외를_올리지_않고_원문을_로그에_남기지_않는다(
    caplog: pytest.LogCaptureFixture,
) -> None:
    w = _Writer(fail=True)
    with caplog.at_level(logging.WARNING, logger="copylane.judgment_store"):
        assert js.save_review(w, _user(), [_resp("02_hold_low_conf.json")]) == js.FAILED  # type: ignore[arg-type]
    assert w.rolled_back, "🔴 실패한 쓰기를 되돌리지 않았다"
    assert "RuntimeError" in caplog.text
    assert _SECRET not in caplog.text and "host=" not in caplog.text, (
        "🔴 원인 문자열이 로그에 남았다"
    )


# ── 화면 경로 ─────────────────────────────────────────────────


@pytest.fixture
def writer() -> _Writer:
    w = _Writer()

    def _dep():  # noqa: ANN202
        yield w

    app.dependency_overrides[get_session] = _dep
    try:
        yield w
    finally:
        app.dependency_overrides.pop(get_session, None)


def _engine_returns(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr(user_router, "_core_judge", lambda *_a, **_k: ("ok", _resp(name)))


@pytest.mark.gate
def test_동의한_회원이_검수하면_판정이_저장된다(
    writer: _Writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_returns(monkeypatch, "02_hold_low_conf.json")
    monkeypatch.setattr(user_router, "current_user", lambda *_a: _user())
    r = TestClient(app).post("/u/judge", content="text=%ED%85%8C%EC%8A%A4%ED%8A%B8&op=all")
    assert r.status_code == 200
    assert writer.committed and any(isinstance(o, Judgment) for o in writer.added)


@pytest.mark.gate
def test_비회원_검수는_DB_에_쓰지_않는다(writer: _Writer, monkeypatch: pytest.MonkeyPatch) -> None:
    _engine_returns(monkeypatch, "02_hold_low_conf.json")
    monkeypatch.setattr(user_router, "current_user", lambda *_a: None)
    r = TestClient(app).post("/u/judge", content="text=%ED%85%8C%EC%8A%A4%ED%8A%B8&op=all")
    assert r.status_code == 200
    assert not writer.added and not writer.committed, "🔴 비회원 판정을 적었다 (D-307)"


@pytest.mark.gate
def test_저장이_실패해도_검수_화면은_결과를_그린다(monkeypatch: pytest.MonkeyPatch) -> None:
    w = _Writer(fail=True)

    def _dep():  # noqa: ANN202
        yield w

    _engine_returns(monkeypatch, "02_hold_low_conf.json")
    monkeypatch.setattr(user_router, "current_user", lambda *_a: _user())
    app.dependency_overrides[get_session] = _dep
    try:
        r = TestClient(app).post("/u/judge", content="text=%ED%85%8C%EC%8A%A4%ED%8A%B8&op=all")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert r.status_code == 200 and w.rolled_back


# ── 실제 DB (선택) ────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("COPYLANE_DB_IT") != "1", reason="실제 DB 에 쓴다 — COPYLANE_DB_IT=1 일 때만"
)
def test_실제_DB_가_모든_픽스처의_행을_받는다() -> None:
    """표의 CHECK · FK 가 이 모듈이 만든 행을 받는가. 🚨 한 트랜잭션 안에서 재고 되돌린다."""
    from app.auth import hash_password  # noqa: PLC0415
    from app.db import _SessionLocal  # noqa: PLC0415
    from app.models import UserAccount  # noqa: PLC0415

    session = _SessionLocal()
    try:
        now = datetime.now(UTC)
        user = UserAccount(
            id=uuid.uuid4(),
            email=f"it-{uuid.uuid4().hex[:8]}@example.com",
            pw_hash=hash_password("x" * 12),
            name="it",
            terms_version="v1",
            terms_agreed_at=now,
            disclaimer_agreed_at=now,
            consent_history_at=now,
        )
        session.add(user)
        session.flush()
        results = [JudgeResponse.model_validate(json.loads(p.read_text("utf-8"))) for p in FIXTURES]
        docs, sents, judgs = js.build_rows(user, results)
        session.add_all(docs)
        session.flush()
        session.add_all(sents)
        session.flush()
        session.add_all(judgs)
        session.flush()  # 🚨 커밋하지 않는다 — 제약은 flush 에서 걸린다
        rows, total = user_router._history_rows(session, user.id, None, 1)
        assert total == len(judgs) and rows, "🔴 적은 판정이 이력에 안 보인다"
    finally:
        session.rollback()
        session.close()


# ── 🆕 2026-10-20 (lse) 품목을 고른 재판정 — 같은 문구의 앞 기록을 바꿔 적는다(`replace_review`) ──────────


class _Replacer(_Writer):
    """앞 기록 찾기(`scalars`) · 지우기(`execute`)를 받는 세션 — 최근 문서 하나의 문장 글자를 들고 있다."""

    def __init__(self, prior_raws: list[str]) -> None:
        super().__init__()
        self.prior_id = uuid.uuid4()
        self.prior_raws = prior_raws
        self.deleted: list[str] = []
        self._calls = 0

    def scalars(self, stmt: object) -> SimpleNamespace:
        self._calls += 1
        rows = [self.prior_id] if self._calls == 1 else list(self.prior_raws)
        return SimpleNamespace(all=lambda: rows)

    def execute(self, stmt: object) -> None:
        self.deleted.append(str(stmt))


def test_고른_품목의_판정은_같은_문구의_앞_기록을_바꿔_적는다() -> None:
    res = _resp("02_hold_low_conf.json")
    raws = [s.text for s in res.sentences if not s.not_claim]
    w = _Replacer(raws)
    assert js.replace_review(w, _user(), res) == js.SAVED  # type: ignore[arg-type]
    assert w.deleted and "DELETE FROM work_doc" in w.deleted[0], (
        "🔴 앞 기록(고르기 전 보류)을 지우지 않았다"
    )
    assert w.added and w.committed, "🔴 고른 품목의 판정을 적지 않았다"


def test_글자가_다른_문구의_기록은_지우지_않는다() -> None:
    res = _resp("02_hold_low_conf.json")
    w = _Replacer(["전혀 다른 문장"])
    assert js.replace_review(w, _user(), res) == js.SAVED  # type: ignore[arg-type]
    assert not w.deleted, "🔴 다른 문구의 기록을 지웠다"
    assert w.added and w.committed


def test_비회원의_고른_판정은_적지_않는다() -> None:
    w = _Replacer([])
    assert js.replace_review(w, None, _resp("02_hold_low_conf.json")) is None  # type: ignore[arg-type]
    assert not w.added and not w.deleted
