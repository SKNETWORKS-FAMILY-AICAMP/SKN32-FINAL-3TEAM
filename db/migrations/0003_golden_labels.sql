-- 0003 · 골든셋을 DB 에 넣기 위한 타입 정정 (2026-09-10 · D-178)
--
-- 🚨 **이미 만들어진 DB 를 옮기는 스크립트다.** 새 DB 는 `db/schema.sql` 하나로 선다.
--    ⛔ 두 곳에 같은 판정이 생기는 자리라(D-99), 여기는 **차이만** 적는다.
--
-- 🔴 `ALTER TYPE ... ADD VALUE` 를 쓰지 않는다. 같은 트랜잭션에서 추가한 값을 즉시 못 쓰고,
--    죽은 값('V0'~'V8')을 떼어낼 수도 없다. **타입을 다시 만든다.**
--    ★ 지금 `golden_sample`·`sanction_rule`·`penal_clause` 는 비어 있고 `dict_entry` 의
--      `violation_type` 은 전부 NULL 이라(적재기가 비워 뒀다) 캐스팅으로 잃을 값이 없다.
--
-- 🚨 **뷰가 컬럼 타입을 붙잡는다.** `v_risk_lookup`(sanction_rule.violation_type)과
--    `v_publishable_golden`(golden_sample.*) 을 먼저 떼지 않으면
--    "cannot alter type of a column used by a view" 로 죽는다. 끝에서 그대로 되만든다.

-- 🚨 **뷰만 붙잡는 게 아니다 — CHECK 제약도 컬럼 타입을 붙잡는다** (2026-09-10 실측).
--    ⛔ 처음에 뷰만 떼고 돌렸다가 `operator does not exist: text = split_t` 로 죽었다.
--       `ck_golden_injected_not_holdout` 이 `split = 'test_holdout'::split_t` 를 들고 있어서,
--       컬럼을 text 로 바꾸는 순간 제약 식이 `text = split_t` 가 된다.
--    ★ 컬럼 타입을 건드리기 전에 **그 컬럼을 참조하는 제약을 전부 뗀다.** 끝에서 되건다.
DROP VIEW IF EXISTS v_risk_lookup;
DROP VIEW IF EXISTS v_publishable_golden;
ALTER TABLE golden_sample DROP CONSTRAINT IF EXISTS ck_golden_injected_not_holdout;

-- ── ① violation_t — 'V0'~'V8' → 우리 라벨 10종 ─────────────────────────
--    🚨 쓰는 곳 넷 — sanction_rule · penal_clause · dict_entry · golden_sample(배열)
ALTER TABLE golden_sample ALTER COLUMN violations DROP DEFAULT;
ALTER TABLE golden_sample ALTER COLUMN violations TYPE text[] USING violations::text[];
ALTER TABLE sanction_rule ALTER COLUMN violation_type TYPE text USING violation_type::text;
ALTER TABLE penal_clause  ALTER COLUMN violation_type TYPE text USING violation_type::text;
ALTER TABLE dict_entry    ALTER COLUMN violation_type TYPE text USING violation_type::text;
-- 🚨 GIN 인덱스도 컬럼 타입에 매여 있다 — 떼고 되만든다.
DROP INDEX IF EXISTS ix_sanction_lookup;
DROP INDEX IF EXISTS ix_golden_viol;
DROP TYPE violation_t;
CREATE TYPE violation_t AS ENUM ('질병_예방치료_표방','건강기능식품_오인','의약품_오인',
                                 '거짓_과장','소비자_기만','후기_체험기_기만',
                                 '추천_보증_뒷광고','부당_비교광고','비방광고',
                                 '실증책임_위반');
ALTER TABLE golden_sample ALTER COLUMN violations TYPE violation_t[] USING violations::violation_t[];
ALTER TABLE golden_sample ALTER COLUMN violations SET DEFAULT '{}';
ALTER TABLE sanction_rule ALTER COLUMN violation_type TYPE violation_t USING violation_type::violation_t;
ALTER TABLE penal_clause  ALTER COLUMN violation_type TYPE violation_t USING violation_type::violation_t;
ALTER TABLE dict_entry    ALTER COLUMN violation_type TYPE violation_t USING violation_type::violation_t;
CREATE INDEX ix_sanction_lookup ON sanction_rule(violation_type, offense_count)
  WHERE superseded_at IS NULL;
CREATE INDEX ix_golden_viol ON golden_sample USING GIN (violations);

-- ── ② split_t — 'test_sentence' 가 없어 골든셋이 DB 밖에 서 있었다 ──────
ALTER TABLE golden_sample ALTER COLUMN split TYPE text USING split::text;
DROP INDEX IF EXISTS ix_golden_split;
DROP TYPE split_t;
CREATE TYPE split_t AS ENUM ('train','dev','test_sentence','test_holdout');
ALTER TABLE golden_sample ALTER COLUMN split TYPE split_t USING split::split_t;
CREATE INDEX ix_golden_split ON golden_sample(split);
CREATE INDEX IF NOT EXISTS ix_golden_origin ON golden_sample(origin);

-- ── ③ 실패할 수 없던 제약을 **고쳐서** 되건다 ─────────────────────────
--    ⛔ 종전 조건은 `split = 'test_holdout'` 하나였는데 평가는 `test_sentence` 로 간다 —
--       **어떤 행에도 안 걸리는 제약**이었다 (D-170).
ALTER TABLE golden_sample ADD CONSTRAINT ck_golden_injected_not_holdout
  CHECK (NOT (origin = 'injected' AND split IN ('test_sentence','test_holdout')));
COMMENT ON CONSTRAINT ck_golden_injected_not_holdout ON golden_sample IS
  '4-8절 · 평가는 실사례 홀드아웃으로만 한다. 주입본이 섞이면 지표가 부풀려진다';

-- ── ④ risk — 골든셋은 시험지이지 위험도를 담는 곳이 아니다 (D-09) ──────
ALTER TABLE golden_sample ALTER COLUMN risk DROP NOT NULL;

-- ── ⑤ 단위 — 문장/낱말 구분이 DB 에서 소실되고 있었다 (D-155 · D-172) ──
ALTER TABLE golden_sample ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT '문장';
ALTER TABLE golden_sample DROP CONSTRAINT IF EXISTS golden_sample_unit_check;
ALTER TABLE golden_sample ADD CONSTRAINT golden_sample_unit_check
  CHECK (unit IN ('문장','낱말'));

-- ── ⑥ 라벨 ↔ 조문 대응표 (타입이 아니라 데이터 · D-158 · D-110) ────────
CREATE TABLE IF NOT EXISTS violation_article (
    violation   violation_t NOT NULL,
    law_id      TEXT        NOT NULL,
    article     TEXT        NOT NULL,
    item        TEXT        NOT NULL DEFAULT '',
    adopted     BOOLEAN     NOT NULL DEFAULT true,
    note        TEXT,
    PRIMARY KEY (violation, law_id, article, item)
);
COMMENT ON TABLE violation_article IS
  '라벨 ↔ 조문 대응. 조문이 확정 라벨이라는 D-158 의 대응표이고, 타입이 아니라 데이터다';

-- ── ⑦ 떼어 둔 뷰를 그대로 되만든다 ───────────────────────────────────
CREATE VIEW v_publishable_golden AS
SELECT g.* FROM golden_sample g
WHERE g.redistributable = true;

CREATE VIEW v_risk_lookup AS
SELECT s.violation_type, s.offense_count, s.sanction_kind,
       s.sanction_value, s.unit, s.risk_level, s.law_id
FROM sanction_rule s
WHERE s.superseded_at IS NULL;
