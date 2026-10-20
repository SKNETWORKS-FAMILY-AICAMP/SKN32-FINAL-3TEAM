"""app/guide_table.py — **두 겹 안내의 승인 표** (🆕 2026-10-20 · D-348 보충 32 결정 3).

🔴 승인된 줄만 적는다(D-147 · D-263 ②). 초안 · 근거는 `docs/ohb/안내문안_초안_2026-10-20.md` — 글자를 바꾸면 그 문서를 먼저 고치고 다시 승인받는다.
★ 열쇠 — `premise:<전제>` · `subst:<법>:<유형>` · `fact:<종류>` (`app/guide.py`).
★ 조문 좌표 — `<문서>|<조>|<가지>|<항>|<호>` · 수집본(`data/derived/law_article.jsonl`) 칸 그대로(문서 = 파일 이름에서 날짜를 뺀 것).
   좌표를 더하거나 바꾸면 생성물을 다시 만든다 — `uv run python scripts/guide_build.py --write`
"""

from __future__ import annotations

#: 쉬운 풀이 — 열쇠 → (무엇인가, 확인하는 법, 헷갈리기 쉬운 것) · 빈 칸은 None · 🔴 승인 전에는 비어 있다
PLAIN: dict[str, tuple[str | None, str | None, str | None]] = {}

#: 원문 짝 표 — 열쇠 → 조문 좌표들 · 🔴 승인 전에는 비어 있다
ARTICLES: dict[str, tuple[str, ...]] = {}
