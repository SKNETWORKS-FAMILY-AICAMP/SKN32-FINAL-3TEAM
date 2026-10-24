"""scripts/eval_graph.py — **그래프 평가 도구 (W1)**. 판정 그래프를 봉인 평가셋(`test_sentence`)에 돌려 잰다.

    uv run python scripts/eval_graph.py --dev --encoder models/<판>   # dev(검증 묶음) — 판 · 문턱 · 규칙은 여기서 고른다 (D-175)
    uv run python scripts/eval_graph.py --dev --limit 200        # 앞 200행만(실행 시간을 먼저 잰다)
    uv run python scripts/eval_graph.py --dev --provenance ftc_decisions_body
    uv run python scripts/eval_graph.py --dev --stub             # DB 없이 — 배선만(전부 미판정 · 수는 0 이 정상)
    uv run python scripts/eval_graph.py --sealed --out build/eval/graph.json   # 봉인 회차 — 날짜 하나에 한 번 (D-339 결정 7)
    uv run python scripts/eval_graph.py --dev --guide-dev --conditional --answers --out …   # 답 경로(모두 예 · 모두 아니오) 🆕 10-21 보충 35
    uv run python scripts/eval_graph.py --dev --guide-dev --conditional --category-only --out …  # 경로 동치의 짝(품목만) → `scripts/eval_diff.py equiv`

🔴 2026-10-15 (전수 점검 · D-175 · D-339 결정 7 집행) — **봉인 평가셋은 기본값이 아니다.** 종전에는 인자 없이 돌리면 봉인 행을 읽었고,
   「날짜 하나에 한 번」은 기록 한 줄만 남기고 막지 않았다(규칙을 고치며 여러 번 돌려도 셈만 늘었다). 이제 `--dev` · `--sealed` 중
   하나를 반드시 고른다. `--sealed` 는 ① 잠금 **채택** 판 인코더 ② 전 행(`--limit` · `--provenance` · `--no-enc-filter` · `--stub` 불가)
   ③ 이 기기에서 그 날짜의 첫 회차일 때만 돌고, **돌기 전에** 커밋과 함께 기록을 남긴다(도중에 죽어도 열어 본 것은 센다).
   🚨 기록은 기기마다(`build/` 미커밋)다 — 두 기기에서 같은 날 한 번씩은 막지 못한다. 정본 기록은 원장이다 (D-178).

★ **무엇을 답하나** (설계초안 09-23 W1 · D-269 · D-275 · D-301) —
  ① 응답 분포 — 문장 판정 상태 · 종착 · **보류율을 사유별로** (D-269 「게이트 수는 보류율을 사유별로 함께」)
  ② 유형 · 호 P/R/F1 — 예측 = **확정 문장의 위반만**(보류 · 근거없음 · 미판정은 예측이 아니다 · D-127). 30 미만은 측정 불가 (D-40)
  ③ selective risk — 판정을 내린 행(전 문장 확정) 중 틀린 비율 · coverage 와 쌍으로 (D-77 L1 #8)
  ④ 조건별 대응표 — 라벨 조건(C/A/B/M/D/L) × 응답 (D-275 가 W1 몫으로 넘긴 표)
  ⑦ 보수 기록 — 확정 ∪ 분기 보류에 실린 유형을 「기록된 판정」으로 센다 (🆕 2026-10-06 · D-263 ① 「게이트 수치도 이것으로」)
     🔄 2026-10-21 (D-348 보충 37 결정 8 · (다)) — **진단 칸이다 · 대표 지표가 아니다.** 보충 33 으로 「가장 보수적」은 위험도에만 남았고 판정은 답 뒤다 —
        보류 사유 이름만 바뀌어도 수가 흔들렸다(원장 10-21(A) ⑥ · 55 → 87 행). 봉인 보고의 대표 지표는 `REPRESENTATIVE`.
  ⑥ 불가 사유 진단 — 확정 위반의 사유(A/B/C)를 라벨 조건과 대조 (🆕 2026-10-06 · 원장 10-03 ㊿-36). 🚨 게이트가 아니다
  ⑤ 적법 문장 오탐률 — 내역(주장 있음 · 주장 없음)과 함께만 (D-301)
🔴 **채점 규칙은 판정기 B 와 한 곳이다** — `scored` · `truth_types` · `truth_ho` · `lawful_report` · D-40 문턱을
   `scripts/eval_rule.py` 에서 가져온다 (D-99). 판정기 B 와 그래프의 수가 같은 자로 재진다.
🚨 **봉인 평가셋으로 규칙을 고르지 않는다** (D-175) — 이 수는 보고용이다. 규칙 · 문턱을 이 수에 맞춰 고치면 누수다.
🔄 2026-10-01 (D-306) — `--conditional` 이면 **조건부**(골든 `품목` 칸을 제품 정보로 넘긴다 · 품목을 아는 행만) · 기본은
   **무조건부**(품목 미확정 · 세 법). 기획서 6-3 「조건부 / 무조건부 병기」 — 두 번 돌려 나란히 적는다.
   🔴 골든에 `품목` 칸이 없으면(재동결 전 판) `--conditional` 은 멈춘다 — 무조건부로 조용히 바꾸지 않는다 (D-220).
🔄 2026-10-10 — 조건부는 골든 `전제` 칸을 먼저 읽는다(없으면 `품목`). 정답은 (문구 · 전제)의 짝에 붙는다 — 승인 문구 규칙 행이
   `식품` 전제로 돌아오고, 분기 지표의 정답 전제도 이 칸이다. 채점은 그대로 기록되는 판정이다 (D-263 결정 1).
🚨 게이트가 아니다 — 답이 기기마다 다르다(`data/**` 미커밋 · D-19). 수는 원장에 기기 · 커밋 · 골든 sha 와 함께 적는다 (D-178).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import logging
import os
import pathlib
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import (  # noqa: E402 — reasons: 조합 판정 칸은 한 곳 (D-344 ⑨)
    claimscope,  # noqa: E402 — 하한 가드 목록 지문(D-348 보충 41)
    model_lock,
    reasons,
)
from app import encoder as enc  # noqa: E402
from app import graph as g  # noqa: E402
from app import premise as pm  # noqa: E402
from app.contracts import (  # noqa: E402
    Answer,
    Category,
    HoldReason,
    Premise,
    ProductContext,
    SentenceJudgment,
    UserFact,
    UserSubst,
    Verdict,
    Violation,
    encoder_judged,
    hold_kind,
    is_conditional,
)
from app.dictmatch import norm as dict_norm  # noqa: E402 — 정규화는 한 곳 (D-99)
from app.sanction import SANCTION_LAW  # noqa: E402 — 법 ID 는 한 곳 (D-99)
from collect import statute  # noqa: E402
from preprocess import devsplit  # noqa: E402
from preprocess import (
    encoder_resplit as resplit,  # noqa: E402 — 봉인 · 확장 dev 의 정의는 한 곳 (D-347 · D-99)
)
from preprocess.golden import lawful_kind  # noqa: E402
from preprocess.split import APPROVED_READING  # noqa: E402
from scripts import sealed_log  # noqa: E402 — 봉인 기록은 한 곳 (D-344 ⑧ · D-99)
from scripts.eval_rule import (  # noqa: E402 — 채점 규칙은 한 곳 (D-99)
    CLASSES as TYPE_CLASSES,
)
from scripts.eval_rule import (  # noqa: E402
    MIN_MEASURABLE,
    lawful_report,
    print_lawful,
    scored,
    truth_ho,
    truth_types,
)

GOLDEN = pathlib.Path("data/derived/golden/golden.jsonl")
#: 🆕 2026-10-08 (D-175 집행) — **봉인 평가셋을 돌린 기록**(이 기기). 원장 · 결정이 「한 번」을 말해도 도구가 세지 않으면 지켜졌는지
#:    알 수 없다. 🚨 `build/` 는 커밋되지 않는다 — 기기마다 따로 쌓인다. 정본 기록은 원장이다(실행마다 판 표지와 함께 옮긴다)
SEALED_LOG = (
    sealed_log.SEALED_LOG
)  # 🔄 2026-10-15 (D-344 ⑧) — 정본은 `scripts/sealed_log.py` · 시험이 이 이름을 갈아 끼운다
#: 🆕 2026-10-08 (D-321 결정 4) — 6종 표. 8종에서 이번 차수에 편입한 둘을 뺀 것(종전 6종 · 2차와 이어 본다)
NEW_IN_D321 = frozenset({"부당_비교광고", "비방광고"})
#: DB 사전 대조의 기준 — 적재기(`scripts/load_db.py` `load_dict`)가 읽는 바로 그 파일
DICT_FILE = pathlib.Path("data/derived/banned_terms.jsonl")

#: 행 하나의 응답 갈래 — 조건별 대응표(D-275)와 selective risk 가 같이 쓴다.
#: 🔴 「확정 위반」은 **전 문장 확정 ∧ 위반 있음**이 아니라 **위반을 확정한 문장이 하나라도** — 예측의 정의와 같다.
#: 🔄 2026-10-16 (D-348 보충 4 결정 2) — 「조건부위반」: 위반을 확정한 문장은 없고, 조건부 위반 문장(답하면 확정되는 보류)이 **하나라도** 있다
#:    (「확정위반」의 「하나라도」와 같은 규칙 · 다른 문장이 확신 부족 보류여도 그 행은 조건부위반이다). 정의는 `contracts.is_conditional`
#:    🔄 같은 날 고침 — 종전 「나머지가 전부 확정일 때만」은 확정위반과 규칙이 달라 같은 행(조건부 + 확신 부족)이 전에는 확정위반 · 뒤에는 보류로 세어졌다
CLASSES = ("확정위반", "조건부위반", "확정무위반", "보류", "근거없음", "미판정")

#: 🆕 2026-10-21 (D-348 보충 37 결정 8 · (다)) **봉인 보고의 대표 지표** — 고른 뒤 · 답 뒤의 판정을 잰다(보충 33 · 34).
#:    무조건부 수 · 보수 기록은 진단 칸이다(대표가 아니다). 측정 기준은 봉인 전에 고정한다(D-339 결정 7).
REPRESENTATIVE = (
    "조건부(골든 전제를 고른 판정) — 분류 · selective risk · coverage · 확정 재현율 · 유형 P/R",
    "답 경로(`--answers` · 보충 35 결정 2) — 조건별 도달 · 답에 달린 오탐 · 상한 뒤 남은 질문",
    "경로 동치(`scripts/eval_diff.py equiv` · 보충 35 결정 3) — 어긋난 행 0 · 봉인 조건",
    "불변식(보충 35 결정 1) — 위반 행 0 · 봉인 조건 · 세 모드 모두",
)


def load_rows(
    path: pathlib.Path = GOLDEN,
    provenance: str | None = None,
    *,
    dev: bool = False,
    guide_dev: bool = False,
) -> list[dict]:
    """봉인 평가셋 행(기본) 또는 **dev 행**(`dev=True`). 🔴 파일이 없으면 멈춘다 — 빈 목록으로 0 을 내지 않는다 (D-220).

    🆕 2026-10-07 — dev 는 학습 분할에서 뗀 검증 묶음이다(`preprocess/devsplit.py` · 인코더 노트북과 같은 행).
       판 · 문턱 · 규칙을 고르는 자리는 봉인이 아니라 여기다 (D-175).
    """
    if not path.exists():
        raise SystemExit(
            f"🔴 {path} 가 없다 — 정본은 `launcher.py golden --write` · 사본은 `data-sync`"
        )
    every = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if dev:
        by_id = {r["id"]: r for r in every}
        rows = [by_id[i] for i in devsplit.dev_ids(every)]
        if guide_dev:
            # 🆕 2026-10-15 (D-347) — 확장 dev = devsplit 의 dev + 재분할의 해설서 dev. 지문은 따로 찍는다(`check_dev`)
            rows += resplit.guide_dev_rows(every)
    else:
        # 🔄 2026-10-15 (D-347) — 봉인 평가셋 = 봉인 행 중 인코더 학습 · dev 로 옮기지 않은 것. 정의는 한 곳(D-99)
        rows = resplit.sealed_rows(every)
    if provenance:
        rows = [r for r in rows if r.get("provenance") == provenance]
    return rows


# ── 한 행 → 예측 ────────────────────────────────────────────────────────


def _ho(sent: SentenceJudgment) -> set[str]:
    """확정 문장의 근거 중 **사전 근거**(인용 꼴로 되돌릴 수 있는 것)의 호. 검색 근거는 판정 문맥이라 세지 않는다.

    🔴 2026-10-08 — 종전에는 `law_id:article+item` 을 이어 붙여 `statute.parse` 에 넣었다. 그래프는 목을 「제5호다목」으로
       적고 인용 꼴은 「제5호|다목」이라 **목 붙은 사전 근거가 전부 조용히 빠졌다**(호 재현율이 낮게 나온다).
       되읽기는 그래프가 쓰는 꼴과 같은 곳(`statute.from_article_item`)에서 한다 (D-99).
    """
    out = set()
    for a in sent.evidence:
        # 🔄 2026-10-08 (D-323 결정 2) — 사전 근거만(`basis`). 꼴은 같은 곳에서 되읽는다
        if a.basis and (c := statute.from_article_item(a.law_id, a.article, a.item)) is not None:
            out.add(statute.ho_key(c))
    return out


def _questions(sents: Iterable[SentenceJudgment]) -> list[str]:
    """문장들에 선 질문 — `<문장>:fact:<종류>` · `<문장>:subst:<유형>` (🆕 2026-10-21 · D-348 보충 35). 결과 파일끼리 질문이 같은지 맞대는 열쇠다.

    🔄 2026-10-21 (보충 39 결정 6 · 2 단계) 실증 질문은 유형마다 따로 선다 — 열쇠에 유형을 싣는다(`SubstBranch.violation`) · 유형이 빈 질문은 종전 꼴
       `<문장>:subst`. 분기마다 다른 유형을 묻는 문장(종전 `_tag_subst` 의 알려진 한계 · 🔄 10-24 보충 42 로 걷음)을 결과 파일로 세는 열쇠다.
       ⚠️ 이 판 전 결과 파일과 `eval_diff diff` 로 맞대면 실증 질문이 선 행은 질문 칸이 바뀐 것으로 나온다(열쇠 꼴이 바뀜 · 판정은 같음).
    """
    out = []
    for s in sents:
        if s.fact_check is not None:
            out.append(f"{s.sent_id}:fact:{s.fact_check.kind.value}")
        if s.substantiation is not None:
            v = s.substantiation.violation
            out.append(f"{s.sent_id}:subst" + (f":{v.value}" if v is not None else ""))
    return sorted(out)


def _risk_max(sents: Iterable[SentenceJudgment]) -> str | None:
    """문장들의 `risk.final` 최댓값 — 없으면 None(낮음으로 세지 않는다 · D-72)."""
    got = [s.risk.final for s in sents if s.risk.final is not None]
    return max(got, key=lambda r: r.level).value if got else None


def predict(state: dict[str, Any]) -> dict[str, Any]:
    """그래프 상태 → 행 예측. 예측 유형 · 호는 **확정 문장의 위반만**이다 (D-127 · 보류는 예측이 아니다)."""
    sents: list[SentenceJudgment] = list(state.get("sentences", []))
    conf = [s for s in sents if s.verdict is Verdict.confirmed]
    types = sorted({v.value for s in conf for v in s.violations})
    #: 🆕 2026-10-02 (D-311) — **보류 문장의 유형 후보**(단독판정 자격 없는 적중). 예측이 아니다 — 탐지 재현율만 읽는다
    cands = sorted({v.value for s in sents if s.verdict is Verdict.hold for v in s.violations})
    ho = sorted({h for s in conf if s.violations for h in _ho(s)})
    verdicts = [s.verdict.value for s in sents]
    cond = [s for s in sents if is_conditional(s)]
    if any(s.violations for s in conf):
        cls = "확정위반"
    elif cond:
        cls = "조건부위반"
    elif sents and len(conf) == len(sents):
        cls = "확정무위반"
    elif any(s.verdict is Verdict.unjudged for s in sents) or not sents:
        cls = "미판정"
    elif any(s.verdict is Verdict.hold for s in sents):
        cls = "보류"
    else:
        cls = "근거없음"
    outcome = state.get("outcome")
    return {
        "outcome": getattr(outcome, "value", outcome),
        "verdicts": verdicts,
        "hold_reasons": sorted({s.hold_reason.value for s in sents if s.hold_reason is not None}),
        "types": types,
        "candidates": cands,
        #: 🔄 2026-10-09 (D-323 집행) — **응답에 실린 인코더 유형 후보**(문장의 `encoder_candidates` · 이 품목의 전제로 거른 것).
        #:    판정에 쓰이지 않은 신호다 — `candidates`(문장 판정에 실린 보류 후보)와 섞지 않는다.
        #:    인코더가 안 돌았으면 `encoded` 가 거짓이고 이 칸은 빈다. ⛔ 종전에는 상태의 `encodings` 를 직접 읽었다 —
        #:    응답에 나가는 것과 재는 것이 달라질 수 있었다(거름이 응답에만 걸린다)
        #: 🔄 2026-10-10 — **인코더가 직접 낸 유형만** 센다. 전제가 옮긴 후보(`moved_from`)는 `enc_moved` 에 따로 둔다 —
        #:    옮긴 후보를 섞으면 건강기능식품 오인 신호가 거짓_과장 적중으로 세어진다
        "enc_candidates": sorted(
            {c.violation.value for s in sents for c in s.encoder_candidates if c.moved_from is None}
        ),
        "enc_moved": sorted(
            {
                c.violation.value
                for s in sents
                for c in s.encoder_candidates
                if c.moved_from is not None
            }
        ),
        #: 🆕 2026-10-14 (D-340 결정 8) — 인코더가 직접 낸 후보의 **확신**(유형 → 문장 중 최댓값). 칸 표 · 추정 위험도의 재료다
        "enc_conf": _enc_conf(sents),
        #: 🔄 2026-10-14 (D-336) — 품목 입력 판은 문장마다 입력 여럿의 신호가 실린다 — **문장 수**로 센다(신호 수가 아니라)
        "encoded": bool(sents)
        and len({e.sent_id for e in state.get("encodings", [])}) == len(sents),
        "enc_truncated": len({e.sent_id for e in state.get("encodings", []) if e.truncated}),
        #: 🆕 2026-10-14 (D-336) — 신호를 낸 품목 입력(문장만 받는 판은 `*`)
        "enc_inputs": sorted({e.input for e in state.get("encodings", [])}),
        "ho": ho,
        "class": cls,
        #: 판정을 내린 행 — **전 문장이 확정**이다(selective risk 의 분모 · D-77 L1 #8)
        "committed": bool(sents) and len(conf) == len(sents),
        #: 🆕 2026-10-17 (D-348 보충 6 결정 5) — 확정 문장 중 **인코더 판정**(사전 근거 · 사용자 답 없음)이 있나 — 조합 칸 「인코더 판정 확정」
        "enc_judged": any(encoder_judged(s) for s in conf),
        #: 🆕 2026-10-02 (W5) — 확정 위반 문장에 **위험도가 다 붙었나**. 붙었는데 종착이 보류면 하한이 아니라 종착 재료(증명서 · 지시 문안)가 없다
        "risked": all(s.risk.final is not None for s in conf if s.violations),
        #: 🆕 2026-10-20 (D-348 보충 31) — **기록 위험도의 가장 높은 등급**(문장들의 `risk.final` 최댓값 · 없으면 None).
        #:    보류 기록이 가정 위의 확정으로 끌려 오르는지(보충 8 · 31)를 이 칸으로 센다 · 판정이 아니다
        "risk_max": _risk_max(sents),
        "n_sents": len(sents),
        #: 🆕 2026-10-15 (D-348 보충 1) — **판정 대상 아님 문장이 있나**(L0 · 주의 · 상담 문구). 칸 표에서 「사전 확정」과 가르고,
        #:    판정 대상 아님만 있는 행이 품목 미확정으로 보류된 까닭(D-319 결정 2)을 「종착 재료 없음」과 가른다
        "not_claim": any(s.not_claim for s in sents),
        "not_claim_only": bool(sents) and all(s.not_claim for s in sents),
        #: 🆕 2026-10-16 (D-348 보충 2) — **기록 판정에 인코더 하한이 붙은 문장이 있나**(보류 문장 · 판정은 그대로).
        #:    보충 1 결정 3 의 지표(적법에 하한이 붙는 비율)가 이 칸을 센다
        "enc_risk": any(s.risk.encoder is not None for s in sents),
        #: 🆕 2026-10-16 (D-348 보충 3) — 사실 확인 분기가 달린 문장이 있나 · 사용자가 확인한 사실로 정한 문장이 있나
        "fact_branch": any(s.fact_check is not None for s in sents),
        #: 🆕 2026-10-21 (D-348 보충 35) — 기록 문장에 선 질문(`_questions`) · 경로 동치 대조(`scripts/eval_diff.py`)와 답 경로의 재료
        "questions": _questions(sents),
        #: 🆕 2026-10-21 (D-348 보충 36 결정 4) — 보류 문장의 종류(답 대기 · 고르기 대기 · 확인 못 함 · 걸린 것 없음 · 그 밖) · 계약 `hold_kind` 한 곳
        "hold_kinds": sorted({k.value for s in sents if (k := hold_kind(s)) is not None}),
        "user_fact": any(s.user_facts for s in sents),
        #: 🆕 2026-10-16 (D-348 보충 4) — 조건부 위반 문장의 유형(가장 나쁜 경우 = 답 없음 · 거짓 분기의 판정) · 사전 유형, 없으면 인코더 근거의 유형
        "cond_types": sorted(
            {v.value for s in cond for v in s.violations}
            | {b.violation.value for s in cond if not s.violations for b in s.risk.encoder_basis}
        ),
        "user_subst": any(s.user_subst is not None for s in sents),
        #: 🆕 2026-10-16 (D-348 보충 5) — **인코더 쪽 보류 + 분기**(답 없이 확정하지 않는다 · 조건부가 아니다)가 달린 문장이 있나 · 그 유형
        "enc_choice": any(
            s.verdict is Verdict.hold
            and s.hold_reason is HoldReason.low_conf
            and (s.fact_check is not None or s.substantiation is not None)
            for s in sents
        ),
        #: 🆕 2026-10-16 — **응답 계약을 지나지 못한 행**(`to_response` 가 거부) · 앱이라면 그 요청은 오류로 끝난다. 실제 실행에서만 채운다(`_checked`)
        "contract_error": state.get("_contract_error"),
        #: 🆕 2026-10-06 (D-263 ① · D-319 ①) — **분기 때문에 보류로 기록된 문장에 실린 유형**(가장 보수적인 전제의 위반).
        #:    `candidates`(자격 없는 적중까지 든 보류 후보)와 다르다 — 전제를 몰라 멈춘 문장만이다
        "premise_held": sorted(
            {
                v.value
                for s in sents
                if s.verdict is Verdict.hold
                and s.hold_reason in PREMISE_HOLDS
                # 🔄 2026-10-16 (D-348 보충 4) — 조건부 위반은 품목 · 전제 보류가 아니다(`cond_types` 로 따로 센다)
                and not is_conditional(s)
                for v in s.violations
            }
        ),
        #: 🆕 2026-10-06 — 확정 위반 문장의 **가장 막힌 불가 사유**(C > A > B · 종착 우선순위와 같은 순서). 없으면 `None`
        "infeasibility": next(
            (
                x.value
                for x in g._INFEAS_ORDER
                if any(s.infeasibility is x for s in conf if s.violations)
            ),
            None,
        ),
        #: 🆕 2026-10-05 (D-319) — **전제별 분기**의 요약. 분기는 판정이 아니다 — 위 칸(기록되는 판정)과 섞어 세지 않는다 (D-263 ①)
        "branches": {b.premise.value: _branch_view(b) for b in state.get("branches", [])},
    }


def _enc_conf(sents: list[SentenceJudgment]) -> dict[str, float]:
    """문장들의 인코더 직접 후보 → 유형별 최대 확신(소수 넷째 자리). 옮긴 후보는 넣지 않는다 — 확신이 원래 유형의 것이다."""
    out: dict[str, float] = {}
    for s in sents:
        for c in s.encoder_candidates:
            if c.moved_from is None:
                out[c.violation.value] = max(out.get(c.violation.value, 0.0), c.confidence)
    return {k: round(v, 4) for k, v in sorted(out.items())}


def _branch_view(b: Any) -> dict[str, Any]:
    """분기 하나 → 확정 위반의 유형 · 호 · 종착. 기록되는 판정과 **같은 규칙**으로 센다(확정 문장의 위반만 · D-127)."""
    conf = [s for s in b.sentences if s.verdict is Verdict.confirmed]
    return {
        #: 🆕 2026-10-14 (D-336 결정 6) — 분기의 **인코더 후보**(그 전제의 품목 입력 · 그 전제로 거른 것). 분기 관문을 따로 적는 재료다
        "enc_candidates": sorted(
            {
                c.violation.value
                for s in b.sentences
                for c in s.encoder_candidates
                if c.moved_from is None
            }
        ),
        "enc_moved": sorted(
            {
                c.violation.value
                for s in b.sentences
                for c in s.encoder_candidates
                if c.moved_from is not None
            }
        ),
        "enc_conf": _enc_conf(list(b.sentences)),
        "outcome": b.outcome.value,
        "types": sorted({v.value for s in conf for v in s.violations}),
        #: 🆕 2026-10-11 — 분기 안 **보류 문장의 유형 후보**(행의 `candidates` 와 같은 뜻 · D-311). 지표에는 쓰지 않는다 —
        #:    전제가 후보를 바꾸는 자리(D-319 보충 10-11)를 결과 파일끼리 견줄 수 있게 적는다. 종전에는 확정 유형만 적어
        #:    분기 안의 후보가 바뀌어도 대조에 보이지 않았다(원장 10-10 ⑮)
        "candidates": sorted(
            {v.value for s in b.sentences if s.verdict is Verdict.hold for v in s.violations}
        ),
        #: 🆕 2026-10-16 (D-348 보충 4) — 분기 안 **조건부 위반** 문장의 유형(답 없음 = 그 분기의 가장 나쁜 경우)
        "cond_types": sorted(
            {v.value for s in b.sentences if is_conditional(s) for v in s.violations}
            | {
                x.violation.value
                for s in b.sentences
                if is_conditional(s) and not s.violations
                for x in s.risk.encoder_basis
            }
        ),
        "ho": sorted({h for s in conf if s.violations for h in _ho(s)}),
        "committed": bool(b.sentences) and len(conf) == len(b.sentences),
        #: 🆕 2026-10-21 (D-348 보충 35 결정 2) — 경로 동치 대조의 칸(기록 쪽 `predict` 와 같은 이름 · 같은 함수)
        "verdicts": [x.verdict.value for x in b.sentences],
        "hold_reasons": sorted(
            {x.hold_reason.value for x in b.sentences if x.hold_reason is not None}
        ),
        "questions": _questions(b.sentences),
        "risk_max": _risk_max(b.sentences),
    }


def branch_report(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """분기 지표 (D-319 ⬜ 「정답 전제의 분기가 맞는가」) — 전제를 아는 채점 행의 **위반 행**에서 그 전제의 분기를 본다.

    ★ 기록되는 판정이 보류(`cat_unknown`)여도 사용자가 자기 제품의 전제를 고르면 보게 되는 것이 이 분기다.
    🚨 분기가 없으면(기준 문안 미확정 · 전제 하나) 0 이다 — 「분기 행」 수를 함께 읽는다.
    🔄 2026-10-10 — 정답 전제는 **골든의 `전제` 칸**이다(`preprocess/golden.py` `label_premise`). 종전에는 품목에서 짐작했다
       (건강기능식품이면 전부 비인정). 전제를 모르는 행은 세지 않는다 — 건강기능식품은 [별표 1] 4.나 인용 행만 든다 (D-220).
       `by_premise` — 전제별 (위반 행 · 그 분기의 확정 위반 · 유형 맞음). 전제마다 행 수가 크게 달라 합만 읽으면 가려진다
    """
    out = {"rows_with_branches": sum(1 for p in preds if p.get("branches")), "positive": 0}
    out.update({"confirmed": 0, "type_hit": 0, "ho_hit": 0, "wrong": 0})
    #: 🆕 2026-10-16 (D-348 보충 4) — 분기의 확정 위반이 없고 조건부 위반이 있는 행 · 그 유형이 정답과 겹친 행(확정 수와 나란히)
    out.update({"conditional": 0, "cond_hit": 0})
    by: dict[str, list[int]] = {}
    for r, p in zip(rows, preds, strict=True):
        name = r.get("전제")
        if not name or not scored(r) or not truth_types(r, set()):
            continue
        b = (p.get("branches") or {}).get(name)
        if b is None:
            continue
        out["positive"] += 1
        cell = by.setdefault(name, [0, 0, 0])
        cell[0] += 1
        if not b["types"]:
            ct = set(b.get("cond_types", ()))
            if ct:
                out["conditional"] += 1
                out["cond_hit"] += bool(ct & truth_types(r, ct))
            continue
        out["confirmed"] += 1
        cell[1] += 1
        cell[2] += bool(set(b["types"]) & truth_types(r, set(b["types"])))
        tt, th = truth_types(r, set(b["types"])), truth_ho(r, set(b["ho"]))
        out["type_hit"] += bool(set(b["types"]) & tt)
        out["ho_hit"] += bool(set(b["ho"]) & th)
        out["wrong"] += not (set(b["types"]) & tt)
    out["by_premise"] = {k: tuple(v) for k, v in sorted(by.items())}
    return out


def branch_encoder_report(rows: list[dict], preds: list[dict]) -> dict[str, tuple[int, int, int]]:
    """분기 인코더 지표 (🆕 2026-10-14 · D-336 결정 6) — 전제를 아는 채점 위반 행에서 **그 전제 분기의 인코더 후보**를 본다.

    전제마다 (위반 행 · 후보가 정답 유형과 겹친 행 · 무엇이든 후보가 선 행). 분기의 후보는 그 전제의 것이라 옮긴 후보도 센다.
    🔴 인코더가 안 돈 행은 세지 않는다(`encoded` · D-220). 🚨 분기는 판정이 아니다 — 기록 판정의 수와 섞지 않는다 (D-263 ①)
    """
    by: dict[str, list[int]] = {}
    for r, p in zip(rows, preds, strict=True):
        name = r.get("전제")
        if not name or not p.get("encoded") or not scored(r):
            continue
        b = (p.get("branches") or {}).get(name)
        if b is None:
            continue
        got = set(b.get("enc_candidates", ())) | set(b.get("enc_moved", ()))
        tt = truth_types(r, got)
        if not tt:
            continue
        cell = by.setdefault(name, [0, 0, 0])
        cell[0] += 1
        cell[1] += bool(got & tt)
        cell[2] += bool(got)
    return {k: tuple(v) for k, v in sorted(by.items())}


#: 조합 판정 칸 (D-340 결정 1 · 원장 10-14(A) ①) — 🔄 2026-10-15 (D-344 ⑨) 칸 이름과 규칙의 정본은 `app/reasons.py` 한 곳이다
COMBO_CELLS = reasons.COMBO_CELLS


def combo_cell(p: dict) -> str:
    """행 예측 → 조합 판정 칸. 기록 판정의 칸이다(인코더 후보는 직접 낸 것만 · 옮긴 후보 제외). 규칙은 `reasons.combo_cell` (D-99)."""
    return reasons.combo_cell(
        bool(p["committed"]),
        p.get("candidates", ()),
        p.get("enc_candidates", ()),
        not_claim=bool(p.get("not_claim_only")),
        encoder_judged=bool(p.get("enc_judged")),
    )


def combo_report(rows: list[dict], preds: list[dict]) -> dict[str, tuple[int, int, int, int]]:
    """조합 판정 칸 표 (🆕 2026-10-14 · D-340 결정 8) — 칸마다 (행 · 위반(조건 A · B · C) · 적법(D · L) · 모호(M)).

    🔴 인코더가 돈 행만 센다 — 안 돈 행을 「인코더 조용」 칸에 넣지 않는다 (D-220). 🚨 진단이다 — 칸의 수로 규칙 · 문턱을 고르지 않는다(D-175).
    """
    by = {k: [0, 0, 0, 0] for k in COMBO_CELLS}
    for r, p in zip(rows, preds, strict=True):
        if not p.get("encoded"):
            continue
        cell = by[combo_cell(p)]
        cond = r.get("조건") or ""
        cell[0] += 1
        cell[1] += cond in ("A", "B", "C")
        cell[2] += cond in ("D", "L")
        cell[3] += cond == "M"
    return {k: tuple(v) for k, v in by.items() if v[0]}


# ── 집계 ────────────────────────────────────────────────────────────────


#: 전제를 몰라 멈춘 보류 사유 — 계약 `_branch_hold_has_branches` 의 것과 같다(D-263 ② · D-229 ⑥).
PREMISE_HOLDS = frozenset({HoldReason.cat_unknown, HoldReason.premise_unknown})


def recorded_report(rows: list[dict], preds: list[dict]) -> dict[str, int]:
    """보수 기록 지표 (🆕 2026-10-06 · D-263 ① 「기록되는 판정 = 가장 보수적인 전제 · 게이트 수치도 이것으로 잰다」).

    🔄 2026-10-21 (D-348 보충 37 결정 8 · (다)) — **진단 칸**으로 내린다(대표 지표 · 게이트 수치가 아니다 · `REPRESENTATIVE`).
       보충 33 이 D-263 ① 의 판정 쪽을 걷었다 · 사유 표지(`low_conf` → `cat_unknown`)만 바뀌어도 수가 흔들린다(원장 10-21(A) ⑥).

    ★ 기록된 유형 = 확정 문장의 위반 ∪ 분기 때문에 보류된 문장에 실린 위반(`premise_held`). 채점 행만 센다.
       `rows` 기록이 있는 행 · `wrong` 기록이 정답과 하나도 안 겹친다(적법 행에 기록이 있는 것 포함) ·
       `positive` 위반 행 · `hit` 그중 기록이 정답과 겹친다.
    🚨 「확정만 센 수」(selective risk · 확정 재현율)와 **나란히만** 읽는다 — 보류는 확정이 아니다(D-127).
       품목 미확정의 보수 기록에는 그 품목에 적용되는지 모르는 법의 유형이 든다(D-319 ①).
    """
    out = {"rows": 0, "wrong": 0, "positive": 0, "hit": 0}
    for r, p in zip(rows, preds, strict=True):
        if not scored(r):
            continue
        rec = set(p["types"]) | set(p.get("premise_held", ()))
        tt = truth_types(r, rec)
        if tt:
            out["positive"] += 1
            out["hit"] += bool(rec & tt)
        if rec:
            out["rows"] += 1
            out["wrong"] += not (rec & tt)
    return out


#: 예측 사유 → 라벨 조건의 짝 가운데 **축이 달라 어긋남으로 세지 않는** 것. 라벨의 A 는 「제품의 지위 · 조성에 달림」 전부이고
#: (지시서 §2 · §3 ⑨ — 천연 · 무첨가 · 인증 마크 · 기관 이름) 증명서의 A 는 「인정 절차를 밟으면 풀림」뿐이다(D-59). 앞쪽은
#: 설계가 B + 사실 확인 분기로 보낸다(D-308 4′ · D-313 결정 4).
REASON_AXIS_GAP = frozenset({("B", "A")})
HF_MISLEAD_TYPE = "건강기능식품_오인"


def reason_report(rows: list[dict], preds: list[dict]) -> dict[str, int]:
    """불가 사유 진단 (🆕 2026-10-06) — 확정 위반을 낸 채점 행에서 예측 사유를 라벨 `조건`(A/B/C)과 대조한다.

    ★ `exact` 글자가 같다 · `axis_gap` 축이 달라 어긋남이 아니다(`REASON_AXIS_GAP`) · `wrong` 증명서 ↔ 지시 또는 A ↔ C 가 바뀐다.
    🚨 **진단이다 — 게이트 · 규칙 선택에 쓰지 않는다** (D-175). 조건 라벨은 대부분 모델 판독의 합의이고(원장 10-03 ㊿-36),
       식품 3호는 사유가 주장의 범위에 달려(범위 안 A · 밖 C · D-320) 유형 하나로 못 정한다 — `wrong_hf` 로 따로 센다.
    🔴 사유가 없는 예측(확정 위반 아님) · 조건이 A/B/C 가 아닌 행은 세지 않는다 — 없음을 일치로 세지 않는다 (D-220).
    """
    out = {"n": 0, "exact": 0, "axis_gap": 0, "wrong": 0, "wrong_hf": 0}
    for r, p in zip(rows, preds, strict=True):
        got, want = p.get("infeasibility"), r.get("조건")
        if got is None or want not in ("A", "B", "C") or not scored(r):
            continue
        out["n"] += 1
        if got == want:
            out["exact"] += 1
        elif (got, want) in REASON_AXIS_GAP:
            out["axis_gap"] += 1
        else:
            out["wrong"] += 1
            out["wrong_hf"] += HF_MISLEAD_TYPE in (r.get("labels") or [])
    return out


def _prf(gold: int, tp: int, fp: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / gold if gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """비율 k/n 의 95% 신뢰구간(윌슨) — D-40 (b) 「신뢰구간 병기」. `n == 0` 이면 `None`(구간이 없다 · 0 으로 쓰지 않는다).

    [문헌] 윌슨 점수 구간 — 표본이 작고 비율이 0 · 1 에 가까울 때 정규 근사보다 덜 깨진다. z = 1.96 은 95% [관행].
    """
    if n <= 0:
        return None
    ph = k / n
    den = 1 + z * z / n
    mid = (ph + z * z / (2 * n)) / den
    half = z * ((ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def _ci(k: int, n: int) -> str:
    c = wilson(k, n)
    return "-" if c is None else f"[{c[0]:.1%}, {c[1]:.1%}]"


def macro_table(types: dict[str, tuple[int, int, int]]) -> dict[str, dict[str, Any]]:
    """🆕 2026-10-08 (D-321 결정 4 · D-40) — 8종 · 6종 **두 표**. 측정 가능한(정답 30 이상) 유형만 macro 에 든다.

    ★ micro 는 측정 불가 유형까지 합친 수다 — 둘을 나란히 낸다. ✅ 2026-10-11 — 어느 쪽도 합격선이 아니다(D-322 결정 A · 보고 묶음).
    🚨 표에 없는 유형(편입 대기)은 `truth_types` 가 이미 뺐다.
    """
    out: dict[str, dict[str, Any]] = {}
    for name, keep in (("8종", TYPE_CLASSES), ("6종", TYPE_CLASSES - NEW_IN_D321)):
        rows = {t: v for t, v in types.items() if t in keep}
        meas = {t: v for t, v in rows.items() if v[0] >= MIN_MEASURABLE}
        prf = [_prf(*v) for v in meas.values()]
        g, tp, fp = (sum(v[i] for v in rows.values()) for i in range(3))
        out[name] = {
            "measurable": sorted(meas),
            "unmeasurable": sorted(set(rows) - set(meas)),
            "macro": tuple(sum(x[i] for x in prf) / len(prf) for i in range(3)) if prf else None,
            "micro": _prf(g, tp, fp),
            "micro_n": (g, tp, fp),
        }
    return out


def _with_encoder(r: dict, p: dict) -> set[str]:
    """확정 ∪ 사전의 보류 후보 ∪ 인코더 후보 — 옮긴 후보는 그 전제인 행에서만 (D-326 보충 12 · `encoder_report` 의 규칙).

    ★ `encoder_report` 와 `detect_by_type` 가 같이 쓴다 — 규칙을 두 곳에 적지 않는다 (D-99).
    """
    pe = set(p["types"]) | set(p.get("candidates", ())) | set(p.get("enc_candidates", ()))
    if r.get("전제") == Premise.건기식_비인정.value:
        pe |= set(p.get("enc_moved", ()))
    return pe


def detect_by_type(sc: list[tuple[dict, dict]]) -> dict[str, tuple[int, int, int, int, int]]:
    """🆕 2026-10-11 (D-321 결정 6 · D-40 · D-311 보충) — **유형별 탐지**: 유형 → (정답, 확정, 사전 후보까지, 인코더가 돈 정답, 인코더 후보까지).

    ★ `types` 표의 R 은 확정만 센다 — 사전이 확정하지 못하는 유형은 0 으로만 찍혀 후보가 어디까지 닿는지 보이지 않았다.
    · **(행 · 유형) 단위다.** 한 행에 유형이 여럿이면 유형마다 센다 — 정답의 합은 위반 행 수(`detect.positive`)보다 크다.
    · 세 칸은 포함 관계다(확정 ⊆ 사전 후보까지 ⊆ 인코더 후보까지). 「탐지」는 사전 후보까지의 이름이다 (D-311 보충).
    · 정답은 `truth_types` — 후보만 있는 행은 가장 넓은 예측(인코더가 돌았으면 인코더 후보까지)에 맞춰 고른다. 세 칸이 같은 정답을 본다.
    🔴 인코더가 안 돈 행은 인코더 칸의 분모에도 들지 않는다 — 「후보 없음」으로 세지 않는다 (D-220).
    ⛔ 판정이 아니고 합격선도 없다 (D-322 결정 A). 정답 30 미만은 측정 불가로 찍는다 (D-40) — 수를 지우지는 않는다.
    """
    acc: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for r, p in sc:
        pt = set(p["types"])
        pd = pt | set(p.get("candidates", ()))
        enc = bool(p.get("encoded"))
        pe = _with_encoder(r, p) if enc else pd
        for t in truth_types(r, pe):
            a = acc[t]
            a[0] += 1
            a[1] += t in pt
            a[2] += t in pd
            a[3] += enc
            a[4] += enc and t in pe
    return {t: (v[0], v[1], v[2], v[3], v[4]) for t, v in sorted(acc.items())}


def encoder_report(
    rows: list[dict], preds: list[dict], sc: list[tuple[dict, dict]]
) -> dict[str, Any]:
    """**인코더 신호를 유형 후보로 더했다면**의 탐지 재현율 (🆕 2026-10-07 · 그림자 배선).

    ★ 판정은 인코더를 읽지 않는다 — 이 수는 「붙이면 탐지가 얼마가 되나」이고 **지금 그래프가 낸 판정의 수가 아니다.**
       `detect`(D-311 결정 5 · 확정 ∪ 보류 유형 후보)는 그대로 두고 **따로** 싣는다.
       ✅ 닫음 (2026-10-11 · D-311 보충) — D-311 의 「보류 유형 후보」는 사전의 자격 없는 적중이다. **「탐지 재현율」은 사전 후보까지
          (`detected`)의 이름이고, 인코더 후보까지(`detected_with_encoder`)는 따로 싣고 그 이름으로 부른다** — 한 수로 합치지 않는다
          (D-323 결정 3 · 안건 1 (나) 기각 이유).
    🔴 인코더가 **전 문장에** 돈 행만 센다(`encoded`). 안 돈 행을 「조용했다」로 세지 않는다 (D-220) — 없으면 `rows` 가 0 이다.
    🆕 2026-10-10 — 「탐지」의 뜻이 둘이라 **이름을 달리해 함께** 낸다. 섞어 견주면 같은 판이 다른 점수로 보인다.
       · `detected_with_encoder` — **유형 적중**: 정답 유형이 (확정 ∪ 보류 후보 ∪ 인코더 후보)에 있다. D-311 결정 5 의 탐지에 인코더 후보를 더한 수다
       · `flagged_any` — **유형 무관**: 무엇이든 하나라도 걸렸다(정답 유형이 아니어도). 인코더 실험 규약 G1 의 「탐지」가 이 뜻이다.
         ★ **인코더 판의 채택 관문은 이 수다**(D-324 결정 4 · 규약 2판 G1). 🚨 틀린 유형으로 걸린 것도 센다 —
            시스템 보고(D-324 결정 5)의 탐지는 유형 적중이고 이 수가 아니다. 둘을 섞어 읽지 않는다 (D-324 보충 10-11)
    · `lawful` — 적법 문장에 인코더 후보가 선 수. 칸은 `lawful_report` 와 같다(음성 L · 주장없음 D · D-301).
    🆕 2026-10-11 (D-326 보충 12) — **옮긴 후보(`enc_moved`)는 골든 `전제` 가 그 옮김의 전제(`건기식_비인정`)인 행에서만 센다.**
       그 행의 정답(거짓_과장 · [별표 1] 4.나)은 「인정 없는 건강기능식품일 때」의 답이고 옮긴 후보가 바로 그 답이다 — 인코더가
       기준 전제(식품)로 배우면 이 행에 `건강기능식품_오인` 을 내고 그래프가 옮긴다. 안 세면 맞는 답이 빗나감으로 찍힌다.
       ⛔ 전제가 다르거나 없는 행에서는 세지 않는다 — 정답이 마침 거짓_과장인 행이 건강기능식품 오인 신호로 맞은 것처럼 세어진다
          (dev 무조건부에서 옮긴 40 행 중 5 행 · 원장 10-10 ⑫). 유형 무관(`flagged_any`)에도 같은 규칙이다.
    """
    done = [(r, p) for r, p in zip(rows, preds, strict=True) if p.get("encoded")]
    if not done:
        return {"rows": 0}
    ids = {id(r) for r, _ in done}
    pos = det = det_enc = any_fired = 0
    for r, p in sc:
        if id(r) not in ids:
            continue
        pt = set(p["types"]) | set(p.get("candidates", ()))
        pe = _with_encoder(r, p)
        tt = truth_types(r, pe)
        if not tt:
            continue
        pos += 1
        det += bool(pt & tt)
        det_enc += bool(pe & tt)
        any_fired += bool(pe)
    fired: dict[str, bool] = {}
    for r, p in done:
        fired[r["text"]] = fired.get(r["text"], False) or bool(p["enc_candidates"])
    return {
        "rows": len(done),
        "positive": pos,
        "detected": det,
        "detected_with_encoder": det_enc,
        "flagged_any": any_fired,
        "lawful": lawful_report([r for r, _ in done], lambda t: fired.get(t, False)),
        "truncated_sents": sum(p.get("enc_truncated", 0) for _, p in done),
    }


def summarize(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """행 · 예측 → 수. 🔴 순수 함수 — 게이트가 대역 예측으로 잰다."""
    assert len(rows) == len(preds)
    n = len(rows)
    out: dict[str, Any] = {"rows": n}
    out["outcome"] = dict(collections.Counter(p["outcome"] for p in preds))
    out["verdict"] = dict(collections.Counter(v for p in preds for v in p["verdicts"]))
    out["class"] = dict(collections.Counter(p["class"] for p in preds))
    # 보류율 — 사유별(행 단위 · 한 행에 사유가 여럿이면 각각 센다) · 「위험도 없음」은 문장이 전부 확정인데 종착이 보류인 행
    held = [p for p in preds if p["outcome"] == "hold"]
    reasons: collections.Counter = collections.Counter()
    for p in held:
        if p["hold_reasons"]:
            reasons.update(p["hold_reasons"])
        elif p.get("not_claim_only"):
            # 🆕 2026-10-15 (D-348 보충 1 · D-319 결정 2) — 판정 대상 아님만 있는 행 · 품목 미확정이라 맨 위 통과를 내지 않았다
            reasons["판정대상아님·품목미확정(D-319 ②)"] += 1
        elif p["committed"]:
            # 🔄 2026-10-02 (W5) — 위험도가 붙은 뒤의 보류는 다른 까닭이다: 종착의 재료가 없다 (`app/graph.py` 종착).
            #    🔄 2026-10-06 — 증명서 조립기는 섰다(D-320). 여기 남는 것은 사유 문안이 없는 조합과 실증 분기가 없는 지시다
            reasons["종착재료없음(문안)" if p["risked"] else "하한없음(W5)"] += 1
        elif "unjudged" in p["verdicts"]:
            reasons["미판정"] += 1
        else:
            reasons["근거없음"] += 1
    # 🔴 2026-10-15 — 행이 없으면 0.0 이 아니라 「잰 것 없음」(None) — 0 % 로 찍히면 잰 것처럼 보인다 (D-220 · selective risk 와 같다)
    out["hold_rate"] = len(held) / n if n else None
    out["hold_reasons"] = dict(reasons)
    # 조건별 대응표 (D-275)
    table: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r, p in zip(rows, preds, strict=True):
        table[r.get("조건") or "-"][p["class"]] += 1
    out["by_condition"] = {k: dict(v) for k, v in sorted(table.items())}
    # 유형 · 호 — 채점 행만 (M · D 는 빼고 뺀 수를 보인다 · eval_rule 과 같다)
    gold_t, tp_t, fp_t = collections.Counter(), collections.Counter(), collections.Counter()
    gold_h, tp_h, fp_h = collections.Counter(), collections.Counter(), collections.Counter()
    committed = errors = 0
    sc = [(r, p) for r, p in zip(rows, preds, strict=True) if scored(r)]
    for r, p in sc:
        pt, ph = set(p["types"]) & TYPE_CLASSES, set(p["ho"])
        #: 🔴 2026-10-15 — 「틀렸나」는 **예측한 유형 전부**로 본다. 유형 표(P/R/F1)는 채점 8 종만 세지만, 그래프가 8 종 밖 유형
        #:    (기능성화장품_오인 · 추천_보증_뒷광고 · 실증책임_위반)을 확정하면 종전에는 `pt` 가 비어 「맞음」으로 셌다 —
        #:    같은 행을 `lawful_report` 는 오탐으로 센다(두 수가 한 행에 다른 말). 판정기 B(`eval_rule.report`)도 거르지 않는다 (D-99)
        p_all = set(p["types"])
        tt, th = truth_types(r, pt), truth_ho(r, ph)
        for t in tt:
            gold_t[t] += 1
            tp_t[t] += t in pt
        for t in pt - tt:
            fp_t[t] += 1
        laws = {statute.parse(c)[0] for c in th}
        for c in th:
            gold_h[c] += 1
            tp_h[c] += c in ph
        for c in ph - th:
            if (
                not th or statute.parse(c)[0] in laws
            ):  # 오탐은 정답의 법 안에서만 (eval_rule.ho_scores 와 같다)
                fp_h[c] += 1
        if p["committed"]:
            committed += 1
            wrong = (not tt and p_all) or (tt and not (p_all & tt))
            errors += bool(wrong)
    out["scored_rows"] = len(sc)
    out["unscored_rows"] = n - len(sc)
    out["types"] = {t: (gold_t[t], tp_t[t], fp_t[t]) for t in sorted(set(gold_t) | set(fp_t))}
    out["ho"] = {c: (gold_h[c], tp_h[c], fp_h[c]) for c in sorted(set(gold_h) | set(fp_h))}
    out["macro"] = macro_table(out["types"])
    # 🆕 2026-10-02 (D-311 · 판정 10-02 보고 규칙) — **탐지 재현율**: 위반 행 중 확정 유형 ∪ 보류 유형 후보가 정답과 겹치는 비율.
    #    ★ 확정 재현율과 **나란히만** 싣는다 — 탐지는 판정이 아니다(보류는 통과가 아니지만 위반 확정도 아니다 · D-127).
    #    재측정 전에 정했다(D-175) — 이 수에 맞춰 사전 자격을 고르지 않는다
    pos = det = conf_hit = 0
    for r, p in sc:
        pt = set(p["types"])
        tt = truth_types(r, pt | set(p.get("candidates", ())))
        if not tt:
            continue
        pos += 1
        conf_hit += bool(pt & tt)
        det += bool((pt | set(p.get("candidates", ()))) & tt)
    out["detect"] = {"positive": pos, "confirmed": conf_hit, "detected": det}
    out["encoder"] = encoder_report(rows, preds, sc)
    out["detect_types"] = detect_by_type(sc)
    out["coverage"] = committed / len(sc) if sc else None
    out["selective_risk"] = errors / committed if committed else None
    out["committed"] = committed
    # 적법 문장 (D-301) — 「울림」= 위반을 확정한 문장이 있다
    flag = {id(r): p["class"] == "확정위반" for r, p in zip(rows, preds, strict=True)}
    by_text: dict[str, bool] = {}
    for r in rows:
        by_text[r["text"]] = by_text.get(r["text"], False) or flag[id(r)]
    out["lawful"] = lawful_report(rows, lambda t: by_text.get(t, False))
    out["lawful_rows_seen"] = sum(1 for r in rows if lawful_kind(r))
    out["branch"] = branch_report(rows, preds)
    out["branch_encoder"] = branch_encoder_report(rows, preds)
    out["combo"] = combo_report(rows, preds)
    out["reason"] = reason_report(rows, preds)
    out["recorded"] = recorded_report(rows, preds)
    out["encoder_risk"] = encoder_risk_report(rows, preds)
    out["contract_errors"] = sum(1 for p in preds if p.get("contract_error"))
    out["fact_branch_rows"] = sum(1 for p in preds if p.get("fact_branch"))
    out["enc_choice_rows"] = sum(1 for p in preds if p.get("enc_choice"))
    out["conditional"] = conditional_report(rows, preds)
    #: 🆕 2026-10-21 (D-348 보충 35 결정 1) — 불변식이 깨진 행(운영은 바로잡았다 · 0 이어야 한다 · 봉인 조건)
    out["invariant_rows"] = sum(1 for p in preds if p.get("invariant"))
    #: 🆕 2026-10-21 (D-348 보충 38 결정 1 · #3 (나)) **틀린 확정 행** — 위반을 확정했는데 라벨에 위반이 없거나 유형이 하나도 안 겹친다(채점 밖 M · D 포함).
    #:    무조건부에서는 「품목을 모르면 확정하지 않는다」(보충 8 · 31)가 새지 않았는지 보는 그물이다 — **0 이어야 한다(봉인 조건)**
    out["wrong_confirm_ids"] = [
        r["id"]
        for r, p in zip(rows, preds, strict=True)
        if p["class"] == "확정위반" and not (set(p["types"]) & truth_types(r, set(p["types"])))
    ]
    #: 🆕 2026-10-21 (D-348 보충 36 결정 4) — 보류 종류(행 단위 · 한 행에 종류가 여럿이면 각각 센다) × 라벨 조건
    kinds: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r, p in zip(rows, preds, strict=True):
        for k in p.get("hold_kinds", ()):
            kinds[k][r.get("조건") or "-"] += 1
    out["hold_kinds"] = {k: dict(sorted(v.items())) for k, v in sorted(kinds.items())}
    #: 🆕 2026-10-21 (D-348 보충 35 결정 2) — 답 경로(`--answers` 로 잰 행만)
    if any("answer_path" in p for p in preds):
        out["answers"] = answer_report(rows, preds)
    return out


def answer_report(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """답 경로 채점 (🆕 2026-10-21 · D-348 보충 35 결정 2 · 인계 10-21 클론B §1 #2 채점표 초안) — 질문이 선 행만 · 라벨 조건별.

    ★ 칸(조건 → 뜻):
       · A · B(위반) — 「아니오」에 골든 유형 확정 = **도달**(답하면 맞힌다) · 「예」에 그 유형 확정 = **답 미반영**
       · C(답 없이 위반) — 질문이 선 것 자체를 센다(D-61 · 묻지 않고 확정할 자리였나의 후보)
       · D(적법) — 「예」에 위반 확정 = **틀림** · 「아니오」에 위반 확정 = **답에 달린 오탐**(사용자가 「없다」고 하면 위반으로 나간다)
       · M · L · 그 밖 — 수만(종착 분포)
       · 이어 묻기 상한 뒤에도 질문이 남은 행 — 따로 센다 · 도달로 세지 않는다
       · 🆕 이미 답한 질문이 다시 선 행(`reasked` · 그래프 결함) — 따로 센다 · 도달로 세지 않는다 · 0 이어야 한다
    🚨 「아니오 = 골든 위반 라벨」은 D-59 의 실증형 정의에 기댄다(사건마다 실증이 없었는지는 보지 않았다 · 인계 10-21 §4).
    🚨 보고 지표다 — 게이트 아님 · 판정은 이 수를 읽지 않는다. 계약 오류 행은 따로 센다(0 이어야 한다).
    """
    out: dict[str, Any] = {
        "rows": 0,
        "by_condition": {},
        "left": 0,
        "reasked": 0,
        "contract_errors": 0,
    }
    tab: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r, p in zip(rows, preds, strict=True):
        ap_ = p.get("answer_path")
        if not ap_:
            continue
        out["rows"] += 1
        yes, no = ap_[Answer.예.value], ap_[Answer.아니오.value]
        out["contract_errors"] += bool(yes.get("contract_error")) + bool(no.get("contract_error"))
        cond = r.get("조건") or "-"
        c = tab[cond]
        c["질문"] += 1
        left = yes["left"] or no["left"]
        if left:
            out["left"] += 1
            c["남음"] += 1
        # 종전 결과 파일(이 칸 전)은 0 으로 읽는다
        again = yes.get("reasked", 0) or no.get("reasked", 0)
        if again:
            out["reasked"] += 1
            c["재질문"] += 1
        tt = truth_types(r, set(no["types"]) | set(yes["types"]))
        if cond in ("A", "B"):
            if not left and not again and tt & set(no["types"]):
                c["도달"] += 1
            if tt & set(yes["types"]):
                c["답미반영"] += 1
        elif cond == "D":
            c["예에위반"] += yes["class"] == "확정위반"
            c["아니오에위반"] += no["class"] == "확정위반"
        for a, x in ((Answer.예.value, yes), (Answer.아니오.value, no)):
            c[f"{a}:{x['class']}"] += 1
    out["by_condition"] = {k: dict(v) for k, v in sorted(tab.items())}
    return out


def conditional_report(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """조건부 위반 (🆕 2026-10-16 · D-348 보충 4 결정 2) — 「답 없음 · 거짓」 분기의 판정을 골든과 맞댄다.

    ★ 골든의 위반 라벨은 그 사건에서 사실이 거짓 · 실증을 못 했다는 전제다 — 조건부 위반은 그 분기에서 위반이므로 유형이 맞으면 맞힌 것이다.
       확정 재현율과 **나란히** 싣는다(`확정 ∪ 조건부`) — 확정 재현율을 대신하지 않는다.
    🚨 적법 행의 조건부 위반은 따로 센다 — 답하면 풀리지만 묻는 것 자체가 사용자 부담이다(오탐의 다른 모양).
    """
    sc = [(r, p) for r, p in zip(rows, preds, strict=True) if scored(r)]
    pos = conf_hit = cond_hit = either = 0
    for r, p in sc:
        pt, ct = set(p["types"]), set(p.get("cond_types", ()))
        tt = truth_types(r, pt | ct)
        if not tt:
            continue
        pos += 1
        conf_hit += bool(pt & tt)
        cond_hit += bool(p["class"] == "조건부위반" and ct & tt)
        either += bool((pt | (ct if p["class"] == "조건부위반" else set())) & tt)
    lawful = [p for r, p in zip(rows, preds, strict=True) if lawful_kind(r)]
    return {
        "rows": sum(1 for p in preds if p["class"] == "조건부위반"),
        "positive": pos,
        "confirmed": conf_hit,
        "conditional": cond_hit,
        "either": either,
        "lawful_rows": len(lawful),
        "lawful_conditional": sum(1 for p in lawful if p["class"] == "조건부위반"),
    }


def _checked(state: dict[str, Any]) -> dict[str, Any]:
    """그래프 상태가 **응답 계약**을 지나는가 — 못 지나면 그 까닭을 상태에 싣는다(🆕 2026-10-16 · D-220).

    ⛔ 종전에는 평가가 응답을 만들지 않아, 앱에서 오류로 끝날 행(기록 ≥ 분기 위반 등)이 eval 에서는 정상으로 세어졌다
       (10-16 인코더 하한 결함 · D-348 보충 2 결정 10). 판정 수는 그대로 세고 오류 행 수를 따로 낸다 — 0 이 아니면 보고 맨 위에 적는다.
    """
    try:
        g.to_response(state)  # type: ignore[arg-type]
    except ValueError as e:  # pydantic ValidationError 도 ValueError 다
        return {**state, "_contract_error": str(e).splitlines()[0][:200] + " · " + str(e)[-200:]}
    return state


def encoder_risk_report(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """인코더 하한이 붙은 행 (🆕 2026-10-16 · D-348 보충 1 결정 3 · 보충 2 결정 5) — 위반 · 적법 · 모호별.

    ★ 지표 = **적법에 하한이 붙는 비율** · 분모 = **적법 행 전체**(조건 D · L · 보충 2 결정 5) · Wilson 95% 상한 ≤ 10% `[임의]`(D-347 결정 7 (ㄱ)
       과 같은 예산)이면 그 가드 세기를 쓴다. 🔴 적법 행이 없으면 「잰 것 없음」(None) — 0 % 로 쓰지 않는다 (D-220).
    🚨 진단이다 — 판정 · 종착은 이 칸을 읽지 않는다. 인코더가 돈 행만 센다(안 돈 행은 하한이 붙을 수 없다).
    """
    pos = law = m = pos_n = law_n = m_n = 0
    for r, p in zip(rows, preds, strict=True):
        if not p.get("encoded"):
            continue
        cond = r.get("조건") or ""
        hit = bool(p.get("enc_risk"))
        if cond in ("A", "B", "C"):
            pos_n += 1
            pos += hit
        elif cond in ("D", "L"):
            law_n += 1
            law += hit
        elif cond == "M":
            m_n += 1
            m += hit
    ci = wilson(law, law_n)
    return {
        "violation": [pos, pos_n],
        "lawful": [law, law_n],
        "ambiguous": [m, m_n],
        "lawful_upper": ci[1] if ci else None,
    }


def conditional_rows(rows: list[dict]) -> list[dict]:
    """조건부 평가 행 — **전제나 품목을 아는 행**. 🔴 칸 자체가 없는 판이면 멈춘다(재동결 전 골든 · D-220).

    🔄 2026-10-10 — 제품 정보는 아는 만큼만 넘긴다(`product_of`): 골든 `전제` 가 있으면 그 전제의 품목 · 없으면 `품목`.
       승인 문구 규칙 행이 돌아온다 — `전제` 가 `식품` 이라 「일반식품이 이 문구를 쓰면」으로 넘어간다(종전에는 뺐다).
    """
    if rows and not all("품목" in r for r in rows):
        raise SystemExit(
            "🔴 골든에 `품목` 칸이 없다 — 재동결 전 판이다(D-306). 조건부 평가를 못 한다\n"
            "  먼저(정본): uv run python launcher.py golden --write"
        )
    if rows and not all("전제" in r for r in rows):
        raise SystemExit(
            "🔴 골든에 `전제` 칸이 없다 — 2026-10-10 재동결 전 판이다. 조건부 평가를 못 한다\n"
            "  먼저(정본): uv run python launcher.py golden --write · (사본): data-sync"
        )
    # 🔴 승인 문구 규칙 행의 `품목`(건기식)은 원천이다 — 그 행은 `전제`(식품)로만 든다. `전제` 가 빈 승인 문구 행이 있으면
    #    품목으로 넘기지 않는다(그래프는 건강기능식품으로 보고 4.나를 내고 채점은 3호를 기대한다 · 원장 10-03 ㊿-40)
    return [
        r
        for r in rows
        if r["전제"] or (r["품목"] and r.get("판독") != APPROVED_READING) or general_row(r)
    ]


#: 🆕 2026-10-20 (D-348 보충 32 · 측정 기준 (ㄴ)) 일반상품으로 채점하는 행의 근거 법 — 표시광고법(법률 ID · `app.sanction.SANCTION_LAW`)
GENERAL_LAW = SANCTION_LAW["표시광고법"]
#: 🆕 2026-10-21 (D-348 보충 38 결정 2) 근거가 빈 행도 일반상품으로 드는 원천 — 공정위 의결서(표시광고법 사건) `[문헌]` 원천 정의 `data_sources.yaml`
GENERAL_SOURCE = "ftc_decisions_body"


def general_row(r: dict) -> bool:
    """**일반상품 규칙** — 골든 `전제` · `품목` 이 비었고 근거 조문이 **모두 표시광고법**인 행 → 일반상품 전제로 채점한다 (🆕 2026-10-20 · 보충 32).

    ★ 까닭 — 품목을 고른 뒤의 성적(조건부)이 품목 빈칸 행을 통째로 뺐다(확장 dev 의 공정위 의결서 404 행이 조건부 0 행).
       근거가 표시광고법뿐인 라벨은 「표시광고법 위반」만 말한다 — 표시광고법은 품목과 무관하게 걸리므로 일반상품 전제
       (표시광고법만 본다 · `premise.CRITERIA`)로 채점해도 라벨의 범위와 맞다.
    🚨 근거가 빈 행(위반 없음 라벨)은 이 규칙에 들지 않는다 — 「근거 법이 표시광고법뿐」을 말할 근거가 없다(D-220).
       🔄 2026-10-21 (D-348 보충 38 결정 2 · 인계 10-21 클론B §1 #12 (가)) — **예외 하나: 공정위 의결서 원천**의 위반 없음 행
       (근거 · 근거 후보 · 라벨이 모두 비었다)은 일반상품으로 든다 — 원천 자체가 표시광고법 사건이다(공정위 의결서 · `GENERAL_SOURCE`).
       일반상품 조건부에 적법 표본이 0 행이던 자리를 메운다(dev 15 행 · 모두 조건 D · 원장 10-21(A) ⑦).
    ⛔ 근거 조문 글자는 `<법 ID>:<조문>` 꼴이다(골든 `근거`) — 꼴이 다르면 들지 않는다.
    """
    if r.get("전제") or r.get("품목"):
        return False
    basis = r.get("근거") or []
    if basis:
        return all(str(x).split(":", 1)[0] == GENERAL_LAW for x in basis)
    return (
        r.get("provenance") == GENERAL_SOURCE
        and not r.get("근거_후보")
        and not r.get("labels")
        and "근거" in r
    )


def product_of(r: dict, conditional: bool, *, category_only: bool = False) -> ProductContext:
    """행의 제품 정보 — 무조건부면 빈 것(세 법) · 조건부면 **아는 만큼**: 골든 `전제` 가 있으면 그 전제의 것 · 없으면 `품목`.

    🚨 채점은 여전히 **기록되는 판정**으로 한다(D-263 결정 1 「게이트 수치도 이것으로 잰다」).
    🔄 2026-10-21 (D-348 보충 33 결정 5 · 보충 34 결정 1) — 골든 `전제` 가 있으면 **그 전제를 고른 판정**이다(`pm.product_of` 가 전제를 싣는다 ·
       그래프가 그 전제 하나로 판정 · 분기 없음). 종전에는 품목만 실려 하위 전제(인정 여부 · 기능성 표시 여부)가 답 대기로 남았다.
       ⚠️ 그래서 조건부 모드의 분기 지표(`branch_report` · `branch_encoder_report`)는 하위 전제가 둘인 품목의 `전제` 행에서 0 이 된다 —
       그 전제의 판정이 기록 쪽에 있다. 무조건부 모드의 분기 지표는 그대로다(전제를 넘기지 않는다).
    🆕 2026-10-21 (D-348 보충 35 결정 2) — `category_only` 면 골든 `전제` 의 **품목만** 넘긴다(전제를 고르기 전 · 분기 미리보기 쪽).
       경로 동치 대조의 짝이다 — 「전제를 고른 판정의 기록」 = 「품목만 넘긴 판정의 그 전제 분기」(`scripts/eval_diff.py equiv`).
    """
    if not conditional:
        return ProductContext()
    if r.get("전제"):
        p = pm.product_of(Premise(r["전제"]))
        return ProductContext(category=p.category) if category_only else p
    if general_row(r):
        return ProductContext(category=Category.일반상품)  # 🆕 2026-10-20 (보충 32) 일반상품 규칙
    return ProductContext(category=Category(r["품목"]))


def _print_answers(a: dict[str, Any]) -> None:
    """답 경로 표 (D-348 보충 35 결정 2) — 조건별 · 95% 구간은 도달 · 오탐 칸만."""
    print(
        f"\n  답 경로 (D-348 보충 35 · 질문이 선 행 {a['rows']} · 모두 예 / 모두 아니오 · 이어 묻기 {ANSWER_ROUNDS}회까지 · 보고 지표)"
    )
    for k, c in a["by_condition"].items():
        n = c.get("질문", 0)
        bits = [f"질문 {n}"]
        if k in ("A", "B"):
            bits += [
                f"도달 {c.get('도달', 0)} {_ci(c.get('도달', 0), n)}",
                f"답 미반영 {c.get('답미반영', 0)}",
            ]
        if k == "D":
            bits += [
                f"예에 위반(틀림) {c.get('예에위반', 0)}",
                f"아니오에 위반(답에 달린 오탐) {c.get('아니오에위반', 0)} {_ci(c.get('아니오에위반', 0), n)}",
            ]
        if k == "C":
            bits += ["질문이 선 C 행 = D-61 후보(묻지 않고 확정할 자리였나)"]
        if c.get("남음"):
            bits += [f"상한 뒤에도 질문 남음 {c['남음']}(도달로 세지 않음)"]
        if c.get("재질문"):
            bits += [f"🔴 답한 질문이 다시 섬 {c['재질문']}(도달로 세지 않음)"]
        print(f"    {k:>2}  " + " · ".join(bits))
        for ans in (Answer.예.value, Answer.아니오.value):
            dist = {x.split(":", 1)[1]: v for x, v in c.items() if x.startswith(ans + ":")}
            print(f"        {ans:4} → {dist}")
    if a["left"]:
        print(f"    상한 뒤에도 질문이 남은 행 {a['left']}")
    if a.get("reasked"):
        print(
            f"    🔴 이미 답한 질문이 다시 선 행 {a['reasked']} — 그래프 결함(0 이어야 한다 · 답 경로 결과를 그대로 읽지 않는다)"
        )
    if a["contract_errors"]:
        print(f"    🔴 답 경로에서 응답 계약을 지나지 못한 판정 {a['contract_errors']}")


def _pct(x: float | None) -> str:
    """비율 글자 — 잰 것이 없으면(`None`) 「-」. 0 % 와 「안 쟀다」를 가른다 (D-220)."""
    return "-" if x is None else f"{x:.1%}"


def report(s: dict[str, Any], conditional: bool = False, *, dev: bool = False) -> None:
    print(
        "  [조건부 — 전제나 품목을 아는 행 · 골든 `전제` → `품목`]"
        if conditional
        else "  [무조건부 — 품목 미확정 · 세 법]"
    )
    print(
        f"그래프 평가 — {'dev(검증 묶음)' if dev else '평가셋'} {s['rows']}행 (채점 {s['scored_rows']} · 채점 밖 M · D {s['unscored_rows']})"
    )
    print(f"  종착   {s['outcome']}")
    print(f"  문장   {s['verdict']}")
    print(f"  행     {s['class']}")
    print(f"  보류율 {_pct(s['hold_rate'])} — 사유별 {s['hold_reasons']}")
    print(
        "  ⓘ 봉인 보고의 대표 지표(D-348 보충 37 결정 8) — "
        + (
            " / ".join(REPRESENTATIVE)
            if conditional
            else "무조건부 수는 진단이다 · 대표는 조건부 · 답 경로 · 경로 동치 · 불변식"
        )
    )
    print("\n  조건별 대응표 (D-275 · 행 수)")
    for k, v in s["by_condition"].items():
        print(f"    {k:>2}  " + "  ".join(f"{c} {v.get(c, 0)}" for c in CLASSES))
    for name, tab in (("유형", s["types"]), ("호 (정본 · D-282)", s["ho"])):
        print(f"\n  {name:26} {'정답':>5} {'P':>7} {'R':>7} {'F1':>7}  R 95% 구간")
        for k, (gold, tp, fp) in tab.items():
            p, r, f = _prf(gold, tp, fp)
            mark = "  🔴 측정 불가 (D-40)" if gold < MIN_MEASURABLE else ""
            if gold == 0:
                mark = f"  🚨 정답 0인데 오탐 {fp}건"
            print(f"  {k:26} {gold:>5} {p:>7.3f} {r:>7.3f} {f:>7.3f}  {_ci(tp, gold):>16}{mark}")
    for name, m in (s.get("macro") or {}).items():
        mac = "-" if m["macro"] is None else " · ".join(f"{x:.3f}" for x in m["macro"])
        mic = " · ".join(f"{x:.3f}" for x in m["micro"])
        print(
            f"\n  {name} (D-321 결정 4) — macro P · R · F1 {mac} (측정 가능 {len(m['measurable'])}종) · "
            f"micro P · R · F1 {mic} · 측정 불가 {', '.join(m['unmeasurable']) or '없음'}"
        )
    sr = s["selective_risk"]
    err = round(sr * s["committed"]) if sr is not None else 0
    sr_mark = (
        "" if s["committed"] >= MIN_MEASURABLE else "  🔴 측정 불가 (판정을 내린 행 n<30 · D-40)"
    )
    print(
        f"\n  selective risk {('-' if sr is None else f'{sr:.1%}')} {_ci(err, s['committed'])} · coverage {_pct(s['coverage'])} "
        f"(판정을 내린 행 {s['committed']} / 채점 {s['scored_rows']}){sr_mark}"
    )
    d = s.get("detect") or {}
    if d.get("positive"):
        print(
            f"\n  위반 행 {d['positive']} — 확정 재현율 {d['confirmed'] / d['positive']:.1%} {_ci(d['confirmed'], d['positive'])} · "
            f"탐지 재현율(확정 ∪ 보류 유형 후보) {d['detected'] / d['positive']:.1%} {_ci(d['detected'], d['positive'])}"
            "  (D-311 · 탐지는 판정이 아니다 · 괄호는 95% 구간)"
        )
    e = s.get("encoder") or {}
    if e.get("rows"):
        print(
            f"\n  [인코더 후보 · 응답의 encoder_candidates] 인코더가 돈 행 {e['rows']} — "
            "🚨 판정(확정 · 보류)은 인코더를 읽지 않는다. 아래는 후보까지 합친 탐지다 (D-323)"
        )
        if e["positive"]:
            print(
                f"    위반 행 {e['positive']} — 탐지 재현율 {e['detected'] / e['positive']:.1%} → "
                f"인코더 후보까지 {e['detected_with_encoder'] / e['positive']:.1%} (유형 적중)"
                f" · 무엇이든 걸린 행 {e['flagged_any'] / e['positive']:.1%}"
                " (유형 무관 · 규약 G1 — 인코더 채택 관문의 수 · 시스템 보고의 탐지가 아니다 · D-324 결정 4)"
            )
        for kind, (n, hit) in e["lawful"].items():
            if n:
                mark = "" if n >= MIN_MEASURABLE else "  ← 측정 불가 (n<30 · D-40)"
                print(
                    f"    적법 · {kind} {n} 행 중 인코더 후보가 선 행 {hit} ({hit / n:.1%}){mark}"
                )
        if e["truncated_sents"]:
            print(
                f"    🔴 토큰 상한을 넘어 뒤가 잘린 문장 {e['truncated_sents']} — 잘린 부분은 보지 않았다"
            )
    cb = s.get("combo") or {}
    if cb:
        print(
            "\n  조합 판정 칸 (D-340 · 기록 판정 · 인코더가 돈 행 · 진단) — 행 · 위반(A·B·C) · 적법(D·L) · 모호(M)"
        )
        for k, (n, pos, law, m) in cb.items():
            print(f"    {k:28} {n:>5} · {pos:>4} / {law:>3} · M {m}")
    if s.get("hold_kinds"):
        print("\n  보류 종류 (D-348 보충 36 · 행 단위 · 라벨 조건별 · 통과가 아니다)")
        for k, v in s["hold_kinds"].items():
            print(
                f"    {k:16} {sum(v.values()):>5}  " + " · ".join(f"{c} {n}" for c, n in v.items())
            )
    if not conditional:
        bad = s.get("wrong_confirm_ids") or []
        print(
            f"\n  {'✅' if not bad else '🔴'} 그물 — 무조건부 틀린 확정 {len(bad)} 행(0 이어야 한다 · 봉인 조건 · D-348 보충 38 결정 1)"
            + (f" · {bad[:5]}" if bad else "")
        )
    if s.get("invariant_rows"):
        print(
            f"\n  🔴 불변식이 깨진 행 {s['invariant_rows']} — 운영은 전제 보류로 바로잡았다 · 0 이어야 한다(행별 `invariant` · D-348 보충 35)"
        )
    if s.get("answers"):
        _print_answers(s["answers"])
    if s.get("contract_errors"):
        print(
            f"\n  🔴 응답 계약을 지나지 못한 행 {s['contract_errors']} — 앱이라면 그 요청은 오류로 끝난다 (행별 `contract_error`)"
        )
    if s.get("fact_branch_rows"):
        print(
            f"\n  사실 확인 분기가 달린 행 {s['fact_branch_rows']} (D-348 보충 3 · 기록은 보류 · 선택지)"
        )
    if s.get("enc_choice_rows"):
        print(
            f"\n  인코더 쪽 보류 + 분기가 달린 행 {s['enc_choice_rows']} (D-348 보충 5 · 답 없이 확정하지 않는다 · 분류는 보류)"
        )
    cd = s.get("conditional") or {}
    if cd.get("rows"):
        print(
            f"\n  조건부 위반 행 {cd['rows']} (D-348 보충 4 · 답하면 확정) — 위반 행 {cd['positive']} 중 "
            f"확정 {cd['confirmed']} · 조건부 {cd['conditional']} · 확정 ∪ 조건부 {cd['either']} · "
            f"적법 {cd['lawful_rows']} 중 조건부 {cd['lawful_conditional']}"
        )
    er = s.get("encoder_risk") or {}
    if er:
        (vk, vn), (lk, ln), (mk, mn) = er["violation"], er["lawful"], er["ambiguous"]
        up = er["lawful_upper"]
        print(
            "\n  인코더 하한 (D-348 보충 2 · 기록 판정 · 보류 문장 · 판정 아님) — 하한이 붙은 행 / 그 조건의 행"
            f"\n    위반(A·B·C) {vk} / {vn} · 적법(D·L) {lk} / {ln}"
            + (f" ({lk / ln:.1%} · 95% 상한 {up:.1%})" if ln else " (잰 것 없음)")
            + f" · 모호(M) {mk} / {mn}"
            + ("" if ln >= MIN_MEASURABLE else "  ← 적법 측정 불가 (n<30 · D-40)")
            + "\n    ⓘ 가드 세기는 적법 95% 상한 ≤ 10% `[임의]` 로 고른다 (보충 1 결정 3) · 분모는 적법 행 전체 (보충 2 결정 5)"
        )
    be = s.get("branch_encoder") or {}
    for name, (pos, hit, fired) in be.items():
        print(
            f"    분기 인코더 · 전제 {name} — 위반 행 {pos} · 유형 맞음 {hit}({hit / pos:.1%}) · 무엇이든 {fired}"
            + ("" if pos >= MIN_MEASURABLE else "  ← 측정 불가 (n<30 · D-40)")
        )
    dt = s.get("detect_types") or {}
    if dt:
        print(
            f"\n  {'유형별 탐지 (D-321 결정 6)':24} {'정답':>5} {'확정':>7} {'사전 후보까지':>9} {'인코더 후보까지':>10}"
        )
        for k, (gold, conf, det, egold, edet) in dt.items():
            mark = "  🔴 측정 불가 (D-40)" if gold < MIN_MEASURABLE else ""
            enc_col = f"{edet / egold:>10.1%}" if egold else f"{'-':>10}"
            if egold and egold != gold:
                enc_col += f" (인코더가 돈 정답 {egold})"
            print(f"  {k:26} {gold:>5} {conf / gold:>7.1%} {det / gold:>9.1%} {enc_col}{mark}")
        print(
            "     ⓘ (행 · 유형) 단위다 — 한 행에 유형이 여럿이면 유형마다 세어 정답의 합이 위반 행 수보다 크다."
            " 후보는 판정이 아니고 합격선도 없다 (D-311 보충 · D-322 결정 A)"
        )
    print_lawful(s["lawful"])
    w = s.get("recorded") or {}
    if w.get("rows"):
        print(
            f"\n  보수 기록 (진단 · 대표 지표 아님 · D-348 보충 37 결정 8 · 확정 ∪ 분기 보류에 실린 유형) — 기록이 있는 채점 행 {w['rows']} · "
            f"틀림 {w['wrong']}({w['wrong'] / w['rows']:.1%}) · 위반 행 {w['positive']} 중 기록이 맞은 것 {w['hit']}"
            + (f"({w['hit'] / w['positive']:.1%})" if w["positive"] else "")
            + "  (확정만 센 수와 나란히만 읽는다)"
        )
    q = s.get("reason") or {}
    if q.get("n"):
        print(
            f"\n  불가 사유 (진단 · 게이트 아님) — 확정 위반 ∧ 라벨 조건 A/B/C 인 행 {q['n']} · 글자 일치 {q['exact']}"
            f"({q['exact'] / q['n']:.1%}) · 축 다름(예측 B · 라벨 A) {q['axis_gap']} · 방향 어긋남 {q['wrong']}"
            f"({q['wrong'] / q['n']:.1%} · 그중 식품 3호 {q['wrong_hf']})"
        )
    b = s.get("branch") or {}
    if b.get("rows_with_branches"):
        n = b["positive"]
        print(
            f"\n  분기 (D-319) — 분기가 나온 행 {b['rows_with_branches']} · 정답 품목의 분기를 본 위반 행 {n}"
            + (
                f" · 그 분기의 확정 위반 {b['confirmed']}({b['confirmed'] / n:.1%}) · 유형 맞음 {b['type_hit']} · "
                f"호 맞음 {b['ho_hit']} · 유형 틀림 {b['wrong']} · 조건부 위반 {b.get('conditional', 0)}"
                f"(유형 맞음 {b.get('cond_hit', 0)})"
                if n
                else ""
            )
            + "  (분기는 판정이 아니다 · 정답 전제는 골든 `전제` 칸 — 전제를 모르는 행은 세지 않는다)"
        )
        for name, (pos, conf, hit) in (b.get("by_premise") or {}).items():
            print(
                f"    전제 {name} — 위반 행 {pos} · 그 분기의 확정 위반 {conf}({conf / pos:.1%}) · 유형 맞음 {hit}"
                + ("" if pos >= MIN_MEASURABLE else "  ← 측정 불가 (n<30 · D-40)")
            )
    else:
        print("\n  분기 (D-319) — 없음(기준 문안 미확정 · 또는 전제가 하나뿐인 품목)")
    if not conditional:
        print(
            "\n  ⓘ 조건부(품목을 아는 경우)는 `--conditional` 로 따로 잰다 (D-306 · 기획서 6-3 병기)"
        )
    if dev:
        print(
            "  ⓘ dev(검증 묶음)다 — 판 · 문턱 · 규칙은 여기서 고른다 (D-175). "
            "🚨 학습 분할에서 뗀 행이라 사전이 평가셋보다 잘 울린다 — 사전 쪽 수를 평가셋 수처럼 읽지 않는다.\n"
            "     해설서 수정문구류(적법 · 주장 없음)가 없다 — 「적법 문구를 가르는가」는 dev 로 재지 못한다"
        )
    else:
        print("  🚨 봉인 평가셋이다 — 이 수에 맞춰 규칙 · 문턱을 고르지 않는다 (D-175)")


# ── 실행 ────────────────────────────────────────────────────────────────


def _sha12(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _key(e: Any) -> tuple[str, str | None, tuple[str, ...]]:
    return (e.term, e.violation_type, tuple(e.basis))


def dict_drift(
    db: Iterable[Any], file_rows: Iterable[dict], *, exact: bool = True
) -> dict[str, int]:
    """DB 의 단독판정 사전(`graph.load_dict_entries`) ↔ 사전 파일 — 어긋난 **수**만 (용어는 싣지 않는다 · ND 면제 조건).

    🆕 2026-10-01 (원장 10-01 ⑦) — A 기기 DB 에 동결 09-30 이전 사전이 남아 **봉인 평가 문서의 문구**가 걸렸다.
       ⛔ 평가 도구가 DB 사전의 판을 몰라 그 수가 정본처럼 찍혔다 — 없음 · 낡음이 성공으로 집계됐다 (D-220 · D-174).
    🔴 파일 쪽 변환은 적재기와 **한 함수**(`load_db.dict_row`)다 (D-99) — 「단독판정 항목만」도 그래프의 `SQL_DICT` 와 같은 거름.
    🔄 2026-10-02 (D-311) — `exact=False` 면 **자격 없는 항목**끼리 대조한다(그래프의 `SQL_DICT_WEAK` 와 같은 거름).
    """
    from scripts.load_db import dict_row  # noqa: PLC0415 — 적재기의 변환을 그대로 (D-99)

    want = {}
    for term, law_ref, solo, vt in map(dict_row, file_rows):
        if solo is exact:
            want[term] = (term, vt, tuple(b.strip() for b in law_ref.split(";") if b.strip()))
    have = {e.term: _key(e) for e in db}
    return {
        "db_only": len(have.keys() - want.keys()),
        "file_only": len(want.keys() - have.keys()),
        "changed": sum(have[t] != want[t] for t in have.keys() & want.keys()),
        "file": len(want),
        "db": len(have),
    }


def check_dict(cur: Any, path: pathlib.Path = DICT_FILE) -> dict[str, Any]:
    """DB 사전이 파일과 같아야 돈다 — 🔴 다르면 **멈춘다** (D-220). 같으면 판 표지(sha · 수)를 돌려준다(D-178)."""
    if not path.exists():
        raise SystemExit(f"🔴 {path} 가 없다 — DB 사전과 대조할 기준이 없다 (D-220)")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    d = dict_drift(g.load_dict_entries(cur), rows)
    # 🆕 2026-10-02 (D-311) — 자격 없는 항목도 대조한다(보류 문장의 유형 후보가 다른 판 사전에서 오지 않게)
    w = dict_drift(g.load_weak_entries(cur), rows, exact=False)
    if w["db_only"] or w["file_only"] or w["changed"]:
        d = {k: d[k] + w[k] for k in d}
    if d["db_only"] or d["file_only"] or d["changed"]:
        raise SystemExit(
            f"🔴 DB 사전이 {path} 와 다르다 — DB 에만 {d['db_only']} · 파일에만 {d['file_only']} · "
            f"값이 다름 {d['changed']} (단독판정 · 파일 {d['file']} · DB {d['db']})\n"
            "  이대로 재면 다른 판 사전의 수가 정본처럼 찍힌다(봉인 문서 문구가 걸릴 수 있다 · D-174).\n"
            "  먼저: uv run python launcher.py load"
        )
    return {"dict_sha": _sha12(path), "dict_entries": d["file"]}


def dict_echo(
    rows: list[dict], preds: list[dict[str, Any]], dict_rows: list[dict]
) -> dict[str, Any]:
    """🆕 2026-10-18 (D-348 보충 24 결정 1) **사전 낱말과 글자가 같은 채점 행** — 「목록에서 찾아 맞힌 몫」을 따로 센다.

    ★ 금지 낱말은 법령 · 지침 · 질의응답집에 똑같이 나온다 — 같은 글자는 누수가 아니라(누수는 빌드의 출처 게이트 · `tests/test_dictionary_leak.py`)
       일반화와 다른 몫이다. D-174 사고(누수 포함 F1 0.161 → 0.027)처럼 몇 행이 점수를 끌 수 있어 **나란히** 적는다.
    🔴 같은 글자 = 정규화한 평가 문장 전체가 사전 항목 하나와 같다(`tests/test_split.py` 와 같은 규칙 · D-99). 채점 행(라벨 있음)만 센다.
    """
    src = {r["term"]: tuple(r.get("출처") or ()) for r in dict_rows}
    hit = [
        (r, p)
        for r, p in zip(rows, preds, strict=True)
        if r.get("labels") and dict_norm(r["text"]) in src
    ]
    by = collections.Counter(" · ".join(src[dict_norm(r["text"])]) for r, _ in hit)
    right = sum(1 for r, p in hit if set(map(str, r["labels"])) & set(p.get("types") or ()))
    return {"rows": len(hit), "type_hit": right, "by_source": dict(by)}


def check_dev(rows: list[dict], model_dir: pathlib.Path | None) -> dict[str, Any]:
    """dev 행이 **그 인코더가 학습에서 뺀 dev 와 같은지** — 모델 폴더의 `label_scheme.json`(`dev_sha` · `dev_rows`)과 대조한다.

    🔴 **다르면 멈춘다** (D-220 · D-175) — 그 모델은 이 행의 일부를 학습에서 봤다. 그 수는 dev 수치가 아니다.
    🚨 모델 폴더에 dev 지문이 없으면(옛 산출물) 대조할 수 없다 — 멈추지 않고 판 표지에 「미확인」으로 적는다.
       없음을 일치로 세지 않는다. 인코더 없이 재면 대조할 모델이 없다 — 지문만 적는다.
    """
    #: 🆕 2026-10-15 (D-347) — 확장 dev 면 해설서 dev(봉인에서 옮긴 행)를 따로 떼어 따로 대조한다
    guide = [r for r in rows if r["id"].startswith(resplit.PREFIXES)]
    base = [r for r in rows if not r["id"].startswith(resplit.PREFIXES)]
    stamp: dict[str, Any] = {"dev_rows": len(base), "dev_sha": devsplit.sha(r["id"] for r in base)}
    if guide:
        stamp |= {
            "guide_dev_rows": len(guide),
            "guide_dev_sha": devsplit.sha(r["id"] for r in guide),
        }
    if model_dir is None:
        return stamp
    try:
        scheme = json.loads((model_dir / "label_scheme.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"🔴 {model_dir} 의 label_scheme.json 을 읽지 못했다 — {e}") from e
    want = scheme.get("dev_sha")
    if not want:
        return stamp | {"dev_check": "미확인(모델 폴더에 dev 지문 없음)"}
    if (want, scheme.get("dev_rows")) != (stamp["dev_sha"], stamp["dev_rows"]):
        raise SystemExit(
            f"🔴 dev 가 이 모델의 dev 와 다르다 — 여기 {stamp['dev_rows']}행 · {stamp['dev_sha']} / "
            f"모델 {scheme.get('dev_rows')}행 · {want}\n"
            "  이 모델은 이 행의 일부를 학습에서 봤다 — dev 수치로 쓸 수 없다 (D-175).\n"
            "  골든 판이 다르거나 모델이 다른 규칙으로 dev 를 뗐다(`preprocess/devsplit.py` 는 v11 규칙이다)."
        )
    #: 재분할로 학습한 판은 `label_scheme.json` 에 재분할 판 · 지문을 싣는다(D-347 결정 4). 없으면 재분할 전 판이다 —
    #: 그 판은 해설서 dev 를 학습에서 보지 않았다(그 행은 봉인이었다).
    if scheme.get("resplit") is not None:
        if scheme.get("resplit") != resplit.VERSION:
            raise SystemExit(
                f"🔴 이 모델은 재분할 {scheme.get('resplit')!r} 로 학습했다 — 여기 규칙은 {resplit.VERSION!r} (D-347)\n"
                "  다른 배정이면 해설서 dev 의 일부를 학습에서 봤을 수 있다 — dev 수치로 쓸 수 없다 (D-175)."
            )
        if guide and scheme.get("resplit_dev_sha") != stamp["guide_dev_sha"]:
            raise SystemExit(
                f"🔴 해설서 dev 가 이 모델의 것과 다르다 — 여기 {stamp['guide_dev_sha']} / "
                f"모델 {scheme.get('resplit_dev_sha')} (D-347 · D-175)"
            )
        return stamp | {"dev_check": "일치(재분할 판)" if guide else "일치"}
    if guide:
        return stamp | {
            "dev_check": "일치 · 해설서 dev 는 이 판이 학습에서 보지 않은 봉인 몫(재분할 전 판)"
        }
    return stamp | {"dev_check": "일치"}


def use_encoder(model_dir: pathlib.Path | None, *, adopted_only: bool = False) -> dict[str, Any]:
    """인코더를 켠다 — 판 표지(폴더 이름 · 가중치 지문 · 판 지문 · 잠금 상태)를 돌려준다. 안 켜면 빈 표지다.

    🔴 **켰는데 못 올리면 멈춘다** (D-220) — 그래프의 `encode` 는 이 경우 경고만 남기고 규칙 판정으로 간다.
       수를 재는 자리에서 그대로 두면 인코더 없는 수가 인코더 수처럼 찍힌다.
    🆕 2026-10-13 (D-333) — 평가는 **잠금 밖 판도 잰다**(실험은 도구 인자로 · D-205). 대신 판 표지에 잠금 상태
       (`채택` · `되돌림` · `잠금 밖`)와 판 지문을 남긴다 — 문턱만 다른 판의 수가 같은 가중치 지문으로 섞이지 않게(D-178).
    """
    if model_dir is not None:
        os.environ[enc.ENV_MODEL_DIR] = str(model_dir)
    path = enc.configured_dir()
    if path is None:
        if adopted_only:
            raise SystemExit(
                "🔴 봉인 회차는 잠금 채택 판 인코더로만 돈다(D-339 결정 7) — --encoder 나 "
                + enc.ENV_MODEL_DIR
            )
        return {}
    if not adopted_only:
        enc.permit_unlocked()
    try:
        if adopted_only and (m0 := enc.lock_match(path)).status != model_lock.ADOPTED:
            raise SystemExit(
                f"🔴 봉인 회차는 잠금 **채택** 판으로만 돈다(D-339 결정 7) — {path.name} 는 「{m0.status}」"
            )
        scheme = enc.encoder_at(path).scheme
        m = enc.lock_match(path)
        return {
            "encoder": path.name,
            "encoder_sha": enc.weights_sha12(path),
            "encoder_bundle": m.bundle,
            "encoder_lock": m.status + (f" · {m.name}" if m.name else f" — {m.why}"),
            # 상한을 모델 폴더가 실어 줬는지 · 기본값으로 돌았는지 함께 적는다 (D-220)
            "encoder_max_tokens": f"{scheme.max_tokens}"
            + ("" if scheme.max_tokens_from_model else "(기본값)"),
            # 🆕 2026-10-14 (D-336) — 품목 입력 판인가 · 문턱이 몇 벌인가
            "encoder_input": "품목 입력(문장쌍 · 문턱 두 벌)" if scheme.pair else "문장만",
        }
    except enc.EncoderUnavailable as e:
        raise SystemExit(
            f"🔴 인코더를 올리지 못했다 — {e}\n  끄려면 --encoder 와 {enc.ENV_MODEL_DIR} 을 비운다"
        ) from e


def stub_runner() -> Callable[[str, ProductContext], dict[str, Any]]:
    """DB 없이 — 스텁 한 바퀴(`run_review_stub`). 사전을 못 훑어 전부 미판정이다 — 배선만 본다."""
    return lambda text, product: g.run_review_stub(text)[0]


class _InvariantLog(logging.Handler):
    """그래프의 불변식 로거(`app.graph.INVARIANT_LOG`)를 행마다 받아 둔다 (🆕 2026-10-21 · D-348 보충 35 결정 1).

    ★ 운영 · 평가는 불변식 위반을 바로잡고(전제 보류) 로그만 남긴다 — 평가가 그 로그를 행에 싣지 않으면 바로잡은 결함이 수에 묻힌다(D-162).
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.got: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.got.append(record.getMessage())


#: 답 경로의 이어 묻기 상한 — 품목 → 하위 전제 → 사실 → 실증(보충 34 결정 2)에서 문장 쪽은 사실 · 실증 두 겹이라 셋이면 남는다 `[임의]`
#: (인계 10-21 클론B §1 #2 (가′) · 보고 지표 · 게이트 아님 · 셋 뒤에도 질문이 남은 행은 따로 센다)
ANSWER_ROUNDS = 3
#: 답 경로의 두 벌 — 사실 확인 문안은 모두 「예 = 적법 조건을 갖춤」이다(`app/factcheck.py` `FACT_QUESTIONS`) → 예 = 가장 좋은 경우 · 아니오 = 가장 나쁜 경우
ANSWER_SETS = (Answer.예, Answer.아니오)


def _open_questions(
    state: dict[str, Any], *, held: bool = False
) -> list[tuple[str, str, str | None]]:
    """상태의 질문 — (문장 글자, `fact` · `subst`, 사실 종류). 기록 문장과 보이는 분기 문장 모두 · 답은 문장 글자에 묶여 모든 분기에 든다(`app/routers/user.py` `_answers_of`).

    `held` — 보류 문장의 질문만(🆕 2026-10-21 · 다시 선 질문 셈). 확정 위반 문장은 실증 분기를 **지시**로 싣는다(D-337 · D-268) — 답을 기다리는
    질문이 아니다. 이걸 빼지 않으면 「아니오」로 확정된 문장의 지시가 「답한 질문이 다시 섰다」로 잘못 잡힌다(원장 10-21 ⑦ — 252 행이 이 꼴).
    """
    sents = list(state.get("sentences", [])) + [
        x for b in state.get("branches", []) for x in b.sentences
    ]
    if held:
        sents = [x for x in sents if x.verdict is Verdict.hold]
    out: dict[tuple[str, str, str | None], None] = {}
    for x in sents:
        if x.fact_check is not None:
            out[(x.text, "fact", x.fact_check.kind.value)] = None
        if x.substantiation is not None:
            # 🔄 2026-10-21 (D-348 보충 39 결정 6) 실증 질문은 유형마다 — 유형을 담아 묻고 답한다(빈 유형은 종전 질문)
            v = x.substantiation.violation
            out[(x.text, "subst", v.value if v is not None else None)] = None
    return list(out)


def answer_path(
    runner: Callable[[str, ProductContext], dict[str, Any]],
    text: str,
    product: ProductContext,
    first: dict[str, Any],
    answer: Answer,
) -> dict[str, Any]:
    """질문이 선 행을 한 가지 답으로 끝까지 — 선 질문에 모두 `answer` 로 답하고 다시 판정 · 새 질문이 서면 또 (상한 `ANSWER_ROUNDS`).

    🆕 2026-10-21 (D-348 보충 35 결정 2 · 인계 10-21 클론B §1 #2 (가′)). 보충 33 으로 판정이 답 뒤로 갔다 — 답하기 전 상태만 재면 판정을 못 잰다.
    🚨 답은 검증이 아니다 · 이 수는 「사용자가 그렇게 답하면」의 판정이다(골든 라벨과 맞대는 해석은 `answer_report`).
    """
    from app.contracts import FactKind  # noqa: PLC0415

    facts, substs = list(product.facts), list(product.substs)
    asked: set[tuple[str, str, str | None]] = set()
    # 🆕 2026-10-21 (인계 10-21 클론A §2 · 답 경로의 알려진 한계) 이미 답한 질문이 **보류 문장에** 다시 서면 그래프 결함이다 — 종전에는 `asked` 로 걸러
    #    다시 답하지도 않고 `left` 에도 세지 않아 **조용히 묻혔다**(D-220). 따로 세고 도달로 세지 않는다(`answer_report`)
    reasked: set[tuple[str, str, str | None]] = set()
    st, rounds = first, 0
    for _ in range(ANSWER_ROUNDS):
        new = [q for q in _open_questions(st) if q not in asked]
        if not new:
            break
        for t, kind, fk in new:
            asked.add((t, kind, fk))
            if kind == "fact":
                facts.append(UserFact(text=t, kind=FactKind(fk), answer=answer))
            else:
                substs.append(
                    UserSubst(text=t, answer=answer, violation=Violation(fk) if fk else None)
                )
        st = runner(text, product.model_copy(update={"facts": facts, "substs": substs}))
        rounds += 1
        reasked.update(q for q in _open_questions(st, held=True) if q in asked)
    p = predict(st)
    left = [q for q in _open_questions(st) if q not in asked]
    return {
        "class": p["class"],
        "types": p["types"],
        "cond_types": p["cond_types"],
        "verdicts": p["verdicts"],
        "hold_reasons": p["hold_reasons"],
        "risk_max": p["risk_max"],
        "rounds": rounds,
        "asked": len(asked),
        "left": len(left),
        "reasked": len(reasked),
        "contract_error": p.get("contract_error"),
    }


def run(
    rows: Iterable[dict],
    runner: Callable[[str, ProductContext], dict[str, Any]],
    every: int = 100,
    *,
    conditional: bool = False,
    category_only: bool = False,
    answers: bool = False,
) -> list[dict]:
    preds = []
    t0 = time.perf_counter()
    inv = _InvariantLog()
    log = logging.getLogger(g.INVARIANT_LOG)
    log.addHandler(inv)
    try:
        for k, r in enumerate(rows, 1):
            product = product_of(r, conditional, category_only=category_only)
            inv.got = []
            st = runner(r["text"], product)
            p = predict(st)
            if answers and _open_questions(st):
                #: 🆕 (보충 35 결정 2) 답 경로 — 질문이 선 행만 · 두 벌
                p["answer_path"] = {
                    a.value: answer_path(runner, r["text"], product, st, a) for a in ANSWER_SETS
                }
            #: 🆕 (보충 35 결정 1) 이 행에서 불변식이 깨진 자리 — 답 경로의 재판정까지 포함
            p["invariant"] = list(inv.got)
            #: 🆕 (보충 35 결정 2) 넘긴 제품 정보 — 경로 동치 대조(`scripts/eval_diff.py`)가 행을 짝짓는다
            p["product"] = {
                "category": None if product.category is None else product.category.value,
                "premise": None if product.premise is None else product.premise.value,
            }
            preds.append(p)
            if every and k % every == 0:
                print(f"  … {k}행 · {time.perf_counter() - t0:.0f}초", file=sys.stderr)
    finally:
        log.removeHandler(inv)
    return preds


def git_head(root: pathlib.Path = pathlib.Path(".")) -> str:
    """지금 커밋 — 정본은 `scripts/sealed_log.py` 한 곳 (🔄 2026-10-15 · D-344 ⑧ · D-99)."""
    return sealed_log.git_head(root)


def sealed_runs_on(date: str) -> list[dict]:
    """이 기기에서 그 날짜(`YYYY-MM-DD`)에 연 **판정 그래프** 봉인 회차들. 판정기 B(`eval_rule`)의 줄은 세지 않는다 (D-344 ⑧)."""
    return sealed_log.runs_on(date, tool=sealed_log.GRAPH, path=SEALED_LOG)


def sealed_refusal(a: argparse.Namespace, today: str) -> str | None:
    """봉인 회차를 열면 안 되는 까닭 — 열어도 되면 `None` (D-175 · D-339 결정 7). 인코더 조건은 `use_encoder` 가 본다."""
    partial = [
        f
        for f, on in (
            ("--limit", a.limit),
            ("--provenance", a.provenance),
            ("--no-enc-filter", a.no_enc_filter),
            ("--stub", a.stub),
        )
        if on
    ]
    if partial:
        return f"봉인 회차는 전 행 · 앱과 같은 조건으로 한 번이다 — {' · '.join(partial)} 와 함께 쓸 수 없다"
    if done := sealed_runs_on(today):
        return (
            f"이 기기에서 {today} 에 이미 봉인 회차를 열었다({len(done)}번 · {SEALED_LOG}) — 날짜 하나에 한 번이다."
            " 같은 날 다시 재야 하면 팀장 판정을 받고 기록 줄을 원장으로 옮긴 뒤 연다"
        )
    return None


def log_sealed_run(stamp: dict[str, Any]) -> int:
    """🆕 2026-10-08 (D-175) — 봉인 평가셋 실행 한 줄을 남기고 이 기기의 누적 횟수를 낸다. 🔴 기록을 못 쓰면 멈춘다(조용히 넘기지 않는다).

    🔄 2026-10-15 — **돌기 전에** 부른다(도중에 죽어도 봉인 행을 연 것은 센다) · 커밋을 같이 적는다.
    🔄 2026-10-15 (D-344 ⑧) — 기록은 `scripts/sealed_log.py` 한 곳이다 · 판정기 B 와 같은 파일에 `tool` 로 갈라 적는다.
    """
    return sealed_log.append(stamp, tool=sealed_log.GRAPH, path=SEALED_LOG)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--provenance")
    ap.add_argument("--stub", action="store_true", help="DB 없이 배선만")
    ap.add_argument("--out", type=pathlib.Path, help="수 · 행 예측을 JSON 으로")
    ap.add_argument(
        "--conditional",
        action="store_true",
        help="조건부 — 골든 품목을 제품 정보로 (품목을 아는 행만)",
    )
    ap.add_argument(
        "--encoder",
        type=pathlib.Path,
        help=f"인코더 모델 폴더 — 그림자로 돌려 「후보로 더했다면」의 수를 낸다 (없으면 {enc.ENV_MODEL_DIR} · 둘 다 없으면 인코더 없이)",
    )
    ap.add_argument(
        "--no-enc-filter",
        action="store_true",
        help="인코더 후보의 전제별 거름 · 옮김을 끈다 — 거름표를 걷을지 판정하는 dev 비교용 (D-336 결정 5 · 앱은 늘 켠다)",
    )
    ap.add_argument(
        "--dict-view",
        choices=g.DICT_VIEWS,
        help="사전 판 — c_only: 칸이 C 인 단독판정 항목만 · 자격 없는 항목 없음(사전 좁히기 전 잃는 몫 측정 · D-348 보충 15 결정 3 · 봉인 회차에는 쓰지 않는다)",
    )
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument(
        "--dev",
        action="store_true",
        help="dev(검증 묶음)로 잰다 — 판 · 문턱 · 규칙을 고르는 자리 (D-175)",
    )
    which.add_argument(
        "--sealed",
        action="store_true",
        help="봉인 평가셋(test_sentence) 회차 — 잠금 채택 판 · 전 행 · 날짜 하나에 한 번 (D-339 결정 7 · 보고 전용)",
    )
    ap.add_argument(
        "--guide-dev",
        action="store_true",
        help="확장 dev — dev 에 재분할의 해설서 dev 를 더한다 (D-347 · `--dev` 와 함께만)",
    )
    ap.add_argument(
        "--category-only",
        action="store_true",
        help="조건부에서 골든 `전제` 의 품목만 넘긴다(전제를 고르기 전) — 경로 동치 대조의 짝(`scripts/eval_diff.py equiv` · D-348 보충 35 · dev 전용)",
    )
    ap.add_argument(
        "--answers",
        action="store_true",
        help=f"답 경로 — 질문이 선 행을 모두 「예」 · 모두 「아니오」로 끝까지(이어 묻기 {ANSWER_ROUNDS} 회까지 · D-348 보충 35 · 보고 지표)",
    )
    a = ap.parse_args(argv)
    if a.category_only and (not a.conditional or a.sealed):
        raise SystemExit(
            "🔴 --category-only 는 dev 조건부 전용 — 경로 동치 대조의 짝이다(D-348 보충 35 · 봉인 회차는 고른 전제로 잰다)"
        )
    if a.answers and not (a.conditional or a.sealed):
        # 🆕 2026-10-24 (보충 35 결정 2 · 보충 34 결정 2 · 보충 37 결정 2) 품목을 모르면 답하지 않는다 — 묻는 순서는 품목 먼저 · 무조건부의 질문은
        #    분기 미리보기다. 종전에는 미리보기 질문에 바로 답해 계약 오류로 멈췄다(봉인 회차 10-24 · 원장 10-24(B) ④)
        raise SystemExit(
            "🔴 --answers 는 조건부(--conditional)에서만 — 품목을 모르면 답하지 않는다(D-348 보충 34 결정 2 · 37 결정 2) · 봉인 회차는 조건부 모드에만 돈다"
        )
    if a.guide_dev and not a.dev:
        raise SystemExit(
            "🔴 --guide-dev 는 --dev 와 함께만 — 봉인 평가셋에는 해설서 dev 가 없다 (D-347)"
        )
    if a.sealed and a.dict_view:
        raise SystemExit("🔴 --dict-view 는 dev 측정 전용 — 봉인 회차는 원래 사전으로만 (D-175)")
    if a.sealed:
        import datetime  # noqa: PLC0415

        if a.conditional:
            raise SystemExit(
                "🔴 봉인 회차는 무조건부 · 조건부를 **한 실행에** 함께 잰다 — --conditional 을 붙이지 않는다(D-306 · D-339 결정 7)"
            )
        if why := sealed_refusal(a, datetime.date.today().isoformat()):
            raise SystemExit(f"🔴 {why}")
        if why := sealed_log.worktree_refusal():
            raise SystemExit(f"🔴 {why}")
    rows = load_rows(dev=a.dev, guide_dev=a.guide_dev)
    #: dev 대조는 **거르기 전 전체 행**으로 한다 — 원천으로 거른 뒤에는 지문이 달라진다
    dev_stamp = check_dev(rows, a.encoder or enc.configured_dir()) if a.dev else {}
    if a.provenance:
        rows = [r for r in rows if r.get("provenance") == a.provenance]
    #: 🆕 2026-10-20 — 잴 모드. 봉인 회차는 **무조건부 → 조건부를 한 실행에**(기록 한 줄 · 결과 파일 둘 · D-306 「두 번 돌려 나란히」를 한 회차로)
    modes = (False, True) if a.sealed else (a.conditional,)
    all_rows = rows
    #: 판 표지 — 원장에 수와 함께 적는다 (D-178). 🔴 실제 실행은 DB 사전이 파일과 같을 때만 돈다(`check_dict`)
    stamp: dict[str, Any] = {"golden_sha": _sha12(GOLDEN), "conditional": a.conditional}
    if a.category_only:
        stamp |= {"category_only": True}
    if a.answers:
        stamp |= {"answers": f"예 · 아니오 · {ANSWER_ROUNDS}회"}
    stamp |= {"split": "dev" if a.dev else "test_sentence", "resplit": resplit.VERSION} | dev_stamp
    stamp |= use_encoder(a.encoder, adopted_only=a.sealed)
    #: 🆕 2026-10-24 (D-348 보충 41 결정 3) 하한 가드의 동작 · 상태 명사 목록 — 없으면 None(하한 가드 = 지금 주장 가드)
    stamp |= {"claim_nouns": claimscope.nouns_stamp()}
    if a.no_enc_filter:
        g.disable_encoder_filter()
        stamp |= {"encoder_filter": "끔"}
    if a.dict_view:
        g.set_dict_view(a.dict_view)
        stamp |= {"dict_view": a.dict_view}
    if a.sealed:
        n_runs = log_sealed_run(
            stamp
            | {
                "conditional": "무조건부 · 조건부",
                "judged_by": g.JUDGED_BY,
                "rows": len(all_rows),
                "rows_conditional": len(conditional_rows(all_rows)),
                "status": "시작",
            }
        )
        print(
            f"  🔒 봉인 평가셋 회차를 연다 — 이 기기 기록 {n_runs}번째 ({SEALED_LOG}) · 원장에 판 표지와 함께 옮긴다 (D-175)"
        )
    if a.stub:
        for cond in modes:
            _one_mode(a, cond, _mode_rows(all_rows, cond, a.limit), stamp, stub_runner())
        return 0
    from app.db import pg_connect  # noqa: PLC0415 — DB 가 없어도 --stub 은 돈다

    review = g.build_review()
    with pg_connect() as conn, conn.cursor() as cur:
        stamp |= check_dict(cur)
        if a.dict_view:
            kept = [e for e in g.load_dict_entries(cur) if g.entry_cell(e) is g.Infeasibility.C]
            stamp |= {"dict_view_kept": len(kept)}  # 남긴 단독판정 항목 수(자격 없는 항목은 0)
        cfg = {"configurable": {"conn": cur}}

        def runner(t: str, p: ProductContext) -> dict[str, Any]:
            return _checked(review.invoke({"text": t, "product": p}, config=cfg))

        for cond in modes:
            _one_mode(a, cond, _mode_rows(all_rows, cond, a.limit), stamp, runner)
    return 0


def _mode_rows(rows: list[dict], conditional: bool, limit: int | None) -> list[dict]:
    """한 모드에서 잴 행 — 조건부면 품목 · 전제를 아는 행만(`conditional_rows`) · `--limit` 은 그 뒤에 자른다(종전 순서 그대로)."""
    out = conditional_rows(rows) if conditional else rows
    return out[:limit] if limit else out


def mode_answers(a: argparse.Namespace, conditional: bool) -> bool:
    """이 모드에서 답 경로를 도는가 — **조건부에서만** (🆕 2026-10-24 · D-348 보충 35 결정 2 · 보충 34 결정 2 · 보충 37 결정 2).

    🔴 무조건부(품목 모름)의 질문은 분기 미리보기다 — 화면은 품목을 고른 뒤 그 전제로 묻는다. 봉인 회차(`--sealed --answers`)는 무조건부 모드를 답 없이 잰다.
    """
    return bool(getattr(a, "answers", False)) and conditional


def _one_mode(
    a: argparse.Namespace,
    conditional: bool,
    rows: list[dict],
    stamp: dict[str, Any],
    runner: Callable[[str, ProductContext], dict[str, Any]],
) -> None:
    """한 모드를 재고 보고 · 결과 파일을 쓴다 — 봉인 회차는 두 모드를 차례로 부른다(`--out` 이름에 `_uncond` · `_cond` 를 붙인다)."""
    on = mode_answers(a, conditional)
    stamp = {k: v for k, v in stamp.items() if on or k != "answers"} | {"conditional": conditional}
    t0 = time.perf_counter()
    preds = run(
        rows,
        runner,
        conditional=conditional,
        category_only=getattr(a, "category_only", False),
        answers=on,
    )
    secs = time.perf_counter() - t0
    s = summarize(rows, preds)
    report(s, conditional, dev=a.dev)
    # 🆕 2026-10-18 (D-348 보충 24 결정 1) 사전 낱말과 글자가 같은 채점 행 — 일반화 지표와 나란히 읽는다
    if DICT_FILE.exists():
        echo = dict_echo(
            rows,
            preds,
            [
                json.loads(x)
                for x in DICT_FILE.read_text(encoding="utf-8").splitlines()
                if x.strip()
            ],
        )
        s["dict_echo"] = echo
        print(
            f"\n  사전 낱말과 글자가 같은 채점 행 {echo['rows']} · 그중 확정 유형 맞음 {echo['type_hit']}"
            f" (목록에서 찾아 맞힌 몫 · 위 지표에 들어 있다 — 빼고 읽을 때 쓴다 · 출처 {echo['by_source']} · D-348 보충 24)"
        )
    print(
        f"\n  실행 {secs:.0f}초 · 행당 {secs / max(len(rows), 1) * 1000:.0f} ms · judged_by {g.JUDGED_BY}"
        f" · " + " · ".join(f"{k} {v}" for k, v in stamp.items())
    )
    out = a.out
    if out and a.sealed:
        out = out.with_name(f"{out.stem}_{'cond' if conditional else 'uncond'}{out.suffix}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "summary": s,
                    "judged_by": g.JUDGED_BY,
                    "stub": a.stub,
                    **stamp,
                    "rows": [{"id": r["id"], **p} for r, p in zip(rows, preds, strict=True)],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(f"  → {out}")


if __name__ == "__main__":
    raise SystemExit(main())
