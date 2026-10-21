"""D4-13 채택안 — 인코더 유형 후보의 **대표 · 순서** (박수진 · 2026-10-15 · `app/reasons.py` 흡수용 초안)

팀장 판정(10-15): 대표 유형 원칙 채택 · 접지 않는다 — 「근거 보기」 접힌 칸 안에서 **확률 순으로 정렬하고 첫 줄을 대표로 표시**한다.
  · 대표 = **원시 확률(`confidence`) 최댓값** — 판정 그래프 dev 후보 2개 이상 행에서 확률 ÷ 문턱보다 나았다(100/137 대 87/137)
  · 품목 전제가 옮긴 후보(`moved_from`)는 **원래 유형의 확률**로 순위를 매긴다 — 그 확률은 이미 `confidence` 에 실려 있다
    (`app/graph.py` `_encoder_candidates` · `EncoderTypeCandidate.confidence` 주석) → 따로 계산하지 않는다
  · ⛔ 판정 · 집합 함수는 그대로 후보 전부를 읽는다 — `agreed_types` · `differing_types` · `combo_cell` · `guessed_types`.
    바뀌는 것은 화면의 **순서와 대표 표시**뿐이다. 표시 문안은 화면 담당(권소라)이 정한다
  · 동률(같은 확률)은 ① 인코더가 직접 낸 후보 먼저 ② 유형 이름 순 — 화면이 요청마다 흔들리지 않게(결정적)

흡수 방법 — 아래 두 함수를 `app/reasons.py` 의 `guessed_types` 근처로 옮기고, 템플릿은 `encoder_candidates` 대신
`ordered_candidates(sentence)` 를 돌며 `loop.first`(또는 `c is representative(sentence)`)에 대표 표지를 단다.
"""
from __future__ import annotations

from collections.abc import Sequence


def _rank_key(c: object) -> tuple[float, int, str]:
    v = getattr(c, "violation", None)
    name = getattr(v, "value", v)
    return (-float(getattr(c, "confidence", 0.0)), getattr(c, "moved_from", None) is not None, str(name))


def ordered_candidates(sentence: object) -> list[object]:
    """문장의 인코더 유형 후보를 **원시 확률 내림차순**으로 — 첫 원소가 대표다. 후보가 없으면 빈 목록.

    🔴 빈 목록은 「인코더가 없다 / 후보가 없다」이지 「문제없음」이 아니다 (D-220 · D-330 결정 1) — 이 함수는 그 말을 하지 않는다.
    ⛔ 후보를 줄이지 않는다(D4-13 R0 그대로) — 개수 · 집합은 입력과 같다. 판정 · 집합 함수는 이 함수를 쓰지 않는다.
    """
    cands: Sequence[object] = getattr(sentence, "encoder_candidates", None) or ()
    return sorted(cands, key=_rank_key)


def representative(sentence: object) -> object | None:
    """대표 유형 후보 — `ordered_candidates` 의 첫 원소 · 없으면 None."""
    got = ordered_candidates(sentence)
    return got[0] if got else None
