"""관리자 쓰기 — 공지 작성 · 수정과 문의 답변 · 상태 변경 (2026-10-20 · psj · D-260 ⑦).

지키는 것
  ① CSRF 이중 제출 — 화면이 쿠키와 hidden 칸에 토큰을 심고, 없으면 403 · 쓰지 않는다 (P1-7)
  ② 값은 허용 목록만 — 분류 · 상태 · 우선순위 · 담당자 밖이면 422 · 쓰지 않는다 · 쓴 내용은 다시 그린다
  ③ 길이는 자르지 않고 거부한다 (D-220)
  ④ 작성자는 로그인한 계정이다 — 폼에서 받지 않는다
  ⑤ 「완료」는 파기 기한을 같이 잡는다 (D-129 · `ck_ticket_closed_expiry`)
  ⑥ 못 쓰면 안내 + 503 — 쓴 내용을 버리지 않는다 · 읽었는데 없으면 404
  ⑦ 로그인 없이는 쓰기도 로그인 화면으로 간다

DB 없이 돈다 — `admin_dbread.run` · `admin_dbwrite.run` 을 가짜로 바꾼다.
"""

from __future__ import annotations

import importlib
import re
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin_dbread, admin_dbwrite, admin_router
from app.settings import TICKET_RETENTION_DAYS, TICKET_TEXT_MAX

NID = "7b1d0000-0000-4000-8000-000000000002"
TID = "3f2a9c1e-0000-4000-8000-000000000001"
NOW = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)

NOTICE = {
    "id": NID,
    "title": "점검 안내",
    "category": "system",
    "body": "점검합니다.",
    "pinned": False,
    "starts_on": None,
    "ends_on": None,
    "hidden_at": None,
    "created_at": NOW,
    "updated_at": NOW,
    "author": "박수진",
}
TICKET = {
    "id": TID,
    "created_at": NOW,
    "category": "judge",
    "title": "검수 결과 문의",
    "body": "같은 문구인데 결과가 달라요.",
    "priority": "normal",
    "status": "open",
    "reply": None,
    "closed_at": None,
    "expires_at": None,
    "who": "홍길동",
    "who_email": "hong@example.com",
    "owner": None,
    "owner_initials": None,
}


class FakeDB:
    def __init__(self) -> None:
        self.writes: list[tuple[str, list, str]] = []
        self.write_result: tuple[str, list[dict]] = ("db", [{"id": NID}])

    def read(self, queries, what):  # noqa: ANN001, ANN201
        key = queries[0][1][-1] if queries and queries[0][1] else None
        table = {
            "board.detail": [[NOTICE] if key == NID else []],
            "cs.detail": [[TICKET] if key == TID else []],
            "cs.assignees": [[{"initials": "psj", "display_name": "박수진"}]],
        }
        return "db", table[what]

    def write(self, sql, params, what):  # noqa: ANN001, ANN201
        self.writes.append((sql, params, what))
        return self.write_result


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    f = FakeDB()
    monkeypatch.setattr(admin_dbread, "run", f.read)
    monkeypatch.setattr(admin_dbwrite, "run", f.write)
    return f


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake: FakeDB) -> TestClient:  # noqa: ARG001
    for name in ("admin", "admin_board", "admin_cs"):
        module = importlib.import_module(f"app.routers.{name}")
        monkeypatch.setattr(module, "require_governor", lambda request: "psj")
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


def _token(client: TestClient, path: str) -> str:
    r = client.get(path)
    assert r.status_code == 200
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m, "🔴 폼에 CSRF 칸이 없다"
    assert client.cookies.get("copylane_csrf") == m.group(1), "🔴 쿠키와 폼의 토큰이 다르다"
    return m.group(1)


def _notice(**over: str) -> dict:
    return {
        "title": "새 기능 안내",
        "category": "update",
        "body": "검수 화면이 바뀌었어요.",
        **over,
    }


# ── 공지 ────────────────────────────────────────────────


def test_새_공지_폼이_뜨고_목록에서_간다(client: TestClient) -> None:
    r = client.get("/admin/board/notices/new")
    assert r.status_code == 200
    assert 'action="/admin/board/notices"' in r.text and 'method="post"' in r.text
    assert 'name="hidden"' not in r.text  # 새 공지에는 숨김이 없다


def test_공지_등록은_작성자를_로그인_계정으로_쓰고_상세로_간다(
    client: TestClient, fake: FakeDB
) -> None:
    token = _token(client, "/admin/board/notices/new")
    r = client.post(
        "/admin/board/notices",
        data={**_notice(pinned="1", author="해커"), "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/admin/board/notices/{NID}?saved=1"
    ((sql, params, what),) = fake.writes
    assert what == "board.create" and sql.lstrip().startswith("INSERT INTO notice")
    assert params[1:5] == ["새 기능 안내", "update", "검수 화면이 바뀌었어요.", True]
    assert params[-1] == "psj" and "해커" not in params


def test_CSRF_없는_공지_등록은_403_이고_쓰지_않는다(client: TestClient, fake: FakeDB) -> None:
    client.get("/admin/board/notices/new")
    r = client.post("/admin/board/notices", data=_notice())
    assert r.status_code == 403
    assert fake.writes == []
    assert "새 기능 안내" in r.text  # 쓴 내용을 버리지 않는다


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"category": "payment"}, "분류를 골라"),
        ({"title": ""}, "제목을"),
        ({"title": "가" * 201}, "제목을"),
        ({"body": "가" * 5001}, "내용을"),
        ({"starts_on": "2026-11-02", "ends_on": "2026-11-01"}, "시작일이"),
        ({"starts_on": "2026-13-40"}, "날짜를"),
    ],
)
def test_공지_값이_틀리면_422_이고_쓰지_않는다(
    client: TestClient, fake: FakeDB, over: dict, msg: str
) -> None:
    token = _token(client, "/admin/board/notices/new")
    r = client.post("/admin/board/notices", data={**_notice(**over), "csrf_token": token})
    assert r.status_code == 422 and msg in r.text
    assert fake.writes == []


def test_공지를_못_쓰면_503_안내이고_내용을_남긴다(client: TestClient, fake: FakeDB) -> None:
    fake.write_result = ("no_db", [])
    token = _token(client, "/admin/board/notices/new")
    r = client.post("/admin/board/notices", data={**_notice(), "csrf_token": token})
    assert r.status_code == 503
    assert "저장하지 못했어요" in r.text and "새 기능 안내" in r.text


def test_공지_수정_폼은_지금_값으로_차_있고_숨김이_있다(client: TestClient) -> None:
    r = client.get(f"/admin/board/notices/{NID}")
    assert f'action="/admin/board/notices/{NID}"' in r.text
    assert 'value="점검 안내"' in r.text and 'name="hidden"' in r.text
    assert ">삭제</button>" not in r.text  # 삭제 버튼이 없다 — 숨김으로 내린다


def test_공지_숨김은_hidden_at_으로_내린다(client: TestClient, fake: FakeDB) -> None:
    token = _token(client, f"/admin/board/notices/{NID}")
    r = client.post(
        f"/admin/board/notices/{NID}",
        data={**_notice(hidden="1"), "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303
    ((sql, params, what),) = fake.writes
    assert what == "board.update" and "hidden_at = CASE" in sql and "DELETE" not in sql
    assert params[6] is True and params[-1] == NID
    assert "저장했어요" in client.get(r.headers["location"]).text


def test_없는_공지는_404(client: TestClient, fake: FakeDB) -> None:
    fake.write_result = ("db", [])
    token = _token(client, f"/admin/board/notices/{NID}")
    r = client.post("/admin/board/notices/no-such", data={**_notice(), "csrf_token": token})
    assert r.status_code == 404


# ── 문의 ────────────────────────────────────────────────


def _ticket(**over: str) -> dict:
    return {
        "status": "in_progress",
        "priority": "urgent",
        "assignee": "psj",
        "reply": "확인 중이에요.",
        **over,
    }


def test_문의_상세에_답변_폼과_담당자_목록이_있다(client: TestClient) -> None:
    r = client.get(f"/admin/cs/tickets/{TID}")
    assert f'action="/admin/cs/tickets/{TID}"' in r.text
    assert 'name="reply"' in r.text and '<option value="psj"' in r.text and "박수진" in r.text
    assert "board-disabled-form" not in r.text  # 비활성 뼈대가 남지 않았다


def test_문의_답변_저장(client: TestClient, fake: FakeDB) -> None:
    fake.write_result = ("db", [{"id": TID}])
    token = _token(client, f"/admin/cs/tickets/{TID}")
    r = client.post(
        f"/admin/cs/tickets/{TID}", data={**_ticket(), "csrf_token": token}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == f"/admin/cs/tickets/{TID}?saved=1"
    ((sql, params, what),) = fake.writes
    assert what == "cs.update"
    assert params[:4] == ["in_progress", "urgent", "psj", "확인 중이에요."]
    assert params[4] is False and params[5] is False  # 안 닫았으면 파기 기한도 없다


def test_완료는_파기_기한을_같이_잡는다(client: TestClient, fake: FakeDB) -> None:
    fake.write_result = ("db", [{"id": TID}])
    token = _token(client, f"/admin/cs/tickets/{TID}")
    client.post(
        f"/admin/cs/tickets/{TID}",
        data={**_ticket(status="closed", assignee="", reply=""), "csrf_token": token},
    )
    ((sql, params, _),) = fake.writes
    assert "COALESCE(closed_at, now())" in sql and "expires_at" in sql
    assert params[2] == "" and params[3] is None  # 미배정 · 빈 답변은 NULL
    assert params[4] is True and params[5] is True and params[6] == TICKET_RETENTION_DAYS


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"status": "deleted"}, "상태를"),
        ({"priority": "top"}, "우선순위를"),
        ({"assignee": "nobody"}, "담당자를"),
        ({"reply": "가" * (TICKET_TEXT_MAX + 1)}, "답변을"),
    ],
)
def test_문의_값이_틀리면_422_이고_쓰지_않는다(
    client: TestClient, fake: FakeDB, over: dict, msg: str
) -> None:
    token = _token(client, f"/admin/cs/tickets/{TID}")
    r = client.post(f"/admin/cs/tickets/{TID}", data={**_ticket(**over), "csrf_token": token})
    assert r.status_code == 422 and msg in r.text
    assert fake.writes == []


def test_CSRF_없는_문의_저장은_403(client: TestClient, fake: FakeDB) -> None:
    client.get(f"/admin/cs/tickets/{TID}")
    r = client.post(f"/admin/cs/tickets/{TID}", data=_ticket())
    assert r.status_code == 403 and fake.writes == []
    assert "확인 중이에요." in r.text


def test_없는_문의는_404(client: TestClient) -> None:
    r = client.post("/admin/cs/tickets/no-such", data=_ticket())
    assert r.status_code == 404


# ── 로그인 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["/admin/board/notices", f"/admin/board/notices/{NID}", f"/admin/cs/tickets/{TID}"]
)
def test_로그인_없이는_쓰기도_로그인_화면으로(path: str, fake: FakeDB) -> None:  # noqa: ARG001
    app = FastAPI()
    app.include_router(admin_router)
    r = TestClient(app).post(path, data={"title": "x"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert fake.writes == []
