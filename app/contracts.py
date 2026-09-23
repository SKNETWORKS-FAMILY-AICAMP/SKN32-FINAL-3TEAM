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
   ④ `outcome`        종착 — 🔄 **진입점마다 목록이 다르다** (D-274) — 검수 `Outcome` 넷 · 생성 `GenerateOutcome` 셋
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
    """`hold` 일 때만. `app/models.py` ck_judgment_hold_reason_values 와 **같은 여섯** (마이그레이션 0018).

    🔄 2026-09-23 — `premise_unknown` · `law_uncovered` 를 더했다 (D-263 ② · D-277).
       `cat_unknown` 은 **품목을 못 가림**, `premise_unknown` 은 **품목은 가렸으나 인정 여부로 등급이 갈림**이다.
    """

    low_conf = "low_conf"  # 확신 부족 — 조건 M(맥락)도 여기로 (D-268)
    #: 🔄 2026-09-23 — 원장 D-127 의 뜻은 **코드 하한 ↔ 모델 예측 2등급 차**(3-5 ③)다.
    #:    ⛔ 종전 주석 「1·2위 격차 부족」은 원장과 달랐다 — 화면 라벨·`KNOWN_GAPS` 에도 같은 오기가 번졌다.
    gap2 = "gap2"  # 코드↔모델 2등급 차
    cat_unknown = "cat_unknown"  # 카테고리 판별 실패 (D-82)
    rd1 = "rd1"  # 공존 규칙 발동 (D-127 · D-120) — 🔄 09-21 종전 주석 「라운드 1 미해소」는 D-127 과 달랐다
    premise_unknown = (
        "premise_unknown"  # 품목은 가렸으나 인정 여부로 등급이 갈림 — 분기를 낸다 (D-263 ② · D-276)
    )
    #: 전용법 품목(의료기기 · 의약외품 등)에서 표시광고법으로 걸린 것이 없는 문장 — 안 본 법이 있다 (D-271 ⑤ · D-277)
    law_uncovered = "law_uncovered"


# ══════════════════════════════════════════════════════════════════════
#  축 ② 위험도 — R0~R3 네 단계 (D-130 · D-227 개정) · D-09 래칫
# ══════════════════════════════════════════════════════════════════════


class Risk(enum.StrEnum):
    """R0(특이사항 없음) · R1(시정명령 위험) · R2(업무정지 위험) · R3(영업 상실 위험).

    🔄 **D-280 — R1 의 이름은 「시정명령 위험」이다.** 옛 이름 「주의」는 D-130 의 옛 뜻(실증·맥락으로 갈림)에서 왔고,
       그 문장들은 분기 · 지시 · 보류로 옮겨 갔다 (D-263 · D-268). 네 단계 이름이 모두 그 등급을 만든 처분이다.

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


#: 통과의 위험도 문턱 — 🔄 **R0** (D-273). 통과 = **확정 ∧ R0** = 확정 ∧ 위반 없음.
#: ⛔ 종전 값 R1 은 D-130 의 옛 R1(「실증 자료가 필요하거나 맥락에 따라 갈림」 — 조건을 달면 쓸 수 있음)에 맞춘 문턱이었다.
#:    D-227 이 R1 에 **시정명령 수준의 확정 위반**을 얹은 뒤로는 그 문턱이 확정 위반을 통과로 흘렸다 —
#:    표시광고법은 구조적으로 R1 이 상한이라(D-272) 일반상품 광고의 확정 위반이 전부 통과였다.
#: 🚨 홈 화면 집계(`app/routers/user.py`)가 이 상수를 그대로 쓴다 — 고치면 그쪽 수의 뜻도 같이 바뀐다.
PASS_RISK_MAX = Risk.R0


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
    """**검수(진입점 A)의 종착** — 🔄 D-274 · D-268. **통과 = 확정 ∧ R0** (D-273).

    우선순위 **보류 > 증명서 > 지시 > 통과**. 보류·근거없음·미판정은 통과가 아니다.
    ⛔ `search_failed` 는 여기 없다 — 검수는 재생성 루프를 돌지 않는다 (D-265). 생성 종착(`GenerateOutcome`)의 것이다.
    """

    passed = "pass"  # 통과 — 🔄 검수는 프론티어를 내지 않는다 (D-265)
    certificate = "certificate"  # A·C — 합법화 불가 증명서 (D-32)
    #: 확정된 **B 실증형** 위반 — 뺄 구간 · 필요한 실증 자료 종류 · 실증하면 내려갈 수 있는 등급 (D-268)
    guidance = "guidance"
    hold = "hold"  # 전문가 검토


class GenerateOutcome(enum.StrEnum):
    """**생성(진입점 B)의 종착** — 🆕 D-274. 검수 종착과 목록이 다르다."""

    frontier = "frontier"  # 프론티어 — 자기 전제로 재판정한 후보 (D-31 · D-264)
    search_failed = "search_failed"  # B 가 K 소진 — 원문 유지 + 실증 자료 안내 (D-125 · D-126)
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
    """**품목 축** — 제품이 무엇인가 (D-271 ④). 판정 결과에 속한다 (D-82).

    🔄 **D-271 — 「일반」은 없다.** 「일반」이 품목(일반 상품) · 판별 결과(일반식품) · 청크의 「분류 못 함」 세 뜻을 지고 있었다.
       `식품` 이 일반식품을 포함한다 · `일반상품` 은 **표시광고법만** 탄다 · `전용법_미수록` 은 우리가 안 가진 법이 걸린다.
    🔄 **D-276 — 첫 검수는 묻지 않고 판별한다. 재검수 때는 늘 묻는다**(판별 결과를 기본 선택으로).
    ⛔ 법 축(`표시광고법` · `식품표시광고법` · `화장품법`)과 섞지 않는다 — 청크의 법은 법 ID 로 정한다 (D-271 ①).
    """

    식품 = "식품"
    건기식 = "건기식"
    화장품 = "화장품"
    일반상품 = "일반상품"
    #: 의료기기 · 의약외품 · 의약품 · 의료 서비스 등 — 🚨 **통과를 내지 않는다** · 「○○법 미검수」 고지 (D-271 ⑤ · D-277)
    전용법_미수록 = "전용법_미수록"


class Premise(enum.StrEnum):
    """**품목 분기의 전제** — 분기 하나 = 전제 하나 (🆕 D-276 · D-263).

    🚨 실증 여부는 여기 없다 — 실증은 문장 단위 실증 분기(`SubstBranch`)다. 곱하지 않는다 (D-263 ④).
    ⛔ `전용법_미수록` 은 전제가 아니다 — 판정할 법이 없다 (D-277).
    """

    식품 = "식품"
    건기식_인정 = "건기식_인정"
    건기식_비인정 = "건기식_비인정"
    화장품 = "화장품"
    일반상품 = "일반상품"


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
        # 🆕 2026-09-21 (전수 재검토) — ⛔ 위 docstring 이 「인코더는 내릴 수 없다」고 적었는데 `floor=R3 · final=R0` 이
        #    검증을 지났다. 래칫(D-09 · max)의 뜻 그대로 — 최종은 하한보다 낮을 수 없다.
        if self.final.level < self.floor.level:
            raise ValueError(
                f"최종 위험도가 코드 하한보다 낮다 — floor={self.floor.value} final={self.final.value} (D-09 래칫)"
            )
        if self.final.level > self.floor.level and self.evidence_span is None:
            raise ValueError(
                "하한 위로 올리려면 근거 스팬이 필요하다 (D-131) — "
                f"floor={self.floor.value} final={self.final.value}"
            )
        return self


class SubstBranch(BaseModel):
    """**실증 분기** — 문장 하나의 주석 (🆕 D-263 ④ · D-268 「지시」의 내용).

    기록되는 판정은 **실증을 못 한 경우**다 (D-263 ①). 이것은 「실증하면 **여기까지** 내려갈 수 있다」는 **상한**이다.
    🚨 「적법」이라 쓰지 않는다 (D-05 · D-130) — 내려갈 수 있는 등급과 인정되는 자료 종류만 적는다.
    ⛔ 특허 · 수상 · 인증은 실증 자료가 아니다 (D-228) — `accepted_evidence` 에 넣지 않는다.
    """

    #: 실증하면 내려갈 수 있는 등급의 **상한** — 실증 전 위험도보다 높을 수 없다 (문장 검증기 `_subst_is_for_B`)
    substantiated_max: Risk
    #: 인정되는 실증 자료의 종류 — 시험·조사 결과 · 전문가 견해 · 학술문헌 (식품 시행규칙 제9조① · D-228)
    accepted_evidence: list[str] = Field(..., min_length=1)
    #: 기준 문안 — 조문을 인용한 설명 (D-263 ②). 🚨 문안 확정은 조문 대조 뒤다
    criteria: str = Field(..., min_length=1)


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
    #: 🆕 **판정 대상 아님** — 주장이 아닌 문장(섭취 대상 · 사업자 정보 · 의무 표기 · 구호 …) (D-275 · D-242 조건 D).
    #:    「특이사항 없음(R0)」과 가른다 — 안 본 것을 본 것처럼 말하지 않는다 (D-63).
    not_claim: bool = False
    #: 🆕 **뺄 구간** — 원문(raw) 좌표 · `label` 에 위반 유형 (D-278 · D-265). ⛔ 상향 근거 구간(`risk.evidence_span`)과 다른 칸이다
    spans: list[Span] = Field(default_factory=list)
    #: 🆕 **실증 분기** — B 실증형에만 (D-263 ④ · D-268)
    substantiation: SubstBranch | None = None

    @model_validator(mode="after")
    def _hold_reason_iff_hold(self) -> SentenceJudgment:
        # `app/models.py` ck_judgment_hold_reason 과 **같은 규칙**이다
        if (self.verdict is Verdict.hold) != (self.hold_reason is not None):
            raise ValueError("hold 일 때만, 그리고 hold 이면 반드시 hold_reason 이 있다 (D-127)")
        return self

    @model_validator(mode="after")
    def _confirmed_risk_invariant(self) -> SentenceJudgment:
        # 🆕 D-273 결정 2 — 확정 문장은 **위반이 없으면 R0, 있으면 R1 이상**이다. 계약과 DB(0018)가 같은 규칙을 든다 (D-99).
        #    ⛔ 이 규칙이 있어야 「통과 = 확정 ∧ R0」이 「확정 ∧ 위반 없음」과 같은 뜻이 된다 — 화면·집계가 위험도 한 칸만 봐도 맞다.
        #    위험도를 안 적은 확정(`final is None`)은 여기서 보지 않는다 — 통과가 아니다 (`is_pass`).
        if self.verdict is Verdict.confirmed and self.risk.final is not None:
            if not self.violations and self.risk.final is not Risk.R0:
                raise ValueError(
                    f"위반이 없는 확정 문장인데 위험도가 {self.risk.final.value} 다 — 위반이 없으면 R0 이다 (D-273)"
                )
            if self.violations and self.risk.final is Risk.R0:
                raise ValueError(
                    "위반을 확정했는데 위험도가 R0 이다 — 위반이 있으면 R1 이상이다 (D-273)"
                )
        # 🆕 D-275 — 판정 대상 아님은 **확정 · 위반 없음 · R0 · 뺄 구간 없음 · 실증 분기 없음**이다
        if self.not_claim and (
            self.verdict is not Verdict.confirmed
            or self.violations
            or self.spans
            or self.substantiation is not None
            or self.risk.final not in (None, Risk.R0)
        ):
            raise ValueError(
                "판정 대상 아님인데 확정 · 위반 없음 · R0 · 구간 없음이 아니다 (D-275) — "
                "주장이 아닌 문장에는 걸린 것이 없다"
            )
        return self

    @model_validator(mode="after")
    def _confirmed_violation_has_reason(self) -> SentenceJudgment:
        # 🆕 D-273 결정 3 — 확정 위반에는 **불가 사유(A/B/C)가 반드시 붙는다** (D-59 · D-242 「없음·C」).
        #    ⛔ 사유가 비면 라우터가 증명서·지시로 못 보내고, 종전 문턱(≤R1)에서는 **통과로 새던** 모양이다.
        #    🚨 사유를 못 정하면 확정이 아니라 **보류**다 — 사유 없는 확정을 내지 않는다 (D-72).
        if self.verdict is Verdict.confirmed and self.violations and self.infeasibility is None:
            raise ValueError(
                f"위반을 확정했는데 불가 사유(A/B/C)가 없다 — {[v.value for v in self.violations]} (D-273 · D-59)"
            )
        return self

    @model_validator(mode="after")
    def _subst_is_for_B(self) -> SentenceJudgment:
        # 🆕 D-263 ④ · D-61 — 실증 분기는 **B 실증형에만** 붙는다. C 절대형은 선택지가 없다 (D-263 ⑤).
        #    ★ 2판의 `condition=B ⇔ substantiation` 을 불가 사유로 대신한다 — 조건 칸은 응답에 싣지 않는다 (D-275).
        if self.substantiation is None:
            return self
        if self.infeasibility is not Infeasibility.B:
            raise ValueError(
                f"실증 분기는 B 실증형에만 붙는다 — 불가 사유 {self.infeasibility} (D-263 ④ · D-61)"
            )
        # 🚨 실증은 **내리기만** 한다. 실증 전 위험도가 없으면 상한을 잴 수 없다 — 없음을 낮음으로 세지 않는다 (D-72)
        if self.risk.final is None:
            raise ValueError("실증 분기가 있는데 실증 전 위험도가 없다 (D-72)")
        if self.substantiation.substantiated_max.level > self.risk.final.level:
            raise ValueError(
                f"실증했을 때의 상한({self.substantiation.substantiated_max.value})이 실증 전 위험도"
                f"({self.risk.final.value})보다 높다 — 실증은 등급을 올리지 않는다 (D-263)"
            )
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
       「B 를 C 처럼 답하기」가 된다. 🔄 검수에서는 그때 `outcome=guidance`(지시)이고, 탐색 실패는 생성 종착이다 (D-268 · D-274).
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

    #: 🔴 **`None` 은 「미확정」이다** (2026-09-16 · D-72). 🔄 D-271 — 「`일반` = 판별 결과 일반식품」은 폐기됐다.
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


class Branch(BaseModel):
    """**품목 분기** — 전제 하나에서 계산한 문서 판정 (🆕 D-263 · D-267 · D-276).

    🚨 **분기는 판정이 아니다.** 기록되는 판정은 응답의 `sentences` 다 — 가장 보수적인 전제의 것 (D-263 ①).
       분기는 「이 제품이 ○○라면」의 결과이고 화면은 **전제 문구와 함께만** 그린다 (D-263 ③).
       ★ 전제가 필수 칸이라 「전제 없는 통과」가 타입으로 나올 수 없다 (2판 `_no_premise_pass_badge` 를 타입이 대신한다).
    """

    premise: Premise
    #: 인정번호를 대조해 확인된 전제인가 (D-263 ⑥). 대조가 되면 기록되는 판정이 이 분기를 따른다
    verified: bool = False
    outcome: Outcome
    sentences: list[SentenceJudgment] = Field(default_factory=list)
    #: 기준 문안 — 조문을 인용한 설명 (D-263 ②). 🚨 문안 확정은 조문 대조 뒤다
    criteria: str = Field(..., min_length=1)
    evidence: list[EvidenceArticle] = Field(default_factory=list)


class JudgeResponse(BaseModel):
    """**검수(진입점 A) 응답.** 🚨 검수는 대체 문구를 내지 않는다 — `candidates` 는 늘 빈 목록 (D-265).

    🔄 2026-09-23 (D-274 ~ D-278) — 품목 · 미검수 법 · 분기 칸이 섰다. 기록되는 판정은 `sentences` 다 (D-263 ①).
    """

    outcome: Outcome
    #: 🆕 **판별된 품목** — 판정 결과에 속한다 (D-82 · D-277). `None` = 미확정 → 세 법 + 분기 (D-229 ⑥)
    category: Category | None = None
    #: 🆕 **미검수 법** — 「○○법 미검수」. 품목이 `전용법_미수록` 이면 비지 않는다 · 제거할 수 없다 (D-271 ⑤ · D-277)
    not_reviewed: list[str] = Field(default_factory=list)
    sentences: list[SentenceJudgment] = Field(default_factory=list)
    #: 🆕 **품목 분기** — 처음에 전부 계산해 담고 화면이 고른다 · 다시 판정하지 않는다 (D-263 ⑦ · D-276)
    branches: list[Branch] = Field(default_factory=list)
    #: ⛔ **검수에서는 늘 빈 목록** (D-265). 칸과 검증기 둘은 D-265 문언대로 둔다 — 프론티어는 생성의 것이다
    candidates: list[Candidate] = Field(default_factory=list)
    #: `outcome=certificate` 일 때만 (D-32 · D-125)
    certificate: Certificate | None = None
    #: 🔴 **0-base.** 총 라운드 K+1=3 이므로 0·1·2 만 (D-126 · ck_judgment_attempt). 🔄 검수에서는 늘 0 (D-265)
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
                    "B 실증형에는 증명서를 내지 않는다 — 검수에서는 outcome=guidance(지시)다 (D-59 · D-268)"
                )
            if self.candidates:
                raise ValueError("증명서를 내면서 대체 문구를 함께 내지 않는다 (D-59)")
        if self.outcome is not Outcome.certificate and self.certificate is not None:
            # 🔄 2026-09-23 — 종전 규칙 「탐색 실패에는 증명서가 없다」를 넓혔다. 탐색 실패는 생성 종착으로 갔다 (D-274)
            raise ValueError("증명서는 outcome=certificate 일 때만 낸다 (D-32 · D-125)")
        if self.outcome is not Outcome.passed and self.candidates:
            raise ValueError("프론티어는 통과했을 때만 낸다 (D-125)")
        # 🆕 2026-09-21 (전수 재검토 I2) — **루프에 안 들어간 통과**(attempt 0)는 문장이 전부 통과여야 한다 (D-125 ·
        #    🔄 D-273 「통과 = 확정 ∧ R0」). ⛔ 종전에는 미판정·R3 문장이 섞인 `pass` 도 계약을 지났다 — 라우터가
        #    위험도를 안 봐도(I1) 여기서 못 잡았다. 🚨 attempt ≥ 1 의 `pass` 는 **대체 문구**의 통과라 원문 판정과 다르다.
        if self.outcome is Outcome.passed and self.attempt == 0:
            bad = [s.sent_id for s in self.sentences if not is_pass(s)]
            if bad:
                raise ValueError(
                    f"outcome=pass 인데 통과가 아닌 문장이 있다 — {bad[:5]} (D-125 · D-273 · 확정 ∧ R0)"
                )
        return self

    @model_validator(mode="after")
    def _guidance_payload(self) -> JudgeResponse:
        # 🆕 D-268 — 「지시」는 확정된 **B 실증형** 위반의 종착이다. 우선순위 보류 > 증명서 > 지시 > 통과 대로 —
        #    하나라도 확정이 아니면 보류 · A·C 가 섞이면 증명서다.
        #    사용자가 받는 것 = **뺄 구간 · 실증 자료 종류 · 내려갈 수 있는 등급** (D-265 표) — 없으면 지시가 빈 카드다.
        if self.outcome is not Outcome.guidance:
            return self
        if not self.sentences or any(s.verdict is not Verdict.confirmed for s in self.sentences):
            raise ValueError(
                "outcome=guidance 인데 확정이 아닌 문장이 있거나 문장이 없다 — 보류다 (D-268)"
            )
        reasons = {s.infeasibility for s in self.sentences if s.infeasibility}
        if reasons & {Infeasibility.A, Infeasibility.C}:
            raise ValueError("outcome=guidance 인데 A·C 가 섞였다 — 증명서다 (D-268 우선순위)")
        subst = [s for s in self.sentences if s.infeasibility is Infeasibility.B and s.violations]
        if not subst:
            raise ValueError("outcome=guidance 인데 확정된 B 실증형 위반이 없다 (D-268)")
        thin = [s.sent_id for s in subst if s.substantiation is None or not s.spans]
        if thin:
            raise ValueError(
                f"지시 문장에 실증 분기나 뺄 구간이 없다 — {thin[:5]} (D-268 · D-265 · D-278)"
            )
        return self

    @model_validator(mode="after")
    def _recorded_is_conservative(self) -> JudgeResponse:
        # 🆕 D-263 ① · D-276 결정 2 — **기록되는 판정은 가장 보수적인 경우다.** 검증 안 된 분기가 기록을 낮추지 못한다.
        #    검증된(인정번호 대조) 분기는 많아야 하나 — 그때는 기록이 그 분기를 따른다 (D-263 ⑥).
        verified = [b for b in self.branches if b.verified]
        if len(verified) > 1:
            raise ValueError(f"검증된 분기가 {len(verified)}개다 — 제품은 하나다 (D-263 ⑥)")
        if verified:
            return self
        recorded = {s.sent_id: s for s in self.sentences}
        for b in self.branches:
            for bs in b.sentences:
                if bs.risk.final is None:
                    continue
                r = recorded.get(bs.sent_id)
                # 🚨 기록에 위험도가 없는데 분기에 있으면 거부 — 없음을 낮음으로 세지 않는다 (D-72)
                if r is None or r.risk.final is None or r.risk.final.level < bs.risk.final.level:
                    got = "없음" if r is None or r.risk.final is None else r.risk.final.value
                    raise ValueError(
                        f"검증 안 된 분기 {b.premise.value} 의 {bs.sent_id} 가 {bs.risk.final.value} 인데 "
                        f"기록은 {got} 다 — 기록은 가장 보수적인 경우여야 한다 (D-263 ①)"
                    )
        return self

    @model_validator(mode="after")
    def _branch_hold_has_branches(self) -> JudgeResponse:
        # 🆕 D-263 ② · D-229 ⑥ — 전제를 몰라 멈췄으면 **선택지(분기)를 준다.**
        #    ⬜ D-229 ⑥ 의 넓은 규칙 「품목 미확정이면 분기는 언제나」는 **W4(`merge_laws`)가 분기를 만드는 커밋**에서
        #       검증기로 올린다 — 지금 걸면 분기를 못 만드는 스텁 그래프 응답이 깨진다 (D-192).
        premise_holds = {HoldReason.cat_unknown, HoldReason.premise_unknown}
        if any(s.hold_reason in premise_holds for s in self.sentences) and not self.branches:
            raise ValueError(
                "전제를 몰라 보류했는데 분기가 없다 — 선택지를 주지 않았다 (D-263 ② · D-229 ⑥)"
            )
        premises = [b.premise for b in self.branches]
        if len(premises) != len(set(premises)):
            raise ValueError(f"분기 전제가 겹친다 — {[p.value for p in premises]} (D-276)")
        ids = {s.sent_id for s in self.sentences}
        stray = sorted({bs.sent_id for b in self.branches for bs in b.sentences} - ids)
        if stray:
            raise ValueError(f"분기에 응답에 없는 문장이 있다 — {stray[:5]}")
        return self

    @model_validator(mode="after")
    def _uncovered_law_notice(self) -> JudgeResponse:
        # 🆕 D-271 ⑤ · D-277 — 전용법 품목은 **통과를 내지 않고 미검수 고지를 단다.** 고지는 제거할 수 없다.
        uncovered = self.category is Category.전용법_미수록
        if uncovered != bool(self.not_reviewed):
            raise ValueError(
                "품목이 전용법_미수록 이면 미검수 법이 있고, 아니면 없다 (D-271 ⑤ · D-277) — "
                f"category={self.category} not_reviewed={self.not_reviewed}"
            )
        if uncovered and self.outcome is Outcome.passed:
            raise ValueError("전용법 품목에 통과를 냈다 — 안 본 법이 있다 (D-271 ⑤ · D-63)")
        if not uncovered and any(s.hold_reason is HoldReason.law_uncovered for s in self.sentences):
            raise ValueError("law_uncovered 보류는 전용법 품목에서만 난다 (D-277)")
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
    """통과 조건 — 🔄 **확정 ∧ R0** (D-273 · D-125 개정 · `PASS_RISK_MAX`). = 확정 ∧ 위반 없음 (불변식 `_confirmed_risk_invariant`).

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
    """B 출력 — 프론티어 (D-31 · D-34 N=3). 🔄 D-274 — **종착 칸이 있다**(프론티어 · 탐색 실패 · 보류).

    🚨 화면이 축의 뜻을 이미 적어 뒀다 — y 축은 **전환율이나 판매 성과가 아니라**
       원문 대비 정보량 보존율이다. 지어낸 성과 지표를 여기 담지 않는다.
    """

    #: 🆕 생성 종착 (D-274) — 🚨 필수다. 없음을 프론티어로 읽지 않는다 (D-72)
    outcome: GenerateOutcome
    candidates: list[Candidate] = Field(default_factory=list)
    keywords: list[KeywordScreen] = Field(default_factory=list)
    #: 각색본 — 프로파일이 주어졌을 때만. 🚨 각 결과가 **판정 코어를 다시 지난다** (D-119)
    adapted: list[AdaptedCopy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _outcome_matches_candidates(self) -> GenerateResponse:
        # 🆕 D-274 — 프론티어는 후보가 있을 때만, 탐색 실패·보류는 후보 없이 (원문 유지 + 실증 안내 · D-125)
        if (self.outcome is GenerateOutcome.frontier) != bool(self.candidates):
            raise ValueError(
                f"생성 종착 {self.outcome.value} 와 후보 {len(self.candidates)}개가 맞지 않다 — "
                "프론티어는 후보가 있을 때만이다 (D-274)"
            )
        return self

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
