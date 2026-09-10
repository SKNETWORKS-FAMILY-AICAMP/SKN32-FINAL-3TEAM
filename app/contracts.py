"""app/contracts.py — 판정 코어의 **출력 계약** (D-124).

  from app.contracts import JudgeResponse, Verdict, Outcome

🚨 **팀원 4인이 기다리는 것은 구현이 아니라 계약이다** (D-124). 판정 엔진이 없어도
   이 파일 하나면 화면·BFF 가 모든 분기를 그릴 수 있다. FastAPI 가 여기서 OpenAPI 를
   자동 생성하므로 **스켈레톤이 곧 목 서버**다.

🔴 **여기서 새로 정하는 것은 없다.** 모든 필드가 결정문에서 온 것이고, 필드마다 출처를
   적어 뒀다. 결정에 없는 축을 여기서 만들면 계약이 아니라 추측이 된다.

🔴 **enum 값의 단일 출처는 `db/schema.sql` 이다** (D-54). 아래 값들은 그 파일의
   `violation_t` · `risk_t` · `infeas_t` 와 `app/models.py` 의 CHECK 에서 옮겼다.
   ⛔ 여기서만 값을 늘리면 계약은 받아 주고 DB 가 거부한다 — 가장 늦게 터지는 자리다.
   게이트 `test_계약의_enum_이_DB_와_같다` 가 둘의 일치를 본다.

★ **축을 넷으로 나눠 갖는다. 섞지 않는다** —
   ① `verdict`        판정 상태 (D-127) — 그래프가 정한다
   ② `risk`           위험도 5값 순서형 (D-130) — `max()` 가 정의되는 전순서
   ③ `infeasibility`  불가 사유 A/B/C (D-59) — **주장의 성질**
   ④ `outcome`        종착 넷 (D-125) — **루프의 결과**
   ⛔ ①과 ②를 섞으면 D-09 래칫이 깨진다. 보류·근거없음은 서로 비교할 수 없어
      `max()` 가 정의되지 않는다. 화면 배지만 둘을 섞고 있었다 (상태 스키마 문서).
   ⛔ ③과 ④도 다른 축이다. A/B/C 는 왜 안 되는가, outcome 은 그래서 어떻게 끝났는가다.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field, model_validator

# ══════════════════════════════════════════════════════════════════════
#  축 ① 판정 상태 — D-127 · `app/models.py` ck_judgment_verdict
# ══════════════════════════════════════════════════════════════════════


class Verdict(enum.StrEnum):
    """🚨 「근거 불일치」는 여기 없다 — 상태가 아니라 **재생성 이벤트**다 (D-127)."""

    confirmed = "confirmed"  # 확정
    hold = "hold"  # 보류 — hold_reason 필수
    no_basis = "no_basis"  # 근거 없음 — 위험도·유형은 유지
    unjudged = "unjudged"  # 미판정 (오류·타임아웃) — 🚨 통과로 집계 금지


class HoldReason(enum.StrEnum):
    """`hold` 일 때만. `app/models.py` ck_judgment_hold_reason_values 와 같은 넷."""

    low_conf = "low_conf"  # 확신 부족
    gap2 = "gap2"  # 1·2위 격차 부족
    cat_unknown = "cat_unknown"  # 카테고리 판별 실패 (D-82)
    rd1 = "rd1"  # 라운드 1 미해소


# ══════════════════════════════════════════════════════════════════════
#  축 ② 위험도 — D-130 5값 순서형 · D-09 래칫
# ══════════════════════════════════════════════════════════════════════


class Risk(enum.StrEnum):
    """R0(특이사항 없음) ~ R4(형사 위험).

    🚨 **R2·R3 의 순서는 검증 ② 에서 확정한다** (`app/models.py` D-130 주석).
       값의 개수와 이름은 고정이고, 그 둘의 상대 순서만 열려 있다.
    """

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"

    @property
    def level(self) -> int:
        """순서형 비교를 위한 정수. `max()` 는 이 축 위에서만 정의된다 (D-09)."""
        return int(self.value[1])


#: 🚨 **잠정값이다.** D-125 의 통과 조건이 「위험도 ≤ 주의」인데, 다섯 값 중 어느 것이
#:    「주의」인지는 검증 ② 가 R2·R3 순서를 정한 뒤에 확정된다 (D-130).
#:    ⛔ 그때까지 이 상수를 판정 로직의 근거로 삼지 않는다 — 화면 표기에만 쓴다.
PASS_RISK_MAX_PROVISIONAL = Risk.R2


# ══════════════════════════════════════════════════════════════════════
#  축 ③ 불가 사유 — D-59
# ══════════════════════════════════════════════════════════════════════


class Infeasibility(enum.StrEnum):
    """왜 합법화가 안 되는가. **주장의 성질**이지 루프의 결과가 아니다.

    🚨 사유별로 대체 문구 정책이 갈린다 (D-59) —
       A 는 **제안 금지**(표현이 아니라 자격의 문제라 재생성이 같은 위반을 반복한다)
       B 는 조건부 제안 · C 는 제안 없음.
    ⛔ 이 구분이 없어서 기획서 2-3 시나리오 A 가 자격 미충족 문구를 고쳐 놓고
       「재판정 통과」로 적었다 — 대표 데모가 우리 미탐을 시연하고 있었다.
    """

    A = "A"  # 자격형 — 인정 기능성이 없다
    B = "B"  # 실증형 — 근거를 대면 된다
    C = "C"  # 절대형 — 표현 자체가 금지


# ══════════════════════════════════════════════════════════════════════
#  축 ④ 종착 — D-125
# ══════════════════════════════════════════════════════════════════════


class Outcome(enum.StrEnum):
    """**통과 = `confirmed` ∧ 위험도 ≤ 주의.** 보류·근거없음·미판정은 통과가 아니다."""

    passed = "pass"  # 프론티어 / 3종 세트
    certificate = "certificate"  # A·C — 판정 직후, 루프 미진입 (D-32)
    search_failed = "search_failed"  # B 가 K 소진 — 원문 유지 + 실증 자료 안내
    hold = "hold"  # 전문가 검토


class Violation(enum.StrEnum):
    """`db/schema.sql` 의 `violation_t` 와 같아야 한다 (D-54).

    🔴 뒤 다섯은 **편입 후보**다 (D-65) — 인코더가 예측하는 확정 클래스는
       `scripts/collect.py` 의 `VIOLATION_TYPES` 6종이고 승격 판정일은 2026-09-17 이다.
    """

    질병_예방치료_표방 = "질병_예방치료_표방"
    건강기능식품_오인 = "건강기능식품_오인"
    의약품_오인 = "의약품_오인"
    거짓_과장 = "거짓_과장"
    소비자_기만 = "소비자_기만"
    후기_체험기_기만 = "후기_체험기_기만"
    추천_보증_뒷광고 = "추천_보증_뒷광고"
    부당_비교광고 = "부당_비교광고"
    비방광고 = "비방광고"
    실증책임_위반 = "실증책임_위반"
    기능성화장품_오인 = "기능성화장품_오인"


class Category(enum.StrEnum):
    """🚨 사용자에게 묻지 않는다 — 우리가 판별한다 (D-82). 판정 결과에 속한다."""

    일반 = "일반"
    식품 = "식품"
    건기식 = "건기식"
    화장품 = "화장품"


# ══════════════════════════════════════════════════════════════════════
#  조각
# ══════════════════════════════════════════════════════════════════════


class Span(BaseModel):
    """원문 좌표. **raw 기준**이다 (D-131 · D-30 주장 BIO).

    ⛔ 정규화문 좌표를 넣으면 화면에서 엉뚱한 글자에 밑줄이 그어진다.
    """

    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    label: str | None = None

    @model_validator(mode="after")
    def _order(self) -> Span:
        if self.end <= self.start:
            raise ValueError("span 은 end > start 여야 한다")
        return self


class EvidenceArticle(BaseModel):
    """근거 조문. **판정에는 반드시 붙는다** (D-100 · 기획서 5-8 원칙 ②).

    🚨 `quote` 는 인용이므로 `source_use.allowed` 가 `U3_cite` 인 것만 담는다.
    """

    law_id: str
    article: str
    item: str = ""
    quote: str | None = None
    chunk_id: str | None = None


class RiskAssessment(BaseModel):
    """D-09 래칫 — `final = max(코드 하한, 인코더 예측)`.

    🚨 **인코더는 내릴 수 없다.** 코드가 보류면 인코더가 못 뒤집는다(단조 규칙).
    🔴 상향(`final > floor`)에는 `evidence_span` 이 반드시 붙는다 (D-131).
       ⛔ 이 규칙이 DB 에서는 널로 우회되고 있었다 — 마이그레이션 0006 이 막았다.
          계약도 같은 조건을 건다. 두 곳이 다르면 늦게 터진다.
    """

    floor: Risk | None = None  # 코드 하한 (D-84 ③)
    encoder: Risk | None = None  # 인코더 예측
    final: Risk | None = None
    evidence_span: Span | None = None

    @model_validator(mode="after")
    def _ratchet(self) -> RiskAssessment:
        if self.final is None:
            return self
        if self.floor is None:
            raise ValueError(
                "최종 위험도를 적으려면 코드 하한이 있어야 한다 — "
                "상향의 정의가 「하한보다 높다」인데 하한이 없으면 상향이 정의되지 않는다 (D-09)"
            )
        if self.final.level > self.floor.level and self.evidence_span is None:
            raise ValueError(
                "하한 위로 올리려면 근거 스팬이 필요하다 (D-131) — "
                f"floor={self.floor.value} final={self.final.value}"
            )
        return self


class SentenceJudgment(BaseModel):
    """문장 하나의 판정. 상태 스키마 「판정 누적」이 그대로 이 모양이다."""

    sent_id: str
    text: str
    verdict: Verdict
    hold_reason: HoldReason | None = None
    violations: list[Violation] = Field(default_factory=list)
    infeasibility: Infeasibility | None = None
    evidence: list[EvidenceArticle] = Field(default_factory=list)
    risk: RiskAssessment = Field(default_factory=RiskAssessment)
    #: 🔄 근거 불일치는 상태가 아니라 **재생성 이벤트**다 (D-127)
    evidence_mismatch: bool = False

    @model_validator(mode="after")
    def _hold_reason_iff_hold(self) -> SentenceJudgment:
        # `app/models.py` ck_judgment_hold_reason 과 **같은 규칙**이다
        if (self.verdict is Verdict.hold) != (self.hold_reason is not None):
            raise ValueError("hold 일 때만, 그리고 hold 이면 반드시 hold_reason 이 있다 (D-127)")
        return self

    @model_validator(mode="after")
    def _confirmed_needs_evidence(self) -> SentenceJudgment:
        # D-100 — 위반을 확정했으면 근거 조문이 붙는다. 「근거 없음」은 별도 상태다
        if self.verdict is Verdict.confirmed and self.violations and not self.evidence:
            raise ValueError(
                "위반을 확정했는데 근거 조문이 없다 (D-100) — "
                "근거를 못 찾은 경우의 상태는 `no_basis` 다"
            )
        return self


class RewriteSet(BaseModel):
    """출력은 **3종 세트**다 (D-33) — 의결서 시정 형태가 정확히 이것이다."""

    body: str  # 본문
    mandatory_note: str | None = None  # 필수 병기 문구
    placement: str | None = None  # 배치 지시


class Candidate(BaseModel):
    """리스크–소구력 프론티어의 한 점 (D-31). 단일 답을 주지 않는다.

    🚨 N=3 · K=2 (D-34) — 보수안 / 균형안 / 공격안.
    """

    label: str
    rewrite: RewriteSet
    residual_risk: Risk
    appeal_retention: float = Field(..., ge=0.0, le=1.0)
    pareto: bool = True


class Certificate(BaseModel):
    """합법화 불가 증명서 (D-32). **A 자격형 · C 절대형에만 낸다** (D-125).

    ⛔ B 실증형이 K 를 소진한 경우에 이것을 내면 D-59 가 금지한
       「B 를 C 처럼 답하기」가 된다. 그때는 `outcome=search_failed` 다.
    """

    reason: Infeasibility
    explanation: str
    #: A 는 자격 취득 경로, C 는 없음. 🚨 특허·수상·논문은 표방 자격이 아니다 (D-59)
    guidance: str | None = None


class ProductContext(BaseModel):
    """🚨 **인정 기능성 보유 여부가 반드시 들어간다** (D-59 · 상태 스키마).

    같은 문구가 카테고리·자격에 따라 적법과 위법으로 갈린다.
    """

    category: Category = Category.일반
    has_recognized_function: bool = False
    recognition_no: str | None = None


class Timing(BaseModel):
    """노드별 소요 (D-77 ⑥ · 상태 스키마 「계측」).

    🚨 D-43 이 LangSmith·W&B 를 배제했으므로 **이 필드가 유일한 계측 경로다.**
       나중에 붙이면 그때까지의 측정치가 없다 — walking skeleton 에서 같이 넣는다.
    """

    node: str
    ms: float = Field(..., ge=0)


# ══════════════════════════════════════════════════════════════════════
#  요청 · 응답
# ══════════════════════════════════════════════════════════════════════


class JudgeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    product: ProductContext = Field(default_factory=ProductContext)


class JudgeResponse(BaseModel):
    outcome: Outcome
    sentences: list[SentenceJudgment] = Field(default_factory=list)
    #: `outcome=pass` 일 때만 채운다 (D-31 · D-34)
    candidates: list[Candidate] = Field(default_factory=list)
    #: `outcome=certificate` 일 때만 (D-32 · D-125)
    certificate: Certificate | None = None
    #: 🔴 **0-base.** 총 라운드 K+1=3 이므로 0·1·2 만 (D-126 · ck_judgment_attempt)
    attempt: int = Field(0, ge=0, le=2)
    timings: list[Timing] = Field(default_factory=list)
    #: 🚨 개정되면 「재검증 대기」의 판단 근거가 된다 (D-103 ③)
    law_version: str = "unknown"
    judged_by: str = "unknown"  # 코드/모델 버전

    @model_validator(mode="after")
    def _outcome_matches_payload(self) -> JudgeResponse:
        if self.outcome is Outcome.certificate:
            if self.certificate is None:
                raise ValueError("outcome=certificate 인데 증명서가 없다 (D-32)")
            if self.certificate.reason is Infeasibility.B:
                raise ValueError(
                    "B 실증형에는 증명서를 내지 않는다 — outcome=search_failed 다 (D-59 · D-125)"
                )
            if self.candidates:
                raise ValueError("증명서를 내면서 대체 문구를 함께 내지 않는다 (D-59)")
        if self.outcome is Outcome.search_failed and self.certificate is not None:
            raise ValueError("B 가 K 를 소진한 것은 「표현 탐색 실패」다 — 증명서가 아니다 (D-125)")
        if self.outcome is not Outcome.passed and self.candidates:
            raise ValueError("프론티어는 통과했을 때만 낸다 (D-125)")
        return self

    @model_validator(mode="after")
    def _no_candidates_for_qualification(self) -> JudgeResponse:
        # D-59 — A 자격형은 대체 문구 생성 노드로 보내지 않는다
        if self.candidates and any(s.infeasibility is Infeasibility.A for s in self.sentences):
            raise ValueError(
                "A 자격형 문장이 있는데 대체 문구를 냈다 (D-59) — "
                "표현이 아니라 자격의 문제라 재생성이 같은 위반을 반복한다"
            )
        return self


def is_pass(s: SentenceJudgment) -> bool:
    """D-125 통과 조건 — 확정 ∧ 위험도 ≤ 주의.

    🚨 임계값이 **잠정**이다 (`PASS_RISK_MAX_PROVISIONAL`). 검증 ② 가 R2·R3 순서를
       정하기 전까지 이 함수를 판정 로직의 근거로 삼지 않는다.
    """
    if s.verdict is not Verdict.confirmed:
        return False
    if s.risk.final is None:
        return False
    return s.risk.final.level <= PASS_RISK_MAX_PROVISIONAL.level
