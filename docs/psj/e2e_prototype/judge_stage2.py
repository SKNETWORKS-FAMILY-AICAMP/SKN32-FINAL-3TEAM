"""
판정 로직 2단계 — **판정** (🔄 2026-10-06 main `ebb3f10` 맞춤판 · 박수진)

🔄 2026-10-06 — **규칙 판정은 판정 그래프의 함수를 그대로 부른다.** 여기에 또 적지 않는다 (D-99).
  · 사전 적중 → 법별로 거르기 → 문장 판정 → 전제별 분기 → 기록되는 판정:
    `graph.NODES[law_*]` · `graph.judge`(`_judge_one`) · `graph._premise_sentences` · `graph._recorded` · 전제 표 `app/premise.py`.
  · 그래서 D-269(사전 침묵은 보류) · D-311(자격 없는 적중은 유형 후보) · D-314(주된 광고법을 안 본 품목은 통과 없음) ·
    D-319(품목을 모르면 모든 전제에서 같은 위반일 때만 확정 · 전제가 유형을 바꾸는 자리)는 **그래프와 같은 코드**로 선다.
  · 이 파일이 더하는 것은 하나다 — **인코더 층**(`adjust`). 그래프의 `encode` 노드가 비어 있어 아직 없는 자리다.
  ⛔ 종전 판(09-29)은 전제 규칙을 여기 따로 적었다 — D-319 가 들어온 뒤 그래프와 어긋났다. 그 사본을 지웠다.

인코더 층 — `[제안]` · 팀장 판정 대기. 규칙 판정 하나(문장 · 전제)를 받아 인코더 신호로 고친다
  ① 사전이 확정한 위반 (단독판정 적중 · 인용 있음)
       인코더가 **같은 유형**에 τ 이상이면 확정 그대로 (D-127 「확정 = 코드 · 인코더 합의」)
       인코더가 그 유형에 조용하면 → `hold(low_conf)` · 유형은 후보로 남긴다   ← `agree=False` 면 이 줄을 끈다(그래프의 지금 규칙 D-269)
  ② 사전이 보류로 둔 문장 (침묵 · 자격 없는 적중)
       인코더 후보가 있다        → `hold(low_conf)` 그대로 · 후보 유형을 싣는다. 🔴 **인코더만으로 확정하지 않는다** — 붙일 조문이 없다 (D-224 · D-131)
       거래 조건 문장            → 보류 그대로(통과 · `not_claim` 없음). 후보는 표시광고법에 자리가 있는 유형만 싣는다 (D-272 개정)
       여유 구간(τ × margin 이상) → 보류 그대로
       사전도 인코더도 조용하다  → **확정 · 위반 없음 · R0** (D-273). 표지가 「판정 대상 아님」이면 `not_claim` (D-275)
                                   🔴 사전이 한 낱말이라도 울렸으면(자격 없는 적중 · 다른 법의 인용 포함) 이 줄로 가지 않는다
                                   🔴 주된 광고법을 안 본 품목이면 `hold(law_uncovered)` — 통과가 없다 (D-314)
  ③ 전제가 유형을 바꾸는 자리 (D-319 ④′) — 건강기능식품 전제 둘 · 일반식품 기능성에서 인코더의 `건강기능식품_오인` 후보는 서지 않는다.
       `건기식_비인정` 에서는 그 자리에 `거짓_과장`([별표 1] 4.나 · 인정하지 않은 기능성)이 선다.
  ④ 품목 미확정에는 통과가 없다 (D-319 ②) — 전제마다 「위반 없음」이어도 `일반상품` 전제가 통과를 내지 못하므로 `hold(cat_unknown)` + 분기다.
       「판정 대상 아님」 문장은 문장 판정으로는 확정(`not_claim`)이지만 종착은 통과가 아니라 보류다.
  ⑤ 사전 확정에 합의를 묻는 것은 **인코더가 낼 수 있는 유형**뿐이다 — 편입 대기 칸(`기능성화장품_오인` · τ 1.01)은 사전이 그대로 선다.

이 파일이 **하지 않는 것**
  · 조문 검색(`retrieve`) · 위험도 하한(`assess_risk` 의 제재표) — DB 가 있어야 한다. 그래서 확정 위반에는 위험도가 없고 종착은 보류다.
  · 문장 분할 — 한 줄을 한 문장으로 본다(골든의 행이 문장 단위다).
  · 인코더로 위험도를 올리는 것(D-131 근거 스팬 조건부) — 지금 모델은 스팬을 내지 않는다.
"""
from __future__ import annotations

import json
from typing import Optional

from judge_stage1 import (QUIET_MARGIN, load_banned_terms, load_encoder, predict_label_probs, resolve_model_dir,
                          stage1_signals)
from app import graph as g
from app import premise as pm
from collect import statute
from app.contracts import (UNCOVERED_CATEGORIES, Branch, Category, HoldReason, Outcome, Premise, ProductContext, Risk,
                           RiskAssessment, SentenceJudgment, Verdict, Violation, is_pass)

HF = Violation.건강기능식품_오인
#: 표시광고법 제3조① 1 ~ 4호에 자리가 있는 유형 — 조문 표(`collect/statute.py`)에서 읽는다. 거래 조건 문장의 후보는 이 안에서만 낸다
FTC_TYPES = frozenset(Violation(t) for n in (1, 2, 3, 4)
                      if (t := statute.type_of(f"{statute.STATUTE_ID['표시광고법']}:제3조제1항제{n}호")))
#: `[제안]` 사전 확정에 인코더 합의를 요구하는가 (D-127). False 면 그래프의 지금 규칙(D-269 「사전 적중 = 위반 확정」) 그대로다.
AGREE_REQUIRED = True
NOTICE_USER_SELECTED = "사업자가 선택한 값이며 확인되지 않았습니다"  # D-229 ⑤ · D-276 ⑤
R0 = RiskAssessment(floor=Risk.R0, final=Risk.R0)
_OUTCOME = {"hold": Outcome.hold, "certificate": Outcome.certificate, "guidance": Outcome.guidance, "passed": Outcome.passed}


def _remake(j: SentenceJudgment, **upd) -> SentenceJudgment:
    """고친 **새 문장** — 계약 검증을 다시 지난다(`graph._with_risk` 와 같은 방식)."""
    return SentenceJudgment(**{**{k: getattr(j, k) for k in type(j).model_fields}, **upd})


def rule_state(text: str, scan: g.DictScan, category: Optional[Category]) -> dict:
    """그래프 상태 — 사전 훑기까지 끝난 것. 법별 노드 · 대조(`merge_laws`)를 그래프의 함수로 돈다. 검색 근거는 없다(DB 없음)."""
    state: dict = {"text": text, "sents": [text], "product": ProductContext(category=category),
                   "dict_scans": [scan], "evidence": []}
    state["laws"] = g.laws_for(category)
    state["law_results"] = [g.NODES[name](g.law_payload(state))["law_results"][0] for name in g.route_laws(state)]
    g.merge_laws(state)      # 🔴 보낸 법이 전부 돌아왔는가 (D-220)
    return state


def encoder_candidates(enc: dict, premise: Optional[Premise]) -> list[Violation]:
    """인코더 후보 — 전제가 유형을 바꾸는 자리를 적용한 것 (D-319 ④′ ① ② ④ · `app/premise.py`)."""
    c = {Violation(x) for x in enc["candidates"]}
    if premise in pm.NO_HF_MISLEAD and HF in c:
        c.discard(HF)                                   # 3호 「건강기능식품이 아닌 것을」 — 이 전제에서는 서지 않는다
        if premise is Premise.건기식_비인정:
            c.add(Violation.거짓_과장)                   # [별표 1] 4.나 — 인정하지 않은 기능성
    return sorted(c, key=lambda v: v.value)


def adjust(j: SentenceJudgment, enc: dict, scan: g.DictScan, *, premise: Optional[Premise] = None,
           category: Optional[Category] = None, agree: bool = AGREE_REQUIRED) -> tuple[SentenceJudgment, str]:
    """**인코더 층** — 규칙 판정 하나를 인코더 신호로 고친다. `(고친 판정, 까닭)`. 모듈 머리말의 ① ~ ③."""
    cat = pm.PREMISE_CATEGORY[premise] if premise is not None else category
    cands = encoder_candidates(enc, premise)
    if j.verdict is Verdict.confirmed and j.violations:
        if not agree:
            return j, "사전 확정 (인코더 합의를 보지 않음 · D-269)"
        askable = {v for v in j.violations if v.value in enc.get("active", ())}
        if not askable:
            # 인코더가 내지 않는 유형(편입 대기 칸 · 이 모델에 없는 유형)에는 합의를 물을 수 없다 — 사전이 선다 (D-269)
            return j, "사전 확정 — 인코더가 내지 않는 유형이라 합의를 묻지 않는다 (D-269 · D-321)"
        if askable & set(cands):
            return j, "사전 확정 · 인코더 합의 (D-127)"
        return (_remake(j, verdict=Verdict.hold, hold_reason=HoldReason.low_conf, infeasibility=None, spans=[],
                        risk=RiskAssessment()),
                "사전 적중 · 인코더 불합의 → 보류 (D-127)")
    if j.verdict is Verdict.hold and j.hold_reason is HoldReason.low_conf:
        if enc["subject"] == "거래조건":
            # 거래 조건(가격 · 할인 · 환불 · 배송)의 주 근거는 표시광고법이다 (D-272 개정 ②) — 그 법에 자리가 있는 유형만 후보로 싣는다.
            # 🔴 통과로도 `not_claim` 으로도 내지 않는다 — 사실 확인이 필요한 보류다 (D-272 개정 ①)
            cands = [v for v in cands if v in FTC_TYPES]
            if not cands:
                return j, "거래 조건 — 표시광고법 사실 확인이 필요하다 (D-272 개정)"
            merged = sorted(set(j.violations) | set(cands), key=lambda v: v.value)
            return _remake(j, violations=merged), "거래 조건 · 인코더 후보(표시광고법 유형만) → 보류 (D-272 개정)"
        if cands:
            merged = sorted(set(j.violations) | set(cands), key=lambda v: v.value)
            return _remake(j, violations=merged), "인코더 후보 → 보류 · 유형 후보 (D-224 · D-131)"
        if scan.hits or scan.weak:
            return j, "사전이 울렸다 — 통과로 내지 않는다 (D-311 · D-319)"
        if not enc["quiet"]:
            return j, "여유 구간 또는 이 전제에서 서지 않는 후보 → 보류"
        not_claim = enc["subject"] == "판정대상아님"
        if cat in UNCOVERED_CATEGORIES and not not_claim:
            return (_remake(j, hold_reason=HoldReason.law_uncovered, violations=[], evidence=[], risk=R0),
                    "주된 광고법을 안 본 품목 — 통과 없음 (D-314)")
        return (_remake(j, verdict=Verdict.confirmed, hold_reason=None, violations=[], evidence=[], risk=R0,
                        not_claim=not_claim),
                "판정 대상 아님 (D-275)" if not_claim else "사전 · 인코더 모두 조용 → 확정 · 위반 없음 (D-273)")
    return j, "규칙 판정 그대로"


def _view(j: SentenceJudgment, why: str = "") -> dict:
    types = [v.value for v in j.violations]
    return {"verdict": j.verdict.value, "hold_reason": j.hold_reason.value if j.hold_reason else None,
            "violations": types if j.verdict is Verdict.confirmed else [],
            "no_basis_types": types if j.verdict is Verdict.no_basis else [],
            "hold_types": types if j.verdict is Verdict.hold else [],
            "not_claim": j.not_claim, "pass": is_pass(j),
            "infeasibility": j.infeasibility.value if j.infeasibility else None, "why": why}


def _passes(j: SentenceJudgment) -> bool:
    return j.verdict is Verdict.confirmed and not j.violations


def stage2_judge(stage1_result: dict, category: Optional[Category] = None, agree: bool = AGREE_REQUIRED,
                 encoder: bool = True) -> dict:
    """기록되는 판정 하나 + 전제별 분기. 규칙은 그래프의 함수 · 인코더는 `adjust`.

    돌려주는 dict 의 `state` 는 그래프 상태 모양(`sentences` · `branches` · `outcome`)이다 —
    팀장 평가 도구(`scripts/eval_graph.py` 의 `predict` · `summarize`)에 그대로 넣을 수 있다.
    `encoder=False` 면 인코더 층을 건너뛴다 — **규칙만**의 결과다(같은 행에서 인코더가 바꾼 것을 재는 기준).
    `pass_blocked` — 사전도 인코더도 조용한데 품목을 몰라 보류로 내린 문장이다(품목을 고르면 그 분기에서 통과가 보인다).
    """
    text, scan, enc = stage1_result["text"], stage1_result["scan"], stage1_result["enc"]
    state = rule_state(text, scan, category)
    rule = g.judge(state)["sentences"][0]                       # 인코더 전 규칙 판정 (그래프와 같다)
    if encoder:
        layer = adjust
    else:
        def layer(j, enc, scan, **_):                           # 규칙만 — 아무것도 고치지 않는다
            return j, "규칙만 (인코더 층 끔)"
    base, why = layer(rule, enc, scan, category=category, agree=agree)

    premises = pm.PREMISES_OF[category]
    per: dict[Premise, tuple[SentenceJudgment, str]] = {}
    branches: list[Branch] = []
    recorded, rec_why = base, why
    pass_blocked = False        # 통과였는데 품목 · 전제를 몰라 보류로 내린 문장인가 (D-319 ②)
    if len(premises) >= 2:
        if not pm.criteria_ready(premises):
            raise SystemExit("🔴 전제의 기준 문안이 비었다 — 분기를 낼 수 없다 (D-319 ③ · `app/premise.py` CRITERIA)")
        per = {p: layer(g._premise_sentences(p, state, [])[0], enc, scan, premise=p, agree=agree) for p in premises}
        same = len({g._judgment_key(j) for j, _ in per.values()}) == 1
        if category is None or not same:                         # 품목을 모르면 같아도 분기를 낸다 (D-229 ⑥ · D-319 ②)
            reason = HoldReason.cat_unknown if category is None else HoldReason.premise_unknown
            rec = g._recorded(base, [j for j, _ in per.values()], reason)
            if rec is not None:
                recorded, rec_why = rec, ("모든 전제에서 같은 위반 → 확정 (D-319 ①)" if rec.verdict is Verdict.confirmed
                                          else "전제에 따라 갈린다 → 보류 + 분기 (D-319 ①)")
            elif _passes(recorded) and not all(_passes(j) for j, _ in per.values()):
                # `[제안]` D-319 ② — 품목 미확정에는 통과 표시가 없다. 통과를 내지 못하는 전제(일반상품 등)가 하나라도 있으면 보류 + 분기
                recorded = _remake(recorded, verdict=Verdict.hold, hold_reason=reason, not_claim=False, risk=R0)
                rec_why = "통과를 내지 못하는 전제가 있다 → 보류 + 분기 (D-319 ②)"
                pass_blocked = True
            elif category is not None and recorded.verdict is Verdict.hold and recorded.hold_reason is HoldReason.low_conf:
                # `[제안]` 품목을 아는데 전제가 후보를 바꾼다(건강기능식품의 3호 → 4호 나목 등) — 그 품목의 어느 전제에서도
                #   서지 않는 유형을 후보로 남기지 않는다. 후보 = 그 품목의 전제들에서 서는 후보의 합 (D-319 ④′)
                union = sorted({v for j, _ in per.values() if j.verdict is Verdict.hold for v in j.violations},
                               key=lambda v: v.value)
                if union != list(recorded.violations):
                    recorded = _remake(recorded, violations=union)
                    rec_why += " · 후보는 이 품목의 전제에서 서는 것만"
            branches = [Branch(premise=p, outcome=_OUTCOME[_route([j], pm.PREMISE_CATEGORY[p])], sentences=[j],
                               criteria=pm.CRITERIA[p]) for p, (j, _) in per.items()]

    outcome = _OUTCOME[_route([recorded], category)]
    out = {"text": text, "category": category.value if category else None, **_view(recorded, rec_why),
           "rule": _view(rule), "dict_backed": bool(scan.hits), "pass_blocked": pass_blocked,
           "dict_terms": sorted({h.term for h in scan.hits}), "weak_terms": sorted({h.term for h in scan.weak}),
           "subject": enc["subject"], "enc_candidates": list(enc["candidates"]), "enc_near": enc["near"],
           "branches": {p.value: _view(j, w) for p, (j, w) in per.items()} if branches else {},
           "outcome": outcome.value,
           "state": {"sentences": [recorded], "branches": branches, "outcome": outcome}}
    return out


def _route(sents: list[SentenceJudgment], category: Optional[Category]) -> str:
    """종착 — 그래프의 라우터 그대로. 지시는 재료가 다 있을 때만(`graph._branch_outcome` 과 같은 규칙)."""
    name = g.route_review({"sentences": sents, "product": ProductContext(category=category)})
    if name == "passed" and category is None:
        return "hold"        # `[제안]` 품목 미확정에는 통과 표시가 없다 (D-319 ②) — 그래프에는 아직 이 길이 없다(인코더 전에는 통과가 안 난다)
    return "hold" if name == "guidance" and not g.guidance_ready(sents) else name


def reinspect_question(detected: Optional[Category] = None) -> dict:
    """재검수 때만 묻는다 (D-276). 판별 결과를 기본 선택으로 (D-276 ④)."""
    default = None
    if detected is Category.건기식:
        default = Premise.건기식_비인정.value  # 인정 여부는 판별로 알 수 없다 — 보수적 기본
    elif detected is not None and detected is not Category.전용법_미수록:
        default = detected.value
    return {"type": "품목", "question": "이 제품의 품목을 골라 주세요 (건강기능식품이면 광고한 기능이 식약처 인정 범위 안인지도)",
            "options": [p.value for p in Premise] + ["모름"], "default": default}


def apply_selection(stage2_result: dict, premise: str, detected: Optional[Category] = None) -> dict:
    """재검수 — 사용자가 고른 전제의 결과를 **따로** 싣는다. 기록되는 판정(verdict)은 바꾸지 않는다 (D-263 ① · D-276)."""
    if premise == "모름" or premise not in stage2_result.get("branches", {}):
        return {**stage2_result, "premise_selection": {"premise": premise, "applied": False}}
    matches = detected is not None and detected.value == premise.split("_")[0]
    return {**stage2_result, "premise_selection": {
        "premise": premise, "source": "user_selected", "applied": True,
        "badge": "전제부 결과", "pass_badge": False,
        "notice": None if matches else NOTICE_USER_SELECTED,
        "result": stage2_result["branches"][premise]}}


def brief(s2: dict) -> str:
    def one(v: dict) -> str:
        return (v["verdict"] + (f"({v['hold_reason']})" if v.get("hold_reason") else "")
                + (" 판정대상아님" if v.get("not_claim") else "")
                + (f" 확정{v['violations']}" if v["violations"] else "") + (f" 후보{v['hold_types']}" if v["hold_types"] else "")
                + (f" 근거없음{v['no_basis_types']}" if v["no_basis_types"] else ""))
    lines = [f"[{one(s2)}] · 사항:{s2['subject']} · {s2['text']}",
             f"    규칙만: {one(s2['rule'])}  →  인코더 층: {s2['why']}",
             f"    사전 {s2['dict_terms'] or '-'} · 자격 없는 적중 {s2['weak_terms'] or '-'} · 인코더 후보 {s2['enc_candidates'] or '-'}"
             + (f" · 여유 구간 {s2['enc_near']}" if s2.get("enc_near") else "")]
    if s2.get("branches"):
        lines.append("    전제별: " + " · ".join(f"{p}→{one(r)}" for p, r in s2["branches"].items()))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--category", default=None, choices=[c.value for c in Category], help="품목을 안다고 가정 (기본: 모름)")
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--margin", type=float, default=QUIET_MARGIN, help="여유 구간 (τ 배수 · 1.0 이면 끔)")
    ap.add_argument("--dict-stands", action="store_true", help="사전 확정에 인코더 합의를 요구하지 않는다 (그래프의 지금 규칙 · D-269)")
    ap.add_argument("texts", nargs="*")
    a = ap.parse_args()

    tok, mdl, labels, th = load_encoder(resolve_model_dir(a.model))
    book = load_banned_terms()
    cat = Category(a.category) if a.category else None
    print(f"[INFO] 사전 {len(book.entries)}건 · 품목: {a.category or '모름(첫 검수)'} · 판정 규칙 {g.JUDGED_BY} + 인코더 층\n")

    samples = a.texts or [
        "이 제품을 드시면 당뇨가 완치됩니다",
        "맛있게 즐기실 수 있는 건강한 간식입니다",
        "이 크림 하나면 주름이 싹 사라지고 피부가 20대로 돌아갑니다",
        "이 제품은 기억력 개선에 도움을 줄 수 있습니다",
        "1일 2회, 1회 2정을 충분한 물과 함께 섭취하십시오",
        "직사광선을 피해 서늘한 곳에 보관하십시오",
        "전 상품 무료배송, 오늘 주문 시 내일 도착",
    ]
    for t in samples:
        s1 = stage1_signals(t, predict_label_probs(t, tok, mdl, labels), book, th, margin=a.margin)
        s2 = stage2_judge(s1, category=cat, agree=not a.dict_stands)
        if a.brief:
            print(brief(s2))
        else:
            print(json.dumps({k: v for k, v in s2.items() if k != "state"}, ensure_ascii=False, indent=2))
