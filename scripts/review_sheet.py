"""review_sheet.py — S0-14 2인 확인 검토표를 뽑는다 (D-66 · D-90 ④).

🚨 이 표는 「검토자가 판정을 **재현할 수 있는가**」를 위한 것이다.
   등급만 나열하면 검토자가 할 수 있는 일은 동의를 찍는 것뿐이고,
   **동의만 찍는 검토는 게이트가 아니다** (D-66).

🚨 판정 근거는 `caution` 이 아니다.
   `caution` 은 「이걸 쓸 때 조심할 것」이고, 판정 근거는 판정매트릭스의 `why` 다.
   둘을 바꿔 실으면 검토자는 활용 아이디어를 읽고 등급에 서명하게 된다.
   근거는 `scripts/registry_rationale.yaml` 에서 온다 (extract_rationale.py).

🚨 건수를 뭉뚱그리지 않는다.
   「용도가 열린 것」과 「status: collect」는 다른 집합이다. 우연히 둘 다 33이라
   같아 보였을 뿐이고, 실제로 겹치는 것은 29건이다.

절차
    py -m uv run python scripts/extract_rationale.py   # 근거가 바뀌었을 때만
    uv run python scripts/review_sheet.py
    → 검토자가 A 를 자세히, B 를 확인, C 를 훑는다
    → scripts/registry_review.yaml 에 reviewed_by · reviewed_at 기입
    → uv run python scripts/gen_registry.py → uv run pytest -m gate
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data_sources.yaml"
LEDGER = ROOT / "scripts/registry_review.yaml"
RATIONALE = ROOT / "scripts/registry_rationale.yaml"
OUT = ROOT / "docs/03_데이터/S0-14_2인확인_검토표.md"

USES = ["U1", "U2", "U3", "U4"]
# 🚨 SA 는 D-60(저장소 공개 라이선스)의 선결 사안이다 — 「데이터셋을 쓸 수 있는가」와
#    「학습 산출물을 어떤 라이선스로 배포할 수 있는가」는 다른 질문이고 후자가 D-60 을 좌우한다.
#    빠져 있어서 k_mhas·klue_dataset 이 C(자명)에 있었다 (권소라 역검토 v1.2 §7).
RISKY_FLAGS = ("GATED", "TOS", "PREAPPROVAL", "NOSTORE", "QUERYLOG", "PII", "NC", "SA")

# 🚨 판정 근거가 스스로 「못 봤다」고 말하는 표현.
#    등급은 맞을 수 있으나 **확인되지 않은 것**이고, 확인되지 않은 것은 자명할 수 없다.
#    (판정매트릭스: 「미확인」을 「아마 괜찮음」으로 읽는 순간 등급이 무의미해진다)
UNVERIFIED = ("미확인", "확인 필요", "확인필요", "불명", "차단돼", "차단으로")


def risk(s: dict, r: dict | None = None) -> tuple[int, list[str]]:
    """위험 점수와 그 이유. 🚨 점수가 아니라 **이유**가 검토자에게 필요한 것이다.

    G0 는 채점하지 않는다 — 전 용도 deny 로 닫혀 있어 검토 대상에 들어올 수 없다.
    (판정매트릭스: 「미확인」을 「아마 괜찮음」으로 읽는 순간 등급이 무의미해진다)
    """
    score, why = 0, []
    grade = s.get("grade")
    flags = set(s.get("constraints") or [])
    use = s.get("use") or {}

    if grade == "G2":
        score += 3
        why.append("**G2 — 사실만 추출 · 원문 미보관.** U2·U3 가 열려 있으면 정의 위반")
    if not s.get("redistributable"):
        score += 4
        why.append(
            "🚨 **재배포 불가.** 등급과 다른 축이다 — 등급 G3 라도 데이터셋 배포는 막힌다 (D-71)"
        )
    hit = sorted(flags & set(RISKY_FLAGS))
    if hit:
        score += len(hit)
        why.append(f"제약 {', '.join(hit)} — 각각이 별도 확인 대상")
    text = (s.get("name") or "") + (s.get("caution") or "")
    if "정정" in text or "🔄" in text:
        score += 2
        why.append("**판정이 한 번 바뀐 이력**이 있다 — 무엇이 왜 바뀌었는지 확인")
    blob = ((r or {}).get("why") or "") + " ".join(((r or {}).get("note") or {}).values())
    seen = sorted({w for w in UNVERIFIED if w in blob})
    if seen:
        # 🚨 단독으로 A 구간(>=4)에 올린다. 확인되지 않은 소스는 「확인만」이 될 수 없고,
        #    B 구간은 이 지시를 실을 자리가 없다.
        score += 4
        why.append(
            f"🚨 **판정 근거가 스스로 「{seen[0]}」이라고 적고 있다.** "
            "등급은 맞을 수 있으나 **확인된 적이 없다** — 확인되지 않은 것은 자명할 수 없다. "
            "**근거 URL 을 열어 이용허락범위를 눈으로 확인**하고, 확인되면 팀장에게 근거 갱신을 "
            "요청하고, 열리지 않으면 그것이 이견이다"
        )
    if (r or {}).get("bundle"):
        n = len((r or {})["bundle"])
        score += 2
        why.append(
            f"**{n}종이 한 건으로 묶인 등재**다 (D-90) — 서명 한 번이 {n}종 전부에 걸린다. "
            "묶은 근거(조건이 정말 같은가)를 먼저 확인한다"
        )
    if grade != "G3" and any(use.get(u) == "allow" for u in ("U2", "U3")):
        score += 3
        why.append("🚨 **등급 상한 초과 의심** — G3 아닌데 원문 색인·화면 인용이 열려 있다")
    return score, why


def opened(s: dict) -> str:
    use = s.get("use") or {}
    return " ".join(u for u in USES if use.get(u) == "allow") or "—"


def hold_mark(s: dict) -> str:
    return "" if s.get("status") == "collect" else f"  ⏸ **{s.get('status')}**"


def basis(key: str, rat: dict) -> list[str]:
    """판정 근거 — 검토자가 등급을 재현하는 데 쓰는 것."""
    r = rat.get(key) or {}
    if not r.get("why"):
        return [
            "",
            "**판정 근거** — ⬜ **없습니다.**",
            "",
            "> 🚨 판정매트릭스에 이 id 의 엔트리가 없습니다 (D-90 — 매트릭스 73건은 "
            "「판정 근거」 단위, 레지스트리 43건은 「이용조건」 단위라 1:1 이 아닙니다). "
            "검토자는 등급을 재현할 수 없으므로, 팀장이 근거를 적어 주기 전에는 "
            "이 소스에 서명하지 마십시오.",
        ]
    lines = ["", "**판정 근거** (판정매트릭스 `why`)", "", f"> {r['why']}"]
    if r.get("bundle"):
        lines += ["", f"묶인 {len(r['bundle'])}종의 개별 근거"]
        lines += [f"- **{m}** — {w}" for m, w in r["bundle"].items()]
    if r.get("note"):
        lines += ["", "용도별 근거"]
        lines += [f"- **{k}** — {v}" for k, v in r["note"].items()]
    return lines


def block(key: str, s: dict, led: dict, rat: dict) -> list[str]:
    _, why = risk(s, rat.get(key))
    lines = [
        f"### `{key}` — {s.get('name', '')}{hold_mark(s)}",
        "",
        f"| 등급 | **{s.get('grade')}** | 열린 용도 | {opened(s)} |",
        "|---|---|---|---|",
        f"| 제약 | {', '.join(s.get('constraints') or []) or '—'} "
        f"| 재배포 | {'가능' if s.get('redistributable') else '🚨 **불가**'} |",
        f"| 판정 | {led.get('decided_by') or '—'} ({led.get('decided_at') or '일자 미상'}) "
        f"| 규모 | {str(s.get('scale') or '—')[:60]} |",
        "",
        "**왜 자세히 봐야 하는가**",
        "",
    ]
    lines += [f"- {w}" for w in why]
    lines += basis(key, rat)
    if s.get("caution"):
        lines += [
            "",
            "**활용 주의** — 판정 근거가 아니라 쓸 때 조심할 것입니다.",
            "",
            f"> {str(s['caution'])[:600]}",
        ]
    ev = s.get("evidence_url")
    lines += ["", f"**근거 확인** → <{ev}>" if ev else "**근거 확인** → ⬜ URL 없음 (하단 참조)"]
    if s.get("access"):
        lines += ["", f"접근 방법: {s['access']}"]
    lines.append("")
    return lines


def compact(key: str, s: dict, rat: dict) -> list[str]:
    """B 구간 — 표는 근거를 못 싣는다. 한 줄 근거를 붙인 목록으로 낸다."""
    ev = s.get("evidence_url")
    r = rat.get(key) or {}
    head = (
        f"**`{key}`** — {s.get('name', '')}{hold_mark(s)}  \n"
        f"**{s.get('grade')}** · 열린 용도 {opened(s)} · "
        f"제약 {', '.join(s.get('constraints') or []) or '없음'} · "
        f"재배포 {'가능' if s.get('redistributable') else '🚨 불가'} · "
        + (f"[근거 확인]({ev})" if ev else "⬜ URL 없음")
    )
    body = (
        f"> {r['why']}"
        if r.get("why")
        else "> ⬜ 판정 근거 없음 — 서명 전에 팀장에게 요청하십시오."
    )
    out = [head, "", body, ""]
    if s.get("caution"):
        out += [f"> ⚠️ **활용 주의** — {str(s['caution'])[:300]}", ""]
    if r.get("bundle"):
        out += [f"- **{m}** — {w}" for m, w in r["bundle"].items()] + [""]
    return out


def row(key: str, s: dict) -> str:
    ev = s.get("evidence_url")
    return (
        f"| `{key}` | {str(s.get('name', ''))[:38]} | **{s.get('grade')}** | {opened(s)} "
        f"| {', '.join(s.get('constraints') or []) or '—'} "
        f"| {'가능' if s.get('redistributable') else '🚨 불가'} "
        f"| {f'[근거]({ev})' if ev else '⬜ 없음'} |"
    )


def url_gap(key: str, s: dict) -> tuple[str, str]:
    """근거 URL 이 없는 이유를 가른다. 넷을 똑같이 🚨 로 세우면 실제보다 부풀려진다."""
    # 🚨 「보류」 조건에 **용도 개방 여부**를 함께 본다. 검토표 자신의 논리가
    #    *"수집 계획이 없어도 용도가 열려 있으면 누군가 부르면 나간다"* 인데 여기만 status 로
    #    갈라서, A그룹에 있는 소스가 「채울 것 0건」으로 집계됐다 (권소라 역검토 v1.2 §8).
    opened_any = any((s.get("use") or {}).get(u) == "allow" for u in USES)
    if s.get("status") != "collect" and not opened_any:
        return (
            "보류",
            f"`{key}` — status `{s.get('status')}` · 전 용도 닫힘. 지금 채우지 않습니다.",
        )
    if str(s.get("org") or "").startswith("★") or "우리" in str(s.get("org") or ""):
        return "자체", (
            f"`{key}` — 자체 산출물이라 외부 URL 이 존재하지 않습니다. "
            "대신 **산출 근거 문서 경로**를 evidence_url 자리에 적습니다."
        )
    return (
        "필요",
        f"`{key}` — {s.get('name')} · 접근 「{s.get('access')}」. **팀장이 URL 을 채워야 합니다.**",
    )


def main() -> None:
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    ledger = yaml.safe_load(LEDGER.read_text(encoding="utf-8")) or {}
    rat = yaml.safe_load(RATIONALE.read_text(encoding="utf-8")) if RATIONALE.exists() else {}
    rat = rat or {}

    sources = {k: v for k, v in (reg.get("sources") or {}).items() if isinstance(v, dict)}
    targets = {
        k: v
        for k, v in sources.items()
        if any((v.get("use") or {}).get(u) == "allow" for u in USES)
    }
    planned = {k: v for k, v in sources.items() if v.get("status") == "collect"}
    both = set(targets) & set(planned)
    closed = {k: v for k, v in planned.items() if k not in targets}
    pending = {k: v for k, v in targets.items() if not (ledger.get(k) or {}).get("reviewed_by")}

    scored = sorted(pending.items(), key=lambda kv: -risk(kv[1], rat.get(kv[0]))[0])
    a = [(k, s) for k, s in scored if risk(s, rat.get(k))[0] >= 4]
    b = [(k, s) for k, s in scored if 1 <= risk(s, rat.get(k))[0] < 4]
    c = [(k, s) for k, s in scored if risk(s, rat.get(k))[0] == 0]

    gaps = [(url_gap(k, s), k) for k, s in pending.items() if not s.get("evidence_url")]
    need = [g for g in gaps if g[0][0] == "필요"]
    no_basis = [k for k in pending if not (rat.get(k) or {}).get("why")]

    L: list[str] = [
        "# S0-14 · 2인 확인 검토표",
        "",
        "> 🚨 **생성물입니다. 이 파일에 결과를 적지 마십시오 — 재생성하면 사라집니다.**",
        "> 검토 결과는 `scripts/registry_review.yaml` 에 적습니다 (하단 「기입 방법」).",
        "",
        "## 무엇이 검토 대상인가",
        "",
        "| 집합 | 건수 |",
        "|---|:-:|",
        f"| 레지스트리 전체 | {len(sources)} |",
        f"| 용도가 하나라도 열린 것 — **게이트가 통과시킬 수 있는 것** | **{len(targets)}** |",
        f"| `status: collect` — 수집 계획이 있는 것 | {len(planned)} |",
        f"| 둘 다인 것 | {len(both)} |",
        f"| 아직 `reviewed_by` 가 비어 있어 **이 표에 실린 것** | **{len(pending)}** |",
        "",
        "> 🚨 앞의 두 숫자가 같아도 **같은 집합이 아닙니다.** 검토는 「수집할 것」이 아니라 "
        "**「게이트가 통과시킬 수 있는 것」**을 대상으로 합니다 — 수집 계획이 없어도 용도가 "
        "열려 있으면 누군가 부르면 나갑니다.",
        "",
        "## 이 검토가 막으려는 것",
        "",
        "> **동의만 찍는 검토는 게이트가 아닙니다** (D-66).",
        "> 그래서 아래에 **판정 근거(왜 이 등급인가)** 와 **근거 URL** 을 함께 실었습니다.",
        "> 검토자는 판정을 **재현**해 보십시오. 재현이 안 되면 그것이 이견입니다.",
        "",
        "> ⚠️ **「판정 근거」와 「활용 주의」는 다릅니다.** 앞은 등급을 그렇게 본 이유이고, "
        "뒤는 쓸 때 조심할 것입니다. 서명의 대상은 **앞** 입니다.",
        "",
        "**확인하는 것 넷**",
        "",
        "1. **등급이 맞는가** — G3(원문 자유) · G2(사실만·원문 미보관) · G0(미표기 → fail-closed)",
        "2. **열린 용도가 등급 상한을 넘지 않는가** — G2 에 U2(원문 색인)·U3(화면 인용)가 열리면 정의 위반",
        "3. **재배포 축을 등급과 혼동하지 않았는가** — 🚨 등급 G3 인데 재배포 불가인 것이 있습니다 (D-71)",
        "4. **근거 URL 이 실제로 그 조건을 말하는가** — 링크를 열어 보십시오",
        "",
        "## 이견이 나오면",
        "",
        "| 단계 | 하는 일 |",
        "|:-:|---|",
        "| 1 | `reviewed_by` 를 **비워 둡니다.** 채우면 게이트가 열립니다 |",
        "| 2 | 이견 내용을 팀장에게 전달 — 무엇이 어떤 근거로 다른지 |",
        "| 3 | 팀장이 재판정하고 `decided_at` 을 갱신 |",
        "| 4 | 재검토 후 동의하면 그때 `reviewed_by` 기입 |",
        "",
        "> 🚨 **이견이 하나라도 있으면 그 소스는 수집하지 않습니다.** 나머지 소스는 영향받지 않습니다.",
        "",
        "---",
        "",
        f"## A. 자세히 봐야 하는 것 ({len(a)}건)",
        "",
        "> 등급 경계 · 재배포 제약 · 판정 변경 이력이 있는 소스입니다. **여기에 시간을 씁니다.**",
        "",
    ]
    for k, s in a:
        L += block(k, s, ledger.get(k) or {}, rat)

    L += [
        "---",
        "",
        f"## B. 확인만 하면 되는 것 ({len(b)}건)",
        "",
        "> 제약이 하나둘 붙어 있으나 등급은 명확합니다. 근거를 읽고 링크를 열어 확인하십시오.",
        "",
    ]
    for k, s in b:
        L += compact(k, s, rat)

    L += [
        "---",
        "",
        f"## C. 거의 자명한 것 ({len(c)}건)",
        "",
        "> 공공기관 공식 API·공표 자료로 제약이 없습니다. 훑어보고 넘어가도 됩니다.",
        "",
        "| 소스 | 이름 | 등급 | 열린 용도 | 제약 | 재배포 | 근거 |",
        "|---|---|:-:|---|---|:-:|:-:|",
        *[row(k, s) for k, s in c],
        "",
    ]
    # 🚨 표에는 자리가 없어 「활용 주의」가 통째로 사라졌다. 팀이 **검토해서 수용하기로 한
    #    리스크**가 기록에서 없어지면, 나중에 「이걸 왜 괜찮다고 했는지」부터 다시 조사해야 한다
    #    (D-21 · 권소라 역검토 v1.2 §9).
    cc = [(k, s) for k, s in c if s.get("caution")]
    if cc:
        L += [
            f"**C 구간의 활용 주의 ({len(cc)}건)** — 판정 근거가 아니라 쓸 때 조심할 것입니다.",
            "",
        ]
        L += [f"- **`{k}`** — {str(s['caution'])[:300]}" for k, s in cc]
        L += [""]

    if closed:
        L += [
            "---",
            "",
            f"## 게이트가 이미 닫아 둔 것 ({len(closed)}건) — 검토 불필요",
            "",
            "> `status: collect` 이지만 **전 용도 deny** 입니다. 게이트가 어떤 용도로도 "
            "내보내지 않으므로 2인 확인의 대상이 아닙니다. 여는 것은 **재판정**이지 검토가 아닙니다.",
            "",
            "| 소스 | 이름 | 등급 | 닫아 둔 이유 |",
            "|---|---|:-:|---|",
            *[
                f"| `{k}` | {str(s.get('name'))[:34]} | **{s.get('grade')}** "
                f"| {'G0 — 미판정이라 fail-closed' if s.get('grade') == 'G0' else str(s.get('access'))[:46]} |"
                for k, s in closed.items()
            ],
            "",
        ]

    if gaps:
        L += [
            "---",
            "",
            f"## ⬜ 근거 URL 이 없는 소스 ({len(gaps)}건)",
            "",
            f"> 그중 **검토 전에 반드시 채워야 하는 것은 {len(need)}건** 입니다. "
            "나머지는 성격상 URL 이 없거나 지금 채울 이유가 없습니다.",
            "",
        ]
        for label, head in [
            ("필요", "🚨 채워야 합니다"),
            ("자체", "산출물 — 외부 URL 없음"),
            ("보류", "보류 소스"),
        ]:
            items = [g for g in gaps if g[0][0] == label]
            if items:
                L += [f"**{head}** ({len(items)}건)", "", *[f"- {g[0][1]}" for g in items], ""]

    if no_basis:
        L += [
            "---",
            "",
            f"## ⬜ 판정 근거가 없는 소스 ({len(no_basis)}건)",
            "",
            "> 🚨 **이 소스들에는 서명하지 마십시오.** 판정매트릭스에 대응 엔트리가 없어 "
            "검토자가 등급을 재현할 수 없습니다. 팀장이 근거를 적은 뒤 재생성합니다.",
            "",
            *[f"- `{k}` — {sources[k].get('name')}" for k in no_basis],
            "",
        ]

    L += [
        "---",
        "",
        "## 기입 방법",
        "",
        "```yaml",
        "# scripts/registry_review.yaml  ← 여기에 적습니다",
        "law_go_kr:",
        "  decided_by: 오한빈",
        "  decided_at: 2026-08-20",
        "  reviewed_by: 권소라      # 🚨 판정자와 달라야 합니다 (ck_source_four_eyes)",
        "  reviewed_at: 2026-08-31",
        "  collected_at: null       # 손으로 적지 않습니다 — 수집기가 찍습니다",
        "```",
        "",
        "기입 후 `uv run python scripts/gen_registry.py` → `uv run pytest -m gate` 로 확인합니다.",
        "",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"검토 대상 {len(pending)}건 — A 자세히 {len(a)} · B 확인 {len(b)} · C 자명 {len(c)}")
    print(f"집합: 용도열림 {len(targets)} · status collect {len(planned)} · 겹침 {len(both)}")
    if need:
        print(f"🚨 근거 URL 을 채워야 하는 것 {len(need)}건: {', '.join(g[1] for g in need)}")
    if no_basis:
        print(f"🚨 판정 근거 없음 {len(no_basis)}건: {', '.join(no_basis)}")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
