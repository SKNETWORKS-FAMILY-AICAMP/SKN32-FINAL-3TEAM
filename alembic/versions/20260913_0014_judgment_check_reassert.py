"""`judgment` 의 D-131 제약을 다시 건다 — `stamp` 로 0006 을 건너뛴 DB 를 위해 (2026-09-13 · D-221).

Revision ID: 0014_judgment_check_reassert
Revises: 0013_risk_lookup_four_eyes
Create Date: 2026-09-13

🚨 **여기는 DDL 을 직접 적는다** — `judgment` 는 **런타임 층**이고 그쪽 정본은 `app/models.py` 다
   (D-89 · 0012 와 같은 이유). `db/migrations/*.sql` 은 거버넌스 층의 자리다.

🔴 **왜 필요한가 — 사람이 손으로 고치게 두지 않는다** (D-117 · 0009 의 규칙).

   2026-09-13 의 빈 DB 버그(D-221) 때문에 팀원이 `alembic stamp 0011_chunk_part` 로 우회했다.
   그 판단의 근거 — *「0003~0011 은 거버넌스 delta 라 `db/schema.sql` 에 이미 있다」* — 는
   **아홉 중 여덟에 대해 맞았다.** ⛔ **`0006` 만 아니었다.**

   `0006` 은 거버넌스 마이그레이션인데 **런타임 표 `judgment` 에도 제약을 건다.**
   `db/schema.sql` 은 런타임 층을 안 담으므로(D-89) **그 부분만 새 DB 에 없다.**
   실측: 그 DB 의 제약은 **0006 이전의 약한 판**이었다 —

       약한 판   risk_final IS NULL OR risk_floor IS NULL
                 OR risk_final <= risk_floor OR evidence_span IS NOT NULL
       강한 판   risk_final IS NULL
                 OR (risk_floor IS NOT NULL
                     AND (risk_final <= risk_floor OR evidence_span IS NOT NULL))

   ⛔ 약한 판은 **`risk_floor` 가 NULL 이면 통과한다** — **코드 하한 없이 최종 위험도를 적을 수
   있다.** D-09 래칫이 막으려던 것이고 0006 이 *「널로 우회되던 제약」* 이라 부른 그 구멍이다.

★ **채팅으로 절차를 알려 주지 않는다.** 명령 넉 줄을 사람이 손으로 치게 하면
  ① 저장소에 안 남고 ② 다음 사람이 또 물어야 하고 ③ 순서를 틀린다
  (실제로 첫 절차가 틀렸다 — `stamp 0013` 으로 끝내면 `v_risk_lookup` 이 옛 정의로 남는다).
  **`git pull` + `migrate` 하나로 낫게 한다.** 그것이 마이그레이션이 있는 이유다.

🚨 **멱등이다** (D-221) — 이미 강한 판인 DB 에서는 같은 것을 떼었다 다시 건다.
⬜ **여기서 안 고치는 것** (D-188) — `stamp` 로 건너뛴 `COMMENT` 넷은 안 되돌린다.
   DB 안의 설명이라 **읽는 사람이 없다.** 고칠 자리는 `db/schema.sql` 쪽이고 별건이다.
"""

from __future__ import annotations

from alembic import op

revision = "0014_judgment_check_reassert"
down_revision = "0013_risk_lookup_four_eyes"
branch_labels = None
depends_on = None

#: 🔴 **정본은 `app/models.py` 의 `CheckConstraint` 다.** 여기 글자가 그것과 달라지면
#:    새 DB(모델에서 나온 것)와 옮긴 DB 가 갈린다 — 고칠 때 둘을 같이 고친다 (D-99).
CHECK = (
    "risk_final IS NULL"
    " OR (risk_floor IS NOT NULL"
    "     AND (risk_final <= risk_floor OR evidence_span IS NOT NULL))"
)

#: 🚨 먼저 **깨는 행이 있는지** 본다 — 0006 과 같은 어법이다.
#:    ⛔ `ADD CONSTRAINT` 가 그냥 죽으면 「무엇이 왜」가 안 나온다 (D-51).
GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM judgment
   WHERE risk_final IS NOT NULL
     AND (risk_floor IS NULL OR (risk_final > risk_floor AND evidence_span IS NULL));
  IF n > 0 THEN
    RAISE EXCEPTION '🔴 근거 없이 위험도가 적힌 판정이 %건 있다 — 그 행을 먼저 본다 (D-131). '
                    '이 제약은 0006 이 걸었어야 했는데 stamp 로 건너뛴 DB 에는 없다 (D-221)', n;
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(GUARD)
    op.execute("ALTER TABLE judgment DROP CONSTRAINT IF EXISTS ck_judgment_raise_needs_evidence")
    op.execute(
        f"ALTER TABLE judgment ADD CONSTRAINT ck_judgment_raise_needs_evidence CHECK ({CHECK})"
    )
    op.execute(
        "COMMENT ON CONSTRAINT ck_judgment_raise_needs_evidence ON judgment IS "
        "'위험도 상향은 근거 스팬이 있을 때만 (D-131). 최종을 적으려면 하한이 있어야 한다 (0006).'"
    )


def downgrade() -> None:
    # ⛔ 되돌리면 **널로 우회하는 길이 다시 열린다.** 0006 이 막은 것을 여는 것이라
    #    자동으로 조용히 하지 않는다 (0013 과 같은 판단).
    raise NotImplementedError(
        "0014 를 되돌리면 risk_floor 없이 최종 위험도를 적는 길이 다시 열린다 (D-131) — "
        "사람이 판정한다."
    )
