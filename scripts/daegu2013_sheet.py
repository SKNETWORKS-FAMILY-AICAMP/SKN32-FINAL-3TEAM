"""대구지방식약청 「식품 등 허위과대광고 사례」(2013) — 확정 문구 전사 → 마스킹 → 파생물.

🚨 원천은 슬라이드 그림이라 글자가 없다. **사람이 원본에 대 확정한 문구 표**(`PHRASES` · 201 행)가 이 파일의 입력이다.
   그 표는 다시 만들 수 없는 **원천**이고 git 이 나르지 않는다(D-249 ⑥ — 인용 광고 문구 원문). 없는 기기에서는 멈춘다.
🔴 **마스킹** — 문구가 `mask.apply_policy(…, "mfds_daegu_ad_cases_2013")` 를 지난다(정책이 없으면 멈춘다 · D-72).
   전사 때 사람이 업체 · 제품 · 인명을 ○○ 로 가렸다. 규칙 축(업체명 · 상표 · 2인 확인 2026-10-04)이 바꾸는 자리는 0 이다
   — 0 이 아니게 되면 무엇이 바뀌었는지 보고 `EXPECTED_MASKED` 를 고친다(원장 10-03 ㊿-14).
🚨 **라벨을 만들지 않는다.** 조문 · 조건은 판독 판(`scripts/guide_statute_round.py` `dg`)의 일이다.

    uv run python scripts/daegu2013_sheet.py          # 인쇄만
    uv run python scripts/daegu2013_sheet.py --dump   # 파생물을 쓴다
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collect import registry  # noqa: E402
from preprocess import mask  # noqa: E402

SOURCE_ID = "mfds_daegu_ad_cases_2013"
PHRASES = ROOT / "data" / "derived" / "labels" / "daegu_2013" / "phrases.json"
OUT = ROOT / "data" / "derived" / "mfds_daegu_ad_cases_2013.jsonl"
#: 전사 한 행이 반드시 드는 칸
REQUIRED = ("번호", "쪽", "묶음", "품목", "문구")
#: 규칙 축이 바꾼 문구 수 [측정] — 기기 2026-10-05 · 201 행 중 0(전사 때 사람이 이미 가렸다)
EXPECTED_MASKED = 0
#: 이 원천의 문서 정보 — 레코드마다 싣는다(D-240 · D-290 ③ 기준 시점 · 판정 지위)
DOC = {
    "문서": "식품 등 허위과대광고 사례",
    "발행일": "2013",
    "기준시점": "2013",
    "판정지위": "행정기관 사례",
}


class SheetError(RuntimeError):
    """전사 표가 이 파일의 규칙에 안 맞는다 — 고르지 않고 멈춘다 (D-220)."""


def load(path: pathlib.Path | None = None) -> list[dict]:
    """전사 표를 읽는다. 🔴 없으면 멈춘다 — 빈 파생물을 내지 않는다 (D-220)."""
    path = PHRASES if path is None else path
    if not path.exists():
        raise SheetError(f"{path} 가 없다 — 확정 문구 전사(원천 · git 밖)를 이 기기로 옮긴다")
    got = json.loads(path.read_text(encoding="utf-8"))
    seen: set[int] = set()
    for r in got:
        miss = [f for f in REQUIRED if r.get(f) in (None, "")]
        if miss:
            raise SheetError(f"{r.get('번호')} 번 행에 빈 칸 {miss}")
        if r["번호"] in seen:
            raise SheetError(f"번호가 두 번 — {r['번호']}")
        seen.add(r["번호"])
    return got


def rows(path: pathlib.Path | None = None) -> tuple[list[dict], list[dict]]:
    """전사 → 마스킹을 지난 레코드와 치환 기록. **산출물로 나가는 모든 길이 여기를 지난다.**"""
    log: list[dict] = []
    out: list[dict] = []
    for r in load(path):
        text = mask.apply_policy(r["문구"], "", SOURCE_ID, log)
        rec = {**r, "문구": text, "원천": SOURCE_ID, **DOC}
        rec["바뀜"] = text != r["문구"]
        out.append(rec)
    return out, log


def verify(got: list[dict]) -> None:
    changed = sum(r["바뀜"] for r in got)
    if changed != EXPECTED_MASKED:
        raise SheetError(
            f"규칙 축이 바꾼 문구 {changed} ≠ 기대 {EXPECTED_MASKED} — 무엇이 바뀌었는지 보고 기대 수를 고친다 (D-17)"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="대구청 사례(2013) 확정 문구 → 파생물")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    a = ap.parse_args()
    got, log = rows()
    verify(got)
    registry.assert_derivable(got, who="daegu2013_sheet")
    live = [r for r in got if not r.get("제외")]
    print(f"행 {len(got)} · 판독 대상 {len(live)} · 제외 {len(got) - len(live)}")
    print(f"  품목 {dict(collections.Counter(r['품목'] for r in got))}")
    print(f"  ○ 로 가려진 문구(전사 때 사람이 가림) {sum('○' in r['문구'] for r in got)}")
    print(f"  🔴 마스킹 — 규칙 축이 바꾼 문구 {sum(r['바뀜'] for r in got)} · 치환 {len(log)}건")
    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for r in got:
                rec = {k: v for k, v in r.items() if k != "바뀜"}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  → {OUT.relative_to(ROOT)}  ({len(got)}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
