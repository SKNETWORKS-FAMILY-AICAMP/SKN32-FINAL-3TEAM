-- 0004 · product_fact 적재를 멱등으로 (2026-09-10)
--
-- ⛔ `load_db.load_product_fact` 가 `ON CONFLICT` 없는 순수 INSERT 인데 테이블에
--    UNIQUE 가 없었다(PK 는 BIGSERIAL). **두 번 돌리면 1,250 → 2,500** 이다.
--    그 파일 docstring 은 「멱등이다. 모든 적재가 ON CONFLICT 로 간다」고 적어 뒀다 —
--    여섯 적재기 중 여기만 빠졌고, 문서와 코드가 정면으로 어긋난 자리였다.
-- 🚨 인정번호는 NULL 일 수 있어 키에 못 쓴다 — 원료명 + 문구 + 종류가 한 행을 가른다.
-- 🚨 이미 중복이 들어가 있으면 UNIQUE 를 못 건다. **먼저 지운다** — fact_id 가 큰 쪽을 남긴다.

DELETE FROM product_fact a USING product_fact b
 WHERE a.fact_id < b.fact_id
   AND a.fragment_id = b.fragment_id
   AND a.ingredient = b.ingredient
   AND a.functional_claim = b.functional_claim
   AND a.recog_kind = b.recog_kind;

ALTER TABLE product_fact DROP CONSTRAINT IF EXISTS uq_product_fact;
ALTER TABLE product_fact ADD CONSTRAINT uq_product_fact
  UNIQUE (fragment_id, ingredient, functional_claim, recog_kind);
