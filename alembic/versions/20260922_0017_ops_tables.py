"""운영 표 — `user_account` · `notice` · `terms` · `ticket` · `work_doc.owner_id` FK (D-260 · 2026-09-22).

Revision ID: 0017_ops_tables
Revises: 0016_app_error_log
Create Date: 2026-09-22

🚨 **여기는 DDL 을 직접 적는다** — `0012_app_account` · `0016_app_error_log` 와 같은 자리다. 런타임 층이고 정본은 `app/models.py` 다 (D-89).
   ⛔ `db/schema.sql` 에 적지 않는다 — 문서 부록 대조 게이트가 거버넌스 층에 런타임 표를 끌고 들어온다.
★ `CHECK` 의 값 목록은 `app/models.py` 의 `NOTICE_CATEGORIES` · `TERMS_KINDS` · `TICKET_*` 와 **같은 값**이다 —
   게이트 `test_ops_tables.py` 가 이 파일의 값과 모델의 값을 맞댄다.

⛔ **만들지 않는 것** — `enterprise` · `signup_review` · `signup_review_doc` · 결제 (D-260 ④⑤⑥).
   승인이 켜 줄 권한이 없는 심사(D-66) · 보관 책임을 질 수 없는 신원 서류(D-107 조건 1) · PG 연동(D-69).
🔴 **계정을 시드하지 않는다** — 시드하면 비밀번호가 저장소에 들어간다(D-213). 데모 계정은 가입 화면으로 만든다.

🚨 `work_doc.owner_id` 에 FK 를 걸기 전에 **값이 있는 행을 센다** — 지금까지 가리킬 표가 없었으므로 값이 있으면
   그것은 어디서 왔는지 모르는 값이다. 있으면 **멈춘다**(지우지도 NULL 로 덮지도 않는다 · D-72 · D-162).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0017_ops_tables"
down_revision = "0016_app_error_log"
branch_labels = None
depends_on = None

_NOW = sa.text("now()")
_UUID = sa.text("gen_random_uuid()")


def _id() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=_UUID)


def _ts(name: str, *, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=nullable, server_default=_NOW if now else None
    )


def upgrade() -> None:
    op.create_table(
        "user_account",
        _id(),
        sa.Column("email", sa.String(120), nullable=False),
        sa.Column("pw_hash", sa.String(200), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("org", sa.String(60)),
        _ts("email_verified_at"),
        sa.Column("terms_version", sa.String(20), nullable=False),
        _ts("terms_agreed_at", nullable=False),
        _ts("disclaimer_agreed_at", nullable=False),
        _ts("consent_history_at"),
        _ts("consent_improve_at"),
        _ts("created_at", nullable=False, now=True),
        _ts("last_login_at"),
        _ts("disabled_at"),
        sa.CheckConstraint("pw_hash LIKE '$argon2id$%'", name="ck_user_account_phc"),
        sa.CheckConstraint("email = lower(email)", name="ck_user_account_email_lower"),
        sa.CheckConstraint("position('@' in email) > 1", name="ck_user_account_email_at"),
    )
    op.create_index("ix_user_account_email", "user_account", ["email"], unique=True)

    op.create_table(
        "notice",
        _id(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("app_account.id"), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("starts_on", sa.Date()),
        sa.Column("ends_on", sa.Date()),
        _ts("hidden_at"),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint(
            "category in ('rule_change','system','update')", name="ck_notice_category"
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR starts_on IS NULL OR starts_on <= ends_on", name="ck_notice_period"
        ),
    )

    op.create_table(
        "terms",
        _id(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by", UUID(as_uuid=True), sa.ForeignKey("app_account.id"), nullable=False
        ),
        _ts("created_at", nullable=False, now=True),
        sa.CheckConstraint("kind in ('service','privacy','disclaimer')", name="ck_terms_kind"),
    )
    op.create_index("uq_terms_kind_version", "terms", ["kind", "version"], unique=True)

    op.create_table(
        "ticket",
        _id(),
        sa.Column(
            "requester_id", UUID(as_uuid=True), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(12), nullable=False, server_default="open"),
        sa.Column("assignee_id", UUID(as_uuid=True), sa.ForeignKey("app_account.id")),
        sa.Column("reply", sa.String(2000)),
        _ts("created_at", nullable=False, now=True),
        _ts("closed_at"),
        _ts("expires_at"),
        sa.CheckConstraint(
            "category in ('judge','generate','account','other')", name="ck_ticket_category"
        ),
        sa.CheckConstraint("priority in ('urgent','normal','low')", name="ck_ticket_priority"),
        sa.CheckConstraint("status in ('open','in_progress','closed')", name="ck_ticket_status"),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_ticket_closed_expiry",
        ),
    )
    op.create_index("ix_ticket_requester_id", "ticket", ["requester_id"])
    op.create_index("ix_ticket_expires_at", "ticket", ["expires_at"])
    op.execute(
        "COMMENT ON TABLE ticket IS "
        "'문의. 판정 원문·판정 id 를 담는 칸이 없다 (D-76 열람 경계 · D-260 ③). 닫히면 expires_at 이 파기 키다 (D-129)'"
    )

    # 🚨 FK 전에 센다 — 가리킬 표가 없던 동안 들어간 값은 출처를 모른다. 있으면 멈춘다 (D-72 · D-162)
    n = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM work_doc WHERE owner_id IS NOT NULL"))
        .scalar()
    )
    if n:
        raise RuntimeError(
            f"work_doc.owner_id 에 값이 있는 행이 {n}개다 — user_account 가 없던 동안 들어간 값이라 가리킬 곳이 없다.\n"
            "  🚨 지우거나 NULL 로 덮지 않는다. 어디서 왔는지 먼저 본다:\n"
            "     SELECT id, owner_id, created_at FROM work_doc WHERE owner_id IS NOT NULL;"
        )
    op.create_foreign_key(
        "fk_work_doc_owner_id_user_account", "work_doc", "user_account", ["owner_id"], ["id"]
    )


def downgrade() -> None:
    # 🚨 되돌리면 계정·공지·약관·문의가 사라진다.
    op.drop_constraint("fk_work_doc_owner_id_user_account", "work_doc", type_="foreignkey")
    op.drop_index("ix_ticket_expires_at", table_name="ticket")
    op.drop_index("ix_ticket_requester_id", table_name="ticket")
    op.drop_table("ticket")
    op.drop_index("uq_terms_kind_version", table_name="terms")
    op.drop_table("terms")
    op.drop_table("notice")
    op.drop_index("ix_user_account_email", table_name="user_account")
    op.drop_table("user_account")
