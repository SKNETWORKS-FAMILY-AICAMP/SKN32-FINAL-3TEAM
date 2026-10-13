"""로컬 KC-BERT 판정 인코더.

이 모듈은 모델이 내는 신호를 ``위반 후보 + confidence``로만 해석한다.
후보 신호만으로는 법령 근거나 최종 판정 상태를 만들 수 없으므로, ``confirmed``·
``hold``·위험도 매핑은 이 계층의 책임이 아니다.

🆕 2026-10-07 — 그래프의 ``encode`` 노드가 이 모듈을 부른다(`app/graph.py` · **그림자 배선**: 신호를 상태에
   싣기만 하고 판정은 읽지 않는다). 어느 모델을 쓸지는 설정 ``COPYLANE_MODEL_DIR`` 하나로 정한다 —
   **비어 있으면 인코더를 올리지 않는다**(`configured_dir`). 라벨 · 문턱은 그 폴더의 ``label_scheme.json`` 이
   정한다 — 코드에 적지 않는다.
🔄 2026-10-13 (D-333) — **앱은 잠금(`models.lock.json`)에 있는 판만 올린다**(`checked_dir`). 설정은 잠금의 채택 ·
   되돌림 판 중에서 **고르는** 것이다 — 판을 바꾼 사실이 git 에 남는다(D-205). 실험(잠금 밖)은 도구가
   `permit_unlocked()` 를 부르고 돌린다(`scripts/eval_graph.py --encoder`). 응답 표지는 **판 지문**이다(`bundle_mark`).
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app import model_lock
from app.contracts import Violation

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "copylane-encoder-kcbert-final"
_REQUIRED_FILES = ("config.json", "label_scheme.json", "model.safetensors", "tokenizer.json")

#: 그래프가 읽는 모델 폴더 — 값이 없으면 인코더 없이 돈다. 이름은 박수진 시제품(`docs/psj/e2e_prototype/judge_stage1.py`
#: `resolve_model_dir`)과 같다 — 두 벌로 두지 않는다 (D-99).
ENV_MODEL_DIR = "COPYLANE_MODEL_DIR"

#: 문장 길이 상한(토큰)의 **기본값**. `[관행]` — 학습 설정값이다(인코더 노트북 · 시제품 `predict_label_probs_batch` 가 128 에서 자른다).
#: ⛔ 종전에는 모델 설정의 최대 길이(kcbert 300)까지 받았다 — 학습 때 못 본 길이의 입력이 들어가 시제품 수치와 어긋난다.
#: 🔄 모델마다 달라질 값이다 — `label_scheme.json` 에 `max_len` 이 실려 있으면 **그 값을 쓴다**(`LabelScheme.max_tokens`).
#:    10-06 산출물(박수진 A · 소성민 v11)에는 그 칸이 없어 이 기본값으로 돈다 — 둘 다 128 로 학습했다.
#:    기본값으로 돌았는지는 `LabelScheme.max_tokens_from_model` 이 말하고 평가 도구가 판 표지에 적는다 (D-220).
MAX_TOKENS = 128
#: `max_len` 으로 받는 범위 — 이 밖은 오타로 보고 멈춘다. 위쪽은 모델의 위치 임베딩 길이가 다시 막는다
_MAX_TOKENS_RANGE = (8, 512)


def configured_dir() -> Path | None:
    """`COPYLANE_MODEL_DIR` 이 가리키는 폴더. **비어 있으면 `None`** — 인코더를 쓰지 않는다는 뜻이다.

    🔄 2026-10-13 (D-333) — `.env` 를 읽는 한 곳(`collect.env.setting`)으로 읽는다. ⛔ 종전에는 `os.environ` 만 봐서
       `.env` 에 적은 값이 **다른 모듈이 `.env` 를 먼저 읽었을 때만** 먹혔다(import 순서 의존 · D-99).
       값은 `models/` 아래 **판 이름**이어도 되고 경로여도 된다 — 이름이면 `models/<이름>` 을 본다.
    🚨 값이 있는데 폴더 · 파일이 없는 것은 「안 쓴다」가 아니다 — `encoder_at` 이 `EncoderUnavailable` 로 멈춘다.
    """
    # `.env` 를 읽는 곳은 하나다 (D-99) · 지연 import — 판정 API 가 수집 층을 끌지 않게
    from collect import env  # noqa: PLC0415

    raw = env.setting(ENV_MODEL_DIR)
    if not raw:
        return None
    path = Path(raw)
    named = model_lock.MODELS / raw
    if not path.is_absolute() and named.is_dir():
        return named
    return path


def weights_sha12(model_dir: Path) -> str:
    """가중치 파일의 sha256 앞 12자 — 수를 낼 때 어느 판으로 쟀는지 적는 지문이다 (D-178). 파일이 없으면 멈춘다.

    🚨 문턱(`label_scheme.json`)만 다른 판을 가르지 못한다 — 판을 가르는 값은 `lock_match(...).bundle` 이다 (D-333).
    """
    path = model_dir / "model.safetensors"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError as e:
        raise EncoderUnavailable(f"판정 인코더 가중치를 읽지 못했다: {path}") from e
    return h.hexdigest()[:12]


#: 인코더가 돈 응답의 표지 접두 — `judged_by` 의 `rule-…` 뒤에 붙고 그 뒤에 판 지문 12자가 온다(`app/graph.py` `judged_by`).
#: 🔄 2026-10-13 (D-333) `+enc:<가중치 지문>` → `+encb:<판 지문>` — 접두를 바꿔 옛 표지와 섞이지 않게 한다(D-178).
#: 🚨 읽는 쪽(검수 화면 · 카피 생성)은 `ran()` 으로 본다 — 글자를 다시 적지 않는다 (D-99)
JUDGED_BY_MARK = "+encb:"


def ran(judged_by: object) -> bool:
    """이 응답에서 인코더가 돌았는가 — 표지로 본다. 🔴 옛 표지(`+enc:`)는 거짓이다 — 판 지문이 아니다 (D-333)."""
    return isinstance(judged_by, str) and JUDGED_BY_MARK in judged_by


#: 잠금 밖 판을 올려도 되는가 — **도구만** 켠다(`permit_unlocked`). 앱은 켜지 않는다 (D-205 · D-333)
_UNLOCKED_OK = False


def permit_unlocked() -> None:
    """이 프로세스에서 **잠금 밖** 판도 올린다 — 평가 · 실험 도구가 부른다. 🚨 앱(서버)은 부르지 않는다.

    ★ 실험은 도구 인자로 한다(D-205). 도구는 판 표지에 「잠금 밖」을 남겨 채택 판의 수와 섞이지 않게 한다.
    """
    global _UNLOCKED_OK  # noqa: PLW0603 — 프로세스 단위 스위치다
    _UNLOCKED_OK = True


@functools.cache
def lock_match(model_dir: Path) -> model_lock.Match:
    """폴더를 잠금에 대 본다 — **폴더마다 한 번만** 해시한다(가중치는 수백 MB 다).

    🔴 잠금을 못 읽으면 `EncoderUnavailable` — 모르는 판을 아는 판으로 세지 않는다 (D-220). 실패는 캐시되지 않는다.
    """
    try:
        return model_lock.match(model_dir, "encoder")
    except (model_lock.LockError, OSError) as e:
        raise EncoderUnavailable(f"모델 잠금으로 판을 확인하지 못했다 — {e}") from e


def checked_dir(model_dir: Path) -> model_lock.Match:
    """앱이 올려도 되는 판인가 — 잠금의 채택 · 되돌림 판이면 그 결과, 아니면 `EncoderUnavailable`.

    🚨 거절은 서비스를 멈추지 않는다 — 그래프의 `encode` 가 경고를 남기고 인코더 없이 규칙 판정으로 간다(D-323).
    """
    m = lock_match(model_dir)
    if m.status == model_lock.OUTSIDE and not _UNLOCKED_OK:
        raise EncoderUnavailable(
            f"잠금(models.lock.json)에 없는 판이다 — {m.why} ({model_dir}).\n"
            "  채택 · 되돌림 판으로 바꾸거나(launcher.py setting COPYLANE_MODEL_DIR <판 이름>) · "
            "실험은 도구 인자로 한다(scripts/eval_graph.py --encoder)"
        )
    return m


@functools.cache
def bundle_mark(model_dir: Path) -> str:
    """응답의 `judged_by` 에 붙는 인코더 판 표지 — **판 지문** 12자(파일 전부 · D-333). 폴더마다 한 번만 읽는다.

    🔄 2026-10-13 — ⛔ 종전 표지는 가중치 지문(`+enc:`)이라 문턱만 다른 판을 가르지 못했다. 접두를 `+encb:` 로 바꿔
       옛 표지와 섞이지 않게 한다(D-178). 🔴 판을 못 읽으면 `지문없음` 이라고 **적는다** — 인코더가 돈 응답이 인코더 없는
       응답과 같은 표지로 나가지 않게 (D-220). 폴더 이름은 싣지 않는다 — `judged_by` 칸은 80자다(`app/models.py`).
    """
    try:
        return lock_match(model_dir).bundle
    except EncoderUnavailable:
        return "지문없음"


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
    #: 문장이 `MAX_TOKENS` 를 넘어 **뒤가 잘렸다** — 잘린 뒷부분은 보지 않았다. 조용히 넘기지 않고 싣는다 (D-220)
    truncated: bool = False


@dataclass(frozen=True)
class LabelScheme:
    """전달 모델과 함께 배포된 라벨 순서·threshold 계약."""

    labels: tuple[Violation, ...]
    thresholds: dict[Violation, float]
    #: 문장 길이 상한(토큰) — 모델 폴더가 실어 주면 그 값, 아니면 기본값(`MAX_TOKENS`)
    max_tokens: int = MAX_TOKENS
    #: 상한을 모델 폴더(`max_len`)에서 읽었는가. 거짓이면 기본값으로 돈 것이다
    max_tokens_from_model: bool = False


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
        thresholds = {
            Violation(label): float(value) for label, value in raw["label_thresholds"].items()
        }
    except (KeyError, TypeError, ValueError) as e:
        raise EncoderUnavailable(f"판정 인코더 라벨 스킴이 잘못됐다: {path}") from e

    if len(labels) != len(set(labels)):
        raise EncoderUnavailable("판정 인코더 라벨 스킴에 중복 라벨이 있다")
    if set(labels) != set(thresholds):
        raise EncoderUnavailable("판정 인코더 라벨과 threshold의 키가 다르다")
    max_len = raw.get("max_len")
    if max_len is None:
        return LabelScheme(labels=labels, thresholds=thresholds)
    lo, hi = _MAX_TOKENS_RANGE
    if isinstance(max_len, bool) or not isinstance(max_len, int) or not lo <= max_len <= hi:
        raise EncoderUnavailable(
            f"판정 인코더 라벨 스킴의 max_len 이 {lo}~{hi} 의 정수가 아니다: {max_len!r} ({path})"
        )
    return LabelScheme(
        labels=labels, thresholds=thresholds, max_tokens=max_len, max_tokens_from_model=True
    )


def select_candidates(
    scheme: LabelScheme, probabilities: list[float]
) -> tuple[EncoderCandidate, ...]:
    """모델 출력 축과 같은 순서의 확률에 라벨별 threshold를 적용한다."""
    if len(probabilities) != len(scheme.labels):
        raise EncoderUnavailable(
            f"판정 인코더 logit 수가 라벨 수와 다르다: logits={len(probabilities)} labels={len(scheme.labels)}"
        )
    return tuple(
        EncoderCandidate(
            violation=label, confidence=probabilities[i], threshold=scheme.thresholds[label]
        )
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
        limit = int(getattr(self.model.config, "max_position_embeddings", self.scheme.max_tokens))
        if self.scheme.max_tokens > limit:
            raise EncoderUnavailable(
                f"문장 길이 상한 {self.scheme.max_tokens} 이 모델이 받는 길이 {limit} 보다 길다: {model_dir}"
            )
        self.model.eval()

    def predict(self, text: str) -> EncoderPrediction:
        """sigmoid 확률과 라벨별 threshold 통과 후보를 반환한다."""
        try:
            import torch
        except ImportError as e:
            raise EncoderUnavailable("torch가 없어 판정 인코더를 실행할 수 없다") from e

        full = len(self.tokenizer(text, truncation=False)["input_ids"])
        inputs = self.tokenizer(
            text, truncation=True, max_length=self.scheme.max_tokens, return_tensors="pt"
        )
        with torch.inference_mode():
            probabilities = torch.sigmoid(self.model(**inputs).logits)[0].tolist()
        scores = {label: float(probabilities[i]) for i, label in enumerate(self.scheme.labels)}
        candidates = select_candidates(self.scheme, list(scores.values()))
        return EncoderPrediction(
            scores=scores, candidates=candidates, truncated=full > self.scheme.max_tokens
        )


@functools.cache
def encoder_at(model_dir: Path) -> JudgeEncoder:
    """폴더마다 한 번만 모델을 메모리에 올린다. 🚨 실패는 캐시되지 않는다 — 파일을 채우면 다음 호출에 올라간다."""
    return JudgeEncoder(model_dir)


def default_encoder() -> JudgeEncoder:
    """기본 폴더(`MODEL_DIR`)의 모델."""
    return encoder_at(MODEL_DIR)


def predict(text: str) -> EncoderPrediction:
    """SLLM·RAG 계층이 쓰는 기본 진입점."""
    return default_encoder().predict(text)
