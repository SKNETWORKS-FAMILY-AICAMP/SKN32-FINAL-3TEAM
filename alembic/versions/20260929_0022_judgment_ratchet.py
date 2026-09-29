"""`judgment` — 최종 위험도는 하한보다 낮을 수 없다 (2026-09-29 · D-09 래칫 · 계약과 같은 규칙).

Revision ID: 0022_judgment_ratchet
Revises: 0021_chunk_exempt
Create Date: 2026-09-29

🚨 **여기는 DDL 을 직접 적는다** — `judgment` 는 런타임 층이고 정본은 `app/models.py` 다 (D-89 · 0014 · 0018 과 같은 자리).
   아래 CHECK 글자는 그 파일의 `CheckConstraint` 와 **같아야 한다** — 게이트 `test_0018_의_제약_글자가_모델과_같다` 가 댄다 (D-99).

무엇을 하나
  계약 `RiskAssessment`(`app/contracts.py`)는 `final < floor` 를 거부하는데(2026-09-21), DB 의 `ck_judgment_raise_needs_evidence` 는
  「하한보다 **높으면** 근거 스팬」만 보아 **하한 R3 · 최종 R0** 을 받았다 — 계약과 DB 가 같은 규칙을 들지 않았다 (D-99).
  ⛔ 인코더는 등급을 내릴 수 없다 (D-09 · D-131).

🚨 **GUARD 가 먼저 센다** — 깨는 행이 있으면 **멈춘다.** 지우지도 고치지도 않는다 (D-72 · D-162).
🚨 **멱등이다** — 제약은 떼었다 다시 건다 (0014 · 0018 과 같은 어법).
"""

from __future__ import annotations

from alembic import op

revision = "0022_judgment_ratchet"
down_revision = "0021_chunk_exempt"
branch_labels = None
depends_on = None

#: 🔴 **정본은 `app/models.py` 의 `CheckConstraint` 다** — 글자가 달라지면 새 DB 와 옮긴 DB 가 갈린다 (D-99).
FINAL_NOT_BELOW_FLOOR = "risk_final IS NULL OR risk_floor IS NULL OR risk_final >= risk_floor"

GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM judgment
   WHERE risk_final IS NOT NULL AND risk_floor IS NOT NULL AND risk_final < risk_floor;
  IF n > 0 THEN
    RAISE EXCEPTION '🔴 최종 위험도가 하한보다 낮은 판정이 %건 있다 — 인코더는 내릴 수 없다 (D-09). '
                    '사람이 판정해 고친 뒤 다시 돌린다', n;
  END IF;
END $$;
"""

_CHECKS = (
    (
        "ck_judgment_final_not_below_floor",
        FINAL_NOT_BELOW_FLOOR,
        "최종 위험도 ≥ 하한 — 래칫 (D-09 · 계약 RiskAssessment)",
    ),
)


def upgrade() -> None:
    op.execute(GUARD)
    for name, check, note in _CHECKS:
        op.execute(f"ALTER TABLE judgment DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE judgment ADD CONSTRAINT {name} CHECK ({check})")
        op.execute(f"COMMENT ON CONSTRAINT {name} ON judgment IS '{note}'")


def downgrade() -> None:
    # ⛔ 되돌리면 최종이 하한 아래로 적히는 길이 다시 열린다 — 사람이 판정한다
    raise NotImplementedError("0022 를 되돌리면 래칫(D-09)이 DB 에서 풀린다 — 사람이 판정한다.")
