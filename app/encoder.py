"""로컬 KC-BERT 판정 인코더.

이 모듈은 모델이 내는 신호를 ``위반 후보 + confidence``로만 해석한다.
후보 신호만으로는 법령 근거나 최종 판정 상태를 만들 수 없으므로, ``confirmed``·
``hold``·위험도 매핑은 이 계층의 책임이 아니다.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts import Violation


MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "copylane-encoder-kcbert-final"
_REQUIRED_FILES = ("config.json", "label_scheme.json", "model.safetensors", "tokenizer.json")


class EncoderUnavailable(RuntimeError):
    """모델 파일 또는 로컬 추론 의존성이 없는 경우."""


@dataclass(frozen=True)
class EncoderCandidate:
    """라벨별 최적 threshold를 통과한 모델 신호 하나."""

    violation: Violation
    confidence: float
    threshold: float


@dataclass(frozen=True)
class EncoderPrediction:
    """한 문장에 대한 전체 확률과 threshold 통과 후보."""

    scores: dict[Violation, float]
    candidates: tuple[EncoderCandidate, ...]


@dataclass(frozen=True)
class LabelScheme:
    """전달 모델과 함께 배포된 라벨 순서·threshold 계약."""

    labels: tuple[Violation, ...]
    thresholds: dict[Violation, float]


def load_label_scheme(model_dir: Path = MODEL_DIR) -> LabelScheme:
    """``label_scheme.json``을 읽고 프로젝트 위반 유형과 대조한다.

    라벨 순서는 가중치의 logit 축과 같으므로 정렬하거나 코드에 다시 적지 않는다.
    """
    path = model_dir / "label_scheme.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise EncoderUnavailable(f"판정 인코더 라벨 파일이 없다: {path}") from e
    except json.JSONDecodeError as e:
        raise EncoderUnavailable(f"판정 인코더 라벨 파일이 JSON이 아니다: {path}") from e

    try:
        labels = tuple(Violation(value) for value in raw["label_list"])
        thresholds = {Violation(label): float(value) for label, value in raw["label_thresholds"].items()}
    except (KeyError, TypeError, ValueError) as e:
        raise EncoderUnavailable(f"판정 인코더 라벨 스킴이 잘못됐다: {path}") from e

    if len(labels) != len(set(labels)):
        raise EncoderUnavailable("판정 인코더 라벨 스킴에 중복 라벨이 있다")
    if set(labels) != set(thresholds):
        raise EncoderUnavailable("판정 인코더 라벨과 threshold의 키가 다르다")
    return LabelScheme(labels=labels, thresholds=thresholds)


def select_candidates(scheme: LabelScheme, probabilities: list[float]) -> tuple[EncoderCandidate, ...]:
    """모델 출력 축과 같은 순서의 확률에 라벨별 threshold를 적용한다."""
    if len(probabilities) != len(scheme.labels):
        raise EncoderUnavailable(
            f"판정 인코더 logit 수가 라벨 수와 다르다: logits={len(probabilities)} labels={len(scheme.labels)}"
        )
    return tuple(
        EncoderCandidate(violation=label, confidence=probabilities[i], threshold=scheme.thresholds[label])
        for i, label in enumerate(scheme.labels)
        if probabilities[i] >= scheme.thresholds[label]
    )


class JudgeEncoder:
    """가중치·토크나이저를 로컬에서만 읽는 다중 라벨 분류기."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self.model_dir = model_dir
        missing = [name for name in _REQUIRED_FILES if not (model_dir / name).is_file()]
        if missing:
            raise EncoderUnavailable(f"판정 인코더 파일이 없다 ({', '.join(missing)}): {model_dir}")
        self.scheme = load_label_scheme(model_dir)
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as e:
            raise EncoderUnavailable("transformers가 없어 판정 인코더를 로드할 수 없다") from e

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_dir, local_files_only=True, trust_remote_code=False
            )
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_dir,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
            )
        except (OSError, ValueError) as e:
            raise EncoderUnavailable(f"판정 인코더를 로드하지 못했다: {model_dir}") from e

        # Transformers 판에 따라 JSON의 문자열 키가 정수 키로 복원된다.
        # 모델 파일의 순서를 검증하되, 라이브러리 표현 차이로 거짓 실패하지 않는다.
        config_labels = tuple(
            Violation(self.model.config.id2label.get(i, self.model.config.id2label.get(str(i))))
            for i in range(len(self.scheme.labels))
        )
        if config_labels != self.scheme.labels:
            raise EncoderUnavailable("config.json과 label_scheme.json의 라벨 순서가 다르다")
        self.model.eval()

    def predict(self, text: str) -> EncoderPrediction:
        """sigmoid 확률과 라벨별 threshold 통과 후보를 반환한다."""
        try:
            import torch
        except ImportError as e:
            raise EncoderUnavailable("torch가 없어 판정 인코더를 실행할 수 없다") from e

        max_length = int(getattr(self.model.config, "max_position_embeddings", 512))
        inputs = self.tokenizer(text, truncation=True, max_length=max_length, return_tensors="pt")
        with torch.inference_mode():
            probabilities = torch.sigmoid(self.model(**inputs).logits)[0].tolist()
        scores = {label: float(probabilities[i]) for i, label in enumerate(self.scheme.labels)}
        candidates = select_candidates(self.scheme, list(scores.values()))
        return EncoderPrediction(scores=scores, candidates=candidates)


@functools.cache
def default_encoder() -> JudgeEncoder:
    """프로세스마다 한 번만 모델을 메모리에 올린다."""
    return JudgeEncoder()


def predict(text: str) -> EncoderPrediction:
    """SLLM·RAG 계층이 쓰는 기본 진입점."""
    return default_encoder().predict(text)
