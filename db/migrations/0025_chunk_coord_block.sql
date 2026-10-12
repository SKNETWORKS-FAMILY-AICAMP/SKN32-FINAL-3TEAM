-- 0025_chunk_coord_block.sql — 좌표를 막는 이유 (2026-10-12 · 팀장 판정 · D-293 개정 안건 1 (나))
--
-- 🔴 **왜 있는가** — 인용 좌표는 「경로가 문서 안에 하나뿐 ∧ 형제 순서가 맞을 때」만 선다(D-293 개정). 둘 다 **문서 단위로만**
--    알 수 있어 한 행만 보는 `app/retrieve.py` `citation()` 이 판단할 수 없다(D-293 집행 🚨). 청크 단계가 계산해 이 칸에 싣는다.
--    값 — 빈 문자열(막지 않는다) · 「겹침」(경로가 문서 안에 둘 이상) · 「순서」(형제 번호가 되돌아가거나 빈 번호를 앞 노드가 줄로 안았다).
--    계산 — 별표 `preprocess/law_norm.coord_block` · 산문 행정규칙 `preprocess/law_article.mark_coord_block`(둘 다 `law_norm.order_breaks`).
--    조문형 법령 · 행정규칙은 원천 키가 조 · 항 · 호라 검사하지 않는다(빈 문자열).
--
-- 🔴 **재임베딩이 없다** — 임베딩 입력(`context + text`)이 안 바뀐다. 값은 `embed` 가 청크를 다시 실을 때 채운다.
-- 🚨 **NULL 은 「아직 재적재 안 됨」이다.** 빈 문자열로 채워 두지 않는다 — 채우면 재적재 전에 겹친 경로에 좌표가 선다(0021 과 같은 규칙).
--    검색은 NULL 인 별표 · 산문 청크에 좌표를 세우지 않는다.

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS coord_block TEXT;
ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_coord_block;
ALTER TABLE chunk ADD CONSTRAINT ck_chunk_coord_block
  CHECK (coord_block IS NULL OR coord_block IN ('', '겹침', '순서'));

COMMENT ON COLUMN chunk.coord_block IS
  '좌표를 막는 이유 — 빈 문자열(막지 않는다) · 겹침(경로가 문서 안에 둘 이상) · 순서(형제 순서가 깨졌다) (0025 · D-293 개정). '
  '🚨 NULL 은 「아직 재적재 안 됨」이다 — 「막지 않는다」로 읽지 않는다. 별표 · 산문 좌표는 빈 문자열일 때만 선다.';

-- 🚨 뷰를 다시 만든다 — `SELECT c.*` 는 열 목록을 **생성 시점에** 고정한다(0009). 안 하면 검색이 새 칸을 모른다.
DROP VIEW IF EXISTS v_current_chunk;

CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

COMMENT ON VIEW v_current_chunk IS
  '검색은 항상 현행만 — superseded_at 필터를 잊는 것이 가장 흔한 사고다. '
  '🔴 chunk 에 열을 더하면 이 뷰를 반드시 다시 만든다: SELECT * 는 생성 시점에 고정된다.';
