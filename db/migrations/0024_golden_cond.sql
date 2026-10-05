-- 0024 · golden_sample 에 조건 칸 · 후보 근거 칸을 더한다 (2026-10-05 · D-317 · 팀장 판정)
--
-- 왜 — `golden_sample` 은 판정을 `violations` 하나로만 담아 「빈 목록 = 적법」으로 읽혔다. 그래서 조건 M(보류) ·
--      D(판정 대상 아님) · 근거가 후보로만 있는 행은 넣지 않고 수만 보였다(D-285 개정 4 ⑥). 재동결(원장 10-03 ㊿-23)
--      뒤 그 수가 1,314 행(골든 10,064 중)이 되어 DB 가 파일의 87% 만 담는다.
--      미룬 이유 둘 중 「동결 전에 스키마를 바꾼다」는 사라졌고, 「읽을 쪽이 없다」는 읽는 쪽(적재 뒤 되읽어 대조 ·
--      아래 뷰 둘)을 같이 만들어 푼다.
--
-- 🚨 더하기만 한다 — 기존 행의 `cond` 는 NULL 로 남는다. **옮긴 뒤 `launcher.py load` 를 돌려야** 채워진다
--    (그 사이에는 조건 있는 행이 「조건 없음」으로 보인다 · `load` 의 되읽어 대조가 잡는다).
-- 🚨 열은 **끝에** 붙는다 — `db/schema.sql` 도 `unit` 뒤에 같은 순서로 둔다(뷰가 `g.*` 다 · 0009 의 교훈).
-- 🚨 제약 이름은 `schema.sql` 의 열 안 CHECK 가 받는 자동 이름과 같게 적는다(`unit` 과 같은 방식 · 0003 ⑤).

ALTER TABLE golden_sample ADD COLUMN IF NOT EXISTS cond TEXT;
ALTER TABLE golden_sample DROP CONSTRAINT IF EXISTS golden_sample_cond_check;
ALTER TABLE golden_sample ADD CONSTRAINT golden_sample_cond_check
  CHECK (cond IN ('C','A','B','M','D','L'));
ALTER TABLE golden_sample ADD COLUMN IF NOT EXISTS evidence_candidate JSONB;

ALTER TABLE golden_sample DROP CONSTRAINT IF EXISTS ck_golden_cond_empty;
ALTER TABLE golden_sample ADD CONSTRAINT ck_golden_cond_empty
  CHECK (cond IS NULL OR cond NOT IN ('D','L')
      OR (cardinality(violations) = 0 AND evidence IS NULL AND evidence_candidate IS NULL));
ALTER TABLE golden_sample DROP CONSTRAINT IF EXISTS ck_golden_cond_basis;
ALTER TABLE golden_sample ADD CONSTRAINT ck_golden_cond_basis
  CHECK (cond IS NULL OR cond NOT IN ('C','A','B')
      OR evidence IS NOT NULL OR evidence_candidate IS NOT NULL);

-- 🔴 `g.*` 는 뷰를 만들 때의 열 목록으로 굳는다 — 열을 더했으면 다시 만든다 (0009).
DROP VIEW IF EXISTS v_publishable_golden;
CREATE VIEW v_publishable_golden AS
SELECT g.* FROM golden_sample g
WHERE g.redistributable = true;

DROP VIEW IF EXISTS v_golden_scored;
CREATE VIEW v_golden_scored AS
SELECT g.* FROM golden_sample g
WHERE g.cond IS NULL OR g.cond NOT IN ('M','D');

DROP VIEW IF EXISTS v_golden_legal;
CREATE VIEW v_golden_legal AS
SELECT g.* FROM golden_sample g
WHERE cardinality(g.violations) = 0 AND (g.cond IS NULL OR g.cond = 'L');
