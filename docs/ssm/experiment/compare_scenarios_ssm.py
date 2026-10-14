"""같은 28 건을 두 번 돌린 결과(`judge_scenarios_ssm.py` 산출 JSON 둘)를 사례 단위로 견준다 — 소성민 · 2026-10-14.

★ 쓰임 — 인코더 `label_scheme.json` 을 F1 최대 판(`7268ad43…`)에서 카드 17 채택 판(D-324 · `max_len` 128 ·
   `3bd100cc…`)으로 바꾼 뒤, 10-13 실행과 새 실행을 견준다. 다른 판끼리 견줘도 된다.
🚨 지표가 아니다 — 지어낸 문구 28 건의 동작 차이를 보는 것이다(D-175 · 골든 · dev · 봉인셋을 읽지 않는다).
🚨 「뒤」 실행에 인코더가 실렸는지 먼저 본다 — 잠금(models.lock.json · D-333) 밖 판이면 앱이 인코더 없이
   규칙 판정으로 간다(D-323). 그때 `judged_by` 에 인코더 표지가 없고, 이 도구가 맨 위에 경고를 띄운다.

실행 (저장소 뿌리에서):
    uv run python docs/ssm/experiment/compare_scenarios_ssm.py 앞.json 뒤.json
결과:
    화면에 요약 · build/eval/ssm_compare_<앞>_vs_<뒤>.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(p: Path) -> dict:
    d = json.loads(p.read_text(encoding="utf-8"))
    d["by_id"] = {c["id"]: c for c in d["cases"]}
    return d


def _enc_mark(judged_by: str | None) -> str:
    """`judged_by` 의 인코더 표지 — `+enc:`(가중치 지문 · 옛) / `+encb:`(판 지문 · D-333) / 없음."""
    if not judged_by:
        return "-"
    for tag in ("+encb:", "+enc:"):
        if tag in judged_by:
            return tag[1:] + judged_by.split(tag, 1)[1][:12]
    return "인코더 없음"


def _viol(sents: list[dict]) -> str:
    return ",".join(sorted({v for s in sents for v in s["violations"]})) or "-"


def _verdicts(sents: list[dict]) -> str:
    return " ".join(
        s["verdict"] + (f"({s['hold_reason']})" if s.get("hold_reason") else "") for s in sents
    )


def _enc(sents: list[dict]) -> str:
    best: dict[str, float] = {}
    for s in sents:
        for c in s.get("encoder", []):
            # 옮긴 후보(전제에 따라 유형을 바꾼 것 · D-326 · D-338)는 「새←원래」로 적는다 — 문턱 효과와 가른다
            v = f"{c['v']}←{c['moved_from']}" if c.get("moved_from") else c["v"]
            best[v] = max(best.get(v, 0.0), c["p"])
    return ", ".join(f"{v} {p:.2f}" for v, p in sorted(best.items(), key=lambda x: -x[1])) or "-"


def _branches(c: dict) -> str:
    return " · ".join(f"{b['premise']}={b['outcome']}" for b in c.get("branches", [])) or "-"


def _cert(c: dict) -> str:
    cert = c.get("certificate")
    return cert["reason"] if cert else "-"


#: 견주는 칸 — (이름, 뽑는 함수)
FIELDS = [
    ("결과", lambda c: c.get("outcome") or f"ERROR {c.get('error')}"),
    ("기록 판정", lambda c: _verdicts(c.get("sentences", []))),
    ("위반 유형", lambda c: _viol(c.get("sentences", []))),
    ("인코더 후보", lambda c: _enc(c.get("sentences", []))),
    ("증명서", _cert),
    ("품목 분기", _branches),
    ("분기 위반", lambda c: _viol([s for b in c.get("branches", []) for s in b["sentences"]])),
    (
        "분기 인코더",
        lambda c: _enc([s for b in c.get("branches", []) for s in b["sentences"]]),
    ),
]


def compare(a: dict, b: dict) -> tuple[list[str], list[str]]:
    """(화면 줄, md 줄)."""
    out: list[str] = []
    md: list[str] = []
    marks_a = Counter(_enc_mark(c.get("judged_by")) for c in a["cases"])
    marks_b = Counter(_enc_mark(c.get("judged_by")) for c in b["cases"])
    if any(m == "인코더 없음" for m in marks_b):
        out.append(
            "🚨 뒤 실행에 인코더가 안 실린 사례가 있다 — 잠금 밖 판이거나 COPYLANE_MODEL_DIR 이 비었다. "
            "이 비교는 인코더 효과가 아니다."
        )
    head = [
        f"앞: {a['made_at']} · 인코더 {dict(marks_a)} · 법령판 {sorted({c.get('law_version') for c in a['cases']})}",
        f"뒤: {b['made_at']} · 인코더 {dict(marks_b)} · 법령판 {sorted({c.get('law_version') for c in b['cases']})}",
    ]
    out += head
    md += ["# 28 건 전후 비교", "", *[f"- {h}" for h in head], ""]

    ids = [c["id"] for c in a["cases"]] + [i for i in b["by_id"] if i not in a["by_id"]]
    changed: dict[str, list[tuple[str, str, str]]] = {}
    for cid in ids:
        ca, cb = a["by_id"].get(cid), b["by_id"].get(cid)
        if ca is None or cb is None:
            changed[cid] = [("사례", "있음" if ca else "없음", "있음" if cb else "없음")]
            continue
        diffs = [(n, f(ca), f(cb)) for n, f in FIELDS if f(ca) != f(cb)]
        if diffs:
            changed[cid] = diffs

    oa = Counter(c.get("outcome") for c in a["cases"])
    ob = Counter(c.get("outcome") for c in b["cases"])
    keys = sorted(set(oa) | set(ob), key=str)
    summ = [
        "결과 분포  " + " · ".join(f"{k}: {oa.get(k, 0)}→{ob.get(k, 0)}" for k in keys),
        f"바뀐 사례  {len(changed)} / {len(ids)}",
        f"첫 호출   {a['cases'][0]['ms']}ms → {b['cases'][0]['ms']}ms",
    ]
    out += summ
    md += ["## 요약", "", *[f"- {s}" for s in summ], ""]

    md += ["## 바뀐 사례", "", "| 사례 | 문구 | 칸 | 앞 | 뒤 |", "|---|---|---|---|---|"]
    for cid, diffs in changed.items():
        text = (a["by_id"].get(cid) or b["by_id"][cid])["text"]
        out.append(f"\n[{cid}] {text}")
        for n, x, y in diffs:
            out.append(f"   {n:7}  {x}\n   {'':7}→ {y}")
            md.append(f"| {cid} | {text} | {n} | {x} | {y} |")
    same = [cid for cid in ids if cid not in changed]
    md += ["", f"## 그대로인 사례 ({len(same)})", "", ", ".join(same) or "-", ""]
    return out, md


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    args = ap.parse_args()
    a, b = _load(args.before), _load(args.after)
    out, md = compare(a, b)
    print("\n".join(out))
    dest = ROOT / "build" / "eval" / f"ssm_compare_{args.before.stem}_vs_{args.after.stem}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(md), encoding="utf-8")
    print(f"\n저장 — {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
