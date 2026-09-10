-- 0007 · sanction_rule 2인 확인 강제를 되돌린다 (2026-09-10)
--
-- 🔴 **없던 차단을 만들었던 것을 거둔다.** 0006 이 처음 쓰였을 때 ② 로 들어 있던 항목이다 —
--    `verified_by`·`reviewed_by` 를 NOT NULL 로 바꿔 서명 없이는 적재가 안 되게 했다.
--    ⛔ 종전에도 그 자리는 서명 없이 들어갔다. **막던 것을 고친 게 아니라 새로 막은 것**이다.
--    ★ 2인 확인의 강제 지점은 `collect/registry.py` 하나이고 그건 이미 서 있다 (D-66).
--      같은 원칙을 두 곳에서 서로 다른 세기로 걸면, 약한 쪽이 무시되거나 강한 쪽이 꺼진다.
--
-- 🚨 **왜 0006 을 고치지 않고 새 파일인가** — 0006 은 이미 돌았다(2026-09-10 · 이 기기).
--    돈 마이그레이션의 본문을 고치면 **새 DB 와 옮긴 DB 가 갈린다** — 새 DB 는 0006 을
--    고친 대로 읽고, 이미 옮긴 DB 는 고치기 전 상태로 남는다. 그 차이는 조용하다 (D-99).
--    ⛔ 그래서 되돌리기도 앞으로 나아가는 방향으로만 적는다.
--
-- ✅ 0006 의 나머지 둘(`ck_chunk_tokens` · `ck_judgment_raise_needs_evidence`)은 그대로 둔다.
--    그 둘은 「막는다고 적혀 있는데 널로 우회되던 것」을 고친 것이고, 사람 손이 새로 들지 않는다.

ALTER TABLE sanction_rule DROP CONSTRAINT IF EXISTS ck_sanction_four_eyes;
ALTER TABLE sanction_rule ALTER COLUMN verified_by DROP NOT NULL;
ALTER TABLE sanction_rule ALTER COLUMN reviewed_by DROP NOT NULL;
ALTER TABLE sanction_rule ADD CONSTRAINT ck_sanction_four_eyes
  CHECK (verified_by IS NULL OR reviewed_by IS NULL OR verified_by <> reviewed_by);
