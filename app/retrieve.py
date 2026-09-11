"""app/retrieve.py — 조문 검색 코어. 두 소비자가 이것을 부른다 (D-99 · D-51).

    app/api.py    /search       by_vector + by_text 둘 다
                                사람이 친 말은 **뜻일 수도 기호일 수도** 있다
    app/graph.py  retrieve()    by_vector 만
                                입력이 **광고 문구**라 조문 번호가 올 일이 없다

🔴 **둘을 합치는 규칙은 여기 없다 — 없는 것이 계약이다** (D-192).
   순위를 섞으려면 「벡터 거리 0.83 과 글자 일치를 어떻게 더하나」라는 가중치가 필요한데,
   그 수에는 근거가 없다. **[임의] 임계값이 판정 경로에 하나 더 생긴다.**
   합칠지 말지는 **부르는 쪽이 정한다.** 코어는 두 갈래를 따로 낸다.

🚨 **모델 이름을 상수로 들지 않는다.** `chunk_embedding.model_id` 를 DB 에서 읽어
   **저장된 벡터를 만든 그 모델**을 로드한다. 상수를 손으로 맞출 자리가 없어지고
   (`scripts/embed.py` 와 두 벌이 되지 않는다), 질의 벡터와 저장 벡터가
   **구조적으로 같은 모델**이 된다 — 다르면 거리는 뜻 없는 수다.

⬜ **벡터 인덱스를 만들지 않았다 — 빠뜨린 것이 아니라 판정이다** (D-192).
   지금 규모(청크 수천)에서는 순차 스캔이 더 빠르다. `ivfflat` 은 `lists` 를 데이터 수에
   맞춰야 하고, 잘못 잡으면 **재현율이 조용히 떨어진다** — 느린 것보다 나쁘다.
   🚨 행 수는 여기 적지 않는다 — 기기마다 다르고(`data/` 미커밋), 적으면 낡는다.
   한 자릿수 만 단위로 가면 그때 `lists` 를 실측해서 만든다.

⬜ **리랭커(`bge-reranker-v2-m3`)도 아직 넣지 않았다.** `db/schema.sql` 의
   `ck_chunk_tokens CHECK (token_count <= 512)` 가 그 리랭커의 상한에 맞춰져 있어
   자리는 준비돼 있다. 모델 하나와 임계값 하나가 더 붙는 일이라 따로 판정한다.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: 🚨 코사인이라야 한다. `scripts/embed.py` 는 `model.encode(...)` 를 그대로 쓰므로
#:    저장된 벡터가 **정규화돼 있지 않다.** `<->`(L2)는 길이에 끌려가 뜻이 달라진다.
VECTOR_OP = "<=>"

MATCH_VECTOR = "vector"
MATCH_TEXT = "text"


class RetrieveError(RuntimeError):
    """검색을 할 수 없다. 🔴 **조용히 빈 목록을 내지 않는다** (D-72 fail-closed).

    ⛔ 빈 목록으로 떨어지면 「의미 검색을 했는데 0건」과 「의미 검색을 못 했다」가
       구별되지 않는다. 2026-09-12 에 `mark_collected` 가 같은 모양으로 틀렸다.
    """


class EmbeddingsMissing(RetrieveError):
    """`chunk_embedding` 이 비었다 — 이 기기에 적재가 안 됐다."""


class ModelsMixed(RetrieveError):
    """`chunk_embedding` 에 모델이 둘 이상이다 — 어느 벡터공간인지 정할 수 없다."""


class EncoderUnavailable(RetrieveError):
    """질의를 임베딩할 수 없다 — 라이브러리나 모델 가중치가 이 기기에 없다."""


@dataclasses.dataclass(frozen=True)
class Hit:
    """검색 결과 한 줄. `match` 가 **어느 갈래로 찾아졌는지**를 결과 자체에 남긴다."""

    chunk_id: str
    law_id: str | None
    article: str | None
    doc_type: str | None
    category: list[str]
    text: str
    attribution: str | None
    source_url: str | None
    match: str
    #: 코사인 거리. 🚨 `by_text` 는 `None` 이다 — **0.0 으로 채우지 않는다.**
    #:    0.0 은 「완전히 같다」는 뜻이라, 없는 값을 가장 좋은 값으로 만든다.
    distance: float | None = None


# ── 거버넌스를 **질의로** 건다 (게이트가 아니다) ────────────────────────────
# 🔴 `source_use.allowed AND use_code='U2_rag'` 를 빼면 U2 가 안 열린 원천이 RAG 에 실린다.
#    `v_current_chunk` 를 안 쓰면 폐지된 조문과 제외된 프래그먼트가 섞인다.
#    ⛔ 이 조인 넷은 **두 질의 모두**에 있어야 한다. `tests/test_retrieve.py` 가 검사한다.
_COLS = (
    "c.chunk_id, c.law_id, c.article, c.doc_type, c.category, c.text,\n       s.attribution, s.url"
)
_JOINS = """FROM v_current_chunk c
JOIN fragment   f ON f.fragment_id = c.fragment_id
JOIN source     s ON s.source_id   = f.source_id
JOIN source_use u ON u.source_id   = s.source_id AND u.use_code = 'U2_rag'"""

SQL_TEXT = f"""SELECT {_COLS}
{_JOINS}
WHERE u.allowed AND c.text ILIKE %s AND %s = ANY(c.category)
-- 🚨 정렬이 없으면 `LIMIT` 결과가 비결정적이다 — 같은 질의가 다른 답을 낸다.
ORDER BY c.law_id, c.article NULLS LAST, c.chunk_id
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
        try:
            model = SentenceTransformer(model_id)
        except Exception as e:  # noqa: BLE001 — 내려받기 실패·가중치 없음 모두 같은 결말이다
            raise EncoderUnavailable(f"모델 {model_id!r} 을 로드하지 못했다 — {e}") from e
        _model_cache[model_id] = model
    return [float(x) for x in model.encode([text])[0]]


def _rows_to_hits(rows: list[tuple], match: str, *, has_distance: bool) -> list[Hit]:
    return [
        Hit(
            chunk_id=r[0],
            law_id=r[1],
            article=r[2],
            doc_type=r[3],
            category=list(r[4] or []),
            text=r[5],
            attribution=r[6],
            source_url=r[7],
            match=match,
            distance=float(r[8]) if has_distance else None,
        )
        for r in rows
    ]


def by_text(cur: Any, q: str, category: str = "일반", limit: int = 5) -> list[Hit]:
    """글자가 그대로 들어 있는 것. 「제5호 아목」처럼 **기호**로 찾을 때 이쪽이다."""
    cur.execute(SQL_TEXT, (f"%{q}%", category, limit))
    return _rows_to_hits(cur.fetchall(), MATCH_TEXT, has_distance=False)


def by_vector(cur: Any, text: str, category: str = "일반", limit: int = 5) -> list[Hit]:
    """뜻이 가까운 것. 「면역력 쑥!」처럼 **글자가 안 겹치는** 광고 문구가 이쪽이다.

    🔴 못 하면 `RetrieveError` 를 던진다 — **빈 목록으로 떨어지지 않는다.**
    """
    model_id = stored_model_id(cur)
    vec = encode(model_id, text)
    literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    cur.execute(SQL_VECTOR, (literal, category, model_id, limit))
    return _rows_to_hits(cur.fetchall(), MATCH_VECTOR, has_distance=True)
