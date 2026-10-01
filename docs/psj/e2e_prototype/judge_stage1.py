"""
판정 로직 1단계 — **신호 모음** (🔄 2026-09-29 계약 준수판 · 박수진)

문장 하나에서 세 가지 체로 **신호**를 모은다. 🔴 이 단계는 판정하지 않는다 — 판정(상태 · 유형 · 전제)은 2단계가 낸다.

  ① 승인 기능성 문구 모양   APPROVED_PHRASE 정규식          → approved_phrase  (품목 전제로 갈림 · D-156)
  ② 금지 표현 사전          banned_terms.jsonl · dictmatch  → dict / overlap / dict_weak
  ③ 판정 인코더             KcBERT 확정 6종 · 유형별 τ      → model

계약 · 결정과 맞춘 것
  · 사전 매칭은 **`app/dictmatch.py` 한 곳**을 쓴다 — 정규화 · 부분문자열 규칙 · 원문 좌표가 판정 그래프와 같다
    (dictmatch docstring · D-117). ⛔ 종전 사본 `norm()` 은 지웠다 — 항목 쪽을 정규화하지 않아 적중이 달랐다.
  · 사전은 **후보**다 — 적중만으로 위반을 확정하지 않는다 (D-127 「확정 = 코드 · 인코더 합의」 · D-155).
  · 사전 · 모델 파일이 없으면 **멈춘다** (D-220 fail-closed). ⛔ 종전: 경고 뒤 빈 사전으로 진행 → 사전이 잡을 문장이 신호 없음.
  · 인코더 τ 는 모델 폴더의 `label_scheme.json`(dev 실측 · D-131)만 쓴다. 없으면 멈춘다 — 0.5 같은 대체값을 두지 않는다.
  · 「적법」이라는 말을 쓰지 않는다 (D-130). 신호가 없다는 것은 「신호 없음」일 뿐이다.

⬜ 팀장 판정 · 이관 대기 (이 파일이 정하지 않는 것)
  · APPROVED_PHRASE 는 `[임의]` 값이다 — 판정 파라미터 단일 출처(`app/settings.py` PARAMS · D-209) 또는
    사전 데이터(`preprocess/dictionary.py` · 승인 문구 종류)로 옮기는 것은 팀장 판정 뒤 (D-99 · D-117).
  · 사전은 DB `dict_entry` 가 정본이다(`graph.load_dict_entries`). 로컬 실행용으로 같은 원천(`banned_terms.jsonl` —
    `scripts/load_db.load_dict` 의 입력)을 읽는다. 단독판정 아닌 항목(적법중첩 · 모호)은 DB 에 `exact_match=false` 로만 있다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from app import dictmatch as dm  # noqa: E402 — 매칭 규칙은 한 곳 (D-117)
from app.contracts import Violation  # noqa: E402

BANNED_TERMS_PATH = os.path.join(REPO, "data", "derived", "banned_terms.jsonl")

#: `[임의]` 승인 기능성 문구 모양 — 식약처 인정 문구의 꼴(「~에 도움을 줄 수 있음」).
#: 바꾸는 조건: 사전 데이터(승인 문구 종류)로 이관되면 지운다 · 🔜 PARAMS/사전 이관 요청 (D-209 · D-117)
APPROVED_PHRASE = re.compile(r"도움을?\s*줄\s*수\s*있|도움이\s*될\s*수\s*있")
APPROVED_PHRASE_TYPE = Violation.건강기능식품_오인.value

#: `[임의]` 여유 구간 (09-30 · 방안 (다)) — 신호가 하나도 없어도 어느 유형의 확률이 τ × QUIET_MARGIN 이상이면
#: 「조용하지 않다」로 보고 보류(low_conf)로 보낸다. τ 바로 아래(예: 거짓 .64 vs τ .65)의 문장이 confirmed(위반 없음)로 새지 않게.
#: 🔄 09-30 sweep (dev 325행 + 추가 파일 홀드아웃 · 모델 +inj4c+negd4 · test 안 봄) → 0.5
#:    margin   aux(6종 밖 실제 위반) 놓침   negd4 홀드아웃(D형) 조용함   inj4c 놓침
#:     1.0        22/44                      46/52                     1/42
#:     0.5         7/44                      28/52                     0/42   ← 채택 (효과 대부분 · D 비용 절반)
#:     0.4         0/44                      17/52                     0/42
#:    ⚠️ 비방광고가 확정 6종에 들어오면 aux 효과를 인코더가 직접 맡는다 → 새 모델로 sweep 을 다시 돌린다(0.9 근처 예상)
#: 바꾸는 조건: 새 모델 · 새 τ · 6종 변경 · 팀장 판정 뒤 PARAMS 로 이관 (D-209)
QUIET_MARGIN = 0.5

# ══════════════════════════════════════════════════════════════════════
#  사항 판별 (🆕 09-30) — 판정이 아니라 **인코더 점수를 어디에 쓸지** 가르는 표지
# ══════════════════════════════════════════════════════════════════════
#: 근거 — D-272 개정 ② 「가격 · 할인율 · 비교 가격 · 환불 · 배송 등 거래 조건 · 경품 조건 · 대가 관계 · 광고 출처 → 표시광고법이 주 근거」
#:        · 조건 ① 「사항이 거래 조건이면 표시광고법 노드로 반드시 보낸다」 → **not_claim 으로 내보내지 않는다**
#:        · 「⬜ 사항 판별 규칙 — 낱말(가격 · 할인 · 환불 · 배송 · 경품 · 협찬 …)로 시작할지 분류기로 갈지」 → 낱말로 시작한다
#: `[임의]` 낱말 목록은 결정 문언의 예시에서 시작했다 · test 문장을 보고 늘리지 않는다(D-175) · 🔜 사전 종류로 이관 제안(D-117)
TRADE_CUE = re.compile(
    r"가격|할인|정가|판매가|최저가|특가|세일|쿠폰|적립금|포인트\s*적립|환불|반품|교환|배송|도착|출고|경품|사은품|증정|"
    r"\d[\d,]*\s*원|만\s*원|1\+1|2\+1|협찬|광고비|대가를|유료\s*광고")
#: 주장 표지 — 효능 · 건강 목적 · 입증 필요 주장이 있으면 판정 대상이다 (D-286 ③ 「효능이 붙지 않은」 · G1 · ⑥ · 개정 2 · 4)
CLAIM_CUE = re.compile(
    r"건강|효과|효능|개선|도움|예방|치료|완치|낫|완화|회복|면역|질환|질병|증상|환자|당뇨|혈압|혈당|콜레스테롤|비만|다이어트|체중|체지방|"
    r"피로|활력|기능성|성장|발달|두뇌|기억|수면|스트레스|관절|뼈|소화|변비|해독|디톡스|항산화|노화|피부|미용|의약|약효|"
    r"최초|최고|유일|1위|No\.?\s*1|넘버원|인증|특허|수상|입증|검증|임상|안심|안전|부작용|걱정\s*(없|끝)|무해|100\s*%|천연|무첨가|프리미엄|완벽|보장")
#: 판정 대상 아님 표지 — 섭취 대상만 · 사업자 정보 · 의무 표기(D-275 계약 주석 「섭취 대상 · 사업자 정보 · 의무 표기 · 구호」 · D-286 ③ · G8 판매원·제조원)
NOTCLAIM_CUE = re.compile(
    r"보관|소비기한|유통기한|제조일|내용량|원재료|원산지|영양\s*정보|열량|kcal|나트륨|분리배출|포장재질|"
    r"제조원|판매원|유통전문판매원|수입원|고객센터|소비자\s*상담|품목보고번호|식품유형|제조국|"
    r"섭취\s*(방법|량)|1일\s*\d+\s*회|\d+\s*회\s*\d+\s*(정|포|캡슐|g|ml|mL)|"
    r"(드세요|드십시오|섭취하십시오|섭취하세요|드시면 됩니다|드셔도\s*(좋아요|좋습니다|됩니다))\s*[.!]?$|"
    r"CFU|/\s*일\b|"
    #: 🆕 09-30 주의사항(의무 표기) — 「주의」 로 끝나거나 과다 섭취 · 섭취 주의 안내
    r"주의\s*(하세요|하십시오|바랍니다|하시기 바랍니다)?\s*[.!]?$|과다\s*섭취|섭취에\s*주의|"
    #: 섭취 대상만 — 「~분께 추천」 · 「~에게 알맞은 구성」 (효능이 붙으면 CLAIM_CUE 가 먼저 잡는다)
    r"분(들)?(께|에게)?\s*(추천|권)|(에게|께)\s*(알맞은|적합한|좋은)\s*(제품|구성)|(을|를)\s*위한\s*(제품|구성)|분\s*$")


def sentence_subject(text: str) -> tuple[str, Optional[re.Match]]:
    """주장 · 거래조건 · 혼합 · 판정대상아님. 🚨 판정이 아니다 — 2단계가 신호를 어떻게 쓸지만 바꾼다."""
    claim = CLAIM_CUE.search(text) or APPROVED_PHRASE.search(text)
    trade = TRADE_CUE.search(text)
    if trade and claim:
        return "혼합", trade          # 사항마다 근거를 단다(D-272 개정 ③) — 식품 신호는 그대로 쓴다
    if trade:
        return "거래조건", trade
    if not claim and NOTCLAIM_CUE.search(text):
        return "판정대상아님", None
    return "주장", None


MODEL_DIR_CANDIDATES = ("copylane-encoder-kcbert-final",)


# ══════════════════════════════════════════════════════════════════════
#  사전
# ══════════════════════════════════════════════════════════════════════
class DictBook:
    """banned_terms.jsonl → dictmatch 항목 + 항목별 성격(단독판정 · 신뢰도 · 유형 목록 · 근거)."""

    def __init__(self, path: str = BANNED_TERMS_PATH) -> None:
        if not os.path.exists(path):
            raise SystemExit(f"🔴 금지 표현 사전이 없다: {path}\n"
                             "  `launcher.py data-setup` 으로 받는다. 빈 사전으로 진행하지 않는다 (D-220)")
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        if not rows:
            raise SystemExit(f"🔴 금지 표현 사전이 비었다: {path} (D-220)")
        self.meta: dict[str, dict] = {}
        self.entries: list[dm.Entry] = []
        for r in rows:
            kinds = r.get("유형") or []
            self.meta[r["term"]] = r
            # scripts/load_db.load_dict 와 같은 규칙 — 유형이 하나일 때만 violation_type (D-155 · D-178)
            self.entries.append(dm.Entry(term=r["term"], violation_type=kinds[0] if len(kinds) == 1 else None,
                                         basis=tuple(r.get("근거") or ())))
        self.path = path

    def find(self, text: str) -> list[tuple[dict, Optional[tuple[int, int]]]]:
        return [(self.meta[m.entry.term], m.span) for m in dm.find(text, self.entries)]


def load_banned_terms(path: str = BANNED_TERMS_PATH) -> DictBook:
    return DictBook(path)


# ══════════════════════════════════════════════════════════════════════
#  인코더
# ══════════════════════════════════════════════════════════════════════
def resolve_model_dir(cli_arg: Optional[str] = None) -> str:
    """모델 폴더: --model > 환경변수 COPYLANE_MODEL_DIR > 이 폴더의 copylane-encoder-kcbert-final.

    🚨 모델 폴더는 저장소에 커밋하지 않는다(.gitignore · 대용량) — 저장소 밖에 두고 --model 로 가리키는 것을 권한다.
    """
    for cand in (cli_arg, os.environ.get("COPYLANE_MODEL_DIR")):
        if cand:
            path = cand if os.path.isabs(cand) else os.path.abspath(cand)
            if not os.path.exists(os.path.join(path, "label_scheme.json")):
                raise SystemExit(f"🔴 모델 폴더에 label_scheme.json 이 없다: {path}")
            return path
    for name in MODEL_DIR_CANDIDATES:
        path = os.path.join(HERE, name)
        if os.path.exists(os.path.join(path, "label_scheme.json")):
            return path
    raise SystemExit(f"🔴 모델 폴더가 없다 — --model 로 지정하거나 COPYLANE_MODEL_DIR 을 둔다 (후보: {MODEL_DIR_CANDIDATES})")


def load_encoder(model_dir: str):
    """(tokenizer, model, label_list, thresholds). 🔴 계약과 어긋나면 멈춘다 (D-220)."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    with open(os.path.join(model_dir, "label_scheme.json"), encoding="utf-8") as f:
        scheme = json.load(f)
    label_list = scheme.get("label_list") or []
    thresholds = scheme.get("label_thresholds")
    unknown = set(label_list) - {v.value for v in Violation}
    if not label_list or unknown:
        raise SystemExit(f"🔴 label_list 가 계약 Violation 과 다르다: {unknown or '비었음'} (D-54 · D-232)")
    if not isinstance(thresholds, dict) or set(thresholds) != set(label_list):
        raise SystemExit("🔴 label_scheme.json 에 유형별 label_thresholds 가 없다 — dev 실측 τ 없이 판정하지 않는다 (D-131 · D-220)")
    with open(os.path.join(model_dir, "config.json"), encoding="utf-8") as f:
        id2label = json.load(f).get("id2label") or {}
    if [id2label.get(str(i)) for i in range(len(label_list))] != label_list:
        raise SystemExit("🔴 config.json id2label 순서가 label_list 와 다르다 — 확률이 다른 유형에 붙는다 (D-220)")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    print(f"[INFO] 모델: {model_dir} · 실험: {scheme.get('experiment', '?')} · golden {str(scheme.get('golden_sha256', ''))[:8]}")
    print(f"[INFO] τ(dev 실측): {thresholds}")
    return tokenizer, model, label_list, thresholds


def predict_label_probs(text: str, tokenizer, model, label_list: list[str]) -> dict[str, float]:
    return predict_label_probs_batch([text], tokenizer, model, label_list)[0]


def predict_label_probs_batch(texts: list[str], tokenizer, model, label_list: list[str],
                              batch_size: int = 32) -> list[dict[str, float]]:
    """동적 패딩 배치 — 문장마다 독립 계산이라 한 문장씩 넣은 결과와 같다."""
    import torch
    out = []
    for i in range(0, len(texts), batch_size):
        inputs = tokenizer(texts[i:i + batch_size], truncation=True, max_length=128, padding=True, return_tensors="pt")
        with torch.no_grad():
            probs = torch.sigmoid(model(**inputs).logits).numpy()
        out.extend({label: float(p) for label, p in zip(label_list, row)} for row in probs)
    return out


# ══════════════════════════════════════════════════════════════════════
#  1단계 — 신호 모음 (판정하지 않는다)
# ══════════════════════════════════════════════════════════════════════
def stage1_signals(text: str, label_probs: dict[str, float], book: DictBook, thresholds: dict[str, float],
                   margin: float = QUIET_MARGIN) -> dict:
    """
    signals[*] = {kind, type, prob, model_agrees, premise, basis, matched_terms, span}
      kind            approved_phrase · dict(단독판정) · overlap(적법중첩 / 승인 문구 안의 단독판정) · dict_weak(모호) · model
                      · near_threshold(신호는 없지만 확률이 τ × margin 이상 — 여유 구간 · 방안 (다))
                      · trade_condition(사항이 거래 조건 — 인코더 점수 대신 표시광고법 사실 확인 · D-272 개정)
    subject  주장 · 거래조건 · 혼합 · 판정대상아님 (사항 판별)
    not_claim 판정 대상 아님 후보 — 표지가 있고 여유 구간 신호뿐일 때만 (D-275 · D-286 ③)
      model_agrees    인코더 확률 >= 그 유형 τ (D-127 「코드 · 인코더 합의」의 인코더 쪽)
      premise         품목 전제(식품 / 건기식 인정 여부)로 결론이 갈리는 신호인가 (D-156 · D-229)
      basis           사전 항목의 근거 인용(D-282 꼴) — 조문 청크 대조 전이다
    """
    signals: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def agrees(label: str) -> bool:
        return label in thresholds and label_probs.get(label, 0.0) >= thresholds[label]

    def add(kind, label, terms, premise=False, basis=(), span=None):
        if (kind, label) in seen:
            return
        seen.add((kind, label))
        signals.append({"kind": kind, "type": label, "prob": round(label_probs.get(label, 0.0), 4),
                        "model_agrees": agrees(label), "premise": premise, "basis": list(basis),
                        "matched_terms": terms, "span": span})

    approved = APPROVED_PHRASE.search(text)
    if approved:
        add("approved_phrase", APPROVED_PHRASE_TYPE, [approved.group(0)], premise=True, span=approved.span())

    for row, span in book.find(text):
        for label in row.get("유형") or []:
            if row.get("단독판정"):
                if approved:  # 승인 문구 모양 안의 사전 표현도 제품 지위로 갈린다 (D-156)
                    add("overlap", label, [row["term"]], premise=True, basis=row.get("근거") or (), span=span)
                else:
                    add("dict", label, [row["term"]], basis=row.get("근거") or (), span=span)
            elif row.get("신뢰도") == "적법중첩":
                add("overlap", label, [row["term"]], premise=True, basis=row.get("근거") or (), span=span)
            elif agrees(label):
                add("dict_weak", label, [row["term"]], basis=row.get("근거") or (), span=span)

    have = {s["type"] for s in signals}
    for label in label_probs:
        if label not in have and agrees(label):
            add("model", label, [])

    # 여유 구간 — 신호가 없을 때만. 확률이 τ 에 가장 가까운 유형 하나를 near_threshold 신호로 남긴다 (방안 (다))
    if not signals and margin < 1.0:
        ratio = {l: label_probs.get(l, 0.0) / thresholds[l] for l in thresholds if thresholds[l] > 0}
        top = max(ratio, key=ratio.get) if ratio else None
        if top is not None and ratio[top] >= margin:
            add("near_threshold", top, [])

    # 🆕 09-30 사항 판별 — 인코더 점수를 어디에 쓸지
    subject, trade_m = sentence_subject(text)
    not_claim = False
    if subject == "거래조건":
        # 인코더의 거짓 · 소비자 점수는 공정위 사건 문서 라벨을 외운 것이라(train 「배송」 35행 전부 위반 라벨 · 이유 구역)
        # 판정 근거로 쓰지 않는다. 표시광고법 사실 확인이 필요한 보류로 보낸다 — not_claim 으로는 절대 내보내지 않는다 (D-272 개정 조건 ①)
        signals = [x for x in signals if x["kind"] not in ("model", "near_threshold")]
        signals.append({"kind": "trade_condition", "type": "거래조건", "prob": round(max(label_probs.values() or [0.0]), 4),
                        "model_agrees": False, "premise": False, "basis": [], "matched_terms": [trade_m.group(0)],
                        "span": trade_m.span()})
    elif subject == "판정대상아님" and all(x["kind"] == "near_threshold" for x in signals):
        # 신호가 여유 구간뿐이면 걷어 내고 판정 대상 아님 후보로 둔다 — 인코더 τ 이상 · 사전 · 승인 문구 신호가 있으면 그대로 둔다
        signals, not_claim = [], True

    return {"text": text, "signals": signals, "probs": {k: round(v, 4) for k, v in label_probs.items()},
            "subject": subject, "not_claim": not_claim,
            "matched_terms_all": sorted({t for s in signals for t in s["matched_terms"]})}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="1단계 신호 확인 — 판정은 judge_stage2.py")
    ap.add_argument("--model", default=None)
    ap.add_argument("texts", nargs="*")
    a = ap.parse_args()
    tok, mdl, labels, th = load_encoder(resolve_model_dir(a.model))
    book = load_banned_terms()
    print(f"[INFO] 사전 {len(book.entries)}건\n")
    for t in a.texts or ["이 제품을 드시면 당뇨가 완치됩니다", "직사광선을 피해 서늘한 곳에 보관하십시오"]:
        print(json.dumps(stage1_signals(t, predict_label_probs(t, tok, mdl, labels), book, th), ensure_ascii=False, indent=2))
