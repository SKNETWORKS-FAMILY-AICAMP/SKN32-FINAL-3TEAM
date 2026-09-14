"""scripts/graph_probe.py — 판정 그래프 한 바퀴를 **진짜 DB 로** 돌린다 (2026-09-14 · D-204).

    uv run python scripts/graph_probe.py
    uv run python scripts/graph_probe.py "탄력 있는 피부로" 화장품

★ **무엇을 답하나** — 구현계획 §2-1 C 의 완료 판정 마지막 칸이다:
  ① `evidence` 가 문장 수만큼 쌓이는가  ② **`vector` 가 실제로 돌았는가**
  ③ `retrieve` 가 몇 ms 인가 (D-77 예산 <500ms · 구현계획 ⑨ 리랭커 선정의 입력)

🔴 **왜 파일인가** — 같은 것을 PowerShell 한 줄로 넣으면 **한글 식별자가 `???` 로 깨진다**
   (2026-09-14 실측 · `Category.건기식` → `Category.???`). stdin 이 콘솔 인코딩을 타기
   때문이다. ⛔ 절차를 채팅으로 주면 다음 사람이 또 묻는다 — 도구로 남긴다 (D-117 · D-221).

🚨 **게이트가 아니다.** 답이 기기마다 다르다 (`data/**` 미커밋 · D-19 · D-89).
   🚨 **`scripts/search_probe.py` 와 다른 물건이다** — 저쪽은 검색 **순위**를 재고,
      이쪽은 **그래프가 검색을 부르는 배선**을 본다. 이름을 가른다 (D-204 의 어법).
⬜ **판정을 재지 않는다** — `judge` 는 아직 스텁이라 종착은 `hold` 가 정상이다 (D-127).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import graph as g  # noqa: E402
from app.contracts import Category, ProductContext  # noqa: E402
from app.settings import dsn  # noqa: E402

DEFAULT_TEXT = "면역력 강화에 도움을 줍니다."


def main(argv: list[str]) -> int:
    text = argv[1] if len(argv) > 1 else DEFAULT_TEXT
    raw = argv[2] if len(argv) > 2 else Category.일반.value
    try:
        category = Category(raw)
    except ValueError:
        print(f"🔴 카테고리가 아니다: {raw!r} — {[c.value for c in Category]}")
        return 1

    import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다 (api.py 와 같은 어법)

    try:
        with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
            out = g.build_graph().invoke(
                {
                    "text": text,
                    "product": ProductContext(category=category),
                    "sentences": [],
                    "rejects": [],
                    "timings": [],
                    "attempt": 0,
                },
                # 🚨 커서를 여기로 넣는다. 노드가 스스로 connect() 하면 문장마다 연결이 열린다.
                config={"configurable": {"conn": cur}},
            )
    except psycopg.Error as e:
        # 🔴 원인을 그대로 낸다 — 이건 사람이 보는 진단 도구다 (응답이 아니다 · P1-4 와 다른 자리).
        print(f"🔴 DB 에 못 붙었다 — {type(e).__name__}: {e}")
        print("   uv run python launcher.py db-up")
        return 1

    print(f"\n문구  {text}   ·   카테고리  {category.value}\n")
    for e in out["evidence"]:
        # 🚨 `vector`·`lexical` 은 「돌았나」다. `pool` 0 은 「안 겹쳤다」이고
        #    `lexical=False` 는 「검색어를 못 만들었다」다 — 다른 사건이다 (D-202).
        print(f"  {e.sent_id}  vector={e.vector}  lexical={e.lexical}  pool={e.pool}")
        if not e.articles:
            print("      ⬜ 좌표를 세운 근거가 없다 — 별표뿐이거나 후보가 비었다 (D-224)")
        for a in e.articles:
            print(f"      {a.law_id}  {a.article}      chunk={a.chunk_id}")

    print(f"\n  종착  {out['outcome'].value}   (🚨 judge 가 스텁이라 hold 가 정상이다 · D-127)")
    print("  계측")
    for t in out["timings"]:
        print(f"      {t.node:12s} {t.ms:8.1f} ms")
    total = sum(t.ms for t in out["timings"])
    print(f"      {'합계':12s} {total:8.1f} ms   (D-77 예산 판정 전체 <500ms)")
    print("\n🚨 이 수는 **이 기기**의 수다 — `data/**` 는 미커밋이다 (D-19 · D-178).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
