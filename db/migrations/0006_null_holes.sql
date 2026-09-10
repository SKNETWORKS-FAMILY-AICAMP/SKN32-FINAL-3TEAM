-- 0006 · NULL 로 우회되던 제약 셋을 막는다 (2026-09-10 · D-170 계열)
--
-- 🚨 **실측이다.** postgres 16 에 같은 표현식·같은 널 허용도로 표를 세우고 넣어 봤다 —
--
--    | 제약                              | 넣어 본 행                          | 결과   |
--    |-----------------------------------|-------------------------------------|--------|
--    | ck_chunk_tokens                   | 900자 청크, token_count 널          | **통과** |
--    | ck_judgment_raise_needs_evidence  | 하한 널 + 위험도 4 + 근거 스팬 없음 | **통과** |
--
--    셋 다 표현식이 `X IS NULL OR …` 로 시작한다. SQL 의 CHECK 는 **FALSE 일 때만** 막는데,
--    NULL 이 섞이면 식이 NULL 로 접히고 NULL 은 통과다. 「막는다」고 적혀 있으나 막지 않았다.
--
-- ✅ **대조군이 같은 스키마 안에 있다.** `ck_source_four_eyes` 와 `ck_segment_k_anon` 은
--    컬럼이 NOT NULL 이라 우회로가 없다 — 같은 원칙을 옳게 건 자리다. 그 모양을 따른다.
--    ★ 규칙: **널이면 안 되는 것은 CHECK 가 아니라 NOT NULL 로 막는다.**
--       CHECK 는 「값들 사이의 관계」만 본다. 「값이 있는가」는 CHECK 의 일이 아니다.
--
-- 🔴 `ck_sanction_four_eyes` 는 **손대지 않는다.** 그 자리는 널 우회가 있는 것이 맞다 —
--    종전에도 서명 없이 들어갔고, 여기서 NOT NULL 을 걸면 **없던 차단을 새로 만드는 것**이다.
--    2인 확인의 강제 지점은 `collect/registry.py` 하나이고 그건 이미 서 있다 (D-66).
-- 🚨 `chunk` 는 0행이라 SET NOT NULL 이 안전하다. 적재가 시작된 뒤에는 못 돈다.

-- ── ① chunk.token_count — 리랭커 512 토큰 상한 ─────────────────────────
--    ⛔ 종전 `token_count IS NULL OR token_count <= 512` 는 **칸을 안 채우면 무제한**이었다.
--       `scripts/embed.py` 가 채우도록 이미 고쳐졌지만, 그건 **적재기가 지키는 규칙**이지
--       DB 가 지키는 규칙이 아니다. 다른 경로로 들어오면 그대로 뚫린다.
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM chunk WHERE token_count IS NULL;
  IF n > 0 THEN
    RAISE EXCEPTION '🔴 chunk.token_count 가 빈 행이 %건 있다 — 먼저 채운다: uv run python -m scripts.embed', n;
  END IF;
END $$;

ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_tokens;
ALTER TABLE chunk ALTER COLUMN token_count SET NOT NULL;
ALTER TABLE chunk ADD CONSTRAINT ck_chunk_tokens CHECK (token_count <= 512);
COMMENT ON CONSTRAINT ck_chunk_tokens ON chunk IS
  '리랭커(bge-reranker-v2-m3) 512 토큰 상한. 널 우회를 막기 위해 컬럼이 NOT NULL 이다 (0006).';

-- ── ③ judgment — 근거 없는 위험도 상향 (D-131) ────────────────────────
--    ⛔ 종전 `risk_final IS NULL OR risk_floor IS NULL OR risk_final <= risk_floor
--       OR evidence_span IS NOT NULL` 은 **하한만 비우면** 근거 없이 R4 를 적을 수 있었다.
--       상향의 정의가 「하한보다 높다」인데, 하한이 없으면 상향이 정의되지 않아 무조건 통과다.
--    ★ 새 뜻 — **최종 위험도를 적으려면 하한이 반드시 있어야 하고**, 하한보다 높으면
--       근거 스팬이 있어야 한다. 위험도를 안 적는 경우(verdict='unjudged' 등)는 그대로 통과.
--    🚨 `risk_final` 을 NOT NULL 로 하지 않는 이유 — 판정이 실패하거나 보류되면 위험도가
--       없는 것이 정상이다. 여기서는 「없음」이 뜻을 가진다. ①② 와 다르다.
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM judgment
   WHERE risk_final IS NOT NULL
     AND (risk_floor IS NULL OR (risk_final > risk_floor AND evidence_span IS NULL));
  IF n > 0 THEN
    RAISE EXCEPTION '🔴 근거 없이 위험도가 적힌 판정이 %건 있다 — 그 행을 먼저 본다 (D-131)', n;
  END IF;
END $$;

ALTER TABLE judgment DROP CONSTRAINT IF EXISTS ck_judgment_raise_needs_evidence;
ALTER TABLE judgment ADD CONSTRAINT ck_judgment_raise_needs_evidence
  CHECK (risk_final IS NULL
         OR (risk_floor IS NOT NULL
             AND (risk_final <= risk_floor OR evidence_span IS NOT NULL)));
COMMENT ON CONSTRAINT ck_judgment_raise_needs_evidence ON judgment IS
  '위험도 상향은 근거 스팬이 있을 때만 (D-131). 최종을 적으려면 하한이 있어야 한다 (0006).';
