"""preprocess/chunk.py — [P5] 청킹. 조문·별표 노드 → RAG 청크.

  uv run python -m preprocess.chunk               # 센다
  uv run python -m preprocess.chunk --dump        # data/derived/chunks.jsonl

왜 있는가 — 2026-09-09 확인: **[P5] 는 이름표만 있고 코드가 0줄이었다.** RAG 가 설계에만
있고 코드에 없었다. `docs/02_설계/청크_스키마.md` 는 제목부터 「W1 확정 대상」이다.

🚨 **조문 단위로 자른다. 임의 길이로 자르지 않는다.**
   판정의 근거는 「제8조제1항제1호」처럼 **조문으로 인용**되어야 한다 (D-158).
   200자씩 기계적으로 자르면 한 청크가 두 호에 걸치고, 화면이 어느 호를 인용하는지
   말할 수 없게 된다. 그러면 D-51(오류는 고치는 법을 보여준다)이 성립하지 않는다.

🚨 **512 토큰은 리랭커의 한계다** (기획서 7-3 · bge-reranker-v2-m3). 넘는 조문은
   **항 단위로 더 쪼갠다.** 그래도 넘으면 문장 경계로 자르되 **`part_no`·`part_total` 을
   붙여 원 조문을 가리킨다** — 잘렸다는 사실을 데이터가 들고 있어야 화면이
   「제N조 (1/3)」이라 말할 수 있다.
   🔄 **2026-09-12 밤 (D-199)** — 종전에는 `part = "1/3"` 문자열 하나였고 **DB 에 열이 없어
      아무도 읽지 않았다.** 만들어 놓고 읽는 쪽을 안 만든 값이었다. 수 둘로 갈라 0011 에
      열을 세우고 `_SELECT` → `Hit` → `SearchHit` 까지 잇는다.
      ⛔ 문자열 「1/3」로 두지 않는 이유 — 받는 쪽이 다시 파싱해야 하고 CHECK 이 못 지킨다.

🚨 **토큰 수는 재는 것이지 어림하는 것이 아니다.** 형태소·서브워드 수가 글자 수와 다르다.
   여기서는 보수적으로 **글자 수 기반 상한**을 쓰고 그 사실을 적어 둔다 —
   ⚠️ **실제 토크나이저로 재는 것이 W1 의 남은 일이다** (청크_스키마 TODO 3).
   글자 상한은 실제 토큰 수를 **넘게 잡는 쪽**이라 512 를 초과할 위험은 없다(한국어는
   글자당 토큰이 1 미만인 경우가 대부분이다). 대신 **불필요하게 잘게 잘릴 수 있다.**
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from app.settings import PARAMS
from collect import store

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"

# 🚨 512 토큰 한계에 대한 **보수적** 글자 상한. 넘게 잡는 쪽이다 (위 docstring).
MAX_CHARS = PARAMS.chunk_max_chars
CATEGORY = {
    "화장품": "화장품",
    "건강기능식품": "건기식",
    "식품 등의 표시": "식품",
    "표시ㆍ광고의 공정화": "일반",
    "표시·광고의 공정화": "일반",
}
_SENT = re.compile(r"(?<=[.。])\s+|\n")

#: 「제8조(부당한 표시 또는 광고행위의 금지)」처럼 **제목뿐인 조 머리 행**.
#: 🔴 2026-09-12 오후 — 이런 청크를 **담지 않는다** (D-159 · D-195).
#:    ⛔ 항이 있는 조는 법제처 XML 이 조 머리에 제목만 준다. 그것이 15토큰짜리 청크가 되어
#:       임베딩 공간의 중앙부에 앉고, **어떤 질의에나 중간 거리**로 상위를 채웠다
#:       (2026-09-12 실측 — 광고 문구 세 건 모두 상위를 이 부류가 점령했다).
#:    🚨 규범이 한 글자도 없다 — 「제8조」라는 이름표뿐이다. 검색에 걸려도 인용할 근거가
#:       없고, 화면은 「제8조가 걸렸다」고만 말하게 된다. 그것이 D-100 이 막으려는 부분 인용이다.
#:    ⬜ 항이 없는 조(본문이 조 머리에 통째로 오는 것)는 **남는다** — 이 정규식에 안 맞는다.
_TITLE_ONLY = re.compile(r"^제\s*\d+\s*조(?:의\s*\d+)?\s*(?:\([^)]*\))?\s*$")


def category_of(title: str) -> str:
    for key, val in CATEGORY.items():
        if key in title:
            return val
    return "일반"


def _context(r: dict) -> str:
    """자립 텍스트를 조립한다 — **검색이 보는 것**이자 **화면이 보여 줄 문맥**이다 (0008).

        호  →  조 제목 + 항 본문     「1. 마약」은 앞의 항이 있어야 읽힌다
        항  →  조 제목               「① 누구든지 …아니 된다」만으로는 무슨 조인지 모른다
        조  →  빈 문자열             `text` 가 이미 제목을 들고 있다 — 붙이면 중복이다

    🔴 **한 값을 임베딩과 화면이 같이 쓴다.** 둘이 다른 문자열이면 「검색이 본 문맥」과
       「사람이 본 문맥」이 갈린다 (D-99).
    🚨 빈 문자열은 「붙일 문맥이 없음」이고 NULL(미적재)과 다르다.
    """
    if not r.get("키"):  # 조 행 — `키` 가 없는 것이 조다 (chunk_id 도 article 을 쓴다)
        return ""
    head = (r.get("제목") or "").strip()
    hang = (r.get("항본문") or "").strip()
    return "\n".join(p for p in (head, hang) if p)


def _split_long(text: str) -> list[str]:
    """길면 문장 경계로 자른다. 🚨 자른 사실은 호출자가 `part` 로 남긴다."""
    if len(text) <= MAX_CHARS:
        return [text]
    out, buf = [], ""
    for piece in _SENT.split(text):
        piece = (piece or "").strip()
        if not piece:
            continue
        if len(buf) + len(piece) + 1 > MAX_CHARS and buf:
            out.append(buf)
            buf = piece
        else:
            buf = f"{buf} {piece}".strip()
    if buf:
        out.append(buf)
    # 문장 경계가 없어 여전히 긴 경우 — 마지막 수단으로 글자로 자른다
    final: list[str] = []
    for c in out:
        if len(c) <= MAX_CHARS:
            final.append(c)
        else:
            final += [c[i : i + MAX_CHARS] for i in range(0, len(c), MAX_CHARS)]
    return final


def from_articles() -> tuple[list[dict], int]:
    """조문 노드 → 청크. **버린 수를 같이 낸다** — 0 이 아닌 수는 보여야 한다 (D-149).

    🚨 반환이 목록 하나가 아니라 `(청크, 버린 수)` 다. ⛔ 버린 수를 안 돌려주면
       「제목뿐인 조를 뺐다」가 **아무 출력에도 안 남고**, 다음 사람은 청크 수가 왜
       줄었는지 모른 채 원장 수치와 어긋나는 것을 본다.
    """
    rows = []
    dropped = 0
    p = DERIVED / "law_article.jsonl"
    if not p.exists():
        return rows, dropped
    for r in (json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()):
        body = (r.get("본문") or "").strip()
        if not body or r.get("본문없음"):
            continue
        # 🔴 제목뿐인 조 머리 행은 담지 않는다 (D-159 · D-195) — 위 `_TITLE_ONLY` 주석 참조.
        #    🚨 **3층 노드에서 지우는 것이 아니다.** `law_article.jsonl` 은 그대로 두고
        #       청킹 정책으로만 뺀다 — 원천의 수와 우리가 검색에 올리는 수는 다른 사실이다.
        if _TITLE_ONLY.match(body):
            dropped += 1
            continue
        law = r["법령"]
        article = f"제{r['조']}조" + (f"의{r['가지']}" if r.get("가지") else "")
        doc_id = f"law:{r['파일'].replace('.xml', '')}"
        parts = _split_long(body)
        for i, text in enumerate(parts):
            rows.append(
                {
                    # 🚨 원천이 주는 유일 키를 쓴다 — 조립하면 겹친다(law_article.py 참조)
                    "chunk_id": f"{doc_id}#{r.get('키') or article}#{i}",
                    "fragment_id": "law_go_kr:article",
                    "doc_id": doc_id,
                    "law_id": r["파일"].split("_")[1],
                    "article": article,
                    # 🔴 항과 호를 **각자의 칸에** 담는다 (2026-09-12 · D-167).
                    #    ⛔ 종전에는 `paragraph` 에 「①1.」이 통째로 들어가고 `item` 은
                    #       **늘 빈 칸**이었다. 생산자가 안 채우는 열은 소비자도 못 읽는다.
                    #    ★ 이 둘이 갈려 있어야 `retrieve.citation()` 이 조립된다.
                    "paragraph": r.get("항") or "",
                    "item": r.get("호") or "",
                    #: 🔴 원문에 항번호가 없어도 항은 있다 — 우리가 센 서수 (D-117 · 0008).
                    "paragraph_no": r.get("항서수"),
                    #: 🔴 **자립 텍스트** — 검색이 보는 것과 인용하는 것을 가른다 (0008).
                    "context": _context(r),
                    "doc_type": "법령",
                    "category": [category_of(law)],
                    "text": text,
                    # 🔴 **쪼갠 조각이라는 사실** (D-199 · 0011). 안 쪼갰으면 1/1 이다 —
                    #    빈 문자열이 아니다. 「모른다」는 적재 전 DB 의 NULL 이 맡는다.
                    "part_no": i + 1,
                    "part_total": len(parts),
                    "법령": law,
                }
            )
    return rows, dropped


def from_annex() -> list[dict]:
    rows = []
    d = DERIVED / "law_norm"
    if not d.exists():
        return rows
    for p in sorted(d.glob("*.jsonl")):
        for r in (json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()):
            text = (r.get("text") or "").strip()
            if not text:
                continue
            doc_id = f"annex:{p.stem}"
            parts = _split_long(text)
            for i, chunk in enumerate(parts):
                rows.append(
                    {
                        "chunk_id": f"{doc_id}#{r['section']}#{r['path']}#{i}",
                        "fragment_id": "law_go_kr:annex",
                        "doc_id": doc_id,
                        "law_id": r["law_id"],
                        "article": r.get("article") or "",
                        "paragraph": r["path"],
                        "item": r["section"],
                        #: ⬜ **별표는 이번 범위 밖이다** (0008). 계층 표기가 `2.가.10` 이라
                        #:    법령의 조·항·호 규칙이 안 먹는다. 빠뜨린 것이 아니라 판정이다 —
                        #:    빈 문자열은 「붙일 문맥이 없음」, NULL 은 「아직 안 채움」이다.
                        "paragraph_no": None,
                        "context": "",
                        "doc_type": "별표",
                        "category": [category_of(r["annex_title"])],
                        "text": chunk,
                        "part_no": i + 1,
                        "part_total": len(parts),
                        "법령": r["annex_title"],
                    }
                )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="[P5] 조문·별표 → RAG 청크")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    # 🔴 **한쪽만 있어도 실패한다** (2026-09-10 · D-72).
    #    ⛔ 종전에는 `if not rows:` 라 **둘 다** 비어야 실패했다. `data/derived/law_norm/`
    #       이 없으면 별표 청크 0개인 `chunks.jsonl` 이 **초록으로** 만들어진다 —
    #       임베딩까지 그대로 흘러가고 수치는 아무 데도 안 튄다 (D-149 의 다른 문).
    #    🚨 `law_norm.py` 의 docstring 이 `--dump` 라 적혀 있으나 실제 쓰기 플래그는
    #       `--write` 다. 문서대로 돌린 사람은 별표가 통째로 빠진 채 여기 도착한다.
    (art, dropped), annex = from_articles(), from_annex()
    missing = [
        n for n, v in (("조문(law_article.jsonl)", art), ("별표(law_norm/)", annex)) if not v
    ]
    if missing:
        print(
            f"🔴 청크 재료가 비어 있다 — {' · '.join(missing)}\n"
            "  조문: uv run python -m preprocess.law_article --dump\n"
            "  별표: uv run python -m preprocess.law_norm --write   🚨 --dump 가 아니다\n"
            "  🚨 한쪽만으로 만들면 그 층이 통째로 빠진 채 임베딩까지 간다.",
            file=sys.stderr,
        )
        return 1
    rows = art + annex

    # 🔴 **키가 겹치면 멈춘다** (D-149 · 2026-09-09).
    #    ⛔ 첫 적재에서 청크 2,594 를 만들고 「임베딩 2594」라 찍었는데 DB 에는 **2,297** 이
    #       들어갔다. `ON CONFLICT (chunk_id) DO UPDATE` 가 **297행을 조용히 덮었다.**
    #       숫자는 초록이었고 아무도 안 봤으면 그대로 갔다.
    #       원인 둘 — 「제1장 총칙」이 조문으로 들어와 키가 `제조` 로 뭉친 것,
    #       행정규칙 최상위 마커(Ⅲ)가 본문과 부칙에서 두 번 쓰인 것.
    #    🚨 덮지 않고 **멈춘다.** 적재 쪽에서 잡으면 이미 늦다 — 무엇이 지워졌는지 모른다.
    seen: dict[str, str] = {}
    clash: list[tuple[str, str, str]] = []
    for r in rows:
        if r["chunk_id"] in seen:
            clash.append((r["chunk_id"], seen[r["chunk_id"]][:40], r["text"][:40]))
        seen[r["chunk_id"]] = r["text"]
    if clash:
        print(f"\n🚨 chunk_id 가 겹친다 — {len(clash)}건 (D-149)")
        for k, a, b in clash[:5]:
            print(f"   {k}\n      먼저: {a!r}\n      나중: {b!r}")
        print("   고치는 법 — 키를 만드는 자리(from_articles · from_annex)가 조·항·호를")
        print("               유일하게 집는지 본다. 덮어쓰기로 넘기지 않는다.")
        return 1

    long_ = sum(1 for r in rows if r["part_total"] > 1)
    cats: dict[str, int] = {}
    for r in rows:
        cats[r["category"][0]] = cats.get(r["category"][0], 0) + 1
    print(f"  청크 {len(rows)}개 · 최장 {max(len(r['text']) for r in rows)}자")
    print(f"  범주 {cats}")
    print(f"  🚨 길어서 쪼갠 청크 {long_}개 — `part_no`/`part_total` 이 원 조문을 가리킨다")
    # 🔴 **뺀 수를 매번 찍는다** — 조용히 줄면 다음 사람이 원장과 어긋나는 수를 보고 헤맨다.
    print(f"  ⬜ 제목뿐인 조 머리 행 {dropped}개를 담지 않았다 (D-159 · D-195)")
    print("     🚨 DB 에 남은 옛 청크는 `scripts/embed.py` 가 거둔다 — 여기서는 안 지운다 (D-187)")
    print(f"  ⚠️ 토큰 수는 글자 상한({MAX_CHARS})으로 어림했다 — 실측은 W1 의 남은 일이다")

    if args.dump:
        out = DERIVED / "chunks.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(store.stamp(r, "law_go_kr"), ensure_ascii=False) + "\n")
        print(f"  💾 → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
