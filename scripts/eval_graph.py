"""scripts/eval_graph.py — **그래프 평가 도구 (W1)**. 판정 그래프를 봉인 평가셋(`test_sentence`)에 돌려 잰다.

    uv run python scripts/eval_graph.py                          # 정본 기기 · 실제 DB · 전부
    uv run python scripts/eval_graph.py --limit 200              # 앞 200행만(실행 시간을 먼저 잰다)
    uv run python scripts/eval_graph.py --provenance ftc_decisions_body
    uv run python scripts/eval_graph.py --dev --encoder models/<판>   # 🆕 dev(검증 묶음)로 — 판 · 문턱 · 규칙은 여기서 고른다 (D-175)
    uv run python scripts/eval_graph.py --stub                   # DB 없이 — 배선만(전부 미판정 · 수는 0 이 정상)
    uv run python scripts/eval_graph.py --out build/eval/graph.json

★ **무엇을 답하나** (설계초안 09-23 W1 · D-269 · D-275 · D-301) —
  ① 응답 분포 — 문장 판정 상태 · 종착 · **보류율을 사유별로** (D-269 「게이트 수는 보류율을 사유별로 함께」)
  ② 유형 · 호 P/R/F1 — 예측 = **확정 문장의 위반만**(보류 · 근거없음 · 미판정은 예측이 아니다 · D-127). 30 미만은 측정 불가 (D-40)
  ③ selective risk — 판정을 내린 행(전 문장 확정) 중 틀린 비율 · coverage 와 쌍으로 (D-77 L1 #8)
  ④ 조건별 대응표 — 라벨 조건(C/A/B/M/D/L) × 응답 (D-275 가 W1 몫으로 넘긴 표)
  ⑦ 보수 기록 — 확정 ∪ 분기 보류에 실린 유형을 「기록된 판정」으로 센다 (🆕 2026-10-06 · D-263 ① 「게이트 수치도 이것으로」)
  ⑥ 불가 사유 진단 — 확정 위반의 사유(A/B/C)를 라벨 조건과 대조 (🆕 2026-10-06 · 원장 10-03 ㊿-36). 🚨 게이트가 아니다
  ⑤ 적법 문장 오탐률 — 내역(주장 있음 · 주장 없음)과 함께만 (D-301)
🔴 **채점 규칙은 판정기 B 와 한 곳이다** — `scored` · `truth_types` · `truth_ho` · `lawful_report` · D-40 문턱을
   `scripts/eval_rule.py` 에서 가져온다 (D-99). 판정기 B 와 그래프의 수가 같은 자로 재진다.
🚨 **봉인 평가셋으로 규칙을 고르지 않는다** (D-175) — 이 수는 보고용이다. 규칙 · 문턱을 이 수에 맞춰 고치면 누수다.
🔄 2026-10-01 (D-306) — `--conditional` 이면 **조건부**(골든 `품목` 칸을 제품 정보로 넘긴다 · 품목을 아는 행만) · 기본은
   **무조건부**(품목 미확정 · 세 법). 기획서 6-3 「조건부 / 무조건부 병기」 — 두 번 돌려 나란히 적는다.
   🔴 골든에 `품목` 칸이 없으면(재동결 전 판) `--conditional` 은 멈춘다 — 무조건부로 조용히 바꾸지 않는다 (D-220).
🚨 게이트가 아니다 — 답이 기기마다 다르다(`data/**` 미커밋 · D-19). 수는 원장에 기기 · 커밋 · 골든 sha 와 함께 적는다 (D-178).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import encoder as enc  # noqa: E402
from app import graph as g  # noqa: E402
from app.contracts import (  # noqa: E402
    Category,
    HoldReason,
    ProductContext,
    SentenceJudgment,
    Verdict,
)
from collect import statute  # noqa: E402
from preprocess import devsplit  # noqa: E402
from preprocess.golden import lawful_kind  # noqa: E402
from preprocess.split import APPROVED_READING  # noqa: E402
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
SEALED_LOG = pathlib.Path("build/eval/sealed_runs.jsonl")
#: 🆕 2026-10-08 (D-321 결정 4) — 6종 표. 8종에서 이번 차수에 편입한 둘을 뺀 것(종전 6종 · 2차와 이어 본다)
NEW_IN_D321 = frozenset({"부당_비교광고", "비방광고"})
#: DB 사전 대조의 기준 — 적재기(`scripts/load_db.py` `load_dict`)가 읽는 바로 그 파일
DICT_FILE = pathlib.Path("data/derived/banned_terms.jsonl")

#: 행 하나의 응답 갈래 — 조건별 대응표(D-275)와 selective risk 가 같이 쓴다.
#: 🔴 「확정 위반」은 **전 문장 확정 ∧ 위반 있음**이 아니라 **위반을 확정한 문장이 하나라도** — 예측의 정의와 같다.
CLASSES = ("확정위반", "확정무위반", "보류", "근거없음", "미판정")


def load_rows(
    path: pathlib.Path = GOLDEN, provenance: str | None = None, *, dev: bool = False
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
    else:
        rows = [r for r in every if r["split"] == "test_sentence"]
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


def predict(state: dict[str, Any]) -> dict[str, Any]:
    """그래프 상태 → 행 예측. 예측 유형 · 호는 **확정 문장의 위반만**이다 (D-127 · 보류는 예측이 아니다)."""
    sents: list[SentenceJudgment] = list(state.get("sentences", []))
    conf = [s for s in sents if s.verdict is Verdict.confirmed]
    types = sorted({v.value for s in conf for v in s.violations})
    #: 🆕 2026-10-02 (D-311) — **보류 문장의 유형 후보**(단독판정 자격 없는 적중). 예측이 아니다 — 탐지 재현율만 읽는다
    cands = sorted({v.value for s in sents if s.verdict is Verdict.hold for v in s.violations})
    ho = sorted({h for s in conf if s.violations for h in _ho(s)})
    verdicts = [s.verdict.value for s in sents]
    if any(s.violations for s in conf):
        cls = "확정위반"
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
        "enc_candidates": sorted({c.violation.value for s in sents for c in s.encoder_candidates}),
        "encoded": bool(sents) and len(state.get("encodings", [])) == len(sents),
        "enc_truncated": sum(1 for e in state.get("encodings", []) if e.truncated),
        "ho": ho,
        "class": cls,
        #: 판정을 내린 행 — **전 문장이 확정**이다(selective risk 의 분모 · D-77 L1 #8)
        "committed": bool(sents) and len(conf) == len(sents),
        #: 🆕 2026-10-02 (W5) — 확정 위반 문장에 **위험도가 다 붙었나**. 붙었는데 종착이 보류면 하한이 아니라 종착 재료(증명서 · 지시 문안)가 없다
        "risked": all(s.risk.final is not None for s in conf if s.violations),
        "n_sents": len(sents),
        #: 🆕 2026-10-06 (D-263 ① · D-319 ①) — **분기 때문에 보류로 기록된 문장에 실린 유형**(가장 보수적인 전제의 위반).
        #:    `candidates`(자격 없는 적중까지 든 보류 후보)와 다르다 — 전제를 몰라 멈춘 문장만이다
        "premise_held": sorted(
            {
                v.value
                for s in sents
                if s.verdict is Verdict.hold and s.hold_reason in PREMISE_HOLDS
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


def _branch_view(b: Any) -> dict[str, Any]:
    """분기 하나 → 확정 위반의 유형 · 호 · 종착. 기록되는 판정과 **같은 규칙**으로 센다(확정 문장의 위반만 · D-127)."""
    conf = [s for s in b.sentences if s.verdict is Verdict.confirmed]
    return {
        "outcome": b.outcome.value,
        "types": sorted({v.value for s in conf for v in s.violations}),
        "ho": sorted({h for s in conf if s.violations for h in _ho(s)}),
        "committed": bool(b.sentences) and len(conf) == len(b.sentences),
    }


#: 골든 `품목` 칸 → 그 품목의 **첫 전제**(가장 보수적인 쪽 · `app/premise.py` 의 값). 분기 지표가 「정답 품목의 분기」를 이것으로 고른다.
#:    🚨 건강기능식품은 인정 여부를 골든이 모른다 — 비인정(보수) 분기로 본다.
BRANCH_OF_CATEGORY = {"식품": "식품", "건기식": "건기식_비인정", "화장품": "화장품"}


def branch_report(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    """분기 지표 (D-319 ⬜ 「정답 품목의 분기가 맞는가」) — 품목을 아는 채점 행의 **위반 행**에서 그 품목의 분기를 본다.

    ★ 기록되는 판정이 보류(`cat_unknown`)여도 사용자가 자기 품목을 고르면 보게 되는 것이 이 분기다.
    🚨 분기가 없으면(기준 문안 미확정 · 전제 하나) 0 이다 — 「분기 행」 수를 함께 읽는다.
    """
    out = {"rows_with_branches": sum(1 for p in preds if p.get("branches")), "positive": 0}
    out.update({"confirmed": 0, "type_hit": 0, "ho_hit": 0, "wrong": 0})
    for r, p in zip(rows, preds, strict=True):
        name = BRANCH_OF_CATEGORY.get(r.get("품목") or "")
        if not name or not scored(r) or not truth_types(r, set()):
            continue
        b = (p.get("branches") or {}).get(name)
        if b is None:
            continue
        out["positive"] += 1
        if not b["types"]:
            continue
        out["confirmed"] += 1
        tt, th = truth_types(r, set(b["types"])), truth_ho(r, set(b["ho"]))
        out["type_hit"] += bool(set(b["types"]) & tt)
        out["ho_hit"] += bool(set(b["ho"]) & th)
        out["wrong"] += not (set(b["types"]) & tt)
    return out


# ── 집계 ────────────────────────────────────────────────────────────────


#: 전제를 몰라 멈춘 보류 사유 — 계약 `_branch_hold_has_branches` 의 것과 같다(D-263 ② · D-229 ⑥).
PREMISE_HOLDS = frozenset({HoldReason.cat_unknown, HoldReason.premise_unknown})


def recorded_report(rows: list[dict], preds: list[dict]) -> dict[str, int]:
    """보수 기록 지표 (🆕 2026-10-06 · D-263 ① 「기록되는 판정 = 가장 보수적인 전제 · 게이트 수치도 이것으로 잰다」).

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

    ★ micro 는 측정 불가 유형까지 합친 수다 — 둘을 나란히 낸다(어느 쪽을 게이트에 쓸지는 정하지 않았다 · ⬜ 판정).
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


def encoder_report(
    rows: list[dict], preds: list[dict], sc: list[tuple[dict, dict]]
) -> dict[str, Any]:
    """**인코더 신호를 유형 후보로 더했다면**의 탐지 재현율 (🆕 2026-10-07 · 그림자 배선).

    ★ 판정은 인코더를 읽지 않는다 — 이 수는 「붙이면 탐지가 얼마가 되나」이고 **지금 그래프가 낸 판정의 수가 아니다.**
       `detect`(D-311 결정 5 · 확정 ∪ 보류 유형 후보)는 그대로 두고 **따로** 싣는다.
       ⬜ D-311 의 「보류 유형 후보」는 사전의 자격 없는 적중을 가리켜 적은 말이다 — 인코더 후보를 같은 줄에 세는지는 팀장 확인.
    🔴 인코더가 **전 문장에** 돈 행만 센다(`encoded`). 안 돈 행을 「조용했다」로 세지 않는다 (D-220) — 없으면 `rows` 가 0 이다.
    · `lawful` — 적법 문장에 인코더 후보가 선 수. 칸은 `lawful_report` 와 같다(음성 L · 주장없음 D · D-301).
    """
    done = [(r, p) for r, p in zip(rows, preds, strict=True) if p.get("encoded")]
    if not done:
        return {"rows": 0}
    ids = {id(r) for r, _ in done}
    pos = det = det_enc = 0
    for r, p in sc:
        if id(r) not in ids:
            continue
        pt = set(p["types"]) | set(p.get("candidates", ()))
        pe = pt | set(p["enc_candidates"])
        tt = truth_types(r, pe)
        if not tt:
            continue
        pos += 1
        det += bool(pt & tt)
        det_enc += bool(pe & tt)
    fired: dict[str, bool] = {}
    for r, p in done:
        fired[r["text"]] = fired.get(r["text"], False) or bool(p["enc_candidates"])
    return {
        "rows": len(done),
        "positive": pos,
        "detected": det,
        "detected_with_encoder": det_enc,
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
        elif p["committed"]:
            # 🔄 2026-10-02 (W5) — 위험도가 붙은 뒤의 보류는 다른 까닭이다: 종착의 재료가 없다 (`app/graph.py` 종착).
            #    🔄 2026-10-06 — 증명서 조립기는 섰다(D-320). 여기 남는 것은 사유 문안이 없는 조합과 실증 분기가 없는 지시다
            reasons["종착재료없음(문안)" if p["risked"] else "하한없음(W5)"] += 1
        elif "unjudged" in p["verdicts"]:
            reasons["미판정"] += 1
        else:
            reasons["근거없음"] += 1
    out["hold_rate"] = len(held) / n if n else 0.0
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
            wrong = (not tt and pt) or (tt and not (pt & tt))
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
    out["coverage"] = committed / len(sc) if sc else 0.0
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
    out["reason"] = reason_report(rows, preds)
    out["recorded"] = recorded_report(rows, preds)
    return out


def conditional_rows(rows: list[dict]) -> list[dict]:
    """조건부 평가 행 — `품목` 을 아는 행만. 🔴 칸 자체가 없는 판이면 멈춘다(재동결 전 골든 · D-220)."""
    if rows and not all("품목" in r for r in rows):
        raise SystemExit(
            "🔴 골든에 `품목` 칸이 없다 — 재동결 전 판이다(D-306). 조건부 평가를 못 한다\n"
            "  먼저(정본): uv run python launcher.py golden --write"
        )
    # 🆕 2026-10-06 (원장 10-03 ㊿-40) — **승인 문구 규칙 행은 뺀다.** 그 행의 `품목`(건기식)은 원천이고 라벨(3호 · 조건 A)은
    #    「일반식품이 이 문구를 쓰면」이라는 보수 전제다(`preprocess/split.py` `APPROVED_READING` · 판정 J1). 품목을 제품 정보로 넘기면
    #    그래프는 건강기능식품으로 보고 4.나를 내고 채점은 3호를 기대한다 — 전제가 어긋난 행이다. 무조건부에는 그대로 든다.
    #    ⬜ 다음 재동결 때 그 행(과 같은 원천의 주입 행)의 `품목` 을 미상으로 고치면 이 줄은 필요 없다 (D-192)
    return [r for r in rows if r["품목"] and r.get("판독") != APPROVED_READING]


def product_of(r: dict, conditional: bool) -> ProductContext:
    """행의 제품 정보 — 무조건부면 빈 것(세 법) · 조건부면 골든 `품목`. 🚨 인정 여부는 모른다(보수 전제 · D-263 ①)."""
    return ProductContext(category=Category(r["품목"])) if conditional else ProductContext()


def report(s: dict[str, Any], conditional: bool = False, *, dev: bool = False) -> None:
    print(
        "  [조건부 — 품목을 아는 행 · 골든 `품목`]"
        if conditional
        else "  [무조건부 — 품목 미확정 · 세 법]"
    )
    print(
        f"그래프 평가 — {'dev(검증 묶음)' if dev else '평가셋'} {s['rows']}행 (채점 {s['scored_rows']} · 채점 밖 M · D {s['unscored_rows']})"
    )
    print(f"  종착   {s['outcome']}")
    print(f"  문장   {s['verdict']}")
    print(f"  행     {s['class']}")
    print(f"  보류율 {s['hold_rate']:.1%} — 사유별 {s['hold_reasons']}")
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
        f"\n  selective risk {('-' if sr is None else f'{sr:.1%}')} {_ci(err, s['committed'])} · coverage {s['coverage']:.1%} "
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
                f"인코더 후보까지 {e['detected_with_encoder'] / e['positive']:.1%}"
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
    print_lawful(s["lawful"])
    w = s.get("recorded") or {}
    if w.get("rows"):
        print(
            f"\n  보수 기록 (D-263 ① · 확정 ∪ 분기 보류에 실린 유형) — 기록이 있는 채점 행 {w['rows']} · "
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
                f"호 맞음 {b['ho_hit']} · 유형 틀림 {b['wrong']}"
                if n
                else ""
            )
            + "  (분기는 판정이 아니다 · 건강기능식품은 비인정 분기로 본다)"
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


def check_dev(rows: list[dict], model_dir: pathlib.Path | None) -> dict[str, Any]:
    """dev 행이 **그 인코더가 학습에서 뺀 dev 와 같은지** — 모델 폴더의 `label_scheme.json`(`dev_sha` · `dev_rows`)과 대조한다.

    🔴 **다르면 멈춘다** (D-220 · D-175) — 그 모델은 이 행의 일부를 학습에서 봤다. 그 수는 dev 수치가 아니다.
    🚨 모델 폴더에 dev 지문이 없으면(옛 산출물) 대조할 수 없다 — 멈추지 않고 판 표지에 「미확인」으로 적는다.
       없음을 일치로 세지 않는다. 인코더 없이 재면 대조할 모델이 없다 — 지문만 적는다.
    """
    stamp: dict[str, Any] = {"dev_rows": len(rows), "dev_sha": devsplit.sha(r["id"] for r in rows)}
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
    return stamp | {"dev_check": "일치"}


def use_encoder(model_dir: pathlib.Path | None) -> dict[str, Any]:
    """인코더를 켠다 — 판 표지(폴더 이름 · 가중치 지문)를 돌려준다. 안 켜면 빈 표지다.

    🔴 **켰는데 못 올리면 멈춘다** (D-220) — 그래프의 `encode` 는 이 경우 경고만 남기고 규칙 판정으로 간다.
       수를 재는 자리에서 그대로 두면 인코더 없는 수가 인코더 수처럼 찍힌다.
    """
    if model_dir is not None:
        os.environ[enc.ENV_MODEL_DIR] = str(model_dir)
    path = enc.configured_dir()
    if path is None:
        return {}
    try:
        scheme = enc.encoder_at(path).scheme
        return {
            "encoder": path.name,
            "encoder_sha": enc.weights_sha12(path),
            # 상한을 모델 폴더가 실어 줬는지 · 기본값으로 돌았는지 함께 적는다 (D-220)
            "encoder_max_tokens": f"{scheme.max_tokens}"
            + ("" if scheme.max_tokens_from_model else "(기본값)"),
        }
    except enc.EncoderUnavailable as e:
        raise SystemExit(
            f"🔴 인코더를 올리지 못했다 — {e}\n  끄려면 --encoder 와 {enc.ENV_MODEL_DIR} 을 비운다"
        ) from e


def stub_runner() -> Callable[[str, ProductContext], dict[str, Any]]:
    """DB 없이 — 스텁 한 바퀴(`run_review_stub`). 사전을 못 훑어 전부 미판정이다 — 배선만 본다."""
    return lambda text, product: g.run_review_stub(text)[0]


def run(
    rows: Iterable[dict],
    runner: Callable[[str, ProductContext], dict[str, Any]],
    every: int = 100,
    *,
    conditional: bool = False,
) -> list[dict]:
    preds = []
    t0 = time.perf_counter()
    for k, r in enumerate(rows, 1):
        preds.append(predict(runner(r["text"], product_of(r, conditional))))
        if every and k % every == 0:
            print(f"  … {k}행 · {time.perf_counter() - t0:.0f}초", file=sys.stderr)
    return preds


def log_sealed_run(stamp: dict[str, Any]) -> int:
    """🆕 2026-10-08 (D-175) — 봉인 평가셋 실행 한 줄을 남기고 이 기기의 누적 횟수를 낸다. 🔴 기록을 못 쓰면 멈춘다(조용히 넘기지 않는다)."""
    import datetime  # noqa: PLC0415

    SEALED_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.datetime.now().isoformat(timespec="seconds")} | stamp
    with SEALED_LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    return sum(1 for x in SEALED_LOG.read_text(encoding="utf-8").splitlines() if x.strip())


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
        "--dev",
        action="store_true",
        help="봉인 평가셋 대신 dev(검증 묶음)로 잰다 — 판 · 문턱 · 규칙을 고르는 자리 (D-175)",
    )
    a = ap.parse_args(argv)
    rows = load_rows(dev=a.dev)
    #: dev 대조는 **거르기 전 전체 행**으로 한다 — 원천으로 거른 뒤에는 지문이 달라진다
    dev_stamp = check_dev(rows, a.encoder or enc.configured_dir()) if a.dev else {}
    if a.provenance:
        rows = [r for r in rows if r.get("provenance") == a.provenance]
    if a.conditional:
        rows = conditional_rows(rows)
    if a.limit:
        rows = rows[: a.limit]
    #: 판 표지 — 원장에 수와 함께 적는다 (D-178). 🔴 실제 실행은 DB 사전이 파일과 같을 때만 돈다(`check_dict`)
    stamp: dict[str, Any] = {"golden_sha": _sha12(GOLDEN), "conditional": a.conditional}
    stamp |= {"split": "dev" if a.dev else "test_sentence"} | dev_stamp
    stamp |= use_encoder(a.encoder)
    t0 = time.perf_counter()
    if a.stub:
        preds = run(rows, stub_runner(), conditional=a.conditional)
    else:
        from app.db import pg_connect  # noqa: PLC0415 — DB 가 없어도 --stub 은 돈다

        review = g.build_review()
        with pg_connect() as conn, conn.cursor() as cur:
            stamp |= check_dict(cur)
            cfg = {"configurable": {"conn": cur}}
            preds = run(
                rows,
                lambda t, p: review.invoke({"text": t, "product": p}, config=cfg),
                conditional=a.conditional,
            )
    secs = time.perf_counter() - t0
    s = summarize(rows, preds)
    if not a.dev and not a.stub:
        n_runs = log_sealed_run(
            stamp
            | {
                "judged_by": g.JUDGED_BY,
                "rows": len(rows),
                "limit": a.limit,
                "provenance": a.provenance,
            }
        )
        print(
            f"  🔒 봉인 평가셋 실행 — 이 기기 기록 {n_runs}번째 ({SEALED_LOG}) · 원장에 판 표지와 함께 옮긴다 (D-175)"
        )
    report(s, a.conditional, dev=a.dev)
    print(
        f"\n  실행 {secs:.0f}초 · 행당 {secs / max(len(rows), 1) * 1000:.0f} ms · judged_by {g.JUDGED_BY}"
        f" · " + " · ".join(f"{k} {v}" for k, v in stamp.items())
    )
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(
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
        print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
