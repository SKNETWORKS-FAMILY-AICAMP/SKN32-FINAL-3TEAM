"""골든셋 타입 정정 — violation_t 를 라벨로, split_t 에 test_sentence (D-178).

Revision ID: 0003_golden_labels
Revises: 6c1f5f12e174
Create Date: 2026-09-10

──────────────────────────────────────────────────────────────
🚨 **DDL 을 여기 적지 않는다** — `db/migrations/0003_golden_labels.sql` 을 읽어 실행한다 (D-99).
   0001 과 같은 규약이다. 파라미터 없이 드라이버 커서로 보낸다 (`%` 문제).

무엇을 옮기나
  ① `violation_t` 'V0'~'V8' → 우리 라벨 10종. 뜻이 스키마 어디에도 없었고 경쟁안이 둘이었다.
  ② `split_t` 에 `test_sentence` — 없어서 골든셋 1,908행이 DB 밖에 서 있었다.
  ③ `ck_golden_injected_not_holdout` — `test_holdout` 만 막아 **어떤 행에도 안 걸렸다.**
  ④ `golden_sample.risk` NOT NULL 해제 — 시험지는 위험도를 담는 곳이 아니다 (D-09).
  ⑤ `violation_article` — 라벨 ↔ 조문 대응은 타입이 아니라 데이터다 (D-158 · D-110).

🔴 **되돌리기는 없다.** 'V0'~'V8' 로 되돌리면 5종이 2칸으로 뭉개져 라벨이 복원되지 않는다.
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "0003_golden_labels"
down_revision = "6c1f5f12e174"
branch_labels = None
depends_on = None

SQL = pathlib.Path(__file__).resolve().parents[2] / "db" / "migrations" / "0003_golden_labels.sql"


def _run(sql: str) -> None:
    raw = op.get_bind().connection
    raw = getattr(raw, "driver_connection", raw)
    with raw.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    if not SQL.exists():
        raise FileNotFoundError(f"{SQL} 가 없다 — 이 마이그레이션의 본문이다")
    _run(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError(
        "되돌릴 수 없다 — 'V0'~'V8' 로 접으면 5종이 2칸으로 뭉개져 라벨이 복원되지 않는다 (D-178)."
    )
