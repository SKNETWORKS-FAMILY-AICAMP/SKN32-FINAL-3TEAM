"""
raw 확률 확인용 디버그 스크립트 — threshold 적용 전 sigmoid 확률을 그대로 출력.
judge_e2e_prototype.py의 threshold(기본 0.5)가 이 모델에 맞는지 판단하기 위함.
"""
import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = os.path.join(os.path.dirname(__file__), "copylane-encoder-koelectra-final")

with open(os.path.join(MODEL_DIR, "label_scheme.json"), encoding="utf-8") as f:
    label_list = json.load(f)["label_list"]

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()

samples = [
    "이 크림 하나면 주름이 싹 사라지고 피부가 20대로 돌아갑니다",
    "매일 아침 상쾌하게 즐기는 오렌지 주스입니다",
]

for text in samples:
    inputs = tokenizer(text, truncation=True, max_length=128, padding="max_length", return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.sigmoid(logits).numpy()[0]
    print(f"\n문장: {text}")
    for label, p in zip(label_list, probs):
        print(f"  {label:20s} {p:.4f}")
