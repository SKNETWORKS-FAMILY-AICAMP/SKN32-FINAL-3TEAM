"""embed.py — 청크를 KURE-v1 로 임베딩해 pgvector 에 넣는다 (D-41 · D-84 ⑪).

  uv run python -m scripts.embed --check      # 모델 차원만 확인한다 (DB 불필요)
  uv run python -m scripts.embed              # chunk + chunk_embedding 적재
  uv run python -m scripts.embed --allow-shrink   # 🚨 DB 청크가 크게 줄어드는 것을 **보고** 받아들일 때만

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
import pathlib
import sys

from app.settings import PARAMS, dsn, load_kwargs
from preprocess.chunk import SHRINK_LIMIT, shrinkage

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "derived" / "chunks.jsonl"

MODEL_ID = PARAMS.embed_model_id
DIM = PARAMS.embed_dim  # 🚨 db/schema.sql 의 vector(1024) 와 같아야 한다
BATCH = PARAMS.embed_batch

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
    # 🔴 2026-09-12 밤 (0011 · D-199) — 쪼갠 조각이라는 사실. `preprocess/chunk.py` 가
    #    만들어 두고 **여기 없어서** 3년치 배선이 끊겨 있던 값이다.
    "part_no",
    "part_total",
    "doc_type",
    # 🔄 2026-09-24 (0019 · W6 · D-271 ①) — 종전 `category`(낱말 범주 배열). 법 ID 로 정한 **법 축 하나**다.
    "law",
    "text",
    "token_count",
    # 🔴 2026-09-12 밤 (0011 · D-200) — 모델에 **실제로 들어가는** 문자열의 토큰 수.
    #    `token_count` 는 `text` 만 센다 — 0008 이후 둘은 다른 문자열이다.
    "input_token_count",
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

    🔴 토큰은 **두 축을 따로 센다** (2026-09-12 밤 · D-200).

        token_count        `text` 만        인용 단위. `ck_chunk_tokens(512)` 가 보는 축
        input_token_count  `embed_input()`  모델·리랭커에 실제로 들어가는 축. 상한 미정

    ⛔ 0008 이 `context` 를 만들면서 **재는 문자열과 쓰는 문자열이 갈렸다.** 한 수로 두면
       「512 를 지킨다」가 어느 축의 말인지 알 수 없어진다 (D-185 — 정본 축/관측 축).
    🚨 임베딩 모델의 토크나이저로 센다 — 상한이 그 모델의 상한이기 때문이다.

    🔴 **못 세면 멈춘다** (D-220 fail-closed · 2026-09-12 밤). ⛔ 종전에는 `_tokens` 주석이
       *"토크나이저 종류가 달라도 적재는 계속한다"* 고 적었는데, `token_count` 가
       `NOT NULL` 이라 **계속되지 않고 psycopg 예외로 터졌다.** 그리고 터지는 자리가
       원인에서 멀어 「토크나이저가 다르다」가 아니라 「적재가 깨졌다」로 읽혔다.
       ★ 멈추는 것 자체는 맞다 — **멈추는 자리와 문장**을 원인 쪽으로 옮긴다.
    """
    v = {
        **r,
        "token_count": _tokens(model, r["text"]),
        "input_token_count": _tokens(model, embed_input(r)),
    }
    missing = [c for c in CHUNK_COLS if c not in v]
    if missing:
        raise SystemExit(f"🔴 청크에 칸이 없다: {missing} — preprocess.chunk 를 다시 돌린다")
    if v["token_count"] is None:
        raise SystemExit(
            f"🔴 토큰을 못 셌다 — {MODEL_ID} 의 토크나이저를 못 읽는다 "
            f"(chunk_id={r.get('chunk_id')!r}).\n"
            "   `token_count` 는 NOT NULL 이라 그냥 두면 적재 도중 psycopg 예외로 터진다.\n"
            "   🚨 상한(ck_chunk_tokens 512)이 이 수 위에 서 있으므로 **어림하지 않는다.**"
        )
    return tuple(v[c] for c in CHUNK_COLS)


def sweep_orphans(
    cur,  # noqa: ANN001
    declared: set[str],
    *,
    partial: bool,
    allow_shrink: bool = False,
) -> int:
    """선언에 없는 `chunk_id` 를 거둔다 — **적재는 선언한 상태로 만드는 것**이다 (D-187).

    🔴 2026-09-12 오후 — 제목뿐인 조 청크를 `preprocess/chunk.py` 가 빼면서 필요해졌다
       (D-195). ⛔ 거두지 않으면 뺀 청크가 DB 에 그대로 남아 **계속 검색에 걸린다** —
       코드는 고쳤는데 증상이 안 사라지고, 다음 사람은 고친 코드를 의심한다.
    🚨 `chunk_embedding` 은 `ON DELETE CASCADE` 라 같이 지워진다 (`db/schema.sql`).

    ⛔ **`--limit` 로 돌렸으면 거두지 않는다.** 앞의 N개만 선언이므로 나머지 전부가
       고아로 보인다 — **한 번의 연습 실행이 표를 비운다.**
       🚨 2026-09-12 오전 `mark_collected` 가 정확히 같은 함정이었다. 같은 가드를 건다.

    🔴 **가드 둘 더** (2026-09-20 · D-254 · 감사 §1-8) — 둘 다 **지우기 전에** 멈춘다 (D-220).
       ① **선언이 비면 거두지 않는다.** ⛔ 종전 `main` 은 파일 **유무**만 봐서, 0행 `chunks.jsonl`
          이면 표 전체가 고아로 보여 **전부 지우고** 「✅ 선언과 같다」를 찍었다.
          `load_db.sweep_golden` 의 「선언이 비면」 가드와 같은 자리다.
       ② **DB 청크의 `SHRINK_LIMIT` 를 넘게 지우게 되면 멈춘다** — `--allow-shrink` 로만 넘긴다.
          ⛔ 09-18 조문 −15% 가 오늘 코드에서도 초록으로 DB 삭제까지 갔다.
          🚨 기준·함수는 `preprocess/chunk.py` 한 곳이다 (D-209 · D-99) — `[임의]` · 판정 대기.
       ★ 멈추면 `SystemExit(1)` 을 던진다 — 호출자의 `with conn` 이 트랜잭션을 되돌린다.
    """
    if not declared:
        # 🔴 `partial` 이어도 멈춘다 — 빈 선언은 연습 실행이 아니라 **입력이 없는 것**이다.
        print(
            "🔴 선언(chunks.jsonl)이 0행이다 — **아무것도 거두지 않고 멈춘다** (D-220)\n"
            "   ⛔ 이대로 거두면 DB 의 청크가 **전부** 지워진다.\n"
            "   먼저: uv run python -m preprocess.chunk --dump   (정본) · launcher.py data-sync (사본)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    cur.execute("SELECT chunk_id FROM chunk")
    existing = {r[0] for r in cur.fetchall()}
    orphans = existing - declared
    if not orphans:
        return 0
    if partial:
        print(f"  ⬜ --limit 로 돌렸다 — 선언 밖 {len(orphans):,}행을 **거두지 않는다**")
        print("     🚨 전량으로 다시 돌려야 DB 가 선언과 같아진다")
        return 0
    shrunk = shrinkage({"DB chunk": len(existing)}, {"DB chunk": len(existing) - len(orphans)})
    if shrunk:
        print(
            f"🔴 DB 청크를 {SHRINK_LIMIT:.0%} 넘게 거두게 된다 — {shrunk[0]} (D-254)",
            file=sys.stderr,
        )
        for cid in sorted(orphans)[:5]:
            print(f"     {cid}", file=sys.stderr)
        if not allow_shrink:
            print(
                "   ⛔ 지우지 않았다 — 이번 실행은 되돌린다.\n"
                "   먼저 `chunks.jsonl` 이 왜 줄었는지 본다 (추출기 입력 · 파생물 동기화).\n"
                "   줄어든 것이 맞다고 판단했으면:\n"
                "     uv run python -m scripts.embed --allow-shrink",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print("   ⚠️ --allow-shrink — 그대로 거둔다", file=sys.stderr)
    # 🚨 **몇 개를 왜 지우는지 먼저 찍는다** — 조용히 지우면 수가 줄어도 아무도 모른다 (D-149).
    print(f"  🧹 선언에 없는 청크 {len(orphans):,}행을 거둔다 (D-187)")
    for cid in sorted(orphans)[:5]:
        print(f"     {cid}")
    if len(orphans) > 5:
        print(f"     … 외 {len(orphans) - 5:,}행")
    cur.execute("DELETE FROM chunk WHERE chunk_id = ANY(%s)", (sorted(orphans),))
    return len(orphans)


def _tokens(model, text: str) -> int | None:
    """임베딩 모델 토크나이저로 센 토큰 수. 못 세면 `None` — **지어내지 않는다**.

    🚨 상한(`ck_chunk_tokens` 512)은 **이 모델의 상한**이므로 이 토크나이저로 세야 뜻이 맞다.
    ⛔ **`None` 을 「괜찮다」로 읽지 않는다.** 이 함수는 모르는 것을 모른다고만 하고,
       멈출지 말지는 `chunk_values()` 가 정한다 — 거기에 `chunk_id` 가 있어서
       **어느 행에서 무엇을 못 셌는지**를 말할 수 있기 때문이다 (D-51 · D-220).
    """
    try:
        tok = model.tokenizer
    except AttributeError:
        return None
    try:
        return len(tok.encode(text, add_special_tokens=True))
    except Exception:  # noqa: BLE001 — 종류를 가리지 않는다. 판단은 chunk_values 가 한다
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
    # 🔴 쓰는 쪽도 같은 문을 지난다 (P0-3 · D-212) — `safetensors` · `trust_remote_code=False`.
    return SentenceTransformer(MODEL_ID, **load_kwargs(MODEL_ID))


def main() -> int:
    ap = argparse.ArgumentParser(description="청크 임베딩 → pgvector")
    ap.add_argument("--check", action="store_true", help="모델 차원만 확인한다 (DB 불필요)")
    ap.add_argument("--limit", type=int, default=0, help="앞의 N개만 (연습용)")
    ap.add_argument(
        "--allow-shrink",
        action="store_true",
        help=f"🚨 DB 청크의 {SHRINK_LIMIT * 100:.0f}%% 넘게 거두어도 진행한다 — 이유를 안 뒤에만",
    )
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
    # 🔴 **W6 전 판이면 멈춘다** (2026-09-24 · 0019). ⛔ 옛 판은 `law` 대신 `category` 를 들고 있어
    #    `chunk_values` 가 `KeyError` 로 **DB 에 반쯤 쓴 뒤** 죽는다 — 원인에서 먼 자리다 (D-220).
    old = sum(1 for r in rows if "law" not in r)
    if old:
        print(
            f"🔴 chunks.jsonl 이 W6 전 판이다 — `law` 칸이 없는 행 {old:,}개 (0019 · D-271 ①).\n"
            "   정본: uv run python launcher.py chunk --dump   ·   사본: uv run python launcher.py data-sync",
            file=sys.stderr,
        )
        return 1
    if args.limit:
        rows = rows[: args.limit]

    import psycopg

    # 🔴 **DB 가 없을 때 스택트레이스로 죽지 않는다** (2026-09-12 밤 · D-51).
    #    ⛔ `load_db.py` 는 같은 자리를 감쌌는데 여기만 안 감쌌다. 팀원이 클론 첫날
    #       `launcher.py embed` 를 누르면 `OperationalError` 트레이스백을 만난다.
    try:
        conn = psycopg.connect(dsn())
    except psycopg.Error as e:
        print(f"🚨 DB 에 못 붙었다 — {type(e).__name__}")
        print("   uv run python launcher.py db-up 을 먼저 돌린다.")
        print("   DB 없이 모델 차원만 재려면 — uv run python launcher.py embed --check")
        raise SystemExit(1) from e
    with conn, conn.cursor() as cur:
        # 🔄 **거두기를 넣기 앞으로 옮겼다** (2026-09-20 · D-254).
        #    ⛔ 종전에는 넣은 뒤에 거뒀다. 고아 집합(DB − 선언)은 순서와 무관하지만, 넣은 뒤에 재면
        #       하한 래칫의 분모에 **방금 넣은 새 id** 가 섞여 줄어든 비율이 묽어진다.
        #    ★ 앞에서 재면 분모가 「지금 DB 에 있던 것」이고, 멈출 때 **아무것도 안 쓴 채** 멈춘다.
        #    🚨 한 트랜잭션 안이다 — 뒤에서 죽으면 거둔 것도 되돌려진다.
        swept = sweep_orphans(
            cur,
            {r["chunk_id"] for r in rows},
            partial=bool(args.limit),
            allow_shrink=args.allow_shrink,
        )
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
        # 🔴 **상한이 없는 축은 재서 찍는다** (0011 · D-200). CHECK 이 못 지키는 축이므로
        #    출력이 유일한 눈이다 — 안 찍으면 「모르는 채로 통과」가 된다 (D-188).
        cur.execute(
            "SELECT max(input_token_count), count(*) FILTER (WHERE input_token_count > 512),"
            "       count(*) FILTER (WHERE part_total > 1)"
            "  FROM chunk"
        )
        max_in, over, split = cur.fetchone()
    print(f"\n  보낸 행 {len(rows)} · DB chunk {n_chunk} · embedding {n_emb} ({MODEL_ID})")
    print(f"  📏 모델 입력 토큰 최대 {max_in} · **512 초과 {over}행** — 상한 CHECK 없음 (D-200)")
    print("     🚨 리랭커 모델을 고를 때 이 수가 상한을 정한다 (기획서 7-3). 원장에 올린다")
    print(f"  ✂️  쪼갠 조각 {split}행 — `part_total > 1`. 화면·인용 검증이 이 칸을 본다 (D-199)")
    if swept:
        print(f"  🧹 거둔 행 {swept:,} — 선언에 없던 옛 청크다 (D-187)")
    if n_chunk < len(rows):
        print(
            f"  🚨 {len(rows) - n_chunk}행이 들어가지 않았다 — chunk_id 가 겹친다 (D-149)",
            file=sys.stderr,
        )
        return 1
    # 🔴 **거둔 뒤에는 「같다」가 아니라 「선언과 같다」라야 한다** (D-187).
    #    ⛔ 전량으로 돌렸는데 DB 가 선언보다 많으면 못 거둔 것이 남았다는 뜻이다 —
    #       초록으로 넘기면 지운 줄 알았던 청크가 계속 검색에 걸린다.
    if not args.limit and n_chunk != len(rows):
        print(
            f"  🚨 DB {n_chunk:,} ≠ 선언 {len(rows):,} — 거두지 못한 행이 있다 (D-187)",
            file=sys.stderr,
        )
        return 1
    print("  ✅ DB 가 선언과 같다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
