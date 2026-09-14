"""app/graph.py — walking skeleton (D-124 · Phase 0 게이트).

  uv run python -m app.graph            # 스텁 한 바퀴를 돌려 방문 순서를 찍는다

🚨 **모델도 판정 로직도 없이 end-to-end 한 바퀴가 돈다** — 그것이 Phase 0 게이트의
   정의(*"문구 하나가 end-to-end 한 바퀴"*)와 정확히 같다 (D-124).

★ D-124 가 검사 항목 셋을 정해 뒀다 —
   ① **라우터 함수는 그래프 없이 단독 테스트한다** → 그래서 이 파일은 langgraph 를
      **모듈 최상단에서 import 하지 않는다.** 라우터는 순수 함수이고, 의존성 없이 돈다.
   ② **스텁 노드로 컴파일해 방문 순서만** 본다 → `run_stub()` 이 langgraph 없이도
      같은 순서를 내므로, 의존성이 붙기 전에도 순서를 고정할 수 있다.
   ③ **리듀서 키를 따로 확인한다** → 잘못된 annotation 이 append 대신 **조용히 덮어쓴다.**
      🚨 목록은 `REDUCER_KEYS` **한 곳**이다 (D-99) — 여기 또 적으면 늘 때 낡는다.
      게이트가 그 표를 돌며 `Annotated[..., operator.add]` 를 확인한다.

🔴 **스텁은 비어 있는 것이지 틀린 것이 아니다.** 각 노드는 자기 자리에 무엇이 올지
   적어 두고 상태를 그대로 넘긴다. ⛔ 그럴듯한 값을 지어 넣으면 그 값이 화면으로 흘러가고,
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
    EvidenceArticle,
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
)
from app.settings import PARAMS

#: D-126 — 총 라운드 K+1=3. `attempt` 는 0-base 이므로 마지막 시도는 2 다
MAX_ATTEMPT = PARAMS.max_attempt  # 🔄 값은 app/settings.py — 계약·DB 가 같은 수를 든다


def sent_id(i: int) -> str:
    """문장 하나의 id. 🔴 **규칙이 한 곳에만 있다** (D-99).

    ⛔ 종전에는 `judge` 안에 `f"s{i}"` 가 박혀 있었고, `retrieve` 가 붙는 순간 **두 곳이
       같은 규칙을 각자 적게 된다.** 짝이 어긋나도 오류가 안 난다 — `judge` 가 근거를
       못 찾고 빈 목록을 낼 뿐이고, 응답은 그럴듯하다. 이 저장소가 사흘에 세 번 밟은 모양이다.
    """
    return f"s{i}"


@dataclass(frozen=True, slots=True)
class SentEvidence:
    """`retrieve` 가 문장 하나에 붙인 근거 — **노드 사이 운반체**다 (2026-09-13 · D-124 ③).

    🔴 **왜 생겼나** — 종전에는 `retrieve` 가 찾아 온 것을 놓을 칸이 상태에 **없었다.**
       ⛔ 그러면 붙이는 사람의 선택지가 둘뿐이고 둘 다 나쁘다 —
          ① 리듀서 없는 칸에 넣는다 → 문장이 여럿일 때 **마지막 하나만 남는다.** 오류는 안 난다.
          ② `judge` 안에서 검색을 다시 부른다 → **코어가 두 벌이 된다** (D-99).
       ★ **키가 있으면 계약이 선다.** 09-12 밤에 진입점 B 의 넷을 같은 이유로 세웠다.

    ⛔ **`app/contracts.py` 에 두지 않는다.** 저기는 밖과 맺은 계약이고
       `tests/contract_surface.json` 이 지문을 잡는다 — 4인이 그 모양을 보고 화면을 붙인다.
       이건 그래프 **내부 배선**이라 밖에서 볼 것이 아니다. 계약을 늘리면 사람이 묶인다.
       🚨 문장 판정에 실려 나가는 것은 `SentenceJudgment.evidence`(= `EvidenceArticle` 목록)다.
          **밖으로 나가는 모양은 안 바뀐다.**

    🚨 `vector`·`lexical` 을 같이 나른다 — `retrieve` 주석이 *「`search()` 가 내는 state 를
       버리지 않는다」* 고 적어 둔 그 값이다. **벡터가 죽은 채 어휘 결과만으로 판정하면
       근거가 반쪽인데 응답은 그럴듯하다.** `hold` 로 보내는 근거가 이 둘이다 (D-202).
    """

    sent_id: str
    #: 🔴 `part_total > 1` 인 조각은 조문의 **일부**다 (0011 · D-199) — 그 사실은
    #:    `EvidenceArticle.chunk_id` 로 따라간다. 여기서 조문 이름만 남기지 않는다.
    articles: tuple[EvidenceArticle, ...] = ()
    #: 두 갈래가 각각 돌았는가. ⛔ **둘 다 False 면 근거 없이 판정하는 것**이다 (D-224) — `hold`
    vector: bool = False
    lexical: bool = False
    #: 후보 풀 크기. 🚨 0 은 「안 겹쳤다」이고, `lexical=False` 는 「검색어를 못 만들었다」다.
    #:    ★ 둘은 다른 사건이다 — 한 칸으로 접으면 왜 못 찾았는지가 사라진다 (D-202).
    pool: int = 0


class JudgeState(TypedDict, total=False):
    """상태 스키마 문서 「상태에 반드시 담을 것」이 그대로 이 모양이다.

    🚨 **누적 키에는 반드시 리듀서가 붙는다.** `Annotated[..., operator.add]` 가 없으면
       LangGraph 는 **마지막 노드의 값으로 조용히 덮어쓴다.** 문장이 여럿인데 마지막
       문장만 남는 사고가 여기서 난다 — 오류가 안 나서 발견이 늦다 (D-124 ③).
    """

    # ── 입력 ──────────────────────────────────────────────────────
    text: str
    product: ProductContext
    # ── 분할 ──────────────────────────────────────────────────────
    sents: list[str]
    # ── 근거 검색 🔴 누적 키 (2026-09-13) ────────────────────────
    #: `retrieve` 가 넣고 `judge` 가 읽는다. 🚨 **문장마다 한 벌**이라 누적이다 —
    #: 리듀서가 없으면 마지막 문장의 근거만 남고, 그 상태로도 응답은 그럴듯하다.
    evidence: Annotated[list[SentEvidence], operator.add]
    # ── 판정 누적 🔴 누적 키 ─────────────────────────────────────
    sentences: Annotated[list[SentenceJudgment], operator.add]
    # ── 재생성 루프 (D-126) ──────────────────────────────────────
    #: 0-base. 거부 3종(주장 원장·인용 검증·사후 대조)은 **한 카운터**를 쓴다
    attempt: int
    rejects: Annotated[list[str], operator.add]  # 🔴 누적 키 — 실패 사유
    # ── 진입점 B — 카피 생성 (2026-09-12 밤 · D-181 · 상태 스키마 §개정) ────────
    #  🔴 **넷이 빠져 있었다.** 상태 스키마 문서가 09-10 에 지목했는데 상태에는 안 왔다 —
    #     `페르소나 목록(팬아웃)` · `키워드 선별 결과` · `후보 N=3` · `프론티어 점수`.
    #  ⛔ 그래서 **ksr·lse 의 「AI 광고 생성」 BFF 가 붙을 자리가 없었다.** 값은 아직 스텁이지만
    #     **키가 있으면 계약이 선다** — 뒤에 더하는 필드는 읽는 쪽을 낡게 만든다 (0008→0009).
    #  ⬜ **계약과 어긋나는 자리 하나** — 상태 스키마 문서는 「페르소나 **목록**(팬아웃)」이라
    #     적었는데 `GenerateRequest` 는 `segment` **하나**를 받는다. 둘 중 하나가 낡았다.
    #     여기서는 **계약을 따른다**(하나) — 지어내지 않는다. 판정은 팀장 몫이다 (D-181).
    segment: Segment
    #: 허용/차단 + **사유**. 🔴 누적 키 — 키워드마다 노드가 갈릴 수 있다
    keywords: Annotated[list[KeywordScreen], operator.add]
    #: 프론티어 후보 N=3 (D-31 · D-34). 점수는 `Candidate.appeal_retention`·`residual_risk` 다 —
    #: 🚨 「프론티어 점수」를 따로 두지 않는다. 두면 후보와 두 벌이 된다 (D-99)
    candidates: Annotated[list[Candidate], operator.add]
    #: 매체 프로파일 — **B 의 후단**에 산다 (D-181). 비면 각색 없이 후보만 낸다
    profile: MediaProfile
    #: 채널별 각색 (팬아웃). 🚨 각 결과가 **판정 코어를 다시 지난다** (D-119 · D-63)
    adapted: Annotated[list[AdaptedCopy], operator.add]
    # ── 진입점 C — AI 광고 생성 (D-164 · D-181) ──────────────────────────────
    #  🚨 C 는 진입점이면서 종착이다 — B 에서 받기도 하고 독립 진입도 받는다
    ad_format: AdFormat
    #: 지면 섹션. 🔴 누적 키 — 섹션마다 판정이 붙는다
    sections: Annotated[list[AdSection], operator.add]
    # ── 종료 ─────────────────────────────────────────────────────
    outcome: Outcome
    # ── 계측 (D-77 · D-43 이 LangSmith 를 배제해 이것이 유일한 경로) 🔴 누적 키 ──
    timings: Annotated[list[Timing], operator.add]


#: 누적 키 목록 — 게이트가 여기 붙은 키 전부에 리듀서가 있는지 본다.
#: 🚨 **키를 늘리면 여기 한 줄만 늘린다** — 게이트가 이 표를 돈다 (D-99).
REDUCER_KEYS = (
    "sentences",
    "rejects",
    "timings",
    # 🆕 2026-09-13 — `retrieve` → `judge` 배선 (D-124 ③)
    "evidence",
    # 🆕 2026-09-12 밤 — 진입점 B·C (D-181)
    "keywords",
    "candidates",
    "adapted",
    "sections",
)

#: 진입점 셋이 상태에 다 있는가 — 게이트가 본다.
#: ⛔ `JudgeState` 라는 **이름**은 아직 판정 전용으로 읽힌다. `PipelineState` 로 고치는 것은
#:    게이트·문서가 같이 움직이는 일이라 **따로 판정한다** (병렬작업 계약 §8 ⑤).
ENTRYPOINT_KEYS = {
    "A_judge": ("text", "sents", "evidence", "sentences", "attempt", "outcome"),
    "B_generate": ("segment", "keywords", "candidates", "profile", "adapted"),
    "C_compose": ("ad_format", "sections"),
}


# ══════════════════════════════════════════════════════════════════════
#  계측 — 데코레이터 하나 (D-77 ⑥ 「공수는 데코레이터 하나 + 상태 필드 하나다」)
# ══════════════════════════════════════════════════════════════════════


def timed(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """노드 진입·종료 시각을 상태에 적재한다.

    ⛔ 나중에 붙이면 그때까지의 측정치가 없다 — walking skeleton 에서 함께 넣는다.

    🔄 **2026-09-14 — 뒤 인자를 그대로 넘긴다.** `retrieve` 가 LangGraph 의 `config` 를
       받으면서 노드 인자가 하나가 아니게 됐다. ⛔ 여기서 `fn(state)` 로 고정하면
       **커서가 조용히 사라지고** 검색이 안 붙은 채로 돈다 — 오류는 안 난다.

    🔴 **`functools.wraps` 가 여기서는 장식이 아니라 배선이다** (2026-09-14 실측).
       LangGraph 는 **노드의 시그니처를 보고** `config` 를 넘길지 정한다. 종전처럼
       `__name__` 만 옮기면 밖에서 보이는 모양이 `(state, *rest)` 라 **config 를 안 준다.**
       ⛔ 그래도 오류는 안 난다 — 커서가 `None` 이라 「DB 없음」 경로로 조용히 떨어지고,
          응답은 그럴듯하다. **실제로 이 실수를 한 번 하고 실측으로 잡았다.**
       ★ `wraps` 가 `__wrapped__` 를 달아 `inspect.signature` 가 원래 모양을 보게 한다.
    """

    @functools.wraps(fn)
    def wrapped(state: JudgeState, *rest: Any, **kw: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        out = fn(state, *rest, **kw)
        ms = (time.perf_counter() - t0) * 1000
        out.setdefault("timings", [])
        out["timings"] = [*out["timings"], Timing(node=fn.__name__, ms=ms)]
        return out

    return wrapped


# ══════════════════════════════════════════════════════════════════════
#  스텁 노드 — 자리와 계약만 있고 판정은 없다
# ══════════════════════════════════════════════════════════════════════


@timed
def split(state: JudgeState) -> dict[str, Any]:
    """문장 분할. 🔜 `preprocess/text.py` 의 분할기가 온다."""
    return {"sents": [state["text"]], "attempt": 0}


@timed
def classify(state: JudgeState) -> dict[str, Any]:
    """카테고리 판별. 🚨 사용자에게 묻지 않는다 — 우리가 판별한다 (D-82).

    🔜 `product_fact` 대조 + 분류기. 못 정하면 `hold(cat_unknown)` 으로 간다.
    """
    return {}


def _evidence_article(hit: rt.Hit) -> EvidenceArticle | None:
    """`Hit` → 계약. 🔴 **확신이 없으면 안 옮긴다** (D-224).

    ⛔ `citation()` 이 `None` 이면 좌표를 못 세운 것이다. 「제18조」로 줄여 적으면 실은
       제3항인 근거를 가리킬 수 있다 — 그 함수가 막으려는 **부분 인용** 바로 그것이다.
       지어내지 않고 **버린다.** 그래서 `articles` 가 `hits` 보다 짧을 수 있다.
    ⛔ **`quote` 는 비운다.** 계약이 *「`quote` 는 `source_use.allowed` 가 `U3_cite` 인 것만」*
       이라 적었는데 `search()` 는 `U2_rag` 로 거른다 — **다른 축이다.** 모르는 자격을
       있다고 적지 않는다 (D-224). 🔜 U3 를 같이 읽게 되면 그때 채운다.
    🔴 `part_total > 1` 이면 이 근거는 조문의 **일부**다 (0011 · D-199). 그 사실은
       `chunk_id` 로 따라간다 — 조문 이름만 남기면 3분의 1을 전문으로 인용하는 것이다.
    """
    # 🚨 **`citation()` 을 다시 부르지 않는다** — `Hit` 이 생성 시점에 이미 들고 있다
    #    (`retrieve.py` 의 `Hit(**d, match=…, citation=citation(d))`). 다시 부르면 같은
    #    판단이 두 곳에서 돌고, 한쪽 규칙만 고쳐지는 날 조용히 갈린다 (D-99).
    if not hit.citation or not hit.law_id:
        return None
    return EvidenceArticle(
        law_id=hit.law_id, article=hit.citation, item=hit.item or "", chunk_id=hit.chunk_id
    )


@timed
def retrieve(state: JudgeState, config=None) -> dict[str, Any]:  # noqa: ANN001
    """조문 검색 — `app/retrieve.py` 의 `search()` 를 부른다 (✅ 2026-09-14 · 구현계획 §2-1 C).

    🔴 **검색을 여기서 새로 쓰지 않는다** — 코어는 `app/retrieve.py` 하나다 (D-99 · D-51).
       `/search` 가 이미 그것을 부르고 있고, 여기서 따로 쓰면 그 순간 두 벌이 된다.

           from app import retrieve as rt
           hits, state = rt.search(cur, sentence_text, category, limit)   # state: rt.SearchState

    🔄 2026-09-12 오후 — 종전 주석은 「여기서는 `by_vector` 만 부른다. `by_text` 를 섞으면
       순위 합산 가중치([임의])가 필요해진다」였다. RRF 는 가중치가 없어 그 이유가
       사라졌다 (D-193). **광고 문구야말로 두 갈래가 다 필요하다** — 2026-09-12 실측에서
       벡터 단독은 정답 조문을 6위·19위·50위 밖에 두었다. `/search` 와 **같은 것**을 부른다.
    ⬜ 기호 검색(`by_literal`)은 여기서 안 부른다 — 입력이 광고 문구라 「제5호 아목」이
       올 일이 없다. 빠뜨린 것이 아니라 판정이다 (D-167 — 열의 뜻으로 가른다).
    🚨 `search()` 가 내는 `state` 를 **버리지 않는다.** 벡터가 죽은 채 어휘 결과만으로
       판정하면 근거가 반쪽인데 응답은 그럴듯하다 — `hold` 로 보내는 근거가 `state.vector` 다.
       🔄 2026-09-12 밤 (D-202) — 반환이 문자열 하나에서 `SearchState` 로 바뀌었다.
          `state.lexical` 도 같이 본다: 「검색어를 못 만들었다」는 「안 겹쳤다」와 다르다.
    🔴 **`part_total > 1` 인 근거는 조문의 일부다** (0011 · D-199). `EvidenceArticle` 로 옮길 때
       그 사실을 같이 옮긴다 — 「제18조」라고만 적으면 3분의 1을 전문으로 인용하는 것이다.
       기획서 5-6 의 인용 검증(「존재」가 아니라 「일치」)이 이 칸을 본다.
    🚨 `rt.RetrieveError` 는 여기서 삼키지 않는다. 근거 없이 판정하면 D-224 위반이라
       **`hold` 로 보내는 것**이 맞다 — 빈 근거로 `judge` 에 들어가지 않는다.

    🆕 **커서는 `config` 로 받는다** (구현계획 §2-1 C). ⛔ 노드가 스스로 `connect()` 하면
       **문장마다 연결이 열린다.** ⛔ 상태에 담지도 않는다 — 커넥션은 직렬화가 안 되므로
       체크포인터(D-129)가 붙는 순간 깨진다. LangGraph 는 두 번째 인자로 넣어 주고,
       `run_stub` 은 안 넣는다 — **기본값이 그 경로다.**

    🔴 **DB 가 없어도 이 노드는 돈다** (D-124 — *「화면은 DB 없이 떠야 한다」*). 그렇다고
       빈 dict 로 삼키지 않는다 — 문장마다 「검색을 못 했다」를 **값으로** 남긴다.
       ⛔ 없음이 성공으로 집계되면 안 된다 (D-220 fail-closed). 둘 다 `False` 면
       `judge` 가 확정을 못 내고 `hold` 로 간다.

    ⛔ **리듀서 없는 새 칸을 만들지 않는다.** 문장이 여럿이면 마지막 하나만 남는데
       오류가 안 난다 (D-124 ③). ⛔ **`judge` 안에서 `search()` 를 다시 부르지 않는다** (D-99).

    ⬜ **리랭커는 아직 없다** — 층 4 이고 모델 선정 실측(구현계획 ⑨)이 선행이다.
       여기 자리를 비워 두는 것이 **빠뜨린 것이 아니라 순서**다.
    ⬜ **`SearchState` 의 이유 문자열은 여기서 `bool` 로 접힌다.** `SentEvidence` 가
       「돌았나」만 나르기 때문이고(2026-09-13 설계), **왜 못 돌았는지는 남지 않는다.**
       `hold` 가 사유를 말하려면 그때 칸이 필요하다 — 지금 만들면 읽는 쪽이 없다.
    """
    sents = state.get("sents", [])
    if not sents:
        return {}
    cur = ((config or {}).get("configurable") or {}).get("conn")
    if cur is None:
        return {"evidence": [SentEvidence(sent_id=sent_id(i)) for i in range(len(sents))]}

    product = state.get("product") or ProductContext()
    found: list[SentEvidence] = []
    for i, text in enumerate(sents):
        # 🚨 코어가 결과도 상태도 짓는다 — 이 노드는 얇다 (D-51 · D-99). `api.py` 와 같은 문이다.
        hits, st = rt.search(cur, text, product.category)
        found.append(
            SentEvidence(
                sent_id=sent_id(i),
                articles=tuple(a for h in hits if (a := _evidence_article(h)) is not None),
                vector=st.vector == rt.VECTOR_OK,
                lexical=st.lexical == rt.LEXICAL_OK,
                pool=st.pool,
            )
        )
    return {"evidence": found}


@timed
def judge(state: JudgeState) -> dict[str, Any]:
    """판정. 🔜 룰(사전 536행) + 인코더.

    🚨 스텁은 `unjudged` 를 낸다 — **통과로 집계 금지** (D-127). 비어 있음을 비어 있다고
       말하는 값이고, 그럴듯한 `confirmed` 를 지어내지 않는다.

    🔴 **근거는 `state["evidence"]` 에서 온다** (2026-09-13) — `retrieve` 가 문장별로 쌓아 둔
       `SentEvidence` 다. `sent_id` 로 맞춰 `SentenceJudgment.evidence` 에 옮긴다.
       ⛔ **여기서 검색을 다시 부르지 않는다** — 코어는 `app/retrieve.py` 하나다 (D-99).
       ⛔ 붙는 근거가 없으면 `confirmed` 를 못 낸다 — 계약이 거부한다 (D-224 · `_confirmed_needs_evidence`).
          그 경우의 상태는 `no_basis` 이고, `vector`·`lexical` 이 왜 그런지를 말해 준다.
    """
    # 🆕 2026-09-14 — `retrieve` 가 쌓아 둔 것을 **sent_id 로 짝짓는다.** 값이 입구부터
    #    출구까지 흐르는 최소 경로를 여기서 닫는다: retrieve → judge → SentenceJudgment.evidence
    #    → to_response. ⛔ 만들어 놓고 읽는 쪽을 안 만들면 조용히 샌다 — 사흘에 세 번 밟았다.
    # 🚨 근거가 붙어도 판정은 여전히 `unjudged` 다. **근거를 찾은 것과 판정한 것은 다르다** —
    #    붙였다고 `confirmed` 로 올리면 D-127 이 막는 「미판정을 통과로 집계」가 된다.
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
def assess_risk(state: JudgeState) -> dict[str, Any]:
    """위험도. 🔜 D-09 래칫 `max(코드 하한, 인코더 예측)`.

    🔴 코드 하한은 `sanction_rule` · `v_risk_lookup` 에서 온다 — **지금 0행이라 스텁이다.**
       ⛔ 하한 없이 최종만 적으면 계약이 거부한다. 그래서 아무것도 적지 않는다.
    """
    return {}


@timed
def certificate(state: JudgeState) -> dict[str, Any]:
    """합법화 불가 증명서 (D-32). **A 자격형 · C 절대형에만** (D-125)."""
    return {"outcome": Outcome.certificate}


@timed
def generate(state: JudgeState) -> dict[str, Any]:
    """대체 문구 생성. 🔜 N=3 (D-34) · 3종 세트 (D-33)."""
    return {"attempt": state.get("attempt", 0) + 1}


@timed
def verify(state: JudgeState) -> dict[str, Any]:
    """거부 3종 — 주장 원장 · 인용 검증 · 사후 대조. **한 카운터를 쓴다** (D-126)."""
    return {}


@timed
def frontier(state: JudgeState) -> dict[str, Any]:
    """리스크–소구력 프론티어 (D-31). 단일 답을 주지 않는다."""
    return {"outcome": Outcome.passed}


@timed
def hold(state: JudgeState) -> dict[str, Any]:
    """전문가 검토 종착 (D-125).

    🔴 **종착에도 노드가 있어야 한다** (2026-09-10 실측). ⛔ 처음에는 라우터가 `hold` 를
       내면 곧장 `END` 로 보냈다. 그랬더니 컴파일본은 `outcome` 이 **None 인 채로 끝났고**,
       같은 입력에서 스텁은 `hold` 를 냈다. 방문 순서는 같은데 결과가 달랐다 —
       라우터 단독 테스트로는 안 잡히는 자리다. D-124 ② 가 「컴파일해서 본다」고 한 이유다.
    """
    return {"outcome": Outcome.hold}


@timed
def search_failed(state: JudgeState) -> dict[str, Any]:
    """표현 탐색 실패 — B 가 K 를 소진했다 (D-125).

    🚨 증명서를 내지 않는다. D-59 가 금지한 「B 를 C 처럼 답하기」다.
    """
    return {"outcome": Outcome.search_failed}


#: 🔄 2026-09-14 — 인자가 하나가 아니다. `retrieve` 가 LangGraph 의 `config` 를 받는다.
NODES: dict[str, Callable[..., dict[str, Any]]] = {
    f.__name__: f
    for f in (
        split,
        classify,
        retrieve,
        judge,
        assess_risk,
        certificate,
        generate,
        verify,
        frontier,
        hold,
        search_failed,
    )
}


# ══════════════════════════════════════════════════════════════════════
#  라우터 — 순수 함수. 🚨 그래프 없이 단독으로 테스트한다 (D-124)
# ══════════════════════════════════════════════════════════════════════


def route_after_judge(state: JudgeState) -> str:
    """판정 직후의 갈림. **A·C 는 루프에 들어가지 않는다** (D-125).

    ⛔ A 자격형을 생성 노드로 보내면 재생성이 같은 위반을 반복한다 — 기획서 2-3
       시나리오 A 가 실제로 그렇게 적혀 있었다 (D-59).
    """
    sents = state.get("sentences", [])
    if not sents:
        return "hold"
    # 🔴 **통과 후보는 전부 `confirmed` 일 때만이다** (D-125).
    #    ⛔ 처음에 `hold` 만 걸러 냈더니, 스텁이 내는 `unjudged` 가 프론티어로 흘러가
    #       종착이 `pass` 로 찍혔다. **미판정을 통과로 집계**한 것이고, 상태 스키마가
    #       「🚨 통과로 집계 금지」라고 적어 둔 바로 그 사고다. 한 바퀴를 돌려 보고 잡혔다.
    #    ★ 보류·근거없음·미판정 셋 다 통과가 아니다. 갈 곳은 전문가 검토다.
    if any(s.verdict is not Verdict.confirmed for s in sents):
        return "hold"
    reasons = {s.infeasibility for s in sents if s.infeasibility}
    if reasons & {Infeasibility.A, Infeasibility.C}:
        return "certificate"
    if Infeasibility.B in reasons:
        return "generate"
    return "frontier"


def route_after_verify(state: JudgeState) -> str:
    """재생성 루프의 갈림 (D-126 · D-125).

    🚨 K 를 소진한 B 는 **증명서가 아니라** 「표현 탐색 실패」다 — D-59 가 금지한
       「B 를 C 처럼 답하기」를 막는 자리가 여기다.
    """
    if not state.get("rejects"):
        return "frontier"
    if state.get("attempt", 0) >= MAX_ATTEMPT:
        return "search_failed"
    return "generate"


ROUTES_AFTER_JUDGE = ("hold", "certificate", "generate", "frontier")
ROUTES_AFTER_VERIFY = ("frontier", "generate", "search_failed")


# ══════════════════════════════════════════════════════════════════════
#  한 바퀴 — langgraph 없이도 같은 순서를 낸다
# ══════════════════════════════════════════════════════════════════════


def run_stub(text: str, product: ProductContext | None = None) -> tuple[JudgeState, list[str]]:
    """스텁 한 바퀴. 상태와 **방문 순서**를 돌려준다.

    🚨 이것이 langgraph 컴파일본과 같은 순서를 내야 한다 (D-124 ②). 의존성이 붙기 전에
       순서를 고정해 두면, 붙인 뒤에 순서가 바뀐 것을 게이트가 잡는다.
    """
    state: JudgeState = {
        "text": text,
        "product": product or ProductContext(),
        "sentences": [],
        "rejects": [],
        "timings": [],
        "attempt": 0,
    }
    visited: list[str] = []

    def step(name: str) -> None:
        visited.append(name)
        out = NODES[name](state)
        for k, v in out.items():
            if k in REDUCER_KEYS:
                state[k] = [*state.get(k, []), *v]  # type: ignore[literal-required]
            else:
                state[k] = v  # type: ignore[literal-required]

    for name in ("split", "classify", "retrieve", "judge", "assess_risk"):
        step(name)

    nxt = route_after_judge(state)
    if nxt != "generate":
        step(nxt)  # hold · certificate · frontier — 전부 노드다
        return state, visited

    while True:  # B 실증형 — 재생성 루프
        step("generate")
        step("verify")
        nxt = route_after_verify(state)
        if nxt != "generate":
            step(nxt)  # frontier · search_failed
            return state, visited


def to_response(state: JudgeState) -> JudgeResponse:
    """상태를 계약으로 옮긴다. 🚨 계약이 거부하면 여기서 터진다 — 화면보다 먼저다."""
    return JudgeResponse(
        outcome=state.get("outcome", Outcome.hold),
        sentences=state.get("sentences", []),
        attempt=state.get("attempt", 0),
        timings=state.get("timings", []),
        law_version="2026-09-10",
        judged_by="stub-0.1.0",
    )


def build_graph():  # noqa: ANN201 — langgraph 타입은 지연 import 라 여기서 못 적는다
    """LangGraph 컴파일본. 🔜 의존성이 붙으면 돈다.

    🚨 **지연 import 다.** langgraph 가 없어도 이 모듈의 나머지(라우터·스텁 한 바퀴)는
       돌아야 한다 — D-124 가 「라우터 함수는 그래프 없이 단독 테스트」라고 정했다.
    """
    # 🔴 **추적이 켜져 있으면 멈춘다** (D-43 · D-220 fail-closed · 2026-09-10).
    #    ⛔ `langgraph` → `langchain-core` → `langsmith` 가 전이 의존이라 패키지를 못 뺀다.
    #       켜지면 광고 문구 원문이 밖으로 나간다 — 온프레미스는 서사가 아니라 제품 요구사항이다.
    #    ⛔ **조용히 끄지 않는다.** `os.environ` 을 덮어쓰면 켠 사람이 자기가 켠 것이
    #       무시된 줄 모른다. 그리고 `app` 을 안 거치는 경로가 남아 「막은 척」이 된다 (D-146).
    #    ★ 여기가 langgraph 를 실제로 쓰는 유일한 자리다. import 부작용이 아니라 함수 실행이라
    #      멈추는 지점이 분명하다.
    from langsmith.utils import tracing_is_enabled  # noqa: PLC0415

    if tracing_is_enabled():
        raise SystemExit(
            "🔴 LangSmith 추적이 켜져 있다 — D-43 이 배제했다.\n"
            "   🚨 켜면 광고 문구 원문이 외부로 나간다.\n"
            "   끄는 법: LANGCHAIN_TRACING_V2 · LANGSMITH_TRACING 을 지우거나 false 로 둔다."
        )

    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    g = StateGraph(JudgeState)
    for name, fn in NODES.items():
        g.add_node(name, fn)
    g.add_edge(START, "split")
    for a, b in (
        ("split", "classify"),
        ("classify", "retrieve"),
        ("retrieve", "judge"),
        ("judge", "assess_risk"),
        ("generate", "verify"),
    ):
        g.add_edge(a, b)
    g.add_conditional_edges(
        "assess_risk",
        route_after_judge,
        {
            "hold": "hold",
            "certificate": "certificate",
            "generate": "generate",
            "frontier": "frontier",
        },
    )
    g.add_conditional_edges(
        "verify",
        route_after_verify,
        {"frontier": "frontier", "generate": "generate", "search_failed": "search_failed"},
    )
    for terminal in ("certificate", "frontier", "hold", "search_failed"):
        g.add_edge(terminal, END)
    return g.compile()


def main() -> int:
    state, visited = run_stub("면역력 강화에 도움을 줍니다.")
    print("방문 순서 —", " → ".join(visited))
    r = to_response(state)
    print(f"종착 {r.outcome.value} · 문장 {len(r.sentences)} · attempt {r.attempt}")
    for t in r.timings:
        print(f"    {t.node:12s} {t.ms:7.3f} ms")
    print("\n🚨 스텁이다 — 판정도 모델도 없다. 한 바퀴가 돈다는 것만 보인다 (D-124).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
