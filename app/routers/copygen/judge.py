"""후보 판정 — **판정 그래프 전체**를 지난다(`GraphJudge`). 판정을 여기서 새로 쓰지 않는다 (D-119).

🔄 2026-10-13 (권소라) — 후보 하나하나가 **검수 그래프 전체**(문장 분할 · 품목 · 검색 · 사전 · 법별 판정 · 인코더)를 지난다.
   `POST /judge` 와 같은 함수다(`app.api.judge`). 종전(같은 날 오전 판)에는 인코더만 봤다(`EncoderJudge` · 결과표 10-12 의 `encoder-only`) —
   사전이 빠져 있었다. 시험 코드의 `--judge encoder`(그래프 탈락 판정 + 인코더)와 같은 길이다.
🚨 **남기는 기준** — 그래프는 사전이 침묵한 문장에 「통과」를 내지 않고 「보류(확신 부족)」를 낸다(D-269). 종착이 `pass` 인 것만
   남기면 후보가 하나도 안 나온다. 그래서 **걸린 것을 떨군다**:
   · 사전에 걸렸다(위반 확정 · 유형 후보) → 탈락   · 인코더 후보가 섰다(그래프가 품목의 전제로 거른 뒤) → 탈락
   · 미판정 · 근거 없음 · 확신 부족이 아닌 보류 → 탈락   · 그 밖(확정 통과 · 걸린 것 없는 확신 부족 보류) → 남긴다
   광고 생성의 `_lands`(`app/routers/user.py`)와 같은 기준이다.
🚨 「남겼다」는 「위반 후보를 못 찾았다」다 — 적법 확인이 아니다.
🚨 그래프가 인코더를 돌리지 않았으면(`judged_by` 에 `+enc:` 가 없다) **생성하지 않는다** — 사전만 지난 것을 다 지난 것처럼 내지 않는다.
★ 보수 · 균형 · 공격을 가르는 「문턱까지의 거리」는 인코더 확률에서 따로 잰다 — 그래프의 응답에는 문턱을 넘은 후보만 실리기 때문이다.
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
        return self._near(pred)

    def _near(self, pred, skip: frozenset[str] = frozenset()) -> Judged:  # noqa: ANN001
        """남긴 후보의 「문턱까지의 거리」. `skip` — 이 품목에서 설 수 없는 유형(거리에서 뺀다)."""
        # 문턱이 1 을 넘는 유형(대기 라벨 · 1.01)은 설 수 없는 유형이다 — 거리에서 뺀다
        thresholds = self._enc.scheme.thresholds
        near = [
            (prob / thresholds[label], label.value, prob, thresholds[label])
            for label, prob in pred.scores.items()
            if 0 < thresholds.get(label, 0) <= 1 and label.value not in skip
        ]
        if not near:
            return Judged(True, "위반 후보 못 찾음")
        ratio, top, prob, thr = max(near)
        # 그래프는 문장마다, 여기는 문구 통째로 잰다 — 통째로는 문턱을 넘는 일이 있다. 남긴 후보의 거리는 1 을 넘기지 않는다
        return Judged(True, "위반 후보 못 찾음", "", round(min(ratio, 1.0), 4), top, prob, thr)


class GraphJudge(EncoderJudge):
    """판정 그래프 전체를 지나게 한다 — 사전 + 검색 + 법별 판정 + 인코더(품목의 전제로 거른 후보)."""

    name = "graph"

    def judge(self, text: str, branch: Branch) -> Judged:
        from fastapi import HTTPException  # noqa: PLC0415

        from app import premise as pm  # noqa: PLC0415
        from app.api import (
            judge as core_judge,  # noqa: PLC0415 — `POST /judge` 와 같은 함수 (D-119)
        )
        from app.contracts import (  # noqa: PLC0415
            Category,
            HoldReason,
            JudgeRequest,
            ProductContext,
            Verdict,
            is_pass,
        )

        category = Category(branch.category)
        product = ProductContext(category=category, has_recognized_function=branch.recognized)
        try:
            res = core_judge(JudgeRequest(text=text, product=product))
        except HTTPException as e:
            if e.status_code in (501, 503):
                # DB · 그래프 의존성이 없다 — 판정을 거치지 않은 문구는 만들지 않는다 (D-147)
                raise CopyGenOff("판정 엔진에 연결하지 못했어요.") from e
            raise
        if "+enc:" not in res.judged_by:
            raise CopyGenOff("판정 그래프가 인코더를 돌리지 못했어요.")
        for s in res.sentences:
            if s.not_claim:
                continue
            if s.verdict is Verdict.unjudged:
                return Judged(False, "미판정")
            if s.violations:
                kinds = " · ".join(v.value for v in s.violations)
                return Judged(False, "사전 적중", f"{s.verdict.value} · {kinds}")
            if s.encoder_candidates:
                detail = " / ".join(
                    f"{c.violation.value} {c.confidence:.2f}" for c in s.encoder_candidates
                )
                return Judged(False, "인코더 유형 후보", detail)
            unsure = s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf
            if not (is_pass(s) or unsure):
                why = s.hold_reason.value if s.hold_reason else ""
                return Judged(False, s.verdict.value, why)
        pred = self._enc.predict(text)
        if pred.truncated:
            return Judged(False, "문장이 길어 끝까지 보지 못함")
        # 그래프가 이 품목에서 서지 않는다고 거른 유형은 거리에서도 뺀다 (`pm.NO_HF_MISLEAD` · D-323 결정 6)
        premises = pm.PREMISES_OF.get(category, ())
        never_hf = bool(premises) and all(p in pm.NO_HF_MISLEAD for p in premises)
        return self._near(pred, frozenset({pm.HF_MISLEAD}) if never_hf else frozenset())
