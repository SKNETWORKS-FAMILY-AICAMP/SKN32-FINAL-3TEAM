"""scripts/graph_probe.py — 판정 그래프 한 바퀴를 **진짜 DB 로** 돌린다 (2026-09-14 · D-204).

    uv run python scripts/graph_probe.py
    uv run python scripts/graph_probe.py "탄력 있는 피부로" 화장품

★ **무엇을 답하나** — 구현계획 §2-1 C 의 완료 판정 마지막 칸이다:
  ① `evidence` 가 문장 수만큼 쌓이는가  ② **`vector` 가 실제로 돌았는가**
  ③ `retrieve` 가 몇 ms 인가 — D-77 L3 예산 **「BM25 + 벡터 검색 < 300ms」**
     (구현계획 ⑨ 리랭커 선정의 입력)

🔄 **2026-09-14 정정 — 종전에 「D-77 예산 판정 전체 <500ms」라 적혀 있었다. 그런 수는 없다.**
   ⛔ D-77 L3 의 표는 **단계별** 예산이고, **500ms 는 리랭커 한 단계**의 몫이다(최적화 1순위).
      판정은 **소계 ≈1.1초 · 목표 p95 < 3초**다. 「전체 500ms」로 읽으면 **아직 없는 리랭커의
      예산을 이미 다 쓴 것처럼** 보여, 통과해야 할 것이 초과로 읽힌다 (실제로 그렇게 읽혔다).
   🚨 이 오기는 이 파일이 만들어질 때(09-14) 같이 들어와 보고 넷에 인용되었다.
      **D 번호를 인용하기 전에 원장 본문을 읽는다** — D-224 가 적은 규율 그대로다.

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
from app import retrieve as rt  # noqa: E402 — 모델이 **이번 실행에서** 로드됐는지 보려고 든다
from app.contracts import Category, ProductContext  # noqa: E402
from app.settings import dsn  # noqa: E402

DEFAULT_TEXT = "면역력 강화에 도움을 줍니다."

#: D-77 L3 「단계별 응답시간 예산」에서 **이 도구가 지나는 노드만** 옮겼다.
#: 🔴 **정본은 원장이다** — 여기는 읽는 자리다 (D-54). 표를 고칠 때는 원장을 고친다.
#: ⛔ 여기에 「판정 전체」 칸을 만들지 않는다. D-77 에 그런 칸이 없다 (위 정정 참조).
BUDGET_MS: dict[str, int] = {"split": 50, "classify": 100, "retrieve": 300}
#: 판정 **소계** — D-77 L3. 목표는 `p95 < 3초`이고 이 소계는 그 안의 배분 합계다.
JUDGE_SUBTOTAL_MS = 1_100


def main(argv: list[str]) -> int:
    text = argv[1] if len(argv) > 1 else DEFAULT_TEXT
    raw = argv[2] if len(argv) > 2 else Category.일반.value
    try:
        category = Category(raw)
    except ValueError:
        print(f"🔴 카테고리가 아니다: {raw!r} — {[c.value for c in Category]}")
        return 1

    import psycopg  # noqa: PLC0415 — DB 가 없어도 임포트는 서야 한다 (api.py 와 같은 어법)

    # 🔴 **모델 로드가 이번 실행에 들어갔는지 센다.** 들어갔으면 `retrieve` 를 예산으로
    #    판정하지 않는다 — 첫 실행은 **늘** 초과이고, 늘 빨간 표시는 아무도 안 본다.
    #    ⛔ 「모델 로드 포함이니 감안해서 보라」를 사람에게 시키지 않는다. 도구가 안다.
    #    🚨 `_model_cache` 는 `app/retrieve.py` 의 사유물이다 — 저쪽이 이름을 바꾸면
    #       여기가 조용히 `False` 로 굳는다. 그래서 아래에서 **비어 있는지도 같이 본다.**
    before = len(rt._model_cache)  # noqa: SLF001

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

    after = len(rt._model_cache)  # noqa: SLF001
    # 🚨 **셋을 가른다.** ① 이번에 로드됐다 — 예산 판정 안 함 ② 이미 떠 있었다 — 판정한다
    #    ③ 끝까지 비어 있다 — 벡터가 안 돈 것이라 **애초에 잴 것이 없다** (D-202 의 어법).
    #    ⛔ ①과 ③을 한 값으로 합치지 않는다. 「느린 것」과 「안 돈 것」은 다른 사건이다.
    skip = "모델 로드 포함" if after > before else ("" if after else "벡터 미실행")

    print(f"\n  종착  {out['outcome'].value}   (🚨 judge 가 스텁이라 hold 가 정상이다 · D-127)")
    print("  계측")
    for t in out["timings"]:
        # 🚨 예산이 **있는 노드만** 판정한다. 없는 노드에 초록·빨강을 찍으면
        #    원장에 없는 수를 지어낸 것이 된다 (D-224 의 어법).
        b = BUDGET_MS.get(t.node)
        if b is None:
            note = ""
        elif t.node == "retrieve" and skip:
            note = f"   ⬜ {skip} — 예산(<{b}ms) 판정 안 함"
        else:
            note = f"   {'✅' if t.ms < b else '🔴'} 예산 <{b}ms"
        print(f"      {t.node:12s} {t.ms:8.1f} ms{note}")
    total = sum(t.ms for t in out["timings"])
    print(
        f"      {'합계':12s} {total:8.1f} ms   "
        f"(D-77 L3 판정 소계 ≈{JUDGE_SUBTOTAL_MS}ms · 목표 p95 < 3초)"
    )
    if skip == "모델 로드 포함":
        print("      🚨 이 실행에서 **모델을 로드했다** — 프로세스당 한 번이다 (`_model_cache`).")
        print("         `retrieve` 의 진짜 수는 **같은 프로세스에서 두 번째 검색부터**다.")
        print("         한 프로세스에서 여러 번 재는 것은 원장에 있다 (D-19 · D-178).")
    print("      ⬜ `retrieve` 는 아직 **문장 하나**만 돈다 — `split` 이 스텁이다 (D-127).")
    print("         문장 분할이 서면 이 수에 문장 수가 곱해진다. 같은 작업에서 배치로 묶는다.")
    print("\n🚨 이 수는 **이 기기**의 수다 — `data/**` 는 미커밋이다 (D-19 · D-178).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
