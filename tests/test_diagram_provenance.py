"""도면 PNG 의 C2PA 공개 문단이 살아 있는가 (2026-09-13 · D-222).

🔒 **사실** — 도면 21장 전부에 C2PA 콘텐츠 자격증명(`caBX` 청크)이 붙어 있다.
   2026-09-13 에 팀장이 **벗기지 않기로 판정했다**(D-222). 대신 **밝히고 산다.**

⛔ **PNG 에 `caBX` 가 있는지를 검사하지 않는다.** 그렇게 걸면 **기기에서 뽑은 장을 빨갛게
   만든다** — 거기서는 안 붙는 것이 정상이고, D-222 가 그 길(선택지 b)을 닫지 않았다.
   🚨 **정상인 것을 빨갛게 만드는 게이트는 곧 꺼진다** (D-170).

★ 그래서 보는 것은 **공개 문단이 살아 있는가** 하나다.
  **D-216 의 `test_가명_규칙_문단이_살아_있다` 와 같은 어법**이다 — 검사가 실물을 못 보는
  자리에서는 **사람이 읽는 자리를 지킨다.**

⬜ **여기서 못 보는 것** (D-188) —
  ① **문단이 맞는 말인지.** 사라지는 것만 잡는다.
  ② **실제 PNG 의 상태.** 위 이유로 일부러 안 본다.

🚨 **거버넌스 게이트다** — 공개 범위가 걸린 판정이라 `gate` 마크를 붙인다 (D-89).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: 사람이 읽는 자리. 🚨 **도면을 여는 사람이 제일 먼저 보는 곳**이 첫째다.
_DOCS = ("assets/diagrams/README.md", "docs/00_사실원장.md")

#: 문단이 반드시 들고 있어야 하는 것 — **무엇이 붙어 있고 왜 안 벗기는가**.
_MUST = ("C2PA", "D-222")


@pytest.mark.gate
@pytest.mark.parametrize("rel", _DOCS)
def test_C2PA_공개_문단이_살아_있다(rel: str) -> None:
    """⛔ 이 문단이 사라지면 **공개 저장소에 서명이 붙어 있다는 사실을 아무도 모른다.**"""
    p = ROOT / rel
    assert p.exists(), f"🔴 {rel} 이 없다 — C2PA 공개 문단이 사는 자리다 (D-222)"
    text = p.read_text(encoding="utf-8", errors="ignore")
    missing = [k for k in _MUST if k not in text]
    assert not missing, (
        f"🔒 {rel} 에서 C2PA 공개 문단이 사라졌다 — 빠진 낱말 {missing} (D-222).\n"
        "   ⛔ 도면 PNG 21장에는 콘텐츠 자격증명이 붙어 있고, **벗기지 않기로 판정했다.**\n"
        "   🚨 밝히지 않으면 판정이 「그냥 안 지운 것」이 된다. 문단을 되살린다."
    )


@pytest.mark.gate
def test_반대_대조_없는_낱말은_안_걸린다() -> None:
    """위 검사가 **실패할 수 있음**을 보인다 (D-170).

    🚨 「있는지만 보는 검사」는 찾는 낱말이 아무 데나 있으면 늘 통과한다.
       여기서는 **없는 낱말을 찾으면 실제로 빠진 것으로 잡히는지**를 고정한다.
    """
    text = (ROOT / _DOCS[0]).read_text(encoding="utf-8", errors="ignore")
    assert "존재하지않는낱말ZZZ" not in text, "🚨 이 낱말이 있으면 위 검사가 뜻을 잃는다"
    assert all(k in text for k in _MUST), "🚨 양성 쪽이 안 걸린다 — 검사가 성립하지 않는다"
