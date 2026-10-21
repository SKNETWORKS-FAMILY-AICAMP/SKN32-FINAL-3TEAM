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
from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator

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
       `cat_unknown` 은 **품목을 못 가림 ∧ 등급이 갈림**(D-229), `premise_unknown` 은 **품목은 가렸으나 인정 여부로 등급이 갈림**이다.
    """

    low_conf = "low_conf"  # 확신 부족 — 조건 M(맥락)도 여기로 (D-268)
    #: 🔄 2026-09-23 — 원장 D-127 의 뜻은 **코드 하한 ↔ 모델 예측 2등급 차**(3-5 ③)다.
    #:    ⛔ 종전 주석 「1·2위 격차 부족」은 원장과 달랐다 — 화면 라벨·`KNOWN_GAPS` 에도 같은 오기가 번졌다.
    gap2 = "gap2"  # 코드↔모델 2등급 차
    cat_unknown = (
        "cat_unknown"  # 품목 미확정 ∧ 등급이 갈림 (D-229 · D-82) — 등급이 안 갈리면 분기만
    )
    rd1 = "rd1"  # 공존 규칙 발동 (D-127 · D-120) — 🔄 09-21 종전 주석 「라운드 1 미해소」는 D-127 과 달랐다
    premise_unknown = (
        "premise_unknown"  # 품목은 가렸으나 인정 여부로 등급이 갈림 — 분기를 낸다 (D-263 ② · D-276)
    )
    #: 전용법 품목(의료기기 · 의약외품 등)에서 표시광고법으로 걸린 것이 없는 문장 — 안 본 법이 있다 (D-271 ⑤ · D-277)
    law_uncovered = "law_uncovered"


class HoldKind(enum.StrEnum):
    """**보류의 종류** — 화면 · 평가가 보류를 나눠 보이는 칸 (🆕 2026-10-21 · D-348 보충 36 결정 4 · (나) 계산 칸 · 흐름 ⑧).

    ★ 사유 코드(`HoldReason`)가 아니다 — 이미 있는 칸(사유 · 질문 · 후보 유무)에서 **계산**한다(`hold_kind` 한 곳 · D-99).
       DB 제약(`ck_judgment_hold_reason_values`)과 저장 칸은 그대로다.
    ⛔ 종전에는 `low_conf` 하나가 「잡았는데 확정 못 함」과 「사전 · 인코더 둘 다 못 잡음」을 함께 담았다(인계 10-21 클론B §1 #4).
    🚨 어느 것도 「적법」 · 「통과」가 아니다(D-340 결정 6 통과 닫힘) — 「걸린 것 없음」도 보류다.
    """

    awaiting_answer = "awaiting_answer"  # 답 대기 — 문장에 질문(사실 확인 · 실증)이 섰다 · 답하면 판정이 난다(보충 33)
    awaiting_pick = "awaiting_pick"  # 고르기 대기 — 품목 · 하위 전제에 달렸다 · 분기가 선택지다
    unconfirmed = "unconfirmed"  # 확인 못 함 — 사전 후보 · 인코더 후보 · 인코더 근거가 있는데 질문도 확정도 없다(막다른 보류)
    nothing_found = (
        "nothing_found"  # 걸린 것 없음 — 사전 · 인코더 둘 다 못 잡았다(흐름 ⑧) · 통과가 아니다
    )
    other = "other"  # 그 밖의 사유(코드 · 모델 등급 차 · 공존 규칙 · 전용법 미검수) — 사유 코드를 그대로 읽는다


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
    🔄 D-265 — 검수는 대체 문구를 내지 않는다: B 는 요건 안내만, 문구 생성은 진입점 B.
       D-264 — A 에서 막는 것은 같은 주장의 대체안(삭제안 · 사실 진술안은 생성에서 허용).
       D-289 ② — 표시로 풀리는 금지는 C 가 아니라 B · 표시요건.
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

    🔴 인코더가 예측하는 확정 클래스는 `scripts/collect.py` 의 `VIOLATION_TYPES` 다 —
       🔄 2026-10-06 (D-321) **8종**(종전 6종 + `부당_비교광고` · `비방광고`). `기능성화장품_오인` 은 편입 대기 ·
       `실증책임_위반` 은 후보(표본 0)다. 목록은 인코더 재학습 차수에만 바뀐다(D-232 ①③).
    🔄 D-255 — `추천_보증_뒷광고` 는 후보가 아니라 **범위 밖**이다(문구로 판정할 수 없다 · 대가 표시 **누락**이 위반).
       🔄 D-282 ④ (D-255 ① 개정) — `후기_체험기_기만` 은 형식 라벨이 아니라 **[별표 1] 5호 다목의 파생 유형**이다. 목이 없는 5호는 `소비자_기만`.
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


#: 🆕 2026-10-02 (팀장 판정 · D-271 ④ · D-277 개정) — **주된 광고법을 검수하지 않은 품목.** 표시광고법 판정은 하되 통과를 내지 않고
#:    미검수 고지를 단다. `일반상품` 을 더한 까닭 — 식품 · 화장품이 아닌 상품에도 광고를 규율하는 법이 따로 있는 경우가 많다
#:    (금융 · 분양 · 의료기기 · 생활화학제품 …). 그 목록을 다 가질 수 없으므로 「없다」고 가정하지 않는다 (D-63 · D-220).
#:    ⛔ 종전에는 `일반상품` 이 표시광고법만 타고 **통과까지** 나갔다 — 안 본 법을 본 것처럼 말하는 자리였다.
UNCOVERED_CATEGORIES = frozenset({Category.전용법_미수록, Category.일반상품})

#: 미검수 법의 이름을 가릴 수 없을 때의 고지 한 줄 — D-277 ⬜ 「해당 품목의 전용법」. 품목 낱말로 법을 가리게 되면 그 이름을 적는다.
NOT_REVIEWED_UNNAMED = "해당 품목의 전용법"

#: 🆕 2026-10-13 — **법령 판을 모른다**는 값. 응답 기본값 · 그래프 · 화면이 같은 값을 본다 (D-99).
#: 🔴 판정에 쓴 코퍼스의 판을 읽을 길이 없으면 이 값을 적는다 — 날짜를 지어내지 않는다 (D-220 · D-103 ③).
#:    ⛔ 2026-10-13 까지 `app/graph.py` 가 「2026-09-10」을 고정으로 적었다 — 코퍼스를 다시 만들어도 그대로였다.
#:    현행 청크의 시행일(`chunk.effective_date`)이 6,686 중 0 이 채워져 있어 읽을 값이 없다 (원장 10-13 클론 A ⑦).
#: 🔄 2026-10-14 (D-103 ③ 개정) — 판을 채우지 않기로 했다. 이 값은 `law_version` 칸을 뺄 때(W10 흡수 뒤)까지만 쓴다
LAW_VERSION_UNKNOWN = "unknown"


class CategorySource(enum.StrEnum):
    """**품목이 어디서 왔나** (🆕 2026-10-02 · D-276 ⑥). `app/models.py` `ck_judgment_category_source_values` 와 **같은 둘**이다.

    🔴 「판별된 품목」과 「사용자가 고른 품목」을 응답이 가른다 — 고른 품목의 결과는 **선택 전제 결과**다.
       화면은 전제 없는 통과 배지를 붙이지 않고 「○○ 기준」과 「사업자가 선택한 값이며 확인되지 않았습니다」를 함께 보인다 (D-229 ⑤ · D-263 ③).
    """

    classified = "classified"  # 우리가 판별했다 (D-82)
    user_selected = "user_selected"  # 사용자가 골랐다 — 확인되지 않은 값이다 (D-276)


class Premise(enum.StrEnum):
    """**품목 분기의 전제** — 분기 하나 = 전제 하나 (🆕 D-276 · D-263).

    🚨 실증 여부는 여기 없다 — 실증은 문장 단위 실증 분기(`SubstBranch`)다. 곱하지 않는다 (D-263 ④).
    ⛔ `전용법_미수록` 은 전제가 아니다 — 판정할 법이 없다 (D-277).
    """

    식품 = "식품"
    건기식_인정 = "건기식_인정"
    건기식_비인정 = "건기식_비인정"
    #: 🆕 2026-09-30 (D-295) — **일반식품 기능성 표시** — 고시 「부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는
    #:    광고에 관한 규정」 제3~6조 요건을 채운 일반식품. 🚨 건기식 인정과 섞지 않는다 — 요건이 다르다(원료 함유 ≠ 요건 충족 · D-263 ②)
    일반식품_기능성 = "일반식품_기능성"
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
    #: 🆕 2026-10-08 (D-323 결정 2) — **사전 항목이 인용한 조문**(판정이 기대는 조문)이면 참 · 검색이 찾은 참고 조문이면 거짓.
    #:    ⛔ enum 이 아니라 참거짓이다 — enum 은 DB 값과 맞춰야 하는 규칙(D-54)을 끌고 온다. 둘뿐이라 참거짓으로 족하다.
    #:    🚨 기본값은 거짓(참고) — 칸을 모르는 쪽이 만든 근거가 「판정 근거」로 읽히지 않게 (D-220).
    basis: bool = False
    #: 🆕 2026-10-12 (D-293 개정 안건 3 (가)) — **문서 이름**(「표시ㆍ광고 내용의 실증에 관한 운영 고시」 · 「…[별표 1] 부당한 표시 또는 광고의 내용」).
    #:    산문 고시 좌표 「Ⅱ.1」 은 고시 이름 없이 뜻이 서지 않는다. 🚨 **좌표가 아니다** — 좌표는 `law_id` + `article` 이다.
    #:    `None` = 이름을 모른다(사전 근거처럼 청크 없이 만든 근거). 화면은 이름이 없으면 `law_id` 로 적는다.
    doc_title: str | None = None


#: 🆕 2026-10-16 (D-348 결정 5 · 보충 2 결정 5) — **인코더 하한을 기록에 들이는 상한**(신뢰 층). 지금은 R1 층뿐이다 —
#:    「위반이라면 적어도 R1」은 유형이 틀려도 참이고 그 문장이 주장이 아닐 때만 틀린다(D-273). R2 이상 층(유형을 믿을 수 있어야 한다)이
#:    판정되면 그 결정으로 올린다. 🔴 저장의 CHECK 가 같은 수를 든다(`app/models.py` `ck_judgment_encoder_max` · D-99)
ENCODER_RECORD_MAX = Risk.R1


class EncoderBasis(BaseModel):
    """인코더 하한의 **근거 하나** — 어느 분기 · 어느 유형 · 대응표의 어느 호 · 그 유형의 하한 (🆕 2026-10-16 · D-348 보충 2 결정 2 · 10).

    ★ 위험도가 **자기 근거를 갖는다** — 사전 하한(`floor`)의 근거가 `evidence` 이듯 인코더 하한(`encoder`)의 근거가 이것이다.
       표시용 AI 추정 유형(`encoder_candidates` · 판정 아님 · D-323)과 칸을 가른다 — 기록 판정의 후보는 「모름」 입력의 것이고
       인코더 하한은 분기(전제마다의 품목 입력)에서 온다. 둘을 섞으면 값과 근거가 다른 입력에서 온다(10-16 결함 · 결정 10).
    🚨 「이 유형이라면 이 조항」이다 — 이 문구에서 찾은 조문이 아니다(`EvidenceArticle.basis` 는 거짓 그대로).
    """

    #: 그 하한을 낸 전제(분기). 품목을 아는 한 전제 판정이면 그 전제다
    premise: Premise
    violation: Violation
    #: 전제가 옮긴 후보면 원래 유형 (`EncoderTypeCandidate.moved_from` 과 같다)
    moved_from: Violation | None = None
    #: 그 유형 · 그 전제의 제재표 하한(R1 이상 · D-273) — 기록에 든 값(`RiskAssessment.encoder`)은 신뢰 층 상한으로 깎인 값이다
    floor: Risk
    articles: list[EvidenceArticle] = Field(..., min_length=1)


class RiskAssessment(BaseModel):
    """D-09 래칫 — `final = max(코드 하한, 인코더 하한)`.

    🚨 **인코더는 내릴 수 없다.** 코드가 보류면 인코더가 못 뒤집는다(단조 규칙).
    🔴 상향(`final > floor`)에는 `evidence_span` 이 반드시 붙는다 (D-131).
       ⛔ 이 규칙이 DB 에서는 널로 우회되고 있었다 — 마이그레이션 0006 이 막았다.
          계약도 같은 조건을 건다. 두 곳이 다르면 늦게 터진다.
    🔄 2026-10-16 (D-348 보충 2 결정 1 · 7) — **사전 하한과 인코더 하한은 칸이 다르다.** `floor` 는 사전 하한(재료 · 뜻 그대로 · D-313 결정 3)
       이고 `encoder` 는 인코더 하한(인코더 유형 + 전제 → 대응표의 호 → 서명된 제재표)이다. 인코더 하한까지 올리는 것은 근거 스팬
       대신 **호 근거**로 선다 — 문장의 인코더 후보 참조 조항(`SentenceJudgment._encoder_risk_has_basis`). 그 위로 올리는 것은
       종전대로 근거 스팬이 필요하다. 인코더 하한은 `ENCODER_RECORD_MAX` 를 넘지 못한다.
    """

    floor: Risk | None = None  # 사전(코드) 하한 (D-09 · D-130 · D-313 결정 3)
    #: 🔄 2026-10-16 (D-348 보충 2) — **인코더 하한**(기록에 들인 값 · 신뢰 층 상한 이하). 종전 뜻 「인코더 예측」을 대신한다 — 값을 내는 곳이
    #:    없던 칸이다. 화면은 「AI 추정 · 판정 아님」 표지로 보인다. 근거는 문장의 인코더 후보 참조 조항(대응표의 호)이다
    encoder: Risk | None = None
    #: 🆕 2026-10-16 (D-348 보충 2 결정 10) — **인코더 하한의 근거**(분기 · 유형 · 호 · 하한). 인코더 하한이 있으면 반드시 있고 없으면 비어 있다.
    #:    여러 유형 · 같은 등급의 여러 분기면 전부 싣는다(화면은 대표 한 줄 + 나머지 · `app/reasons.py` `encoder_basis_view`)
    encoder_basis: list[EncoderBasis] = Field(default_factory=list)
    final: Risk | None = None
    evidence_span: Span | None = None
    #: 🆕 2026-10-01 (D-310 개정 (다)) **가능 상한** — 하한은 「확실한 최소」다. 목(별표1)을 못 맞혀 하한이 「그 밖에 R1」로 떨어진
    #:    문장도 목에 따라 더 무거운 처분(예: 영업정지)이 있을 수 있다 — 그 가능성을 **숫자를 올리지 않고** 보인다.
    #:    🚨 판정 · 통과 · 래칫에 쓰지 않는다(표시 전용). 상한이 하한과 같으면 비운다
    ceiling: Risk | None = None
    #: 상한이 무엇에서 나왔나 — 「목에 따라 R2(업무정지)까지 — 수상 · 체험기 · 이온수 등」. 상한이 있으면 반드시 있다
    ceiling_note: str | None = None

    @model_validator(mode="after")
    def _ratchet(self) -> RiskAssessment:
        # 🆕 2026-10-16 (D-348 보충 2 결정 5) — 인코더 하한은 신뢰 층 상한을 넘지 못한다
        if self.encoder is not None and self.encoder.level > ENCODER_RECORD_MAX.level:
            raise ValueError(
                f"인코더 하한 {self.encoder.value} 이 기록 상한 {ENCODER_RECORD_MAX.value} 을 넘는다 — "
                "R2 이상은 유형을 믿을 수 있어야 한다 (D-348 결정 5)"
            )
        # 🆕 2026-10-16 (D-348 보충 2 결정 10) — 인코더 하한과 그 근거는 함께 있거나 함께 없다 (D-224 · 근거 없는 등급을 내지 않는다)
        if (self.encoder is None) != (not self.encoder_basis):
            raise ValueError(
                "인코더 하한과 그 근거(encoder_basis)는 함께 있거나 함께 없다 (D-348 보충 2 결정 10 · D-224)"
            )
        if self.encoder_basis and any(b.floor.level < Risk.R1.level for b in self.encoder_basis):
            raise ValueError("인코더 하한의 근거에 R0 하한이 있다 — 위반이라면 R1 이상이다 (D-273)")
        if self.final is None:
            if self.encoder is not None:
                raise ValueError(
                    "인코더 하한을 적었는데 최종 위험도가 없다 — 합치지 않았다 (D-348 결정 4)"
                )
            return self
        if self.floor is None and self.encoder is None:
            raise ValueError(
                "최종 위험도를 적으려면 하한(사전 또는 인코더)이 있어야 한다 — "
                "상향의 정의가 「하한보다 높다」인데 하한이 없으면 상향이 정의되지 않는다 (D-09)"
            )
        # 🆕 2026-09-21 (전수 재검토) — ⛔ 위 docstring 이 「인코더는 내릴 수 없다」고 적었는데 `floor=R3 · final=R0` 이
        #    검증을 지났다. 래칫(D-09 · max)의 뜻 그대로 — 최종은 하한보다 낮을 수 없다.
        for name, low in (("코드 하한", self.floor), ("인코더 하한", self.encoder)):
            if low is not None and self.final.level < low.level:
                raise ValueError(
                    f"최종 위험도가 {name}보다 낮다 — {name}={low.value} final={self.final.value} (D-09 래칫)"
                )
        base = max((r for r in (self.floor, self.encoder) if r is not None), key=lambda r: r.level)
        if self.final.level > base.level and self.evidence_span is None:
            raise ValueError(
                "하한 위로 올리려면 근거 스팬이 필요하다 (D-131) — "
                f"floor={self.floor.value if self.floor else None} encoder="
                f"{self.encoder.value if self.encoder else None} final={self.final.value}"
            )
        return self

    @model_validator(mode="after")
    def _ceiling_above_floor(self) -> RiskAssessment:
        # 🆕 D-310 개정 (다) — 상한은 하한보다 **높을 때만** · 근거 줄과 함께. 하한이 없으면 상한도 없다(없음을 상한으로 꾸미지 않는다 · D-220)
        if self.ceiling is None:
            if self.ceiling_note is not None:
                raise ValueError("상한 근거 줄만 있고 상한이 없다 (D-310)")
            return self
        if self.floor is None:
            raise ValueError("하한 없이 가능 상한을 적을 수 없다 (D-310 · D-09)")
        if self.ceiling.level <= self.floor.level:
            raise ValueError(
                f"가능 상한({self.ceiling.value})이 하한({self.floor.value})보다 높지 않다 — 같으면 비운다 (D-310)"
            )
        if not (self.ceiling_note or "").strip():
            raise ValueError(
                "가능 상한에는 근거 줄이 있어야 한다 — 무엇에서 나온 상한인가 (D-310 · D-305)"
            )
        return self


class GuideArticle(BaseModel):
    """**원문 보기** 한 조각 — 수집본 조문의 글자 그대로 (🆕 2026-10-20 · D-348 보충 32 결정 3).

    🚨 판정이 아니다 — 판정 · 분기 열쇠 · 위험도 어디에도 들지 않는다(표시 전용). 글자는 수집본(`data/derived/law_article.jsonl`)에서
       `scripts/guide_build.py` 가 옮긴다 — 손으로 적지 않는다(D-90).
    """

    #: 문서 이름(「부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정」)
    law_name: str = Field(..., min_length=1)
    #: 조 · 항 · 호 표기(「제6조③」 · 「제3조②3.」)
    where: str = Field(..., min_length=1)
    #: 호를 가리킬 때 그 호가 딸린 항의 머리 글(「② 제1항에도 불구하고 … 제외한다.」) — 항 · 조를 가리키면 None
    lead: str | None = None
    text: str = Field(..., min_length=1)
    #: 수집본 판의 날짜(파일 이름의 `YYYYMMDD` → `YYYY-MM-DD`) — 모르면 None(지어내지 않는다 · D-220). 현행 여부는 말하지 않는다
    version: str | None = None


class Guide(BaseModel):
    """**두 겹 안내** — 사용자가 전제 · 답을 고를 때 펼쳐 보는 설명 (🆕 2026-10-20 · D-348 보충 32 결정 3).

    ★ 두 겹 — 쉬운 풀이(무엇인가 · 확인하는 법 · 헷갈리기 쉬운 것)와 원문 보기(조문 그대로).
    🔴 **승인된 글 · 짝 표만** 싣는다(D-147 · D-263 ②) — 승인 전에는 칸이 없다(`app/guide.py`). 「적법」 · 「안전」을 쓰지 않는다(D-05 · D-130).
    🚨 판정이 아니다 — 판정 · 분기 열쇠 · 위험도 어디에도 들지 않는다(표시 전용 · 응답을 만든 뒤 붙인다).
    """

    what: str | None = None
    check: str | None = None
    pitfall: str | None = None
    articles: list[GuideArticle] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_empty(self) -> Guide:
        if not (self.what or self.check or self.pitfall or self.articles):
            raise ValueError("빈 안내 — 승인된 글 · 조문이 없으면 칸을 두지 않는다 (D-220)")
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
    #: 🆕 2026-10-20 (D-348 보충 32 결정 3) 두 겹 안내 — 승인된 것만 · 없으면 None(표시 전용)
    guide: Guide | None = None
    #: 🆕 2026-10-21 (D-348 보충 39 결정 6 · 2 단계) **어느 유형의 실증 질문인가** — 섞인 유형 문장은 유형마다 따로 묻는다(`app/graph.py` `_enc_mixed`).
    #:    화면은 이 값을 답(`UserSubst.violation`)에 그대로 담아 보낸다 · 비면 유형을 가리지 않은 질문(사전 쪽 · 종전 판)
    violation: Violation | None = None

    @model_validator(mode="after")
    def _not_patent_or_award(self) -> SubstBranch:
        # 🆕 2026-10-01 (D-308 ④) — 특허 · 수상 · 인증은 실증 자료가 아니다 (D-228). 사실 확인은 `FactBranch` 다
        bad = [e for e in self.accepted_evidence if any(w in e for w in NOT_SUBSTANTIATION)]
        if bad:
            raise ValueError(
                f"실증 자료가 아니다 — {bad} (D-228) · 사실 확인은 사실 확인 분기(FactBranch)로"
            )
        return self


#: 🆕 2026-10-01 (D-308 ④ (가)) — 실증 분기에 **올 수 없는** 자료 낱말. 특허 · 수상 · 인증은 효능 실증이 아니다 (D-228).
#:    ⛔ 종전에는 docstring 의 약속뿐이었다 — 사실 확인 분기(`FactBranch`)가 생기며 둘이 섞일 자리가 생겨 코드로 막는다 (D-117)
NOT_SUBSTANTIATION = ("특허", "수상", "상장", "인증")


class FactKind(enum.StrEnum):
    """사실 확인 분기의 주장 종류 (D-308 ④). 별표1 4.마(수상 · 인증 명칭) · 7.나(원재료 · 성분명)."""

    수상_상장 = "수상_상장"
    인증 = "인증"
    원재료 = "원재료"
    #: 🆕 2026-10-16 (D-348 보충 3 결정 5) — 표시광고법 3조①1호로 의결된 사실 주장(원장 10-14(B) ⑤) · 건기식 인정 전제의 질병 문구
    특허 = "특허"
    등급 = "등급"
    자격 = "자격"
    #: 건기식 인정 전제에서 질병 문구가 **인정받은 기능성 그대로인가**(질병 발생 위험 감소 등 · [별표 1] 1호 목 나 · 다가 아님) — 결정 2
    인정_기능성 = "인정_기능성"
    #: 🆕 2026-10-17 (D-348 보충 6 결정 3 · 4 · 보충 7 결정 5 · 6 · 7) — **유형에 딸린** 사실 종류(낱말이 아니라 인코더 근거 유형이 묻게 한다)
    #:    부당 비교 — 비교 대상 · 기준을 밝혔나(표시광고법 시행령 3③ · 식품 [별표 1] 7.가 · 화장품 [별표 5] 2.바 앞부분)
    비교_기준 = "비교_기준"
    #: 비방 ② — 경쟁 제품의 불리한 사실만 고른 게 아닌가(같은 광고에 장점 · 비교 조건을 함께 밝혔나 · 표시광고법 시행령 3④)
    비방_선별 = "비방_선별"
    #: 소비자 기만(은폐 · 누락) — 같은 광고에 조건(제한 · 부대비용 등)을 함께 밝혔나
    조건_고지 = "조건_고지"
    #: 소비자 기만(가짜 후기) — 실존 소비자가 실제로 사용하고 쓴 후기인가(추천 · 보증 심사지침 35032)
    후기_실재 = "후기_실재"
    #: 무첨가 — 고시의 표시 조건(식품등의 표시기준 36814 별지 1.아.3)을 모두 지켰나(식품 [별표 1] 7.나)
    무첨가_조건 = "무첨가_조건"
    #: 🆕 2026-10-19 (D-348 보충 6 결정 9 · 보충 27) 기능성화장품 오인 — 이 효능으로 기능성화장품 심사 · 보고를 받았고 그 내용 그대로인가
    #:    (화장품법 제13조①2호 · 법 제4조① · 시행규칙 제2조)
    기능성_심사 = "기능성_심사"
    #: 🆕 2026-10-19 (D-348 보충 28 결정 3) 일반식품 기능성 표시 — 기능성 표시 고시(75449)의 요건을 모두 갖추었고 고시가 정한 방법 그대로인가
    #:    (식품표시광고법 시행령 [별표 1] 3.나 · 제8조①3호)
    기능성_표시 = "기능성_표시"


class Answer(enum.StrEnum):
    """사용자의 답 셋 (🆕 2026-10-16 · D-348 보충 5 · 보충 3 결정 2 의 「해당 없음」 집행).

    ★ 예 = 사실이 참이다 · 실증 자료가 있다 / 아니오 = 사실이 거짓이다 · 실증 자료가 없다 /
       해당없음 = 이 문장은 그 주장을 하지 않는다(질문이 엉뚱하다 — 그 분기를 걷는다).
    🔴 「예」 · 「아니오」는 **그 주장이 이 문장에 있다는 것까지** 사용자가 확인한 답이다 — 「해당없음」을 고르지 않았다(보충 5).
    🚨 검증이 아니다 — 책임은 답한 사람에게 있다(`UserFact` · `UserSubst`).
    """

    예 = "예"
    아니오 = "아니오"
    해당없음 = "해당없음"


class FactBranch(BaseModel):
    """**사실 확인 분기** — 문장이 **사실을 주장**하고(수상 · 인증 · 원재료) 위반 여부가 그 주장의 참에 달린 경우 (🆕 D-308 ④).

    기록되는 판정은 **사실을 확인 못 한 경우**다 (D-263 ①). 이것은 「그 사실이 참이면 **여기까지**」의 상한이다.
    🚨 실증 분기(`SubstBranch`)와 다르다 — 이 증빙은 **그 사실만** 증명한다. 수상 증서는 「수상했다」를 증명할 뿐
       효능을 증명하지 않는다(D-228). 그래서 칸을 나눴다 — 섞으면 「수상 = 실증」 착오가 화면에 되살아난다.
    """

    kind: FactKind
    #: 사실이 참이면 내려갈 수 있는 등급의 **상한** — 확인 전 위험도보다 높을 수 없다(문장 검증기 `_fact_is_for_B`)
    confirmed_max: Risk
    #: 그 사실을 증명하는 자료 — 수상 증서 · 인증서 · 원료 배합 기록 등
    accepted_evidence: list[str] = Field(..., min_length=1)
    #: 기준 문안 (D-263 ②). 🚨 문안 확정은 조문 대조 뒤다
    criteria: str = Field(..., min_length=1)
    #: 🆕 2026-10-20 (D-348 보충 32 결정 3) 두 겹 안내 — 승인된 것만 · 없으면 None(표시 전용)
    guide: Guide | None = None


class RiskEstimate(BaseModel):
    """인코더만 잡은 문장의 **추정 위험도** — 「확정되면 R? · 목에 따라 R?」 (🆕 2026-10-15 · D-340 결정 5 · D-346 · D-347 결정 6).

    🚨 **판정이 아니다** — 하한 · 래칫 · 종착 · 분기 열쇠 어디에도 들지 않는다(표시 전용). 근거 인용 없이 그 전제의 법 ∩ 그 유형의
       조항이 있는 법의 서명된 제재표에서 찾는다(`app/graph.py` `estimate_of` · `sanction.floor_rows`). D-131 개정 ① 이 판정되기
       전까지 표시로만 쓴다.
    🔴 `floor` 가 비면 **모른다**(그 법의 서명 행이 없다 · 그 법에 이 유형 조항이 없다) — R0 이 아니다 (D-220).
    """

    floor: Risk | None = None
    #: 목에 따라 더 무거울 수 있는 처분 — `RiskAssessment.ceiling` 과 같은 뜻(D-310 개정 (다)) · 하한과 같으면 비운다
    ceiling: Risk | None = None
    ceiling_note: str | None = None


class EncoderTypeCandidate(BaseModel):
    """인코더가 낸 **유형 후보** 하나 (🆕 2026-10-08 · D-323 결정 1 · D-131). 🚨 판정이 아니다.

    ⛔ 하한 · 확정 · 재판정 탈락 · 분기 열쇠 어디에도 들지 않는다 — 근거 구간(스팬)이 없는 인코더 출력은 상향 0 이다 (D-131).
    ⛔ `SentenceJudgment.violations` 와 섞지 않는다 — 그 칸은 사전 근거가 있는 유형만이다 (D-323 결정 3).
    """

    violation: Violation
    #: 모델의 확률 — 문턱은 모델 폴더(`label_scheme.json`)의 것이라 여기 싣지 않는다 (D-324)
    confidence: float = Field(..., ge=0.0, le=1.0)
    #: 🆕 2026-10-10 — **전제가 유형을 옮긴 후보**면 인코더가 실제로 낸 유형. `None` 이면 인코더가 이 유형을 그대로 냈다.
    #:    건강기능식품 오인(3호)은 건강기능식품 전제에서 서지 않고, 인정이 없는 전제에서는 그 자리에 [별표 1] 4.나
    #:    (인정하지 않은 기능성 · 거짓_과장)가 선다 — 사전 적중과 같은 규칙이다(`app/graph.py` `_premise_hits` · D-319 ④′ ②).
    #:    🚨 이때 `confidence` 는 **옮기기 전 유형**의 확률이다. 화면 · 평가는 이 칸으로 「옮긴 후보」를 가른다
    moved_from: Violation | None = None
    #: 🆕 2026-10-12 (D-327) — **참조 조항** — 이 유형을 정한 금지 조항과 세부 기준. 문장이 보내진 법마다 따로 실린다.
    #:    🚨 **이 문구에서 찾아낸 근거가 아니다** — 「이 유형이라면 이 조항」이다. `SentenceJudgment.evidence`(사전이 인용한 근거 ·
    #:       검색이 찾은 참고 조문)와 섞지 않는다 (D-323 결정 2 · 3). `basis` 는 늘 거짓이다 — 판정이 기대는 조문이 아니다.
    #:    🔴 비어 있으면 「그 법에 이 유형의 조항이 없다」다(예: 화장품법의 건강기능식품 오인) — 조항이 없다고 후보가 틀린 것은 아니다.
    #:       좌표만 있고 `quote` 가 비면 원문을 못 붙인 것이다(DB 없음 · 인용 자격 없음 · 쪼갠 조각) — 좌표는 표가 정한 값이다.
    references: list[EvidenceArticle] = Field(default_factory=list)
    #: 🆕 2026-10-15 (D-340 결정 5 · D-346) — **추정 위험도**. `None` 이면 대상이 아니다 — 기록 판정(품목 미상) · 사전 유형이 있는
    #:    문장 · 표시 목록 밖의 (전제 · 유형)(`app/graph.py` `ESTIMATE_TYPES`). 대상인데 모르면 `RiskEstimate(floor=None)` 이다
    estimate: RiskEstimate | None = None


class UserFact(BaseModel):
    """**사용자가 확인한 사실** 하나 (🆕 2026-10-16 · D-348 보충 3 결정 4 · (가) 출처를 남기고 반영).

    ★ 결과 화면의 사실 확인 분기에서 사용자가 고른 것 — 재검수 요청에 실려 오고, 그 문장의 판정을 그 사실로 다시 낸다.
       책임은 사용자에게 있다 — 그래서 판정된 문장에 이 칸을 그대로 남긴다(`SentenceJudgment.user_facts` · 저장 `evidence.user_fact`).
    🚨 **검증이 아니다** — 시스템은 증빙을 대조하지 않는다(D-263 ⑥ 의 「검증된 분기」와 다르다). 화면은 「사용자 확인 전제」로 그린다(배지 ⬜).
    """

    #: 그 사실 주장이 있는 문장 글자 — 재검수의 문장과 정규화(공백 · NFKC)로 맞춘다. 문장 번호는 재분할로 바뀔 수 있어 쓰지 않는다
    text: str = Field(..., min_length=1)
    kind: FactKind
    #: 🔄 2026-10-16 (D-348 보충 5) — 답 셋 · 예 = 참 · 아니오 = 거짓 · 해당없음 = 이 문장은 그 사실을 주장하지 않는다(종전 `true: bool`)
    answer: Answer


class UserSubst(BaseModel):
    """**사용자가 답한 실증 여부** 하나 (🆕 2026-10-16 · D-348 보충 4 결정 3 · `UserFact` 의 실증 판).

    ★ 조건부 위반 문장(보류 · 실증 분기)에서 사용자가 「실증 자료가 있다 / 없다」를 고른 것 — 재검수 요청에 실려 오고 그 문장에만 반영한다.
    🚨 **검증이 아니다** — 자료를 대조하지 않는다. 책임은 사용자에게 있다 — 판정된 문장에 이 칸을 남긴다(`SentenceJudgment.user_subst`).
    ⛔ 특허 · 수상 · 인증은 실증 자료가 아니다(D-228) — 그 사실은 `UserFact` 로 답한다.
    """

    #: 그 주장이 있는 문장 글자 — `UserFact.text` 와 같은 규칙(정규화로 맞춘다 · 문장 번호는 쓰지 않는다)
    text: str = Field(..., min_length=1)
    #: 🔄 2026-10-16 (D-348 보충 5) — 답 셋 · 예 = 자료 있음 · 아니오 = 자료 없음 · 해당없음 = 실증이 필요한 주장이 아니다(종전 `has_evidence: bool`)
    answer: Answer
    #: 🆕 2026-10-21 (D-348 보충 39 결정 6 · 2 단계) **어느 주장(유형)의 자료인가** — 질문의 `SubstBranch.violation` 을 그대로 담는다.
    #:    🔴 비면 그 문장의 **첫 실증형 유형**의 답으로 읽는다(1 단계 · 보충 39 결정 5 — 유형을 담지 않는 종전 화면이 깨지지 않게)
    violation: Violation | None = None


class SentenceJudgment(BaseModel):
    """문장 하나의 판정. 상태 스키마 「판정 누적」이 그대로 이 모양이다."""

    sent_id: str
    text: str
    verdict: Verdict
    hold_reason: HoldReason | None = None
    #: 🔄 2026-10-08 (D-323 결정 3) — **사전 근거가 있는 유형만**: 확정의 위반 · 보류의 자격 없는 사전 적중(D-311 결정 4).
    #:    재판정 탈락 · 고쳐 쓰기 버튼 · 생성 서버에 넘기는 유형이 이 칸을 읽는다. ⛔ 인코더 후보는 `encoder_candidates` 로
    violations: list[Violation] = Field(default_factory=list)
    infeasibility: Infeasibility | None = None
    evidence: list[EvidenceArticle] = Field(default_factory=list)
    risk: RiskAssessment = Field(default_factory=RiskAssessment)
    #: 🆕 2026-10-08 (D-323 결정 1) — 인코더 유형 후보. 비어 있으면 인코더가 없거나 조용하다 — **「위반 없음」이 아니다** (D-220).
    #:    🔄 그래프의 `encode` 가 채운다(배선 10-09 · 판은 잠금 · D-333) — 인코더가 안 돌면(폴더 없음 · 잠금 밖) 빈 목록이다.
    encoder_candidates: list[EncoderTypeCandidate] = Field(default_factory=list)
    #: 🔄 근거 불일치는 상태가 아니라 **재생성 이벤트**다 (D-127)
    evidence_mismatch: bool = False
    #: 🆕 **판정 대상 아님** — 주장이 아닌 문장(섭취 대상 · 사업자 정보 · 의무 표기 · 구호 …) (D-275 · D-242 조건 D).
    #:    「특이사항 없음(R0)」과 가른다 — 안 본 것을 본 것처럼 말하지 않는다 (D-63).
    #:    🚨 **거래 조건(가격 · 할인 · 환불) 문장은 여기에 싣지 않는다** — 라벨의 조건 D 는 「식품표시광고법 판정 대상 아님」일 뿐
    #:       표시광고법의 대상이다(D-272 개정 ② · 2026-09-28 팀장 판정 (가)). W4 사항 판별이 그 문장을 표시광고법 노드로
    #:       보내기 전에는 `not_claim` 으로 내보내면 통과 쪽으로 샌다 (D-192 · 들어올 자리에 적는다)
    not_claim: bool = False
    #: 🆕 **뺄 구간** — 원문(raw) 좌표 · `label` 에 위반 유형 (D-278 · D-265). ⛔ 상향 근거 구간(`risk.evidence_span`)과 다른 칸이다
    spans: list[Span] = Field(default_factory=list)
    #: 🆕 **실증 분기** — B 실증형에만 (D-263 ④ · D-268)
    substantiation: SubstBranch | None = None
    #: 🆕 2026-10-01 **사실 확인 분기** — B 에만 (D-308 ④) · 실증 분기와 **다른 칸**이다
    fact_check: FactBranch | None = None
    #: 🆕 2026-10-16 (D-348 보충 3 결정 4) — 이 문장의 판정이 **사용자가 확인한 사실**로 정해졌다(출처 · 책임). 있으면 확정이고 사실 확인 분기는 없다
    #: 🔄 2026-10-16 (보충 4 「이어 묻기」) — 답한 사실이 여럿일 수 있다(특허 · 인증 …) · 하나에 답했고 조건이 남았으면 조건부 보류에도 실린다
    user_facts: list[UserFact] = Field(default_factory=list)
    #: 🆕 2026-10-16 (D-348 보충 4 결정 3) — 이 문장의 판정이 **사용자가 답한 실증 여부**로 정해졌다(출처 · 책임)
    #: 🔄 2026-10-21 (D-348 보충 39 결정 6 · 2 단계 · 팀장 (나)) — **답이 여럿일 수 있다**(섞인 유형 · 유형마다 하나) · 이 목록이 정본이다.
    #:    종전 칸 `user_subst` 는 이 목록의 첫 답을 보이는 **계산 칸**이다(아래 · 지금 화면 · 저장이 그대로 읽는다) — 입력에 `user_subst` 가 오면
    #:    목록으로 옮긴다(`_user_subst_in` · 종전 응답 · 저장 JSON · 종전 호출)
    user_substs: list[UserSubst] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _user_subst_in(cls, data: Any) -> Any:
        # 🆕 2026-10-21 (보충 39 결정 6) 종전 칸 `user_subst` 로 들어온 답을 목록으로 — 계산 칸은 입력에서 무시되므로(pydantic) 여기서 옮기지 않으면
        #    답이 **조용히 사라진다**(D-220). 둘이 함께 오고 어긋나면 거부한다 — 어느 쪽이 맞는지 정하지 않는다
        if not isinstance(data, dict) or "user_subst" not in data:
            return data
        data = dict(data)
        one = data.pop("user_subst")
        if one is None:
            return data
        many = data.get("user_substs") or []
        if not many:
            data["user_substs"] = [one]
            return data
        first = many[0]
        same = (first.model_dump() if isinstance(first, BaseModel) else first) == (
            one.model_dump() if isinstance(one, BaseModel) else one
        )
        if not same:
            raise ValueError(
                "user_subst 가 user_substs 의 첫 답과 다르다 — 정본은 목록이다 (보충 39 결정 6)"
            )
        return data

    def model_copy(
        self, *, update: dict[str, Any] | None = None, deep: bool = False
    ) -> SentenceJudgment:  # type: ignore[override]
        """🆕 2026-10-21 (인계 10-21 클론A §2 · 보충 39 결정 6) 계산 칸 `user_subst` 를 `update` 로 바꾸려 하면 거부한다.

        ⛔ pydantic 의 `model_copy(update=…)` 는 검증을 건너뛰고 계산 칸 이름은 그냥 버린다 — 답을 바꾼 줄 알았는데 **조용히 그대로**다(D-220).
           옮겨 주지 않고 막는다 — 정본은 목록 하나다(D-99) · 답을 바꿀 때는 `user_substs` 를 쓴다. 생성자 · JSON 입력은 `_user_subst_in` 이 옮긴다(종전 저장 JSON).
        """
        if update and "user_subst" in update:
            raise ValueError(
                "user_subst 는 계산 칸이다 — model_copy 로 바꾸지 않는다 · 답을 바꿀 때는 user_substs (보충 39 결정 6)"
            )
        return super().model_copy(update=update, deep=deep)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def user_subst(self) -> UserSubst | None:
        """🔄 2026-10-21 (D-348 보충 39 결정 6 (나)) 실증 답 목록의 첫 답 — 계산 칸(지금 화면 · 저장 · 평가가 읽는다) · 답이 없으면 None."""
        return self.user_substs[0] if self.user_substs else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hold_kind(self) -> HoldKind | None:
        """🆕 2026-10-21 (D-348 보충 36 결정 4) 보류의 종류 — 응답 JSON 에 실린다 · 보류가 아니면 None (`hold_kind` 함수 한 곳)."""
        return hold_kind(self)

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
    def _encoder_risk_has_basis(self) -> SentenceJudgment:
        # 🆕 2026-10-16 (D-348 보충 2 결정 2 · 3) — 인코더 하한은 **보류 문장에만** · **근거 호가 있을 때만** 적는다.
        #    근거 = 인코더 후보의 참조 조항(대응표의 호 · D-327). 근거 없는 등급을 내지 않는다 (D-224 · D-220).
        #    ⛔ 확정 · 판정 대상 아님에는 적지 않는다 — 사전 확정과 인코더 다른 유형은 합치지 않는다(D-340 결정 3) ·
        #       주장이 아닌 문장은 R0 이다(D-275). 확정에 들이는 층(신뢰 규칙)이 판정되면 이 규칙을 그 결정으로 넓힌다
        if self.risk.encoder is None:
            return self
        if self.verdict is not Verdict.hold or self.not_claim:
            raise ValueError(
                f"인코더 하한은 보류 문장에만 적는다 — {self.verdict.value} (D-348 보충 2 결정 3)"
            )
        # 🔄 2026-10-16 (결정 10) — 근거는 위험도 자신이 든다(`RiskAssessment.encoder_basis`) · 표시용 후보(`encoder_candidates`)를 보지 않는다
        if not self.risk.encoder_basis:
            raise ValueError(
                "인코더 하한의 근거 호(encoder_basis)가 없다 (D-348 보충 2 결정 2 · 10)"
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
        # 🔄 2026-10-16 (D-348 보충 4 결정 1) — 확정 문장이거나 **조건부 위반**(실증 여부를 몰라 멈춘 보류 · `premise_unknown`)에 붙는다
        # 🔄 2026-10-16 (D-348 보충 5) — 또는 **인코더 쪽 판정의 보류**(`low_conf`) — 인코더 판단은 답 없이 확정하지 않는다. 분기만 붙고
        #    조건부 위반이 아니다(`is_conditional` 은 `premise_unknown` 만)
        if self.verdict is Verdict.hold and self.hold_reason not in (
            HoldReason.premise_unknown,
            HoldReason.low_conf,
        ):
            raise ValueError(
                f"보류 문장의 실증 분기는 조건부 위반(premise_unknown) · 인코더 쪽 보류(low_conf)에만 붙는다 — {self.hold_reason} (D-348 보충 4 · 5)"
            )
        if self.verdict not in (Verdict.confirmed, Verdict.hold):
            raise ValueError(f"실증 분기가 {self.verdict.value} 문장에 붙었다 (D-348 보충 4)")
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
    def _fact_is_for_B(self) -> SentenceJudgment:
        # 🔄 2026-10-16 (D-348 보충 3 결정 1 · 5) — 사실 확인 분기는 **사실을 몰라 멈춘 보류**(`premise_unknown`)에 붙는다.
        #    ⛔ 종전 「확정 B 에만」(D-308 ④)은 사실을 모르는데 위반을 확정한 꼴이었다 — 사실이 참이면 위반이 아니다.
        #    확인 전 위험도(가장 나쁜 경우)가 있어야 · 상한은 그 아래 (`_subst_is_for_B` 와 같은 규칙) · 불가 사유는 묻지 않는다(질병 C 도 붙는다)
        # 🔄 2026-10-16 (보충 4 「이어 묻기」) — 답한 사실은 확정 문장에, 또는 **남은 조건이 있는 조건부 보류**(다음 사실 · 실증)에 실린다.
        #    같은 종류를 다시 묻지 않는다 · 같은 종류에 두 답이 없다
        if self.user_facts:
            kinds = [f.kind for f in self.user_facts]
            if len(set(kinds)) != len(kinds):
                raise ValueError(
                    f"같은 사실 종류에 답이 둘이다 — {[k.value for k in kinds]} (보충 4)"
                )
            pending = (
                self.verdict is Verdict.hold
                and self.hold_reason is HoldReason.premise_unknown
                and (self.fact_check is not None or self.substantiation is not None)
            )
            # 🔄 2026-10-16 (D-348 보충 5) — 인코더 쪽 보류(`low_conf`)에도 실린다 — 답 없이 확정하지 않는 쪽의 출처(남은 분기 · 해당없음 · ⬜ 아니오)
            enc = self.verdict is Verdict.hold and self.hold_reason is HoldReason.low_conf
            if self.verdict is not Verdict.confirmed and not pending and not enc:
                raise ValueError(
                    "사용자 확인 사실이 실린 문장은 확정 · 남은 조건이 있는 조건부 보류 · 인코더 쪽 보류다 (D-348 보충 3 결정 4 · 보충 4 · 5)"
                )
            if self.fact_check is not None and self.fact_check.kind in kinds:
                raise ValueError(
                    f"이미 답한 사실을 다시 묻는다 — {self.fact_check.kind.value} (보충 4)"
                )
        if self.user_subst is not None and (
            self.fact_check is not None
            or not (
                self.verdict is Verdict.confirmed
                or (self.verdict is Verdict.hold and self.hold_reason is HoldReason.low_conf)
            )
        ):
            raise ValueError(
                "사용자가 답한 실증 여부가 실린 문장은 확정이거나 인코더 쪽 보류이고 사실 확인 분기가 없다 (D-348 보충 4 결정 3 · 보충 5)"
            )
        if self.fact_check is None:
            return self
        if self.not_claim:
            raise ValueError("판정 대상 아님 문장에 사실 확인 분기가 붙었다 (D-275)")
        # 🔄 2026-10-16 (D-348 보충 5) — 인코더 쪽 보류(`low_conf`)에도 붙는다(조건부가 아니다 · 실증 분기와 같은 규칙)
        if self.verdict is not Verdict.hold or self.hold_reason not in (
            HoldReason.premise_unknown,
            HoldReason.low_conf,
        ):
            raise ValueError(
                "사실 확인 분기는 사실을 몰라 멈춘 보류(premise_unknown) · 인코더 쪽 보류(low_conf)에 붙는다 (D-348 보충 3 결정 1 · 보충 5)"
            )
        if self.risk.final is None:
            raise ValueError("사실 확인 분기가 있는데 확인 전 위험도가 없다 (D-72)")
        if self.fact_check.confirmed_max.level > self.risk.final.level:
            raise ValueError(
                "사실이 참일 때의 상한이 확인 전 위험도보다 높다 — 확인은 등급을 올리지 않는다 (D-263)"
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
    #:    🚨 미확정이면 `classify` 가 판별하고, 못 정하면 **분기는 언제나** 낸다 — `hold(cat_unknown)` 은
    #:       **미확정 ∧ 등급이 갈릴 때만**이다 (D-229 ⑥ · D-127 개정)
    #:       (D-127 의 사유코드 — 그 괄호가 「**D-61 분기 병렬 출력**」이라고 적어 두었다).
    #:    ⛔ **`max` 로 접지 않는다.** 접으면 분기가 사라진다 — `max` 는 **축 자체가 없어서 물어볼
    #:       수도 없는 것**(업종: 제조·판매·음식점)에만 쓴다 (D-227).
    category: Category | None = None
    #: 자격 축. 🔜 **기능성표시식품**(별표1 3호나목 단서 · 고시)은 여기도 `category` 도 아니다 —
    #:   **D-61 분기로 낸다.** 「본 제품은 건강기능식품이 아닙니다」는 고시 제6조①5호의 **의무 표시**
    #:   이지 자격이 아니다(함량 30% · 안전관리인증업소 제조가 요건) — D-228 의 특허와 같은 어법.
    has_recognized_function: bool = False
    recognition_no: str | None = None
    #: 🆕 2026-10-16 (D-348 보충 3 결정 4) — 사용자가 확인한 사실(수상 · 인증 · 원재료 …). 제품에 관한 사실이라 여기 싣는다
    #:    (`has_recognized_function` 과 같은 축 — 「이 문구를 쓸 자격 · 근거가 있는가」). 비면 사실을 모른다 = 가장 나쁜 쪽(D-263 ①)
    facts: list[UserFact] = Field(default_factory=list)
    #: 🆕 2026-10-16 (D-348 보충 4 결정 3) — 사용자가 답한 실증 여부(문장 단위). 비면 모른다 = 가장 나쁜 쪽(D-263 ①)
    substs: list[UserSubst] = Field(default_factory=list)
    #: 🆕 2026-10-21 (D-348 보충 34 결정 1) — 사용자가 **고른 전제**(하위 전제까지 · 예: 건기식_인정). 비면 고르지 않았다.
    #:    🔴 `has_recognized_function` 으로 대신하지 않는다 — 기본값 거짓이 「안 줬다」와 「인정 없음이라고 줬다」를 가르지 못한다(D-72 와 같은 꼴).
    #:    고르면 그래프는 그 전제 하나로 판정한다(`app/graph.py` `premise_branches` · 분기 없음). 품목은 전제의 품목이어야 한다(아래 검증).
    #:    🚨 검증이 아니다 — 사용자의 자기 신고다(책임은 고른 사람 · 출처는 화면의 이력이 남긴다 · D-61 · 보충 3 결정 4).
    premise: Premise | None = None

    @model_validator(mode="after")
    def _premise_matches_category(self) -> ProductContext:
        # 🆕 2026-10-21 (보충 34) — 전제와 품목이 어긋나면 거부한다. 품목을 비우고 전제만 주면 전제의 품목으로 채운다(전제가 품목을 정한다)
        if self.premise is None:
            return self
        from app import premise as pm  # noqa: PLC0415 — app.premise 가 이 모듈을 읽는다(순환)

        cat = pm.PREMISE_CATEGORY[self.premise]
        if self.category is None:
            self.category = cat
        elif self.category is not cat:
            raise ValueError(
                f"고른 전제 {self.premise.value} 는 품목 {cat.value} 의 전제다 — 품목 {self.category.value} 와 어긋난다 (D-348 보충 34)"
            )
        return self


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
    #: 🆕 2026-10-20 (D-348 보충 32 결정 3) 두 겹 안내 — 이 전제가 무엇인지 · 어떻게 확인하는지(승인된 것만 · 없으면 None · 표시 전용)
    guide: Guide | None = None


class JudgeResponse(BaseModel):
    """**검수(진입점 A) 응답.** 🚨 검수는 대체 문구를 내지 않는다 — `candidates` 는 늘 빈 목록 (D-265).

    🔄 2026-09-23 (D-274 ~ D-278) — 품목 · 미검수 법 · 분기 칸이 섰다. 기록되는 판정은 `sentences` 다 (D-263 ①).
    """

    outcome: Outcome
    #: 🆕 **판별된 품목** — 판정 결과에 속한다 (D-82 · D-277). `None` = 미확정 → 세 법 + 분기 (D-229 ⑥)
    category: Category | None = None
    #: 🆕 2026-10-02 **품목의 출처** — 판별(`classified`) · 사용자 선택(`user_selected`). 품목이 있으면 출처가 있다 (D-276 ⑥)
    category_source: CategorySource | None = None
    #: 🆕 **미검수 법** — 「○○법 미검수」. 품목이 `UNCOVERED_CATEGORIES` 면 비지 않는다 · 제거할 수 없다 (D-271 ⑤ · D-277)
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
    #: ⛔ **폐기 예정 — 새 코드는 이 칸을 읽지 않는다** (D-103 ③ 개정 2026-10-14). 법령 판(날짜 하나)을 정하지 않는다 —
    #:    개정 영향은 판정 시각 + 인용한 법 + 수집 원장(`fetched_at`)으로 계산한다. 계약 · DB · 화면에서 빼는 것은 W10 흡수 뒤
    law_version: str = LAW_VERSION_UNKNOWN
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
        # 🆕 2026-09-21 (전수 재검토 I2) — 검수의 통과는 문장이 전부 통과여야 한다 (D-125 ·
        #    🔄 D-273 「통과 = 확정 ∧ R0」). ⛔ 종전에는 미판정·R3 문장이 섞인 `pass` 도 계약을 지났다 — 라우터가
        #    위험도를 안 봐도(I1) 여기서 못 잡았다.
        #    🔄 2026-09-29 — 종전 조건 `attempt == 0` 을 걷었다. 검수에는 라운드가 없어(D-265 · `_review_has_no_rounds`)
        #    `attempt ≥ 1` 의 `pass` 가 이 검사를 건너뛰는 구멍이었다(미판정 문장 + attempt=1 → pass 가 계약을 지났다).
        if self.outcome is Outcome.passed:
            bad = [s.sent_id for s in self.sentences if not is_pass(s)]
            if bad:
                raise ValueError(
                    f"outcome=pass 인데 통과가 아닌 문장이 있다 — {bad[:5]} (D-125 · D-273 · 확정 ∧ R0)"
                )
        return self

    @model_validator(mode="after")
    def _review_has_no_rounds(self) -> JudgeResponse:
        # 🆕 2026-09-29 (D-265 집행) — **검수는 한 번 판정하고 끝난다.** 재생성 루프는 생성(진입점 B)의 것이다 (D-266).
        #    ⛔ 칸은 0~K 를 받고 있었다 — 화면(`review.html` 「라운드」)이 읽는 칸이라 지우지 않고 0 으로 묶는다.
        if self.attempt != 0:
            raise ValueError(
                f"검수 응답의 attempt 가 {self.attempt} 다 — 검수에는 재생성 라운드가 없다 (D-265 · D-266)"
            )
        return self

    @model_validator(mode="after")
    def _guidance_payload(self) -> JudgeResponse:
        # 🆕 D-268 — 「지시」는 확정된 **B 실증형** 위반의 종착이다. 우선순위 보류 > 증명서 > 지시 > 통과 대로 —
        #    하나라도 확정이 아니면 보류 · A·C 가 섞이면 증명서다.
        #    사용자가 받는 것 = **뺄 구간 · 실증 자료 종류 · 내려갈 수 있는 등급** (D-265 표) — 없으면 지시가 빈 카드다.
        if self.outcome is not Outcome.guidance:
            return self
        # 🔄 2026-10-16 (D-348 보충 4 결정 2) — 조건부 위반(답하면 확정되는 보류)은 지시를 막지 않는다 · 그 밖의 확정 아님은 보류다
        if not self.sentences or any(
            s.verdict is not Verdict.confirmed and not is_conditional(s) for s in self.sentences
        ):
            raise ValueError(
                "outcome=guidance 인데 확정도 조건부 위반도 아닌 문장이 있거나 문장이 없다 — 보류다 (D-268)"
            )
        reasons = {s.infeasibility for s in self.sentences if s.infeasibility}
        if reasons & {Infeasibility.A, Infeasibility.C}:
            raise ValueError("outcome=guidance 인데 A·C 가 섞였다 — 증명서다 (D-268 우선순위)")
        subst = [s for s in self.sentences if s.infeasibility is Infeasibility.B and s.violations]
        if not subst:
            raise ValueError("outcome=guidance 인데 확정된 B 실증형 위반이 없다 (D-268)")
        # 🔄 2026-10-17 (D-348 보충 5 결정 5 · 1-b) — 사실이 거짓으로 확정된 문장(사용자 「아니오」)은 실증으로 풀리지 않는다 —
        #    실증 분기 없이 지시(「사실과 다른 표시 — 고치거나 빼기」)다. 뺄 구간은 그대로 필요하다
        thin = [
            s.sent_id
            for s in subst
            if (s.substantiation is None and not fact_false(s)) or not s.spans
        ]
        if thin:
            raise ValueError(
                f"지시 문장에 실증 분기나 뺄 구간이 없다 — {thin[:5]} (D-268 · D-265 · D-278)"
            )
        return self

    @model_validator(mode="after")
    def _recorded_is_conservative(self) -> JudgeResponse:
        # 🆕 D-263 ① · D-276 결정 2 — **기록되는 판정은 가장 보수적인 경우다.** 검증 안 된 분기가 기록을 낮추지 못한다.
        #    검증된(인정번호 대조) 분기는 많아야 하나 — 그때는 기록이 그 분기를 따른다 (D-263 ⑥).
        # 🔄 2026-10-21 (근거 정정 · D-348 보충 33 · 인계 10-21 클론B §0-3) — 이 검증기가 지키는 것은 **위험도**다(D-348 결정 4 · D-263 ① 의
        #    위험도 쪽). 판정(확정 · 보류)은 보충 33 으로 「답 대기 · 판정은 답 뒤」라 가장 나쁜 쪽을 가정해 확정하지 않는다 —
        #    기록 판정과 분기의 짝은 `app/graph.py` `_invariant`(보충 35 결정 1)가 본다.
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
        #    ⬜ D-229 ⑥ 의 넓은 규칙 「품목 미확정이면 분기는 언제나」는 아직 검증기로 올리지 않았다. 분기는 이제
        #       `app/graph.py` `premise_branches` 가 만들지만(D-319) DB 가 없거나 기준 문안이 비면 분기를 내지 않는다 —
        #       지금 걸면 그 응답이 깨진다 (D-192).
        premise_holds = {HoldReason.cat_unknown, HoldReason.premise_unknown}
        # 🔄 2026-10-16 (D-348 보충 3) — 사실을 몰라 멈춘 문장은 그 문장의 사실 확인 분기가 선택지다(품목 분기가 없어도 된다)
        if (
            any(s.hold_reason in premise_holds and not _own_choice(s) for s in self.sentences)
            and not self.branches
        ):
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
        # 🔄 2026-10-02 — `일반상품` 도 같다(`UNCOVERED_CATEGORIES`). 주된 광고법을 안 본 품목은 통과를 내지 않는다
        uncovered = self.category in UNCOVERED_CATEGORIES
        if uncovered != bool(self.not_reviewed):
            raise ValueError(
                "주된 광고법을 안 본 품목(전용법_미수록 · 일반상품)이면 미검수 법이 있고, 아니면 없다 (D-271 ⑤ · D-277) — "
                f"category={self.category} not_reviewed={self.not_reviewed}"
            )
        if uncovered and self.outcome is Outcome.passed:
            raise ValueError(
                "주된 광고법을 안 본 품목에 통과를 냈다 — 안 본 법이 있다 (D-271 ⑤ · D-63)"
            )
        if not uncovered and any(s.hold_reason is HoldReason.law_uncovered for s in self.sentences):
            raise ValueError("law_uncovered 보류는 주된 광고법을 안 본 품목에서만 난다 (D-277)")
        return self

    @model_validator(mode="after")
    def _category_has_source(self) -> JudgeResponse:
        # 🆕 2026-10-02 (D-276 ⑥) — 품목이 있으면 출처가 있고 없으면 없다. DB `ck_judgment_category_source_pair` 와 같은 규칙 (D-99).
        #    ⛔ 출처가 비면 화면이 「판별된 품목」과 「사용자가 고른 품목」을 못 가른다 — 고른 값에 통과 배지가 붙는다.
        if (self.category is None) != (self.category_source is None):
            raise ValueError(
                "품목과 품목 출처는 함께 있거나 함께 없다 (D-276 ⑥) — "
                f"category={self.category} category_source={self.category_source}"
            )
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


def _own_choice(s: SentenceJudgment) -> bool:
    """문장 자신이 선택지(사실 확인 분기 · 실증 분기)를 든 보류인가 — 품목 분기가 없어도 된다 (D-348 보충 3 · 4)."""
    return s.fact_check is not None or s.substantiation is not None


def fact_false(s: SentenceJudgment) -> bool:
    """사용자가 사실을 **거짓**으로 답한 문장인가 (🆕 2026-10-17 · D-348 보충 5 결정 5) — 그 위반은 실증으로 풀리지 않는다(지시 문안 · 종착 검증이 쓴다 · D-99)."""
    return any(f.answer is Answer.아니오 for f in s.user_facts)


def encoder_judged(s: SentenceJudgment) -> bool:
    """**인코더 판정**으로 확정된 위반인가 — 사전 근거(`basis`)도 사용자 답도 없는 확정 위반 (🆕 2026-10-17 · D-348 보충 6 결정 5).

    인코더 쪽 절대형(C) 위반이 이 꼴이다. 화면 · 기록이 「AI 판정 · 신뢰 판단 대기」 출처를 가릴 때 쓴다(정의는 여기 한 곳 · D-99).
    """
    return (
        s.verdict is Verdict.confirmed
        and bool(s.violations)
        and not any(e.basis for e in s.evidence)
        and not s.user_facts
        and s.user_subst is None
    )


def is_conditional(s: SentenceJudgment) -> bool:
    """**조건부 위반** — 글 밖 사실(사실 · 실증 여부)을 몰라 멈춘 보류 ∧ 그 선택지가 문장에 있다 ∧ 가장 나쁜 경우의 위험도가 섰다
    (🆕 2026-10-16 · D-348 보충 4 결정 2).

    ★ 판정은 끝났다 — 답하면 확정된다. 확신 부족 보류(`low_conf`)와 다른 분류다(평가 · 화면 · 종착이 이 함수 하나를 쓴다 · D-99).
    🚨 위험도가 없으면 조건부 위반이 아니다 — 없음을 판정으로 세지 않는다 (D-72).
    """
    return (
        s.verdict is Verdict.hold
        and s.hold_reason is HoldReason.premise_unknown
        and _own_choice(s)
        and s.risk.final is not None
    )


def hold_kind(s: SentenceJudgment) -> HoldKind | None:
    """보류의 종류 (🆕 2026-10-21 · D-348 보충 36 결정 4) — 보류가 아니면 None. 순서가 뜻이다(앞이 이긴다).

    ① 문장에 질문이 섰다(`_own_choice`) → 답 대기 — 조건부 위반(`premise_unknown` + 선택지)도 여기다
    ② 품목 · 전제 보류(`cat_unknown` · `premise_unknown`) → 고르기 대기 — 분기가 선택지다
    ③ 확신 부족(`low_conf`) ∧ 후보가 있다(사전 후보 `violations` · 인코더 후보 · 인코더 근거) → 확인 못 함
    ④ 확신 부족 ∧ 후보가 없다 → 걸린 것 없음
    ⑤ 그 밖의 사유 → 그 밖(사유 코드를 읽는다)
    🚨 판정 대상 아님(`not_claim`)은 확정이라 보류가 아니다 · 미판정(`unjudged`)은 보류가 아니다(None).
    """
    if s.verdict is not Verdict.hold:
        return None
    if _own_choice(s):
        return HoldKind.awaiting_answer
    if s.hold_reason in (HoldReason.cat_unknown, HoldReason.premise_unknown):
        return HoldKind.awaiting_pick
    if s.hold_reason is HoldReason.low_conf:
        found = bool(s.violations or s.encoder_candidates or s.risk.encoder_basis)
        return HoldKind.unconfirmed if found else HoldKind.nothing_found
    return HoldKind.other


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
