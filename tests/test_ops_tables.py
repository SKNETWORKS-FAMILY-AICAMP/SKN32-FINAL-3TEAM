"""운영 표와 사용자 세션 — 🆕 2026-09-22 (D-260 · 마이그레이션 0017).

★ 재는 것 —
  ① 표의 `CHECK` 값 목록 = 모델의 목록(한 벌 · D-99) · 문의 상한 = 설정값
  ② 🔴 **넣지 않기로 한 칸이 없다** — 회원 유형·역할·채널·팔로워·요금제·상태(D-66 · D-68 · D-69 · D-180) ·
     문의에 판정·문장을 가리키는 칸(D-76 열람 경계)
  ③ 🔴 **만들지 않기로 한 표가 없다** — `enterprise` · `signup_review` · `signup_review_doc` (D-260 ④⑤)
  ④ `work_doc.owner_id` → `user_account.id`
  ⑤ 🔴 **사용자 세션으로 관리자 문을 못 연다** — 반대도 마찬가지 (D-260 6-3 (가))
  ⑥ (DB 있을 때만 · `COPYLANE_DB_IT=1`) 대문자 이메일 · 기한 없이 닫힌 문의를 DB 가 거절한다
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

from app import models as m
from app.settings import TICKET_TEXT_MAX

ROOT = Path(__file__).resolve().parents[1]
_MIGRATION = (ROOT / "alembic" / "versions" / "20260922_0017_ops_tables.py").read_text(
    encoding="utf-8"
)


def _check_values(name: str) -> tuple[str, ...]:
    """마이그레이션의 `CHECK (… in (…))` 에서 값 목록."""
    hit = re.search(r'"(\w+) in \(([^)]*)\)",\s*name="' + name + '"', _MIGRATION)
    assert hit, f"🔴 마이그레이션에 {name} 가 없다"
    return tuple(re.findall(r"'(\w+)'", hit.group(2)))


@pytest.mark.gate
@pytest.mark.parametrize(
    ("check", "values"),
    [
        ("ck_notice_category", m.NOTICE_CATEGORIES),
        ("ck_terms_kind", m.TERMS_KINDS),
        ("ck_ticket_category", m.TICKET_CATEGORIES),
        ("ck_ticket_priority", m.TICKET_PRIORITIES),
        ("ck_ticket_status", m.TICKET_STATUSES),
    ],
)
def test_마이그레이션_값_목록이_모델과_같다(check: str, values: dict[str, str]) -> None:
    assert _check_values(check) == tuple(values), f"🔴 {check} — 마이그레이션과 모델이 어긋난다"


@pytest.mark.gate
def test_문의_상한이_설정값과_같다() -> None:
    assert _MIGRATION.count(f"sa.String({TICKET_TEXT_MAX})") == 2, (
        "🔴 body·reply 상한 ≠ TICKET_TEXT_MAX"
    )
    assert m.Ticket.__table__.c.body.type.length == TICKET_TEXT_MAX


_FORBIDDEN_USER_COLS = {"type", "role", "member_type", "channel", "followers", "plan", "status"}


@pytest.mark.gate
def test_사용자_계정에_넣지_않기로_한_칸이_없다() -> None:
    """🔴 역할 신고를 받으면 「진짜인가」 검증이 생긴다(D-66) · 채널·팔로워는 식별 가능성(D-68 · D-180) · 결제 없음(D-69)."""
    cols = set(m.UserAccount.__table__.c.keys())
    assert not cols & _FORBIDDEN_USER_COLS, f"🔴 넣지 않기로 한 칸 — {cols & _FORBIDDEN_USER_COLS}"


@pytest.mark.gate
def test_문의는_판정이나_문장을_가리키지_않는다() -> None:
    """🔴 관리자가 문의를 통해 사용자 문구를 보는 길이 생기면 D-76 열람 경계가 뚫린다 (D-260 ③)."""
    t = m.Ticket.__table__
    targets = {fk.column.table.name for fk in t.foreign_keys}
    assert targets <= {"user_account", "app_account"}, f"🔴 문의가 다른 표를 가리킨다 — {targets}"
    suspicious = [
        c
        for c in t.c.keys()  # noqa: SIM118 — 열 이름 목록
        if re.search(r"judg|sentence|copy|doc|verdict", c)
    ]
    assert not suspicious, f"🔴 판정·문장을 담을 칸 — {suspicious}"


@pytest.mark.gate
def test_만들지_않기로_한_표가_없다() -> None:
    """🔴 승인이 켜 줄 권한이 없는 심사(D-66) · 보관 책임을 질 수 없는 신원 서류(D-107 조건 1) (D-260 ④⑤)."""
    closed = {"enterprise", "signup_review", "signup_review_doc", "payment", "member"}
    tables = set(m.Base.metadata.tables)
    assert not tables & closed, f"🔴 만들지 않기로 한 표 — {tables & closed}"
    created = set(re.findall(r'create_table\(\s*"(\w+)"', _MIGRATION))
    assert created == {"user_account", "notice", "terms", "ticket"}, (
        f"🔴 0017 이 만드는 표 — {created}"
    )


@pytest.mark.gate
def test_작업문서_소유자는_사용자_계정을_가리킨다() -> None:
    fks = {fk.target_fullname for fk in m.WorkDoc.__table__.c.owner_id.foreign_keys}
    assert fks == {"user_account.id"}, f"🔴 work_doc.owner_id 의 FK — {fks}"


# ── ⑤ 세션 ──────────────────────────────────────────────────


@pytest.mark.gate
def test_사용자_세션은_관리자_세션으로_읽히지_않는다() -> None:
    from app import auth  # noqa: PLC0415

    uid = uuid.uuid4()
    user_tok = auth.issue_user_session(uid)
    admin_tok = auth.issue_session("ohb")
    assert auth.read_user_session(user_tok) == uid
    assert auth.read_session(admin_tok) == "ohb"
    assert auth.read_session(user_tok) is None, "🔴 사용자 세션이 관리자 세션으로 읽혔다"
    assert auth.read_user_session(admin_tok) is None, "🔴 관리자 세션이 사용자 세션으로 읽혔다"
    assert auth.USER_SESSION_COOKIE != auth.SESSION_COOKIE


@pytest.mark.gate
def test_사용자_세션_위조와_접두어_이니셜을_거절한다() -> None:
    from app import auth  # noqa: PLC0415

    tok = auth.issue_user_session(uuid.uuid4())
    subject, exp, sig = tok.split(".")
    forged = f"{auth.USER_PREFIX}{uuid.uuid4()}.{exp}.{sig}"
    assert auth.read_user_session(forged) is None, "🔴 서명을 안 본다"
    with pytest.raises(ValueError):
        auth.issue_session(f"{auth.USER_PREFIX}x")


@pytest.mark.gate
def test_사용자_쿠키를_관리자_자리에_넣어도_관리자_화면이_안_뜬다() -> None:
    """🔴 **응답을 받아 본다** (D-170) — 함수가 거절하는 것과 문이 막히는 것은 다른 일이다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app import auth  # noqa: PLC0415
    from app.api import app  # noqa: PLC0415

    client = TestClient(app)
    client.cookies.set(auth.SESSION_COOKIE, auth.issue_user_session(uuid.uuid4()))
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code == 303 and r.headers.get("location") == "/login", (
        f"🔴 사용자 세션으로 관리자 화면이 떴다 — {r.status_code}"
    )


# ── ⑥ 실제 DB (선택) ─────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("COPYLANE_DB_IT") != "1", reason="실제 DB 에 쓴다 — COPYLANE_DB_IT=1 일 때만"
)
def test_DB_가_규칙을_거절한다() -> None:
    import psycopg  # noqa: PLC0415

    from app.auth import hash_password  # noqa: PLC0415
    from app.db import pg_connect  # noqa: PLC0415

    ph = hash_password("x" * 12)
    base = (
        "INSERT INTO user_account (email, pw_hash, name, terms_version, terms_agreed_at, disclaimer_agreed_at) "
        "VALUES (%s, %s, 'n', 'v1', now(), now()) RETURNING id"
    )
    # 🚨 바깥 트랜잭션 하나 안에서 재고 **되돌린다** — psycopg 의 `transaction()` 은 바깥이 없으면 커밋한다(실측: 행이 남았다)
    with pg_connect() as conn, conn.cursor() as cur, conn.transaction() as outer:
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            cur.execute(base, ("Upper@example.com", ph))
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            cur.execute(base, ("lower@example.com", "sha256$abc"))
        with conn.transaction():
            cur.execute(base, ("it-ops@example.com", ph))
            uid = cur.fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            cur.execute(
                "INSERT INTO ticket (requester_id, category, title, body, status, closed_at) "
                "VALUES (%s, 'other', 't', 'b', 'closed', now())",
                (uid,),
            )
        raise psycopg.Rollback(outer)
