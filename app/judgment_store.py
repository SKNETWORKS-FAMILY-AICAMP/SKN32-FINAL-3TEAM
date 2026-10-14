"""app/judgment_store.py — 검수 판정을 `work_doc` · `copy_sentence` · `judgment` 에 적는다 · 🆕 2026-10-13 (소성민).

★ W10(BFF DB 쓰기)의 판정 쪽 첫 판이다. `/u/judge` 가 코어 판정을 받은 **뒤에** 부른다 — 판정을 바꾸지 않는다 (D-119).

🔴 **저장 조건 — 둘 다일 때만 쓴다**
   ① 로그인한 회원이다 — 비회원 판정은 응답만 내고 아무것도 쓰지 않는다 (D-307)
   ② 회원이 선택 동의 ①「검수 이력 보관」을 했다(`user_account.consent_history_at`) — 동의가 없으면 쓰지 않는다 (D-96)
      ★ 그래서 `work_doc.consent_store` 는 늘 참이고 `expires_at` 은 비운다(`ck_work_doc_expiry_without_consent`).
        동의 없는 회원 행을 만들었다가 지우는 길(TTL · 파기 증명)을 만들지 않는다 — 처음부터 안 쓰는 것이 D-96 의 기본값이다.
   ③ `work_doc.consent_train` 은 선택 동의 ②(`consent_improve_at`)를 그대로 옮긴다 — 학습 · 원문 조회의 유일한 문(D-128)

🔴 **실패해도 판정 응답은 나간다** — 저장은 부가 기능이다. 실패하면 되돌리고(rollback) 예외 **종류 이름만** 로그에 남긴다.
   ⛔ 원문 · 원인 문자열은 로그에 담지 않는다 — 원문은 영업비밀이고(D-46) 원인 문자열에는 접속 정보가 섞인다(`app.db.reachable` 와 같은 이유).

★ 적는 단위 — 검수 한 번(문구 여러 칸) = `work_doc` 하나 · 엔진이 나눈 문장 하나 = `copy_sentence` 하나 + `judgment` 하나.
   이력 화면(`_history_rows`)이 `judgment` × `copy_sentence` 를 문장 단위로 읽는다.
★ 적는 판정 — 응답의 **기록되는 판정**(`sentences`)만이다. 분기(`branches`)는 적지 않는다 —
   「선택한 전제의 저장은 판정 저장과 함께 정한다」(D-319 결정 7 ⬜) · 「고른 전제의 결과는 통과율에 섞지 않는다」(D-263 ①).
⚠️ `judgment.violation_type` 은 한 칸이다 — 문장에 위반 유형이 여럿이면 **첫 유형**을 적고, 전부는 `evidence.violations` 에 남긴다.
⚠️ 인코더 후보(`encoder_candidates`)는 적지 않는다 — 판정이 아니라 추정이다(D-323). 적을지는 따로 정한다.
🔴 🆕 2026-10-14 (흡수 중 고침 · 팀장 (다)) — **판정 대상 아님(`not_claim`) 문장은 적지 않는다.** 표에 그 칸이 없어 적으면
   「확정 · 위반 없음 · R0」 — 이력 · 통계에서 「특이사항 없음」(통과에 가까운 상태)으로 읽힌다. 통과는 닫아 두었다(D-275 · D-323 결정 5).
   ksr 의 이력 저장(`_save_review` · 10-13)과 같은 규칙이다 — 저장은 이 모듈 하나로 모은다(ksr 흡수 때 나머지 규칙을 옮긴다 · D-99).
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.contracts import CategorySource, Risk
from app.dictmatch import norm
from app.models import CopySentence, Judgment, WorkDoc

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.contracts import JudgeResponse, SentenceJudgment
    from app.models import UserAccount

_log = logging.getLogger("copylane.judgment_store")

#: 칸 길이 — `app/models.py` 와 같은 값이다. 넘치면 DB 가 거부하므로 여기서 자른다.
_TITLE_MAX = 200
_LAW_VERSION_MAX = 40
_JUDGED_BY_MAX = 80


def should_store(user: UserAccount | None) -> bool:
    """이 사용자의 판정을 적는가 — 회원 ∧ 선택 동의 ① (D-307 · D-96)."""
    return user is not None and user.consent_history_at is not None


def _risk_int(r: Risk | None) -> int | None:
    """`R0`~`R4` → 0~4. 표의 칸은 정수다 (`ck_judgment_risk_*`)."""
    return None if r is None else int(r.value[1:])


def _category(res: JudgeResponse) -> tuple[str | None, str | None]:
    """(품목, 품목 출처) — **둘 다 있거나 둘 다 없다** (`ck_judgment_category_source_pair` · D-276).

    ★ 응답에 품목은 있는데 출처가 비었으면 `classified` 다 — `/u/judge` 는 품목을 넘기지 않으므로 그 품목은 엔진이 판별한 것이다 (D-82).
    """
    if res.category is None:
        return None, None
    source = res.category_source or CategorySource.classified
    return res.category.value, source.value


def _judgment_row(
    doc_id: uuid.UUID, subject_id: uuid.UUID, s: SentenceJudgment, res: JudgeResponse
) -> Judgment:
    category, source = _category(res)
    violations = [v.value for v in s.violations]
    evidence = (
        {
            "violations": violations,
            "articles": [a.model_dump(mode="json") for a in s.evidence],
        }
        if violations or s.evidence
        else None
    )
    span = s.risk.evidence_span
    return Judgment(
        id=uuid.uuid4(),
        doc_id=doc_id,
        subject_type="copy_sentence",
        subject_id=subject_id,
        verdict=s.verdict.value,
        hold_reason=s.hold_reason.value if s.hold_reason else None,
        product_category=category,
        product_category_source=source,
        violation_type=violations[0] if violations else None,
        evidence=evidence,
        evidence_span=span.model_dump(mode="json") if span is not None else None,
        risk_floor=_risk_int(s.risk.floor),
        risk_final=_risk_int(s.risk.final),
        law_version=(res.law_version or "unknown")[:_LAW_VERSION_MAX],
        attempt=res.attempt,
        judged_by=(res.judged_by or "unknown")[:_JUDGED_BY_MAX],
    )


def _judged(res: JudgeResponse) -> list[SentenceJudgment]:
    """적을 문장 — 판정 대상 아님(`not_claim`)을 뺀 기록되는 판정 (D-275 · 모듈 머리말)."""
    return [s for s in res.sentences if not s.not_claim]


def build_rows(
    user: UserAccount, results: Iterable[JudgeResponse]
) -> tuple[WorkDoc, list[CopySentence], list[Judgment]]:
    """적을 행을 만든다(DB 를 열지 않는다). 테스트가 이 함수로 칸을 잰다."""
    results = list(results)
    n_sent = sum(len(_judged(r)) for r in results)
    doc = WorkDoc(
        id=uuid.uuid4(),
        title=f"문구 검수 {len(results)}건 · 문장 {n_sent}개"[:_TITLE_MAX],
        kind="single",
        consent_store=True,
        consent_train=user.consent_improve_at is not None,
        owner_id=user.id,
        expires_at=None,
    )
    sentences: list[CopySentence] = []
    judgments: list[Judgment] = []
    for res in results:
        for s in _judged(res):
            cs = CopySentence(
                id=uuid.uuid4(),
                doc_id=doc.id,
                raw=s.text,
                norm=norm(s.text),
                origin="user",
            )
            sentences.append(cs)
            judgments.append(_judgment_row(doc.id, cs.id, s, res))
    return doc, sentences, judgments


def save_review(
    session: Session, user: UserAccount | None, results: Iterable[JudgeResponse]
) -> int | None:
    """검수 결과를 적는다. 반환 — 적은 판정 행 수 · 적지 않을 사용자면 `0` · **실패하면 `None`**.

    🚨 예외를 올리지 않는다 — 호출한 화면은 반환값과 무관하게 판정 결과를 그린다.
    """
    if not should_store(user):
        return 0
    try:
        doc, sentences, judgments = build_rows(user, results)  # type: ignore[arg-type]
        if not judgments:
            return 0
        session.add(doc)
        session.flush()  # work_doc 먼저 — copy_sentence · judgment 의 FK 가 가리킨다
        session.add_all(sentences)
        session.flush()
        session.add_all(judgments)
        session.commit()
        return len(judgments)
    except Exception as e:  # noqa: BLE001 — 저장 실패가 판정 응답을 막지 않는다
        with contextlib.suppress(Exception):  # 되돌리기 실패도 응답을 막지 않는다
            session.rollback()
        _log.warning("판정 저장 실패 — %s", type(e).__name__)
        return None
