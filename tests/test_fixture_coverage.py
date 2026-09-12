"""골든 픽스처가 **화면이 그려야 할 분기를 다 덮는가** (2026-09-12 밤 · D-124 · 병렬작업 계약 §2-1).

⛔ **무엇이 있었나** — 픽스처 14건은 있는데 *"모든 분기를 그린다"* 를 **아무도 안 세고 있었다.**
   D-124 가 픽스처의 값어치를 *"화면·BFF 가 픽스처로 모든 분기를 그린다"* 로 적었는데,
   enum 에 값을 하나 더해도 픽스처는 그대로였다 — **화면이 모르는 값을 런타임에 처음 만난다.**

★ 여기서 세는 것은 **판정 축 넷과 위험도**다. 화면의 분기가 그 위에서 갈린다.
🚨 **덮지 못한 값은 「없는 것」이 아니라 「사유를 적은 것」이다** — `KNOWN_GAPS` 가 그 자리다.
   ⛔ 사유 없는 예외를 두지 않는다. 그리고 **예외가 덮이면 예외를 지우게 만든다** —
      통과만 하는 예외가 남으면 목록이 장식이 된다 (D-170).

🚨 이 파일은 **정적 검사**다 — 픽스처가 실제 파이프라인 출력과 같은지는 보지 않는다.
   ⬜ 그 검사(픽스처 낡음)는 아직 없다. 병렬작업 계약 §2-1 이 그것을 남은 일로 적었다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts import HoldReason, Infeasibility, Outcome, Risk, Verdict

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 세는 축 — (enum, 픽스처 JSON 안에서 그 값이 실릴 수 있는 키들)
#: 🚨 **키를 하나로 적지 않는다.** 같은 enum 이 두 모델에 다른 이름으로 실린다 —
#:    `Infeasibility` 는 `SentenceJudgment.infeasibility` 이면서 `Certificate.reason` 이다.
#:    ⛔ 하나만 적으면 다른 쪽에만 있는 값을 「안 덮었다」고 오탐한다 (실제로 그랬다).
#: ⛔ 값 문자열만 훑지도 않는다 — `Outcome.hold` 와 `Verdict.hold` 가 같은 글자라
#:    한쪽만 덮여도 둘 다 덮인 것으로 읽힌다. **축은 키로 가른다** (D-167).
_AXES: tuple[tuple[type, tuple[str, ...]], ...] = (
    (Outcome, ("outcome",)),
    (Verdict, ("verdict",)),
    (HoldReason, ("hold_reason",)),
    (Infeasibility, ("infeasibility", "reason")),
    (Risk, ("final",)),
)

#: 🚨 **덮지 못한 값과 그 사유.** 사유 없는 예외는 두지 않는다.
KNOWN_GAPS: dict[str, str] = {
    "HoldReason.gap2": (
        "1·2위 격차 부족 — **인코더가 있어야 나오는 상태**다. 스텁으로는 만들 수 없고, "
        "지어내면 화면이 가짜 모양에 붙는다 (D-147). T2 인코더 뒤에 픽스처를 만든다"
    ),
    "Risk.R0": (
        "특이사항 없음 — 위반 문장이 **하나도 없는** 응답이라 판정 픽스처의 대상이 아니다. "
        "⬜ 화면에 「위반 없음」 화면이 있다면 그때 픽스처가 하나 필요하다 (SCR 미정)"
    ),
}


def _seen() -> dict[str, set[str]]:
    """픽스처 전부에서 키별로 등장한 문자열 값. 🚨 중첩을 끝까지 훑는다."""
    out: dict[str, set[str]] = {}

    def walk(o: object) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str):
                    out.setdefault(k, set()).add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for p in sorted(FIXTURES.rglob("*.json")):
        walk(json.loads(p.read_text(encoding="utf-8")))
    return out


@pytest.mark.gate
def test_픽스처가_판정_축의_모든_값을_덮는다() -> None:
    """🔴 새 enum 값을 더하고 픽스처를 안 만들면 여기서 걸린다.

    ⛔ 그것이 정확히 「화면이 모르는 값을 받는」 자리다 — 계약 표면 게이트가 **변경**을 잡고,
       이 게이트는 **덮이지 않은 분기**를 잡는다. 둘은 다른 것을 본다.
    """
    seen = _seen()
    missing = [
        f"{enum_cls.__name__}.{m.name}"
        for enum_cls, keys in _AXES
        for m in enum_cls
        if not any(m.value in seen.get(k, set()) for k in keys)
    ]
    undeclared = [m for m in missing if m not in KNOWN_GAPS]
    assert not undeclared, (
        f"🔴 픽스처가 안 덮는 분기가 있다: {undeclared}\n"
        "   화면은 이 값을 **런타임에 처음** 만난다 (D-124).\n"
        "   고치는 법 — 픽스처를 하나 만들거나, 못 만드는 사유를 `KNOWN_GAPS` 에 적는다"
    )


@pytest.mark.gate
def test_덮인_값이_예외_목록에_남아_있지_않다() -> None:
    """🚨 **통과만 하는 예외는 장식이다** (D-170 · D-203).

    픽스처가 생겼는데 사유가 남아 있으면, 다음 사람은 아직 못 덮는 줄 안다.
    """
    seen = _seen()
    stale = [
        name
        for enum_cls, keys in _AXES
        for m in enum_cls
        if (name := f"{enum_cls.__name__}.{m.name}") in KNOWN_GAPS
        and any(m.value in seen.get(k, set()) for k in keys)
    ]
    assert not stale, f"🔴 이제 픽스처가 덮는다 — `KNOWN_GAPS` 에서 지운다: {stale}"


@pytest.mark.gate
def test_예외에는_사유가_붙어_있다() -> None:
    """⛔ 사유 없는 예외는 「왜 없는지 모르는 구멍」이다 (D-192 — 없는 이유가 저항이다)."""
    thin = [k for k, v in KNOWN_GAPS.items() if len(v.strip()) < 20]
    assert not thin, f"🔴 사유가 너무 짧다: {thin}"


def test_진입점_셋이_모두_픽스처를_갖는다() -> None:
    """🚨 게이트가 아니다 — 건수는 원장이 정본이다 (D-54). 여기서는 **셋이 다 있는지**만 본다."""
    kinds = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
    assert kinds == {"judge", "generate", "compose"}, f"진입점 픽스처 폴더가 셋이 아니다: {kinds}"
    for k in sorted(kinds):
        assert list((FIXTURES / k).glob("*.json")), f"🔴 {k} 픽스처가 0건이다"
