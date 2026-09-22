"""
CopyLane 판정 인코더 — E2E 연결용 프로토타입 (박수진, 2026-09-21)

목적: sLLM/RAG 파트와 인터페이스(출력 JSON 스펙)를 먼저 맞추고 E2E 파이프라인을
     끝까지 연결해보기 위한 것. 라벨은 실제 모델(KoELECTRA) 추론, 스팬/위험도는 더미 규칙.

⚠️ 스팬/위험도는 "값이 나온다"만 보장하는 자리채움(placeholder)입니다.
   실제 성능은 없습니다 — E2E 연결 검증 전용.

⚠️ 라벨 순서는 label_scheme.json에서 그대로 읽어온다 — 하드코딩 금지.
   (Colab에서 라벨을 정렬 순서로 저장했기 때문에 "golden.jsonl 등장 순서"와
    다르다 — 순서를 임의로 다시 적으면 라벨이 뒤바뀐 채로 추론된다.)

다음 단계(순서):
  1. 이 인터페이스로 sLLM/RAG 쪽과 연결 테스트
  2. 연결 확인되면 spans는 injected_golden_spans(898건)로 실제 학습
  3. risk_score는 라벨 스킴 설계부터 (현재 라벨 데이터 자체가 없음)
"""
import json
import os
from typing import Optional

# README 기준 위험도는 R0~R3 (4단계) — 확정 전까지 이 스케일로 임시 사용
RISK_LEVELS = ["R0", "R1", "R2", "R3"]


class JudgeEncoder:
    """
    판정 인코더 통합 추론 래퍼.

    model_dir을 넘기면 그 폴더의 config.json/model.safetensors/tokenizer.json/
    label_scheme.json을 로드해서 실제 추론. model_dir=None이면 더미 모드로
    동작 (모델 없이 인터페이스만 검증할 때 사용).
    """

    def __init__(self, model_dir: Optional[str] = None, threshold: float = 0.5):
        self.threshold = threshold
        self.model = None
        self.tokenizer = None
        self.label_list = None

        if model_dir is not None:
            self._load(model_dir)

    def _load(self, model_dir: str):
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        scheme_path = os.path.join(model_dir, "label_scheme.json")
        with open(scheme_path, encoding="utf-8") as f:
            scheme = json.load(f)
        self.label_list = scheme["label_list"]  # 반드시 이 순서로만 라벨 해석

        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self.model.eval()

        print(f"[INFO] JudgeEncoder: 모델 로드 완료 ({model_dir})")
        print(f"[INFO] 라벨 순서: {self.label_list}")

    # ── 1) 라벨: 실제 추론 (모델 있으면) / 더미 (모델 없으면) ──────────
    def predict_labels(self, text: str) -> list[dict]:
        if self.model is None or self.tokenizer is None:
            # 모델 미탑재 상태 — 인터페이스 검증용 더미
            # (실전에서는 이 분기를 타면 안 됨. 로그로 남겨서 눈에 띄게 함)
            print("[WARN] JudgeEncoder: 모델 미탑재 — 더미 라벨 반환")
            return [{"type": "거짓_과장", "confidence": 0.42}] if "완치" in text else []

        import torch

        inputs = self.tokenizer(text, truncation=True, max_length=128,
                                 padding="max_length", return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**inputs).logits
        probs = torch.sigmoid(logits).numpy()[0]

        results = []
        for i, label in enumerate(self.label_list):
            if probs[i] > self.threshold:
                results.append({"type": label, "confidence": round(float(probs[i]), 4)})
        return results

    # ── 2) 스팬: 더미 규칙 ──────────────────────────────────────────
    # 실제 학습 전까지: 라벨이 있으면 "문장 전체"를 스팬으로 반환.
    # (책임 소재를 명확히: 실제 근거 구절이 아니라 자리채움임을 label마다 명시)
    def predict_spans(self, text: str, labels: list[dict]) -> list[dict]:
        spans = []
        for lab in labels:
            spans.append({
                "label": lab["type"],
                "start": 0,
                "end": len(text),
                "text": text,
                "_placeholder": True,  # 실제 스팬 학습 전까지 이 필드로 더미임을 표시
            })
        return spans

    # ── 3) 위험도: 더미 규칙 ────────────────────────────────────────
    # 실제 라벨 체계 설계 전까지: 위반 라벨 개수 기준 단순 매핑.
    # 0개 -> R0, 1개 -> R1, 2개 -> R2, 3개 이상 -> R3
    def predict_risk(self, labels: list[dict]) -> dict:
        n = len(labels)
        idx = min(n, 3)
        return {
            "level": RISK_LEVELS[idx],
            "_placeholder": True,  # 실제 위험도 헤드 학습 전까지 규칙 기반임을 표시
        }

    # ── 통합 판정 ───────────────────────────────────────────────────
    def judge(self, text: str) -> dict:
        labels = self.predict_labels(text)
        spans = self.predict_spans(text, labels)
        risk = self.predict_risk(labels)

        verdict = "violation" if labels else "ok"

        return {
            "text": text,
            "verdict": verdict,
            "labels": labels,
            "spans": spans,
            "risk_score": risk,
        }


if __name__ == "__main__":
    # 실제 모델을 붙이려면 아래처럼 model_dir 지정
    # (예: koelectra-final 압축을 이 스크립트와 같은 폴더에 풀었다면)
    MODEL_DIR = os.path.join(os.path.dirname(__file__), "copylane-encoder-koelectra-final")

    if os.path.isdir(MODEL_DIR):
        encoder = JudgeEncoder(model_dir=MODEL_DIR)
    else:
        print(f"[WARN] 모델 폴더를 찾을 수 없음: {MODEL_DIR} — 더미 모드로 실행")
        encoder = JudgeEncoder()  # 모델 미탑재 — 인터페이스 검증 모드

    samples = [
        "이 제품을 드시면 당뇨가 완치됩니다",
        "맛있게 즐기실 수 있는 건강한 간식입니다",
    ]

    for text in samples:
        result = encoder.judge(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
