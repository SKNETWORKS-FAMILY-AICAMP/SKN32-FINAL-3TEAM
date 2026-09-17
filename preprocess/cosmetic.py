"""preprocess/cosmetic.py — 화장품 원료 API 2종 → **제품 사실**.

  uv run python -m preprocess.cosmetic
  uv run python -m preprocess.cosmetic --dump

원천 `cosmetic_ingredient`(원료성분정보 21,897) · `cosmetic_restricted`(사용제한 원료 31,191).
**받아 두고 읽는 코드가 없었다** (2026-09-09 확인).

🚨 **판정에 직접 쓰이지 않는다.** 원료명은 위법·적법을 가르지 않는다 — 「사용제한 원료를
   썼다」는 표시·광고 위반이 아니라 제조 기준 위반이다. 그래서 층이 「제품 사실」이고,
   쓰임은 **제품 지위 확인**이다(2층 판정이 「표현 + 제품 지위」의 함수이므로).
   🔴 지금 이 데이터를 읽는 판정 경로는 없다. 붙는 자리가 생길 때까지 산출만 해 둔다.

🚨 마스킹 정책이 필요 없다 — 원료명·CAS 번호·함량뿐이고 개인·업체 축이 없다.
   그래도 `apply_policy` 를 부르지 않는다. **부르면 정책이 없어 멈춘다**(D-72).
   부르지 않는 이유를 여기 적어 둔다 — 안 적으면 다음 사람이 「빠뜨린 것」으로 읽는다.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from collect import store

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

SOURCES = {
    "cosmetic_ingredient": (
        "INGR_KOR_NAME",
        "INGR_ENG_NAME",
        "CAS_NO",
        "ORIGIN_MAJOR_KOR_NAME",
        "INGR_SYNONYM",
    ),
    "cosmetic_restricted": (
        "REGULATE_TYPE",
        "INGR_STD_NAME",
        "INGR_ENG_NAME",
        "CAS_NO",
        "INGR_SYNONYM",
        "COUNTRY_NAME",
        "NOTICE_INGR_NAME",
        "PROVIS_ATRCL",
        "LIMIT_COND",
    ),
}
NAME = {"cosmetic_ingredient": "INGR_KOR_NAME", "cosmetic_restricted": "INGR_STD_NAME"}


def _records(directory: str) -> list[dict]:
    def dig(x: object) -> list[dict] | None:
        if isinstance(x, dict):
            for v in x.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
                found = dig(v)
                if found is not None:
                    return found
        return None

    d = RAW / directory
    # 🔴 **디렉터리가 없어도 glob 은 예외를 안 낸다** — 빈 이터레이터를 준다 (2026-09-10).
    #    ⛔ 그래서 원문을 안 받았거나 폴더 이름이 바뀌면 「0행」을 찍고 **성공으로 끝났다.**
    #       원장에는 수가 적혀 있는데 산출물만 조용히 비는, D-149 와 같은 모양이다.
    if not d.exists():
        raise SystemExit(
            f"🔴 {d} 가 없다 — 이 원천의 원문을 이 기기에서 아직 안 받았다.\n"
            f"  먼저: uv run python launcher.py collect {directory} --use U1\n"
            "  🚨 「0행」을 성공으로 찍지 않는다 (D-72)."
        )
    files = store.current_files(d, "*.json")
    if not files:
        raise SystemExit(f"🔴 {d} 에 json 이 한 개도 없다 — 수집이 비었다.")
    out: list[dict] = []
    for p in files:
        got = dig(json.loads(p.read_text(encoding="utf-8")))
        if got:
            out += got
    if not out:
        raise SystemExit(
            f"🔴 {d} 의 파일 {len(files)}개를 읽었는데 **레코드가 0** 이다.\n"
            "  🚨 응답 껍데기가 바뀌어 `dig()` 가 엉뚱한 배열을 집었을 수 있다 — 파일을 열어 본다."
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="화장품 원료 API 2종 → 제품 사실")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    for source, fields in SOURCES.items():
        recs = _records(source)
        rows = []
        for r in recs:
            row = {f: (r.get(f) or "").strip() for f in fields}
            row["층"] = "제품 사실"
            rows.append(store.stamp(row, source))
        key = NAME[source]
        uniq = len({r[key] for r in rows if r[key]})
        empty = sum(1 for r in rows if not r[key])
        print(f"  {source:22} {len(rows):>6}행 · 고유 원료명 {uniq:>6} · 이름 없음 {empty}")
        if source == "cosmetic_restricted":
            kinds = {}
            for r in rows:
                kinds[r["REGULATE_TYPE"]] = kinds.get(r["REGULATE_TYPE"], 0) + 1
            print(f"        규제 구분: {kinds}")
        if args.dump:
            out = store.derived_dir(".") / f"{source}.jsonl"
            with out.open("w", encoding="utf-8", newline="\n") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"        💾 → {out.relative_to(ROOT)}")

    print("\n🚨 판정 경로가 아직 없다 — 제품 지위 확인이 붙을 때 쓴다 (D-153).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
