-- 0009_view_refresh.sql — 0008 이 더한 열을 뷰가 못 보고 있었다 (2026-09-12)
--
-- 🔴 **PostgreSQL 은 뷰의 `SELECT c.*` 를 생성 시점에 열 목록으로 전개해 고정한다.**
--    0008 이 `chunk` 에 `context`·`paragraph_no` 를 더했지만 `v_current_chunk` 는
--    **그 열을 모른 채 남았다.** 그래서 검색이 통째로 503 이 났다 —
--        column c.paragraph_no does not exist
--
-- ⛔ **게이트 193 이 이것을 못 잡았다.** 정적 검사는 질의 문자열만 보고, 재임베딩은
--    `chunk` 를 직접 써서 뷰를 안 지난다. **실제 질의 한 번이 잡았다** (D-146 의 다른 문).
--
-- ⚠️ **새 DB 는 멀쩡했다.** `db/schema.sql` 로 만들면 뷰가 새 열을 포함한 채 생긴다.
--    갈린 것은 **이미 돌아가던 DB 뿐**이다 — 0007 이 *「새 DB 와 옮긴 DB 가 갈린다」*고
--    경고한 바로 그 모양이고, 그래서 0008 을 고치지 않고 **앞으로 나아가는 방향**으로 적는다.
--
-- ★ 규칙으로 올린다 — **`chunk` 에 열을 더하는 마이그레이션은 이 뷰를 같이 다시 만든다.**
--   `tests/test_db_schema.py` 가 그 순서를 검사한다. 사람이 기억할 일로 두지 않는다.

DROP VIEW IF EXISTS v_current_chunk;

-- 🚨 `c.*` 를 그대로 둔다. 열을 손으로 나열하면 `chunk` 정의와 **두 벌**이 되고,
--    그건 이 사고보다 조용한 사고다 (D-99). 대신 다시 만드는 것을 검사로 강제한다.
CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

COMMENT ON VIEW v_current_chunk IS
  '검색은 항상 현행만 — superseded_at 필터를 잊는 것이 가장 흔한 사고다. '
  '🔴 chunk 에 열을 더하면 이 뷰를 반드시 다시 만든다: SELECT * 는 생성 시점에 고정된다.';
