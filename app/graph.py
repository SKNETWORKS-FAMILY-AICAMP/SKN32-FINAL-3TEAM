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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app import retrieve as rt
from app.contracts import (
    AdaptedCopy,
    AdFormat,
    AdSection,
    Candidate,
    Category,
    EvidenceArticle,
    GenerateOutcome,
    Infeasibility,
    JudgeResponse,
    KeywordScreen,
    MediaProfile,
    Outcome,
    ProductContext,
    Segment,
    SentenceJudgment,
    Timing,
    Verdict,
    is_pass,
)
from app.settings import DEFAULT_CATEGORY, PARAMS

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
    #: 🔴 `part_total > 1` 인 조각은 조문의 **일부**다 (0011 · D-199) — `EvidenceArticle.chunk_id` 로 따라간다.
    articles: tuple[EvidenceArticle, ...] = ()
    #: 두 갈래가 각각 돌았는가. ⛔ **둘 다 False 면 근거 없이 판정하는 것**이다 (D-224) — `hold`
    vector: bool = False
    lexical: bool = False
    #: 두 갈래 **후보 수의 합**(겹친 것은 두 번 센다). 🚨 0 은 「안 겹쳤다」이고, `lexical=False` 는
    #: 「검색어를 못 만들었다」다 — 다른 사건이다 (D-202).
    pool: int = 0


@dataclass(frozen=True, slots=True)
class LawResult:
    """법별 노드 하나가 낸 것 (D-267). `merge_laws` 가 모은다.

    🔜 **W3 에서 칸이 는다** — 전제(`Premise`) · 문장별 유형 · 근거 · 하한. 계약에 `Premise` 가 서기 전에는
       여기 적을 값이 없다. ⛔ 문자열로 전제를 미리 지어 두면 계약이 선 날 **두 벌**이 된다 (D-99).
    ★ 지금은 **「이 법이 이 문장들을 봤다」** 만 나른다 — `merge_laws` 의 fail-closed 대조가 읽는 값이다.
    """

    law: str
    sent_ids: tuple[str, ...] = ()


# ══════════════════════════════════════════════════════════════════════
#  상태 넷 (D-266) — 🚨 누적 키에는 반드시 리듀서가 붙는다
# ══════════════════════════════════════════════════════════════════════
#
# ⛔ `Annotated[..., operator.add]` 가 없으면 LangGraph 는 **마지막 노드의 값으로 조용히 덮어쓴다.**
#    문장이 여럿인데 마지막 문장만 남는 사고가 여기서 난다 — 오류가 안 나서 발견이 늦다 (D-124 ③).


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
    # ── 법별 팬아웃 🔴 누적 (D-267) — 법 노드가 **병렬로** 쓴다. 리듀서가 없으면 하나만 남는다
    law_results: Annotated[list[LawResult], operator.add]
    # ── 판정 누적 🔴 누적 ─────────────────────────────────────────────
    sentences: Annotated[list[SentenceJudgment], operator.add]
    # ── 계측 (D-77 · D-43 이 LangSmith 를 배제해 이것이 유일한 경로) 🔴 누적 ──
    timings: Annotated[list[Timing], operator.add]


class ReviewState(CoreState, total=False):
    """검수 (진입점 A · D-266). 코어 출력 + 종착.

    🔴 **재생성 키가 없다** — `attempt`·`rejects`·`rejected` 는 생성 상태로 옮겼다 (D-265 · D-266).
       검수에서는 늘 0 인 칸이었고, 칸이 있으면 누군가 쓴다.
    """

    outcome: Outcome


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
    "core": (CoreState, ("evidence", "law_results", "sentences", "timings")),
    "review": (ReviewState, ("evidence", "law_results", "sentences", "timings")),
    "generate": (GenerateState, ("keywords", "candidates", "rejects", "adapted", "timings")),
    "compose": (ComposeState, ("sections",)),
}

#: 코어 입출력 — 함수 노드가 **이것만** 넣고 **이것만** 꺼낸다 (모듈 docstring 의 실측 참조).
CORE_IN = ("text", "product")
CORE_OUT = ("sents", "laws", "evidence", "law_results", "sentences", "timings")


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
#:    ⛔ **청크의 `category` 와 섞지 않는다** — 청크 쪽 「일반」은 법 이름 낱말이 안 걸린 기본값이었다(D-271 맥락 2).
#:       🔜 W6 — 칸 이름이 `law` 로 바뀌고 법별 노드가 자기 법 근거만 거른다.
#: 🚨 **순서가 곧 팬아웃 순서다** — 스텁과 컴파일본이 같은 순서를 낸다(`Send` 목록 순서 · 2026-09-23 실측).
LAW_SCOPE: dict[str, frozenset[Category] | None] = {
    "law_ftc": None,
    "law_food": frozenset({Category.식품, Category.건기식}),
    "law_cosmetic": frozenset({Category.화장품}),
}
LAW_NODES = tuple(LAW_SCOPE)


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
    return {"sents": list(state.get("sents", [])), "product": state.get("product")}


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
    """문장 분할. 🔜 W4 — `preprocess/text.py` 의 분할기가 온다."""
    return {"sents": [state["text"]]}


@timed
def classify(state: CoreState) -> dict[str, Any]:
    """품목 판별 → **적용할 법**. 🚨 사용자에게 묻지 않는다 — 우리가 판별한다 (D-82).

    ★ 지금은 **받은 품목**으로만 법을 고른다 — 받은 것이 없으면(`None`) 세 법 전부다 (D-229 ⑥ · D-267).
       판별해서 지어내지 않는다. 🔜 W4 — `product_fact` 인정번호 대조 + 규칙으로 `None` 을 좁힌다.
    """
    product = state.get("product") or ProductContext()
    return {"laws": laws_for(product.category)}


#: 🔜 **W6 에서 지운다** — 품목(계약 `Category`)을 청크 범주로 넘기는 **임시 다리**다 (D-271 ③ · D-192).
#: 🔄 2026-09-23 (W3) — 계약에서 「일반」이 `일반상품` · `전용법_미수록` 으로 갈렸는데 **청크 값은 아직 「일반」이다**
#:    (정본 B 재생성 · 0019 전). 품목 이름을 그대로 넘기면 `ANY(c.category)` 가 **0건**이 된다 — 오류 없이 근거가 빈다.
#:    두 품목 모두 표시광고법만 타므로(D-277) 청크의 「일반」(= 법 이름 낱말이 안 걸린 기본값 · 사실상 표시광고법 쪽)으로 보낸다.
#: ⛔ W6 — 검색은 **법으로** 거르고 품목을 청크 필터로 넘기지 않는다(D-271 ③). 그때 이 표와 `DEFAULT_CATEGORY` 가 같이 사라진다.
_CHUNK_CATEGORY: dict[Category, str] = {
    Category.일반상품: DEFAULT_CATEGORY,
    Category.전용법_미수록: DEFAULT_CATEGORY,
}


def _chunk_category(category: Category | None) -> str:
    """품목 → 청크 범주 (W6 전 임시). 미확정이면 `DEFAULT_CATEGORY` 로 한 번 — 종전과 같다."""
    if category is None:
        return DEFAULT_CATEGORY
    return _CHUNK_CATEGORY.get(category, category.value)


def _evidence_article(hit: rt.Hit) -> EvidenceArticle | None:
    """`Hit` → 계약. 🔴 **확신이 없으면 안 옮긴다** (D-224).

    ⛔ `citation` 이 `None` 이면 좌표를 못 세운 것이다 — 「제18조」로 줄여 적으면 실은 제3항인 근거를 가리킨다.
       지어내지 않고 **버린다.** ⛔ **`quote` 는 비운다** — `search()` 는 `U2_rag` 로 거르고 인용 자격은 `U3_cite` 다.
    🚨 `citation()` 을 다시 부르지 않는다 — `Hit` 이 생성 시점에 이미 들고 있다 (D-99).
    """
    if not hit.citation or not hit.law_id:
        return None
    return EvidenceArticle(
        law_id=hit.law_id, article=hit.citation, item=hit.item or "", chunk_id=hit.chunk_id
    )


@timed
def retrieve(state: CoreState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """조문 검색 — `app/retrieve.py` 의 `search()` 를 부른다 (✅ 2026-09-14 · 구현계획 §2-1 C).

    🔴 검색을 여기서 새로 쓰지 않는다 — 코어는 `app/retrieve.py` 하나다 (D-99 · D-51).
    🆕 **커서는 `config` 로 받는다** — 주석 없는 `config` 여야 LangGraph 가 넘긴다(2026-09-14 실측).
       ⛔ 노드가 스스로 `connect()` 하면 문장마다 연결이 열린다 · 상태에 담으면 체크포인터(D-129)가 깨진다.
    🔴 **DB 가 없어도 돈다** (D-124). 빈 dict 로 삼키지 않고 문장마다 「검색을 못 했다」를 값으로 남긴다 (D-220).
    🔴 **팬아웃 앞에서 한 번** 돈다 (D-267) — 법마다 다시 부르면 검색이 3~4배다.
       ⬜ 지금은 `category` 하나로 거른다(`%s = ANY(c.category)`). 미확정이면 `DEFAULT_CATEGORY`(청크 `일반` =
       표시광고법)로만 돈다 — **식품·화장품 전용 조문을 못 본다.** 🔜 W6 — 넓게 한 번 · 법별 노드가 거른다 (D-229 ⬜).
    🚨 `rt.RetrieveError` 는 여기서 삼키지 않는다 — 근거 없이 판정하면 D-224 위반이다.
    """
    sents = state.get("sents", [])
    if not sents:
        return {}
    cur = ((config or {}).get("configurable") or {}).get("conn")
    if cur is None:
        return {"evidence": [SentEvidence(sent_id=sent_id(i)) for i in range(len(sents))]}

    product = state.get("product") or ProductContext()
    chunk_category = _chunk_category(product.category)
    found: list[SentEvidence] = []
    for i, text in enumerate(sents):
        hits, st = rt.search(cur, text, chunk_category)
        found.append(
            SentEvidence(
                sent_id=sent_id(i),
                articles=tuple(a for h in hits if (a := _evidence_article(h)) is not None),
                vector=st.vector == rt.VECTOR_OK,
                lexical=st.lexical == rt.LEXICAL_OK,
                # 🔄 2026-09-21 — `st.pool` 은 후보 **폭**(늘 50)이라 갈래별 후보 수의 합을 넣는다
                pool=st.pool_vector + st.pool_lexical,
            )
        )
    return {"evidence": found}


@timed
def match_dict(state: CoreState) -> dict[str, Any]:
    """금지 표현 사전 매칭 — **위험도 하한만** 건다 (구현계획 F · D-09).

    🔜 W4 — `dict_entry` 의 단독판정 항목. `exact_match=false` 는 하한을 못 건다.
    🚨 사전의 **침묵은 「특이사항 없음」이 아니다** — 인코더 전에는 안 걸린 문장이 보류다 (D-269).
    """
    return {}


@timed
def encode(state: CoreState) -> dict[str, Any]:
    """인코더 — 유형 · 근거 스팬 · 확신 (D-131). **팬아웃 앞에서 한 번** 돈다 (D-267).

    🔜 W7 — harness(D-94) 뒤. ⛔ 법별 노드가 인코더를 부르면 판정기가 세 벌이다 (D-99).
    """
    return {}


def _law_node(name: str) -> Callable[..., dict[str, Any]]:
    """법별 노드 하나 (D-267). 🔜 W4 — 자기 법의 조문 적용(유형 유효성 · 단서) · 근거 거름 · 하한 조회.

    ★ 지금은 **「이 법이 이 문장들을 봤다」** 만 적는다 — 판정을 지어내지 않는다.
    🚨 읽는 것은 `law_payload()` 가 보낸 키뿐이다 — 컴파일본에서는 그것만 온다.
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        n = len(state.get("sents", []))
        return {"law_results": [LawResult(law=name, sent_ids=tuple(sent_id(i) for i in range(n)))]}

    node.__name__ = name
    node.__qualname__ = name
    return timed(node)


@timed
def merge_laws(state: CoreState) -> dict[str, Any]:
    """법별 결과를 모은다 (D-267 팬인). 🔜 W3 — 전제별로 묶어 `branches` · `premise_basis`(D-263 ①).

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


@timed
def judge(state: CoreState) -> dict[str, Any]:
    """판정. 🔜 W4 — 상태 4종 · 조건(없음·C/A/B/M/D · D-242) · 불가 사유 · 실증 분기 주석(D-263 ④).

    🚨 스텁은 `unjudged` 를 낸다 — **통과로 집계 금지** (D-127). 그럴듯한 `confirmed` 를 지어내지 않는다.
    🔴 근거는 `state["evidence"]` 에서 `sent_id` 로 짝지어 옮긴다. ⛔ 여기서 검색을 다시 부르지 않는다 (D-99).
       ⛔ 붙는 근거가 없으면 `confirmed` 를 못 낸다 — 계약이 거부한다 (D-224 · `_confirmed_needs_evidence`).
    🚨 **근거를 찾은 것과 판정한 것은 다르다** — 붙였다고 `confirmed` 로 올리지 않는다 (D-127).
    """
    by_sent = {e.sent_id: e for e in state.get("evidence", [])}
    return {
        "sentences": [
            SentenceJudgment(
                sent_id=(sid := sent_id(i)),
                text=t,
                verdict=Verdict.unjudged,
                evidence=list(by_sent[sid].articles) if sid in by_sent else [],
            )
            for i, t in enumerate(state.get("sents", []))
        ]
    }


@timed
def assess_risk(state: CoreState) -> dict[str, Any]:
    """위험도. 🔜 W5 — D-09 래칫 `max(코드 하한, 인코더 예측)` · 초기 판정과 분기마다.

    🔴 코드 하한은 `sanction_rule` · `v_risk_lookup` 에서 온다 — **지금 0행이라 스텁이다.**
       ⛔ 하한 없이 최종만 적으면 계약이 거부한다. 그래서 아무것도 적지 않는다.
    """
    return {}


@timed
def doc_rules(state: CoreState) -> dict[str, Any]:
    """층 3 문서 규칙 — R-D1 최소판 → 문서 경고 + `hold(rd1)` (D-83). 🔜 W8.

    ⛔ 「문맥을 이해한다」고 말하지 않는다 (D-83 ④) — 문장별 판정 결과의 **집합 연산**이다.
    """
    return {}


#: 코어 순서 — 팬아웃 앞 · 법별 노드(`LAW_NODES` · 병렬) · 팬아웃 뒤. 컴파일본과 스텁이 **이 표 하나**를 쓴다 (D-99).
CORE_BEFORE_LAWS = ("split", "classify", "retrieve", "match_dict", "encode")
CORE_AFTER_LAWS = ("merge_laws", "judge", "assess_risk", "doc_rules")
NODES: dict[str, Callable[..., dict[str, Any]]] = {
    **{f.__name__: f for f in (split, classify, retrieve, match_dict, encode)},
    **{name: _law_node(name) for name in LAW_NODES},
    **{f.__name__: f for f in (merge_laws, judge, assess_risk, doc_rules)},
}


# ══════════════════════════════════════════════════════════════════════
#  검수 (진입점 A) — 종착 넷 · 루프 없음 (D-265 · D-268)
# ══════════════════════════════════════════════════════════════════════


@timed
def certificate(state: ReviewState) -> dict[str, Any]:
    """합법화 불가 증명서 (D-32). **A 자격형 · C 절대형에만** (D-125).

    ⬜ 계약은 `outcome=certificate` 에 `Certificate` 를 요구한다 — 🔜 W4 (판정이 불가 사유를 낼 때 같이).
    """
    return {"outcome": Outcome.certificate}


@timed
def guidance(state: ReviewState) -> dict[str, Any]:
    """「지시」 — 확정된 **실증형** 위반: 뺄 구간 · 실증 자료의 종류 · 내려갈 수 있는 등급 (D-268).

    🔄 2026-09-23 (W3) — 계약에 `Outcome.guidance` 가 섰다 (D-274). 종전에는 보류로 끝냈다.
    ⛔ 통과로 보내지 않는다 — 확정 위반이다. 증명서도 아니다 — 실증형이다 (D-59).
    🚨 계약은 지시 문장마다 **실증 분기와 뺄 구간**을 요구한다(`_guidance_payload`) — 판정 노드(W4)가 그것을 내야
       이 종착이 계약을 지난다. ★ 스텁 `judge` 는 `unjudged` 만 내므로 **지금 이 노드에 오는 길은 없다.**
    """
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
    """통과 — 전부 확정 ∧ 위험도 ≤ 주의 (D-125). 🚨 「적법」이라 부르지 않는다 (D-130).

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
    reasons = {s.infeasibility for s in sents if s.infeasibility}
    if reasons & {Infeasibility.A, Infeasibility.C}:
        return "certificate"
    if Infeasibility.B in reasons:
        return "guidance"
    # 🔴 통과는 D-125 의 정의대로만 — 확정 ∧ 위험도 ≤ 주의 (`is_pass`) · 위험도가 없으면 통과가 아니다
    if all(is_pass(s) for s in sents):
        return "passed"
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
       탐색 실패로 끝난다(전수 재검토 I3). `rejected` 를 안 적었으면 누적으로 판단한다 — 모르면 거부 쪽이다.
    🚨 K 를 소진한 것은 **증명서가 아니라** 「표현 탐색 실패」다 (D-59).
    ⬜ 재판정이 보류·근거없음을 남기는 경우의 `hold` 종착 — 🔜 `rejudge` 가 판정을 낼 때 같이 (D-266 표).
    """
    rejected = state.get("rejected")
    if rejected is None:
        rejected = bool(state.get("rejects"))
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
        state[k] = [*state.get(k, []), *v] if k in reducers else v


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


def to_response(state: ReviewState) -> JudgeResponse:
    """검수 상태를 계약으로 옮긴다. 🚨 계약이 거부하면 여기서 터진다 — 화면보다 먼저다.

    🔄 D-265 — `attempt` 를 넘기지 않는다. 검수에서는 **항상 0** 이다(재검수 횟수와 다른 축).
    ⬜ `category` · `not_reviewed` · `branches` (D-276 · D-277) 는 **넘기지 않는다** — 받은 품목은 판별 결과가 아니고(D-82),
       분기는 `merge_laws` 가 만든다. 🔜 W4 — `classify` 가 판별하고 `merge_laws` 가 분기를 낼 때 같이 옮긴다 (D-192).
    """
    return JudgeResponse(
        outcome=state.get("outcome", Outcome.hold),
        sentences=state.get("sentences", []),
        timings=state.get("timings", []),
        law_version="2026-09-10",
        judged_by="stub-0.2.0",
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
