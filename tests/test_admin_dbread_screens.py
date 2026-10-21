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
#: 집계 칸 키 — KST 오늘 0시 (naive · SQL `date_trunc(… AT TIME ZONE 'Asia/Seoul')` 결과 모양)
TODAY0 = datetime.now(admin_dbread.KST).replace(
    hour=0, minute=0, second=0, microsecond=0, tzinfo=None
)


def fake_run(
    *, ticket_title: str = "검수 결과 문의", calls: list | None = None, generated: bool = False
):  # noqa: ANN201
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
        {
            "id": T1,
            "kind": "service",
            "version": "v1",
            "effective_on": TODAY - timedelta(days=30),
            "body": "본문1",
            "change_reason": "최초",
            "created_at": NOW,
            "created_by": "psj",
        },
        {
            "id": T2,
            "kind": "service",
            "version": "v2",
            "effective_on": TODAY + timedelta(days=10),
            "body": "본문2",
            "change_reason": "면책 조항",
            "created_at": NOW,
            "created_by": "psj",
        },
        {
            "id": T3,
            "kind": "privacy",
            "version": "p1",
            "effective_on": TODAY - timedelta(days=5),
            "body": "본문3",
            "change_reason": "최초",
            "created_at": NOW,
            "created_by": None,
        },
    ]
    member = {
        "id": MID,
        "email": "kim@example.com",
        "name": "김회원",
        "org": "푸드랩",
        "created_at": NOW,
        "last_login_at": None,
        "disabled_at": None,
        "terms_version": "v1",
        "terms_agreed_at": NOW,
        "consent_history_at": NOW,
        "consent_improve_at": None,
        "email_verified_at": None,
        "status": "active",
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
            "cs.assignees": [[{"initials": "psj", "display_name": "박수진"}]],
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
            "stats.usage": [
                [{"docs": 3, "n": 7}],
                [{"docs": 2, "n": 4}],
                [{"b": TODAY0, "n": 7}],
            ],
            "stats.members": [
                [
                    {
                        "live": 5,
                        "dormant": 1,
                        "disabled": 2,
                        "verified": 3,
                        "history": 4,
                        "improve": 1,
                        "with_org": 2,
                        "last_join": NOW,
                    }
                ],
                [{"b": TODAY0, "n": 2}],
                [{"b": TODAY0, "n": 1}],
            ],
            "stats.generation": [
                [{"n": 3 if generated else 0, "last_at": NOW if generated else None}],
                [{"k": "TimeoutError", "n": 2}, {"k": "CopyGenError", "n": 1}] if generated else [],
                [{"d": TODAY, "n": 3}] if generated else [],
            ],
            "stats.judge": [
                [
                    {
                        "n": 12,
                        "docs": 4,
                        "unjudged": 1,
                        "no_basis": 0,
                        "viol": 3,
                        "first_at": NOW,
                        "last_at": NOW,
                    }
                ],
                [{"k": "hold", "n": 8}, {"k": "confirmed_viol", "n": 3}, {"k": "unjudged", "n": 1}],
                [{"k": "low_conf", "n": 8}],
                [{"k": "식품", "n": 12}],
                [{"k": 0, "n": 2}, {"k": 2, "n": 2}],
                [{"k": "거짓_과장", "n": 3}],
                [{"d": TODAY, "n": 12}],
                [{"k": "classified", "n": 10}, {"k": "none", "n": 2}],
                [{"k": "rule-0.3.0-dict+encb:c451942436f0", "n": 12}],
                [{"k": "enc_up", "n": 2}, {"k": "dict_only", "n": 5}],
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


def test_문의_필터는_허용_값만_SQL_로_간다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    monkeypatch.setattr(admin_dbread, "run", fake_run(calls=calls))
    client.get("/admin/cs/tickets", params={"status": "closed", "type": "결제", "priority": "x"})
    sql, params = calls[0][1][0]
    assert params == ["closed"]
    assert "t.status = %s" in sql and "t.category" not in sql


def test_문의_상세_없음과_못읽음을_가른다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get(f"/admin/cs/tickets/{TID}").status_code == 200
    assert client.get("/admin/cs/tickets/no-such").status_code == 404
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_db", []))
    r = client.get("/admin/cs/tickets/no-such")
    assert r.status_code == 200
    assert "DB 에 연결하지 못했어요" in r.text


def test_못_읽으면_0건이라_말하지_않는다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_table", []))
    for path in (
        "/admin/cs/tickets",
        "/admin/board/notices",
        "/admin/terms",
        "/admin/members",
        "/admin/stats/quality/judge",
        "/admin/stats/quality/generation",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "launcher.py migrate" in r.text, path
        for empty in (
            "아직 접수된",
            "등록된 공지가",
            "등록된 약관 버전이",
            "아직 가입한",
            "저장된 검수가",
        ):
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
    kpi = r.context["kpi"]
    assert (kpi["viol"], kpi["unjudged"]) == (3, 1) and "enc_pct" not in kpi
    assert "보류" in r.text and "확신 부족" in r.text and "R2 업무정지 위험" in r.text
    assert "확정 위반" in r.text and "미판정 (오류 · 시간 초과)" in r.text
    assert "자동 판별" in r.text and "품목 미확정" in r.text
    assert "인코더가 위험도를 올림" in r.text and "c451942436f0" in r.text
    assert "마지막 판정" in r.text and "인코더가 함께 판정" not in r.text
    assert "94.2%" not in r.text and "이의제기" not in r.text and "더미" not in r.text
    assert client.get("/admin/stats/quality/judge?days=13").context["days"] == 30
    assert client.get("/admin/stats/quality/judge?days=all").context["days"] == 0


def test_운영_대시보드의_문의와_회원수는_DB_값이다(client: TestClient) -> None:
    r = client.get("/admin/")
    assert r.context["member_total"] == 3
    assert r.context["pending_tickets"] == 1
    assert r.context["tickets"][0]["id"] == TID
    assert "/admin/cs/tickets?status=open" in r.text


def test_생성_통계는_셀_수_없는_수를_그리지_않는다(client: TestClient) -> None:
    r = client.get("/admin/stats/quality/generation")
    assert r.status_code == 200
    assert "kpi" not in r.context and "by_origin" not in r.context
    assert "저장하지 않아요" in r.text and "사용하지 않았다는 뜻이 아니에요" in r.text
    for gone in (
        "카피 생성 문구",
        "승인된 생성 문구",
        "생성 비중",
        "저장 문구 출처",
        "88.4",
        "GPT-4o",
        "재생성 사유",
    ):
        assert gone not in r.text, gone
    assert "집계를 열려면 필요한 결정" in r.text and "생성 엔진" in r.text


def test_생성_실패는_오류_로그에서_센다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers import admin_stats  # noqa: PLC0415

    monkeypatch.setattr("app.settings.error_log_enabled", lambda s=None: True)
    calls: list = []
    monkeypatch.setattr(admin_dbread, "run", fake_run(generated=True, calls=calls))
    r = client.get("/admin/stats/quality/generation", params={"days": "7"})
    assert r.context["days"] == 7 and r.context["fail"]["n"] == 3
    assert "3건" in r.text and "TimeoutError" in r.text and "일별 생성 실패" in r.text
    sql, params = calls[0][1][0]
    assert "app_error_log" in sql and params == [
        admin_stats.GEN_FAIL_LOGGER,
        admin_stats.GEN_FAIL_MESSAGE,
        7,
    ]
    # 「전체」는 로그 보관 기간만큼이다
    client.get("/admin/stats/quality/generation", params={"days": "all"})
    from app.settings import ERROR_LOG_RETENTION_DAYS  # noqa: PLC0415

    assert calls[-1][1][0][1][-1] == ERROR_LOG_RETENTION_DAYS


def test_오류_로그를_안_쌓는_환경이면_0이_아니라_기록_안_함(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.settings.error_log_enabled", lambda s=None: False)
    r = client.get("/admin/stats/quality/generation")
    assert "기록 안 함" in r.text and "일별 생성 실패" not in r.text


def test_생성_실패_로그_자리가_user_py_와_맞다() -> None:
    """🚨 글자가 어긋나면 실패가 조용히 0 건으로 보인다 — 생성 처리부의 로그 호출과 맞댄다."""
    from pathlib import Path  # noqa: PLC0415

    from app.routers import admin_stats  # noqa: PLC0415

    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "user.py").read_text(
        encoding="utf-8"
    )
    assert admin_stats.GEN_FAIL_LOGGER == "app.routers.user"
    assert f'warning("{admin_stats.GEN_FAIL_MESSAGE}", exc_info=True)' in src


@pytest.mark.parametrize("path", ["/admin/", "/admin/stats/dashboard"])
def test_대시보드_이용_현황은_judgment_건수다(client: TestClient, path: str) -> None:
    for period, n_bars in (("daily", None), ("weekly", 7), ("monthly", 6)):
        r = client.get(path, params={"period": period})
        assert r.status_code == 200
        dash = r.context["dash"]
        assert dash["source"] == "db"
        assert dash["kpi"]["judge"] == "3" and dash["kpi"]["sentences"] == 7
        assert dash["kpi"]["gen"] == "저장 안 함"
        assert "2건" in dash["delta"]["judge"]
        assert len(dash["judge_series"]) == len(dash["labels"])
        if n_bars:
            assert len(dash["labels"]) == n_bars
        if period != "monthly":
            assert sum(dash["judge_series"]) == 7
        # 예시 수치가 남지 않았다
        assert "143" not in r.text and "3,842" not in r.text and "예시" not in r.text


def test_대시보드를_못_읽으면_대시와_안내다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_db", []))
    for path in ("/admin/", "/admin/stats/dashboard"):
        r = client.get(path)
        assert r.context["dash"]["kpi"]["judge"] == "-"
        assert "이용 기록을 읽지 못했어요" in r.text and "0건이라는 뜻이 아니에요" in r.text


def test_이용자_통계는_user_account_에서_센다(client: TestClient) -> None:
    r = client.get("/admin/stats/member", params={"period": "daily"})
    assert r.status_code == 200
    k = r.context["kpi"]
    assert (k["live"], k["active"], k["dormant"], k["disabled"]) == (5, 4, 1, 2)
    assert [c["pct"] for c in r.context["consents"]] == [20.0, 60.0, 40.0]
    trend = r.context["trend"]
    assert len(trend) == 7 and trend[-1]["join"] == 2 and trend[-1]["leave"] == 1
    for gone in ("12,483", "인플루언서", "Basic", "Enterprise", "유료 계정", "예시"):
        assert gone not in r.text, gone
    assert len(client.get("/admin/stats/member?period=weekly").context["trend"]) == 8
    assert len(client.get("/admin/stats/member?period=monthly").context["trend"]) == 6


def test_이용자_통계를_못_읽으면_안내다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin_dbread, "run", lambda queries, what: ("no_table", []))
    r = client.get("/admin/stats/member")
    assert r.status_code == 200
    assert "launcher.py migrate" in r.text and "이용자 통계를 확인할 수 없습니다" in r.text


@pytest.mark.parametrize(
    "path",
    [
        "/admin/",
        "/admin/stats/dashboard",
        "/admin/stats/member",
        "/admin/stats/quality/judge",
        "/admin/stats/quality/generation",
    ],
)
def test_통계_화면에는_결정_번호를_띄우지_않는다(client: TestClient, path: str) -> None:
    """근거 번호(D-…)는 코드 · 커밋에만 남긴다 — 화면 본문에는 싣지 않는다 (10-21 사용자 요청)."""
    import re  # noqa: PLC0415

    html = client.get(path).text
    start = html.index('id="admin-content"')
    body = html[start : html.index('class="admin-page-footer"', start)]  # 공용 바닥글은 이 화면 밖
    assert not re.search(r"D-\d+", body), re.findall(r".{20}D-\d+.{5}", body)
