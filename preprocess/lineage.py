"""preprocess/lineage.py — 골든셋 행의 **계보 → (프래그먼트, 재배포)** 한 표 (D-249 · D-133 · D-71).

🔴 **한 곳에만 둔다** (D-99) — `preprocess.golden` 이 행의 `redistributable` 을, `scripts.load_db` 가
   `golden_sample.fragment_id` 를 이 표에서 읽는다.
   ⛔ 2026-09-20 까지 둘이 따로였다 — 적재기는 인용 문구를 G2(재배포 금지 조각)로 만들고, 골든셋은 모든 행에
      `redistributable: True` 를 **상수로** 박았다. 인용 광고 문구 5,801행이 「공개 가능」으로 적혀 있었다.

★ 규칙 (D-249) — **광고주가 쓴 문구를 인용한 행은 재배포 불가**다. 원천 문서가 공공저작물이어도
  (공정위 의결서 = 저작권법 제7조 3호 · 식약처 문서 = 제24조의2) 인용된 부분은 광고주 몫으로 본다.
  승인 기능성 문구(식약처 저작물 · G3)와 그것에서 규칙으로 만든 **우리 합성문**만 재배포할 수 있다.
🚨 **모르는 계보는 멈춘다** (D-220) — 표에 없는 원천이 골든셋에 들어오면 판정부터 한다.
🚨 등급(G2/G3)은 `scripts/load_db.py` 의 `FRAGMENTS` 가 들고, 게이트가 「G2 ↔ 재배포 불가」를 대조한다.
"""

from __future__ import annotations

#: (provenance, origin) → (fragment_id, redistributable)
GOLDEN_LINEAGE: dict[tuple[str, str], tuple[str, bool]] = {
    # 인용 광고 문구 — 광고주 저작물 조각 (D-133 ① · D-249)
    ("ftc_decisions_body", "real"): ("ftc_decisions_body:golden", False),
    ("mfds_casebook", "real"): ("mfds_casebook:golden", False),
    ("mfds_special_use_guide", "real"): ("mfds_special_use_guide:golden", False),
    # 식약처 승인 문구와 우리 합성문
    ("mfds_hf_ingredient_board", "approved"): ("mfds_hf_ingredient_board:approved", True),
    ("mfds_hf_ingredient_board", "injected"): ("mfds_hf_ingredient_board:injected", True),
}


def lineage(provenance: str, origin: str) -> tuple[str, bool]:
    """행의 계보. 🔴 표에 없으면 `SystemExit` — 조용히 「공개 가능」으로 두지 않는다."""
    key = (provenance, origin)
    if key not in GOLDEN_LINEAGE:
        raise SystemExit(
            f"🔴 골든셋 계보 {key} 가 `preprocess/lineage.py` 에 없다.\n"
            "  🚨 재배포·등급 판정이 없는 행은 넣지 않는다 (D-18 · D-249) — 표에 판정과 함께 올린다."
        )
    return GOLDEN_LINEAGE[key]
