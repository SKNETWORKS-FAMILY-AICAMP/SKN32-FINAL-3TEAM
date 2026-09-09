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
CREATE TYPE violation_t   AS ENUM ('V0','V1','V2','V3','V4','V5','V6','V7','V8');
CREATE TYPE risk_t        AS ENUM ('R0','R1','R2','R3','R4');
CREATE TYPE infeas_t      AS ENUM ('A','B','C');          -- D-59 자격형/실증형/절대형
CREATE TYPE origin_t      AS ENUM ('real','injected','approved');
CREATE TYPE split_t       AS ENUM ('train','dev','test_holdout');
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
    token_count     INTEGER,
    effective_date  DATE,
    superseded_at   DATE,
    CONSTRAINT ck_chunk_tokens CHECK (token_count IS NULL OR token_count <= 512)
);
COMMENT ON CONSTRAINT ck_chunk_tokens ON chunk IS
  '리랭커 bge-reranker-v2-m3 의 512 토큰 상한에 맞춘다';
CREATE INDEX ix_chunk_fragment ON chunk(fragment_id);
CREATE INDEX ix_chunk_current  ON chunk(law_id, article) WHERE superseded_at IS NULL;

-- 🚨 D-41 · pgvector 를 쓰는 이유가 바로 이 CASCADE 다
CREATE TABLE chunk_embedding (
    chunk_id   TEXT PRIMARY KEY REFERENCES chunk(chunk_id) ON DELETE CASCADE,
    embedding  vector(1024) NOT NULL,   -- 🚨 KURE-v1 실제 차원 1W 확인 후 확정
    model_id   TEXT NOT NULL
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
    dict_kind       TEXT NOT NULL,   -- prohibited / allowed / disease_adj / mitigation_banned
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
    recog_kind       TEXT NOT NULL         -- 고시형 / 개별인정형
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
    risk             risk_t NOT NULL,
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
    CONSTRAINT ck_golden_injected_not_holdout
      CHECK (NOT (origin = 'injected' AND split = 'test_holdout')),
    -- 🚨 D-91 — 표면 변형은 S0 원형과 짝으로만 존재한다. 짝이 없으면 델타를 못 잰다
    CONSTRAINT ck_surface_pairing
      CHECK ((surface_variant = 'S0' AND surface_of IS NULL)
          OR (surface_variant <> 'S0' AND surface_of IS NOT NULL))
);
COMMENT ON CONSTRAINT ck_golden_injected_not_holdout ON golden_sample IS
  '4-8절 · 평가는 실사례 홀드아웃으로만 한다. 주입본이 섞이면 지표가 부풀려진다';
CREATE INDEX ix_golden_split ON golden_sample(split);
CREATE INDEX ix_golden_viol  ON golden_sample USING GIN (violations);
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
CREATE VIEW v_risk_lookup AS
SELECT s.violation_type, s.offense_count, s.sanction_kind,
       s.sanction_value, s.unit, s.risk_level, s.law_id
FROM sanction_rule s
WHERE s.superseded_at IS NULL;
