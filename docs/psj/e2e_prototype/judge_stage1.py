"""
판정 로직 재설계 — 1단계: 모델 확률 + 근거 키워드(banned_terms 사전) 결합 판정

design: docs/psj/e2e_prototype/judge_logic_redesign.md 의 1단계
  문구 입력
    │
    ├─ 확률 낮음(무해 확신) ──────────► "판정: 적법" (바로 확정)
    ├─ 확률 높음 + 근거 키워드 명확 ──► "판정: 위반" (바로 확정)
    └─ 애매 구간 ─────────────────────► 2단계로 넘김 (이 스크립트 범위 밖)

사전 출처: data/derived/banned_terms.jsonl (preprocess/dictionary.py 산출물)
  - 단독판정=true  : 그 표현이 문장에 있으면 그 자체로 위반 확정 가능 (D-156)
  - 단독판정=false : 적법중첩(승인 표현에도 포함) 또는 모호(여러 유형 겹침)
                     → 문맥 없이는 단독 판정 불가, 사람/사용자 확인 필요

⚠️ 이 파일은 1단계 프로토타입이다. 유형(건기식/화장품) 판별 기반 2단계
   사용자 분기 질문은 아직 포함하지 않음 — needs_review로만 표시.
"""
import json
import os
import re
import unicodedata
from typing import Optional

BANNED_TERMS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "derived", "banned_terms.jsonl"
)
BANNED_TERMS_PATH = os.path.normpath(BANNED_TERMS_PATH)

# 확률이 이 값 미만이면 "무해 확신" — 키워드 매칭과 무관하게 바로 적법 처리
LOW_PROB_THRESHOLD = 0.3
# 확률이 이 값 이상이면 "고확신" 구간 — 근거 키워드가 있어야 위반 확정
HIGH_PROB_THRESHOLD = 0.5


def norm(s: str) -> str:
    """banned_terms 사전과 동일한 정규화 방식 (preprocess/dictionary.py 기준)."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s)))


def load_banned_terms(path: str = BANNED_TERMS_PATH) -> list[dict]:
    if not os.path.exists(path):
        print(f"[WARN] banned_terms.jsonl을 찾을 수 없음: {path} — 키워드 매칭 없이 진행")
        return []
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                terms.append(json.loads(line))
    return terms


def find_matched_terms(text: str, banned_terms: list[dict]) -> list[dict]:
    """문장에 포함된 금지 표현 사전 항목을 찾는다 (부분 문자열 매칭, 정규화 기준)."""
    n_text = norm(text)
    matches = []
    for entry in banned_terms:
        term = entry["term"]
        if term and term in n_text:
            matches.append(entry)
    return matches


def stage1_judge(
    text: str,
    label_probs: dict[str, float],
    banned_terms: list[dict],
    low_threshold: float = LOW_PROB_THRESHOLD,
    high_threshold: float = HIGH_PROB_THRESHOLD,
) -> dict:
    """
    1단계 판정 (절충안).

    ⚠️ 판정 권한의 우선순위:
      1) 사전(banned_terms)에 단독판정 가능한 표현이 매칭되면, 그 표현의 유형으로
         즉시 위반 확정한다 — 모델 확률과 무관. 사전은 실제 사례(판례·의결서)에서
         사람이 뽑아 조문 근거까지 붙인 소스라 그 자체로 신뢰.
      2) 모델이 고확신(prob >= high_threshold)인데 그 라벨을 뒷받침하는 사전 매칭이
         없거나(표면 패턴 오판정 의심) 사전의 유형과 어긋나면(예: 사전은 "질병_예방
         치료_표방"인데 모델은 "거짓_과장") → 위반 확정하지 않고 needs_review로 내리되,
         "model_signal"로 남겨서 데이터 품질 점검(라벨링/학습 데이터 보강)에 쓴다.
      3) 확률이 낮으면(low_threshold 미만) 사전 매칭이 있어도 일단 무해로 본다
         (모델이 이미 확신이 없다는 뜻이므로 사전 매칭 하나만으로 위반 확정하지 않음
          — 오탐 방지 목적. 단, 이건 보수적 설계 선택이라 추후 재검토 가능).
      4) 예외 — 사전에 "적법중첩"(신뢰도="적법중첩") 표현이 매칭되면, 모델 확률이
         낮아도(=모델이 무해로 봐도) 강제로 needs_review로 올린다. "기억력 개선"처럼
         위반 표현과 적법 완곡 표현("기억력 개선에 도움을 줄 수 있음")이 표면적으로
         겹치는 경우, 실제 위법/적법은 원료의 기능성 인정 여부에 달려 있어 확률만으로
         단정할 수 없기 때문 (D-156). 확인 없이 ok로 흘려보내면 위험.

    Args:
        text: 판정할 문구
        label_probs: {"거짓_과장": 0.93, "소비자_기만": 0.14, ...} 형태 (모델 sigmoid 확률)
        banned_terms: load_banned_terms()로 불러온 사전

    Returns:
        {
          "verdict": "ok" | "violation" | "needs_review",
          "labels": [...],          # 위반 확정 (사전 근거 기준)
          "model_signal": [...],    # 모델은 고확신이나 사전과 라벨 불일치/매칭 없음 (참고용)
          "matched_terms_all": [...],
        }
    """
    matched = find_matched_terms(text, banned_terms)

    # 사전 근거로 위반 확정할 수 있는 라벨들 (모델 확률과 무관 — 단, 확률이 아예
    # 낮은 라벨은 위 설계상 제외하지 않고 그대로 확정한다: 사전이 우선이므로.
    # low_threshold는 "사전 매칭이 없을 때"의 모델 신호 해석에만 쓰인다.)
    confirmed_labels = []
    confirmed_types = set()
    for m in matched:
        if not m["단독판정"]:
            continue
        for label in m["유형"]:
            if label in confirmed_types:
                continue
            confirmed_types.add(label)
            confirmed_labels.append({
                "type": label,
                "source": "dictionary",
                "matched_term": m["term"],
                "article": m["근거"],
                "model_confidence_for_this_label": round(label_probs.get(label, 0.0), 4),
            })

    # 모델은 고확신인데 사전 근거로 확정되지 않은 라벨 → model_signal로 기록
    model_signal = []
    for label, prob in label_probs.items():
        if label in confirmed_types:
            continue  # 이미 사전으로 확정됨
        # 이 라벨에 약한(모호/적법중첩) 사전 매칭이 있는지 확인
        weak_matches = [m for m in matched if label in m["유형"] and not m["단독판정"]]
        overlap_matches = [m for m in weak_matches if m["신뢰도"] == "적법중첩"]

        if overlap_matches:
            # 🔴 D-156 — "기억력 개선" 같은 표현은 그 자체로는 위반과 적법(완곡 표현)
            # 양쪽에 다 걸쳐 있다. 원료가 실제 기능성 인정을 받았는지에 따라 갈리므로,
            # 모델 확률이 낮아도(=모델은 무해로 봐도) 강제로 needs_review로 올린다.
            # 확률만으로 조용히 ok 처리하면, "~에 도움을 줄 수 있음"처럼 인정 여부에
            # 따라 위법/적법이 갈리는 문구를 근거 확인 없이 적법으로 흘려보내게 된다.
            model_signal.append({
                "type": label,
                "confidence": round(prob, 4),
                "reason": "적법중첩 표현 — 완곡한 인정 표현과 표면적으로 겹침. "
                          "원료가 실제 기능성 인정을 받았는지 확인 전에는 위법/적법을 "
                          "단정할 수 없음 (모델 확률과 무관하게 확인 필요)",
                "matched_terms": [m["term"] for m in overlap_matches],
            })
            continue

        if prob < high_threshold:
            continue  # 모델도 확신 없고 적법중첩 매칭도 없음 — 조용히 무해 취급
        if weak_matches:
            reason = "사전 근거가 모호함 (여러 유형에 걸침, 문맥 확인 필요)"
        else:
            reason = "모델 확률은 높으나 사전에 이 라벨을 뒷받침할 근거 표현이 없음 (표면 패턴 오판정 의심)"
        model_signal.append({
            "type": label,
            "confidence": round(prob, 4),
            "reason": reason,
            "matched_terms": [m["term"] for m in weak_matches],
        })

    if confirmed_labels:
        verdict = "violation"
    elif model_signal:
        verdict = "needs_review"
    else:
        verdict = "ok"

    return {
        "text": text,
        "verdict": verdict,
        "labels": confirmed_labels,
        "model_signal": model_signal,
        "matched_terms_all": [m["term"] for m in matched],
    }


if __name__ == "__main__":
    # 스모크 테스트 — judge_e2e_prototype.py와 같은 모델로 확률을 뽑아서 결합
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    MODEL_DIR = os.path.join(os.path.dirname(__file__), "copylane-encoder-koelectra-final")

    with open(os.path.join(MODEL_DIR, "label_scheme.json"), encoding="utf-8") as f:
        label_list = json.load(f)["label_list"]

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    model.eval()

    banned_terms = load_banned_terms()
    print(f"[INFO] banned_terms 로드: {len(banned_terms)}건\n")

    samples = [
        "이 제품을 드시면 당뇨가 완치됩니다",
        "맛있게 즐기실 수 있는 건강한 간식입니다",
        "이 크림 하나면 주름이 싹 사라지고 피부가 20대로 돌아갑니다",
        "매일 아침 상쾌하게 즐기는 오렌지 주스입니다",
    ]

    for text in samples:
        inputs = tokenizer(text, truncation=True, max_length=128, padding="max_length", return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.sigmoid(logits).numpy()[0]
        label_probs = {label: float(p) for label, p in zip(label_list, probs)}

        result = stage1_judge(text, label_probs, banned_terms)
        print(f"문장: {text}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
