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

★ 적는 단위 — 🔄 2026-10-14 (ksr 흡수 · 팀장 (다)) **문구 하나 = `work_doc` 하나** · 엔진이 나눈 문장 하나 = `copy_sentence` 하나 +
   `judgment` 하나. 문구 칸마다 별개의 광고 문구이고 `kind='single'` 은 「사용자가 직접 쓰는 문서」다(`app/models.py`).
   ⛔ 종전(ssm 10-13)에는 검수 한 번(문구 여러 칸)을 문서 하나로 묶었다. 이력 화면(`_history_rows`)이 `judgment` × `copy_sentence` 를
   문장 단위로 읽는다. 문서 제목에는 문구 원문을 넣지 않는다 — 원문은 `copy_sentence.raw` 한 곳이다(동의 철회 때 지울 자리를 늘리지 않는다).
★ 🆕 2026-10-14 (ksr 흡수) — 불가 사유(A · B · C)를 `evidence.infeasibility` 에 싣는다 — 표에 칸이 없고, 이력의 배지가 검수 화면과
   같은 말을 하려면 사유가 있어야 한다(`app/routers/user.py` `_hist_view`).
★ 🆕 2026-10-14 (ksr 흡수) — 결과를 **상태 글자**로 돌려준다 — 화면이 그대로 알린다(`review.html` `history_kept`):
   `saved` 적었다 · `off` 회원인데 선택 동의 ① 이 꺼져 있다 · `failed` 적지 못했다 · `None` 비회원이거나 적을 판정이 없다.
   못 적었으면 「저장됐다」고 말하지 않는다(D-147). 저장은 ksr 의 `_save_review` · `_keep_history`(10-13)와 이 모듈(ssm 10-13)이
   같은 일을 두 벌로 하던 것을 이 모듈 하나로 모았다(D-99).
★ 적는 판정 — 응답의 **기록되는 판정**(`sentences`)만이다. 분기(`branches`)는 적지 않는다 —
   「선택한 전제의 저장은 판정 저장과 함께 정한다」(D-319 결정 7 ⬜) · 「고른 전제의 결과는 통과율에 섞지 않는다」(D-263 ①).
⚠️ `judgment.violation_type` 은 한 칸이다 — 문장에 위반 유형이 여럿이면 **첫 유형**을 적고, 전부는 `evidence.violations` 에 남긴다.
⚠️ 인코더 후보(`encoder_candidates`)는 적지 않는다 — 판정이 아니라 추정이다(D-323). 적을지는 따로 정한다.
   🔄 2026-10-16 (D-348 보충 2 결정 8 · D-323 좁힘) — **인코더 하한(`risk_encoder`)이 적힌 문장은 그 근거 호만 적는다**
   (`evidence.encoder_refs` · 유형과 참조 조항). 저장된 등급마다 근거가 남아야 한다(D-224) — 후보 전체 · 확률은 여전히 적지 않는다.
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

from app.contracts import LAW_VERSION_UNKNOWN, Risk, is_conditional
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


def _encoder_refs(s: SentenceJudgment) -> list[dict]:
    """인코더 하한의 근거 — 위험도가 든 근거(`risk.encoder_basis` · 분기 · 유형 · 하한 · 호) 그대로 (D-348 보충 2 결정 2 · 8 · 10).

    ⛔ 확률(`confidence`) · 표시용 후보(`encoder_candidates`)는 적지 않는다 — 판정이 아니다(D-323). 인코더 하한이 없으면 빈 목록.
    """
    if s.risk.encoder is None:
        return []
    return [b.model_dump(mode="json") for b in s.risk.encoder_basis]


def _category(res: JudgeResponse) -> tuple[str | None, str | None]:
    """(품목, 품목 출처) — **둘 다 있거나 둘 다 없다** (`ck_judgment_category_source_pair` · D-276).

    🔄 2026-10-14 (ksr 흡수) — 계약이 이 짝을 이미 강제한다(`JudgeResponse` 검증 · D-99). 그대로 옮긴다.
    ⛔ 종전에는 출처가 비면 `classified` 로 채웠다 — 계약이 바뀌면 조용히 틀린 출처를 적는 자리였다(D-220).
       짝이 깨진 응답이 오면 DB 의 CHECK 가 거부하고 `failed` 로 알린다.
    """
    return (
        res.category.value if res.category else None,
        res.category_source.value if res.category_source else None,
    )


def _judgment_row(
    doc_id: uuid.UUID, subject_id: uuid.UUID, s: SentenceJudgment, res: JudgeResponse
) -> Judgment:
    category, source = _category(res)
    violations = [v.value for v in s.violations]
    enc_refs = _encoder_refs(s)
    evidence: dict | None = (
        {
            "violations": violations,
            "articles": [a.model_dump(mode="json") for a in s.evidence],
            # 🆕 2026-10-14 (ksr 흡수) — 이력 배지가 읽는다(`_hist_view`). 확정 위반이 아니면 None
            "infeasibility": s.infeasibility.value if s.infeasibility else None,
        }
        if violations
        or s.evidence
        or enc_refs
        or bool(s.user_facts)
        or s.user_subst is not None
        or is_conditional(s)
        else None
    )
    if evidence is not None and s.user_facts:
        # 🆕 2026-10-16 (D-348 보충 3 결정 4) — 이 판정은 사용자가 확인한 사실로 정했다 · 출처(책임)를 남긴다
        evidence["user_facts"] = [f.model_dump(mode="json") for f in s.user_facts]
    if evidence is not None and is_conditional(s):
        # 🆕 2026-10-16 (D-348 보충 4 결정 2) — **조건부 위반**은 보류 사유가 아니라 분류다 · 이력 화면이 이 칸으로 그린다(`_hist_view`).
        #    DB 칸(verdict · hold_reason)은 보류 · premise_unknown 그대로 — 갈래와 받는 자료 · 답하면 내려가는 상한을 남긴다
        branch = s.fact_check or s.substantiation
        evidence["conditional"] = {
            "kind": "fact" if s.fact_check is not None else "subst",
            "accepted_evidence": list(branch.accepted_evidence) if branch else [],
            "max": (
                s.fact_check.confirmed_max.value
                if s.fact_check is not None
                else s.substantiation.substantiated_max.value  # type: ignore[union-attr]
            ),
        }
    if evidence is not None and s.user_subst is not None:
        # 🆕 2026-10-16 (D-348 보충 4 결정 3) — 사용자가 답한 실증 여부 · 출처(책임)를 남긴다
        evidence["user_subst"] = s.user_subst.model_dump(mode="json")
        # 🆕 2026-10-21 (D-348 보충 39 결정 6 · 2 단계) 섞인 유형은 실증 답이 유형마다 하나씩 — 목록 전부를 남긴다(정본 `user_substs`) ·
        #    `user_subst` 는 그 첫 답(종전 칸 · 이력 화면이 읽는다 · 계약의 계산 칸과 같은 값)
        evidence["user_substs"] = [u.model_dump(mode="json") for u in s.user_substs]
    if evidence is not None and enc_refs:
        # 🆕 2026-10-16 (D-348 보충 2 결정 8) — 인코더 하한의 근거 호 · DB 가 `ck_judgment_encoder_has_basis` 로 댄다
        evidence["encoder_refs"] = enc_refs
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
        risk_encoder=_risk_int(
            s.risk.encoder
        ),  # 🆕 2026-10-16 (D-348 보충 2) — 인코더 하한 · 사전 하한과 칸이 다르다
        law_version=(res.law_version or LAW_VERSION_UNKNOWN)[:_LAW_VERSION_MAX],
        attempt=res.attempt,
        judged_by=(res.judged_by or "unknown")[:_JUDGED_BY_MAX],
    )


def _judged(res: JudgeResponse) -> list[SentenceJudgment]:
    """적을 문장 — 판정 대상 아님(`not_claim`)을 뺀 기록되는 판정 (D-275 · 모듈 머리말)."""
    return [s for s in res.sentences if not s.not_claim]


def build_rows(
    user: UserAccount, results: Iterable[JudgeResponse]
) -> tuple[list[WorkDoc], list[CopySentence], list[Judgment]]:
    """적을 행을 만든다(DB 를 열지 않는다). 테스트가 이 함수로 칸을 잰다.

    🔄 2026-10-14 — **문구(응답) 하나 = 문서 하나**. 적을 문장이 없는 문구는 문서를 만들지 않는다.
    """
    docs: list[WorkDoc] = []
    sentences: list[CopySentence] = []
    judgments: list[Judgment] = []
    for res in results:
        judged = _judged(res)
        if not judged:
            continue
        doc = WorkDoc(
            id=uuid.uuid4(),
            title=f"문구 검수 · 문장 {len(judged)}개"[:_TITLE_MAX],
            kind="single",
            consent_store=True,
            consent_train=user.consent_improve_at is not None,
            owner_id=user.id,
            expires_at=None,
        )
        docs.append(doc)
        for s in judged:
            cs = CopySentence(
                id=uuid.uuid4(),
                doc_id=doc.id,
                raw=s.text,
                norm=norm(s.text),
                origin="user",
            )
            sentences.append(cs)
            judgments.append(_judgment_row(doc.id, cs.id, s, res))
    return docs, sentences, judgments


#: `save_review` 의 상태 글자 — 화면(`review.html` `history_kept`)이 이 글자로 알린다
SAVED, OFF, FAILED = "saved", "off", "failed"


def save_review(
    session: Session, user: UserAccount | None, results: Iterable[JudgeResponse]
) -> str | None:
    """검수 결과를 적고 **어떻게 됐는지** 돌려준다 — `SAVED` · `OFF` · `FAILED` · `None`(비회원 · 적을 판정 없음).

    🚨 예외를 올리지 않는다 — 호출한 화면은 판정 결과를 그대로 그리고, 상태 글자로 저장 여부만 알린다.
       삼키지 않는다 — 실패는 `FAILED` 로 화면에 나가고 예외 종류는 로그에 남는다(D-162 · D-147).
    """
    if user is None:
        return None  # D-69 · D-307 — 비회원 안내는 입력 카드에 이미 있다
    if not should_store(user):
        return OFF  # D-96 — 기본값은 미보관. 검수는 그대로 된다
    try:
        docs, sentences, judgments = build_rows(user, results)
        if not judgments:
            return None
        session.add_all(docs)
        session.flush()  # work_doc 먼저 — copy_sentence · judgment 의 FK 가 가리킨다
        session.add_all(sentences)
        session.flush()
        session.add_all(judgments)
        session.commit()
        return SAVED
    except Exception as e:  # noqa: BLE001 — 저장 실패가 판정 응답을 막지 않는다(상태는 화면에 나간다)
        with contextlib.suppress(Exception):  # 되돌리기 실패도 응답을 막지 않는다
            session.rollback()
        _log.warning("판정 저장 실패 — %s", type(e).__name__)
        return FAILED
