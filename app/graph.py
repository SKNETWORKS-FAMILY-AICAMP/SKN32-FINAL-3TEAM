"""app/graph.py — 판정 코어 서브그래프 + 진입점 그래프 (D-266 · D-124 walking skeleton).

  uv run python -m app.graph            # 스텁 한 바퀴(검수 · 생성)를 돌려 방문 순서를 찍는다

🔄 **2026-09-23 — 그래프를 갈랐다 (D-266).** 종전에는 상태 하나(`JudgeState`)·그래프 하나 안에서
   판정 뒤 B 실증형을 재생성 루프로 보냈다. D-265 로 **검수는 문구를 만들지 않으므로** 그 루프는
   검수 경로에 있으면 안 되는 가지가 됐다.

       core     (서브그래프)  split → classify → retrieve → match_dict → encode
                              → 법별 팬아웃(D-267) → merge_laws → judge → assess_risk → doc_rules
       review   (진입점 A)   core → route_review → certificate · guidance · hold · passed   ← 루프 없음
       generate (진입점 B)   keyword_screen → assemble → claim_ledger → rejudge → 루프(D-126)
       compose  (진입점 C)   상태만 — 이번 범위 밖 (계약만 · D-266)

🚨 **모델도 판정 로직도 없이 end-to-end 한 바퀴가 돈다** — Phase 0 게이트의 정의(D-124)는 그대로다.

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
import operator
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Annotated, Any, TypedDict

from app import dictmatch as dm
from app import premise as pm
from app import retrieve as rt
from app import sanction, sentsplit
from app.contracts import (
    NOT_REVIEWED_UNNAMED,
    UNCOVERED_CATEGORIES,
    AdaptedCopy,
    AdFormat,
    AdSection,
    Branch,
    Candidate,
    Category,
    CategorySource,
    Certificate,
    EvidenceArticle,
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
    Segment,
    SentenceJudgment,
    Span,
    Timing,
    Verdict,
    Violation,
    is_pass,
)
from app.settings import PARAMS
from collect import statute
from collect.law_map import LAWS, REFERENCE_ONLY

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
    🚨 `vector`·`lexical` 을 같이 나른다 — **벡터가 죽은 채 어휘 결과만으로 판정하면 근거가 반쪽인데
       응답은 그럴듯하다.** `hold` 로 보내는 근거가 이 둘이다 (D-202).
    """

    sent_id: str
    #: 🔄 2026-09-28 (W4 · D-291) — **넓은 검색의 두 갈래 후보**(법마다 폭만큼 · `rt.wide`)를 섞지 않고 나른다.
    #:    법별 노드가 `rt.law_view()` 로 **자기 법 것만 골라 섞는다** — 섞은 뒤 거르면 순위가 뒤집힌다(사실원장 ㊲).
    #:    ⛔ 종전에는 여기 `articles`(전역 상위 `top_k` 5 를 좌표로 옮긴 것)가 있었다 — 세 법이 다섯 자리를 나눠 썼다.
    #:       좌표로 옮기는 일은 이제 법별 노드가 한다(`LawResult.articles`).
    vector_hits: tuple[rt.Hit, ...] = ()
    lexical_hits: tuple[rt.Hit, ...] = ()
    #: 두 갈래가 각각 돌았는가. ⛔ **둘 다 False 면 근거 없이 판정하는 것**이다 (D-224) — `hold`
    vector: bool = False
    lexical: bool = False
    #: 두 갈래 **후보 수의 합**(겹친 것은 두 번 센다 · 법을 합친 행 수 — 법마다 폭은 `rt.POOL`). 🚨 0 은 「안 겹쳤다」이고,
    #: `lexical=False` 는 「검색어를 못 만들었다」다 — 다른 사건이다 (D-202).
    pool: int = 0


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

    🔜 **W4 에서 칸이 는다** — 전제(`Premise`) · 문장별 유형 · 근거 · 하한. 🔄 2026-09-24 — W3 로 계약에 `Premise` 가
       섰다(`app/contracts.py`). 칸을 늘릴 때 **그 타입을 쓴다** — ⛔ 문자열로 전제를 따로 지으면 **두 벌**이 된다 (D-99).
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
    #: 🆕 2026-10-02 (W5) — 합법화 불가 증명서(D-32). **조립기가 아직 없다** — 사유 설명 문안이 확정된 뒤에 선다(D-308 ⬜).
    #:    읽는 쪽(`certificate` 종착 · `to_response`)을 먼저 세웠다 — 이 칸이 비면 증명서 종착은 보류로 내린다 (D-220).
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
    "core": (CoreState, ("evidence", "dict_scans", "law_results", "sentences", "timings")),
    "review": (ReviewState, ("evidence", "dict_scans", "law_results", "sentences", "timings")),
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
#  코어 노드 — 자리와 계약만 있고 판정은 없다
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
       판별해서 지어내지 않는다. 🔜 W4 — `product_fact` 인정번호 대조 + 규칙으로 `None` 을 좁힌다.
    """
    product = state.get("product") or ProductContext()
    return {"laws": laws_for(product.category)}


#: ⛔ 🔄 2026-09-24 (W6 · D-271 ③) — 품목을 청크 범주로 넘기던 **임시 다리**(`_CHUNK_CATEGORY` · `_chunk_category`)를 지웠다.
#:    검색은 **법으로** 거르고 판정 그래프는 **넓게 한 번**(법 필터 없음) 찾는다 — 법별 노드가 자기 법 근거만 거른다(D-267).
#:    🚨 품목을 검색 필터로 넘기지 않는다 — 품목과 법은 다른 축이다(D-271 ④). 게이트가 `retrieve` 의 호출을 본다.


def _evidence_article(hit: rt.Hit) -> EvidenceArticle | None:
    """`Hit` → 계약. 🔴 **확신이 없으면 안 옮긴다** (D-224).

    ⛔ 위반 근거 좌표(`basis_citation`)가 `None` 이면 좌표를 못 세운 것이다 — 「제18조」로 줄여 적으면 실은 제3항인 근거를
       가리킨다. 지어내지 않고 **버린다.** ⛔ **`quote` 는 비운다** — `search()` 는 `U2_rag` 로 거르고 인용 자격은 `U3_cite` 다.
    🔄 2026-09-28 (D-238 개정 (나)) — `citation` 이 아니라 `basis_citation` 을 옮긴다. 적용 제외 목이면 **부모 목의 좌표**가
       오고, 그 좌표를 가진 청크는 이 청크가 아니므로 `chunk_id` 를 비운다 — 제외 목의 글이 위반 근거 자리에 보이지 않게.
       제외 목 자신은 `_proviso()` 가 따로 나른다.
    🚨 `citation()` 을 다시 부르지 않는다 — `Hit` 이 생성 시점에 이미 들고 있다 (D-99).
    """
    if not hit.basis_citation or not hit.law_id:
        return None
    return EvidenceArticle(
        law_id=hit.law_id,
        article=hit.basis_citation,
        item=hit.item or "",
        chunk_id=None if hit.exempt_of else hit.chunk_id,
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
    return {"evidence": found}


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
    """금지 표현 사전 매칭 — **위험도 하한의 재료만** 낸다 (구현계획 F · D-09). 🆕 2026-09-28 (W4) 연결.

    ★ 매칭 규칙은 `app/dictmatch.py` 한 곳이다 — 판정기 B(`scripts/eval_rule.py`)와 **같은 적중**을 낸다 (D-99).
    🔴 `exact_match`(단독판정) 항목만 — `load_dict_entries`. 🔴 커서는 `retrieve` 와 같이 `config` 로 받는다(주석 없이).
    🔴 **DB 가 없어도 돈다** — 문장마다 `ran=False` 를 남긴다. ⛔ 빈 dict 로 삼키면 「못 훑었다」가 「안 걸렸다」가 된다 (D-220).
    🚨 사전의 **침묵은 「특이사항 없음」이 아니다** — 인코더 전에는 안 걸린 문장이 보류다 (D-269). 그 판정은 `judge` 가 한다.
    🚨 사전 적중은 **판정이 아니다** — 하한과 근거 후보다. 확정은 법별 노드 · `judge` 가 조문 적용 뒤에 낸다 (D-127).
    """
    sents = state.get("sents", [])
    if not sents:
        return {}
    cur = ((config or {}).get("configurable") or {}).get("conn")
    if cur is None:
        return {"dict_scans": [DictScan(sent_id=sent_id(i)) for i in range(len(sents))]}
    entries = load_dict_entries(cur)
    weak = load_weak_entries(cur)  # 🆕 D-311 — 보류 문장의 유형 후보

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

    return {
        "dict_scans": [
            DictScan(
                sent_id=sent_id(i), ran=True, hits=_hits(text, entries), weak=_hits(text, weak)
            )
            for i, text in enumerate(sents)
        ]
    }


@timed
def encode(state: CoreState) -> dict[str, Any]:
    """인코더 — 유형 · 근거 스팬 · 확신 (D-131). **팬아웃 앞에서 한 번** 돈다 (D-267).

    🔜 W7 — harness(D-94) 뒤. ⛔ 법별 노드가 인코더를 부르면 판정기가 세 벌이다 (D-99).
    """
    return {}


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
    """법별 노드 하나 (D-267). 🔜 W4 다음 — 자기 법의 조문 적용(유형 유효성 · 단서) · 하한 조회.

    🆕 2026-09-28 (W4 · D-291) — **자기 법의 근거를 거른다.** 넓은 검색의 두 갈래 후보에서 이 법 것만 골라 섞고
       (`rt.law_view` — 거른 뒤 섞는다 · ㊲) 앞의 `LAW_TOP_K` 개를 좌표로 옮긴다. 좌표를 못 세운 것은 버린다 (D-224).
    ★ 판정은 여전히 없다 — 「이 법이 이 문장들을 봤다 + 이 근거를 골랐다」까지다. 판정을 지어내지 않는다.
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
        picked: list[tuple[str, tuple[EvidenceArticle, ...]]] = []
        proviso_picked: list[tuple[str, tuple[Proviso, ...]]] = []
        dict_picked: list[tuple[str, tuple[DictHit, ...]]] = []
        weak_picked: list[tuple[str, tuple[DictHit, ...]]] = []
        for i in range(n):
            sid = sent_id(i)
            e = by_sent.get(sid)
            hits = rt.law_view(e.vector_hits, e.lexical_hits, law) if e else []
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


#: 🆕 2026-10-01 (W4 · D-273 결정 3) — 위반 유형 → **불가 사유**(A 자격형 · B 실증형 · C 절대형 · D-59).
#:    출처 `[문헌]` — `docs/ohb/sanction_rule_초안_2026-09-16.md` §6(별표 1 각 목의 단서 · 문언). D-273 이 이 표를 전제로 결정 3 을 세웠다.
#: 🔴 **표에 없는 유형은 확정하지 않는다 — 보류다** (D-273 「사유를 못 정하면 보류」 · D-72).
#: 🔄 2026-10-01 (D-308 ⑨) — `후기_체험기_기만` = C(체험기 형식 자체 금지 · 8①5 다목) · `기능성화장품_오인` = A(심사 · 보고를 받으면 표시)
#:    🚨 `추천_보증_뒷광고` 는 판정이 A 지만 **표에 넣지 않는다** — D-255 가 범위 밖으로 뒀다(대가 표시 **누락**이 위반이라 문구로 못 본다).
#:       넣으면 인용이 그 유형을 낼 때 확정이 생긴다 — 범위 밖 유형은 보류로 남는다 (D-192 · 들어올 자리에 적는다)
#: 🔄 2026-10-01 (D-304) — `비방광고` = **B** · 실증 분기의 상한은 **R0 아래로 못 간다**(「불리한 사실만 골라 비방」은 사실이어도
#:    남는다 · 표시광고 고시). 상한은 실증 분기(`SubstBranch.substantiated_max`)가 싣는다 — 하한(W5)이 선 뒤에 만든다.
INFEASIBILITY_OF: dict[Violation, Infeasibility] = {
    Violation.질병_예방치료_표방: Infeasibility.C,
    Violation.의약품_오인: Infeasibility.C,
    Violation.건강기능식품_오인: Infeasibility.A,
    Violation.거짓_과장: Infeasibility.B,
    Violation.소비자_기만: Infeasibility.B,
    Violation.부당_비교광고: Infeasibility.B,
    Violation.실증책임_위반: Infeasibility.B,
    Violation.비방광고: Infeasibility.B,  # D-304 — 실증 분기 상한 ≥ R1
    Violation.후기_체험기_기만: Infeasibility.C,  # D-308 ⑨
    Violation.기능성화장품_오인: Infeasibility.A,  # D-308 ⑨
}

#: 사유가 여럿이면 **더 막힌 쪽** — 종착 우선순위(증명서 A·C > 지시 B · D-268)와 같은 순서다.
_INFEAS_ORDER = (Infeasibility.C, Infeasibility.A, Infeasibility.B)


def _basis_article(cite: str) -> EvidenceArticle | None:
    """사전 근거 인용(`법ID:제N조제N항제N호[|목]`) → 근거 조문. 꼴이 틀리면 `None` — 좌표를 지어내지 않는다 (D-224)."""
    try:
        law, jo, hang, ho, mok = statute.parse(cite)
    except ValueError:
        return None
    return EvidenceArticle(
        law_id=law, article=f"제{jo}조", item=f"제{hang}항제{ho}호" + (f"{mok}목" if mok else "")
    )


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
) -> SentenceJudgment:
    """문장 하나 — **인코더 전 판정** (D-269 그대로 · ⚠️ 재검 대기).

    ① 사전을 **못 훑었으면** 미판정 — 못 본 것을 본 것처럼 말하지 않는다 (D-220 · D-63)
    ② 이 판정에 보낸 법의 인용을 가진 적중(`hits` — 법별 노드가 거른 것)이 있으면 **위반 확정** (D-269)
       — 근거 = 적중의 인용 조문 + 법별 노드가 고른 조문 · 뺄 구간 = 적중의 원문 좌표 · 불가 사유 = `INFEASIBILITY_OF`
       🔴 유형마다 사유를 못 정하면(표에 없음) **보류** · 인용 좌표를 하나도 못 세우면 **근거 없음** (D-273 · D-127 · D-224)
    ③ 적중은 있는데 그 인용이 **어느 법인지 못 정한다** → 근거 없음 — 유형은 유지 (D-127 「유형은 잡았는데 조문이 없다」)
       ⛔ 인용이 **보내지 않은 법** 것이면 근거 없음이 아니다 — 이 판정이 볼 법이 아니다(D-267)
    ④ 그 밖에 → **보류(확신 부족)** — 사전의 침묵은 「특이사항 없음」이 아니다 (D-269)
       🆕 2026-10-02 (D-311 · D-273 ④) — 단독판정 자격 **없는** 항목이 이 법의 인용으로 울렸으면 보류 문장에 **유형 후보**를 싣는다.
       확정하지 않는다 · 하한을 걸지 않는다(W5 · D-273 ④ 의 하한은 인코더 뒤 안건) · 근거는 적중의 인용 조문.
       ⛔ 싣지 않으면 강등된 질병 이름(「당뇨에 좋은 차」)이 사전 침묵과 같은 보류가 된다(원장 10-02 ⑤)
    🚨 위험도를 적지 않는다 — 하한(`sanction_rule` · W5)이 없다. 지어내면 계약이 거부한다(D-09 · D-131).
    🚨 `not_claim` 을 내지 않는다 — 주장 여부 판별은 인코더 몫이다 (D-275).
    """
    if scan is None or not scan.ran:
        return SentenceJudgment(
            sent_id=sid, text=text, verdict=Verdict.unjudged, evidence=retrieved
        )
    if hits:
        types = _typed({t for h in hits for t in _hit_types(h)})
        if not types:
            return SentenceJudgment(
                sent_id=sid, text=text, verdict=Verdict.hold, hold_reason=HoldReason.low_conf
            )
        reasons = {INFEASIBILITY_OF.get(t) for t in types}
        if None in reasons:
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
                a = _basis_article(c)
                if a is not None and a not in basis:
                    basis.append(a)
        if not basis:
            return SentenceJudgment(
                sent_id=sid, text=text, verdict=Verdict.no_basis, violations=types
            )
        evidence = basis + [a for a in retrieved if a not in basis]
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
            infeasibility=next(r for r in _INFEAS_ORDER if r in reasons),
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
            a = _basis_article(c)
            if a is not None and a not in basis_w:
                basis_w.append(a)
    return SentenceJudgment(
        sent_id=sid,
        text=text,
        verdict=Verdict.hold,
        hold_reason=HoldReason.low_conf,
        violations=cand,
        evidence=basis_w + [a for a in retrieved if a not in basis_w],
    )


@timed
def judge(state: CoreState) -> dict[str, Any]:
    """판정 — 🔄 2026-10-01 (W4 1판) **인코더 전 규칙 판정** (D-269 · D-127 · D-224 · D-273). 문장 규칙은 `_judge_one`.

    🔴 근거는 **법별 노드가 고른 것**(`law_results[*].articles`)과 **법별 노드가 거른 사전 적중**(`dict_hits`)을
       `sent_id` 로 짝지어 옮긴다. 법 순서는 `LAW_NODES` 순서이고 같은 좌표는 한 번만 싣는다. ⛔ 검색을 다시 부르지 않는다 (D-99).
    🚨 **근거를 찾은 것과 판정한 것은 다르다** — 사전 적중 없이 검색 근거만으로는 확정하지 않는다 (D-127 · D-269).
    ⚠️ D-269 는 「전제 정정 · 결론 재검 대기」다 — 그래프 평가 도구(`scripts/eval_graph.py` · W1)의 수로 재검한다. 결론은 그때까지 그대로다.
    ⬜ 단서(`provisos`)는 아직 읽지 않는다 — 제품 사실을 모르면 요건 충족을 모른다(D-238 개정 (나)). 판정을 바꾸지 않고 근거에 남는다.
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
    # 🔴 원문 좌표를 못 되찾으면(분할 밖에서 문장이 들어왔다) **구간을 싣지 않는다** — 좌표를 지어내지 않는다 (D-224 · D-278).
    #    판정 자체는 바뀌지 않는다. 뺄 구간이 필요한 지시 종착은 그때 계약이 막는다.
    try:
        starts: list[int | None] = list(sentsplit.offsets(state.get("text", ""), sents))
    except ValueError:
        starts = [None] * len(sents)
    return {
        "sentences": [
            _judge_one(
                sid := sent_id(i),
                t,
                starts[i],
                scans.get(sid),
                hits_of.get(sid, []),
                per_sent.get(sid, []),
                weak_of.get(sid, []),
            )
            for i, t in enumerate(sents)
        ]
    }


#: 위험도 하한을 읽는 질의 — 🔴 **뷰만 읽는다**(`v_risk_lookup` · 2인 서명이 끝난 현행 행만 보인다 · 0013 · D-309).
#:    칸은 `app/sanction.py` `Row` 의 열쇠로 옮긴다 — 원천 검사(yaml)와 **같은 함수**(`floor_rows`)가 읽는다 (D-99).
SQL_RISK = """SELECT rule_key, law_id, violation_type::text, sanction_kind, annex1, cover, quote, fact_kind
FROM v_risk_lookup
ORDER BY rule_key"""


def load_sanction_rows(cur: Any) -> list[dict[str, Any]]:
    """`v_risk_lookup` → 하한 조회 행. 서명 전이거나 적재 전이면 **빈 목록**이다 — 그러면 하한이 없어 판정이 보류로 멈춘다 (D-220)."""
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


def _with_risk(s: SentenceJudgment, risk: RiskAssessment) -> SentenceJudgment:
    """문장에 위험도를 붙인 **새 문장** — 계약 검증을 다시 지난다(위반 없으면 R0 · 있으면 R1 이상 · D-273)."""
    return SentenceJudgment(**{**{k: getattr(s, k) for k in type(s).model_fields}, "risk": risk})


@timed
def assess_risk(state: CoreState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """위험도 — **코드 하한**(제재표) · 가능 상한 (D-09 · D-305 · D-310). 🆕 2026-10-02 (W5) 배선.

    ★ 확정 문장에만 적는다 — 보류 문장의 유형 후보에는 하한을 걸지 않는다(D-311 · D-313 ③).
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
    done = {s.sent_id for s in out}
    todo = [
        s
        for s in sents
        if s.verdict is Verdict.confirmed and s.risk.final is None and s.sent_id not in done
    ]
    if not todo or cur is None or product.category is None:
        return {"sentences": out} if out else {}
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
                    floor=f.floor, final=f.floor, ceiling=f.ceiling, ceiling_note=f.ceiling_note
                ),
            )
        )
    return {"sentences": out} if out else {}


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
            unknown += unk + list(dict(r.weak_hits).get(sid, ()))
            if kept:
                by_law[LAW_OF_NODE[law]] = tuple(kept)
        hits = [h for hs in by_law.values() for h in hs]
        if undecided or (raw_hit and voided and not hits):
            # 🔴 이 전제에서 **판정하지 못한다** — 보류이고 걸린 것은 전부 유형 후보로만 싣는다 (D-319 ④′ · D-220 · D-311).
            #    · 판정하지 못하는 적중이 하나라도 있으면(질병 표방의 목을 모른다) 남은 적중만으로 확정하지 않는다 —
            #      확정하면 그 분기는 「거짓 · 과장뿐」이라고 말하게 된다(🔄 2026-10-05 재검 · 원장 10-03 ㊿-34).
            #    · 3호가 **서지 않는다 ≠ 통과다.** 인정 · 고시된 문구와 맞는지는 대조하지 않았다 — 그 재료(건강기능식품의
            #      고시형 문구 · 일반식품 기능성 고시 [별표 2])를 읽는 자리가 아직 없다. 그 대조가 붙기 전에는 통과를 내지 않는다.
            #    ⛔ 하한을 걸지 않는다 — 보류 문장의 유형 후보다 (D-311 · D-313 ③).
            j = _judge_one(sid, text, starts[i], scans.get(sid), [], arts, hits + unknown)
        else:
            j = _judge_one(sid, text, starts[i], scans.get(sid), hits, arts, unknown)
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
    """
    hit = [j for j in per if j.verdict is Verdict.confirmed and j.violations]
    if not hit:
        return None  # 어느 전제에서도 확정 위반이 없다 — 종전 판정(사전 침묵 보류 등) 그대로
    risks = [j.risk.final for j in per if j.risk.final is not None]
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
                else worst.risk.model_copy(update={"floor": top, "final": top})
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
    )


def _judgment_key(j: SentenceJudgment) -> tuple:
    """전제끼리 판정이 같은가를 보는 열쇠 — 판정 · 사유 · 유형 · 불가 사유 · 위험도 · 근거 좌표."""
    return (
        j.verdict,
        j.hold_reason,
        tuple(j.violations),
        j.infeasibility,
        j.risk.final,
        tuple((e.law_id, e.article, e.item) for e in j.evidence),
    )


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
    rows = load_sanction_rows(cur)
    per = {p: _premise_sentences(p, state, rows) for p in premises}
    if category is not None and len({tuple(map(_judgment_key, per[p])) for p in premises}) == 1:
        # 품목이 주어졌고 전제가 판정을 바꾸지 않는다 — 고를 것이 없는 선택지를 내지 않는다(종전 판정 그대로).
        # ⛔ 품목을 모를 때는 같아도 낸다 — 「품목 미확정이면 분기는 언제나」(D-229 ⑥ · D-319 ②).
        return {}
    reason = HoldReason.cat_unknown if category is None else HoldReason.premise_unknown
    changed = [
        r
        for i, b in enumerate(base)
        if (r := _recorded(b, [per[p][i] for p in premises], reason)) is not None
    ]
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
    """
    return {}


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


@timed
def certificate(state: ReviewState) -> dict[str, Any]:
    """합법화 불가 증명서 (D-32). **A 자격형 · C 절대형에만** (D-125).

    🔴 2026-10-02 (W5) — 계약은 `outcome=certificate` 에 증명서(`Certificate` · 사유 · 설명)를 요구한다. **조립기가 아직 없다** —
       설명은 사용자에게 보이는 문안이고 조문 대조 뒤에 확정한다(D-308 ⬜ · D-263 ②). 증명서가 없으면 **보류로 내린다**.
       ⛔ 빈 증명서로 종착을 찍으면 계약이 응답을 거부해 화면에 오류가 난다 — 위험도가 붙은 뒤로는 실제 요청이 여기 온다.
       문장 판정(확정 · 유형 · 근거 · 위험도)은 그대로 나간다. 조립기가 서면 이 분기가 사라진다 (D-192).
    """
    if state.get("sentences") and state.get("certificate") is None:
        return {"outcome": Outcome.hold}
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
    if any(s.verdict is not Verdict.confirmed for s in sents):
        return "hold"
    # 🆕 2026-10-01 (W4 1판) — **위험도가 없는 확정 위반은 증명서 · 지시로 못 간다** — 보류다 (D-268 「막힘」 · D-220).
    #    지시는 실증 분기(실증 전 위험도)를, 증명서는 사유 설명을 요구한다 — 하한(`sanction_rule` · W5)이 서기 전에는 어느 쪽도
    #    계약을 못 지난다. ⛔ 위험도를 지어내지 않는다 (D-09 · D-131). 문장 판정(확정 · 위반 · 근거 · 구간)은 그대로 나간다.
    #    ⬜ D-227 「제재 기준이 없을 때 무엇을 내나」 — 판정 대기. 이 줄이 그 판정이 들어올 자리다 (D-192)
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
        law_version="2026-09-10",
        judged_by=JUDGED_BY,
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
    """생성 그래프 (진입점 B · D-266). 🔜 W9 — `rejudge` 가 코어를 부르는 배선."""
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
    print("\n🚨 스텁이다 — 판정도 모델도 없다. 한 바퀴가 돈다는 것만 보인다 (D-124 · D-266).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
