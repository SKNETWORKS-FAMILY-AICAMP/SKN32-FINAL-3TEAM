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
   ② `risk`           위험도 순서형 **R0~R3** (D-130 · D-227 개정) — `max()` 가 정의되는 전순서
   ③ `infeasibility`  불가 사유 A/B/C (D-59) — **주장의 성질**
   ④ `outcome`        종착 넷 (D-125) — **루프의 결과**
   ⛔ ①과 ②를 섞으면 D-09 래칫이 깨진다. 보류·근거없음은 서로 비교할 수 없어
      `max()` 가 정의되지 않는다. 화면 배지만 둘을 섞고 있었다 (상태 스키마 문서).
   ⛔ ③과 ④도 다른 축이다. A/B/C 는 왜 안 되는가, outcome 은 그래서 어떻게 끝났는가다.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field, model_validator

from app.settings import PARAMS

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
#  축 ② 위험도 — R0~R3 네 단계 (D-130 · D-227 개정) · D-09 래칫
# ══════════════════════════════════════════════════════════════════════


class Risk(enum.StrEnum):
    """R0(특이사항 없음) · R1(주의) · R2(업무정지 위험) · R3(영업 상실 위험).

    🔄 **D-227 — 척도는 네 단계다.** 경계는 전부 조문이 그었다 —
       R1 제14조(시정명령) · R2 제16조①③(정지 · 제19조 갈음 과징금 포함) · R3 제16조②④(취소·폐쇄).
       ⛔ D-130 의 「R3 = 과징금 위험」은 폐기됐다. 제19조가 과징금을 **영업정지에 갈음하여**
          부과하는 것으로 정하므로 둘은 **같은 단계**이고, 그것이 D-130 이 「R2·R3 순서 미확정」을
          남긴 원인이었다.

    🔴 **`R4` 는 ENUM 에 남아 있으나 이 설계에서 도달 불가다.** 형벌은 R 축에 얹지 않는다 —
       `penal_clause`(징역 n년 · 벌금 n원)가 그 자리다 (D-182). 되살리려면 **D-182 를 개정**하는
       결정이 선행해야 한다. ⛔ 「나중에 쓸 수도 있다」로 읽지 않는다 (D-21).
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


#: 통과(D-125)의 위험도 문턱 — **R1(주의)까지** (D-130 · D-227).
#: 🔄 2026-09-21 (소성민 코드 리뷰 #8) — 종전 값은 `PASS_RISK_MAX_PROVISIONAL = Risk.R2` 였다.
#:    D-130 은 *"통과 = 상태 == 확정 ∧ 위험도 ≤ **R1**"* 이라 적었고 표에서 **R1 = 주의가 확정**이다.
#:    미확정이었던 것은 **R2 ↔ R3 의 상대 순서**이지 「어느 것이 주의인가」가 아닌데, 종전 주석이 그렇게 읽고
#:    문턱을 **한 등급 느슨하게** 잡았다 — 「업무정지 위험」이 통과가 됐다. D-227 이 R2·R3 순서 문제를 없애며
#:    R1 로 고친다고 정했고, 이름의 「잠정(PROVISIONAL)」도 같이 뺀다.
#: ⛔ 종전에는 「코드 하한이 들어오는 커밋에서 같이 고친다」고 미뤘다. 부르는 곳이 0 이라 **지금 고쳐도 무해**하고,
#:    묶어 두면 그 커밋에서 잊는 쪽이 위험이다 — 하한이 서는 순간 틀린 문턱이 조용히 살아난다.
PASS_RISK_MAX = Risk.R1


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
    🔄 D-255 — `추천_보증_뒷광고` 는 후보가 아니라 **범위 밖**이다(문구로 판정할 수 없다 · 대가 표시 **누락**이 위반).
       `후기_체험기_기만` 은 **형식** 라벨이다 — 내용 라벨(`의약품_오인` 등)과 함께 붙을 수 있다.
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
    """근거 조문. **판정에는 반드시 붙는다** (D-224 · 기획서 5-8 원칙 ②).

    🚨 `quote` 는 인용이므로 `source_use.allowed` 가 `U3_cite` 인 것만 담는다.

    🔴 **제재 수치 필드를 두지 않는다 — 없는 것이 계약이다** (D-192).
       ⛔ 과징금·매출액·환산 금액을 여기에 담지 않는 것은 빠뜨린 것이 아니라 **판정**이다.
          D-182 — 제재 수치를 금액으로 환산하려면 **그 업체의 매출을 알아야 하는데, 모르고
          묻지도 않는다.** 모르는 수를 넣으면 화면이 그것을 아는 것처럼 보인다.
       ⛔ D-183 — 광고와 무관한 제재는 애초에 적재하지 않는다. 근거로 붙을 조문이 아니다.
       🚨 화면에 「예상 과징금」을 붙이려면 이 주석을 지우는 커밋이 필요하다. **그 커밋이 저항이다.**
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
        # D-224 — 위반을 확정했으면 근거 조문이 붙는다. 「근거 없음」은 별도 상태다
        if self.verdict is Verdict.confirmed and self.violations and not self.evidence:
            raise ValueError(
                "위반을 확정했는데 근거 조문이 없다 (D-224) — "
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

    🔴 **`category` 와 `has_recognized_function` 은 다른 축이다** (2026-09-16).
       `category` 는 **제품이 무엇인가**(어느 법·어느 별표 행을 타는가),
       `has_recognized_function` 은 **이 문구를 쓸 자격이 있는가**다.
       ⛔ 건기식인데 인정 범위를 넘겨 표방하면 `건기식 ∧ 자격 없음` 이다 — 한 필드로 못 담는다.
    """

    #: 🔴 **`None` 은 「미확정」이고 `일반` 은 「판별 결과 일반식품」이다** (2026-09-16 · D-72).
    #:    ⛔ 종전 기본값이 `Category.일반` 이라 **「안 줬다」와 「일반이라고 줬다」가 같은 값**이었다.
    #:       없음이 성공으로 집계되는 자리였다.
    #:    🚨 미확정이면 `classify` 가 판별하고, **못 정하면 `hold(cat_unknown)`** 으로 간다
    #:       (D-127 의 사유코드 — 그 괄호가 「**D-61 분기 병렬 출력**」이라고 적어 두었다).
    #:    ⛔ **`max` 로 접지 않는다.** 접으면 분기가 사라진다 — `max` 는 **축 자체가 없어서 물어볼
    #:       수도 없는 것**(업종: 제조·판매·음식점)에만 쓴다 (D-227).
    category: Category | None = None
    #: 자격 축. 🔜 **기능성표시식품**(별표1 3호나목 단서 · 고시)은 여기도 `category` 도 아니다 —
    #:   **D-61 분기로 낸다.** 「본 제품은 건강기능식품이 아닙니다」는 고시 제6조①5호의 **의무 표시**
    #:   이지 자격이 아니다(함량 30% · 안전관리인증업소 제조가 요건) — D-228 의 특허와 같은 어법.
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
    text: str = Field(..., min_length=1, max_length=PARAMS.max_text_len)
    product: ProductContext = Field(default_factory=ProductContext)


class JudgeResponse(BaseModel):
    outcome: Outcome
    sentences: list[SentenceJudgment] = Field(default_factory=list)
    #: `outcome=pass` 일 때만 채운다 (D-31 · D-34)
    candidates: list[Candidate] = Field(default_factory=list)
    #: `outcome=certificate` 일 때만 (D-32 · D-125)
    certificate: Certificate | None = None
    #: 🔴 **0-base.** 총 라운드 K+1=3 이므로 0·1·2 만 (D-126 · ck_judgment_attempt)
    attempt: int = Field(0, ge=0, le=PARAMS.max_attempt)
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
    """D-125 통과 조건 — 확정 ∧ 위험도 ≤ 주의(R1) (D-130 · D-227 · `PASS_RISK_MAX`).

    🚨 위험도가 없으면(`final is None`) 통과가 아니다 — 없음을 통과로 세지 않는다 (D-72).
    """
    if s.verdict is not Verdict.confirmed:
        return False
    if s.risk.final is None:
        return False
    return s.risk.final.level <= PASS_RISK_MAX.level


# ══════════════════════════════════════════════════════════════════════
#  진입점 B — 카피 생성 (D-181 · 프로토타입 v7.2 `gen-input` → `gen-result`)
# ══════════════════════════════════════════════════════════════════════
#
# 🚨 **판정 코어는 하나다** (D-119). B 가 만든 문구도 위의 `SentenceJudgment` 를 지난다.
#    아래 모델은 **생성의 입출력**이지 두 번째 판정기가 아니다.


class Channel(enum.StrEnum):
    """출력 프로파일 4종 (D-93). 🚨 뒤 둘은 **설계만** — 10주 안에 구현하지 않는다."""

    상세페이지 = "상세페이지"
    인스타 = "인스타"
    기사형 = "기사형"  # 🚨 「광고」 표시 구조적 강제가 특히 중요한 자리
    유튜브 = "유튜브"  # 스크립트·자막 (영상 아님)


class MediaProfile(BaseModel):
    """매체 프로파일 — **바꾸는 것이 넷뿐이다** (D-93 표).

    🔴 **이 모델에 판정 기준·허용 어휘·근거 조문 필드를 두지 않는다.** 없는 것이 계약이다 —
       필드가 없으면 프로파일이 그것을 바꿀 방법이 구조적으로 없다.
    ⛔ 「플랫폼마다 규정이 다르다」는 D-93 이 **기각한 착각**이다. 표시 의무의 *내용* 은
       매체와 무관하게 같고, 갈리는 것은 표시의 *방법* 뿐이다.
    🔄 프로파일이 적용되는 자리는 C 가 아니라 **B 의 후단**이다 (D-181 · 화면 「채널별 각색」).
    """

    channel: Channel
    max_chars: int | None = Field(None, ge=1)  # 길이
    max_sentences: int | None = Field(None, ge=1)  # 문장 수
    tone: str | None = None  # 문체
    #: 표시 문구 배치 — 🚨 코드가 **먼저** 넣는다. sLLM 은 본문만 다시 쓴다 (D-93 · D-181)
    disclosure_placement: str


class Segment(BaseModel):
    """대상고객 (프로토타입 `segments` · 「비슷한 리뷰 214건에서 모인 고객군」).

    🚨 `member_count >= 20` 은 DB `ck_segment_k_anon` 과 **같은 규칙**이다 (K-익명).

    🔴 **인플루언서·계정·개인 식별 필드를 두지 않는다 — 없는 것이 계약이다** (D-192).
       ⛔ D-180 — 인플루언서 매칭은 **범위 밖**이다. 「이 세그먼트에 맞는 계정」은
          고객군이 아니라 **사람의 명단**이고, 그 순간 이 모델은 K-익명을 지킬 수 없다.
       🚨 `top_terms` 는 어휘이지 사람이 아니다. 여기에 handle·URL·팔로워 수가 들어오면
          `member_count >= 20` 이 지키던 것이 무너진다 — **검증기가 아니라 부재가 막고 있다.**
    """

    segment_id: str
    label: str
    member_count: int = Field(..., ge=PARAMS.k_anon_min)
    vulnerable_flag: bool = False
    top_terms: list[str] = Field(default_factory=list)


class KeywordScreen(BaseModel):
    """지향 키워드 선별 — 허용/차단 **+ 사유** (상태 스키마 「진입점 B」).

    화면 문안: 「회색은 판정 코어가 막은 키워드라 고를 수 없어요.
    차단된 키워드를 누르면 **사유를 볼 수 있어요**」
    ⛔ 사유 없는 차단은 사용자에게 「왜 안 되는지 모르는 회색」이 된다 — 그건 판정이 아니다.
    """

    term: str
    allowed: bool
    reason: str | None = None
    evidence: list[EvidenceArticle] = Field(default_factory=list)

    @model_validator(mode="after")
    def _blocked_needs_reason(self) -> KeywordScreen:
        if not self.allowed and not self.reason:
            raise ValueError(f"차단한 키워드에는 사유가 붙는다 — {self.term!r}")
        return self


class GenerateRequest(BaseModel):
    """B 입력 — 세그먼트 + 키워드 + 제품 컨텍스트 (+ 매체 프로파일은 선택)."""

    segment: Segment
    keywords: list[KeywordScreen] = Field(default_factory=list)
    product: ProductContext = Field(default_factory=ProductContext)
    #: 비우면 각색 없이 후보만 낸다 — 각색은 B 의 **후단**이다 (D-181)
    profile: MediaProfile | None = None

    @model_validator(mode="after")
    def _no_blocked_keywords(self) -> GenerateRequest:
        bad = [k.term for k in self.keywords if not k.allowed]
        if bad:
            raise ValueError(
                f"차단된 키워드를 생성 입력에 넣지 않는다 — {bad} "
                "(화면에서 회색이라 고를 수 없는 것들이다)"
            )
        return self


class GenerateResponse(BaseModel):
    """B 출력 — 프론티어 (D-31 · D-34 N=3).

    🚨 화면이 축의 뜻을 이미 적어 뒀다 — y 축은 **전환율이나 판매 성과가 아니라**
       원문 대비 정보량 보존율이다. 지어낸 성과 지표를 여기 담지 않는다.
    """

    candidates: list[Candidate] = Field(default_factory=list)
    keywords: list[KeywordScreen] = Field(default_factory=list)
    #: 각색본 — 프로파일이 주어졌을 때만. 🚨 각 결과가 **판정 코어를 다시 지난다** (D-119)
    adapted: list[AdaptedCopy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pareto_only(self) -> GenerateResponse:
        # 화면 문안: 「파레토 최적 3안만 표시 — 지배당하는 후보는 자동 제외돼요」
        if any(not c.pareto for c in self.candidates):
            raise ValueError("지배당하는 후보는 프론티어에 올리지 않는다 (D-31)")
        return self


class AdaptedCopy(BaseModel):
    """채널별 각색 결과 (D-181 · 화면 「채널별 각색」).

    화면 문안이 이 모델의 계약이다 —
      > 코드가 매체별 표시 위치에 광고 표시 문구를 **먼저** 넣고, sLLM이 본문만 매체 형식에
      > 맞게 다시 쓴 뒤, 판정 코어가 각 결과를 **다시 검증**해요.

    🔴 그래서 세 필드가 전부 필수다 — 표시 문구 · 배치 · 재검증 결과.
    """

    channel: Channel
    rewrite: RewriteSet
    #: 🚨 **「광고」 표시 없는 출력 경로를 만들지 않는다** (D-93 방어 · D-164)
    disclosure: str = Field(..., min_length=1)
    disclosure_placement: str = Field(..., min_length=1)
    #: 재검증 결과. ⛔ 비면 D-63 「재검증 대기로는 템플릿에 쓰이지 않는다」가 무너진다
    recheck: SentenceJudgment


# ══════════════════════════════════════════════════════════════════════
#  진입점 C — AI 광고 생성 (D-164 · 프로토타입 `draft-setup` → `draft-editor`)
# ══════════════════════════════════════════════════════════════════════
#
# 🔄 **C 는 진입점이면서 종착이다** (D-181). B 에서 각색된 문구를 받아 지면에 얹고,
#    동시에 **독립 진입**도 받는다 — 종류 선택 → 내용 입력 → 판정 → 템플릿.
# 🚨 D-93 이 경계한 것 — 「우리가 템플릿을 제공하면 **위장 광고 생성 도구로 읽힌다**」.
#    답은 「템플릿이 「광고」 표시를 **구조적으로 강제**하고, 표시 없는 출력 경로를
#    만들지 않는다」였다. 아래 검증기가 그 약속을 코드로 만든다.


class AdFormat(enum.StrEnum):
    """01 · 어떤 종류로 만들까요 (프로토타입 `draft-setup`)."""

    상세페이지 = "상세페이지"
    카드뉴스 = "카드뉴스"
    배너 = "배너"


class AdSection(BaseModel):
    """섹션 골격 한 칸. 🚨 「규격 · 여백 · 글자 크기는 KRDS 표준형 스타일 기준」(화면)."""

    order: int = Field(..., ge=0)
    kind: str  # 헤드라인 / 본문 / 이미지 / 표시문구 …
    text: str | None = None
    #: 이미지·문구는 섹션별로 사용자가 직접 채운다 — 비어 있는 것이 정상이다
    placeholder: str | None = None


class ComposeRequest(BaseModel):
    """C 입력 — 두 경로가 한 모델로 들어온다.

    ① B 에서 넘어옴 — `source_copy` 에 **판정을 지난** 문구가 담긴다
    ② 독립 진입     — `prompt` 에 사용자가 적은 내용. 「판정 코어가 입력한 내용을 먼저 걸러요」
    """

    ad_format: AdFormat
    #: ① B 에서 넘어온 각색본
    source_copy: AdaptedCopy | None = None
    #: ② 「담고 싶은 내용을 적어주세요. 적은 내용에 맞춰 섹션 구성과 문구가 달라져요」
    prompt: str | None = Field(None, max_length=PARAMS.max_text_len)
    product: ProductContext = Field(default_factory=ProductContext)

    @model_validator(mode="after")
    def _one_of_two_paths(self) -> ComposeRequest:
        if (self.source_copy is None) == (self.prompt is None):
            raise ValueError(
                "C 는 두 경로 중 하나로 들어온다 — B 의 각색본(source_copy) 또는 "
                "직접 입력(prompt). 둘 다이거나 둘 다 없으면 어느 쪽인지 정해지지 않는다"
            )
        return self


class ComposeResponse(BaseModel):
    """C 출력 — 지면에 얹힌 광고.

    🔴 **불변식 셋을 계약이 지킨다** —
       ① 「광고」 표시 섹션이 반드시 있다 (D-93 · D-164 — 표시 없는 출력 경로가 없다)
       ② 판정을 지나지 않은 문구는 얹히지 않는다 (D-63 · D-119)
       ③ 재검증이 `confirmed` 가 아니면 배치하지 않는다 (D-63 「재검증 대기」)
    """

    ad_format: AdFormat
    sections: list[AdSection] = Field(default_factory=list)
    #: 입력을 거른 판정 — 두 경로 모두 코어를 지난다 (D-119)
    screening: list[SentenceJudgment] = Field(default_factory=list)
    #: 🚨 구조적 강제 — 비면 거부한다
    disclosure_section_order: int | None = None

    @model_validator(mode="after")
    def _disclosure_is_structural(self) -> ComposeResponse:
        if self.disclosure_section_order is None:
            raise ValueError(
                "「광고」 표시 섹션이 없다 — 표시 없는 출력 경로를 만들지 않는다 (D-93 · D-164)"
            )
        if not any(s.order == self.disclosure_section_order for s in self.sections):
            raise ValueError(
                f"표시 섹션 자리({self.disclosure_section_order})가 섹션 목록에 없다 — "
                "번호만 적고 칸을 안 만들면 표시가 안 나간다"
            )
        return self

    @model_validator(mode="after")
    def _only_confirmed_copy_lands(self) -> ComposeResponse:
        # D-63 — 재검증 대기 상태로는 템플릿에 사용되지 않는다
        pending = [s.sent_id for s in self.screening if s.verdict is not Verdict.confirmed]
        if pending and any(s.text for s in self.sections):
            raise ValueError(
                f"판정이 확정되지 않은 문장이 있는데 섹션에 문구가 얹혔다 — {pending} "
                "(D-63 재검증 대기로는 템플릿에 쓰이지 않는다)"
            )
        return self
