"""embed.py — 청크를 KURE-v1 로 임베딩해 pgvector 에 넣는다 (D-41 · D-84 ⑪).

  uv run python -m scripts.embed --check      # 모델 차원만 확인한다 (DB 불필요)
  uv run python -m scripts.embed              # chunk + chunk_embedding 적재

왜 있는가 — 2026-09-09 확인: 임베딩 코드가 **0줄**이었다. pgvector 확장과
`chunk_embedding.embedding vector(1024)` 는 서 있는데 채우는 것이 없었다.

🚨 **`vector(1024)` 가 KURE-v1 과 맞는지 아무도 안 재 봤다.** 스키마의 1024 는 설계 시점의
   값이고, 모델이 다른 차원을 내면 **적재가 통째로 실패한다.** `--check` 가 그것만 잰다 —
   모델을 내려받아 한 문장을 임베딩하고 차원을 찍는다. DB 없이 돈다.
   🔴 어긋나면 **고칠 곳이 셋**이다: `db/schema.sql` · 부록 문서 · 마이그레이션.
      게이트 `test_벡터_차원이_한_곳에만_있다` 가 그 셋의 일치를 본다.

🚨 모델을 코드에 박지 않고 상수 하나로 둔다. `chunk_embedding.model_id` 에 그대로 들어가
   **어느 모델이 만든 벡터인지**가 행에 남는다 — 모델을 바꾸면 섞이면 안 된다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "derived" / "chunks.jsonl"

MODEL_ID = "nlpai-lab/KURE-v1"
DIM = 1024  # 🚨 db/schema.sql 의 vector(1024) 와 같아야 한다
BATCH = 32

# ── chunk 적재 — 🔴 **칸 목록이 한 곳이다** (2026-09-12 · D-99) ─────────────
# ⛔ 종전에는 INSERT 칸·VALUES·DO UPDATE SET·값 튜플이 **네 벌**이었다. 그래서 09-10 에
#    `token_count` 를 넣도록 고쳤는데 `DO UPDATE SET` 에 안 넣어 **기존 2,585행이 널로
#    남았다.** 마이그레이션 0006 은 「먼저 embed 를 돌려라」고 안내했고 — 돌려도 안 채워졌다.
#    🚨 그때 남긴 처방은 *「넣는 칸이 늘면 갱신 칸도 같이 늘린다」*는 **사람이 지키는 규칙**이었다.
#       2026-09-12 에 `paragraph`·`item` 을 고치면서 **같은 자리를 또 밟을 뻔했다.**
# ★ 그래서 규칙을 없애고 **구조로 옮긴다** — 칸을 여기 한 줄에만 적으면 나머지가 따라온다.
#   D-189 가 호출 경로에 대해 한 것과 같다: 갈릴 수 있는 두 벌을 한 벌로 만든다.
CHUNK_COLS = (
    "chunk_id",
    "fragment_id",
    "doc_id",
    "law_id",
    "article",
    "paragraph",
    "item",
    # 🔴 2026-09-12 (0008) — 항 서수와 자립 텍스트. 여기 한 줄 더하면 나머지가 따라온다.
    "paragraph_no",
    "context",
    "doc_type",
    "category",
    "text",
    "token_count",
)
#: 기본키는 갱신하지 않는다 — 나머지는 **전부** 갱신한다.
CHUNK_UPDATABLE = tuple(c for c in CHUNK_COLS if c != "chunk_id")
SQL_CHUNK_UPSERT = (
    f"INSERT INTO chunk ({', '.join(CHUNK_COLS)}) "
    f"VALUES ({', '.join(['%s'] * len(CHUNK_COLS))}) "
    "ON CONFLICT (chunk_id) DO UPDATE SET "
    + ", ".join(f"{c}=EXCLUDED.{c}" for c in CHUNK_UPDATABLE)
)


def embed_input(r: dict) -> str:
    """모델에 실제로 넣는 문자열 — `context` + `text` (2026-09-12 · 0008).

    🔴 **`text` 를 바꾸지 않는다.** 인용 단위는 호 그대로 두고 **검색이 보는 것만** 키운다.
       「1. 마약」이 「① …제조·수입하여서는 아니 된다 / 1. 마약」으로 임베딩되어
       엉뚱한 질의에 붙지 않게 된다. `chunk_id` 도 `text` 도 그대로라 골든셋이 안 흔들린다.
    🚨 **화면이 보여 주는 문맥과 같은 값**이다 (`chunk.context`). 두 문자열이면 갈린다 (D-99).
    """
    ctx = (r.get("context") or "").strip()
    return f"{ctx}\n{r['text']}" if ctx else r["text"]


def input_fingerprint(r: dict) -> str:
    """임베딩 입력의 sha256 — 재현의 근거는 seed 가 아니라 **입력 지문**이다 (D-176).

    ⛔ `model_id` 만으로는 문맥판과 무문맥판이 구별되지 않는다. 재임베딩을 중간에 멈추면
       두 벡터공간이 한 표에 섞이고 **거리는 조용히 뜻을 잃는다.**
    """
    return hashlib.sha256(embed_input(r).encode("utf-8")).hexdigest()


EMB_COLS = ("chunk_id", "embedding", "model_id", "input_sha256")
EMB_UPDATABLE = tuple(c for c in EMB_COLS if c != "chunk_id")
SQL_EMB_UPSERT = (
    f"INSERT INTO chunk_embedding ({', '.join(EMB_COLS)}) "
    f"VALUES ({', '.join(['%s'] * len(EMB_COLS))}) "
    "ON CONFLICT (chunk_id) DO UPDATE SET " + ", ".join(f"{c}=EXCLUDED.{c}" for c in EMB_UPDATABLE)
)


def chunk_values(r: dict, model) -> tuple:  # noqa: ANN001 — model 은 지연 로드 타입이다
    """`CHUNK_COLS` 순서로 값을 낸다. 🚨 **순서를 손으로 맞추지 않는다.**

    🔴 `token_count` 는 **실제로 센다** (2026-09-10). ⛔ 종전에는 항상 `None` 이라
       `ck_chunk_tokens`(512 상한)가 **영구히 무효**였다. 설계 문서는 「900토큰 청크 거부
       확인」을 성과로 적어 뒀는데 실무에서는 안 걸렸다 (D-170).
    🚨 임베딩 모델의 토크나이저로 센다 — 상한이 그 모델의 상한이기 때문이다.
    """
    v = {**r, "token_count": _tokens(model, r["text"])}
    missing = [c for c in CHUNK_COLS if c not in v]
    if missing:
        raise SystemExit(f"🔴 청크에 칸이 없다: {missing} — preprocess.chunk 를 다시 돌린다")
    return tuple(v[c] for c in CHUNK_COLS)


def dsn() -> str:
    return os.environ.get("DATABASE_URL") or (
        "postgresql://copylane:copylane@localhost:5432/copylane"
    )


def _tokens(model, text: str) -> int | None:
    """임베딩 모델 토크나이저로 센 토큰 수. 못 세면 `None` — **지어내지 않는다**.

    🚨 상한(`ck_chunk_tokens` 512)은 **이 모델의 상한**이므로 이 토크나이저로 세야 뜻이 맞다.
    """
    try:
        tok = model.tokenizer
    except AttributeError:
        return None
    try:
        return len(tok.encode(text, add_special_tokens=True))
    except Exception:  # noqa: BLE001 — 토크나이저 종류가 달라도 적재는 계속한다
        return None


def load_model():  # noqa: ANN201
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "🚨 sentence-transformers 가 없다 — `uv add sentence-transformers` 후 다시 돌린다",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    return SentenceTransformer(MODEL_ID)


def main() -> int:
    ap = argparse.ArgumentParser(description="청크 임베딩 → pgvector")
    ap.add_argument("--check", action="store_true", help="모델 차원만 확인한다 (DB 불필요)")
    ap.add_argument("--limit", type=int, default=0, help="앞의 N개만 (연습용)")
    args = ap.parse_args()

    model = load_model()
    if args.check:
        v = model.encode(["부당한 표시·광고의 내용"])[0]
        print(f"  모델 {MODEL_ID}")
        print(f"  차원 {len(v)}  vs 스키마 vector({DIM})")
        if len(v) != DIM:
            print("\n🚨 어긋난다. 고칠 곳이 셋이다 —", file=sys.stderr)
            print("   db/schema.sql · docs/02_설계/거버넌스데이터층_DDL.md 부록 ·", file=sys.stderr)
            print("   alembic/versions/0001_governance_layer.py", file=sys.stderr)
            print("   게이트 test_벡터_차원이_한_곳에만_있다 가 셋의 일치를 본다.", file=sys.stderr)
            return 1
        print("  ✅ 맞다")
        return 0

    if not CHUNKS.exists():
        print("청크가 없다 — `python -m preprocess.chunk --dump` 를 먼저 돌린다", file=sys.stderr)
        return 1
    rows = [json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.limit:
        rows = rows[: args.limit]

    import psycopg

    conn = psycopg.connect(dsn())
    with conn, conn.cursor() as cur:
        # 🚨 청크를 먼저 넣는다 — chunk_embedding 이 chunk 를 가리킨다
        for r in rows:
            cur.execute(SQL_CHUNK_UPSERT, chunk_values(r, model))
        done = 0
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            vecs = model.encode([embed_input(b) for b in batch])
            for b, v in zip(batch, vecs, strict=True):
                if len(v) != DIM:
                    raise SystemExit(f"🚨 차원이 {len(v)} 다 — vector({DIM}) 와 어긋난다")
                cur.execute(
                    SQL_EMB_UPSERT,
                    (
                        b["chunk_id"],
                        "[" + ",".join(f"{x:.6f}" for x in v) + "]",
                        MODEL_ID,
                        input_fingerprint(b),
                    ),
                )
            done += len(batch)
            print(f"    {done}/{len(rows)}", end="\r")
    # 🚨 **넣은 수가 아니라 들어간 수를 센다** (D-149 · 2026-09-09).
    #    ⛔ 첫 실행에서 「임베딩 2594」라 찍었는데 DB 에는 2,297 이었다.
    #       `ON CONFLICT` 가 297행을 덮었고 출력은 그것을 몰랐다.
    with psycopg.connect(dsn()) as check, check.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunk")
        n_chunk = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM chunk_embedding WHERE model_id = %s", (MODEL_ID,))
        n_emb = cur.fetchone()[0]
    print(f"\n  보낸 행 {len(rows)} · DB chunk {n_chunk} · embedding {n_emb} ({MODEL_ID})")
    if n_chunk < len(rows):
        print(
            f"  🚨 {len(rows) - n_chunk}행이 들어가지 않았다 — chunk_id 가 겹친다 (D-149)",
            file=sys.stderr,
        )
        return 1
    print("  ✅ 보낸 수와 들어간 수가 같다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
