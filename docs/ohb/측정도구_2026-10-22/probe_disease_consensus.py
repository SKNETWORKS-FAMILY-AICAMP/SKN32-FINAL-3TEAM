"""build/probe_disease_consensus.py — D-340 결정 2 「질병 표방 합의 확정」의 관문 ㉠ ㉡ 을 잰다 (2026-10-14 · 클론 A · git 무시).

판정 코드를 바꾸지 않는다 — 지금 응답에서 「합의로 확정될 문장」을 센다.
  질병 합의 = 보류 문장 ∧ `violations`(사전의 자격 없는 적중 유형)에 질병_예방치료_표방 ∧ 인코더 후보(옮긴 것 제외)에도 같은 유형

  uv run python build/probe_disease_consensus.py --axis                       # ㉠ 주의사항 관측 축 (DB · 인코더 필요)
  uv run python build/probe_disease_consensus.py --eval build/eval/<dev 결과>.json   # ㉡ dev (eval_graph 결과 파일을 읽기만)

㉠ 관측 축 — `data/derived/hf_display_claims.jsonl` 의 섭취 주의사항(`IFTKN_ATNT_MATR_CN`)을 문장으로 나누고(`app.sentsplit.split`)
   앞의 번호 · 기호를 떼고 같은 문장을 한 번만 센다. 🚨 원장 09-29 의 「274 문장」을 만든 절차와 같은지는 대조하지 않았다 —
   이 도구가 센 문장 수를 함께 적는다. 전부 표시 · 주의 문구라 질병 합의 확정은 모두 오확정이다.
㉡ dev — 결과 파일의 행 예측(`candidates` · `enc_candidates` · `committed`)과 골든 조건 · 라벨로 센다(원장 10-14(A) ② 와 같은 정의).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DISEASE = "질병_예방치료_표방"
AXIS = ROOT / "data/derived/hf_display_claims.jsonl"
GOLDEN = ROOT / "data/derived/golden/golden.jsonl"
#: 앞의 기호(◆ · ※ · - …)와 번호(1. · 1) · 가. · ①)를 뗀다
_SYMBOLS = re.compile(r"^[^0-9A-Za-z가-힣]+")
_NUMBER = re.compile(r"^(\d{1,2}|[가-하])[\.\)]\s*")


def axis_sentences() -> list[str]:
    from app.sentsplit import split  # noqa: PLC0415

    seen: dict[str, None] = {}
    for line in AXIS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line).get("IFTKN_ATNT_MATR_CN") or ""
        for s in split(raw):
            s = _NUMBER.sub("", _SYMBOLS.sub("", s)).strip()
            s = _SYMBOLS.sub("", s).strip()
            if len(s) >= 4:
                seen.setdefault(s, None)
    return list(seen)


def consensus(s) -> bool:  # noqa: ANN001 — SentenceJudgment
    if s.verdict.value != "hold":
        return False
    mine = {v.value for v in s.violations}
    enc = {c.violation.value for c in s.encoder_candidates if c.moved_from is None}
    return DISEASE in mine and DISEASE in enc


def run_axis() -> int:
    from app.api import judge  # noqa: PLC0415 — `POST /judge` 와 같은 함수 (D-119)
    from app.contracts import JudgeRequest  # noqa: PLC0415

    sents = axis_sentences()
    hit_disease = agreed = 0
    shown: list[str] = []
    encoded = None
    for text in sents:
        res = judge(JudgeRequest(text=text))
        encoded = res.judged_by
        for s in res.sentences:
            if DISEASE in {v.value for v in s.violations}:
                hit_disease += 1
            if consensus(s):
                agreed += 1
                shown.append(s.text)
    print(f"[관측 축] 입력 문장 {len(sents)} · 판정 {encoded}")
    print(f"  사전이 질병으로 걸린 문장 {hit_disease} · 질병 합의(= 확정될 문장 · 모두 오확정) {agreed}")
    print(f"  관문 ㉠ (≤ 1) — {'통과' if agreed <= 1 else '넘음'}")
    for t in shown:
        print("   ·", t[:80])
    if "+encb:" not in (encoded or ""):
        print("  🔴 인코더가 돌지 않았다(judged_by 에 +encb: 없음) — 이 수는 관문이 아니다")
        return 1
    return 0


def run_eval(path: Path) -> int:
    g = {}
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        g[r["id"]] = r
    d = json.loads(path.read_text(encoding="utf-8"))
    n = ok = law = m = 0
    for p in d["rows"]:
        if p.get("committed"):
            continue
        if DISEASE in p.get("candidates", ()) and DISEASE in p.get("enc_candidates", ()):
            n += 1
            cond = g[p["id"]]["조건"]
            if cond in ("D", "L"):
                law += 1
            elif cond == "M":
                m += 1
            elif cond == "C":
                ok += 1  # 질병은 사유 C — 라벨 조건 C 와 맞으면 일치
    scored = n - m - law
    rate = ok / scored if scored else 0.0
    print(f"[dev] {path.name} · 판정 {d.get('judged_by')} · 인코더 {str(d.get('encoder_sha'))[:12]}")
    print(f"  질병 합의 {n} · 사유 일치 {ok} / {scored} ({rate:.1%}) · 적법(D · L) {law} · 라벨 모호(M) {m}")
    gate = rate >= 0.85 and law <= 1
    print(f"  관문 ㉡ (사유 일치 ≥ 85% ∧ 적법 ≤ 1) — {'통과' if gate else '넘음'}")
    return 0 if gate else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--axis", action="store_true")
    ap.add_argument("--eval", type=Path)
    a = ap.parse_args()
    code = 0
    if a.axis:
        code |= run_axis()
    if a.eval:
        code |= run_eval(a.eval)
    if not (a.axis or a.eval):
        ap.error("--axis 또는 --eval 을 준다")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
