-- 0021_chunk_exempt.sql — 적용 제외 목이라는 사실과 그 부모 (2026-09-28 · 팀장 판정 (나) · D-238 개정)
--
-- 🔴 **왜 있는가** — 「다만 … 제외한다」의 하위 목(적용 제외 목)은 **해당하면 위반이 아닌** 경우다. 그런데 이 청크의
--    `context` 가 부모 목의 금지 문장을 통째로 들고 있어(`preprocess/chunk.py` `_annex_context`) 검색이 금지 본문보다
--    제외 목을 먼저 올렸다 — 「이 제품은 암 예방에 좋습니다」 식품 근거 1위가 특수의료용도식품 제외 목이었다(사실원장 ㊷).
--    판정 노드가 그 좌표를 위반 근거로 쓰면 D-238 이 라벨에서 막은 오류가 판정에 그대로 들어간다.
-- ★ 판정 (나) — **제외 목은 검색 결과에 남기되 표시를 달고, 위반 근거 좌표는 부모 목으로 올린다.** 제외 목은 단서 조건으로 따로 나른다.
--    이 칸이 그 표시다. 값은 `preprocess/chunk.py` 가 `preprocess/law_norm.exemption_parents()` 로 계산한다(라벨 게이트와 같은 함수 · D-99).
--
-- 🔴 **재임베딩이 없다** — 임베딩 입력(`context + text`)이 안 바뀐다. 값은 `embed` 가 청크를 다시 실을 때 채운다.
-- 🚨 **NULL 은 「아직 재적재 안 됨」이다.** 빈 문자열(제외 목이 아니다)로 채워 두지 않는다 — 채우면 재적재 전에
--    제외 목이 「제외 목이 아니다」로 읽힌다(0011 의 part_no 와 같은 규칙). 검색은 NULL 인 별표 청크에 위반 근거 좌표를 세우지 않는다.

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS exempt_of TEXT;
ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_exempt;
ALTER TABLE chunk ADD CONSTRAINT ck_chunk_exempt
  CHECK (exempt_of IS NULL OR exempt_of = '' OR doc_type = '별표');

COMMENT ON COLUMN chunk.exempt_of IS
  '적용 제외 목이면 그 목을 제외로 만든 단서 목의 경로(같은 별표 · 본문 구역), 아니면 빈 문자열 (0021 · D-238 개정 (나)). '
  '🚨 NULL 은 「아직 재적재 안 됨」이다 — 「제외 목이 아니다」로 읽지 않는다. 위반 근거 좌표는 이 경로로 올린다.';

-- 🚨 뷰를 다시 만든다 — `SELECT c.*` 는 열 목록을 **생성 시점에** 고정한다(0009). 안 하면 검색이 새 칸을 모른다.
DROP VIEW IF EXISTS v_current_chunk;

CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

COMMENT ON VIEW v_current_chunk IS
  '검색은 항상 현행만 — superseded_at 필터를 잊는 것이 가장 흔한 사고다. '
  '🔴 chunk 에 열을 더하면 이 뷰를 반드시 다시 만든다: SELECT * 는 생성 시점에 고정된다.';
