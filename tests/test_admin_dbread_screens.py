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


def test_약관_목록과_상세는_DB_조회_없이_닫힘_안내다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_read(*args, **kwargs):
        raise AssertionError("닫힌 약관 화면은 DB를 읽지 않는다")

    monkeypatch.setattr(admin_dbread, "run", unexpected_read)
    for path in ("/admin/terms", f"/admin/terms/{T1}", "/admin/terms/no-such"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.template.name == "admin/_closed.html"
        assert response.context["page_title"] == "약관 관리"
        assert "닫혀 있습니다" in response.text
        assert "새 버전 등록" not in response.text
        assert "rows" not in response.context and "history" not in response.context


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
    assert "인코더가 위험도를 올림" in r.text
    assert "by_version" not in r.context  # 10-21 — 판정 버전 구역은 화면에서 뺐다
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
    assert "생성 결과는 저장하지 않으며" in r.text
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
    assert "집계 범위 안내" in r.text and "생성 엔진" in r.text


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
        assert "이용 기록을 읽지 못했어요" in r.text and "0건이라는 뜻" in r.text


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


def test_생성_엔진_구성은_설정에서_읽는다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers.copygen import llm  # noqa: PLC0415
    from app.routers.copygen.branches import BRANCHES  # noqa: PLC0415

    monkeypatch.setenv(llm.ENV_MODEL, "model-a, model-b")
    r = client.get("/admin/stats/quality/generation")
    cfg = r.context["config"]
    assert cfg["models"] == ["model-a", "model-b"]
    assert len(cfg["branches"]) == len(BRANCHES)
    assert (
        "카피 생성 엔진 구성" in r.text
        and "<li>model-a</li>" in r.text
        and "<li>model-b</li>" in r.text
        and "A안" in r.text
    )


def test_서버_시작_이후_생성_현황은_메모리_카운터다(client: TestClient) -> None:
    from app import gen_usage  # noqa: PLC0415

    gen_usage.reset()
    r = client.get("/admin/stats/quality/generation")
    assert r.context["usage"]["total"] == 0 and "아직 생성 요청이 없어요" in r.text
    gen_usage.record(
        "ok", "food_no", 12.0, candidates=10, passed=4, reasons={"number": 4, "judge": 2}, rounds=2
    )
    gen_usage.record(
        "ok", "food_no", 8.0, more=True, candidates=6, passed=4, reasons={"number": 2}, rounds=1
    )
    gen_usage.record("failed", "cos_no")
    gen_usage.record("off", "food_no")
    gen_usage.record("이상한값", "food_no")  # 모르는 결과는 세지 않는다
    u = client.get("/admin/stats/quality/generation").context["usage"]
    assert (u["total"], u["ok"], u["failed"], u["off"]) == (4, 2, 1, 1)
    assert u["success_pct"] == 66.7  # 꺼짐은 분모에서 뺀다
    assert (u["avg_secs"], u["max_secs"], u["more"]) == (10.0, 12.0, 1)
    assert u["by_branch"][0]["n"] == 3 and "식품" in u["by_branch"][0]["label"]
    assert (u["candidates"], u["passed"], u["pass_pct"], u["avg_rounds"]) == (16, 8, 50.0, 1.5)
    assert u["reasons"][0] == {"label": "입력에 없는 수치", "n": 6, "pct": 75.0}
    assert u["reasons"][1]["label"] == "판정엔진 미통과"
    r = client.get("/admin/stats/quality/generation")
    assert "서버를 다시 켜면 0부터" in r.text and "이후</b> 이 서버" in r.text
    assert "후보 통과율" in r.text and "입력에 없는 수치" in r.text and "평균 탐색 라운드" in r.text
    gen_usage.reset()


def test_생성_처리부가_세_갈래를_모두_센다() -> None:
    """🚨 생성 처리부에서 세는 줄이 빠지면 화면이 조용히 0 으로 보인다 — 소스와 맞댄다."""
    import re  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "user.py").read_text(
        encoding="utf-8"
    )
    for outcome in ("ok", "failed", "off"):
        assert re.search(rf'gen_usage\.record\(\s*"{outcome}"', src), outcome


def test_AI_광고_생성_요청과_광고_종류를_센다(client: TestClient) -> None:
    import re  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from app import gen_usage  # noqa: PLC0415

    gen_usage.reset()
    assert "아직 광고 만들기 요청이 없어요" in client.get("/admin/stats/quality/generation").text
    for fmt in ("SNS 피드", "SNS 피드", "배너"):
        gen_usage.record_compose(fmt)
    r = client.get("/admin/stats/quality/generation")
    u = r.context["usage"]
    assert u["compose_total"] == 3
    assert u["compose_by_format"][0] == {"label": "SNS 피드", "n": 2, "pct": 66.7}
    assert "광고 만들기 요청" in r.text and "고른 광고 종류" in r.text
    gen_usage.reset()
    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "user.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r"gen_usage\.record_compose\(ad_format\)", src)  # 광고 생성 처리부가 센다
