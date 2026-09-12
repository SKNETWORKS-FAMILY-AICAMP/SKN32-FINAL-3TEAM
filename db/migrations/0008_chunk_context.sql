-- 0008_chunk_context.sql — 자립 텍스트와 항 서수, 그리고 임베딩 입력 지문 (2026-09-12)
--
-- 🔴 **왜 필요한가** — 2026-09-12 에 벡터 검색을 켜자마자 드러난 것.
--    「1. 마약」·「1. 열량」 같은 **호 한 줄이 독립 청크**라 문맥이 없고, 짧아서
--    아무 질의에나 중간 거리로 붙었다. 정답과 쓰레기의 거리 간격이 0.034 뿐이었다.
--    ⛔ 그 조각이 `EvidenceArticle` 로 나가면 「근거: 1. 마약」이 된다 (D-100 위배).
--
-- ★ **청크를 다시 자르지 않는다.** 호는 곧 위법 유형이라(제8조제1항 1~10호가
--   `VIOLATION_TYPES` 와 거의 1:1) 인용 단위를 뭉개면 판정 단위를 뭉갠다 (D-158).
--   대신 **검색이 보는 텍스트**와 **인용하는 텍스트**를 가른다.
--
--     chunk.text      호 본문 그대로          ← 인용. 한 글자도 안 바뀐다
--     chunk.context   조 제목 + 항 본문        ← 🆕 자립성. 임베딩과 화면이 같은 값을 쓴다
--
-- 🚨 셋 다 **NULL 을 허용한다** — 「아직 안 채움」과 「채울 것이 없음」은 다르다.
--    `context = ''` 는 조 청크처럼 **자기가 제목을 들고 있어 붙일 게 없는 것**이고,
--    `context IS NULL` 은 **아직 재적재가 안 된 것**이다. 둘을 한 값으로 만들면
--    「적재가 끝났는가」를 물을 수 없게 된다 (2026-09-12 `mark_collected` 와 같은 부류).

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS paragraph_no SMALLINT;
COMMENT ON COLUMN chunk.paragraph_no IS
  '항 서수 — 원문에 항번호가 없어도 우리가 센 것. 법제처 XML 은 항이 하나뿐인 조에 '
  '<항번호>를 주지 않아 호의 31%(283/909)가 paragraph 빈 칸이다. 원문(paragraph)과 '
  '우리가 센 것(paragraph_no)을 갈라 둔다 — 원문에 없는 「①」를 지어내지 않는다 (D-117).';

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS context TEXT;
COMMENT ON COLUMN chunk.context IS
  '자립 텍스트 — 호는 「조 제목 + 항 본문」, 항은 「조 제목」, 조는 빈 문자열(자기가 '
  '제목을 들고 있다). 임베딩 입력이자 화면 문맥이다. 🔴 한 값을 둘이 쓰므로 갈릴 수 없다 '
  '(D-99). NULL 은 「아직 재적재 안 됨」이고 빈 문자열은 「붙일 문맥이 없음」이다.';

ALTER TABLE chunk_embedding ADD COLUMN IF NOT EXISTS input_sha256 TEXT;
COMMENT ON COLUMN chunk_embedding.input_sha256 IS
  '이 벡터를 만든 입력 문자열의 sha256 — D-176(재현의 근거는 seed 가 아니라 입력 지문). '
  '🔴 model_id 만으로는 문맥판과 무문맥판이 구별되지 않는다. 재임베딩을 중간에 멈추면 '
  '두 벡터공간이 한 표에 섞이고 거리는 조용히 뜻을 잃는다. app/retrieve.py 가 '
  '「일부만 NULL」을 섞임으로 보고 막는다.';
