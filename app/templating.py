"""app/templating.py — Jinja2 를 **한 곳에서** 만든다 (D-99 · 보안점검 P2-9).

⛔ **왜 모듈 하나를 따로 두나** — `Jinja2Templates(...)` 를 라우터마다 만들면
   **자동 이스케이프 설정이 사람마다 갈린다.** 한 사람이 `autoescape=False` 를 주면
   그 화면만 조용히 XSS 가 열린다. 만드는 자리를 하나로 두면 갈릴 자리가 없다 (D-117).

🔴 **자동 이스케이프는 켜져 있다** — `Jinja2Templates` 의 기본값이고, 아래 `assert` 가
   그것을 **런타임에** 확인한다. 게이트도 같은 것을 본다 (`tests/test_templates.py`).
   ⛔ `|safe` 는 쓰지 않는다. 하이라이트는 문자열이 아니라 `(offset, length, type)` 로 넘긴다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"
STATIC_ROOT = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_ROOT))

# 🚨 **가정을 실행 시점에 확인한다.** Jinja2 의 기본값이 바뀌거나 누가 만드는 자리를
#    늘리면 여기서 즉시 죽는다 — 조용히 열리는 것보다 낫다 (D-220 fail-closed).
if not templates.env.autoescape:  # pragma: no cover — 기본값이 바뀌어야 도달한다
    raise RuntimeError(
        "Jinja2 자동 이스케이프가 꺼져 있다 — 보안점검 P2-9.\n"
        "  고치는 법 — app/templating.py 에서 autoescape 를 켠 채로 만든다"
    )


def evidence_parts(evidence: object) -> dict[str, list]:
    """근거 목록 → `{"basis": 인용 근거, "refs": 참고 조문}` (🆕 2026-10-08 · 근거 표시 「(나)」 · D-224).

    ★ **인용 근거** = 사전 항목이 인용한 조문 — 판정이 기대는 조문. 꼴이 인용으로 되돌아오는 줄이다
       (`collect.statute.from_article_item` · 그래프가 쓰는 꼴과 한 곳 · D-99).
    ★ **참고 조문** = 검색이 문장과 가깝다고 찾은 조문 — 판정을 바꾸지 않는다.
    🚨 계약(`EvidenceArticle`)에는 둘을 가르는 칸이 없다 — 꼴로 가른다. 칸을 둘지는 판정 안건이다(인코더 후보 출처와 함께).
       그래프는 인용 근거를 **앞에** 둔다(`app/graph.py` `_judge_one`). 순서가 아니라 꼴로 가르는 것은 픽스처 · 외부 응답도 같게 읽으려고다.
    """
    from collect import statute  # noqa: PLC0415 — 템플릿 필터에서만 쓴다

    basis: list = []
    refs: list = []
    for e in evidence or ():  # type: ignore[attr-defined]
        cite = statute.from_article_item(e.law_id, e.article, e.item)
        (basis if cite is not None else refs).append(e)
    return {"basis": basis, "refs": refs}


templates.env.filters["evidence_parts"] = evidence_parts
