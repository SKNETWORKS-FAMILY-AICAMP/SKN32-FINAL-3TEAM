"""extract_rationale.py — 판정매트릭스에서 **판정 근거**를 뽑아 검토용 YAML 로 옮긴다.

🚨 왜 별도 파일인가
   `data_sources.yaml` 은 **수집기가 읽는 집행 목록**이다. 판정 근거는 사람이 읽는
   검토 자료이고 수집기는 한 번도 읽지 않는다. 집행 산출물에 산문을 섞으면
   게이트 테스트가 산문을 검사하게 된다. 그래서 근거는 옆 파일로 뺀다 (D-90).

🚨 왜 손으로 안 적고 뽑는가
   근거의 원본은 `docs/03_데이터/판정매트릭스.html` 이다. 손으로 옮기면 두 벌이
   갈라지고, 갈라진 순간 검토자는 **어느 쪽이 판정 근거인지 알 수 없다.**
   원본이 고쳐지면 이 스크립트를 다시 돌린다.

    uv run python scripts/extract_rationale.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs/03_데이터/판정매트릭스.html"
OUT = ROOT / "scripts/registry_rationale.yaml"

# 매트릭스의 다섯 질문 열. 레지스트리 U1~U4 와 이름이 다르다 — 매핑을 명시한다.
NOTE_KEYS = {
    "train": "U1 학습",
    "commercial": "상업",
    "raw": "원문",
    "cite": "U3 인용",
    "deploy": "U4 배포",
}

FIELD = r"{f}:'((?:[^'\\]|\\.)*)'"

# 🚨 매트릭스 id 와 레지스트리 키가 다른 것들.
#    D-90 — 매트릭스는 「판정 근거」 단위(73건), 레지스트리는 「이용조건」 단위(43건)라
#    1:1 이 아니다. 이름만 다른 것은 1:1 로 잇고, 조건 하나로 묶인 것은 N:1 로 잇는다.
#    이 표가 없으면 검토표에 「판정 근거 없음」이 뜨는데, 근거는 있고 이름만 어긋난 것이다.
ALIAS: dict[str, list[str]] = {
    "ftc_decisions": ["ftc_decisions_bulk"],
    "kcia_guideline": ["kcia_guideline_2025"],
    "k_mhas": ["kmhas"],
    "aihub_review_corpus": ["aihub_review"],
    # 법제처 OPEN API 는 OC 키 하나·조건 하나라 11종이 레지스트리 1건으로 묶인다.
    "law_go_kr": [
        "law_acts",
        "law_annex",
        "mfds_notice",
        "func_claim_rule",
        "ftc_guidelines",
        "cosmetic_guides",
        "sanction_annex",
        "penalty_notice",
        "penal_clause",
        "admin_appeal",
        "precedent",
    ],
}

BUNDLE_WHY = (
    "법제처 OPEN API 로 받는 11종을 **이용조건 하나**로 묶은 것이다 (D-90). "
    "전부 공공저작물이라 조건이 같고, OC 키도 하나다. 개별 근거는 아래와 같다."
)


def clean(v: str) -> str:
    """HTML 태그와 엔티티를 벗긴다. 근거는 산문이지 마크업이 아니다."""
    v = v.replace("\\'", "'").replace("\\n", " ")
    v = re.sub(r"<[^>]+>", "", v)
    return html.unescape(v).strip()


def field(blob: str, name: str) -> str | None:
    m = re.search(FIELD.format(f=name), blob)
    return clean(m.group(1)) if m else None


def main() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(r"\{id:'", text)]
    starts.append(len(text))

    out: dict[str, dict] = {}
    for i in range(len(starts) - 1):
        blob = text[starts[i] : starts[i + 1]]
        key = field(blob, "id")
        if not key:
            continue
        entry: dict = {}
        for f in ("why", "valueNote", "url"):
            v = field(blob, f)
            if v:
                entry[f] = v
        nm = re.search(r"note:\{(.*?)\},\s*\n", blob, re.S) or re.search(
            r"note:\{(.*?)\}", blob, re.S
        )
        if nm:
            note = {}
            for nk, label in NOTE_KEYS.items():
                v = field(nm.group(1), nk)
                if v:
                    note[label] = v
            if note:
                entry["note"] = note
        if entry:
            out[key] = entry

    # 레지스트리 키로도 찾을 수 있게 잇는다. 매트릭스 id 키는 그대로 남긴다.
    for reg_key, mat_ids in ALIAS.items():
        found = [(m, out[m]) for m in mat_ids if m in out]
        if not found:
            continue
        if len(found) == 1:
            out[reg_key] = dict(found[0][1])
        else:
            out[reg_key] = {
                "why": BUNDLE_WHY,
                "bundle": {m: e.get("why", "") for m, e in found},
            }

    OUT.write_text(
        "# 생성물 — scripts/extract_rationale.py 가 판정매트릭스.html 에서 뽑는다.\n"
        "# 🚨 손으로 고치지 마십시오. 근거를 바꾸려면 판정매트릭스를 고치고 다시 뽑습니다.\n"
        + yaml.safe_dump(out, allow_unicode=True, sort_keys=True, width=10**6),
        encoding="utf-8",
    )
    with_why = sum(1 for v in out.values() if v.get("why"))
    with_note = sum(1 for v in out.values() if v.get("note"))
    print(f"엔트리 {len(out)}건 — why {with_why} · 용도별 근거 {with_note}")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
