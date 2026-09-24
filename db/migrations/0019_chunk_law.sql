-- 0019_chunk_law.sql — 청크의 `category` 를 **법 축 `law`** 로 바꾼다 (2026-09-24 · W6 · D-271 ① ②)
--
-- 🔴 **왜 있는가** — 청크 `category` 는 법령 이름·별표 제목의 **낱말**로 정해졌고, 안 걸리면 「일반」이었다.
--    별표 제목에는 법 이름이 없어서 「일반」 735개 중 **265개(36%)가 다른 법**이었다 — 식품 광고의 핵심 규범인
--    식품표시광고법 시행령 [별표 1] 50청크가 그 안에 있었다(D-271 맥락 2). 품목 「식품」으로 검색하면 안 나왔다.
-- ★ 법은 **법 ID 로** 정한다. 한 청크는 법 ID 하나에서 왔으므로 법도 하나다 — 배열(TEXT[])을 글자(TEXT)로 바꾼다.
--
-- 🔴 **대응표의 정본은 `collect/law_map.py` `LAW_OF_ID` 다** (D-271 ①). 아래 `_law_of_id` 값은 그 사본이고,
--    게이트 `tests/test_law_map.py::test_0019_의_대응표가_law_map_과_같다` 가 **글자까지** 댄다 (D-99 — 못 합치면 서로 가리킨다).
--    ⛔ 마이그레이션이 파이썬 모듈을 불러 값을 채우지 않는 이유 — 돈 마이그레이션은 **그날의 값**을 남겨야 한다.
--       모듈이 나중에 바뀌면 같은 0019 가 다른 DB 를 만든다(0007 이 세운 규칙).
--
-- 🔴 **재임베딩이 없다** — 임베딩 입력은 `context + text` 라 법이 안 들어간다(D-271 맥락 6). 값은 이 파일이
--    `law_id` 로 채운다. 그래서 **사본(A)은 `migrate` 만으로 정본과 같은 값**이 된다 (D-271 데이터 흐름).
--
-- 🚨 **GUARD 가 먼저 센다** — 대응표에 없는 법 ID 를 든 청크가 있으면 **멈춘다.** 지우지도 고치지도 않는다 (D-220 · D-162).
--    ⛔ 종전 `category_of()` 가 모르면 「일반」을 준 것이 이번 사고였다 — 여기서 기본값을 두지 않는다.
--
-- 🚨 뷰를 먼저 뗀다 — `SELECT c.*` 는 열 이름을 **생성 시점에** 고정한다(0009). 떼지 않고 이름을 바꾸면
--    뷰는 옛 이름 `category` 로 계속 내보내고, 타입을 바꾸면 `cannot alter type … used by a view` 로 죽는다.

CREATE TEMP TABLE _law_of_id (law_id TEXT PRIMARY KEY, law TEXT NOT NULL) ON COMMIT DROP;
INSERT INTO _law_of_id (law_id, law) VALUES
  ('002011', '표시광고법'),
  ('005361', '표시광고법'),
  ('013094', '식품표시광고법'),
  ('013453', '식품표시광고법'),
  ('013475', '식품표시광고법'),
  ('002015', '화장품법'),
  ('005668', '화장품법'),
  ('008741', '화장품법'),
  ('009353', '건강기능식품법'),
  ('69549', '식품표시광고법'),
  ('75449', '식품표시광고법'),
  ('37971', '건강기능식품법'),
  ('34650', '건강기능식품법'),
  ('34717', '표시광고법'),
  ('35032', '표시광고법'),
  ('35037', '표시광고법'),
  ('20207', '표시광고법'),
  ('2052445', '표시광고법'),
  ('41277', '화장품법'),
  ('36122', '화장품법');

DO $$
DECLARE n bigint; ids text;
BEGIN
  SELECT count(*), string_agg(DISTINCT coalesce(c.law_id, '(NULL)'), ', ')
    INTO n, ids
    FROM chunk c
   WHERE NOT EXISTS (SELECT 1 FROM _law_of_id m WHERE m.law_id = c.law_id);
  IF n > 0 THEN
    RAISE EXCEPTION '🔴 법을 정할 수 없는 청크가 %건 있다 — 법 ID %. collect/law_map.py 와 이 파일의 대응표에 '
                    '먼저 더한 뒤 다시 돌린다 (D-271 ①). 기본값으로 떨어뜨리지 않는다', n, ids;
  END IF;
END $$;

DROP VIEW IF EXISTS v_current_chunk;

ALTER TABLE chunk DROP CONSTRAINT IF EXISTS ck_chunk_law;
ALTER TABLE chunk RENAME COLUMN category TO law;
ALTER TABLE chunk ALTER COLUMN law DROP DEFAULT;
-- 🚨 NOT NULL 을 먼저 뗀다 — 옛 칸이 NOT NULL 이라 NULL 로 바꾸는 순간 죽는다(2026-09-24 컨테이너 실측). 채운 뒤 다시 건다.
ALTER TABLE chunk ALTER COLUMN law DROP NOT NULL;
ALTER TABLE chunk ALTER COLUMN law TYPE TEXT USING NULL;
UPDATE chunk c SET law = m.law FROM _law_of_id m WHERE m.law_id = c.law_id;
ALTER TABLE chunk ALTER COLUMN law SET NOT NULL;
ALTER TABLE chunk ADD CONSTRAINT ck_chunk_law
  CHECK (law IN ('표시광고법', '식품표시광고법', '화장품법', '건강기능식품법'));

COMMENT ON COLUMN chunk.law IS
  '법 축 (D-271 ①) — 법 ID(law_id)로 정한다. 낱말로 정하지 않는다. 정본 대응표는 collect/law_map.py. '
  '🚨 품목(식품·건기식·화장품·일반상품)과 다른 축이다 — 제품 품목을 이 칸의 필터로 넘기지 않는다 (D-271 ③).';

CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

COMMENT ON VIEW v_current_chunk IS
  '검색은 항상 현행만 — superseded_at 필터를 잊는 것이 가장 흔한 사고다. '
  '🔴 chunk 에 열을 더하면 이 뷰를 반드시 다시 만든다: SELECT * 는 생성 시점에 고정된다.';
