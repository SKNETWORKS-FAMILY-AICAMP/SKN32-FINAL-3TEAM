"""라벨 시트 ↔ 엑셀(CSV) — 🚨 **사람은 번호만 채운다** (2026-09-10).

  uv run python scripts/label_sheet.py export data/derived/mfds_guide_labelsheet.jsonl --who 권소라
  uv run python scripts/label_sheet.py import build/labels/권소라.csv

──────────────────────────────────────────────────────────────
⛔ 종전에는 **JSONL 을 손으로 고치게** 했다. 다섯 사람이 각자 편집기로 열어
   `"확정유형": ["질병_예방치료_표방"]` 을 타이핑한다 — 다음이 전부 실제로 나는 사고다.

     · 대괄호·따옴표를 빠뜨려 그 줄이 **JSON 이 아니게** 된다
     · 유형 이름을 한 글자 틀린다 (`질병_예방치료표방`) — 조용히 다른 라벨이 된다
     · `문구` 칸을 건드려 **키가 어긋난다** — 취합에서 짝이 안 맞는다

★ 그래서 **채우는 칸을 하나로 줄인다.** `유형번호` 에 1~8 만 적는다.
  번호는 **판정 순서 그대로**다 — 지시서 §3 을 위에서부터 읽다가 걸린 번호를 적으면 된다.

🚨 **의존성을 늘리지 않는다.** openpyxl 을 넣으면 팀 다섯이 전부 re-lock 을 겪는다
   (`pyproject.toml` 주석이 경고하는 자리다). CSV 를 **UTF-8 BOM** 으로 쓰면
   Windows 엑셀이 그대로 연다.

🔴 **되돌릴 때 문구를 대조한다.** `문구` 열을 고치면 가져오기가 **멈춘다** —
   키가 어긋난 라벨은 취합에서 짝을 못 찾고 조용히 사라지기 때문이다 (D-160).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "build" / "labels"  # 🚨 data/ 가 아니다 — 작업용 사본은 커밋 축 밖이다

#: 🔴 **번호 = 지시서 §3 의 판정 순서.** 두 곳이 갈리면 사람이 딴 라벨을 적는다 (D-99).
#:    ⛔ 순서를 바꾸려면 지시서와 **같은 커밋에서** 바꾼다.
TYPES: tuple[str, ...] = (
    "질병_예방치료_표방",  # 1
    "의약품_오인",  # 2
    "건강기능식품_오인",  # 3
    "후기_체험기_기만",  # 4
    "소비자_기만",  # 5
    "부당_비교광고",  # 6
    "비방광고",  # 7
    "거짓_과장",  # 8
)
HEADER = ["행", "문구", "후보유형", "유형번호", "붙인이", "붙인날", "지문"]


def _text(r: dict) -> str:
    """시트마다 문구 칸 이름이 다르다 — guide 는 `문구`, casebook 은 `글`."""
    for f in ("문구", "글"):
        v = r.get(f)
        if v:
            return str(v)
    return ""


def _fp(text: str) -> str:
    """문구 지문 — 되돌릴 때 **다른 칸을 고쳤는지** 본다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _rows(sheet: pathlib.Path) -> list[dict]:
    if not sheet.exists():
        raise SystemExit(
            f"🔴 {sheet} 가 없다.\n"
            "  먼저 시트를 뽑는다 — 지시서 §0:\n"
            "    uv run python launcher.py extract mfds_special_use_guide --sheet 90 --min-len 20"
        )
    return [json.loads(x) for x in sheet.read_text(encoding="utf-8").splitlines() if x.strip()]


def pick(part: str | None, n: int) -> list[int]:
    """`1-40,93-144` → 1부터 세는 행 번호들. 🚨 **구간을 여럿 받는다** (2026-09-10).

    ⛔ 하나만 받으면 「전원이 겹쳐 붙이는 공통 블록 + 각자 고유 구간」을 못 만든다.
       그래서 12건씩만 겹치게 됐는데, **κ 를 12건에서 재는 것**은 이 프로젝트 자기 기준
       (D-40 · 30건 미만 측정 불가)에 안 맞는다. 겹치기도 30 이상이어야 뜻이 있다.
    """
    if not part:
        return list(range(1, n + 1))
    got: list[int] = []
    for seg in part.split(","):
        seg = seg.strip()
        if not seg:
            continue
        a, _, b = seg.partition("-")
        lo, hi = int(a), int(b or a)
        if not (1 <= lo <= hi <= n):
            raise SystemExit(f"🔴 구간 {seg!r} 이 시트 범위(1~{n}) 밖이다")
        got += [i for i in range(lo, hi + 1) if i not in got]
    return sorted(got)


def export(sheet: pathlib.Path, who: str, part: str | None) -> int:
    rows = _rows(sheet)
    idx = pick(part, len(rows))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{who}.csv"
    # 🚨 BOM 을 붙인다 — 없으면 Windows 엑셀이 한글을 깨서 연다.
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i in idx:
            r = rows[i - 1]
            t = _text(r)
            w.writerow([i, t, " / ".join(r.get("후보유형") or []), "", who, "", _fp(t)])
    legend = OUT_DIR / "유형번호표.csv"
    with legend.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "유형", "메모"])
        for n, t in enumerate(TYPES, 1):
            w.writerow([n, t, "판정 순서 — 위에서부터 보다가 걸리면 멈춘다"])
        w.writerow(["(비움)", "모르겠다", "🚨 빈칸은 실패가 아니라 판단이다"])
    print(f"  → {out.relative_to(ROOT)}  ({len(idx)}행)")
    print(f"  → {legend.relative_to(ROOT)}")
    print("\n  채우는 칸은 **`유형번호` 하나**다. 1~8, 둘이면 `1,5` 처럼 쉼표로.")
    print("  🚨 `문구`·`지문` 열은 건드리지 않는다 — 고치면 가져오기가 멈춘다.")
    return 0


def load_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        got = list(csv.DictReader(f))
    if not got or set(HEADER) - set(got[0]):
        raise SystemExit(f"🔴 {path} 의 머리글이 다르다 — export 로 만든 파일이어야 한다")
    return got


def parse_no(raw: str, line: int) -> list[str]:
    """`1,5` → 라벨 둘. 🚨 못 읽는 값은 **멈춘다** — 조용히 버리면 그 사람의 판단이 사라진다."""
    got = []
    for tok in str(raw).replace(" ", "").split(","):
        if not tok:
            continue
        if not tok.isdigit() or not 1 <= int(tok) <= len(TYPES):
            raise SystemExit(
                f"🔴 {line}행의 유형번호 {tok!r} 을 못 읽는다 — 1~{len(TYPES)} 만 쓴다.\n"
                "  모르겠으면 **비워 둔다.** 빈칸은 실패가 아니라 판단이다."
            )
        lab = TYPES[int(tok) - 1]
        if lab not in got:
            got.append(lab)
    return got


def import_(csv_path: pathlib.Path, sheet: pathlib.Path, day: str) -> int:
    rows = _rows(sheet)
    filled = load_csv(csv_path)
    tampered, out_rows, n = [], [], 0
    for rec in filled:
        i = int(rec["행"])
        base = dict(rows[i - 1])
        # 🔴 **세 개를 맞춘다** — 시트의 문구 · CSV 의 문구 · 지문 (2026-09-10 정정).
        #    ⛔ 처음에 시트↔지문만 봤다. 그러면 사람이 CSV 의 `문구` 칸을 고쳐도
        #       지문이 그대로라 **그냥 통과한다** — 정확히 막으려던 것을 못 막았다.
        #       반대 대조로 잡았다: 문구를 고쳐 넣었는데 4건이 그대로 들어갔다.
        if not (_fp(_text(base)) == rec["지문"] == _fp(rec["문구"])):
            tampered.append(i)
            continue
        labs = parse_no(rec.get("유형번호") or "", i)
        if not labs:
            continue
        base["확정유형"] = labs
        base["붙인이"] = (rec.get("붙인이") or "").strip()
        base["붙인날"] = (rec.get("붙인날") or "").strip() or day
        if not base["붙인이"]:
            raise SystemExit(f"🔴 {i}행에 `붙인이` 가 없다 — 누가 붙였는지가 라벨의 일부다 (D-66)")
        out_rows.append(base)
        n += 1
    if tampered:
        raise SystemExit(
            f"🔴 `문구` 열이 바뀐 행 {len(tampered)}개 — {tampered[:8]}\n"
            "  🚨 문구가 키다. 고치면 취합에서 짝을 못 찾고 **조용히 사라진다** (D-160).\n"
            "  → 그 행을 원래대로 되돌리거나, export 를 다시 받아 채운다."
        )
    who = (filled[0].get("붙인이") or "이름없음").strip()
    out = ROOT / "data" / "derived" / "labels" / f"{who}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  → {out.relative_to(ROOT)}  ({n}건 · 빈칸 {len(filled) - n}건)")
    print("  🚨 빈칸은 **안 들어갔다.** 버린 것이 아니라 판단이 없는 것이다.")
    print("\n  취합 — uv run python scripts/label_merge.py data/derived/labels/*.jsonl")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="라벨 시트 ↔ 엑셀(CSV) — 사람은 번호만 채운다")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="시트 → 채울 CSV")
    e.add_argument("sheet", type=pathlib.Path)
    e.add_argument("--who", required=True, help="붙이는 사람 이름 — 파일명이 된다")
    e.add_argument("--part", help="맡은 구간 — 여럿 가능 (예: 1-40,93-144)")
    i = sub.add_parser("import", help="채운 CSV → data/derived/labels/<이름>.jsonl")
    i.add_argument("csv", type=pathlib.Path)
    i.add_argument("--sheet", type=pathlib.Path, required=True, help="export 에 쓴 원본 시트")
    i.add_argument("--day", default="", help="붙인날 기본값 (비면 CSV 값을 쓴다)")
    a = ap.parse_args()
    if a.cmd == "export":
        return export(a.sheet, a.who, a.part)
    return import_(a.csv, a.sheet, a.day)


if __name__ == "__main__":
    sys.exit(main())
