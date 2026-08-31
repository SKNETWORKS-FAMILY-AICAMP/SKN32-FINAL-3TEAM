"""review_sheet.py — S0-14 2인 확인 검토표를 뽑는다 (D-66 · D-90 ④).

🚨 이 표는 「검토자가 판정에 동의하는가」를 묻는 자리다. 판정을 다시 하는 자리가 아니다.
   그래서 등급·용도·제약·근거 URL 을 한 화면에 모아 두고, 검토자는 각 행에
   동의 / 이견만 남긴다. 이견이 하나라도 있으면 그 소스는 수집하지 않는다.

절차
    uv run python scripts/review_sheet.py        # docs/03_데이터/S0-14_2인확인_검토표.md
    → 검토자가 표를 보고 판단
    → scripts/registry_review.yaml 에 reviewed_by · reviewed_at 기입
    → uv run python scripts/gen_registry.py      # data_sources.yaml 재생성
    → uv run pytest -m gate

🚨 reviewed_by 를 data_sources.yaml 에 직접 적지 말 것 — 생성물이라 다음 생성 때 사라진다.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data_sources.yaml"
LEDGER = ROOT / "scripts/registry_review.yaml"
# 🚨 생성물이지만 커밋한다 — 검토자(팀원)가 받아 보는 문서다.
#    data_sources.yaml 과 같은 층이다 (build/ 는 아무도 안 보는 중간물 전용).
OUT = ROOT / "docs/03_데이터/S0-14_2인확인_검토표.md"

USES = ["U1", "U2", "U3", "U4"]


def main() -> None:
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    ledger = yaml.safe_load(LEDGER.read_text(encoding="utf-8")) or {}
    sources = {k: v for k, v in (reg.get("sources") or {}).items() if isinstance(v, dict)}

    # 수집 대상 = 용도가 하나라도 열려 있는 소스. 전부 deny 면 검토 대상이 아니다.
    targets = {
        k: v
        for k, v in sources.items()
        if any((v.get("use") or {}).get(u) == "allow" for u in USES)
    }
    pending = {k: v for k, v in targets.items() if not (ledger.get(k) or {}).get("reviewed_by")}

    rows = []
    for key, s in pending.items():
        use = s.get("use") or {}
        use_txt = " ".join(u for u in USES if use.get(u) == "allow") or "—"
        flags = ", ".join(s.get("constraints") or []) or "—"
        redist = "가능" if s.get("redistributable") else "🚨 **불가**"
        decided = (ledger.get(key) or {}).get("decided_by") or "—"
        rows.append(
            f"| `{key}` | {s.get('name', '')} | **{s.get('grade')}** | {use_txt} | {flags} "
            f"| {redist} | {decided} | | |"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(
            [
                "# S0-14 · 2인 확인 검토표",
                "",
                "> 생성물입니다. 고칠 곳은 `scripts/registry_review.yaml` 입니다.",
                f"> 검토 대상 **{len(pending)}건** / 수집 대상 {len(targets)}건 "
                f"(전체 {len(sources)}건)",
                "",
                "## 검토자가 확인하는 것",
                "",
                "1. **등급이 맞는가** — G3(원문 자유) · G2(사실만) · G0(미표기 → fail-closed)",
                "2. **열린 용도가 등급 상한을 넘지 않는가** — G2 에 U2·U3 가 열려 있으면 안 된다",
                "3. **재배포 축이 등급과 헷갈리지 않았는가** — 🚨 등급 G3 인데 재배포 불가인 것이 있다 (D-71)",
                "4. **근거 URL 이 실제로 그 조건을 말하는가**",
                "",
                "> 🚨 **이견이 하나라도 있으면 그 소스는 수집하지 않습니다.** "
                "동의만 적고 넘어가는 검토는 게이트가 아닙니다 (D-66).",
                "",
                "| 소스 | 이름 | 등급 | 열린 용도 | 제약 | 재배포 | 판정자 | 동의/이견 | 비고 |",
                "|---|---|:-:|---|---|:-:|---|:-:|---|",
                *rows,
                "",
                "## 기입 방법",
                "",
                "```yaml",
                "# scripts/registry_review.yaml",
                "law_go_kr:",
                "  decided_by: 오한빈",
                "  decided_at: 2026-08-20",
                "  reviewed_by: 권소라      # 🚨 판정자와 달라야 한다 (ck_source_four_eyes)",
                "  reviewed_at: 2026-08-31",
                "  collected_at: null       # 손으로 적지 않는다 — 수집기가 찍는다",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"검토 대상 {len(pending)}건 / 수집 대상 {len(targets)}건 (전체 {len(sources)}건)")
    print(f"→ {OUT.relative_to(ROOT)}")
    if pending:
        print("🚨 검토가 끝날 때까지 collect.registry.require() 가 수집을 거부한다 (D-90 ④)")


if __name__ == "__main__":
    main()
