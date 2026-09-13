-- 0013 · 서명 없는 제재 행이 위험도 하한으로 쓰이지 않게 한다 (2026-09-13 · D-66 · D-170)
--
-- 🔴 **무엇이 열려 있었나** — `ck_sanction_four_eyes` 는 이렇게 적혀 있다:
--
--        CHECK (verified_by IS NULL OR reviewed_by IS NULL OR verified_by <> reviewed_by)
--
--    ⛔ 읽으면 「2인 확인」이지만, **둘 다 NULL 이면 통과한다.** 막는 것은 *「한 사람이
--       두 칸을 다 적는 것」* 뿐이고 *「아무도 안 적는 것」* 은 안 막는다.
--       🚨 D-170 이 말한 **통과만 하는 게이트**의 교과서적인 모양이다 — 이름은 four_eyes 인데
--          zero_eyes 를 허용한다.
--
-- 🚨 **0007 을 되돌리는 것이 아니다.** 0007 은 NOT NULL 을 걷었고 그 판정은 옳았다 —
--    *「2인 확인의 강제 지점은 `collect/registry.py` 하나」*(D-66). 같은 원칙을 두 곳에서
--    다른 세기로 걸면 약한 쪽이 무시된다.
--    ⛔ **그런데 `sanction_rule` 은 그 경로로 안 들어온다.** 별표 파싱(243행)이 직접 넣는다.
--       registry 는 **소스**를 서명하지 **행**을 서명하지 않는다. 그래서 이 표에는
--       강제 지점이 **하나도 없었다.**
--
-- ★ **막는 자리를 적재가 아니라 읽는 자리로 둔다.**
--    ① 적재는 된다 — 파싱 결과를 둘 곳이 있어야 서명을 DB 위에서 한다.
--       막으면 서명이 파일 위에서 이뤄지고, 그건 되돌아볼 수 없다.
--    ② 서명 전에는 **위험도 계산에 안 보인다** — `assess_risk` 의 하한이 안 잡히고,
--       하한이 없으면 계약이 최종 위험도를 거부한다 (D-09 래칫 · `RiskAssessment._ratchet`).
--       🚨 즉 **조용히 통과하는 대신 판정이 멈춘다.** 그것이 fail-closed 다 (D-220).
--
-- ⬜ **이 마이그레이션이 안 하는 것** (D-188) —
--    ① `verified_by <> reviewed_by` 는 여전히 CHECK 가 본다. 뷰는 **있는지**만 본다.
--    ② 서명자가 **누구여야 하는가**는 여기서 안 정한다 — 사람 몫이다 (`registry_review.yaml`).
--    ③ 지금 `sanction_rule` 은 **0행**이다. 그래서 이 변경으로 사라지는 행은 없다.
--       ⛔ 「0행이라 안전하다」가 이유는 아니다 — 적재기가 붙기 **전에** 세우는 것이 요점이다.
--
-- 🚨 왜 0007 을 고치지 않고 새 파일인가 — 0007 은 이미 돌았다. 돈 마이그레이션의 본문을
--    고치면 새 DB 와 옮긴 DB 가 갈리고 그 차이는 조용하다 (0007 자신이 적어 둔 규칙).

DROP VIEW IF EXISTS v_risk_lookup;

-- 🚨 본문은 `db/schema.sql` 과 **글자까지 같아야 한다** — `tests/test_db_schema.py`
--    (`test_마이그레이션이_만드는_모양이_schema_sql_과_같다`)가 대조한다.
CREATE VIEW v_risk_lookup AS
SELECT s.violation_type, s.offense_count, s.sanction_kind,
       s.sanction_value, s.unit, s.risk_level, s.law_id
FROM sanction_rule s
WHERE s.superseded_at IS NULL
  AND s.verified_by IS NOT NULL
  AND s.reviewed_by IS NOT NULL;

COMMENT ON VIEW v_risk_lookup IS
  '위험도 하한의 유일한 입구. 🔴 2인 확인(verified_by · reviewed_by)이 끝난 행만 보인다 — '
  'ck_sanction_four_eyes 는 둘 다 NULL 이면 통과하므로 제약만으로는 안 막힌다 (D-66 · D-170).';
