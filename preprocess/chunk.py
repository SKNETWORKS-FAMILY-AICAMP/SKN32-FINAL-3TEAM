"""preprocess/chunk.py — [P5] 청킹. 조문·별표 노드 → RAG 청크.

  uv run python -m preprocess.chunk               # 센다
  uv run python -m preprocess.chunk --dump        # data/derived/chunks.jsonl
  uv run python -m preprocess.chunk --dump --allow-shrink   # 🚨 줄어든 것을 **보고** 받아들일 때만

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
import collections
import json
import pathlib
import re
import sys

from app.settings import PARAMS
from collect import store
from collect.law_map import LAW_OF_ID

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"

# 🚨 512 토큰 한계에 대한 **보수적** 글자 상한. 넘게 잡는 쪽이다 (위 docstring).
MAX_CHARS = PARAMS.chunk_max_chars
#: ⛔ 🔄 2026-09-24 (W6 · D-271 ①) — 종전 `CATEGORY` 표와 `category_of()` 를 지웠다.
#:    법령 이름·별표 제목의 **낱말**로 범주를 정했고, 안 걸리면 「일반」이었다 — 별표 제목에는 법 이름이 없어
#:    식품표시광고법 시행령 [별표 1] 50청크를 포함해 265개(11%)가 「일반」으로 떨어졌다(D-271 맥락 2).
#:    ★ 청크의 법은 **법 ID 로** 정한다 — 대응표는 `collect/law_map.py` 한 곳이다.
_SENT = re.compile(r"(?<=[.。])\s+|\n")

#: 🔴 **하한 래칫** — 이전 판보다 이 비율을 넘게 줄면 멈춘다 (2026-09-20 · D-254 · 감사 §1-8).
#:    ⛔ 09-18 조문 노드가 2,207 → 1,873 으로 **조용히** 줄었고 게이트는 전부 초록이었다.
#:       그 판이 `chunks.jsonl` → `embed` 의 `sweep_orphans` 로 흘러 **DB 삭제까지** 초록으로 간다.
#:    🚨 `[임의]` — 5% 는 근거 없는 첫 값이다. **판정 대기** — 팀이 정할 값이다.
#:       (09-18 사고는 −15% 라 이 값이면 잡힌다. 그보다 작은 정상 변동이 있는지는 안 재 봤다.)
#:    🔗 **한 곳이다** (D-209 · D-99) — `scripts/embed.py` 가 이 상수와 `shrinkage()` 를 들여 쓴다.
#:       `app/settings.PARAMS` 로 옮기는 것이 원칙에 맞으나 이번 고침의 범위 밖이었다.
SHRINK_LIMIT = 0.05


def shrinkage(old: dict[str, int], new: dict[str, int], limit: float = SHRINK_LIMIT) -> list[str]:
    """이전 판 대비 **`limit` 을 넘게 줄어든 층**을 사람이 읽을 줄로 낸다. 없으면 빈 리스트.

    🔴 **늘어난 것·새로 생긴 층은 보지 않는다** — 막는 것은 「조용히 사라지는 것」뿐이다.
    🚨 **층이 통째로 사라진 것**(새 판에 키가 없음)도 줄어든 것이다 — 0 으로 센다 (D-220).
    ★ `chunk`(파일 대 파일)와 `embed`(DB 대 선언)가 **같은 함수**를 쓴다 (D-99).
    """
    out = []
    for key, before in sorted(old.items()):
        after = new.get(key, 0)
        if before <= 0 or after >= before:
            continue
        drop = (before - after) / before
        if drop > limit:
            out.append(f"{key}: {before:,} → {after:,} (−{before - after:,} · −{drop:.1%})")
    return out


def layer_counts(rows: list[dict]) -> dict[str, int]:
    """전체 + 층(`fragment_id`)별 청크 수. 🚨 층 키가 없는 옛 행은 「(층 없음)」으로 센다."""
    c: collections.Counter[str] = collections.Counter()
    for r in rows:
        c["전체"] += 1
        c[str(r.get("fragment_id") or "(층 없음)")] += 1
    return dict(c)


def previous_counts(path: pathlib.Path) -> dict[str, int] | None:
    """이전 판 `chunks.jsonl` 의 수. **없으면 `None`** — 첫 판이라 비교할 것이 없다.

    🚨 파일은 있는데 0행이면 `{}` 다 — 비교 기준이 0 이라 래칫은 아무것도 막지 않는다.
       ⛔ 깨진 JSON 은 삼키지 않는다 — 예외 그대로 멈춘다 (D-220).
    """
    if not path.exists():
        return None
    return layer_counts(
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    )


#: 「제8조(부당한 표시 또는 광고행위의 금지)」처럼 **제목뿐인 조 머리 행**.
#: 🔴 2026-09-12 오후 — 이런 청크를 **담지 않는다** (D-159 · D-195).
#:    ⛔ 항이 있는 조는 법제처 XML 이 조 머리에 제목만 준다. 그것이 15토큰짜리 청크가 되어
#:       임베딩 공간의 중앙부에 앉고, **어떤 질의에나 중간 거리**로 상위를 채웠다
#:       (2026-09-12 실측 — 광고 문구 세 건 모두 상위를 이 부류가 점령했다).
#:    🚨 규범이 한 글자도 없다 — 「제8조」라는 이름표뿐이다. 검색에 걸려도 인용할 근거가
#:       없고, 화면은 「제8조가 걸렸다」고만 말하게 된다. 그것이 D-224 이 막으려는 부분 인용이다.
#:    ⬜ 항이 없는 조(본문이 조 머리에 통째로 오는 것)는 **남는다** — 이 정규식에 안 맞는다.
_TITLE_ONLY = re.compile(r"^제\s*\d+\s*조(?:의\s*\d+)?\s*(?:\([^)]*\))?\s*$")


def _context(r: dict) -> str:
    """자립 텍스트를 조립한다 — **검색이 보는 것**이자 **화면이 보여 줄 문맥**이다 (0008).

        호  →  조 제목 + 항 본문     「1. 마약」은 앞의 항이 있어야 읽힌다
        항  →  조 제목               「① 누구든지 …아니 된다」만으로는 무슨 조인지 모른다
        조  →  빈 문자열             `text` 가 이미 제목을 들고 있다 — 붙이면 중복이다

    🔴 **한 값을 임베딩과 화면이 같이 쓴다.** 둘이 다른 문자열이면 「검색이 본 문맥」과
       「사람이 본 문맥」이 갈린다 (D-99).
    🚨 빈 문자열은 「붙일 문맥이 없음」이고 NULL(미적재)과 다르다.
    """
    # 🆕 2026-09-25 (팀장 판정 (나)) — 시행 전 조항 표시(`law_article.PENDING_ALLOWED` → 노드 `시행예정`)를
    #    **문맥 맨 앞에** 둔다. 검색이 보는 값과 화면이 보여 주는 값이 같아야 한다(D-99) — 칸을 새로 만들지 않고
    #    이미 DB · 화면까지 가는 `context` 에 싣는다. 🚨 이 표시가 없는 조항은 지금 시행 중인 글이다.
    note = (r.get("시행예정") or "").strip()
    pre = [f"[{note}]"] if note else []
    if not r.get("키"):  # 조 행 — `키` 가 없는 것이 조다 (chunk_id 도 article 을 쓴다)
        return "\n".join(pre)
    head = (r.get("제목") or "").strip()
    hang = (r.get("항본문") or "").strip()
    return "\n".join(p for p in (*pre, head, hang) if p)


def _annex_context(r: dict, by_path: dict[tuple[str, str], str]) -> str:
    """별표 청크의 자립 텍스트 — **별표 제목 + 상위 항목** (🆕 2026-09-24 · W6 재측정).

        「제품명」 → 「[별표 1] 식품등의 일부 표시사항(제2조 관련)
                      자사(自社)에서 제조ㆍ가공할 목적으로 수입하는 식품등」

    🔴 **왜** — W6 로 시행규칙 별표 131청크가 「일반」에서 식품표시광고법으로 옮겨 오자, 「제품명」·「면류」·「식염」
       같은 **글자 몇 개짜리 목록 청크가 벡터 상위 1~6위를 점령했다**(2026-09-24 B 실측 · 질의 넷 전부). 짧은 청크는
       임베딩 공간 중앙에 앉아 **어떤 질의에나 중간 거리**로 걸린다 — 09-12 에 조문 쪽에서 겪은 병(D-195)이고,
       조문은 0008 이 문맥을 붙여 고쳤다. 별표는 「계층 표기가 달라 범위 밖」으로 비워 두었다(0008).
    ★ **같은 처방을 별표에 쓴다** — 조문 `_context()` 와 뜻이 같다(검색이 보고 화면이 보여 주는 한 값 · D-99).
       상위 항목은 **같은 별표 · 같은 구역**(`본문`/`비고`)에서 경로(`1.가.10` → `1` · `1.가`)로 찾는다.
    🚨 `text` 는 바꾸지 않는다 — 인용 단위와 `chunk_id` 가 그대로다(D-158). 바뀌는 것은 임베딩 입력뿐이라 **재임베딩**이 필요하다.
    🚨 상위 항목을 못 찾으면 **있는 것만** 붙인다 — 지어내지 않는다. 비고 구역은 「비고」를 붙인다.
    """
    no = r.get("annex_no_head")
    head = f"[별표 {no}] {r['annex_title']}" if no else str(r["annex_title"])
    if r["section"] != "본문":
        head = f"{head} · {r['section']}"
    parts = str(r["path"]).split(".")
    anc = [by_path.get((r["section"], ".".join(parts[:k]))) for k in range(1, len(parts))]
    return "\n".join([head, *(a for a in anc if a)])


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
                    #: 🔄 W6 — 법 축(D-271 ①). 모르는 법 ID 면 `None` 으로 두고 `main()` 이 **쓰기 전에** 멈춘다
                    "law": LAW_OF_ID.get(r["파일"].split("_")[1]),
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
        src = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        #: 같은 별표 안에서 상위 항목을 찾는 표 — (구역, 경로) → 본문 (`_annex_context`)
        by_path = {(r["section"], str(r["path"])): (r.get("text") or "").strip() for r in src}
        for r in src:
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
                        #: ⬜ 항 서수는 별표에 없다 — 계층 표기가 `2.가.10` 이라 법령의 조·항·호 규칙이 안 먹는다.
                        "paragraph_no": None,
                        #: 🔄 2026-09-24 — 종전에는 「별표는 범위 밖」(0008)으로 **빈 문자열**이었다.
                        #:    짧은 목록 청크가 벡터 상위를 점령해(W6 재측정) 별표 제목 + 상위 항목을 붙인다.
                        # ⛔ 2026-09-26 — 한때 문맥을 글자 상한(900)에 맞춰 잘랐다(`_fit_context`). 근거가 틀렸다 —
                        #    KURE-v1 은 8192토큰까지 받아 임베딩은 잘리지 않았고(512 는 리랭커 축 · D-200), 긴 문맥은
                        #    `law_norm` 이 `(1)` 계층 · [부표] 를 놓쳐 만든 거대 상위 노드였다. 파서를 고치고 자르기를 걷었다(사실원장 ㉜).
                        #    🚨 되살리지 않는다 — 상위 항목이 길면 먼저 **파서가 계층을 놓쳤는지** 본다.
                        "context": _annex_context(r, by_path),
                        "doc_type": "별표",
                        "law": LAW_OF_ID.get(r["law_id"]),
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
    ap.add_argument(
        "--allow-shrink",
        action="store_true",
        help=f"🚨 이전 판보다 {SHRINK_LIMIT * 100:.0f}%% 넘게 줄어도 쓴다 — 줄어든 이유를 안 뒤에만",
    )
    args = ap.parse_args()

    # 🔴 **한쪽만 있어도 실패한다** (2026-09-10 · D-220).
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

    # 🔴 **법을 못 정한 청크가 있으면 멈춘다** (W6 · D-271 ① · D-220).
    #    ⛔ 종전 `category_of()` 는 모르면 「일반」을 줬다 — 그 기본값이 265청크를 틀린 법에 앉혔다.
    #    ★ 법 ID 가 대응표에 없으면 `collect/law_map.py` 에 한 줄 더한다 (게이트가 `TARGETS` 와 양방향으로 댄다).
    unknown = collections.Counter(str(r.get("law_id")) for r in rows if r.get("law") is None)
    if unknown:
        print(
            f"🔴 법을 못 정한 청크 {sum(unknown.values())}개 — 법 ID {dict(unknown)}\n"
            "   `collect/law_map.py` `LAW_OF_ID` 에 없다. 기본값으로 떨어뜨리지 않는다 (D-271 ①).",
            file=sys.stderr,
        )
        return 1

    long_ = sum(1 for r in rows if r["part_total"] > 1)
    laws = collections.Counter(r["law"] for r in rows)
    print(f"  청크 {len(rows)}개 · 최장 {max(len(r['text']) for r in rows)}자")
    print(f"  법 {dict(laws.most_common())}")
    print(f"  🚨 길어서 쪼갠 청크 {long_}개 — `part_no`/`part_total` 이 원 조문을 가리킨다")
    # 🔴 **뺀 수를 매번 찍는다** — 조용히 줄면 다음 사람이 원장과 어긋나는 수를 보고 헤맨다.
    print(f"  ⬜ 제목뿐인 조 머리 행 {dropped}개를 담지 않았다 (D-159 · D-195)")
    print("     🚨 DB 에 남은 옛 청크는 `scripts/embed.py` 가 거둔다 — 여기서는 안 지운다 (D-187)")
    print(f"  ⚠️ 토큰 수는 글자 상한({MAX_CHARS})으로 어림했다 — 실측은 W1 의 남은 일이다")

    out = DERIVED / "chunks.jsonl"
    # 🔴 **하한 래칫** (2026-09-20 · D-254) — 이전 판보다 크게 줄면 **쓰기 전에** 멈춘다.
    #    ⛔ 종전 가드는 「두 층이 다 비었나」뿐이라 −15% 가 초록으로 지나갔다 (09-18 조문).
    #    ★ 미리보기(`--dump` 없이)에서도 수는 찍는다 — 쓰기 전에 보이게.
    prev = previous_counts(out)
    shrunk = shrinkage(prev, layer_counts(rows)) if prev is not None else []
    if shrunk:
        print(
            f"\n🔴 이전 판 대비 {SHRINK_LIMIT:.0%} 넘게 줄었다 — data/derived/{out.name}",
            file=sys.stderr,
        )
        for line in shrunk:
            print(f"   {line}", file=sys.stderr)
        print(
            "   🚨 이 판이 `embed` 로 가면 DB 의 청크가 그만큼 **지워진다** (sweep_orphans · D-187).\n"
            "   먼저 왜 줄었는지 본다 — 추출기 입력(원문 판)·`_TITLE_ONLY`·파생물 동기화.\n"
            "   줄어든 것이 맞다고 판단했으면:\n"
            "     uv run python -m preprocess.chunk --dump --allow-shrink",
            file=sys.stderr,
        )
        if args.dump and not args.allow_shrink:
            print("   ⛔ 쓰지 않았다 — 이전 판이 그대로 남아 있다.", file=sys.stderr)
            return 1
        if args.dump:
            print("   ⚠️ --allow-shrink — 줄어든 판을 쓴다 (위 수를 기록에 남긴다)", file=sys.stderr)

    if args.dump:
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(store.stamp(r, "law_go_kr"), ensure_ascii=False) + "\n")
        print(f"  💾 → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
