"""app/graph.py — 판정 코어 서브그래프 + 진입점 그래프 (D-266 · D-124 walking skeleton).

  uv run python -m app.graph            # 스텁 한 바퀴(검수 · 생성)를 돌려 방문 순서를 찍는다

🔄 **2026-09-23 — 그래프를 갈랐다 (D-266).** 종전에는 상태 하나(`JudgeState`)·그래프 하나 안에서
   판정 뒤 B 실증형을 재생성 루프로 보냈다. D-265 로 **검수는 문구를 만들지 않으므로** 그 루프는
   검수 경로에 있으면 안 되는 가지가 됐다.

       core     (서브그래프)  split → classify → retrieve → match_dict → encode
                              → 법별 팬아웃(D-267) → merge_laws → judge → assess_risk → premise_branches(D-319)
                              → doc_rules
       review   (진입점 A)   core → route_review → certificate · guidance · hold · passed   ← 루프 없음
       generate (진입점 B)   keyword_screen → assemble → claim_ledger → rejudge → 루프(D-126)
                              🔄 2026-10-14 — 스텁이다 · 앱에서 부르는 곳이 없다(`build_generate`). 지금 도는 카피 생성(B)은
                              `app/routers/copygen`(D-332)이고 코어를 `app.api.judge` 로 부른다
       compose  (진입점 C)   상태만 — 이번 범위 밖 (계약만 · D-266)

🚨 **DB 도 모델도 없이 end-to-end 한 바퀴가 돈다** — Phase 0 게이트의 정의(D-124)는 그대로다.
   🔄 2026-10-06 — 판정 로직은 섰다: **인코더 전 규칙 판정**(`JUDGED_BY` · D-269) · 위험도 하한(`assess_risk`) ·
      품목 분기(`premise_branches`) · 증명서 조립(`_certificate_of` · D-320). DB 가 없으면 사전을 못 훑어 문장은 미판정이다.
      빈 노드는 `doc_rules` 와 생성(B)의 `keyword_screen` · `claim_ledger` · `rejudge` 다(`assemble` 은 라운드 수만 센다).
   🔄 2026-10-07 — `encode` 는 모델 폴더가 설정되면(`COPYLANE_MODEL_DIR`) 문장마다 인코더 신호를 상태(`encodings`)에 싣는다.
   🔄 2026-10-09 (D-323 집행) — 그 신호가 응답에 나간다: 문장의 **`encoder_candidates`**(유형 · 확신) 한 칸에만.
      🚨 판정(확정 · 보류 · `violations` · 하한 · 분기 열쇠)은 그 칸을 **읽지 않는다** — 여전히 인코더 전 규칙 판정이다(`JUDGED_BY`).
   🔄 2026-10-14 (D-337) — 확정된 B 실증형에 실증 분기(`_substantiated`)가 붙으면 종착 `guidance` 가 선다.
   🔄 2026-10-18 (D-348 보충 20) — 사전 쪽 실증 분기는 걷었다(사전은 칸 C 만 확정) · 지시 종착의 재료는 인코더 쪽 실증 답(「없음」 → 확정)이다.

★ D-124 가 정한 검사 셋도 그대로다 —
   ① **라우터 함수는 그래프 없이 단독 테스트한다** → langgraph 를 **모듈 최상단에서 import 하지 않는다.**
   ② **스텁 노드로 컴파일해 방문 순서를 본다** → `run_review_stub` · `run_generate_stub` 이 langgraph 없이
      같은 순서를 낸다. 컴파일본이 그 순서와 같은지 게이트가 본다.
   ③ **리듀서 키를 따로 확인한다** → 누적 키 표는 `STATE_REDUCERS` **한 곳**이다 (D-99).

🔴 **코어 서브그래프를 그대로 노드로 끼우지 않는다 — 함수 노드가 부른다** (2026-09-23 실측 · 리눅스 컨테이너 ·
   langgraph 1.2.11). ⛔ 컴파일한 서브그래프를 `add_node("core", core)` 로 끼우면 **부모에 이미 있던 누적 키 값이
   두 번 쌓였다** — 부모 `timings=[pre]` 를 넣었더니 `[pre, pre, …]` 가 나왔다. 서브그래프가 받은 값을 **자기 최종
   상태째** 돌려주고, 부모가 그것을 리듀서로 **또** 더하기 때문이다. 오류는 안 난다.
   ★ 그래서 `CORE_IN` 만 넣고 `CORE_OUT` 만 꺼내는 함수 노드로 부른다. 입출력이 표로 보인다.
   🚨 D-206 — 이 실측은 **리눅스**다. Windows 판은 게이트(`test_코어를_지나도_누적_키가_두_번_쌓이지_않는다`)가 잰다.

🔴 **스텁은 비어 있는 것이지 틀린 것이 아니다.** 각 노드는 자기 자리에 무엇이 올지 적어 두고
   상태를 그대로 넘긴다. ⛔ 그럴듯한 값을 지어 넣으면 그 값이 화면으로 흘러가고,
   진짜가 붙을 때 무엇이 바뀌었는지 아무도 모른다 (D-147 의 그래프 판).
"""

from __future__ import annotations

import functools
import logging
import operator
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Annotated, Any, TypedDict

from app import claimscope, factcheck, sanction, sentsplit
from app import dictmatch as dm
from app import encoder as enc
from app import premise as pm
from app import reasons as rs
from app import retrieve as rt
from app.contracts import (
    ENCODER_RECORD_MAX,
    LAW_VERSION_UNKNOWN,
    NOT_REVIEWED_UNNAMED,
    UNCOVERED_CATEGORIES,
    AdaptedCopy,
    AdFormat,
    AdSection,
    Answer,
    Branch,
    Candidate,
    Category,
    CategorySource,
    Certificate,
    EncoderBasis,
    EncoderTypeCandidate,
    EvidenceArticle,
    FactBranch,
    FactKind,
    GenerateOutcome,
    HoldReason,
    Infeasibility,
    JudgeResponse,
    KeywordScreen,
    MediaProfile,
    Outcome,
    Premise,
    ProductContext,
    Risk,
    RiskAssessment,
    RiskEstimate,
    Segment,
    SentenceJudgment,
    Span,
    SubstBranch,
    Timing,
    UserFact,
    UserSubst,
    Verdict,
    Violation,
    is_conditional,
    is_pass,
)
from app.settings import PARAMS
from collect import statute
from collect.law_map import LAW_OF_ID, LAWS, REFERENCE_ONLY

#: D-126 — 총 라운드 K+1=3. `attempt` 는 0-base 이므로 마지막 시도는 2 다
MAX_ATTEMPT = PARAMS.max_attempt  # 🔄 값은 app/settings.py — 계약·DB 가 같은 수를 든다


def sent_id(i: int) -> str:
    """문장 하나의 id. 🔴 **규칙이 한 곳에만 있다** (D-99).

    ⛔ 종전에는 `judge` 안에 `f"s{i}"` 가 박혀 있었고, `retrieve` 가 붙는 순간 **두 곳이
       같은 규칙을 각자 적게 된다.** 짝이 어긋나도 오류가 안 난다 — `judge` 가 근거를
       못 찾고 빈 목록을 낼 뿐이고, 응답은 그럴듯하다. 이 저장소가 사흘에 세 번 밟은 모양이다.
    """
    return f"s{i}"


# ══════════════════════════════════════════════════════════════════════
#  그래프 내부 운반체 — 계약(`app/contracts.py`)에 두지 않는다
# ══════════════════════════════════════════════════════════════════════
#
# ⛔ 저기는 밖과 맺은 계약이고 `tests/contract_surface.json` 이 지문을 잡는다 — 4인이 그 모양을 보고
#    화면을 붙인다. 아래 둘은 그래프 **내부 배선**이라 밖에서 볼 것이 아니다 (구현계획 §2-1 A · G).


@dataclass(frozen=True, slots=True)
class SentEvidence:
    """`retrieve` 가 문장 하나에 붙인 근거 — **노드 사이 운반체**다 (2026-09-13 · D-124 ③).

    🔴 **왜 생겼나** — 종전에는 `retrieve` 가 찾아 온 것을 놓을 칸이 상태에 **없었다.**
       ① 리듀서 없는 칸에 넣으면 문장이 여럿일 때 **마지막 하나만 남는다** ② `judge` 안에서 검색을
       다시 부르면 **코어가 두 벌이 된다** (D-99). 키가 있으면 계약이 선다.
    🚨 `vector`·`lexical` 을 같이 나른다 — **벡터가 죽은 채 어휘 결과만으로 찾으면 참고 조문이 반쪽인데
       응답은 그럴듯하다** (D-202).
    🔄 2026-10-15 (D-344 ④) — ⛔ 종전 「`hold` 로 보내는 근거가 이 둘이다」는 틀렸다. 읽는 노드가 없고, 보내지도 않는다 —
       검색은 **참고 조문**만 낸다. 확정 · 보류의 근거는 사전 적중과 그 인용이다(`_judge_one` · D-127 · D-269). 그래서 벡터가 죽어도
       판정은 같다. 까닭은 기기 단위(검색 임베딩 캐시 없음 · 임베딩 판 섞임)라 `doctor --env` ④-4 와 프로세스당 한 번 경고
       (`app/retrieve.py` `_warn_vector_off`)로 알린다 — 응답 칸은 두지 않는다(D-344 ④ (마)). 읽는 곳은 진단 도구(`graph_probe` ·
       `time_graph`)뿐이다.
    """

    sent_id: str
    #: 🔄 2026-09-28 (W4 · D-291) — **넓은 검색의 두 갈래 후보**(법마다 폭만큼 · `rt.wide`)를 섞지 않고 나른다.
    #:    법별 노드가 `rt.law_view()` 로 **자기 법 것만 골라 섞는다** — 섞은 뒤 거르면 순위가 뒤집힌다(사실원장 ㊲).
    #:    ⛔ 종전에는 여기 `articles`(전역 상위 `top_k` 5 를 좌표로 옮긴 것)가 있었다 — 세 법이 다섯 자리를 나눠 썼다.
    #:       좌표로 옮기는 일은 이제 법별 노드가 한다(`LawResult.articles`).
    vector_hits: tuple[rt.Hit, ...] = ()
    lexical_hits: tuple[rt.Hit, ...] = ()
    #: 두 갈래가 각각 돌았는가. 🔄 둘 다 False 여도 판정은 사전으로 선다 — 검색 근거(참고 조문)가 없을 뿐이다 (위 docstring · D-344 ④).
    #:    DB 가 없으면(커서 없음) 사전도 못 돌아 문장이 미판정이다 — 이 칸이 아니라 `scan.ran` 이 가른다.
    vector: bool = False
    lexical: bool = False
    #: 두 갈래 **후보 수의 합**(겹친 것은 두 번 센다 · 법을 합친 행 수 — 법마다 폭은 `rt.POOL`). 🚨 0 은 「안 겹쳤다」이고,
    #: `lexical=False` 는 「검색어를 못 만들었다」다 — 다른 사건이다 (D-202).
    pool: int = 0


#: 🆕 2026-10-14 (D-336) — 문장만 받는 판(카드 17)의 신호 표지. 품목 입력을 받지 않으므로 **어느 품목 입력에도 같은 신호**다
ANY_INPUT = "*"


@dataclass(frozen=True, slots=True)
class SentEncoding:
    """문장 하나의 **인코더 신호** (🆕 2026-10-07 · 그림자 배선). 🚨 판정이 아니다 — 유형 후보와 확신뿐이다 (D-131).

    ⛔ 판정(`_judge_one`) · 분기 열쇠 · 종착은 이 칸을 읽지 않는다. 읽는 쪽은 응답의 후보 칸으로 옮기는 `_encoder_candidates` 뿐이다.
       판정에 쓰는 규칙(합의 · 통과 · 후보를 어느 칸에 싣나)은 팀장 판정 뒤에 들어온다 — 그 자리는 `judge` 다 (D-192).
    ⛔ 문장 판정의 `violations` 에 섞지 않는다 — 그 칸은 고쳐 쓰기(`app/routers/user.py` 버튼 · sLLM 에 넘기는 유형 ·
       `_rejudge` 의 탈락 기준)가 읽는다. 섞으면 적법 문장에 버튼이 뜨고 고친 문구가 재판정에서 탈락한다.
    🔄 2026-10-08 (D-323) — 응답에 실을 자리가 정해졌다: `SentenceJudgment.encoder_candidates`(유형 · 확신). 배선(클론 B)은
       이 칸만 채운다 — 하한 · 확정 · 분기 열쇠(`_judgment_key`)에는 넣지 않는다 · 거름은 유형 단위(`pm.NO_HF_MISLEAD`)다.
    ✅ 2026-10-09 — 배선했다: `_encoder_candidates` 가 이 운반체를 계약 칸으로 옮긴다(`judge` · `_premise_sentences` · `_recorded`).
    """

    sent_id: str
    #: (유형, 확률) — 모델의 출력 순서 그대로. 문턱은 모델 폴더의 것이라 여기 싣지 않는다
    scores: tuple[tuple[str, float], ...]
    #: 문턱을 넘은 유형. 편입 대기 칸(문턱 > 1 · D-321)은 넘을 수 없어 들지 않는다
    candidates: tuple[str, ...]
    #: 문장이 길어 뒤가 잘렸다 — 잘린 부분은 인코더가 보지 않았다 (D-220)
    truncated: bool = False
    #: 🆕 2026-10-14 (D-336 · D-339 결정 5) — 이 신호를 낸 **품목 입력**(`pm.encoder_input` 의 글자). 품목 입력 판은 문장마다
    #:    입력 하나에 한 벌씩 싣는다(기록 판정의 입력 + 품목 분기들의 입력 · 한 배치). 문장만 받는 판은 `ANY_INPUT` 한 벌이다.
    #:    읽는 쪽은 `_encodings_for` 로 고른다 — 기록 판정은 요청 품목의 입력, 분기는 그 전제의 입력
    input: str = ANY_INPUT


def _encoder_inputs(category: Category | None) -> tuple[str, ...]:
    """이 요청에서 인코더에 넣을 품목 입력 (🆕 2026-10-14 · D-339 결정 5) — **기록 판정의 입력이 맨 앞**, 그 뒤에 품목 분기들의 입력.

    ★ 품목을 모르면 「모름」 + 식품 · 건기식 · 화장품 — 한 배치다(분기 여섯의 입력은 넷으로 모인다 · 일반상품 → 모름).
    ★ 품목을 알면 그 품목의 입력 하나다(전제가 둘이어도 품목 입력은 같다).
    """
    record = pm.encoder_input(category)
    return tuple(
        dict.fromkeys([record, *(pm.premise_input(p) for p in pm.PREMISES_OF.get(category, ()))])
    )


def _encodings_for(state: CoreState, category_input: str) -> dict[str, SentEncoding]:
    """문장 → 이 품목 입력의 신호 (🆕 2026-10-14 · D-336). 문장만 받는 판의 신호(`ANY_INPUT`)는 어느 입력에나 든다.

    🔴 그 입력의 신호가 없으면 그 문장은 비어 있다 — 다른 입력의 신호로 메우지 않는다(입력마다 문턱 · 확률이 다르다 · D-220).
    """
    return {
        e.sent_id: e for e in state.get("encodings", []) if e.input in (ANY_INPUT, category_input)
    }


@dataclass(frozen=True, slots=True)
class DictHit:
    """사전 항목 하나가 문장에서 울린 것 (🆕 2026-09-28 · W4). 🔴 **위험도 하한의 재료**다 — 판정이 아니다 (D-09 · D-127).

    `span` 은 **원문** 좌표 `[start, end)` — 뺄 구간(D-278)이 원문 위에 그려진다. 못 세우면 `None`(`app/dictmatch.py`).
    """

    term: str
    violation_type: str | None
    #: 근거 조문 인용(D-282 꼴). 🚨 법별 노드가 **제 법의 인용만** 남긴다(`statute.law_of`)
    basis: tuple[str, ...]
    span: tuple[int, int] | None
    #: 🆕 2026-10-18 (D-348 보충 16) — 단독판정 항목이었으나 **후보로 내린** 적중(칸이 C 가 아님 · 또는 확정 막기 가드에 걸림).
    #:    🔴 후보(`weak`)로만 실린다 · 판정 대상 아님(`claimscope.is_caution`)을 열지 못한다 — 위반 낱말이 주의 문맥에서 통과로 새지 않게
    demoted: bool = False


@dataclass(frozen=True, slots=True)
class DictScan:
    """문장 하나를 사전으로 훑은 결과. 🔴 **「안 돌았다」와 「안 걸렸다」를 가른다** (D-220 · D-202 의 사전 판).

    ⛔ 빈 목록 하나로 두면 DB 가 없어 못 훑은 것과 훑었는데 안 걸린 것이 같아진다. 🚨 **안 걸린 것도 「특이사항 없음」이 아니다** —
       인코더 전에는 사전에 안 걸린 문장이 보류다 (D-269). 그 판정은 `judge` 몫이고 여기는 사실만 나른다.
    """

    sent_id: str
    ran: bool = False
    hits: tuple[DictHit, ...] = ()
    #: 🆕 2026-10-02 (D-311 · D-273 ④) — **단독판정 자격이 없는** 항목의 적중(적법중첩 · 모호 · 비주장문맥).
    #:    🔴 확정의 재료가 아니다 — 보류 문장의 **유형 후보**로만 실린다(`_judge_one`). ⛔ 버리면 강등된 질병 이름이
    #:       「사전 침묵」과 같은 보류가 되어, 사용자에게 힌트가 없고 탐지 재현율을 잴 수 없다(원장 10-02 ⑤).
    weak: tuple[DictHit, ...] = ()


@dataclass(frozen=True, slots=True)
class Proviso:
    """적용 제외 목 하나 — **해당하면 위반이 아닌 경우** (🆕 2026-09-28 · 팀장 판정 (나) · D-238 개정).

    검색이 제외 목 청크를 찾으면 위반 근거 좌표는 부모 목으로 올리고(`rt.basis_citation`), 제외 목 자신은 이것으로 따로 나른다.
    🔴 판정은 이것을 **단서 조건**으로 읽는다 — 광고가 제외 요건(예: 특수의료용도식품)에 들면 부모 목 위반이 서지 않는다.
    🚨 제품 사실을 모르면 요건 충족 여부를 모른다 — 그 판단은 `judge` 몫이고 여기는 사실만 나른다 (D-127).
    """

    #: 제외 목 자신의 좌표 — 「[별표 1]제1호가목1)」
    citation: str
    #: 위반 근거로 올린 부모 목의 좌표 — 「[별표 1]제1호가목」
    parent: str
    law_id: str
    chunk_id: str


@dataclass(frozen=True, slots=True)
class LawResult:
    """법별 노드 하나가 낸 것 (D-267). `merge_laws` 가 모은다.

    🔄 **칸이 늘었다** — 근거(`articles`) · 사전 적중(`dict_hits` · `weak_hits`) · 단서(`provisos`). 전제 · 문장별 유형 · 하한은
       이 칸에 싣지 않는다 — `judge` · `assess_risk` 가 이 결과를 읽어 문장에 적고, 전제는 `premise_branches` 가 법별 결과를 전제의
       법 묶음으로 다시 읽어 계약 `Branch`(`Premise`)로 낸다(D-319). ⛔ 문자열로 전제를 따로 지으면 **두 벌**이 된다 (D-99).
    ★ 「이 법이 이 문장들을 봤다」(`sent_ids` — `merge_laws` 의 fail-closed 대조가 읽는다)와 🆕 **이 법이 고른 근거**(`articles` · W4)를 나른다.
    """

    law: str
    sent_ids: tuple[str, ...] = ()
    #: 🆕 2026-09-28 (W4 · D-291) — 문장별로 **이 법이 고른 근거**(`sent_id`, 근거들). 좌표를 못 세운 것은 없다(D-224).
    #:    🔴 `judge` 가 이것을 모아 문장의 근거로 붙인다 — 검색을 다시 부르지 않는다 (D-99).
    articles: tuple[tuple[str, tuple[EvidenceArticle, ...]], ...] = ()
    #: 🆕 2026-09-28 (W4) — 문장별로 **이 법의 근거를 가진 사전 적중**(`sent_id`, 적중들). 근거는 이 법 인용만 남는다.
    dict_hits: tuple[tuple[str, tuple[DictHit, ...]], ...] = ()
    #: 🆕 2026-09-28 (D-238 개정 (나)) — 문장별로 **근거에 딸린 적용 제외 목**(`sent_id`, 단서들). 부모 좌표가 `articles` 에 있다.
    provisos: tuple[tuple[str, tuple[Proviso, ...]], ...] = ()
    #: 🆕 2026-10-02 (D-311) — 문장별로 **이 법의 근거를 가진 자격 없는 적중**. `dict_hits` 와 같은 거름이다
    weak_hits: tuple[tuple[str, tuple[DictHit, ...]], ...] = ()


# ══════════════════════════════════════════════════════════════════════
#  상태 넷 (D-266) — 🚨 누적 키에는 반드시 리듀서가 붙는다
# ══════════════════════════════════════════════════════════════════════
#
# ⛔ `Annotated[..., operator.add]` 가 없으면 LangGraph 는 **마지막 노드의 값으로 조용히 덮어쓴다.**
#    문장이 여럿인데 마지막 문장만 남는 사고가 여기서 난다 — 오류가 안 나서 발견이 늦다 (D-124 ③).


def upsert_sentences(
    old: list[SentenceJudgment], new: list[SentenceJudgment]
) -> list[SentenceJudgment]:
    """`sentences` 의 리듀서 — **같은 `sent_id` 는 바꿔 끼우고, 새 것은 뒤에 붙인다** (🆕 2026-10-02 · W5).

    ★ 왜 `operator.add` 가 아닌가 — 문장 판정은 한 노드가 끝내지 않는다. `judge` 가 판정을 내고 `assess_risk` 가 같은 문장에
      위험도를 붙이며, 문서 규칙(`doc_rules` · W8)이 다시 보류로 바꾼다. 더하기만 하면 뒤 노드가 낸 문장이 **두 번째 줄**로 쌓여
      문장 수가 늘고, 앞 줄(위험도 없는 판정)이 그대로 종착으로 간다.
    🔴 순서는 **처음 들어온 자리**를 지킨다 — 바꿔 끼워도 문장 순서가 안 바뀐다. 서로 다른 `sent_id` 는 종전처럼 쌓인다(D-124 ③).
    """
    at = {s.sent_id: i for i, s in enumerate(old)}
    out = list(old)
    for s in new:
        if s.sent_id in at:
            out[at[s.sent_id]] = s
        else:
            at[s.sent_id] = len(out)
            out.append(s)
    return out


class CoreState(TypedDict, total=False):
    """판정 코어 (D-266). 상태 스키마 문서 「상태에 반드시 담을 것」의 판정 쪽이 이 모양이다."""

    # ── 입력 (`CORE_IN`) ────────────────────────────────────────────
    text: str
    product: ProductContext
    # ── 분할 · 라우팅 ────────────────────────────────────────────────
    sents: list[str]
    #: 🆕 D-267 — `classify` 가 정한 **이번에 적용할 법**. `route_laws` 가 이것으로 팬아웃하고
    #:    `merge_laws` 가 **보낸 법이 전부 돌아왔는지** 이것으로 대조한다. 덮어쓰는 칸이다(리듀서 없음).
    laws: tuple[str, ...]
    # ── 근거 검색 🔴 누적 (2026-09-13) ─────────────────────────────
    evidence: Annotated[list[SentEvidence], operator.add]
    # ── 사전 매칭 🔴 누적 (🆕 2026-09-28 · W4) — 문장마다 한 벌 ───────────
    dict_scans: Annotated[list[DictScan], operator.add]
    #: 🆕 2026-10-08 — 사전 근거 인용 → 원문이 붙은 근거 조문(`basis_texts`). `match_dict` **한 노드만** 쓴다(리듀서 없음).
    #:    비면 원문 없이 좌표만 간다 — 판정은 바뀌지 않는다 (D-224 ④).
    basis_texts: dict[str, EvidenceArticle]
    #: 🆕 2026-10-12 (D-327) — 참조 조항 좌표 → 원문이 붙은 조항(`reference_texts`). `match_dict` **한 노드만** 쓴다(리듀서 없음).
    #:    비면 좌표만 간다 — 좌표는 표(`collect/statute.py` `references`)가 정한 값이라 DB 없이도 선다.
    ref_texts: dict[str, EvidenceArticle]
    #: 🆕 2026-10-12 (D-328) — 판정 화면의 참고 조문으로 실어도 되는 별표 `(법 ID, 별표 번호)`. `retrieve` **한 노드만** 쓴다(리듀서 없음).
    #:    🚨 비거나 없으면 **별표를 하나도 싣지 않는다**(D-220) — 모르는 별표를 참고 조문으로 내지 않는다.
    #:    ⛔ frozenset 이 아니라 정렬한 튜플이다 — 체크포인터(D-129)가 상태를 직렬화한다.
    annex_scope: tuple[tuple[str, int], ...]
    #: 🆕 2026-10-12 (D-329) — 참고 조문으로 실어도 되는 **본문**의 `(법 ID, 조)` · 산문 고시는 `(법 ID, 장)`(🔄 D-293 개정 집행). `retrieve` **한 노드만** 쓴다.
    #:    🚨 비거나 없으면 본문을 하나도 싣지 않는다(D-220). ⛔ 정렬한 튜플이다 — 체크포인터(D-129)가 직렬화한다.
    body_scope: tuple[tuple[str, str], ...]
    # ── 인코더 신호 🔴 누적 (🆕 2026-10-07 · 그림자) — 문장마다 한 벌. 모델이 없으면 **비어 있다**(없음 ≠ 조용함)
    encodings: Annotated[list[SentEncoding], operator.add]
    # ── 법별 팬아웃 🔴 누적 (D-267) — 법 노드가 **병렬로** 쓴다. 리듀서가 없으면 하나만 남는다
    law_results: Annotated[list[LawResult], operator.add]
    # ── 판정 누적 🔴 누적 — 🔄 2026-10-02 같은 문장은 바꿔 끼운다(`upsert_sentences`) ─────────
    sentences: Annotated[list[SentenceJudgment], upsert_sentences]
    # ── 품목 분기 (🆕 2026-10-05 · D-319 · D-263 ⑦) — `premise_branches` **한 노드만** 쓴다. 덮어쓰는 칸이다(리듀서 없음)
    branches: list[Branch]
    # ── 계측 (D-77 · D-43 이 LangSmith 를 배제해 이것이 유일한 경로) 🔴 누적 ──
    timings: Annotated[list[Timing], operator.add]


class ReviewState(CoreState, total=False):
    """검수 (진입점 A · D-266). 코어 출력 + 종착.

    🔴 **재생성 키가 없다** — `attempt`·`rejects`·`rejected` 는 생성 상태로 옮겼다 (D-265 · D-266).
       검수에서는 늘 0 인 칸이었고, 칸이 있으면 누군가 쓴다.
    """

    outcome: Outcome
    #: 🆕 2026-10-02 (W5) — 합법화 불가 증명서(D-32). 🔄 2026-10-06 (D-320) — 조립기가 섰다: `certificate` 종착이
    #:    `_certificate_of` 로 지어 이 칸에 적는다. 승인된 사유 문안이 없는 조합이면 칸이 비고 종착은 보류로 내린다 (D-220).
    certificate: Certificate


class GenerateState(TypedDict, total=False):
    """카피 생성 (진입점 B · D-181 · D-264 · D-266).

    ⬜ 상태 스키마 문서는 「페르소나 **목록**(팬아웃)」이라 적었고 계약 `GenerateRequest` 는 `segment` **하나**다.
       **계약을 따른다** — 페르소나 팬아웃은 D-270 으로 **설계만**이다.
    """

    segment: Segment
    product: ProductContext
    #: 허용/차단 + **사유**. 🔴 누적 — 키워드마다 노드가 갈릴 수 있다
    keywords: Annotated[list[KeywordScreen], operator.add]
    #: 프론티어 후보 N=3 (D-31 · D-34). 🚨 「프론티어 점수」를 따로 두지 않는다 — `Candidate` 의 칸이다 (D-99)
    candidates: Annotated[list[Candidate], operator.add]
    # ── 재생성 루프 (D-126) — 🔄 D-266 으로 검수에서 이리로 왔다 ──────────
    #: 0-base · **첫 조립이 0 이다.** 거부 3종(주장 원장·인용 검증·사후 대조)은 **한 카운터**를 쓴다
    attempt: int
    rejects: Annotated[list[str], operator.add]  # 🔴 누적 — 실패 사유 (보고용 · 모든 시도)
    #: **이번 시도**가 거부됐는가. 시도마다 덮어쓴다 — 그래서 리듀서가 없다 (전수 재검토 I3)
    rejected: bool
    #: 매체 프로파일 — **B 의 후단**에 산다 (D-181). 🔜 각색은 D-270 으로 설계만
    profile: MediaProfile
    #: 채널별 각색. 🚨 각 결과가 **판정 코어를 다시 지난다** (D-119 · D-63)
    adapted: Annotated[list[AdaptedCopy], operator.add]
    #: 🔄 D-274 — 생성 종착은 검수와 **다른 목록**이다 (프론티어 · 탐색 실패 · 보류)
    outcome: GenerateOutcome
    timings: Annotated[list[Timing], operator.add]


class ComposeState(TypedDict, total=False):
    """AI 광고 생성 (진입점 C · D-164 · D-181). 🔜 **그래프가 없다** — 이번 범위 밖 (D-266)."""

    ad_format: AdFormat
    #: 지면 섹션. 🔴 누적 — 섹션마다 판정이 붙는다
    sections: Annotated[list[AdSection], operator.add]


#: 상태별 누적 키 — 게이트가 **양쪽으로** 본다: 여기 적힌 키에 리듀서가 있는가 · 리듀서가 붙은 키가 여기 다 있는가.
#: 🚨 **키를 늘리면 여기 한 줄만 늘린다** (D-99).
STATE_REDUCERS: dict[str, tuple[type, tuple[str, ...]]] = {
    "core": (
        CoreState,
        ("evidence", "dict_scans", "encodings", "law_results", "sentences", "timings"),
    ),
    "review": (
        ReviewState,
        ("evidence", "dict_scans", "encodings", "law_results", "sentences", "timings"),
    ),
    "generate": (GenerateState, ("keywords", "candidates", "rejects", "adapted", "timings")),
    "compose": (ComposeState, ("sections",)),
}

#: 🆕 2026-10-02 (W5) — 누적 키의 리듀서. **표에 없는 키는 `operator.add`** 다. 게이트와 스텁(`_apply`)이 이 표로 읽는다 (D-99).
REDUCER_OF: dict[str, Callable[[list[Any], list[Any]], list[Any]]] = {"sentences": upsert_sentences}


def reducer_of(key: str) -> Callable[[list[Any], list[Any]], list[Any]]:
    return REDUCER_OF.get(key, operator.add)


#: 코어 입출력 — 함수 노드가 **이것만** 넣고 **이것만** 꺼낸다 (모듈 docstring 의 실측 참조).
CORE_IN = ("text", "product")
CORE_OUT = (
    "sents",
    "laws",
    "evidence",
    "dict_scans",
    "encodings",
    "law_results",
    "sentences",
    "branches",
    "timings",
)


# ══════════════════════════════════════════════════════════════════════
#  계측 — 데코레이터 하나 (D-77 ⑥ 「공수는 데코레이터 하나 + 상태 필드 하나다」)
# ══════════════════════════════════════════════════════════════════════


def timed(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """노드 진입·종료 시각을 상태에 적재한다.

    🔴 **`functools.wraps` 가 여기서는 장식이 아니라 배선이다** (2026-09-14 실측).
       LangGraph 는 **노드의 시그니처를 보고** `config` 를 넘길지 정한다. `wraps` 가 `__wrapped__` 를 달아
       원래 모양이 보이게 한다. ⛔ 빠지면 커서가 조용히 `None` 이 되고 「DB 없음」 경로로 떨어진다.
    """

    @functools.wraps(fn)
    def wrapped(state: dict[str, Any], *rest: Any, **kw: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        out = fn(state, *rest, **kw)
        ms = (time.perf_counter() - t0) * 1000
        out.setdefault("timings", [])
        out["timings"] = [*out["timings"], Timing(node=fn.__name__, ms=ms)]
        return out

    return wrapped


# ══════════════════════════════════════════════════════════════════════
#  법별 라우팅 (D-267) — 순수 함수. 🚨 그래프 없이 단독으로 테스트한다 (D-124 ①)
# ══════════════════════════════════════════════════════════════════════

#: 법별 노드가 받는 품목. `None` = **모든 품목** (표시광고법은 품목과 무관하게 걸린다).
#: 🔄 **D-271 — 「일반」은 없다.** `일반상품`(기획서 2-4 「일반 상품」)과 `전용법_미수록` 은 **표시광고법만** 탄다 —
#:    두 품목 모두 아래 어느 법의 범위에도 없어서 `law_ftc` 하나로 떨어진다. 전용법 품목은 통과 금지 · 미검수 고지다 (D-277).
#:    ⛔ **청크의 `law`(법 축)와 섞지 않는다** — 🔄 W6(0019)로 청크 칸이 `category` → `law` 가 됐다(D-271 ①).
#:       🔄 2026-09-28 (W4) — 법별 노드가 자기 법 근거만 거른다 · 노드 이름 ↔ 법 축은 아래 `LAW_OF_NODE`.
#: 🚨 **순서가 곧 팬아웃 순서다** — 스텁과 컴파일본이 같은 순서를 낸다(`Send` 목록 순서 · 2026-09-23 실측).
LAW_SCOPE: dict[str, frozenset[Category] | None] = {
    "law_ftc": None,
    "law_food": frozenset({Category.식품, Category.건기식}),
    "law_cosmetic": frozenset({Category.화장품}),
}
LAW_NODES = tuple(LAW_SCOPE)

#: 🆕 2026-09-28 (W4) — 법별 노드 ↔ **법 축**(`collect/law_map.LAWS` · 청크의 `law` 칸). 노드는 이 법의 근거만 거른다.
#: 🔴 **건강기능식품법은 노드가 없다** — 참고 전용이라 위반 근거로 보내지 않는다 (D-271 ⑥ · `REFERENCE_ONLY`).
#:    ⛔ 종전에는 `REFERENCE_ONLY` 를 읽는 곳이 없었고 `judge` 가 전역 검색 결과를 전부 근거로 옮겨 건강기능식품법
#:       청크가 근거로 나갈 길이 열려 있었다(판정이 `unjudged` 라 해가 없었을 뿐). 게이트가 이 표를 두 방향으로 본다.
LAW_OF_NODE: dict[str, str] = {
    "law_ftc": "표시광고법",
    "law_food": "식품표시광고법",
    "law_cosmetic": "화장품법",
}

#: 법별 노드 하나가 문장마다 받는 근거 수. 🚨 **`[임의]`** — `top_k`(5)를 법마다 쓴다. 받을 개수(k)는 판정 대기다
#:    (D-291 ⬜ · 사실원장 ㊳). 값을 바꾸면 판정 근거가 바뀐다 — 보고에 올린다.
LAW_TOP_K = PARAMS.top_k

# 🔴 표가 어긋나면 **import 에서 멈춘다** (D-220) — 법 축이 늘거나 노드가 늘었는데 한쪽만 고치면 그 법은 근거 없이 판정된다.
if set(LAW_OF_NODE) != set(LAW_NODES) or set(LAW_OF_NODE.values()) != set(LAWS) - REFERENCE_ONLY:
    raise RuntimeError(
        f"🔴 법별 노드 ↔ 법 축 표가 어긋났다 — 노드 {sorted(LAW_OF_NODE)} · 법 {sorted(LAW_OF_NODE.values())} · "
        f"위반 근거 법 {sorted(set(LAWS) - REFERENCE_ONLY)} (D-267 · D-271 ⑥)"
    )


def laws_for(category: Category | None) -> tuple[str, ...]:
    """이번에 적용할 법. **품목을 모르면(`None`) 전부** — 분기는 미확정이면 언제나 (D-229 ⑥).

    🚨 **빈 결과가 나올 수 없다** — 표시광고법(`scope=None`)이 늘 들어간다. 빈 팬아웃은 LangGraph 가
       **오류 없이 그래프를 끝낸다**(2026-09-23 실측 — `Send` 가 0개면 뒤 노드를 건너뛰고 END).
       그래서 `route_laws` 가 한 번 더 막는다.
    """
    return tuple(
        name
        for name, scope in LAW_SCOPE.items()
        if category is None or scope is None or category in scope
    )


def law_payload(state: CoreState) -> dict[str, Any]:
    """법별 노드에 보내는 것. 🔴 **컴파일본(`Send`)과 스텁이 같은 함수를 쓴다** (D-99).

    ⛔ `Send` 로 보낸 노드는 **이 dict 만** 본다 — 부모 상태 전체가 아니다. 여기 없는 키를 노드가 읽으면
       스텁에서는 돌고 컴파일본에서는 빈 값이 된다. 오류는 안 난다. 그래서 스텁도 이것만 넘긴다.
    """
    return {
        "sents": list(state.get("sents", [])),
        "product": state.get("product"),
        # 🆕 2026-09-28 (W4) — 법별 노드가 자기 법 근거를 거를 재료. ⛔ 빠지면 컴파일본의 노드는 빈 근거를 본다(오류 없음)
        "evidence": list(state.get("evidence", [])),
        # 🆕 2026-09-28 (W4) — 사전 적중도 법별로 가른다. ⛔ 빠지면 컴파일본의 노드는 적중이 없는 것으로 본다(오류 없음)
        "dict_scans": list(state.get("dict_scans", [])),
        # 🆕 2026-10-12 (D-328) — 참고 조문으로 실어도 되는 별표. ⛔ 빠지면 컴파일본의 노드는 별표를 하나도 안 싣는다(오류 없음 · 안전 쪽)
        "annex_scope": tuple(state.get("annex_scope") or ()),
        # 🆕 2026-10-12 (D-329) — 참고 조문으로 실어도 되는 본문. ⛔ 빠지면 컴파일본의 노드는 본문을 하나도 안 싣는다(오류 없음 · 안전 쪽)
        "body_scope": tuple(state.get("body_scope") or ()),
    }


def route_laws(state: CoreState) -> tuple[str, ...]:
    """팬아웃할 법 이름. 🚨 **비거나 모르는 이름이면 멈춘다** (D-220) — 빈 팬아웃은 조용히 그래프를 끝낸다."""
    laws = tuple(state.get("laws") or ())
    if not laws:
        raise RuntimeError(
            "🔴 적용할 법이 없다 — `classify` 가 `laws` 를 안 적었다. "
            "빈 팬아웃은 LangGraph 가 오류 없이 끝낸다 (D-267 · D-220)"
        )
    unknown = set(laws) - set(LAW_NODES)
    if unknown:
        raise RuntimeError(f"🔴 법별 노드에 없는 이름 — {sorted(unknown)} (D-267)")
    return laws


# ══════════════════════════════════════════════════════════════════════
#  코어 노드 — `doc_rules` 는 자리와 계약만 있다(빈 노드) · `encode` 의 신호는 후보 칸으로만 나간다(판정이 읽지 않는다 · D-323)
# ══════════════════════════════════════════════════════════════════════


@timed
def split(state: CoreState) -> dict[str, Any]:
    """문장 분할 — 전처리 사양 [P4](줄바꿈 · 이모지 · 해시태그 · 종결 부호 뒤 공백). 🔄 2026-10-01 (W4).

    ★ 규칙은 `app/sentsplit.py` 한 곳이다 (D-99). 문장은 원문의 부분 문자열이라 `judge` 가 원문 좌표를 되찾는다(D-278).
    ⛔ 종전 스텁은 원문 전체를 한 문장으로 넘겼다 — 여러 줄 광고의 문장별 판정 · 뺄 구간이 서지 않았다.
    🚨 경계 규칙은 `[관행]` — 분할 정답 셋이 없어 정확도(D-77 L1-1)는 미측정이다.
    """
    return {"sents": sentsplit.split(state["text"])}


@timed
def classify(state: CoreState) -> dict[str, Any]:
    """품목 판별 → **적용할 법**. 🚨 사용자에게 묻지 않는다 — 우리가 판별한다 (D-82).

    ★ 지금은 **받은 품목**으로만 법을 고른다 — 받은 것이 없으면(`None`) 세 법 전부다 (D-229 ⑥ · D-267).
       판별해서 지어내지 않는다. 🔜 `product_fact` 인정번호 대조 + 규칙으로 `None` 을 좁힌다 — 아직 없다.
    """
    product = state.get("product") or ProductContext()
    return {"laws": laws_for(product.category)}


#: ⛔ 🔄 2026-09-24 (W6 · D-271 ③) — 품목을 청크 범주로 넘기던 **임시 다리**(`_CHUNK_CATEGORY` · `_chunk_category`)를 지웠다.
#:    검색은 **법으로** 거르고 판정 그래프는 **넓게 한 번**(법 필터 없음) 찾는다 — 법별 노드가 자기 법 근거만 거른다(D-267).
#:    🚨 품목을 검색 필터로 넘기지 않는다 — 품목과 법은 다른 축이다(D-271 ④). 게이트가 `retrieve` 의 호출을 본다.


def _evidence_article(hit: rt.Hit) -> EvidenceArticle | None:
    """`Hit` → 계약. 🔴 **확신이 없으면 안 옮긴다** (D-224).

    ⛔ 위반 근거 좌표(`basis_citation`)가 `None` 이면 좌표를 못 세운 것이다 — 「제18조」로 줄여 적으면 실은 제3항인 근거를
       가리킨다. 지어내지 않고 **버린다.**
    🔄 2026-10-08 — `quote` 는 **원천의 `U3_cite` 가 열린 청크만** 싣는다(`hit.citable` · D-224 ④). 종전에는 그 자격을 읽지 않아
       늘 비웠다. ⛔ 제외 목에서 올린 좌표(`exempt_of`)는 이 청크의 글이 그 좌표의 글이 아니므로 싣지 않는다(`chunk_id` 와 같은 이유).
       ⛔ 쪼갠 조각(`part_total` ≠ 1)도 싣지 않는다 — 계약에 「일부다」를 말할 칸이 없어 조각이 조문 전문처럼 보인다(D-224 ③ · D-199).
          `None`(재적재 전)도 싣지 않는다 — 모르는 것을 전문으로 치지 않는다 (D-220).
    🔄 2026-09-28 (D-238 개정 (나)) — `citation` 이 아니라 `basis_citation` 을 옮긴다. 적용 제외 목이면 **부모 목의 좌표**가
       오고, 그 좌표를 가진 청크는 이 청크가 아니므로 `chunk_id` 를 비운다 — 제외 목의 글이 위반 근거 자리에 보이지 않게.
       제외 목 자신은 `_proviso()` 가 따로 나른다.
    🚨 `citation()` 을 다시 부르지 않는다 — `Hit` 이 생성 시점에 이미 들고 있다 (D-99).
    """
    if not hit.basis_citation or not hit.law_id:
        return None
    own = not hit.exempt_of
    whole = hit.part_total == 1
    return EvidenceArticle(
        law_id=hit.law_id,
        article=hit.basis_citation,
        item=hit.item or "",
        chunk_id=hit.chunk_id if own else None,
        quote=hit.text if own and whole and hit.citable is True and hit.text else None,
        doc_title=hit.doc_title,  # 🆕 2026-10-12 (D-293 개정 안건 3) — 산문 좌표는 고시 이름과 같이 가야 뜻이 선다
    )


def _proviso(hit: rt.Hit) -> Proviso | None:
    """적용 제외 목 청크 → 단서 (D-238 개정 (나)). 제외 목이 아니거나 좌표가 안 서면 `None`."""
    if not hit.exempt_of or not hit.citation or not hit.basis_citation or not hit.law_id:
        return None
    return Proviso(
        citation=hit.citation, parent=hit.basis_citation, law_id=hit.law_id, chunk_id=hit.chunk_id
    )


def _pick(hits: list[rt.Hit]) -> tuple[tuple[EvidenceArticle, ...], tuple[Proviso, ...]]:
    """법별 노드 하나가 문장 하나에 고르는 근거와 단서 (D-238 개정 (나)).

    🔴 **같은 위반 좌표는 한 번만** — 제외 목 여럿(1.가.1 · 1.가.2)이 같은 부모로 올라오거나 부모 청크 자신도 걸리면
       좌표가 겹친다. 먼저 나온 순서를 지키고, 부모 청크 자신이 있으면 그 줄(청크가 있는 줄)을 남긴다.
    🚨 자르는 개수는 **겹침을 걷어 낸 뒤** `LAW_TOP_K` 다 — 걷기 전에 자르면 같은 좌표가 자리를 먹는다.
    """
    arts: list[EvidenceArticle] = []
    where: dict[tuple[str, str], int] = {}
    provisos: list[Proviso] = []
    for h in hits:
        a = _evidence_article(h)
        if a is None:
            continue
        key = (a.law_id, a.article)
        if key in where:
            i = where[key]
            if a.chunk_id is not None and arts[i].chunk_id is None:
                arts[i] = a  # 부모 청크 자신이 뒤에 나왔다 — 청크가 있는 줄로 바꾼다
        else:
            if len(arts) >= LAW_TOP_K:
                continue
            where[key] = len(arts)
            arts.append(a)
        if (p := _proviso(h)) is not None:
            provisos.append(p)
    return tuple(arts), tuple(provisos)


@timed
def retrieve(state: CoreState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """조문 검색 — `app/retrieve.py` 의 `search()` 를 부른다 (✅ 2026-09-14 · 구현계획 §2-1 C).

    🔴 검색을 여기서 새로 쓰지 않는다 — 코어는 `app/retrieve.py` 하나다 (D-99 · D-51).
    🆕 **커서는 `config` 로 받는다** — 주석 없는 `config` 여야 LangGraph 가 넘긴다(2026-09-14 실측).
       ⛔ 노드가 스스로 `connect()` 하면 문장마다 연결이 열린다 · 상태에 담으면 체크포인터(D-129)가 깨진다.
    🔴 **DB 가 없어도 돈다** (D-124). 빈 dict 로 삼키지 않고 문장마다 「검색을 못 했다」를 값으로 남긴다 (D-220).
    🔴 **팬아웃 앞에서 한 번** 돈다 (D-267) — 법마다 다시 부르면 검색이 3~4배다.
       🔄 2026-09-24 (W6 · D-271 ③) — **법 필터 없이 넓게 한 번** 찾는다. ⛔ 종전에는 품목을 청크 범주로 넘겨
       미확정이면 「일반」만 봤다 — 식품·화장품 전용 조문을 못 봤다. 🔜 W4 — 법별 노드가 `law` 로 자기 근거만 거른다.
       🔄 2026-09-28 (W4 · D-291) — `rt.wide()` 를 부른다(법마다 폭만큼 · 두 갈래 따로). 법별 노드가 `rt.law_view()` 로
          자기 법 것만 골라 섞는다 — 법 필터로 따로 찾은 것과 후보가 같다(사실원장 ㊲ · ㊳ · ㊵ 124/124).
          ⛔ 종전에는 `search()`(전역 상위 `top_k` 5)를 불러 세 법이 다섯 자리를 나눠 썼다.
    🚨 `rt.RetrieveError` 는 여기서 삼키지 않는다 — 근거 없이 판정하면 D-224 위반이다.
    """
    sents = state.get("sents", [])
    if not sents:
        return {}
    cur = ((config or {}).get("configurable") or {}).get("conn")
    if cur is None:
        return {"evidence": [SentEvidence(sent_id=sent_id(i)) for i in range(len(sents))]}

    found: list[SentEvidence] = []
    for i, text in enumerate(sents):
        vec, lex, st = rt.wide(cur, text)
        found.append(
            SentEvidence(
                sent_id=sent_id(i),
                vector_hits=tuple(vec),
                lexical_hits=tuple(lex),
                vector=st.vector == rt.VECTOR_OK,
                lexical=st.lexical == rt.LEXICAL_OK,
                # 🔄 2026-09-21 — `st.pool` 은 후보 **폭**(늘 50)이라 갈래별 후보 수의 합을 넣는다
                pool=st.pool_vector + st.pool_lexical,
            )
        )
    # 🆕 2026-10-12 (D-328) — 참고 조문으로 실어도 되는 별표. 같은 커서로 요청마다 한 번 묻는다(`reference_texts` 와 같은 꼴)
    # 🆕 2026-10-12 (D-329) — 본문도 같은 커서로 한 번 (조문 표 · 고시 이름 · 상투 조문)
    return {"evidence": found, "annex_scope": annex_scope(cur), "body_scope": body_scope(cur)}


#: 사전 종류 — 🚨 `scripts/load_db.py` `DICT_KIND` 와 **같은 값**이다. ⛔ `app/` 이 `scripts/` 를 import 하지 않는다 —
#:    양쪽에 서로를 가리키는 주석을 두고 게이트(`test_사전_종류가_적재기와_같다`)가 대조한다 (D-99).
DICT_KIND = "금지표현"

#: 🚨 **단독판정 자격(`exact_match`)이 있는 항목만** 읽는다 — 적법중첩 · 모호는 단독으로 하한을 못 건다 (D-156 · 스키마 주석).
SQL_DICT = """SELECT term, violation_type::text, law_ref
FROM dict_entry
WHERE dict_kind = %s AND exact_match
ORDER BY term"""
#: 🆕 2026-10-02 (D-311) — **자격이 없는** 항목. 보류 문장의 유형 후보로만 쓴다 — 확정 · 하한의 재료가 아니다.
#:    🚨 `SQL_DICT` 와 거름 하나만 다르다 — 칸 · 순서는 같다(`_entries` 가 둘을 같은 꼴로 읽는다 · D-99)
SQL_DICT_WEAK = SQL_DICT.replace("AND exact_match", "AND NOT exact_match")


def load_dict_entries(cur: Any) -> list[dm.Entry]:
    """`dict_entry` → 매칭 항목. 근거(`law_ref`)는 적재기가 `"; "` 로 이은 인용이다(`scripts/load_db.py` `load_dict`)."""
    return _entries(cur, SQL_DICT)


def load_weak_entries(cur: Any) -> list[dm.Entry]:
    """🆕 2026-10-02 (D-311) — 단독판정 자격이 **없는** 항목. 꼴은 `load_dict_entries` 와 같다."""
    return _entries(cur, SQL_DICT_WEAK)


def _entries(cur: Any, sql: str) -> list[dm.Entry]:
    cur.execute(sql, (DICT_KIND,))
    return [
        dm.Entry(
            term=term,
            violation_type=vt,
            basis=tuple(b.strip() for b in (ref or "").split(";") if b.strip()),
        )
        for term, vt, ref in cur.fetchall()
    ]


@timed
def match_dict(state: CoreState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """금지 표현 사전 매칭 — **재료만** 낸다: 판정(`judge`)과 위험도 하한(`assess_risk`)이 읽는다 (구현계획 F · D-09). 🆕 2026-09-28 (W4) 연결.

    ★ 매칭 규칙은 `app/dictmatch.py` 한 곳이다 — 판정기 B(`scripts/eval_rule.py`)와 **같은 적중**을 낸다 (D-99).
    🔴 `exact_match`(단독판정) 항목만 — `load_dict_entries`. 🔴 커서는 `retrieve` 와 같이 `config` 로 받는다(주석 없이).
    🔴 **DB 가 없어도 돈다** — 문장마다 `ran=False` 를 남긴다. ⛔ 빈 dict 로 삼키면 「못 훑었다」가 「안 걸렸다」가 된다 (D-220).
    🚨 사전의 **침묵은 「특이사항 없음」이 아니다** — 인코더 전에는 안 걸린 문장이 보류다 (D-269). 그 판정은 `judge` 가 한다.
    🚨 사전 적중은 **판정이 아니다** — 하한과 근거 후보다. 확정은 `judge` 가 법별 노드가 거른 적중으로 낸다 (D-127 · D-269).
    """
    sents = state.get("sents", [])
    if not sents:
        return {}
    cur = ((config or {}).get("configurable") or {}).get("conn")
    if cur is None:
        return {"dict_scans": [DictScan(sent_id=sent_id(i)) for i in range(len(sents))]}
    entries = load_dict_entries(cur)
    weak = load_weak_entries(cur)  # 🆕 D-311 — 보류 문장의 유형 후보
    # 🔄 2026-10-18 (D-348 보충 16) — 단독판정은 칸이 C 인 항목만 · 나머지 단독판정 항목은 후보로 내린다(`demoted`)
    entries, weak, lowered = _viewed(entries, weak)

    def _hits(text: str, es: list[dm.Entry]) -> tuple[DictHit, ...]:
        return tuple(
            DictHit(
                term=m.entry.term,
                violation_type=m.entry.violation_type,
                basis=m.entry.basis,
                span=m.span,
            )
            for m in dm.find(text, es)
        )

    def _lowered(text: str) -> tuple[DictHit, ...]:
        return tuple(
            DictHit(
                term=h.term,
                violation_type=h.violation_type,
                basis=h.basis,
                span=h.span,
                demoted=True,
            )
            for h in _hits(text, lowered)
        )

    scans = [
        DictScan(
            sent_id=sent_id(i),
            ran=True,
            hits=_hits(text, entries),
            weak=_hits(text, weak) + _lowered(text),
        )
        for i, text in enumerate(sents)
    ]
    # 🆕 2026-10-08 — 걸린 항목의 인용 조문에 원문을 붙일 재료 (근거 표시 「(나)」 · D-224 ④). 같은 커서로 한 번만 묻는다
    cites = {c for s in scans for h in (*s.hits, *s.weak) for c in h.basis}
    return {
        "dict_scans": scans,
        "basis_texts": basis_texts(cur, cites),
        "ref_texts": reference_texts(cur),
    }


#: 참조 조항표가 낼 수 있는 좌표 전부 — 유형 · 위반 근거 법의 모든 짝과 옮긴 후보의 인용([별표 1] 4.나). 수십 개다.
_REF_COORDS: tuple[str, ...] = tuple(
    sorted(
        {
            c
            for v in Violation
            for law in LAW_OF_NODE.values()
            for c in statute.references(v.value, law)
        }
        | set(statute.reference_of_cite(pm.UNRECOGNIZED_FUNCTION_CITE))
    )
)
_ANNEX_NO = re.compile(r"^\[별표 (\d+)\]")
_ARTICLE = re.compile(r"^제\d+조(?:의\d+)?")


def _ref_article(coord: str) -> EvidenceArticle:
    """참조 조항 좌표(`법ID:좌표`) → 좌표만 든 조항. 🚨 `basis` 는 거짓이다 — 판정이 기대는 조문이 아니다 (D-327 · D-323 결정 2)."""
    law_id, _, cite = coord.partition(":")
    return EvidenceArticle(law_id=law_id, article=cite)


#: 🆕 2026-10-12 (D-328) — 참고 조문으로 실을 별표를 가르는 낱말. 🚨 `[판정]` D-328 — 위임 근거(법령 별표는 위임 조문의 제목 ·
#:    행정규칙 별표는 고시 이름)에 이 낱말이 있어야 싣는다. 바꾸면 화면의 참고 조문이 바뀐다 — 보고에 올린다.
AD_WORD = "광고"
#: 별표 제목의 「(제N조 관련)」 — 위임 조문. 여럿이면 하나라도 맞으면 된다(013475 [별표 3] 「제5조제2항, 제6조제4항 및 제7조제2항」)
_DELEGATE = re.compile(r"제(\d+)조(?:의(\d+))?")
#: 조 머리 줄 「제8조(광고의 기준) …」 — 조문 제목
_ARTICLE_HEAD = re.compile(r"^(제\d+조(?:의\d+)?)\s*\(([^)]*)\)")
#: 현행 별표 문서와 그 별표가 딸린 법령 문서(같은 법 ID · 문서 종류 「법령」)의 이름 · 원천 파일.
#: 🚨 원천 파일(`source_ref`)의 머리 `admrul_` 로 행정규칙을 가른다 — 적재기가 `law_article.jsonl` 의 `파일` 을 그대로 넣는다(`scripts/load_db.py`)
SQL_ANNEX_DOCS = """SELECT d.law_id, d.annex_no, d.title, p.title, p.source_ref
FROM document d
LEFT JOIN LATERAL (
  SELECT title, source_ref FROM document
  WHERE law_id = d.law_id AND doc_type = '법령' AND superseded_at IS NULL
  ORDER BY doc_id DESC LIMIT 1
) p ON TRUE
WHERE d.doc_type = '별표' AND d.annex_no IS NOT NULL AND d.superseded_at IS NULL"""
#: 위임 조문의 청크들 — 조문 제목은 두 자리에 있다(`preprocess/chunk.py` `_context`):
#:    조 행  → 글이 「제N조(제목) …」으로 시작한다
#:    항 행  → 문맥이 조 제목이다(앞에 시행 예정 표시 「[…]」 줄이 올 수 있다). ⛔ 제목뿐인 조 머리 행은 청크로 안 싣는다(D-195) —
#:             013453 제3조가 그렇다. 조 행만 보면 제목을 못 읽는다
SQL_ARTICLE_HEADS = """SELECT DISTINCT c.law_id, c.article, c.text, c.context, c.item
FROM v_current_chunk c
WHERE c.doc_type = '법령' AND c.law_id = ANY(%s::text[]) AND c.article = ANY(%s::text[])"""


def annex_in_scope(
    annex_title: str | None,
    law_title: str | None,
    law_source: str | None,
    article_titles: dict[str, str],
) -> bool:
    """별표 하나를 판정 화면의 참고 조문으로 실어도 되는가 (🆕 2026-10-12 · D-328).

        행정규칙(고시) 별표  → 고시 이름에 `AD_WORD`
        법령 별표           → 별표 제목의 「(제N조 관련)」 조문 중 하나라도 그 제목에 `AD_WORD`

    🔴 **모르면 거짓이다** (D-220) — 딸린 법령 문서를 못 찾았거나 · 위임 조문이 제목에 없거나 · 그 조문의 제목을 못 읽었으면 싣지 않는다.
    ⛔ 손으로 만든 문서 목록을 두지 않는다 — 원문의 제목에서 계산한다(D-90). 새 별표도 같은 규칙으로 갈린다.
    🚨 대상은 별표뿐이다 — 법령 · 행정규칙 **본문**은 이 규칙을 타지 않는다(D-328 범위 · D-293 개정에서 산문을 따로 정한다).
    """
    if not law_source:
        return False
    if law_source.startswith("admrul_"):
        return AD_WORD in (law_title or "")
    refs = [f"제{a}조" + (f"의{b}" if b else "") for a, b in _DELEGATE.findall(annex_title or "")]
    return any(AD_WORD in (article_titles.get(r) or "") for r in refs)


def annex_scope(cur: Any) -> tuple[tuple[str, int], ...]:
    """현행 별표 중 참고 조문으로 실어도 되는 것 `(법 ID, 별표 번호)` — 정렬한 튜플 (🆕 2026-10-12 · D-328).

    ★ 규칙은 `annex_in_scope` 한 곳이다. 여기는 재료(별표 제목 · 딸린 법령의 이름과 원천 · 위임 조문의 제목)만 DB 에서 모은다.
    🚨 별표 번호가 없는 별표는 처음부터 빠진다 — 좌표가 서지 않아 어차피 참고 조문이 못 된다(`_annex_citation` · D-224).
    """
    cur.execute(SQL_ANNEX_DOCS)
    docs = cur.fetchall()
    want: dict[str, set[str]] = {}
    for law_id, _no, title, _lt, src in docs:
        if src and not str(src).startswith("admrul_"):
            for a, b in _DELEGATE.findall(title or ""):
                want.setdefault(law_id, set()).add(f"제{a}조" + (f"의{b}" if b else ""))
    found: dict[tuple[str, str], set[str]] = {}
    if want:
        cur.execute(
            SQL_ARTICLE_HEADS,
            (sorted(want), sorted({a for v in want.values() for a in v})),
        )
        for law_id, article, text, context, item in cur.fetchall():
            if article not in want.get(law_id, ()):
                continue
            title = _article_title(article, text, context, item)
            if title:
                found.setdefault((law_id, article), set()).add(title)
    # 🔴 제목이 하나로 모이지 않으면 모르는 것이다 — 싣지 않는다 (D-220)
    heads: dict[str, dict[str, str]] = {}
    for (law_id, article), titles in found.items():
        if len(titles) == 1:
            heads.setdefault(law_id, {})[article] = next(iter(titles))
    return tuple(
        sorted(
            (law_id, int(no))
            for law_id, no, title, law_title, src in docs
            if annex_in_scope(title, law_title, src, heads.get(law_id, {}))
        )
    )


def _article_title(
    article: str, text: str | None, context: str | None, item: str | None
) -> str | None:
    """청크 하나에서 조문 제목을 읽는다 — 조 행은 글의 머리 「제N조(제목)」, 항 행은 문맥(시행 예정 「[…]」 줄을 뺀 한 줄). 못 읽으면 `None`.

    🚨 호 행의 문맥은 「제목 + 항 본문」이라 읽지 않는다 — 제목이 빈 조라면 항 본문을 제목으로 읽게 된다.
    """
    m = _ARTICLE_HEAD.match(text or "")
    if m:
        return m[2] if m[1] == article else None
    if item:
        return None
    lines = [
        x.strip()
        for x in (context or "").split("\n")
        if x.strip() and not x.strip().startswith("[")
    ]
    return lines[0] if len(lines) == 1 else None


#: 🆕 2026-10-12 (D-329) — 본문 청크의 조 머리 · 문맥 · 원천. 🚨 글은 앞부분만 읽는다 — 조 제목을 읽는 데 그만큼이면 된다(`_article_title`).
#:    산문 고시는 `paragraph` 의 장(「Ⅱ」)과 장 머리 글로 가른다(🔄 2026-10-12 · D-293 개정 집행 — 종전 고시 단위 `"*"`).
SQL_BODY_HEADS = """SELECT DISTINCT c.law_id, c.article, left(c.text, 120), left(c.context, 240), c.item,
       d.title, d.source_ref, c.paragraph
FROM v_current_chunk c
JOIN document d ON d.doc_id = c.doc_id
WHERE c.doc_type = '법령'"""
_NUM_ARTICLE = re.compile(r"^제\d+조(?:의\d+)?$")
#: 산문 고시의 장 머리 줄 — 「Ⅰ. 목적 이 고시는 …」 → 「목적 이 고시는 …」. 글자는 `preprocess/law_article.py` `_ROMAN` 과 같다
_CHAPTER_HEAD = re.compile(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.\s*(.*)$")


def _boilerplate_chapter(head: str) -> bool:
    """장 머리 글이 상투 제목(`BOILERPLATE_TITLES`)으로 시작하는가 — 「목적 이 심사지침은 …」 · 「재검토기한 공정거래위원회는 …」.

    🚨 낱말 경계를 본다 — 제목 바로 뒤가 글 끝 · 띄어쓰기 · 괄호여야 한다(「목적물」 같은 낱말은 아니다).
    """
    for t in statute.BOILERPLATE_TITLES:
        if head.startswith(t) and (len(head) == len(t) or head[len(t)] in " (\u3000"):
            return True
    return False


def body_scope(cur: Any) -> tuple[tuple[str, str], ...]:
    """참고 조문으로 실어도 되는 본문 — `(법 ID, 조)` · 산문 고시는 `(법 ID, 장)` · 정렬한 튜플 (🆕 2026-10-12 · D-329).

        법령 본문      → `collect/statute.py` `REFERENCE_ARTICLES` 의 조 중 **DB 의 조 제목이 표와 같은 것**
        행정규칙 본문  → 고시 이름에 `AD_WORD` 가 있는 고시의 조 — 상투 조문(`BOILERPLATE_TITLES`)과 제목을 못 읽은 조는 뺀다.
                         산문 고시(숫자 조가 없다)는 **장 단위** `(법 ID, "Ⅱ")` 로 싣는다 — 상투 장(「Ⅰ. 목적」 · 「Ⅵ. 재검토기한」)과
                         머리 글을 못 읽은 장은 뺀다
                         🔄 2026-10-12 (D-293 개정 집행) — 종전 고시 단위(`(법 ID, "*")`)였다. 산문 좌표가 서면서 상투 장이 참고 조문
                         자리를 차지할 수 있어 D-329 안건 2 의 규칙을 장에 그대로 건다

    🔴 **제목이 표와 다르면 싣지 않는다** — 개정으로 조 번호가 밀리면 다른 조문을 가리킨다. 다른 조를 경고로 남긴다 (D-220).
    ★ 조 제목은 `_article_title` 한 곳에서 읽는다 — 별표의 위임 조문 제목과 같은 규칙이다 (D-99).
    """
    cur.execute(SQL_BODY_HEADS)
    rows = cur.fetchall()
    titles: dict[tuple[str, str], set[str]] = {}
    kind: dict[str, tuple[str, str]] = {}  # 법 ID → (원천 파일, 문서 이름)
    chapters: dict[tuple[str, str], set[str]] = {}  # (법 ID, 장) → 장 머리 글
    for law_id, article, text, context, item, doc_title, src, paragraph in rows:
        kind.setdefault(law_id, (str(src or ""), str(doc_title or "")))
        if article and _NUM_ARTICLE.match(article):
            t = _article_title(article, text, context, item)
            if t:
                titles.setdefault((law_id, article), set()).add(t)
        ch = rt.prose_chapter(paragraph or "")
        if ch is not None:
            # 장 노드 자신은 글이 머리 줄이다 · 아래 노드는 문맥 첫 줄(시행 예정 표시 `[` 줄 다음)이 장 머리 줄이다(`chunk._context`)
            lines = (
                [str(text or "")]
                if str(paragraph).strip() == ch
                else str(context or "").split("\n")
            )
            head = next((m[1] for x in lines if (m := _CHAPTER_HEAD.match(x.strip()))), None)
            chapters.setdefault((law_id, ch), set())
            if head:
                chapters[(law_id, ch)].add(head)
    out: set[tuple[str, str]] = set()
    mismatched: list[str] = []
    for law_id, article, title, _crit in statute.REFERENCE_ARTICLES:
        got = titles.get((law_id, article), set())
        if got == {title}:
            out.add((law_id, article))
        elif law_id in kind:  # 법령이 적재돼 있는데 제목이 다르거나 못 읽었다
            mismatched.append(f"{law_id}:{article}({' · '.join(sorted(got)) or '제목 없음'})")
    for law_id, (src, doc_title) in kind.items():
        if not src.startswith("admrul_") or AD_WORD not in doc_title:
            continue
        nums = [a for (lid, a) in titles if lid == law_id]
        if not nums:  # 산문 고시 — 숫자 조가 없다. 장 단위로 싣는다
            for (lid, ch), heads in chapters.items():
                if lid == law_id and heads and not any(_boilerplate_chapter(h) for h in heads):
                    out.add((law_id, ch))
        for a in nums:
            ts = titles[(law_id, a)]
            if len(ts) == 1 and not (ts & statute.BOILERPLATE_TITLES):
                out.add((law_id, a))
    if mismatched:
        logging.getLogger("copylane.graph").warning(
            "참고 조문 표의 조 제목이 DB 와 다르다 — 싣지 않는다 (D-329) · %s",
            ", ".join(mismatched),
        )
    return tuple(sorted(out))


def in_reference_scope(
    hit: rt.Hit,
    scope: frozenset[tuple[str, int]],
    body: frozenset[tuple[str, str]] = frozenset(),
) -> bool:
    """검색 근거 하나를 참고 조문 후보로 남기는가.

        별표  → `scope`(D-328 · 위임 근거에 「광고」)에 `(법 ID, 별표 번호)`
        본문  → `body`(D-329)에 `(법 ID, 조)` · 산문 고시는 `(법 ID, 장)`(🔄 2026-10-12 · D-293 개정 집행)
        그 밖 → 거짓 — 모르는 문서 종류다

    🔴 없거나 모르면 거짓이다 (D-220).
    """
    if hit.law_id is None:
        return False
    if hit.doc_type == "별표":
        return hit.annex_no is not None and (hit.law_id, hit.annex_no) in scope
    if hit.doc_type == "법령":
        ch = rt.prose_chapter(hit.paragraph or "")
        if ch is not None:
            return (hit.law_id, ch) in body
        return (hit.law_id, hit.article or "") in body
    return False


def reference_texts(cur: Any) -> dict[str, EvidenceArticle]:
    """참조 조항 좌표 → **원문이 붙은** 조항 (🆕 2026-10-12 · D-327). 유형 후보 옆에 「이 유형을 정한 조항」으로 싣는다.

    ★ 청크는 좌표로 찾는다 — 법령 조문은 `rt.by_article`, 별표는 `rt.by_annex`, 대조는 청크의 `citation`(D-99 · 좌표를 여기서 조립하지 않는다).
    🔴 **원문을 싣는 조건은 근거 조문과 같다**(`basis_texts`) — 원천의 `U3_cite` 가 열렸고 · 쪼갠 조각이 아니고 · 제외 목이 아니다.
       못 찾거나 조건이 안 서면 그 좌표는 **빠진다** — 받는 쪽(`_candidate_refs`)이 좌표만으로 낸다 (D-220 · 지어내지 않는다).
    """
    arts: list[tuple[str, str]] = []
    annexes: list[tuple[str, int]] = []
    for c in _REF_COORDS:
        law_id, _, cite = c.partition(":")
        if (m := _ANNEX_NO.match(cite)) is not None:
            annexes.append((law_id, int(m[1])))
        elif (m := _ARTICLE.match(cite)) is not None:
            arts.append((law_id, m[0]))
    hits = rt.by_article(cur, [a[0] for a in arts], [a[1] for a in arts])
    hits += rt.by_annex(cur, [a[0] for a in annexes], [a[1] for a in annexes])
    at = {(h.law_id, h.citation): h for h in hits if h.citation}
    out: dict[str, EvidenceArticle] = {}
    for c in _REF_COORDS:
        law_id, _, cite = c.partition(":")
        h = at.get((law_id, cite))
        if h is None or h.citable is not True or h.part_total != 1 or h.exempt_of or not h.text:
            continue
        out[c] = EvidenceArticle(
            law_id=law_id,
            article=cite,
            item=h.item or "",
            chunk_id=h.chunk_id,
            quote=h.text,
            doc_title=h.doc_title,
        )
    return out


def basis_texts(cur: Any, cites: Iterable[str]) -> dict[str, EvidenceArticle]:
    """사전 근거 인용 → **원문이 붙은** 근거 조문 (🆕 2026-10-08 · D-224 ④ · 근거 표시 「(나)」).

    ★ 좌표 꼴은 `_basis_article` 과 같다(`statute.article_item`) — 원문만 더 붙는다. 청크는 조문 청크의 `citation` 으로 찾는다(D-99).
    🔴 **원문을 싣는 조건은 검색 근거와 같다** — 원천의 `U3_cite` 가 열렸고(`citable`) · 쪼갠 조각이 아니다(`part_total == 1`).
       못 찾거나 조건이 안 서면 그 인용은 **빠진다** — `_basis_article` 이 원문 없는 좌표로 낸다 (D-220 · 지어내지 않는다).
    🚨 목(「|다목」)은 시행령 [별표] 의 것이다 — 조문 청크는 **호까지**라 호의 글을 붙인다. 좌표(항목 칸)는 목까지 그대로다.
    """
    want: dict[str, tuple[str, str, str, str]] = {}
    for c in cites:
        try:
            law, article, item = statute.article_item(c)
        except ValueError:
            continue
        ho = item.split("호", 1)[0] + "호"
        want[c] = (law, article, item, article + ho)
    if not want:
        return {}
    hits = rt.by_article(cur, [w[0] for w in want.values()], [w[1] for w in want.values()])
    at = {(h.law_id, h.citation): h for h in hits if h.citation}
    out: dict[str, EvidenceArticle] = {}
    for c, (law, article, item, coord) in want.items():
        h = at.get((law, coord))
        if h is None or h.citable is not True or h.part_total != 1 or not h.text:
            continue
        out[c] = EvidenceArticle(
            law_id=law,
            article=article,
            item=item,
            chunk_id=h.chunk_id,
            quote=h.text,
            basis=True,
            doc_title=h.doc_title,
        )
    return out


@timed
def encode(state: CoreState) -> dict[str, Any]:
    """인코더 — 유형 후보 · 확신 (D-131). **팬아웃 앞에서 한 번** 돈다 (D-267). 🆕 2026-10-07 배선 · 🔄 2026-10-09 응답에 싣는다.

    ★ 문장마다 신호를 `encodings` 에 싣는다 — **판정은 바뀌지 않는다.** `judge` 는 이 신호를 문장의 `encoder_candidates`
       칸으로 옮기기만 한다(`_encoder_candidates` · D-323).
    🔴 값이 없을 때 (D-220)
       · 모델 폴더가 설정되지 않았다 → 아무것도 싣지 않는다. 인코더를 쓰지 않는 정상 경로다(CI · 모델 없는 기기)
       · 설정했는데 올리지 못했다 → **경고를 남기고** 아무것도 싣지 않는다. 판정은 규칙 판정 그대로 나간다(보류 쪽이라 안전하다).
         ⛔ 조용히 넘기지 않는다 — 켰다고 믿는 사람이 꺼진 줄 모른다 (D-162). 수를 재는 도구는 이 경우 **멈춘다**
         (`scripts/eval_graph.py --encoder`).
    ⛔ 법별 노드가 인코더를 부르면 판정기가 세 벌이다 (D-99). 근거 구간(스팬)은 지금 모델이 내지 않는다.
    🆕 2026-10-14 (D-336 · D-339 결정 5) — **품목 입력 판**(`takes_category`)이면 문장마다 품목 입력 여럿을 **한 배치**로 돌려
       입력마다 한 벌씩 싣는다(`_encoder_inputs` · `SentEncoding.input`). 기록 판정은 요청 품목의 입력(모르면 「모름」), 분기는
       그 전제의 입력을 읽는다. 문장만 받는 판(카드 17 · 가짜 인코더)은 종전대로 문장마다 한 번 · `ANY_INPUT` 한 벌이다.
    """
    model_dir = enc.configured_dir()
    if model_dir is None:
        return {}
    sents = state.get("sents", [])
    try:
        enc.checked_dir(
            model_dir
        )  # 🆕 2026-10-13 (D-333) — 잠금에 없는 판은 올리지 않는다 · 거절도 아래 경고 경로를 탄다
        model = enc.encoder_at(model_dir)
        if getattr(model, "takes_category", False):
            need = _encoder_inputs((state.get("product") or ProductContext()).category)
            runs = [
                (i, x, p)
                for i, t in enumerate(sents)
                for x, p in zip(need, model.predict_many(t, need), strict=True)
            ]
        else:
            runs = [(i, ANY_INPUT, model.predict(t)) for i, t in enumerate(sents)]
    except enc.EncoderUnavailable as e:
        _warn_encoder_off(str(model_dir), str(e))
        return {}
    return {
        "encodings": [
            SentEncoding(
                sent_id=sent_id(i),
                scores=tuple((label.value, score) for label, score in p.scores.items()),
                candidates=tuple(c.violation.value for c in p.candidates),
                truncated=p.truncated,
                input=x,
            )
            for i, x, p in runs
        ]
    }


@functools.cache
def _warn_encoder_off(model_dir: str, why: str) -> None:
    """같은 까닭은 프로세스에서 한 번만 적는다 — 요청마다 같은 줄이 쌓이지 않게."""
    logging.getLogger("copylane.graph").warning(
        "판정 인코더를 올리지 못했다 — 인코더 신호 없이 규칙 판정으로 간다 (%s): %s", model_dir, why
    )


#: [별표 1] 4.나(인정하지 않은 기능성)의 8유형 — 인코더 후보를 옮길 때 쓴다. 🔴 인용에서 유형을 못 읽으면 import 에서 멈춘다 (D-220)
_UNRECOGNIZED_TYPE = statute.type_of(pm.UNRECOGNIZED_FUNCTION_CITE)
if _UNRECOGNIZED_TYPE is None:
    raise RuntimeError(
        f"🔴 {pm.UNRECOGNIZED_FUNCTION_CITE} 의 유형을 못 읽었다 — `collect/statute.py` 의 표를 본다 (D-319 ④′ ②)"
    )


def _cosmetic_moved(c: EncoderTypeCandidate) -> bool:
    """화장품 전제에서 옮긴 후보인가 (D-338 · `rs.COSMETIC_MOVE`)."""
    return c.moved_from is not None and rs.COSMETIC_MOVE.get(c.moved_from) is c.violation


def _candidate_refs(
    c: EncoderTypeCandidate, laws: Iterable[str], texts: dict[str, EvidenceArticle] | None
) -> list[EvidenceArticle]:
    """유형 후보 하나의 **참조 조항** — 문장이 보내진 법(`laws` · 법 축)마다 표가 정한 좌표 (🆕 2026-10-12 · D-327).

    ★ 유형만으로는 법을 못 정한다(D-323 결정 6) — 그래서 법마다 따로 싣고, 그 법에 조항이 없으면 그 법은 비운다 (D-220).
    ★ 옮긴 후보(`moved_from`)는 식품표시광고법에서 **옮겨 간 인용**([별표 1] 4.나)의 조항을 싣는다 — 유형의 일반 조항(제4호)이 아니라.
    🚨 좌표는 표(`collect/statute.py`)가 정한다. `texts` 에 있으면 원문이 붙고, 없으면 좌표만이다.
    """
    food = LAW_OF_NODE["law_food"]
    cosmetic = LAW_OF_NODE["law_cosmetic"]
    coords: list[str] = []
    for law in laws:
        if _cosmetic_moved(c):
            # 🆕 2026-10-14 (D-338) — 화장품 전제에서 옮긴 후보는 「화장품이라면」의 것이다 — 화장품법의 조항만 싣는다
            if law == cosmetic:
                coords += statute.references(c.violation.value, law)
        elif c.moved_from is not None and law == food:
            coords += statute.reference_of_cite(pm.UNRECOGNIZED_FUNCTION_CITE)
        else:
            coords += statute.references(c.violation.value, law)
    return [(texts or {}).get(x) or _ref_article(x) for x in dict.fromkeys(coords)]


#: 🆕 2026-10-14 (D-336 결정 5 · D-339 ⬜) — 인코더 후보의 **전제별 거름 · 옮김**을 켜 두는가. 앱은 늘 켠다.
#:    끄는 것은 평가 도구뿐이다(`scripts/eval_graph.py --no-enc-filter`) — 품목 입력 판의 dev 에서 거름 켬 / 끔을 견줘 거름표를 걷을지 판정한다.
#:    🚨 꺼도 사전 적중의 전제 거름(`_premise_hits`)은 그대로다 — 이 스위치는 인코더 후보 칸만 본다
_ENCODER_FILTER = True


def disable_encoder_filter() -> None:
    """이 프로세스에서 인코더 후보의 전제별 거름 · 옮김을 끈다 — **평가 도구만** 부른다(앱은 부르지 않는다)."""
    global _ENCODER_FILTER  # noqa: PLW0603 — 프로세스 단위 스위치다(`enc.permit_unlocked` 와 같은 모양)
    _ENCODER_FILTER = False


def _encoder_candidates(
    e: SentEncoding | None,
    premises: Iterable[Premise],
    laws: Iterable[str] = (),
    texts: dict[str, EvidenceArticle] | None = None,
) -> list[EncoderTypeCandidate]:
    """인코더 신호 → 문장의 `encoder_candidates` (🆕 2026-10-09 · D-323 결정 1 · 6). 🚨 판정이 아니다 — 유형 후보와 확신뿐이다.

    ★ 거름은 **유형 단위**다 — 건강기능식품 오인은 건강기능식품 전제 둘 · 일반식품 기능성 전제에서 서지 않는다
       (`pm.NO_HF_MISLEAD` · 사전 적중의 `_premise_hits` 와 같은 표 · D-319 ④′ · D-99). 법 거름은 하지 않는다 —
       유형만으로는 법을 못 정한다(D-323 결정 6).
    ★ 🆕 2026-10-10 — `건기식_비인정` 에서는 3호를 빼는 데서 그치지 않고 **4.나(거짓_과장)로 옮긴다**(`moved_from` 에 원래 유형).
       같은 문구가 제품에 따라 다른 조항에 걸린다 — 인정 없는 건강기능식품이 기능성을 내세우면 3호가 아니라 4.나다.
    ★ `premises` 가 여럿이면 **전제별로 거른 후보의 합집합**이다 — 한 전제에서라도 설 수 있는 후보는 남기고, 어느 전제에서도
       설 수 없는 후보만 뺀다(2026-10-09 팀장 판정 (다) · D-323 ⬜ 「기록 판정에 실리는 후보」). 분기 문장은 전제 하나로,
       기록 판정은 그 품목의 전제 전부(`pm.PREMISES_OF`)로 부른다 — 위험도를 가장 보수적인 전제로 적는 것과 같은 방향이다 (D-263 ①).
    🔴 값이 없을 때 (D-220)
       · 신호가 없다(인코더가 꺼졌거나 못 올렸다) → 빈 목록. 「후보 없음」이 아니라 「인코더가 없다」다 — 계약 주석이 그렇게 읽게 한다
       · 전제가 없다(전제 표에 없는 품목 · `전용법_미수록`) → **거르지 않는다.** 빈 합집합으로 후보를 전부 지우지 않는다
    """
    if e is None:
        return []
    # 거름을 끈 평가(`disable_encoder_filter`)는 전제가 없는 것처럼 — 거르지도 옮기지도 않는다. 참조 조항은 그대로 붙인다
    ps = tuple(premises) if _ENCODER_FILTER else ()
    never_hf = bool(ps) and all(p in pm.NO_HF_MISLEAD for p in ps)
    score = dict(e.scores)
    out = [
        EncoderTypeCandidate(violation=Violation(t), confidence=score[t])
        for t in e.candidates
        if not (never_hf and t == pm.HF_MISLEAD)
    ]
    # 🆕 2026-10-10 (팀장 판정 (나)) — 인정이 없는 건강기능식품 전제에서는 3호가 빠진 자리에 4.나(거짓_과장)가 선다.
    #    사전 적중이 `_premise_hits` 에서 하는 것과 같은 옮김이다 (D-319 ④′ ② · D-99). 그 전제가 `premises` 에 있으면 합집합에 든다.
    #    ⛔ 인코더가 거짓_과장을 직접 냈으면 더하지 않는다 — 같은 유형이 두 번 실리지 않고, 직접 낸 쪽(제 확률)이 남는다
    moved = Violation(_UNRECOGNIZED_TYPE)
    if (
        pm.HF_MISLEAD in e.candidates
        and Premise.건기식_비인정 in ps
        and moved.value not in e.candidates
    ):
        out.append(
            EncoderTypeCandidate(
                violation=moved,
                confidence=score[pm.HF_MISLEAD],
                moved_from=Violation(pm.HF_MISLEAD),
            )
        )
    # 🆕 2026-10-14 (D-338) — **화장품 전제만**(분기 · 품목이 화장품인 기록)에서는 질병 표방 · 건강기능식품 오인 후보를 의약품 오인으로
    #    옮긴다 — 우리 라벨 규약에서 화장품의 질병 · 건강 기능 주장은 의약품 오인이다(`rs.COSMETIC_MOVE`). 원래 후보는 그 전제에서 서지 않는다.
    #    ⛔ 품목 미상 기록(전제 여섯의 합집합)에서는 옮기지 않는다 — 원래 후보가 식품 전제에서 서고, 화장품이라면의 사본을 더하면 소음이다.
    #    ⛔ 인코더가 의약품 오인을 직접 냈으면 더하지 않는다 · 둘이 같은 유형으로 옮겨 가면 확률이 높은 쪽 하나만
    if ps and all(p is Premise.화장품 for p in ps):
        moves = [c for c in out if c.violation in rs.COSMETIC_MOVE]
        out = [c for c in out if c.violation not in rs.COSMETIC_MOVE]
        have = {c.violation for c in out}
        for c in sorted(moves, key=lambda x: -x.confidence):
            to = rs.COSMETIC_MOVE[c.violation]
            if to in have:
                continue
            have.add(to)
            out.append(
                EncoderTypeCandidate(violation=to, confidence=c.confidence, moved_from=c.violation)
            )
    # 🆕 2026-10-12 (D-327) — 후보마다 참조 조항을 붙인다. `laws` 가 비면(법을 모른다) 붙이지 않는다 — 빈 목록이다
    law_axes = tuple(laws)
    return [c.model_copy(update={"references": _candidate_refs(c, law_axes, texts)}) for c in out]


def _mine(hits: Iterable[DictHit], law: str) -> tuple[DictHit, ...]:
    """🆕 W4 — 사전 적중 중 **이 법의 인용**을 가진 것만, 인용도 이 법 것만 남긴다. 법을 못 정한 인용은 버린다 (D-220).

    🔄 2026-10-02 (D-311) — 단독판정 적중과 자격 없는 적중이 **같은 거름**을 쓴다 (D-99).
    """
    mine = []
    for h in hits:
        basis = tuple(b for b in h.basis if statute.law_of(b) == law)
        if basis:
            mine.append(DictHit(h.term, h.violation_type, basis, h.span))
    return tuple(mine)


def _law_node(name: str) -> Callable[..., dict[str, Any]]:
    """법별 노드 하나 (D-267). 🔜 자기 법의 조문 적용(유형 유효성 · 단서)은 아직 없다. 하한은 이 노드가 아니라
    `assess_risk` 가 법별 적중으로 읽는다(`floor_of_sentence`).

    🆕 2026-09-28 (W4 · D-291) — **자기 법의 근거를 거른다.** 넓은 검색의 두 갈래 후보에서 이 법 것만 골라 섞고
       (`rt.law_view` — 거른 뒤 섞는다 · ㊲) 앞의 `LAW_TOP_K` 개를 좌표로 옮긴다. 좌표를 못 세운 것은 버린다 (D-224).
    ★ 이 노드는 판정하지 않는다 — 「이 법이 이 문장들을 봤다 + 이 근거 · 사전 적중을 골랐다」까지다. 판정은 `judge` 가 낸다.
    🚨 읽는 것은 `law_payload()` 가 보낸 키뿐이다 — 컴파일본에서는 그것만 온다.
    🔴 참고 전용 법(건강기능식품법)은 노드가 될 수 없다 — 여기서 한 번 더 막는다 (D-271 ⑥ · D-220).
    """
    law = LAW_OF_NODE[name]
    if law in REFERENCE_ONLY:
        raise RuntimeError(
            f"🔴 참고 전용 법 {law!r} 은 위반 근거를 거르는 노드가 될 수 없다 (D-271 ⑥)"
        )

    def node(state: dict[str, Any]) -> dict[str, Any]:
        n = len(state.get("sents", []))
        by_sent = {e.sent_id: e for e in state.get("evidence", [])}
        scans = {s.sent_id: s for s in state.get("dict_scans", [])}
        scope = frozenset(state.get("annex_scope") or ())
        body = frozenset(state.get("body_scope") or ())
        picked: list[tuple[str, tuple[EvidenceArticle, ...]]] = []
        proviso_picked: list[tuple[str, tuple[Proviso, ...]]] = []
        dict_picked: list[tuple[str, tuple[DictHit, ...]]] = []
        weak_picked: list[tuple[str, tuple[DictHit, ...]]] = []
        for i in range(n):
            sid = sent_id(i)
            e = by_sent.get(sid)
            hits = rt.law_view(e.vector_hits, e.lexical_hits, law) if e else []
            # 🆕 2026-10-12 (D-328) — 광고를 다루지 않는 별표는 참고 조문으로 싣지 않는다. 🚨 근거로 바꾸기 **전에** 거른다 —
            #    적용 제외 목은 근거가 되면 `chunk_id` 가 비어 어느 문서인지 모른다. 섞은 순서(`law_view`)는 그대로 둔다(거른 뒤 섞지 않는다)
            # 🆕 2026-10-12 (D-329) — 본문도 같은 자리에서 거른다(법령 본문은 조문 표 · 고시는 이름 · 상투 조문 제외)
            hits = [h for h in hits if in_reference_scope(h, scope, body)]
            # 🔄 2026-09-28 (D-238 개정 (나)) — 적용 제외 목은 부모 좌표로 올리고 단서로 따로 나른다(`_pick`)
            arts, provs = _pick(hits)
            picked.append((sid, arts))
            proviso_picked.append((sid, provs))
            # 🆕 W4 — 사전 적중 중 **이 법의 인용**을 가진 것만, 인용도 이 법 것만 남긴다. 법을 못 정한 인용은 버린다 (D-220)
            dict_picked.append((sid, _mine(scans[sid].hits if sid in scans else (), law)))
            weak_picked.append((sid, _mine(scans[sid].weak if sid in scans else (), law)))
        return {
            "law_results": [
                LawResult(
                    law=name,
                    sent_ids=tuple(sent_id(i) for i in range(n)),
                    articles=tuple(picked),
                    dict_hits=tuple(dict_picked),
                    provisos=tuple(proviso_picked),
                    weak_hits=tuple(weak_picked),
                )
            ]
        }

    node.__name__ = name
    node.__qualname__ = name
    return timed(node)


@timed
def merge_laws(state: CoreState) -> dict[str, Any]:
    """법별 결과를 모은다 (D-267 팬인). 🔄 2026-10-05 — 전제별로 묶어 분기를 내는 일은 `premise_branches` 가 한다(D-319 ·
    판정과 위험도가 선 뒤라야 전제마다 다시 낼 수 있다). 여기는 대조만 한다.

    🔴 **보낸 법이 전부, 한 번씩, 문장을 다 보고 돌아왔는가**를 여기서 대조한다 (D-220 fail-closed).
       ⛔ 병렬 노드 하나가 빠지거나 두 번 쌓여도 LangGraph 는 오류를 안 낸다 — 판정이 한 법만큼 가벼워진 채
       응답은 그럴듯하다. 리듀서가 빠진 경우(마지막 법만 남는다)도 여기서 걸린다.
    """
    laws = tuple(state.get("laws") or ())
    results = state.get("law_results", [])
    got = [r.law for r in results]
    if sorted(got) != sorted(laws):
        raise RuntimeError(
            f"🔴 법별 결과가 보낸 법과 다르다 — 보냄 {list(laws)} · 돌아옴 {got} (D-267 · D-220)"
        )
    want = tuple(sent_id(i) for i in range(len(state.get("sents", []))))
    short = [r.law for r in results if r.sent_ids != want]
    if short:
        raise RuntimeError(f"🔴 문장을 다 보지 않은 법이 있다 — {short} (D-267 · D-220)")
    return {}


#: 🆕 2026-10-01 (W4 · D-273 결정 3) — 불가 사유(A 자격형 · B 실증형 · C 절대형 · D-59).
#: 🔄 2026-10-17 (D-348 보충 6 결정 1 · 2 · D-273 결정 3 개정) — **(유형 × 법 축) 칸**이다. 종전의 「유형 하나에 사유 하나」는 비방에서
#:    거짓이 됐다 — 식품 제8조①6호 · 화장품 시행규칙 [별표 5] 2.카 는 근거와 관계없이 위반(C), 표시광고법 시행령 제3조④ 는 「객관적 근거
#:    없이 · 불리한 사실만」(B). 출처 `[문헌]` — 각 칸의 조문(보충 6 의 칸 표 · `collect/statute.references` 가 같은 자리를 덮는다 — 게이트).
#: 🔴 **빈 칸은 사유를 모름 → 보류다** (D-273 「사유를 못 정하면 보류」 · D-72 · D-220) — 대응표에 조항이 없는 칸(예: 표시광고법 × 질병)은
#:    그 법 축으로 판정하지 않는다(보충 6 결정 8). 기본값을 두지 않는다 — 기본값이 검토하지 않은 법 축으로 새면 C 가 답 없는 위반을 낸다.
#:    🚨 `추천_보증_뒷광고` 는 칸이 없다 — D-255 가 범위 밖으로 뒀다(대가 표시 **누락**이 위반이라 문구로 못 본다 · D-192).
#:    🚨 `실증책임_위반` 은 세 법 모두 대응표 칸이 없다 — 칸 없음(보충 7 결정 10 · 사전 항목 0 · 인코더 라벨 없음).
#: ⬜ 화장품 [별표 5] 2.바 뒷부분(「"최고" · "최상" 등 절대적 표현」)은 C 지만 유형이 `부당_비교광고` 와 같은 목이다 — 사전 항목(보충 7
#:    결정 3 · 4)이 C 로 들고 온다. 이 칸은 앞부분(비교 대상 · 기준 · 객관적 확인)의 B 다.
_FOOD_AX, _FAIR_AX, _COSM_AX = "식품표시광고법", "표시광고법", "화장품법"
INFEASIBILITY_CELL: dict[tuple[Violation, str], Infeasibility] = {
    (Violation.질병_예방치료_표방, _FOOD_AX): Infeasibility.C,  # 8①1
    (Violation.의약품_오인, _FOOD_AX): Infeasibility.C,  # 8①2
    (Violation.의약품_오인, _COSM_AX): Infeasibility.C,  # 13①1 · [별표 5] 2.가
    (Violation.건강기능식품_오인, _FOOD_AX): Infeasibility.A,  # 8①3
    (Violation.기능성화장품_오인, _COSM_AX): Infeasibility.A,  # 13①2 · 2.나 (D-308 ⑨)
    (Violation.거짓_과장, _FOOD_AX): Infeasibility.B,  # 8①4
    (Violation.거짓_과장, _FAIR_AX): Infeasibility.B,  # 3①1
    (Violation.거짓_과장, _COSM_AX): Infeasibility.B,  # 13①4 · 2.사 · 2.아
    (Violation.소비자_기만, _FOOD_AX): Infeasibility.B,  # 8①5
    (Violation.소비자_기만, _FAIR_AX): Infeasibility.B,  # 3①2
    (Violation.소비자_기만, _COSM_AX): Infeasibility.B,  # 13①4 · 2.사
    (Violation.후기_체험기_기만, _FOOD_AX): Infeasibility.C,  # [별표 1] 5.다 (D-308 ⑨ · D-282)
    (Violation.부당_비교광고, _FOOD_AX): Infeasibility.B,  # 8①7 「객관적인 근거 없이」
    (Violation.부당_비교광고, _FAIR_AX): Infeasibility.B,  # 시행령 3③
    (Violation.부당_비교광고, _COSM_AX): Infeasibility.B,  # 2.바 앞부분
    (
        Violation.비방광고,
        _FOOD_AX,
    ): Infeasibility.C,  # 8①6 · [별표 1] 6 — 근거 조건 없음 (보충 6 결정 3)
    (Violation.비방광고, _FAIR_AX): Infeasibility.B,  # 시행령 3④ — 두 갈래 (보충 6 결정 3)
    (Violation.비방광고, _COSM_AX): Infeasibility.C,  # [별표 5] 2.카 「사실 유무와 관계없이」
}
#: 전용법 축 — 같은 유형에 전용법 칸이 있으면 그 칸이 먼저다(보충 6 결정 1 · 식품표시광고법 제3조 · 화장품은 `[관행]` 특별법 우선 · 보충 7 결정 1)
_SPECIAL_AXES = frozenset({_FOOD_AX, _COSM_AX})

#: 사유가 여럿이면 **더 막힌 쪽** — 종착 우선순위(증명서 A·C > 지시 B · D-268)와 같은 순서다.
_INFEAS_ORDER = (Infeasibility.C, Infeasibility.A, Infeasibility.B)


def _cell(v: Violation, law: str, text: str | None) -> Infeasibility | None:
    """칸 하나 — 🆕 2026-10-17 (D-348 보충 10) 식품 · 화장품 축의 비방은 **낱말로 가른다**: 타사 언급 ∧ 부정(`factcheck.slander_absolute`)이면
    비방 칸(C), 아니면 그 축의 부당 비교 칸(B — 자사 우월 비교 · 최상급 · 순위). 문장을 모르면(`text` 없음) 칸 그대로."""
    if (
        v is Violation.비방광고
        and law in _SPECIAL_AXES
        and text is not None
        and not factcheck.slander_absolute(text)
    ):
        return INFEASIBILITY_CELL.get((Violation.부당_비교광고, law))
    return INFEASIBILITY_CELL.get((v, law))


def infeasibility_of(
    cells: Iterable[tuple[Violation, str | None]], text: str | None = None
) -> Infeasibility | None:
    """(유형 · 법 축) 쌍들 → 문장의 불가 사유 — **조회는 여기 한 곳**(D-99 · 🆕 2026-10-17 · 보충 6 결정 1).

    ① 유형마다 그 유형의 칸을 모은다 — 전용법 칸(`_SPECIAL_AXES`)이 있으면 그것만(식품 · 화장품 먼저) · 없으면 걸린 칸 전부
    ② 한 유형이라도 칸이 하나도 없으면 **None**(사유를 모름 → 보류 · D-273 · D-220) · 쌍이 없어도 None
    ③ 유형들의 사유 중 더 막힌 쪽(`_INFEAS_ORDER`)
    🚨 부르는 쪽이 **그 품목에 걸린 법의 쌍만** 넘긴다(보충 6 결정 1 「그 법이 이 품목에 걸릴 때만」) — 인코더 근거는 `_basis_cells`.
    """
    by: dict[Violation, list[tuple[str | None, Infeasibility | None]]] = {}
    for v, law in cells:
        by.setdefault(v, []).append((law, _cell(v, law, text) if law else None))
    if not by:
        return None
    found: set[Infeasibility] = set()
    for pairs in by.values():
        known = [(law, r) for law, r in pairs if r is not None]
        special = [r for law, r in known if law in _SPECIAL_AXES]
        rs_ = special or [r for _, r in known]
        if not rs_:
            return None
        found.add(next(x for x in _INFEAS_ORDER if x in rs_))
    return next(x for x in _INFEAS_ORDER if x in found)


def _cells_of(
    basis: Iterable[str], violation_type: str | None
) -> list[tuple[Violation, str | None]]:
    """사전 항목 · 적중 하나의 (유형 · 법 축) 쌍 — 유형은 인용에서(`_hit_types` 와 같은 규칙 · D-282) · 법 축은 그 인용의 법 (`_hit_cells` · `entry_cell` 공통 · D-99)."""
    out: list[tuple[Violation, str | None]] = []
    basis = tuple(basis)
    typed = False
    for c in basis:
        t_ = statute.type_of(c)
        if t_ and t_ in Violation.__members__:
            out.append((Violation(t_), statute.law_of(c)))
            typed = True
    if not typed and violation_type and violation_type in Violation.__members__:
        axes = {statute.law_of(c) for c in basis} or {None}
        out.extend((Violation(violation_type), ax) for ax in axes)
    return out


def _hit_cells(hits: Iterable[DictHit]) -> list[tuple[Violation, str | None]]:
    """사전 적중 → (유형 · 법 축) 쌍. 법별 노드가 이미 보낸 법 것만 남겼다."""
    return [c for h in hits for c in _cells_of(h.basis, h.violation_type)]


def entry_cell(e: dm.Entry) -> Infeasibility | None:
    """사전 항목 하나의 불가 사유 칸 — 적중과 같은 조회(`infeasibility_of`) · 비방의 낱말 규칙은 항목 글자로 본다(근사 · 보충 15 결정 3 측정용)."""
    return infeasibility_of(_cells_of(e.basis, e.violation_type), e.term)


#: 🆕 2026-10-18 (D-348 보충 15 결정 3 · 보충 6 결정 7 · **측정 전용**) — 사전 판. None = 원래 사전 ·
#:    「c_only」 = 단독판정 항목 중 칸이 C 인 것만 · 자격 없는 항목 없음(좁히기 뒤의 사전을 흉내 낸다).
#:    끄고 켜는 것은 평가 도구뿐이다(`scripts/eval_graph.py --dict-view`) — 앱은 부르지 않는다 · 봉인 회차에서는 쓰지 않는다.
#:    🚨 근사 — 항목 칸은 항목의 인용으로만 본다(전제마다 다른 C — 건기식 인정 전제의 질병 표현 등 — 는 가르지 않는다)
_DICT_VIEW: str | None = None
DICT_VIEWS = ("c_only", "legacy")


def set_dict_view(view: str) -> None:
    """이 프로세스의 사전 판을 바꾼다 — **평가 도구만** 부른다. 모르는 판은 멈춘다 (D-220)."""
    global _DICT_VIEW  # noqa: PLW0603 — 프로세스 단위 스위치다(`disable_encoder_filter` 와 같은 모양)
    if view not in DICT_VIEWS:
        raise ValueError(f"🔴 모르는 사전 판 {view!r} — {DICT_VIEWS}")
    _DICT_VIEW = view


def _viewed(
    entries: list[dm.Entry], weak: list[dm.Entry]
) -> tuple[list[dm.Entry], list[dm.Entry], list[dm.Entry]]:
    """(단독판정 · 자격 없는 후보 · 내린 후보) — 🔄 2026-10-18 (D-348 보충 16) **기본 = 칸이 C 인 단독판정 항목만 단독판정**,
    나머지 단독판정 항목은 **후보로 내린다**(보충 15 결정 3 · 후보 전용 (나)) · 「legacy」 = 종전 사전 · 「c_only」 = 10-18(B) ① 의 측정 판(후보 없음)."""
    if _DICT_VIEW == "legacy":
        return entries, weak, []
    keep = [e for e in entries if entry_cell(e) is Infeasibility.C]
    if _DICT_VIEW == "c_only":
        return keep, [], []
    return keep, weak, [e for e in entries if entry_cell(e) is not Infeasibility.C]


def _basis_cells(basis: Iterable[EncoderBasis]) -> list[tuple[Violation, str | None]]:
    """인코더 근거 → (유형 · 법 축) 쌍 — **그 근거가 선 전제의 법만**(`pm.PREMISE_LAWS` · 보충 6 결정 1 「그 법이 이 품목에 걸릴 때만」).

    🔴 품목을 모르면 세 법을 모두 보내 참조 조항이 법마다 실린다(`laws_for(None)` · `_candidate_refs`) — 화장품 축의 C 가 식품 전제 근거에
       붙지 않게 전제의 법으로 거른다. 거르고 남는 축이 없으면 그 근거는 쌍을 내지 않는다(→ 그 유형은 사유 모름).
    """
    out: list[tuple[Violation, str | None]] = []
    for b in basis:
        allowed = {LAW_OF_NODE[n] for n in pm.PREMISE_LAWS.get(b.premise, ()) if n in LAW_OF_NODE}
        axes = {LAW_OF_ID.get(a.law_id) for a in b.articles} & allowed
        out.extend((b.violation, ax) for ax in sorted(axes, key=str))
        if not axes:
            out.append((b.violation, None))
    return out


def _basis_article(
    cite: str, texts: dict[str, EvidenceArticle] | None = None
) -> EvidenceArticle | None:
    """사전 근거 인용(`법ID:제N조제N항제N호[|목]`) → 근거 조문. 꼴이 틀리면 `None` — 좌표를 지어내지 않는다 (D-224).

    🆕 2026-10-08 — `texts`(`basis_texts`)에 있으면 **원문이 붙은 줄**을 낸다. 없으면 종전대로 좌표만.
    """
    if texts and cite in texts:
        return texts[cite]
    # 꼴은 `collect/statute.py` 한 곳 — 평가 도구가 되읽는다 (D-99)
    try:
        law, article, item = statute.article_item(cite)
    except ValueError:
        return None
    return EvidenceArticle(law_id=law, article=article, item=item, basis=True)  # D-323 결정 2


def _references(
    retrieved: list[EvidenceArticle], basis: list[EvidenceArticle]
) -> list[EvidenceArticle]:
    """검색 근거 중 인용 근거와 겹치지 않는 것 — 인용 근거 **뒤에** 붙는 참고 조문 (🆕 2026-10-08 · 근거 표시 「(나)」).

    🔴 같은 청크는 한 번 — 인용 근거에 원문이 붙으면(`basis_texts`) 검색이 같은 청크를 찾았을 때 두 번 나간다.
    """
    own = {b.chunk_id for b in basis if b.chunk_id}
    return [
        a for a in retrieved if a not in basis and (a.chunk_id is None or a.chunk_id not in own)
    ]


def _typed(names: set[str]) -> list[Violation]:
    """유형 이름 → 계약 값. 계약에 없는 이름은 뺀다(판정 재료가 아니다). 정렬 · 중복 없음."""
    return sorted(
        (Violation(n) for n in names if n in Violation.__members__), key=lambda v: v.value
    )


def _hit_types(h: DictHit) -> set[str]:
    """적중 하나의 유형 — 🔴 **인용에서 계산한다** (D-282 「라벨의 정본은 조문 인용 · 유형은 인용에서」).

    ★ 법별 노드가 인용을 **제 법 것만** 남겼으므로 같은 항목이라도 법마다 맞는 유형이 나온다.
    ⛔ `dict_entry.violation_type` 은 유형이 하나인 항목에만 채워진다(적재기 `load_dict` — 여러 유형 항목은 NULL).
       그 칸으로 고르면 여러 유형 항목이 전부 「유형 없음」이 된다. 인용이 유형을 못 주면(식품 8~10호 등) 그 칸을 쓴다.
    """
    return set(statute.types_of(list(h.basis))) or (
        {h.violation_type} if h.violation_type else set()
    )


def _judge_one(
    sid: str,
    text: str,
    start: int | None,
    scan: DictScan | None,
    hits: list[DictHit],
    retrieved: list[EvidenceArticle],
    weak: list[DictHit] | None = None,
    texts: dict[str, EvidenceArticle] | None = None,
) -> SentenceJudgment:
    """문장 하나 — **인코더 전 판정** (D-269 그대로 · ⚠️ 재검 대기).

    ① 사전을 **못 훑었으면** 미판정 — 못 본 것을 본 것처럼 말하지 않는다 (D-220 · D-63)
    ② 이 판정에 보낸 법의 인용을 가진 적중(`hits` — 법별 노드가 거른 것)이 있으면 **위반 확정** (D-269)
       — 근거 = 적중의 인용 조문 + 법별 노드가 고른 조문 · 뺄 구간 = 적중의 원문 좌표 · 불가 사유 = `infeasibility_of`(칸 · 보충 6)
       🔴 유형마다 사유를 못 정하면(표에 없음) **보류** · 인용 좌표를 하나도 못 세우면 **근거 없음** (D-273 · D-127 · D-224)
    ③ 적중은 있는데 그 인용이 **어느 법인지 못 정한다** → 근거 없음 — 유형은 유지 (D-127 「유형은 잡았는데 조문이 없다」)
       ⛔ 인용이 **보내지 않은 법** 것이면 근거 없음이 아니다 — 이 판정이 볼 법이 아니다(D-267)
    ④ 그 밖에 → **보류(확신 부족)** — 사전의 침묵은 「특이사항 없음」이 아니다 (D-269)
       🆕 2026-10-02 (D-311 · D-273 ④) — 단독판정 자격 **없는** 항목이 이 법의 인용으로 울렸으면 보류 문장에 **유형 후보**를 싣는다.
       확정하지 않는다 · 하한을 걸지 않는다(W5 · D-273 ④ 의 하한은 인코더 뒤 안건) · 근거는 적중의 인용 조문.
       ⛔ 싣지 않으면 강등된 질병 이름(「당뇨에 좋은 차」)이 사전 침묵과 같은 보류가 된다(원장 10-02 ⑤)
    🚨 여기서는 위험도를 적지 않는다 — 하한은 `assess_risk` 가 제재표(`sanction_rule` · W5)에서 읽어 붙인다. 지어내면 계약이 거부한다(D-09 · D-131).
    🔄 2026-10-15 (D-348 보충 1) — 주의 · 상담 문구(`app/claimscope.py`)만 `not_claim` 으로 낸다 · 사전 자격 적중이 있으면 내지 않는다.
       그 밖의 주장 여부 판별은 여전히 없다(D-275 ⚠️ 재검의 나머지).
    """
    if scan is None or not scan.ran:
        return SentenceJudgment(
            sent_id=sid, text=text, verdict=Verdict.unjudged, evidence=retrieved
        )
    # 🆕 2026-10-18 (D-348 보충 16) — 확정 막기 가드: 주장이 아닌 자리의 적중은 확정하지 않고 후보로 내린다(인코더 쪽 판정으로)
    blocked = [h for h in hits if claimscope.confirm_block(text, h.span)]
    if blocked:
        hits = [h for h in hits if h not in blocked]
        weak = [
            *(weak or ()),
            *(
                DictHit(
                    term=h.term,
                    violation_type=h.violation_type,
                    basis=h.basis,
                    span=h.span,
                    demoted=True,
                )
                for h in blocked
            ),
        ]
    if not scan.hits and not any(h.demoted for h in scan.weak) and claimscope.is_caution(text):
        # 🆕 2026-10-15 (D-348 보충 1 결정 1 · D-275) — 주의 · 상담 문구는 **판정 대상 아님**(확정 · 위반 없음 · R0 은 `assess_risk`).
        #    🔴 사전 자격 적중이 하나라도 있으면(법을 가리지 않는다 · `scan.hits`) 쓰지 않는다 — 주장이 섞인 문장을 지우지 않는다.
        #    자격 없는 적중(`weak` · 「당뇨」 비주장문맥 등)은 막지 않는다 — 그 적중을 주의 문맥에서 끄는 것이 이 규칙의 목적이다.
        #    근거 · 참고 조문을 싣지 않는다 — 판정할 주장이 없다.
        return SentenceJudgment(sent_id=sid, text=text, verdict=Verdict.confirmed, not_claim=True)
    if hits:
        types = _typed({t for h in hits for t in _hit_types(h)})
        if not types:
            return SentenceJudgment(
                sent_id=sid, text=text, verdict=Verdict.hold, hold_reason=HoldReason.low_conf
            )
        # 🔄 2026-10-17 (보충 6 결정 1) — 사유는 (유형 × 법 축) 칸에서 · 적중 인용의 법이 칸의 법이다
        reason = infeasibility_of(_hit_cells(hits), text)
        if reason is None:
            # 🔴 D-273 — 사유를 못 정하면 보류. ⬜ 사유 칸(`low_conf`)은 D-273 「결정 4 의 보류 문장을 어느 사유로」(W4)의 1판이다
            return SentenceJudgment(
                sent_id=sid,
                text=text,
                verdict=Verdict.hold,
                hold_reason=HoldReason.low_conf,
                violations=types,
                evidence=retrieved,
            )
        basis: list[EvidenceArticle] = []
        for h in hits:
            for c in h.basis:
                a = _basis_article(c, texts)
                if a is not None and a not in basis:
                    basis.append(a)
        if not basis:
            return SentenceJudgment(
                sent_id=sid, text=text, verdict=Verdict.no_basis, violations=types
            )
        evidence = basis + _references(retrieved, basis)
        # 같은 적중이 두 법 노드로 들어온다(인용이 두 법에 걸친 항목) — 구간은 좌표마다 한 번 · 라벨은 두 법의 유형을 합친다
        at: dict[tuple[int, int], set[str]] = {}
        if start is not None:
            for h in hits:
                if h.span is not None:
                    at.setdefault(h.span, set()).update(_hit_types(h))
        spans = [
            Span(start=start + a, end=start + b, label=",".join(sorted(ts)) or None)
            for (a, b), ts in at.items()
        ]
        return SentenceJudgment(
            sent_id=sid,
            text=text,
            verdict=Verdict.confirmed,
            violations=types,
            infeasibility=reason,
            evidence=evidence,
            spans=spans,
        )
    unplaced = [
        h for h in scan.hits if h.violation_type and not any(statute.law_of(b) for b in h.basis)
    ]
    if unplaced:
        return SentenceJudgment(
            sent_id=sid,
            text=text,
            verdict=Verdict.no_basis,
            violations=_typed({h.violation_type for h in unplaced if h.violation_type}),
        )
    # 보낸 법 밖의 인용만 울린 경우도 여기다 — 이 판정이 볼 법이 아니다(D-267)
    cand = _typed({t for h in weak or () for t in _hit_types(h)})
    basis_w: list[EvidenceArticle] = []
    for h in weak or ():
        for c in h.basis:
            a = _basis_article(c, texts)
            if a is not None and a not in basis_w:
                basis_w.append(a)
    return SentenceJudgment(
        sent_id=sid,
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        violations=cand,
        evidence=basis_w + _references(retrieved, basis_w),
    )


@timed
def judge(state: CoreState) -> dict[str, Any]:
    """판정 — 🔄 2026-10-01 (W4 1판) **인코더 전 규칙 판정** (D-269 · D-127 · D-224 · D-273). 문장 규칙은 `_judge_one`.

    🔴 근거는 **법별 노드가 고른 것**(`law_results[*].articles`)과 **법별 노드가 거른 사전 적중**(`dict_hits`)을
       `sent_id` 로 짝지어 옮긴다. 법 순서는 `LAW_NODES` 순서이고 같은 좌표는 한 번만 싣는다. ⛔ 검색을 다시 부르지 않는다 (D-99).
    🚨 **근거를 찾은 것과 판정한 것은 다르다** — 사전 적중 없이 검색 근거만으로는 확정하지 않는다 (D-127 · D-269).
    ⚠️ D-269 는 「전제 정정 · 결론 재검 대기」다 — 그래프 평가 도구(`scripts/eval_graph.py` · W1)의 수로 재검한다. 결론은 그때까지 그대로다.
    ⬜ 단서(`provisos`)는 아직 읽지 않는다 — 제품 사실을 모르면 요건 충족을 모른다(D-238 개정 (나)). 판정을 바꾸지 않는다.
       🔄 2026-10-15 (전수 점검) — ⛔ 종전 주석 「근거에 남는다」는 틀렸다. 법별 노드가 고른 단서(`LawResult.provisos`)는
       **응답에 실리지 않는다**(읽는 곳은 `scripts/graph_probe.py` 뿐). 🔄 D-344 ⑥b — **일부러 싣지 않는다.** 판정이 단서를 어떻게 확인하는가(D-238 개정 (나) ⬜)가
       정해지지 않았다 — 「다만 ~은 제외」를 보여 주면 이용자가 자기가 예외라고 읽는다. D-238 ⬜ 가 닫히면 다시 연다.
    """
    order = {name: k for k, name in enumerate(LAW_NODES)}
    results = sorted(state.get("law_results", []), key=lambda r: order.get(r.law, len(order)))
    per_sent: dict[str, list[EvidenceArticle]] = {}
    seen: dict[str, set[tuple[str, str, str | None]]] = {}
    hits_of: dict[str, list[DictHit]] = {}
    weak_of: dict[str, list[DictHit]] = {}
    for r in results:
        for sid, arts in r.articles:
            for a in arts:
                # 🔄 2026-09-28 — 같은 청크 · 같은 좌표는 한 번. ⛔ 종전 열쇠 `chunk_id` 는 부모로 올린 줄(`chunk_id=None`)을
                #    서로 다른 좌표여도 하나로 뭉갰다 (D-238 개정 (나))
                key = (a.law_id, a.article, a.chunk_id)
                if key in seen.setdefault(sid, set()):
                    continue
                seen[sid].add(key)
                per_sent.setdefault(sid, []).append(a)
        for sid, hs in r.dict_hits:
            hits_of.setdefault(sid, []).extend(hs)
        for sid, hs in r.weak_hits:
            weak_of.setdefault(sid, []).extend(hs)
    scans = {s.sent_id: s for s in state.get("dict_scans", [])}
    sents = state.get("sents", [])
    texts = state.get("basis_texts") or {}
    # 🔴 원문 좌표를 못 되찾으면(분할 밖에서 문장이 들어왔다) **구간을 싣지 않는다** — 좌표를 지어내지 않는다 (D-224 · D-278).
    #    판정 자체는 바뀌지 않는다. 뺄 구간이 필요한 지시 종착은 그때 계약이 막는다.
    try:
        starts: list[int | None] = list(sentsplit.offsets(state.get("text", ""), sents))
    except ValueError:
        starts = [None] * len(sents)
    # 🆕 2026-10-09 (D-323) — 인코더 신호는 **한 칸에만** 옮긴다. `_judge_one` 은 그 신호를 받지 않는다 — 판정이 읽을 길이 없다.
    #    기록 판정이라 이 품목의 전제 전부로 거른다(합집합 · `_encoder_candidates`).
    #    🆕 2026-10-14 (D-336 결정 2 · 3) — 품목 입력 판이면 **요청 품목의 입력**(모르면 「모름」)의 신호를 읽는다 — 카피 생성의
    #       재검수(품목을 넘긴다)가 그 품목 분기와 같은 계산을 탄다. 문장만 받는 판은 종전과 같다(`ANY_INPUT`)
    category = (state.get("product") or ProductContext()).category
    encs = _encodings_for(state, pm.encoder_input(category))
    premises = pm.PREMISES_OF[category]
    # 🆕 2026-10-12 (D-327) — 참조 조항은 **이번에 보낸 법**마다 싣는다(`state["laws"]` 는 노드 이름이다 → 법 축)
    ref_laws = tuple(LAW_OF_NODE[n] for n in state.get("laws") or () if n in LAW_OF_NODE)
    ref_texts = state.get("ref_texts") or {}
    out: list[SentenceJudgment] = []
    for i, t in enumerate(sents):
        sid = sent_id(i)
        j = _judge_one(
            sid,
            t,
            starts[i],
            scans.get(sid),
            hits_of.get(sid, []),
            per_sent.get(sid, []),
            weak_of.get(sid, []),
            texts,
        )
        # 🆕 2026-10-15 (D-348 보충 1) — 판정 대상 아님 문장에는 AI 추정 유형을 싣지 않는다(「주장이 아니다」와 함께 내지 않는다)
        if sid in encs and not j.not_claim:
            j = j.model_copy(
                update={
                    "encoder_candidates": _encoder_candidates(
                        encs[sid], premises, ref_laws, ref_texts
                    )
                }
            )
        out.append(j)
    return {"sentences": out}


#: 위험도 하한을 읽는 질의 — 🔴 **뷰만 읽는다**(`v_risk_lookup` · 2인 서명이 끝난 현행 행만 보인다 · 0013 · D-309).
#:    칸은 `app/sanction.py` `Row` 의 열쇠로 옮긴다 — 원천 검사(yaml)와 **같은 함수**(`floor_rows`)가 읽는다 (D-99).
SQL_RISK = """SELECT rule_key, law_id, violation_type::text, sanction_kind, annex1, cover, quote, fact_kind
FROM v_risk_lookup
ORDER BY rule_key"""


def load_sanction_rows(cur: Any) -> list[dict[str, Any]]:
    """`v_risk_lookup` → 하한 조회 행. 서명 전이거나 적재 전이면 **빈 목록**이다 — 그러면 하한이 없어 판정이 보류로 멈춘다 (D-220).

    🔄 2026-10-15 (D-343) — 식품 4~7호의 「그 밖에 R1」도 이제 이 규칙을 따른다(`sanction.floor_rows` · 그 법의 서명 행이 있어야 선다).
    """
    cur.execute(SQL_RISK)
    return [
        {
            "id": k,
            "law_id": law,
            "type": t,
            "kind": kind,
            "annex1": a1,
            "cover": cv,
            "quote": q,
            "fact": f,
        }
        for k, law, t, kind, a1, cv, q, f in cur.fetchall()
    ]


def floor_of_sentence(
    rows: list[dict[str, Any]], by_law: dict[str, tuple[DictHit, ...]]
) -> sanction.Floor:
    """문장 하나의 하한 — **한 전제 안에서 걸린 법들의 하한 중 높은 쪽** (D-272 · D-09). `by_law` = 법 축 이름 → 그 법의 적중.

    유형은 인용에서 계산한다(`_hit_types` · 판정과 같은 함수 · D-282) · 목 단위 하한은 그 법의 인용으로 찾는다 (D-310).
    🔴 (유형 · 법) 하나라도 **행이 없으면 하한을 모른다** — `Floor(None)`. ⛔ 아는 것만으로 max 를 내면 모르는 처분이
       더 무거울 때 하한이 「확실한 최소」가 아니게 된다. 모르면 위험도를 적지 않고 보류로 둔다 (D-220 · D-72).
    가능 상한은 하한보다 높은 것 중 가장 높은 것 하나 — 근거 줄과 함께 (D-310 개정 (다)).
    """
    found: list[sanction.Floor] = []
    for law, hits in by_law.items():
        law_id = sanction.SANCTION_LAW[law]
        cites = [b for h in hits for b in h.basis]
        for t in sorted({t for h in hits for t in _hit_types(h)}):
            if t not in Violation.__members__:
                continue  # 계약에 없는 유형은 판정 재료가 아니다 (`_typed`)
            f = sanction.floor_rows(rows, t, law_id, cites)
            if f.floor is None:
                return sanction.Floor(None)
            found.append(f)
    return _combine_floors(found)


def _combine_floors(found: list[sanction.Floor]) -> sanction.Floor:
    """하한들의 합 — 하한은 가장 높은 것 · 가능 상한은 그보다 높은 것 중 가장 높은 것 하나 · 근거 줄은 순서대로 (D-272 · D-310).

    🚨 판정(`floor_of_sentence`)과 추정 위험도(`estimate_of`)가 **이 함수 하나**로 합친다 (D-99). 비면 모른다(`Floor(None)`).
    """
    if not found:
        return sanction.Floor(None)
    top = max(found, key=lambda f: f.floor.level)  # type: ignore[union-attr]
    ceil = max(
        (f for f in found if f.ceiling is not None and f.ceiling.level > top.floor.level),  # type: ignore[union-attr]
        key=lambda f: f.ceiling.level,  # type: ignore[union-attr]
        default=None,
    )
    return sanction.Floor(
        top.floor,
        ceiling=ceil.ceiling if ceil else None,
        ceiling_note=ceil.ceiling_note if ceil else None,
        basis=tuple(dict.fromkeys(b for f in found for b in f.basis)),
    )


#: 🆕 2026-10-15 (D-340 결정 5 · D-346 결정 3 ~ 5 · D-347 결정 6) — **추정 위험도를 싣는 (전제 · 유형)**. `[측정]` D4-10 dev
#:    「제 전제 행 · 인코더만 잡은 문장」에서 n ≥ 20 ∧ 위반 비율 ≥ 90% ∧ 다른 생성기 적법 후보율 ≤ 15%(M 은 비율 · n 모두에서 뺌 ·
#:    비방광고 제외) — 식품 거짓_과장(n 82 · 1.00 · 적법 0 / 40) · 식품 소비자_기만(n 31 · 0.94 · 2 / 40) · 화장품 의약품_오인(n 36 ·
#:    0.97 · 0 / 78) (2026-10-15 · 클론 A · 원장 미기록). 🔄 **새 인코더 판이 채택되면 같은 규칙으로 다시 센다** — 목록은 판에 딸린다.
#: 🚨 표시 전용이다 — 하한 · 판정에 들지 않는다. D-131 개정 ①(위험도만)은 D-347 결정 6 의 관문을 넘은 뒤 판정한다
ESTIMATE_TYPES: frozenset[tuple[Premise, Violation]] = frozenset(
    {
        (Premise.식품, Violation.거짓_과장),
        (Premise.식품, Violation.소비자_기만),
        (Premise.화장품, Violation.의약품_오인),
    }
)


def estimate_of(rows: list[dict[str, Any]], premise: Premise, vtype: Violation) -> RiskEstimate:
    """(전제 · 유형) → 추정 위험도 — 그 전제의 법 ∩ 그 유형의 조항이 있는 법의 서명된 제재표 · 근거 인용 없이 (D-340 결정 5).

    🔴 법 하나라도 하한을 모르면 모른다 — 아는 법만으로 max 를 내지 않는다(`floor_of_sentence` 와 같은 규칙 · D-220).
       그 전제의 법 어디에도 이 유형의 조항이 없어도 모른다. 근거 인용이 없으니 식품 4 ~ 7 호는 「그 밖에」 하한 · 가장 무거운 처분이 상한이다.
    """
    laws = [
        LAW_OF_NODE[n]
        for n in pm.PREMISE_LAWS[premise]
        if n in LAW_OF_NODE and statute.references(vtype.value, LAW_OF_NODE[n])
    ]
    found: list[sanction.Floor] = []
    for law in laws:
        law_id = sanction.SANCTION_LAW.get(law)
        f = sanction.floor_rows(rows, vtype.value, law_id, []) if law_id else sanction.Floor(None)
        if f.floor is None:
            return RiskEstimate()
        found.append(f)
    c = _combine_floors(found)
    return RiskEstimate(floor=c.floor, ceiling=c.ceiling, ceiling_note=c.ceiling_note)


def _with_estimates(
    j: SentenceJudgment, premise: Premise, rows: list[dict[str, Any]]
) -> SentenceJudgment:
    """분기 문장의 인코더 후보에 추정 위험도를 싣는다 — **사전 유형이 없는 문장**(인코더만 잡은 문장)의 표시 목록 유형만 (D-340 결정 5).

    ⛔ 판정 칸(판정 · 위험도 · 유형)은 건드리지 않는다 — 후보 칸만 바뀐다. 판정 대상 아님(`not_claim`) 문장은 싣지 않는다.
    """
    if j.violations or j.not_claim or not j.encoder_candidates:
        return j
    if not any((premise, c.violation) in ESTIMATE_TYPES for c in j.encoder_candidates):
        return j
    cands = [
        c.model_copy(update={"estimate": estimate_of(rows, premise, c.violation)})
        if (premise, c.violation) in ESTIMATE_TYPES
        else c
        for c in j.encoder_candidates
    ]
    return j.model_copy(update={"encoder_candidates": cands})


def _with_risk(s: SentenceJudgment, risk: RiskAssessment) -> SentenceJudgment:
    """문장에 위험도를 붙인 **새 문장** — 계약 검증을 다시 지난다(위반 없으면 R0 · 있으면 R1 이상 · D-273)."""
    return SentenceJudgment(**{**{k: getattr(s, k) for k in type(s).model_fields}, "risk": risk})


# ── 인코더 하한 (🆕 2026-10-16 · D-348 결정 3 ~ 5 · 보충 2) ─────────────────────────────
# ★ 사전 하한(`risk.floor`)과 **따로** 낸다 — 인코더 유형 + 전제 → 대응표의 호 → 서명된 제재표(`estimate_of` 와 같은 계산 · D-99).
#   기록에 들이는 높이는 신뢰 층이 정한다(`encoder_cap`) · 최종 = max(사전 하한, 인코더 하한).
# 🚨 판정(확정 · 보류) · 종착은 바뀌지 않는다 — 보류 문장의 위험도 칸만 채운다(보충 2 결정 3).


def encoder_floor(
    rows: list[dict[str, Any]], premise: Premise, cands: Iterable[EncoderTypeCandidate]
) -> sanction.Floor:
    """전제 하나에서 문장의 인코더 하한 — 후보(옮긴 후보 포함)마다 `estimate_of` 를 내고 합친다(`_combine_floors`). **R2 이상 층의 계산**이다.

    🔴 후보 하나라도 하한을 모르면 **모른다**(`Floor(None)`) — 아는 것만으로 max 를 내지 않는다(`floor_of_sentence` 와 같은 규칙 · D-220).
       후보가 없으면 모른다(인코더가 조용하다 ≠ R0). 🔴 R0 하한은 모름이다 — 위반이라면 R1 이상이다(D-273 · 아래 `_r1_known`).
    ⛔ R1 층(지금 기록 상한)은 이 함수로 고르지 않는다 — `_r1_known`(보충 2 결정 4 개정 · 2026-10-16).
    """
    found: list[sanction.Floor] = []
    for c in cands:
        e = estimate_of(rows, premise, c.violation)
        if e.floor is None or e.floor is Risk.R0:
            return sanction.Floor(None)
        found.append(sanction.Floor(e.floor, ceiling=e.ceiling, ceiling_note=e.ceiling_note))
    return _combine_floors(found)


def encoder_cap(text: str) -> Risk | None:
    """신뢰 층 — 인코더 하한을 **기록에 들일 높이**. 지금은 R1 층뿐이다(D-348 결정 5 · 계약 `ENCODER_RECORD_MAX`).

    R1 층은 「주장인가만」 가린다(유형 무관 · D-273) — 주장 가드(`claimscope.claim_guard`)를 지나면 R1, 아니면 들이지 않는다(`None`).
    ⬜ R2 이상 층(유형을 믿을 수 있어야 한다)은 판정 뒤 여기서 연다.
    """
    return ENCODER_RECORD_MAX if claimscope.claim_guard(text) else None


def _with_encoder_risk(
    j: SentenceJudgment, premise: Premise, rows: list[dict[str, Any]]
) -> SentenceJudgment:
    """보류 문장에 그 전제의 인코더 하한을 합친 새 문장 — 못 내면 그대로 (D-348 보충 2 결정 3 · 4 · 10).

    🔴 보류 문장에만 · 판정 대상 아님 제외 · 주장 가드를 지날 때만 · 근거(그 전제에서 하한을 아는 후보의 호)가 있을 때만 (D-220).
       이미 적힌 인코더 하한이 있으면 그대로 둔다. 근거는 **이 문장의 후보**(이 전제의 품목 입력 · 이 전제로 거른 것)에서 낸다.
    """
    if j.verdict is not Verdict.hold or j.not_claim or j.risk.encoder is not None:
        return j
    cap = encoder_cap(j.text)
    if cap is None:
        return j
    basis = _encoder_basis(rows, premise, j.encoder_candidates)
    if cap.level <= Risk.R1.level:
        # 🔄 2026-10-16 (D-348 보충 2 결정 4 개정 · 팀장) — **R1 층은 「위반이라면 적어도 R1」**(D-273)이다. 유형이 틀려도 참이라
        #    하한을 아는 후보 하나면 선다 — 모르는 후보가 이 값을 틀리게 하지 못한다. 「하나라도 모르면 비움」은 R2 이상 층(`encoder_floor`)
        if not basis:
            return j
        return _with_risk(j, _merged(j.risk, cap, basis))
    f = encoder_floor(rows, premise, j.encoder_candidates)
    if f.floor is None or not basis:
        return j
    enc = min(f.floor, cap, key=lambda r: r.level)
    return _with_risk(j, _merged(j.risk, enc, basis))


def _encoder_basis(
    rows: list[dict[str, Any]], premise: Premise, cands: Iterable[EncoderTypeCandidate]
) -> list[EncoderBasis]:
    """그 전제에서 인코더 하한의 근거 — **하한이 R1 이상으로 확인되고 참조 조항(호)이 있는 후보 전부** (보충 2 결정 2 · 4 개정 · 10).

    ★ 다중 라벨이면 유형마다 하나씩 전부 싣는다 — R1 층에서는 각 후보가 따로 「위반이라면 적어도 R1」의 근거다. 대표는 화면이 고른다.
    🔴 R0 하한은 모름으로 센다 — 「위반이라면 R0」은 D-273(위반이면 R1 이상)과 모순이다. 제재표에 R0 에 대응하는 처분이 들어오면
       그것은 D-273 을 바꾸는 결정이다 — 보류 문장에 R0 을 조용히 적지 않는다(통과로 읽힌다 · D-280).
    """
    out: list[EncoderBasis] = []
    for c in cands:
        f = estimate_of(rows, premise, c.violation).floor
        if f is None or f.level < Risk.R1.level or not c.references:
            continue
        out.append(
            EncoderBasis(
                premise=premise,
                violation=c.violation,
                moved_from=c.moved_from,
                floor=f,
                articles=list(c.references),
            )
        )
    return out


def _r1_known(
    rows: list[dict[str, Any]], premise: Premise, cands: Iterable[EncoderTypeCandidate]
) -> bool:
    """R1 층 — 그 전제에서 하한이 R1 이상으로 확인되는 (근거 호가 있는) 후보가 하나라도 있는가 — `_encoder_basis` 가 비지 않음과 같다."""
    return bool(_encoder_basis(rows, premise, cands))


def _merged(risk: RiskAssessment, enc: Risk, basis: list[EncoderBasis]) -> RiskAssessment:
    """사전 쪽 위험도에 인코더 하한과 그 근거를 합친다 — 최종 = max(그 위험도의 최종 또는 사전 하한, 인코더 하한) (D-348 결정 4 · D-09 래칫).

    🔴 새로 만든다(`model_copy` 가 아니다) — 계약 검증(인코더 하한 ⇔ 근거 · 상한 · 래칫)을 다시 지나게 한다.
    """
    have = risk.final or risk.floor
    final = enc if have is None or enc.level > have.level else have
    return RiskAssessment(
        **{**risk.model_dump(), "encoder": enc, "encoder_basis": basis, "final": final}
    )


def _record_encoder(r: SentenceJudgment, per: list[SentenceJudgment]) -> SentenceJudgment | None:
    """기록되는 보류 문장의 인코더 하한 = **전제 최댓값** · 근거 = **그 값을 낸 분기들의 근거**(같은 등급이 여럿이면 전부) (보충 2 결정 4 · 10).

    ★ 분기를 내지 않는 경로(품목이 주어졌고 전제가 판정을 바꾸지 않는다)에서도 부른다 — 기록은 전제 최댓값이다(D-263 ① · 기록 ≥ 분기).
    ★ 근거는 분기 문장이 든 것을 그대로 옮긴다 — 값과 근거가 같은 곳(그 전제의 품목 입력)에서 온다. ⛔ 기록 문장의 표시용 후보
       (「모름」 입력 · 판정 아님)에서 근거를 찾지 않는다 — 그 후보가 비면 분기만 하한을 갖고 기록이 비어 응답이 거부됐다(10-16 결함).
    """
    encs = [j.risk.encoder for j in per if j.risk.encoder is not None]
    if not encs or r.verdict is not Verdict.hold or r.not_claim or r.risk.encoder is not None:
        return None
    top = max(encs, key=lambda x: x.level)
    basis = [b for j in per if j.risk.encoder is top for b in j.risk.encoder_basis]
    return _with_risk(r, _merged(r.risk, top, basis))


# 🔄 2026-10-18 (D-348 보충 20 · 보충 16 결정 5 집행) — 사전 B 확정의 실증 분기(`_substantiated` · D-337)는 걷었다. 사전은 칸 C 만 확정한다(보충 16) ·
#    실증 분기는 인코더 쪽(`_enc_subst`)만 단다. ⛔ 사전 확정 문장에 실증 · 사실 분기를 다시 달지 않는다(보충 15 결정 3)


@timed
def assess_risk(state: CoreState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """위험도 — **코드 하한**(제재표) · 가능 상한 (D-09 · D-305 · D-310). 🆕 2026-10-02 (W5) 배선.

    ★ 확정 문장에만 적는다 — 보류 문장의 유형 후보에는 하한을 걸지 않는다(D-311 · D-313 ③).
       🔄 2026-10-16 (D-348 보충 2) — 보류 문장에는 **인코더 하한**(`risk.encoder` · 사전 하한과 다른 칸)이 붙을 수 있다. 사전 하한 칸은
       위 규칙 그대로다. 전제가 하나인 품목은 여기서(`_single_premise_encoder`), 여럿이면 `premise_branches` 가 붙인다
       · 위반 없는 확정 → 하한 R0 · 최종 R0 (D-130 「걸린 것이 없으면 R0」 · D-273 불변식)
       · 위반 확정 → 하한 = 한 전제 안에서 걸린 법들의 하한 중 높은 쪽(`floor_of_sentence`) · 최종 = 하한(인코더가 없다 · D-131)
    🔴 **하한을 모르면 적지 않는다** — 제재표가 비었거나(서명 전 · 적재 전) 맞는 행이 없으면 위험도가 없고, 위험도 없는 확정 위반은
       종착이 보류다(`route_review` · D-220). ⛔ 지어내면 계약이 거부한다(D-09).
    🚨 **품목 미확정은 여기서 적지 않는다** — 전제(식품 · 화장품 · …)마다 하한이 다르다. 전제마다 다시 판정해 가장 보수적인
       등급을 적는 것은 `premise_branches` 다(🔄 2026-10-05 · D-319 — D-229 ⑥ 재검이 닫혔다).
    🔴 커서는 `match_dict` 와 같이 `config` 로 받는다(주석 없이). DB 가 없으면 아무것도 적지 않는다 — 판정은 그대로 나간다.
    """
    sents = list(state.get("sentences", []))
    product = state.get("product") or ProductContext()
    cur = ((config or {}).get("configurable") or {}).get("conn")
    out: list[SentenceJudgment] = []
    if product.category in UNCOVERED_CATEGORIES:
        # 🆕 2026-10-02 (D-277 · D-271 ④ 개정) — 주된 광고법을 안 본 품목은 「걸린 것 없음」을 확정하지 않는다.
        #    표시광고법으로 걸린 것이 없을 뿐 그 품목의 법은 보지 않았다 — 보류(`law_uncovered`)다. 걸린 문장은 확정 그대로다.
        #    🚨 판정 대상 아님(`not_claim`)은 그대로 둔다 — 주장이 없으면 어느 법으로도 걸릴 것이 없다 (D-275).
        #       그 문장뿐인 문서도 통과는 아니다 — 종착(`route_review`)이 막는다.
        for s in sents:
            if s.verdict is Verdict.confirmed and not s.violations and not s.not_claim:
                out.append(
                    SentenceJudgment(
                        **{
                            **{k: getattr(s, k) for k in type(s).model_fields},
                            "verdict": Verdict.hold,
                            "hold_reason": HoldReason.law_uncovered,
                            "risk": RiskAssessment(floor=Risk.R0, final=Risk.R0),
                        }
                    )
                )
    # 🆕 2026-10-15 (D-348 보충 1 · D-275) — **판정 대상 아님은 품목 · 제재표와 무관하게 R0** 이다(계약 불변식 · 걸린 것이 없다).
    #    🔴 품목 미확정(기록 판정)에서도 적는다 — 아래 조기 반환을 타면 기록은 위험도가 비고 분기 문장은 R0 이라
    #       「기록 ≥ 분기」 검증기(`_recorded_is_conservative`)가 응답을 거부한다.
    seen_out = {s.sent_id for s in out}
    for s in sents:
        if s.not_claim and s.risk.final is None and s.sent_id not in seen_out:
            out.append(_with_risk(s, RiskAssessment(floor=Risk.R0, final=Risk.R0)))
    done = {s.sent_id for s in out}
    todo = [
        s
        for s in sents
        if s.verdict is Verdict.confirmed and s.risk.final is None and s.sent_id not in done
    ]
    if not todo or cur is None or product.category is None:
        return _single_premise_encoder(state, cur, sents, out)
    # 🚨 제재표는 **적을 문장이 있을 때만** 읽는다 — 보류뿐인 요청에 질의를 하나 더 얹지 않는다 (D-77 L3)
    rows = load_sanction_rows(cur) if any(s.violations for s in todo) else []
    by_sent: dict[str, dict[str, tuple[DictHit, ...]]] = {}
    for r in state.get("law_results", []):
        for sid, hits in r.dict_hits:
            if hits:
                by_sent.setdefault(sid, {})[LAW_OF_NODE[r.law]] = hits
    for s in todo:
        if not s.violations:
            out.append(_with_risk(s, RiskAssessment(floor=Risk.R0, final=Risk.R0)))
            continue
        f = floor_of_sentence(rows, by_sent.get(s.sent_id, {}))
        if f.floor is None:
            continue
        out.append(
            _with_risk(
                s,
                RiskAssessment(
                    floor=f.floor,
                    final=f.floor,
                    ceiling=f.ceiling,
                    ceiling_note=f.ceiling_note,
                ),
            )
        )
    return _single_premise_encoder(state, cur, sents, out)


def _single_premise_encoder(
    state: CoreState, cur: Any, sents: list[SentenceJudgment], out: list[SentenceJudgment]
) -> dict[str, Any]:
    """품목을 알고 전제가 **하나**면(화장품 · 일반상품) 분기 노드가 돌지 않는다 — 기록 판정의 보류 문장에 그 전제의 인코더 하한을
    여기서 합친다 (🆕 2026-10-16 · D-348 보충 2 결정 4 · 분기 노드와 같은 함수 `_with_encoder_risk` · D-99).

    ★ 전제가 여럿(품목 미상 · 식품 · 건기식)이면 `premise_branches` 가 전제마다 내고 기록 = 최댓값으로 맞춘다 — 여기서 하지 않는다.
    🔴 DB 가 없거나 인코더 신호가 없으면 아무것도 하지 않는다(하한을 지어내지 않는다 · D-09 · D-220).
    """
    category = (state.get("product") or ProductContext()).category
    premises = pm.PREMISES_OF.get(category, ()) if category is not None else ()
    if len(premises) != 1 or cur is None or not state.get("encodings"):
        return {"sentences": out} if out else {}
    (premise,) = premises
    now = {s.sent_id: s for s in sents} | {s.sent_id: s for s in out}
    todo = [
        s
        for s in now.values()
        if s.verdict is Verdict.hold
        and not s.not_claim
        and s.encoder_candidates
        and s.risk.encoder is None
    ]
    by = {s.sent_id: s for s in out}
    if todo:
        rows = load_sanction_rows(cur)
        for s in todo:
            e = _with_encoder_risk(s, premise, rows)
            if e is not s:
                by[s.sent_id] = e
    res = list(by.values())
    return {"sentences": res} if res else {}


# ══════════════════════════════════════════════════════════════════
#  품목 분기 (🆕 2026-10-05 · D-319 · D-229 ⑥ · D-263 · D-267 · D-276) — 전제마다 판정을 다시 낸다
# ══════════════════════════════════════════════════════════════════
#
# ★ 재료는 법별 노드가 이미 갈라 둔 것이다(`law_results`) — 검색 · 사전 · 인코더를 다시 부르지 않는다 (D-267 · D-99).
#   전제 하나 = 그 전제의 법 묶음(`pm.PREMISE_LAWS`)에서 울린 적중만으로 `_judge_one` 을 다시 부른 것 + 전제가 유형을 바꾸는 자리.
# 🔴 사전을 읽는 방식은 그대로다 — 낱말의 인용 법이 그 판정의 법이다. 그래서 식품법 낱말은 화장품 · 일반상품 전제에서
#    「위반 없음」이 아니라 **사전 침묵(보류)** 이다 (D-269). 그 차이를 확정으로 덮지 않는 것이 D-319 ① 이다.


def _premise_hits(
    premise: Premise, hits: Iterable[DictHit]
) -> tuple[list[DictHit], list[DictHit], bool, bool]:
    """전제가 유형을 바꾸는 자리 (D-319 ④′). `(남는 적중, 판정하지 못하는 적중, 꺼진 것이 있나, 자격형으로 바뀐 것이 있나)`.

    ① ④ 건강기능식품 전제 둘 · 일반식품 기능성에서 3호(건강기능식품 오인) 인용은 서지 않는다 — 인용에서 그 줄만 뺀다
    ② `건기식_비인정` 은 그 자리에 [별표 1] 4.나(인정하지 않은 기능성)가 선다 — 자격형이다
    ③ `건기식_인정` 의 질병 표방은 인용의 목이 나 · 다일 때만 그대로 남고, 아니면 판정하지 못한다
    """
    kept: list[DictHit] = []
    unknown: list[DictHit] = []
    voided = converted = False
    for h in hits:
        basis = list(h.basis)
        if premise in pm.NO_HF_MISLEAD:
            rest = [c for c in basis if statute.type_of(c) != pm.HF_MISLEAD]
            if len(rest) != len(basis):
                if premise is Premise.건기식_비인정:
                    rest.append(pm.UNRECOGNIZED_FUNCTION_CITE)
                    converted = True
                else:
                    voided = True
                basis = rest
        if premise is Premise.건기식_인정:
            vague = [
                c
                for c in basis
                if statute.type_of(c) == pm.DISEASE
                and statute.parse(c)[4] not in pm.DISEASE_NO_PROVISO_MOK
            ]
            if vague:
                unknown.append(replace(h, basis=tuple(vague)))
                basis = [c for c in basis if c not in vague]
        if basis:
            kept.append(h if tuple(basis) == h.basis else replace(h, basis=tuple(basis)))
    return kept, unknown, voided, converted


def _premise_sentences(
    premise: Premise, state: CoreState, rows: list[dict[str, Any]]
) -> list[SentenceJudgment]:
    """전제 하나에서의 문장 판정 — 위험도까지. `judge` · `assess_risk` 와 같은 함수를 전제의 법 묶음으로 다시 부른다 (D-99)."""
    laws = pm.PREMISE_LAWS[premise]
    results = {r.law: r for r in state.get("law_results", [])}
    scans = {s.sent_id: s for s in state.get("dict_scans", [])}
    sents = state.get("sents", [])
    try:
        starts: list[int | None] = list(sentsplit.offsets(state.get("text", ""), sents))
    except ValueError:
        starts = [None] * len(sents)
    category = pm.PREMISE_CATEGORY[premise]
    texts = state.get("basis_texts") or {}
    # 🆕 2026-10-14 (D-336 결정 3) — 분기는 **그 전제의 품목 입력**의 신호를 읽는다(일반상품 → 「모름」 · `pm.premise_input`)
    encs = _encodings_for(state, pm.premise_input(premise))
    out: list[SentenceJudgment] = []
    for i, text in enumerate(sents):
        sid = sent_id(i)
        arts: list[EvidenceArticle] = []
        by_law: dict[str, tuple[DictHit, ...]] = {}
        unknown: list[DictHit] = []
        undecided: list[DictHit] = []
        raw_hit = voided = converted = False
        for law in laws:
            r = results.get(law)
            if r is None:
                continue
            for a in dict(r.articles).get(sid, ()):
                if a not in arts:
                    arts.append(a)
            hs = dict(r.dict_hits).get(sid, ())
            raw_hit = raw_hit or bool(hs)
            kept, unk, v, c = _premise_hits(premise, hs)
            voided, converted = voided or v, converted or c
            undecided += unk
            # 판정하지 못하는 적중은 자격 없는 적중과 같은 길로 — 보류 문장의 유형 후보다 (D-311 과 같은 모양)
            # 🔄 2026-10-11 — **자격 없는 적중도 전제 거름을 탄다** (D-319 ④′ ① ②). ⛔ 종전에는 그대로 붙였다 — 건강기능식품
            #    전제에서도 보류 후보에 건강기능식품 오인(3호)이 남았다(dev 조건부 건강기능식품 제품 82 행 중 10 · 원장 10-10 ⑭).
            #    확정 여부 · 「판정하지 못한다」 갈래는 자격 있는 적중만 본다 — 후보가 그 갈래를 움직이지 않는다
            wk, wunk, _, _ = _premise_hits(premise, dict(r.weak_hits).get(sid, ()))
            unknown += unk + wk + wunk
            if kept:
                by_law[LAW_OF_NODE[law]] = tuple(kept)
        hits = [h for hs in by_law.values() for h in hs]
        # 🔄 2026-10-18 (D-348 보충 20 · 보충 16 결정 5 집행) — 사전 질병 적중의 건기식 인정 분기(`_disease_answer` · `_disease_branch`)는 걷었다.
        #    건기식_인정 전제에서 「판정하지 못함」으로 빠진 질병 표방은 **전제별 제외**로 그대로 보류다(그 전제에서는 질병 표현이 C 가 아니다 ·
        #    [별표 1] 1.가.2) · 같은 질문(`인정_기능성`)은 인코더 쪽(`_enc_disease`)이 문안 승인 뒤 단다
        if undecided or (raw_hit and voided and not hits):
            # 🔴 이 전제에서 **판정하지 못한다** — 보류이고 걸린 것은 전부 유형 후보로만 싣는다 (D-319 ④′ · D-220 · D-311).
            #    · 판정하지 못하는 적중이 하나라도 있으면(질병 표방의 목을 모른다) 남은 적중만으로 확정하지 않는다 —
            #      확정하면 그 분기는 「거짓 · 과장뿐」이라고 말하게 된다(🔄 2026-10-05 재검 · 원장 10-03 ㊿-34).
            #    · 3호가 **서지 않는다 ≠ 통과다.** 인정 · 고시된 문구와 맞는지는 대조하지 않았다 — 그 재료(건강기능식품의
            #      고시형 문구 · 일반식품 기능성 고시 [별표 2])를 읽는 자리가 아직 없다. 그 대조가 붙기 전에는 통과를 내지 않는다.
            #    ⛔ 하한을 걸지 않는다 — 보류 문장의 유형 후보다 (D-311 · D-313 ③).
            j = _judge_one(sid, text, starts[i], scans.get(sid), [], arts, hits + unknown, texts)
        else:
            j = _judge_one(sid, text, starts[i], scans.get(sid), hits, arts, unknown, texts)
            if converted and j.verdict is Verdict.confirmed and j.violations:
                j = j.model_copy(
                    update={
                        "infeasibility": next(
                            x for x in _INFEAS_ORDER if x in {j.infeasibility, Infeasibility.A}
                        )
                    }
                )
        if j.verdict is Verdict.confirmed:
            if not j.violations:
                risk = RiskAssessment(floor=Risk.R0, final=Risk.R0)
                if category in UNCOVERED_CATEGORIES and not j.not_claim:
                    # `assess_risk` 와 같은 규칙 — 주된 광고법을 안 본 품목은 「걸린 것 없음」을 확정하지 않는다 (D-314)
                    j = j.model_copy(
                        update={"verdict": Verdict.hold, "hold_reason": HoldReason.law_uncovered}
                    )
                j = _with_risk(j, risk)
            else:
                f = floor_of_sentence(rows, by_law)
                if f.floor is not None:
                    j = _with_risk(
                        j,
                        RiskAssessment(
                            floor=f.floor,
                            final=f.floor,
                            ceiling=f.ceiling,
                            ceiling_note=f.ceiling_note,
                        ),
                    )
        if sid in encs and not j.not_claim:
            # 분기 문장 — 이 전제 하나로 거른다 (D-323 결정 6). 판정 대상 아님에는 싣지 않는다(D-348 보충 1 · `judge` 와 같다).
            # 판정이 끝난 뒤에 붙인다 — 위 판정은 이 칸을 보지 않았다
            j = j.model_copy(
                update={
                    "encoder_candidates": _encoder_candidates(
                        encs[sid],
                        (premise,),
                        # 분기 문장 — 이 전제의 법 묶음으로 참조 조항을 싣는다 (D-327)
                        tuple(LAW_OF_NODE[n] for n in laws if n in LAW_OF_NODE),
                        state.get("ref_texts") or {},
                    )
                }
            )
            # 🆕 2026-10-15 (D-340 결정 5 · D-346) — 인코더만 잡은 문장의 추정 위험도(표시 전용 · 판정이 끝난 뒤)
            j = _with_estimates(j, premise, rows)
            # 🆕 2026-10-16 (D-348 보충 2 결정 4) — 이 전제의 인코더 하한(보류 문장 · 기록 위험도 칸 · 판정은 그대로)
            j = _with_encoder_risk(j, premise, rows)
        out.append(j)
    return out


def _branch_outcome(premise: Premise, sents: list[SentenceJudgment]) -> Outcome:
    """분기의 종착 — 검수 종착과 같은 라우터를 전제의 품목으로 부른다 (D-99). 지시는 재료가 다 있을 때만(`guidance_ready`)."""
    name = route_review(
        {"sentences": sents, "product": ProductContext(category=pm.PREMISE_CATEGORY[premise])}  # type: ignore[typeddict-item]
    )
    if name == "guidance" and not guidance_ready(sents):
        return Outcome.hold
    return {
        "hold": Outcome.hold,
        "certificate": Outcome.certificate,
        "guidance": Outcome.guidance,
        "passed": Outcome.passed,
    }[name]


def _recorded(
    base: SentenceJudgment, per: list[SentenceJudgment], reason: HoldReason
) -> SentenceJudgment | None:
    """기록되는 판정 하나 (D-319 ① ①′ · D-263 ①). 바꿀 것이 없으면 `None`.

    🔴 **모든 전제에서 같은 위반이 설 때만 확정이다.** 한 전제라도 판정하지 못하거나(사전 침묵) 위반이 없으면 보류 + 분기다 —
       적용되는지 모르는 법의 조문으로 확정하지 않는다. 보류에도 유형 · 근거 · 가장 보수적인 위험도를 싣는다
       (계약 `_recorded_is_conservative` — 기록된 위험도 ≥ 검증 안 된 모든 분기의 위험도).
    🚨 인코더 후보는 **기록 판정의 것**(`base` — 이 품목의 전제 전부로 거른 합집합)을 그대로 둔다. 가장 무거운 전제의
       문장을 옮겨 올 때 그 전제 하나로 거른 후보가 따라오면 다른 전제에서 서는 후보가 사라진다 (D-323 · 2026-10-09 (다)).
    """
    hit = [j for j in per if j.verdict is Verdict.confirmed and j.violations]
    if not hit:
        return None  # 어느 전제에서도 확정 위반이 없다 — 종전 판정(사전 침묵 보류 등) 그대로
    # 🔄 2026-10-16 (D-348 보충 2 결정 1) — 여기서 모으는 것은 **사전 쪽** 위험도다. 인코더 하한이 붙은 분기 문장은 사전 하한만 센다 —
    #    인코더 몫은 `_record_encoder` 가 `encoder` 칸으로 따로 합친다(사전 하한 칸에 인코더 값을 섞지 않는다)
    risks = [
        r
        for j in per
        if (r := (j.risk.floor if j.risk.encoder is not None else j.risk.final)) is not None
    ]
    top = max(risks, key=lambda r: r.level) if risks else None
    worst = max(hit, key=lambda j: j.risk.final.level if j.risk.final is not None else -1)
    risk = RiskAssessment(floor=top, final=top) if top is not None else RiskAssessment()
    same = len(hit) == len(per) and len({tuple(j.violations) for j in per}) == 1
    if same:
        # 등급만 다르면 가장 높은 등급으로 기록한다 (D-319 ①′)
        return worst.model_copy(
            update={
                "risk": worst.risk
                if top is None
                else worst.risk.model_copy(update={"floor": top, "final": top}),
                "encoder_candidates": base.encoder_candidates,
            }
        )
    return SentenceJudgment(
        sent_id=base.sent_id,
        text=base.text,
        verdict=Verdict.hold,
        hold_reason=reason,
        violations=worst.violations,
        infeasibility=worst.infeasibility,
        evidence=worst.evidence,
        spans=worst.spans,
        risk=risk,
        encoder_candidates=base.encoder_candidates,
    )


def _held_candidates(
    base: SentenceJudgment, per: list[SentenceJudgment]
) -> SentenceJudgment | None:
    """제품을 알 때 보류 문장의 **유형 후보** — 그 품목의 전제로 거른 후보의 합집합 (🆕 2026-10-11 · D-319 ④′). 같으면 `None`.

    기록되는 판정(`judge`)은 전제 거름 전의 것이다 — 건강기능식품이라고 알려 줬는데 후보에 건강기능식품 오인(3호)이 남는다.
    그 유형은 건강기능식품 전제 둘에서 서지 않는다. 인코더 후보를 품목의 전제로 거르는 것과 같은 규칙이다
    (`_encoder_candidates` · D-323 · 2026-10-09 (다)) — 한 전제에서라도 서는 후보는 남기고 어디서도 서지 않는 후보만 뺀다.
    ★ 문장이 **모든 전제에서 확신 부족 보류일 때만** 손댄다. 한 전제라도 확정 · 근거 없음이면 `_recorded` 의 몫이다.
    ⛔ 품목을 모를 때는 부르지 않는다 — 전제 여섯에 식품이 있어 3호 후보가 설 수 있고, 다른 전제의 옮긴 후보까지 합치면
       정답이 마침 그 유형인 행이 맞은 것처럼 세어진다(인코더의 옮긴 후보를 따로 두는 것과 같은 까닭 · 원장 10-10 ⑫).
    🚨 건강기능식품의 `거짓_과장` 후보는 「그 기능성으로 인정받지 않았다면」의 것이다 — 근거에 [별표 1] 4.나가 실린다.
    """

    def low(j: SentenceJudgment) -> bool:
        return j.verdict is Verdict.hold and j.hold_reason is HoldReason.low_conf

    if not low(base) or not per or not all(low(j) for j in per):
        return None
    types = _typed({v.value for j in per for v in j.violations})
    evidence: list[EvidenceArticle] = []
    for j in per:
        for a in j.evidence:
            if a not in evidence:
                evidence.append(a)
    if types == list(base.violations):
        return None
    return SentenceJudgment(
        **{
            **{k: getattr(base, k) for k in type(base).model_fields},
            "violations": types,
            "evidence": evidence,
        }
    )


def _with_record_encoder(
    base: list[SentenceJudgment],
    changed: list[SentenceJudgment],
    per: dict[Premise, list[SentenceJudgment]],
    premises: tuple[Premise, ...],
) -> list[SentenceJudgment]:
    """기록 문장마다 인코더 하한(전제 최댓값)을 합친 바뀐 문장 목록 — 이미 바뀐 문장은 그 위에, 그대로인 문장은 기록 판정 위에 (D-348 보충 2 결정 4)."""
    by = {c.sent_id: c for c in changed}
    out = list(changed)
    for i, b in enumerate(base):
        r = by.get(b.sent_id, b)
        e = _record_encoder(r, [per[p][i] for p in premises])
        if e is None:
            continue
        if b.sent_id in by:
            out[out.index(by[b.sent_id])] = e
        else:
            out.append(e)
    return out


def _judgment_key(j: SentenceJudgment) -> tuple:
    """전제끼리 판정이 같은가를 보는 열쇠 — 판정 · 사유 · 유형 · 불가 사유 · 위험도 · 근거 좌표.

    ⛔ 인코더 후보(`encoder_candidates`)는 넣지 않는다 — 판정이 아니다. 넣으면 후보만 다른데도 분기가 생긴다 (D-323 결정 1).
    🚨 보류 문장의 유형 후보는 이 열쇠에 **들어 있다** — 분기를 낼지는 `_branch_key` 로 본다(후보만 다르면 분기를 내지 않는다).
       이 열쇠는 그대로 둔다 — 팀원 프로토타입(`docs/psj/e2e_prototype/judge_stage2.py`)이 부른다.
    """
    return (
        j.verdict,
        j.hold_reason,
        tuple(j.violations),
        j.infeasibility,
        j.risk.final,
        tuple((e.law_id, e.article, e.item) for e in j.evidence),
    )


def _branch_key(j: SentenceJudgment) -> tuple:
    """**분기를 낼지** 보는 열쇠 (🆕 2026-10-11 · D-319 · D-311 · D-323 결정 1) — 확신 부족 보류 문장은 유형 후보 · 그 근거를 뺀다.

    보류 문장의 유형은 후보이지 판정이 아니다(D-311). 후보까지 견주면 어느 전제를 골라도 보류인데 제품 유형을 고르라는
    분기가 생긴다 — 자격 없는 적중이 전제를 따르게 되면서(`_premise_sentences`) dev 조건부 345 행의 분기가 6 → 33 이 된다
    (원장 10-10 ⑮). 인코더 후보를 열쇠에 넣지 않는 것과 같은 까닭이다.
    ★ 판정이 갈리는 분기(한쪽 확정 · 한쪽 보류 · 등급 · 사유)는 `_judgment_key` 의 칸이 달라 그대로 선다.
    """
    if j.verdict is Verdict.hold and j.hold_reason is HoldReason.low_conf:
        return (j.verdict, j.hold_reason)
    return _judgment_key(j)


@timed
def premise_branches(state: CoreState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """품목 분기 — 전제마다 판정을 내고, 기록되는 판정을 가장 보수적인 쪽으로 맞춘다 (D-319 · D-263 ⑦ 「처음에 전부 계산」).

    ★ 품목을 모르면 전제 여섯, 식품이면 둘(식품 · 일반식품 기능성), 건강기능식품이면 둘(인정 · 비인정). 전제가 하나뿐이면 분기가 없다.
       품목이 주어졌는데 전제마다 판정이 같아도 분기가 없다.
    🔴 **기준 문안이 확정되지 않았으면 아무것도 하지 않는다** — 분기에는 문안이 필수 칸이고(계약 `Branch.criteria`) 초안 문안으로
       응답을 내지 않는다 (D-147 · D-220). 그때는 종전대로다(품목 미확정의 확정 위반은 위험도 없이 보류로 내려간다).
    🔴 DB 가 없으면(하한을 못 읽는다) 아무것도 하지 않는다 — 분기마다 위험도를 지어내지 않는다 (D-09).
    🚨 `judge` · `assess_risk` 가 낸 문장을 **바꿔 끼운다**(`upsert_sentences`) — 문장 수는 늘지 않는다.
    """
    category = (state.get("product") or ProductContext()).category
    premises = pm.PREMISES_OF[category]
    cur = ((config or {}).get("configurable") or {}).get("conn")
    base = list(state.get("sentences", []))
    if len(premises) < 2 or not pm.criteria_ready(premises) or cur is None or not base:
        return {}
    if any(s.verdict is Verdict.unjudged for s in base):
        return {}  # 사전을 못 훑었다 — 전제별 판정의 재료가 없다 (D-220)
    # 하한은 확정 위반에만 쓰인다 — 어느 법에서도 걸린 낱말이 없으면 제재표를 읽지 않는다(`assess_risk` 가 할 일이 없으면 안 읽는 것과 같다)
    hit = any(hs for r in state.get("law_results", []) for _, hs in r.dict_hits)
    # 🔄 2026-10-15 (D-340 결정 5) — 인코더 후보가 있으면 추정 위험도에도 쓴다. 안 읽으면 표가 빈 것처럼 「모름」이 된다(D-343)
    rows = load_sanction_rows(cur) if hit or state.get("encodings") else []
    per = {p: _premise_sentences(p, state, rows) for p in premises}
    # 🆕 2026-10-11 — 제품을 알 때 보류 문장의 유형 후보는 그 품목의 전제로 거른 합집합이다 (`_held_candidates`)
    held = (
        []
        if category is None
        else [
            h
            for i, b in enumerate(base)
            if (h := _held_candidates(b, [per[p][i] for p in premises])) is not None
        ]
    )
    if category is not None and len({tuple(map(_branch_key, per[p])) for p in premises}) == 1:
        # 품목이 주어졌고 전제가 판정을 바꾸지 않는다 — 고를 것이 없는 선택지를 내지 않는다.
        # ⛔ 품목을 모를 때는 같아도 낸다 — 「품목 미확정이면 분기는 언제나」(D-229 ⑥ · D-319 ②).
        # 🔄 2026-10-11 — 판정은 종전 그대로이고 보류 문장의 후보만 바로잡는다. 바꿀 것이 없으면 아무것도 내지 않는다
        # 🔄 2026-10-16 (D-348 보충 2 결정 4) — 분기를 내지 않아도 보류 문장의 기록 위험도는 전제 최댓값이다
        recs = _with_record_encoder(base, held, per, premises)
        # 🆕 2026-10-16 (보충 3 결정 4 · 건기식 인정 질병 분기) — 분기를 내지 않아도 사용자의 답은 기록에 출처로 남긴다(전제마다 판정이 같아 분기가 생략된 경우)
        recs = _with_record_answers(base, recs, per, premises)
        return {"sentences": recs} if recs else {}
    reason = HoldReason.cat_unknown if category is None else HoldReason.premise_unknown
    changed = [
        r
        for i, b in enumerate(base)
        if (r := _recorded(b, [per[p][i] for p in premises], reason)) is not None
    ]
    changed += [h for h in held if h.sent_id not in {r.sent_id for r in changed}]
    # 🆕 2026-10-16 (D-348 보충 2 결정 4) — 기록 문장(바뀐 것 · 그대로인 것)의 인코더 하한 = 전제 최댓값
    changed = _with_record_encoder(base, changed, per, premises)
    branches = [
        Branch(
            premise=p,
            outcome=_branch_outcome(p, per[p]),
            sentences=per[p],
            criteria=pm.CRITERIA[p],
        )
        for p in premises
    ]
    return {"branches": branches, "sentences": changed}


@timed
def doc_rules(state: CoreState) -> dict[str, Any]:
    """층 3 문서 규칙 — R-D1 최소판 → 문서 경고 + `hold(rd1)` (D-83). 🔜 W8.

    ⛔ 「문맥을 이해한다」고 말하지 않는다 (D-83 ④) — 문장별 판정 결과의 **집합 연산**이다.
    🆕 2026-10-16 (D-348 보충 3) — **사실 확인 분기**를 여기서 단다(기록 판정 · 위험도 · 품목 분기가 선 뒤 · `_with_condition`).
    🔄 2026-10-16 (D-348 보충 4) — **조건부 위반** 전부(사실 · 실증)를 여기서 낸다. 사실 확인 문안 표가 비면 그 갈래는 서지 않고
       실증 분기(문안 승인본 · `rs.subst_branch`)로 간다.
    🔄 2026-10-16 (보충 4 · 보충 2 결정 6 「분기마다 계산 · 기록 = 분기에서」) — 분기가 있으면 **분기 문장마다** 조건부를 정하고
       (전제마다 걸린 법 · 호가 다르다) 기록은 분기에서 모은다(`_record_condition`). 분기가 없으면 기록 문장에 바로 정한다.
    """
    product = state.get("product") or ProductContext()
    facts, substs = list(product.facts), list(product.substs)
    sents = list(state.get("sentences", []))
    branches = list(state.get("branches") or [])
    spans = _sentence_spans(state)
    # 🔄 2026-10-17 (보충 8 결정 1) — 인코더 쪽 절대형 확정은 품목이 정해졌을 때만(사용자가 품목을 고르면 그 품목으로 다시 판정)
    known = product.category is not None
    if not branches:
        changed = [
            f
            for s in sents
            if (f := _with_condition(s, facts, substs, spans.get(s.sent_id), known)) is not None
        ]
        return {"sentences": changed} if changed else {}
    new_b: list[Branch] = []
    for b in branches:
        ss = [
            _with_condition(x, facts, substs, spans.get(x.sent_id), known) or x for x in b.sentences
        ]
        if all(x is y for x, y in zip(ss, b.sentences, strict=True)):
            new_b.append(b)
            continue
        new_b.append(
            Branch(
                **{
                    **{k: getattr(b, k) for k in type(b).model_fields},
                    "sentences": ss,
                    "outcome": _branch_outcome(b.premise, ss),
                }
            )
        )
    reason = HoldReason.cat_unknown if product.category is None else HoldReason.premise_unknown
    by = [{x.sent_id: x for x in b.sentences} for b in new_b]
    changed = []
    for s in sents:
        per = [m[s.sent_id] for m in by if s.sent_id in m]
        r = _record_condition(s, per, reason)
        # 🆕 2026-10-17 (보충 6 결정 5 · D-263 ①) — 분기가 답 없이 확정 위반(절대형)이 되면 기록이 그보다 낮을 수 없다
        r2 = _record_at_least(r or s, per)
        x = r2 or r
        r3 = None if known else _mark_category_needed(x or s, per)
        if r3 is not None:
            changed.append(r3)
        elif x is not None:
            changed.append(x)
    out: dict[str, Any] = {"branches": new_b}
    if changed:
        out["sentences"] = changed
    return out


def _sentence_spans(state: CoreState) -> dict[str, Span]:
    """문장 번호 → **문장 전체** 구간(원문 좌표) — 인코더 쪽 확정 위반의 뺄 구간이다(D-348 결정 3 「문장 단위」 · 보충 5 · 1-b).

    좌표는 `sentsplit.offsets` 한 곳(D-99 · `judge` 와 같다). 못 찾으면 빈 표 — 그 문장은 확정하지 않는다(D-220).
    """
    sents = state.get("sents", [])
    try:
        starts = list(sentsplit.offsets(state.get("text", ""), sents))
    except ValueError:
        return {}
    return {
        sent_id(i): Span(start=st, end=st + len(t))
        for i, (t, st) in enumerate(zip(sents, starts, strict=False))
        if st is not None and t
    }


def _with_record_answers(
    base: list[SentenceJudgment],
    recs: list[SentenceJudgment],
    per: dict[Premise, list[SentenceJudgment]],
    premises: tuple[Premise, ...] | list[Premise],
) -> list[SentenceJudgment]:
    """분기가 생략된 경로의 기록 문장에 **전제 문장이 받은 사용자 답**(`user_facts`)을 옮긴다 — 기록이 확정일 때만(계약). 판정은 그대로다."""
    by = {r.sent_id: r for r in recs}
    out = dict(by)
    for i, b in enumerate(base):
        rec = by.get(b.sent_id, b)
        if rec.verdict is not Verdict.confirmed or rec.user_facts:
            continue
        got: list[UserFact] = []
        for p in premises:
            for f in per[p][i].user_facts:
                if f.kind not in {g.kind for g in got}:
                    got.append(f)
        if got:
            out[rec.sent_id] = SentenceJudgment(
                **{**{k: getattr(rec, k) for k in type(rec).model_fields}, "user_facts": got}
            )
    return list(out.values())


def _mark_category_needed(
    rec: SentenceJudgment, per: list[SentenceJudgment]
) -> SentenceJudgment | None:
    """품목을 모르는데 어떤 전제에서는 절대형(C) 위반이 서는 문장 → 기록을 **품목 선택 필요**(`cat_unknown`)로 (🆕 2026-10-17 · 보충 8 결정 1).

    ★ 전제마다 등급이 갈린다(D-229 · `cat_unknown` 의 뜻) — 그 전제에서는 답 없이 위반, 다른 전제에서는 아니다. 품목을 고르면 다시 판정한다.
    🔴 확신 부족 보류 · 선택지 · 답이 없는 기록만 — 선택지(`fact_check` · `substantiation`)는 `cat_unknown` 에 실을 수 없다(계약). 바꿀 것이 없으면 None.
    """
    if (
        rec.verdict is not Verdict.hold
        or rec.hold_reason is not HoldReason.low_conf
        or rec.fact_check is not None
        or rec.substantiation is not None
        or rec.user_facts
        or rec.user_subst is not None
        or rec.not_claim
    ):
        return None
    if not any(_encoder_only(x) and _absolute_types(x) for x in per):
        return None
    return SentenceJudgment(
        **{
            **{k: getattr(rec, k) for k in type(rec).model_fields},
            "hold_reason": HoldReason.cat_unknown,
        }
    )


def _record_at_least(rec: SentenceJudgment, per: list[SentenceJudgment]) -> SentenceJudgment | None:
    """기록 문장을 분기의 가장 나쁜 경우 **이상**으로 (🆕 2026-10-17 · D-263 ① · D-319 ① · 보충 6 결정 5). 바꿀 것이 없으면 None.

    ★ 분기 문장이 기록 뒤에(`doc_rules`) 인코더 쪽 절대형 위반으로 오르면 기록의 위험도가 분기보다 낮아진다 — 계약이 거부한다
       (`_recorded_is_conservative`). 두 경우:
       · 위험도가 선 분기가 **전부** 확정 위반이고 유형이 같다 → 기록 = 가장 무거운 분기의 판정(D-319 ① 「모든 전제에서 같은 위반」)
       · 그 밖 → 판정은 그대로(품목 · 전제에 달렸다) · 위험도만 분기 최댓값으로 올린다(기록 = 가장 보수적인 경우)
    """
    live = [x for x in per if x.risk.final is not None and not x.not_claim]
    if not live or rec.not_claim:
        return None
    top = max(live, key=lambda x: x.risk.final.level)  # type: ignore[union-attr]
    have = rec.risk.final
    if have is not None and have.level >= top.risk.final.level:  # type: ignore[union-attr]
        return None
    confirmed = [x for x in live if x.verdict is Verdict.confirmed and x.violations]
    if len(confirmed) == len(live) and len({tuple(x.violations) for x in confirmed}) == 1:
        return SentenceJudgment(
            **{
                **{k: getattr(top, k) for k in type(top).model_fields},
                "sent_id": rec.sent_id,
                "encoder_candidates": rec.encoder_candidates,
            }
        )
    # 하한 칸은 분기가 든 하한(그 유형 · 전제의 제재표 하한 — `_enc_absolute` 와 같은 칸)을 올려 싣는다 — 근거 스팬 없이 하한 위로 올리지 않는다(D-131)
    lows = [r for r in (rec.risk.floor, top.risk.floor) if r is not None]
    if not lows:
        return None
    floor = max(lows, key=lambda r: r.level)
    final = max((floor, top.risk.final), key=lambda r: r.level)  # type: ignore[arg-type]
    risk = RiskAssessment(**{**rec.risk.model_dump(), "floor": floor, "final": final})
    return SentenceJudgment(
        **{**{k: getattr(rec, k) for k in type(rec).model_fields}, "risk": risk}
    )


def _record_condition(
    rec: SentenceJudgment, per: list[SentenceJudgment], reason: HoldReason
) -> SentenceJudgment | None:
    """기록 문장의 조건부 여부를 **분기에서** 모은다 (🆕 2026-10-16 · D-348 보충 4 · 보충 2 결정 6). 바꿀 것이 없으면 None.

    ★ 세 상태 — 확정 / 조건부 / 보류. 기록 = 분기들의 합(D-319 ① 과 같은 규칙):
       · 위험도가 선 분기가 **전부** 조건부 → 기록도 조건부(선택지는 위험도가 가장 높은 분기의 것 · 기록 위험도 · 근거는 그대로 — 이미 전제 최댓값이다)
       · 전부 사용자의 답으로 정해졌다 → 가장 무거운 분기의 결과(풀렸으면 R0 확정 · 출처)
       · 조건부와 그렇지 않은 분기가 섞였다 → 품목 · 전제를 몰라 보류(분기가 선택지 · 조건이 품목에 달렸다)
    🚨 기록이 이미 품목 · 전제 보류면 손대지 않는다 — 분기가 선택지다. 분기에 문장이 없으면 손대지 않는다.
    """
    if (
        not per
        or rec.not_claim
        or rec.hold_reason in (HoldReason.cat_unknown, HoldReason.premise_unknown)
    ):
        return None
    if not (
        (rec.verdict is Verdict.confirmed and rec.violations)
        or (rec.verdict is Verdict.hold and rec.hold_reason is HoldReason.low_conf)
    ):
        return None
    live = [x for x in per if x.risk.final is not None and not x.not_claim]
    cond = [x for x in live if is_conditional(x)]
    # 「답으로 정해졌다」 = 조건이 남지 않은 문장(확정) — 사실 하나에 답했고 실증 · 다음 사실이 남은 조건부 보류는 조건부 쪽이다
    # 🔄 2026-10-16 (D-348 보충 5) — 인코더 쪽 보류 + 분기(`low_conf` · 남은 선택지)는 「답으로 정해졌다」가 아니다
    enc = [
        x
        for x in live
        if x.verdict is Verdict.hold
        and x.hold_reason is HoldReason.low_conf
        and (x.fact_check is not None or x.substantiation is not None)
    ]
    answered = [
        x
        for x in live
        if not is_conditional(x) and x not in enc and (x.user_facts or x.user_subst is not None)
    ]
    fields = {k: getattr(rec, k) for k in type(rec).model_fields}
    if live and len(answered) == len(live):
        # 🔄 2026-10-17 (보충 5 결정 1 · 1-b) — 가장 나쁜 분기 = 판정 순서(확정 위반 > 보류 > R0) · 같으면 위험도
        top = max(
            answered,
            key=lambda x: (
                2 if x.verdict is Verdict.confirmed and x.violations else 0 if is_pass(x) else 1,
                x.risk.final.level,  # type: ignore[union-attr]
            ),
        )
        if not top.violations and top.risk.final is Risk.R0:
            return _answered(rec, user_facts=top.user_facts, user_subst=top.user_subst)
        if (
            top.verdict is Verdict.confirmed
            and top.violations
            and rec.verdict is Verdict.hold
            and rec.hold_reason is HoldReason.low_conf
        ):
            # 🆕 (1-b) 인코더 쪽 보류 기록이 분기에서 「아니오」로 확정 위반이 됐다 — 기록 = 가장 나쁜 분기의 판정(표시용 후보는 기록 것)
            return SentenceJudgment(
                **{
                    **{k: getattr(top, k) for k in type(top).model_fields},
                    "encoder_candidates": rec.encoder_candidates,
                }
            )
        if rec.verdict is Verdict.confirmed or (
            rec.verdict is Verdict.hold and rec.hold_reason is HoldReason.low_conf
        ):
            # 🔄 (보충 5) 인코더 쪽 보류에도 답(출처)을 싣는다 — 판정은 그대로
            return SentenceJudgment(
                **{**fields, "user_facts": top.user_facts, "user_subst": top.user_subst}
            )
        return None
    if enc and len(enc) == len(live) and rec.hold_reason is HoldReason.low_conf:
        # 🆕 (보충 5) 분기가 전부 인코더 쪽 보류 + 선택지 → 기록도 그대로(확신 부족 보류)에 위험도가 가장 높은 분기의 선택지
        top = max(enc, key=lambda x: x.risk.final.level)  # type: ignore[union-attr]
        if rec.risk.final is None:
            return None
        return SentenceJudgment(
            **{
                **fields,
                "infeasibility": top.infeasibility,
                "substantiation": top.substantiation,
                "fact_check": top.fact_check,
                "user_facts": top.user_facts,
            }
        )
    if not cond:
        return None
    if len(cond) == len(live):
        top = max(cond, key=lambda x: x.risk.final.level)  # type: ignore[union-attr]
        if rec.risk.final is None:
            return None  # 기록에 위험도가 없다 — 조건부를 세울 수 없다 (D-72)
        return SentenceJudgment(
            **{
                **fields,
                "verdict": Verdict.hold,
                "hold_reason": HoldReason.premise_unknown,
                "infeasibility": top.infeasibility,
                "substantiation": top.substantiation,
                "fact_check": top.fact_check,
                "user_facts": top.user_facts,
            }
        )
    return SentenceJudgment(
        **{
            **fields,
            "verdict": Verdict.hold,
            "hold_reason": reason,
            "substantiation": None,
            "fact_check": None,
        }
    )


# ── 사실 확인 분기 (🆕 2026-10-16 · D-348 보충 3) ─────────────────────────────────────


def _coords(arts: Iterable[EvidenceArticle]) -> set[tuple[str, int, int, int]]:
    """조문 → 호 좌표 · 못 읽는 것은 버린다 — `_encoder_side`(인코더 근거만)가 쓴다 (D-99)."""
    out: set[tuple[str, int, int, int]] = set()
    for a in arts:
        c = statute.from_article_item(a.law_id, a.article, a.item)
        if c is None and not a.basis:
            # 참조 조항 꼴(인코더 근거 · 대응표) — 좌표는 article 한 칸에 있다(`_ref_article` · `reference_texts`).
            # 🔴 2026-10-17 (D-348 보충 5 · 원장 10-16(B) ⑧) — 종전 조건 `not a.item` 은 DB 가 원문과 함께 붙이는 청크 항목
            #    (「4.」 · 「1.」 · 「본문」)이 있으면 좌표를 버렸다 → 인코더 근거 좌표가 전부 비어 호 관문이 늘 닫혔다(dev 분기 0 행).
            #    항목 칸은 청크의 이름표라 좌표가 아니다 — 사전 인용(`basis`)은 종전 길(`from_article_item`)만 탄다
            c = f"{a.law_id}:{a.article}"
        try:
            law, jo, hang, ho, _ = statute.parse(c) if c else (None, 0, 0, 0, None)
        except ValueError:
            continue
        if law:
            out.add((law, jo, hang, ho))
    return out


# ── 인코더 쪽 판정 (🆕 2026-10-16 · D-348 보충 5 · 1 단계) ─────────────────────────────────────

#: 인코더 쪽 실증 문안의 법 축 — **그 전제의 주 근거**(D-272 개정 (나) ① · ⑥). 인코더 근거는 문장이 보내진 법마다 실려(`_candidate_refs`)
#:   표시광고법(늘 보낸다)이 함께 들어 축이 둘이 된다 — 축 하나를 요구하는 `rs.subst_branch` 에 전제의 주 근거 축을 준다.
#:   🔴 화장품은 고르지 않는다 — 화장품법과 표시광고법의 주 근거는 ⬜(D-272 개정 (나) ⑥) · 분기 없음(D-220).
#:   🚨 `[가정]` 문장의 사항이 거래 조건(가격 · 할인 · 출처)이면 주 근거는 표시광고법이다(같은 개정 ②) — 인코더는 사항을 가리지 않는다.
ENC_SUBST_AXIS: dict[Premise, str | None] = {
    Premise.식품: "식품표시광고법",
    Premise.일반식품_기능성: "식품표시광고법",
    Premise.건기식_인정: "식품표시광고법",
    Premise.건기식_비인정: "식품표시광고법",
    Premise.화장품: None,
    Premise.일반상품: "표시광고법",
}


def _encoder_only(s: SentenceJudgment) -> bool:
    """사전 쪽 판정이 없는 문장인가 — 사전이 확정하지 않은(사유 · 구간 없음) 확신 부족 보류에 인코더 하한이 선 문장 (보충 5 · 1 단계의 대상).

    🔄 2026-10-18 (D-348 보충 15 결정 3 · 보충 16 — 2 단계 = 사전 좁히기) — **사전 후보만 울린 문장도 인코더 쪽 판정으로 간다.**
       사전은 칸이 C 인 항목만 단독판정이고, 나머지 · 확정 막기 가드에 걸린 적중은 후보(`weak` · 유형 후보 · 근거 표시)다 —
       후보는 판정을 막지 않는다. ⛔ 종전(보충 5 결정 8)에는 후보가 울린 문장을 막았다 — 그때의 결함(신뢰 규칙 없이 조건부 위반)은
       인코더 쪽 판정이 답 없이 확정하지 않으므로(보충 5) 다시 생기지 않는다. 유형 후보 칸(`violations`)은 그대로 실려 간다.
    """
    return (
        s.verdict is Verdict.hold
        and s.hold_reason is HoldReason.low_conf
        and s.infeasibility is None
        and not s.spans
        and s.risk.encoder is not None
        and bool(s.risk.encoder_basis)
    )


def _enc_subst(s: SentenceJudgment) -> SubstBranch | None:
    """인코더 쪽 실증 분기 — 인코더 근거 유형 · 그 근거가 선 전제의 주 근거 축(`ENC_SUBST_AXIS`). 전제가 둘 이상(기록 문장) · 축이 없으면 None."""
    premises = {b.premise for b in s.risk.encoder_basis}
    if len(premises) != 1:
        return None  # 기록 문장 — 분기마다 정하고 기록은 분기에서 모은다(`_record_condition`)
    axis = ENC_SUBST_AXIS.get(next(iter(premises)))
    if axis is None:
        return None
    return rs.subst_branch(sorted({b.violation for b in s.risk.encoder_basis}), {axis})


def _encoder_side(
    s: SentenceJudgment,
    facts: list[UserFact],
    substs: list[UserSubst],
    span: Span | None = None,
    absolute_ok: bool = True,
) -> SentenceJudgment | None:
    """**인코더 쪽 판정** — 사전 쪽 판정이 없는 문장(`_encoder_only`)의 분기와 답. 바꿀 것이 없으면 None (🆕 2026-10-16 · D-348 보충 5 · 1 단계).

    ★ 사전과 따로 판정한다 — 호 관문 · 실증 유형 · 법 축은 **인코더 근거만** 본다(사전 근거와 합치지 않는다).
    ★ **답 없이 확정하지 않는다** — 답이 없으면 확신 부족 보류(`low_conf`) 그대로 + 분기. 조건부 위반이 아니다(`is_conditional` 은 `premise_unknown` 만).
       신뢰 게이트(`_encoder_trusted`)는 여기서 보지 않는다 — 어디에 어떻게 걸지는 사전과 합치는 단계(2 단계)에서 판정 뒤 정한다(D-192).
    ★ 분기는 **문구 밖 사실이 있는 유형에만**(보충 5 결정 2) — 거짓_과장의 사실 확인(문안이 승인된 종류) · 실증(`_enc_subst`) ·
       건기식 인정 전제의 질병 표방(`인정_기능성` · 결정 2 의 자격형). 인코더 근거 유형이 그 분기의 유형과 같을 때만 묻는다.
    ★ 답 셋(`Answer`) — 예: 사실 참(∧ 사실만 주장) · 실증 있음 · 인정 기능성 그대로 → 확정 · R0 · 출처 / 해당없음: 그 분기를 걷는다 /
       아니오: **확정 위반** + 출처(`_enc_confirmed` · 보충 5 결정 4 · 1-b) — 「해당없음」을 고르지 않았으니 주장 있음까지 사용자가 확인했다.
    """
    if s.not_claim:
        return None
    types0 = {b.violation for b in s.risk.encoder_basis}
    prem0 = {b.premise for b in s.risk.encoder_basis}
    if not (types0 == {Violation.질병_예방치료_표방} and prem0 == {Premise.건기식_인정}):
        absolute = _absolute_types(s)
        if absolute:
            # 🆕 2026-10-17 (보충 6 결정 5 · 6) — 그 법 축 칸이 C 인 유형은 **답 없이 위반** · 분기를 열지 않는다(관문 (b) — C 가 이긴다)
            # 🔄 2026-10-17 (보충 8 결정 1) — **품목이 정해졌을 때만** 확정한다. 품목을 모르면 전제 자체가 가정이다 — 보류 그대로(분기 없음) ·
            #    기록은 「품목 선택 필요」(`cat_unknown` · `_mark_category_needed`) · 품목을 고르면 그 품목으로 다시 판정한다
            return _enc_absolute(s, absolute, span) if absolute_ok else None
    if any(b.moved_from is not None for b in s.risk.encoder_basis):
        return None  # 전제가 옮긴 근거(인정받지 않은 기능성 · 4.나)는 자격(A) 문제다 — 사실 · 실증으로 풀리지 않는다(`_qualification` 과 같다)
    types = {b.violation for b in s.risk.encoder_basis}
    premises = {b.premise for b in s.risk.encoder_basis}
    key = dm.norm(s.text)
    fields = {k: getattr(s, k) for k in type(s).model_fields}
    if types == {Violation.질병_예방치료_표방} and premises == {Premise.건기식_인정}:
        return _enc_disease(s, facts, span)
    # 🔄 2026-10-17 (보충 11) 타사를 깎지 않는 식품 비방은 7호(부당 비교) 좌표로 관문을 본다 — 칸 조회(`_cell`)와 같은 낱말 규칙
    if not factcheck.in_gate(
        factcheck.slander_gate_coords(
            _coords(a for b in s.risk.encoder_basis for a in b.articles), s.text
        )
    ):
        return None
    # 🔴 (1-b) 낱말 사실 확인 분기는 분기 유형(거짓_과장)에만 — 화장품법 13조①4호는 기만과 같은 호라 관문만으로는 기만 문장에도 선다
    word_kinds = (
        [k for k in factcheck.fact_kinds(s.text) if k in factcheck.FACT_TEXTS]
        if types == {Violation.거짓_과장}
        else []
    )
    # 🆕 2026-10-17 (보충 6 결정 3 · 4 · 보충 7 결정 7) — **유형에 딸린 사실 종류** — 그 전제 축의 칸이 B 인 유형만(C 는 위에서 끝났다)
    b_types = [
        v
        for v in sorted(types, key=list(Violation).index)
        if infeasibility_of(
            _basis_cells(b for b in s.risk.encoder_basis if b.violation is v), s.text
        )
        is Infeasibility.B
    ]

    def _ask_as(v: Violation) -> list[str]:
        # 🆕 (보충 10) 타사를 깎아내리지 않는 「비방」 문장은 비교 · 우월 주장이다 — 비교 기준을 묻는다
        # 🔄 (보충 11) 비교 · 우월 표지(`comparison_claim`)가 있을 때만 묻는다 — 없으면(범주 깎기 · 전문성 자랑 등) 묻지 않는다:
        #    보류 그대로 + 화면의 기준 한 줄(`reasons.slander_note`). 맞지 않는 질문을 띄우지 않는다(보충 9 결정 1 · 질문은 사실 하나)
        if v is Violation.비방광고 and not factcheck.slander_absolute(s.text):
            return [Violation.부당_비교광고.value] if factcheck.comparison_claim(s.text) else []
        # 🆕 (보충 13) 조건 고지(표시광고법 제3조①2호 · 은폐 · 축소)는 **표시광고법 축의 기만에만** 묻는다 — 전용법 축(식품 8조①5호 ·
        #    화장품 13조①4호)의 근거가 있으면 묻지 않는다: 식품 [별표 1] 5(가 ~ 카)에 은폐 · 축소 목이 없고, 「예」가 R0 으로 닫는다(보충 6)
        if v is Violation.소비자_기만 and any(
            ax in _SPECIAL_AXES
            for _, ax in _basis_cells(b for b in s.risk.encoder_basis if b.violation is v)
        ):
            return []
        return [v.value]

    def _kinds_of(v: Violation) -> list[FactKind]:
        # 🆕 (보충 14) 조건표에 있는 무첨가 표현(설탕 무첨가 · 무가당 · 나트륨 무첨가 · 무가염)을 쓴 식품 축의 비교 · 비방 문장은
        #    비교 기준 대신 무첨가 조건을 묻는다 — 식품 [별표 1] 7.나 단서(고시가 정한 무첨가 표시는 조건을 지키면 쓸 수 있다)
        if (
            v in (Violation.부당_비교광고, Violation.비방광고)
            and FactKind.무첨가_조건 in factcheck.FACT_TEXTS
            and factcheck.nofree_conditions(s.text)
            and any(
                ax == _FOOD_AX
                for _, ax in _basis_cells(b for b in s.risk.encoder_basis if b.violation is v)
            )
        ):
            return [FactKind.무첨가_조건]
        # 🆕 (보충 15) 조건표 밖 무첨가 꼴은 묻지 않는다 — 7.나 단서는 고시가 정한 표시뿐이라 비교 기준 질문이 맞지 않는다 ·
        #    보류 그대로 + 화면의 기준 한 줄(`reasons.nofree_note`)
        if (
            v in (Violation.부당_비교광고, Violation.비방광고)
            and factcheck.nofree_outside_table(s.text)
            and any(
                ax == _FOOD_AX
                for _, ax in _basis_cells(b for b in s.risk.encoder_basis if b.violation is v)
            )
        ):
            return []
        return factcheck.type_kinds(_ask_as(v))

    t_kinds = [
        k for k in dict.fromkeys(k for v in b_types for k in _kinds_of(v)) if k not in word_kinds
    ]
    kind_type = {k: Violation.거짓_과장 for k in word_kinds} | {
        k: v for v in b_types for k in _kinds_of(v)
    }
    kinds = word_kinds + t_kinds
    ans: dict[FactKind, UserFact] = {}
    for f in facts:
        if f.kind in kinds and f.kind not in ans and dm.norm(f.text) == key:
            ans[f.kind] = f
    carried = [ans[k] for k in kinds if k in ans]
    kinds = [k for k in kinds if not (k in ans and ans[k].answer is Answer.해당없음)]
    no = [k for k in kinds if k in ans and ans[k].answer is Answer.아니오]
    if no:
        return _enc_confirmed(s, kind_type[no[0]], span, user_facts=carried)
    reason = _encoder_reason(s)
    sb = _enc_subst(s) if reason is Infeasibility.B else None
    pending = [k for k in kinds if k not in ans]
    if pending:
        t = factcheck.FACT_TEXTS[pending[0]]
        cap = min(t.confirmed_max, s.risk.final, key=lambda r: r.level)  # type: ignore[arg-type]
        then = None if factcheck.fact_only(s.text) else sb
        return SentenceJudgment(
            **{
                **fields,
                "infeasibility": Infeasibility.B if then is not None else s.infeasibility,
                "substantiation": then,
                "fact_check": FactBranch(
                    kind=pending[0],
                    confirmed_max=cap,
                    accepted_evidence=list(t.accepted_evidence),
                    criteria=t.criteria,
                ),
                "user_facts": carried,
            }
        )
    if [
        k for k in t_kinds if k in kinds
    ] and not word_kinds:  # 「해당 없음」으로 걷힌 갈래는 세지 않는다
        # 🆕 (보충 6 결정 3 · 4) 유형에 딸린 사실이 전부 「예」 — 갈래 ① (객관적 근거)이 따로 있는 유형은 실증 갈래가 서야 닫는다(갈래 결과 max)
        if any(v.value in factcheck.NEED_SUBST for v in b_types) and sb is None:
            return SentenceJudgment(**{**fields, "user_facts": carried})
        if sb is None:
            return _answered(s, user_facts=carried)
    elif kinds and factcheck.fact_only(s.text):
        return _answered(s, user_facts=carried)  # 남은 사실이 전부 참 · 사실만 주장
    if sb is None:
        return SentenceJudgment(**{**fields, "user_facts": carried}) if carried else None
    us = next((u for u in substs if dm.norm(u.text) == key), None)
    if us is not None:
        if us.answer is Answer.예 and sb.substantiated_max is Risk.R0:
            return _answered(s, user_facts=carried, user_subst=us)
        if us.answer is Answer.아니오:
            sv = b_types[0] if len(b_types) == 1 else Violation.거짓_과장
            return _enc_confirmed(s, sv, span, user_facts=carried, user_subst=us, subst=sb)
        # 해당없음 — 실증 분기를 걷는다 · 보류 + 출처
        return SentenceJudgment(**{**fields, "user_facts": carried, "user_subst": us})
    return SentenceJudgment(
        **{
            **fields,
            "infeasibility": Infeasibility.B,
            "substantiation": sb,
            "user_facts": carried,
        }
    )


def _absolute_types(s: SentenceJudgment) -> set[Violation]:
    """인코더 근거 중 **사유가 C 인 유형** — 유형마다 그 유형 근거의 칸으로(`infeasibility_of` · 전용법 칸 먼저 · 전제의 법만)."""
    out: set[Violation] = set()
    for v in {b.violation for b in s.risk.encoder_basis}:
        cells = _basis_cells(b for b in s.risk.encoder_basis if b.violation is v)
        if infeasibility_of(cells, s.text) is Infeasibility.C:
            out.add(v)
    return out


def _enc_absolute(
    s: SentenceJudgment, types: set[Violation], span: Span | None
) -> SentenceJudgment | None:
    """인코더 쪽 **절대형(C) 위반** — 답 없이 확정한다 (🆕 2026-10-17 · D-348 보충 6 결정 5 · 보충 7 결정 10).

    ★ 칸 — 유형 = 칸이 C 인 인코더 근거 유형(섞인 A · B 유형은 싣지 않는다 — C 가 남는 한 그 답으로 결론이 바뀌지 않는다) ·
       근거 = 대응표 조항(`basis` 거짓) · 구간 = **문장 전체** · 위험도 = 그 유형 · 전제의 **제재표 하한**(`EncoderBasis.floor` · 1-b 와 같은 값) ·
       사유 C · 실증 분기 없음. 출처는 사전 근거(`basis`)도 사용자 답도 없는 확정이다 — 화면은 `contracts.encoder_judged` 로 가린다.
    🔴 구간을 못 세우면 None(보류 그대로 · 분기 없음 · D-220). 🚨 인코더를 믿어도 되는지(신뢰 규칙)는 2 단계에서 판정한다(보충 5 결정 6).
    """
    basis = [b for b in s.risk.encoder_basis if b.violation in types]
    if span is None or not basis:
        return None
    floor = max((b.floor for b in basis), key=lambda r: r.level)
    arts: list[EvidenceArticle] = []
    for b in basis:
        for a in b.articles:
            if a not in arts:
                arts.append(a)
    vs = sorted(types, key=list(Violation).index)
    return SentenceJudgment(
        sent_id=s.sent_id,
        text=s.text,
        verdict=Verdict.confirmed,
        violations=vs,
        infeasibility=Infeasibility.C,
        evidence=arts,
        risk=RiskAssessment(floor=floor, final=floor),
        encoder_candidates=s.encoder_candidates,
        spans=[Span(start=span.start, end=span.end, label=",".join(v.value for v in vs))],
    )


def _enc_disease(
    s: SentenceJudgment, facts: list[UserFact], span: Span | None
) -> SentenceJudgment | None:
    """인코더 쪽 **건기식 인정 질병 분기** — 건기식_인정 전제에서 인코더만 질병 표방을 잡은 문장 (🆕 2026-10-17 · 보충 5 결정 2 · 1-b).

    ★ 질문(`인정_기능성` · 인정받은 기능성 문구 그대로인가)은 **인코더 쪽에만** 선다(🔄 2026-10-18 보충 20 — 사전 쪽 분기는 걷었다) · 문안이 승인되기 전에는 서지 않는다.
       답 없음 → 보류 그대로 + 분기 · 예 → 확정 · R0 · 출처 · 아니오 → 질병 표방 확정 위반(C) + 출처 · 해당없음 → 보류 + 출처.
    """
    if FactKind.인정_기능성 not in factcheck.FACT_TEXTS or s.risk.final is None:
        return None
    key = dm.norm(s.text)
    fields = {k: getattr(s, k) for k in type(s).model_fields}
    uf = next((f for f in facts if f.kind is FactKind.인정_기능성 and dm.norm(f.text) == key), None)
    if uf is None:
        t = factcheck.FACT_TEXTS[FactKind.인정_기능성]
        return SentenceJudgment(
            **{
                **fields,
                "fact_check": FactBranch(
                    kind=FactKind.인정_기능성,
                    confirmed_max=min(t.confirmed_max, s.risk.final, key=lambda r: r.level),
                    accepted_evidence=list(t.accepted_evidence),
                    criteria=t.criteria,
                ),
            }
        )
    if uf.answer is Answer.예:
        return _answered(s, user_facts=[uf])
    if uf.answer is Answer.아니오:
        return _enc_confirmed(s, Violation.질병_예방치료_표방, span, user_facts=[uf])
    return SentenceJudgment(**{**fields, "user_facts": [uf]})


def _enc_confirmed(
    s: SentenceJudgment,
    v: Violation,
    span: Span | None,
    *,
    user_facts: list[UserFact] | None = None,
    user_subst: UserSubst | None = None,
    subst: SubstBranch | None = None,
) -> SentenceJudgment:
    """인코더 쪽 문장을 **사용자의 「아니오」로 확정 위반**으로 (🆕 2026-10-17 · D-348 보충 5 결정 4 · 1-b · D-348 결정 3 의 칸).

    ★ 칸 — 유형 = 그 분기의 유형(인코더 근거 유형과 같을 때만) · 근거 = 그 유형의 대응표 조항(문장에서 찾은 조문이 아니다 · `basis` 거짓) ·
       구간 = **문장 전체**(결정 3) · 위험도 = 그 유형 · 그 전제의 **제재표 하한**(`EncoderBasis.floor` · 사전 확정이 인용 호의 하한을 쓰는 것과 같다) ·
       사유 = 그 근거의 칸(`infeasibility_of` · 보충 6) · 실증 없음이면 실증 분기(지시 문안) · 사실 거짓이면 실증 분기 없음(지시 문안은 「고치거나 빼기」).
    🔴 못 세우면(구간을 모른다 · 근거 유형이 다르다 · 섞였다) **보류 + 출처** — 지어내지 않는다 (D-220 · D-224).
    🚨 `[판정 대기]` 위험도를 제재표 하한으로 올린다 — 답 없는 인코더 쪽의 기록 위험도(R1 층 상한)보다 높을 수 있다. 유형은 질문이 보인 유형을
       사용자가 「해당없음」으로 닫지 않은 것으로 섰다고 본다(결정 5 「R2 이상: 유형을 믿을 수 있어야」의 해석).
    """
    fields = {k: getattr(s, k) for k in type(s).model_fields}
    held = SentenceJudgment(
        **{**fields, "user_facts": list(user_facts or []), "user_subst": user_subst}
    )
    basis = [b for b in s.risk.encoder_basis if b.violation is v]
    if span is None or not basis or {b.violation for b in s.risk.encoder_basis} != {v}:
        return held
    floor = max((b.floor for b in basis), key=lambda r: r.level)
    arts: list[EvidenceArticle] = []
    for b in basis:
        for a in b.articles:
            if a not in arts:
                arts.append(a)
    reason = infeasibility_of(_basis_cells(basis), s.text)
    if reason is None:
        return held
    return SentenceJudgment(
        sent_id=s.sent_id,
        text=s.text,
        verdict=Verdict.confirmed,
        violations=[v],
        infeasibility=reason,
        evidence=arts,
        risk=RiskAssessment(floor=floor, final=floor),
        encoder_candidates=s.encoder_candidates,
        spans=[Span(start=span.start, end=span.end, label=v.value)],
        substantiation=subst if reason is Infeasibility.B else None,
        user_facts=list(user_facts or []),
        user_subst=user_subst,
    )


def _with_condition(
    s: SentenceJudgment,
    facts: list[UserFact],
    substs: list[UserSubst],
    span: Span | None = None,
    absolute_ok: bool = True,
) -> SentenceJudgment | None:
    """문장 하나의 분기 · 답 — 사전 쪽 판정이 없는 문장(인코더만)을 **인코더 쪽 판정**(`_encoder_side`)으로 보낸다. 바꿀 것이 없으면 None.

    🔄 2026-10-18 (D-348 보충 20 · 보충 16 결정 5 집행) — 종전에는 사전 확정 문장의 **조건부 위반**(호 관문 · 사실 → 실증 이어 묻기 ·
       보충 4)도 여기서 세웠다. 사전이 칸 C 만 확정하면서(보충 16) 그 경로로 오는 문장이 0 이 됐고, 걷었다(보충 15 결정 3 · 사전 확정에는 분기 없음).
       조건부 위반 분류 · 뒷단은 남는다 — 생성처(인코더 쪽 신뢰 규칙)는 재학습판 측정 뒤 판정(보충 17 결정 2).
    """
    if s.not_claim or s.user_subst is not None or s.fact_check is not None or is_conditional(s):
        return None
    if s.user_facts and s.verdict is Verdict.confirmed:
        return None  # 이미 답으로 정해진 문장(확정) — 다시 정하지 않는다
    if not (
        (s.verdict is Verdict.confirmed and s.violations)
        or (s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf)
    ):
        return None
    # 🔄 2026-10-16 (D-348 보충 5 · 1 단계) — **사전과 인코더는 따로 판정한다.** 사전 쪽 판정이 없는 문장(인코더만)은 인코더 쪽 판정으로
    if _encoder_only(s):
        return _encoder_side(s, facts, substs, span, absolute_ok)
    # 🔄 2026-10-18 (D-348 보충 20 · 보충 16 결정 5 집행) — **사전 쪽 조건부 위반 경로(사실 · 실증 분기)는 걷었다.** 사전은 칸 C 만 확정하고
    #    (보충 16) C 항목의 호는 조건부 호가 아니다 — 사전 확정 문장에는 분기를 달지 않는다(보충 15 결정 3). 확정이 아닌 문장은 위에서 갈랐다
    #    (인코더만 → `_encoder_side` · 그 밖 → 분기 없음 · 2 단계 = 사전 좁히기).
    #    ★ 조건부 위반 분류(`is_conditional`)와 뒷단(기록 모음 · 종착 · 저장 · 화면 · 평가)은 남긴다 — 생성처는 인코더 쪽 신뢰 규칙(`_encoder_trusted`)의
    #      자리이고, 끼울지 · 어디에 끼울지는 재학습판 측정 뒤 판정한다(보충 17 결정 2 · 보충 5 결정 6 · D-192)
    return None


#: 🔴 **인코더만 잡은 거짓_과장의 확정 신뢰 문턱 τ** (D-348 보충 1 결정 2) — 값이 아니라 고르는 규칙으로 정한다: 서술 · 주장 표지 ∧ 거부 가드를
#:    지난 후보에서 확장 dev 의 확정 적법 ≤ 1 인 가장 낮은 τ → 데이터 밖(검수판 측정용 171 · 다른 생성기 적법 213)에서 확정 95% 상한 ≤ 2% `[임의]`
#:    를 넘으면 연다. **None = 닫힘**(관문 전 · fail-closed · D-220) — 판에 딸린 값이라 판이 바뀌면 다시 고른다(보충 1 결정 5)
ENCODER_CONFIRM_TAU: float | None = None


def _encoder_trusted(s: SentenceJudgment) -> bool:
    """확신 부족 보류를 조건부 위반(답하지 않으면 확정 B)으로 들여도 되는가 — D-348 결정 5 의 신뢰 규칙 (보충 1 결정 2).

    = 문턱이 열렸다(`ENCODER_CONFIRM_TAU`) ∧ 주장 가드(주의 · 상담 아님 ∧ 거부 가드에 안 걸림 ∧ 서술 · 광고 표지 · `claimscope.claim_guard`)
      ∧ 인코더 근거 유형이 전부 거짓_과장 ∧ 그 후보의 확신 ≥ τ. 문턱이 닫혔으면 늘 거짓이다.
    🚨 2026-10-18 (D-348 보충 20) — **지금 부르는 곳이 없다.** 유일한 호출 자리는 걷은 사전 쪽 조건부 경로 안이었다(인코더만 잡은 문장은 그 앞에서
       인코더 쪽 판정으로 빠져 닿지 않았다). 인코더 쪽 판정의 어디에 끼울지 · 끼울지는 재학습판 측정 뒤 판정한다(보충 17 결정 2 · 보충 5 결정 6 · D-192)
    """
    tau = ENCODER_CONFIRM_TAU
    if tau is None or not s.risk.encoder_basis or not claimscope.claim_guard(s.text):
        return False
    if {b.violation for b in s.risk.encoder_basis} != {Violation.거짓_과장}:
        return False
    conf = max(
        (
            c.confidence
            for c in s.encoder_candidates
            if c.violation is Violation.거짓_과장 and c.moved_from is None
        ),
        default=0.0,
    )
    return conf >= tau


def _encoder_reason(s: SentenceJudgment) -> Infeasibility | None:
    """사유가 비어 있는 문장(인코더만 잡은 보류)의 사유 — 인코더 근거의 (유형 × 법 축) 칸에서 **더 막힌 쪽**(`infeasibility_of`).

    🔄 2026-10-17 (보충 6 결정 6) — 종전 「유형의 사유가 하나로 같을 때만」은 화장품 상품의 비방(화장품 C · 표시광고법 B)에서 사유를 비웠다.
       칸은 그 근거가 선 전제의 법만 센다(`_basis_cells`) · 칸이 없는 유형이 섞이면 None(사유 모름).
    """
    return infeasibility_of(_basis_cells(s.risk.encoder_basis), s.text)


def _answered(
    s: SentenceJudgment,
    *,
    user_facts: list[UserFact] | None = None,
    user_subst: UserSubst | None = None,
) -> SentenceJudgment:
    """사용자의 답으로 위반이 풀린 문장 — 확정 · 위반 없음 · R0 · 출처 (보충 3 결정 4 · 보충 4 결정 3). 인코더 후보(표시용)는 남긴다."""
    return SentenceJudgment(
        sent_id=s.sent_id,
        text=s.text,
        verdict=Verdict.confirmed,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
        encoder_candidates=s.encoder_candidates,
        user_facts=list(user_facts or []),
        user_subst=user_subst,
    )


#: 코어 순서 — 팬아웃 앞 · 법별 노드(`LAW_NODES` · 병렬) · 팬아웃 뒤. 컴파일본과 스텁이 **이 표 하나**를 쓴다 (D-99).
CORE_BEFORE_LAWS = ("split", "classify", "retrieve", "match_dict", "encode")
CORE_AFTER_LAWS = ("merge_laws", "judge", "assess_risk", "premise_branches", "doc_rules")
NODES: dict[str, Callable[..., dict[str, Any]]] = {
    **{f.__name__: f for f in (split, classify, retrieve, match_dict, encode)},
    **{name: _law_node(name) for name in LAW_NODES},
    **{f.__name__: f for f in (merge_laws, judge, assess_risk, premise_branches, doc_rules)},
}


# ══════════════════════════════════════════════════════════════════════
#  검수 (진입점 A) — 종착 넷 · 루프 없음 (D-265 · D-268)
# ══════════════════════════════════════════════════════════════════════


def _certificate_of(sents: list[SentenceJudgment], category: Category | None) -> Certificate | None:
    """증명서 조립 (🆕 2026-10-06 · D-320 · D-59 · D-125). 문안은 `app/reasons.py` 의 승인된 줄만 — 없으면 **None**.

    ★ 자격형 · 절대형 문장마다 (품목의 법, 유형, 사유)로 문안을 꺼낸다. 증명서의 사유는 **가장 막힌 사유**(절대형 > 자격형 ·
       종착 우선순위와 같다)이고 설명은 그 사유의 문장들에서 꺼낸 글을 문장 순서대로 겹치지 않게 잇는다.
       자격 안내는 증명서의 사유가 자격형일 때만 싣는다 — 절대형 증명서에 「인정받으면 된다」를 함께 적지 않는다(D-61 🚨).
    🔴 자격형 · 절대형 문장 중 **하나라도 문안이 없으면 증명서를 내지 않는다** — 일부 문장만 설명하는 증명서는 나머지가
       왜 불가인지 말하지 못한다(D-220). 품목 미확정 · 일반상품 · 전용법 미수록도 꺼낼 법이 없어 None 이다(D-320 ⑤).
    ⛔ 실증형(B) 문장은 보지 않는다 — 증명서의 대상이 아니다(D-59 · D-268).
    """
    picked: list[tuple[Infeasibility, list[rs.ReasonText]]] = []
    for s in sents:
        if not s.violations or s.infeasibility not in (Infeasibility.A, Infeasibility.C):
            continue
        got = [t for v in s.violations if (t := rs.lookup(category, v, s.infeasibility))]
        if not got:
            return None
        picked.append((s.infeasibility, got))
    if not picked:
        return None
    top = next(r for r in _INFEAS_ORDER if any(i is r for i, _ in picked))
    lines = [t for i, got in picked if i is top for t in got]
    explanation = list(dict.fromkeys(t.explanation for t in lines))
    guidance = list(dict.fromkeys(t.guidance for t in lines if t.guidance))
    return Certificate(
        reason=top,
        explanation=" ".join(explanation),
        guidance=" ".join(guidance) if top is Infeasibility.A and guidance else None,
    )


@timed
def certificate(state: ReviewState) -> dict[str, Any]:
    """합법화 불가 증명서 (D-32). **A 자격형 · C 절대형에만** (D-125).

    🔄 2026-10-06 (D-320) — **조립기가 섰다**(`_certificate_of`). 승인된 문안이 있는 조합이면 증명서를 내고, 없으면 종전대로 보류다.

    🔴 계약은 `outcome=certificate` 에 증명서(`Certificate` · 사유 · 설명)를 요구한다. 설명은 사용자에게 보이는 문안이라
       승인된 줄만 쓴다(`app/reasons.py` · D-263 ②). 증명서를 못 지으면 **보류로 내린다** — 문안이 없는 조합 · 품목 미확정 ·
       일반상품 · 전용법 미수록이 여기다(D-320 ② ⑤).
       ⛔ 빈 증명서로 종착을 찍으면 계약이 응답을 거부해 화면에 오류가 난다 — 위험도가 붙은 뒤로는 실제 요청이 여기 온다.
       문장 판정(확정 · 유형 · 근거 · 위험도)은 그대로 나간다.
       (2026-10-02 · W5 에는 조립기가 없어 이 종착이 늘 보류였다.)
    """
    cert = state.get("certificate")
    if cert is None and state.get("sentences"):
        category = (state.get("product") or ProductContext()).category
        cert = _certificate_of(list(state["sentences"]), category)
        if cert is None:
            return {"outcome": Outcome.hold}
        return {"outcome": Outcome.certificate, "certificate": cert}
    return {"outcome": Outcome.certificate}


def guidance_ready(sents: list[SentenceJudgment]) -> bool:
    """「지시」의 재료가 다 있는가 — 확정된 B 실증형 위반마다 **실증 분기와 뺄 구간** (D-268 · 계약 `_guidance_payload` 와 같은 조건)."""
    subst = [s for s in sents if s.infeasibility is Infeasibility.B and s.violations]
    return bool(subst) and all(s.substantiation is not None and s.spans for s in subst)


@timed
def guidance(state: ReviewState) -> dict[str, Any]:
    """「지시」 — 확정된 **실증형** 위반: 뺄 구간 · 실증 자료의 종류 · 내려갈 수 있는 등급 (D-268).

    🔄 2026-09-23 (W3) — 계약에 `Outcome.guidance` 가 섰다 (D-274). 종전에는 보류로 끝냈다.
    ⛔ 통과로 보내지 않는다 — 확정 위반이다. 증명서도 아니다 — 실증형이다 (D-59).
    🔴 2026-10-02 (W5) — 계약은 지시 문장마다 **실증 분기와 뺄 구간**을 요구한다(`_guidance_payload`). 실증 분기는 기준 문안
       (조문을 인용한 설명 · D-263 ②)을 싣는데 **문안이 아직 초안**이다 — 재료가 모자라면 **보류로 내린다** (D-220).
       ⛔ 종전 주석 「지금 이 노드에 오는 길은 없다」는 위험도가 붙으면서 틀린 말이 됐다. 문안이 확정되면 이 분기가 사라진다 (D-192).
    🔄 2026-10-18 (D-348 보충 20) — 사전 쪽 실증 분기(`_substantiated`)는 걷었다 · 지금 지시 종착의 재료는 인코더 쪽 실증 답뿐이다(dev 지시 0 · 원장 10-18(B) ⑤).
    🔄 2026-10-14 (D-337) — 실증 분기는 `assess_risk` · `premise_branches` 가 채운다(`_substantiated`). 지시 종착이 선다 —
       dev 749 행 중 63(원장 10-14(A) ⑧). 위 「재료가 모자라면 보류로 내린다」는 그대로 산다(`guidance_ready`).
       ⛔ 종전 주석 「실증 분기를 채우는 노드가 아직 없다 · 늘 보류」(10-06)는 D-337 로 틀린 말이 됐다 (2026-10-15 전수 점검).
    """
    sents = list(state.get("sentences", []))
    if sents and not guidance_ready(sents):
        return {"outcome": Outcome.hold}
    return {"outcome": Outcome.guidance}


@timed
def hold(state: ReviewState) -> dict[str, Any]:
    """전문가 검토 종착 (D-125).

    🔴 **종착에도 노드가 있어야 한다** (2026-09-10 실측) — 라우터가 곧장 `END` 로 보내면 컴파일본만 `outcome` 이
       None 으로 끝났다. 라우터 단독 테스트로는 안 잡히는 자리다.
    """
    return {"outcome": Outcome.hold}


@timed
def passed(state: ReviewState) -> dict[str, Any]:
    """통과 — 전부 확정 ∧ R0 (D-125 · 🔄 D-273). 🚨 「적법」이라 부르지 않는다 (D-130).

    🔄 D-265 — 검수의 통과는 **프론티어를 내지 않는다.** 프론티어는 생성(B)의 것이다.
    """
    return {"outcome": Outcome.passed}


REVIEW_TERMINALS: dict[str, Callable[..., dict[str, Any]]] = {
    f.__name__: f for f in (certificate, guidance, hold, passed)
}
ROUTES_REVIEW = tuple(REVIEW_TERMINALS)


def route_review(state: ReviewState) -> str:
    """검수 종착 (D-125 · D-265 · D-268). 우선순위 **보류 > 증명서 > 지시 > 통과**.

    🔴 **하나라도 확정이 아니면 보류다** — 스텁이 내는 `unjudged` 가 통과로 흘러 종착이 `pass` 로 찍힌 적이 있다
       (2026-09-10 · 미판정을 통과로 집계). ⛔ A 자격형이 섞이면 증명서 — 재생성하지 않는다 (D-59).
    🆕 D-268 — 확정된 **B 실증형**은 「지시」다. 종전에는 재생성 루프(`generate`)로 갔다 — 검수는 문구를 안 만든다 (D-265).
    """
    sents = state.get("sentences", [])
    if not sents:
        return "hold"
    # 🔄 2026-10-16 (D-348 보충 4 결정 2) — **조건부 위반**(답하면 확정되는 보류)은 **답하지 않은 경우 = 확정 B** 로 센다
    #    (D-263 ① 기록 = 가장 나쁜 경우) — A/C 가 섞이면 증명서 · B 만이면 지시(재료가 없으면 `guidance` 가 보류로) · 통과는 아니다(확정 ∧ R0).
    #    그 밖의 확정 아님은 보류다
    if any(s.verdict is not Verdict.confirmed and not is_conditional(s) for s in sents):
        return "hold"
    # 🆕 2026-10-01 (W4 1판) — **위험도가 없는 확정 위반은 증명서 · 지시로 못 간다** — 보류다 (D-268 「막힘」 · D-220).
    #    지시는 실증 분기(실증 전 위험도)를, 증명서는 사유 설명을 요구한다 — 하한(`sanction_rule` · W5)이 서기 전에는 어느 쪽도
    #    계약을 못 지난다. ⛔ 위험도를 지어내지 않는다 (D-09 · D-131). 문장 판정(확정 · 위반 · 근거 · 구간)은 그대로 나간다.
    #    ⬜ D-227 「제재 기준이 없을 때 무엇을 내나」 — 판정 대기. 이 줄이 그 판정이 들어올 자리다 (D-192)
    #    🔄 2026-10-06 — 하한은 섰다(`assess_risk` · W5). 지금 이 줄에 걸리는 것은 제재표에서 하한을 못 읽은 확정 위반이다
    #       (표가 비었다 · 맞는 행이 없다 · 품목 미확정인데 분기가 서지 않았다).
    if any(s.violations and s.risk.final is None for s in sents):
        return "hold"
    reasons = {s.infeasibility for s in sents if s.infeasibility}
    if reasons & {Infeasibility.A, Infeasibility.C}:
        return "certificate"
    if Infeasibility.B in reasons:
        return "guidance"
    # 🔴 통과는 D-125 의 정의대로만 — 확정 ∧ R0 (🔄 D-273 · `is_pass`) · 위험도가 없으면 통과가 아니다
    if all(is_pass(s) for s in sents):
        # 🆕 2026-10-02 (D-271 ④ · D-277 개정) — 주된 광고법을 안 본 품목은 통과가 없다. 계약(`_uncovered_law_notice`)과 같은 규칙 (D-99)
        category = (state.get("product") or ProductContext()).category
        if category is None and any(s.not_claim for s in sents):
            # 🆕 2026-10-15 (D-348 보충 1 · D-319 결정 2) — 품목 미확정에는 맨 위 통과를 내지 않는다. 판정 대상 아님(L0)이 이 그래프에
            #    처음으로 「확정 ∧ R0」 문장을 내므로 그 길에서 막는다 · 품목을 알면 통과(D-275 · 계약 고정물 16)
            return "hold"
        return "hold" if category in UNCOVERED_CATEGORIES else "passed"
    return "hold"


# ══════════════════════════════════════════════════════════════════════
#  생성 (진입점 B) — 규칙 조립 · 주장 원장 · 재판정 루프 (D-264 · D-30 · D-126)
# ══════════════════════════════════════════════════════════════════════


@timed
def keyword_screen(state: GenerateState) -> dict[str, Any]:
    """지향 키워드 선별 — 코어를 **어휘 모드**로 부른다 (기획서 3-3). 🔜 차단에는 사유가 붙는다."""
    return {}


@timed
def assemble(state: GenerateState) -> dict[str, Any]:
    """규칙 조립 4종 — 삭제안 · 사실 진술 치환 · 인정 문구 슬롯 · 실증 유지 (D-264). 🔜 W9.

    🔴 **첫 조립이 `attempt=0` 이다** (D-126 · 0-base · 총 라운드 K+1=3). ⛔ 종전(검수 그래프 안)에는 원문 판정이
       0 을 차지해 **조립이 두 번뿐**이었다 — 최악 호출 N×(K+1)=9 가 6 이 되던 자리다.
    ⬜ sLLM 은 같은 전제 안의 **다듬기**로만 뒤에 붙는다 — D-270 으로 설계만.
       🔄 2026-10-06 — 검수 화면의 문장 고쳐 쓰기(`POST /u/review/rewrite` · `app/routers/sllm_client.py`)가 병합됐다. 그 경로는
          이 그래프를 거치지 않고, 이 노드는 그대로다. D-265 · D-270 과의 관계 · 승인 범위는 **판정 대기**다
          (D-270 은 「전제 정정 · 결론 재검 대기」).
    """
    attempt = state.get("attempt")
    return {"attempt": 0 if attempt is None else attempt + 1}


@timed
def claim_ledger(state: GenerateState) -> dict[str, Any]:
    """주장 원장 — `신규주장 = 생성주장 − (제품사실 ∪ 입력주장)` ≠ ∅ 이면 거부 (D-30). 🔜 W9.

    🔜 거부하면 `rejected=True` · `rejects` 에 사유 — 세 거부는 **한 카운터**다 (D-126).
    """
    return {}


@timed
def rejudge(state: GenerateState) -> dict[str, Any]:
    """후보를 **자기 전제로** 코어에 다시 넣는다 (D-264 · D-119). 🔜 W9 — `build_core()` 를 문장 모드로 부른다.

    🚨 판정 코어는 하나다 — 여기서 판정을 새로 쓰지 않는다 (D-119 · D-266).
    """
    return {}


@timed
def frontier(state: GenerateState) -> dict[str, Any]:
    """리스크–소구력 프론티어 (D-31) — **같은 전제의 후보끼리**만 (D-264). 단일 답을 주지 않는다.

    🔄 D-274 — 생성 종착 `frontier`. ⛔ 종전에는 검수의 `pass` 를 빌려 썼다 — 「통과」가 아니다(후보에 잔여 위험도가 붙는다).
    """
    return {"outcome": GenerateOutcome.frontier}


@timed
def search_failed(state: GenerateState) -> dict[str, Any]:
    """표현 탐색 실패 — K 를 소진했다 (D-125). 🚨 증명서를 내지 않는다 — 「B 를 C 처럼 답하기」다 (D-59).

    🔄 D-265 · D-266 — **생성에서만** 난다. 검수에서는 실증 분기가 대신한다.
    """
    return {"outcome": GenerateOutcome.search_failed}


GENERATE_NODES: dict[str, Callable[..., dict[str, Any]]] = {
    f.__name__: f
    for f in (keyword_screen, assemble, claim_ledger, rejudge, frontier, search_failed)
}
GENERATE_ROUND = ("assemble", "claim_ledger", "rejudge")
ROUTES_AFTER_REJUDGE = ("frontier", "assemble", "search_failed")


def route_after_rejudge(state: GenerateState) -> str:
    """재생성 루프의 갈림 (D-126 · D-125).

    🔴 **이번 시도**의 판정(`rejected`)을 본다 — 누적 `rejects` 가 비었는지로 읽으면 한 번 거부된 뒤 통과해도
       탐색 실패로 끝난다(전수 재검토 I3). 🔄 2026-10-01 — `rejected` 를 안 적었으면 **거부**다 — 모르면 거부 쪽이다.
    🚨 K 를 소진한 것은 **증명서가 아니라** 「표현 탐색 실패」다 (D-59).
    ⬜ 재판정이 보류·근거없음을 남기는 경우의 `hold` 종착 — 🔜 `rejudge` 가 판정을 낼 때 같이 (D-266 표).
    """
    rejected = state.get("rejected")
    if rejected is None:
        # 🔄 2026-10-01 — ⛔ 종전 `bool(rejects)` 는 아무도 안 적은 상태(주장 원장 · 재판정 스텁)를 **통과(프론티어)**로 보냈다 —
        #    위 docstring 「모르면 거부 쪽」과 반대였다 (D-220 · D-125 (a) 기각). 이번 시도의 판정이 없으면 **거부**다
        rejected = True
    if not rejected:
        return "frontier"
    if state.get("attempt", 0) >= MAX_ATTEMPT:
        return "search_failed"
    return "assemble"


# ══════════════════════════════════════════════════════════════════════
#  한 바퀴 — langgraph 없이도 컴파일본과 같은 순서를 낸다 (D-124 ②)
# ══════════════════════════════════════════════════════════════════════


def _apply(state: dict[str, Any], out: dict[str, Any], reducers: tuple[str, ...]) -> None:
    for k, v in out.items():
        state[k] = reducer_of(k)(list(state.get(k, [])), list(v)) if k in reducers else v


def _run_core(state: dict[str, Any], visited: list[str]) -> None:
    """코어 한 바퀴 (스텁). 🚨 법별 노드는 **`law_payload()` 만** 받는다 — 컴파일본의 `Send` 와 같다."""
    reducers = STATE_REDUCERS["core"][1]

    def step(name: str, arg: dict[str, Any]) -> None:
        visited.append(name)
        _apply(state, NODES[name](arg), reducers)

    for name in CORE_BEFORE_LAWS:
        step(name, state)
    for name in route_laws(state):  # type: ignore[arg-type]
        step(name, law_payload(state))  # type: ignore[arg-type]
    for name in CORE_AFTER_LAWS:
        step(name, state)


def run_review_stub(
    text: str, product: ProductContext | None = None
) -> tuple[ReviewState, list[str]]:
    """검수 스텁 한 바퀴. 상태와 **방문 순서**를 돌려준다 — 컴파일본(`build_review`)과 같아야 한다."""
    state: dict[str, Any] = {"text": text, "product": product or ProductContext()}
    visited: list[str] = []
    _run_core(state, visited)
    nxt = route_review(state)  # type: ignore[arg-type]
    visited.append(nxt)
    _apply(state, REVIEW_TERMINALS[nxt](state), STATE_REDUCERS["review"][1])
    return state, visited  # type: ignore[return-value]


def run_generate_stub(init: GenerateState | None = None) -> tuple[GenerateState, list[str]]:
    """생성 스텁 한 바퀴. 🚨 루프가 끝나는지(K+1 라운드 안) 이 함수로 단독 확인한다."""
    state: dict[str, Any] = dict(init or {})
    reducers = STATE_REDUCERS["generate"][1]
    visited: list[str] = []

    def step(name: str) -> None:
        visited.append(name)
        _apply(state, GENERATE_NODES[name](state), reducers)

    step("keyword_screen")
    while True:
        for name in GENERATE_ROUND:
            step(name)
        nxt = route_after_rejudge(state)  # type: ignore[arg-type]
        if nxt != "assemble":
            step(nxt)
            return state, visited  # type: ignore[return-value]


#: 판정 코드의 판 — 응답 · 평가 도구(`scripts/eval_graph.py`)가 같은 값을 적는다 (D-99).
#: 🔄 2026-10-01 — 스텁(`stub-0.2.0`)이 아니다 · **인코더 전 규칙 판정**(사전 적중 · D-269)이다
JUDGED_BY = "rule-0.3.0-dict"


def judged_by(state: dict[str, Any]) -> str:
    """응답의 판 표지 (🆕 2026-10-09). 인코더가 돌았으면 그 판의 판 지문을 붙인다 — `rule-0.3.0-dict+encb:<판 지문 12자>`.

    🔄 2026-10-13 (D-333) — ⛔ 종전 `+enc:<가중치 지문>` 은 문턱만 다른 판(카드 17 의 F1 최대 판 · 채택 판)을 가르지 못했다.
       판 지문은 판의 **파일 전부**로 낸다(`app/model_lock.py` `bundle_sha`). 접두를 바꿔 옛 표지와 섞이지 않게 한다(D-178).

    ★ 앞머리는 그대로 `JUDGED_BY` 다 — **판정은 규칙 판정**이고 인코더는 `encoder_candidates` 만 채웠다 (D-323).
    🔴 인코더가 안 돌았으면(설정 없음 · 못 올림) 붙이지 않는다 — 신호가 실린 응답만 인코더 판을 적는다.
    """
    model_dir = enc.configured_dir()
    if model_dir is None or not state.get("encodings"):
        return JUDGED_BY
    return f"{JUDGED_BY}{enc.JUDGED_BY_MARK}{enc.bundle_mark(model_dir)}"


def to_response(state: ReviewState) -> JudgeResponse:
    """검수 상태를 계약으로 옮긴다. 🚨 계약이 거부하면 여기서 터진다 — 화면보다 먼저다.

    🔄 D-265 — `attempt` 를 넘기지 않는다. 검수에서는 **항상 0** 이다(재검수 횟수와 다른 축).
    🔄 2026-10-02 — **품목 · 품목 출처 · 미검수 법을 싣는다** (D-276 ⑥ · D-277 · D-271 ④ 개정).
       · 품목은 요청이 준 값이다 — `classify` 가 아직 판별하지 않으므로 출처는 늘 `user_selected`(확인되지 않은 값)다.
         ⛔ 종전에는 「받은 품목은 판별 결과가 아니다」라 싣지 않았다 — 그러면 계약의 통과 금지(`_uncovered_law_notice`)가 발동하지 않는다.
       · 주된 광고법을 안 본 품목(`UNCOVERED_CATEGORIES`)이면 미검수 고지가 붙는다. 법 이름을 가릴 낱말 목록이 아직 없어 한 줄이다 (D-277 ⬜).
    🆕 2026-10-05 (D-319) — `branches` 를 넘긴다. 분기는 `premise_branches` 가 전제별로 판정을 내 만든다 — 기준 문안이 확정되지
       않았으면 빈 목록이다(`app/premise.py` `criteria_ready`).
    """
    category = (state.get("product") or ProductContext()).category
    return JudgeResponse(
        outcome=state.get("outcome", Outcome.hold),
        category=category,
        category_source=CategorySource.user_selected if category is not None else None,
        not_reviewed=[NOT_REVIEWED_UNNAMED] if category in UNCOVERED_CATEGORIES else [],
        sentences=state.get("sentences", []),
        branches=state.get("branches", []),
        certificate=state.get("certificate"),
        timings=state.get("timings", []),
        # 🔄 2026-10-13 — 고정 날짜를 뺐다. 읽을 판이 없으면 「모름」이다 (D-220 · D-103 ③ · `LAW_VERSION_UNKNOWN`).
        #    ⬜ 현행 청크의 시행일을 적재가 채우면 그 최댓값을 읽는다 — 그 전에는 날짜를 적지 않는다.
        law_version=LAW_VERSION_UNKNOWN,
        judged_by=judged_by(state),
    )


# ══════════════════════════════════════════════════════════════════════
#  컴파일본 — 🚨 지연 import. langgraph 가 없어도 위(라우터·스텁)는 돈다 (D-124 ①)
# ══════════════════════════════════════════════════════════════════════


def _require_tracing_off() -> None:
    """🔴 **추적이 켜져 있으면 멈춘다** (D-43 · D-220). 모든 `build_*` 가 부른다 — 한 곳이다 (D-99).

    ⛔ `langgraph` → `langchain-core` → `langsmith` 가 전이 의존이라 패키지를 못 뺀다. 켜지면 광고 문구 원문이
       밖으로 나간다. ⛔ **조용히 끄지 않는다** — 켠 사람이 자기가 켠 것이 무시된 줄 모른다 (D-146).
    """
    from langsmith.utils import tracing_is_enabled  # noqa: PLC0415

    if tracing_is_enabled():
        raise SystemExit(
            "🔴 LangSmith 추적이 켜져 있다 — D-43 이 배제했다.\n"
            "   🚨 켜면 광고 문구 원문이 외부로 나간다.\n"
            "   끄는 법: LANGCHAIN_TRACING_V2 · LANGSMITH_TRACING 을 지우거나 false 로 둔다."
        )


def _chain(g: Any, names: tuple[str, ...]) -> None:
    for a, b in zip(names, names[1:], strict=False):
        g.add_edge(a, b)


def build_core():  # noqa: ANN201 — langgraph 타입은 지연 import 라 여기서 못 적는다
    """판정 코어 서브그래프 (D-266 · D-267). 🚨 **부를 때마다 새로 컴파일한다** — 게이트가 `NODES` 를 바꿔 끼운다."""
    _require_tracing_off()
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415
    from langgraph.types import Send  # noqa: PLC0415

    g = StateGraph(CoreState)
    for name, fn in NODES.items():
        g.add_node(name, fn)
    g.add_edge(START, CORE_BEFORE_LAWS[0])
    _chain(g, CORE_BEFORE_LAWS)

    def fan_out(state: CoreState) -> list[Any]:
        return [Send(name, law_payload(state)) for name in route_laws(state)]

    g.add_conditional_edges(CORE_BEFORE_LAWS[-1], fan_out, list(LAW_NODES))
    for name in LAW_NODES:
        g.add_edge(name, CORE_AFTER_LAWS[0])
    _chain(g, CORE_AFTER_LAWS)
    g.add_edge(CORE_AFTER_LAWS[-1], END)
    return g.compile()


def _core_node(core_graph: Any) -> Callable[..., dict[str, Any]]:
    """코어를 부르는 함수 노드. `CORE_IN` 만 넣고 `CORE_OUT` 만 꺼낸다 (모듈 docstring 의 실측).

    ⛔ **`timed` 를 두르지 않는다** — 안의 노드가 각자 잰다. 두르면 코어 시간이 두 번 셈해진다.
    🔴 `config` 는 **주석 없이** 받아 그대로 넘긴다 — 커서가 코어의 `retrieve` 까지 가야 한다 (2026-09-14 실측).
    """

    def core(state: dict[str, Any], config=None) -> dict[str, Any]:  # noqa: ANN001
        out = core_graph.invoke({k: state[k] for k in CORE_IN if k in state}, config=config)
        return {k: out[k] for k in CORE_OUT if k in out}

    return core


def build_review():  # noqa: ANN201
    """검수 그래프 (진입점 A · D-266). 코어 → 종착 넷. **루프가 없다** (D-265)."""
    _require_tracing_off()
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    g = StateGraph(ReviewState)
    g.add_node("core", _core_node(build_core()))
    for name, fn in REVIEW_TERMINALS.items():
        g.add_node(name, fn)
        g.add_edge(name, END)
    g.add_edge(START, "core")
    g.add_conditional_edges("core", route_review, {n: n for n in ROUTES_REVIEW})
    return g.compile()


def build_generate():  # noqa: ANN201
    """생성 그래프 (진입점 B · D-266). 🔜 W9 — `rejudge` 가 코어를 부르는 배선.

    🔄 2026-10-14 — **앱에서 부르는 곳이 없다**(스텁 노드 · 게이트 `tests/test_graph_routers.py` 만 짓는다). 지금 도는 카피 생성(B)은
       이 그래프가 아니라 `app/routers/copygen`(D-332 · GPT 후보 → 코드 필터 → `GraphJudge` → `app.api.judge`)이다.
       ⬜ 이 그래프를 채울지 · D-266 의 진입점 B 를 고칠지는 판정 대기다.
    """
    _require_tracing_off()
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    g = StateGraph(GenerateState)
    for name, fn in GENERATE_NODES.items():
        g.add_node(name, fn)
    g.add_edge(START, "keyword_screen")
    _chain(g, ("keyword_screen", *GENERATE_ROUND))
    g.add_conditional_edges(
        GENERATE_ROUND[-1], route_after_rejudge, {n: n for n in ROUTES_AFTER_REJUDGE}
    )
    for terminal in ("frontier", "search_failed"):
        g.add_edge(terminal, END)
    return g.compile()


def main() -> int:
    state, visited = run_review_stub("면역력 강화에 도움을 줍니다.")
    print("검수 방문 순서 —", " → ".join(visited))
    r = to_response(state)
    print(f"   종착 {r.outcome.value} · 문장 {len(r.sentences)} · 법 {', '.join(state['laws'])}")
    for t in r.timings:
        print(f"    {t.node:12s} {t.ms:7.3f} ms")
    gstate, gvisited = run_generate_stub()
    print("\n생성 방문 순서 —", " → ".join(gvisited))
    print(f"   종착 {gstate['outcome'].value} · attempt {gstate['attempt']}")
    print(
        "\n🚨 DB 없이 돈 한 바퀴다 — 사전을 못 훑어 문장은 미판정이고 모델도 없다. 방문 순서만 보인다 (D-124 · D-266)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
