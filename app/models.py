"""app/models.py — 런타임 층 ORM (D-103 · D-104).

🚨 **판정은 다형 참조로 저장한다.**
   규제가 붙는 대상은 도메인상 문장이 아니라 **주장**이다. 그러나 주장의 축은
   9/17 범위 확정(D-65)에서 정해지고, 「기능」의 값 집합은 인정 기능성 원료 데이터가
   들어와야 나온다. **지금 정하면 근거 없이 정하는 것이다.**
   `subject_type` 을 두면 주장 계층이 열릴 때 행이 **추가**될 뿐이므로,
   그 결정을 9/17 이후로 **미룰 수 있다.**

🚨 **`law_version` 은 문장이 아니라 판정에 붙는다.** 재판정하면 새 판정 행이 쌓이고
   이력이 남는다. 문장에 박으면 덮어써서 「언제 무엇으로 판정했었나」를 잃는다 (D-103 ③).

🚨 **`consent` 기본값은 미보관이다** (D-96). 동의가 없으면 이 행들은 세션 종료와 함께 지운다.
   템플릿 조립은 동의 여부와 무관하게 동작한다 — 동의가 기능의 대가가 되면 안 된다.

🚨 **지울 키가 있어야 지운다** (D-129). `work_doc` 의 `owner_id`·`session_id`·`expires_at` 이 그 키이고,
   `judgment.doc_id` 가 문장이 지워질 때 판정 행을 고아로 남기지 않는다. 업로드물은 `upload_blob` 한 곳에만
   경로가 있다 — 게이트 35 가 보는 것은 그 경로다 (D-128 · `UPLOAD_ROOT`).

🚨 **`consent_train` 은 `NOTRAIN` 의 유일한 해제다** (D-128). 학습·색인 코드가 `UPLOAD_ROOT` 를 참조할 때
   이 필터를 거치지 않으면 게이트 35 가 실패한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class WorkDoc(Base):
    """사용자 작업 문서 — 제품 1개 기준의 **재료 창고** (D-103 ②).

    템플릿은 이 문서를 조립한다. 문서는 슬롯을 모른다.

    🚨 **`product_category` 를 여기 두지 않는다** (D-82 · D-105).
       배치 검수는 한 실행 안에서 SKU 마다 카테고리가 다르고(건기식·화장품 혼재),
       D-82 는 카테고리를 **사용자에게 묻지 않고 우리가 판별**한다고 정했다.
       카테고리는 문서의 속성이 아니라 **판정의 결과**다 → `Judgment` 로 옮겼다.
    """

    __tablename__ = "work_doc"

    id: Mapped[uuid.UUID] = _pk()
    title: Mapped[str] = mapped_column(String(200))
    # 'single' = 사용자가 직접 쓰는 문서 · 'batch' = 배치 검수 1회가 만든 문서
    # 🚨 배치 실행 1회 = work_doc 1개다. batch_run.doc_id 가 그것을 가리킨다.
    kind: Mapped[str] = mapped_column(String(10), default="single")
    # 🚨 D-96 — 기본값은 미보관. true 일 때만 서버에 남는다
    consent_store: Mapped[bool] = mapped_column(default=False, nullable=False)
    # 🔄 D-96 개정분 ② — 「품질 개선을 위한 학습 · 검토 활용」. 학습(D-128 NOTRAIN 해제)과
    #    관리자 「원문 조회」 열람을 **같이** 연다. 열람용 플래그를 따로 두지 않는다. 기본 미동의.
    consent_train: Mapped[bool] = mapped_column(default=False, nullable=False)
    # 🚨 D-129 — 수명 키. 비회원(D-66 「A 는 가입 없음」)은 owner_id NULL · session_id + expires_at 로 지운다
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sentences: Mapped[list[CopySentence]] = relationship(
        back_populates="doc", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("kind in ('single','batch')", name="ck_work_doc_kind"),
        # 동의 없는 문서는 반드시 만료가 있다 — 「세션 종료와 함께 지운다」의 구조적 형태
        CheckConstraint(
            "consent_store OR expires_at IS NOT NULL", name="ck_work_doc_expiry_without_consent"
        ),
    )


class CopySentence(Base):
    """사용자가 쓰거나 우리가 생성한 문구 한 줄.

    🚨 수집한 원문의 `sentence` 와 다른 개체다 — fragment 에서 오지 않는다.
    """

    __tablename__ = "copy_sentence"

    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_doc.id", ondelete="CASCADE"), index=True
    )
    # D-84 ① · D-91 — 매칭은 정규화문에서, 보고는 원문 좌표로
    raw: Mapped[str] = mapped_column(Text)
    norm: Mapped[str] = mapped_column(Text)
    offset_map: Mapped[dict | None] = mapped_column(JSONB)
    # 'user'(붙여넣기) | 'generated'(진입점 B) | 'batch'(CSV 일괄) | 'crawl'(URL — 설계만)
    origin: Mapped[str] = mapped_column(String(16))
    external_ref: Mapped[str | None] = mapped_column(String(120))  # 배치 SKU · 출처 URL
    # 🚨 D-104 — 이미지 설명 생성 보조를 나중에 얹기 위한 자리.
    #    비워 두는 것이 「지금 넣지 않는다」를 고를 수 있게 한 조건이다.
    image_description: Mapped[str | None] = mapped_column(Text)
    # 승인은 판정의 속성이 아니라 상태다 (D-103)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    doc: Mapped[WorkDoc] = relationship(back_populates="sentences")

    __table_args__ = (
        CheckConstraint(
            "origin in ('user','generated','batch','crawl')", name="ck_copy_sentence_origin"
        ),
    )


class BatchRun(Base):
    """배치 검수 1회 — CSV/엑셀 일괄 판정 (D-105).

    🚨 **판정 코어 위의 for-loop 다.** 새 모델도 새 데이터도 없고, 결과 집계와 리포트가 전부다.
       그래서 판정 코어(Phase 0)만 서면 바로 붙는다.
    """

    __tablename__ = "batch_run"

    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_doc.id", ondelete="CASCADE"), index=True
    )
    source_name: Mapped[str] = mapped_column(String(200))  # 업로드 파일명
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    # 🚨 **집계 스냅샷** — 위험도 추이가 보관 동의에 걸리지 않게 하는 장치다.
    #    D-96 대로 동의가 없으면 원문(copy_sentence)은 세션 종료와 함께 사라지는데,
    #    그러면 judgment 를 조인해 계산하는 추이도 함께 사라진다.
    #    원문을 지우고 **집계만 남기면** 추이는 남는다 — 권소라 역검토 회신에서
    #    반려 문구에 적용한 것과 같은 형태다(원문 없이 집계만).
    #    { "verdict": {...}, "violation_type": {...}, "category": {...} }
    summary: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "state in ('pending','parsing','checking','revising','ready','failed')",
            name="ck_batch_run_state",
        ),
        CheckConstraint("done <= total", name="ck_batch_run_progress"),
    )


class Judgment(Base):
    """판정 — **다형 참조**. 지금은 `copy_sentence` 만, 나중에 `claim` 이 추가된다.

    🚨 다형이라 FK 무결성이 DB 수준에서 안 걸린다. 게이트 테스트로 대신 막는다.
    """

    __tablename__ = "judgment"

    id: Mapped[uuid.UUID] = _pk()
    # 🚨 D-129 — 다형 subject_id 와 별개로 문서 FK 를 둔다. 문장·문서가 지워지면 판정도 지워진다
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_doc.id", ondelete="CASCADE"), index=True
    )
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # D-127 — 상태 4종. 「근거 불일치(인용 검증 실패)」는 상태가 아니라 재생성 이벤트다 (D-126 카운터)
    #   confirmed 확정 · hold 보류(hold_reason 필수) · no_basis 근거없음(위험도·유형 유지) ·
    #   unjudged 미판정(오류·타임아웃 — 🚨 통과로 집계 금지)
    verdict: Mapped[str] = mapped_column(String(24))
    # hold 일 때만: low_conf | gap2 | cat_unknown | rd1
    hold_reason: Mapped[str | None] = mapped_column(String(16))
    # D-82 — 사용자에게 묻지 않고 우리가 판별한다. 그래서 판정 결과에 속한다
    product_category: Mapped[str | None] = mapped_column(String(40))
    violation_type: Mapped[str | None] = mapped_column(String(40))
    evidence: Mapped[dict | None] = mapped_column(JSONB)  # 근거 조문 집합
    # D-131 — 인코더가 하한 위로 올릴 때 반드시 붙는 근거 스팬 (raw 좌표 · D-30 주장 BIO)
    evidence_span: Mapped[dict | None] = mapped_column(JSONB)
    risk_floor: Mapped[int | None] = mapped_column(Integer)  # 코드 하한 (D-84 ③)
    risk_final: Mapped[int | None] = mapped_column(Integer)
    # 🚨 D-103 ③ — 개정되면 「재검증 대기」의 판단 근거가 된다
    law_version: Mapped[str] = mapped_column(String(40))
    # D-126 — 0-base. 총 라운드 K+1=3 이므로 0·1·2 만 가능
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    # D-68 — 공개 여부와 스크리닝 시각 (DB_스키마 W1 필수 · D-129 로 ORM 에 반영)
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False)
    screened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    judged_by: Mapped[str] = mapped_column(String(80))  # 코드/모델 버전
    judged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "subject_type in ('copy_sentence','claim')", name="ck_judgment_subject_type"
        ),
        CheckConstraint(
            "verdict in ('confirmed','hold','no_basis','unjudged')", name="ck_judgment_verdict"
        ),
        CheckConstraint(
            "(verdict = 'hold') = (hold_reason IS NOT NULL)", name="ck_judgment_hold_reason"
        ),
        CheckConstraint(
            "hold_reason IS NULL OR hold_reason in ('low_conf','gap2','cat_unknown','rd1')",
            name="ck_judgment_hold_reason_values",
        ),
        CheckConstraint("attempt BETWEEN 0 AND 2", name="ck_judgment_attempt"),
        # D-130 — 5값 순서형 R0(특이사항 없음)~R4(형사 위험). R2·R3 순서는 검증 ② 에서 확정
        CheckConstraint(
            "risk_floor IS NULL OR risk_floor BETWEEN 0 AND 4", name="ck_judgment_risk_floor"
        ),
        CheckConstraint(
            "risk_final IS NULL OR risk_final BETWEEN 0 AND 4", name="ck_judgment_risk_final"
        ),
        # D-131 — 인코더 상향은 근거 스팬이 있을 때만. 하한보다 높은데 스팬이 없으면 위반
        CheckConstraint(
            "risk_final IS NULL OR risk_floor IS NULL OR risk_final <= risk_floor OR evidence_span IS NOT NULL",
            name="ck_judgment_raise_needs_evidence",
        ),
        Index("ix_judgment_subject", "subject_type", "subject_id"),
    )


class UploadBlob(Base):
    """사용자 업로드물 — CSV · 이미지 (D-128 · D-129).

    🚨 **업로드물의 경로는 이 테이블에만 있다.** `path` 는 `UPLOAD_ROOT` 아래이고, 그 상수가
       D-122 의 `NOTRAIN` 이다 — 소스 플래그가 아니라 저장 경로다. 게이트 35 는 학습·색인 코드가
       `UPLOAD_ROOT` 를 `consent_train=true` 필터 없이 참조하면 실패한다.
    """

    __tablename__ = "upload_blob"

    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_doc.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))  # 'csv' | 'image'
    path: Mapped[str] = mapped_column(String(300))  # UPLOAD_ROOT 상대 경로
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("kind in ('csv','image')", name="ck_upload_blob_kind"),)


class SlotAssignment(Base):
    """템플릿 조립 — 슬롯에 무엇이 들어갔는가 (D-103 ①).

    🚨 **슬롯은 승인 객체만 받는다.** `sentence_id` 가 없는 슬롯은 「미검수」로 남고,
       그 표시는 산출물에서 제거할 수 없다.
    """

    __tablename__ = "slot_assignment"

    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_doc.id", ondelete="CASCADE"), index=True
    )
    template: Mapped[str] = mapped_column(String(24))  # 'detail_page' | ...
    slot: Mapped[str] = mapped_column(String(24))
    position: Mapped[int] = mapped_column(Integer)
    sentence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("copy_sentence.id", ondelete="SET NULL")
    )
    image_ref: Mapped[str | None] = mapped_column(String(200))
    # 🚨 승인 객체가 아닌 것이 들어간 슬롯 — 제거 불가능한 고지
    unreviewed_note: Mapped[str | None] = mapped_column(Text)
