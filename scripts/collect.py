"""collect.py — 제재 사례 수집과 범위 판정 집계 (D-65).

launcher는 얇은 껍데기이고 로직은 여기 있다 (D-51).

  python scripts/collect.py schema           # 레코드 계약을 출력한다
  python scripts/collect.py validate         # 수집 레코드가 계약을 지키는지 검사
  python scripts/collect.py report           # ★ D-65 범위 판정 집계 (9/17 판정용)

★ 이 파일의 핵심은 수집기가 아니라 **레코드 계약**이다.
   T1이 어떤 소스에서 무엇을 채워야 하는지가 CASE_FIELDS에 정의돼 있고,
   그 계약만 지키면 9/17 범위 판정이 `report` 출력 하나로 끝난다 (D-65).

표준 라이브러리만 쓴다 — uv 환경이 서기 전에도, 팀원 누구의 OS에서도 돈다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# ── 거버넌스 (D-19) — 위치가 곧 게이트. G3 자료만 여기서 읽는다.
DATA_DIR = Path("data/g3/cases")

# ── 레코드 계약 ────────────────────────────────────────────────────────────
CASE_FIELDS = {
    "case_id": "str   · 사건 식별자 (소스 내 고유)",
    "source": "str   · ftc_decisions | mfds_action | ...  (data_sources.yaml 키)",
    "source_url": "str   · 원문 URL",
    "fragment_id": "str   · 🚨 필수 — 캐스케이드 삭제 경로 (D-20)",
    "decided_date": "str   · YYYY-MM-DD · 처분·의결일",
    "law": "str   · 표시광고법 | 식품표시광고법 | 화장품법",
    "category": "str   · 일반 | 식품 | 건기식 | 화장품",
    "violation_types": "list · 위법 유형 (다중). VIOLATION_TYPES 참조",
    "has_ad_text": "bool  · 🚨 광고 문구 원문이 인용돼 있는가",
    "ad_text_before": "str|null · 시정 전 문구 (마스킹 후 — D-17)",
    "ad_text_after": "str|null · 시정 후 문구",
}

# 현행 3법령의 기존 위법 유형 — 30건 미달이 하나라도 있으면 확장 금지 (D-65)
VIOLATION_TYPES = [
    "질병_예방치료_표방",
    "건강기능식품_오인",
    "의약품_오인",
    "거짓_과장",
    "소비자_기만",
    "후기_체험기_기만",
]

# 편입 후보 — 새 법령이 아니라 표시광고법 안의 유형이라 라우팅이 바뀌지 않는다 (D-65)
CANDIDATE_TYPES = [
    "추천_보증_뒷광고",
    "부당_비교광고",
    "실증책임_위반",
]

MIN_SAMPLES = 30  # D-40 — 유형별 최소 표본. 미달은 「측정 불가」


def load_cases(path: Path = DATA_DIR):
    """data/g3/cases/*.jsonl 을 읽는다. 한 줄에 레코드 하나."""
    if not path.exists():
        return []
    rows = []
    for f in sorted(path.glob("*.jsonl")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"X {f.name}:{i}  JSON 파싱 실패 — {e}")
    return rows


def cmd_schema(_):
    print("레코드 계약 — data/g3/cases/*.jsonl · 한 줄에 레코드 하나\n")
    w = max(len(k) for k in CASE_FIELDS)
    for k, v in CASE_FIELDS.items():
        print(f"  {k:<{w}}  {v}")
    print(f"\n기존 위법 유형 ({len(VIOLATION_TYPES)})")
    for t in VIOLATION_TYPES:
        print(f"  · {t}")
    print(f"\n편입 후보 유형 ({len(CANDIDATE_TYPES)}) — 표시광고법 내부, 라우팅 불변")
    for t in CANDIDATE_TYPES:
        print(f"  · {t}")


def cmd_validate(_):
    cases = load_cases()
    if not cases:
        print(f"! {DATA_DIR} 에 레코드가 없습니다.")
        return 1
    required = list(CASE_FIELDS)
    known = set(VIOLATION_TYPES) | set(CANDIDATE_TYPES)
    bad = 0
    for i, c in enumerate(cases, 1):
        miss = [k for k in required if k not in c]
        if miss:
            print(f"X #{i} {c.get('case_id', '?')}  누락 필드 — {', '.join(miss)}")
            bad += 1
        if not c.get("fragment_id"):
            print(
                f"X #{i} {c.get('case_id', '?')}  fragment_id 없음 — 캐스케이드 삭제가 깨집니다 (D-20)"
            )
            bad += 1
        for t in c.get("violation_types", []):
            if t not in known:
                print(f"! #{i} {c.get('case_id', '?')}  미등록 유형 — {t}")
    print(f"\n{'O' if bad == 0 else 'X'} 레코드 {len(cases)}건 · 오류 {bad}건")
    return 0 if bad == 0 else 1


def cmd_report(_):
    cases = load_cases()
    n = len(cases)
    print("=" * 68)
    print("  D-65 범위 판정 집계        판정일 2026-09-17 (3W 마감 · 인코더 학습 전)")
    print("=" * 68)
    if not n:
        print(f"\n! {DATA_DIR} 에 레코드가 없습니다. 수집 후 다시 실행하십시오.")
        return 1

    by_type = Counter()
    for c in cases:
        by_type.update(c.get("violation_types", []))

    # ── ② ③ 건수보다 중요한 두 숫자 (D-65)
    with_text = sum(1 for c in cases if c.get("has_ad_text"))
    with_pair = sum(1 for c in cases if c.get("ad_text_before") and c.get("ad_text_after"))
    # 유형별 「실질」 = 문구 원문이 있는 것만
    eff = Counter()
    for c in cases:
        if c.get("has_ad_text"):
            eff.update(c.get("violation_types", []))

    print(f"\n[1] 총 사례            {n}건")
    print(
        f"[2] 광고 문구 원문 인용  {with_text}건 ({with_text / n * 100:.1f}%)"
        "   <- 없으면 학습 데이터가 되지 않는다"
    )
    print(
        f"[3] 시정 전/후 페어      {with_pair}건 ({with_pair / n * 100:.1f}%)"
        "   <- 파인튜닝 데이터의 크기 (D-26)"
    )

    print(f"\n[4] 유형별 건수 — 기준 {MIN_SAMPLES}건 (D-40)")
    print(f"    {'유형':<24}{'전체':>6}{'실질':>7}   판정")
    blocked = []
    for t in VIOLATION_TYPES:
        tot, e = by_type.get(t, 0), eff.get(t, 0)
        ok = e >= MIN_SAMPLES
        if not ok:
            blocked.append(t)
        print(f"    {t:<24}{tot:>6}{e:>7}   {'O 측정 가능' if ok else 'X 측정 불가'}")

    print("\n[5] 편입 후보 유형")
    admit, defer = [], []
    for t in CANDIDATE_TYPES:
        tot, e = by_type.get(t, 0), eff.get(t, 0)
        (admit if e >= MIN_SAMPLES else defer).append((t, tot, e))
        print(f"    {t:<24}{tot:>6}{e:>7}   {'O 편입 가능' if e >= MIN_SAMPLES else 'X 표본 부족'}")

    print("\n[6] 연도 분포")
    yrs = Counter((c.get("decided_date") or "????")[:4] for c in cases)
    for y in sorted(yrs):
        print(f"    {y}  {yrs[y]:>5}")

    print("\n[7] 카테고리 분포")
    for k, v in Counter(c.get("category", "?") for c in cases).most_common():
        print(f"    {k:<12}{v:>5}")

    # ── 판정 (D-65)
    print("\n" + "-" * 68)
    if blocked:
        print("! 확장 금지 — 기존 유형에 표본 미달이 있습니다")
        for t in blocked:
            print(f"    X {t}  실질 {eff.get(t, 0)}건 / {MIN_SAMPLES}")
        print("\n  있는 것도 측정하지 못하는 상태에서 범위를 넓히지 않습니다 (D-65).")
        print("  먼저 기존 유형의 표본을 채우십시오.")
    elif admit:
        print("O 편입 가능 — 아래 유형만 편입합니다 (법령이 아니라 유형 단위)")
        for t, _tot, e in admit:
            print(f"    O {t}  실질 {e}건")
        if defer:
            print("\n  아래는 편입하지 않고 「측정 불가 유형」으로 기록만 합니다.")
            for t, _tot, e in defer:
                print(f"    - {t}  실질 {e}건 / {MIN_SAMPLES}")
    else:
        print("O 기존 유형은 전부 측정 가능하나, 편입 후보 중 기준을 넘는 유형이 없습니다.")
        print("  현행 범위를 유지하고 깊이(불가 사유 라벨 · 시정 페어)에 투입합니다.")
    print("-" * 68)
    return 0


# ── 수집 어댑터 ────────────────────────────────────────────────────────────
def cmd_fetch(args):
    """TODO(T1): 소스별 수집. data_sources.yaml 에 등록되지 않았거나
    grade 가 G1이면 실행을 거부한다 (D-15).

      ftc_decisions  공정거래위원회 의결서   (표시광고법)
      mfds_action    식약처 행정처분         (식품표시광고법 · 화장품법)

    🚨 업체명·상표·대표자명은 수집 직후 즉시 마스킹하고 원문을 보관하지 않는다 (D-17).
    """
    raise SystemExit("collect fetch: T1 구현 예정 — 위 docstring이 계약이다")


def main():
    p = argparse.ArgumentParser(description="제재 사례 수집 · 범위 판정 집계 (D-65)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schema", help="레코드 계약 출력").set_defaults(fn=cmd_schema)
    sub.add_parser("validate", help="레코드 계약 검증").set_defaults(fn=cmd_validate)
    sub.add_parser("report", help="D-65 범위 판정 집계").set_defaults(fn=cmd_report)
    sub.add_parser("fetch", help="소스별 수집 (T1 구현 예정)").set_defaults(fn=cmd_fetch)
    a = p.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
