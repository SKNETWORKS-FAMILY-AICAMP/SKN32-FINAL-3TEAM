"""`judgment` — 인코더 하한 칸 · 하한은 사전 또는 인코더 (2026-10-16 · D-348 보충 2 · 계약과 같은 규칙).

Revision ID: 0026_judgment_encoder_floor
Revises: 0025_chunk_coord_block
Create Date: 2026-10-16

🚨 **여기는 DDL 을 직접 적는다** — `judgment` 는 런타임 층이고 정본은 `app/models.py` 다 (D-89 · 0014 · 0018 · 0022 와 같은 자리).
   아래 CHECK 글자는 그 파일의 `CheckConstraint` 와 **같아야 한다** — 게이트 `test_0018_의_제약_글자가_모델과_같다` 가 댄다 (D-99).

무엇을 하나
  사전 하한(`risk_floor`)과 인코더 하한(`risk_encoder`)의 칸을 가른다(D-348 보충 2 결정 1). 종전 `ck_judgment_raise_needs_evidence` 는
  「최종을 적으려면 코드 하한이 있어야 한다」라서 인코더만 잡은 보류 문장의 위험도를 받지 못했다 — 하한은 둘 중 하나면 된다.
  ⛔ 하한 없이 최종을 적는 길은 여전히 막는다 · 인코더 하한은 R1 이하 · 보류 문장에만.

🚨 **GUARD 는 두지 않는다** — 새 제약은 새 칸(전부 NULL)만 조이고, 바뀐 제약은 종전보다 넓다. 기존 행이 깨질 수 없다.
🚨 **멱등이다** — 칸은 `IF NOT EXISTS` · 제약은 떼었다 다시 건다 (0014 · 0018 · 0022 와 같은 어법).
"""

from __future__ import annotations

from alembic import op

revision = "0026_judgment_encoder_floor"
down_revision = "0025_chunk_coord_block"
branch_labels = None
depends_on = None

#: 🔴 **정본은 `app/models.py` 의 `CheckConstraint` 다** — 글자가 달라지면 새 DB 와 옮긴 DB 가 갈린다 (D-99).
_CHECKS = (
    (
        "ck_judgment_raise_needs_evidence",
        "risk_final IS NULL"
        " OR ((risk_floor IS NOT NULL OR risk_encoder IS NOT NULL)"
        "     AND (risk_final <= GREATEST(risk_floor, risk_encoder) OR evidence_span IS NOT NULL))",
        "하한(사전 또는 인코더) 위로는 근거 스팬 — D-131 · D-348 보충 2",
    ),
    (
        "ck_judgment_encoder_max",
        "risk_encoder IS NULL OR risk_encoder BETWEEN 0 AND 1",
        "인코더 하한은 기록 상한 R1 이하 — D-348 결정 5",
    ),
    (
        "ck_judgment_final_not_below_encoder",
        "risk_encoder IS NULL OR (risk_final IS NOT NULL AND risk_final >= risk_encoder)",
        "최종 위험도 ≥ 인코더 하한 — 래칫 (D-09 · D-348 보충 2)",
    ),
    (
        "ck_judgment_encoder_hold_only",
        "risk_encoder IS NULL OR verdict = 'hold'",
        "인코더 하한은 보류 문장에만 — D-348 보충 2 결정 3",
    ),
)


def upgrade() -> None:
    op.execute("ALTER TABLE judgment ADD COLUMN IF NOT EXISTS risk_encoder integer")
    op.execute(
        "COMMENT ON COLUMN judgment.risk_encoder IS "
        "'인코더 하한(기록에 들인 값) — 사전 하한 risk_floor 와 칸이 다르다 (D-348 보충 2)'"
    )
    for name, check, note in _CHECKS:
        op.execute(f"ALTER TABLE judgment DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE judgment ADD CONSTRAINT {name} CHECK ({check})")
        op.execute(f"COMMENT ON CONSTRAINT {name} ON judgment IS '{note}'")


def downgrade() -> None:
    # ⛔ 되돌리면 인코더 하한이 적힌 행이 종전 제약(코드 하한 필수)에 걸린다 — 사람이 판정한다
    raise NotImplementedError("0026 을 되돌리면 인코더 하한 행이 갈 곳이 없다 — 사람이 판정한다.")
