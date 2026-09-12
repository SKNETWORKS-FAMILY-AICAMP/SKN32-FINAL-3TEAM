"""`governor` 계정 — 거버넌스 콘솔 로그인 (2026-09-12 밤 · D-66 · D-213).

Revision ID: 0012_app_account
Revises: 0011_chunk_part
Create Date: 2026-09-12

🚨 **여기는 DDL 을 직접 적는다** — 앞의 0008~0011 과 다르다.
   그것들은 **거버넌스 데이터층**(`db/schema.sql` 이 정본)이라 `db/migrations/*.sql` 을 읽어
   실행했다. `app_account` 는 **런타임 층**이고 그쪽 정본은 `app/models.py` 다 (D-89).
   ⛔ 런타임 표를 `db/schema.sql` 에 적으면 **문서 부록 대조 게이트**가 거버넌스 층에
      런타임 표를 끌고 들어온다 — 층이 섞인다.

🔴 **가입 화면이 없으므로 이 표는 비어 있는 채로 뜬다** (D-66 — 온프레미스는 계정 주입).
   계정을 만드는 길은 하나다 —

       uv run python launcher.py admin-add <이니셜>

   ⛔ **기본 계정을 시드하지 않는다.** 시드하면 그 비밀번호가 저장소에 들어가고,
      「나중에 바꾸겠다」는 안 바뀐다.

🔴 `pw_hash` 의 `CHECK` 가 **PHC 접두어를 강제**한다 — `$argon2id$…`.
   보안점검 P1-7 이 *"단순 SHA-256 1회 해시는 부적절"* 이라 적었고,
   **적어 두는 것과 막는 것은 다른 일이다** (D-117).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_app_account"
down_revision = "0011_chunk_part"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_account",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("initials", sa.String(16), nullable=False, unique=True),
        sa.Column("display_name", sa.String(40), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="governor"),
        sa.Column("pw_hash", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role in ('governor')", name="ck_app_account_role"),
        sa.CheckConstraint("pw_hash LIKE '$argon2id$%'", name="ck_app_account_phc"),
    )
    op.create_index("ix_app_account_initials", "app_account", ["initials"])
    op.execute(
        "COMMENT ON TABLE app_account IS "
        "'governor 계정 (D-66 · D-213). 가입 화면 없음 — launcher.py admin-add 로만 만든다'"
    )
    op.execute(
        "COMMENT ON COLUMN app_account.pw_hash IS "
        "'Argon2id PHC 문자열. 알고리즘·파라미터가 값 안에 있다 (OWASP m=19456,t=2,p=1)'"
    )
    op.execute(
        "COMMENT ON COLUMN app_account.initials IS "
        "'docs/<이니셜>/ 과 같은 철자. 명단의 정본은 디스크다 (D-99)'"
    )


def downgrade() -> None:
    # 🚨 되돌리면 **계정이 사라진다.** 접속기록이 가리킬 행도 같이 사라진다 —
    #    운영 중에는 `disabled_at` 을 쓰고 이 경로를 쓰지 않는다.
    op.drop_index("ix_app_account_initials", table_name="app_account")
    op.drop_table("app_account")
