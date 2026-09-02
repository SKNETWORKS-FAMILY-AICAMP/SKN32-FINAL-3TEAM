"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

🚨 `import pgvector` 는 지우지 마십시오 — autogenerate 가 Vector 컬럼을 쓴 마이그레이션을
   만들면 이 import 가 있어야 실행됩니다 (D-84 ⑪).
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector  # noqa: F401  — Vector 컬럼용. 지우지 마십시오
import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
