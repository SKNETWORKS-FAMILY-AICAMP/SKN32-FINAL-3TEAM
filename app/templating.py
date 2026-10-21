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

from app import encoder, factcheck, reasons
from app.contracts import LAW_VERSION_UNKNOWN, fact_false

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

    ★ **인용 근거** = 사전 항목이 인용한 조문 — 판정이 기대는 조문. ★ **참고 조문** = 검색이 찾은 조문 — 판정을 바꾸지 않는다.
    🔄 2026-10-08 (D-323 결정 2) — 계약 칸 `EvidenceArticle.basis` 로 가른다. ⛔ 종전에는 좌표 꼴로 갈랐다(칸이 없던 때의 임시).
       칸이 거짓이면 참고다 — 칸을 모르는 쪽이 만든 근거가 판정 근거로 그려지지 않게 (D-220).
    """
    basis: list = []
    refs: list = []
    for e in evidence or ():  # type: ignore[attr-defined]
        (basis if getattr(e, "basis", False) is True else refs).append(e)
    return {"basis": basis, "refs": refs}


templates.env.filters["evidence_parts"] = evidence_parts
# 🆕 2026-10-11 — 보류 문장의 조건부 후보에 붙일 말. 문안과 규칙은 `app/reasons.py` 한 곳이다 (D-99)
templates.env.filters["candidate_condition"] = reasons.candidate_condition
# 🆕 2026-10-14 (D-330 보충 2 · D-323 보충) — 사전 유형 없이 인코더 유형 후보만 있는 문장. 규칙 · 문안은 `app/reasons.py` 한 곳 (D-99)
templates.env.filters["guessed_types"] = reasons.guessed_types
templates.env.filters["guessed_mark"] = reasons.guessed_mark
templates.env.filters["agreed_mark"] = reasons.agreed_mark
templates.env.filters["moved_note"] = reasons.moved_note
# 🆕 2026-10-15 (D-340 결정 3 · D-344 ⑨) — 사전 확정 문장에 인코더가 다른 유형을 냈다. 「근거 보기」 안에만 그린다
templates.env.filters["differing_types"] = reasons.differing_types
templates.env.globals["ENC_DIFFERS_MARK"] = reasons.ENC_DIFFERS_MARK
# 🆕 2026-10-15 (D-346 결정 6 · D-340 결정 5) — 후보 순서 · 대표 표지 · 추정 위험도 글자. 규칙 · 글자는 `app/reasons.py` 한 곳
templates.env.filters["ordered_candidates"] = reasons.ordered_candidates
templates.env.filters["estimate_text"] = reasons.estimate_text
# 🆕 2026-10-16 (D-348 보충 2 결정 10) — 인코더 하한의 근거(대표 한 줄 + 나머지). 규칙 · 글자는 `app/reasons.py` 한 곳
templates.env.filters["encoder_basis_view"] = reasons.encoder_basis_view
# 🆕 2026-10-16 (D-348 보충 4 결정 2) — 조건부 위반 문장의 결론 한 줄. 규칙(`contracts.is_conditional`) · 글자는 `app/reasons.py` 한 곳
templates.env.filters["conditional_text"] = reasons.conditional_text
#: 🆕 2026-10-16 (D-348 보충 5) — 질문이 달린 문장(조건부 위반 · 인코더 쪽 보류 + 분기)의 결론 한 줄 · 질문 칸을 그릴지
templates.env.filters["question_text"] = reasons.question_text
#: 🆕 2026-10-17 (D-348 보충 5 결정 5) — 사실이 거짓으로 확정된 문장인가(할 일 줄을 「고치거나 빼기」로) · 정의는 계약 한 곳
templates.env.filters["fact_false"] = fact_false
templates.env.globals["FACT_FALSE_TODO"] = reasons.FACT_FALSE_TODO
#: 🆕 2026-10-17 (D-348 보충 6 결정 8) — 일반상품 안내 두 줄(문안 초안)
templates.env.filters["general_goods_notes"] = reasons.general_goods_notes
templates.env.filters["slander_note"] = reasons.slander_note  # 🆕 2026-10-17 (D-348 보충 11)
templates.env.filters["nofree_note"] = reasons.nofree_note  # 🆕 2026-10-17 (D-348 보충 15)
#: 🆕 2026-10-17 (보충 5 결정 5 의 집행 꼴) — 종류별 질문 한 줄(승인 전에는 공통 질문)
templates.env.filters["fact_question"] = factcheck.fact_question
templates.env.filters["nofree_conditions"] = (
    factcheck.nofree_conditions
)  # 🆕 2026-10-17 (D-348 보충 14)
templates.env.globals["REPRESENTATIVE_MARK"] = reasons.REPRESENTATIVE_MARK
templates.env.globals["ENC_REMAINS_MARK"] = reasons.ENC_REMAINS_MARK
templates.env.globals["NOTE_UNJUDGED_MARK"] = (
    reasons.NOTE_UNJUDGED_MARK
)  # 🆕 2026-10-15 (D-344 ⑤) — 광고 생성의 필수 병기 문구


def law_version_label(value: object) -> str:
    """법령 판 → 화면 글자 (🆕 2026-10-13). 모르는 판은 「미확인」이다 — 내부 값 `unknown` 을 그리지 않는다.

    🔴 빈 값 · `None` 도 「미확인」이다 — 비어 있다고 아무 글자 없이 두면 판을 확인한 것처럼 읽힌다 (D-220).
    """
    if value is None or value == "" or value == LAW_VERSION_UNKNOWN:
        return "미확인"
    return str(value)


templates.env.filters["law_version_label"] = law_version_label

# 🆕 2026-10-13 (D-333) — 이 응답에서 인코더가 돌았는가. ⛔ 종전에는 화면이 `"+enc:" in judged_by` 를 직접 적었다 —
#    표지가 `+encb:` 로 바뀌면 화면만 조용히 「사용 안 함」이 된다. 표지 글자는 `app/encoder.py` 한 곳이다 (D-99)
templates.env.filters["encoder_ran"] = encoder.ran


def admin_closed_menus() -> dict[str, dict[str, str]]:
    """Read each router's current label lazily; eager imports would create a router cycle."""
    from app.routers import (  # noqa: PLC0415
        admin_enterprise,
        admin_review_docs,
        admin_signup_review,
        admin_stats,
        admin_terms,
    )

    return {
        path: {"state": "닫힘", "label": module.LABEL}
        for path, module in (
            ("/admin/signup-review", admin_signup_review),
            ("/admin/enterprise", admin_enterprise),
            ("/admin/review-docs", admin_review_docs),
            ("/admin/terms", admin_terms),
            ("/admin/stats/revenue", admin_stats),
        )
    }


templates.env.globals["admin_closed_menus"] = admin_closed_menus
