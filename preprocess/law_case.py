"""preprocess/law_case.py — 판례·재결례 → 5층 반례.

  uv run python -m preprocess.law_case
  uv run python -m preprocess.law_case --dump

원천 `law_go_kr` · `data/raw/law/prec_*.xml`(판례 84) · `decc_*.xml`(재결례 120).
**받아 두고 읽는 코드가 없었다** (2026-09-09 확인).

🚨 둘은 **필드가 다르다.** 같은 `PrecService` 껍데기를 쓰지만 —
     판례   판시사항 · 판결요지 · 참조조문 · 선고일자 · 법원명
     재결례 주문 · 청구취지 · 이유 · 재결요지 · 처분청 · 재결청 · 처분일자
   한 표로 뭉개면 「재결요지」와 「판결요지」가 같은 칸에 들어가 **어느 기관의 판단인지**가
   사라진다. 5층 반례는 「누가 무엇을 뒤집었나」가 요점이라 그 구분이 곧 값이다 (D-167).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import xml.etree.ElementTree as ET

from collect import store

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAW = ROOT / "data" / "raw" / "law"
SOURCE = "law_go_kr"

FIELDS = {
    "prec": (
        "판례정보일련번호",
        "사건명",
        "사건번호",
        "선고일자",
        "선고",
        "법원명",
        "사건종류명",
        "판결유형",
        "판시사항",
        "판결요지",
        "참조조문",
    ),
    "decc": (
        "행정심판례일련번호",
        "사건명",
        "사건번호",
        "처분일자",
        "의결일자",
        "처분청",
        "재결청",
        "재결례유형명",
        "주문",
        "청구취지",
        "이유",
        "재결요지",
    ),
}
KIND = {"prec": "판례", "decc": "재결례"}


def parse(path: pathlib.Path, kind: str) -> dict:
    root = ET.parse(path).getroot()
    row = {"종류": KIND[kind], "파일": path.name, "층": "5층 반례"}
    for f in FIELDS[kind]:
        el = root.find(f".//{f}")
        row[f] = (el.text or "").strip() if el is not None and el.text else ""
    return store.stamp(row, SOURCE)


def main() -> int:
    ap = argparse.ArgumentParser(description="판례·재결례 → 5층 반례")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    out_rows: dict[str, list[dict]] = {}
    for kind in ("prec", "decc"):
        rows = [parse(p, kind) for p in sorted(LAW.glob(f"{kind}_*.xml"))]
        out_rows[kind] = rows
        body = "판결요지" if kind == "prec" else "재결요지"
        filled = sum(1 for r in rows if r[body])
        empty = [r["사건번호"] for r in rows if not r[body]]
        print(f"  {KIND[kind]:4} {len(rows):>4}건 · {body} 있음 {filled} · 없음 {len(empty)}")
        if empty[:3]:
            print(f"        요지 없는 사건: {empty[:3]}{' …' if len(empty) > 3 else ''}")

    if args.dump:
        for kind, rows in out_rows.items():
            out = store.derived_dir(".") / f"law_{kind}.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  💾 {len(rows)}행 → {out.relative_to(ROOT)}")
        print("  🚨 판례와 재결례를 한 파일로 합치지 않았다 — 필드가 다르다 (D-167).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
