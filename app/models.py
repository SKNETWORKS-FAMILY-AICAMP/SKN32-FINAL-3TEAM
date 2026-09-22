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
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

from app.settings import ERROR_LOG_MESSAGE_MAX, PARAMS, TICKET_TEXT_MAX


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
    # 🔄 D-260 ② — `user_account.id` 를 가리킨다(0017). ON DELETE 없음 — 계정은 지우지 않고 끈다
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), index=True
    )
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
        # 🔄 상한은 `app/settings.py` 의 `PARAMS.max_attempt` 하나가 든다 (D-99 · D-126).
        #    ⛔ 종전에는 여기·계약·라우터 셋이 각각 `2` 를 적고 있었다. K 를 올리면
        #       라우터만 따라가고 DB 가 거부한다 — **가장 늦게 터지는 자리**였다.
        CheckConstraint(f"attempt BETWEEN 0 AND {PARAMS.max_attempt}", name="ck_judgment_attempt"),
        # D-130 · 🔄 D-227 — 척도는 **R0~R3 네 단계**다 (R0 특이사항 없음 · R1 주의 ·
        #   R2 업무정지 위험 · R3 영업 상실 위험). 🔴 `R4` 는 ENUM 에 남아 있으나 **도달 불가**다 —
        #   형벌은 R 축에 얹지 않고 `penal_clause` 가 그 자리다 (D-182).
        #   ⛔ CHECK 범위는 `0 AND 4` 로 **둔다** — ENUM 을 줄이지 않기로 했으므로 제약도 그대로다.
        CheckConstraint(
            "risk_floor IS NULL OR risk_floor BETWEEN 0 AND 4", name="ck_judgment_risk_floor"
        ),
        CheckConstraint(
            "risk_final IS NULL OR risk_final BETWEEN 0 AND 4", name="ck_judgment_risk_final"
        ),
        # D-131 — 인코더 상향은 근거 스팬이 있을 때만. 하한보다 높은데 스팬이 없으면 위반
        # ⛔ 종전 식은 `risk_floor IS NULL OR …` 라, **하한만 비우면** 근거 없이 R4 를
        #    적을 수 있었다 (0006 실측). 상향의 정의가 「하한보다 높다」인데 하한이 없으면
        #    상향이 정의되지 않아 무조건 통과였다.
        # ★ 새 뜻 — 최종 위험도를 적으려면 하한이 반드시 있어야 하고, 하한보다 높으면
        #    근거 스팬이 있어야 한다. 위험도를 안 적는 경우(unjudged·hold)는 그대로 통과.
        CheckConstraint(
            "risk_final IS NULL"
            " OR (risk_floor IS NOT NULL"
            "     AND (risk_final <= risk_floor OR evidence_span IS NOT NULL))",
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


class AppAccount(Base):
    """`governor` 계정 — **거버넌스 콘솔의 로그인** (D-66 · D-213 · 보안점검 P1-7).

    ★ D-66 이 *"`decided_by`·`reviewed_by` 를 채우려면 누가 로그인했는지 알아야 한다"* 라고
      적었다. **이 테이블이 그 「누가」다.** 없으면 2인 확인(D-66)의 서명이 손으로 적는 글자다.

    🚨 **가입 화면은 없다** (D-66 — 온프레미스는 계정 주입). 만드는 길은 하나 —
       `uv run python launcher.py admin-add <이니셜>`. 비밀번호는 `getpass` 로만 받는다
       (`setkey` 와 같은 모양 — 값이 셸 기록에 안 남는다).

    🔴 **`pw_hash` 는 PHC 문자열이다** — `$argon2id$v=19$m=19456,t=2,p=1$…`.
       알고리즘과 파라미터가 값 안에 있어서 나중에 올릴 때 판별이 필요 없다.
       ⛔ `CHECK` 가 접두어를 강제한다 — **SHA-256 한 방을 넣는 길을 코드가 막는다**
       (고시 제7조 · P1-7 이 *"단순 SHA-256 1회 해시는 부적절"* 이라 적었다).

    🚨 **역할은 `governor` 하나다** (D-66 — *"행동이 역할을 정한다"*). 역할을 늘리면
       「마케터라고 주장하는 사람이 진짜인가」라는 검증 문제가 생긴다.

    🔄 **`work_doc.owner_id` 는 이 테이블이 아니라 `UserAccount` 를 가리킨다** (D-260 ② · 0017).
       관리자 계정과 일반 사용자 계정은 **둘이다** — 세션 쿠키도 따로다(D-260 6-3 (가) · `auth.USER_SESSION_COOKIE`).
    """

    __tablename__ = "app_account"

    id: Mapped[uuid.UUID] = _pk()
    #: 🚨 `docs/<이니셜>/` 과 같은 철자다 — **명단의 정본은 디스크**다 (D-99 · `experiment.py` 와 같은 방식)
    initials: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(16), default="governor")
    pw_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 🚨 지우지 않고 **끈다** — 접속기록(고시 제8조)이 가리킬 행이 남아야 한다
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("role in ('governor')", name="ck_app_account_role"),
        # 🔴 PHC 접두어 강제 — 약한 해시가 들어오는 길을 **DB 가** 막는다 (D-220 · P1-7)
        CheckConstraint("pw_hash LIKE '$argon2id$%'", name="ck_app_account_phc"),
    )


#: 오류 로그가 받는 레벨. 🚨 표의 `CHECK` · 핸들러의 문턱 · 관리자 화면 필터가 이 한 벌을 쓴다 (D-99).
ERROR_LOG_LEVELS = ("WARNING", "ERROR", "CRITICAL")


class AppErrorLog(Base):
    """앱 오류 로그 — **WARNING 이상**만 · 🆕 2026-09-22 (ssm 요청 `docs/ssm/요청_2026-09-16_app_error_log.md` · 보안점검 P1-4).

    ★ 쓰는 곳은 하나 — `app/error_log.py` 의 백그라운드 기록기. 읽는 곳도 하나 — `/admin/errors`(관리자 에디션만 · D-213).

    🔴 **마스킹 필터(`RedactFilter`)를 지난 문장만** 들어온다 — 핸들러가 필터를 **직접** 단다(자식 로거 레코드는
       부모 로거의 필터를 안 지난다).
    🔴 **트레이스백 전문을 두지 않는다** — `exc_type`(클래스 이름)과 위치(`module`·`func_name`·`lineno`)만.
       트레이스백은 필터 밖이었다(P1-4 표 첫 줄). 요청 경로·쿼리스트링·사용자 이니셜·IP 도 두지 않는다 —
       뒤의 둘은 **접속기록**(P1-8 · 고시 제8조)이고 보관 기준이 다르다.
    🚨 **보관 90일** `[임의]` (`settings.ERROR_LOG_RETENTION_DAYS`) — 기록기가 뜰 때와 6시간마다 지난 행을 지운다.
    🚨 id 는 **DB 가** 만든다(`gen_random_uuid()`) — 기록기가 ORM 없이 psycopg 로 넣기 때문이다. 순차 정수는 안 쓴다(P1-5).
    """

    __tablename__ = "app_error_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    level: Mapped[str] = mapped_column(String(8))
    logger_name: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    exc_type: Mapped[str | None] = mapped_column(String(120))
    module: Mapped[str | None] = mapped_column(String(120))
    func_name: Mapped[str | None] = mapped_column(String(120))
    lineno: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "level in (" + ",".join(f"'{lv}'" for lv in ERROR_LOG_LEVELS) + ")",
            name="ck_app_error_log_level",
        ),
        # 🚨 상한은 **자르는 쪽**(기록기)과 **막는 쪽**(DB) 둘에 둔다 — 한쪽만 고치면 갈린다
        CheckConstraint(
            f"char_length(message) <= {ERROR_LOG_MESSAGE_MAX}", name="ck_app_error_log_message_len"
        ),
        Index("ix_app_error_log_occurred", occurred_at.desc()),
        Index("ix_app_error_log_level_occurred", "level", occurred_at.desc()),
    )


# ══════════════════════════════════════════════════════════════════════
#  운영 표 — D-260 (관리자 콘솔과 사용자 계정을 실제 데이터로 돌린다) · 마이그레이션 0017
#  🚨 만들지 않는 것 — `enterprise` · `signup_review` · `signup_review_doc` · 결제 (D-260 ④⑤⑥)
# ══════════════════════════════════════════════════════════════════════


class UserAccount(Base):
    """일반 사용자 계정 — 가입·로그인·마이페이지 · 관리자 회원 목록 (D-260 ② · D-66).

    ★ lse 안(`docs/lse/일반사용자_계정테이블_초안_2026-09-16.md`)을 뼈대로 psj `member` 를 합쳤다 — 같은 대상의 두 벌 금지 (D-99).
    🚨 **넣지 않는 칸** — 회원 유형·역할(D-66 「행동이 역할을 정한다」) · 채널·팔로워(D-68 · D-180) · 요금제(D-69) ·
       상태(`active`·`dormant` — `disabled_at`·`last_login_at` 에서 **계산**한다. 따로 두면 두 벌이다).
    🚨 **이메일은 소문자로 정규화해 저장한다** — `CHECK` 가 강제한다(대소문자만 다른 두 계정 방지).
    🚨 `email_verified_at` 은 **늘 NULL** 이다 — 인증 메일을 보내지 않는다(D-260 ⑧). 화면은 「미인증」.
    🚨 동의는 **시각**으로 둔다 — NULL = 미동의(기본). 선택 동의 ①②(D-96)는 기능의 대가가 아니다.
    🚨 지우지 않고 **끈다**(`disabled_at`) — `work_doc.owner_id` 가 가리킬 행이 남아야 한다.
    """

    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    pw_hash: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(40))
    #: 소속(자유 기재). 🚨 FK 아님 — `enterprise` 를 만들지 않는다(D-260 ④)
    org: Mapped[str | None] = mapped_column(String(60))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 동의한 약관 버전 문자열. 🚨 `terms` 에 FK 로 묶지 않는다 — 약관이 바뀌어도 **무엇에 동의했는지**가 남아야 한다
    terms_version: Mapped[str] = mapped_column(String(20))
    terms_agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: 「진단은 법적 확정 판단이 아니다」 동의 (필수)
    disclaimer_agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: D-96 선택 동의 ① 검수 이력 보관 · ② 품질 개선 활용. NULL = 미동의
    consent_history_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_improve_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("pw_hash LIKE '$argon2id$%'", name="ck_user_account_phc"),
        CheckConstraint("email = lower(email)", name="ck_user_account_email_lower"),
        CheckConstraint("position('@' in email) > 1", name="ck_user_account_email_at"),
    )


#: 공지 분류 — 🚨 표의 `CHECK` 와 화면이 이 한 벌을 쓴다 (D-99). 값은 저장 코드, 뜻은 화면 이름.
NOTICE_CATEGORIES = {"rule_change": "규정 변경", "system": "시스템", "update": "업데이트"}
#: 약관 종류 — 서비스 이용약관 · 개인정보 처리방침 · 진단 면책
TERMS_KINDS = {
    "service": "서비스 이용약관",
    "privacy": "개인정보 처리방침",
    "disclaimer": "진단 면책",
}
#: 문의 분류. 🚨 「결제」·「매칭」은 **없다** — 결제 없음(D-69) · 인플루언서 매칭은 범위 밖(D-68 · D-180)
TICKET_CATEGORIES = {"judge": "검수", "generate": "카피 생성", "account": "계정", "other": "기타"}
TICKET_PRIORITIES = {"urgent": "긴급", "normal": "보통", "low": "낮음"}
TICKET_STATUSES = {"open": "미처리", "in_progress": "처리중", "closed": "완료"}


def _in(col: str, values: dict[str, str]) -> str:
    """`CHECK (col in (…))` 조각 — 목록이 한 벌이게 (마이그레이션은 같은 값을 직접 적고 게이트가 맞댄다)."""
    return f"{col} in ({','.join(repr(v) for v in values)})"


class Notice(Base):
    """공지 (D-260 ①). 🚨 본문은 템플릿이 자동 이스케이프한다(`|safe` 금지 · `test_templates`).

    psj 안의 `status`(게시중·숨김)는 `hidden_at` 으로 — 상태를 시각으로 둔다. `author` 문자열 대신 계정 FK.
    """

    __tablename__ = "notice"

    id: Mapped[uuid.UUID] = _pk()
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_account.id"))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in("category", NOTICE_CATEGORIES), name="ck_notice_category"),
        CheckConstraint(
            "ends_on IS NULL OR starts_on IS NULL OR starts_on <= ends_on", name="ck_notice_period"
        ),
    )


class Terms(Base):
    """약관 버전 (D-260 ①). 🚨 **본문을 고치지 않는다 — 새 버전을 쌓는다.** 이미 동의한 사람이 무엇에 동의했는지가 남아야 한다.

    psj 안의 `status`(시행 중·예정·만료) · `prev_version` 은 두지 않는다 — `effective_on` 과 같은 `kind` 의 순서에서 계산된다.
    ⬜ 약관 **문구**는 법률 검토 대상이다(D-96) — 이 표는 그릇이다.
    """

    __tablename__ = "terms"

    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(20))
    effective_on: Mapped[date] = mapped_column(Date)
    body: Mapped[str] = mapped_column(Text)
    change_reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in("kind", TERMS_KINDS), name="ck_terms_kind"),
        Index("uq_terms_kind_version", "kind", "version", unique=True),
    )


class Ticket(Base):
    """문의 (D-260 ③ — 자유 텍스트를 받되 상한·보관 기한·안내문).

    🔴 **판정 원문을 붙이거나 판정 id 를 링크하는 칸이 없다** — 관리자가 문의를 통해 사용자 문구를 보는 길이 생기면
       D-76 열람 경계가 뚫린다. 화면은 「광고 문구 원문을 붙여 넣지 마세요」를 안내한다.
    🚨 로그인한 사용자만 접수한다(`requester_id` NOT NULL) — 비회원 문의는 연락처를 따로 받게 되어 범위 밖이다.
    🚨 닫히면 `expires_at = closed_at + TICKET_RETENTION_DAYS` — 파기 키다(D-129). `CHECK` 가 닫힘과 기한을 묶는다.
    표시 번호(`TK-…`)는 저장하지 않는다 — 화면이 `created_at` 으로 만든다.
    """

    __tablename__ = "ticket"

    id: Mapped[uuid.UUID] = _pk()
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id"), index=True
    )
    category: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(String(TICKET_TEXT_MAX))
    #: 관리자가 매긴다 — 사용자는 고르지 않는다
    priority: Mapped[str] = mapped_column(String(10), default="normal", server_default="normal")
    status: Mapped[str] = mapped_column(String(12), default="open", server_default="open")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_account.id")
    )
    #: 관리자 답변 — 한 번 답하는 모양(스레드는 범위 밖)
    reply: Mapped[str | None] = mapped_column(String(TICKET_TEXT_MAX))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        CheckConstraint(_in("category", TICKET_CATEGORIES), name="ck_ticket_category"),
        CheckConstraint(_in("priority", TICKET_PRIORITIES), name="ck_ticket_priority"),
        CheckConstraint(_in("status", TICKET_STATUSES), name="ck_ticket_status"),
        # 🔴 닫힌 문의는 파기 기한이 있다 — 「닫았는데 영원히 남는」 행을 DB 가 막는다 (D-129)
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_ticket_closed_expiry",
        ),
    )
