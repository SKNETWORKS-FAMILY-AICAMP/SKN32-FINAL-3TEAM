"""annex_audit.py — [별표] 파싱 자동 감사 (S2-04 · D-98 개정).

  uv run python -m scripts.annex_audit              # 전량 감사
  uv run python -m scripts.annex_audit --law 008741
  uv run python -m scripts.annex_audit --update     # 기준선 갱신 (법 개정 시 사람이 판단)

왜 있는가 — 종전 S2-04 는 「2인 수동 대조가 필수다」를 **출력 한 줄과 `needs_review: True`
플래그로만** 두고 있었다. 강제하는 CHECK 도 게이트도 없었다. 아무도 안 해도 아무것도
실패하지 않았으니 **이미 없는 검사였다** (D-146). 그러면서 5법령 243행이라
「전량 대조」는 2인 3.4인시라 앞으로도 안 될 일이었다.

그래서 사람이 하던 일을 셋으로 갈랐다 —
  ① 산수로 되는 것        → 이 감사가 매 수집 직후 자동으로 잰다 (안 부를 수 없다)
  ② 신호가 뜬 행만        → 사람이 본다 (전량도 무작위 표본도 아니다)
  ③ 판정이 필요한 것      → 2인 확인 원장에 남는다 (D-66 은 그대로다)

🚨 **신호는 별표의 성격으로 가른다** (D-167). 2026-09-09 실측 —
   「처분 칸에 글자가 있는데 sanctions 가 비었다」가 243행 중 54행인데,
   **54행 전부가 과징금·과태료·수수료·영양성분 별표**다. 처분 종류가 애초에 없는 표라
   못 읽은 게 아니라 읽을 것이 없다. 전 별표에 같은 임계를 걸면 오탐 54건으로 시작하고,
   오탐으로 시작한 검사는 곧 꺼진다.
   행정처분 기준 별표 둘(008741 별표7 71행 · 013475 별표7 87행)에서는 **0건**이다.

🚨 **기준선이 이 감사의 본체다.** ①과 ②는 지금 값이 깨끗해서 0 을 낸다. 0 을 내는 검사는
   「잘 돼서 0」인지 「못 잡아서 0」인지 구분되지 않는다 (D-170). 그래서 별표별 행 수를
   `scripts/annex_baseline.json` 에 박고 **줄면 실패한다.** 「식품 [별표 7] 처분 칸 197개 중
   160개를 못 잡았다」는 실제 사고가 잡히는 자리가 여기다 — 그날도 수치는 초록이었고
   줄어든 것은 행 수였다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived" / "law_annex"
BASELINE = ROOT / "scripts" / "annex_baseline.json"

# 처분 종류를 담는 별표인지 — 제목으로 가른다
SANCTION_TITLE = "행정처분"


def _cells(row: dict) -> list[str]:
    """처분 칸(3번째 열부터)의 글자. `fragments` 가 원본 셀 조각이다."""
    frags = row.get("fragments") or []
    return ["".join(c) for c in frags[2:]] if len(frags) > 2 else []


def measure(rows: list[dict]) -> dict[str, dict]:
    """별표별로 센다. 판정하지 않는다 — 세기만 한다."""
    out: dict[str, dict] = {}
    for r in rows:
        key = f"{r['law_id']}_{r['kind']}_{r['annex_no']}_{r.get('annex_branch', '00')}"
        st = out.setdefault(
            key,
            {"title": r.get("title", ""), "rows": 0, "mute": 0, "no_article": 0, "inherited": 0},
        )
        st["rows"] += 1
        if r.get("article_inherited"):
            st["inherited"] += 1
        if not (r.get("article") or "").strip():
            st["no_article"] += 1
        if not r.get("sanctions") and any(c.strip() for c in _cells(r)):
            st["mute"] += 1
    return out


def _load(law_id: str | None) -> list[dict]:
    if not DERIVED.exists():
        return []
    files = [DERIVED / f"{law_id}.jsonl"] if law_id else sorted(DERIVED.glob("*.jsonl"))
    rows: list[dict] = []
    for f in files:
        if not f.exists():
            continue
        rows += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows


def judge(stats: dict[str, dict], baseline: dict[str, dict]) -> list[str]:
    """실패 사유를 문장으로 낸다. 빈 목록이면 통과다.

    🔴 **양쪽을 다 돈다** (2026-09-10). ⛔ 종전에는 `stats`(이번에 읽은 것)만 순회해서
       「행이 줄었다」는 잡고 **「별표 파일이 통째로 사라졌다」는 통과**시켰다.
       이 감사의 본체가 「줄면 실패한다」인데 **100% 줄면 통과**하는 모양이었다 (D-149).
    """
    bad: list[str] = []
    for key in sorted(set(baseline) - set(stats)):
        bad.append(
            f"{key} 「{baseline[key].get('title', '')[:24]}」 **기준선에 있는데 산출물에 없다** "
            f"({baseline[key].get('rows', '?')}행 → 0) — 별표가 통째로 빠졌다. "
            "법에서 삭제됐으면 --update, 아니면 파서나 수집이 잃은 것이다"
        )
    for key, st in sorted(stats.items()):
        is_sanction = SANCTION_TITLE in st["title"]
        if is_sanction and st["mute"]:
            bad.append(
                f"{key} 「{st['title'][:24]}」 처분 칸에 글자가 있는데 못 읽은 행 {st['mute']}건 "
                f"— extract_sanction 의 처분 용어 목록을 의심한다"
            )
        if is_sanction and st["no_article"]:
            bad.append(
                f"{key} 「{st['title'][:24]}」 상속 후에도 조문이 없는 행 {st['no_article']}건 "
                f"— 4층 라벨이 근거를 잃는다"
            )
        base = baseline.get(key)
        if base is None:
            bad.append(
                f"{key} 「{st['title'][:24]}」 기준선에 없다 — 새 별표다. --update 로 등재한다"
            )
        elif st["rows"] < base["rows"]:
            bad.append(
                f"{key} 「{st['title'][:24]}」 행이 줄었다 {base['rows']} → {st['rows']} "
                f"— 법 개정이면 --update, 아니면 파서가 잃은 것이다"
            )
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="[별표] 파싱 자동 감사 (S2-04 · D-98)")
    ap.add_argument("--law", default=None, help="법령 ID (생략하면 전량)")
    ap.add_argument("--update", action="store_true", help="기준선을 지금 값으로 갱신한다")
    args = ap.parse_args()

    rows = _load(args.law)
    if not rows:
        print("감사할 파싱 산출물이 없다 — collect.law_annex 를 먼저 돌린다", file=sys.stderr)
        return 1

    stats = measure(rows)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}

    print(f"{'별표':28}{'행':>5}{'조문빔':>7}{'물려받음':>9}{'못읽은칸':>9}")
    for key, st in sorted(stats.items()):
        mark = " 🔴" if (SANCTION_TITLE in st["title"] and (st["mute"] or st["no_article"])) else ""
        print(
            f"{key:28}{st['rows']:>5}{st['no_article']:>7}{st['inherited']:>9}{st['mute']:>9}{mark}"
        )

    if args.update:
        # 🚨 `--update` 는 `judge()` 를 **건너뛴다.** 그래서 사라진 별표를 먼저 보여 준다 —
        #    ⛔ `{**baseline, **now}` 는 낡은 키를 안 지우므로, 말없이 갱신하면
        #       「사라진 별표」가 기준선에 영원히 남아 매번 실패한다. 사람이 보고 정한다.
        gone = sorted(set(baseline) - set(stats))
        if gone:
            print(f"\n🚨 **기준선에만 있는 별표 {len(gone)}건** — 갱신해도 기준선에서 안 지워진다:")
            for k in gone:
                print(
                    f"     {k} 「{baseline[k].get('title', '')[:24]}」 {baseline[k].get('rows')}행"
                )
            print("     법에서 삭제된 것이면 scripts/annex_baseline.json 에서 손으로 뺀다.")
        now = {k: {"title": v["title"], "rows": v["rows"]} for k, v in stats.items()}
        merged = {**baseline, **now}
        BASELINE.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\n💾 기준선 {len(merged)}건 → {BASELINE.relative_to(ROOT)}")
        return 0

    bad = judge(stats, baseline)
    if bad:
        print("\n🚨 감사 실패 —", file=sys.stderr)
        for b in bad:
            print(f"   · {b}", file=sys.stderr)
        return 1

    print(f"\n✅ 별표 {len(stats)}건 · {sum(s['rows'] for s in stats.values())}행 — 사람이 볼 행 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
