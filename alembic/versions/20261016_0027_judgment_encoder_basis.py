"""`judgment` — 인코더 하한에는 근거 호가 적혀 있다 (2026-10-16 · D-348 보충 2 결정 8 · 계약과 같은 규칙).

Revision ID: 0027_judgment_encoder_basis
Revises: 0026_judgment_encoder_floor
Create Date: 2026-10-16

🚨 **여기는 DDL 을 직접 적는다** — `judgment` 는 런타임 층이고 정본은 `app/models.py` 다 (D-89 · 0022 · 0026 과 같은 자리).
   아래 CHECK 글자는 그 파일의 `CheckConstraint` 와 **같아야 한다** — 게이트 `test_0018_의_제약_글자가_모델과_같다` 가 댄다 (D-99).

무엇을 하나
  0026 은 인코더 하한(`risk_encoder`)을 받게 했지만 그 근거(대응표의 호)는 적지 않았다 — 이력만 보고는 R1 이 어디서 왔는지 모른다.
  저장된 등급마다 근거가 남아야 한다(D-224 · D-131 이 근거 스팬 없는 상향을 막은 것과 같은 자리). 근거는 `evidence.encoder_refs` 다.

🚨 **GUARD 가 먼저 센다** — 인코더 하한이 있는데 근거가 없는 행이 있으면 **멈춘다.** 지우지도 고치지도 않는다 (D-72 · D-162).
🚨 **멱등이다** — 제약은 떼었다 다시 건다.
"""

from __future__ import annotations

from alembic import op

revision = "0027_judgment_encoder_basis"
down_revision = "0026_judgment_encoder_floor"
branch_labels = None
depends_on = None

#: 🔴 **정본은 `app/models.py` 의 `CheckConstraint` 다** — 글자가 달라지면 새 DB 와 옮긴 DB 가 갈린다 (D-99).
_CHECKS = (
    (
        "ck_judgment_encoder_has_basis",
        "risk_encoder IS NULL OR COALESCE(jsonb_array_length(evidence -> 'encoder_refs'), 0) > 0",
        "인코더 하한에는 근거 호(evidence.encoder_refs)가 있다 — D-348 보충 2 결정 8 · D-224",
    ),
)

GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM judgment
   WHERE risk_encoder IS NOT NULL
     AND COALESCE(jsonb_array_length(evidence -> 'encoder_refs'), 0) = 0;
  IF n > 0 THEN
    RAISE EXCEPTION '🔴 인코더 하한이 있는데 근거 호가 없는 판정이 %건 있다 (D-348 보충 2 결정 8). '
                    '사람이 판정해 고친 뒤 다시 돌린다', n;
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(GUARD)
    for name, check, note in _CHECKS:
        op.execute(f"ALTER TABLE judgment DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE judgment ADD CONSTRAINT {name} CHECK ({check})")
        op.execute(f"COMMENT ON CONSTRAINT {name} ON judgment IS '{note}'")


def downgrade() -> None:
    for name, _, _ in _CHECKS:
        op.execute(f"ALTER TABLE judgment DROP CONSTRAINT IF EXISTS {name}")
