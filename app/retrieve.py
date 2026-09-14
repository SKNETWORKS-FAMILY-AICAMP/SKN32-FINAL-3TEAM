"""app/retrieve.py — 조문 검색 코어. 두 소비자가 이것을 부른다 (D-99 · D-51).

    app/api.py    /search       search() — 어휘 + 벡터를 RRF 로 섞은 한 순위
    app/graph.py  retrieve()    search() — 같은 것을 부른다 (🔜 W4~)

갈래는 셋이고 **뜻이 각각 다르다** (D-167 — 열의 뜻으로 가른다):

    by_vector    뜻이 가까운 것.  「면역력 쑥!」 → 「질병의 예방 및 치료에 효능이…」
    by_lexical   어휘가 겹치는 것. 조사·어미를 깎고 접두어로 맞춘다
    by_literal   글자가 그대로 있는 것. 「제5호 아목」처럼 **기호**로 찾을 때

🔄 **2026-09-12 오후 — 「둘을 합치지 않는다」던 판정을 뒤집는다** (D-193).
   ⛔ 종전 판정(D-192 의 적용): 「합치려면 벡터 거리 0.83 과 글자 일치를 어떻게 더하냐는
      **[임의] 가중치**가 필요하고, 그 수는 판정 경로에 들어가면 안 된다.」
   ★ 그 판정은 **가중합만 보고 내린 것**이다. RRF(Reciprocal Rank Fusion)는 점수를 안 쓰고
      **순위만** 쓴다 — `Σ 1/(k + 순위)`. 더할 가중치가 없으니 [임의] 가 생기지 않는다.
      상수는 `k` 하나이고 문헌값이 있다 (`RRF_K` 참조 · `[문헌]`).
   🚨 뒤집은 이유는 **측정**이다. 2026-09-12 실측 — 광고 문구 세 건 중 정답 조문이
      벡터 단독으로 6위 · 19위 · 50위 밖이었다. 한 갈래로는 상위가 서지 않는다.

🚨 **모델 이름을 상수로 들지 않는다.** `chunk_embedding.model_id` 를 DB 에서 읽어
   **저장된 벡터를 만든 그 모델**을 로드한다. 상수를 손으로 맞출 자리가 없어지고
   (`scripts/embed.py` 와 두 벌이 되지 않는다), 질의 벡터와 저장 벡터가
   **구조적으로 같은 모델**이 된다 — 다르면 거리는 뜻 없는 수다.

⬜ **벡터 인덱스를 만들지 않았다 — 빠뜨린 것이 아니라 판정이다** (D-192).
   지금 규모(청크 수천)에서는 순차 스캔이 더 빠르다. `ivfflat` 은 `lists` 를 데이터 수에
   맞춰야 하고, 잘못 잡으면 **재현율이 조용히 떨어진다** — 느린 것보다 나쁘다.
   🚨 행 수는 여기 적지 않는다 — 기기마다 다르고(`data/` 미커밋), 적으면 낡는다.
   한 자릿수 만 단위로 가면 그때 `lists` 를 실측해서 만든다.

⬜ **리랭커(`bge-reranker-v2-m3`)도 아직 넣지 않았다.** 모델 하나와 임계값 하나가
   더 붙는 일이라 따로 판정한다 — 기획서 7-3 이 **0.6B(v2-m3)와 0.3B(base)를 나란히 재라**고
   적어 두었고, 그 재기가 끝나야 상한이 수가 된다.
   ⛔ **「자리는 이미 준비돼 있다」고 적었던 것을 거둔다** (2026-09-12 밤 · D-200).
      `ck_chunk_tokens CHECK (token_count <= 512)` 가 보는 `token_count` 는 **`text` 만** 센
      수인데, 리랭커에 들어가는 것은 `context + text`(`scripts/embed.py` `embed_input()`)다.
      0008 이 `context` 를 만든 순간 **재는 축과 쓰는 축이 갈렸고** 주석만 안 따라왔다.
      🚨 지금 서 있는 것은 `chunk.input_token_count`(0011) — **재기만 하고 상한은 없다.**
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from app.settings import DEFAULT_CATEGORY, PARAMS, load_kwargs

#: 🚨 코사인이라야 한다. `scripts/embed.py` 는 `model.encode(...)` 를 그대로 쓰므로
#:    저장된 벡터가 **정규화돼 있지 않다.** `<->`(L2)는 길이에 끌려가 뜻이 달라진다.
VECTOR_OP = "<=>"

MATCH_VECTOR = "vector"
MATCH_LEXICAL = "lexical"
MATCH_LITERAL = "literal"
MATCH_FUSED = "fused"
#: ⛔ 옛 이름. 2026-09-12 이전 응답은 `text` 였다 — 화면이 아직 없어 깨질 곳은 없지만
#:    골든셋 기록이나 붙여 둔 JSON 이 이 문자열을 들고 있을 수 있다. 지우지 말고 가리킨다.
MATCH_TEXT = MATCH_LITERAL

#: RRF 상수. `[문헌]` — Cormack·Clarke·Buettcher (SIGIR 2009) 가 제시한 값이고
#: 이후 하이브리드 검색 구현들이 기본값으로 쓴다.
#: 🚨 **이 수는 가중치가 아니다.** 갈래 사이의 비중이 아니라 **상위 순위를 얼마나 더
#:    쳐 주는가**의 완만함이다. k 를 바꿔도 한 갈래가 다른 갈래를 이기지 않는다 —
#:    그래서 [임의] 가중치가 판정 경로에 들어가는 문제가 여기에는 없다 (D-193).
RRF_K = PARAMS.rrf_k  # 🔄 값은 app/settings.py 가 든다 (D-99). 여기는 이름만 남긴다

#: 각 갈래에서 뽑아 오는 후보 수. **`[설계]` — 근거는 기획서 5-6 RAG 파이프라인이다** (D-201).
#:
#:      문장 -> [BM25 + 벡터 하이브리드] 상위 50
#:                    v
#:            [cross-encoder 리랭커] 상위 5
#:
#: ⛔ **2026-09-12 오후까지 `[임의]` 라 적혀 있었다.** 기획서에 있는 수를 「우리가 임의로
#:    고른 수」라 부른 것이다 — 문서를 안 펴고 태그를 붙였다 (D-100).
#: 🚨 **그렇다고 「고정값」도 아니다** (D-205 — 같은 날 D-201 을 고쳤다). 기획서 스스로
#:    이 수를 잠정으로 적었다: 8-4 #10 *"W1에 실제 청크 수를 보고 정합니다"* ·
#:    7-3 *"응답시간으로 실측해서"*. ★ **설계·탐색은 자유롭게, 결정은 실측과 검증으로.**
#:
#: 🔴 **바꾸는 조건 — 둘이 다 서야 한다** (원장 「판정 경로의 출처 태그」 표가 정본):
#:      ① 골든셋 30건 (D-40)
#:      ② 리랭커 선정 후 **응답시간 <500ms 실측** (D-77 예산표 · 기획서 7-3)
#:    ⬜ 부르는 실측은 **이미 있다** — 09-12 오후 「타사 제품보다 3배」가 벡터 112위였다.
#:       폭 50 이면 그 갈래에서 아예 안 보인다. ⛔ 그래도 지금 안 바꾼다: 3건이고(D-40),
#:       그 실측은 폭 50→200 과 제목뿐인 조 185개 제외가 **같이 들어간 수**다 (D-190).
POOL = PARAMS.pool  # 🔄 값은 app/settings.py · 바꾸는 조건도 거기 적혀 있다 (D-205)


class RetrieveError(RuntimeError):
    """검색을 할 수 없다. 🔴 **조용히 빈 목록을 내지 않는다** (D-220 fail-closed).

    ⛔ 빈 목록으로 떨어지면 「의미 검색을 했는데 0건」과 「의미 검색을 못 했다」가
       구별되지 않는다. 2026-09-12 에 `mark_collected` 가 같은 모양으로 틀렸다.
    """


class EmbeddingsMissing(RetrieveError):
    """`chunk_embedding` 이 비었다 — 이 기기에 적재가 안 됐다."""


class ModelsMixed(RetrieveError):
    """`chunk_embedding` 에 모델이 둘 이상이다 — 어느 벡터공간인지 정할 수 없다."""


class InputsMixed(RetrieveError):
    """`chunk_embedding` 에 문맥판과 무문맥판이 섞였다 — 거리가 뜻을 잃는다 (D-176)."""


class EncoderUnavailable(RetrieveError):
    """질의를 임베딩할 수 없다 — 라이브러리나 모델 가중치가 이 기기에 없다."""


@dataclasses.dataclass(frozen=True)
class Hit:
    """검색 결과 한 줄. `match` 가 **어느 갈래로 찾아졌는지**를 결과 자체에 남긴다."""

    chunk_id: str
    law_id: str | None
    article: str | None
    #: 항 — 「①」. 🚨 종전에는 `paragraph` 에 「①1.」이 뭉쳐 있었다 (2026-09-12 분리).
    paragraph: str | None
    #: 호 — 「1.」. ⛔ 종전에는 법령 쪽이 **늘 빈 칸**이었다.
    item: str | None
    #: 항 서수 — 원문에 「①」가 없어도 우리가 센 것. `paragraph` 가 비면 이쪽으로 인용한다.
    paragraph_no: int | None
    #: 자립 텍스트 (조 제목 + 항 본문). 🚨 `None` 은 **아직 재적재 안 됨**이고
    #:    빈 문자열은 **붙일 문맥이 없음**(조 청크·별표)이다. 둘을 한 값으로 만들지 않는다.
    context: str | None
    #: 쪼갠 조각 번호와 총수 (0011). 🔴 `part_total > 1` 이면 **이 근거는 조문의 일부다** —
    #:    `citation` 은 좌표로 맞지만 전문이 아니다. 화면과 인용 검증이 이 둘을 보고 말한다.
    #:    🚨 `None` 은 「아직 재적재 안 됨」이다. 1/1 로 채우지 않는다 (D-199).
    part_no: int | None
    part_total: int | None
    doc_type: str | None
    #: 🆕 별표 번호 — **원문 머리글에서 읽은 값만** (0015). `None` = 머리글에 번호가 없다.
    #:    ⛔ 파일명 일련번호가 아니다. `None` 이면 별표 인용을 세우지 않는다 (D-224).
    annex_no: int | None
    #: 🆕 문서 이름 — 사람이 읽는 자리. 🚨 **좌표가 아니다** (좌표는 `citation`).
    doc_title: str | None
    category: list[str]
    text: str
    attribution: str | None
    source_url: str | None
    match: str
    #: 「제8조제1항제1호」. 🔴 조립할 수 없으면 `None` — **부분 인용을 내지 않는다.**
    #:    「제8조」만 내면 실은 제3항인 근거가 제1항처럼 읽힌다. 틀린 인용은 없는 인용보다 나쁘다.
    citation: str | None = None
    #: 코사인 거리. 🚨 어휘·기호 갈래는 `None` 이다 — **0.0 으로 채우지 않는다.**
    #:    0.0 은 「완전히 같다」는 뜻이라, 없는 값을 가장 좋은 값으로 만든다.
    distance: float | None = None
    #: `ts_rank_cd` 원점수. 🚨 벡터 갈래는 `None` — 같은 이유로 0.0 을 안 넣는다.
    lexical: float | None = None
    # ── 아래 셋은 `search()` 가 합칠 때만 찬다 ────────────────────────────────
    #: 🔴 **합친 뒤에도 어느 갈래가 몇 위로 올렸는지 남긴다** (D-185 — 정본 축/관측 축).
    #:    ⛔ 합친 순위만 내면 「어휘가 올린 것」과 「벡터가 올린 것」이 구별되지 않고,
    #:       한 갈래가 죽어도 결과가 그럴듯해서 **안 보인다.** 2026-09-12 에 벡터 단독
    #:       6위/19위/50위밖을 잰 것이 바로 이 구별이었다.
    #:    🚨 1부터 센다. `None` 은 「그 갈래 후보에 없었다」이고 0 이 아니다.
    rank_vector: int | None = None
    rank_lexical: int | None = None
    #: RRF 합산 점수. 클수록 앞. 🚨 **갈래 간 비교용이 아니다** — 같은 질의 안에서만 뜻이 있다.
    rrf: float | None = None


# ── 거버넌스를 **질의로** 건다 (게이트가 아니다) ────────────────────────────
# 🔴 `source_use.allowed AND use_code='U2_rag'` 를 빼면 U2 가 안 열린 원천이 RAG 에 실린다.
#    `v_current_chunk` 를 안 쓰면 폐지된 조문과 제외된 프래그먼트가 섞인다.
#    ⛔ 이 조인 넷은 **두 질의 모두**에 있어야 한다. `tests/test_retrieve.py` 가 검사한다.
#: 🚨 **뽑는 칸과 이름을 한 곳에 둔다** — 자리번호로 꺼내면 칸이 늘 때 조용히 밀린다.
#:    `scripts/embed.py` 의 `CHUNK_COLS` 와 같은 처방이다 (D-99).
_SELECT: tuple[tuple[str, str], ...] = (
    ("c.chunk_id", "chunk_id"),
    ("c.law_id", "law_id"),
    ("c.article", "article"),
    # 🔴 2026-09-12 추가 — 이 둘이 없어 「제8조제1항제1호」로 인용할 수 없었다 (D-224).
    #    ⛔ `chunk.py` 는 채우고 있었는데 **읽는 쪽이 없었다** — 생산자만 있고 소비자 없는 값.
    ("c.paragraph", "paragraph"),
    ("c.item", "item"),
    # 🔴 2026-09-12 (0008) — 원문에 항번호가 없는 호가 31%(283/909)다. 원문(`paragraph`)과
    #    우리가 센 서수(`paragraph_no`)를 갈라 두고, 인용은 **둘 중 있는 쪽**으로 조립한다.
    ("c.paragraph_no", "paragraph_no"),
    # 🔴 자립 텍스트 — 임베딩이 본 것과 **같은 값**이다. 화면이 문맥으로 접어 보여 준다.
    ("c.context", "context"),
    # 🔴 2026-09-12 밤 (0011 · D-199) — **이 근거가 조문의 일부인가.**
    #    ⛔ `preprocess/chunk.py` 가 700자 초과 조문을 쪼개면서 만들던 값인데 **DB 에 열조차
    #       없어** 여기까지 온 적이 없다. 그래서 `citation()` 이 3분의 1짜리 조각에
    #       「제18조」를 달았고, 받는 쪽은 그것이 전문이 아니라는 것을 알 방법이 없었다.
    #    🚨 `part_total > 1` 이면 조각이다. `None` 은 **「아직 재적재 안 됨」**이고
    #       「안 쪼갰다」가 아니다 — 안 쪼갰으면 1/1 이다.
    ("c.part_no", "part_no"),
    ("c.part_total", "part_total"),
    ("c.doc_type", "doc_type"),
    ("c.category", "category"),
    ("c.text", "text"),
    # 🔴 2026-09-14 (0015) — **별표에 좌표를 세우려면 「몇 번 별표인가」가 있어야 한다.**
    #    ⛔ 종전에는 상위 5건 중 4건이 별표였고 **전부 버려졌다** — 하필
    #       013453 [별표 1]「부당한 표시 또는 광고의 내용」처럼 문구가 실제로 걸리는 자리다.
    #    🚨 `d.annex_no` 에는 **원문 머리글에서 읽은 값만** 들어 있다. NULL 이면 인용을
    #       세우지 않는다 — 파일명 일련번호로 짐작하지 않는다 (D-224 · D-72).
    ("d.annex_no", "annex_no"),
    #: 사람이 읽는 이름 — 「부당한 표시 또는 광고의 내용(제3조제1항 관련)」. 좌표가 아니다.
    ("d.title", "doc_title"),
    ("s.attribution", "attribution"),
    ("s.url", "source_url"),
)
_COLS = ",\n       ".join(e for e, _ in _SELECT)
_NAMES = tuple(n for _, n in _SELECT)
# 🔴 2026-09-14 — 다섯째 조인. ⛔ **`JOIN` 이 아니라 `LEFT JOIN` 이다** — `document` 행이
#    없는 청크가 있으면 `JOIN` 은 그 청크를 **검색 결과에서 통째로 지운다.** 거버넌스 조인 넷은
#    「자격이 없으면 안 나간다」가 뜻이지만, 이것은 **이름을 붙이려고** 드는 것이다.
#    ⛔ 없음을 배제로 바꾸면 *「없음이 성공으로 집계」* 의 거울상이 된다 — 조용히 줄어든다.
_JOINS = """FROM v_current_chunk c
JOIN fragment   f ON f.fragment_id = c.fragment_id
JOIN source     s ON s.source_id   = f.source_id
JOIN source_use u ON u.source_id   = s.source_id AND u.use_code = 'U2_rag'
LEFT JOIN document d ON d.doc_id = c.doc_id"""

SQL_LITERAL = f"""SELECT {_COLS}
{_JOINS}
WHERE u.allowed AND c.text ILIKE %s AND %s = ANY(c.category)
-- 🚨 정렬이 없으면 `LIMIT` 결과가 비결정적이다 — 같은 질의가 다른 답을 낸다.
ORDER BY c.law_id, c.article NULLS LAST, c.chunk_id
LIMIT %s"""

# 🔴 **어휘 갈래 (0010).** `chunk.tsv` 는 **생성열**이다 — 여기서 `to_tsvector(...)` 를
#    다시 쓰면 정의가 두 벌이 되고, 한쪽만 고치면 인덱스를 안 타면서 **조용히 느려진다** (D-99).
#    ⛔ `@@` 로 거르지 않고 `ts_rank_cd` 로만 정렬하면 안 걸린 행도 0점으로 전부 딸려 온다.
# 🚨 정규화 플래그 `32` = `rank/(rank+1)` — 0~1 로 눌러 담는다. `[관행]`
#    **길이 정규화(`2`)는 일부러 안 건다.** 짧은 청크가 유리해지는데, 제목뿐인 조 청크가
#    상위를 점령한 것이 2026-09-12 에 잰 바로 그 증상이었다 (D-195 로 그 청크는 뺐다).
SQL_LEXICAL = f"""SELECT {_COLS},
       ts_rank_cd(c.tsv, query, 32) AS lexical
{_JOINS},
     to_tsquery('simple', %s) AS query
WHERE u.allowed AND %s = ANY(c.category) AND c.tsv @@ query
-- 동점일 때도 같은 답을 내야 한다 — chunk_id 로 가른다 (D-176 의 결정성).
ORDER BY lexical DESC, c.chunk_id
LIMIT %s"""

SQL_VECTOR = f"""SELECT {_COLS},
       (e.embedding {VECTOR_OP} %s::vector) AS distance
{_JOINS}
JOIN chunk_embedding e ON e.chunk_id = c.chunk_id
-- 🔴 `model_id` 대조 — 저장한 벡터와 **같은 모델**로 만든 질의만 비교한다.
--    ⛔ 이 줄이 없으면 `embed.py` 가 행마다 적어 둔 `model_id` 를 아무도 안 읽는다.
WHERE u.allowed AND %s = ANY(c.category) AND e.model_id = %s
-- 거리 동점일 때도 같은 답을 내야 한다 — chunk_id 로 가른다.
ORDER BY distance, c.chunk_id
LIMIT %s"""

_model_cache: dict[str, Any] = {}


def stored_model_id(cur: Any) -> str:
    """저장된 벡터를 만든 모델. 🚨 **DB 가 정본이다** — 상수로 들지 않는다."""
    cur.execute("SELECT DISTINCT model_id FROM chunk_embedding")
    ids = sorted(r[0] for r in cur.fetchall())
    if not ids:
        raise EmbeddingsMissing(
            "chunk_embedding 이 비었다 — 이 기기에 임베딩이 없다. "
            "먼저: uv run python -m scripts.embed"
        )
    if len(ids) > 1:
        raise ModelsMixed(f"chunk_embedding 에 모델이 둘 이상이다: {ids}")
    return ids[0]


def check_inputs(cur: Any) -> None:
    """임베딩 입력판이 **한 벌인가** (0008 · D-176).

    🔴 `model_id` 는 문맥판과 무문맥판을 구별하지 못한다. 재임베딩을 중간에 멈추면
       두 벡터공간이 한 표에 섞이고 **거리가 조용히 뜻을 잃는다** — 오류도 안 난다.
    ★ 전부 NULL(옛판)이나 전부 채움(새판)은 통과시킨다. **섞인 것만** 막는다.
       「아직 안 옮겼다」는 상태이고, 「반쯤 옮겼다」는 사고다.
    """
    cur.execute(
        "SELECT count(*) FILTER (WHERE input_sha256 IS NULL), count(*) FROM chunk_embedding"
    )
    null_n, total = cur.fetchone()
    if total and null_n and null_n != total:
        raise InputsMixed(
            f"임베딩 입력판이 섞였다 — 지문 없는 행 {null_n:,} / 전체 {total:,}. "
            "재임베딩이 중간에 멈췄다. 다시: uv run python -m scripts.embed"
        )


def encode(model_id: str, text: str) -> list[float]:
    """질의 한 줄을 벡터로. 모델은 프로세스당 한 번만 로드한다."""
    model = _model_cache.get(model_id)
    if model is None:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as e:
            raise EncoderUnavailable(
                f"sentence-transformers 가 없다 — 질의를 임베딩할 수 없다 ({e})"
            ) from e
        # 🔴 **DB 에서 온 이름을 그대로 로드하지 않는다** (보안점검 P0-3 · D-212).
        #    허용 목록 밖이면 여기서 막는다 — `.bin`(pickle) 역직렬화 경로를 끊는다.
        try:
            kwargs = load_kwargs(model_id)
        except ValueError as e:
            raise EncoderUnavailable(str(e)) from e
        try:
            model = SentenceTransformer(model_id, **kwargs)
        except Exception as e:  # noqa: BLE001 — 내려받기 실패·가중치 없음 모두 같은 결말이다
            raise EncoderUnavailable(f"모델 {model_id!r} 을 로드하지 못했다 — {e}") from e
        _model_cache[model_id] = model
    return [float(x) for x in model.encode([text])[0]]


#: 항 표기 — 법제처 원문은 원문자다. 「제N항」으로 옮기려면 이 표가 있어야 한다.
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


#: 목의 글자 — 「가·나·다…」. 🚨 **`preprocess/law_norm.py` 의 `JO` 와 같은 값이다.**
#:    ⛔ 합치지 않았다 — `app/` 이 `preprocess/` 를 import 하면 런타임이 전처리 층에 매인다.
#:       그래서 D-99 의 나머지 절반을 쓴다: **양쪽에 서로를 가리키는 주석.**
#:       ★ 한쪽을 고치면 다른 쪽도 고친다. 게이트가 두 값이 같은지 본다.
_JO = "가나다라마바사아자차카타파하"

#: 별표 계층을 옮기는 말 — 깊이마다 **모양이 다르다** (2026-09-14 실측 · 301행 전부).
#:    깊이 0 `1`      → 제1호      (숫자)
#:    깊이 1 `1.가`   → 가목        (가나다 한 글자)
#:    깊이 2 `1.가.1` → 1)         (숫자)
#: 🔴 깊이 3(`dots=3`)은 **2행뿐이고 모양을 안 봤다** — 옮기지 않는다 (D-188 · D-224).
_ANNEX_DEPTH: tuple[tuple[str, str], ...] = (
    ("digit", "제{}호"),
    ("jo", "{}목"),
    ("digit", "{})"),
)
#: 별표의 구역 이름 중 **원문이 준 낱말**. ⛔ `구역N` 은 우리가 붙인 이름이라 인용에 안 쓴다.
_ANNEX_SECTIONS = {"본문": "", "비고": " 비고"}


def _annex_citation(hit_like: dict) -> str | None:
    """「[별표 1] 제2호가목1)」을 조립한다. 🔴 확신이 없으면 `None`.

    🚨 **번호가 있어야 시작한다.** `document.annex_no` 는 원문 머리글에서 읽은 값만 담는다
       (0015). ⛔ NULL 이면 포기한다 — 파일명 일련번호로 짐작하면 **다른 별표를 가리킬 수
       있다.** 실측(2026-09-14): 013475 의 `2.가.1` 이 `_0003`·`_0004` **두 별표**에 있다.

    🔴 **구역을 빠뜨리면 부분 인용이 된다.** 013453 [별표 1] 은 8호까지가 위법 유형이고 그
       뒤 「비고」에 **적용 제외**가 1호부터 다시 온다 (D-153 · D-156). 구역 없이
       「제1호」라 적으면 **위법 유형 1호와 적용제외 1호를 같은 좌표로** 가리킨다.
       ⛔ 그래서 우리가 붙인 이름(`구역N`)이면 **포기한다** — 원문에 없는 말을 넣지 않는다.
    """
    no = hit_like.get("annex_no")
    if not no:
        return None
    section = (hit_like.get("item") or "").strip()
    if section not in _ANNEX_SECTIONS:
        return None
    out = f"[별표 {int(no)}]{_ANNEX_SECTIONS[section]}"

    path = (hit_like.get("paragraph") or "").strip()
    if not path:
        return out
    parts = path.split(".")
    if len(parts) > len(_ANNEX_DEPTH):
        return None  # 깊이 3 이상 — 아는 모양이 아니다
    for token, (shape, fmt) in zip(parts, _ANNEX_DEPTH, strict=False):
        if shape == "digit":
            if not token.isdigit():
                return None
        elif len(token) != 1 or token not in _JO:
            return None
        out += fmt.format(token)
    return out


def citation(hit_like: dict) -> str | None:
    """「제8조제1항제1호」를 조립한다. 🔴 확신이 없으면 `None` 이다.

    🔄 **2026-09-14 — 별표에도 좌표를 세운다** (0015 · 판정 A). 종전 주석은
       *「⛔ 별표는 조립하지 않는다」* 였고, 그것은 **빠뜨린 것이 아니라 판정**이었다
       (`preprocess/chunk.py` 가 그렇게 적어 두었다). 그 판정을 다시 열었다 —
       실측으로 상위 5건 중 **4건이 별표**였고 전부 버려졌으며, 별표 301행(12.5%)이
       구조적으로 근거가 될 수 없었다. **규칙은 여전히 「모르면 `None`」이다.**
       ★ 별표 갈래는 `_annex_citation()` 에 따로 둔다 — 두 체계를 한 함수에 섞지 않는다.
    🚨 항·호가 예상 밖 표기면 **조까지만 내지 않고 통째로 포기한다** — 부분 인용은
       「제8조」라고 적어 놓고 실은 제3항인 근거를 가리킬 수 있다.

    🔴 **쪼갠 조각 여부는 여기 안 섞는다** (2026-09-12 밤 · D-199). 「제18조 (1/3)」처럼
       문자열에 붙이면 기획서 5-6 의 **인용 검증**(판정 결과의 조문 집합과 대조)이 문자열
       파싱이 된다. ★ **좌표는 좌표대로, 「일부다」는 `part_total` 칸으로** 낸다.
       ⛔ 그러므로 이 함수가 값을 냈다고 「조문 전문을 인용했다」가 아니다 — 받는 쪽은
          `part_total` 을 **같이** 봐야 한다. 게이트가 세 질의 모두 그 칸을 싣는지 본다.
    """
    # 🚨 **갈래를 먼저 가른다.** 별표는 조·항·호 규칙이 안 먹는다 — 다른 함수가 맡는다.
    if hit_like.get("doc_type") == "별표":
        return _annex_citation(hit_like)
    if hit_like.get("doc_type") != "법령":
        return None
    art = (hit_like.get("article") or "").strip()
    if not art:
        return None
    out = art
    para = (hit_like.get("paragraph") or "").strip()
    ho_raw = (hit_like.get("item") or "").strip()
    if para:
        i = _CIRCLED.find(para[:1])
        if i < 0 or para[1:]:  # 원문자 한 글자가 아니면 우리가 아는 모양이 아니다
            return None
        out += f"제{i + 1}항"
    elif hit_like.get("paragraph_no"):
        # ★ 원문에 항번호가 없어도 **우리가 센 서수**가 있으면 인용이 선다 (0008).
        #    「①」를 지어내 `paragraph` 에 넣지 않고, 옆 칸의 수를 여기서만 옮긴다 (D-117).
        out += f"제{int(hit_like['paragraph_no'])}항"
    elif ho_raw:
        # 🔴 **호가 있는데 항번호가 없다 — 항이 없는 게 아니다** (2026-09-12 실측 283건 · 호의 31%).
        #    법제처 XML 은 **항이 하나뿐인 조에 `<항번호>` 를 주지 않는다.** 「①」를 안 쓰니까.
        #    그런데 `law_article.py` 는 `hang.iter("호")` 로만 호를 만드므로 **조 직속 호는 없다** —
        #    빈 항번호는 「항이 없다」가 아니라 **「번호가 표기되지 않은 제1항」**이다.
        # ⛔ 여기서 항을 건너뛰면 「제10조제3호」가 되는데 정확한 인용은 「제10조제1항제3호」다.
        #    그것이 이 함수가 막으려는 **부분 인용** 바로 그것이다 (D-224).
        # 🚨 여기에 오는 것은 `paragraph_no` 조차 없는 행 — **0008 재적재 전**이거나
        #    법령이 아닌 경로로 들어온 것이다. 지어내지 않고 포기한다.
        return None
    ho = ho_raw.rstrip(".")
    if ho:
        if not ho.isdigit():
            return None
        out += f"제{ho}호"
    return out


def _rows_to_hits(rows: list[tuple], match: str, *, score: str | None = None) -> list[Hit]:
    """🚨 자리번호가 아니라 **이름으로** 꺼낸다 — 칸이 늘어도 조용히 밀리지 않는다.

    `score` 는 `_SELECT` 뒤에 하나 더 붙은 칸의 **이름**이다 (`distance` 또는 `lexical`).
    🔴 이름을 받는다 — `has_distance=True/False` 였을 때는 갈래가 셋이 되는 순간
       불리언이 하나 더 늘 참이었다. 늘어날 값에 불리언을 쓰지 않는다.
    """
    out = []
    for r in rows:
        d = dict(zip(_NAMES, r, strict=False))
        d["category"] = list(d.get("category") or [])
        extra = {score: float(r[len(_NAMES)])} if score else {}
        out.append(Hit(**d, match=match, citation=citation(d), **extra))
    return out


# ── 질의를 어휘로 바꾼다 ───────────────────────────────────────────────────────
#: 🚨 **형태소 분석기를 안 쓴다 — 빠뜨린 것이 아니라 판정이다** (D-194).
#:    mecab-ko 를 쓰려면 PostgreSQL 이미지를 갈아야 하는데, 스택 핀이
#:    `pgvector/pgvector:0.8.6-pg16-bookworm` 으로 박혀 있다. 이미지를 갈면 pgvector
#:    버전까지 같이 흔들린다. `simple` 파서는 **공백으로만** 자르므로 조사가 붙어 오고,
#:    그것을 아래 두 가지로 메운다 — 조사 깎기 + 접두어 매칭.
#: ⬜ 이 처방은 **근사다.** 「했다/하였다」 같은 어미 변형은 접두어로 안 잡힌다.
#:    제대로 하려면 형태소 분석이고, 그것은 이미지 교체 판정과 함께 간다.
#: 🚨 **길이 내림차순이라야 한다** — 「에서는」을 「는」보다 먼저 만나야 한 겹만 깎인다.
#:    ⛔ 이 순서는 **눈으로 지키지 않는다.** 처음에 세 글자·두 글자·한 글자를 줄로 나눠 적었는데
#:       `ruff --fix`(SIM905)가 한 줄로 폈다 — **읽으라고 만든 배치는 포매터가 지워 준다.**
#:    ★ 그래서 배치가 아니라 게이트가 지킨다: `test_조사표가_길이_내림차순이다`.
_JOSA = tuple(
    [
        "에서는",
        "으로서",
        "으로써",
        "에게서",
        "이라고",
        "에서도",
        "에게는",
        "라고",
        "에게",
        "한테",
        "께서",
        "부터",
        "까지",
        "보다",
        "처럼",
        "마다",
        "조차",
        "밖에",
        "으로",
        "이나",
        "에는",
        "에도",
        "에서",
        "이란",
        "라는",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "와",
        "과",
        "도",
        "만",
        "로",
        "나",
    ]
)
#: 어절에서 남길 글자 — 한글·영숫자. 🚨 `to_tsquery` 에 들어갈 문자열이므로
#:    `&`·`|`·`!`·`:`·`(`·`)` 가 섞이면 **구문 오류로 500** 이 난다. 화이트리스트로 막는다.
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")
#: 조사를 깎은 뒤 이보다 짧아지면 **안 깎는다.** ⛔ 「효과」→「효」, 「제품」→「제」처럼
#:    낱말 자체가 조사로 끝나는 것을 깎으면 뜻이 없는 접두어가 되어 아무 데나 붙는다.
_MIN_STEM = PARAMS.min_stem


def _stem(word: str) -> str:
    """어절에서 조사를 한 겹 깎는다. 🚨 못 깎으면 **그대로 돌려준다** (지어내지 않는다)."""
    for j in _JOSA:  # 긴 것부터 — `_JOSA` 가 길이 내림차순으로 적혀 있다
        if word.endswith(j) and len(word) - len(j) >= _MIN_STEM:
            return word[: -len(j)]
    return word


#: 어절 전체가 조사인 것 — 「이 제품은…」의 「이」. 🔴 **검색어에서 뺀다.**
#:    ⛔ 접두어 매칭이라 `이:*` 는 「이하」·「이상」·「이내」에 전부 붙는다.
#:    한 글자라고 빼는 것이 아니다 — 「암」·「독」은 남아야 한다. **조사만** 뺀다.
_JOSA_SET = frozenset(_JOSA)


def terms(q: str) -> list[str]:
    """질의 → 검색어들. 순서를 지키고 중복은 앞의 것만 남긴다 (결정성)."""
    out: list[str] = []
    for w in _WORD.findall(q):
        s = _stem(w)
        if s and s not in _JOSA_SET and s not in out:
            out.append(s)
    return out


def tsquery(q: str) -> str:
    """`to_tsquery('simple', ...)` 에 넣을 문자열. 🔴 없으면 **빈 문자열**이다.

    🚨 **`&`(AND)가 아니라 `|`(OR)로 묶는다.** 광고 문구는 어절이 여남은 개이고
       조문이 그 전부를 담는 일은 없다 — AND 면 거의 언제나 0건이다. OR 로 받고
       **몇 개나 겹쳤는지로 `ts_rank_cd` 가 순위를 매긴다** (BM25 의 자리).
    🚨 `:*` 는 접두어 매칭이다. 문서 쪽 어절에도 조사가 붙어 있으므로
       질의 「면역력」이 문서의 「면역력을」·「면역력이」를 잡는다.
    """
    return " | ".join(f"{t}:*" for t in terms(q))


def by_literal(
    cur: Any, q: str, category: str = DEFAULT_CATEGORY, limit: int = PARAMS.top_k
) -> list[Hit]:
    """글자가 그대로 들어 있는 것. 「제5호 아목」처럼 **기호**로 찾을 때 이쪽이다.

    🔴 **어휘 갈래로 대체하지 않는다** (D-167). `simple` 파서는 「제5호」를 어떻게
       자를지 보장하지 않고, 기호 검색은 **부분 일치가 아니라 정확히 그 글자**를 원한다.
       두 가지는 이름만 비슷하고 뜻이 다르다 — 한쪽으로 합치면 둘 다 나빠진다.
    """
    cur.execute(SQL_LITERAL, (f"%{q}%", category, limit))
    return _rows_to_hits(cur.fetchall(), MATCH_LITERAL)


#: ⛔ 옛 이름. 부르는 곳이 남아 있을 수 있어 가리켜만 둔다 (D-192 — 폐기는 계약에 적는다).
by_text = by_literal


def by_lexical(
    cur: Any, q: str, category: str = DEFAULT_CATEGORY, limit: int = PARAMS.top_k
) -> list[Hit]:
    """어휘가 겹치는 것. 🔴 검색어가 하나도 안 남으면 **빈 목록**이다 — 오류가 아니다.

    ⛔ 빈 `to_tsquery` 를 그대로 넣으면 PostgreSQL 이 경고를 내고 0건을 준다. 같은 0건이라도
       「질의에 검색어가 없다」와 「겹치는 조문이 없다」는 다른 사실이라, 여기서 가른다.
    """
    tq = tsquery(q)
    if not tq:
        return []
    cur.execute(SQL_LEXICAL, (tq, category, limit))
    return _rows_to_hits(cur.fetchall(), MATCH_LEXICAL, score="lexical")


def by_vector(
    cur: Any, text: str, category: str = DEFAULT_CATEGORY, limit: int = PARAMS.top_k
) -> list[Hit]:
    """뜻이 가까운 것. 「면역력 쑥!」처럼 **글자가 안 겹치는** 광고 문구가 이쪽이다.

    🔴 못 하면 `RetrieveError` 를 던진다 — **빈 목록으로 떨어지지 않는다.**
    """
    model_id = stored_model_id(cur)
    check_inputs(cur)
    vec = encode(model_id, text)
    literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    cur.execute(SQL_VECTOR, (literal, category, model_id, limit))
    return _rows_to_hits(cur.fetchall(), MATCH_VECTOR, score="distance")


def fuse(
    vector_hits: list[Hit], lexical_hits: list[Hit], *, k: int = RRF_K, limit: int = PARAMS.top_k
) -> list[Hit]:
    """두 순위를 RRF 로 섞는다 — `Σ 1/(k + 순위)` (D-193).

    🔴 **점수를 안 쓰고 순위만 쓴다.** 그래서 「코사인 거리 0.62 와 ts_rank 0.041 을 어떻게
       더하나」라는 물음이 생기지 않는다. 두 갈래의 눈금이 달라도 상관없다.
    🚨 한 갈래에만 있는 행도 들어온다 — 그쪽 항만 더해진다. ⛔ 없는 쪽을 **최하위로
       채워 넣지 않는다.** 후보 50개 밖은 「50위」가 아니라 「모른다」다 (D-188).
    🚨 동점은 `chunk_id` 로 가른다 — 같은 질의가 두 번 다른 답을 내면 안 된다.
    """
    ranks: dict[str, dict[str, int]] = {}
    base: dict[str, Hit] = {}
    #: 갈래별 원점수 — 🚨 `distance` 와 `lexical` 은 **서로 다른 갈래가 들고 온다.**
    #:    한 행에 둘 다 실리려면 행이 아니라 칸을 모아야 한다.
    scores: dict[str, dict[str, float]] = {}
    for field, hits in (("rank_vector", vector_hits), ("rank_lexical", lexical_hits)):
        for i, h in enumerate(hits, start=1):
            ranks.setdefault(h.chunk_id, {})[field] = i
            base.setdefault(h.chunk_id, h)
            # 🔴 **점수는 행이 아니라 칸 단위로 모은다** (2026-09-12 오후 실측으로 고침).
            #    ⛔ 종전에는 `base.setdefault` 로 **벡터 쪽 행 통째**를 들고 갔다. 그러면
            #       양쪽에 다 걸린 줄이 `rank_lexical=3` 인데 `lexical=null` 로 나간다 —
            #       **어휘가 올렸다고 말하면서 그 점수는 안 보여 주는 상태**다.
            #    🚨 거리에만 대칭을 맞춰 두고 반대쪽을 안 봤다. 게이트도 `distance` 만 봤다.
            if h.distance is not None:
                scores.setdefault(h.chunk_id, {})["distance"] = h.distance
            if h.lexical is not None:
                scores.setdefault(h.chunk_id, {})["lexical"] = h.lexical
    scored = []
    for cid, r in ranks.items():
        score = sum(1.0 / (k + rank) for rank in r.values())
        scored.append(
            dataclasses.replace(
                base[cid],
                match=MATCH_FUSED,
                rank_vector=r.get("rank_vector"),
                rank_lexical=r.get("rank_lexical"),
                rrf=score,
                **scores.get(cid, {}),
            )
        )
    scored.sort(key=lambda h: (-(h.rrf or 0.0), h.chunk_id))
    return scored[:limit]


#: 벡터 갈래가 돌았다. 🚨 `LEXICAL_OK` 와 **값이 같아도 축이 다르다** — 한 상수로 합치지
#:    않는다. 합치면 「어휘가 ok 다」와 「벡터가 ok 다」를 같은 이름으로 부르게 된다 (D-167).
#:    ⛔ 부르는 쪽이 `"ok"` 를 손으로 적지 않게 이름을 준다 — 판정 경로의 매직 문자열이다 (D-99).
VECTOR_OK = "ok"

#: 어휘 갈래가 「할 수 있었는가」. 🔴 **0건에는 두 뜻이 있다** — 겹치는 조문이 없었거나,
#:    애초에 검색어를 못 만들었거나. `by_lexical` 이 그 둘을 가른다고 적어 놓고
#:    **둘 다 `[]` 를 냈다** — 부르는 쪽에서는 구별이 없었다 (2026-09-12 밤 · D-202).
LEXICAL_OK = "ok"
LEXICAL_NO_TERMS = "no_terms: 질의에서 검색어를 못 만들었다 — 어절이 전부 조사이거나 기호뿐이다"


@dataclasses.dataclass(frozen=True)
class SearchState:
    """한 번의 검색이 **무엇을 할 수 있었는가**. 🔴 결과 목록이 답하지 못하는 것을 답한다.

    ⛔ 종전에는 `vector` 문자열 하나였다. 그러면 셋을 구별할 수 없다 —
       ① 벡터가 못 돌았다 ② 벡터가 돌았고 후보가 0이었다 ③ **후보는 있었는데 상위에 못 들었다.**
       `counts` 만 보면 ②와 ③이 같은 0 이다 (2026-09-12 밤 · D-202).
    🚨 **분모를 같이 낸다** — `pool_*` 는 후보 폭(`pool`) 안의 수이고, 상위 진입 수는
       `limit` 안의 수다. 서로 다른 분모를 한 칸에 담지 않는다 (D-178).
    """

    #: `ok` 이거나 벡터가 **안 된 이유** 그대로.
    vector: str
    #: `LEXICAL_OK` 이거나 `LEXICAL_NO_TERMS`.
    lexical: str
    #: 후보 폭 — 이 수가 `pool_*` 의 분모다. 기획서 5-6 이 고정한 50 이 기본이다.
    pool: int
    #: 갈래별 **후보** 수 (합치기 전, `pool` 안).
    pool_vector: int
    pool_lexical: int


def search(
    cur: Any,
    q: str,
    category: str = DEFAULT_CATEGORY,
    limit: int = PARAMS.top_k,
    pool: int = POOL,
) -> tuple[list[Hit], SearchState]:
    """부르는 쪽이 쓰는 하나의 문. `(결과, 상태)` 를 낸다.

    🔴 **벡터가 안 돼도 어휘 결과는 낸다 — 대신 왜 안 됐는지를 같이 낸다** (D-220 · D-162).
       ⛔ 예외를 위로 던지면 화면이 통째로 500 이 되고, 삼키면 「의미 검색을 했는데 0건」과
          「의미 검색을 못 했다」가 구별되지 않는다. **둘 다 아니게** 상태를 같이 낸다.
    🚨 상태를 만드는 자리는 여기 하나다 — `app/api.py` 가 같은 문장을 또 짓지 않는다.
    """
    vector_state = VECTOR_OK
    vector_hits: list[Hit] = []
    try:
        vector_hits = by_vector(cur, q, category, pool)
    except RetrieveError as e:
        vector_state = f"{type(e).__name__}: {e}"
    lexical_hits = by_lexical(cur, q, category, pool)
    # 🚨 `terms()` 를 다시 부른다 — 판단을 복사하는 것이 아니라 **같은 함수**를 쓴다 (D-99).
    state = SearchState(
        vector=vector_state,
        lexical=LEXICAL_OK if terms(q) else LEXICAL_NO_TERMS,
        pool=pool,
        pool_vector=len(vector_hits),
        pool_lexical=len(lexical_hits),
    )
    return fuse(vector_hits, lexical_hits, limit=limit), state
