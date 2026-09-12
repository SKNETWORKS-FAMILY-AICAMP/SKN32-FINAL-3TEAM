-- 0010_chunk_tsv.sql — 어휘 검색(BM25 자리)의 색인 (2026-09-12 오후 · D-193 · D-194)
--
-- 왜 있는가 — 2026-09-12 실측: 광고 문구 세 건으로 벡터 단독 검색을 재니 정답 조문이
--   각각 **6위 · 19위 · 50위 밖**이었다. 순위가 **질의와 조문의 어휘 겹침 순서 그대로**였다.
--   벡터는 「3배 빠른 효과 ⊂ 부당하게 비교하는 표시·광고」 같은 **포섭** 관계를 못 세운다.
--   D-77 의 예산표는 이미 「BM25 + 벡터」로 적혀 있었다 — 한 층만 짓고 다섯 층의 성능을 쟀다.
--
-- 🚨 **형태소 분석기를 안 쓴다 — 빠뜨린 것이 아니라 판정이다** (D-194).
--    mecab-ko 를 넣으려면 PostgreSQL 이미지를 갈아야 하는데 스택 핀이
--    `pgvector/pgvector:0.8.6-pg16-bookworm` 이다. 이미지를 갈면 pgvector 버전이 같이 흔들린다.
--    `simple` 파서는 공백으로만 자르므로 조사가 붙어 온다. 그 값은 `app/retrieve.py` 가
--    **질의 쪽에서** 메운다 — 조사 깎기 + 접두어(`:*`) 매칭. ⬜ 근사이고, 그 사실을 적어 둔다.
--
-- 🔴 **표현식 인덱스가 아니라 생성열이다.** 표현식 인덱스로 두면 질의가 똑같은
--    `to_tsvector('simple', ...)` 를 다시 적어야 인덱스를 타고, 한쪽만 고치면
--    **결과는 맞는데 조용히 느려진다** — 틀린 것보다 찾기 어렵다 (D-99).
--    정의는 여기 한 줄뿐이고 `app/retrieve.py` 는 `c.tsv` 만 본다.
--
-- 🚨 `context` 를 같이 담는다 — **임베딩이 본 것과 같은 문자열**이다 (`scripts/embed.py`
--    `embed_input()`). 두 갈래가 서로 다른 텍스트를 보면 순위를 섞는 뜻이 없다.

ALTER TABLE chunk
  ADD COLUMN IF NOT EXISTS tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', coalesce(context, '') || ' ' || text)) STORED;

COMMENT ON COLUMN chunk.tsv IS
  '어휘 검색 색인 (0010). context + text — 임베딩 입력과 같은 문자열이다. '
  '🚨 simple 파서라 조사가 붙어 있다: 질의 쪽에서 조사를 깎고 접두어로 맞춘다 (app/retrieve.py).';

CREATE INDEX IF NOT EXISTS ix_chunk_tsv ON chunk USING GIN (tsv);

-- 🔴 **`chunk` 에 열을 더했으므로 뷰를 다시 만든다** (0009 가 규칙으로 올린 것).
--    ⛔ 안 하면 `v_current_chunk` 가 `tsv` 를 모른 채 남고 검색이 통째로 503 이 난다 —
--       2026-09-12 오전에 `paragraph_no` 로 똑같이 겪었다. 게이트가 이 순서를 검사한다.
DROP VIEW IF EXISTS v_current_chunk;

CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

COMMENT ON VIEW v_current_chunk IS
  '검색은 항상 현행만 — superseded_at 필터를 잊는 것이 가장 흔한 사고다. '
  '🔴 chunk 에 열을 더하면 이 뷰를 반드시 다시 만든다: SELECT * 는 생성 시점에 고정된다.';
