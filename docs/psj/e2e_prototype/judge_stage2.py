"""
판정 로직 재설계 — 2단계: 유형(건기식/의약품/화장품) 판별 + 사용자 분기 질문

design: docs/psj/e2e_prototype/judge_logic_redesign.md 의 2단계,
        docs/psj/e2e_prototype/stage2_type_detection_draft.md 의 유형 판별 초안

1단계(judge_stage1.stage1_judge)가 "needs_review"로 내린 케이스만 이어서 처리한다.
1단계에서 이미 "violation"/"ok"로 확정된 건은 그대로 통과.

  needs_review 케이스
      │
      ▼
  유형 판별 (라벨 기반: 건기식/의약품, 키워드 기반: 화장품)
      │
   유형 해당 ──► 사용자에게 재확인 질문 제시 (review_questions)
      │
   유형 미해당 ──► needs_review 그대로 유지 (보수적으로 남김 — 아직 처리 로직 없음)

사용자가 답변하면 re_judge()로 재판정한다.
  "예"(인정받음)  → ok로 하향
  "아니오"        → violation으로 확정
  "모름"          → needs_review 유지 (보수적)

⚠️ 화장품 판별 키워드와 건기식/의약품 판별(라벨 기반)의 근거는 stage2_type_detection_draft.md
   참고. 화장품 키워드 목록은 상식 수준 초안이라 추후 실제 사례 데이터와 대조해 정교화 필요.
"""
import json
import os
from typing import Optional

from judge_stage1 import stage1_judge, load_banned_terms

# 화장품 표지 키워드 (초안 — stage2_type_detection_draft.md 참고)
COSMETIC_KEYWORDS = [
    "피부", "주름", "미백", "탄력", "모공", "각질", "트러블", "여드름", "보습",
    "자외선", "기미", "잡티", "탈모", "발모", "양모", "튼살",
]

TYPE_QUESTIONS = {
    "건기식": {
        "trigger_labels": {"건강기능식품_오인"},
        "question": "이 원료(성분)가 식약처로부터 기능성을 인정받았나요?",
    },
    "의약품": {
        "trigger_labels": {"의약품_오인"},
        "question": "이 제품이 의약품으로 허가/신고되어 있나요?",
    },
    "화장품": {
        "trigger_labels": set(),  # 라벨이 아니라 키워드로 판별
        "question": "해당 효능이 화장품 기능성 심사(또는 고시)로 인정된 표현인가요?",
    },
}


def detect_types(text: str, candidate_labels: set[str]) -> list[str]:
    """needs_review 케이스의 후보 라벨과 문장 키워드로 유형을 판별한다."""
    types = []

    for type_name, spec in TYPE_QUESTIONS.items():
        if spec["trigger_labels"] and spec["trigger_labels"] & candidate_labels:
            types.append(type_name)

    if any(kw in text for kw in COSMETIC_KEYWORDS):
        if "화장품" not in types:
            types.append("화장품")

    return types


def stage2_judge(stage1_result: dict) -> dict:
    """
    1단계 결과를 받아, needs_review인 경우 유형 판별 + 질문을 덧붙인다.
    violation/ok는 그대로 통과.
    """
    if stage1_result["verdict"] != "needs_review":
        return {**stage1_result, "review_questions": []}

    candidate_labels = {s["type"] for s in stage1_result["model_signal"]}
    types = detect_types(stage1_result["text"], candidate_labels)

    if not types:
        # 유형 미해당 — 아직 처리 로직 없음, needs_review 그대로 유지
        return {**stage1_result, "detected_types": [], "review_questions": []}

    review_questions = []
    for t in types:
        review_questions.append({
            "type": t,
            "question": TYPE_QUESTIONS[t]["question"],
            "options": ["예", "아니오", "모름"],
        })

    return {
        **stage1_result,
        "detected_types": types,
        "review_questions": review_questions,
    }


def re_judge(stage2_result: dict, answers: dict[str, str]) -> dict:
    """
    사용자 답변을 반영해 재판정한다.

    answers: {"건기식": "예", "화장품": "아니오"} 형태
             (stage2_judge가 낸 review_questions의 "type" 키를 그대로 씀)

    규칙:
      "예"(인정받음) → ok로 하향
      "아니오"       → violation으로 확정 (model_signal의 라벨을 labels로 승격)
      "모름"         → needs_review 유지 (보수적)
    """
    if not answers:
        return stage2_result

    # 하나라도 "아니오"면 위반 확정 (가장 보수적 — 안전 우선)
    if any(a == "아니오" for a in answers.values()):
        promoted_labels = [
            {**s, "source": "user_confirmed"} for s in stage2_result.get("model_signal", [])
        ]
        return {
            **stage2_result,
            "verdict": "violation",
            "labels": stage2_result.get("labels", []) + promoted_labels,
            "review_answers": answers,
        }

    # 전부 "예"면 적법으로 하향
    if all(a == "예" for a in answers.values()):
        return {
            **stage2_result,
            "verdict": "ok",
            "review_answers": answers,
        }

    # 그 외("모름" 포함) → 보수적으로 needs_review 유지
    return {
        **stage2_result,
        "verdict": "needs_review",
        "review_answers": answers,
    }


if __name__ == "__main__":
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
        "이 영양제는 관절 건강에 도움을 주는 기능성 원료를 함유하고 있습니다",
        "이 제품은 관절 건강 유지에 도움을 줄 수 있는 원료로 만들었습니다",
        "이 제품은 기억력 개선에 도움을 줄 수 있습니다",  # 사전 "적법중첩" 표현 테스트
    ]

    for text in samples:
        inputs = tokenizer(text, truncation=True, max_length=128, padding="max_length", return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.sigmoid(logits).numpy()[0]
        label_probs = {label: float(p) for label, p in zip(label_list, probs)}

        s1 = stage1_judge(text, label_probs, banned_terms)
        s2 = stage2_judge(s1)

        print(f"문장: {text}")
        print(json.dumps(s2, ensure_ascii=False, indent=2))
        print()
