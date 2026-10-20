"""app/guide.py — **두 겹 안내**(쉬운 풀이 · 원문 보기)를 응답에 붙이는 곳 (🆕 2026-10-20 · D-348 보충 32 결정 3).

★ 자리 셋 — 사용자가 고르는 칸마다 하나:
   · 품목 · 하위 전제 선택지(`Branch`) — 열쇠 `premise:<전제>`
   · 실증 질문(`SubstBranch`) — 열쇠 `subst:<법>:<유형>`(기준 문안 표 `reasons.SUBST_TEXT` · `TYPE_SUBST_TEXT` 의 줄 하나)
   · 사실 확인 · 유형 질문(`FactBranch`) — 열쇠 `fact:<종류>`
🔴 **승인된 것만 싣는다**(D-147 · D-263 ②) — 아래 두 표(`PLAIN` · `ARTICLES`)에 없는 열쇠는 안내 칸이 없다(None).
   초안은 `docs/ohb/안내문안_초안_2026-10-20.md` 에 있고, 승인된 줄만 여기로 옮긴다(글자를 바꾸면 문서를 먼저 고치고 다시 승인).
🔴 원문 글자는 손으로 적지 않는다 — `scripts/guide_build.py` 가 수집본(`data/derived/law_article.jsonl`)에서 `app/guide_articles.json` 으로
   옮긴다(D-90). 짝 표에 있는 조문이 그 파일에 없으면 import 에서 멈춘다(D-220 · 낡은 생성물로 원문을 빼먹지 않는다).
🚨 판정이 아니다 — 응답을 다 만든 뒤(`graph.to_response`) 붙인다. 판정 · 분기 열쇠(`_branch_key` · `_shown_key`) · 위험도에 들지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import reasons as rs
from app.contracts import (
    Branch,
    FactKind,
    Guide,
    GuideArticle,
    JudgeResponse,
    Premise,
    SentenceJudgment,
    SubstBranch,
)

# 🔴 승인 표는 `app/guide_table.py` 한 곳 — 생성 스크립트(`scripts/guide_build.py`)도 그것을 읽는다(이 모듈의 import 검사를 거치지 않게)
from app.guide_table import ARTICLES, PLAIN

#: 생성물 — `scripts/guide_build.py` 가 쓴다(손으로 고치지 않는다 · D-90)
ARTICLES_FILE = Path(__file__).with_name("guide_articles.json")


def premise_key(p: Premise) -> str:
    return f"premise:{p.value}"


def fact_key(k: FactKind) -> str:
    return f"fact:{k.value}"


def _subst_keys() -> dict[str, str]:
    """실증 기준 문안 → 열쇠. 문안 표가 한 곳이라(`reasons`) 문안 글자로 줄을 찾는다(D-99) — 같은 글자의 줄이 둘이면 멈춘다."""
    out: dict[str, str] = {}
    rows = [(f"subst:{ax}:거짓_과장", t.criteria) for ax, t in rs.SUBST_TEXT.items()]
    rows += [(f"subst:{ax}:{v.value}", t.criteria) for (v, ax), t in rs.TYPE_SUBST_TEXT.items()]
    for key, crit in rows:
        if crit in out:
            raise RuntimeError(
                f"🔴 실증 기준 문안이 두 줄에서 같다 — {out[crit]} · {key} (안내 열쇠를 정하지 못한다)"
            )
        out[crit] = key
    return out


SUBST_KEYS = _subst_keys()


def subst_key(b: SubstBranch) -> str | None:
    return SUBST_KEYS.get(b.criteria)


def _load_articles() -> dict[str, GuideArticle]:
    if not ARTICLES_FILE.exists():
        return {}
    raw = json.loads(ARTICLES_FILE.read_text(encoding="utf-8"))
    return {k: GuideArticle(**v) for k, v in raw.items()}


TEXTS = _load_articles()


def missing_texts(
    articles: dict[str, tuple[str, ...]], texts: dict[str, GuideArticle]
) -> list[str]:
    """짝 표의 조문 중 생성물에 없는 좌표 — import 에서 하나라도 있으면 멈춘다."""
    return sorted({c for cs in articles.values() for c in cs} - set(texts))


if _missing := missing_texts(ARTICLES, TEXTS):
    raise RuntimeError(
        f"🔴 승인된 짝 표의 조문이 생성물에 없다 — {_missing[:5]} …\n"
        "   다시 만든다(정본): uv run python scripts/guide_build.py --write"
    )


def guide_for(key: str | None) -> Guide | None:
    """열쇠의 안내 — 승인된 글도 조문도 없으면 None (D-220)."""
    if key is None:
        return None
    plain = PLAIN.get(key)
    arts = [TEXTS[c] for c in ARTICLES.get(key, ())]
    if plain is None and not arts:
        return None
    what, check, pitfall = plain if plain is not None else (None, None, None)
    return Guide(what=what, check=check, pitfall=pitfall, articles=arts)


def _sentence(s: SentenceJudgment) -> SentenceJudgment:
    upd: dict = {}
    if s.fact_check is not None and s.fact_check.guide is None:
        g = guide_for(fact_key(s.fact_check.kind))
        if g is not None:
            upd["fact_check"] = s.fact_check.model_copy(update={"guide": g})
    if s.substantiation is not None and s.substantiation.guide is None:
        g = guide_for(subst_key(s.substantiation))
        if g is not None:
            upd["substantiation"] = s.substantiation.model_copy(update={"guide": g})
    return s.model_copy(update=upd) if upd else s


def _branch(b: Branch) -> Branch:
    g = b.guide or guide_for(premise_key(b.premise))
    sents = [_sentence(x) for x in b.sentences]
    if g is b.guide and all(x is y for x, y in zip(sents, b.sentences, strict=True)):
        return b
    return b.model_copy(update={"guide": g, "sentences": sents})


def attach(resp: JudgeResponse) -> JudgeResponse:
    """응답의 선택지 · 질문마다 승인된 안내를 붙인다 — 바꿀 것이 없으면 그대로(같은 객체)."""
    sents = [_sentence(s) for s in resp.sentences]
    branches = [_branch(b) for b in resp.branches]
    if all(x is y for x, y in zip(sents, resp.sentences, strict=True)) and all(
        x is y for x, y in zip(branches, resp.branches, strict=True)
    ):
        return resp
    return resp.model_copy(update={"sentences": sents, "branches": branches})


__all__ = [
    "ARTICLES",
    "PLAIN",
    "TEXTS",
    "attach",
    "fact_key",
    "guide_for",
    "missing_texts",
    "premise_key",
    "subst_key",
]
