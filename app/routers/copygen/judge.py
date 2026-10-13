"""후보 판정 — **우리 판정 인코더**(`app.encoder`)로 한다. 판정을 여기서 새로 쓰지 않는다 (D-119).

결과표(10-12)의 `encoder-only` 와 같은 길이다 — 유형 후보가 하나라도 문턱을 넘으면 탈락.
모델은 `.env` 의 `COPYLANE_MODEL_DIR` 이 가리키는 것 — 검수 그래프가 쓰는 것과 같은 모델 · 같은 문턱이다(`encoder_at` 이 한 번만 올린다).
🚨 「통과」는 「위반 후보를 못 찾았다」다. 인코더는 후보 신호만 낸다 — 확정 · 위험도는 정하지 않는다.
🚨 사전 판정(검수 그래프)은 여기서 돌리지 않는다. 단독판정 낱말은 코드 필터가 먼저 거르고(`filters.dict_terms`),
   고른 문구를 광고 생성으로 넘기면 그때 검수 그래프가 다시 본다(`POST /u/compose`).
⛔ 품목의 전제로 후보를 거르지 않는다(D-323 결정 6 은 그래프의 것) — 건강기능식품 분기에서도 `건강기능식품_오인` 후보가 설 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .branches import Branch
from .errors import CopyGenOff


@dataclass(frozen=True)
class Judged:
    passed: bool
    outcome: str
    detail: str = ""
    #: 🆕 2026-10-13 — **문턱까지 얼마나 가까운가**(0 = 멀다 · 1 = 문턱). 유형마다 문턱이 달라(비방광고 0.3 · 의약품 오인 0.825)
    #:    확률 그대로는 견줄 수 없다 — 유형별 `확률 ÷ 문턱` 의 최댓값이다. 통과한 후보는 1 미만이다.
    #:    🚨 위험도 등급(R0~R4)이 아니다. 보수 · 균형 · 공격을 가르는 데만 쓴다 (`pipeline.pick`)
    closeness: float = 0.0
    #: 가장 가까운 유형 · 그 확률 · 그 문턱 — 화면이 수치로 적는다
    top: str = ""
    top_prob: float = 0.0
    top_threshold: float = 0.0


class EncoderJudge:
    name = "encoder"

    def __init__(self) -> None:
        from app import encoder as enc  # noqa: PLC0415 — torch 는 판정 경로에서만 든다

        model_dir = enc.configured_dir()
        if model_dir is None:
            raise CopyGenOff("판정 인코더가 설정되지 않았어요.")
        try:
            self._enc = enc.encoder_at(model_dir)
        except enc.EncoderUnavailable as e:
            raise CopyGenOff("판정 인코더를 올리지 못했어요.") from e

    def judge(self, text: str, branch: Branch) -> Judged:  # noqa: ARG002 — 분기는 판정기 자리의 약속이다
        pred = self._enc.predict(text)
        if pred.truncated:
            # 뒤가 잘린 문장은 「못 본 것」이다 — 통과로 세지 않는다 (D-220)
            return Judged(False, "문장이 길어 끝까지 보지 못함")
        if pred.candidates:
            detail = " / ".join(
                f"{c.violation.value} {c.confidence:.2f}≥{c.threshold}" for c in pred.candidates
            )
            return Judged(False, "인코더 유형 후보", detail)
        # 문턱이 1 을 넘는 유형(대기 라벨 · 1.01)은 설 수 없는 유형이다 — 거리에서 뺀다
        thresholds = self._enc.scheme.thresholds
        near = [
            (prob / thresholds[label], label.value, prob, thresholds[label])
            for label, prob in pred.scores.items()
            if 0 < thresholds.get(label, 0) <= 1
        ]
        if not near:
            return Judged(True, "위반 후보 못 찾음")
        ratio, top, prob, thr = max(near)
        return Judged(True, "위반 후보 못 찾음", "", round(ratio, 4), top, prob, thr)
