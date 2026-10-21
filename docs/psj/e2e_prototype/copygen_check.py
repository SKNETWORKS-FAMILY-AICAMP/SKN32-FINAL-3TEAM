"""생성 그래프 점검 — 앱의 카피 생성(`app.routers.copygen.generate`)을 권소라 시험 사례 13개로 돌려 분기별로 센다 (박수진 · 2026-10-19).

화면(`POST /u/generate`)이 부르는 바로 그 함수를 부른다 — GPT 생성 → 코드 필터 → 판정 그래프 전체(잠금된 인코더 판) → 보수 · 균형 · 공격.
분기마다: 결과(ok · 탐색 실패) · 라운드 · 남긴 수 · 고른 셋의 「문턱까지 거리」와 가장 가까운 유형 · 탈락 사유(코드 필터 사유 · 판정 사유 · 판정에서 걸린 유형) · 걸린 시간.

  $env:PYTHONPATH="."; uv run python docs\\psj\\e2e_prototype\\copygen_check.py              # 13 사례 전부
  $env:PYTHONPATH="."; uv run python docs\\psj\\e2e_prototype\\copygen_check.py --case cos_yes_1
🚨 `.env` 에 `COPYLANE_COPYGEN=gpt` 와 `OPENAI_API_KEY` 가 있어야 한다(생성 경로만 GPT 를 부른다) · DB 와 잠금 인코더 판이 필요하다.
🚨 결과 JSON(`build/copygen_check/`)에는 생성 문구가 들어 있다 — git 무시 폴더 · 올리지 않는다. 화면에 찍는 것은 건수 · 유형 · 거리뿐이다.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
CASES = ROOT / "docs" / "ksr" / "llm_copy" / "cases.json"
OUT = ROOT / "build" / "copygen_check"
TYPE = re.compile(r"(질병_예방치료_표방|건강기능식품_오인|의약품_오인|거짓_과장|소비자_기만|후기_체험기_기만|부당_비교광고|비방광고|기능성화장품_오인)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", help="사례 id (여러 번 · 비우면 전부)")
    a = ap.parse_args(argv)
    from app import encoder as enc
    from app.routers import copygen as cg

    if why := cg.off_reason():
        raise SystemExit(f"🔴 생성 엔진을 못 쓴다 — {why}")
    mdir = enc.configured_dir()
    lock = enc.lock_match(mdir)
    print(f"인코더 판: {mdir.name} · 잠금 {lock.status}")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if a.case:
        cases = [c for c in cases if c["id"] in set(a.case)]
    rows, dump = [], []
    for c in cases:
        t0 = time.time()
        try:
            res = cg.generate(c["branch"], c["inputs"])
            err = ""
        except Exception as e:  # noqa: BLE001 — 사례마다 결과를 남긴다
            res, err = None, f"{type(e).__name__}: {e}"
        sec = time.time() - t0
        if res is None:
            rows.append((c["id"], "오류", 0, 0, err[:80], "", "", sec)); dump.append({"case": c["id"], "error": err}); continue
        reasons = res.reasons()
        jhits = collections.Counter()
        for d in res.dropped:
            if d["reason"] == "judge":
                kind = d["hit"].split(" · ")[0]
                types = TYPE.findall(d["hit"]) or ["—"]
                for t in set(types):
                    jhits[f"{kind}:{t}"] += 1
        picks = " / ".join(f"{k.tier or '-'} {k.closeness:.2f}({k.top})" for k in res.picked)
        rows.append((c["id"], res.status, len(res.rounds), len(res.kept), dict(reasons), dict(jhits.most_common(4)), picks, sec))
        dump.append({"case": c["id"], "branch": c["branch"], "status": res.status, "rounds": res.rounds, "notice": res.notice,
                     "kept": [k.__dict__ for k in res.kept], "picked": [k.__dict__ for k in res.picked], "dropped": res.dropped, "sec": sec})
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"copygen_check_{datetime.datetime.now():%Y%m%d_%H%M}.json"
    p.write_text(json.dumps({"model_dir": mdir.name, "lock": lock.status, "cases": dump}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n| 사례 | 결과 | 라운드 | 남김 | 탈락 사유 | 판정에서 걸린 것 (상위 4) | 고른 셋 (거리 · 가까운 유형) | 초 |\n|---|---|---:|---:|---|---|---|---:|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]:.0f} |")
    ok = sum(1 for r in rows if r[1] == "ok")
    print(f"\n✅ ok {ok} / {len(rows)} · 결과 JSON(생성 문구 포함 · 올리지 않음): {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
