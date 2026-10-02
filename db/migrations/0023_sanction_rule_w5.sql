-- 0023_sanction_rule_w5.sql — 제재표 행에 **행 열쇠 · 별표1 목 · 덮음 · 원문 인용 · 사실 칸 · 판 sha** (2026-10-02 · W5 · D-305 · D-309 · D-310)
--
-- 🔴 **왜 있는가** — 하한 원천은 서명된 `scripts/sanction_review.yaml` 이고 적재기(`scripts/load_db.py` `load_sanction_rule`)가
--    이 표에 싣는다. 식품 4~7호는 유형이 아니라 **[별표 1] 목**으로 하한이 갈리고(D-310), 목을 일부만 덮는 행은 하한이 아니라
--    **가능 상한**이다(D-310 개정 2). 그 판단에 쓰는 칸이 표에 없으면 판정 그래프가 서명한 표와 **다른 규칙**으로 하한을 낸다 (D-99).
-- ★ 규칙은 `app/sanction.py` `floor_rows` 한 곳이다 — 원천 검사(yaml)와 판정 그래프(이 표의 뷰)가 **같은 열쇠**의 행을 넘긴다.
--
-- 🚨 **NULL 의 뜻** — `annex1` NULL 은 「목으로 갈리지 않는 행」이고 빈 배열은 「목 칸이 빈 행(고시로 닿는다)」이다. 둘을 합치지 않는다.
--    `rule_key` NULL 은 이 마이그레이션 전에 들어온 행이다 — 지금 0행이라 없다. ⛔ 「0행이라 안전하다」가 이유는 아니다(0013).
-- 🚨 **위험도 칸(`risk_level`)의 값은 적재기가 처분 종류에서 계산해 넣는다**(`KIND_RISK`) — 이 표에 손으로 적지 않는다 (D-227 · D-90).

ALTER TABLE sanction_rule ADD COLUMN IF NOT EXISTS rule_key TEXT;
ALTER TABLE sanction_rule ADD COLUMN IF NOT EXISTS annex1 TEXT[];
ALTER TABLE sanction_rule ADD COLUMN IF NOT EXISTS cover TEXT;
ALTER TABLE sanction_rule ADD COLUMN IF NOT EXISTS quote TEXT;
ALTER TABLE sanction_rule ADD COLUMN IF NOT EXISTS fact_kind TEXT;
ALTER TABLE sanction_rule ADD COLUMN IF NOT EXISTS plan_sha TEXT;

ALTER TABLE sanction_rule DROP CONSTRAINT IF EXISTS ck_sanction_cover;
ALTER TABLE sanction_rule ADD CONSTRAINT ck_sanction_cover
  CHECK ((COALESCE(cardinality(annex1), 0) > 0) = (cover IS NOT NULL)
         AND (cover IS NULL OR cover IN ('전부', '일부')));

CREATE UNIQUE INDEX IF NOT EXISTS ux_sanction_rule_key ON sanction_rule(rule_key)
  WHERE rule_key IS NOT NULL;

COMMENT ON COLUMN sanction_rule.rule_key IS
  '원천 행의 id (scripts/sanction_review.yaml · 0023). 적재는 이 열쇠로 넣고 거둔다.';
COMMENT ON COLUMN sanction_rule.annex1 IS
  '식품 4~7호 행의 [별표 1] 목 목록 (D-310). NULL = 목으로 갈리지 않는 행 · 빈 배열 = 목 칸이 빈 행(고시로 닿는다).';
COMMENT ON COLUMN sanction_rule.cover IS
  '별표7 행이 별표1 목을 덮는 정도 — 전부면 하한 · 일부면 가능 상한만 (D-310 개정 2).';
COMMENT ON COLUMN sanction_rule.plan_sha IS
  '이 행이 실린 원천 판의 sha (D-309). 서명은 판에 묶인다 — 판이 바뀌면 다시 싣는다.';

-- 🚨 뷰를 다시 만든다 — 판정 그래프가 새 칸을 읽는다. 열은 **끝에** 더한다(앞 열의 순서 · 뜻은 0013 그대로).
DROP VIEW IF EXISTS v_risk_lookup;

-- 🚨 본문은 `db/schema.sql` 과 **글자까지 같아야 한다** — `tests/test_db_schema.py`
--    (`test_마이그레이션이_만드는_모양이_schema_sql_과_같다`)가 대조한다.
CREATE VIEW v_risk_lookup AS
SELECT s.violation_type, s.offense_count, s.sanction_kind,
       s.sanction_value, s.unit, s.risk_level, s.law_id,
       s.rule_key, s.annex1, s.cover, s.quote, s.fact_kind
FROM sanction_rule s
WHERE s.superseded_at IS NULL
  AND s.verified_by IS NOT NULL
  AND s.reviewed_by IS NOT NULL;

COMMENT ON VIEW v_risk_lookup IS
  '위험도 하한의 유일한 입구. 🔴 2인 확인(verified_by · reviewed_by)이 끝난 행만 보인다 — '
  'ck_sanction_four_eyes 는 둘 다 NULL 이면 통과하므로 제약만으로는 안 막힌다 (D-66 · D-170).';
