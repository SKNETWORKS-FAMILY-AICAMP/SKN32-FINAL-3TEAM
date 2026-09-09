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
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "derived" / "chunks.jsonl"

MODEL_ID = "nlpai-lab/KURE-v1"
DIM = 1024  # 🚨 db/schema.sql 의 vector(1024) 와 같아야 한다
BATCH = 32


def dsn() -> str:
    return os.environ.get("DATABASE_URL") or (
        "postgresql://copylane:copylane@localhost:5432/copylane"
    )


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
            cur.execute(
                "INSERT INTO chunk (chunk_id, fragment_id, doc_id, law_id, article, paragraph, "
                "item, doc_type, category, text, token_count) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (chunk_id) DO UPDATE SET text=EXCLUDED.text",
                (
                    r["chunk_id"],
                    r["fragment_id"],
                    r["doc_id"],
                    r["law_id"],
                    r["article"],
                    r["paragraph"],
                    r["item"],
                    r["doc_type"],
                    r["category"],
                    r["text"],
                    None,
                ),
            )
        done = 0
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            vecs = model.encode([b["text"] for b in batch])
            for b, v in zip(batch, vecs, strict=True):
                if len(v) != DIM:
                    raise SystemExit(f"🚨 차원이 {len(v)} 다 — vector({DIM}) 와 어긋난다")
                cur.execute(
                    "INSERT INTO chunk_embedding (chunk_id, embedding, model_id) "
                    "VALUES (%s,%s,%s) ON CONFLICT (chunk_id) DO UPDATE SET "
                    "embedding=EXCLUDED.embedding, model_id=EXCLUDED.model_id",
                    (b["chunk_id"], "[" + ",".join(f"{x:.6f}" for x in v) + "]", MODEL_ID),
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
