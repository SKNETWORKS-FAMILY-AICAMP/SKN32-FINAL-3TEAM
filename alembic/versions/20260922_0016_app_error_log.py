"""`app_error_log` — WARNING 이상 앱 오류 로그 (2026-09-22 · ssm 요청 · 보안점검 P1-4).

Revision ID: 0016_app_error_log
Revises: 0015_document_annex_no
Create Date: 2026-09-22

🚨 **여기는 DDL 을 직접 적는다** — `0012_app_account` 와 같은 자리다. 런타임 층이고 정본은 `app/models.py` 다 (D-89).
   ⛔ `db/schema.sql` 에 적지 않는다 — 문서 부록 대조 게이트가 거버넌스 층에 런타임 표를 끌고 들어온다.

★ 넣는 쪽은 `app/error_log.py` 의 백그라운드 기록기 하나다 — **마스킹 필터를 지난 문장**과 예외 **클래스 이름**만.
   트레이스백 · 요청 경로 · 사용자 이니셜 · IP 는 **칸 자체가 없다** (요청 §2 「일부러 안 넣는 것」).
🚨 `char_length(message) <= 2000` 은 기록기의 자르기(`settings.ERROR_LOG_MESSAGE_MAX`)와 **같은 수**다 —
   게이트 `test_error_log.py` 가 이 파일의 수와 설정값을 맞댄다.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0016_app_error_log"
down_revision = "0015_document_annex_no"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_error_log",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("logger_name", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("exc_type", sa.String(120)),
        sa.Column("module", sa.String(120)),
        sa.Column("func_name", sa.String(120)),
        sa.Column("lineno", sa.Integer()),
        sa.CheckConstraint(
            "level in ('WARNING','ERROR','CRITICAL')", name="ck_app_error_log_level"
        ),
        sa.CheckConstraint("char_length(message) <= 2000", name="ck_app_error_log_message_len"),
    )
    op.create_index("ix_app_error_log_occurred", "app_error_log", [sa.text("occurred_at DESC")])
    op.create_index(
        "ix_app_error_log_level_occurred", "app_error_log", ["level", sa.text("occurred_at DESC")]
    )
    op.execute(
        "COMMENT ON TABLE app_error_log IS "
        "'WARNING 이상 앱 로그. 마스킹 필터를 지난 값만 들어온다 (보안점검 P1-4). "
        "트레이스백 없음. 보관 90일 (settings.ERROR_LOG_RETENTION_DAYS)'"
    )
    op.execute(
        "COMMENT ON COLUMN app_error_log.exc_type IS "
        "'예외 클래스 이름만. 트레이스백·예외 메시지 원문은 두지 않는다'"
    )


def downgrade() -> None:
    # 🚨 되돌리면 쌓인 오류 기록이 사라진다 — 보관 기간이 지난 것만 지우는 길은 기록기의 파기다.
    op.drop_index("ix_app_error_log_level_occurred", table_name="app_error_log")
    op.drop_index("ix_app_error_log_occurred", table_name="app_error_log")
    op.drop_table("app_error_log")
