-- ═══════════════════════════════════════════════════════════════════
--  🧊 동결본 — 2026-09-14.  `alembic/versions/0001_governance_layer.py` 가 읽는 파일이다.
--
--  ⛔ 이 파일을 고치지 않는다. 한 글자도.
--     `tests/test_db_schema.py` 의 sha256 핀이 막는다.
--     고치면 「이미 0001 을 지난 DB」와 「지금 처음 지나는 DB」가 다른 모양이 된다 —
--     2026-09-13·14 에 팀원 둘이 이틀 연속 막힌 원인이 정확히 그것이다 (D-221).
--
--  ★ 스키마를 바꿀 때 고치는 것은 둘이다 —
--      ① db/schema.sql        현재 상태의 선언 (사람이 읽는 정본)
--      ② 새 마이그레이션        그 변화를 이미 있는 DB 에 옮기는 것
--    둘이 갈렸는지는 `uv run python launcher.py db-drift` 가 대조한다.
--
--  🚨 이 파일은 2026-09-14 시점의 `db/schema.sql` 과 본문이 같다 (이 머리 주석만 더 붙었다).
--     그 시점에 `db-drift` 로 「alembic head 와 구조 차이 0」을 실측하고 박았다.
-- ═══════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════
--  CopyLane 데이터베이스 스키마 v1.0
--  PostgreSQL 16 + pgvector  ·  작성자 오한빈 (팀장)  ·  2026-08-20
--
--  🚨 설계 원칙 넷 — 전부 설계결정으로 근거가 있다
--   D-18  등급은 소스가 아니라 FRAGMENT의 속성이다
--   D-20  모든 파생물은 fragment_id FK ON DELETE CASCADE 로 매달린다
--   D-66  2인 확인(4-eyes)을 CHECK 제약으로 강제한다
--   D-71  「데이터 재배포 금지」는 배포 축이지 학습 축이 아니다 → provenance 기록
-- ═══════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────── 열거형 ───────────────────────────
CREATE TYPE grade_t       AS ENUM ('G0','G1','G2','G3');
CREATE TYPE use_t         AS ENUM ('U1_train','U2_rag','U3_cite','U4_deploy');
CREATE TYPE flag_t        AS ENUM ('BY','NC','SA','PII','TOS','GATED',
                                   'NOREDIST','NOSTORE','QUERYLOG','PREAPPROVAL',
                                   'NOTRAIN');   -- 🔄 D-122 · 사용자 업로드물은 학습·색인 금지
CREATE TYPE cost_t        AS ENUM ('free','gated','paid','unknown');
CREATE TYPE value_t       AS ENUM ('A','B','C','D','X');
-- 🔴 위법 유형 — **우리 라벨이 곧 타입이다** (2026-09-10 · D-178).
--    ⛔ 종전 'V0'~'V8' 은 뜻이 스키마 어디에도 없었고, 경쟁하는 대응표가 둘이었다
--       (수집전처리_기획 §4-6 의 V표 vs 별표1 호수). 접으면 5종이 2칸으로 뭉갠다 —
--       V6 ← 소비자_기만 + 후기_체험기_기만 + 추천_보증_뒷광고, V7 ← 부당_비교광고 + 비방광고.
--       되돌릴 수 없는 손실이라 **라벨을 그대로 타입으로** 둔다.
--    ★ 조문 대응(별표1 제1~8호)은 **타입이 아니라 데이터**다 — `violation_article` 을 본다.
--      조문이 확정 라벨이면(D-158) 그 대응은 바뀔 수 있는 사실이지 스키마가 아니다.
--    🚨 '적법' 값을 두지 않는다 — 적법은 `violations = '{}'` 다. 값으로 두면 두 표현이 생긴다.
-- 🔴 뒤 다섯은 **편입 후보**다 (D-65). 인코더가 예측하는 확정 클래스는
--    `scripts/collect.py` 의 `VIOLATION_TYPES` 6종이고, 승격 판정일은 2026-09-17 이다.
--    ⛔ 여기 있다는 것이 「인코더 클래스」라는 뜻이 아니다 — 대응표·사전·제재가 쓰는 어휘다.
--    🔄 `기능성화장품_오인` 2026-09-10 등재 (0005) — 화장품법 시행규칙 [별표 5] 제2호 나목.
--       앞의 셋은 식품표시광고법 제8조제1항 1~3호 구조라 식품 축이고, 화장품 축의 같은
--       자리가 비어 있어 `violation_article` 에 나목을 적을 수가 없었다.
CREATE TYPE violation_t   AS ENUM ('질병_예방치료_표방','건강기능식품_오인','의약품_오인',
                                   '거짓_과장','소비자_기만','후기_체험기_기만',
                                   '추천_보증_뒷광고','부당_비교광고','비방광고',
                                   '실증책임_위반','기능성화장품_오인');
CREATE TYPE risk_t        AS ENUM ('R0','R1','R2','R3','R4');
CREATE TYPE infeas_t      AS ENUM ('A','B','C');          -- D-59 자격형/실증형/절대형
CREATE TYPE origin_t      AS ENUM ('real','injected','approved');
-- 🔴 분할 — `test_sentence` 가 없어 골든셋 1,908행이 DB 밖에 서 있었다 (2026-09-10).
--    🚨 `test_holdout` 과 **뜻이 다르다.** test_sentence 는 문장 단위 평가(ftc 의결서 봉인 +
--       승인 문구 음성)이고, test_holdout 은 `mfds_press` 홀드아웃 자리다. 접으면
--       두 평가가 한 칸에 섞이고, 그것이 D-172 가 경고한 「단위를 섞는」 자리다.
--    ⬜ 'dev' 는 코드·데이터 어디에서도 배정되지 않는 **죽은 값**이다. 쓸 자리가 생길 때까지 둔다.
CREATE TYPE split_t       AS ENUM ('train','dev','test_sentence','test_holdout');
CREATE TYPE certainty_t   AS ENUM ('확실','불확실');        -- D-74 측정 축
CREATE TYPE tense_t       AS ENUM ('과거','현재','미래');
CREATE TYPE senttype_t    AS ENUM ('사실형','추론형','대화형','예측형');
-- D-91 표면 변환 축 — 회피 표기. 🚨 위법 유형과 직교한다 (rule_id 에 섞지 않는다)
CREATE TYPE surface_t     AS ENUM ('S0','S1','S2','S3','S4','S5');

-- ═══════════════════ 1. 거버넌스 — 게이트의 본체 ═══════════════════

CREATE TABLE source (
    source_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    publisher           TEXT NOT NULL,
    url                 TEXT,
    layer               TEXT NOT NULL,
    grade               grade_t NOT NULL,
    cost                cost_t  NOT NULL DEFAULT 'unknown',
    value               value_t NOT NULL,
    access              TEXT,
    license             TEXT,
    attribution         TEXT,                      -- 출처표시 문구 (BY 플래그 시 필수)
    collector           TEXT,                      -- scripts/collect/*.py
    refresh             TEXT,
    robots_checked_at   TIMESTAMPTZ,
    -- 🚨 D-66 · 2인 확인을 코드가 아니라 제약으로 강제한다
    grade_decided_by    TEXT NOT NULL,
    grade_reviewed_by   TEXT NOT NULL,
    grade_decided_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    grade_evidence_url  TEXT,
    supersedes          TEXT REFERENCES source(source_id) ON DELETE SET NULL,
    verified            BOOLEAN NOT NULL DEFAULT false,
    note                TEXT,
    CONSTRAINT ck_source_four_eyes CHECK (grade_decided_by <> grade_reviewed_by),
    CONSTRAINT ck_source_by_attr   CHECK (attribution IS NOT NULL OR grade = 'G1')
);
COMMENT ON CONSTRAINT ck_source_four_eyes ON source IS
  'D-66 · 같은 사람이 판정하고 스스로 확인하는 것을 구조적으로 불가능하게 한다';

CREATE TABLE source_constraint (
    source_id  TEXT NOT NULL REFERENCES source(source_id) ON DELETE CASCADE,
    flag       flag_t NOT NULL,
    note       TEXT,
    PRIMARY KEY (source_id, flag)
);

CREATE TABLE source_use (
    source_id  TEXT NOT NULL REFERENCES source(source_id) ON DELETE CASCADE,
    use_code   use_t   NOT NULL,
    allowed    BOOLEAN NOT NULL,
    note       TEXT,
    PRIMARY KEY (source_id, use_code)
);

-- 🚨 D-18 · 등급은 여기서 갈린다. 소스 등급은 기본값일 뿐이다
CREATE TABLE fragment (
    fragment_id   TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES source(source_id) ON DELETE CASCADE,
    frag_type     TEXT NOT NULL,           -- 법리서술 / 광고문구 / 캡처이미지 / 업체명 …
    grade         grade_t NOT NULL,        -- 소스 등급을 상속하지 않고 개별 판정
    masking       TEXT,                    -- always / none
    excluded      BOOLEAN NOT NULL DEFAULT false,
    note          TEXT
);
CREATE INDEX ix_fragment_source ON fragment(source_id);
CREATE INDEX ix_fragment_grade  ON fragment(grade) WHERE excluded = false;

CREATE TABLE collect_manifest (
    manifest_id  BIGSERIAL PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES source(source_id) ON DELETE CASCADE,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    url          TEXT,
    sha256       TEXT,
    bytes        BIGINT,
    rows         INTEGER,
    event        TEXT NOT NULL DEFAULT 'fetch'   -- fetch / skip / delete
);
CREATE INDEX ix_manifest_source_time ON collect_manifest(source_id, fetched_at DESC);

-- ═══════════════════ 2. 원문 · 문장 ═══════════════════

CREATE TABLE document (
    doc_id          TEXT PRIMARY KEY,
    fragment_id     TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    doc_type        TEXT NOT NULL,          -- 법률/시행령/시행규칙/고시/지침/의결서/처분/보도자료
    title           TEXT,
    law_id          TEXT,
    source_ref      TEXT,                   -- 사건번호 · 법령ID · 인정번호
    effective_date  DATE,
    superseded_at   DATE                    -- 🚨 NULL 이 아니면 현행이 아니다
);
CREATE INDEX ix_document_fragment ON document(fragment_id);
CREATE INDEX ix_document_current  ON document(law_id) WHERE superseded_at IS NULL;

-- 4-2/4-3절 · 정규화는 비파괴, 오프셋은 원문 기준
CREATE TABLE sentence (
    sent_id        TEXT PRIMARY KEY,
    doc_id         TEXT NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    fragment_id    TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    sent_idx       INTEGER NOT NULL,
    start_off      INTEGER NOT NULL,
    end_off        INTEGER NOT NULL,
    raw            TEXT NOT NULL,           -- 표시·오프셋 기준
    norm           TEXT NOT NULL,           -- 매칭 기준
    offset_map     JSONB,                   -- norm[i] -> raw 시작 오프셋
    evasion_flags  TEXT[] NOT NULL DEFAULT '{}',  -- JAMO_SPLIT / SEP_INSERT / FULLWIDTH …
    prev_sent_id   TEXT,
    next_sent_id   TEXT,
    category       TEXT,
    CONSTRAINT ck_sentence_span CHECK (end_off > start_off),
    CONSTRAINT uq_sentence_pos  UNIQUE (doc_id, sent_idx)
);
CREATE INDEX ix_sentence_doc      ON sentence(doc_id);
CREATE INDEX ix_sentence_fragment ON sentence(fragment_id);

-- ═══════════════════ 3. RAG 청크 + 벡터 ═══════════════════

CREATE TABLE chunk (
    chunk_id        TEXT PRIMARY KEY,
    fragment_id     TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    doc_id          TEXT REFERENCES document(doc_id) ON DELETE CASCADE,
    law_id          TEXT,
    article         TEXT,
    paragraph       TEXT,
    item            TEXT,
    doc_type        TEXT,
    category        TEXT[] NOT NULL DEFAULT '{}',
    text            TEXT NOT NULL,
    -- 🔴 2026-09-12 (0008) — **검색이 보는 텍스트와 인용하는 텍스트를 가른다.**
    --    호 한 줄(「1. 마약」)은 문맥이 없어 아무 질의에나 붙었다. 청크를 다시 자르는 대신
    --    자립 텍스트를 옆 칸에 둔다 — `text` 는 한 글자도 안 바뀌므로 인용 단위가 산다 (D-158).
    --    🚨 NULL 은 「아직 재적재 안 됨」, 빈 문자열은 「붙일 문맥이 없음」(조 청크)이다.
    context         TEXT,
    --    항 서수 — 원문에 항번호가 없어도 우리가 센 것. 법제처 XML 은 항이 하나뿐인 조에
    --    <항번호>를 안 줘서 호의 31%(283/909)가 `paragraph` 빈 칸이다. 원문과 우리 셈을
    --    갈라 둔다 — 원문에 없는 「①」를 지어내지 않는다 (D-117).
    paragraph_no    SMALLINT,
    -- 🔴 2026-09-12 밤 (0011) — **쪼갠 조각이라는 사실**. 청크_스키마 TODO ③(리랭커 512 토큰
    --    제한 대응 · 긴 조문 분할 규칙)의 못 채운 절반이다. `preprocess/chunk.py` 가 700자를
    --    넘는 조문을 문장 경계로 쪼개면서 만들어 놓고 **아무도 읽지 않았다** (D-199).
    --    ⛔ 읽는 쪽이 없으면 `citation()` 이 「제18조」를 내고 화면은 그것을 **조문 전문**으로
    --       읽는다 — 기획서 5-6 의 「인용 검증은 존재가 아니라 일치까지」가 막으려는 자리다.
    --    🚨 NULL 은 「아직 재적재 안 됨」이다. 1/1 로 채워 두지 않는다 — 그러면 쪼갠 121개가
    --       「안 쪼갰다」고 **거짓말**한다 (0008 의 context 와 같은 규칙).
    part_no         SMALLINT,
    part_total      SMALLINT,
    -- 🚨 NOT NULL 이라야 `ck_chunk_tokens` 가 실제로 막는다 (0006). 널이면 CHECK 가 통과한다
    --    🔴 이것이 재는 것은 **인용 단위(`text`)** 다. 모델·리랭커에 들어가는 것은 아래
    --       `input_token_count` 이고 **둘은 0008 이후로 다른 문자열**이다 (D-200).
    token_count     INTEGER NOT NULL,
    -- 🔴 2026-09-12 밤 (0011) — `scripts/embed.py` `embed_input()`(= context + text)의 토큰.
    --    ⛔ **CHECK 을 걸지 않는다 — 빠뜨린 것이 아니라 판정이다** (D-200). 리랭커가 아직
    --       미선정이라 상한이 수가 아니다: 기획서 7-3 이 `bge-reranker-v2-m3`(0.6B)와
    --       `bge-reranker-base`(0.3B)를 **나란히 재라**고 했고 그 재기가 끝나야 수가 선다.
    --    ★ 그때까지는 **재고 원장에 올린다.** 상한 없는 칸이 「지킨다」고 말하지 않게 한다.
    --    🚨 NULL 은 「아직 재적재 안 됨」이다.
    input_token_count SMALLINT,
    -- 🔴 2026-09-12 오후 (0010) — 어휘 검색(BM25 자리)의 색인. **생성열이다.**
    --    ⛔ 표현식 인덱스로 두면 질의가 같은 to_tsvector(...) 를 다시 적어야 인덱스를 타고,
    --       한쪽만 고치면 결과는 맞는데 **조용히 느려진다** (D-99). 정의는 이 한 줄뿐이다.
    --    🚨 `context` 를 같이 담는다 — scripts/embed.py 의 embed_input() 과 **같은 토큰열**이다.
    --       ⛔ 「같은 문자열」이 아니다: 구분자가 여기는 공백이고 embed_input 은 개행이며,
    --          context 가 NULL 이면 여기만 앞에 공백이 하나 붙는다. `simple` 파서가 공백으로만
    --          자르므로 **토큰열은 같다** — 재 보지 않고 「같은 문자열」이라 적었던 것을 고친다.
    --       두 갈래가 다른 토큰을 보면 순위를 섞는(RRF · D-193) 뜻이 없다.
    --    🚨 `simple` 파서는 공백으로만 자른다 — 형태소 분석기를 안 쓰는 것은 판정이다 (D-194).
    tsv             tsvector GENERATED ALWAYS AS
                      (to_tsvector('simple', coalesce(context, '') || ' ' || text)) STORED,
    effective_date  DATE,
    superseded_at   DATE,
    CONSTRAINT ck_chunk_tokens CHECK (token_count <= 512),
    -- 🔴 둘 다 NULL(미적재)이거나 둘 다 서고, 서면 1 ≤ part_no ≤ part_total 이라야 한다 (0011).
    --    ⛔ 한쪽만 서면 「3분의 몇인지 모르는 조각」이 되어 화면이 아무 말도 못 한다.
    CONSTRAINT ck_chunk_part CHECK (
        (part_no IS NULL AND part_total IS NULL)
        OR (part_no >= 1 AND part_total >= 1 AND part_no <= part_total)
    )
);
COMMENT ON CONSTRAINT ck_chunk_tokens ON chunk IS
  '인용 단위(text)의 토큰 상한 512. 🔴 리랭커에 들어가는 것은 input_token_count 이고 '
  '그 상한은 리랭커 모델 선정(기획서 7-3 · v2-m3 0.6B vs base 0.3B) 뒤에 건다 — '
  '지금 이 CHECK 을 그 축의 보증으로 읽지 않는다 (D-200).';
COMMENT ON COLUMN chunk.part_no IS
  '쪼갠 조각의 번호 (1부터). 700자를 넘는 조문을 문장 경계로 쪼갠 것 — 청크_스키마 TODO ③. '
  '🚨 NULL 은 「아직 재적재 안 됨」이지 「안 쪼갰다」가 아니다. 안 쪼갰으면 1/1 이다 (D-199).';
COMMENT ON COLUMN chunk.part_total IS
  '쪼갠 조각의 총수. part_total > 1 이면 이 청크는 조문의 일부다 — citation() 이 내는 '
  '「제18조」는 좌표로는 맞지만 전문이 아니다. 화면·인용 검증은 이 칸을 보고 말한다 (D-199).';
COMMENT ON COLUMN chunk.input_token_count IS
  '임베딩·리랭커에 실제로 들어가는 문자열(embed_input = context + text)의 토큰 수 (0011). '
  '🚨 상한 CHECK 이 없다 — 리랭커 미선정이라 상한이 아직 수가 아니다. 재고 원장에 올린다 (D-200).';
COMMENT ON COLUMN chunk.tsv IS
  '어휘 검색 색인 (0010). context + text — 임베딩 입력과 같은 토큰열이다(구분자만 다르다). '
  '🚨 simple 파서라 조사가 붙어 있다: 질의 쪽에서 조사를 깎고 접두어로 맞춘다 (app/retrieve.py).';
CREATE INDEX ix_chunk_fragment ON chunk(fragment_id);
CREATE INDEX ix_chunk_current  ON chunk(law_id, article) WHERE superseded_at IS NULL;
CREATE INDEX ix_chunk_tsv      ON chunk USING GIN (tsv);

-- 🚨 D-41 · pgvector 를 쓰는 이유가 바로 이 CASCADE 다
CREATE TABLE chunk_embedding (
    chunk_id   TEXT PRIMARY KEY REFERENCES chunk(chunk_id) ON DELETE CASCADE,
    embedding  vector(1024) NOT NULL,   -- 🚨 KURE-v1 실제 차원 1W 확인 후 확정
    model_id   TEXT NOT NULL,
    -- 🔴 2026-09-12 (0008) — 이 벡터를 만든 **입력 문자열**의 sha256 (D-176).
    --    ⛔ `model_id` 만으로는 문맥판과 무문맥판이 구별되지 않는다. 재임베딩을 중간에
    --       멈추면 두 벡터공간이 한 표에 섞이고 **거리는 조용히 뜻을 잃는다.**
    --    ★ `app/retrieve.py` 가 「일부만 NULL」을 섞임으로 보고 막는다.
    input_sha256 TEXT
);

-- ═══════════════ 4. 위험도 — 🚨 RAG 가 아니라 관계형이다 ═══════════════
-- 별표를 평문화해 벡터에 넣으면 표 구조가 깨지고
-- 「블랙박스 점수는 검수 도구로서 실격」(기획서 3-4) 원칙과 충돌한다.

CREATE TABLE sanction_rule (
    rule_id         BIGSERIAL PRIMARY KEY,
    fragment_id     TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    law_id          TEXT NOT NULL,
    annex_no        TEXT,
    violation_type  violation_t NOT NULL,
    offense_count   SMALLINT NOT NULL DEFAULT 1,   -- 위반 차수
    sanction_kind   TEXT NOT NULL,                 -- 시정명령 / 업무정지 / 과징금 / 등록취소
    sanction_value  NUMERIC,
    unit            TEXT,                          -- 일 / 원 / 배
    risk_level      risk_t NOT NULL,
    effective_date  DATE,
    superseded_at   DATE,
    verified_by     TEXT,                          -- 🚨 병합 셀 파싱은 2인 대조
    reviewed_by     TEXT,
    CONSTRAINT ck_sanction_four_eyes
      CHECK (verified_by IS NULL OR reviewed_by IS NULL OR verified_by <> reviewed_by)
);
CREATE INDEX ix_sanction_lookup ON sanction_rule(violation_type, offense_count)
  WHERE superseded_at IS NULL;

CREATE TABLE penalty_rule (
    rule_id         BIGSERIAL PRIMARY KEY,
    fragment_id     TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    tier            TEXT NOT NULL,        -- 매우중대 / 중대 / 중대성약함
    base_rate       NUMERIC,              -- 부과기준율
    base_amount     NUMERIC,              -- 정액 기준금액
    aggravation     JSONB,                -- 반복위반 100% 등 (2026.7.1 개정)
    mitigation      JSONB,
    effective_date  DATE NOT NULL,
    superseded_at   DATE
);

CREATE TABLE penal_clause (
    clause_id               BIGSERIAL PRIMARY KEY,
    fragment_id             TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    law_id                  TEXT NOT NULL,
    article                 TEXT NOT NULL,
    violation_type          violation_t,
    max_imprisonment_years  SMALLINT,
    max_fine_krw            BIGINT,
    effective_date          DATE,
    superseded_at           DATE
);

-- ═══════════════════ 5. 사전 · 제품 사실 ═══════════════════

CREATE TABLE dict_entry (
    entry_id        BIGSERIAL PRIMARY KEY,
    fragment_id     TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    -- 🔴 적재기가 넣는 값과 **같은 말로** 적는다 (2026-09-10).
    --    ⛔ 주석은 영문(prohibited / allowed …)인데 `load_db` 는 `'금지표현'` 을 넣는다.
    --       ENUM 이 아니라 TEXT 라 DB 가 안 막고, `uq_dict_term` 이 (dict_kind, term) 이라
    --       **표기가 갈리면 같은 용어가 두 벌 들어간다.**
    dict_kind       TEXT NOT NULL,        -- 금지표현 / 적법표현 / 질병표현 / 완화금지
    term            TEXT NOT NULL,
    violation_type  violation_t,
    law_ref         TEXT,
    category_scope  TEXT[] NOT NULL DEFAULT '{}',
    exact_match     BOOLEAN NOT NULL DEFAULT true,  -- 🚨 정확매칭만 위험도 하한 자격
    confidence      NUMERIC,
    CONSTRAINT uq_dict_term UNIQUE (dict_kind, term)
);
COMMENT ON COLUMN dict_entry.exact_match IS
  '기획서 3-5절 ④ · 유사도 근사매칭은 인코더와 동등 취급하며 하한을 걸지 못한다';
CREATE INDEX ix_dict_kind ON dict_entry(dict_kind);

-- A 자격형 판정(D-59)의 근거 — 「이 제품이 이 표현을 쓸 자격이 있는가」
CREATE TABLE product_fact (
    fact_id          BIGSERIAL PRIMARY KEY,
    fragment_id      TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    ingredient       TEXT NOT NULL,
    recognition_no   TEXT,                 -- 인정번호 · 심사번호 (D-61 대조 키)
    functional_claim TEXT NOT NULL,        -- 인정 기능성 문구 (100% 지향 프레임)
    daily_intake     TEXT,
    caution          TEXT,
    category         TEXT NOT NULL,
    recog_kind       TEXT NOT NULL,        -- 고시형 / 개별인정형
    -- 🔴 **자연키** (2026-09-10). ⛔ 없어서 적재가 멱등이 아니었다 —
    --    `load_db` 가 `ON CONFLICT` 없는 순수 INSERT 라 **두 번 돌리면 1,250 → 2,500** 이다.
    --    그 파일 docstring 은 「멱등이다. 모든 적재가 ON CONFLICT 로 간다」고 적어 뒀다.
    --    여섯 적재기 중 여기만 빠져 있었고, 문서와 코드가 정면으로 어긋난 자리였다.
    -- 🚨 인정번호는 NULL 일 수 있어 키에 못 쓴다 — 원료명 + 문구 + 종류가 한 행을 가른다.
    CONSTRAINT uq_product_fact UNIQUE (fragment_id, ingredient, functional_claim, recog_kind)
);
CREATE INDEX ix_product_ingredient ON product_fact(ingredient);

-- ═══════════════════ 6. 골든셋 · 학습 ═══════════════════

CREATE TABLE golden_sample (
    sample_id        TEXT PRIMARY KEY,
    sent_id          TEXT REFERENCES sentence(sent_id) ON DELETE CASCADE,
    fragment_id      TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    text             TEXT NOT NULL,
    category         TEXT,
    -- 판정 라벨 4종
    violations       violation_t[] NOT NULL DEFAULT '{}',
    three_elem       JSONB,                -- {false, misleading, anticomp}
    infeasibility    infeas_t,
    -- 🔄 2026-09-10 NOT NULL 을 뗐다 (D-178). 골든셋은 **정답 라벨을 담는 시험지**이지
    --    위험도를 담는 곳이 아니다. 위험도는 판정 시 `sanction_rule` · `v_risk_lookup` 으로
    --    계산한다 (D-09 래칫). ⛔ 없는 수를 지어내 칸을 채우면 그 수가 원장으로 흘러간다.
    risk             risk_t,
    evidence         JSONB,                -- [{law_id, article, item}]
    claim_spans      JSONB,                -- [{start, end, label}]  ← 주입 좌표에서 자동 생성
    -- 🔄 D-74 측정 축 3종
    certainty        certainty_t,
    tense            tense_t,
    sent_type        senttype_t,
    -- 생성 이력
    origin           origin_t NOT NULL,
    rule_id          TEXT,                 -- TRANSFORM_RULES T1~T10 (의미 변환)
    -- 🔄 D-91 표면 변환 축 — 의미 변환과 직교. 정규화 층의 이득을 재는 자리
    surface_variant  surface_t NOT NULL DEFAULT 'S0',
    surface_of       TEXT REFERENCES golden_sample(sample_id) ON DELETE CASCADE,
    -- 🚨 D-71 · 이걸 수집 시점에 안 남기면 복원 불가능하다
    provenance       TEXT NOT NULL,
    redistributable  BOOLEAN NOT NULL,
    split            split_t NOT NULL,
    -- 🔴 **단위** — 문장인가 낱말인가 (2026-09-10 · D-155 · D-172).
    --    ⛔ 이 칸이 없어서 골든셋의 단위 구분이 DB 에서 소실됐다. 사례집은 낱말(중앙 4자),
    --       의결서는 문장(중앙 12자)이고, 한 시험지로 세면 **두 과제를 평균한 수**가 된다.
    --       그 혼동을 이틀에 걸쳐 두 번 밟았다 — 칸으로 막는다.
    --    🚨 **자리가 맨 뒤인 이유** — 마이그레이션의 `ADD COLUMN` 은 뒤에 붙는다.
    --       중간에 두면 새 DB 와 옮긴 DB 의 컬럼 순서가 갈리고, `v_publishable_golden`
    --       이 `g.*` 라 **뷰 컬럼 순서까지** 갈린다. 실측으로 확인한 유일한 차이였다.
    unit             TEXT NOT NULL DEFAULT '문장'
                     CHECK (unit IN ('문장','낱말')),
    -- 🔴 **평가 split 전부**를 막는다 (2026-09-10 · D-170).
    --    ⛔ 종전 조건은 `split = 'test_holdout'` 하나였다. 그런데 파이프라인이 실제로 쓰는
    --       평가 split 은 `test_sentence` 라, 이 제약은 **어떤 행에도 걸리지 않았다.**
    --       그런데 설계 문서는 「주입본을 test_holdout 에 넣으니 거부됐다」를 성과로 적어 뒀다 —
    --       검증한 값과 파이프라인이 쓰는 값이 달랐다. 실패할 수 없는 제약이었다.
    CONSTRAINT ck_golden_injected_not_holdout
      CHECK (NOT (origin = 'injected' AND split IN ('test_sentence','test_holdout'))),
    -- 🚨 D-91 — 표면 변형은 S0 원형과 짝으로만 존재한다. 짝이 없으면 델타를 못 잰다
    CONSTRAINT ck_surface_pairing
      CHECK ((surface_variant = 'S0' AND surface_of IS NULL)
          OR (surface_variant <> 'S0' AND surface_of IS NOT NULL))
);
COMMENT ON CONSTRAINT ck_golden_injected_not_holdout ON golden_sample IS
  '4-8절 · 평가는 실사례 홀드아웃으로만 한다. 주입본이 섞이면 지표가 부풀려진다';
CREATE INDEX ix_golden_split ON golden_sample(split);
CREATE INDEX ix_golden_origin ON golden_sample(origin);
CREATE INDEX ix_golden_viol  ON golden_sample USING GIN (violations);

-- 🔴 라벨 ↔ 조문 대응 — **데이터다** (2026-09-10 · D-178).
--    ⛔ 종전에는 이 대응이 어디에도 없었다. `후기_체험기_기만` 은 법에서 제5호의 **목**이고,
--       별표1 제8호(사행심·음란)는 우리 목록에 없다 — 「빠진 것」인지 「뺀 것」인지
--       문서에 없었다. 타입에 접으면 그 사실이 사라진다.
--    ★ 조문이 확정 라벨이면(D-158) 대응은 **바뀔 수 있는 사실**이다. 개정되면 행을 고친다.
--    🚨 `adopted=false` 가 「뺐다」를 남기는 자리다 — D-110 의 not_adopted 와 같은 뜻.
CREATE TABLE violation_article (
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
CREATE INDEX ix_golden_redis ON golden_sample(redistributable);

-- D-26 · 실사례 시정 페어 (철수 조건 5번의 실물)
CREATE TABLE transform_pair (
    pair_id      BIGSERIAL PRIMARY KEY,
    fragment_id  TEXT NOT NULL REFERENCES fragment(fragment_id) ON DELETE CASCADE,
    doc_id       TEXT REFERENCES document(doc_id) ON DELETE CASCADE,
    before_text  TEXT NOT NULL,
    after_text   TEXT NOT NULL,
    rule_id      TEXT,                     -- 귀납된 TRANSFORM_RULES ID
    note         TEXT
);

-- ═══════════════════ 7. 세그먼트 (Phase 3) ═══════════════════

CREATE TABLE segment (
    segment_id       TEXT PRIMARY KEY,
    label            TEXT,
    member_count     INTEGER NOT NULL,
    vulnerable_flag  BOOLEAN NOT NULL DEFAULT false,
    top_terms        TEXT[] NOT NULL DEFAULT '{}',
    demographics     JSONB,
    source_set       TEXT[] NOT NULL,
    built_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_segment_k_anon CHECK (member_count >= 20)   -- 🚨 K_MIN · W1 확정 후 조정
);
COMMENT ON CONSTRAINT ck_segment_k_anon ON segment IS
  'k-익명성 · 미달 군집은 생성 자체가 차단된다. K_MIN 값은 사실원장 참조';

-- ═══════════════════ 8. 재현성 ═══════════════════

CREATE TABLE dataset_manifest (
    manifest_id         TEXT PRIMARY KEY,
    source_set_version  TEXT NOT NULL,     -- 값이 바뀌면 재학습 트리거 (D-22)
    seed                INTEGER NOT NULL,
    built_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    counts              JSONB NOT NULL,
    unmeasurable        TEXT[] NOT NULL DEFAULT '{}',  -- 30건 미만 유형 (D-40)
    source_sets         JSONB NOT NULL
);

-- ═══════════════════ 9. 뷰 — 실수를 구조로 막는다 ═══════════════════

-- 🚨 검색은 항상 현행만. superseded_at 필터를 잊는 것이 가장 흔한 사고다
CREATE VIEW v_current_chunk AS
SELECT c.* FROM chunk c
JOIN fragment f USING (fragment_id)
WHERE c.superseded_at IS NULL AND f.excluded = false;

-- 🚨 D-71 · 데이터셋을 공개할 때 반드시 이 뷰를 통한다
CREATE VIEW v_publishable_golden AS
SELECT g.* FROM golden_sample g
WHERE g.redistributable = true;

-- 위험도 산정은 코드가 이 뷰를 읽는다 (블랙박스 점수 금지)
-- 🔴 **2인 확인이 끝난 행만 보인다** (2026-09-13 · 0013 · D-66 · D-170).
--    ⛔ `ck_sanction_four_eyes` 는 **둘 다 NULL 이면 통과한다** — 0007 이 NOT NULL 을 걷으면서
--       난 구멍이다. 그 판정 자체는 옳았다(「강제 지점은 collect/registry.py 하나」).
--       🚨 다만 `sanction_rule` 은 **그 경로로 안 들어온다** — 별표 파싱이 직접 넣는다.
--          그래서 서명 없는 행이 **위험도 하한으로 쓰이는 길**이 열려 있었다.
--    ★ 막는 자리를 적재가 아니라 **읽는 자리**로 둔다 — 적재는 되고, 서명 전에는 안 보인다.
--      적재를 막으면 파싱 결과를 둘 곳이 없어지고, 그러면 서명이 파일 위에서 이뤄진다.
CREATE VIEW v_risk_lookup AS
SELECT s.violation_type, s.offense_count, s.sanction_kind,
       s.sanction_value, s.unit, s.risk_level, s.law_id
FROM sanction_rule s
WHERE s.superseded_at IS NULL
  AND s.verified_by IS NOT NULL
  AND s.reviewed_by IS NOT NULL;
