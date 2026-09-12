-- 0011_chunk_part.sql — 쪼갠 조각이라는 사실과, 모델에 들어가는 토큰 수 (2026-09-12 밤)
--
-- 🔴 **왜 있는가** — `docs/02_설계/청크_스키마.md` 의 W1 TODO ③
--    *"리랭커 512 토큰 제한 대응 (긴 조문 분할 규칙)"* 은 **절반만 채워져 있었다.**
--    자르는 쪽(`preprocess/chunk.py` `_split_long`)은 있고 **읽는 쪽이 없다.**
--
--      chunk.py:159      part = "1/3" 을 만든다
--      CHUNK_COLS         없다
--      chunk 테이블       열이 없다
--      _SELECT · Hit      없다
--      화면 · 인용 검증    없다
--
--    ⛔ 그래서 `retrieve.citation()` 이 3분의 1짜리 조각에 **「제18조」**를 단다. 좌표로는
--       맞지만 전문이 아니고, 받는 쪽은 그 차이를 알 방법이 없다. 기획서 5-6 이
--       *"인용 검증은 「존재」가 아니라 「일치」까지"* 라 못 박은 자리가 여기다 (D-199).
--
-- ★ **`citation()` 은 그대로 순수하게 둔다.** 「제18조 (1/3)」처럼 문자열에 섞으면
--   판정 결과의 조문 집합과 대조(기획서 5-6 · 서술층 불변 ②)가 문자열 파싱이 된다.
--   **좌표는 좌표대로, 「일부다」는 옆 칸으로** 낸다.
--
-- 🚨 **1/1 로 채우지 않는다.** DEFAULT 1 을 걸면 이미 들어가 있는 쪼갠 청크 121개가
--    「안 쪼갰다」고 말한다. NULL = 「아직 재적재 안 됨」 — 0008 의 `context` 와 같은 규칙이다.
--
-- 🔴 **두 번째 것 — 재는 축과 쓰는 축을 가른다** (D-200).
--    `ck_chunk_tokens(512)` 는 `token_count` 를 보는데 그것은 `text` 만 센 수다. 0008 이후
--    모델에 들어가는 것은 `embed_input()` = `context` + `text` 다. 기획서 7-3 이
--    *"⚠️ 리랭커 512 토큰 제한 주의"* 라 적은 512 는 **들어가는 쪽**의 수다.
--    ⛔ 그렇다고 CHECK 을 옮기지 않는다 — 리랭커가 아직 미선정이고(v2-m3 0.6B vs base 0.3B를
--       나란히 재기로 했다) **상한이 아직 수가 아니다.** 없는 수로 게이트를 세우면
--       적재가 통째로 막힌다. 지금 하는 것은 **재서 보이게 하는 것**뿐이다.

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS part_no    SMALLINT;
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS part_total SMALLINT;

COMMENT ON COLUMN chunk.part_no IS
  '쪼갠 조각의 번호 (1부터). 700자를 넘는 조문을 문장 경계로 쪼갠 것 — 청크_스키마 TODO ③. '
  '🚨 NULL 은 「아직 재적재 안 됨」이지 「안 쪼갰다」가 아니다. 안 쪼갰으면 1/1 이다 (D-199).';
COMMENT ON COLUMN chunk.part_total IS
  '쪼갠 조각의 총수. part_total > 1 이면 이 청크는 조문의 일부다 — citation() 이 내는 '
  '「제18조」는 좌표로는 맞지만 전문이 아니다. 화면·인용 검증은 이 칸을 보고 말한다 (D-199).';

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS input_token_count SMALLINT;

COMMENT ON COLUMN chunk.input_token_count IS
  '임베딩·리랭커에 실제로 들어가는 문자열(embed_input = context + text)의 토큰 수 (0011). '
  '🚨 상한 CHECK 이 없다 — 리랭커 미선정이라 상한이 아직 수가 아니다. 재고 원장에 올린다 (D-200).';

-- 🔴 한쪽만 선 상태를 막는다 — 「3분의 몇인지 모르는 조각」은 화면이 아무 말도 못 한다.
--    🚨 `NOT VALID` 를 쓰지 않는다. 기존 행은 전부 NULL/NULL 이라 지금 검증해도 통과한다.
ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_part;
ALTER TABLE chunk ADD CONSTRAINT ck_chunk_part CHECK (
    (part_no IS NULL AND part_total IS NULL)
    OR (part_no >= 1 AND part_total >= 1 AND part_no <= part_total)
);

-- 🔄 `ck_chunk_tokens` 의 주석을 **정직하게** 고친다 — 제약 자체는 안 바꾼다.
--    ⛔ 종전 주석은 *"리랭커 bge-reranker-v2-m3 의 512 토큰 상한에 맞춘다"* 였다. 이 CHECK 이
--       보는 `token_count` 는 `text` 만 센 수이므로 그 문장은 **0008 이후로 참이 아니다.**
--       고칠 것은 제약이 아니라 **그것이 무엇을 지킨다고 말하는가**다 (D-170 · D-200).
COMMENT ON CONSTRAINT ck_chunk_tokens ON chunk IS
  '인용 단위(text)의 토큰 상한 512. 🔴 리랭커에 들어가는 것은 input_token_count 이고 '
  '그 상한은 리랭커 모델 선정(기획서 7-3 · v2-m3 0.6B vs base 0.3B) 뒤에 건다 — '
  '지금 이 CHECK 을 그 축의 보증으로 읽지 않는다 (D-200).';

-- 🔄 0010 의 「같은 문자열」을 「같은 토큰열」로 고친다 — 구분자가 다르다(공백 vs 개행)는
--    사실을 재 보지 않고 「같다」고 적었던 자리다. `simple` 파서 기준 토큰열은 같다.
COMMENT ON COLUMN chunk.tsv IS
  '어휘 검색 색인 (0010). context + text — 임베딩 입력과 같은 토큰열이다(구분자만 다르다). '
  '🚨 simple 파서라 조사가 붙어 있다: 질의 쪽에서 조사를 깎고 접두어로 맞춘다 (app/retrieve.py).';

-- 🔴 **`chunk` 에 열을 더했으므로 뷰를 다시 만든다** (0009 가 규칙으로 올리고 D-197 이 게이트로 만든 것).
--    ⛔ 안 하면 `v_current_chunk` 가 `part_no`·`part_total`·`input_token_count` 를 모른 채 남고
--       검색이 통째로 503 이 난다 — 09-12 오전에 `paragraph_no` 로 똑같이 겪었다.
DROP VIEW IF EXISTS v_current_chunk;

CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

COMMENT ON VIEW v_current_chunk IS
  '검색은 항상 현행만 — superseded_at 필터를 잊는 것이 가장 흔한 사고다. '
  '🔴 chunk 에 열을 더하면 이 뷰를 반드시 다시 만든다: SELECT * 는 생성 시점에 고정된다.';
