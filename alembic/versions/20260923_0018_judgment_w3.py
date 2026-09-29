"""`judgment` — 보류 사유 둘 · 품목 출처 칸 · 확정 행 불변식 (2026-09-23 · D-273 · D-276 · D-277).

Revision ID: 0018_judgment_w3
Revises: 0017_ops_tables
Create Date: 2026-09-23

🚨 **여기는 DDL 을 직접 적는다** — `judgment` 는 런타임 층이고 정본은 `app/models.py` 다 (D-89 · 0014 와 같은 자리).
   아래 CHECK 글자는 그 파일의 `CheckConstraint` 와 **같아야 한다** — 고칠 때 둘을 같이 고친다 (D-99).

무엇을 하나
  ① 보류 사유를 넓힌다 — `premise_unknown`(품목은 가렸으나 인정 여부로 등급이 갈림 · D-263 ②) ·
     `law_uncovered`(전용법 품목에서 표시광고법으로 걸린 것이 없음 · D-277)
  ② 품목 출처 칸 `product_category_source` — `classified`(판별) · `user_selected`(재검수 때 사용자가 고름) (D-276)
  ③ 확정 행 불변식 — **위반이 없으면 R0, 있으면 R1 이상** (D-273 결정 2 · 계약 `_confirmed_risk_invariant`)

⛔ **종착(`outcome`)은 여기 없다** — 종착은 DB 에 저장되지 않는다. D-268 이 「0018 에 묶는다」고 적은 것은
   할 일이 없었다 (D-274 맥락 3).

🚨 **GUARD 가 먼저 센다** — 깨는 행이 있으면 **멈춘다.** 지우지도 고치지도 않는다 (D-72 · D-162).
   ① 은 넓히기라 기존 행이 어길 수 없다 — GUARD 가 없다.
   ②·③ 은 **새 제약**이라 기존 행이 어길 수 있다 — 센다.
   그리고 **옛 품목 값 「일반」** 을 센다 — 「일반」은 옛 뜻이 둘이라(D-271 맥락 1) 조용히 새 이름으로 읽으면 안 된다.
   ⬜ `judgment` 표가 비어 있다고 코드 주석(`app/routers/user.py` history)이 적었지만 **재지 않았다** — GUARD 가 잰다.

🚨 **멱등이다** — 칸은 `IF NOT EXISTS`, 제약은 떼었다 다시 건다 (0014 와 같은 어법).
"""

from __future__ import annotations

from alembic import op

revision = "0018_judgment_w3"
down_revision = "0017_ops_tables"
branch_labels = None
depends_on = None

#: 🔴 **정본은 `app/models.py` 의 `CheckConstraint` 다** — 글자가 달라지면 새 DB 와 옮긴 DB 가 갈린다 (D-99).
HOLD_REASONS = (
    "hold_reason IS NULL OR hold_reason in "
    "('low_conf','gap2','cat_unknown','rd1','premise_unknown','law_uncovered')"
)
SOURCE_VALUES = (
    "product_category_source IS NULL OR product_category_source in ('classified','user_selected')"
)
SOURCE_PAIR = "(product_category IS NULL) = (product_category_source IS NULL)"
CONFIRMED_RISK = (
    "verdict <> 'confirmed' OR risk_final IS NULL OR ((violation_type IS NULL) = (risk_final = 0))"
)

#: 🚨 먼저 **깨는 행이 있는지** 본다. ⛔ `ADD CONSTRAINT` 가 그냥 죽으면 「무엇이 왜」가 안 나온다 (D-51).
GUARD = """
DO $$
DECLARE n_old bigint; n_cat bigint; n_risk bigint;
BEGIN
  SELECT count(*) INTO n_old FROM judgment WHERE product_category = '일반';
  IF n_old > 0 THEN
    RAISE EXCEPTION '🔴 옛 품목 값 「일반」 판정이 %건 있다 — 일반상품인지 일반식품인지 옛 뜻이 둘이다 (D-271). '
                    '사람이 판정해 고친 뒤 다시 돌린다', n_old;
  END IF;
  -- 🚨 출처가 **빈** 것만 센다 — 이미 0018 을 지난 DB 의 정상 행(품목 + 출처)으로 재실행이 멈추면 멱등이 깨진다
  SELECT count(*) INTO n_cat FROM judgment
   WHERE product_category IS NOT NULL AND product_category_source IS NULL;
  IF n_cat > 0 THEN
    RAISE EXCEPTION '🔴 품목이 적힌 판정이 %건 있다 — 출처(판별 · 사용자 선택)를 모르는 채로 짝 제약을 걸 수 없다 (D-276). '
                    '출처를 채울 규칙을 정한 뒤 다시 돌린다', n_cat;
  END IF;
  SELECT count(*) INTO n_risk FROM judgment
   WHERE verdict = 'confirmed' AND risk_final IS NOT NULL
     AND (violation_type IS NULL) <> (risk_final = 0);
  IF n_risk > 0 THEN
    RAISE EXCEPTION '🔴 확정 판정 중 위반 유무와 위험도가 어긋난 행이 %건 있다 — '
                    '위반이 없으면 R0, 있으면 R1 이상이다 (D-273)', n_risk;
  END IF;
END $$;
"""

_CHECKS = (
    ("ck_judgment_hold_reason_values", HOLD_REASONS, "보류 사유 여섯 (D-127 · D-263 · D-277)"),
    ("ck_judgment_category_source_values", SOURCE_VALUES, "품목 출처 — 판별 · 사용자 선택 (D-276)"),
    ("ck_judgment_category_source_pair", SOURCE_PAIR, "품목이 있으면 출처가 있다 (D-276)"),
    (
        "ck_judgment_confirmed_risk",
        CONFIRMED_RISK,
        "확정 행 — 위반 없으면 R0, 있으면 R1 이상 (D-273)",
    ),
)


def upgrade() -> None:
    op.execute("ALTER TABLE judgment ADD COLUMN IF NOT EXISTS product_category_source varchar(16)")
    op.execute(GUARD)
    for name, check, note in _CHECKS:
        op.execute(f"ALTER TABLE judgment DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE judgment ADD CONSTRAINT {name} CHECK ({check})")
        op.execute(f"COMMENT ON CONSTRAINT {name} ON judgment IS '{note}'")


def downgrade() -> None:
    # ⛔ 되돌리면 확정 위반이 R0 으로 적히는 길(D-273)과 출처 없는 품목(D-276)이 다시 열린다 — 사람이 판정한다
    raise NotImplementedError(
        "0018 을 되돌리면 확정 행 불변식(D-273)과 품목 출처(D-276)가 풀린다 — 사람이 판정한다."
    )
