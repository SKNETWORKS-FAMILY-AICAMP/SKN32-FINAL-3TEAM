"""
판정 로직 2단계 — **판정** (🔄 2026-09-29 계약 준수판 · 박수진)

1단계 신호(judge_stage1.stage1_signals)를 받아 **계약의 상태**(`app.contracts.Verdict` · `HoldReason`)로 판정한다.

상태 (D-127)
  confirmed  코드(사전 · 근거 인용 있음)와 인코더(τ 이상)가 **같은 유형에 합의**할 때만.
             신호가 하나도 없고 모든 유형 확률이 τ × QUIET_MARGIN 미만이면 `confirmed` · 위반 없음 (τ 근처는 near_threshold → hold · 방안 (다)) — 🚨 위험도(assess_risk)가 없으므로 **통과가 아니다**(`is_pass` · D-273).
             「적법」이라 부르지 않는다 (D-130).  ⬜ 이 처리는 팀장 판정 대기(그래프 비교 문서 6절 ②)
  no_basis   유형은 규칙으로 정해졌는데 붙일 조문 인용이 없을 때 (D-127 · D-224 — 근거 없이 confirmed 로 올리지 않는다)
  hold       그 밖 — 사유코드 필수: low_conf · cat_unknown · premise_unknown · law_uncovered (계약 HoldReason)

품목 전제 (D-229 · D-263 · D-276)
  · 품목을 모르면 전제 다섯(`app.contracts.Premise`)을 **처음에 전부 계산**해 `branches` 로 싣는다(D-276 ⑦).
  · 전제마다 결과가 **같으면** 그 결과를 쓰고, **갈리면** 보류 — 품목 모름 `cat_unknown` · 건기식인데 인정 여부 모름 `premise_unknown` (D-229).
  · 기록되는 판정은 이것 하나다. 사용자가 전제를 고른 결과는 `apply_selection()` 이 **따로** 싣는다 —
    판정을 덮어쓰지 않고, 「전제부 결과」 뱃지 · 통과 뱃지 없음 · 「사업자가 선택한 값이며 확인되지 않았습니다」(D-263 · D-276 ⑤).
  · 첫 검수는 묻지 않는다 — 질문은 재검수 흐름(`reinspect_question`)에서만, 판별 결과를 기본 선택으로 (D-276 ④).

전제별 규칙 (신호 kind → 전제)
  approved_phrase · overlap (전제로 갈리는 신호)
    식품 · 일반상품      건기식 아님 → 그 유형 위반 (인용 + 인코더 합의 → confirmed · 인용 없음 → no_basis · 인용 있으나 불합의 → hold)
    건기식_인정          승인 문구 모양 ∧ 유형이 건기식_오인 · 거짓_과장 → 해소. 그 밖(질병 · 의약품 · 단정형)은 hold —
                         사용자의 선택은 「적법이 되는 단서」를 열지 않는다 (D-229 ④)
    건기식_비인정        건기식_오인은 **건기식에 성립하지 않는다**(D-229 표) → hold(호 재지정 필요) · 그 밖 유형은 식품과 같다
    화장품               규칙 없음 → hold
  dict · dict_weak · model (전제와 무관한 신호)
    dict ∧ 인용 ∧ 인코더 합의 → confirmed · 그 밖 → hold(low_conf)
    건기식 전제에서 건기식_오인 신호는 성립하지 않으므로 hold 로 남기고 표시한다 (D-229)
"""
from __future__ import annotations

import json
from typing import Optional

from judge_stage1 import (QUIET_MARGIN, load_banned_terms, load_encoder, predict_label_probs, resolve_model_dir,
                          stage1_signals)
from app.contracts import Category, HoldReason, Premise, Verdict, Violation

HF = Violation.건강기능식품_오인.value
#: 건기식_인정 전제가 풀어 주는 유형 — 승인 문구 모양일 때만. 질병 · 의약품은 인정 건기식도 금지(식품표시광고법 제8조 ① 1·2호 · D-229 ④)
RESOLVED_BY_RECOGNITION = {HF, Violation.거짓_과장.value}
NOTICE_USER_SELECTED = "사업자가 선택한 값이며 확인되지 않았습니다"  # D-229 ⑤ · D-276 ⑤


def _premises(category: Optional[Category], recognized: Optional[bool]) -> list[Premise]:
    if category is None:
        return list(Premise)
    if category is Category.건기식:
        if recognized is None:
            return [Premise.건기식_인정, Premise.건기식_비인정]
        return [Premise.건기식_인정 if recognized else Premise.건기식_비인정]
    if category is Category.전용법_미수록:
        return []  # 전제가 아니다 — 판정할 법이 없다 (D-277)
    return [Premise(category.value)]


def judge_under(signals: list[dict], premise: Premise) -> dict:
    """전제 하나를 가정했을 때의 결과."""
    hedged = any(s["kind"] == "approved_phrase" for s in signals)
    confirmed, no_basis, hold, notes, basis = [], [], [], [], []

    def violate(s):
        if s["basis"] and s["model_agrees"]:
            confirmed.append(s["type"]); basis.extend(s["basis"])
        elif s["basis"]:
            hold.append(s["type"]); notes.append(f"{s['type']}: 사전 인용은 있으나 인코더 불합의")
        else:
            no_basis.append(s["type"])

    for s in signals:
        t = s["type"]
        if s["kind"] == "trade_condition":
            hold.append("거래조건"); notes.append("거래 조건 — 표시광고법이 주 근거 · 광고 문구만으로 사실을 판정할 수 없다 (D-272 개정 ②)")
            continue
        is_hf_premise = premise in (Premise.건기식_인정, Premise.건기식_비인정)
        if s["premise"]:
            if premise in (Premise.식품, Premise.일반상품):
                violate(s)
            elif premise is Premise.건기식_인정:
                if hedged and t in RESOLVED_BY_RECOGNITION:
                    continue
                hold.append(t)
            elif premise is Premise.건기식_비인정:
                if t == HF:
                    hold.append(t); notes.append("건기식_오인은 건기식에 성립 안 함(D-229) — 인정 범위 밖 표방 · 호 재지정 필요")
                else:
                    violate(s)
            else:  # 화장품
                hold.append(t); notes.append(f"{premise.value} 전제 규칙 없음")
        else:
            if is_hf_premise and t == HF:
                hold.append(t); notes.append("건기식_오인은 건기식에 성립 안 함(D-229)")
            elif s["kind"] == "dict" and s["basis"] and s["model_agrees"]:
                confirmed.append(t); basis.extend(s["basis"])
            else:
                hold.append(t)

    if hold:
        verdict, reason = Verdict.hold, HoldReason.low_conf
    elif no_basis:
        verdict, reason = Verdict.no_basis, None
    else:
        verdict, reason = Verdict.confirmed, None  # 위반 있음 또는 신호 없음 — 위험도 미산정이라 통과 아님
    return {"verdict": verdict.value, "hold_reason": reason.value if reason else None,
            "violations": sorted(set(confirmed)), "no_basis_types": sorted(set(no_basis)),
            "hold_types": sorted(set(hold)), "basis": sorted(set(basis)), "notes": notes}


def _key(r: dict) -> tuple:
    return (r["verdict"], tuple(r["violations"]), tuple(r["no_basis_types"]), tuple(r["hold_types"]))


def stage2_judge(stage1_result: dict, category: Optional[Category] = None, recognized: Optional[bool] = None) -> dict:
    """기록되는 판정 하나 + (전제가 여럿이면) 전제별 결과. 🔴 사용자 선택은 여기서 받지 않는다 — apply_selection()."""
    sig = stage1_result["signals"]
    premises = _premises(category, recognized)
    base = {"text": stage1_result["text"], "category": category.value if category else None,
            "signals": sig, "dict_backed": any(s["kind"] == "dict" for s in sig), "review_questions": [],
            "subject": stage1_result.get("subject"), "not_claim": bool(stage1_result.get("not_claim"))}

    if category is Category.전용법_미수록:
        r = judge_under(sig, Premise.일반상품)  # 표시광고법만 — 우리가 안 가진 법이 있다
        if r["verdict"] == Verdict.confirmed.value and not r["violations"]:
            r = {**r, "verdict": Verdict.hold.value, "hold_reason": HoldReason.law_uncovered.value}
        return {**base, **r, "branches": {}}

    branches = {p.value: judge_under(sig, p) for p in premises}
    if len(branches) == 1 or len({_key(r) for r in branches.values()}) == 1:
        rec = next(iter(branches.values()))
        return {**base, **rec, "branches": branches if len(branches) > 1 else {}}

    reason = HoldReason.premise_unknown if category is Category.건기식 else HoldReason.cat_unknown
    conservative = Premise.건기식_비인정 if category is Category.건기식 else Premise.식품  # 인정 없음 (D-263 ①)
    merged = {k: sorted({x for r in branches.values() for x in r[k]}) for k in ("violations", "no_basis_types", "hold_types", "basis")}
    return {**base, "verdict": Verdict.hold.value, "hold_reason": reason.value, **merged,
            "notes": ["전제에 따라 결과가 갈림 — 전제별 결과는 branches"],
            "branches": branches, "conservative_premise": conservative.value}


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
    sig = ", ".join(f"{x['kind']}:{x['type']}({x['prob']}{'✓' if x['model_agrees'] else ''})" for x in s2["signals"])
    tag = " [사전근거]" if s2.get("dict_backed") else ""
    nc = " (판정 대상 아님)" if s2.get("not_claim") else ""
    head = f"[{s2['verdict']}{'(' + s2['hold_reason'] + ')' if s2.get('hold_reason') else ''}]{nc}{tag} · 사항:{s2.get('subject')} · {s2['text']}"
    lines = [head, f"    신호: {sig or '없음'}",
             f"    확정 {s2['violations'] or '-'} · 근거없음 {s2['no_basis_types'] or '-'} · 보류 {s2['hold_types'] or '-'}"]
    if s2.get("branches"):
        lines.append("    전제별: " + " · ".join(f"{p}→{r['verdict']}{r['violations'] or r['no_basis_types'] or ''}"
                                                   for p, r in s2["branches"].items()))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--category", default=None, choices=[c.value for c in Category], help="품목을 안다고 가정 (기본: 모름)")
    ap.add_argument("--recognized", default=None, choices=["yes", "no"], help="건기식일 때 인정 여부")
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--margin", type=float, default=QUIET_MARGIN, help="여유 구간 (τ 배수 · 1.0 이면 끔)")
    ap.add_argument("texts", nargs="*")
    a = ap.parse_args()

    tok, mdl, labels, th = load_encoder(resolve_model_dir(a.model))
    book = load_banned_terms()
    cat = Category(a.category) if a.category else None
    rec = None if a.recognized is None else a.recognized == "yes"
    print(f"[INFO] 사전 {len(book.entries)}건 · 품목: {a.category or '모름(첫 검수)'}\n")

    samples = a.texts or [
        "이 제품을 드시면 당뇨가 완치됩니다",
        "맛있게 즐기실 수 있는 건강한 간식입니다",
        "이 크림 하나면 주름이 싹 사라지고 피부가 20대로 돌아갑니다",
        "이 영양제는 관절 건강에 도움을 주는 기능성 원료를 함유하고 있습니다",
        "이 제품은 관절 건강 유지에 도움을 줄 수 있는 원료로 만들었습니다",
        "이 제품은 기억력 개선에 도움을 줄 수 있습니다",
        "1일 2회, 1회 2정을 충분한 물과 함께 섭취하십시오",
        "바쁜 직장인, 운동을 즐기시는 분께 추천합니다",
        "직사광선을 피해 서늘한 곳에 보관하십시오",
        # 거래 조건 — 식품표시광고법 판정 대상은 아니지만 표시광고법 대상이다. not_claim(판정 대상 아님)이 아니다 (D-272 개정)
        "전 상품 무료배송, 오늘 주문 시 내일 도착",
    ]
    for t in samples:
        s2 = stage2_judge(stage1_signals(t, predict_label_probs(t, tok, mdl, labels), book, th, margin=a.margin), category=cat, recognized=rec)
        print(brief(s2) if a.brief else json.dumps(s2, ensure_ascii=False, indent=2))
