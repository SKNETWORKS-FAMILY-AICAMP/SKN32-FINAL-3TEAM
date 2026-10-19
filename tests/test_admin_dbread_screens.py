"""관리자 화면이 운영 표(`ticket` · `notice` · `terms` · `user_account` · `judgment`)를 읽는다 — 2026-10-20 (psj).

지키는 것
  ① 읽었으면 표의 값을 그린다 — 더미 글자가 남지 않는다 · 라벨은 `app/models.py` 한 벌
  ② 못 읽으면 빈 화면 + 안내 — 0건이라 말하지 않고, 상세는 404 가 아니다 (D-72 · D-188)
  ③ 읽었는데 없으면 404
  ④ 필터 값은 허용 목록만 SQL 로 간다 · 상태(약관 · 공지 · 회원)는 저장값이 아니라 계산값이다
  ⑤ 검수 통계는 건수만 — 정확도 같은 셀 수 없는 수를 그리지 않는다 (D-147)

DB 없이 돈다 — `admin_dbread.run` 을 가짜로 바꾼다.
"""

from __future__ import annotations

import importlib
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin, admin_dbread, admin_router

TID = "3f2a9c1e-0000-4000-8000-000000000001"
NID = "7b1d0000-0000-4000-8000-000000000002"
MID = "9c4e0000-0000-4000-8000-000000000003"
T1 = "a1000000-0000-4000-8000-000000000011"
T2 = "a2000000-0000-4000-8000-000000000012"
T3 = "a3000000-0000-4000-8000-000000000013"

NOW = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)
TODAY = date.today()


def fake_run(*, ticket_title: str = "검수 결과 문의", calls: list | None = None, generated: bool = False):  # noqa: ANN201
    """`what` 마다 정해 둔 행을 돌려준다. `calls` 에 (what, queries) 를 쌓는다."""
    ticket = {
        "id": TID,
        "created_at": NOW,
        "category": "judge",
        "title": ticket_title,
        "body": "같은 문구인데 결과가 달라요.",
        "priority": "urgent",
        "status": "open",
        "reply": None,
        "closed_at": None,
        "expires_at": None,
        "who": "홍길동",
        "who_email": "hong@example.com",
        "owner": None,
    }
    counts = {"total": 1, "open": 1, "in_progress": 0, "urgent": 1}
    notice = {
        "id": NID,
        "title": "점검 안내",
        "category": "system",
        "body": "점검합니다.",
        "pinned": True,
        "starts_on": TODAY + timedelta(days=3),
        "ends_on": None,
        "hidden_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "author": "박수진",
    }
    terms = [
        {"id": T1, "kind": "service", "version": "v1", "effective_on": TODAY - timedelta(days=30),
         "body": "본문1", "change_reason": "최초", "created_at": NOW, "created_by": "psj"},
        {"id": T2, "kind": "service", "version": "v2", "effective_on": TODAY + timedelta(days=10),
         "body": "본문2", "change_reason": "면책 조항", "created_at": NOW, "created_by": "psj"},
        {"id": T3, "kind": "privacy", "version": "p1", "effective_on": TODAY - timedelta(days=5),
         "body": "본문3", "change_reason": "최초", "created_at": NOW, "created_by": None},
    ]
    member = {
        "id": MID, "email": "kim@example.com", "name": "김회원", "org": "푸드랩",
        "created_at": NOW, "last_login_at": None, "disabled_at": None,
        "terms_version": "v1", "terms_agreed_at": NOW, "consent_history_at": NOW,
        "consent_improve_at": None, "email_verified_at": None, "status": "active",
    }

    def run(queries, what):  # noqa: ANN001, ANN202
        if calls is not None:
            calls.append((what, queries))
        last = queries[0][1][-1] if queries and queries[0][1] else None
        detail_id = last if what.endswith(".detail") else None
        table = {
            "cs.count": [[{"n": 1}], [counts]],
            "cs.list": [[ticket]],
            "cs.recent": [[ticket], [counts]],
            "cs.detail": [[ticket] if detail_id == TID else []],
            "index.members": [[{"n": 3}]],
            "board.count": [[{"n": 1}]],
            "board.list": [[notice]],
            "board.detail": [[notice] if detail_id == NID else []],
            "terms.list": [terms],
            "terms.detail": [[t for t in terms if t["kind"] == "service"]],
            "members.count": [[{"n": 1}]],
            "members.list": [[member]],
            "members.detail": [
                [member] if last == MID else [],
                [{"sentences": 12, "requests": 4, "month": 5, "last_at": NOW}],
                [{"id": TID, "created_at": NOW, "title": "검수 결과 문의", "status": "open"}],
            ],
            "stats.generation": [
                [{"k": "user", "n": 12}] + ([{"k": "generated", "n": 4}] if generated else []),
                [{"n": 4 if generated else 0, "docs": 2 if generated else 0,
                  "approved": 1 if generated else 0, "last_at": NOW if generated else None}],
                [{"d": TODAY, "n": 4}] if generated else [],
            ],
            "stats.judge": [
                [{"n": 12, "docs": 4, "enc": 9, "first_at": NOW, "last_at": NOW}],
                [{"k": "hold", "n": 8}, {"k": "confirmed", "n": 4}],
                [{"k": "low_conf", "n": 8}],
                [{"k": "식품", "n": 12}],
                [{"k": 0, "n": 2}, {"k": 2, "n": 2}],
                [{"k": "거짓_과장", "n": 3}],
                [{"d": TODAY, "n": 12}],
            ],
        }
        if what == "terms.detail" and queries[0][1][0] not in (T1, T2):
            return "db", [[]]
        return "db", table[what]

    return run


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in ("admin", "admin_cs", "admin_board", "admin_terms", "admin_members", "admin_stats"):
        module = importlib.import_module(f"app.routers.{name}")
        monkeypatch.setattr(module, "require_governor", lambda request: "UI-TEST")
    monkeypatch.setattr(admin, "_table_counts", lambda: {})
    monkeypatch.setattr(admin_dbread, "run", fake_run())
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


def test_문의_목록은_표의_값과_모델_라벨로_그린다(client: TestClient) -> None:
    r = client.get("/admin/cs/tickets")
    assert r.status_code == 200
    assert f'href="/admin/cs/tickets/{TID}"' in r.text
    assert "TK-" in r.text and "홍길동" in r.text
    assert "검수" in r.text and "긴급" in r.text and "미처리" in r.text
    assert "더미" not in r.text and "결제" not in r.text and "매칭" not in r.text


def test_문의_필터는_허용_값만_SQL_로_간다(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(admin_dbread, "run", fake_run(calls=calls))
    client.get("/admin/cs/tickets", params={"status": "closed", "type": "결제", "priority": "x"})
    sql, params = calls[0][1][0]
    assert params == ["closed"]
    assert "t.status = %s" in sql and "t.category" not in sql


def test_문의_상세_없음과_못읽음을_가른다(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.get(f"/admin/cs/tickets/{TID}").status_code == 200
    assert client.get("/admin/cs/tickets/no-such").status_code == 404
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_db", []))
    r = client.get("/admin/cs/tickets/no-such")
    assert r.status_code == 200
    assert "DB 에 연결하지 못했어요" in r.text


def test_못_읽으면_0건이라_말하지_않는다(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_table", []))
    for path in ("/admin/cs/tickets", "/admin/board/notices", "/admin/terms", "/admin/members",
                 "/admin/stats/quality/judge", "/admin/stats/quality/generation"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "launcher.py migrate" in r.text, path
        for empty in ("아직 접수된", "등록된 공지가", "등록된 약관 버전이", "아직 가입한", "저장된 검수가"):
            assert empty not in r.text, (path, empty)


def test_공지_상태는_계산한다(client: TestClient) -> None:
    r = client.get("/admin/board/notices")
    assert "점검 안내" in r.text and "시스템" in r.text and "예정" in r.text
    assert client.get(f"/admin/board/notices/{NID}").status_code == 200
    assert client.get("/admin/board/notices/no-such").status_code == 404


def test_약관_상태와_이전_버전을_시행일_순서로_계산한다(client: TestClient) -> None:
    rows = client.get("/admin/terms").context["rows"]
    by_version = {r["version"]: r for r in rows}
    assert by_version["v1"]["status"] == "시행 중"
    assert by_version["v2"]["status"] == "예정"
    assert by_version["v2"]["prev_version"] == "v1"
    assert by_version["p1"]["status"] == "시행 중"
    assert [r["kind"] for r in rows] == ["service", "service", "privacy"]
    d = client.get(f"/admin/terms/{T1}")
    assert d.status_code == 200
    assert [h["version"] for h in d.context["history"]] == ["v2", "v1"]
    assert client.get("/admin/terms/no-such").status_code == 404


def test_회원_상태_필터는_계산식에_기준일과_같이_간다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    monkeypatch.setattr(admin_dbread, "run", fake_run(calls=calls))
    r = client.get("/admin/members", params={"status": "dormant", "q": "50%"})
    assert r.status_code == 200
    sql, params = calls[0][1][0]
    assert params == [r"%50\%%", r"%50\%%", r"%50\%%", 365, "dormant"]
    assert "플랜" not in r.text and "회원 유형" not in r.text


def test_회원_상세는_건수만_보이고_결제_예시가_없다(client: TestClient) -> None:
    r = client.get(f"/admin/members/{MID}")
    assert r.status_code == 200
    assert "김회원" in r.text and "4건" in r.text and "12건" in r.text
    assert "결제" not in r.text and "Enterprise" not in r.text
    assert f'href="/admin/cs/tickets/{TID}"' in r.text
    assert client.get("/admin/members/no-such").status_code == 404


def test_검수_통계는_judgment_건수만_그린다(client: TestClient) -> None:
    r = client.get("/admin/stats/quality/judge", params={"days": "7"})
    assert r.status_code == 200
    assert r.context["days"] == 7
    assert r.context["kpi"]["enc_pct"] == 75.0
    assert "보류" in r.text and "확신 부족" in r.text and "R2 업무정지 위험" in r.text
    assert "94.2%" not in r.text and "이의제기" not in r.text and "더미" not in r.text
    assert client.get("/admin/stats/quality/judge?days=13").context["days"] == 30
    assert client.get("/admin/stats/quality/judge?days=all").context["days"] == 0


def test_운영_대시보드의_문의와_회원수는_DB_값이다(client: TestClient) -> None:
    r = client.get("/admin/")
    assert r.context["member_total"] == 3
    assert r.context["pending_tickets"] == 1
    assert r.context["tickets"][0]["id"] == TID
    assert "/admin/cs/tickets?status=open" in r.text


def test_생성_통계는_저장_안_함을_0건과_구분해_알린다(client: TestClient) -> None:
    r = client.get("/admin/stats/quality/generation")
    assert r.status_code == 200
    assert r.context["kpi"]["generated"] == 0
    assert "저장하지 않아요" in r.text and "쓰지 않았다는 뜻이 아니에요" in r.text
    assert "88.4" not in r.text and "GPT-4o" not in r.text and "재생성 사유" not in r.text


def test_생성_통계는_출처별_건수를_센다(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(admin_dbread, "run", fake_run(generated=True, calls=calls))
    r = client.get("/admin/stats/quality/generation", params={"days": "7"})
    assert r.context["days"] == 7
    assert r.context["kpi"]["generated"] == 4 and r.context["kpi"]["share"] == 25.0
    assert "카피 생성" in r.text and "직접 입력 · 검수" in r.text
    assert "저장하지 않아요" not in r.text
    sql = calls[0][1][1][0]
    assert "origin = 'generated'" in sql and "raw" not in sql  # 원문 칸을 읽지 않는다 (D-76)
